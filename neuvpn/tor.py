"""Local, free "VPN" through Tor with exit relays pinned to one country (default Romania).

Tor (https://www.torproject.org, open source) is started as a local proxy whose
exit relays are restricted to the chosen country (`ExitNodes {ro}` +
`StrictNodes 1`). On macOS the system proxy is switched to it, so browsers and
most apps leave the internet with a Romanian IP. Only TCP is carried (no UDP).
"""

import ipaddress
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOCKS_PORT = 9055
DEFAULT_HTTP_PORT = 9056  # HTTP proxy (neuvpn.httpproxy) for apps/phones without SOCKS support
DEFAULT_CONTROL_PORT = 9057
BOOTSTRAP_TIMEOUT = 300
STALL_TIMEOUT = 90  # restart tor if the bootstrap is stuck this long
WATCH_INTERVAL = 20  # seconds between exit-country checks while connected

_HTTP_MARKER = "# neuvpn-http-proxy"
HTTP_PROXY_FLAG = "--neuvpn-http-proxy"
_PRIVATE_NETS = ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]


class TorError(Exception):
    pass


class TorBootstrapTimeout(TorError):
    """Tor could not finish bootstrapping (network blocks Tor, or the chosen
    country's exits are dead) – callers may fall back to free proxies."""


@dataclass
class TorPaths:
    base: Path

    @property
    def torrc(self) -> Path:
        return self.base / "torrc"

    @property
    def data(self) -> Path:
        return self.base / "tor-data"

    @property
    def log(self) -> Path:
        return self.base / "tor.log"

    @property
    def pid(self) -> Path:
        return self.base / "tor.pid"

    @property
    def http_pid(self) -> Path:
        return self.base / "http-proxy.pid"

    @property
    def http_log(self) -> Path:
        return self.base / "http-proxy.log"

    @property
    def excluded(self) -> Path:
        """Exit IPs that websites do not locate in the chosen country (see ensure_exit_country)."""
        return self.base / "excluded-exits.txt"

    @property
    def proxy_state(self) -> Path:
        return self.base / "system-proxy-services"


def build_torrc(
    paths: TorPaths,
    country: str = "RO",
    socks_port: int = DEFAULT_SOCKS_PORT,
    http_port: int = DEFAULT_HTTP_PORT,
    control_port: int = DEFAULT_CONTROL_PORT,
    share: bool = False,
) -> str:
    code = country.strip().lower()
    if len(code) != 2 or not code.isalpha():
        raise TorError(f"Ungültiger Ländercode: {country!r} (z. B. RO)")
    bind = "0.0.0.0" if share else "127.0.0.1"
    lines = [
        f"# neuvpn – Tor mit Ausgang nur in {code.upper()}",
        f"SocksPort {bind}:{socks_port}",
        # not a tor option: start() runs neuvpn's own HTTP proxy here (http:// and https://)
        f"{_HTTP_MARKER} {bind}:{http_port}",
        f"ControlPort 127.0.0.1:{control_port}",
        "CookieAuthentication 1",
        f"DataDirectory {_quote(paths.data)}",
        # logs go to stdout, which start() writes to tor.log (also catches early errors)
        "Log notice stdout",
        f"ExitNodes {{{code}}}",
        "StrictNodes 1",
        "GeoIPExcludeUnknown 1",
        # new circuit every 10 minutes at most, keeps the IP stable while browsing
        "MaxCircuitDirtiness 600",
    ]
    excluded = excluded_exits(paths)
    if excluded:
        lines.append(f"ExcludeExitNodes {','.join(excluded)}")
    bundle = bundled_tor_dir()
    if bundle and (bundle / "data" / "geoip").exists():
        # the bundled tor has no compiled-in GeoIP path; needed for ExitNodes {ro}
        lines.append(f"GeoIPFile {_quote(bundle / 'data' / 'geoip')}")
        lines.append(f"GeoIPv6File {_quote(bundle / 'data' / 'geoip6')}")
    if share:
        # only devices from the local network may use the proxy
        lines += [f"SocksPolicy accept {net}" for net in _PRIVATE_NETS]
        lines.append("SocksPolicy reject *")
    return "\n".join(lines) + "\n"


