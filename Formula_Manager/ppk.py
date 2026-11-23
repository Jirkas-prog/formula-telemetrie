"""Offline kinematic GNSS processing. Raw inputs and derived epochs live separately from ride data."""
import csv
import gzip
import hashlib
import io
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import closing, contextmanager, nullcontext
from datetime import date
from pathlib import Path

from mediafiles import open_download

CHUNK = 1024 * 1024
COLUMNS = ("gps_week", "tow_ms", "lat", "lon", "height_m", "quality", "satellites",
           "sd_n_m", "sd_e_m", "sd_u_m", "age_s", "ratio")
RAW = {".ubx": "ubx", ".sbf": "sbf", ".rtcm": "rtcm3", ".rtcm3": "rtcm3"}
SOLVER_OPTIONS = ("-p","2","-f","2","-m","15","-v","3","-sys","G,R,E,C","-d","3")


def file_format(name, head):
    suffix = Path(name.removesuffix(".gz")).suffix
    if suffix in RAW:
        signature = {"ubx": b"\xb5\x62", "sbf": b"$@", "rtcm3": b"\xd3"}[RAW[suffix]]
        if signature not in head:
            raise ValueError("Soubor neobsahuje očekávanou hlavičku přijímače.")
        return RAW[suffix]
    first = head.split(b"\n", 1)[0]
    if b"RINEX VERSION / TYPE" in first and first[20:21] in (b"O", b"N", b"G", b"H", b"L", b"J"):
        try:
            version = float(first[:9])
        except ValueError:
            version = 0
        if not 2 <= version < 4:
            raise ValueError("Tato verze RTKLIB pracuje s RINEX 2 a 3.")
        return "obs" if first[20:21] == b"O" else "nav"
    raise ValueError("Zvol observace nebo navigaci RINEX 2/3, UBX, SBF nebo RTCM3. Hatanaka vyžaduje předchozí rozbalení.")


def positive_id(value):
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError("Neplatný identifikátor vstupu.")
    return value


def space(path, amount=0):
    if shutil.disk_usage(path).free < amount + 256*CHUNK:
        raise ValueError("Na NVMe chybí volné místo pro PPK.")


def rinex_xyz(path):
    """Read the RINEX header only; epochs and carrier observations are checked by the solver."""
    xyz = None
    with path.open("rb") as f:
        for _ in range(8192):
            line = f.readline(4096)
            if not line:
                break
            label = line[60:].strip()
            if label == b"APPROX POSITION XYZ":
                try:
                    coords = list(map(float, line[:60].split()))
                    if len(coords) == 3 and 6e6 < math.hypot(*coords) < 7e6:
                        xyz = coords
                except ValueError:
                    pass
            if label == b"END OF HEADER":
                return xyz
    raise ValueError("Chybí platná hlavička observací RINEX.")


