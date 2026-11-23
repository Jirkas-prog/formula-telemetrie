#!/bin/bash
set -euo pipefail
work=/root/codex-rpi-nvme-20261102
src='/mnt/d/01_Skola/01_TUL/BAKALÁŘKA/Doplňkové_materiály/Raspberry_Pi_5_instalace/2026-10-06-raspios-trixie-arm64-lite.img.xz'
mkdir -p "$work"
if [[ ! -f "$work/original.img" ]]; then
    xz -dc "$src" > "$work/original.img.partial"
    mv "$work/original.img.partial" "$work/original.img"
fi
sfdisk --json "$work/original.img"
loop=$(losetup --find --show --partscan --read-only "$work/original.img")
mkdir -p "$work/inspect-root" "$work/inspect-boot"
cleanup() {
    mountpoint -q "$work/inspect-root" && umount "$work/inspect-root" || true
    mountpoint -q "$work/inspect-boot" && umount "$work/inspect-boot" || true
    losetup -d "$loop"
}
trap cleanup EXIT
mount -o ro,noload "${loop}p2" "$work/inspect-root"
mount -o ro "${loop}p1" "$work/inspect-boot"
cat "$work/inspect-boot/cmdline.txt"
cat "$work/inspect-root/etc/os-release"
cat "$work/inspect-root/etc/fstab"
ls "$work/inspect-root/usr/lib/raspberrypi-sys-mods/"
find "$work/inspect-root/usr/lib/modules" -iname '*ntfs*' -print
grep -E '^(logger|pi):' "$work/inspect-root/etc/passwd" || true
ls /usr/bin/qemu-aarch64-static /usr/bin/qemu-aarch64 /proc/sys/fs/binfmt_misc/qemu-aarch64 2>/dev/null || true
cp "$work/inspect-root/usr/lib/raspberrypi-sys-mods/firstboot" "$work/firstboot-in-image.txt" 2>/dev/null || true
find "$work/inspect-root/usr/lib" -maxdepth 3 -iname '*firstboot*' -o -iname '*resize*'
cat "$work/inspect-root/usr/lib/systemd/system/rpi-resize.service"
find "$work/inspect-root/usr/lib/systemd/system" -maxdepth 1 -iname '*userconfig*' -print
cat "$work/inspect-root/etc/sudoers.d/010_pi-nopasswd" 2>/dev/null || true
chroot "$work/inspect-root" /usr/bin/true
echo 'ARM64 chroot executable works.'
losetup -j "$work/original.img"
