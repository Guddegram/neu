# Majma Webapp

Die Web-App für Mitglieder **ohne iPhone** (Android, Tablet, Computer). Sie läuft in jedem
Browser und lässt sich wie eine App auf den Startbildschirm legen (PWA).

## Was drin ist

| Seite | Datei | Design-Vorlage |
| --- | --- | --- |
| Startseite (Werbeseite) | `index.html` | „Website A – Glas & Grün“ |
| Anmelden | `app/#/login` | Login (Glas) |
| Start | `app/#/start` | Handy: Start (Glas) · Computer: Dashboard mit Seitenleiste |
| Gebetszeiten | `app/#/gebet` | Gebetszeiten mit Countdown-Ring und Glocken |
| Bedarf | `app/#/bedarf` | Bedarf mit Kategorien und Spenden |
| Installieren | erscheint auf dem Handy nach dem Anmelden | „Majma installieren“ |
| Feed, Profil | `app/#/feed`, `app/#/profil` | einfache Liste, Abmelden |
| Moschee, Nachrichten, Schule, Beiträge | | noch ohne Design → „Kommt bald“ |

**Wichtig – Demo-Modus:** Alle Daten (Moschee, Gebetszeiten, Bedarf, Feed, Login) sind
Beispiele aus `js/data.js`. Jede E-Mail und jedes Passwort funktioniert. Damit Web- und
iPhone-Mitglieder dieselben Daten sehen, muss `js/data.js` an den Server der iPhone-App
angeschlossen werden. Alles andere bleibt dabei unverändert.

## Ansehen

Die App braucht einen kleinen lokalen Server (Doppelklick auf die Datei reicht nicht,
weil der Browser sonst die Skripte blockiert). Python ist dafür schon eingebaut:

```bash
cd majma-webapp
python3 -m http.server 8000
```

Dann im Browser öffnen:
- Startseite: <http://localhost:8000>
- Web-App: <http://localhost:8000/app/>

Beenden mit `Ctrl+C`.

## Ordner

```
majma-webapp/
├── index.html            Startseite
├── app/index.html        Web-App (alle Seiten, gewechselt wird über #/…)
├── css/site.css          Aussehen Startseite
├── css/app.css           Aussehen Web-App (Handy + Computer)
├── js/data.js            ← DATENQUELLE (hier kommt später der echte Server rein)
├── js/prayer.js          Rechnen mit Gebetszeiten (nächstes Gebet, Countdown)
├── js/icons.js           Symbole
├── js/site.js            Logik Startseite
├── js/app/main.js        Seitenwechsel, Navigation
├── js/app/views.js       Die einzelnen Seiten
├── js/app/install.js     „Zum Startbildschirm hinzufügen“
├── manifest.webmanifest  App-Name, Symbol, Farben (für die Installation)
├── sw.js                 Service Worker (Installation + offline nutzbar)
└── assets/               Bilder, Logo, App-Symbole
```

## Cloud und lokal – so bleibt alles synchron

Der Code lebt auf GitHub. Cloud und dein Rechner holen sich von dort den aktuellen Stand.

**Auf der Arbeit (Cloud):** In claude.ai/code eine Session mit dem Repo `Guddegram/neu`
starten. Was dort gebaut wird, wird committet und auf GitHub gepusht.

**Später lokal – einmalig herunterladen:**

```bash
git clone https://github.com/Guddegram/neu.git
```

```bash
cd neu
```

Solange die Arbeit noch auf dem Branch `claude/jolly-rubin-wp725s` liegt (und nicht im
Hauptstand), musst du ihn einmal auswählen:

```bash
git checkout claude/jolly-rubin-wp725s
```

**Lokal – vor jedem Arbeiten den neuesten Stand holen:**

```bash
git pull
```

**Lokal – nach dem Arbeiten hochladen:**

```bash
git add majma-webapp
```

```bash
git commit -m "Majma: was du geändert hast"
```

```bash
git push
```

Wichtig: Immer erst `git pull`, dann arbeiten, dann `git push`. Wer an zwei Orten ohne
`pull` gleichzeitig ändert, bekommt Konflikte.
