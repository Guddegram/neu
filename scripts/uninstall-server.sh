#!/usr/bin/env bash
# neuvpn-Server entfernen. Mit --purge werden auch alle Schlüssel/Clients gelöscht.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }
IFACE=wg0
if [ -f /etc/neuvpn/state.json ]; then
  IFACE="$(python3 -c 'import json;print(json.load(open("/etc/neuvpn/state.json"))["interface"])')"
fi
systemctl disable --now "wg-quick@$IFACE" 2>/dev/null || wg-quick down "$IFACE" 2>/dev/null || true
systemctl disable --now neuvpn-duckdns.timer 2>/dev/null || true
rm -f /etc/systemd/system/neuvpn-duckdns.{service,timer} /usr/local/bin/neuvpn-duckdns
rm -f "/etc/wireguard/$IFACE.conf" /etc/sysctl.d/99-neuvpn.conf /usr/local/bin/neuvpn
rm -rf /opt/neuvpn
systemctl daemon-reload 2>/dev/null || true
if [ "${1:-}" = "--purge" ]; then
  rm -rf /etc/neuvpn
  echo "neuvpn inkl. aller Schlüssel entfernt."
else
  echo "neuvpn entfernt. Schlüssel/Clients liegen noch in /etc/neuvpn (löschen mit --purge)."
fi
