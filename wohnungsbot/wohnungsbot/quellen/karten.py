"""Angebots-"Karten" in beliebigem HTML finden (Webseite oder Alarm-E-Mail).

Idee: Jede Anzeige steht in einem Block, der einen Link, einen €-Betrag und eine
Fläche (m²) enthält. Für jeden Link wird der kleinste umgebende Block gesucht, der
beides enthält. Blöcke, die andere solche Blöcke enthalten (die ganze Liste, die
ganze Mail), werden verworfen. Dadurch braucht es keine seitenspezifischen
CSS-Selektoren – das übersteht auch kleine Layout-Änderungen der Anbieter.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_HAT_PREIS = re.compile(r"\d\s*(?:,-|,–)?\s*(?:€|EUR\b|Euro\b)", re.I)
_HAT_FLAECHE = re.compile(r"\d\s*(?:m²|m2\b|qm\b)", re.I)
_UNWICHTIG = re.compile(
    r"(?<![a-z0-9])(?:abmelden|unsubscribe|abbestellen|impressum|datenschutz|privacy|agb|login|"
    r"einloggen|registrieren|passwort|apps\.apple|play\.google|facebook|instagram|twitter|"
    r"linkedin|youtube|tiktok|newsletter|einstellungen|settings|hilfe|help|suchauftrag|"
    r"suchauftr%C3%A4ge|suchagent)(?![a-z0-9])",
    re.I)
_BEVORZUGT = re.compile(r"expose|expos%C3%A9|s-anzeige|/anzeige|wohnung|immobilie|objekt|angebot|detail", re.I)
_MAX_TIEFE = 15


def _text(node):
    t = node.get_text("\n", strip=True)
    t = re.sub(r"[ \t ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t)


def _ist_karte(text):
    return bool(_HAT_PREIS.search(text) and _HAT_FLAECHE.search(text))


def _titel(karte, link):
    lt = link.get_text(" ", strip=True)
    if len(lt) >= 12 and not _HAT_PREIS.search(lt):
        return lt
    for tag in ("h1", "h2", "h3", "h4", "h5", "strong", "b"):
        el = karte.find(tag)
        if el:
            t = el.get_text(" ", strip=True)
            if len(t) >= 8:
                return t
    for zeile in _text(karte).splitlines():
        if len(zeile) >= 8:
            return zeile
    return lt or "Wohnungsangebot"


def adresszeile(text):
    """Zeile mit '53xxx Bonn' oder 'Bonn-...' / 'Bonn (...)' – die eigentliche Ortsangabe."""
    for zeile in text.splitlines():
        if re.search(r"\b53\d{3}\b|\bBonn\b", zeile) and len(zeile) <= 160:
            return zeile.strip()
    return ""


def karten_aus_html(html, basis_url=""):
    """Liefert Liste von dicts: url, titel, text, adresse."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()

    kandidaten = {}  # id(karte) -> (karte, [links])
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(basis_url, href)
        if not url.startswith("http"):
            continue
        # Nur Adresse ohne Query prüfen: Tracking-Tokens enthalten zufällige Buchstaben
        if _UNWICHTIG.search(url.split("?")[0]) or _UNWICHTIG.search(a.get_text(" ", strip=True)):
            continue
        knoten = a
        for _ in range(_MAX_TIEFE):
            if _ist_karte(_text(knoten)):
                eintrag = kandidaten.setdefault(id(knoten), (knoten, []))
                eintrag[1].append((url, a))
                break
            if knoten.parent is None:
                break
            knoten = knoten.parent

    # Blöcke verwerfen, die andere Kandidaten-Blöcke enthalten (Liste/Mail als Ganzes)
    knoten_ids = set(kandidaten)
    karten = []
    for kid, (knoten, links) in kandidaten.items():
        enthaelt_andere = any(id(n) in knoten_ids for n in knoten.find_all(True))
        if enthaelt_andere:
            continue
        url, link = next(((u, l) for u, l in links if _BEVORZUGT.search(u)), links[0])
        text = _text(knoten)
        karten.append({"url": url, "titel": _titel(knoten, link), "text": text,
                       "adresse": adresszeile(text)})

    # Reihenfolge wie im Dokument, gleiche URL nur einmal
    gesehen, ergebnis = set(), []
    for k in karten:
        if k["url"] not in gesehen:
            gesehen.add(k["url"])
            ergebnis.append(k)
    return ergebnis


def text_zu_html(text):
    """Reine Text-Mail -> einfaches HTML (ein Block je Absatz), damit derselbe Erkenner greift."""
    from html import escape
    bloecke = re.split(r"\n\s*\n", text)
    teile = []
    for block in bloecke:
        b = escape(block)
        b = re.sub(r"(https?://[^\s<>\"']+)", r'<a href="\1">\1</a>', b)
        teile.append("<div>" + b.replace("\n", "<br>") + "</div>")
    return "<html><body>" + "".join(teile) + "</body></html>"
