"""Ein Wohnungsangebot und die Prüfung gegen deine Suchkriterien."""

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from . import parse

# Tracking-Parameter, die dieselbe Anzeige unter verschiedenen Links erscheinen lassen
_TRACKING = re.compile(r"^(utm_|referrer|ref$|source$|campaign|mc_|fbclid|gclid|cmp|trk|tracking)", re.I)


def normalisiere_url(url):
    teile = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(teile.query) if not _TRACKING.match(k)]
    pfad = teile.path.rstrip("/") or "/"
    return urlunsplit((teile.scheme.lower() or "https", teile.netloc.lower(), pfad, urlencode(query), ""))


@dataclass
class Angebot:
    quelle: str
    url: str
    titel: str = ""
    text: str = ""       # alles, was über das Angebot bekannt ist (Karte, Beschreibung)
    adresse: str = ""    # Adresse/Ortsangabe, wenn die Quelle sie getrennt liefert
    warm: float | None = None
    kalt: float | None = None
    nk: float | None = None
    hk: float | None = None
    zimmer: float | None = None
    flaeche: float | None = None
    kontakt_email: str | None = None

    @property
    def id(self):
        return hashlib.sha1(normalisiere_url(self.url).encode()).hexdigest()[:16]

    def ergaenze_aus_text(self):
        """Fehlende Werte aus Titel + Text herauslesen."""
        gesamt = f"{self.titel}\n{self.adresse}\n{self.text}"
        m = parse.mieten(gesamt)
        for key in ("warm", "kalt", "nk", "hk"):
            if getattr(self, key) is None:
                setattr(self, key, m[key])
        if self.zimmer is None:
            self.zimmer = parse.zimmer(gesamt)
        if self.flaeche is None:
            self.flaeche = parse.flaeche(gesamt)
        if self.kontakt_email is None:
            mails = parse.emails(self.text)
            self.kontakt_email = mails[0] if mails else None
        return self

    def fingerabdruck(self):
        """Gleiche Wohnung auf zwei Portalen -> gleicher Fingerabdruck (grob)."""
        if self.flaeche is None or (self.kalt is None and self.warm is None):
            return None
        preis = self.kalt if self.kalt is not None else self.warm
        return f"{round(self.flaeche)}|{round(preis / 10)}|{self.zimmer or ''}"


@dataclass
class Preisgrenze:
    zimmer_min: float
    zimmer_max: float
    warm_max: float


@dataclass
class Kriterien:
    stadtteile: list
    min_flaeche: float = 65
    preisgrenzen: list = field(default_factory=list)
    ausschluss: list = field(default_factory=list)
    nk_pro_qm: float = 3.0  # Schätzung, wenn nur die Kaltmiete bekannt ist
    plz: dict = field(default_factory=dict)  # PLZ -> Beschreibung, nur als Notbehelf


@dataclass
class Ergebnis:
    passt: bool
    grund: str = ""
    stadtteil: str | None = None
    warm: float | None = None
    warm_art: str = "unbekannt"   # angegeben | berechnet | geschätzt | unbekannt
    grenze: float | None = None
    hinweise: list = field(default_factory=list)


def warmmiete(a, nk_pro_qm):
    if a.warm is not None:
        return a.warm, "angegeben"
    if a.kalt is not None and (a.nk is not None or a.hk is not None):
        return a.kalt + (a.nk or 0) + (a.hk or 0), "berechnet"
    if a.kalt is not None and a.flaeche is not None:
        return round(a.kalt + a.flaeche * nk_pro_qm, 2), "geschätzt"
    return None, "unbekannt"


def _stadtteil(a, k):
    # 1. Gesuchter Stadtteil in der Adresse
    if a.adresse:
        treffer = parse.finde_stadtteil(a.adresse, k.stadtteile)
        if treffer:
            return treffer, None
        # 2. Anderer Bonner Ortsteil in der Adresse -> sicher falsch
        anderer = parse.finde_stadtteil(a.adresse, parse.BONNER_ORTSTEILE)
        if anderer:
            return None, f"liegt in {anderer}"
    # 3. Gesuchter Stadtteil im Titel/Text
    treffer = parse.finde_stadtteil(f"{a.titel}\n{a.text}", k.stadtteile)
    if treffer:
        return treffer, None
    # 4. Notbehelf: Postleitzahl (53117 fast nur Zielviertel, 53119 teils Nordstadt)
    for plz in re.findall(r"\b(53\d{3})\b", f"{a.adresse}\n{a.titel}\n{a.text}"):
        if plz in k.plz:
            return f"PLZ {plz} ({k.plz[plz]})", "nur per PLZ erkannt – Lage prüfen"
    return None, "kein gesuchter Stadtteil erkennbar"


def pruefe(a, k):
    """Passt das Angebot zu den Kriterien? Fehlende Angaben -> durchlassen mit Hinweis
    (lieber eine Nachricht zu viel als die eine passende Wohnung verpassen)."""
    gesamt = f"{a.titel}\n{a.text}"
    # Nur im Titel: "Kein Wohnungstausch!" im Text soll ein Angebot nicht aussortieren.
    for wort in k.ausschluss:
        if parse.stadtteil_regex(wort).search(a.titel):
            return Ergebnis(False, f"Ausschlusswort „{wort}“ im Titel")

    stadtteil, grund = _stadtteil(a, k)
    if not stadtteil:
        return Ergebnis(False, grund)

    erg = Ergebnis(True, stadtteil=stadtteil)
    if grund:
        erg.hinweise.append(grund)

    if a.flaeche is None:
        erg.hinweise.append("Wohnfläche unbekannt")
    elif a.flaeche < k.min_flaeche:
        return Ergebnis(False, f"{a.flaeche:g} m² < {k.min_flaeche:g} m²", stadtteil)

    erg.warm, erg.warm_art = warmmiete(a, k.nk_pro_qm)

    if a.zimmer is None:
        erg.hinweise.append("Zimmerzahl unbekannt")
        erg.grenze = max((g.warm_max for g in k.preisgrenzen), default=None)
    else:
        passende = [g for g in k.preisgrenzen if g.zimmer_min <= a.zimmer <= g.zimmer_max]
        if not passende:
            return Ergebnis(False, f"{a.zimmer:g} Zimmer gesucht nicht", stadtteil)
        erg.grenze = max(g.warm_max for g in passende)

    if erg.warm is None:
        if a.kalt is not None and erg.grenze is not None and a.kalt > erg.grenze:
            return Ergebnis(False, f"schon kalt {a.kalt:g} € > {erg.grenze:g} €", stadtteil)
        erg.hinweise.append("Warmmiete unbekannt")
    elif erg.grenze is not None and erg.warm > erg.grenze:
        return Ergebnis(False, f"warm {erg.warm:g} € ({erg.warm_art}) > {erg.grenze:g} €", stadtteil)

    if re.search(r"\bWBS\b|Wohnberechtigungsschein", gesamt, re.I):
        erg.hinweise.append("WBS erforderlich?")
    return erg
