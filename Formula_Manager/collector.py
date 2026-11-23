"""Septentrio USB1 command / USB2 data collector. Requires python3-serial.

SBF framing and PVT fields follow the mosaic-X5 Firmware Reference Guide,
sections "SBF Block Structure", "PVTGeodetic" (4007), and "setSBFOutput".
"""
import binascii
from contextlib import closing
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import threading
import time

import serial
from diagnostics import BlockCache, decode, clean_reply, change_command, PARAMETERS, EDITABLE, SNAPSHOT
from overview import BLOCKS as OVERVIEW_BLOCKS, REQUEST as OVERVIEW_REQUEST, overview_data
from corrections import CorrectionLink, DEFAULT_RTK, validate as validate_rtk


RATE = {1: "sec1", 5: "msec200", 10: "msec100", 20: "msec50", 50: "msec20"}
DEFAULTS = {"rate_hz": 50, "commit_ms": 100, "raw_observations": True, "autostart": False}
NAV_BLOCKS = {5891, 4004, 4002, 4081}  # GPSNav, GLONav, GALNav, BDSNav
SAMPLE_FIELDS = ("seq", "t_ms", "gps_week", "tow_ms", "valid", "lat", "lon",
                 "alt_m", "speed_kmh", "sats", "mode", "error_code")
SCHEMA = """
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, started_ms INTEGER NOT NULL,
    stopped_ms INTEGER, state TEXT NOT NULL, samples INTEGER NOT NULL DEFAULT 0,
    raw_bytes INTEGER NOT NULL DEFAULT 0, settings_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id),
    seq INTEGER NOT NULL, t_ms INTEGER NOT NULL, gps_week INTEGER, tow_ms INTEGER,
    valid INTEGER NOT NULL, lat REAL, lon REAL, alt_m REAL, speed_kmh REAL,
    sats INTEGER, mode INTEGER NOT NULL, error_code INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS sample_session ON samples(session_id, id);
CREATE TABLE IF NOT EXISTS raw_chunks (
    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id),
    t_ms INTEGER NOT NULL, data BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS raw_session ON raw_chunks(session_id, id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id),
    t_ms INTEGER NOT NULL, detail TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS event_session ON events(session_id, id);
"""
INSERT_SAMPLE = ("INSERT INTO samples (session_id," + ",".join(SAMPLE_FIELDS) +
                 ") VALUES (" + ",".join(["?"] * (len(SAMPLE_FIELDS) + 1)) + ")")


def now_ms():
    return time.time_ns() // 1_000_000


class SbfFramer:
    def __init__(self):
        self.buffer = bytearray()
        self.crc_errors = 0

    def feed(self, data):
        self.buffer.extend(data)
        while True:
            start = self.buffer.find(b"$@")
            if start < 0:
                self.buffer[:] = b"$" if self.buffer.endswith(b"$") else b""
                return
            del self.buffer[:start]
            if len(self.buffer) < 8:
                return
            crc, block_id, length = struct.unpack_from("<HHH", self.buffer, 2)
            if length < 8 or length % 4:
                del self.buffer[:2]
                continue
            if len(self.buffer) < length:
                return
            block = bytes(self.buffer[:length])
            if binascii.crc_hqx(block[4:], 0) != crc:
                self.crc_errors += 1
                del self.buffer[:2]
                continue
            del self.buffer[:length]
            yield block_id & 8191, block


def decode_pvt(block, received_ms):
    if len(block) < 76:
        return None
    tow, week, flags, error = struct.unpack_from("<IHBB", block, 8)
    lat, lon, alt = struct.unpack_from("<ddd", block, 16)
    vn, ve = struct.unpack_from("<ff", block, 44)
    mode = flags & 15
    valid = bool(mode and not error and -math.pi/2 <= lat <= math.pi/2 and -math.pi <= lon <= math.pi)
    def numeric(v):
        return math.isfinite(v) and v != -2e10
    return dict(t_ms=received_ms, gps_week=None if week == 65535 else week,
                tow_ms=tow if tow < 604800000 else None, valid=valid,
                lat=math.degrees(lat) if valid else None, lon=math.degrees(lon) if valid else None,
                alt_m=alt if valid and numeric(alt) else None,
                speed_kmh=math.hypot(vn, ve)*3.6 if valid and numeric(vn) and numeric(ve) else None,
                sats=block[74] if block[74] != 255 else None, mode=mode, error_code=error)


