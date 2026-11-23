"""Independent SQLite store for horizontal GNSS repeatability at physical survey marks."""
import math
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS marks(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, note TEXT NOT NULL,
 anchor_lat REAL, anchor_lon REAL, known_lat REAL, known_lon REAL, reference_id INTEGER);
CREATE TABLE IF NOT EXISTS runs(
 id INTEGER PRIMARY KEY, mark_id INTEGER NOT NULL REFERENCES marks(id), step_s INTEGER NOT NULL,
 started_ms INTEGER NOT NULL, ended_ms INTEGER, state TEXT NOT NULL,
 n INTEGER NOT NULL DEFAULT 0, sum_e REAL NOT NULL DEFAULT 0, sum_n REAL NOT NULL DEFAULT 0,
 last_ms INTEGER, last_epoch INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS one_running ON runs(state) WHERE state='running';
CREATE INDEX IF NOT EXISTS runs_mark ON runs(mark_id,id);
CREATE TABLE IF NOT EXISTS fixes(
 run_id INTEGER NOT NULL REFERENCES runs(id), epoch INTEGER NOT NULL, t_ms INTEGER NOT NULL,
 lat REAL NOT NULL, lon REAL NOT NULL, height REAL, mode INTEGER NOT NULL, e REAL NOT NULL, n REAL NOT NULL,
 PRIMARY KEY(run_id,epoch)) WITHOUT ROWID;
"""
PAGE = 20
PLOT_POINTS = 500
WGS84_A = 6378137.0
WGS84_E2 = 6.6943799901413165e-3


def now_ms():
    return time.time_ns() // 1_000_000


def local_en(lat, lon, lat0, lon0):
    """WGS84 ECEF projected onto the mark's horizontal tangent plane at zero height."""
    a, e2 = WGS84_A, WGS84_E2
    p, p0, dl = map(math.radians, (lat, lat0, lon-lon0))
    s, c, s0, c0 = math.sin(p), math.cos(p), math.sin(p0), math.cos(p0)
    r, r0 = a / math.sqrt(1-e2*s*s), a / math.sqrt(1-e2*s0*s0)
    east = r*c*math.sin(dl)
    north = -s0*(r*c*math.cos(dl)-r0*c0) + c0*(1-e2)*(r*s-r0*s0)
    return east, north


def centroid_coords(east, north, lat0, lon0):
    """Intersect the normal through the EN centroid with the WGS84 ellipsoid."""
    a, e2 = WGS84_A, WGS84_E2
    s, c = math.sin(math.radians(lat0)), math.cos(math.radians(lat0))
    r = a / math.sqrt(1-e2*s*s)
    x, y, z = r*c-s*north, east, r*(1-e2)*s+c*north
    k = 1/(1-e2)
    b = x*c+k*z*s
    residual = x*x+y*y+k*z*z-a*a
    disc = b*b-(c*c+k*s*s)*residual
    if disc < 0:
        return None
    up = -residual/(b+math.sqrt(disc))
    x, z = x+c*up, z+s*up
    return [math.degrees(math.atan2(k*z,math.hypot(x,y))),
            (lon0+math.degrees(math.atan2(y,x))+180)%360-180]


def run_info(row):
    if row is None:
        return None
    run = dict(row)
    count = run["n"]
    east, north = run.pop("sum_e"), run.pop("sum_n")
    run["east"] = east / count if count else None
    run["north"] = north / count if count else None
    run.pop("last_epoch")
    return run


class Accuracy:
    def __init__(self, data_dir):
        self.path = (Path(data_dir) / "accuracy.sqlite3").resolve()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        with self.db:
            self.db.execute("UPDATE runs SET state='interrupted', ended_ms=COALESCE(last_ms,started_ms) WHERE state='running'")
        self.lock = threading.Lock()
        self.active = None
        self.error = None
        self.next_epoch = None
        self.started_mono = 0
        self.stop_event = threading.Event()
        self.thread = None
        self.cache_lock = threading.Lock()
        self.cache = OrderedDict()

    def start_worker(self, collector):
        def sample():
            while not self.stop_event.wait(0.1 if self.active else 0.4):
                if self.active is None:
                    continue
                with collector.lock:
                    row, received = collector.latest, collector.last_pvt
                    connected = collector.data is not None
                if connected and received is not None and time.monotonic()-received < 2:
                    try:
                        self.observe(row, received)
                    except sqlite3.Error as exc:
                        with self.lock:
                            self.error = "Zápis testu na NVMe selhal: " + str(exc)
        self.thread = threading.Thread(target=sample, name="accuracy", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        with self.lock, closing(self.db):
            with self.db:
                self.db.execute("UPDATE runs SET state='interrupted', ended_ms=? WHERE state='running'", (now_ms(),))

    def observe(self, row, received):
        if not row or not row["valid"] or row["mode"] == 3 or row["gps_week"] is None or row["tow_ms"] is None:
            return
        epoch = row["gps_week"] * 604800000 + row["tow_ms"]
        with self.lock:
            if not self.active or received < self.started_mono or (self.next_epoch is not None and epoch < self.next_epoch):
                return
            run_id, mark_id, step = self.active
            lat, lon = row["lat"], row["lon"]
            with self.db:
                mark = self.db.execute("SELECT anchor_lat,anchor_lon FROM marks WHERE id=?", (mark_id,)).fetchone()
                lat0, lon0 = mark
                if lat0 is None:
                    lat0, lon0 = lat, lon
                    self.db.execute("UPDATE marks SET anchor_lat=?,anchor_lon=? WHERE id=?", (lat,lon,mark_id))
                east, north = local_en(lat, lon, lat0, lon0)
                self.db.execute("INSERT INTO fixes VALUES (?,?,?,?,?,?,?,?,?)",
                                (run_id, epoch, row["t_ms"], lat, lon, row["alt_m"], row["mode"], east, north))
                self.db.execute("UPDATE runs SET n=n+1,sum_e=sum_e+?,sum_n=sum_n+?,last_ms=?,last_epoch=? WHERE id=?",
                                (east,north,row["t_ms"],epoch,run_id))
            self.next_epoch = epoch + step * 1000
            self.error = None

    def save_mark(self, body):
        name, note = body.get("name"), body.get("note", "")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or not isinstance(note,str) or len(note)>1200:
            raise ValueError("Zadej název značky do 100 znaků a popis do 1200 znaků.")
        lat, lon = body.get("known_lat"), body.get("known_lon")
        if (lat, lon) != (None, None) and not (
                type(lat) in (float,int) and -90 <= lat <= 90 and type(lon) in (float,int) and -180 <= lon <= 180):
            raise ValueError("Zadej obě platné referenční souřadnice, nebo obě ponech prázdné.")
        values = (name.strip(), note.strip(), lat, lon)
        with self.lock, self.db:
            try:
                if body.get("id") is None:
                    return self.db.execute("INSERT INTO marks(name,note,known_lat,known_lon) VALUES (?,?,?,?)", values).lastrowid
                key = body["id"]
                if type(key) is not int or not self.db.execute(
                        "UPDATE marks SET name=?,note=?,known_lat=?,known_lon=? WHERE id=?", (*values,key)).rowcount:
                    raise ValueError("Měřicí místo neexistuje.")
                return key
            except sqlite3.IntegrityError as exc:
                raise ValueError("Místo s tímto názvem již existuje.") from exc

    def change_run(self, action, body):
        with self.lock:
            old = self.active
            if action in ("stop","reset"):
                if not old or type(body.get("run")) is not int or old[0] != body["run"]:
                    raise RuntimeError("Vybraný test již neběží.")
            elif old:
                raise RuntimeError("Nejprve ukonči probíhající test.")
            if action == "start":
                mark, step = body.get("mark"), body.get("step_s")
                if type(step) is not int or not 1 <= step <= 86400:
                    raise ValueError("Interval musí být celé číslo od 1 do 86 400 sekund.")
                if type(mark) is not int or not self.db.execute("SELECT 1 FROM marks WHERE id=?", (mark,)).fetchone():
                    raise ValueError("Vyber uložené měřicí místo.")
            elif old:
                _, mark, step = old
            stamp = now_ms()
            new = None
            with self.db:
                if old:
                    self.db.execute("UPDATE runs SET state='done',ended_ms=? WHERE id=?", (stamp,old[0]))
                if action != "stop":
                    rid = self.db.execute("INSERT INTO runs(mark_id,step_s,started_ms,state) VALUES (?,?,?,'running')",
                                          (mark,step,stamp)).lastrowid
                    new = rid, mark, step
            self.active, self.next_epoch, self.started_mono = new, None, time.monotonic()
            self.error = None
            return new[0] if new else old[0]

    def reference(self, mark, run):
        with self.lock, self.db:
            if type(mark) is not int or type(run) is not int or not self.db.execute(
                "SELECT 1 FROM runs WHERE id=? AND mark_id=? AND state!='running' AND n>0", (run, mark)).fetchone():
                raise ValueError("Referencí může být dokončený test s body na stejném místě.")
            self.db.execute("UPDATE marks SET reference_id=? WHERE id=?", (run,mark))

    def detail(self, db, run):
        count = run["n"]
        key = (run["id"], count)
        with self.cache_lock:
            if key in self.cache:
                return self.cache[key]
            # Stream every point to compute exact radii; only the polar preview is decimated.
            stride = max(1, math.ceil(count/PLOT_POINTS))
            plot, modes, total, largest, farthest = [], {}, 0., -1., None
            rows = db.execute("SELECT e,n,t_ms,mode FROM fixes WHERE run_id=? ORDER BY epoch", (run["id"],))
            for i, (east,north,stamp,mode) in enumerate(rows):
                x, y = east-run["east"], north-run["north"]
                radius = math.hypot(x,y)
                total += radius
                modes[mode] = modes.get(mode,0)+1
                if i % stride == 0 or i == count-1:
                    plot.append([x,y,stamp,mode])
                if radius > largest:
                    largest, farthest = radius, [x,y,stamp,mode]
            if farthest and farthest not in plot:
                plot.append(farthest)
            result = dict(mean=total/count if count else None, maximum=largest if count else None,
                          farthest=farthest, plot=plot, modes=modes)
            self.cache[key] = result
            if len(self.cache)>6:
                self.cache.popitem(last=False)
            return result

    def view(self, mark_id=0, run_id=0, page=0):
        with closing(sqlite3.connect(self.path.as_uri()+"?mode=ro",uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            marks = [dict(row) for row in db.execute("SELECT * FROM marks ORDER BY name COLLATE NOCASE,id")]
            active = run_info(db.execute("SELECT * FROM runs WHERE state='running'").fetchone())
            chosen = mark_id or (active["mark_id"] if active else marks[0]["id"] if marks else 0)
            mark = next((m for m in marks if m["id"]==chosen),None)
            result = dict(marks=marks,mark=mark,active=active,error=self.error,detail=None,run=None,
                          reference=None,history=[],page=0,total=0,per_page=PAGE,known_en=None)
            if not mark:
                return result
            total = db.execute("SELECT count(*) FROM runs WHERE mark_id=?", (chosen,)).fetchone()[0]
            page = min(max(0,page),max(0,(total-1)//PAGE))
            history = [run_info(row) for row in db.execute(
                "SELECT * FROM runs WHERE mark_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (chosen,PAGE,page*PAGE))]
            reference = db.execute("SELECT * FROM runs WHERE mark_id=? AND state!='running' AND n>0 "
                                   "ORDER BY (id IS ?) DESC,id LIMIT 1",(chosen,mark["reference_id"])).fetchone()
            run = (run_info(db.execute("SELECT * FROM runs WHERE id=? AND mark_id=?", (run_id,chosen)).fetchone())
                   if run_id else history[0] if history else None)
            if mark["known_lat"] is not None and mark["anchor_lat"] is not None:
                result["known_en"] = local_en(mark["known_lat"],mark["known_lon"],mark["anchor_lat"],mark["anchor_lon"])
            if run and run["n"]:
                run["coordinates"] = centroid_coords(run["east"],run["north"],mark["anchor_lat"],mark["anchor_lon"])
            result.update(history=history,page=page,total=total,reference=run_info(reference),run=run,
                          detail=self.detail(db,run) if run else None)
            return result
