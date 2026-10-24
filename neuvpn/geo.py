"""Check which public IP / country your traffic currently leaves from."""

import http.client
import json
import re
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


# Google's own idea of where the IP is: youtube.com embeds the detected country
# as "GL":"XX" in its page config. This is what "my location" on Google follows.
GOOGLE_URL = "https://www.youtube.com/"
_GL_RE = re.compile(rb'"[gG][lL]"\s*:\s*"([A-Z]{2})"')
_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def _open_response(url: str, timeout: float, socks: tuple[str, int] | None = None,
                   http_proxy: tuple[str, int] | None = None):
    if socks:
        parts = urllib.parse.urlsplit(url)
        https = parts.scheme == "https"
        port = parts.port or (443 if https else 80)
        sock = socks5_connect(socks, parts.hostname, port, timeout)
        if https:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
        conn = http.client.HTTPConnection(parts.hostname, port, timeout=timeout)
        conn.sock = sock
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        conn.request("GET", target, headers={**_BROWSER_HEADERS, "Host": parts.netloc})
        return conn.getresponse()
    if http_proxy:
        addr = f"http://{http_proxy[0]}:{http_proxy[1]}"
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": addr, "https": addr}))
        return opener.open(urllib.request.Request(url, headers=_BROWSER_HEADERS),
                           timeout=timeout)
    return urllib.request.urlopen(urllib.request.Request(url, headers=_BROWSER_HEADERS),
                                  timeout=timeout)


def google_country(timeout: float = 25.0, socks: tuple[str, int] | None = None,
                   http_proxy: tuple[str, int] | None = None) -> str | None:
    """Country code Google itself assigns to the current IP, or None (best effort).

    Streams youtube.com only until the "gl" config value appears (usually within
    the first 100 KB), so the check stays cheap even through Tor or slow proxies.
    """
    resp = None
    try:
        resp = _open_response(GOOGLE_URL, timeout, socks=socks, http_proxy=http_proxy)
        buf = b""
        while len(buf) < 1_500_000:
            chunk = resp.read(65536)
            if not chunk:
                break
            buf += chunk
            match = _GL_RE.search(buf)
            if match:
                return match.group(1).decode()
    except (OSError, ValueError):
        pass
    finally:
        if resp is not None:
            resp.close()
    return None


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


def _get_json_via_http_proxy(url: str, proxy: tuple[str, int], timeout: float) -> dict:
    """Fetch through a remote HTTP proxy (CONNECT for https, TLS checked as usual)."""
    addr = f"http://{proxy[0]}:{proxy[1]}"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": addr, "https": addr}))
    req = urllib.request.Request(url, headers=_HEADERS)
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def lookup_consensus(
    urls: list[str] | None = None, timeout: float = 10.0, socks: tuple[str, int] | None = None,
    http_proxy: tuple[str, int] | None = None,
) -> tuple[str | None, set[str], str | None]:
    """Ask EVERY reachable geo service and return (ip, {country codes}, city).

    Websites use different GeoIP databases; a Tor exit that one database places
    in Romania may be Iceland in another. Only when all reachable services agree
    does the set contain a single country.
    """
    results, errors = [], []
    for url in urls or GEO_SERVICES:
        try:
            if socks:
                results.append(parse_geo(_get_json_via_socks(url, socks, timeout)))
            elif http_proxy:
                results.append(parse_geo(_get_json_via_http_proxy(url, http_proxy, timeout)))
            else:
                req = urllib.request.Request(url, headers=_HEADERS)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    results.append(parse_geo(json.load(resp)))
        except (OSError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
    if not results:
        raise OSError("Kein Geo-IP-Dienst erreichbar:\n  " + "\n  ".join(errors))
    ip = next((r[0] for r in results if r[0]), None)
    city = next((r[2] for r in results if r[2]), None)
    countries = {r[1] for r in results if r[1]}
    return ip, countries, city
