#!/usr/bin/python3
"""Manage wlan0 profiles over a group-restricted, systemd-activated Unix socket."""
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import dbus

NM = "org.freedesktop.NetworkManager"
BASE = "/org/freedesktop/NetworkManager"
WIFI = "802-11-wireless"
SEC = WIFI + "-security"
AP = "1d1db196-d1db-4dc8-9719-7c0e5c861b69"
EDU = "c9251384-c34a-4d92-a120-73015be69280"
CA = "/etc/formula-manager/tul-eduroam-ca.pem"
MARKER = Path("/var/lib/formula-wifi-profiles/initialized")
TEST_FILE = MARKER.with_name("eduroam-test.json")
TEST_UNIT = "formula-eduroam-test.service"


class Invalid(ValueError):
    pass


def store_test(result):
    tmp=TEST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(result),encoding="utf-8")
    tmp.replace(TEST_FILE)


def last_test():
    if not TEST_FILE.exists():
        return None
    result=json.loads(TEST_FILE.read_text(encoding="utf-8"))
    if result["state"]=="running":
        state=subprocess.run(["systemctl","show","-p","ActiveState","--value",TEST_UNIT],
                             capture_output=True,text=True,timeout=4).stdout.strip()
        if state not in ("active","activating","deactivating","reloading"):
            return {**result,"state":"interrupted","message":"Test byl přerušen. Spusť ověření znovu."}
    return result


def attempt(wait,*args):
    return subprocess.run(["/usr/bin/nmcli","--wait",str(wait),*args],capture_output=True,
                          text=True,timeout=wait+5,env={**os.environ,"LC_ALL":"C"})


def failure_message(since):
    # Report only recognized supplicant events. Never send raw logs or identities to the browser.
    events=subprocess.run(["journalctl","-b","-u","wpa_supplicant.service","--since",f"@{since:.6f}",
                           "-n","180","-o","cat","--no-pager"],capture_output=True,text=True,timeout=4)
    lines="\n".join(s for s in events.stdout.splitlines() if "wlan0:" in s)
    if "CTRL-EVENT-EAP-TLS-CERT-ERROR" in lines:
        return "Pi odmítlo certifikát ověřovacího serveru. Zkontroluj čas na Pi a profil TUL."
    if "CTRL-EVENT-EAP-FAILURE" in lines:
        return "Ověření 802.1X selhalo. Zkontroluj školní jméno a heslo TUL pro vzdálený přístup."
    if "CTRL-EVENT-EAP-SUCCESS" in lines:
        return "Pi zaznamenalo úspěch 802.1X, ale nedokončilo síťové připojení. Zkontroluj přidělení IP adresy."
    return "Spojení s eduroamem se nedokončilo. Platnost účtu se nepodařilo potvrdit."


