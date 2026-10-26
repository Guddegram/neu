import threading
import unittest
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from wohnungsbot.quellen import email_alarm
from wohnungsbot.quellen.email_alarm import EmailQuelle, angebote_aus_mail
from wohnungsbot.quellen.karten import karten_aus_html
from wohnungsbot.quellen.web import HtmlQuelle, RssQuelle

# Aufbau wie typische Alarm-Mails: Tabellen, Logo-Link oben, je Anzeige Bild- und Titel-Link
# (Tracking-Links), unten Abmelde-/Impressum-Links.
ALARM_HTML = """<html><body><table width="600">
<tr><td><a href="https://www.immobilienscout24.de/"><img src="logo.png"></a></td></tr>
<tr><td><h1>3 neue Angebote für Ihren Suchauftrag „Bonn“</h1></td></tr>
<tr><td><table><tr>
  <td><a href="https://click.immobilienscout24.de/ls/click?upn=AAA111"><img src="1.jpg"></a></td>
  <td><a href="https://click.immobilienscout24.de/ls/click?upn=AAA111">Helle 3-Zimmer-Wohnung mit Balkon</a><br>
      Brieger Weg 14, 53119 Bonn, Tannenbusch<br>
      <b>1.050 €</b> Warmmiete &nbsp; <b>72 m²</b> Wohnfläche &nbsp; <b>3</b> Zi.</td>
</tr></table></td></tr>
<tr><td><table><tr>
  <td><a href="https://click.immobilienscout24.de/ls/click?upn=BBB222"><img src="2.jpg"></a></td>
  <td><a href="https://click.immobilienscout24.de/ls/click?upn=BBB222">Altbau-Charme nahe Uni</a><br>
      Kessenicher Str. 1, 53129 Bonn, Kessenich<br>
      <b>990 €</b> Kaltmiete &nbsp; <b>80 m²</b> Wohnfläche &nbsp; <b>3</b> Zi.</td>
</tr></table></td></tr>
<tr><td><table><tr>
  <td><a href="https://www.immobilienscout24.de/expose/155555555?referrer=mail">Familienwohnung, 4 Zimmer</a><br>
      53117 Bonn (Auerberg)<br>Kaltmiete 950 € · 90 m² · 4 Zimmer</td>
</tr></table></td></tr>
<tr><td><a href="https://www.immobilienscout24.de/suche/suchauftraege">Suchauftrag bearbeiten</a> |
  <a href="https://www.immobilienscout24.de/abmelden?x=1">Abmelden</a> |
  <a href="https://www.immobilienscout24.de/impressum">Impressum</a></td></tr>
</table></body></html>"""


def alarm_mail(html=ALARM_HTML, absender="ImmoScout24 <suchauftrag@mail.immobilienscout24.de>"):
    m = EmailMessage()
    m["From"] = absender
    m["To"] = "ich@example.de"
    m["Subject"] = "Neue Angebote"
    m.set_content("Bitte HTML-Ansicht verwenden.")
    m.add_alternative(html, subtype="html")
    return m.as_bytes()


class KartenTest(unittest.TestCase):
    def test_alarm_mail_karten(self):
        karten = karten_aus_html(ALARM_HTML)
        self.assertEqual(len(karten), 3, karten)
        self.assertEqual(karten[0]["url"], "https://click.immobilienscout24.de/ls/click?upn=AAA111")
        self.assertEqual(karten[0]["titel"], "Helle 3-Zimmer-Wohnung mit Balkon")
        self.assertIn("Tannenbusch", karten[0]["adresse"])
        self.assertIn("1.050 €", karten[0]["text"])
        self.assertIn("expose/155555555", karten[2]["url"])
        self.assertEqual(karten[2]["adresse"], "53117 Bonn (Auerberg)")

    def test_ganze_karte_als_link(self):
        html = """<ul>
          <li><a href="/wohnung/1"><h3>3 Zimmer in Dransdorf</h3><p>75 m² · 1.020 € warm</p></a></li>
          <li><a href="/wohnung/2"><h3>4 Zimmer in Buschdorf</h3><p>99 m² · 1.280 € warm</p></a></li>
        </ul><a href="/impressum">Impressum</a>"""
        karten = karten_aus_html(html, "https://wohnen.example.de/angebote/")
        self.assertEqual([k["url"] for k in karten],
                         ["https://wohnen.example.de/wohnung/1", "https://wohnen.example.de/wohnung/2"])
        self.assertEqual(karten[1]["titel"], "4 Zimmer in Buschdorf")

    def test_seite_ohne_angebote(self):
        self.assertEqual(karten_aus_html("<p>Derzeit keine freien Wohnungen.</p><a href='/x'>x</a>"), [])


