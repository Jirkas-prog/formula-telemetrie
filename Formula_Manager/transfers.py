"""Stream completed rides and stationary tests into a new, atomically published export."""
import csv
import hashlib
import io
import json
import math
import os
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path

from mediafiles import disks, volume, media_action
from accuracy import centroid_coords


def reader(path):
    db=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)
    db.row_factory=sqlite3.Row
    return db


def csv_line(writer,buf,values):
    buf.seek(0)
    buf.truncate()
    writer.writerow(values)
    return buf.getvalue().encode("utf-8")


def file_parts(folder,name,chunks,limit,header=b""):
    result=[]
    path=Path(name)
    f=None
    try:
        def begin(part):
            filename=name if part==1 else f"{path.stem}.part{part:03}{path.suffix}"
            fd=(folder/filename).open("xb")
            h=hashlib.sha256()
            fd.write(header)
            h.update(header)
            return fd,h,filename
        def finish():
            f.flush()
            os.fsync(f.fileno())
            result.append(dict(name=filename,bytes=f.tell(),sha256=h.hexdigest()))
            f.close()
        f,h,filename=begin(1)
        for chunk in chunks:
            if f.tell()>len(header) and f.tell()+len(chunk)>limit:
                finish()
                f,h,filename=begin(len(result)+1)
            f.write(chunk)
            h.update(chunk)
        finish()
    finally:
        if f and not f.closed:
            f.close()
    return result


def export_csv(folder,name,cursor,limit,extra=(),transform=None):
    buf=io.StringIO(newline="")
    writer=csv.writer(buf)
    header=csv_line(writer,buf,[col[0] for col in cursor.description]+list(extra))
    return file_parts(folder,name,(csv_line(writer,buf,transform(row) if transform else row) for row in cursor),limit,header)


