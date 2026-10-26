# 🏠 Wohnungsbot Bonn

Sucht rund um die Uhr nach Wohnungen in deinen Bonner Vierteln, meldet passende Angebote
sofort per **Telegram** und bereitet auf Knopfdruck die **Bewerbung** vor. Verschickt wird
erst, wenn du in Telegram auf **„✅ Senden“** drückst (Version B).

```
Portale (Suchauftrags-Mails) ─┐
Wohnungsgesellschaften (Web) ─┼─► Bot (alle 30 Min) ─► Filter ─► 📱 Telegram
RSS-Feeds ────────────────────┘                                    │
                                     📝 Bewerbung vorbereiten ◄────┘
                                     ✅ Senden (nach deiner Freigabe) ─► E-Mail an Vermieter
```

## Deine Suchkriterien (stehen in `config.toml`)

| | |
|---|---|
| Stadtteile | Neu-/Alt-Tannenbusch, Auerberg, Endenich, Castell, Graurheindorf, Dransdorf, Buschdorf |
| 3 (bis 3,5) Zimmer | max. **1.100 € warm** |
| 4 bis 5,5 Zimmer | max. **1.300 € warm** |
| Wohnfläche | ab **65 m²** |
| Prüfintervall | alle **30 Minuten** |

So entscheidet der Filter:
- **Stadtteil**: Ganzes Wort, „Endenich“ zählt, „Endenicher Allee“ (Poppelsdorf) dagegen nicht.
  Steht in der Adresse ein *anderer* Bonner Ortsteil (z. B. „53115 Bonn-Poppelsdorf“), wird
  die Anzeige aussortiert, auch wenn im Text „Nähe Endenich“ steht. Nennt eine Anzeige nur
  die PLZ, gelten 53117 und 53119 als Notbehelf, mit dem Hinweis „Lage prüfen“.
- **Warmmiete**: Steht sie in der Anzeige, gilt sie. Sonst rechnet der Bot Kaltmiete +
  Nebenkosten (+ Heizkosten). Ist nur die Kaltmiete bekannt, **schätzt** er
  Kaltmiete + 3,00 €/m², und die Meldung zeigt „geschätzt“ an.
- **Fehlende Angaben** (z. B. keine Zimmerzahl): Die Anzeige wird trotzdem gemeldet, mit ⚠️-Hinweis.
  Lieber eine Nachricht zu viel, als die eine passende Wohnung zu verpassen.
- **Aussortiert** wird alles mit „Tausch“, „Zwischenmiete“ oder „Untermiete“ im Titel.
  „WBS erforderlich“ wird nur markiert, nicht aussortiert.
- **Doppelt**: Erscheint dieselbe Wohnung auf zwei Portalen (gleiche Fläche, ähnlicher Preis),
  kommt nur eine Meldung.

## Woher kommen die Wohnungen? (ehrlich)

| Quelle | Wie | Warum so |
|---|---|---|
| **ImmobilienScout24, immowelt, Kleinanzeigen** | Du legst dort **Suchaufträge mit E-Mail „sofort“** an. Der Bot liest die Mails per IMAP. | IS24 und Kleinanzeigen **verbieten automatisches Auslesen** in ihren AGB und sperren Bots technisch. Ein Scraper würde ständig geblockt und kann dein Konto kosten. Die Suchauftrags-Mails sind erlaubt und kostenlos. |
| **VEBOWAG, GWG Bonn** (Genossenschaft) | Beide vergeben Wohnungen über **Immomio**. Dort ein Suchprofil mit E-Mail-Benachrichtigung anlegen, dann liest der Bot diese Mails. Zusätzlich liest er ihre Angebotsseiten direkt. | Wie die Angebotsseiten gerade aufgebaut sind, konnte ich nicht prüfen (siehe unten). |
| **Vonovia, Vivawest, LEG, BImA** | Suchauftrag/Benachrichtigung per E-Mail einrichten, falls angeboten. Der Absenderfilter kennt sie schon. | Vonovia hat ~1.200 Wohnungen in Neu-Tannenbusch, Vivawest Neubauten in Auerberg (Pariser Str./Helsinkistraße). |
| Andere Seiten / RSS | In `config.toml` als `[[quelle]]` mit `typ = "html"` oder `"rss"` | Der Bot erkennt Angebote auf normalen Webseiten selbst (Block mit Link + € + m²) und braucht dafür keine Selektoren. |

> **Was ich nicht testen konnte:** Aus meiner Bauumgebung waren die echten Portale nicht
> erreichbar. Getestet ist alles mit nachgebauten Seiten und Mails im typischen Aufbau
> (38 automatische Tests + Docker-Test). Ob die **echten** Seiten von VEBOWAG und GWG ihre
> Angebote direkt im HTML haben oder per JavaScript nachladen, zeigt sich beim ersten Lauf:
> `/status` meldet dann „0 Angebote gelesen“. Das ist auch normal, wenn gerade nichts frei
> ist. Echte Alarm-Mails prüfst du mit `mail-datei` (siehe unten).