class EmailTest(unittest.TestCase):
    def test_angebote_aus_mail_mit_aufloesung(self):
        aufgeloest = []

        def aufloeser(url):
            aufgeloest.append(url)
            return "https://www.immobilienscout24.de/expose/1" + url[-3:]

        angebote = angebote_aus_mail(alarm_mail(), aufloeser)
        self.assertEqual(len(angebote), 3)
        self.assertEqual(angebote[0].quelle, "ImmobilienScout24")
        self.assertEqual(angebote[0].url, "https://www.immobilienscout24.de/expose/1111")
        # direkter Exposé-Link wird nicht aufgelöst
        self.assertEqual(len(aufgeloest), 2)

    def test_text_mail(self):
        m = EmailMessage()
        m["From"] = "Kleinanzeigen <noreply@kleinanzeigen.de>"
        m.set_content("Neue Anzeige für Ihren Suchauftrag:\n\n"
                      "3 Zimmer Wohnung Endenich\n75 m², 1.000 € warm\n"
                      "https://www.kleinanzeigen.de/s-anzeige/3-zimmer/123-203-1166\n\n"
                      "Suchauftrag verwalten: https://www.kleinanzeigen.de/m-meine-suchauftraege.html\n")
        angebote = angebote_aus_mail(m.as_bytes())
        self.assertEqual(len(angebote), 1)
        self.assertEqual(angebote[0].quelle, "Kleinanzeigen")
        self.assertIn("s-anzeige/3-zimmer/123", angebote[0].url)

    def test_imap_ablauf(self):
        """Nur Portal-Mails werden gelesen und als gelesen markiert; fremde Mails bleiben unberührt."""
        privat = EmailMessage()
        privat["From"] = "Oma <oma@example.de>"
        privat.set_content("Hallo! 3 Zimmer, 70 m², 500 € – https://example.de/x")
        postfach = {b"1": alarm_mail(), b"2": privat.as_bytes()}
        markiert = []

        class FakeImap:
            def __init__(self, host, port):
                self.host = host

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def login(self, u, p):
                assert (u, p) == ("ich", "geheim")

            def select(self, ordner):
                return "OK", [b"2"]

            def search(self, charset, kriterium):
                assert kriterium == "UNSEEN"
                return "OK", [b"1 2"]

            def fetch(self, nr, teil):
                assert "PEEK" in teil
                return "OK", [(b"1 (BODY[] {123}", postfach[nr]), b")"]

            def store(self, nr, aktion, flag):
                markiert.append(nr)

        q = EmailQuelle("imap.example.de", "ich", "geheim", absender=["immobilienscout24"],
                        links_aufloesen=False, imap_klasse=FakeImap)
        angebote = q.hole()
        self.assertEqual(len(angebote), 3)
        self.assertEqual(markiert, [b"1"])

    def test_imap_login_fehler_verstaendlich(self):
        import imaplib

        class Abgelehnt:
            def __init__(self, host, port):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def login(self, u, p):
                raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")

        with self.assertRaisesRegex(RuntimeError, "imap.example.de.*App-Passwort"):
            EmailQuelle("imap.example.de", "ich", "falsch", imap_klasse=Abgelehnt).hole()

    def test_portalname(self):
        self.assertEqual(email_alarm.portal_name("noreply@immomio.de"), "Immomio (VEBOWAG/GWG)")
        self.assertEqual(email_alarm.portal_name("info@unbekannt.de"), "unbekannt.de")


class _Server:
    """Kleiner lokaler Webserver für HTML-/RSS-Tests."""

    def __init__(self, seiten):
        seiten_ref = seiten

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                inhalt = seiten_ref.get(self.path)
                if inhalt is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                daten = inhalt.encode()
                self.send_response(200)
                # absichtlich ohne charset – wie bei manchen echten Servern
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(daten)))
                self.end_headers()
                self.wfile.write(daten)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class WebTest(unittest.TestCase):
    def setUp(self):
        self.server = _Server({
            "/angebote": ("<div class='liste'><div class='objekt'><a href='/expose/7'>3-Zimmer in Castell</a>"
                          "<span>74,5 m²</span><span>Gesamtmiete 1.080,00 €</span></div></div>"),
            "/feed.rss": """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
                <item><title>4 Zimmer Auerberg</title><link>https://example.de/a/1</link>
                <description>&lt;p&gt;95 m², Warmmiete 1.250 €&lt;/p&gt;</description></item>
                </channel></rss>""",
            "/atom": """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
                <entry><title>3 Zi. Buschdorf</title><link href="https://example.de/b/2"/>
                <summary>70 m² 900 € kalt</summary></entry></feed>""",
        })

    def tearDown(self):
        self.server.stop()

    def test_html_quelle(self):
        angebote = HtmlQuelle("Test", self.server.url + "/angebote").hole()
        self.assertEqual(len(angebote), 1)
        a = angebote[0].ergaenze_aus_text()
        self.assertEqual(a.url, self.server.url + "/expose/7")
        self.assertEqual((a.warm, a.flaeche, a.zimmer), (1080, 74.5, 3))

    def test_html_quelle_fehler(self):
        with self.assertRaises(Exception):
            HtmlQuelle("Test", self.server.url + "/gibtsnicht").hole()

    def test_rss_und_atom(self):
        rss = RssQuelle("Feed", self.server.url + "/feed.rss").hole()
        self.assertEqual(len(rss), 1)
        a = rss[0].ergaenze_aus_text()
        self.assertEqual((a.titel, a.url, a.warm, a.flaeche), ("4 Zimmer Auerberg", "https://example.de/a/1", 1250, 95))
        atom = RssQuelle("Atom", self.server.url + "/atom").hole()
        self.assertEqual(atom[0].url, "https://example.de/b/2")
        self.assertEqual(atom[0].ergaenze_aus_text().kalt, 900)


if __name__ == "__main__":
    unittest.main()
