#!/usr/bin/env bash
# CI (macOS): the real user path – mac-setup.sh, "Rumänien-VPN an", Safari/Chrome,
# a phone using the Mac as proxy (--share), "Rumänien-VPN aus".
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
pass() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
# country seen through a proxy; several services because some answer Tor exits with 403
country_via() {
  local url c
  for url in https://ipinfo.io/json https://ifconfig.co/json http://ip-api.com/json; do
    c="$(curl -sS --max-time 90 --proxy "$1" "$url" 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(next((v for k in ("country_iso", "countryCode", "country") if len(v := str(d.get(k, ""))) == 2), ""))
' 2>/dev/null || true)"
    if [ -n "$c" ]; then echo "$c"; return; fi
  done
}
proxy_service() { networksetup -listallnetworkservices | sed 1d | grep -v '^\*' | head -1; }

trap 'neuvpn tor stop >/dev/null 2>&1 || true' EXIT

echo "== Einrichtung wie beim Nutzer"
"$REPO/scripts/mac-setup.sh"
python3 -m venv /tmp/selenium-venv
/tmp/selenium-venv/bin/pip install --quiet selenium
sudo safaridriver --enable

echo "== Doppelklick auf 'Rumänien-VPN an' (mit Freigabe fürs Handy)"
sed -i '' 's/tor start$/tor start --share --timeout 300/' "$HOME/Desktop/Rumänien-VPN an.command"
"$HOME/Desktop/Rumänien-VPN an.command"
networksetup -getsocksfirewallproxy "$(proxy_service)" | grep -q "Enabled: Yes" || fail "macOS-Proxy nicht aktiv"
pass "macOS-Proxy aktiv"

echo "== Safari und Chrome"
/tmp/selenium-venv/bin/python "$REPO/tests/e2e/mac_browsers.py" RO || fail "Browser nicht über Rumänien"

echo "== Handy im selben WLAN (benutzt den Mac als Proxy)"
LAN="$(PYTHONPATH="$REPO" python3 -c 'from neuvpn import tor; print(tor.lan_addresses()[0])')"
echo "   Mac-IP im Netz: $LAN"
c="$(country_via "http://$LAN:9056")"
[ "$c" = RO ] || fail "HTTPS über Proxy $LAN:9056 (iPhone-Einstellung) kommt aus '$c'"
pass "iPhone-Weg: HTTPS-Seiten über $LAN:9056 kommen aus Rumänien"
c="$(country_via "socks5h://$LAN:9055")"
[ "$c" = RO ] || fail "SOCKS über $LAN:9055 kommt aus '$c'"
pass "SOCKS-Weg: $LAN:9055 kommt aus Rumänien"
c="$(curl -sS --max-time 90 --proxy "http://$LAN:9056" http://ip-api.com/json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("countryCode",""))' 2>/dev/null || true)"
[ "$c" = RO ] || fail "Unverschlüsselte http://-Seite über $LAN:9056 kommt aus '$c'"
pass "Auch unverschlüsselte http://-Seiten über $LAN:9056 kommen aus Rumänien"

echo "== Doppelklick auf 'Rumänien-VPN aus'"
"$HOME/Desktop/Rumänien-VPN aus.command"
networksetup -getsocksfirewallproxy "$(proxy_service)" | grep -q "Enabled: No" || fail "Proxy noch aktiv"
networksetup -getsecurewebproxy "$(proxy_service)" | grep -q "Enabled: No" || fail "HTTPS-Proxy noch aktiv"
/tmp/selenium-venv/bin/python "$REPO/tests/e2e/mac_browsers.py" '!RO' || fail "Browser nach dem Ausschalten noch in RO"
pass "Ausgeschaltet: Browser haben wieder die normale IP"

echo
echo "Alle Mac-Tests bestanden."
