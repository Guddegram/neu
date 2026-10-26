"""Bewerbungsunterlagen verschlüsselt ablegen (Fernet = AES-128 + HMAC aus `cryptography`).

Auf dem Server liegen nur verschlüsselte Dateien. Der Schlüssel steht in der
Umgebungsvariable UNTERLAGEN_SCHLUESSEL (.env) – ohne ihn sind die Dateien wertlos.
"""

import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class UnterlagenFehler(Exception):
    pass


def neuer_schluessel():
    return Fernet.generate_key().decode()


class Tresor:
    def __init__(self, ordner, schluessel, speicher):
        if not schluessel:
            raise UnterlagenFehler(
                "UNTERLAGEN_SCHLUESSEL fehlt. Erzeugen mit: python -m wohnungsbot schluessel")
        try:
            self.fernet = Fernet(schluessel.encode() if isinstance(schluessel, str) else schluessel)
        except (ValueError, TypeError):
            raise UnterlagenFehler("UNTERLAGEN_SCHLUESSEL ist ungültig (kein Fernet-Schlüssel).")
        self.ordner = Path(ordner)
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.speicher = speicher

    def hinzufuegen(self, datei, name=None, erstkontakt=False):
        datei = Path(datei)
        if not datei.is_file():
            raise UnterlagenFehler(f"Datei nicht gefunden: {datei}")
        uid = uuid.uuid4().hex[:12]
        (self.ordner / f"{uid}.enc").write_bytes(self.fernet.encrypt(datei.read_bytes()))
        self.speicher.unterlage_neu(uid, name or datei.stem, datei.name, erstkontakt)
        return uid

    def lesen(self, uid):
        try:
            return self.fernet.decrypt((self.ordner / f"{uid}.enc").read_bytes())
        except FileNotFoundError:
            raise UnterlagenFehler(f"Verschlüsselte Datei {uid} fehlt")
        except InvalidToken:
            raise UnterlagenFehler("Entschlüsseln fehlgeschlagen – falscher UNTERLAGEN_SCHLUESSEL?")

    def entfernen(self, uid):
        (self.ordner / f"{uid}.enc").unlink(missing_ok=True)
        return self.speicher.unterlage_loeschen(uid)

    def anhaenge_erstkontakt(self):
        """Nur Unterlagen, die für den Erstkontakt freigegeben sind – SCHUFA, Gehalt und
        Ausweis gehören da normalerweise NICHT dazu (erst nach der Besichtigung)."""
        return [(row["dateiname"], self.lesen(row["id"]))
                for row in self.speicher.unterlagen(nur_erstkontakt=True)]
