"""Quellen aus dem Netz: normale Angebotsseiten (HTML) und RSS/Atom-Feeds."""

import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from ..angebot import Angebot
from .karten import adresszeile, karten_aus_html

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36 wohnungsbot")
TIMEOUT = 30


def hole_url(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"},
                     timeout=TIMEOUT)
    r.raise_for_status()
    return r


class HtmlQuelle:
    """Eine Seite mit einer Liste von Wohnungsangeboten (z. B. Wohnungsgesellschaft, Genossenschaft)."""

    def __init__(self, name, url):
        self.name = name
        self.url = url

    def hole(self):
        r = hole_url(self.url)
        # Ohne charset im Header rät requests Latin-1 (aus "€" wird Zeichensalat).
        # Dann die Rohdaten geben: BeautifulSoup liest <meta charset> bzw. erkennt UTF-8 selbst.
        html = r.text if "charset" in r.headers.get("Content-Type", "").lower() else r.content
        return [Angebot(quelle=self.name, url=k["url"], titel=k["titel"], text=k["text"],
                        adresse=k["adresse"])
                for k in karten_aus_html(html, r.url)]


def _lokal(tag):
    return tag.rsplit("}", 1)[-1]


def _kind(el, name):
    for c in el:
        if _lokal(c.tag) == name:
            return c
    return None


def _html_text(s):
    return BeautifulSoup(s or "", "lxml").get_text("\n", strip=True)


class RssQuelle:
    """RSS 2.0 oder Atom (manche Portale/Suchaufträge bieten einen Feed an)."""

    def __init__(self, name, url):
        self.name = name
        self.url = url

    def hole(self):
        root = ET.fromstring(hole_url(self.url).content)
        angebote = []
        for el in root.iter():
            art = _lokal(el.tag)
            if art not in ("item", "entry"):
                continue
            titel_el = _kind(el, "title")
            titel = (titel_el.text or "").strip() if titel_el is not None else ""
            link_el = _kind(el, "link")
            if link_el is None:
                continue
            link = (link_el.get("href") or link_el.text or "").strip()
            beschreibung = ""
            for feld in ("description", "summary", "content", "encoded"):
                f = _kind(el, feld)
                if f is not None and f.text:
                    beschreibung = _html_text(f.text)
                    break
            if link:
                angebote.append(Angebot(quelle=self.name, url=link, titel=titel, text=beschreibung,
                                        adresse=adresszeile(f"{titel}\n{beschreibung}")))
        return angebote