def run_tool(args, folder):
    try:
        # Limit the external solver on the 2 GiB Pi without changing the acquisition process.
        with subprocess.Popen(["nice","-n","15","prlimit","--as=805306368","--",*map(str,args)],
                              cwd=folder,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as proc:
            deadline=time.monotonic()+3600
            try:
                while proc.poll() is None:
                    space(folder)
                    if time.monotonic()>=deadline:
                        raise ValueError("Výpočet překročil hodinu. Použij kratší relaci.")
                    try:
                        proc.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                if proc.poll() is None:
                    proc.kill()
    except FileNotFoundError as exc:
        raise ValueError("Chybí nástroje RTKLIB nebo util-linux.") from exc
    if proc.returncode:
        raise ValueError(f"{args[0]} nedokončil výpočet (kód {proc.returncode}). Ověř soubory a délku relace.")


def prepare(path, fmt, date_hint):
    if fmt == "obs":
        rinex_xyz(path)
        return path, []
    if fmt not in RAW.values():
        raise ValueError("Jako měření vyber observace nebo surový záznam přijímače.")
    obs, nav = path.with_suffix(".obs"), path.with_suffix(".nav")
    args = ["convbin", "-r", fmt, "-v", "3.04", "-o", obs, "-n", nav]
    if fmt == "rtcm3":
        try:
            stamp = date.fromisoformat(date_hint)
        except (TypeError, ValueError) as exc:
            raise ValueError("Pro RTCM3 zadej skutečné datum měření (GPS týden).") from exc
        args.extend(["-tr", stamp.strftime("%Y/%m/%d"), "12:00:00"])
    run_tool(args+[path], path.parent)
    if not obs.exists():
        raise ValueError(f"V souboru {path.name} nebyly nalezeny surové observace.")
    rinex_xyz(obs)
    return obs, [nav] if nav.is_file() and nav.stat().st_size else []


class PPK:
    def __init__(self, data):
        self.data = Path(data).resolve()
        self.inbox = self.data/"imports"
        self.inbox.mkdir(exist_ok=True)
        self.path = self.data/"ppk.sqlite3"
        self.lock = threading.Lock()
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY, name TEXT NOT NULL, format TEXT NOT NULL,
                    bytes INTEGER NOT NULL, sha256 TEXT UNIQUE, imported INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks(asset INTEGER NOT NULL REFERENCES assets(id), seq INTEGER NOT NULL,
                    payload BLOB NOT NULL, PRIMARY KEY(asset,seq)) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                    started INTEGER NOT NULL, params TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', reference TEXT, solver TEXT);
                CREATE TABLE IF NOT EXISTS epochs(job INTEGER NOT NULL REFERENCES jobs(id), gps_week INTEGER NOT NULL,
                    tow_ms INTEGER NOT NULL, lat REAL, lon REAL, height_m REAL, quality INTEGER, satellites INTEGER,
                    sd_n_m REAL, sd_e_m REAL, sd_u_m REAL, age_s REAL, ratio REAL,
                    PRIMARY KEY(job,gps_week,tow_ms)) WITHOUT ROWID;
            """)
            if "solver" not in {r[1] for r in db.execute("PRAGMA table_info(jobs)")}:
                db.execute("ALTER TABLE jobs ADD COLUMN solver TEXT")
            db.execute("UPDATE jobs SET state='failed',note='Přerušeno restartem. Lze spustit znovu.' WHERE state='running'")
        for path in self.data.glob(".formula-part-ppk-*"):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def start(self, kind, params):
        if kind not in ("import","solve"):
            raise ValueError("Neznámá úloha PPK.")
        if kind == "solve":
            nav = params.get("nav",[])
            if not isinstance(nav,list) or len(nav)>8:
                raise ValueError("Zvol nejvýše osm navigačních souborů RINEX.")
            for aid in nav:
                positive_id(aid)
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("Právě probíhá jiná úloha PPK.")
        try:
            with self.db() as db:
                job = db.execute("INSERT INTO jobs(kind,state,started,params) VALUES(?,'running',?,?)",
                                 (kind,int(time.time()*1000),json.dumps(params,ensure_ascii=False))).lastrowid
            threading.Thread(target=self._work, args=(job,kind,params), daemon=True,name="ppk").start()
            return job
        except BaseException:
            self.lock.release()
            raise

    def _work(self, job, kind, params):
        try:
            with self.db() as db:
                if kind == "import":
                    note = self._import(db, params)
                else:
                    note = self._solve(db, job, params)
                db.execute("UPDATE jobs SET state='done',note=? WHERE id=?", (note,job))
        except Exception as exc:
            if isinstance(exc, ValueError):
                logging.warning("PPK job %d: %s",job,exc)
            else:
                logging.exception("PPK job %d failed",job)
            with self.db() as db:
                db.execute("UPDATE jobs SET state='failed',note=? WHERE id=?", (str(exc)[:500],job))
        finally:
            self.lock.release()

    def _import(self, db, p):
        target = p.get("target")
        if not isinstance(target,str) or not (target in ("inbox","local") or re.fullmatch(r"usb-[0-9a-f]{24}",target)):
            raise ValueError("Vyber soubor ze složky PPK, místních exportů nebo z připojeného USB.")
        stream, name = open_download(self.data/"exports",target,p.get("path"))
        with stream:
            stat = os.fstat(stream.fileno())
            with (gzip.GzipFile(fileobj=stream) if name.lower().endswith(".gz") else nullcontext(stream)) as src:
                head = src.read(65536)
                fmt = file_format(name.lower(),head)
                space(self.data,stat.st_size)
                db.execute("SAVEPOINT copy_input")
                asset = db.execute("INSERT INTO assets(name,format,bytes,imported) VALUES(?,?,0,?)",
                                   (name,fmt,int(time.time()*1000))).lastrowid
                digest = hashlib.sha256()
                seq = size = 0
                part = head
                while part:
                    digest.update(part)
                    if seq%16 == 0:
                        space(self.data,2*len(part))
                    db.execute("INSERT INTO chunks VALUES(?,?,?)",(asset,seq,part))
                    size += len(part)
                    seq += 1
                    part = src.read(CHUNK)
            after = os.fstat(stream.fileno())
            if (after.st_size,after.st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):
                raise ValueError("Zdrojový soubor se během importu změnil. Po dokončení kopírování import zopakuj.")
        sha = digest.hexdigest()
        old = db.execute("SELECT id FROM assets WHERE sha256=?",(sha,)).fetchone()
        if old:
            db.execute("ROLLBACK TO copy_input")
            db.execute("RELEASE copy_input")
            return f"Soubor již je v knihovně pod číslem {old[0]}."
        db.execute("UPDATE assets SET bytes=?,sha256=? WHERE id=?",(size,sha,asset))
        return f"Importován soubor č. {asset} · {name}"

    def _materialize(self, db, asset, folder, label):
        row = db.execute("SELECT format,bytes FROM assets WHERE id=?",(positive_id(asset),)).fetchone()
        if row is None:
            raise ValueError("Importovaný soubor nebyl nalezen.")
        fmt, size = row
        space(folder,size)
        path = folder/(label+"."+fmt)
        with path.open("wb") as f:
            for part, in db.execute("SELECT payload FROM chunks WHERE asset=? ORDER BY seq",(asset,)):
                f.write(part)
        return path,fmt

    def _ride(self, ride, folder):
        path = folder/"rover.sbf"
        uri = (self.data/"logger.sqlite3").as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True)) as db:
            row = db.execute("SELECT state,obs_epochs,raw_bytes FROM sessions WHERE id=?",(positive_id(ride),)).fetchone()
            if not row or row[0]=="recording" or not row[2]:
                raise ValueError("Vyber ukončenou jízdu se surovými daty.")
            if row[1] == 0:
                raise ValueError("Jízda nemá zaznamenané měřicí epochy MeasEpoch pro PPK.")
            space(folder,row[2])
            with path.open("wb") as f:
                last=0
                while True:
                    batch=db.execute("SELECT id,data FROM raw_chunks WHERE session_id=? AND id>? ORDER BY id LIMIT 8",
                                     (ride,last)).fetchall()
                    if not batch:
                        break
                    for last,part in batch:
                        f.write(part)
            if path.stat().st_size != row[2]:
                raise ValueError("Surový záznam jízdy není úplný.")
        return path,"sbf"

    def _solve(self, db, job, p):
        if not shutil.which("convbin") or not shutil.which("rnx2rtkp"):
            raise ValueError("Na Pi chybí balíček rtklib.")
        if p.get("rover") is not None and p.get("ride") is not None:
            raise ValueError("Vyber jeden zdroj měření roveru.")
        if p.get("rover") == p.get("base"):
            raise ValueError("Vyber rozdílná měření roveru a základny.")
        with tempfile.TemporaryDirectory(prefix=".formula-part-ppk-",dir=self.data) as tmp:
            folder = Path(tmp)
            rover = (self._ride(p["ride"],folder) if p.get("ride") is not None else
                     self._materialize(db,p.get("rover"),folder,"rover"))
            base = self._materialize(db,p.get("base"),folder,"base")
            rover_obs, nav = prepare(*rover,p.get("date"))
            base_obs, base_nav = prepare(*base,p.get("date"))
            nav.extend(base_nav)
            for aid in p.get("nav",[]):
                path,fmt = self._materialize(db,aid,folder,"nav"+str(positive_id(aid)))
                if fmt != "nav":
                    raise ValueError("Jako efemeridy vyber navigační soubor RINEX.")
                nav.append(path)
            if not nav:
                raise ValueError("Chybí efemeridy. Importuj navigační RINEX ze stejné doby.")
            if p.get("reference") == "header":
                coords = rinex_xyz(base_obs)
                if not coords:
                    raise ValueError("Základna nemá použitelné souřadnice XYZ v hlavičce. Zadej zaměřenou polohu.")
                ref = ["-r",*map(str,coords)]
            elif p.get("reference") == "manual":
                coords = p.get("llh")
                if (not isinstance(coords,list) or len(coords)!=3 or
                    any(type(x) not in (float,int) or not math.isfinite(x) for x in coords) or
                    not -90<=coords[0]<=90 or not -180<=coords[1]<=180 or not -1000<=coords[2]<=20000):
                    raise ValueError("Zkontroluj šířku, délku a elipsoidickou výšku základny.")
                ref = ["-l",*map(str,coords)]
            else:
                raise ValueError("Vyber zdroj souřadnic základny.")
            pos = folder/"solution.pos"
            run_tool(["rnx2rtkp",*SOLVER_OPTIONS,
                      *ref,"-o",pos,rover_obs,base_obs,*nav],folder)
            if not pos.is_file():
                raise ValueError("RTKLIB nevytvořil řešení. Zkontroluj časový překryv a efemeridy.")
            fixed = floating = total = 0
            program = "rnx2rtkp"
            with pos.open(encoding="ascii",errors="replace") as f:
                for line in f:
                    if line.startswith("% program") and ":" in line:
                        program = line.split(":",1)[1].strip()
                    if not line.strip() or line.lstrip().startswith("%"):
                        continue
                    v = line.split()
                    week,tow = int(v[0]),round(float(v[1])*1000)
                    lat,lon,h = map(float,v[2:5])
                    quality,ns = map(int,v[5:7])
                    stats = list(map(float,v[7:10]+v[13:15]))
                    if (not 0<=tow<604800000 or not -90<=lat<=90 or not -180<=lon<=180 or
                        not all(math.isfinite(x) for x in [h,*stats]) or len(stats)!=5):
                        raise ValueError("RTKLIB vrátil neplatnou epochu.")
                    db.execute("INSERT INTO epochs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (job,week,tow,lat,lon,h,quality,ns,*stats))
                    fixed += quality==1
                    floating += quality==2
                    total += 1
                    if total%4096 == 0:
                        space(folder)
            if not (fixed or floating):
                raise ValueError("Žádná společná epocha s RTK Fix/Float. Ověř časový překryv, fáze, efemeridy a referenci.")
            solver = json.dumps(dict(program=program,options=SOLVER_OPTIONS))
            db.execute("UPDATE jobs SET reference=?,solver=? WHERE id=?",(json.dumps(ref),solver,job))
            return f"{total} epoch · Fix {fixed} · Float {floating} · ostatní {total-fixed-floating}"

    def view(self, job=0, page=0):
        with self.db() as db:
            assets = [dict(r) for r in db.execute("SELECT id,name,format,bytes,sha256 FROM assets ORDER BY id DESC")]
            jobs = [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 100")]
            solutions = [dict(r) for r in db.execute("SELECT id,started,note FROM jobs WHERE kind='solve' AND state='done' ORDER BY id DESC")]
            if not job and solutions:
                job = solutions[0]["id"]
            count = db.execute("SELECT count(*) FROM epochs WHERE job=?",(job,)).fetchone()[0]
            page = min(page,max(0,(count-1)//50))
            rows = [dict(r) for r in db.execute("SELECT * FROM epochs WHERE job=? ORDER BY gps_week,tow_ms LIMIT 50 OFFSET ?",(job,page*50))]
            detail = db.execute("SELECT params,reference,solver,note FROM jobs WHERE id=? AND state='done' AND kind='solve'",(job,)).fetchone()
        with closing(sqlite3.connect((self.data/"logger.sqlite3").as_uri()+"?mode=ro",uri=True)) as rides:
            rides.row_factory=sqlite3.Row
            available=[dict(r) for r in rides.execute("SELECT id,name,obs_epochs FROM sessions WHERE state!='recording' AND raw_bytes>0 ORDER BY id DESC")]
        return dict(assets=assets,jobs=jobs,rides=available,solutions=solutions,job=job,epochs=rows,count=count,page=page,
                    detail=dict(detail) if detail else None)

    def csv(self, job):
        with self.db() as db:
            if not db.execute("SELECT 1 FROM jobs WHERE id=? AND kind='solve' AND state='done'",(job,)).fetchone():
                raise ValueError("Uložené řešení nebylo nalezeno.")
            buf=io.StringIO(newline="")
            writer=csv.writer(buf)
            writer.writerow(COLUMNS)
            yield buf.getvalue().encode()
            for row in db.execute(f"SELECT {','.join(COLUMNS)} FROM epochs WHERE job=? ORDER BY gps_week,tow_ms",(job,)):
                buf.seek(0)
                buf.truncate()
                writer.writerow(row)
                yield buf.getvalue().encode()