def _quote(path: Path) -> str:
    """torrc value quoting, so paths with spaces (macOS home folders) work."""
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def bundled_tor_dir() -> Path | None:
    """Tor Expert Bundle shipped inside the Mac app (Contents/Resources/tor-bundle)."""
    env = os.environ.get("NEUVPN_TOR_BUNDLE")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent.parent / "Resources" / "tor-bundle"
        if candidate.is_dir():
            return candidate
    return None


def find_tor() -> str:
    bundle = bundled_tor_dir()
    if bundle and os.access(bundle / "tor" / "tor", os.X_OK):
        return str(bundle / "tor" / "tor")
    tor = shutil.which("tor")
    if tor:
        return tor
    for candidate in ("/opt/homebrew/bin/tor", "/usr/local/bin/tor"):
        if os.access(candidate, os.X_OK):
            return candidate
    hint = "brew install tor" if platform.system() == "Darwin" else "sudo apt install tor"
    raise TorError(f"Tor ist nicht installiert. Installieren mit: {hint}")


def running_pid(paths: TorPaths) -> int | None:
    return _alive_pid(paths.pid)


def _alive_pid(pidfile: Path) -> int | None:
    try:
        pid = int(pidfile.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    return pid


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def torrc_ports(torrc: str) -> dict[str, tuple[str, int]]:
    """Listen addresses from a neuvpn torrc: {'socks': (host, port), 'http': ..., 'control': ...}."""
    keys = {"SocksPort": "socks", _HTTP_MARKER: "http", "ControlPort": "control"}
    ports = {}
    for line in torrc.splitlines():
        for prefix, name in keys.items():
            if line.startswith(prefix + " "):
                host, _, port = line[len(prefix) + 1:].strip().rpartition(":")
                ports[name] = (host, int(port))
    return ports


def _spawn_tor(tor: str, paths: TorPaths) -> subprocess.Popen:
    with paths.log.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [tor, "-f", str(paths.torrc)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    paths.pid.write_text(str(proc.pid), encoding="utf-8")
    return proc


def _terminate(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def start(
    paths: TorPaths,
    torrc: str,
    timeout: float = BOOTSTRAP_TIMEOUT,
    progress=None,
    stall_timeout: float = STALL_TIMEOUT,
    on_restart=None,
) -> int:
    """Start tor and wait until it is connected.

    If the bootstrap makes no progress for `stall_timeout` seconds (it sometimes
    hangs at 50% while loading relay descriptors), tor is restarted with a fresh
    cache, until `timeout` is reached.
    """
    if running_pid(paths):
        raise TorError("Tor läuft bereits. Erst 'neuvpn tor stop' ausführen.")
    ports = torrc_ports(torrc)
    for _, port in ports.values():
        if not _port_free(port):
            raise TorError(f"Port {port} ist belegt. Anderen Port mit --port wählen.")
    tor = find_tor()
    paths.base.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths.torrc.write_text(torrc, encoding="utf-8")
    proc = _spawn_tor(tor, paths)
    deadline = time.monotonic() + timeout
    last = -1
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            paths.pid.unlink(missing_ok=True)
            raise TorError("Tor hat sich beendet:\n" + _log_tail(paths))
        percent = bootstrap_percent(paths.log.read_text(encoding="utf-8", errors="replace"))
        if percent != last:
            last, last_change = percent, time.monotonic()
            if progress:
                progress(percent)
        if percent == 100:
            if "http" in ports:
                try:
                    _start_http_proxy(paths, ports["http"], ports["socks"][1])
                except TorError:
                    stop(paths)
                    raise
            return proc.pid
        if time.monotonic() - last_change > stall_timeout:
            if on_restart:
                on_restart(percent)
            _terminate(proc)
            shutil.rmtree(paths.data, ignore_errors=True)  # fresh cache and guards
            paths.data.mkdir(parents=True, exist_ok=True, mode=0o700)
            proc = _spawn_tor(tor, paths)
            last, last_change = -1, time.monotonic()
        time.sleep(0.5)
    _terminate(proc)
    paths.pid.unlink(missing_ok=True)
    raise TorBootstrapTimeout(
        "Tor konnte sich nicht rechtzeitig verbinden (blockiert das Netz Tor?).\n" + _log_tail(paths)
    )


def bootstrap_percent(log_text: str) -> int:
    percent = 0
    for line in log_text.splitlines():
        marker = "Bootstrapped "
        if marker in line:
            try:
                percent = int(line.split(marker, 1)[1].split("%", 1)[0])
            except ValueError:
                pass
    return percent


def _log_tail(paths: TorPaths, lines: int = 8) -> str:
    try:
        text = paths.log.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    return "\n".join("  " + line for line in text.splitlines()[-lines:])


def _exit_country(torrc: str) -> str | None:
    for line in torrc.splitlines():
        if line.startswith("ExitNodes {") and line.endswith("}"):
            return line[len("ExitNodes {"):-1].upper()
    return None


def watch_exit_country(paths: TorPaths, country: str, socks_port: int, control_port: int,
                       interval: float = WATCH_INTERVAL, stop_event=None) -> None:
    """Re-check the exit regularly; Tor changes circuits, and single exits may be
    located elsewhere by the databases websites use."""
    while True:
        if stop_event is not None:
            if stop_event.wait(interval):
                return
        else:
            time.sleep(interval)
        try:
            ensure_exit_country(paths, country, socks_port, control_port)
        except Exception as exc:  # keep watching, whatever happens
            print(f"Prüfung fehlgeschlagen: {exc}", flush=True)


def _start_http_proxy(paths: TorPaths, listen: tuple[str, int], socks_port: int) -> None:
    host, port = listen
    if getattr(sys, "frozen", False):  # Mac app: the app binary runs the proxy itself
        cmd = [sys.executable, HTTP_PROXY_FLAG, host, str(port), str(socks_port)]
    else:
        cmd = [sys.executable, "-m", "neuvpn.httpproxy", host, str(port), str(socks_port)]
    if host == "0.0.0.0":
        cmd.append("--lan-only")
    country = _exit_country(paths.torrc.read_text(encoding="utf-8"))
    control = torrc_ports(paths.torrc.read_text(encoding="utf-8")).get("control")
    if country and control:
        # keep checking the exit like a website does while tor runs (see ensure_exit_country)
        cmd += ["--watch", country, str(paths.base), str(control[1])]
    env = dict(os.environ)
    package_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_root, env.get("PYTHONPATH")]))
    with paths.http_log.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                env=env, start_new_session=True)
    paths.http_pid.write_text(str(proc.pid), encoding="utf-8")
    for _ in range(50):
        if proc.poll() is not None:
            break
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.1)
    raise TorError("HTTP-Proxy startet nicht:\n" + paths.http_log.read_text(errors="replace")[-500:])


