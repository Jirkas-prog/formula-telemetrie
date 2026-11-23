"""Five-second Linux hardware telemetry, stored on the logger's data volume."""
import logging
import os
import shutil
import sqlite3
import threading
import time
from collections import deque
from contextlib import closing
from pathlib import Path


INTERVAL_S = 5
IO_COLUMNS = ("disk_read_bytes", "disk_write_bytes", "wifi_rx_bytes", "wifi_tx_bytes")
COLUMNS = ("t", "cpu_c", "ssd_c", "sink_c", "rpm", "cpu_pct", "ram_total", "ram_free",
           "ram_avail", "ram_used", "disk_total", "disk_used", "disk_free") + IO_COLUMNS
INSERT_SAMPLE = (f"INSERT INTO samples ({','.join(COLUMNS)}) "
                 f"VALUES ({','.join('?' for _ in COLUMNS)})")


def open_history(path):
    db = sqlite3.connect(path, timeout=1)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS samples(
                id INTEGER PRIMARY KEY,
                t INTEGER NOT NULL,
                cpu_c REAL, ssd_c REAL, sink_c REAL, rpm INTEGER, cpu_pct REAL,
                ram_total INTEGER, ram_free INTEGER, ram_avail INTEGER, ram_used INTEGER,
                disk_total INTEGER, disk_used INTEGER, disk_free INTEGER
            );
            CREATE INDEX IF NOT EXISTS samples_time ON samples(t);
        """)
        with db:
            cols = {row[1] for row in db.execute("PRAGMA table_info(samples)")}
            for name in IO_COLUMNS:
                if name not in cols:
                    db.execute(f"ALTER TABLE samples ADD COLUMN {name} INTEGER")
        return db
    except sqlite3.Error:
        db.close()
        raise


def write_samples(db, rows):
    with db:
        db.executemany(INSERT_SAMPLE, (tuple(row.get(key) for key in COLUMNS) for row in rows))


def text_file(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


class Hardware:
    def __init__(self, volume):
        self.volume = Path(volume).resolve()
        dev = self.volume.stat().st_dev
        self.block_stat = (Path("/sys/dev/block") / f"{os.major(dev)}:{os.minor(dev)}" / "stat"
                           if hasattr(os, "major") else None)
        self.path = self.volume / "hardware.sqlite3"
        self.storage_error = None
        self.dropped = 0
        self.stop_event = threading.Event()
        self.previous_cpu = None
        self.sensors = {}
        for chip in Path("/sys/class/hwmon").glob("hwmon*"):
            name = text_file(chip/"name")
            for sensor in sorted(chip.glob("temp*_input")):
                label = text_file(sensor.with_name(sensor.name.replace("_input","_label"))).lower()
                if name == "cpu_thermal":
                    self.sensors["cpu_c"] = sensor
                elif name == "nvme" and ("composite" in label or "ssd_c" not in self.sensors):
                    self.sensors["ssd_c"] = sensor
                elif "heatsink" in (name+" "+label).lower():
                    self.sensors["sink_c"] = sensor
            if name == "pwmfan" and (chip/"fan1_input").is_file():
                self.sensors["rpm"] = chip/"fan1_input"
        self.thread = threading.Thread(target=self._run,daemon=True,name="hardware-monitor")
        self.thread.start()

    def _sample(self):
        row = {"t": time.time_ns()//1_000_000}
        if self.block_stat:
            sectors = text_file(self.block_stat).split()
            if len(sectors) >= 7 and sectors[2].isdigit() and sectors[6].isdigit():
                row.update(disk_read_bytes=int(sectors[2])*512, disk_write_bytes=int(sectors[6])*512)
        for direction in ("rx", "tx"):
            value = text_file(Path("/sys/class/net/wlan0/statistics")/(direction+"_bytes"))
            if value.isdigit():
                row["wifi_"+direction+"_bytes"] = int(value)
        for name, path in self.sensors.items():
            value = text_file(path)
            if value.lstrip("-").isdigit():
                row[name] = int(value) if name == "rpm" else int(value)/1000
        mem = {}
        for line in text_file(Path("/proc/meminfo")).splitlines():
            key, data = line.split(":",1)
            if key in ("MemTotal","MemFree","MemAvailable"):
                mem[key] = int(data.split()[0])*1024
        if len(mem)==3:
            row.update(ram_total=mem["MemTotal"],ram_free=mem["MemFree"],ram_avail=mem["MemAvailable"],
                       ram_used=mem["MemTotal"]-mem["MemAvailable"])
        stats = text_file(Path("/proc/stat")).splitlines()
        if stats:
            cpu = [int(x) for x in stats[0].split()[1:9]]
            total, idle = sum(cpu), cpu[3]+cpu[4]
            if self.previous_cpu and total>self.previous_cpu[0]:
                row["cpu_pct"] = max(0,min(100,100*(1-(idle-self.previous_cpu[1])/(total-self.previous_cpu[0]))))
            self.previous_cpu = total,idle
        try:
            size,used,free = shutil.disk_usage(self.volume)
            row.update(disk_total=size,disk_used=used,disk_free=free)
        except OSError:
            pass
        return row

    def _run(self):
        db = None
        pending = deque(maxlen=360)
        try:
            while not self.stop_event.is_set():
                started = time.monotonic()
                if len(pending) == pending.maxlen:
                    self.dropped += 1
                pending.append(self._sample())
                try:
                    if db is None:
                        db = open_history(self.path)
                    write_samples(db, pending)
                    pending.clear()
                    self.storage_error = None
                except sqlite3.Error as exc:
                    if not self.storage_error:
                        logging.warning("Hardware history write failed: %s", exc)
                    self.storage_error = "Zápis hardwaru na NVMe selhal: " + str(exc)
                    if db is not None:
                        db.close()
                        db = None
                self.stop_event.wait(max(0, INTERVAL_S - (time.monotonic()-started)))
        finally:
            if db is not None:
                db.close()
            if pending:
                logging.warning("Hardware monitor stopped with %d uncommitted samples", len(pending))

    def snapshot(self, minutes=30, end_ms=None):
        end = time.time_ns()//1_000_000 if end_ms is None else end_ms
        rows = []
        error = self.storage_error
        if self.path.exists():
            try:
                with closing(sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True, timeout=1)) as db:
                    db.row_factory = sqlite3.Row
                    result = db.execute(f"SELECT {','.join(COLUMNS)} FROM samples WHERE t BETWEEN ? AND ? "
                                        "ORDER BY t,id", (end-minutes*60_000, end))
                    rows = [{k: r[k] for k in COLUMNS if r[k] is not None} for r in result]
            except sqlite3.Error as exc:
                error = error or ("Čtení historie hardwaru selhalo: " + str(exc))
        return {"samples": rows, "sensors": list(self.sensors), "end_ms": end,
                "storage_error": error, "dropped": self.dropped}

    def close(self):
        self.stop_event.set()
        self.thread.join()
