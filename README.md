# neuvpn – kostenloses VPN mit rumänischer IP 🇷🇴

`neuvpn` gibt dir **kostenlos** eine **rumänische IP-Adresse** – lokal auf deinem Mac und Handy,
**ohne** eigenen Server und ohne jemanden in Rumänien. Alles basiert auf Open Source:

| Modus | Was passiert | Rumänien sicher? | Geschwindigkeit |
| --- | --- | --- | --- |
| **`neuvpn tor`** (Hauptmodus) | [Tor](https://www.torproject.org) läuft lokal, Ausgang **nur über rumänische Tor-Server** (`ExitNodes {ro}`) | ✅ ja | mittel – reicht für Surfen, Social Media, Shops |
| **`neuvpn free`** | Öffentliche, kostenlose [VPN-Gate](https://www.vpngate.net)-Server in Rumänien (OpenVPN) | ⚠️ nur wenn gerade einer online ist | meist schneller |

Außerdem kann `neuvpn` später auch einen **eigenen WireGuard-Server** verwalten (siehe ganz unten).

> **Ehrlich gesagt:** Ein kostenloser Dienst hat Grenzen. Tor überträgt nur TCP (kein Online-Gaming,
> keine Anrufe über UDP), ist langsamer als ein Bezahl-VPN, und manche Seiten zeigen bei Tor
> Captchas oder sperren es. VPN-Gate-Server werden von unbekannten Freiwilligen betrieben und
> protokollieren Verbindungen. Für Online-Banking deshalb lieber das VPN ausschalten.

---

## 💻 Mac – die App „Rumänien-VPN“ (ohne Terminal)

### Einmalig installieren
1. **[Rumaenien-VPN.dmg herunterladen](https://github.com/Guddegram/neu/releases/download/mac-app/Rumaenien-VPN.dmg)**
   (läuft auf allen Macs ab macOS 11, Apple-Chip und Intel).
2. Die Datei im Download-Ordner doppelklicken → es öffnet sich ein Fenster mit **Rumänien-VPN**
   und dem Ordner **Programme**. **Rumänien-VPN auf „Programme“ ziehen.** Fertig installiert.
3. **Erstes Öffnen** (nur einmal nötig, weil die App nicht bei Apple registriert ist):
   - Rumänien-VPN in **Programme** (oder über Launchpad/Spotlight) öffnen → macOS meldet, dass sie
     nicht geöffnet werden kann → **Fertig** klicken.
   - **Systemeinstellungen › Datenschutz & Sicherheit** öffnen, ganz nach unten scrollen →
     bei „Rumänien-VPN wurde blockiert“ auf **Dennoch öffnen** klicken → Passwort eingeben →
     **Öffnen**.

Danach startet die App wie jedes andere Programm (Programme-Ordner, Launchpad, Spotlight, Dock).

### Benutzen
- App öffnen → **Land wählen** (Rumänien, Türkei, Indien, Argentinien, Ecuador) → **Einschalten**.
  Nach 10–60 Sekunden steht da z. B. **„An – Rumänien“** mit deiner neuen IP.
  Beim ersten Einschalten fragt macOS nach deinem Passwort (für die Proxy-Einstellung des Macs).
  Die App prüft die IP bei **mehreren** Geo-Diensten und wechselt den Server automatisch, bis
  **alle** dasselbe Land melden – IP-Adresse und angezeigter Standort sind damit immer identisch.
  Hat ein Land gerade keine Tor-Ausgangs-Server (bei Argentinien/Ecuador normal), sucht die App
  automatisch einen **freien Proxy-Server** in dem Land und prüft ihn genauso streng. Freie Proxys
  werden von Unbekannten betrieben und sind langsamer – nichts Sensibles (Banking, Logins) darüber
  machen. Ist gerade keiner online, sagt die App das ehrlich, statt ewig zu verbinden.
- **Neue IP (Land)**: wechselt die IP, bleibt im gewählten Land.
- **Handy im selben WLAN mitnutzen**: vor dem Einschalten anhaken – die App zeigt dann Server und
  Port, die du am Handy einträgst (siehe unten, Handy Variante 2).
- **Ausschalten**, das **Fenster schließen** oder **Cmd+Q** → normale IP. Falls der Mac abstürzt,
  stellt die App beim nächsten Öffnen die Proxy-Einstellung automatisch zurück.

Die App bringt alles mit (auch Tor vom offiziellen Tor-Projekt) – kein Homebrew, kein Terminal.

### Alternative: Einrichtung mit Terminal (für Fortgeschrittene)
1. **Terminal** öffnen (Programme › Dienstprogramme › Terminal).
2. Falls noch nicht vorhanden, [Homebrew](https://brew.sh) installieren:
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
3. neuvpn holen und einrichten:
   ```bash
   git clone https://github.com/guddegram/neu.git && cd neu
   ./scripts/mac-setup.sh
   ```
   Danach liegen auf dem Schreibtisch **„Rumänien-VPN an“** und **„Rumänien-VPN aus“** zum Doppelklicken.

### Im Terminal
```bash
neuvpn tor start      # Tor (Ausgang Rumänien) starten + Mac-Proxy umstellen
neuvpn tor status     # zeigt deine aktuelle IP und das Land
neuvpn tor new-ip     # neue rumänische IP
neuvpn tor stop       # aus, Proxy zurückstellen
```
`tor start` prüft am Ende selbst, ob die IP wirklich aus Rumänien kommt.
Safari, Chrome, Firefox (Einstellung „System-Proxy verwenden“) und die meisten Apps nutzen den Proxy.

### Mac: VPN Gate (Alternative)
```bash
neuvpn free                  # sucht rumänische Server, speichert die besten als .ovpn-Dateien
```
Die Dateien (Ordner `vpngate-profile/`) per Doppelklick in **Tunnelblick** (kostenlos, Open Source;
`./scripts/mac-setup.sh --tunnelblick`) oder **OpenVPN Connect** öffnen und verbinden.

---

## 📱 Handy

### Variante 1: Android – Orbot (Tor, Ausgang Rumänien)
1. **Orbot** installieren (Play Store oder F-Droid, Open Source vom Guardian Project).
2. Orbot öffnen, **Verbinden** (englisch „Connect“) tippen und die VPN-Anfrage mit **OK** bestätigen.
3. Wenn „Verbunden“ dasteht: **Ausgang ändern** (🌎, englisch „Change exit“) tippen, nach unten
   scrollen und **🇷🇴 Rumänien** wählen. Orbot stellt dann selbst „nur Rumänien“ ein.
4. Fertig – alle Apps des Handys laufen über Rumänien. Prüfen: im Browser
   [ifconfig.co/json](https://ifconfig.co/json) öffnen → `"country_iso": "RO"`.

### Variante 2: iPhone oder Android – über deinen Mac im gleichen WLAN
Auf dem Mac:
```bash
neuvpn tor start --share
```
Das zeigt die IP deines Macs an. Dann auf dem Handy:
- **iPhone:** Einstellungen › WLAN › ⓘ neben deinem WLAN › Proxy konfigurieren › **Manuell** →
  Server = IP des Macs, Port = **9056**
- **Android:** WLAN lange drücken › Netzwerk ändern › Erweitert › Proxy › **Manuell** → gleiche Werte

So laufen Webseiten (`https://` und `http://`) und alle Apps, die die Proxy-Einstellung des Handys
nutzen, über Rumänien. Funktioniert nur im gleichen WLAN wie der Mac und nur, solange der Mac an ist.
Danach den Proxy am Handy wieder auf „Aus“ stellen.

### Variante 3: iPhone oder Android – VPN Gate mit OpenVPN Connect
1. **OpenVPN Connect** installieren (App Store / Play Store, kostenlos).
2. Auf dem Mac:
   ```bash
   neuvpn free --serve
   ```
3. Mit dem Handy den angezeigten **QR-Code scannen**, ein Profil antippen → „In OpenVPN Connect
   öffnen“ → verbinden. (Alternativ die `.ovpn`-Datei per AirDrop schicken.)

---

## Prüfen, ob es klappt
- Mac: `neuvpn tor status` oder `neuvpn check`
- Überall: [ifconfig.co/json](https://ifconfig.co/json) öffnen → `"country_iso": "RO"` (ipinfo.io sperrt manche Tor-Ausgänge)

---

## Befehle

| Befehl | Zweck |
| --- | --- |
| `neuvpn tor start [--share] [--country RO] [--port 9055]` | Tor mit Ausgang nur in Rumänien starten (macOS: System-Proxy an) |
| `neuvpn tor stop` / `status` / `new-ip` | Beenden / Status + aktuelle IP / neue IP |
| `neuvpn free [--serve] [--connect] [--list]` | Kostenlose VPN-Gate-Server in Rumänien |
| `neuvpn check [--socks 127.0.0.1:9055] [--expect RO]` | Aus welchem Land kommt der Verkehr? |
| `neuvpn init` / `add` / `show` / `list` / `remove` / `enable` / `disable` / `apply` / `status` | Eigener WireGuard-Server (siehe unten) |

Ports von `neuvpn tor`: SOCKS5 `9055`, HTTP-Proxy `9056` (für `http://` und `https://`),
Steuerung `9057` (nur lokal). Mit `--share` sind SOCKS- und HTTP-Proxy nur für Geräte aus dem lokalen
Netz (`192.168.x.x` usw.) erlaubt.

---

## Später: eigener WireGuard-Server (schnellstes & privatestes VPN)

Falls du irgendwann einen Server in Rumänien hast (Raspberry Pi bei Bekannten oder ein günstiger
rumänischer VPS für ca. 2–5 €/Monat), macht `neuvpn` daraus ein vollwertiges WireGuard-VPN:
```bash
sudo ./scripts/install-server.sh --duckdns meinvpn-ro DEIN-DUCKDNS-TOKEN   # auf dem Server
sudo neuvpn add handy --qr && sudo neuvpn apply                            # weiteres Gerät
```
Das Skript installiert WireGuard, richtet NAT, kostenloses DynDNS ([DuckDNS](https://www.duckdns.org)) und
Autostart ein, **prüft, ob der Server wirklich in Rumänien steht**, und zeigt einen QR-Code für die
WireGuard-App. Zu Hause am Router dann **UDP 51820** auf den Server weiterleiten. Als Docker-Variante:
`NEUVPN_ENDPOINT=meinvpn-ro.duckdns.org docker compose up -d --build`.
Deinstallieren: `sudo ./scripts/uninstall-server.sh [--purge]`.

Eigenschaften: Preshared Key pro Gerät, Geräte live hinzufügen/sperren (`wg syncconf`), Geräte
untereinander isoliert, IPv6-Leckschutz, DNS über Quad9, optional IPv6 im Tunnel (`init --ipv6`).

---

## Verwandte Open-Source-Projekte (Recherche)
- Tor mit Länder-Ausgang: [torsystem](https://github.com/amgpulse/torsystem), [vpndesk](https://github.com/sandipbera35/vpndesk)
- VPN-Gate-Clients: [davegallant/vpngate](https://github.com/davegallant/vpngate), [vpnclient](https://github.com/bonheur15/vpnclient), [autovpn2](https://github.com/ruped24/autovpn2)
- Eigene WireGuard-Server: [awesome-wireguard](https://github.com/cedrickchee/awesome-wireguard) (wg-easy, Firezone, NetBird, Headscale …)
- Nicht Open-Source-Dienst, aber kostenlos: Proton VPN Free hat Rumänien unter den Gratis-Ländern,
  [das Land lässt sich dort aber nicht auswählen](https://protonvpn.com/support/change-server-free-plan).

## Entwicklung & Tests
```
neuvpn/        Python-Paket ohne Abhängigkeiten (tor, vpngate, geo, WireGuard-Verwaltung)
scripts/       mac-setup.sh, install-server.sh, uninstall-server.sh, duckdns-update.sh
docker/        Dockerfile + Entrypoint (WireGuard-Server)
tests/         python3 -m unittest discover -s tests -t .
tests/e2e/     sudo tests/e2e/netns_test.sh – echte WireGuard-Tunnel in Netzwerk-Namespaces
```

Lizenz: MIT