def run_eduroam_test():
    result={"started":int(time.time()*1000),"state":"running","message":"Vyhledávám eduroam."}
    store_test(result)
    checkpoint=None
    original=""
    try:
        bus=dbus.SystemBus()
        manager=dbus.Interface(bus.get_object(NM,BASE),NM)
        device=manager.GetDeviceByIpIface("wlan0")
        original=nm("-g","GENERAL.CON-UUID","device","show","wlan0")
        uuid.UUID(original)  # Only interrupt a connection that can be restored by its UUID.
        previous=nm("-g",WIFI+".ssid","connection","show","uuid",original)
        time.sleep(2)  # Let the web client receive the acknowledgement before a radio switch.
        if original!=nm("-g","GENERAL.CON-UUID","device","show","wlan0"):
            raise Invalid("Připojení se právě změnilo. Spusť test znovu.")
        # A NetworkManager-owned timeout also restores wlan0 if the worker exits unexpectedly.
        mode=nm("-g",WIFI+".mode","connection","show","uuid",original)
        if mode=="ap" or original==EDU:
            checkpoint=manager.CheckpointCreate([device],dbus.UInt32(100),dbus.UInt32(0))
            attempt(8,"device","disconnect","wlan0").check_returncode()
        scan=attempt(15,"--escape","no","-g","SSID","device","wifi","list","ifname","wlan0","--rescan","yes")
        scan.check_returncode()
        if "eduroam" not in scan.stdout.splitlines():
            result.update(state="unavailable",message="Pi v dosahu nenašlo eduroam. Účet ověř v místě s pokrytím.")
        else:
            if checkpoint is None:
                if original!=nm("-g","GENERAL.CON-UUID","device","show","wlan0"):
                    raise Invalid("Připojení se během hledání změnilo. Spusť test znovu.")
                checkpoint=manager.CheckpointCreate([device],dbus.UInt32(100),dbus.UInt32(0))
            store_test({**result,"message":"Ověřuji přihlášení 802.1X a přidělení IP adresy."})
            since=time.time()
            activation=attempt(40,"connection","up","uuid",EDU,"ifname","wlan0")
            if activation.returncode==0 and nm("-g","GENERAL.CON-UUID","device","show","wlan0")==EDU:
                addresses=nm("--escape","no","-g","IP4.ADDRESS","device","show","wlan0").splitlines()
                if not addresses:
                    addresses=[v for v in nm("--escape","no","-g","IP6.ADDRESS","device","show","wlan0").splitlines()
                               if v and not v.lower().startswith("fe80:")]
                if addresses:
                    result.update(state="verified",message="Přihlášení k eduroamu ověřeno.",ip=addresses[0].split("/")[0])
                else:
                    result.update(state="failed",message="Pi aktivovalo profil, ale nezískalo použitelnou IP adresu.")
            else:
                result.update(state="failed",message=failure_message(since))
    except Invalid as exc:
        result.update(state="failed",message=str(exc))
    except (ValueError,OSError,subprocess.SubprocessError,dbus.DBusException):
        result.update(state="failed",message="Test se nepodařilo dokončit. Zkontroluj stav Wi-Fi a zkus to znovu.")
    finally:
        if checkpoint is not None:
            store_test({**result,"state":"running","message":"Vracím Pi na původní síť."})
            restored=False
            try:
                manager.CheckpointRollback(checkpoint,timeout=25)
            except dbus.DBusException:
                pass
            try:
                def on_original():
                    return (nm("-g","GENERAL.CON-UUID","device","show","wlan0")==original and
                            nm("-g","GENERAL.STATE","device","show","wlan0").startswith("100"))
                for _ in range(20):
                    if on_original():
                        restored=True
                        break
                    time.sleep(.5)
                if not restored:
                    attempt(22,"connection","up","uuid",original,"ifname","wlan0")
                    restored=on_original()
            except (OSError,subprocess.SubprocessError):
                pass
            result["restored"]=restored
            result["previous"]=previous
        result["finished"]=int(time.time()*1000)
        store_test(result)


def nm(*args):
    return subprocess.run(["/usr/bin/nmcli","--wait","5",*args],check=True,
                          capture_output=True,text=True,timeout=7).stdout.strip()


def field(data, name, limit):
    value = data.get(name)
    if not isinstance(value,str) or not value or len(value.encode()) > limit or any(ord(c)<32 for c in value):
        raise Invalid("Zkontroluj pole " + {"ssid":"název sítě","password":"heslo","identity":"školní účet"}[name] + ".")
    return value


