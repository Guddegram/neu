"""Anschreiben aus deiner Vorlage + den Daten der Anzeige erzeugen."""

import re
import time
from pathlib import Path

STANDARD_VORLAGE = """Betreff: Anfrage zur Wohnung „{titel}“

Sehr geehrte Damen und Herren,

mit großem Interesse habe ich Ihr Angebot für die {zimmer_text} in {ort} gesehen und würde mich sehr über einen Besichtigungstermin freuen.

Kurz zu mir: {ueber_mich}
Ich arbeite als {beruf_text}.
Einziehen würden: {haushalt}.
Das monatliche Nettoeinkommen beträgt {einkommen}.
Einzug wäre ab {einzug} möglich.
{unterlagen_satz}

Sie erreichen mich jederzeit:
Telefon: {telefon}
E-Mail: {email}

Mit freundlichen Grüßen
{name}
"""

_PLATZHALTER = re.compile(r"\{(\w+)\}")


def _zahl(x):
    return f"{x:g}".replace(".", ",") if x is not None else ""


def _euro(x):
    return f"{x:,.0f} €".replace(",", ".") if x is not None else ""


def werte(angebot, ergebnis, bewerber, anhaenge_namen):
    ort = ergebnis.stadtteil or "Bonn"
    if ort.startswith("PLZ "):
        ort = "Bonn"
    elif not ort.startswith("Bonn"):
        ort = f"Bonn-{ort}"
    zimmer_text = (f"{_zahl(angebot.zimmer)}-Zimmer-Wohnung" if angebot.zimmer else "Wohnung")
    if angebot.flaeche:
        zimmer_text += f" ({_zahl(angebot.flaeche)} m²)"
    if anhaenge_namen:
        unterlagen_satz = (f"Im Anhang finden Sie: {', '.join(anhaenge_namen)}. Weitere Unterlagen "
                           "(z. B. SCHUFA-Auskunft, Einkommensnachweise) reiche ich gern nach.")
    else:
        unterlagen_satz = ("Mieterselbstauskunft, SCHUFA-Auskunft und Einkommensnachweise "
                           "reiche ich Ihnen gern nach.")
    w = {k: str(v).strip() for k, v in (bewerber or {}).items()}
    w["beruf_text"] = " bei ".join(x for x in (w.get("beruf"), w.get("arbeitgeber")) if x)
    w.update({
        "titel": angebot.titel.strip() or "Ihre Wohnung",
        "ort": ort,
        "stadtteil": ergebnis.stadtteil or "",
        "adresse": angebot.adresse,
        "zimmer": _zahl(angebot.zimmer),
        "zimmer_text": zimmer_text,
        "flaeche": _zahl(angebot.flaeche),
        "warmmiete": _euro(ergebnis.warm),
        "quelle": angebot.quelle,
        "url": angebot.url,
        "unterlagen_satz": unterlagen_satz,
        "datum": time.strftime("%d.%m.%Y"),
    })
    return w


def fuelle(vorlage, w):
    """Platzhalter ersetzen. Zeilen, deren Platzhalter alle leer sind, fallen weg –
    so muss man in der Vorlage nicht jede Angabe ausfüllen."""
    zeilen = []
    for zeile in vorlage.splitlines():
        namen = _PLATZHALTER.findall(zeile)
        if namen and all(not w.get(n) for n in namen):
            continue
        zeilen.append(_PLATZHALTER.sub(lambda m: w.get(m.group(1), ""), zeile))
    text = "\n".join(zeilen).strip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", text)


def erstelle(angebot, ergebnis, bewerber, vorlage_pfad=None, anhaenge_namen=()):
    """-> (betreff, text)"""
    vorlage = STANDARD_VORLAGE
    if vorlage_pfad and Path(vorlage_pfad).is_file():
        vorlage = Path(vorlage_pfad).read_text(encoding="utf-8")
    text = fuelle(vorlage, werte(angebot, ergebnis, bewerber, list(anhaenge_namen)))
    betreff = f"Anfrage zur Wohnung {angebot.titel}".strip()
    erste, _, rest = text.partition("\n")
    if erste.lower().startswith("betreff:"):
        betreff = erste.split(":", 1)[1].strip()
        text = rest.lstrip("\n")
    return betreff, text
