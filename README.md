# neuvpn – unser eigenes, kostenloses VPN (Standort: Rumänien 🇷🇴)

`neuvpn` ist ein selbst gehostetes VPN auf Basis von **[WireGuard](https://www.wireguard.com/)**
(Open Source, modern, schnell, im Linux-Kernel eingebaut). Keine Abos, keine fremden Anbieter,
keine Logs: der VPN-Server gehört dir.

- 🔐 WireGuard mit zusätzlichem Preshared Key pro Gerät
- 📱 Geräte per **QR-Code** in die offizielle WireGuard-App holen (Android, iOS, Windows, macOS, Linux)
- 🇷🇴 Standard-Standort **Rumänien** – mit eingebautem Check, dass der Verkehr wirklich aus RO kommt
- ⚡ Geräte hinzufügen/sperren **ohne** Verbindungsabbruch
- 🛡️ Ganzer Verkehr durchs VPN, IPv6-Leckschutz, DNS über Quad9, Geräte untereinander isoliert
- 🆓 Zusätzlich: **sofort kostenlos** über öffentliche rumänische VPN-Gate-Server (ohne eigenen Server)
- 🐍 Keine Abhängigkeiten außer Python 3.10+ (Schlüssel werden selbst erzeugt, Curve25519 nach RFC 7748)

---

## Wie kommt man kostenlos an eine rumänische IP?

Wichtig zu wissen: **Die IP-Adresse (und damit das Land), mit der du im Internet auftauchst, ist
immer die des VPN-Servers.** Für „Rumänien“ muss der Server also in Rumänien stehen.
Die bekannten Gratis-Clouds (Oracle Always Free, Google Cloud Free Tier, AWS Free Tier) haben
derzeit keine Region in Rumänien. Kostenlos gibt es deshalb zwei Wege:

| Weg | Kosten | Eigenes VPN | Datenschutz | Aufwand |
| --- | --- | --- | --- | --- |
| **A) Eigener Server in Rumänien** – Raspberry Pi, alter Laptop/PC oder Mini-PC bei Familie/Freunden in RO | 0 € (vorhandene Hardware, Strom ≈ 0,50 €/Monat beim Pi) | ✅ | ✅ sehr gut – nur du | 15 Min. einmalig |
| **B) `neuvpn free`** – öffentliche VPN-Gate-Server in Rumänien (Uni Tsukuba, Freiwillige) | 0 € | ❌ | ⚠️ fremde Betreiber, Verbindungen werden protokolliert | 1 Min. |
| C) Günstiger VPS bei einem rumänischen Hoster | ca. 2–5 €/Monat | ✅ | ✅ gut | 10 Min. |

**Empfehlung:** Weg A ist „unser eigenes VPN“. Weg B ist ideal, um sofort loszulegen oder als Notlösung.
Für Weg C funktioniert exakt dieselbe Anleitung wie für A (nur ohne Portweiterleitung).

---

## Weg A: Eigener VPN-Server in Rumänien

### Was du brauchst
- Ein Linux-Gerät in Rumänien, das dauerhaft läuft: Raspberry Pi (ab Pi 3), alter PC/Laptop, Mini-PC
  mit **Debian, Ubuntu oder Raspberry Pi OS**
