"""End-to-end check on the LAN. Creates one explicitly named test session on the Pi."""
import argparse
import binascii
import csv
import getpass
import http.cookiejar
import io
import json
from pathlib import Path
import ssl
import struct
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("host", nargs="?", default="formula-logger.local")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--cafile", type=Path, required=True, help="Ověřený veřejný TLS certifikát vlastního loggeru")
    args = parser.parse_args()
    origin = "https://" + args.host
    tls = ssl.create_default_context(cafile=str(args.cafile))
    tls.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    web = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=tls),
                                      urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = ""
    def fetch(path, body=None):
        req = urllib.request.Request(origin + path)
        if body is not None:
            req.data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
            req.add_header("Origin", origin)
            req.add_header("X-CSRF-Token", csrf)
        try:
            with web.open(req, timeout=12) as resp:
                data = resp.read()
                return json.loads(data) if resp.headers.get_content_type()=="application/json" else data
        except urllib.error.HTTPError as exc:
            raise RuntimeError((exc.code, exc.read(400).decode(errors="replace"))) from exc
    assert b"Formula" in fetch("/")
    for protected in ("/api/status", ":8444/"):
        try:
            fetch(protected)
        except RuntimeError as exc:
            assert exc.args[0][0] == 401, exc
        else:
            raise RuntimeError("Missing authentication at "+protected)
    csrf = fetch("/api/login", {"username":"formula69","password":getpass.getpass("Web password: ")})["csrf"]
    initial = fetch("/api/status")
    print("status", {k:v for k,v in initial.items() if k!="csrf"}, flush=True)
    assert b"firmwareTimeTag" in fetch(":8444/")
    assert len(fetch(":8444/jquery-1.9.1.min.js")) > 10000
    if args.inspect:
        return
    if initial["recording"]["active"] or not initial["device"]["connected"]:
        raise RuntimeError("Test needs an idle connected receiver")
    config = initial["settings"]
    started = False
    try:
        test_cfg = {**config, "rate_hz":5, "raw_observations":True}
        fetch("/api/settings",test_cfg)
        assert fetch("/api/status")["settings"] == test_cfg
        sid = fetch("/api/start", {"name":"Test USB bez antény – ověření instalace"})["id"]
        started = True
        time.sleep(3)
        first = fetch(f"/api/sessions/{sid}/points?limit=20")["points"]
        time.sleep(4)
        later = fetch(f"/api/sessions/{sid}/points?limit=40")["points"]
        fetch("/api/stop",{})
        started = False
        meta = next(s for s in fetch("/api/sessions")["sessions"] if s["id"]==sid)
        rows = list(csv.DictReader(io.StringIO(fetch(f"/api/sessions/{sid}/export.csv").decode())))
        raw = fetch(f"/api/sessions/{sid}/raw.bin")
        valid_blocks = {}
        i = 0
        while (i := raw.find(b"$@",i)) >= 0 and i+8 <= len(raw):
            crc, block, length = struct.unpack_from("<HHH",raw,i+2)
            if length>=8 and length%4==0 and i+length<=len(raw) and binascii.crc_hqx(raw[i+4:i+length],0)==crc:
                block &= 8191
                valid_blocks[block] = valid_blocks.get(block,0)+1
                i += length
            else:
                i += 2
        print("session",sid, "snapshots",len(first),len(later),"CSV rows",len(rows),"raw bytes",len(raw),"CRC-valid blocks",valid_blocks,"valid positions",sum(r["valid"]=="1" for r in rows),flush=True)
        assert meta["state"]=="stopped" and meta["samples"]==len(rows) and meta["raw_bytes"]==len(raw)
        assert len(raw)>0 and valid_blocks
        assert all(r["lat"]==r["lon"]=="" for r in rows if r["valid"]=="0")
    finally:
        if started:
            fetch("/api/stop",{})
        fetch("/api/settings",config)
        print("restored",fetch("/api/status")["settings"],flush=True)
        fetch("/api/logout",{})


if __name__=="__main__":
    main()

