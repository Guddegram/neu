import os
import unittest
from pathlib import Path
from unittest import mock

from wohnungsbot import parse
from wohnungsbot.angebot import Angebot, normalisiere_url, pruefe
from wohnungsbot.config import lade

BEISPIEL = Path(__file__).resolve().parents[1] / "config.example.toml"


def kriterien():
    with mock.patch.dict(os.environ, {"IMAP_HOST": "x", "IMAP_BENUTZER": "x", "IMAP_PASSWORT": "x"}):
        return lade(BEISPIEL).kriterien


def angebot(text, titel="Schöne Wohnung", adresse="", **kw):
    return Angebot(quelle="Test", url="https://example.org/1", titel=titel, text=text,
                   adresse=adresse, **kw).ergaenze_aus_text()


class ConfigTest(unittest.TestCase):
    def test_smtp_optional(self):
        env = {"IMAP_HOST": "x", "IMAP_BENUTZER": "x", "IMAP_PASSWORT": "x", "SMTP_HOST": "smtp.gmail.com"}
        with mock.patch.dict(os.environ, env):
            self.assertIsNone(lade(BEISPIEL).smtp)
        with mock.patch.dict(os.environ, {**env, "SMTP_BENUTZER": "ich@gmail.com", "SMTP_PASSWORT": "p"}):
            cfg = lade(BEISPIEL)
        self.assertEqual((cfg.smtp["absender"], cfg.smtp["port"]), ("ich@gmail.com", 587))
        self.assertEqual(len(cfg.quellen), 3)  # GWG, VEBOWAG, E-Mail

    def test_imap_pflicht_wenn_aktiv(self):
        from wohnungsbot.config import ConfigFehler
        with mock.patch.dict(os.environ, {"IMAP_HOST": "", "IMAP_BENUTZER": "", "IMAP_PASSWORT": ""}):
            with self.assertRaises(ConfigFehler):
                lade(BEISPIEL)


class ParseTest(unittest.TestCase):
    def test_zahlen(self):
        self.assertEqual(parse.zahl("1.100,50 €"), 1100.5)
        self.assertEqual(parse.zahl("950,-"), 950)
        self.assertEqual(parse.zahl("72.5"), 72.5)
        self.assertEqual(parse.zahl("1.100"), 1100)

    def test_mieten(self):
        self.assertEqual(parse.mieten("Warmmiete: 1.050 €")["warm"], 1050)
        m = parse.mieten("Kaltmiete 780,00 EUR, Nebenkosten 220 €, Heizkosten 90 €")
        self.assertEqual((m["kalt"], m["nk"], m["hk"]), (780, 220, 90))
        self.assertEqual(parse.mieten("1.100 € inkl. NK")["warm"], 1100)
        self.assertEqual(parse.mieten("950 € kalt")["kalt"], 950)
        # Kaution ist keine Miete
        self.assertEqual(parse.mieten("Kaution 2.400 € Miete 800 €")["kalt"], 800)
        # "Warmwasser" ist kein Warmmiete-Label
        self.assertIsNone(parse.mieten("Warmwasser inklusive, 700 €")["warm"])

    def test_zimmer_flaeche(self):
        self.assertEqual(parse.zimmer("3-Zimmer-Wohnung"), 3)
        self.assertEqual(parse.zimmer("3,5 Zi."), 3.5)
        self.assertEqual(parse.zimmer("Zimmer: 4"), 4)
        self.assertEqual(parse.flaeche("72,5 m²"), 72.5)
        self.assertEqual(parse.flaeche("Wohnfläche ca. 81 qm"), 81)

    def test_stadtteil_ganzes_wort(self):
        namen = ["Endenich", "Tannenbusch", "Neu-Tannenbusch"]
        self.assertIsNone(parse.finde_stadtteil("Endenicher Allee 5, 53115 Bonn", namen))
        self.assertEqual(parse.finde_stadtteil("Bonn-Endenich", namen), "Endenich")
        self.assertEqual(parse.finde_stadtteil("53119 Bonn (Neu Tannenbusch)", namen), "Neu-Tannenbusch")

    def test_url_ohne_tracking(self):
        self.assertEqual(normalisiere_url("https://WWW.x.de/expose/1/?utm_source=mail&id=5#top"),
                         "https://www.x.de/expose/1?id=5")


