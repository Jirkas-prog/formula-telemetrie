"""Local HTTP application for the Formula GNSS manager. nginx terminates TLS."""
import csv
import hashlib
import hmac
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import threading
import time
from contextlib import closing, contextmanager
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from collector import Collector
from corrections import radio_names
from diagnostics import PARAMETERS, EDITABLE
from accuracy import Accuracy
from hardware import Hardware
from ppk import PPK, positive_id
from transfers import Transfers
from mediafiles import browse, open_download


STATIC = Path(__file__).resolve().parent / "static"
SMB_PASSWORD = Path("/etc/formula-manager/samba-password")
COOKIE = "formula_session"
COOKIE_MAX_AGE = 400 * 24 * 60 * 60
POINT_COLUMNS = ("id", "seq", "t_ms", "gps_week", "tow_ms", "valid", "lat", "lon",
                 "alt_m", "speed_kmh", "sats", "mode", "error_code")
SESSION_ROUTE = re.compile(r"/api/sessions/([1-9][0-9]{0,15})/(points|export\.csv|raw\.bin)")
EDIT_ROUTE = re.compile(r"/api/sessions/([1-9][0-9]{0,15})/(rename|delete)")


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def wifi_profiles(payload):
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            sock.connect("/run/formula-wifi-profiles.sock")
            sock.sendall(json.dumps(payload,ensure_ascii=False).encode()+b"\n")
            with sock.makefile("rb") as stream:
                result=json.load(stream)
    except (OSError,ValueError) as exc:
        raise Problem(503,"Správce Wi-Fi neodpověděl. Obnov seznam profilů.") from exc
    if "error" in result:
        raise Problem(400,result["error"])
    return result


class SessionAccess:
    def __init__(self):
        self.start_or_delete = threading.Lock()
        self.lock = threading.Lock()
        self.readers = {}
        self.deleting = None

    @contextmanager
    def maintenance(self):
        if not self.start_or_delete.acquire(blocking=False):
            raise Problem(409, "Probíhá údržba záznamu. Zkus to za chvíli.")
        try:
            yield
        finally:
            self.start_or_delete.release()

    @contextmanager
    def reading(self, session_id):
        # Exports release their SQLite snapshot between pages while keeping this ride intact.
        with self.lock:
            if self.deleting == session_id:
                raise Problem(409, "Tato jízda se právě maže.")
            self.readers[session_id] = self.readers.get(session_id, 0) + 1
        try:
            yield
        finally:
            with self.lock:
                self.readers[session_id] -= 1
                if not self.readers[session_id]:
                    del self.readers[session_id]

    @contextmanager
    def deletion(self, session_id):
        with self.maintenance():
            with self.lock:
                if session_id in self.readers:
                    raise Problem(409, "Probíhá čtení nebo export této jízdy. Po dokončení akci zopakuj.")
                self.deleting = session_id
            try:
                yield
            finally:
                with self.lock:
                    self.deleting = None


def session_name(value, required=False):
    if (not isinstance(value, str) or len(value) > 120 or any(ord(ch) < 32 for ch in value)
            or (required and not value.strip())):
        raise Problem(400, "Zadej platný název jízdy o nejvýše 120 znacích.")
    return value.strip()


