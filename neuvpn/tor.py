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
BOOTSTRAP_TIMEOUT = 180

_HTTP_MARKER = "# neuvpn-http-proxy"
_PRIVATE_NETS = ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]


class TorError(Exception):
    pass


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
    if share:
        # only devices from the local network may use the proxy
        lines += [f"SocksPolicy accept {net}" for net in _PRIVATE_NETS]
        lines.append("SocksPolicy reject *")
    return "\n".join(lines) + "\n"


def _quote(path: Path) -> str:
    """torrc value quoting, so paths with spaces (macOS home folders) work."""
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_tor() -> str:
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


def start(paths: TorPaths, torrc: str, timeout: float = BOOTSTRAP_TIMEOUT, progress=None) -> int:
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
    with paths.log.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [tor, "-f", str(paths.torrc)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    paths.pid.write_text(str(proc.pid), encoding="utf-8")
    deadline = time.monotonic() + timeout
    last = -1
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            paths.pid.unlink(missing_ok=True)
            raise TorError("Tor hat sich beendet:\n" + _log_tail(paths))
        percent = bootstrap_percent(paths.log.read_text(encoding="utf-8", errors="replace"))
        if percent != last and progress:
            progress(percent)
            last = percent
        if percent == 100:
            if "http" in ports:
                try:
                    _start_http_proxy(paths, ports["http"], ports["socks"][1])
                except TorError:
                    stop(paths)
                    raise
            return proc.pid
        time.sleep(0.5)
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    paths.pid.unlink(missing_ok=True)
    raise TorError(
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


def _start_http_proxy(paths: TorPaths, listen: tuple[str, int], socks_port: int) -> None:
    host, port = listen
    cmd = [sys.executable, "-m", "neuvpn.httpproxy", host, str(port), str(socks_port)]
    if host == "0.0.0.0":
        cmd.append("--lan-only")
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


def new_identity(paths: TorPaths, control_port: int = DEFAULT_CONTROL_PORT) -> None:
    """Ask Tor for fresh circuits (a new Romanian exit IP)."""
    cookie = (paths.data / "control_auth_cookie").read_bytes().hex()
    with socket.create_connection(("127.0.0.1", control_port), timeout=10) as s:
        s.sendall(f"AUTHENTICATE {cookie}\r\nSIGNAL NEWNYM\r\nQUIT\r\n".encode())
        reply = s.recv(4096).decode(errors="replace")
    if reply.count("250") < 2:
        raise TorError(f"Tor hat die Anfrage abgelehnt: {reply.strip()}")


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


def _networksetup(*args: str) -> subprocess.CompletedProcess:
    cmd = ["networksetup", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or "requires admin" in (result.stdout + result.stderr).lower():
        result = subprocess.run(["sudo", *cmd], capture_output=True, text=True, check=False)
    return result


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


def mac_proxy_commands(service: str, socks_port: int, http_port: int, enable: bool) -> list[list[str]]:
    if enable:
        return [
            ["-setsocksfirewallproxy", service, "127.0.0.1", str(socks_port)],
            ["-setsocksfirewallproxystate", service, "on"],
            ["-setsecurewebproxy", service, "127.0.0.1", str(http_port)],
            ["-setsecurewebproxystate", service, "on"],
        ]
    return [
        ["-setsocksfirewallproxystate", service, "off"],
        ["-setsecurewebproxystate", service, "off"],
    ]


def set_mac_system_proxy(paths: TorPaths, socks_port: int, http_port: int, enable: bool) -> list[str]:
    if enable:
        services = mac_network_services()
        paths.proxy_state.write_text("\n".join(services), encoding="utf-8")
    else:
        try:
            services = [s for s in paths.proxy_state.read_text(encoding="utf-8").splitlines() if s]
        except FileNotFoundError:
            services = mac_network_services()
        paths.proxy_state.unlink(missing_ok=True)
    changed = []
    for service in services:
        ok = all(
            _networksetup(*cmd).returncode == 0
            for cmd in mac_proxy_commands(service, socks_port, http_port, enable)
        )
        if ok:
            changed.append(service)
    return changed


def is_mac() -> bool:
    return platform.system() == "Darwin"
