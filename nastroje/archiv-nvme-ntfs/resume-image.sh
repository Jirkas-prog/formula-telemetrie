#!/bin/bash
set -euo pipefail
umask 077
work=/root/codex-rpi-nvme-20261102
here=$(cd -- "$(dirname -- "$0")" && pwd)
image="$work/formula-logger.img"
root="$work/root"
test -f "$image"
test -e "$work/resolv.conf.original" || test -L "$work/resolv.conf.original"
loop=$(losetup --find --show --partscan "$image")
cleanup() {
    set +e
    for target in "$root/sys" "$root/proc" "$root/dev/pts" "$root/dev" "$root/boot/firmware" "$root/srv/logs" "$root"; do
        mountpoint -q "$target" && umount "$target"
    done
    losetup -d "$loop"
}
trap cleanup EXIT
mount "${loop}p2" "$root"
mount "${loop}p1" "$root/boot/firmware"
data_uuid=$(blkid -s UUID -o value "${loop}p3")
python3 "$here/configure-image.py" "$root" "$work/settings.json" "$data_uuid"
chmod 755 "$root/etc/samba" "$root/etc/systemd/system/smbd.service.d"
chmod 644 "$root/etc/resolv.conf"
mount --bind /dev "$root/dev"
mount --bind /dev/pts "$root/dev/pts"
mount -t proc proc "$root/proc"
mount -t sysfs -o ro sysfs "$root/sys"
printf 'MODULES=most\n' > "$root/etc/initramfs-tools/conf.d/formula-storage"
chmod 644 "$root/etc/initramfs-tools/conf.d/formula-storage"
chroot "$root" /usr/bin/getent ahostsv4 deb.debian.org
source "$here/finish-image.sh"
