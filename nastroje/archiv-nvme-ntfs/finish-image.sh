#!/bin/bash
# Sourced by build-image.sh or resume-image.sh with a mounted task-owned image.
echo 'Installing Samba and storage tools inside the ARM64 image.'
chroot "$root" /usr/bin/env DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=2 -o APT::Update::Error-Mode=any update
chroot "$root" /usr/bin/env DEBIAN_FRONTEND=noninteractive apt-get -o Dpkg::Options::=--force-confold install -y --no-install-recommends samba smbclient ntfs-3g avahi-daemon
chroot "$root" /usr/bin/apt-get clean
chroot "$root" /usr/sbin/usermod -l logger -d /home/logger -m -s /bin/bash pi
chroot "$root" /usr/sbin/groupmod -n logger pi
chroot "$root" /usr/sbin/usermod -aG sudo,dialout logger
chroot "$root" /usr/sbin/chpasswd -e < "$work/user-password-hash.txt"
chroot "$root" /usr/bin/cancel-rename logger
systemctl --root="$root" disable userconfig.service
chroot "$root" /usr/bin/pdbedit -i smbpasswd:/etc/formula-logger/smbpasswd.seed
rm "$root/etc/formula-logger/smbpasswd.seed"
chroot "$root" /usr/bin/testparm -s >/dev/null
chroot "$root" /usr/bin/pdbedit -L
systemctl --root="$root" enable ssh smbd avahi-daemon formula-wifi-unblock.service formula-ssh-host-keys.service
systemctl --root="$root" disable nmbd 2>/dev/null || true
systemctl --root="$root" mask rpi-resize.service
rm "$root/usr/sbin/policy-rc.d"
rm "$root/etc/resolv.conf"
cp -a "$work/resolv.conf.original" "$root/etc/resolv.conf"
# Generate unique host keys on the real Pi on its first start.
find "$root/etc/ssh" -maxdepth 1 -type f -name 'ssh_host_*' -delete
truncate -s 0 "$root/etc/machine-id"
rm -f "$root/var/lib/dbus/machine-id"
ln -s /etc/machine-id "$root/var/lib/dbus/machine-id"
sync
echo 'Image configured; running offline validation.'
python3 "$here/verify-image.py" "$root" "$image" "$data_uuid"
cleanup
trap - EXIT
losetup --find --show --partscan --read-only "$image" > "$work/validation-loop.txt"
check_loop=$(cat "$work/validation-loop.txt")
trap 'losetup -d "$check_loop"' EXIT
e2fsck -fn "${check_loop}p2"
ntfsresize --info "${check_loop}p3"
losetup -d "$check_loop"
trap - EXIT
echo 'Compressing the completed image.'
zstd -T4 -3 "$image" -o "$here/formula-logger-rpi5-64GiB-NTFS.img.zst"
zstd -t "$here/formula-logger-rpi5-64GiB-NTFS.img.zst"
sha256sum "$here/formula-logger-rpi5-64GiB-NTFS.img.zst" > "$here/IMAGE_SHA256.txt"
cp "$work/data-uuid.txt" "$here/DATA_UUID.txt"
cp "$work/offline-verification.json" "$here/OFFLINE_VERIFICATION.json"
echo 'BUILD COMPLETED. No physical disk has been written.'
