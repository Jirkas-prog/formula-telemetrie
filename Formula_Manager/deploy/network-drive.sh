#!/bin/bash
# Run locally on the logger, after deploying the manager.
set -euo pipefail
cd "$(dirname "$0")"
[[ $(id -u) == 0 ]] || { echo 'Spusť pomocí sudo.' >&2; exit 1; }
. /etc/os-release
case "${VERSION_CODENAME:-}" in trixie|bookworm) ;; *) echo 'Určeno pro Raspberry Pi OS Trixie nebo Bookworm.' >&2; exit 1;; esac
id formula69 >/dev/null
id formula-manager >/dev/null
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
apt-get update
apt-get install -y ca-certificates curl samba avahi-daemon acl
if ! command -v tailscale >/dev/null; then
    base="https://pkgs.tailscale.com/stable/debian/$VERSION_CODENAME"
    curl -fsSL --retry 3 "$base.noarmor.gpg" -o "$work/key"
    curl -fsSL --retry 3 "$base.tailscale-keyring.list" -o "$work/list"
    install -m 0644 "$work/key" /usr/share/keyrings/tailscale-archive-keyring.gpg
    install -m 0644 "$work/list" /etc/apt/sources.list.d/tailscale.list
    apt-get update
    apt-get install -y tailscale
fi
install -d -m 2770 -o formula-manager -g formula-manager /var/lib/formula-manager/imports
setfacl -m u:formula69:--x /var/lib/formula-manager
cfg=/etc/samba/smb.conf
fragment=/etc/samba/formula-ppk.conf
cp -p "$cfg" "$work/smb.conf"
if ! grep -Fqx "    include = $fragment" "$work/smb.conf"; then
    if testparm -s "$cfg" 2>/dev/null | grep -Eiq '^\[PPK\]'; then
        echo 'Sdílení PPK už existuje s jinou konfigurací.' >&2
        exit 1
    fi
    printf '\n[global]\n    include = %s\n' "$fragment" >> "$work/smb.conf"
fi
# Validate the new share before changing the active configuration.
cp smb-ppk.conf "$work/share.conf"
sed "s|^    include = $fragment$|    include = $work/share.conf|" "$work/smb.conf" > "$work/test.conf"
testparm -s "$work/test.conf" >/dev/null
[[ $(testparm -s --section-name=PPK --parameter-name=path "$work/test.conf" 2>/dev/null) == /var/lib/formula-manager/imports ]]
if ! cmp -s "$cfg" "$work/smb.conf"; then
    cp -p --backup=numbered "$cfg" "$cfg.before-formula"
fi
install -m 0644 smb-ppk.conf "$fragment"
install -m 0644 "$work/smb.conf" "$cfg"
if ! pdbedit -L -u formula69 >/dev/null 2>&1; then
    python3 samba-password.py
elif [[ ! -s /etc/formula-manager/samba-password ]]; then
    echo 'Pro zobrazení hesla ve webu spusť sudo python3 deploy/samba-password.py.'
fi
systemctl enable --now avahi-daemon smbd tailscaled
smbcontrol smbd reload-config
if ! tailscale status --json | python3 -c 'import json,sys; sys.exit(json.load(sys.stdin).get("BackendState") != "Running")'; then
    tailscale up
fi
dns=$(tailscale status --json | python3 -c 'import json,sys; print((json.load(sys.stdin)["Self"].get("DNSName") or "").rstrip("."))')
if [[ -n "$dns" ]]; then
    printf 'Sdílení přes Tailscale: \\\\%s\\PPK\n' "$dns"
else
    echo 'V administraci Tailscale ověř MagicDNS a spusť tailscale status.'
fi
printf 'Místní sdílení: \\\\%s.local\\PPK\n' "$(hostname -s)"

