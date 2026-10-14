#!/usr/bin/env bash
# End-to-end test of neuvpn with real WireGuard tunnels in Linux network namespaces.
#
#   [neu-cl] client 192.0.2.10 ──┐                 ┌── 198.51.100.1 [neu-ro] VPN server ("Romania")
#                                └──── [neu-inet] ─┘
#                                  "internet" + geo-IP echo service 203.0.113.80
#
# The geo service reports country RO only for the server's address, so the test
# proves that the client's traffic leaves through the VPN server.
#
# Needs root, iproute2, wireguard-tools, iptables and either the wireguard kernel
# module or wireguard-go.  Usage: sudo tests/e2e/netns_test.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
export PYTHONPATH="$REPO"
export NEUVPN_DIR="$WORK/state"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
NEUVPN=(python3 -m neuvpn)
GEO_URL="http://203.0.113.80:8080/"
SRV_IF=wgro
CL_IF=wgcl

cleanup() {
  set +e
  ip netns exec neu-cl wg-quick down "$WORK/$CL_IF.conf" >/dev/null 2>&1
  ip netns exec neu-ro wg-quick down "$WORK/srv/$SRV_IF.conf" >/dev/null 2>&1
  [ -n "${GEO_PID:-}" ] && kill "$GEO_PID" 2>/dev/null
  for ns in neu-cl neu-ro neu-inet; do
    ip netns pids "$ns" 2>/dev/null | xargs -r kill 2>/dev/null
    ip netns del "$ns" 2>/dev/null
  done
  rm -rf "$WORK"
}
trap cleanup EXIT

pass() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
in_ns() { local ns=$1; shift; ip netns exec "$ns" "$@"; }

echo "== Netzwerk aufbauen"
for ns in neu-inet neu-ro neu-cl; do ip netns del "$ns" 2>/dev/null || true; ip netns add "$ns"; done
ip link add inet-ro netns neu-inet type veth peer name wan0 netns neu-ro
ip link add inet-cl netns neu-inet type veth peer name eth0 netns neu-cl
in_ns neu-inet ip addr add 198.51.100.254/24 dev inet-ro
in_ns neu-inet ip addr add 192.0.2.254/24 dev inet-cl
in_ns neu-inet ip addr add 203.0.113.80/32 dev lo
in_ns neu-ro ip addr add 198.51.100.1/24 dev wan0
in_ns neu-cl ip addr add 192.0.2.10/24 dev eth0
for spec in neu-inet:inet-ro neu-inet:inet-cl neu-ro:wan0 neu-cl:eth0; do
  in_ns "${spec%%:*}" ip link set "${spec#*:}" up
done
for ns in neu-inet neu-ro neu-cl; do in_ns "$ns" ip link set lo up; done
in_ns neu-inet sysctl -q -w net.ipv4.ip_forward=1
in_ns neu-ro ip route add default via 198.51.100.254
in_ns neu-cl ip route add default via 192.0.2.254

# Fake geo-IP service: answers like ipinfo.io, country derived from the source IP.
in_ns neu-inet python3 - <<'PY' &
import json, http.server
COUNTRY = {"198.51.100.1": ("RO", "Bucharest")}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ip = self.client_address[0]
        country, city = COUNTRY.get(ip, ("DE", "Berlin"))
        body = json.dumps({"ip": ip, "country": country, "city": city}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("203.0.113.80", 8080), H).serve_forever()
PY
GEO_PID=$!
for _ in $(seq 50); do in_ns neu-cl python3 -c "import urllib.request;urllib.request.urlopen('$GEO_URL',timeout=1)" 2>/dev/null && break; sleep 0.1; done

echo "== Ohne VPN"
in_ns neu-cl "${NEUVPN[@]}" check --url "$GEO_URL" --expect RO >/dev/null && fail "Client ist ohne VPN schon in RO?!"
pass "Client kommt ohne VPN aus DE (192.0.2.10)"

echo "== VPN-Server einrichten (neuvpn init / add / apply --start)"
"${NEUVPN[@]}" init --endpoint 198.51.100.1 --interface "$SRV_IF" --dns 9.9.9.9 >/dev/null
# CI runners have IPv6; minimal sandboxes may not – then tunnel IPv4 only.
ALLOWED="0.0.0.0/0, ::/0"; [ -e /proc/net/if_inet6 ] || ALLOWED="0.0.0.0/0"
"${NEUVPN[@]}" add laptop --allowed-ips "$ALLOWED" >/dev/null
in_ns neu-ro "${NEUVPN[@]}" apply --wg-dir "$WORK/srv" --start --no-systemd >"$WORK/srv.log" 2>&1 \
  || { cat "$WORK/srv.log"; fail "Server startet nicht"; }
in_ns neu-ro wg show "$SRV_IF" >/dev/null || fail "Server-Interface fehlt"
pass "Server läuft auf 198.51.100.1:51820"

echo "== Client verbinden"
# no resolvconf inside the test namespaces, so drop the DNS line
"${NEUVPN[@]}" show laptop | grep -v '^DNS' > "$WORK/$CL_IF.conf"
chmod 600 "$WORK/$CL_IF.conf"
in_ns neu-cl wg-quick up "$WORK/$CL_IF.conf" >/dev/null 2>&1 || fail "Client-Tunnel startet nicht"
in_ns neu-cl ping -c 2 -W 2 10.8.0.1 >/dev/null || fail "Server im Tunnel nicht erreichbar"
pass "Tunnel steht, 10.8.0.1 per ping erreichbar"

echo "== Standort prüfen"
out=$(in_ns neu-cl "${NEUVPN[@]}" check --url "$GEO_URL") || { echo "$out"; fail "Verkehr kommt nicht aus RO"; }
echo "$out" | sed 's/^/     /'
echo "$out" | grep -q "198.51.100.1" || fail "Falsche Ausgangs-IP"
pass "Client-Verkehr verlässt das Netz über den rumänischen Server"

echo "== Status"
status=$(in_ns neu-ro "${NEUVPN[@]}" status)
echo "$status" | sed 's/^/     /'
echo "$status" | grep -q "^laptop .*vor" || fail "Handshake von 'laptop' fehlt im Status"
pass "Status zeigt den verbundenen Client"

echo "== Client live hinzufügen und sperren (wg syncconf)"
"${NEUVPN[@]}" add handy --allowed-ips "$ALLOWED" >/dev/null
in_ns neu-ro "${NEUVPN[@]}" apply --wg-dir "$WORK/srv" >/dev/null
[ "$(in_ns neu-ro wg show "$SRV_IF" peers | wc -l)" = 2 ] || fail "Neuer Peer nicht übernommen"
in_ns neu-cl ping -c 1 -W 2 10.8.0.1 >/dev/null || fail "Bestehende Verbindung durch apply unterbrochen"
pass "Neuer Client ohne Unterbrechung übernommen"
"${NEUVPN[@]}" disable laptop >/dev/null
in_ns neu-ro "${NEUVPN[@]}" apply --wg-dir "$WORK/srv" >/dev/null
in_ns neu-cl ping -c 1 -W 2 10.8.0.1 >/dev/null && fail "Gesperrter Client kommt noch durch"
pass "Gesperrter Client hat sofort keinen Zugang mehr"

echo
echo "Alle Ende-zu-Ende-Tests bestanden."