class FilterTest(unittest.TestCase):
    def setUp(self):
        self.k = kriterien()

    def test_drei_zimmer_unter_grenze(self):
        e = pruefe(angebot("3 Zimmer, 72 m², Warmmiete 1.050 €", adresse="53119 Bonn-Tannenbusch"), self.k)
        self.assertTrue(e.passt, e.grund)
        self.assertEqual((e.stadtteil, e.warm, e.warm_art, e.grenze), ("Tannenbusch", 1050, "angegeben", 1100))

    def test_drei_zimmer_zu_teuer(self):
        e = pruefe(angebot("3 Zimmer, 72 m², Warmmiete 1.150 €", adresse="Bonn-Auerberg"), self.k)
        self.assertFalse(e.passt)

    def test_vier_zimmer_hoehere_grenze(self):
        e = pruefe(angebot("4 Zimmer, 95 m², Warmmiete 1.290 €", adresse="Bonn-Dransdorf"), self.k)
        self.assertTrue(e.passt)
        self.assertEqual(e.grenze, 1300)

    def test_fuenfeinhalb_ja_sechs_nein(self):
        self.assertTrue(pruefe(angebot("5,5 Zimmer, 120 m², warm 1.250 €", adresse="Buschdorf"), self.k).passt)
        self.assertFalse(pruefe(angebot("6 Zimmer, 130 m², warm 1.250 €", adresse="Buschdorf"), self.k).passt)

    def test_zwei_zimmer_aussortiert(self):
        self.assertFalse(pruefe(angebot("2 Zimmer, 70 m², warm 800 €", adresse="Castell"), self.k).passt)

    def test_zu_klein(self):
        self.assertFalse(pruefe(angebot("3 Zimmer, 60 m², warm 800 €", adresse="Castell"), self.k).passt)

    def test_falscher_stadtteil_in_adresse_schlaegt_text(self):
        a = angebot("3 Zimmer, 70 m², warm 900 €. Nur 5 Minuten bis Endenich!",
                    adresse="53115 Bonn-Poppelsdorf")
        e = pruefe(a, self.k)
        self.assertFalse(e.passt)
        self.assertIn("Poppelsdorf", e.grund)

    def test_warmmiete_berechnet_und_geschaetzt(self):
        e = pruefe(angebot("3 Zimmer, 70 m², Kaltmiete 800 €, Nebenkosten 250 €", adresse="Graurheindorf"), self.k)
        self.assertEqual((e.warm, e.warm_art), (1050, "berechnet"))
        e = pruefe(angebot("3 Zimmer, 70 m², Kaltmiete 800 €", adresse="Graurheindorf"), self.k)
        self.assertEqual((e.warm, e.warm_art), (1010, "geschätzt"))  # 800 + 70 * 3,00
        self.assertTrue(e.passt)
        e = pruefe(angebot("3 Zimmer, 70 m², Kaltmiete 900 €", adresse="Graurheindorf"), self.k)
        self.assertFalse(e.passt)  # 900 + 210 = 1110 > 1100

    def test_fehlende_angaben_durchlassen_mit_hinweis(self):
        e = pruefe(angebot("Schöne Wohnung in Auerberg, Miete auf Anfrage"), self.k)
        self.assertTrue(e.passt)
        self.assertIn("Zimmerzahl unbekannt", e.hinweise)
        self.assertIn("Warmmiete unbekannt", e.hinweise)

    def test_tausch_im_titel(self):
        self.assertFalse(pruefe(angebot("3 Zimmer, 70 m², warm 900 €", titel="Tausche 3 Zimmer in Auerberg"),
                                self.k).passt)
        # "kein Tausch" im Text ist ok
        self.assertTrue(pruefe(angebot("3 Zimmer, 70 m², warm 900 €. Kein Wohnungstausch!",
                                       titel="3 Zimmer in Auerberg"), self.k).passt)

    def test_plz_notbehelf(self):
        e = pruefe(angebot("3 Zimmer, 70 m², warm 900 €", adresse="Musterweg 3, 53117 Bonn"), self.k)
        self.assertTrue(e.passt)
        self.assertTrue(any("PLZ" in h for h in e.hinweise))
        self.assertFalse(pruefe(angebot("3 Zimmer, 70 m², warm 900 €", adresse="Musterweg 3, 53115 Bonn"),
                                self.k).passt)

    def test_wbs_hinweis(self):
        e = pruefe(angebot("3 Zimmer, 70 m², warm 900 €, WBS erforderlich", adresse="Bonn-Tannenbusch"), self.k)
        self.assertTrue(e.passt)
        self.assertIn("WBS erforderlich?", e.hinweise)


if __name__ == "__main__":
    unittest.main()
