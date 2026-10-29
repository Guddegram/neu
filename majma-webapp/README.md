# Majma Webapp

Hier entsteht die Web-App für **Majma**. Der Ordner liegt im Repo `Guddegram/neu`, damit du
überall daran arbeiten kannst – auf der Arbeit in der Cloud (claude.ai/code) und später fest
auf deinem eigenen Rechner.

## Aktueller Stand

Nur das Grundgerüst: eine Startseite (`index.html`). Funktionen, Aussehen und Technik
(z. B. ob ein Framework dazukommt) werden festgelegt, sobald klar ist, was die App können soll.

## Ansehen

`index.html` einfach im Browser öffnen (Doppelklick). Oder mit einem kleinen lokalen Server,
der in Python schon eingebaut ist:

```bash
cd majma-webapp
python3 -m http.server 8000
```

Danach im Browser <http://localhost:8000> öffnen. Beenden mit `Ctrl+C`.

## Cloud und lokal – so bleibt alles synchron

Der Code lebt auf GitHub. Cloud und dein Rechner holen sich von dort den aktuellen Stand.

**Auf der Arbeit (Cloud):** In claude.ai/code eine Session mit dem Repo `Guddegram/neu`
starten. Was dort gebaut wird, wird committet und auf GitHub gepusht.

**Später lokal – einmalig herunterladen:**

```bash
git clone https://github.com/Guddegram/neu.git
```

```bash
cd neu/majma-webapp
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