def change_session(db_path, session_id, new_name):
    # This transaction either changes the entire ride or leaves it intact on any failure.
    try:
        with closing(sqlite3.connect(db_path, timeout=0.3)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA secure_delete=OFF")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise Problem(404, "Jízda nebyla nalezena.")
            if row[0] not in ("stopped", "interrupted"):
                raise Problem(409, "Tuto jízdu lze upravit až po ukončení záznamu.")
            if new_name is not None:
                db.execute("UPDATE sessions SET name=? WHERE id=?", (new_name, session_id))
                return
            if db.execute("SELECT 1 FROM sessions WHERE state='recording' LIMIT 1").fetchone():
                raise Problem(409, "Smazání je dostupné po ukončení probíhajícího záznamu.")
            for table in ("events", "raw_chunks", "samples"):
                db.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    except sqlite3.OperationalError as exc:
        primary = getattr(exc, "sqlite_errorcode", 0) & 255
        if primary in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise Problem(409, "Databázi právě používá logger. Akci zopakuj.") from exc
        if primary == sqlite3.SQLITE_FULL:
            raise Problem(507, "Na SSD chybí místo pro dokončení operace.") from exc
        raise


class Access:
    def __init__(self, directory):
        self.user = os.environ["FORMULA_USER"]
        salt, digest = os.environ["FORMULA_PASSWORD_HASH"].split(":")
        self.salt, self.digest = bytes.fromhex(salt), bytes.fromhex(digest)
        if len(self.salt) < 16 or len(self.digest) != 32:
            raise ValueError("Invalid login hash format")
        self.lock = threading.Lock()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(directory / "sessions.sqlite3", check_same_thread=False)
        self.key = hmac.digest(self.digest, self.user.encode(), "sha256")
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS sessions "
                            "(token BLOB PRIMARY KEY, csrf TEXT NOT NULL, expires INTEGER NOT NULL)")
            self.db.execute("DELETE FROM sessions WHERE expires <= ?", (int(time.time()),))
        self.failures = {}
        self.secure = os.getenv("FORMULA_COOKIE_SECURE", "1") != "0"

    def login(self, client, username, password):
        now = time.monotonic()
        if not isinstance(username, str) or not isinstance(password, str):
            raise Problem(400, "Zadej uživatelské jméno a heslo.")
        with self.lock:
            self.failures = {key: value for key, value in self.failures.items() if now < value[1]}
            count, until = self.failures.get(client, (0, now + 180))
            if count >= 8:
                raise Problem(429, "Příliš mnoho pokusů. Zkus to za tři minuty.")
            self.failures[client] = (count + 1, until)
        digest = hashlib.scrypt(password.encode(), salt=self.salt, n=16384, r=8, p=1, dklen=32)
        if not hmac.compare_digest(self.digest, digest) or self.user != username:
            raise Problem(401, "Nesprávné uživatelské jméno nebo heslo.")
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.lock, self.db:
            self.failures.pop(client, None)
            stamp = int(time.time())
            self.db.execute("DELETE FROM sessions WHERE expires <= ?", (stamp,))
            self.db.execute("INSERT INTO sessions(token, csrf, expires) VALUES(?,?,?)",
                            (self.token_key(sid), csrf, stamp + COOKIE_MAX_AGE))
        return sid, csrf

    def token_key(self, sid):
        return hmac.digest(self.key, sid.encode(), "sha256")

    def check(self, sid, renew=False):
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", sid):
            raise Problem(401, "Přihlas se ke správě loggeru.")
        token = self.token_key(sid)
        now = int(time.time())
        with self.lock, self.db:
            session = self.db.execute("SELECT csrf FROM sessions WHERE token=? AND expires>?",
                                      (token, now)).fetchone()
            if not session:
                raise Problem(401, "Přihlas se ke správě loggeru.")
            if renew:
                self.db.execute("UPDATE sessions SET expires=? WHERE token=?", (now + COOKIE_MAX_AGE, token))
            return session[0]

    def logout(self, sid):
        with self.lock, self.db:
            self.db.execute("DELETE FROM sessions WHERE token=?", (self.token_key(sid),))

    def cookie(self, sid):
        attributes = "; Secure" if self.secure else ""
        return f"{COOKIE}={sid}; Max-Age={COOKIE_MAX_AGE if sid else 0}; Path=/; HttpOnly; SameSite=Strict{attributes}"


