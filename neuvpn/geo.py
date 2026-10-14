"""Check which public IP / country your traffic currently leaves from."""

import json
import urllib.request

GEO_SERVICES = [
    "https://ipinfo.io/json",
    "https://ifconfig.co/json",
    "http://ip-api.com/json",
]


def parse_geo(data: dict) -> tuple[str | None, str | None, str | None]:
    """Return (ip, country_code, city) from the JSON of any supported service."""
    ip = data.get("ip") or data.get("query")
    country = data.get("country_iso") or data.get("countryCode") or data.get("country")
    if country and len(country) != 2:
        country = None
    city = data.get("city")
    return ip, country.upper() if country else None, city


def lookup(urls: list[str] | None = None, timeout: float = 10.0) -> tuple[str | None, str | None, str | None]:
    errors = []
    for url in urls or GEO_SERVICES:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "curl/8 neuvpn", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return parse_geo(json.load(resp))
        except (OSError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
    raise OSError("Kein Geo-IP-Dienst erreichbar:\n  " + "\n  ".join(errors))