def receiver_ports():
    pairs = []
    for ctrl in Path("/dev/serial/by-id").glob("usb-Septentrio_*-if02"):
        data = ctrl.with_name(ctrl.name[:-2] + "04")
        if ctrl.exists() and data.exists():
            pairs.append((ctrl, data))
    if len(pairs) != 1:
        raise OSError(f"Nalezeno dvojic portů USB1/USB2 přijímače Septentrio: {len(pairs)} (očekávána jedna).")
    return pairs[0]


COMMAND_LOCK = threading.RLock()


def command(port, cmd):
    with COMMAND_LOCK:
        return _command(port, cmd)


def _command(port, cmd):
    port.reset_input_buffer()
    port.write((cmd + "\r").encode("ascii"))
    reply = bytearray()
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline and len(reply) < 262144:
        reply.extend(port.read(min(8192, max(1, port.in_waiting))))
        if b"$R" in reply and re.search(rb"(?:\r|\n)USB1>\s*$", reply):
            break
    else:
        raise OSError(f"USB1: přijímač nedokončil odpověď na {cmd.split(',')[0]}.")
    lines = reply.decode("ascii", errors="replace").replace("\r", "\n")
    if "$R?" in lines or not ("$R:" in lines or "$R;" in lines):
        message = " ".join(lines.split())[-220:]
        raise OSError(f"Přijímač odmítl příkaz: {message}")
    return lines


def stream_table(reply):
    # Firmware can wrap long '+' lists onto the following line.
    reply = re.sub(r"\n+\s*(?=\+)", "", reply)
    rows = re.findall(r"(?im)^\s*SBFOutput,\s*(Stream\d+),\s*([^,\r\n]+),\s*([^,\r\n]+),\s*(\w+)", reply)
    return {slot.lower(): (cd.strip().lower(),
                           sorted({s.strip().lower() for s in names.split("+") if s.strip()}),
                           interval.lower()) for slot, cd, names, interval in rows}


def configure_stream(port, receiver_id, settings, known):
    slots = stream_table(command(port, "gso"))
    if not slots:
        raise OSError("USB1: přijímač nevrátil přehled SBF streamů.")
    slot = known.get("slot", "") if known.get("receiver") == receiver_id else ""
    if slot not in slots or list(slots[slot]) != known.get("signature"):
        slot = next((s for s in sorted(slots, key=lambda k: int(k[6:]), reverse=True)
                     if slots[s][0] == "none" and slots[s][1] == ["none"]), "")
    if not slot:
        raise OSError("Přijímač nemá volný SBF stream. Zkontroluj výstupy ve webu přijímače.")
    # Do not mix independently configured streams on the data port. This also
    # prevents a failed read-back from claiming more and more free slots.
    if any(s != slot and row[0] == "usb2" and row[2] != "off" for s, row in slots.items()):
        raise OSError("USB2 již používá jiný SBF stream. Zkontroluj výstupy ve webu přijímače.")
    names = ["PVTGeodetic", "ReceiverStatus"]
    if settings["raw_observations"]:
        names += ["MeasEpoch", "MeasExtra", "GPSNav", "GLONav", "GALNav", "BDSNav"]
    interval = RATE[settings["rate_hz"]]
    expected = ("usb2", sorted(n.lower() for n in names), interval.lower())
    if slots[slot] != expected:
        command(port, f"sso,{slot},USB2,{'+'.join(names)},{interval}")
    actual = stream_table(command(port, "gso," + slot)).get(slot)
    if actual != expected:
        raise OSError("USB1: výstup přečtený z přijímače neodpovídá zadanému nastavení.")
    return {"receiver": receiver_id, "slot": slot, "signature": list(actual)}