- Zugriff auf den Internet-Router dort (für eine Portweiterleitung)
- Optional: kostenloses DynDNS bei [DuckDNS](https://www.duckdns.org) (Heim-IPs wechseln oft)

### 1. Kostenlosen DuckDNS-Namen holen (empfohlen)
Auf [duckdns.org](https://www.duckdns.org) anmelden, eine Subdomain anlegen (z. B. `meinvpn-ro`) und
den **Token** notieren.

### 2. Server installieren (auf dem Gerät in Rumänien)
```bash
sudo apt install -y git
git clone https://github.com/guddegram/neu.git
cd neu
sudo ./scripts/install-server.sh --duckdns meinvpn-ro DEIN-DUCKDNS-TOKEN
```
Ohne DuckDNS einfach `sudo ./scripts/install-server.sh` (dann wird die aktuelle öffentliche IP verwendet).

Das Skript
1. installiert WireGuard, iptables und qrencode,
2. aktiviert IP-Weiterleitung und NAT,
3. **prüft, ob der Server wirklich in Rumänien steht**,
4. erzeugt alle Schlüssel und das erste Gerät `handy`,
5. startet den VPN-Server (startet auch nach Neustart automatisch),
6. zeigt den **QR-Code** und die nötige Portweiterleitung an.

### 3. Portweiterleitung am Router in Rumänien
Im Router (z. B. Digi/RCS-RDS-, Orange- oder Vodafone-Box, FritzBox, TP-Link …):
**UDP-Port 51820 → lokale IP des Servers, Port 51820**. Das Skript zeigt die lokale IP an.

> Kein Erfolg? Manche Anschlüsse haben keine eigene öffentliche IPv4 („CGNAT“). Dann beim Anbieter
> eine öffentliche IPv4 anfragen, oder Weg C bzw. B nutzen.

### 4. Geräte verbinden
1. Offizielle **WireGuard**-App installieren (Play Store / App Store / [wireguard.com/install](https://www.wireguard.com/install/))
2. „+“ → **QR-Code scannen** (Handy) bzw. „Tunnel aus Datei importieren“ (PC: `/etc/neuvpn/clients/<name>.conf`)
3. Tunnel einschalten → fertig. Prüfen z. B. auf [ipinfo.io](https://ipinfo.io): `"country": "RO"`

Weitere Geräte:
```bash
sudo neuvpn add laptop --qr     # neues Gerät + QR-Code
sudo neuvpn apply               # Server übernimmt es sofort, ohne Unterbrechung
```

---

## Weg B: Sofort kostenlos über VPN Gate (ohne eigenen Server)

Läuft auf deinem eigenen Rechner (Linux/macOS/Windows mit Python 3):
```bash
git clone https://github.com/guddegram/neu.git && cd neu
python3 -m neuvpn free             # listet rumänische Server, speichert die 3 besten als .ovpn
sudo python3 -m neuvpn free --connect   # Linux: direkt mit dem besten verbinden (benötigt openvpn)
```
Die `.ovpn`-Dateien (Ordner `vpngate-profile/`) kannst du auch in **OpenVPN Connect** (Windows, macOS,
Android, iOS) importieren. Sie sind bereits für aktuelle OpenVPN-Versionen angepasst.

⚠️ VPN-Gate-Server werden von unbekannten Freiwilligen betrieben und protokollieren Verbindungen.
Für Online-Banking & private Daten deinen eigenen Server (Weg A) nutzen. Ob gerade ein rumänischer
Server online ist, ändert sich laufend.

---

## Alternative: Docker

Auf einem Server mit Docker (z. B. Weg C):
```bash
git clone https://github.com/guddegram/neu.git && cd neu
NEUVPN_ENDPOINT=meinvpn-ro.duckdns.org docker compose up -d --build
docker compose logs neuvpn                                   # QR-Codes für "handy" und "laptop"
docker compose exec neuvpn neuvpn add tablet --qr            # weiteres Gerät
docker compose exec neuvpn neuvpn apply
```
Schlüssel liegen in `./data`. Das Image bringt `wireguard-go` mit und funktioniert daher auch auf
VPS ohne WireGuard-Kernelmodul.

---

## Befehle

| Befehl | Zweck |
| --- | --- |
| `neuvpn init --endpoint HOST` | Server einrichten (Schlüssel, Subnetz `10.8.0.0/24`, Standort `RO`) |
| `neuvpn add NAME [--qr]` | Gerät hinzufügen |
| `neuvpn show NAME [--qr] [--png datei.png] [--out datei.conf]` | Geräte-Konfiguration anzeigen/exportieren |
| `neuvpn list` | Alle Geräte |
| `neuvpn disable NAME` / `enable NAME` | Gerät sperren / wieder freigeben |
| `neuvpn remove NAME` | Gerät löschen |
| `neuvpn apply [--start]` | `/etc/wireguard/wg0.conf` schreiben, laufenden Server live aktualisieren |
| `neuvpn status` | Wer ist verbunden, letzter Kontakt, Datenmenge |
| `neuvpn check [--expect RO]` | Aus welchem Land kommt mein Verkehr gerade? |
| `neuvpn free [--connect]` | Kostenlose VPN-Gate-Server in Rumänien |
| `neuvpn server-config` | Server-Konfiguration ausgeben |

Nützliche `init`-Optionen: `--port`, `--dns 1.1.1.1,1.0.0.1`, `--ipv6` (IPv6 im Tunnel, wenn der Server
IPv6 hat), `--allow-client-to-client`, `--mtu`, `--wan-interface eth0`.
Ohne `--ipv6` wird IPv6-Verkehr der Geräte trotzdem in den Tunnel gelenkt und dort verworfen –
so gibt es kein IPv6-Leck an deiner echten IP vorbei.

Gerät nur für das Heimnetz in Rumänien statt für alles (Split-Tunnel):
`neuvpn add nas --allowed-ips 10.8.0.0/24,192.168.1.0/24`

## Sicherheit
- Alle Schlüssel liegen nur auf dem Server in `/etc/neuvpn` (Rechte `600`) – niemals ins Git hochladen.
- Jede Verbindung nutzt zusätzlich einen eigenen Preshared Key (Schutz gegen künftige Quantenangriffe).
- Verlorenes Handy? `sudo neuvpn remove handy && sudo neuvpn apply` – sofort gesperrt.
- Server aktuell halten: `sudo apt update && sudo apt upgrade` (Raspberry Pi: `unattended-upgrades` aktivieren).
- Deinstallieren: `sudo ./scripts/uninstall-server.sh` (mit `--purge` inkl. Schlüssel).

## Projektaufbau
```
neuvpn/            Python-Paket (CLI, Schlüssel, Konfiguration, VPN Gate, Geo-Check)
scripts/           install-server.sh, uninstall-server.sh, duckdns-update.sh
docker/            Dockerfile + Entrypoint;  docker-compose.yml im Hauptordner
tests/             Unit-Tests (python3 -m unittest discover -s tests -t .)
tests/e2e/         Ende-zu-Ende-Test mit echten WireGuard-Tunneln (sudo tests/e2e/netns_test.sh)
```

Der Ende-zu-Ende-Test baut in Linux-Netzwerk-Namespaces ein Mini-Internet mit einem „rumänischen“
Server und einem Client auf, verbindet beide über `neuvpn` und prüft, dass der Client-Verkehr über
den Server herauskommt, Live-Updates funktionieren und gesperrte Geräte sofort rausfliegen.

Lizenz: MIT
