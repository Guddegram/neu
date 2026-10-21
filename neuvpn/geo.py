"""Check which public IP / country your traffic currently leaves from."""

import http.client
import json
import socket
import ssl
import struct
import urllib.parse
import urllib.request

# ifconfig.co first: it uses the MaxMind database that many websites use for their
# country checks; ipinfo.io often answers Tor exits with 403.
GEO_SERVICES = [
    "https://ifconfig.co/json",
    "http://ip-api.com/json",
    "https://ipinfo.io/json",
]


def parse_geo(data: dict) -> tuple[str | None, str | None, str | None]:
    """Return (ip, country_code, city) from the JSON of any supported service."""
    ip = data.get("ip") or data.get("query")
    country = data.get("country_iso") or data.get("countryCode") or data.get("country")
    if country and len(country) != 2:
        country = None
    city = data.get("city")
    return ip, country.upper() if country else None, city


_HEADERS = {"User-Agent": "curl/8 neuvpn", "Accept": "application/json"}


def socks5_connect(proxy: tuple[str, int], host: str, port: int, timeout: float) -> socket.socket:
    """Open a TCP connection to host:port through a SOCKS5 proxy (DNS resolved by the proxy)."""
    sock = socket.create_connection(proxy, timeout=timeout)
    try:
        sock.sendall(b"\x05\x01\x00")  # version 5, one auth method: none
        if _recv_exact(sock, 2) != b"\x05\x00":
            raise OSError("SOCKS5-Proxy verlangt eine unbekannte Anmeldung")
        name = host.encode("idna")
        sock.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + struct.pack(">H", port))
        version, status, _, atyp = _recv_exact(sock, 4)
        if version != 5 or status != 0:
            raise OSError(f"SOCKS5-Verbindung zu {host}:{port} abgelehnt (Code {status})")
        skip = {1: 4, 4: 16}.get(atyp)
        if skip is None:
            skip = _recv_exact(sock, 1)[0]
        _recv_exact(sock, skip + 2)
        return sock
    except BaseException:
        sock.close()
        raise


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise OSError("SOCKS5-Proxy hat die Verbindung geschlossen")
        buf += chunk
    return buf


def _get_json_via_socks(url: str, proxy: tuple[str, int], timeout: float) -> dict:
    parts = urllib.parse.urlsplit(url)
    https = parts.scheme == "https"
    port = parts.port or (443 if https else 80)
    sock = socks5_connect(proxy, parts.hostname, port, timeout)
    if https:
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
    conn = http.client.HTTPConnection(parts.hostname, port, timeout=timeout)
    conn.sock = sock
    try:
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        conn.request("GET", target, headers={**_HEADERS, "Host": parts.netloc})
        resp = conn.getresponse()
        if resp.status != 200:
            raise OSError(f"HTTP {resp.status}")
        return json.loads(resp.read())
    finally:
        conn.close()


def lookup(
    urls: list[str] | None = None, timeout: float = 10.0, socks: tuple[str, int] | None = None
) -> tuple[str | None, str | None, str | None]:
    errors = []
    for url in urls or GEO_SERVICES:
        try:
            if socks:
                return parse_geo(_get_json_via_socks(url, socks, timeout))
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return parse_geo(json.load(resp))
        except (OSError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
    raise OSError("Kein Geo-IP-Dienst erreichbar:\n  " + "\n  ".join(errors))
