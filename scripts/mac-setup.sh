#!/usr/bin/env bash
# neuvpn auf dem Mac einrichten: Tor (Ausgang Rumänien) + VPN-Gate-Profile.
#
#   git clone https://github.com/guddegram/neu.git && cd neu
#   ./scripts/mac-setup.sh               # optional: --tunnelblick (OpenVPN-App für VPN Gate)
#
# Legt außerdem auf dem Schreibtisch zwei Doppelklick-Dateien an:
#   "Rumänien-VPN an.command" und "Rumänien-VPN aus.command"
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TUNNELBLICK=""
for arg in "$@"; do
  case "$arg" in
    --tunnelblick) TUNNELBLICK=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Unbekannte Option: $arg" >&2; exit 1 ;;
  esac
done

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m ✔\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m ✘\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || die "Dieses Skript ist für macOS."
[ "$(id -u)" != 0 ] || die "Bitte ohne sudo ausführen."

if ! command -v brew >/dev/null; then
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$candidate" ] && eval "$("$candidate" shellenv)" && break
  done
fi
if ! command -v brew >/dev/null; then
  cat <<'EOF'
Homebrew (kostenloser Paketmanager für den Mac) fehlt. Erst installieren:

  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

Danach dieses Skript erneut starten.
EOF
  exit 1
fi

info "Tor, Python und qrencode installieren (Homebrew)"
brew install tor python qrencode
if [ -n "$TUNNELBLICK" ]; then
  brew install --cask tunnelblick
fi
ok "Pakete installiert"

info "neuvpn installieren"
APP="$HOME/.neuvpn/app"
rm -rf "$APP"
mkdir -p "$APP"
cp -R "$REPO/neuvpn" "$APP/"
BIN="$(brew --prefix)/bin/neuvpn"
PY="$(brew --prefix)/bin/python3"
cat > "$BIN" <<EOF
#!/bin/sh
PYTHONPATH="$APP" exec "$PY" -m neuvpn "\$@"
EOF
chmod 755 "$BIN"
ok "Befehl 'neuvpn' verfügbar ($BIN)"

info "Doppelklick-Dateien auf dem Schreibtisch anlegen"
DESK="$HOME/Desktop"
cat > "$DESK/Rumänien-VPN an.command" <<EOF
#!/bin/sh
"$BIN" tor start
echo
echo "Dieses Fenster kann geschlossen werden – das VPN läuft weiter."
EOF
cat > "$DESK/Rumänien-VPN aus.command" <<EOF
#!/bin/sh
"$BIN" tor stop
EOF
chmod 755 "$DESK/Rumänien-VPN an.command" "$DESK/Rumänien-VPN aus.command"
ok "Schreibtisch: 'Rumänien-VPN an' und 'Rumänien-VPN aus'"

cat <<'EOF'

Fertig!
  Einschalten:   Doppelklick auf "Rumänien-VPN an"   (oder: neuvpn tor start)
  Ausschalten:   Doppelklick auf "Rumänien-VPN aus"  (oder: neuvpn tor stop)
  Prüfen:        neuvpn tor status
  Neue IP:       neuvpn tor new-ip
  Handy mitnutzen (gleiches WLAN): neuvpn tor start --share

Beim ersten Einschalten fragt macOS evtl. nach deinem Passwort (Proxy-Einstellungen).
EOF