def stop(paths: TorPaths) -> bool:
    _stop_pidfile(paths.http_pid)
    return _stop_pidfile(paths.pid)


def _stop_pidfile(pidfile: Path) -> bool:
    pid = _alive_pid(pidfile)
    pidfile.unlink(missing_ok=True)
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    os.kill(pid, signal.SIGKILL)
    return True


def _control(paths: TorPaths, control_port: int, commands: list[str]) -> str:
    cookie = (paths.data / "control_auth_cookie").read_bytes().hex()
    lines = [f"AUTHENTICATE {cookie}", *commands, "QUIT"]
    reply = b""
    with socket.create_connection(("127.0.0.1", control_port), timeout=10) as s:
        s.sendall(("\r\n".join(lines) + "\r\n").encode())
        while chunk := s.recv(4096):
            reply += chunk
    text = reply.decode(errors="replace")
    if text.count("250 ") < len(lines):
        raise TorError(f"Tor hat die Anfrage abgelehnt: {text.strip()}")
    return text


def new_identity(paths: TorPaths, control_port: int = DEFAULT_CONTROL_PORT) -> None:
    """Ask Tor for fresh circuits (a new Romanian exit IP)."""
    _control(paths, control_port, ["SIGNAL NEWNYM"])


def excluded_exits(paths: TorPaths) -> list[str]:
    try:
        return [l.strip() for l in paths.excluded.read_text().splitlines() if l.strip()]
    except FileNotFoundError:
        return []


