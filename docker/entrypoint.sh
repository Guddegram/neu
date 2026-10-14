#!/bin/sh
set -eu
NEUVPN_DIR="${NEUVPN_DIR:-/etc/neuvpn}"
if [ ! -f "$NEUVPN_DIR/state.json" ]; then
  : "${NEUVPN_ENDPOINT:?NEUVPN_ENDPOINT setzen (öffentliche IP oder DuckDNS-Name des Servers)}"
  set -- --endpoint "$NEUVPN_ENDPOINT" --port "${NEUVPN_PORT:-51820}" --country "${NEUVPN_COUNTRY:-RO}"
  [ -n "${NEUVPN_DNS:-}" ] && set -- "$@" --dns "$NEUVPN_DNS"
  [ "${NEUVPN_IPV6:-0}" = 1 ] && set -- "$@" --ipv6
  neuvpn init "$@"
  for name in $(echo "${NEUVPN_CLIENTS:-handy}" | tr ',' ' '); do
    neuvpn add "$name"
    neuvpn show "$name" --qr
  done
fi
IFACE="$(python3 -c 'import json,os;print(json.load(open(os.environ["NEUVPN_DIR"]+"/state.json"))["interface"])')"
neuvpn apply --start --no-systemd
trap 'wg-quick down "$IFACE"; exit 0' TERM INT
echo "neuvpn läuft. Geräte: docker compose exec neuvpn neuvpn add <name> --qr && docker compose exec neuvpn neuvpn apply"
sleep infinity &
wait $!