def new_settings(kind, data, priority, pending=False):
    uid = EDU if kind=="eduroam" else AP if kind=="ap" else str(uuid.uuid4())
    ssid = "eduroam" if kind=="eduroam" else "formula69" if kind=="ap" else field(data,"ssid",32)
    if ssid=="eduroam" and kind!="eduroam":
        raise Invalid("Pro eduroam vyber typ připojení eduroam.")
    config = {
        "connection": {"id":"formula69-fallback" if kind=="ap" else ssid, "uuid":uid, "type":WIFI,
                       "interface-name":"wlan0","autoconnect":dbus.Boolean(not pending),
                       "autoconnect-priority":dbus.Int32(priority)},
        WIFI: {"ssid":dbus.ByteArray(ssid.encode()),"mode":"ap" if kind=="ap" else "infrastructure"},
        "ipv4":{"method":"auto"},"ipv6":{"method":"auto"}
    }
    if kind=="eduroam":
        identity = "anonymous@tul.cz" if pending else field(data,"identity",253).strip()
        if not re.fullmatch(r"[^@\s]+@tul\.cz",identity,re.IGNORECASE):
            raise Invalid("Zadej celé školní jméno ve tvaru jmeno.prijmeni@tul.cz.")
        eap = {"eap":dbus.Array(["peap"],signature="s"),"phase2-auth":"mschapv2","identity":identity,
               "anonymous-identity":"anonymous@tul.cz","domain-match":"radius1.tul.cz;radius2.tul.cz",
               "ca-cert":dbus.ByteArray(("file://"+CA+"\0").encode())}
        if not pending:
            eap["password"] = field(data,"password",512)
        config["802-1x"] = eap
        config[SEC] = {"key-mgmt":"wpa-eap"}
    elif kind in ("personal","sae","ap"):
        pw = field(data,"password",128)
        if kind=="sae":
            valid = len(pw.encode())<=63
        else:
            valid = 8<=len(pw.encode())<=63 or bool(re.fullmatch("[0-9a-fA-F]{64}",pw))
        if not valid:
            raise Invalid("Zkontroluj délku hesla pro zvolený typ Wi-Fi.")
        config[SEC] = {"key-mgmt":"sae" if kind=="sae" else "wpa-psk","psk":pw}
        if kind=="ap":
            config[WIFI].update(band="bg",channel=dbus.UInt32(6))
            config[WIFI]["ap-isolation"]=dbus.Int32(1)
            config[SEC].update(proto=dbus.Array(["rsn"],signature="s"),
                               pairwise=dbus.Array(["ccmp"],signature="s"),group=dbus.Array(["ccmp"],signature="s"))
            config["ipv4"]={"method":"shared","never-default":dbus.Boolean(True),
                            "address-data":dbus.Array([dbus.Dictionary({"address":"10.69.0.1","prefix":dbus.UInt32(24)},signature="sv")],signature="a{sv}")}
            config["ipv6"]={"method":"disabled"}
    elif kind!="open":
        raise Invalid("Neznámý typ Wi-Fi.")
    return config


