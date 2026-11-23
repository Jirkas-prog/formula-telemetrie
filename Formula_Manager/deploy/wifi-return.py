#!/usr/bin/python3
"""Prefer a saved station network when nobody is using the Raspberry Pi AP."""
import os
import subprocess

os.environ["LC_ALL"] = "C"
DEVICE = "wlan0"
AP = "1d1db196-d1db-4dc8-9719-7c0e5c861b69"


def call(*args):
    return subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=22)


def nm(*args):
    return call("nmcli", "--wait", "12", "--escape", "no", *args)


def idle_hotspot():
    active = nm("-g", "GENERAL.CON-UUID", "device", "show", DEVICE)
    if active.stdout.strip() != AP:
        return False
    stations = call("iw", "dev", DEVICE, "station", "dump")
    return stations.returncode == 0 and not stations.stdout.strip()


def known_networks():
    floor = int(nm("-g", "connection.autoconnect-priority", "connection", "show", "uuid", AP).stdout.strip())
    listings = nm("-t", "-f", "UUID,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY,TIMESTAMP", "connection", "show")
    networks = []
    for line in listings.stdout.splitlines():
        uuid, kind, auto, priority, stamp = line.split(":")
        if kind not in ("wifi", "802-11-wireless") or auto != "yes" or uuid == AP or int(priority or 0) <= floor:
            continue
        detail = nm("-g", "802-11-wireless.mode,802-11-wireless.ssid,connection.interface-name", "connection", "show", "uuid", uuid).stdout.splitlines()
        if len(detail) >= 2 and detail[0] in ("", "infrastructure") and (len(detail)<3 or detail[2] in ("", DEVICE)):
            networks.append((int(priority or 0), int(stamp or 0), uuid, detail[1]))
    return sorted(networks, reverse=True)


def main():
    if not idle_hotspot():
        return
    known = known_networks()
    if not known:
        return
    scan = call("iw", "dev", DEVICE, "scan", "ap-force")
    managed_scan = scan.returncode != 0 or "BSS " not in scan.stdout
    if not managed_scan:
        visible = {line.lstrip()[6:] for line in scan.stdout.splitlines() if line.lstrip().startswith("SSID: ")}
        if not any(ssid in visible for _, _, _, ssid in known):
            return
    if not idle_hotspot():
        return
    switched = False
    try:
        if managed_scan:
            # Some onboard radios can only scan reliably in station mode.
            nm("device", "set", DEVICE, "autoconnect", "no").check_returncode()
            nm("connection", "down", "uuid", AP).check_returncode()
            result = nm("-g", "SSID", "device", "wifi", "list", "ifname", DEVICE, "--rescan", "yes")
            visible = set(result.stdout.splitlines())
        for _, _, uuid, ssid in known:
            if ssid in visible:
                switched = nm("connection", "up", "uuid", uuid, "ifname", DEVICE).returncode == 0
                if switched:
                    return
    finally:
        if managed_scan:
            nm("device", "set", DEVICE, "autoconnect", "yes")
        if not switched and (managed_scan or not idle_hotspot()):
            active = nm("-g", "GENERAL.CON-UUID", "device", "show", DEVICE).stdout.strip()
            if active in ("", "--"):
                nm("connection", "up", "uuid", AP, "ifname", DEVICE).check_returncode()


if __name__ == "__main__":
    main()
