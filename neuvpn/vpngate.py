"""Free fallback: public VPN Gate relay servers (University of Tsukuba, Japan).

VPN Gate is a free academic project where volunteers run OpenVPN servers. The
server list is published as CSV at https://www.vpngate.net/api/iphone/ and
includes a ready-to-use OpenVPN config per server. We filter it by country
(default Romania, "RO") and write .ovpn files.

Note: these servers are run by unknown volunteers and log connections. Use
your own WireGuard server for anything private.
"""

import base64
import csv
import io
import urllib.request
from dataclasses import dataclass

API_URLS = [
    "https://www.vpngate.net/api/iphone/",
    "http://www.vpngate.net/api/iphone/",
]

# OpenVPN >= 2.5 no longer negotiates the legacy AES-128-CBC cipher by default,
# but most VPN Gate servers still use it.
_COMPAT_LINES = [
    "data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC",
    "data-ciphers-fallback AES-128-CBC",
]


@dataclass
class Server:
    hostname: str
    ip: str
    score: int
    ping: int
    speed: int
    country_long: str
    country_short: str
    sessions: int
    uptime_ms: int
    operator: str
    config_b64: str

    @property
    def speed_mbps(self) -> float:
        return self.speed / 1_000_000

    @property
    def uptime_days(self) -> float:
        return self.uptime_ms / 86_400_000

    def openvpn_config(self) -> str:
        raw = base64.b64decode(self.config_b64).decode("utf-8", errors="replace")
        raw = raw.replace("\r\n", "\n")
        lines = [line for line in raw.split("\n") if not line.lower().startswith(("data-ciphers",))]
        header = [
            f"# neuvpn – kostenloser VPN-Gate-Server {self.hostname} ({self.country_long})",
            f"# IP {self.ip}, Score {self.score}, Betreiber: {self.operator or 'unbekannt'}",
        ]
        return "\n".join(header + lines).rstrip("\n") + "\n" + "\n".join(_COMPAT_LINES) + "\n"


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_server_list(text: str) -> list[Server]:
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line and line != "*"]
    lines = [line for line in lines if not line.startswith("*")]
    if lines and lines[0].startswith("#"):
        lines[0] = lines[0][1:]
    servers: list[Server] = []
    for row in csv.DictReader(io.StringIO("\n".join(lines))):
        config = (row.get("OpenVPN_ConfigData_Base64") or "").strip()
        if not config or not row.get("IP"):
            continue
        servers.append(
            Server(
                hostname=row.get("HostName", ""),
                ip=row["IP"],
                score=_to_int(row.get("Score")),
                ping=_to_int(row.get("Ping")),
                speed=_to_int(row.get("Speed")),
                country_long=row.get("CountryLong", ""),
                country_short=(row.get("CountryShort") or "").upper(),
                sessions=_to_int(row.get("NumVpnSessions")),
                uptime_ms=_to_int(row.get("Uptime")),
                operator=row.get("Operator", ""),
                config_b64=config,
            )
        )
    return servers


def filter_country(servers: list[Server], country: str) -> list[Server]:
    country = country.upper()
    matches = [s for s in servers if s.country_short == country]
    return sorted(matches, key=lambda s: s.score, reverse=True)


def fetch_server_list(timeout: float = 20.0, urls: list[str] | None = None) -> str:
    errors = []
    for url in urls or API_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "neuvpn"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"{url}: {exc}")
    raise OSError("VPN-Gate-Liste nicht erreichbar:\n  " + "\n  ".join(errors))
