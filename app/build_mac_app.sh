#!/usr/bin/env bash
# Baut das Mac-Programm "Rumänien-VPN" als Universal-App (Apple-Chip + Intel) und
# verpackt es als dist/Rumaenien-VPN.dmg (öffnen, App in "Programme" ziehen).
# Enthält: Python (python.org, universal2), die neuvpn-Oberfläche und das offizielle
# Tor Expert Bundle (torproject.org) für beide Prozessoren.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
WORK="$(mktemp -d)"
DIST="$REPO/dist"
APP_TITLE="Rumänien-VPN"
EXE="Rumaenien-VPN"

echo "== Python (universal2) von python.org"
PY_VERSION="$(curl -fsSL https://www.python.org/ftp/python/ | grep -oE 'href="3\.13\.[0-9]+/"' \
  | grep -oE '3\.13\.[0-9]+' | sort -Vr | while read -r v; do
    curl -fsI "https://www.python.org/ftp/python/$v/python-$v-macos11.pkg" >/dev/null 2>&1 && { echo "$v"; break; }
  done)"
[ -n "$PY_VERSION" ] || { echo "Kein Python-Installer gefunden" >&2; exit 1; }
curl -fsSL -o "$WORK/python.pkg" "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg"
pkgutil --check-signature "$WORK/python.pkg" | grep -q "Python Software Foundation"
sudo installer -pkg "$WORK/python.pkg" -target / >/dev/null
PY="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
echo "   Python $PY_VERSION: $(lipo -archs "$PY")"

echo "== Tor Expert Bundle für beide Prozessoren"
BASE=https://dist.torproject.org/torbrowser
TOR_VERSION=""
for v in $(curl -fsSL "$BASE/" | grep -oE 'href="[0-9]+\.[0-9]+(\.[0-9]+)?/"' | grep -oE '[0-9][0-9.]*[0-9]' | sort -Vr); do
  if curl -fsI "$BASE/$v/tor-expert-bundle-macos-aarch64-$v.tar.gz" >/dev/null 2>&1 \
     && curl -fsI "$BASE/$v/tor-expert-bundle-macos-x86_64-$v.tar.gz" >/dev/null 2>&1; then
    TOR_VERSION="$v"; break
  fi
done
[ -n "$TOR_VERSION" ] || { echo "Kein Tor Expert Bundle gefunden" >&2; exit 1; }
curl -fsSL -o "$WORK/sha256sums.txt" "$BASE/$TOR_VERSION/sha256sums-signed-build.txt"
for arch in aarch64 x86_64; do
  name="tor-expert-bundle-macos-$arch-$TOR_VERSION.tar.gz"
  curl -fsSL -o "$WORK/$name" "$BASE/$TOR_VERSION/$name"
  (cd "$WORK" && grep " $name\$" sha256sums.txt | shasum -a 256 -c -)
  mkdir -p "$WORK/tor-$arch"
  tar -xzf "$WORK/$name" -C "$WORK/tor-$arch"
done
# one universal tor + libevent (lipo), GeoIP data; bridges/pluggable transports are not used
BUNDLE="$WORK/tor-bundle"
mkdir -p "$BUNDLE/tor"
cp -R "$WORK/tor-aarch64/data" "$BUNDLE/"
for f in tor $(cd "$WORK/tor-aarch64/tor" && ls ./*.dylib); do
  f="${f#./}"
  lipo -create "$WORK/tor-aarch64/tor/$f" "$WORK/tor-x86_64/tor/$f" -output "$BUNDLE/tor/$f"
done
chmod 755 "$BUNDLE/tor/tor"
# Apple Silicon only runs signed code; the bundle ships libevent unsigned -> sign ad hoc
codesign --force --sign - "$BUNDLE"/tor/*
"$BUNDLE/tor/tor" --version | head -1
echo "   Tor $TOR_VERSION: $(lipo -archs "$BUNDLE/tor/tor")"

echo "== App bauen (PyInstaller, universal2)"
"$PY" -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet pyinstaller pillow
"$WORK/venv/bin/python" "$REPO/app/make_icon.py" "$WORK/icon.icns"
rm -rf "$REPO/build" "$DIST"
"$WORK/venv/bin/pyinstaller" --noconfirm --windowed --name "$EXE" --target-arch universal2 \
  --icon "$WORK/icon.icns" --osx-bundle-identifier de.guddegram.rumaenienvpn \
  --paths "$REPO" --hidden-import neuvpn.httpproxy \
  --distpath "$WORK/dist" --workpath "$WORK/build" --specpath "$WORK" \
  "$REPO/app/rumaenien_vpn.py"
APP="$WORK/dist/$APP_TITLE.app"
mv "$WORK/dist/$EXE.app" "$APP"
mkdir -p "$APP/Contents/Resources/tor-bundle"
cp -R "$BUNDLE/tor" "$BUNDLE/data" "$APP/Contents/Resources/tor-bundle/"
PLIST="$APP/Contents/Info.plist"
APP_VERSION="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' "$REPO/neuvpn/__init__.py")"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_TITLE" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_TITLE" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string $APP_TITLE" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 11.0" "$PLIST" 2>/dev/null || true
lipo -archs "$APP/Contents/MacOS/$EXE"

echo "== Signieren (ad hoc, ohne Apple-Entwicklerkonto)"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

echo "== DMG bauen"
STAGE="$WORK/dmg"
mkdir -p "$STAGE" "$DIST"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Programme"
hdiutil create -quiet -volname "$APP_TITLE" -srcfolder "$STAGE" -ov -format UDZO \
  "$DIST/Rumaenien-VPN.dmg"
echo "Fertig: $DIST/Rumaenien-VPN.dmg (Python $PY_VERSION, Tor $TOR_VERSION)"
