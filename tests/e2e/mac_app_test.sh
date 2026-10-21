#!/usr/bin/env bash
# CI (macOS): the built app exactly as a user gets it – no Homebrew, no terminal tor.
# Start the app (it switches on by itself in test mode), check Safari/Chrome and a
# phone via the Mac, quit the app, and check that a crash leaves no broken proxy.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ZIP="$1"
pass() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
proxy_service() { networksetup -listallnetworkservices | sed 1d | grep -v '^\*' | head -1; }
proxy_on() { networksetup -getsocksfirewallproxy "$(proxy_service)" | grep -q "Enabled: Yes"; }
STATUS="$(mktemp -d)/status.json"
state() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("state",""))' "$STATUS" 2>/dev/null || true; }
wait_state() {  # $1 = state, $2 = seconds
  for _ in $(seq "$2"); do [ "$(state)" = "$1" ] && return 0; sleep 1; done
  echo "   Status: $(cat "$STATUS" 2>/dev/null)"; return 1
}
cleanup() { pkill -f "Rumaenien-VPN.app" 2>/dev/null || true; pkill -x tor 2>/dev/null || true; }
trap cleanup EXIT

echo "== App auspacken (wie nach dem Download)"
command -v tor >/dev/null && fail "Auf diesem Mac ist schon Tor installiert – Test wäre nicht aussagekräftig"
DEST="$HOME/Applications"
mkdir -p "$DEST"
rm -rf "$DEST/Rumaenien-VPN.app"
ditto -x -k "$ZIP" "$DEST"
APP="$DEST/Rumaenien-VPN.app"
BIN="$APP/Contents/MacOS/Rumaenien-VPN"
codesign --verify --deep --strict "$APP" && pass "App-Signatur gültig"
python3 -m venv /tmp/selenium-venv
/tmp/selenium-venv/bin/pip install --quiet selenium
sudo safaridriver --enable

start_app() {  # extra env as arguments
  rm -f "$STATUS"
  env NEUVPN_GUI_STATUS="$STATUS" "$@" "$BIN" >/tmp/app.log 2>&1 &
  APP_PID=$!
}

echo "== App starten und einschalten"
start_app NEUVPN_GUI_AUTOSTART=1 NEUVPN_GUI_SHARE=1
wait_state on 400 || { cat /tmp/app.log; fail "App wurde nicht 'An'"; }
cat "$STATUS"; echo
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(d.get("country")!="RO")' "$STATUS" \
  || fail "App zeigt nicht Rumänien"
pass "App: An – Rumänien"
proxy_on || fail "macOS-Proxy nicht aktiv"
pass "macOS-Proxy aktiv"
# Tor's GeoIP and the databases websites use can disagree about single exits; the app
# re-checks every 30 s and replaces such exits, so give it up to two minutes.
ok=""
for attempt in 1 2 3 4; do
  if /tmp/selenium-venv/bin/python "$REPO/tests/e2e/mac_browsers.py" RO; then ok=1; break; fi
  echo "   Versuch $attempt: noch nicht RO – App korrigiert den Ausgang, warte 35 s"
  sleep 35
done
excluded="$HOME/.neuvpn/tor/excluded-exits.txt"
echo "   Von der App gesperrte Ausgänge: $([ -s "$excluded" ] && tr '\n' ' ' < "$excluded" || echo keine)"
[ -n "$ok" ] || fail "Browser nicht über Rumänien"

echo "== Handy über den Mac (Proxy-Prozess der App)"
LAN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["lan"])' "$STATUS")"
for url in https://ifconfig.co/json http://ip-api.com/json; do
  c="$(curl -sS --max-time 90 --proxy "http://$LAN:9056" "$url" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("country_iso") or d.get("countryCode") or "")')"
  [ "$c" = RO ] || fail "$url über $LAN:9056 kommt aus '$c'"
  pass "$url über $LAN:9056 kommt aus Rumänien"
done

echo "== App schließen (= ausschalten)"
kill -TERM "$APP_PID"
wait "$APP_PID" || true
[ "$(state)" = closed ] || fail "App hat sich nicht sauber beendet: $(cat "$STATUS")"
proxy_on && fail "Proxy nach dem Schließen noch aktiv"
pgrep -x tor >/dev/null && fail "Tor läuft nach dem Schließen weiter"
/tmp/selenium-venv/bin/python "$REPO/tests/e2e/mac_browsers.py" '!RO' || fail "Browser noch in RO"
pass "Geschlossen: Proxy aus, Tor beendet, normale IP"

echo "== Absturz: App und Tor hart beenden, dann App neu öffnen"
start_app NEUVPN_GUI_AUTOSTART=1
wait_state on 400 || fail "App wurde nicht 'An'"
kill -9 "$APP_PID"; pkill -9 -x tor; pkill -9 -f "neuvpn-http-proxy" || true
sleep 2
proxy_on || fail "Testvoraussetzung: Proxy sollte nach dem Absturz noch an sein"
start_app
wait_state off 30 || fail "App startet nach Absturz nicht im Zustand 'Aus'"
proxy_on && fail "Proxy wurde nach dem Absturz nicht zurückgesetzt"
pass "Nach einem Absturz setzt die App den Proxy beim nächsten Öffnen zurück"
kill -TERM "$APP_PID"; wait "$APP_PID" || true

echo
echo "Alle App-Tests bestanden."
