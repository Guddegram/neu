#!/usr/bin/env bash
# neuvpn – WireGuard-VPN-Server installieren (Debian, Ubuntu, Raspberry Pi OS).
#
# Ausführen AUF DEM SERVER IN RUMÄNIEN (z. B. Raspberry Pi bei Familie/Freunden):
#   git clone https://github.com/guddegram/neu.git && cd neu
#   sudo ./scripts/install-server.sh
#
# Optionen:
#   --endpoint HOST        Öffentliche IP/DNS-Name (Standard: automatisch ermitteln)
#   --port PORT            UDP-Port (Standard: 51820)
#   --client NAME          Name des ersten Geräts (Standard: handy)
#   --duckdns SUB TOKEN    Kostenloses DynDNS SUB.duckdns.org einrichten (für wechselnde Heim-IPs)
#   --ipv6                 IPv6 im Tunnel aktivieren (nur wenn der Server IPv6 hat)
#   --country CC           Erwarteter Server-Standort (Standard: RO)
#   --yes                  Keine Rückfragen
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENDPOINT=""
PORT=51820
CLIENT="handy"
DUCK_SUB=""
DUCK_TOKEN=""
IPV6=""
COUNTRY="RO"
YES=""

while [ $# -gt 0 ]; do
  case "$1" in
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --client) CLIENT="$2"; shift 2 ;;
    --duckdns) DUCK_SUB="$2"; DUCK_TOKEN="$3"; shift 3 ;;
    --ipv6) IPV6="--ipv6"; shift ;;
    --country) COUNTRY="$2"; shift 2 ;;
    --yes|-y) YES=1; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Unbekannte Option: $1" >&2; exit 1 ;;
  esac
done

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m ✔\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m ✘\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "Bitte mit sudo ausführen."
command -v apt-get >/dev/null || die "Nur Debian/Ubuntu/Raspberry Pi OS werden unterstützt."

info "Pakete installieren (WireGuard, iptables, qrencode)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq wireguard-tools iptables iproute2 qrencode python3 curl ca-certificates >/dev/null
if ! ip link add neuvpn-probe type wireguard 2>/dev/null; then
  warn "Kein WireGuard-Kernelmodul – installiere Paket 'wireguard' (Kernel-Modul/Userspace)"
  apt-get install -y -qq wireguard >/dev/null || true
  modprobe wireguard 2>/dev/null || apt-get install -y -qq wireguard-go >/dev/null 2>&1 \
    || warn "Bitte Kernel aktualisieren (WireGuard ist ab Linux 5.6 eingebaut) und neu starten."
else
  ip link del neuvpn-probe
fi
ok "Pakete installiert"

info "neuvpn nach /opt/neuvpn installieren"
rm -rf /opt/neuvpn
mkdir -p /opt/neuvpn
cp -r "$REPO/neuvpn" /opt/neuvpn/
cat > /usr/local/bin/neuvpn <<'EOF'
#!/bin/sh
PYTHONPATH=/opt/neuvpn exec python3 -m neuvpn "$@"
EOF
chmod 755 /usr/local/bin/neuvpn
ok "Befehl 'neuvpn' verfügbar"

info "IP-Weiterleitung dauerhaft aktivieren"
cat > /etc/sysctl.d/99-neuvpn.conf <<'EOF'
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
sysctl -q -p /etc/sysctl.d/99-neuvpn.conf 2>/dev/null || sysctl -q -w net.ipv4.ip_forward=1
ok "Weiterleitung aktiv"

if [ -n "$DUCK_SUB" ]; then
  info "DuckDNS einrichten: $DUCK_SUB.duckdns.org"
  install -d -m 700 /etc/neuvpn
  umask 077
  printf 'DUCKDNS_DOMAIN=%s\nDUCKDNS_TOKEN=%s\n' "$DUCK_SUB" "$DUCK_TOKEN" > /etc/neuvpn/duckdns.env
  install -m 755 "$REPO/scripts/duckdns-update.sh" /usr/local/bin/neuvpn-duckdns
  cat > /etc/systemd/system/neuvpn-duckdns.service <<'EOF'
[Unit]
Description=neuvpn DuckDNS-Update
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/neuvpn/duckdns.env
ExecStart=/usr/local/bin/neuvpn-duckdns
EOF
  cat > /etc/systemd/system/neuvpn-duckdns.timer <<'EOF'
[Unit]
Description=neuvpn DuckDNS alle 5 Minuten aktualisieren

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now neuvpn-duckdns.timer >/dev/null
  systemctl start neuvpn-duckdns.service || warn "DuckDNS-Update fehlgeschlagen – Token prüfen."
  [ -z "$ENDPOINT" ] && ENDPOINT="$DUCK_SUB.duckdns.org"
  ok "DynDNS aktiv – Endpoint $ENDPOINT"
fi

if [ -z "$ENDPOINT" ]; then
  ENDPOINT="$(curl -4 -fsS --max-time 10 https://api.ipify.org || curl -4 -fsS --max-time 10 https://ifconfig.me || true)"
  [ -n "$ENDPOINT" ] || die "Öffentliche IP nicht ermittelbar. Bitte --endpoint angeben."
  warn "Endpoint ist die aktuelle IP $ENDPOINT. Wechselt sie (typisch bei Heim-Internet), --duckdns nutzen."
fi

info "Server-Standort prüfen (muss $COUNTRY sein)"
rc=0
neuvpn check --expect "$COUNTRY" || rc=$?
if [ "$rc" = 1 ]; then
  warn "Dieser Server steht NICHT in $COUNTRY – deine VPN-IP wird das Land dieses Servers haben."
  if [ -z "$YES" ]; then
    read -r -p "Trotzdem fortfahren? [j/N] " answer
    case "$answer" in j|J|y|Y) ;; *) die "Abgebrochen." ;; esac
  fi
elif [ "$rc" != 0 ]; then
  warn "Standort konnte nicht geprüft werden (Geo-IP-Dienst nicht erreichbar)."
fi

if [ -f /etc/neuvpn/state.json ]; then
  ok "Bestehende Konfiguration in /etc/neuvpn wird weiterverwendet"
else
  info "VPN-Server einrichten"
  neuvpn init --endpoint "$ENDPOINT" --port "$PORT" --country "$COUNTRY" $IPV6
fi
if ! neuvpn list | grep -q "^$CLIENT "; then
  neuvpn add "$CLIENT" >/dev/null
fi

IFACE="$(python3 -c 'import json;print(json.load(open("/etc/neuvpn/state.json"))["interface"])')"
info "VPN-Server starten (systemd: wg-quick@$IFACE)"
neuvpn apply --start
systemctl enable "wg-quick@$IFACE" >/dev/null 2>&1 || true
ok "Server läuft und startet automatisch nach einem Neustart"

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow "$PORT/udp" >/dev/null && ok "Firewall (ufw): Port $PORT/udp geöffnet"
fi

LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')"
echo
echo "════════════════════════════════════════════════════════════════"
echo " Fertig! Gerät '$CLIENT' – in der WireGuard-App QR-Code scannen:"
echo "════════════════════════════════════════════════════════════════"
neuvpn show "$CLIENT" --qr
cat <<EOF
Konfigurationsdatei: /etc/neuvpn/clients/$CLIENT.conf

WICHTIG – am Router in Rumänien eine Portweiterleitung einrichten:
  UDP $PORT  →  ${LAN_IP:-<IP dieses Geräts>}:$PORT

Weitere Geräte:     sudo neuvpn add laptop --qr && sudo neuvpn apply
Wer ist verbunden:  sudo neuvpn status
EOF
