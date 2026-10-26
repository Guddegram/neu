"""SQLite-Datenbank: welche Angebote schon bekannt sind, Status der Bewerbungen, Quellen-Gesundheit."""

import json
import sqlite3
import time
from dataclasses import asdict

from .angebot import Angebot, Ergebnis

SCHEMA = """
CREATE TABLE IF NOT EXISTS angebote (
    nr INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE NOT NULL,
    quelle TEXT, url TEXT, titel TEXT,
    daten TEXT NOT NULL,          -- Angebot als JSON
    ergebnis TEXT,                -- Prüfergebnis als JSON
    passt INTEGER NOT NULL,
    grund TEXT,
    fingerabdruck TEXT,
    status TEXT NOT NULL,         -- abgelehnt | doppelt | gemeldet | vorbereitet | beworben | ignoriert
    kontakt_email TEXT,
    anschreiben TEXT,
    betreff TEXT,
    tg_nachricht INTEGER,         -- Telegram-Nachricht mit dem Angebot
    tg_vorbereitung INTEGER,      -- Telegram-Nachricht mit dem Anschreiben
    erstmals INTEGER NOT NULL,
    geaendert INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fp ON angebote(fingerabdruck);
CREATE TABLE IF NOT EXISTS quellen (
    name TEXT PRIMARY KEY,
    fehler_in_folge INTEGER NOT NULL DEFAULT 0,
    letzter_fehler TEXT,
    gewarnt INTEGER NOT NULL DEFAULT 0,
    letzter_erfolg INTEGER,
    letzte_anzahl INTEGER
);
CREATE TABLE IF NOT EXISTS unterlagen (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    dateiname TEXT NOT NULL,
    erstkontakt INTEGER NOT NULL,
    hinzugefuegt INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (schluessel TEXT PRIMARY KEY, wert TEXT);
"""


class Speicher:
    def __init__(self, pfad):
        self.db = sqlite3.connect(pfad)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ---- Angebote ----------------------------------------------------
    def bekannt(self, angebot_id):
        return self.db.execute("SELECT 1 FROM angebote WHERE id=?", (angebot_id,)).fetchone() is not None

    def fingerabdruck_gemeldet(self, fp, tage=14):
        if not fp:
            return False
        grenze = int(time.time()) - tage * 86400
        return self.db.execute(
            "SELECT 1 FROM angebote WHERE fingerabdruck=? AND passt=1 AND erstmals>=?",
            (fp, grenze)).fetchone() is not None

    def speichere(self, a: Angebot, erg: Ergebnis, status):
        jetzt = int(time.time())
        cur = self.db.execute(
            """INSERT OR IGNORE INTO angebote (id, quelle, url, titel, daten, ergebnis, passt, grund,
               fingerabdruck, status, kontakt_email, erstmals, geaendert)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a.id, a.quelle, a.url, a.titel, json.dumps(asdict(a), ensure_ascii=False),
             json.dumps(asdict(erg), ensure_ascii=False), int(erg.passt), erg.grund,
             a.fingerabdruck(), status, a.kontakt_email, jetzt, jetzt))
        self.db.commit()
        return cur.lastrowid

    def hole(self, angebot_id):
        return self.db.execute("SELECT * FROM angebote WHERE id=?", (angebot_id,)).fetchone()

    def hole_nr(self, nr):
        return self.db.execute("SELECT * FROM angebote WHERE nr=?", (nr,)).fetchone()

    def nach_vorbereitungsnachricht(self, msg_id):
        return self.db.execute("SELECT * FROM angebote WHERE tg_vorbereitung=?", (msg_id,)).fetchone()

    def setze(self, angebot_id, **felder):
        felder["geaendert"] = int(time.time())
        spalten = ", ".join(f"{k}=?" for k in felder)
        self.db.execute(f"UPDATE angebote SET {spalten} WHERE id=?", (*felder.values(), angebot_id))
        self.db.commit()

    def letzte_treffer(self, anzahl=10):
        return self.db.execute(
            "SELECT * FROM angebote WHERE passt=1 AND status!='doppelt' ORDER BY nr DESC LIMIT ?",
            (anzahl,)).fetchall()

    def zaehle(self):
        rows = self.db.execute("SELECT status, COUNT(*) n FROM angebote GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    @staticmethod
    def angebot_aus(row):
        return Angebot(**json.loads(row["daten"]))

    @staticmethod
    def ergebnis_aus(row):
        return Ergebnis(**json.loads(row["ergebnis"]))

    # ---- Quellen-Gesundheit -------------------------------------------
    def quelle_ok(self, name, anzahl):
        """Gibt True zurück, wenn vorher gewarnt wurde (-> Entwarnung schicken)."""
        row = self.db.execute("SELECT gewarnt FROM quellen WHERE name=?", (name,)).fetchone()
        war_gewarnt = bool(row and row["gewarnt"])
        self.db.execute(
            """INSERT INTO quellen (name, fehler_in_folge, gewarnt, letzter_erfolg, letzte_anzahl)
               VALUES (?,0,0,?,?) ON CONFLICT(name) DO UPDATE SET fehler_in_folge=0, gewarnt=0,
               letzter_erfolg=excluded.letzter_erfolg, letzte_anzahl=excluded.letzte_anzahl""",
            (name, int(time.time()), anzahl))
        self.db.commit()
        return war_gewarnt

    def quelle_fehler(self, name, fehler, warnen_ab=3):
        """Gibt True zurück, wenn jetzt (einmalig) gewarnt werden soll."""
        self.db.execute(
            """INSERT INTO quellen (name, fehler_in_folge, letzter_fehler) VALUES (?,1,?)
               ON CONFLICT(name) DO UPDATE SET fehler_in_folge=fehler_in_folge+1,
               letzter_fehler=excluded.letzter_fehler""", (name, fehler))
        row = self.db.execute("SELECT fehler_in_folge, gewarnt FROM quellen WHERE name=?", (name,)).fetchone()
        warnen = row["fehler_in_folge"] >= warnen_ab and not row["gewarnt"]
        if warnen:
            self.db.execute("UPDATE quellen SET gewarnt=1 WHERE name=?", (name,))
        self.db.commit()
        return warnen

    def quellen(self):
        return self.db.execute("SELECT * FROM quellen ORDER BY name").fetchall()

    # ---- Unterlagen ---------------------------------------------------
    def unterlage_neu(self, uid, name, dateiname, erstkontakt):
        self.db.execute("INSERT INTO unterlagen VALUES (?,?,?,?,?)",
                        (uid, name, dateiname, int(erstkontakt), int(time.time())))
        self.db.commit()

    def unterlagen(self, nur_erstkontakt=False):
        sql = "SELECT * FROM unterlagen" + (" WHERE erstkontakt=1" if nur_erstkontakt else "")
        return self.db.execute(sql + " ORDER BY hinzugefuegt").fetchall()

    def unterlage_loeschen(self, uid):
        cur = self.db.execute("DELETE FROM unterlagen WHERE id=?", (uid,))
        self.db.commit()
        return cur.rowcount > 0

    # ---- Meta ---------------------------------------------------------
    def meta(self, schluessel, standard=None):
        row = self.db.execute("SELECT wert FROM meta WHERE schluessel=?", (schluessel,)).fetchone()
        return row["wert"] if row else standard

    def setze_meta(self, schluessel, wert):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (schluessel, str(wert)))
        self.db.commit()