class Handler(BaseHTTPRequestHandler):
    server_version = "FormulaManager"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(45)
        self.started_response = False

    def log_message(self, fmt, *args):
        pass  # nginx logs requests. Keep session tokens and credentials out of logs.

    def headers_for(self, code, content_type=None, size=None, extra=None):
        self.started_response = True
        self.send_response(code)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        host = self.headers.get("Host", "").partition(":")[0].lower()
        if not re.fullmatch(r"formula-logger(?:\.local)?|(?:[0-9]{1,3}\.){3}[0-9]{1,3}", host):
            host = "formula-logger.local"
        self.send_header("Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
            f"connect-src 'self'; frame-src https://{host}:8444; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if content_type:
            self.send_header("Content-Type", content_type)
        if size is not None:
            self.send_header("Content-Length", str(size))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def json(self, payload, status=200, extra=None):
        data = json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode()
        self.headers_for(status, "application/json; charset=utf-8", len(data), extra)
        self.wfile.write(data)

    def body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise Problem(400, "Neplatná délka požadavku.") from None
        if not 0 <= length <= 8192:
            raise Problem(413, "Požadavek je příliš velký.")
        if self.headers.get_content_type() != "application/json":
            raise Problem(415, "Požadavek musí obsahovat JSON.")
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError, RecursionError):
            raise Problem(400, "Požadavek neobsahuje platný JSON.") from None
        if not isinstance(value, dict):
            raise Problem(400, "Očekávám objekt JSON.")
        return value

    def session_cookie(self):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except CookieError:
            return ""
        value = jar.get(COOKIE)
        return value.value if value else ""

    def do_GET(self):
        self.handle_route(False)

    def do_POST(self):
        self.handle_route(True)

    def handle_route(self, write):
        try:
            url = urlsplit(self.path)
            if write:
                self.post(url.path)
            else:
                self.get(url.path, parse_qs(url.query))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Problem as exc:
            self.send_problem(exc.status, str(exc))
        except Exception:
            logging.exception("Request failed")
            self.send_problem(500, "Operaci se nepodařilo dokončit. Podrobnosti jsou v protokolu služby.")

    def send_problem(self, code, message):
        if self.started_response:
            self.close_connection = True
            return
        self.json({"error": message}, code)

    def post(self, path):
        access, collector = self.server.access, self.server.collector
        origin = self.headers.get("Origin")
        scheme = "https" if access.secure else "http"
        if origin and origin != f"{scheme}://{self.headers.get('Host', '')}":
            raise Problem(403, "Původ požadavku neodpovídá správci.")
        if path == "/api/login":
            data = self.body()
            peer = self.client_address[0]
            # Only trust nginx's own X-Real-IP header on the loopback listener.
            client = self.headers.get("X-Real-IP", peer) if peer in ("127.0.0.1", "::1") else peer
            sid, csrf = access.login(client, data.get("username"), data.get("password"))
            self.json({"csrf": csrf}, extra={"Set-Cookie": access.cookie(sid)})
            return
        sid = self.session_cookie()
        csrf = access.check(sid)
        if not hmac.compare_digest(self.headers.get("X-CSRF-Token", "").encode(), csrf.encode()):
            raise Problem(403, "Neplatný ověřovací token. Obnov stránku.")
        data = self.body()
        try:
            if path == "/api/logout":
                access.logout(sid)
                self.json({"ok": True}, extra={"Set-Cookie": access.cookie("")})
            elif path in ("/api/wifi/order","/api/wifi/save","/api/wifi/remove","/api/wifi/test-eduroam"):
                self.json(wifi_profiles({**data,"op":path.rsplit("/",1)[1]}))
            elif path == "/api/network-drive/password":
                try:
                    password = SMB_PASSWORD.read_text(encoding="utf-8").removesuffix("\n")
                except FileNotFoundError:
                    raise Problem(404, "Správce zatím nezpřístupnil heslo síťového disku.") from None
                self.json({"password": password})
            elif path == "/api/accuracy/mark":
                self.json({"id": self.server.accuracy.save_mark(data)})
            elif path in ("/api/accuracy/start","/api/accuracy/stop","/api/accuracy/reset"):
                self.json({"id": self.server.accuracy.change_run(path.rsplit("/",1)[1],data)})
            elif path == "/api/accuracy/reference":
                self.server.accuracy.reference(data.get("mark"),data.get("run"))
                self.json({"ok":True})
            elif path in ("/api/ppk/import","/api/ppk/solve"):
                self.json({"job":self.server.ppk.start(path.rsplit("/",1)[1],data)},202)
            elif path == "/api/transfers/start":
                self.json(self.server.transfers.start(data),202)
            elif path in ("/api/media/mount","/api/media/unmount"):
                self.server.transfers.mount(data.get("target"),path.rsplit("/",1)[1])
                self.json({"ok":True})
            elif path == "/api/start":
                name = session_name(data.get("name", ""))
                with self.server.session_access.maintenance():
                    result = collector.start_logging(name)
                self.json({"ok": True, "id": result}, 201)
            elif path == "/api/stop":
                collector.stop_logging()
                self.json({"ok": True})
            elif path in ("/api/settings", "/api/startup"):
                if not data:
                    raise Problem(400, "Prázdné nastavení.")
                saved = collector.configure(data, startup=(path == "/api/startup"))
                self.json({"ok": True, "settings": saved})
            elif path == "/api/rtk":
                collector.configure_rtk(data)
                self.json({"ok": True})
            elif path == "/api/receiver":
                answer = collector.receiver_query(data.get("action"), data.get("name"), data.get("arguments"))
                self.json({"reply": answer})
            elif edit := EDIT_ROUTE.fullmatch(path):
                session_id = int(edit[1])
                if edit[2] == "rename":
                    change_session(collector.db_path, session_id, session_name(data.get("name"), required=True))
                else:
                    confirmed = data.get("confirm_id")
                    if type(confirmed) is not int or confirmed != session_id:
                        raise Problem(400, "Smazání vyžaduje výslovné potvrzení vybrané jízdy.")
                    with self.server.session_access.deletion(session_id):
                        change_session(collector.db_path, session_id, None)
                self.json({"ok": True})
            else:
                raise Problem(404, "Adresa neexistuje.")
        except ValueError as exc:
            raise Problem(400, str(exc)) from exc
        except RuntimeError as exc:
            raise Problem(409, str(exc)) from exc

    def get(self, path, query):
        if not path.startswith("/api/"):
            self.static(path)
            return
        sid = self.session_cookie()
        renew = path == "/api/status" and query.get("renew") == ["1"]
        csrf = self.server.access.check(sid, renew=renew)
        c = self.server.collector
        if path == "/api/auth/check":
            self.headers_for(HTTPStatus.NO_CONTENT)
        elif path == "/api/wifi":
            self.json(wifi_profiles({"op":"list"}))
        elif path == "/api/network-drive":
            dns = None
            try:
                result = subprocess.run(["tailscale","status","--json"],capture_output=True,timeout=2)
                status = json.loads(result.stdout)
                if status.get("BackendState") == "Running":
                    name = (status.get("Self") or {}).get("DNSName","").rstrip(".")
                    if re.fullmatch(r"[a-zA-Z0-9.-]+",name):
                        dns = name
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            address = None
            try:
                interface = subprocess.run(["ip","-j","-4","addr","show","dev","wlan0"],
                                           capture_output=True,check=True,timeout=1)
                address = next((a["local"] for dev in json.loads(interface.stdout)
                                for a in dev.get("addr_info",[]) if a.get("scope") == "global"),None)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            self.json({"local": socket.gethostname().split(".")[0]+".local", "tailscale": dns, "wifi_ip":address,
                       "username":"formula69","share":"PPK","has_password":SMB_PASSWORD.is_file()})
        elif path == "/api/accuracy":
            try:
                args=[int(query.get(k,["0"])[0]) for k in ("mark","run","page")]
                if any(v<0 or v>2**63-1 for v in args):
                    raise ValueError
            except ValueError:
                raise Problem(400,"Neplatný výběr testu.") from None
            self.json(self.server.accuracy.view(*args))
        elif path == "/api/hardware":
            try:
                minutes = int(query.get("minutes", ["30"])[0])
                end_ms = int(query["end_ms"][0]) if "end_ms" in query else None
                if minutes not in (1, 5, 15, 30) or (end_ms is not None and not 0 <= end_ms < 2**63):
                    raise ValueError
            except ValueError:
                raise Problem(400, "Neplatné období historie hardwaru.") from None
            self.json(self.server.hardware.snapshot(minutes, end_ms))
        elif path in ("/api/ppk","/api/ppk/result.csv"):
            try:
                job = int(query.get("job",["0"])[0])
                page = int(query.get("page",["0"])[0])
                if not 0<=job<2**63 or not 0<=page<2**50:
                    raise ValueError("Neplatný výběr výsledku PPK.")
                if path.endswith(".csv"):
                    with closing(self.server.ppk.csv(positive_id(job))) as chunks:
                        header = next(chunks)
                        self.headers_for(200,"text/csv; charset=utf-8",extra={"Content-Disposition":f'attachment; filename="ppk-{job}.csv"'})
                        self.wfile.write(header)
                        for chunk in chunks:
                            self.wfile.write(chunk)
                else:
                    self.json(self.server.ppk.view(job,page))
            except ValueError as exc:
                raise Problem(400,str(exc)) from exc
        elif path == "/api/media":
            self.json({"targets":self.server.transfers.targets(include_readonly=query.get("browse")==["1"])})
        elif path == "/api/transfers":
            self.json({"items":self.server.transfers.catalog(),"job":self.server.transfers.status()})
        elif path == "/api/transfers/job":
            self.json(self.server.transfers.status())
        elif path in ("/api/files","/api/files/download"):
            target=query.get("target",["local"])[0]
            file=query.get("path",[""])[0]
            try:
                if path == "/api/files":
                    self.json(browse(self.server.transfers.root,target,file,int(query.get("page",["0"])[0])))
                else:
                    stream,name=open_download(self.server.transfers.root,target,file)
                    with stream:
                        self.headers_for(200,"application/octet-stream",os.fstat(stream.fileno()).st_size,
                                         {"Content-Disposition":"attachment; filename*=UTF-8''"+quote(name,safe="")})
                        shutil.copyfileobj(stream,self.wfile)
            except (ValueError,OSError) as exc:
                raise Problem(400,"Soubor nebo jednotka nejsou dostupné. "+str(exc)) from exc
        elif path == "/api/receiver/overview":
            self.json(c.receiver_overview())
        elif path == "/api/diagnostics":
            try:
                block = int(query.get("block", ["4007"])[0])
            except ValueError:
                raise Problem(400, "Neplatné číslo SBF.") from None
            self.json(c.diagnostics(block))
        elif path == "/api/receiver/parameters":
            try:
                menu = c.receiver_query("catalog", None)
            except RuntimeError as exc:
                raise Problem(503, str(exc)) from exc
            getters = set(re.findall(r"(?m)^\w+[ \t]*,[ \t]*get(\w+)[ \t]*$", menu))
            setters = set(re.findall(r"(?m)^\w+[ \t]*,[ \t]*set(\w+)[ \t]*$", menu))
            if not getters:
                raise Problem(502, "Přijímač nevrátil katalog parametrů.")
            self.json({"parameters": [
                dict(name=k, group=PARAMETERS.get(k, "Další parametry firmwaru"),
                     readable=k in PARAMETERS, editable=k in EDITABLE and k in setters)
                for k in sorted(getters)]})
        elif path == "/api/status":
            s = c.status()
            db = Path(c.db_path)
            size = 0
            for suffix in ("", "-wal", "-shm"):
                try:
                    size += Path(str(db) + suffix).stat().st_size
                except FileNotFoundError:
                    pass
            self.json({
                "device": {"connected": s["connected"], "name": s["device"], "error": s["error"],
                           "age_s": s["age_s"], "rx_bytes": s["rx_bytes"], "crc_errors": s["crc_errors"],
                           "settings_applied": s.get("settings_applied", False)},
                "latest": s["latest"], "recording": {"active": s["logging"], "id": s["session_id"]},
                "manual_settings": s["manual_settings"], "startup_settings": s["startup_settings"],
                "rtk": s["rtk"], "corrections": s["corrections"], "radios": radio_names(),
                "settings": s["settings"], "database": {"size_bytes": size, "free_bytes": shutil.disk_usage(db.parent).free},
                "receiver_url": os.getenv("FORMULA_RECEIVER_UI") == "1",
                "now_ms": time.time_ns() // 1000000, "csrf": csrf},
                extra={"Set-Cookie": self.server.access.cookie(sid)} if renew else None)
        elif path == "/api/sessions":
            self.json({"sessions": c.sessions()})
        else:
            match = SESSION_ROUTE.fullmatch(path)
            if not match:
                raise Problem(404, "Adresa neexistuje.")
            session_id, action = int(match[1]), match[2]
            db_uri = Path(c.db_path).resolve().as_uri() + "?mode=ro"
            with (self.server.session_access.reading(session_id),
                  closing(sqlite3.connect(db_uri, uri=True, timeout=3, isolation_level=None)) as db):
                db.row_factory = sqlite3.Row
                if not db.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone():
                    raise Problem(404, "Jízda nebyla nalezena.")
                if action == "points":
                    try:
                        limit = int(query.get("limit", ["1200"])[0])
                    except ValueError:
                        raise Problem(400, "Neplatný počet bodů.") from None
                    if not 2 <= limit <= 5000:
                        raise Problem(400, "Počet bodů musí být od 2 do 5000.")
                    self.json({"points": self.points(db, session_id, limit)})
                else:
                    self.export(db, session_id, action)

    def points(self, db, session_id, limit):
        # A session has one writer. Probe uniformly spaced IDs with its index, preserving endpoints.
        first, last = (db.execute(f"SELECT id FROM samples WHERE session_id=? ORDER BY id {order} LIMIT 1",
                                 (session_id,)).fetchone() for order in ("ASC", "DESC"))
        if not first:
            return []
        lo, hi = first[0], last[0]
        fields = ",".join(POINT_COLUMNS)
        if hi - lo + 1 <= limit:
            rows = db.execute(f"SELECT {fields} FROM samples WHERE session_id=? AND id<=? ORDER BY id", (session_id,hi))
        else:
            # Each quantile is an index lookup, avoiding full-table COUNT and modulo scans during a ride.
            rows = db.execute(f"""
                WITH RECURSIVE n(i) AS (VALUES(0) UNION ALL SELECT i+1 FROM n WHERE i+1 < :n)
                SELECT {fields} FROM samples WHERE id IN
                (SELECT (SELECT id FROM samples WHERE session_id=:s AND id >= :lo + i*(:hi-:lo)/(:n-1)
                         ORDER BY id LIMIT 1) FROM n) AND session_id=:s ORDER BY id
            """, {"s":session_id,"lo":lo,"hi":hi,"n":limit})
        return [dict(row) for row in rows]

    def export(self, db, session_id, action):
        binary = action == "raw.bin"
        table = "raw_chunks" if binary else "samples"
        fields = "id,data" if binary else ",".join(POINT_COLUMNS)
        last = db.execute(f"SELECT id FROM {table} WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
        last_id = last[0] if last else 0
        ext = "sbf" if binary else "csv"
        self.headers_for(200, "application/octet-stream" if binary else "text/csv; charset=utf-8",
            extra={"Content-Disposition": f'attachment; filename="formula-{session_id}.{ext}"', "X-Accel-Buffering": "no"})
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        if not binary:
            writer.writerow(POINT_COLUMNS)
            self.wfile.write(output.getvalue().encode())
        cursor = 0
        while cursor < last_id:
            # Close each SQLite read snapshot before writing to a possibly slow wireless client.
            rows = db.execute(f"SELECT {fields} FROM {table} WHERE session_id=? AND id>? AND id<=? ORDER BY id LIMIT ?",
                              (session_id, cursor, last_id, 1 if binary else 512)).fetchall()
            if not rows:
                break
            if binary:
                self.wfile.write(rows[0]["data"])
            else:
                output.seek(0)
                output.truncate()
                writer.writerows(rows)
                self.wfile.write(output.getvalue().encode())
            cursor = rows[-1]["id"]

    def static(self, route):
        name = unquote(route).lstrip("/") or "index.html"
        if name.startswith("static/"):
            name = name[len("static/"):]
        filename = (STATIC / name).resolve()
        if not filename.is_relative_to(STATIC) or not filename.is_file():
            raise Problem(404, "Soubor neexistuje.")
        mime = mimetypes.guess_type(str(filename))[0] or "application/octet-stream"
        if filename.suffix == ".js":
            mime = "application/javascript"
        with filename.open("rb") as f:
            self.headers_for(200, mime, os.fstat(f.fileno()).st_size)
            shutil.copyfileobj(f, self.wfile)


def main():
    data_dir = Path(os.getenv("FORMULA_DATA_DIR", "/var/lib/formula-manager")).resolve()
    access = Access(data_dir.with_name(data_dir.name + "-auth"))
    collector = Collector(data_dir)
    with ThreadingHTTPServer(("127.0.0.1", int(os.getenv("FORMULA_PORT", "8080"))), Handler) as server:
        server.access = access
        server.session_access = SessionAccess()
        server.collector = collector
        server.accuracy = Accuracy(collector.db_path.parent)
        server.transfers = Transfers(collector.db_path.parent)
        server.ppk = PPK(collector.db_path.parent)
        server.hardware = Hardware(collector.db_path.parent)
        def shutdown(signum, frame):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        collector.start()
        server.accuracy.start_worker(collector)
        try:
            server.serve_forever()
        finally:
            server.accuracy.close()
            server.hardware.close()
            collector.close()
            with access.lock:
                access.db.close()


if __name__ == "__main__":
    main()