class Collector:
    def __init__(self, data_dir):
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = (data_dir / "logger.sqlite3").resolve()
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        with self.db:
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(sessions)")}
            for name in ("obs_epochs", "nav_blocks"):
                if name not in cols:
                    self.db.execute(f"ALTER TABLE sessions ADD COLUMN {name} INTEGER")
            self.db.execute("UPDATE sessions SET state='interrupted' WHERE state='recording'")
            highest_id = self.db.execute("SELECT COALESCE(MAX(id),0) FROM sessions").fetchone()[0]
            self._save("last_session_id", max(highest_id, self._load("last_session_id", 0)))
        previous = {**DEFAULTS, **self._load("settings", {})}
        self.manual_settings = {k: v for k, v in previous.items() if k != "autostart"}
        self.startup_settings = self._load("startup", None)
        if self.startup_settings is None:
            self.startup_settings = previous.copy()
            with self.db:
                self._save("startup", self.startup_settings)
        self.recording_profile = None
        self.rtk = {**DEFAULT_RTK, **self._load("rtk", {})}
        self.corrections = CorrectionLink(self)
        self.rtk_thread = None
        self.rtcm_ready = False
        self.boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        new_boot = self._load("auto_boot", "") != self.boot_id
        self.auto_pending = self.startup_settings["autostart"] and (new_boot or self._load("auto_resume", False))
        self.resume_profile = None if new_boot else self._load("resume_profile", None)
        self.pending_obs = self.pending_nav = 0
        self.known = self._load("stream", {})
        self.stop_event = threading.Event()
        self.thread = None
        self.ctrl = self.data = None
        self.device = self.session_id = self.latest = self.last_pvt = None
        self.error = self.storage_error = None
        self.rx_bytes = self.seq = self.live_seq = self.crc_total = 0
        self.blocks = BlockCache()
        self.overview_due = 0
        self.overview_error = None
        self.framer = SbfFramer()
        self.last_commit = time.monotonic()
        self.pending_rows = self.pending_bytes = 0

    def _load(self, key, default):
        row = self.db.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _save(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO config VALUES (?,?)", (key, json.dumps(value)))

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True, name="septentrio")
            self.thread.start()
            self.rtk_thread = threading.Thread(target=self.corrections.run, daemon=True, name="rtcm")
            self.rtk_thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        if self.rtk_thread:
            self.rtk_thread.join()
        with self.lock:
            try:
                self.stop_logging(shutdown=True)
            finally:
                self._disconnect()
                self.db.close()

    @property
    def settings(self):
        return self.recording_profile or self.manual_settings

    def status(self):
        with self.lock:
            return dict(connected=self.data is not None, device=self.device,
                        error=self.storage_error or self.error, latest=self.latest,
                        logging=self.session_id is not None, session_id=self.session_id,
                        age_s=time.monotonic()-self.last_pvt if self.last_pvt is not None else None,
                        rx_bytes=self.rx_bytes, crc_errors=self.crc_total + self.framer.crc_errors,
                        settings={**self.settings, "autostart": self.startup_settings["autostart"]},
                        manual_settings=dict(self.manual_settings), startup_settings=dict(self.startup_settings),
                        settings_applied=self.data is not None,
                        rtk=dict(self.rtk), corrections=self.corrections.status())

    def configure_rtk(self, cfg):
        validate_rtk(cfg)
        with self.lock:
            if self.session_id is not None:
                raise RuntimeError("Před změnou nastavení ukonči záznam.")
            with self.db:
                self._save("rtk", cfg)
            self.rtk = dict(cfg)
            self.corrections.reset()
            self.rtcm_ready = False

    def diagnostics(self, selected):
        with self.lock:
            rows, detail = self.blocks.snapshot(selected)
            connected = self.data is not None
        return dict(connected=connected, blocks=rows,
                    detail={**detail[0], **decode(detail[1])} if detail else None)

    def receiver_overview(self):
        with self.lock:
            port = self.ctrl
            refresh = port is not None and time.monotonic() >= self.overview_due
            if refresh:
                self.overview_due = time.monotonic() + 4
        if refresh:
            error = None
            try:
                command(port, OVERVIEW_REQUEST)
            except OSError as exc:
                error = str(exc)
            with self.lock:
                if self.ctrl is port:
                    self.overview_error = error
        with self.lock:
            frames = {key: self.blocks.latest[key] for key in OVERVIEW_BLOCKS if key in self.blocks.latest}
            error = self.overview_error
        return {"frames": overview_data(frames, now_ms()), "error": error}

    def receiver_query(self, action, name, arguments=None):
        if action == "snapshot":
            cmd = SNAPSHOT
        elif action == "catalog":
            cmd = "lstCommandHelp"
        elif not isinstance(name, str) or name not in PARAMETERS:
            raise ValueError("Neznámý parametr přijímače.")
        elif action == "read":
            cmd = "get" + name
        elif action == "help":
            cmd = "lstCommandHelp," + ("set" if name in EDITABLE else "get") + name
        elif action == "write":
            cmd = change_command(name, arguments)
        else:
            raise ValueError("Neznámá operace.")
        try:
            with self.lock:
                port = self.ctrl
                if port is None:
                    raise RuntimeError("Přijímač není připojen.")
                if action == "write":
                    if self.session_id is not None:
                        raise RuntimeError("Před změnou konfigurace ukonči záznam.")
                    command(port, cmd)
                    return clean_reply(command(port, "get" + name))
            # A read-only query must not hold the collector lock while USB2 delivers data.
            with COMMAND_LOCK:
                if not port.is_open:
                    raise RuntimeError("Přijímač byl odpojen.")
                return clean_reply(command(port, cmd))
        except OSError as exc:
            raise RuntimeError(str(exc)) from exc

    def send_rtcm(self, packet):
        # Caller owns the same lock as disconnect/configure. USB1 is command-only here.
        if self.data is None:
            raise OSError("Čekám na USB přijímače.")
        if not self.rtcm_ready:
            command(self.ctrl, "setDataInOut,USB2,RTCMv3,")
            reply = command(self.ctrl, "getDataInOut,USB2")
            if not re.search(r"(?im)^\s*DataInOut,\s*USB2,\s*RTCMv3,", reply):
                raise OSError("Přijímač nepotvrdil vstup RTCM 3 na USB2.")
            self.rtcm_ready = True
        if self.data.write(packet) != len(packet):
            raise OSError("Neúplný zápis korekce do USB2.")

    def configure(self, changes, *, startup=False):
        if not isinstance(changes, dict) or set(changes) - DEFAULTS.keys():
            raise ValueError("Neznámé nastavení loggeru.")
        with self.lock:
            if self.session_id is not None and not startup:
                raise RuntimeError("Před změnou nastavení ukonči záznam.")
            base = self.startup_settings if startup else {
                **self.manual_settings, "autostart": self.startup_settings["autostart"]}
            cfg = {**base, **changes}
            if (type(cfg["rate_hz"]) is not int or cfg["rate_hz"] not in RATE or
                    type(cfg["commit_ms"]) is not int or cfg["commit_ms"] not in (20,50,100,200,500,1000) or
                    type(cfg["raw_observations"]) is not bool or type(cfg["autostart"]) is not bool):
                raise ValueError("Nepodporovaná frekvence, doba zápisu nebo volba surových měření.")
            if not startup and self.ctrl is not None:
                try:
                    self._apply(cfg)
                except OSError as exc:
                    self.error = str(exc)
                    self._disconnect()
                    raise RuntimeError(str(exc)) from exc
            manual = {k: v for k, v in cfg.items() if k != "autostart"}
            # Older clients submitted automatic and manual settings in a single form.
            boot_cfg = {**self.startup_settings, **changes} if startup or "autostart" in changes else self.startup_settings
            toggled = boot_cfg["autostart"] != self.startup_settings["autostart"]
            with self.db:
                if not startup:
                    self._save("settings", manual)
                if boot_cfg != self.startup_settings:
                    self._save("startup", boot_cfg)
                if toggled:
                    self._save("auto_boot", self.boot_id)
                    self._save("auto_resume", False)
                # A next-boot edit may share the current SQLite transaction with live samples.
                self._commit()
            if toggled:
                self.auto_pending = False
            if not startup:
                self.manual_settings = manual
            self.startup_settings = boot_cfg
            return dict(cfg)

    def _apply(self, cfg):
        known = configure_stream(self.ctrl, self.device, cfg, self.known)
        with self.db:
            self._save("stream", known)
        self.known = known

    def start_logging(self, name="", *, profile=None):
        if not isinstance(name, str) or len(name) > 120:
            raise ValueError("Název záznamu může mít nejvýše 120 znaků.")
        with self.lock:
            if self.session_id is not None:
                raise RuntimeError("Záznam už běží.")
            if self.data is None:
                raise RuntimeError("Připoj přijímač GNSS a počkej na konfiguraci USB.")
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                session_id = self._load("last_session_id", 0) + 1
                measurement = {k: (profile or self.manual_settings)[k] for k in self.manual_settings}
                snapshot = {**measurement, "autostart": self.startup_settings["autostart"], "rtk": self.rtk}
                self.db.execute("INSERT INTO sessions(id,name,started_ms,state,settings_json,obs_epochs,nav_blocks) "
                                "VALUES (?,?,?, 'recording',?,0,0)",
                                (session_id, name.strip() or "Jízda", now_ms(), json.dumps(snapshot)))
                self._save("last_session_id", session_id)
                self._save("auto_boot", self.boot_id)
                self._save("auto_resume", self.startup_settings["autostart"])
                self._save("resume_profile", measurement)
            self.session_id = session_id
            self.recording_profile = measurement
            self.storage_error = None
            self.seq = 0
            self.last_commit = time.monotonic()
            self.framer.buffer.clear()
            self.auto_pending = False
            self._request_navigation()
            return self.session_id

    def _request_navigation(self):
        if self.settings["raw_observations"]:
            try:
                command(self.ctrl, "exeSBFOnce,USB2,ReceiverSetup+GPSNav+GLONav+GALNav+BDSNav")
            except OSError as exc:
                self._event("PPK: " + str(exc))

    def stop_logging(self, shutdown=False):
        with self.lock:
            if self.session_id is None:
                return None
            sid = self.session_id
            self.db.execute("UPDATE sessions SET state='stopped', stopped_ms=? WHERE id=?", (now_ms(), sid))
            if not shutdown:
                self._save("auto_resume", False)
            self._commit()
            self.session_id = None
            previous = self.recording_profile
            self.recording_profile = None
            if not shutdown and self.ctrl is not None and previous != self.manual_settings:
                try:
                    self._apply(self.manual_settings)
                except OSError as exc:
                    self.error = str(exc)
                    self._disconnect()
            return sid

    def _read(self, query, args=()):
        with closing(sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True)) as reader:
            reader.row_factory = sqlite3.Row
            return [dict(row) for row in reader.execute(query, args)]

    def sessions(self):
        return self._read("SELECT * FROM sessions ORDER BY id DESC")

    def samples(self, session_id, after=0, limit=1000):
        return self._read("SELECT * FROM samples WHERE session_id=? AND id>? ORDER BY id LIMIT ?",
                          (int(session_id), int(after), max(1, min(10000, int(limit)))))

    def _event(self, detail):
        if self.session_id is not None:
            self.db.execute("INSERT INTO events(session_id,t_ms,detail) VALUES (?,?,?)",
                            (self.session_id, now_ms(), detail))
            self._commit()

    def _commit(self):
        if self.pending_bytes or self.pending_rows:
            self.db.execute("UPDATE sessions SET samples=samples+?, raw_bytes=raw_bytes+?, "
                            "obs_epochs=obs_epochs+?,nav_blocks=nav_blocks+? WHERE id=?",
                            (self.pending_rows, self.pending_bytes, self.pending_obs, self.pending_nav, self.session_id))
        self.db.commit()
        self.pending_rows = self.pending_bytes = 0
        self.pending_obs = self.pending_nav = 0
        self.last_commit = time.monotonic()

    def _connect(self):
        ctrl_path, data_path = receiver_ports()
        self.ctrl = serial.Serial(str(ctrl_path), 115200, timeout=0.05, write_timeout=1, exclusive=True)
        self.device = str(data_path)
        self.data = serial.Serial(str(data_path), 115200, timeout=0.015, write_timeout=.1, exclusive=True)
        profile = (self.resume_profile or self.startup_settings) if self.auto_pending else self.settings
        self._apply(profile)
        self.error = None
        self._event("USB connected")
        if self.session_id is not None:
            self._request_navigation()
        elif self.auto_pending:
            self.start_logging("Automatický záznam " + time.strftime("%Y-%m-%d %H.%M.%S"), profile=profile)

    def _disconnect(self):
        self.rtcm_ready = False
        for p in (self.data, self.ctrl):
            if p is not None:
                try:
                    with COMMAND_LOCK:
                        p.close()
                except OSError:
                    pass
        self.data = self.ctrl = self.device = None
        self.blocks = BlockCache()
        self.overview_due = 0
        self.overview_error = None
        self.latest = self.last_pvt = None
        self.crc_total += self.framer.crc_errors
        self.framer = SbfFramer()

    def _consume(self, chunk):
        received = now_ms()
        self.rx_bytes += len(chunk)
        if self.session_id is not None:
            self.db.execute("INSERT INTO raw_chunks(session_id,t_ms,data) VALUES (?,?,?)",
                            (self.session_id, received, chunk))
            self.pending_bytes += len(chunk)
        for block_id, block in self.framer.feed(chunk):
            self.blocks.observe(block_id, block, received)
            if self.session_id is not None:
                if block_id == 4027 and len(block) >= 20 and block[14] > 0:
                    self.pending_obs += 1
                if block_id in NAV_BLOCKS:
                    self.pending_nav += 1
            if block_id != 4007:
                continue
            row = decode_pvt(block, received)
            if row is None:
                continue
            self.last_pvt = time.monotonic()
            self.live_seq += 1
            row.update(id=None, seq=self.live_seq)
            if self.session_id is not None:
                self.seq += 1
                row["seq"] = self.seq
                values = [self.session_id] + [row[field] for field in SAMPLE_FIELDS]
                row["id"] = self.db.execute(INSERT_SAMPLE, values).lastrowid
                self.pending_rows += 1
            self.latest = row

    def _storage_failed(self, exc):
        self.storage_error = "Záznam do SQLite se přerušil: " + str(exc)
        self.db.rollback()
        if self.session_id is not None:
            try:
                with self.db:
                    self.db.execute("UPDATE sessions SET state='interrupted', stopped_ms=? WHERE id=?",
                                    (now_ms(), self.session_id))
            except sqlite3.Error:
                pass
        self.session_id = None
        self.recording_profile = None
        self.pending_bytes = self.pending_rows = 0
        self.pending_obs = self.pending_nav = 0

    def _run(self):
        while not self.stop_event.is_set():
            retry = False
            with self.lock:
                try:
                    if self.data is None:
                        self._connect()
                    data = self.data.read(min(65536, max(1, self.data.in_waiting)))
                    if data:
                        self._consume(data)
                    if self.db.in_transaction and time.monotonic()-self.last_commit >= self.settings["commit_ms"]/1000:
                        self._commit()
                except (OSError, serial.SerialException) as exc:
                    connected = self.data is not None
                    self.error = str(exc)
                    self._disconnect()
                    retry = True
                    if connected:
                        try:
                            self._event("USB disconnected: " + str(exc))
                        except sqlite3.Error as db_exc:
                            self._storage_failed(db_exc)
                except sqlite3.Error as exc:
                    self._storage_failed(exc)
                    self._disconnect()
                    retry = True
            # Also give waiting HTTP handlers a chance to acquire the lock at low input rates.
            self.stop_event.wait(2 if retry else 0.001)
