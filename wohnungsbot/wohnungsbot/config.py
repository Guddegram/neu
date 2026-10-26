"""Einstellungen: Suchkriterien aus config.toml, Geheimnisse (Passwörter, Tokens) aus .env."""

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .angebot import Kriterien, Preisgrenze
from .quellen.email_alarm import EmailQuelle
from .quellen.web import HtmlQuelle, RssQuelle


log = logging.getLogger(__name__)


class ConfigFehler(Exception):
    pass


def lade_env_datei(pfad=".env"):
    """Einfache .env-Unterstützung für den Start ohne Docker (Docker liest .env selbst)."""
    p = Path(pfad)
    if not p.is_file():
        return
    for zeile in p.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        k, v = zeile.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


def _env(name, standard=None):
    wert = os.environ.get(name, "").strip()
    return wert or standard


@dataclass
class Config:
    kriterien: Kriterien
    intervall_minuten: float = 30
    max_meldungen_pro_lauf: int = 15
    quellen: list = field(default_factory=list)
    bewerber: dict = field(default_factory=dict)
    vorlage: str | None = None
    daten_dir: str = "daten"
    telegram_token: str | None = None
    telegram_chat_id: int | None = None
    telegram_api: str = "https://api.telegram.org"
    smtp: dict | None = None
    unterlagen_schluessel: str | None = None


def lade(pfad):
    pfad = Path(pfad)
    if not pfad.is_file():
        raise ConfigFehler(f"Konfiguration nicht gefunden: {pfad} (Vorlage: config.example.toml)")
    try:
        roh = tomllib.loads(pfad.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigFehler(f"Fehler in {pfad}: {e}") from None

    s = roh.get("suche", {})
    grenzen = [Preisgrenze(float(g["zimmer_min"]), float(g["zimmer_max"]), float(g["warm_max"]))
               for g in s.get("preisgrenze", [])]
    if not grenzen:
        raise ConfigFehler("In [suche] fehlt mindestens eine [[suche.preisgrenze]].")
    if not s.get("stadtteile"):
        raise ConfigFehler("In [suche] fehlt die Liste 'stadtteile'.")
    kriterien = Kriterien(
        stadtteile=list(s["stadtteile"]),
        min_flaeche=float(s.get("min_flaeche", 0)),
        preisgrenzen=grenzen,
        ausschluss=list(s.get("ausschluss_im_titel", [])),
        nk_pro_qm=float(s.get("nebenkosten_pro_qm", 3.0)),
        plz={str(k): str(v) for k, v in s.get("plz_notbehelf", {}).items()},
    )

    quellen = []
    for q in roh.get("quelle", []):
        typ, name, url = q.get("typ"), q.get("name"), q.get("url")
        if not (typ and name and url):
            raise ConfigFehler(f"[[quelle]] braucht typ, name und url: {q}")
        if typ == "html":
            quellen.append(HtmlQuelle(name, url))
        elif typ == "rss":
            quellen.append(RssQuelle(name, url))
        else:
            raise ConfigFehler(f"Unbekannter Quellen-Typ {typ!r} (erlaubt: html, rss)")

    e = roh.get("email_suchauftraege", {})
    if e.get("aktiv"):
        host, benutzer, passwort = _env("IMAP_HOST"), _env("IMAP_BENUTZER"), _env("IMAP_PASSWORT")
        if not (host and benutzer and passwort):
            raise ConfigFehler("E-Mail-Suchaufträge aktiv, aber IMAP_HOST/IMAP_BENUTZER/IMAP_PASSWORT "
                               "fehlen in der .env")
        quellen.append(EmailQuelle(host, benutzer, passwort, ordner=e.get("ordner", "INBOX"),
                                   absender=e.get("absender", []),
                                   links_aufloesen=e.get("links_aufloesen", True),
                                   port=int(_env("IMAP_PORT", 993))))

    smtp = None
    if _env("SMTP_HOST") and not (_env("SMTP_BENUTZER") or _env("SMTP_ABSENDER")):
        log.warning("SMTP_HOST gesetzt, aber SMTP_BENUTZER leer: E-Mail-Versand bleibt aus.")
    elif _env("SMTP_HOST"):
        smtp = {"host": _env("SMTP_HOST"), "port": int(_env("SMTP_PORT", 587)),
                "benutzer": _env("SMTP_BENUTZER"), "passwort": _env("SMTP_PASSWORT"),
                "absender": _env("SMTP_ABSENDER") or _env("SMTP_BENUTZER"),
                "absender_name": roh.get("bewerber", {}).get("name", ""),
                "starttls": _env("SMTP_STARTTLS", "ja").lower() not in ("nein", "no", "0", "false")}

    chat = _env("TELEGRAM_CHAT_ID")
    try:
        chat_id = int(chat) if chat else None
    except ValueError:
        raise ConfigFehler("TELEGRAM_CHAT_ID muss eine Zahl sein") from None

    b = roh.get("bewerbung", {})
    vorlage = b.get("vorlage")
    if vorlage and not Path(vorlage).is_absolute():
        vorlage = str(pfad.parent / vorlage)

    return Config(
        kriterien=kriterien,
        intervall_minuten=float(s.get("intervall_minuten", 30)),
        max_meldungen_pro_lauf=int(s.get("max_meldungen_pro_lauf", 15)),
        quellen=quellen,
        bewerber=roh.get("bewerber", {}),
        vorlage=vorlage,
        daten_dir=_env("DATEN_DIR", "daten"),
        telegram_token=_env("TELEGRAM_TOKEN"),
        telegram_chat_id=chat_id,
        telegram_api=_env("TELEGRAM_API", "https://api.telegram.org"),
        smtp=smtp,
        unterlagen_schluessel=_env("UNTERLAGEN_SCHLUESSEL"),
    )
