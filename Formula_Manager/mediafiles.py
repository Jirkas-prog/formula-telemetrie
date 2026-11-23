"""USB volumes via UDisks and a directory-fd confined, read-only file browser."""
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

FILESYSTEMS = {"vfat", "fat", "msdos", "exfat", "ntfs", "ntfs3"}


def disks(include_readonly=False):
    ls = subprocess.run(["lsblk","--tree","--json","--bytes","--output",
                         "NAME,PATH,TYPE,TRAN,RO,SIZE,FSTYPE,LABEL,UUID,PARTUUID,START,MOUNTPOINTS,SERIAL"],
                        capture_output=True,check=True,text=True,timeout=6)
    result = []
    for disk in json.loads(ls.stdout)["blockdevices"]:
        if disk["type"] != "disk" or disk["tran"] != "usb" or (disk["ro"] and not include_readonly):
            continue
        children = disk.get("children",[])
        if any(p in ("/","/boot","/boot/firmware","[SWAP]") for v in [disk,*children] for p in v["mountpoints"] if p):
            continue
        for v in children or [disk]:
            if v.get("children") or (v["ro"] and not include_readonly) or not v["size"] or v["fstype"] not in FILESYSTEMS:
                continue
            # UDisks handles USB mass storage. Exclude the GNSS receiver's own card reader.
            sysdev = Path("/sys/class/block",Path(disk["path"]).name,"device").resolve()
            if any((n/"manufacturer").is_file() and "septentrio" in (n/"manufacturer").read_text().lower()
                   for n in (sysdev,*sysdev.parents)):
                continue
            serial = disk.get("serial") or ""
            media_id = v.get("uuid") or v.get("partuuid") or serial
            if not media_id:
                # Without a persistent ID, keep incremental exports scoped to this attachment.
                seq = (Path("/sys/class/block")/Path(disk["path"]).name/"diskseq").read_text().strip()
                media_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()+"-"+seq
            identity = f"{serial}|{media_id}|{v.get('start')}|{v['size']}"
            key = "usb-"+hashlib.sha256(identity.encode()).hexdigest()[:24]
            result.append(dict(key=key,path=v["path"],name=v["label"] or Path(v["path"]).name,
                               fs=v["fstype"],size=v["size"],readonly=bool(disk["ro"] or v["ro"]),
                               mount=next((p for p in v["mountpoints"] if p),None)))
    return result


def pick(key, include_readonly=False):
    choices = [d for d in disks(include_readonly) if d["key"]==key]
    if len(choices)!=1:
        raise ValueError("Vybranou USB jednotku se nepodařilo jednoznačně najít.")
    return choices[0]


def media_action(key, op):
    d = pick(key, include_readonly=True)
    if op=="mount" and d["mount"] or op=="unmount" and not d["mount"]:
        return
    args = ["udisksctl",op,"--no-user-interaction","-b",d["path"]]
    if op=="mount":
        args += ["-o","nosuid,nodev,noexec"+(",ro" if d["readonly"] else "")]
    r = subprocess.run(args,capture_output=True,text=True,timeout=40)
    if r.returncode:
        raise ValueError("USB: "+(r.stderr or r.stdout).strip()[:400])


def mount_field(s):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1],8)), s)


@contextmanager
def volume(root, key, include_readonly=False):
    if key=="local":
        target,fs = root,"local"
    else:
        d = pick(key,include_readonly)
        if not d["mount"]:
            raise ValueError("Nejdřív připoj USB jednotku tlačítkem Připojit.")
        target,fs = d["mount"],d["fs"]
    fd = os.open(target,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        if key!="local":
            mid = next(line.split()[1] for line in Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines() if line.startswith("mnt_id:"))
            mounted = False
            for line in Path("/proc/self/mountinfo").read_text().splitlines():
                head,tail = line.split(" - ",1)
                if head.split()[0]==mid and mount_field(head.split()[4])==target:
                    source = mount_field(tail.split()[1])
                    mounted = os.path.realpath(source)==os.path.realpath(d["path"])
                    break
            if not mounted:
                raise ValueError("Jednotka byla odpojena nebo se změnil přípojný bod.")
        yield fd,fs
    finally:
        os.close(fd)


def path_parts(path):
    if not isinstance(path,str) or len(path)>4096 or "\x00" in path or path.startswith("/"):
        raise ValueError("Neplatná cesta.")
    parts=path.split("/") if path else []
    if any(p in ("",".","..") or p.startswith(".formula-part-") for p in parts):
        raise ValueError("Neplatná cesta.")
    return parts


@contextmanager
def directory(fd, parts):
    current=os.dup(fd)
    try:
        for part in parts:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
            os.close(current)
            current=child
        yield current
    finally:
        os.close(current)


def browse(root, key, path, page):
    if key == "inbox":
        root,key = root.parent/"imports","local"
    data_area = key == "data"
    with volume(root.parent if data_area else root,"local" if data_area else key,include_readonly=True) as (fd,_), directory(fd,path_parts(path)) as dest:
        rows=[]
        with os.scandir(dest) as entries:
            for file in entries:
                if file.name.startswith(".formula-part-"):
                    continue
                if data_area and (file.name.startswith(".formula-snapshot-") or file.name.endswith(("-wal","-shm","-journal"))):
                    continue
                try:
                    info=file.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                folder=stat.S_ISDIR(info.st_mode)
                if folder or stat.S_ISREG(info.st_mode):
                    rows.append(dict(name=file.name,folder=folder,size=info.st_size,t=int(info.st_mtime*1000)))
        rows.sort(key=lambda x:(not x["folder"],x["name"].casefold()))
        page=min(max(0,page),max(0,(len(rows)-1)//100))
        return dict(entries=rows[page*100:page*100+100],total=len(rows),page=page)


def open_download(root,key,path):
    if key == "inbox":
        root,key = root.parent/"imports","local"
    parts=path_parts(path)
    if not parts or any(p.startswith(".formula-part-") for p in parts):
        raise ValueError("Vyber dokončený soubor.")
    if key=="data":
        if any(p.startswith(".formula-snapshot-") or p.endswith(("-wal","-shm","-journal")) for p in parts):
            raise ValueError("Zvol hlavní databázový soubor.")
        if len(parts)==1 and parts[0] in ("logger.sqlite3","accuracy.sqlite3","transfers.sqlite3","hardware.sqlite3","ppk.sqlite3"):
            source=root.parent/parts[0]
            if source.is_symlink():
                raise ValueError("Neplatný databázový soubor.")
            snap=tempfile.NamedTemporaryFile(dir=root.parent,prefix=".formula-snapshot-")
            try:
                with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as db, closing(sqlite3.connect(snap.name)) as copy:
                    db.execute("BEGIN")
                    db.execute("SELECT count(*) FROM sqlite_schema").fetchone()
                    db.backup(copy,pages=256)
                snap.seek(0)
                return snap,parts[0]
            except BaseException:
                snap.close()
                raise
        root,key=root.parent,"local"
    with volume(root,key,include_readonly=True) as (fd,_), directory(fd,parts[:-1]) as dest:
        f=os.fdopen(os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dest),"rb")
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            f.close()
            raise ValueError("Vyber běžný soubor.")
        return f,parts[-1]
