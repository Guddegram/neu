"""Ende-zu-Ende: Webseite -> Filter -> Telegram (nachgebaut) -> Knöpfe -> E-Mail (nachgebauter SMTP-Server)."""

import email
import email.policy
import json
import os
import socketserver
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from wohnungsbot import config as config_mod
from wohnungsbot.bot import Bot
from wohnungsbot.telegram import Telegram
from wohnungsbot.unterlagen import neuer_schluessel

from .test_quellen import _Server

BEISPIEL = Path(__file__).resolve().parents[1] / "config.example.toml"
CHAT = 4242

ANGEBOTSSEITE = """<html><body><h1>Unsere freien Wohnungen</h1>
<div class="angebot"><a href="/expose/1"><h3>Helle 3-Zimmer-Wohnung</h3></a>
  <p>Oppelner Str. 10, 53119 Bonn-Tannenbusch</p><p>3 Zimmer · 72 m² · Warmmiete 1.050 €</p></div>
<div class="angebot"><a href="/expose/2"><h3>Familienwohnung</h3></a>
  <p>Londoner Str. 5, 53117 Bonn-Auerberg</p><p>4 Zimmer · 90 m² · Kaltmiete 950 €</p>
  <p>Kontakt: vermietung@wohnen-auerberg.de</p></div>
<div class="angebot"><a href="/expose/3"><h3>Altbau</h3></a>
  <p>53115 Bonn-Poppelsdorf</p><p>3 Zimmer · 80 m² · Warmmiete 1.000 €</p></div>
<div class="angebot"><a href="/expose/4"><h3>Kleine Wohnung</h3></a>
  <p>53121 Bonn-Dransdorf</p><p>2 Zimmer · 66 m² · Warmmiete 800 €</p></div>
<footer><a href="/impressum">Impressum</a></footer></body></html>"""


class FakeTelegram:
    """Nachgebaute Telegram-Bot-API auf localhost."""

    def __init__(self):
        self.aufrufe = []
        self.updates = []
        self.naechste_id = 100
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                methode = self.path.rsplit("/", 1)[-1]
                daten = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                fake.aufrufe.append((methode, daten))
                if methode == "sendMessage":
                    fake.naechste_id += 1
                    ergebnis = {"message_id": fake.naechste_id, "chat": {"id": daten["chat_id"]}}
                elif methode == "getUpdates":
                    ergebnis, fake.updates = fake.updates, []
                else:
                    ergebnis = True
                antwort = json.dumps({"ok": True, "result": ergebnis}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(antwort)))
                self.end_headers()
                self.wfile.write(antwort)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def nachrichten(self):
        return [d for m, d in self.aufrufe if m == "sendMessage"]

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class FakeSmtp:
    """Minimaler SMTP-Server (ohne TLS), der empfangene Mails sammelt."""

    def __init__(self):
        self.mails = []
        fake = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                def sag(text):
                    self.wfile.write((text + "\r\n").encode())
                sag("220 fake")
                empfaenger = []
                while True:
                    zeile = self.rfile.readline().decode(errors="replace").strip()
                    if not zeile:
                        return
                    cmd = zeile.split(" ")[0].upper()
                    if cmd in ("EHLO", "HELO"):
                        sag("250 fake")
                    elif cmd == "MAIL":
                        empfaenger = []
                        sag("250 OK")
                    elif cmd == "RCPT":
                        empfaenger.append(zeile.split(":", 1)[1].strip(" <>"))
                        sag("250 OK")
                    elif cmd == "DATA":
                        sag("354 los")
                        daten = []
                        while True:
                            z = self.rfile.readline()
                            if z in (b".\r\n", b".\n", b""):
                                break
                            daten.append(z[1:] if z.startswith(b"..") else z)
                        fake.mails.append((empfaenger, email.message_from_bytes(b"".join(daten), policy=email.policy.default)))
                        sag("250 OK")
                    elif cmd == "QUIT":
                        sag("221 tschüss")
                        return
                    else:
                        sag("250 OK")

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def klick(daten, chat=CHAT, msg_id=1):
    return {"update_id": 0, "callback_query": {"id": "cb", "data": daten,
                                               "message": {"message_id": msg_id, "chat": {"id": chat}}}}


def text(t, chat=CHAT, antwort_auf=None):
    m = {"message_id": 999, "chat": {"id": chat}, "text": t}
    if antwort_auf:
        m["reply_to_message"] = {"message_id": antwort_auf}
    return {"update_id": 0, "message": m}


class BotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.web = _Server({"/wohnungen": ANGEBOTSSEITE})
        self.tg = FakeTelegram()
        self.smtp = FakeSmtp()
        with mock.patch.dict(os.environ, {"IMAP_HOST": "x", "IMAP_BENUTZER": "x", "IMAP_PASSWORT": "x"}):
            cfg = config_mod.lade(BEISPIEL)
        from wohnungsbot.quellen.web import HtmlQuelle
        self.cfg = replace(
            cfg, quellen=[HtmlQuelle("Testgesellschaft", self.web.url + "/wohnungen")],
            daten_dir=self.tmp.name, telegram_token="TOKEN", telegram_chat_id=CHAT,
            telegram_api=self.tg.url, unterlagen_schluessel=neuer_schluessel(),
            smtp={"host": "127.0.0.1", "port": self.smtp.port, "benutzer": None, "passwort": None,
                  "absender": "ich@example.de", "absender_name": "Max Mustermann", "starttls": False})
        self.bot = Bot(self.cfg, telegram=Telegram("TOKEN", self.tg.url))

    def tearDown(self):
        self.bot.speicher.db.close()
        self.web.stop()
        self.tg.stop()
        self.smtp.stop()
        self.tmp.cleanup()

    def eingabe(self, update):
        self.bot.verarbeite(update)

    def test_ganzer_ablauf(self):
        # Unterlagen: eine für den Erstkontakt, eine sensible (darf NICHT mit)
        auskunft = Path(self.tmp.name, "Mieterselbstauskunft.pdf")
        auskunft.write_bytes(b"%PDF-1.4 Selbstauskunft")
        schufa = Path(self.tmp.name, "SCHUFA.pdf")
        schufa.write_bytes(b"%PDF-1.4 SCHUFA geheim")
        self.bot.tresor.hinzufuegen(auskunft, "Mieterselbstauskunft", erstkontakt=True)
        self.bot.tresor.hinzufuegen(schufa, "SCHUFA-Auskunft", erstkontakt=False)
        # Auf der Platte liegt nichts im Klartext
        for f in Path(self.tmp.name, "unterlagen").iterdir():
            self.assertNotIn(b"SCHUFA geheim", f.read_bytes())
            self.assertNotIn(b"Selbstauskunft", f.read_bytes())

        # 1. Prüfen: genau 2 Treffer (Tannenbusch 3 Zi, Auerberg 4 Zi geschätzt 950+270=1220 €)
        treffer = self.bot.pruefen()
        self.assertEqual(sorted(a.url.rsplit("/", 1)[-1] for a, _ in treffer), ["1", "2"])
        meldungen = self.tg.nachrichten()
        self.assertEqual(len(meldungen), 2)
        self.assertIn("Tannenbusch", meldungen[0]["text"])
        self.assertIn("1.050 € warm", meldungen[0]["text"])
        self.assertIn("1.220 € warm (geschätzt", meldungen[1]["text"])
        self.assertTrue(all(m["chat_id"] == CHAT for m in meldungen))

        # 2. Zweite Prüfung: nichts doppelt melden
        self.assertEqual(self.bot.pruefen(), [])
        self.assertEqual(len(self.tg.nachrichten()), 2)

        auerberg = next(a for a, _ in treffer if a.url.endswith("/2"))
        tannenbusch = next(a for a, _ in treffer if a.url.endswith("/1"))

        # 3. Auerberg: E-Mail steht in der Anzeige -> vorbereiten -> Senden-Knopf
        self.eingabe(klick(f"prep:{auerberg.id}"))
        vorb = self.tg.nachrichten()[-1]
        self.assertIn("Sehr geehrte Damen und Herren", vorb["text"])
        self.assertIn("4-Zimmer-Wohnung (90 m²) in Bonn-Auerberg", vorb["text"])
        self.assertIn("Max Mustermann", vorb["text"])
        knoepfe = [k["callback_data"] for reihe in vorb["reply_markup"]["inline_keyboard"] for k in reihe]
        self.assertIn(f"send:{auerberg.id}", knoepfe)
        self.assertEqual(self.smtp.mails, [])  # ohne Klick geht nichts raus

        # Fremder Chat darf nicht senden
        self.eingabe(klick(f"send:{auerberg.id}", chat=666))
        self.assertEqual(self.smtp.mails, [])

        self.eingabe(klick(f"send:{auerberg.id}"))
        self.assertEqual(len(self.smtp.mails), 1)
        an, mail = self.smtp.mails[0]
        self.assertEqual(an, ["vermietung@wohnen-auerberg.de"])
        self.assertIn("Familienwohnung", mail["Subject"])
        anhaenge = {t.get_filename(): t.get_payload(decode=True) for t in mail.walk() if t.get_filename()}
        self.assertEqual(anhaenge, {"Mieterselbstauskunft.pdf": b"%PDF-1.4 Selbstauskunft"})
        self.assertEqual(self.bot.speicher.hole(auerberg.id)["status"], "beworben")
        self.assertIn("gesendet (1 Anhänge)", self.tg.nachrichten()[-1]["text"])

        # Doppelklick auf Senden -> kein zweiter Versand
        self.eingabe(klick(f"send:{auerberg.id}"))
        self.assertEqual(len(self.smtp.mails), 1)

        # 4. Tannenbusch: keine E-Mail -> Hinweis Kontaktformular, kein Senden-Knopf
        self.eingabe(klick(f"prep:{tannenbusch.id}"))
        vorb = self.tg.nachrichten()[-1]
        self.assertIn("Keine E-Mail-Adresse", vorb["text"])
        knoepfe = [k["callback_data"] for reihe in vorb["reply_markup"]["inline_keyboard"] for k in reihe]
        self.assertNotIn(f"send:{tannenbusch.id}", knoepfe)
        vorb_id = self.bot.speicher.hole(tannenbusch.id)["tg_vorbereitung"]

        # Antwort mit E-Mail-Adresse auf die Vorbereitungsnachricht -> Senden-Knopf erscheint
        self.eingabe(text("hausverwaltung@example.de", antwort_auf=vorb_id))
        vorb = self.tg.nachrichten()[-1]
        knoepfe = [k["callback_data"] for reihe in vorb["reply_markup"]["inline_keyboard"] for k in reihe]
        self.assertIn(f"send:{tannenbusch.id}", knoepfe)
        self.eingabe(klick(f"send:{tannenbusch.id}"))
        self.assertEqual(self.smtp.mails[-1][0], ["hausverwaltung@example.de"])

        # 5. Übersicht
        self.eingabe(text("/liste"))
        self.assertIn("Nr. ", self.tg.nachrichten()[-1]["text"])
        self.eingabe(text("/status"))
        self.assertIn("Testgesellschaft: zuletzt 4 Angebote", self.tg.nachrichten()[-1]["text"])

    def test_ignorieren_und_selbst_beworben(self):
        treffer = self.bot.pruefen()
        a, b = treffer[0][0], treffer[1][0]
        self.eingabe(klick(f"ign:{a.id}"))
        self.assertEqual(self.bot.speicher.hole(a.id)["status"], "ignoriert")
        self.eingabe(klick(f"prep:{b.id}"))
        self.eingabe(klick(f"done:{b.id}"))
        self.assertEqual(self.bot.speicher.hole(b.id)["status"], "beworben")
        self.assertEqual(self.smtp.mails, [])

    def test_mail_befehl(self):
        treffer = self.bot.pruefen()
        a = next(x for x, _ in treffer if x.url.endswith("/1"))
        nr = self.bot.speicher.hole(a.id)["nr"]
        self.eingabe(text(f"/bewerben {nr}"))
        self.eingabe(text(f"/mail {nr} neu@example.de"))
        self.assertIn("neu@example.de", self.tg.nachrichten()[-1]["text"])

    def test_fremder_chat_bekommt_nur_chat_id(self):
        self.eingabe(text("/start", chat=777))
        letzte = self.tg.nachrichten()[-1]
        self.assertEqual(letzte["chat_id"], 777)
        self.assertIn("777", letzte["text"])
        self.eingabe(text("/liste", chat=777))
        self.assertEqual(len(self.tg.nachrichten()), 1)

    def test_kaputte_quelle_warnt_einmal_und_entwarnt(self):
        from wohnungsbot.quellen.web import HtmlQuelle
        kaputt = HtmlQuelle("Kaputt", self.web.url + "/gibtsnicht")
        self.bot.cfg = replace(self.cfg, quellen=[kaputt])
        for _ in range(5):
            self.bot.pruefen()
        warnungen = [m for m in self.tg.nachrichten() if "funktioniert seit" in m["text"]]
        self.assertEqual(len(warnungen), 1)
        kaputt.url = self.web.url + "/wohnungen"
        self.bot.pruefen()
        self.assertTrue(any("läuft wieder" in m["text"] for m in self.tg.nachrichten()))

    def test_schleife_mit_telegram_updates(self):
        """schritt(): prüft beim ersten Mal, holt dann Updates und verarbeitet /pruefen."""
        self.tg.updates = [{**text("/status"), "update_id": 5}]
        self.bot.schritt(poll_timeout=1)
        self.assertEqual(self.bot.speicher.meta("tg_offset"), "6")
        self.assertTrue(any("Status" in m["text"] for m in self.tg.nachrichten()))
        self.assertGreater(self.bot.naechste_pruefung, 0)
        self.tg.updates = [{**text("/pruefen"), "update_id": 6}]
        self.bot.schritt(poll_timeout=1)
        self.assertEqual(self.bot.naechste_pruefung, 0)


if __name__ == "__main__":
    unittest.main()