---

## Einrichtung Schritt für Schritt

Du brauchst: einen kleinen Server (ca. 4–6 €/Monat), ein Telegram-Konto und ein
E-Mail-Postfach für die Suchaufträge. Dauer: etwa 45 Minuten.

### 1. Telegram-Bot anlegen (5 Min)
1. In Telegram **@BotFather** öffnen → `/newbot` → Namen ausdenken (z. B. „Meine Bonn Wohnungen“)
   und einen Benutzernamen, der auf `bot` endet.
2. BotFather schickt dir einen **Token** (sieht aus wie `123456:ABC-...`). Den brauchst du gleich.

### 2. Postfach für die Suchaufträge (10 Min)
Am besten ein **neues Gmail-Konto** nur für den Bot (z. B. `max.wohnungssuche@gmail.com`):
1. In dem Google-Konto die **2-Faktor-Anmeldung** einschalten (Pflicht für Schritt 2).
2. https://myaccount.google.com/apppasswords → App-Passwort „Wohnungsbot“ erstellen →
   16-stelliges Passwort notieren. **Nicht** dein normales Passwort verwenden.
3. Mit dieser Adresse **Suchaufträge** anlegen, jeweils Bonn, Mietwohnung, ab 3 Zimmer,
   ab 65 m², bis ca. 1.300 € (die genaue Filterung macht der Bot), Benachrichtigung **sofort**:
   - ImmobilienScout24 → Suche → „Suchauftrag speichern“
   - immowelt → Suche → „Suchauftrag“ (Häufigkeit: sofort)
   - Kleinanzeigen → Wohnung mieten, Bonn → „Suchauftrag speichern“, E-Mail an
   - Immomio (für VEBOWAG/GWG) → Suchprofil anlegen, E-Mail-Benachrichtigung an
   - ggf. Vonovia, Vivawest, LEG, BImA, falls dort eine E-Mail-Benachrichtigung angeboten wird

Die Bewerbungen schickt der Bot über dasselbe Konto (SMTP). Soll der Vermieter lieber
deine normale Adresse sehen, trägst du für SMTP dein normales Konto ein (ebenfalls mit App-Passwort).

### 3. Server mieten (10 Min)
Empfehlung: **Hetzner Cloud**, kleinster Server mit **Ubuntu 24.04**, Standort Deutschland
(ca. 4–6 €/Monat). Jeder andere Linux-VPS geht genauso.
Nach dem Anlegen bekommst du eine IP-Adresse. Verbinden (Mac: Programm „Terminal“):
```bash
ssh root@DEINE-SERVER-IP
```

### 4. Bot installieren (10 Min)
Auf dem Server, Zeile für Zeile:
```bash
curl -fsSL https://get.docker.com | sh                 # Docker installieren
git clone https://github.com/Guddegram/neu.git
cd neu/wohnungsbot
cp config.example.toml config.toml
cp .env.example .env
docker compose build
docker compose run --rm wohnungsbot schluessel         # Schlüssel für die Unterlagen
```
Die ausgegebene Zeile (der Schlüssel) **im Passwortmanager sichern**. Ohne ihn sind die
verschlüsselten Unterlagen nicht mehr lesbar.

Jetzt die Geheimnisse eintragen:
```bash
nano .env
```
`TELEGRAM_TOKEN`, `IMAP_BENUTZER`/`IMAP_PASSWORT` (Gmail-Adresse + App-Passwort),
`SMTP_BENUTZER`/`SMTP_PASSWORT` (dasselbe oder dein normales Konto) und
`UNTERLAGEN_SCHLUESSEL` eintragen. Speichern: `Strg+O`, `Enter`, `Strg+X`.

Danach deine Angaben fürs Anschreiben:
```bash
nano config.toml        # Abschnitt [bewerber] ganz unten ausfüllen
```

### 5. Chat-ID holen und starten
```bash
docker compose up -d
```
Schreib deinem Bot in Telegram `/start`. Er antwortet mit **„Deine Chat-ID: 12345…“**.
Diese Zahl als `TELEGRAM_CHAT_ID` in die `.env` eintragen, dann:
```bash
docker compose up -d --force-recreate
docker compose run --rm wohnungsbot test-telegram     # Testnachricht
docker compose run --rm wohnungsbot test-mail deine@adresse.de
```
Kommt beides an, ist alles fertig. Der Bot startet nach einem Server-Neustart automatisch.

### 6. Unterlagen hinterlegen (optional)
Lade die Datei zuerst auf den Server (vom Mac: `scp Mieterselbstauskunft.pdf root@DEINE-SERVER-IP:~/neu/wohnungsbot/`), dann:
```bash
docker compose run --rm -v "$PWD:/eingang:ro" wohnungsbot \
  unterlagen hinzufuegen /eingang/Mieterselbstauskunft.pdf --name "Mieterselbstauskunft" --erstkontakt
rm Mieterselbstauskunft.pdf          # Original vom Server löschen – verschlüsselt liegt es in daten/
docker compose run --rm wohnungsbot unterlagen liste
```
- Der Dateiname ist der Name des Anhangs beim Vermieter, also sinnvoll benennen
  (z. B. `Mieterselbstauskunft_Max_Mustermann.pdf`).
