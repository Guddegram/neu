"""Hauptschleife: alle N Minuten Quellen prüfen, dazwischen auf Telegram-Knöpfe reagieren.

Ablauf einer Bewerbung (Version B – nichts geht ohne deine Freigabe raus):
  neue passende Wohnung  -> Telegram-Nachricht  [📝 Bewerbung vorbereiten] [🙈 Ignorieren]
  📝                      -> Anschreiben + Anhänge-Liste  [✅ Senden an …] / [✅ Selbst beworben]
  ✅ Senden               -> E-Mail mit Erstkontakt-Unterlagen geht raus, Status "beworben"
"""

import logging
import re
import time
import traceback
from pathlib import Path

from . import anschreiben, mailer
from .angebot import pruefe
from .speicher import Speicher
from .telegram import Telegram, TelegramFehler, h, knoepfe
from .unterlagen import Tresor

log = logging.getLogger("wohnungsbot")

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
FEHLER_BIS_WARNUNG = 3


def _zahl(x):
    return f"{x:g}".replace(".", ",")


def _euro(x):
    return f"{x:,.0f} €".replace(",", ".")


class Bot:
    def __init__(self, cfg, telegram=None, uhr=time.time):
        self.cfg = cfg
        Path(cfg.daten_dir).mkdir(parents=True, exist_ok=True)
        self.speicher = Speicher(str(Path(cfg.daten_dir) / "wohnungsbot.db"))
        self.tg = telegram or (Telegram(cfg.telegram_token, cfg.telegram_api) if cfg.telegram_token else None)
        self.chat = cfg.telegram_chat_id
        self.uhr = uhr
        self.naechste_pruefung = 0.0
        self.tresor = None
        if cfg.unterlagen_schluessel:
            self.tresor = Tresor(Path(cfg.daten_dir) / "unterlagen", cfg.unterlagen_schluessel, self.speicher)

    # ------------------------------------------------------------------ Senden
    def melde(self, text, markup=None, antwort_auf=None):
        if not (self.tg and self.chat):
            log.info("(keine Telegram-Ausgabe) %s", re.sub(r"<[^>]+>", "", text))
            return None
        try:
            return self.tg.sende(self.chat, text, markup, antwort_auf)["message_id"]
        except TelegramFehler as e:
            log.error("Telegram-Nachricht fehlgeschlagen: %s", e)
            return None

    def knoepfe_weg(self, nachricht_id):
        if self.tg and self.chat and nachricht_id:
            self.tg.knoepfe_aendern(self.chat, nachricht_id)

    # ------------------------------------------------------------------ Prüfen
    def pruefen(self):
        """Ein Durchlauf über alle Quellen. Gibt Liste (Angebot, Ergebnis) der neuen Treffer zurück."""
        treffer = []
        for quelle in self.cfg.quellen:
            try:
                angebote = quelle.hole()
            except Exception as e:
                fehler = f"{e.__class__.__name__}: {e}"[:300]
                log.warning("Quelle %s fehlgeschlagen: %s", quelle.name, fehler)
                if self.speicher.quelle_fehler(quelle.name, fehler, FEHLER_BIS_WARNUNG):
                    self.melde(f"⚠️ Quelle <b>{h(quelle.name)}</b> funktioniert seit "
                               f"{FEHLER_BIS_WARNUNG} Prüfungen nicht:\n<code>{h(fehler)}</code>")
                continue
            if self.speicher.quelle_ok(quelle.name, len(angebote)):
                self.melde(f"✅ Quelle <b>{h(quelle.name)}</b> läuft wieder.")
            neu = 0
            for a in angebote:
                if self.speicher.bekannt(a.id):
                    continue
                neu += 1
                a.ergaenze_aus_text()
                erg = pruefe(a, self.cfg.kriterien)
                if erg.passt and self.speicher.fingerabdruck_gemeldet(a.fingerabdruck()):
                    self.speicher.speichere(a, erg, "doppelt")
                    log.info("Doppelt (schon von anderer Quelle gemeldet): %s", a.url)
                    continue
                self.speicher.speichere(a, erg, "gemeldet" if erg.passt else "abgelehnt")
                if erg.passt:
                    treffer.append((a, erg))
                else:
                    log.debug("abgelehnt (%s): %s", erg.grund, a.titel)
            log.info("Quelle %s: %d Angebote, %d neu", quelle.name, len(angebote), neu)

        for a, erg in treffer[: self.cfg.max_meldungen_pro_lauf]:
            self.melde_angebot(a, erg)
        rest = len(treffer) - self.cfg.max_meldungen_pro_lauf
        if rest > 0:
            self.melde(f"… und {rest} weitere passende Angebote. Übersicht: /liste")
        self.speicher.setze_meta("letzte_pruefung", int(self.uhr()))
        log.info("Prüfung fertig: %d neue Treffer", len(treffer))
        return treffer

    def text_angebot(self, a, erg, nr):
        zeilen = [f"🏠 <b>Neue Wohnung: {h(erg.stadtteil)}</b>",
                  f'<a href="{h(a.url)}">{h(a.titel or a.url)}</a>']
        if erg.warm is not None:
            art = {"angegeben": "", "berechnet": " (kalt + NK)",
                   "geschätzt": f" (geschätzt: kalt + {_zahl(self.cfg.kriterien.nk_pro_qm)} €/m²)"}
            preis = f"💶 {_euro(erg.warm)} warm{art.get(erg.warm_art, '')}"
        elif a.kalt is not None:
            preis = f"💶 {_euro(a.kalt)} kalt"
        else:
            preis = "💶 Miete unbekannt"
        if erg.grenze:
            preis += f" · Grenze {_euro(erg.grenze)}"
        zeilen.append(preis)
        details = []
        if a.zimmer:
            details.append(f"🛏 {_zahl(a.zimmer)} Zimmer")
        if a.flaeche:
            details.append(f"📐 {_zahl(a.flaeche)} m²")
        if details:
            zeilen.append(" · ".join(details))
        if a.adresse:
            zeilen.append(f"📍 {h(a.adresse)}")
        zeilen.append(f"🔎 {h(a.quelle)} · Nr. {nr}")
        for hinweis in erg.hinweise:
            zeilen.append(f"⚠️ {h(hinweis)}")
        return "\n".join(zeilen)

    def melde_angebot(self, a, erg):
        row = self.speicher.hole(a.id)
        msg = self.melde(self.text_angebot(a, erg, row["nr"]),
                         knoepfe([("📝 Bewerbung vorbereiten", f"prep:{a.id}"), ("🙈 Ignorieren", f"ign:{a.id}")]))
        if msg:
            self.speicher.setze(a.id, tg_nachricht=msg)

    # ------------------------------------------------------------------ Bewerbung
    def _anhaenge_namen(self):
        if not self.tresor:
            return []
        return [r["dateiname"] for r in self.speicher.unterlagen(nur_erstkontakt=True)]

    def vorbereiten(self, angebot_id):
        row = self.speicher.hole(angebot_id)
        if row is None:
            return self.melde("Angebot nicht (mehr) gefunden.")
        if row["status"] == "beworben":
            return self.melde(f"Für Nr. {row['nr']} hast du dich schon beworben.")
        a, erg = Speicher.angebot_aus(row), Speicher.ergebnis_aus(row)
        anhaenge = self._anhaenge_namen()
        betreff, text = anschreiben.erstelle(a, erg, self.cfg.bewerber, self.cfg.vorlage, anhaenge)
        text = text[:3000]
        self.speicher.setze(angebot_id, status="vorbereitet", anschreiben=text, betreff=betreff)
        msg = self.melde(self.text_vorbereitung(self.speicher.hole(angebot_id)),
                         self.knoepfe_vorbereitung(self.speicher.hole(angebot_id)))
        if msg:
            self.speicher.setze(angebot_id, tg_vorbereitung=msg)
        self.knoepfe_weg(row["tg_nachricht"])

    def text_vorbereitung(self, row):
        anhaenge = self._anhaenge_namen()
        teile = [f"📝 <b>Bewerbung Nr. {row['nr']}</b> – {h(row['titel'])}",
                 f"<b>Betreff:</b> {h(row['betreff'])}",
                 f"<pre>{h(row['anschreiben'])}</pre>",
                 "📎 Anhänge (Erstkontakt): " + (h(", ".join(anhaenge)) if anhaenge else "keine")]
        if not self.cfg.smtp:
            teile.append("ℹ️ E-Mail-Versand ist nicht eingerichtet (SMTP in .env). "
                         f'Text kopieren und im <a href="{h(row["url"])}">Kontaktformular</a> einfügen.')
        elif row["kontakt_email"]:
            teile.append(f"✉️ Empfänger: <b>{h(row['kontakt_email'])}</b>\n"
                         "Andere Adresse? Einfach auf diese Nachricht mit der E-Mail-Adresse antworten.")
        else:
            teile.append("✉️ Keine E-Mail-Adresse in der Anzeige.\n"
                         f'• Text kopieren und im <a href="{h(row["url"])}">Kontaktformular</a> einfügen, oder\n'
                         "• auf diese Nachricht mit der E-Mail-Adresse des Vermieters antworten – dann kann ich senden.")
        return "\n\n".join(teile)

    def knoepfe_vorbereitung(self, row):
        aid = row["id"]
        erste = []
        if self.cfg.smtp and row["kontakt_email"]:
            erste.append((f"✅ Senden an {row['kontakt_email']}"[:60], f"send:{aid}"))
        zweite = [("✔️ Selbst beworben", f"done:{aid}"), ("❌ Abbrechen", f"cancel:{aid}")]
        return knoepfe(erste, zweite)

    def senden(self, angebot_id):
        row = self.speicher.hole(angebot_id)
        if row is None or row["status"] != "vorbereitet":
            return self.melde("Diese Bewerbung ist nicht (mehr) zum Senden vorbereitet.")
        if not (self.cfg.smtp and row["kontakt_email"]):
            return self.melde("Kein Empfänger oder kein E-Mail-Versand eingerichtet.")
        try:
            anhaenge = self.tresor.anhaenge_erstkontakt() if self.tresor else []
            mailer.sende(self.cfg.smtp, row["kontakt_email"], row["betreff"], row["anschreiben"], anhaenge)
        except Exception as e:  # SMTP-, Netz- oder Entschlüsselungsfehler
            log.error("Senden fehlgeschlagen: %s", traceback.format_exc())
            return self.melde(f"❌ Senden an {h(row['kontakt_email'])} fehlgeschlagen:\n"
                              f"<code>{h(str(e)[:300])}</code>")
        self.speicher.setze(angebot_id, status="beworben")
        self.knoepfe_weg(row["tg_vorbereitung"])
        self.melde(f"✅ Bewerbung Nr. {row['nr']} an <b>{h(row['kontakt_email'])}</b> gesendet "
                   f"({len(anhaenge)} Anhänge).")

    def setze_email(self, row, adresse):
        self.speicher.setze(row["id"], kontakt_email=adresse)
        row = self.speicher.hole(row["id"])
        if row["status"] != "vorbereitet":
            return self.melde(f"Adresse für Nr. {row['nr']} gespeichert. Erst „📝 Bewerbung vorbereiten“ drücken.")
        self.knoepfe_weg(row["tg_vorbereitung"])
        msg = self.melde(self.text_vorbereitung(row), self.knoepfe_vorbereitung(row))
        if msg:
            self.speicher.setze(row["id"], tg_vorbereitung=msg)

    # ------------------------------------------------------------------ Telegram-Eingaben
    def verarbeite(self, update):
        if "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq.get("message", {}).get("chat", {}).get("id")
            if chat_id != self.chat:
                self.tg.callback_beantworten(cq["id"], "Nicht erlaubt.")
                return
            self.tg.callback_beantworten(cq["id"])
            aktion, _, aid = (cq.get("data") or "").partition(":")
            row = self.speicher.hole(aid)
            if aktion == "prep":
                self.vorbereiten(aid)
            elif aktion == "send":
                self.senden(aid)
            elif row is None:
                self.melde("Angebot nicht (mehr) gefunden.")
            elif aktion == "done":
                self.speicher.setze(aid, status="beworben")
                self.knoepfe_weg(cq["message"]["message_id"])
                self.melde(f"✔️ Nr. {row['nr']} als beworben markiert.")
            elif aktion == "ign":
                self.speicher.setze(aid, status="ignoriert")
                self.knoepfe_weg(cq["message"]["message_id"])
            elif aktion == "cancel":
                self.speicher.setze(aid, status="gemeldet")
                self.knoepfe_weg(cq["message"]["message_id"])
                self.melde(f"Bewerbung Nr. {row['nr']} abgebrochen. Neu starten: /bewerben {row['nr']}")
            return

        msg = update.get("message")
        if not msg:
            return
        chat_id = msg.get("chat", {}).get("id")
        text = (msg.get("text") or "").strip()
        if chat_id != self.chat:
            # Fremde bekommen nur ihre Chat-ID (für die Einrichtung), sonst nichts.
            if self.tg and text.startswith("/start"):
                try:
                    self.tg.sende(chat_id, f"Deine Chat-ID: <code>{chat_id}</code>\n"
                                           "Trage sie als TELEGRAM_CHAT_ID in die .env ein.")
                except TelegramFehler:
                    pass
            return

        antwort_auf = (msg.get("reply_to_message") or {}).get("message_id")
        if antwort_auf and EMAIL_RE.match(text):
            row = self.speicher.nach_vorbereitungsnachricht(antwort_auf)
            if row:
                return self.setze_email(row, text)
        befehl, _, rest = text.partition(" ")
        befehl = befehl.split("@")[0].lower()
        if befehl in ("/start", "/hilfe", "/help"):
            self.melde(HILFE)
        elif befehl == "/status":
            self.melde(self.text_status())
        elif befehl == "/liste":
            self.melde(self.text_liste())
        elif befehl == "/pruefen":
            self.melde("🔄 Prüfe jetzt alle Quellen …")
            self.naechste_pruefung = 0
        elif befehl == "/mail":
            teile = rest.split()
            if len(teile) == 2 and teile[0].isdigit() and EMAIL_RE.match(teile[1]):
                row = self.speicher.hole_nr(int(teile[0]))
                if row:
                    return self.setze_email(row, teile[1])
                return self.melde(f"Nr. {teile[0]} gibt es nicht.")
            self.melde("So geht's: <code>/mail 12 vermieter@beispiel.de</code>")
        elif befehl == "/bewerben":
            if rest.strip().isdigit() and (row := self.speicher.hole_nr(int(rest))):
                return self.vorbereiten(row["id"])
            self.melde("So geht's: <code>/bewerben 12</code>")
        elif befehl == "/unterlagen":
            self.melde(self.text_unterlagen())
        else:
            self.melde("Unbekannter Befehl. /hilfe zeigt alle Befehle.")

    def text_status(self):
        z = self.speicher.zaehle()
        letzte = self.speicher.meta("letzte_pruefung")
        zeilen = ["📊 <b>Status</b>",
                  "Letzte Prüfung: " + (time.strftime("%d.%m. %H:%M", time.localtime(int(letzte))) if letzte else "noch keine"),
                  f"Intervall: alle {_zahl(self.cfg.intervall_minuten)} Minuten",
                  f"Gemeldet: {z.get('gemeldet', 0) + z.get('vorbereitet', 0)} · beworben: {z.get('beworben', 0)} · "
                  f"ignoriert: {z.get('ignoriert', 0)} · aussortiert: {z.get('abgelehnt', 0)}",
                  "", "<b>Quellen</b>"]
        bekannte = {r["name"]: r for r in self.speicher.quellen()}
        for q in self.cfg.quellen:
            r = bekannte.get(q.name)
            if r is None:
                zeilen.append(f"• {h(q.name)}: noch nicht geprüft")
            elif r["fehler_in_folge"]:
                zeilen.append(f"• ❌ {h(q.name)}: {r['fehler_in_folge']}× Fehler – {h(r['letzter_fehler'])}")
            else:
                zeilen.append(f"• ✅ {h(q.name)}: zuletzt {r['letzte_anzahl']} Angebote gelesen")
        if not self.cfg.quellen:
            zeilen.append("• keine Quellen eingerichtet (config.toml)")
        zeilen.append("")
        zeilen.append("E-Mail-Versand: " + ("eingerichtet" if self.cfg.smtp else "nicht eingerichtet"))
        return "\n".join(zeilen)

    def text_liste(self):
        rows = self.speicher.letzte_treffer(10)
        if not rows:
            return "Noch keine passenden Wohnungen gefunden."
        symbol = {"gemeldet": "🆕", "vorbereitet": "📝", "beworben": "✅", "ignoriert": "🙈"}
        zeilen = ["<b>Letzte Treffer</b>"]
        for r in rows:
            erg = Speicher.ergebnis_aus(r)
            preis = f"{_euro(erg.warm)} warm" if erg.warm is not None else "Preis ?"
            zeilen.append(f'{symbol.get(r["status"], "•")} Nr. {r["nr"]}: <a href="{h(r["url"])}">'
                          f"{h((r['titel'] or '')[:50])}</a> – {h(erg.stadtteil)}, {preis}")
        zeilen.append("\nBewerben: <code>/bewerben NR</code>")
        return "\n".join(zeilen)

    def text_unterlagen(self):
        if not self.tresor:
            return "Unterlagen-Tresor nicht eingerichtet (UNTERLAGEN_SCHLUESSEL in .env)."
        rows = self.speicher.unterlagen()
        if not rows:
            return "Keine Unterlagen hinterlegt."
        return "<b>Hinterlegte Unterlagen</b> (verschlüsselt)\n" + "\n".join(
            f"• {h(r['name'])} ({h(r['dateiname'])}) – "
            + ("📎 wird beim Erstkontakt angehängt" if r["erstkontakt"] else "🔒 nur nach Rücksprache")
            for r in rows)

    # ------------------------------------------------------------------ Schleife
    def schritt(self, poll_timeout=25):
        """Ein Schritt der Endlosschleife (für Tests einzeln aufrufbar)."""
        if self.uhr() >= self.naechste_pruefung:
            try:
                self.pruefen()
            except Exception:
                log.error("Prüfung abgestürzt:\n%s", traceback.format_exc())
            self.naechste_pruefung = self.uhr() + self.cfg.intervall_minuten * 60
        if not self.tg:
            time.sleep(max(0, min(poll_timeout, self.naechste_pruefung - self.uhr())))
            return
        warte = int(max(1, min(poll_timeout, self.naechste_pruefung - self.uhr())))
        offset = int(self.speicher.meta("tg_offset", 0)) or None
        try:
            updates = self.tg.updates(offset, warte)
        except TelegramFehler as e:
            log.warning("Telegram nicht erreichbar: %s", e)
            time.sleep(5)
            return
        for u in updates:
            self.speicher.setze_meta("tg_offset", u["update_id"] + 1)
            try:
                self.verarbeite(u)
            except Exception:
                log.error("Fehler bei Telegram-Eingabe:\n%s", traceback.format_exc())

    def laufen(self):
        log.info("Wohnungsbot gestartet: %d Quellen, Prüfung alle %s Minuten",
                 len(self.cfg.quellen), _zahl(self.cfg.intervall_minuten))
        if self.tg and not self.chat:
            log.warning("TELEGRAM_CHAT_ID fehlt: Schreib deinem Bot /start, er antwortet mit deiner Chat-ID.")
        else:
            self.melde("🤖 Wohnungsbot gestartet. /hilfe zeigt alle Befehle.")
        while True:
            self.schritt()


HILFE = """<b>Wohnungsbot Bonn</b>
Ich prüfe regelmäßig alle Quellen und melde mich bei passenden Wohnungen.

/status – letzte Prüfung, Zustand der Quellen
/liste – die letzten 10 Treffer
/pruefen – sofort prüfen
/bewerben NR – Bewerbung für Treffer NR vorbereiten
/mail NR adresse – E-Mail des Vermieters setzen
/unterlagen – hinterlegte Unterlagen

Nichts wird ohne deinen Klick auf „✅ Senden“ verschickt."""
