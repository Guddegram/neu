import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from wohnungsbot import anschreiben
from wohnungsbot.angebot import Angebot, Ergebnis
from wohnungsbot.speicher import Speicher
from wohnungsbot.unterlagen import Tresor, UnterlagenFehler


class AnschreibenTest(unittest.TestCase):
    def setUp(self):
        self.a = Angebot(quelle="ImmobilienScout24", url="https://x.de/1", titel="Helle Wohnung",
                         zimmer=3, flaeche=72.5)
        self.e = Ergebnis(True, stadtteil="Auerberg", warm=1050)

    def test_leere_angaben_fallen_weg(self):
        betreff, text = anschreiben.erstelle(self.a, self.e, {"name": "Max", "telefon": "0170 1"})
        self.assertEqual(betreff, "Anfrage zur Wohnung „Helle Wohnung“")
        self.assertIn("3-Zimmer-Wohnung (72,5 m²) in Bonn-Auerberg", text)
        self.assertNotIn("Ich arbeite als", text)   # beruf leer -> Zeile weg
        self.assertNotIn("{", text)
        self.assertIn("0170 1", text)
        self.assertTrue(text.rstrip().endswith("Max"))

    def test_beruf_ohne_arbeitgeber(self):
        _, text = anschreiben.erstelle(self.a, self.e, {"beruf": "Lehrerin"})
        self.assertIn("Ich arbeite als Lehrerin.", text)

    def test_anhaenge_satz(self):
        _, text = anschreiben.erstelle(self.a, self.e, {}, anhaenge_namen=["Selbstauskunft.pdf"])
        self.assertIn("Im Anhang finden Sie: Selbstauskunft.pdf", text)

    def test_eigene_vorlage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp, "v.txt")
            p.write_text("Betreff: Bewerbung {titel}\n\nHallo, {flaeche} m² in {ort} für {warmmiete}.\n{unbekannt}\n",
                         encoding="utf-8")
            betreff, text = anschreiben.erstelle(self.a, self.e, {}, str(p))
        self.assertEqual(betreff, "Bewerbung Helle Wohnung")
        self.assertIn("72,5 m² in Bonn-Auerberg für 1.050 €.", text)
        self.assertNotIn("unbekannt", text)


class TresorTest(unittest.TestCase):
    def test_falscher_schluessel(self):
        with tempfile.TemporaryDirectory() as tmp:
            sp = Speicher(str(Path(tmp, "db")))
            datei = Path(tmp, "a.pdf")
            datei.write_bytes(b"geheim")
            uid = Tresor(Path(tmp, "u"), Fernet.generate_key().decode(), sp).hinzufuegen(datei, erstkontakt=True)
            with self.assertRaises(UnterlagenFehler):
                Tresor(Path(tmp, "u"), Fernet.generate_key().decode(), sp).lesen(uid)
            with self.assertRaises(UnterlagenFehler):
                Tresor(Path(tmp, "u"), "kein-schluessel", sp)
            sp.db.close()


if __name__ == "__main__":
    unittest.main()