def exclude_exit(paths: TorPaths, ip: str, control_port: int = DEFAULT_CONTROL_PORT) -> None:
    """Never use this exit IP again (now and in future runs) and switch to a new circuit."""
    ipaddress.ip_address(ip)  # only plain IPs end up in the torrc
    excluded = excluded_exits(paths)
    if ip not in excluded:
        excluded.append(ip)
        paths.excluded.write_text("\n".join(excluded) + "\n", encoding="utf-8")
    _control(paths, control_port, [f'SETCONF ExcludeExitNodes="{",".join(excluded)}"',
                                   "SIGNAL NEWNYM"])


def ensure_exit_country(paths: TorPaths, country: str, socks_port: int = DEFAULT_SOCKS_PORT,
                        control_port: int = DEFAULT_CONTROL_PORT, attempts: int = 6,
                        wait: float = 3.0):
    """Check the exit like websites do; exclude exits located elsewhere and try again.

    All reachable geo services must agree on the country (they use different
    databases, e.g. MaxMind vs. ip-api): an exit that only one of them places in
    the chosen country would still show up as another country on some websites.
    Returns (ip, country, city) of the last check.
    """
    from . import geo

    result = (None, None, None)
    target = country.upper()
    for _ in range(attempts):
        try:
            ip, countries, city = geo.lookup_consensus(socks=("127.0.0.1", socks_port),
                                                       timeout=30)
        except OSError:
            time.sleep(wait)
            continue
        ok = countries == {target}
        if ok and ip:
            # Google keeps its own database; "my location" must match too
            google = geo.google_country(socks=("127.0.0.1", socks_port))
            if google not in (None, target):
                ok = False
                countries = {google}
        # if services disagree, show a country that is NOT the target (honest display)
        found = target if ok else next(
            iter(sorted(countries - {target})), next(iter(countries), None))
        result = (ip, found, city)
        if ok or not ip or not countries:
            return result
        try:
            exclude_exit(paths, ip, control_port)
        except (TorError, OSError, ValueError):
            pass
        time.sleep(wait)
    return result


ONIONOO_URL = ("https://onionoo.torproject.org/summary"
               "?search=country:{}%20flag:exit%20running:true")


