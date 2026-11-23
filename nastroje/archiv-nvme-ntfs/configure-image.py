#!/usr/bin/env python3
"""Configure the mounted, task-owned image. Never prints credentials."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

root = Path(sys.argv[1]).resolve()
assert root == Path('/root/codex-rpi-nvme-20261102/root')
settings_path = Path(sys.argv[2])
settings = json.loads(settings_path.read_text())
data_uuid = sys.argv[3]
assert len(data_uuid) == 16 and all(c in '0123456789ABCDEFabcdef' for c in data_uuid)

def put(name, text, mode=0o644):
    path = root / name.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(mode)

cmd = (root / 'boot/firmware/cmdline.txt').read_text().split()
cmd = [v.replace('27b94958-02', '6f726d31-02') for v in cmd if v != 'resize' and not v.startswith('cfg80211.ieee80211_regdom=')]
cmd.append('cfg80211.ieee80211_regdom=CZ')
put('/boot/firmware/cmdline.txt', ' '.join(cmd) + '\n')
put('/etc/hostname', 'formula-logger\n')
hosts = (root / 'etc/hosts').read_text()
hosts = '\n'.join(line for line in hosts.splitlines() if not line.startswith('127.0.1.1'))
put('/etc/hosts', hosts + '\n127.0.1.1\tformula-logger\n')
put('/etc/timezone', 'Europe/Prague\n')
localtime = root / 'etc/localtime'
localtime.unlink(missing_ok=True)
localtime.symlink_to('/usr/share/zoneinfo/Europe/Prague')
put('/etc/fstab', f'''proc /proc proc defaults 0 0
PARTUUID=6f726d31-01 /boot/firmware vfat defaults 0 2
PARTUUID=6f726d31-02 / ext4 defaults,noatime 0 1
UUID={data_uuid} /srv/logs ntfs3 defaults,nofail,noatime,nodev,nosuid,noexec,windows_names,uid=1000,gid=1000,dmask=0027,fmask=0137,x-systemd.device-timeout=10s 0 0
''')
psk = hashlib.pbkdf2_hmac('sha1', settings['wifi_password'].encode(), settings['wifi_ssid'].encode(), 4096, 32).hex()
put('/etc/NetworkManager/system-connections/LAB-WIFI.nmconnection', f'''[connection]
id=LAB-WIFI
uuid={uuid.uuid4()}
type=wifi
autoconnect=true
autoconnect-priority=100

[wifi]
mode=infrastructure
ssid={settings['wifi_ssid']}
powersave=2

[wifi-security]
key-mgmt=wpa-psk
psk={psk}

[ipv4]
method=auto

[ipv6]
method=auto
addr-gen-mode=stable-privacy
''', 0o600)
put('/etc/modprobe.d/formula-wifi.conf', 'options cfg80211 ieee80211_regdom=CZ\n')
put('/etc/systemd/system/formula-wifi-unblock.service', '''[Unit]
Description=Unblock Wi-Fi for formula-logger
Before=NetworkManager.service
After=systemd-rfkill.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/rfkill unblock wifi
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
''')
put('/etc/ssh/sshd_config.d/10-formula-logger.conf', 'PasswordAuthentication yes\nPermitRootLogin no\n')
put('/etc/systemd/system/formula-ssh-host-keys.service', '''[Unit]
Description=Generate missing SSH host keys for this Raspberry Pi
Before=ssh.service

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
RemainAfterExit=yes

[Install]
RequiredBy=ssh.service
''')
put('/etc/sudoers.d/010_logger', 'logger ALL=(ALL:ALL) ALL\n', 0o440)
put('/etc/samba/smb.conf', '''[global]
   workgroup = WORKGROUP
   server string = Formula GNSS IMU logger
   server role = standalone server
   security = user
   map to guest = never
   server min protocol = SMB2
   load printers = no
   disable spoolss = yes
   log file = /var/log/samba/log.%m
   max log size = 1000

[logy]
   path = /srv/logs
   comment = GNSS and IMU data on NTFS
   browseable = yes
   read only = no
   guest ok = no
   valid users = logger
   force user = logger
   force group = logger
   create mask = 0640
   directory mask = 0750
   follow symlinks = no
''')
put('/usr/local/sbin/check-log-volume', f'''#!/bin/sh
set -eu
test "$(findmnt -n -o TARGET --target /srv/logs)" = /srv/logs
test "$(findmnt -n -o UUID --target /srv/logs)" = {data_uuid}
test "$(findmnt -n -o FSTYPE --target /srv/logs)" = ntfs3
findmnt -n -o OPTIONS --target /srv/logs | tr ',' '\\n' | grep -qx rw
''', 0o755)
put('/etc/systemd/system/smbd.service.d/10-log-volume.conf', '''[Unit]
Requires=srv-logs.mount
After=srv-logs.mount
BindsTo=srv-logs.mount

[Service]
ExecStartPre=/usr/local/sbin/check-log-volume
''')
(root / 'etc/samba').chmod(0o755)
(root / 'etc/systemd/system/smbd.service.d').chmod(0o755)
put('/etc/formula-logger/storage.json', json.dumps({
    'system_partition_gib': 64, 'data_uuid': data_uuid,
    'data_mount': '/srv/logs', 'sessions': '/srv/logs/sessions',
    'share': r'\\formula-logger\logy', 'logger_installed': False,
    'network': 'LAB-WIFI', 'created': '2026-11-02'
}, indent=2) + '\n')
# Store only password hashes in the guest image. No clear-text credentials in logs.
password = settings['user_password']
shadow_hash = subprocess.check_output(['openssl', 'passwd', '-6', '-stdin'], input=(password+'\n').encode()).decode().strip()
hash_file = settings_path.parent / 'user-password-hash.txt'
hash_file.write_text('logger:' + shadow_hash + '\n')
hash_file.chmod(0o600)
nt_hash = subprocess.check_output(['openssl', 'dgst', '-provider', 'legacy', '-md4', '-binary'], input=password.encode('utf-16-le')).hex().upper()
put('/etc/formula-logger/smbpasswd.seed', f'logger:1000:{"X"*32}:{nt_hash}:[U          ]:LCT-{int(time.time()):08X}:\n', 0o600)
print('Network, storage, SSH and Samba configurations prepared; credentials omitted.')
