"""Free public HTTP proxies for countries where Tor has no exit relays (e.g. AR, EC).

Candidates come from public proxy lists and are only accepted after the same
strict check as Tor exits: the proxy must answer, and every reachable HTTPS geo
service must place its public IP in the requested country. Plain-http services
are not used for the check, so a malicious proxy cannot fake the country.

Honest limits: free proxies are run by unknown operators and disappear often.
They are fine for browsing with https:// sites, but nothing sensitive
(banking, logins) should run through them.
"""

import concurrent.futures
import json
import urllib.request

from . import geo

SOURCES = [
    ("https://api.proxyscrape.com/v4/free-proxy-list/get"
     "?request=display_proxies&country={cc}&proxy_format=protocolipport&format=text"),
    "https://proxylist.geonode.com/api/proxy-list?limit=200&country={cc}",
]
# country check must go through TLS only (a proxy can tamper with plain http)
CHECK_URLS = [u for u in geo.GEO_SERVICES if u.startswith("https://")]
_HEADERS = {"User-Agent": "Mozilla/5.0 neuvpn"}


def _parse_source(text: str) -> list[tuple[str, int]]:
    """Accept both formats: 'protocol://ip:port' lines and geonode's JSON."""
    found: list[tuple[str, int]] = []
    text = text.strip()
    if text.startswith("{"):
        try:
            entries = json.loads(text).get("data", [])
        except ValueError:
            return []
        for e in entries:
            protos = [p.lower() for p in e.get("protocols", [])]
            if ("http" in protos or "https" in protos) and e.get("ip") and e.get("port"):
                try:
                    found.append((str(e["ip"]), int(e["port"])))
                except (TypeError, ValueError):
                    pass
        return found
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(("http://", "https://")):
            continue  # socks proxies are not usable as macOS web proxy upstream
        hostport = line.split("://", 1)[1]
        host, _, port = hostport.rpartition(":")
        try:
            found.append((host, int(port)))
        except ValueError:
            pass
    return found


def candidates(country: str, timeout: float = 20.0) -> list[tuple[str, int]]:
    """Proxy candidates for a country from all sources (deduplicated, unchecked)."""
    cc = country.strip().upper()
    seen: dict[tuple[str, int], None] = {}
    for url in SOURCES:
        try:
            req = urllib.request.Request(url.format(cc=cc), headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
        except (OSError, ValueError):
            continue
        for proxy in _parse_source(text):
            seen.setdefault(proxy, None)
    return list(seen)


def verify(proxy: tuple[str, int], country: str,
           timeout: float = 12.0) -> tuple[str, str | None] | None:
    """(public ip, city) if ALL reachable HTTPS geo services agree on the country."""
    try:
        ip, countries, city = geo.lookup_consensus(urls=CHECK_URLS, timeout=timeout,
                                                   http_proxy=proxy)
    except OSError:
        return None
    cc = country.strip().upper()
    if not ip or countries != {cc}:
        return None
    google = geo.google_country(http_proxy=proxy)  # "my location" must match too
    if google not in (None, cc):
        return None
    return ip, city


def find_proxy(country: str, exclude: set[tuple[str, int]] | None = None, limit: int = 60,
               workers: int = 12, progress=None, should_cancel=None):
    """First proxy that passes verify(), as ((host, port), ip, city) – or None.

    Tests many candidates in parallel; free proxies are mostly dead, so this
    can take one or two minutes when few are alive.
    """
    todo = [p for p in candidates(country) if p not in (exclude or set())][:limit]
    if not todo:
        return None
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(verify, p, country): p for p in todo}
        try:
            for fut in concurrent.futures.as_completed(futures):
                done += 1
                if should_cancel and should_cancel():
                    return None
                if progress:
                    progress(done, len(todo))
                result = fut.result()
                if result:
                    return futures[fut], result[0], result[1]
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    return None
