#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys

root, image, ntfs_uuid = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
table = json.loads(subprocess.check_output(['sfdisk', '--json', str(image)]))['partitiontable']
parts = table['partitions']
assert len(parts) == 3 and table['label'] == 'dos'
assert [(p['start'], p['size'], p['type']) for p in parts] == [
    (16384, 1048576, 'c'), (1064960, 134217728, '83'), (135282688, 2097152, '7')]
assert image.stat().st_size == (parts[-1]['start'] + parts[-1]['size']) * 512
cmd = (root/'boot/firmware/cmdline.txt').read_text().split()
assert 'resize' not in cmd and 'root=PARTUUID=6f726d31-02' in cmd
assert ntfs_uuid in (root/'etc/fstab').read_text()
assert (root/'etc/NetworkManager/system-connections/LAB-WIFI.nmconnection').stat().st_mode & 0o777 == 0o600
assert 'logger:x:1000:1000:' in (root/'etc/passwd').read_text()
assert (root/'usr/lib/modules/6.18.50+rpt-rpi-2712/kernel/fs/ntfs3/ntfs3.ko.xz').is_file()
assert (root/'usr/sbin/smbd').is_file()
assert not (root/'etc/formula-logger/smbpasswd.seed').exists()
assert (root/'etc/systemd/system/multi-user.target.wants/ssh.service').is_symlink()
assert (root/'etc/systemd/system/multi-user.target.wants/smbd.service').is_symlink()
assert (root/'etc/systemd/system/rpi-resize.service').readlink() == Path('/dev/null')
assert not (root/'etc/systemd/system/multi-user.target.wants/userconfig.service').is_symlink()
assert not (root/'etc/ssh/sshd_config.d/rename_user.conf').exists()
assert (root/'etc/systemd/system/ssh.service.requires/formula-ssh-host-keys.service').is_symlink()
result = {
    'verified_on': '2026-11-02', 'image_partitions': parts,
    'root_gib': 64, 'ntfs_seed_gib': 1,
    'ntfs_expansion': 'Windows Resize-Partition after flashing, before first boot',
    'wifi_ssid': 'LAB-WIFI', 'username': 'logger', 'hostname': 'formula-logger',
    'samba_share': r'\\formula-logger\logy', 'passwords_printed': False,
    'arm64_binaries_executed_under_qemu': True,
    'physical_pi_boot_tested': False, 'physical_disk_written': False,
    'gnss_imu_logger_installed': False
}
(image.parent/'offline-verification.json').write_text(json.dumps(result, indent=2)+'\n')
print('Partition geometry, system configuration, installed Samba and NTFS module verified.')