class Transfers:
    def __init__(self, data):
        self.data=Path(data).resolve()
        self.root=self.data/"exports"
        self.root.mkdir(exist_ok=True)
        self.index=self.data/"transfers.sqlite3"
        self.lock=threading.RLock()
        self.thread=None
        with closing(sqlite3.connect(self.index)) as db,db:
            db.executescript("CREATE TABLE IF NOT EXISTS sent(target TEXT,item TEXT,PRIMARY KEY(target,item));"
                             "CREATE TABLE IF NOT EXISTS last_job(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT);")
            last=db.execute("SELECT value FROM last_job WHERE id=1").fetchone()
        self.job=json.loads(last[0]) if last else {"state":"idle"}
        if self.job["state"]=="running":
            self.update(state="failed",error="Export byl přerušen restartem. Lze jej spustit znovu.")

    def update(self,**values):
        with self.lock:
            self.job.update(values)
            with closing(sqlite3.connect(self.index)) as db,db:
                db.execute("INSERT OR REPLACE INTO last_job VALUES(1,?)",(json.dumps(self.job),))

    def status(self):
        with self.lock:
            return dict(self.job)

    def targets(self,include_readonly=False):
        return [dict(key="local",name="Exporty na NVMe",fs="NVMe",mount=str(self.root),
                     size=shutil.disk_usage(self.root).total),*disks(include_readonly)]

    def mount(self,key,action):
        with self.lock:
            if self.job["state"]=="running" and self.job["target"]==key:
                raise RuntimeError("Na tuto jednotku probíhá export.")
            media_action(key,action)

    def catalog(self):
        with closing(reader(self.data/"logger.sqlite3")) as rides, closing(reader(self.data/"accuracy.sqlite3")) as acc:
            rows=[dict(key=f"ride-{r[0]}",kind="ride",name=r[1],t=r[2],n=r[3])
                  for r in rides.execute("SELECT id,name,started_ms,samples FROM sessions WHERE state!='recording'")]
            rows.extend(dict(key=f"test-{r[0]}",kind="test",name=r[1],t=r[2],n=r[3]) for r in acc.execute(
                "SELECT r.id,m.name,r.started_ms,r.n FROM runs r JOIN marks m ON m.id=r.mark_id WHERE r.state!='running'"))
        return sorted(rows,key=lambda r:(r["t"],r["key"]),reverse=True)

    def start(self,data):
        target,scope=data.get("target"),data.get("scope")
        kinds=data.get("kinds")
        if not isinstance(kinds,list) or not kinds or any(k not in ("ride","test") for k in kinds):
            raise ValueError("Vyber jízdy nebo testy.")
        with self.lock:
            if self.job["state"]=="running":
                raise RuntimeError("Export právě běží.")
            with volume(self.root,target):
                pass
            rows=[r for r in self.catalog() if r["kind"] in kinds]
            if scope=="selected":
                keys=data.get("items")
                if not isinstance(keys,list) or not all(isinstance(k,str) for k in keys):
                    raise ValueError("Vyber položky exportu.")
                keys=set(keys)
                rows=[r for r in rows if r["key"] in keys]
                if len(rows)!=len(keys):
                    raise ValueError("Některý záznam již není k dispozici. Obnov seznam.")
            elif scope in ("latest","days"):
                n=data.get("amount")
                if type(n) is not int or not 1<=n<=1000000:
                    raise ValueError("Zadej kladný počet.")
                rows=rows[:n] if scope=="latest" else [r for r in rows if r["t"]>=(time.time()-n*86400)*1000]
            elif scope=="new":
                with closing(sqlite3.connect(self.index)) as db:
                    sent={r[0] for r in db.execute("SELECT item FROM sent WHERE target=?",(target,))}
                rows=[r for r in rows if r["key"] not in sent]
            elif scope!="all":
                raise ValueError("Neznámý výběr exportu.")
            if not rows:
                raise ValueError("Výběru neodpovídá žádný ukončený záznam.")
            name="Formula-"+time.strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:10]
            self.job={}
            self.update(state="running",target=target,folder=name,done=0,total=len(rows),error=None)
            self.thread=threading.Thread(target=self._write,args=(target,name,rows),daemon=True,name="usb-export")
            self.thread.start()
            return dict(self.job)

    def _item(self,dest,item,limit):
        kind,key=item["key"].split("-")
        ident=int(key)
        files=[]
        with closing(reader(self.data/("logger.sqlite3" if kind=="ride" else "accuracy.sqlite3"))) as db:
            db.execute("BEGIN")
            if kind=="ride":
                row=db.execute("SELECT * FROM sessions WHERE id=? AND state!='recording'",(ident,)).fetchone()
                if not row:
                    raise ValueError("Jízda již není dostupná.")
                meta=dict(row)
                meta["settings"]=json.loads(meta.pop("settings_json"))
                for table in ("samples","events"):
                    cursor=db.execute(f"SELECT * FROM {table} WHERE session_id=? ORDER BY id",(ident,))
                    files+=export_csv(dest,table+".csv",cursor,limit)
                chunks=(r[0] for r in db.execute("SELECT data FROM raw_chunks WHERE session_id=? ORDER BY id",(ident,)))
                files+=file_parts(dest,"receiver.sbf",chunks,limit)
            else:
                row=db.execute("SELECT * FROM runs WHERE id=? AND state!='running'",(ident,)).fetchone()
                if not row:
                    raise ValueError("Test již není dostupný.")
                meta=dict(row)
                meta["mark"]=dict(db.execute("SELECT * FROM marks WHERE id=?",(row["mark_id"],)).fetchone())
                count=row["n"]
                e=row["sum_e"]/count if count else None
                n=row["sum_n"]/count if count else None
                sums=[0.,0.]
                def polar(p):
                    x,y=p["e"]-e,p["n"]-n
                    r=math.hypot(x,y)
                    sums[0]+=r
                    sums[1]=max(sums[1],r)
                    return [*p,x,y,r,math.degrees(math.atan2(x,y))%360 if r else None]
                cursor=db.execute("SELECT * FROM fixes WHERE run_id=? ORDER BY epoch",(ident,))
                files=export_csv(dest,"fixes.csv",cursor,limit,("east_from_centroid_m","north_from_centroid_m","radius_m","bearing_deg"),polar)
                meta.update(centroid_e_m=e,centroid_n_m=n,mean_radius_m=sums[0]/count if count else None,max_radius_m=sums[1] if count else None)
                if count:
                    meta["centroid_lat_lon"]=centroid_coords(e,n,meta["mark"]["anchor_lat"],meta["mark"]["anchor_lon"])
        meta["files"]=files
        self._json(dest/"metadata.json",meta)

    @staticmethod
    def _json(path,obj):
        with path.open("x",encoding="utf-8") as out:
            json.dump(obj,out,ensure_ascii=False,indent=2,allow_nan=False)
            out.flush()
            os.fsync(out.fileno())

    @staticmethod
    def _syncdir(path):
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _write(self,target,name,rows):
        try:
            with volume(self.root,target) as (fd,fs):
                root=Path(f"/proc/self/fd/{fd}")
                stage=root/(".formula-part-"+name)
                stage.mkdir()
                try:
                    limit=4000*1024**2 if fs in ("vfat","fat","msdos") else 2**63-1
                    for i,item in enumerate(rows,1):
                        dest=stage/item["key"]
                        dest.mkdir()
                        self._item(dest,item,limit)
                        self._syncdir(dest)
                        self.update(done=i)
                    self._json(stage/"manifest.json",dict(format_version=1,created_ms=round(time.time()*1000),items=rows))
                    self._syncdir(stage)
                    stage.rename(root/name)
                    self._syncdir(root)
                except BaseException:
                    if stage.exists():
                        shutil.rmtree(stage,ignore_errors=True)
                    raise
            with closing(sqlite3.connect(self.index)) as db,db:
                db.executemany("INSERT OR IGNORE INTO sent VALUES(?,?)",((target,r["key"]) for r in rows))
            self.update(state="done")
        except Exception as exc:
            self.update(state="failed",error=str(exc)[:400])

