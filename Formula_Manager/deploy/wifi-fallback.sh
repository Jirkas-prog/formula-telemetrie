#!/bin/bash
# Configure the Pi's Wi-Fi without replacing its saved client networks.
set -eu
cd "$(dirname "$0")"
test "$(id -u)" = 0
command -v dnsmasq >/dev/null
command -v iw >/dev/null
test "$(hostname -s)" = formula-logger
uuid='1d1db196-d1db-4dc8-9719-7c0e5c861b69'
profile=/etc/NetworkManager/system-connections/formula69-fallback.nmconnection
priority=$(nmcli -g connection.autoconnect-priority connection show uuid "$uuid" 2>/dev/null || true)
if [ -t 0 ]; then printf 'Heslo hotspotu formula69: ' >&2; fi
IFS= read -rs password
if [ -t 0 ]; then printf '\n' >&2; fi
psk=$(printf '%s' "$password" | python3 -c "import hashlib,sys; p=sys.stdin.buffer.read(); assert 8<=len(p)<=63; print(hashlib.pbkdf2_hmac('sha1',p,b'formula69',4096,32).hex())")
unset password
umask 077
tmp=$(mktemp "${profile}.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
cat > "$tmp" <<EOF
[connection]
id=formula69-fallback
uuid=$uuid
type=wifi
interface-name=wlan0
autoconnect=true
autoconnect-priority=${priority:--999}
[wifi]
mode=ap
ssid=formula69
band=bg
channel=6
ap-isolation=1
[wifi-security]
key-mgmt=wpa-psk
proto=rsn;
pairwise=ccmp;
group=ccmp;
psk=$psk
[ipv4]
method=shared
address1=10.69.0.1/24
never-default=true
[ipv6]
method=disabled
EOF
mv -- "$tmp" "$profile"
unset psk
install -d /etc/NetworkManager/dnsmasq-shared.d
printf '%s\n' 'host-record=formula-logger.local,10.69.0.1' > /etc/NetworkManager/dnsmasq-shared.d/formula-logger.conf
chmod 0644 /etc/NetworkManager/dnsmasq-shared.d/formula-logger.conf
nmcli connection load "$profile"
systemctl enable --now avahi-daemon
install -m 0755 wifi-return.py /usr/local/sbin/formula-wifi-return
install -m 0644 formula-wifi-return.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now formula-wifi-return.timer