class Profiles:
    def __init__(self):
        self.bus = dbus.SystemBus()
        self.settings = dbus.Interface(self.bus.get_object(NM,BASE+"/Settings"),NM+".Settings")

    def entries(self):
        result=[]
        for path in self.settings.ListConnections():
            conn=dbus.Interface(self.bus.get_object(NM,path),NM+".Settings.Connection")
            props=conn.GetSettings()
            c=props["connection"]
            if c.get("type")!=WIFI or c.get("interface-name","") not in ("","wlan0"):
                continue
            enabled=bool(c.get("autoconnect",True))
            uid=str(c["uuid"])
            row=dict(id=uid,ssid=bytes(props[WIFI]["ssid"]).decode("utf-8","replace"),
                     name=str(c["id"]),ap=props[WIFI].get("mode")=="ap",enabled=enabled,
                     eduroam=uid==EDU,priority=int(c.get("autoconnect-priority",0)))
            result.append((row,conn))
        return sorted(result,key=lambda item:(-item[0]["priority"],item[0]["id"]))

    def view(self):
        active=nm("-g","GENERAL.CON-UUID","device","show","wlan0")
        return {"profiles":[dict(row,active=row["id"]==active) for row,_ in self.entries()],"eduroam_test":last_test()}

    def rank(self, order):
        current={r["id"]:r["priority"] for r,_ in self.entries()}
        if len(order)!=len(current) or set(order)!=set(current) or len(order)>1800:
            raise Invalid("Seznam sítí se změnil. Obnov nastavení.")
        changed=[]
        try:
            for i,uid in enumerate(order):
                priority=999-i
                if current[uid]!=priority:
                    nm("connection","modify","uuid",uid,"connection.autoconnect-priority",str(priority))
                    changed.append(uid)
        except Exception:
            for uid in reversed(changed):
                nm("connection","modify","uuid",uid,"connection.autoconnect-priority",str(current[uid]))
            raise

    def initialize(self):
        if MARKER.exists():
            return
        rows=[r for r,_ in self.entries()]
        if not any(r["ssid"]=="eduroam" for r in rows):
            self.settings.AddConnection(new_settings("eduroam",{},0,pending=True))
        rows=self.view()["profiles"]
        def initial(row):
            if row["active"] and not row["ap"] and not row["eduroam"]: return 0
            if row["ssid"]=="eduroam": return 1
            if row["id"]==AP: return 2
            return 3
        self.rank([r["id"] for r in sorted(rows,key=initial)])
        MARKER.parent.mkdir(mode=0o700,exist_ok=True)
        MARKER.touch(mode=0o600)

    def run(self, data):
        op=data.get("op")
        if op=="list":
            return self.view()
        entries=self.entries()
        rows=[r for r,_ in entries]
        ids=[r["id"] for r in rows]
        if data.get("before")!=ids:
            raise Invalid("Seznam sítí se změnil. Obnov nastavení.")
        if (last_test() or {}).get("state")=="running":
            if op=="test-eduroam":
                return self.view()
            raise Invalid("Probíhá ověření eduroamu. Počkej na návrat k původní síti.")
        if op=="test-eduroam":
            if EDU not in ids or not rows[ids.index(EDU)]["enabled"]:
                raise Invalid("Nejprve ulož přihlašovací údaje eduroamu.")
            store_test({"state":"running","started":int(time.time()*1000),"message":"Spouštím test eduroamu."})
            subprocess.run(["systemctl","start",TEST_UNIT],check=True,timeout=6)
            return self.view()
        if op=="order":
            order=data.get("order")
            if not isinstance(order,list) or not all(isinstance(s,str) for s in order):
                raise Invalid("Neplatné pořadí.")
            self.rank(order)
        elif op=="remove":
            uid=data.get("id")
            if uid not in ids:
                raise Invalid("Profil nebyl nalezen.")
            entries[ids.index(uid)][1].Delete()
            if uid==EDU:
                TEST_FILE.unlink(missing_ok=True)
        elif op=="save":
            kind=data.get("kind")
            if kind not in ("personal","sae","open","eduroam","ap"):
                raise Invalid("Neznámý typ Wi-Fi.")
            if kind=="eduroam" and EDU in ids:
                row,conn=entries[ids.index(EDU)]
                conn.Update(new_settings(kind,data,row["priority"]))
                TEST_FILE.unlink(missing_ok=True)
            else:
                config=new_settings(kind,data,-998)
                ssid=bytes(config[WIFI]["ssid"]).decode()
                if any(r["ssid"]==ssid and r["ap"]==(kind=="ap") for r in rows):
                    raise Invalid("Tento profil již existuje.")
                # Save disabled until its final priority has been persisted.
                config["connection"]["autoconnect"]=dbus.Boolean(False)
                path=self.settings.AddConnection(config)
                conn=dbus.Interface(self.bus.get_object(NM,path),NM+".Settings.Connection")
                uid=config["connection"]["uuid"]
                pos=ids.index(AP) if AP in ids else len(ids)
                try:
                    self.rank(ids[:pos]+[uid]+ids[pos:])
                    nm("connection","modify","uuid",uid,"connection.autoconnect","yes")
                except Exception:
                    conn.Delete()
                    raise
        else:
            raise Invalid("Neznámá operace.")
        return self.view()


def main():
    if sys.argv[1:]==["--test-eduroam"]:
        run_eduroam_test()
        return
    profiles=Profiles()
    if sys.argv[1:]==["--initialize"]:
        profiles.initialize()
        return
    # One listener processes mutations serially, including operations from different browsers.
    with socket.socket(fileno=3) as listener:
        while True:
            conn,_=listener.accept()
            with conn:
                conn.settimeout(7)
                try:
                    with conn.makefile("rb") as stream:
                        line=stream.readline(16385)
                    if len(line)>16384 or not line.endswith(b"\n"):
                        raise Invalid("Neplatná délka požadavku.")
                    payload=json.loads(line)
                    if not isinstance(payload,dict):
                        raise Invalid("Neplatný požadavek.")
                    result=profiles.run(payload)
                except Invalid as exc:
                    result={"error":str(exc)}
                except (ValueError,OSError,subprocess.SubprocessError,dbus.DBusException) as exc:
                    print("Wi-Fi request failed:",type(exc).__name__,file=sys.stderr,flush=True)
                    result={"error":"NetworkManager změnu nepotvrdil. Obnov seznam profilů."}
                try:
                    conn.sendall(json.dumps(result).encode()+b"\n")
                except OSError:
                    pass


if __name__=="__main__":
    main()

