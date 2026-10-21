#!/usr/bin/env bash
# Baut "Rumänien-VPN.app" für den Mac, auf dem das Skript läuft (Apple Silicon oder Intel).
# Enthält: Python, die neuvpn-Oberfläche und das offizielle Tor Expert Bundle (torproject.org).
# Ergebnis: dist/Rumaenien-VPN-mac-<arm64|x86_64>.zip
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
ARCH="$(uname -m)"                               # arm64 | x86_64
TOR_ARCH="$([ "$ARCH" = arm64 ] && echo aarch64 || echo x86_64)"
WORK="$(mktemp -d)"
DIST="$REPO/dist"
APP_NAME="Rumaenien-VPN"

echo "== Neuestes Tor Expert Bundle für macOS-$TOR_ARCH suchen"
BASE=https://dist.torproject.org/torbrowser
VERSIONS="$(curl -fsSL "$BASE/" | grep -oE 'href="[0-9]+\.[0-9]+(\.[0-9]+)?/"' | grep -oE '[0-9][0-9.]*[0-9]' | sort -Vr)"
TARBALL=""
for v in $VERSIONS; do
  name="tor-expert-bundle-macos-$TOR_ARCH-$v.tar.gz"
  if curl -fsI "$BASE/$v/$name" >/dev/null 2>&1; then
    TARBALL="$name"; VERSION="$v"; break
  fi
done
[ -n "$TARBALL" ] || { echo "Kein Tor Expert Bundle gefunden" >&2; exit 1; }
echo "   $TARBALL"
curl -fsSL -o "$WORK/$TARBALL" "$BASE/$VERSION/$TARBALL"
curl -fsSL -o "$WORK/sha256sums.txt" "$BASE/$VERSION/sha256sums-signed-build.txt"
(cd "$WORK" && grep " $TARBALL\$" sha256sums.txt | shasum -a 256 -c -)
mkdir -p "$WORK/tor-bundle"
tar -xzf "$WORK/$TARBALL" -C "$WORK/tor-bundle"
test -x "$WORK/tor-bundle/tor/tor" && test -f "$WORK/tor-bundle/data/geoip"
"$WORK/tor-bundle/tor/tor" --version | head -1

echo "== App bauen (PyInstaller)"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet pyinstaller
rm -rf "$REPO/build" "$DIST/$APP_NAME.app"
"$WORK/venv/bin/pyinstaller" --noconfirm --windowed --name "$APP_NAME" \
  --osx-bundle-identifier de.guddegram.rumaenienvpn \
  --paths "$REPO" --hidden-import neuvpn.httpproxy \
  --distpath "$DIST" --workpath "$WORK/build" --specpath "$WORK" \
  "$REPO/app/rumaenien_vpn.py"
APP="$DIST/$APP_NAME.app"
mkdir -p "$APP/Contents/Resources/tor-bundle"
cp -R "$WORK/tor-bundle/tor" "$WORK/tor-bundle/data" "$APP/Contents/Resources/tor-bundle/"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Rumänien-VPN" "$APP/Contents/Info.plist" \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string Rumänien-VPN" "$APP/Contents/Info.plist"
APP_VERSION="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' "$REPO/neuvpn/__init__.py")"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$APP/Contents/Info.plist"

echo "== Signieren (ad hoc, ohne Apple-Entwicklerkonto)"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "== Packen"
ZIP="$DIST/$APP_NAME-mac-$ARCH.zip"
rm -f "$ZIP"
(cd "$DIST" && ditto -c -k --keepParent "$APP_NAME.app" "$ZIP")
echo "Fertig: $ZIP (Tor $VERSION)"