- `--erstkontakt` = wird beim ersten Anschreiben automatisch angehängt.
  **Nur für unkritische Dokumente** (Mieterselbstauskunft, ggf. Lebenslauf).
- **SCHUFA, Gehaltsnachweise, Ausweis ohne `--erstkontakt`** hinterlegen (oder gar nicht).
  Die schickst du erst nach der Besichtigung an einen Vermieter, den du kennst. Auf
  Anzeigen, die vorab Ausweis oder SCHUFA wollen, steckt oft ein Betrüger.

---

## Bedienung in Telegram

Bei jeder passenden Wohnung:
```
🏠 Neue Wohnung: Tannenbusch
Helle 3-Zimmer-Wohnung            ← Link zur Anzeige
💶 1.050 € warm · Grenze 1.100 €
🛏 3 Zimmer · 📐 72 m²
📍 Oppelner Str. 10, 53119 Bonn-Tannenbusch
🔎 ImmobilienScout24 · Nr. 17
[📝 Bewerbung vorbereiten] [🙈 Ignorieren]
```
**📝 Bewerbung vorbereiten** → der Bot zeigt das fertige Anschreiben (Text antippen = kopieren) und dann:
- **E-Mail-Adresse in der Anzeige** → Knopf **„✅ Senden an …“** (mit sichtbarem Empfänger).
- **Keine Adresse** (bei Portalen der Normalfall) → Text ins Kontaktformular der Anzeige
  einfügen und **„✔️ Selbst beworben“** drücken. Oder auf die Nachricht mit der
  E-Mail-Adresse des Vermieters **antworten**, dann erscheint der Senden-Knopf.

Befehle: `/status` · `/liste` · `/pruefen` (sofort prüfen) · `/bewerben NR` ·
`/mail NR adresse` · `/unterlagen` · `/hilfe`

Der Bot reagiert **nur auf deine Chat-ID**. Fremde, die ihn finden, sehen nichts und können nichts auslösen.
Klappt eine Quelle dreimal hintereinander nicht, schickt er dir **eine** Warnung (und eine Entwarnung, wenn sie wieder läuft).

## Nützliche Befehle auf dem Server

```bash
docker compose logs -f --tail 50                 # zuschauen, was der Bot macht
docker compose run --rm wohnungsbot pruefen      # einmal prüfen, Ergebnis anzeigen, nichts senden
docker compose up -d --force-recreate            # nach Änderung an config.toml / .env
git pull && docker compose up -d --build         # Update
```

**Eine echte Alarm-Mail testen:** In Gmail die Mail öffnen → ⋮ → „Original anzeigen“ →
„Original herunterladen“ (.eml), auf den Server kopieren, dann:
```bash
docker compose run --rm -v "$PWD:/eingang:ro" wohnungsbot mail-datei /eingang/mail.eml
```
Er zeigt jedes erkannte Angebot mit Zimmern, Fläche, Miete, Stadtteil und ob es passt.
Erkennt er nichts, schick mir die Mail (persönliche Daten vorher schwärzen).

## Anschreiben anpassen
Eigene Vorlage: Datei `anschreiben.txt` neben `config.toml` anlegen, in `config.toml`
`vorlage = "anschreiben.txt"` setzen und in `docker-compose.yml` die Zeile mit
`anschreiben.txt` einkommentieren. Die erste Zeile `Betreff: …` wird der Betreff.
Platzhalter: `{titel}` `{ort}` `{stadtteil}` `{adresse}` `{zimmer}` `{zimmer_text}` `{flaeche}`
`{warmmiete}` `{quelle}` `{url}` `{unterlagen_satz}` `{datum}` sowie alle Felder aus
`[bewerber]` (`{name}`, `{telefon}`, `{beruf}`, …) und `{beruf_text}` (Beruf + Arbeitgeber).
Zeilen, deren Platzhalter alle leer sind, fallen automatisch weg.

## Datenschutz
- Passwörter und Tokens stehen nur in `.env` auf deinem Server (nicht in Git, siehe `.gitignore`).
- Unterlagen liegen nur **verschlüsselt** (Fernet/AES) in `daten/unterlagen/`. Der Schlüssel steht in `.env`.
- Ohne deinen Klick in Telegram verschickt der Bot **nichts**. Der Empfänger steht vorher auf dem Knopf.
- Beim Erstkontakt gehen nur Dokumente mit `--erstkontakt` raus.

## Für Entwickler
```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .        # 38 Tests, inkl. Ende-zu-Ende mit Fake-Telegram/SMTP
```
