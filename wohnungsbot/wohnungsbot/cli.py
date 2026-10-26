"""Befehle: python -m wohnungsbot <befehl>  (Hilfe: python -m wohnungsbot -h)"""

import argparse
import logging
import os
import sys
import tempfile
from dataclasses import replace

from . import config as config_mod
from . import mailer
from .bot import Bot
from .telegram import Telegram, TelegramFehler
from .unterlagen import UnterlagenFehler, neuer_schluessel


def _cfg(args):
    config_mod.lade_env_datei(args.env)
    return config_mod.lade(args.config)


def cmd_starten(args):
    cfg = _cfg(args)
    if not cfg.telegram_token:
        sys.exit("TELEGRAM_TOKEN fehlt in der .env – ohne Telegram kann ich dir nichts melden.")
    Bot(cfg).laufen()


def cmd_pruefen(args):
    """Einmal alle Quellen prüfen und das Ergebnis anzeigen (ohne Telegram, ohne Speichern)."""
    cfg = _cfg(args)
    with tempfile.TemporaryDirectory() as tmp:
        bot = Bot(replace(cfg, daten_dir=tmp, unterlagen_schluessel=None), telegram=None)
        bot.chat = None
        treffer = bot.pruefen()
        print()
        for row in bot.speicher.db.execute("SELECT * FROM angebote ORDER BY passt DESC, nr"):
            zeichen = "✅" if row["passt"] else "  "
            grund = "" if row["passt"] else f"  [{row['grund']}]"
            print(f"{zeichen} {row['quelle']}: {(row['titel'] or '')[:70]}{grund}\n     {row['url']}")
        for q in bot.speicher.quellen():
            if q["fehler_in_folge"]:
                print(f"❌ Quelle {q['name']}: {q['letzter_fehler']}")
        print(f"\n{len(treffer)} passende Angebote.")


def cmd_mail_datei(args):
    """Eine gespeicherte Suchauftrags-Mail (.eml) prüfen: Was erkennt der Bot darin?"""
    from pathlib import Path

    from .angebot import pruefe
    from .quellen.email_alarm import angebote_aus_mail
    cfg = _cfg(args)
    angebote = angebote_aus_mail(Path(args.datei).read_bytes())
    if not angebote:
        print("Keine Angebote erkannt. Schick mir die Mail (ohne private Daten), dann passe ich den Erkenner an.")
    for a in angebote:
        a.ergaenze_aus_text()
        e = pruefe(a, cfg.kriterien)
        print(f"{'✅' if e.passt else '  '} {a.titel[:70]}\n     {a.url[:100]}\n"
              f"     Zimmer {a.zimmer} · {a.flaeche} m² · warm {a.warm} · kalt {a.kalt} · "
              f"Stadtteil {e.stadtteil or '?'}" + ("" if e.passt else f"  [{e.grund}]"))
    print(f"\n{len(angebote)} Angebote erkannt.")


def cmd_test_telegram(args):
    cfg = _cfg(args)
    if not (cfg.telegram_token and cfg.telegram_chat_id):
        sys.exit("TELEGRAM_TOKEN und TELEGRAM_CHAT_ID müssen in der .env stehen.")
    try:
        Telegram(cfg.telegram_token, cfg.telegram_api).sende(cfg.telegram_chat_id, "✅ Testnachricht vom Wohnungsbot")
    except TelegramFehler as e:
        sys.exit(f"Fehlgeschlagen: {e}")
    print("Gesendet – schau in Telegram.")


def cmd_test_mail(args):
    cfg = _cfg(args)
    if not cfg.smtp:
        sys.exit("SMTP_HOST usw. fehlen in der .env.")
    mailer.sende(cfg.smtp, args.an, "Test vom Wohnungsbot", "Wenn du das liest, funktioniert der Versand.")
    print(f"Testmail an {args.an} gesendet.")


def cmd_schluessel(args):
    print(neuer_schluessel())
    print("\nIn die .env eintragen:  UNTERLAGEN_SCHLUESSEL=<obige Zeile>\n"
          "Gut aufheben (z. B. Passwortmanager) – ohne ihn sind die Unterlagen nicht mehr lesbar.",
          file=sys.stderr)


def cmd_unterlagen(args):
    cfg = _cfg(args)
    bot = Bot(replace(cfg, telegram_token=None))
    if not bot.tresor:
        sys.exit("UNTERLAGEN_SCHLUESSEL fehlt in der .env (erzeugen: python -m wohnungsbot schluessel)")
    try:
        if args.aktion == "hinzufuegen":
            uid = bot.tresor.hinzufuegen(args.datei, args.name, args.erstkontakt)
            print(f"Verschlüsselt gespeichert (ID {uid}). Original kannst du vom Server löschen.")
        elif args.aktion == "entfernen":
            print("Entfernt." if bot.tresor.entfernen(args.id) else "ID nicht gefunden.")
        else:
            rows = bot.speicher.unterlagen()
            if not rows:
                print("Keine Unterlagen hinterlegt.")
            for r in rows:
                art = "Erstkontakt (wird angehängt)" if r["erstkontakt"] else "nur nach Rücksprache"
                print(f"{r['id']}  {r['name']}  ({r['dateiname']})  – {art}")
    except UnterlagenFehler as e:
        sys.exit(str(e))


def main(argv=None):
    p = argparse.ArgumentParser(prog="wohnungsbot", description="Wohnungsbot Bonn")
    p.add_argument("--config", default=os.environ.get("WOHNUNGSBOT_CONFIG", "config.toml"))
    p.add_argument("--env", default=".env", help="Datei mit Passwörtern/Tokens (Standard: .env)")
    p.add_argument("-v", "--ausfuehrlich", action="store_true")
    sub = p.add_subparsers(dest="befehl")
    sub.add_parser("starten", help="Bot dauerhaft laufen lassen (Standard)").set_defaults(f=cmd_starten)
    sub.add_parser("pruefen", help="einmal prüfen und Ergebnis anzeigen (nichts senden)").set_defaults(f=cmd_pruefen)
    m = sub.add_parser("mail-datei", help="gespeicherte Suchauftrags-Mail (.eml) testweise auswerten")
    m.add_argument("datei")
    m.set_defaults(f=cmd_mail_datei)
    sub.add_parser("test-telegram", help="Testnachricht an dich senden").set_defaults(f=cmd_test_telegram)
    t = sub.add_parser("test-mail", help="Testmail über SMTP senden")
    t.add_argument("an")
    t.set_defaults(f=cmd_test_mail)
    sub.add_parser("schluessel", help="neuen Schlüssel für die Unterlagen erzeugen").set_defaults(f=cmd_schluessel)
    u = sub.add_parser("unterlagen", help="Bewerbungsunterlagen verschlüsselt verwalten")
    us = u.add_subparsers(dest="aktion", required=True)
    h = us.add_parser("hinzufuegen")
    h.add_argument("datei")
    h.add_argument("--name", help="Anzeigename, z. B. 'Mieterselbstauskunft'")
    h.add_argument("--erstkontakt", action="store_true",
                   help="beim ersten Anschreiben automatisch anhängen (NICHT für SCHUFA/Gehalt/Ausweis)")
    us.add_parser("liste")
    e = us.add_parser("entfernen")
    e.add_argument("id")
    u.set_defaults(f=cmd_unterlagen)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.ausfuehrlich else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%d.%m. %H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    try:
        (getattr(args, "f", None) or cmd_starten)(args)
    except config_mod.ConfigFehler as e:
        sys.exit(f"Konfigurationsfehler: {e}")
    except KeyboardInterrupt:
        pass
