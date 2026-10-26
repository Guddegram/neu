"""Suchauftrags-E-Mails der Portale (ImmobilienScout24, immowelt, Kleinanzeigen, ...) per IMAP lesen.

Das ist der saubere Weg für die großen Portale: Sie verbieten automatisches Auslesen
ihrer Seiten, schicken dir aber auf Wunsch jede neue passende Anzeige per E-Mail.
Der Bot liest diese Mails aus einem eigenen Postfach und filtert sie mit deinen Kriterien.
"""

import email
import imaplib
import logging
import re
from email.header import decode_header, make_header
from email.utils import parseaddr

import requests

from ..angebot import Angebot
from .karten import karten_aus_html, text_zu_html
from .web import USER_AGENT

log = logging.getLogger(__name__)

PORTALE = {
    "immobilienscout24": "ImmobilienScout24",
    "immowelt": "immowelt",
    "immonet": "immonet",
    "kleinanzeigen": "Kleinanzeigen",
    "vonovia": "Vonovia",
    "wg-gesucht": "WG-Gesucht",
    "immomio": "Immomio (VEBOWAG/GWG)",
    "vebowag": "VEBOWAG",
    "gwg-bonn": "GWG Bonn",
    "vivawest": "Vivawest",
    "leg-wohnen": "LEG",
    "bundesimmobilien": "BImA",
}

# Direkte Anzeigen-Links: brauchen keine Auflösung
_DIREKT = re.compile(
    r"immobilienscout24\.de/expose/\d+|immowelt\.de/(?:expose|projekte/expose)/|"
    r"kleinanzeigen\.de/s-anzeige/|vonovia\.de/.+/immobilien/|wg-gesucht\.de/.+\.\d+\.html",
    re.I)


def _header(wert):
    try:
        return str(make_header(decode_header(wert or "")))
    except Exception:
        return wert or ""


def portal_name(absender, urls=()):
    quelle = " ".join([absender, *urls]).lower()
    for schluessel, name in PORTALE.items():
        if schluessel in quelle:
            return name
    domain = parseaddr(absender)[1].split("@")[-1]
    return domain or "E-Mail"


def _inhalt(msg):
    html, text = None, None
    for teil in msg.walk():
        if teil.get_content_maintype() == "multipart" or teil.get_filename():
            continue
        art = teil.get_content_type()
        try:
            daten = teil.get_payload(decode=True)
            if daten is None:
                continue
            inhalt = daten.decode(teil.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        if art == "text/html" and html is None:
            html = inhalt
        elif art == "text/plain" and text is None:
            text = inhalt
    return html, text


def angebote_aus_mail(roh, link_aufloeser=None):
    """Eine komplette E-Mail (bytes) -> Liste von Angeboten."""
    msg = email.message_from_bytes(roh)
    absender = _header(msg.get("From"))
    html, text = _inhalt(msg)
    if html is None and text is None:
        return []
    karten = karten_aus_html(html if html is not None else text_zu_html(text))
    portal = portal_name(absender, [k["url"] for k in karten])
    angebote = []
    for k in karten:
        url = k["url"]
        if link_aufloeser and not _DIREKT.search(url):
            url = link_aufloeser(url)
        angebote.append(Angebot(quelle=portal, url=url, titel=k["titel"], text=k["text"],
                                adresse=k["adresse"]))
    return angebote


def loese_link_auf(url):
    """Tracking-Link aus der Mail (click.xyz...) -> echte Anzeigen-URL. Bei Fehler: Original."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=15, headers={"User-Agent": USER_AGENT})
        if r.url and r.url.startswith("http"):
            return r.url
    except requests.RequestException as e:
        log.info("Link nicht auflösbar (%s): %s", e.__class__.__name__, url[:80])
    return url


class EmailQuelle:
    name = "E-Mail-Suchaufträge"

    def __init__(self, host, benutzer, passwort, ordner="INBOX", absender=(), links_aufloesen=True,
                 port=993, imap_klasse=imaplib.IMAP4_SSL):
        self.host, self.port = host, port
        self.benutzer, self.passwort = benutzer, passwort
        self.ordner = ordner
        self.absender = [a.lower() for a in absender]
        self.links_aufloesen = links_aufloesen
        self.imap_klasse = imap_klasse

    def _von_portal(self, roh):
        if not self.absender:
            return True
        kopf = email.message_from_bytes(roh, _class=email.message.Message)
        von = _header(kopf.get("From")).lower()
        return any(a in von for a in self.absender)

    def hole(self):
        try:
            return self._hole()
        except imaplib.IMAP4.error as e:
            raise RuntimeError(f"IMAP {self.host}: {e} – Benutzer/App-Passwort prüfen") from None
        except OSError as e:
            raise RuntimeError(f"IMAP {self.host}:{self.port} nicht erreichbar ({e})") from None

    def _hole(self):
        angebote = []
        with self.imap_klasse(self.host, self.port) as imap:
            imap.login(self.benutzer, self.passwort)
            status, _ = imap.select(f'"{self.ordner}"')
            if status != "OK":
                raise RuntimeError(f"IMAP-Ordner {self.ordner!r} nicht gefunden")
            status, daten = imap.search(None, "UNSEEN")
            if status != "OK":
                raise RuntimeError("IMAP-Suche fehlgeschlagen")
            for nummer in daten[0].split():
                status, teile = imap.fetch(nummer, "(BODY.PEEK[])")
                if status != "OK" or not teile or not isinstance(teile[0], tuple):
                    continue
                roh = teile[0][1]
                if not self._von_portal(roh):
                    continue  # fremde Mails ungelesen lassen
                aufloeser = loese_link_auf if self.links_aufloesen else None
                angebote.extend(angebote_aus_mail(roh, aufloeser))
                imap.store(nummer, "+FLAGS", "\\Seen")
        return angebote
