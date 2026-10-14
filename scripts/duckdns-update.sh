#!/bin/sh
# Aktualisiert DOMAIN.duckdns.org auf die aktuelle öffentliche IP (kostenloses DynDNS).
# Erwartet DUCKDNS_DOMAIN und DUCKDNS_TOKEN (siehe /etc/neuvpn/duckdns.env).
set -eu
: "${DUCKDNS_DOMAIN:?DUCKDNS_DOMAIN fehlt}"
: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN fehlt}"
answer="$(curl -fsS --max-time 20 "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=")"
if [ "$answer" != "OK" ]; then
  echo "DuckDNS-Update fehlgeschlagen: $answer" >&2
  exit 1
fi
echo "DuckDNS: ${DUCKDNS_DOMAIN}.duckdns.org aktualisiert"
