#!/bin/bash
set -euo pipefail
work=/root/codex-rpi-nvme-20261102
here=$(cd -- "$(dirname -- "$0")" && pwd)
root="$work/final-readonly"
mkdir -p "$root"
loop=$(losetup --find --show --partscan --read-only "$work/formula-logger.img")
cleanup() {
    set +e
    mountpoint -q "$root/var/log/samba" && umount "$root/var/log/samba"
    mountpoint -q "$root/var/lib/samba" && umount "$root/var/lib/samba"
    mountpoint -q "$root/run" && umount "$root/run"
    mountpoint -q "$root/proc" && umount "$root/proc"
    mountpoint -q "$root" && umount "$root"
    losetup -d "$loop"
}
trap cleanup EXIT
mount -o ro,noload "${loop}p2" "$root"
mount -t proc proc "$root/proc"
# Samba opens its TDB database read-write for locks even for inspection.
# Give the diagnostic a private copy; the prepared image stays read-only.
mkdir -p "$work/samba-validation"
cp -a "$root/var/lib/samba/." "$work/samba-validation/"
mount --bind "$work/samba-validation" "$root/var/lib/samba"
mount -t tmpfs tmpfs "$root/run"
mount -t tmpfs tmpfs "$root/var/log/samba"
python3 - "$root" "$work/settings.json" "$here" <<'PY'
from pathlib import Path
import crypt, hashlib, json, subprocess, sys
root, secrets, output = map(Path,sys.argv[1:])
settings=json.loads(secrets.read_text())
shadow=[l for l in (root/'etc/shadow').read_text().splitlines() if l.startswith('logger:')][0].split(':')[1]
assert crypt.crypt(settings['user_password'],shadow)==shadow
profile=root/'etc/NetworkManager/system-connections/LAB-WIFI.nmconnection'
expected=hashlib.pbkdf2_hmac('sha1',settings['wifi_password'].encode(),b'LAB-WIFI',4096,32).hex()
assert 'psk='+expected in profile.read_text()
nm=subprocess.run(['chroot',str(root),'/usr/bin/nmcli','--offline','connection','modify','connection.autoconnect','yes'],input=profile.read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
assert nm.returncode==0, 'NetworkManager rejected the prepared profile'
nt_hash=subprocess.check_output(['openssl','dgst','-provider','legacy','-md4','-binary'],input=settings['user_password'].encode('utf-16-le')).hex().upper()
pdb=subprocess.run(['chroot',str(root),'/usr/bin/pdbedit','-L','-w'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
assert pdb.returncode==0, 'Cannot inspect Samba account database'
line=next(l for l in pdb.stdout.decode().splitlines() if l.startswith('logger:'))
assert line.split(':')[3].upper()==nt_hash
assert 'D' not in line.split(':')[4], 'Samba account is disabled'
assert not (root/'etc/systemd/system/multi-user.target.wants/userconfig.service').is_symlink()
assert not (root/'etc/ssh/sshd_config.d/rename_user.conf').exists()
guard=subprocess.run(['chroot',str(root),'/usr/local/sbin/check-log-volume'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
assert guard.returncode!=0, 'Storage guard incorrectly accepted an unmounted data volume'
report=json.loads((output/'OFFLINE_VERIFICATION.json').read_text())
report.update({'linux_password_verified':True,'samba_password_hash_verified':True,'networkmanager_profile_parsed':True,'wifi_psk_verified':True,'unmounted_data_guard_rejects':True,'user_setup_dialog_disabled':True})
(output/'OFFLINE_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: Linux login hash, Samba login hash, NetworkManager profile, Wi-Fi PSK, and missing-volume guard.')
PY
