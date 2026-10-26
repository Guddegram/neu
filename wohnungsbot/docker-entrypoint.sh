#!/bin/sh
# Datenordner gehört dem Bot-Benutzer, dann ohne Root-Rechte starten.
set -e
mkdir -p "$DATEN_DIR"
chown -R bot:bot "$DATEN_DIR"
exec setpriv --reuid=bot --regid=bot --init-groups python -m wohnungsbot "$@"
