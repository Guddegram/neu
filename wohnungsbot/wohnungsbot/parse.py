"""Zahlen, Mieten, Zimmer, Fläche und Stadtteile aus deutschen Anzeigentexten lesen."""

import re

# Bonner Ortsteile, die NICHT gesucht werden. Steht einer davon in der Adresse,
# wird das Angebot verworfen – auch wenn im Beschreibungstext "Nähe Endenich" steht.
BONNER_ORTSTEILE = [
    "Zentrum", "Nordstadt", "Südstadt", "Weststadt", "Gronau", "Dottendorf", "Ippendorf",
    "Kessenich", "Lessenich", "Meßdorf", "Messdorf", "Poppelsdorf", "Röttgen", "Ückesdorf",
    "Venusberg", "Duisdorf", "Hardtberg", "Brüser Berg", "Lengsdorf", "Medinghoven",
    "Beuel", "Geislar", "Hoholz", "Holtorf", "Holzlar", "Küdinghoven", "Limperich",
    "Oberkassel", "Pützchen", "Bechlinghoven", "Ramersdorf", "Schwarzrheindorf",
    "Vilich", "Vilich-Müldorf", "Ennert", "Bad Godesberg", "Godesberg", "Friesdorf",
    "Heiderhof", "Hochkreuz", "Lannesdorf", "Mehlem", "Muffendorf", "Pennenfeld",
    "Plittersdorf", "Rüngsdorf", "Schweinheim",
]

_ZAHL = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"


def zahl(text):
    """'1.100,50' -> 1100.5, '950,-' -> 950.0, '72.5' -> 72.5, sonst None."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = re.search(_ZAHL, str(text).replace(" ", " "))
    if not m:
        return None
    s = m.group(0)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):  # 1.100 oder 1.100,50
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _norm(text):
    text = (text or "").replace(" ", " ").replace(" ", " ")
    text = text.replace("m^2", "m²").replace("m 2", "m²")
    return re.sub(r"[ \t]+", " ", text)


_EURO = r"(?:€|EUR|Euro)"
_BETRAG = rf"({_ZAHL})\s*(?:,-|,–)?\s*{_EURO}"

# Reihenfolge wichtig: "Nettokaltmiete" vor "kalt", "Gesamtmiete" vor "Miete".
_LABELS = {
    "warm": r"warmmiete|gesamtmiete|miete\s*warm|monatliche\s+gesamtkosten|warm|inkl\.?\s*(?:nk|nebenkosten)",
    "kalt": r"nettokaltmiete|kaltmiete|grundmiete|nettomiete|miete\s*kalt|kalt",
    "nk": r"nebenkosten|betriebskosten|nk(?:-vorauszahlung)?",
    "hk": r"heizkosten|hk",
}


def _label_betrag(text, label_re):
    # "Warmmiete: 1.050 €" / "Warmmiete 1.050,00 EUR"
    m = re.search(rf"(?<![\wÄÖÜäöüß])(?:{label_re})\b\s*[:\-]?\s*(?:ca\.?\s*)?{_BETRAG}", text, re.I)
    if m:
        return zahl(m.group(1))
    # "1.050 € warm" / "1.050 € Warmmiete"
    m = re.search(rf"{_BETRAG}\s*\(?\s*(?:{label_re})\b", text, re.I)
    if m:
        return zahl(m.group(1))
    return None


def mieten(text):
    """Liefert dict mit warm/kalt/nk/hk (jeweils float oder None)."""
    text = _norm(text)
    werte = {key: _label_betrag(text, rx) for key, rx in _LABELS.items()}
    # Wörter wie "warm" können auch in "Warmwasser" stecken: \b verhindert das.
    if werte["kalt"] is None and werte["warm"] is None:
        # Unbeschriftete Miete: Portale zeigen fast immer die Kaltmiete.
        # Als kalt behandeln = vorsichtig (die Warmmiete wird dann eher zu hoch geschätzt).
        ohne_nebenposten = re.sub(
            rf"(?:Kaution|Provision|Stellplatz|Garage|Kaufpreis|Genossenschaftsanteile?)\s*[:\-]?\s*(?:ca\.?\s*)?{_BETRAG}",
            " ", text, flags=re.I)
        betraege = [zahl(b) for b in re.findall(_BETRAG, ohne_nebenposten)]
        betraege = [b for b in betraege if b and 150 <= b <= 5000
                    and b not in (werte["nk"], werte["hk"])]
        if betraege:
            werte["kalt"] = betraege[0]
    return werte


def zimmer(text):
    text = _norm(text)
    m = re.search(rf"({_ZAHL})\s*(?:-\s*)?(?:Zimmer|Zi\b|Zi\.|Räume|Raum)", text, re.I)
    if not m:
        m = re.search(rf"Zimmer(?:anzahl)?\s*[:\-]?\s*({_ZAHL})", text, re.I)
    if m:
        wert = zahl(m.group(1))
        if wert is not None and 0 < wert <= 15:
            return wert
    return None


def flaeche(text):
    text = _norm(text)
    m = re.search(rf"({_ZAHL})\s*(?:m²|m2|qm|Quadratmeter)", text, re.I)
    if not m:
        m = re.search(rf"(?:Wohnfläche|Fläche)\s*(?:ca\.?)?\s*[:\-]?\s*(?:ca\.?\s*)?({_ZAHL})", text, re.I)
    if m:
        wert = zahl(m.group(1))
        if wert is not None and 10 <= wert <= 1000:
            return wert
    return None


def emails(text):
    found = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text or "")
    out = []
    for e in found:
        e = e.strip(".")
        if e.lower() not in (x.lower() for x in out) and not re.search(r"noreply|no-reply|donotreply", e, re.I):
            out.append(e)
    return out


def stadtteil_regex(name):
    """Passt auf 'Endenich' und 'Bonn-Endenich', aber NICHT auf 'Endenicher Allee'."""
    teile = [re.escape(t) for t in re.split(r"[\s\-]+", name.strip())]
    return re.compile(r"(?<![\wÄÖÜäöüß])" + r"[\s\-]*".join(teile) + r"(?![\wÄÖÜäöüß])", re.I)


def finde_stadtteil(text, namen):
    """Erster Name aus `namen`, der im Text als eigenes Wort vorkommt, sonst None."""
    text = _norm(text)
    for name in sorted(namen, key=len, reverse=True):  # "Neu-Tannenbusch" vor "Tannenbusch"
        if stadtteil_regex(name).search(text):
            return name
    return None
