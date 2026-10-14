"""neuvpn – eigenes, kostenloses WireGuard-VPN mit Standort Rumänien."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import __version__, geo, qr, vpngate
from .config import (
    DEFAULT_PORT,
    DEFAULT_SUBNET,
    DEFAULT_SUBNET6,
    FULL_TUNNEL,
    NeuVPNError,
    load_state,
    new_state,
    save_state,
    write_secret,
)

COUNTRY_NAMES = {"RO": "Rumänien", "DE": "Deutschland", "AT": "Österreich", "CH": "Schweiz"}


def _country(code: str) -> str:
    return f"{COUNTRY_NAMES.get(code, code)} ({code})"


def _data_dir(args) -> Path:
    from .config import default_data_dir

    return Path(args.data_dir) if args.data_dir else default_data_dir()


def _client_path(data_dir: Path, name: str) -> Path:
    return data_dir / "clients" / f"{name}.conf"


def _write_client(data_dir: Path, state, name: str) -> Path:
    path = _client_path(data_dir, name)
    write_secret(path, state.render_client(name))
    return path


def _print_qr(text: str) -> None:
    # comments only make the QR code bigger and harder to scan
    text = "\n".join(line for line in text.splitlines() if not line.startswith("#")) + "\n"
    code = qr.terminal_qr(text)
    if code is None:
        print("(Für QR-Codes 'qrencode' installieren: sudo apt install qrencode)")
    else:
        print(code)


# ---- commands ---------------------------------------------------------


def cmd_init(args) -> int:
    data_dir = _data_dir(args)
    if (data_dir / "state.json").exists() and not args.force:
        raise NeuVPNError(
            f"In {data_dir} ist bereits ein Server eingerichtet. Mit --force überschreiben "
            "(alle Clients werden ungültig!)."
        )
    dns = [d.strip() for d in args.dns.split(",") if d.strip()] if args.dns is not None else None
    state = new_state(
        args.endpoint,
        port=args.port,
        subnet=args.subnet,
        subnet6=args.subnet6 if args.ipv6 else None,
        dns=dns,
        country=args.country,
        interface=args.interface,
        wan_interface=args.wan_interface,
        mtu=args.mtu,
        client_isolation=not args.allow_client_to_client,
    )
    save_state(data_dir, state)
    print(f"✔ Server eingerichtet in {data_dir}")
    print(f"  Standort:   {_country(state.country)}")
    print(f"  Endpoint:   {state.endpoint}:{state.port}/udp")
    print(f"  Subnetz:    {state.subnet}" + (f", {state.subnet6}" if state.subnet6 else ""))
    print(f"  Public Key: {state.server_public_key}")
    print("\nNächste Schritte:\n  neuvpn add handy --qr\n  sudo neuvpn apply --start")
    return 0


def cmd_add(args) -> int:
    data_dir = _data_dir(args)
    state = load_state(data_dir)
    client = state.add_client(args.name, allowed_ips=args.allowed_ips)
    save_state(data_dir, state)
    path = _write_client(data_dir, state, client.name)
    print(f"✔ Client '{client.name}' angelegt – IP {client.address}")
    print(f"  Konfiguration: {path}")
    if args.qr:
        _print_qr(state.render_client(client.name))
    print("Hinweis: 'sudo neuvpn apply' ausführen, damit der Server den neuen Client kennt.")
    return 0


def cmd_remove(args) -> int:
    data_dir = _data_dir(args)
    state = load_state(data_dir)
    state.remove_client(args.name)
    save_state(data_dir, state)
    _client_path(data_dir, args.name).unlink(missing_ok=True)
    print(f"✔ Client '{args.name}' entfernt. Mit 'sudo neuvpn apply' sofort sperren.")
    return 0


def cmd_list(args) -> int:
    state = load_state(_data_dir(args))
    print(f"Server {state.endpoint}:{state.port} – Standort {_country(state.country)}")
    if not state.clients:
        print("Noch keine Clients. Anlegen mit: neuvpn add <name>")
        return 0
    print(f"{'NAME':<20} {'IP':<15} {'ANGELEGT':<17} AKTIV")
    for c in sorted(state.clients.values(), key=lambda c: tuple(int(p) for p in c.address.split("."))):
        created = time.strftime("%Y-%m-%d %H:%M", time.localtime(c.created))
        print(f"{c.name:<20} {c.address:<15} {created:<17} {'ja' if c.enabled else 'nein'}")
    return 0


def cmd_show(args) -> int:
    data_dir = _data_dir(args)
    state = load_state(data_dir)
    text = state.render_client(args.name)
    if args.out:
        write_secret(Path(args.out), text)
        print(f"✔ Gespeichert: {args.out}")
    if args.png:
        if qr.png_qr(text, args.png):
            print(f"✔ QR-Code gespeichert: {args.png}")
        else:
            print("PNG-QR benötigt 'qrencode' (sudo apt install qrencode).", file=sys.stderr)
    if args.qr:
        _print_qr(text)
    if not (args.out or args.qr or args.png):
        print(text, end="")
    return 0


def _set_enabled(args, enabled: bool) -> int:
    data_dir = _data_dir(args)
    state = load_state(data_dir)
    state.get_client(args.name).enabled = enabled
    save_state(data_dir, state)
    word = "aktiviert" if enabled else "deaktiviert"
    print(f"✔ Client '{args.name}' {word}. Mit 'sudo neuvpn apply' übernehmen.")
    return 0


def cmd_server_config(args) -> int:
    print(load_state(_data_dir(args)).render_server(), end="")
    return 0


def _interface_running(iface: str) -> bool:
    if not shutil.which("wg"):
        return False
    return subprocess.run(["wg", "show", iface], capture_output=True, check=False).returncode == 0


def cmd_apply(args) -> int:
    data_dir = _data_dir(args)
    state = load_state(data_dir)
    conf = Path(args.wg_dir) / f"{state.interface}.conf"
    write_secret(conf, state.render_server())
    print(f"✔ Server-Konfiguration geschrieben: {conf}")
    if _interface_running(state.interface):
        stripped = subprocess.run(
            ["wg-quick", "strip", str(conf)], capture_output=True, text=True, check=True
        ).stdout
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as tmp:
            os.chmod(tmp.name, 0o600)
            tmp.write(stripped)
        try:
            subprocess.run(["wg", "syncconf", state.interface, tmp.name], check=True)
        finally:
            os.unlink(tmp.name)
        print(f"✔ Laufendes Interface {state.interface} live aktualisiert (keine Unterbrechung).")
    elif args.start:
        if args.systemd and shutil.which("systemctl") and Path("/run/systemd/system").is_dir():
            subprocess.run(["systemctl", "enable", "--now", f"wg-quick@{state.interface}"], check=True)
        else:
            subprocess.run(["wg-quick", "up", str(conf)], check=True)
        print(f"✔ VPN-Server {state.interface} gestartet.")
    else:
        print(f"Starten mit: sudo systemctl enable --now wg-quick@{state.interface}")
    return 0


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"


def cmd_status(args) -> int:
    state = load_state(_data_dir(args))
    result = subprocess.run(
        ["wg", "show", state.interface, "dump"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print(f"Interface {state.interface} läuft nicht. ({result.stderr.strip()})")
        return 1
    names = {c.public_key: c.name for c in state.clients.values()}
    lines = result.stdout.strip().splitlines()
    print(f"VPN-Server {state.interface} läuft – Standort {_country(state.country)}, Port {state.port}")
    print(f"{'CLIENT':<20} {'LETZTER KONTAKT':<18} {'EMPFANGEN':>11} {'GESENDET':>11}  ENDPOINT")
    now = time.time()
    for line in lines[1:]:
        pub, _psk, endpoint, _allowed, handshake, rx, tx, _ka = line.split("\t")
        hs = int(handshake)
        if hs == 0:
            seen = "nie"
        else:
            ago = int(now - hs)
            seen = f"vor {ago}s" if ago < 120 else f"vor {ago // 60} min"
        print(
            f"{names.get(pub, pub[:12] + '…'):<20} {seen:<18} {_fmt_bytes(int(rx)):>11} "
            f"{_fmt_bytes(int(tx)):>11}  {endpoint if endpoint != '(none)' else '-'}"
        )
    return 0


def cmd_check(args) -> int:
    expect = args.expect
    if expect is None:
        try:
            expect = load_state(_data_dir(args)).country
        except NeuVPNError:
            expect = "RO"
    ip, country, city = geo.lookup(urls=args.url or None)
    where = _country(country) if country else "unbekannt"
    print(f"Öffentliche IP: {ip}\nStandort:       {where}" + (f", {city}" if city else ""))
    if country == expect.upper():
        print(f"✔ Dein Datenverkehr kommt aus {_country(expect.upper())}.")
        return 0
    print(f"✘ Erwartet war {_country(expect.upper())} – VPN aktiv?")
    return 1


def cmd_free(args) -> int:
    if args.from_file:
        text = Path(args.from_file).read_text(encoding="utf-8", errors="replace")
    else:
        text = vpngate.fetch_server_list()
    servers = vpngate.filter_country(vpngate.parse_server_list(text), args.country)
    if not servers:
        print(f"Aktuell kein kostenloser VPN-Gate-Server in {_country(args.country.upper())} online.")
        print("Später erneut versuchen oder eigenen Server aufsetzen (siehe README).")
        return 1
    print(f"{len(servers)} kostenlose Server in {_country(args.country.upper())}:")
    print(f"{'#':>2} {'HOST':<18} {'IP':<16} {'SCORE':>9} {'PING':>5} {'MBIT/S':>7} {'UPTIME':>8}")
    for i, s in enumerate(servers[: args.count], start=1):
        print(
            f"{i:>2} {s.hostname[:18]:<18} {s.ip:<16} {s.score:>9} {s.ping:>5} "
            f"{s.speed_mbps:>7.1f} {s.uptime_days:>6.1f} d"
        )
    if args.list:
        return 0
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for s in servers[: args.count]:
        path = out_dir / f"vpngate-{s.country_short.lower()}-{s.hostname or s.ip}.ovpn"
        path.write_text(s.openvpn_config(), encoding="utf-8")
        written.append(path)
    print("\n✔ OpenVPN-Profile gespeichert:")
    for path in written:
        print(f"  {path}")
    if args.connect:
        if not shutil.which("openvpn"):
            raise NeuVPNError("openvpn ist nicht installiert (sudo apt install openvpn).")
        print(f"\nVerbinde mit {servers[0].hostname} … (Strg+C zum Trennen)")
        os.execvp("openvpn", ["openvpn", "--config", str(written[0])])
    print("\nVerbinden: sudo openvpn --config <datei>  oder Datei in OpenVPN Connect importieren.")
    return 0


# ---- parser -----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neuvpn",
        description="Eigenes kostenloses WireGuard-VPN (Standard-Standort: Rumänien).",
    )
    p.add_argument("--version", action="version", version=f"neuvpn {__version__}")
    p.add_argument("--data-dir", help="Datenverzeichnis (Standard: /etc/neuvpn als root, sonst ~/.neuvpn)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="Server einrichten (Schlüssel + Einstellungen erzeugen)")
    s.add_argument("--endpoint", required=True, help="Öffentliche IP oder DNS-Name des Servers")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.add_argument("--subnet", default=DEFAULT_SUBNET)
    s.add_argument("--ipv6", action="store_true",
                   help="IPv6 im Tunnel (Server braucht IPv6). Ohne: IPv6 wird blockiert, kein Leck.")
    s.add_argument("--subnet6", default=DEFAULT_SUBNET6)
    s.add_argument("--dns", help="DNS-Server, kommagetrennt (Standard: Quad9)")
    s.add_argument("--country", default="RO", help="Ländercode des Server-Standorts (Standard: RO)")
    s.add_argument("--interface", default="wg0")
    s.add_argument("--wan-interface", help="Internet-Interface des Servers (Standard: automatisch)")
    s.add_argument("--mtu", type=int)
    s.add_argument("--allow-client-to-client", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("add", help="Client/Gerät hinzufügen")
    s.add_argument("name")
    s.add_argument("--allowed-ips", default=FULL_TUNNEL, help="Standard: gesamter Verkehr durchs VPN")
    s.add_argument("--qr", action="store_true", help="QR-Code für die Handy-App anzeigen")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("remove", help="Client entfernen")
    s.add_argument("name")
    s.set_defaults(func=cmd_remove)

    s = sub.add_parser("list", help="Clients auflisten")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="Client-Konfiguration anzeigen/exportieren")
    s.add_argument("name")
    s.add_argument("--qr", action="store_true")
    s.add_argument("--png", help="QR-Code als PNG speichern")
    s.add_argument("--out", help="Konfiguration in Datei schreiben")
    s.set_defaults(func=cmd_show)

    for name, enabled in (("enable", True), ("disable", False)):
        s = sub.add_parser(name, help=f"Client {'aktivieren' if enabled else 'sperren'}")
        s.add_argument("name")
        s.set_defaults(func=lambda a, e=enabled: _set_enabled(a, e))

    s = sub.add_parser("server-config", help="Server-Konfiguration (wg0.conf) ausgeben")
    s.set_defaults(func=cmd_server_config)

    s = sub.add_parser("apply", help="wg0.conf schreiben und laufenden Server aktualisieren")
    s.add_argument("--wg-dir", default="/etc/wireguard")
    s.add_argument("--start", action="store_true", help="Server starten, falls er nicht läuft")
    s.add_argument("--no-systemd", dest="systemd", action="store_false",
                   help="Mit wg-quick statt systemd starten")
    s.set_defaults(func=cmd_apply)

    s = sub.add_parser("status", help="Verbundene Clients anzeigen")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("check", help="Prüfen, aus welchem Land dein Verkehr kommt")
    s.add_argument("--expect", help="Erwarteter Ländercode (Standard: Server-Standort bzw. RO)")
    s.add_argument("--url", action="append", help="Eigener Geo-IP-Dienst (JSON)")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("free", help="Sofort & kostenlos: öffentliche VPN-Gate-Server in Rumänien")
    s.add_argument("--country", default="RO")
    s.add_argument("--count", type=int, default=3, help="Wie viele Profile speichern")
    s.add_argument("--list", action="store_true", help="Nur auflisten")
    s.add_argument("--out-dir", default="vpngate-profile")
    s.add_argument("--connect", action="store_true", help="Direkt mit dem besten Server verbinden")
    s.add_argument("--from-file", help="Serverliste aus Datei statt Internet (CSV der VPN-Gate-API)")
    s.set_defaults(func=cmd_free)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except NeuVPNError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 3
    except subprocess.CalledProcessError as exc:
        print(f"Fehler: Befehl fehlgeschlagen: {' '.join(map(str, exc.cmd))}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