def exit_count(country: str, timeout: float = 8.0) -> int | None:
    """Running Tor exit relays in a country, or None if the check is unavailable.

    Best effort via the Tor project's Onionoo API (direct connection, before
    tor runs). Lets the app say honestly that a country has no exits right now
    instead of hanging in the bootstrap forever.
    """
    import json
    import urllib.request

    try:
        req = urllib.request.Request(ONIONOO_URL.format(country.strip().lower()),
                                     headers={"User-Agent": "neuvpn"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return len(json.load(resp).get("relays", []))
    except (OSError, ValueError):
        return None


def lan_addresses() -> list[str]:
    """Best-effort list of this machine's private IPv4 addresses."""
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no packet is sent for UDP connect
            found.append(s.getsockname()[0])
    except OSError:
        pass
    return [a for a in found if ipaddress.ip_address(a).is_private and not a.startswith("127.")]


# ---- macOS system proxy -----------------------------------------------


def _run_privileged(commands: list[list[str]]) -> bool:
    """Run commands as admin: sudo in a terminal, the macOS password dialog otherwise."""
    if sys.stdin and sys.stdin.isatty():
        return all(subprocess.run(["sudo", *c], check=False).returncode == 0 for c in commands)
    script = " && ".join(" ".join(_sh_quote(a) for a in c) for c in commands)
    applescript = f'do shell script "{_as_quote(script)}" with administrator privileges'
    return subprocess.run(["osascript", "-e", applescript], capture_output=True, check=False).returncode == 0


def _sh_quote(arg: str) -> str:
    return "'" + arg.replace("'", "'\\''") + "'"


def _as_quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _networksetup_all(commands: list[list[str]]) -> list[bool]:
    """Run networksetup commands; failed ones are retried together with admin rights."""
    results = []
    for args in commands:
        r = subprocess.run(["networksetup", *args], capture_output=True, text=True, check=False)
        results.append(r.returncode == 0 and "requires admin" not in (r.stdout + r.stderr).lower())
    failed = [i for i, ok in enumerate(results) if not ok]
    if failed and _run_privileged([["networksetup", *commands[i]] for i in failed]):
        for i in failed:
            results[i] = True
    return results


def mac_network_services() -> list[str]:
    out = subprocess.run(
        ["networksetup", "-listallnetworkservices"], capture_output=True, text=True, check=True
    ).stdout
    services = []
    for line in out.splitlines()[1:]:  # first line is an explanatory note
        line = line.strip()
        if line and not line.startswith("*"):  # '*' marks disabled services
            services.append(line)
    return services


def mac_proxy_commands(service: str, socks_port: int, http_port: int, enable: bool,
                       http_only: bool = False) -> list[list[str]]:
    if enable and http_only:
        # free-proxy mode: everything through the local HTTP forwarder (no SOCKS)
        return [
            ["-setwebproxy", service, "127.0.0.1", str(http_port)],
            ["-setwebproxystate", service, "on"],
            ["-setsecurewebproxy", service, "127.0.0.1", str(http_port)],
            ["-setsecurewebproxystate", service, "on"],
        ]
    if enable:
        return [
            ["-setsocksfirewallproxy", service, "127.0.0.1", str(socks_port)],
            ["-setsocksfirewallproxystate", service, "on"],
            ["-setsecurewebproxy", service, "127.0.0.1", str(http_port)],
            ["-setsecurewebproxystate", service, "on"],
        ]
    return [  # disable always clears both modes (tor and free-proxy)
        ["-setsocksfirewallproxystate", service, "off"],
        ["-setwebproxystate", service, "off"],
        ["-setsecurewebproxystate", service, "off"],
    ]


def set_mac_system_proxy(paths: TorPaths, socks_port: int, http_port: int, enable: bool,
                         http_only: bool = False) -> list[str]:
    if enable:
        services = mac_network_services()
        paths.proxy_state.write_text("\n".join(services), encoding="utf-8")
    else:
        try:
            services = [s for s in paths.proxy_state.read_text(encoding="utf-8").splitlines() if s]
        except FileNotFoundError:
            services = mac_network_services()
        paths.proxy_state.unlink(missing_ok=True)
    per_service = [mac_proxy_commands(svc, socks_port, http_port, enable, http_only)
                   for svc in services]
    results = _networksetup_all([cmd for cmds in per_service for cmd in cmds])
    changed, i = [], 0
    for service, cmds in zip(services, per_service):
        if all(results[i:i + len(cmds)]):
            changed.append(service)
        i += len(cmds)
    return changed


def recover_system_proxy(paths: TorPaths) -> bool:
    """After a crash: proxy still points to a tor that no longer runs -> switch it off."""
    if is_mac() and paths.proxy_state.exists() and not running_pid(paths):
        set_mac_system_proxy(paths, 0, 0, enable=False)
        return True
    return False


def is_mac() -> bool:
    return platform.system() == "Darwin"
