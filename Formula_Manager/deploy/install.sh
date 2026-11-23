#!/bin/bash
set -eu
cd "$(dirname "$0")/.."
if systemctl is-active --quiet formula-eduroam-test.service; then
    echo 'Probíhá ověření eduroamu. Aktualizaci spusť po jeho dokončení.' >&2
    exit 1
fi
if systemctl is-active --quiet formula-manager && [ -f /var/lib/formula-manager/logger.sqlite3 ]; then
    python3 - <<'PY'
import sqlite3
import json
from pathlib import Path
db = sqlite3.connect("file:/var/lib/formula-manager/logger.sqlite3?mode=ro", uri=True)
if db.execute("SELECT EXISTS(SELECT 1 FROM sessions WHERE state='recording')").fetchone()[0]:
    raise SystemExit("Probíhá záznam. Aktualizaci spusť po ukončení jízdy.")
for name,sql in (("accuracy","SELECT 1 FROM runs WHERE state='running'"),
                 ("transfers","SELECT value FROM last_job WHERE id=1")):
    path=Path("/var/lib/formula-manager")/(name+".sqlite3")
    if path.exists():
        row=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True).execute(sql).fetchone()
        if row and (name=="accuracy" or json.loads(row[0]).get("state")=="running"):
            raise SystemExit("Probíhá test přesnosti nebo export. Aktualizaci spusť po jeho dokončení.")
ppk = Path("/var/lib/formula-manager/ppk.sqlite3")
if ppk.exists() and sqlite3.connect(ppk.as_uri()+"?mode=ro",uri=True).execute("SELECT 1 FROM jobs WHERE state='running' LIMIT 1").fetchone():
    raise SystemExit("Probíhá import nebo výpočet PPK. Počkej na dokončení.")
PY
fi
install -d /etc/formula-manager
if [ ! -s /etc/formula-manager/auth.env ]; then
    python3 - <<'PY'
from getpass import getpass
from pathlib import Path
import hashlib, os, secrets
pwd = getpass("Nové webové heslo účtu formula69: ")
if not pwd or getpass("Zopakuj heslo: ") != pwd:
    raise SystemExit("Hesla se neshodují nebo jsou prázdná.")
salt = secrets.token_bytes(16)
digest = hashlib.scrypt(pwd.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
os.umask(0o077)
with Path("/etc/formula-manager/auth.env").open("x", encoding="ascii") as out:
    out.write("FORMULA_USER=formula69\nFORMULA_PASSWORD_HASH=" + salt.hex() + ":" + digest.hex() + "\n")
PY
fi
apt-get install -y nginx python3-serial python3-venv python3-dbus udisks2 ntfs-3g rtklib
getent passwd formula-manager >/dev/null || useradd --system --user-group --home-dir /var/lib/formula-manager --shell /usr/sbin/nologin formula-manager
install -d -m 0750 -o formula-manager -g formula-manager /var/lib/formula-manager
install -d /opt/formula-manager /etc/formula-manager
if [ ! -x /opt/formula-manager/venv/bin/python ]; then
    python3 -m venv --system-site-packages /opt/formula-manager/venv
fi
/opt/formula-manager/venv/bin/python -m pip --disable-pip-version-check install --only-binary=:all: \
    'pysbf2==1.0.7' 'pynmeagps==1.1.9' 'pyrtcm==1.2.1'
umask 077
if [ ! -s /etc/formula-manager/web.key ]; then
    addr=$(ip -4 -o addr show wlan0 | awk '{print $4}' | cut -d/ -f1 | head -1)
    test -n "$addr"
    openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:P-256 -days 730 -sha256 \
        -subj /CN=formula-logger.local -addext "subjectAltName=DNS:formula-logger.local,DNS:formula-logger,IP:$addr" \
        -addext 'basicConstraints=critical,CA:FALSE' -addext 'extendedKeyUsage=serverAuth' \
        -keyout /etc/formula-manager/web.key -out /etc/formula-manager/web.crt
fi
if [ ! -s /etc/formula-manager/receiver.crt ]; then
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    timeout 8 openssl s_client -connect 192.168.3.1:443 -showcerts </dev/null 2>/dev/null | openssl x509 -out "$tmp"
    actual=$(openssl x509 -in "$tmp" -noout -sha256 -fingerprint | cut -d= -f2 | tr -d :)
    expected=$(printf '%s' "${RECEIVER_SHA256:?Nastav předem ověřený otisk certifikátu přijímače.}" | tr -d : | tr '[:lower:]' '[:upper:]')
    [[ $expected =~ ^[0-9A-F]{64}$ && "$actual" = "$expected" ]] || { echo 'Otisk přijímače nesouhlasí.' >&2; exit 1; }
    install -m 0644 "$tmp" /etc/formula-manager/receiver.crt
fi
chmod 0644 /etc/formula-manager/web.crt
install -m 0644 server.py collector.py corrections.py diagnostics.py overview.py accuracy.py transfers.py mediafiles.py hardware.py ppk.py /opt/formula-manager/
install -d /media /etc/polkit-1/rules.d
install -m 0644 deploy/62-formula-usb.rules /etc/polkit-1/rules.d/
if [ -f README.md ]; then install -m 0644 README.md /opt/formula-manager/README.md; fi
if [ -f PPK.md ]; then install -m 0644 PPK.md /opt/formula-manager/PPK.md; fi
cp -R static /opt/formula-manager/
chmod -R a+rX /opt/formula-manager/static
install -m 0644 deploy/formula-manager.service /etc/systemd/system/formula-manager.service
receiver_name=$(openssl x509 -in /etc/formula-manager/receiver.crt -noout -subject -nameopt multiline | sed -n 's/^[[:space:]]*commonName[[:space:]]*=[[:space:]]*//p')
[[ $receiver_name =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || { echo 'Chybí DNS jméno v certifikátu přijímače.' >&2; exit 1; }
sed "s/__RECEIVER_TLS_NAME__/$receiver_name/g" deploy/nginx.conf > /etc/nginx/sites-available/formula-manager
chmod 0644 /etc/nginx/sites-available/formula-manager
ln -sfn /etc/nginx/sites-available/formula-manager /etc/nginx/sites-enabled/formula-manager
if [ "$(readlink -f /etc/nginx/sites-enabled/default)" = /etc/nginx/sites-available/default ] && [ -L /etc/nginx/sites-enabled/default ]; then
    unlink /etc/nginx/sites-enabled/default
fi
nginx -t
install -d -m 0755 /usr/local/libexec
install -m 0755 deploy/wifi-profiles.py /usr/local/libexec/formula-wifi-profiles.py
install -m 0644 deploy/tul-eduroam-ca.pem /etc/formula-manager/tul-eduroam-ca.pem
install -m 0644 deploy/formula-wifi-profiles.{socket,service} /etc/systemd/system/
install -m 0644 deploy/formula-eduroam-test.service /etc/systemd/system/
install -m 0755 deploy/wifi-return.py /usr/local/sbin/formula-wifi-return
/usr/bin/python3 -I /usr/local/libexec/formula-wifi-profiles.py --initialize
systemctl daemon-reload
systemctl enable --now formula-wifi-profiles.socket
systemctl try-restart formula-wifi-profiles.service
systemctl enable nginx formula-manager
systemctl restart formula-manager
systemctl reload nginx
systemctl is-active formula-manager nginx

