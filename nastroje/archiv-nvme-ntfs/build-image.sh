#!/bin/bash
# Only regular image files under the fixed build directory are modified.
set -euo pipefail
umask 077
work=/root/codex-rpi-nvme-20261102
here=$(cd -- "$(dirname -- "$0")" && pwd)
image="$work/formula-logger.img"
root="$work/root"
if [[ -e "$image" ]]; then
    echo 'Build image already exists; refusing to overwrite it.' >&2
    exit 1
fi
test -f "$work/original.img"
test -f "$work/settings.json"
echo 'Creating image with 512 MiB boot, 64 GiB root, and a 1 GiB NTFS seed partition.'
cp --sparse=always "$work/original.img" "$image"
truncate -s 70338478080 "$image"
sfdisk --no-reread --wipe never "$image" <<'TABLE'
label: dos
label-id: 0x6f726d31
unit: sectors

start=16384, size=1048576, type=c
start=1064960, size=134217728, type=83
start=135282688, size=2097152, type=7
TABLE
loop=$(losetup --find --show --partscan "$image")
mkdir -p "$root"
cleanup() {
    set +e
    for target in "$root/sys" "$root/proc" "$root/dev/pts" "$root/dev" "$root/boot/firmware" "$root/srv/logs" "$root"; do
        mountpoint -q "$target" && umount "$target"
    done
    losetup -d "$loop"
}
trap cleanup EXIT
# e2fsck exit status 1 means errors were corrected successfully.
e2fsck -fy "${loop}p2" || test "$?" -eq 1
resize2fs "${loop}p2"
e2fsck -fn "${loop}p2"
mkntfs -F -Q -L FORMULA_LOGS "${loop}p3"
mount "${loop}p2" "$root"
mount "${loop}p1" "$root/boot/firmware"
mkdir -p "$root/srv/logs"
chmod 700 "$root/srv/logs"
# ntfs-3g is available in the build environment; target Pi uses its ntfs3 module.
mount -t ntfs-3g "${loop}p3" "$root/srv/logs"
mkdir -p "$root/srv/logs/sessions" "$root/srv/logs/exports"
printf 'Data volume for formula-logger. GNSS/IMU logger is not installed yet.\n' > "$root/srv/logs/README.txt"
umount "$root/srv/logs"
data_uuid=$(blkid -s UUID -o value "${loop}p3")
echo "$data_uuid" > "$work/data-uuid.txt"
python3 "$here/configure-image.py" "$root" "$work/settings.json" "$data_uuid"

# Use the registered QEMU ARM64 interpreter. No target services run on the PC.
printf '#!/bin/sh\nexit 101\n' > "$root/usr/sbin/policy-rc.d"
chmod 755 "$root/usr/sbin/policy-rc.d"
cp -a "$root/etc/resolv.conf" "$work/resolv.conf.original"
rm "$root/etc/resolv.conf"
cp /etc/resolv.conf "$root/etc/resolv.conf"
chmod 644 "$root/etc/resolv.conf"
mount --bind /dev "$root/dev"
mount --bind /dev/pts "$root/dev/pts"
mount -t proc proc "$root/proc"
mount -t sysfs -o ro sysfs "$root/sys"
printf 'MODULES=most\n' > "$root/etc/initramfs-tools/conf.d/formula-storage"
chmod 644 "$root/etc/initramfs-tools/conf.d/formula-storage"
source "$here/finish-image.sh"
