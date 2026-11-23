"""Exercise the actual importer and RTKLIB on a temporary data volume."""
import argparse
import gzip
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ppk import PPK

FIXTURES = {
    "07590920.05o":"8474af556633e9c03293a8fb1e2c1f55180b42336b17574a84fda06eb6a02f9e",
    "30400920.05o":"732ba88d70412b6a70c145494a8030f79b844e99bd5225d0e7b7d982d2e2b540",
    "07590920.05n":"eb26dce205b59269147035be49db481d38dc51bb8601dac6e84c0c868bb8094a",
}


def wait(ppk, kind, params, expected="done"):
    job = ppk.start(kind,params)
    limit = time.monotonic()+60
    while time.monotonic()<limit:
        with ppk.db() as db:
            row = db.execute("SELECT state,note FROM jobs WHERE id=?",(job,)).fetchone()
        if row[0]!="running":
            assert row[0]==expected, row[1]
            return job
        time.sleep(.1)
    raise RuntimeError("Timed out waiting for PPK")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures",type=Path,help="Directory with the three RTKLIB RINEX sample files")
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        with sqlite3.connect(root/"logger.sqlite3") as db:
            db.execute("CREATE TABLE sessions(id INTEGER,name TEXT,state TEXT,raw_bytes INTEGER,obs_epochs INTEGER)")
            db.execute("INSERT INTO sessions VALUES (1,'Pouze polohové zprávy','stopped',1024,0)")
        ppk=PPK(root)
        ids=[]
        for name,sha in FIXTURES.items():
            if args.fixtures:
                data=(args.fixtures/name).read_bytes()
            else:
                url="https://raw.githubusercontent.com/tomojitakasu/RTKLIB/rtklib_2.4.3/test/data/rinex/"+name
                with urllib.request.urlopen(url,timeout=20) as response:
                    data=response.read()
            assert hashlib.sha256(data).hexdigest()==sha
            (ppk.inbox/name).write_bytes(data)
            wait(ppk,"import",dict(target="inbox",path=name))
            with ppk.db() as db:
                ids.append(db.execute("SELECT id FROM assets WHERE sha256=?",(sha,)).fetchone()[0])
        rover,base,nav=ids
        name="duplicate.obs.gz"
        (ppk.inbox/name).write_bytes(gzip.compress((ppk.inbox/"07590920.05o").read_bytes()))
        wait(ppk,"import",dict(target="inbox",path=name))
        for path in ppk.inbox.iterdir():
            path.unlink()
        params=dict(rover=rover,base=base,nav=[nav],reference="header")
        job=wait(ppk,"solve",params)
        wait(ppk,"solve",dict(params,nav=[]),"failed")
        wait(ppk,"solve",dict(ride=1,base=base,nav=[nav],reference="header"),"failed")
        manual=wait(ppk,"solve",dict(params,reference="manual",llh=[35.132066140,139.624302130,75.8027]))
        saved=PPK(root).view(job)
        assert len(saved["assets"])==3 and saved["count"]==115, saved["count"]
        assert all(row["quality"]==1 for row in saved["epochs"])
        assert abs(saved["epochs"][0]["lat"]-35.160875)<.00001
        assert len(b"".join(ppk.csv(job)).splitlines())==116
        assert "rnx2rtkp" in json.loads(saved["detail"]["solver"])["program"]
        manual_view=ppk.view(manual)
        assert manual_view["count"]==115 and abs(manual_view["epochs"][0]["height_m"]-saved["epochs"][0]["height_m"])<.001
        with ppk.db() as db:
            assert db.execute("SELECT count(*) FROM epochs JOIN jobs ON jobs.id=epochs.job WHERE jobs.state!='done'").fetchone()[0]==0
            assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        print(f"OK · {saved['detail']['note']} · ověřeny import, opětovné otevření databáze a CSV")


if __name__=="__main__":
    main()
