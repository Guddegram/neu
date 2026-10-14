"""State handling and WireGuard config rendering for the neuvpn server."""

import ipaddress
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import keys

STATE_VERSION = 1
DEFAULT_PORT = 51820
DEFAULT_SUBNET = "10.8.0.0/24"
DEFAULT_SUBNET6 = "fd42:4e55:524f::/64"
DEFAULT_DNS = ["9.9.9.9", "149.112.112.112"]  # Quad9 (no logging, malware blocking)
DEFAULT_KEEPALIVE = 25
FULL_TUNNEL = "0.0.0.0/0, ::/0"

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$")


class NeuVPNError(Exception):
    """Error with a user-facing message."""


@dataclass
class Client:
    name: str
    private_key: str
    public_key: str
    preshared_key: str
    address: str
    address6: str | None = None
    allowed_ips: str = FULL_TUNNEL
    created: int = field(default_factory=lambda: int(time.time()))
    enabled: bool = True


@dataclass
class State:
    endpoint: str
    server_private_key: str
    server_public_key: str
    country: str = "RO"
    interface: str = "wg0"
    port: int = DEFAULT_PORT
    subnet: str = DEFAULT_SUBNET
    subnet6: str | None = None
    dns: list[str] = field(default_factory=lambda: list(DEFAULT_DNS))
    wan_interface: str | None = None
    mtu: int | None = None
    keepalive: int = DEFAULT_KEEPALIVE
    client_isolation: bool = True
    clients: dict[str, Client] = field(default_factory=dict)
    version: int = STATE_VERSION

    # ---- addressing -------------------------------------------------

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network(self.subnet, strict=True)

    @property
    def network6(self) -> ipaddress.IPv6Network | None:
        return ipaddress.IPv6Network(self.subnet6, strict=True) if self.subnet6 else None

    @property
    def server_address(self) -> str:
        return str(next(self.network.hosts()))

    @property
    def server_address6(self) -> str | None:
        net6 = self.network6
        return str(net6.network_address + 1) if net6 else None

    def _next_free_offset(self) -> int:
        used = {self.server_address} | {c.address for c in self.clients.values()}
        for offset, host in enumerate(self.network.hosts(), start=1):
            if str(host) not in used:
                return offset
        raise NeuVPNError(f"Subnetz {self.subnet} ist voll – keine freie IP mehr.")

    # ---- clients ----------------------------------------------------

    def add_client(self, name: str, allowed_ips: str = FULL_TUNNEL) -> Client:
        if not _NAME_RE.match(name):
            raise NeuVPNError(
                "Ungültiger Name. Erlaubt: Buchstaben, Ziffern, '-', '_', '.' (max. 32 Zeichen)."
            )
        if name in self.clients:
            raise NeuVPNError(f"Client '{name}' existiert bereits.")
        _validate_allowed_ips(allowed_ips)
        offset = self._next_free_offset()
        address = str(self.network.network_address + offset)
        address6 = None
        if self.network6:
            address6 = str(self.network6.network_address + offset)
        priv, pub = keys.generate_keypair()
        client = Client(
            name=name,
            private_key=priv,
            public_key=pub,
            preshared_key=keys.generate_preshared_key(),
            address=address,
            address6=address6,
            allowed_ips=allowed_ips,
        )
        self.clients[name] = client
        return client

    def get_client(self, name: str) -> Client:
        try:
            return self.clients[name]
        except KeyError:
            raise NeuVPNError(f"Client '{name}' nicht gefunden.") from None

    def remove_client(self, name: str) -> Client:
        client = self.get_client(name)
        del self.clients[name]
        return client

    # ---- rendering --------------------------------------------------

    def _firewall_hooks(self) -> tuple[list[str], list[str]]:
        # Without an explicit WAN interface, masquerade everything that leaves
        # through any interface other than the tunnel itself.
        out = f"-o {self.wan_interface}" if self.wan_interface else "! -o %i"
        up = ["sysctl -q -w net.ipv4.ip_forward=1 || true"]
        down: list[str] = []
        families = [("iptables", self.subnet, "")]
        if self.subnet6:
            up.append("sysctl -q -w net.ipv6.conf.all.forwarding=1 || true")
            # IPv6 is best effort: a server without IPv6 must still come up
            families.append(("ip6tables", self.subnet6, " || true"))
        for tool, subnet, tolerate in families:
            rules = [
                "FORWARD -i %i -j ACCEPT",
                "FORWARD -o %i -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT",
            ]
            if self.client_isolation:
                rules.append("FORWARD -i %i -o %i -j DROP")
            for rule in rules:
                up.append(f"{tool} -I {rule}{tolerate}")
                down.append(f"{tool} -D {rule}{tolerate}")
            nat = f"POSTROUTING -s {subnet} {out} -j MASQUERADE"
            mss = "FORWARD -o %i -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu"
            up += [f"{tool} -t nat -A {nat}{tolerate}", f"{tool} -t mangle -A {mss}{tolerate}"]
            down += [f"{tool} -t nat -D {nat}{tolerate}", f"{tool} -t mangle -D {mss}{tolerate}"]
        return up, down

    def render_server(self) -> str:
        addresses = [f"{self.server_address}/{self.network.prefixlen}"]
        if self.network6:
            addresses.append(f"{self.server_address6}/{self.network6.prefixlen}")
        lines = [
            "# Erzeugt von neuvpn – nicht von Hand bearbeiten (neuvpn apply überschreibt).",
            f"# Standort: {self.country}",
            "[Interface]",
            f"Address = {', '.join(addresses)}",
            f"ListenPort = {self.port}",
            f"PrivateKey = {self.server_private_key}",
        ]
        if self.mtu:
            lines.append(f"MTU = {self.mtu}")
        up, down = self._firewall_hooks()
        lines += [f"PostUp = {h}" for h in up]
        lines += [f"PostDown = {h}" for h in down]
        for client in sorted(self.clients.values(), key=lambda c: ipaddress.IPv4Address(c.address)):
            if not client.enabled:
                continue
            allowed = [f"{client.address}/32"]
            if client.address6:
                allowed.append(f"{client.address6}/128")
            lines += [
                "",
                f"# Client: {client.name}",
                "[Peer]",
                f"PublicKey = {client.public_key}",
                f"PresharedKey = {client.preshared_key}",
                f"AllowedIPs = {', '.join(allowed)}",
            ]
        return "\n".join(lines) + "\n"

    def render_client(self, name: str) -> str:
        client = self.get_client(name)
        addresses = [f"{client.address}/32"]
        if client.address6:
            addresses.append(f"{client.address6}/128")
        endpoint_host = self.endpoint
        if ":" in endpoint_host and not endpoint_host.startswith("["):
            endpoint_host = f"[{endpoint_host}]"  # bare IPv6 literal
        lines = [
            f"# neuvpn – Client '{client.name}' – Standort {self.country}",
            "[Interface]",
            f"PrivateKey = {client.private_key}",
            f"Address = {', '.join(addresses)}",
        ]
        if self.dns:
            lines.append(f"DNS = {', '.join(self.dns)}")
        if self.mtu:
            lines.append(f"MTU = {self.mtu}")
        lines += [
            "",
            "[Peer]",
            f"PublicKey = {self.server_public_key}",
            f"PresharedKey = {client.preshared_key}",
            f"Endpoint = {endpoint_host}:{self.port}",
            f"AllowedIPs = {client.allowed_ips}",
            f"PersistentKeepalive = {self.keepalive}",
        ]
        return "\n".join(lines) + "\n"

    # ---- (de)serialisation -----------------------------------------

    def to_dict(self) -> dict:
        data = asdict(self)
        data["clients"] = {n: asdict(c) for n, c in self.clients.items()}
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "State":
        data = dict(data)
        if data.get("version", 0) > STATE_VERSION:
            raise NeuVPNError("state.json stammt von einer neueren neuvpn-Version.")
        clients = {n: Client(**c) for n, c in data.pop("clients", {}).items()}
        return cls(clients=clients, **data)


def _validate_allowed_ips(value: str) -> None:
    for part in value.split(","):
        try:
            ipaddress.ip_network(part.strip(), strict=False)
        except ValueError:
            raise NeuVPNError(f"Ungültiges AllowedIPs-Netz: {part.strip()!r}") from None


def new_state(
    endpoint: str,
    *,
    port: int = DEFAULT_PORT,
    subnet: str = DEFAULT_SUBNET,
    subnet6: str | None = None,
    dns: list[str] | None = None,
    country: str = "RO",
    interface: str = "wg0",
    wan_interface: str | None = None,
    mtu: int | None = None,
    client_isolation: bool = True,
) -> State:
    if not endpoint:
        raise NeuVPNError("Endpoint (öffentliche IP oder DNS-Name des Servers) fehlt.")
    if not 1 <= port <= 65535:
        raise NeuVPNError("Port muss zwischen 1 und 65535 liegen.")
    try:
        net = ipaddress.IPv4Network(subnet, strict=True)
        if subnet6:
            ipaddress.IPv6Network(subnet6, strict=True)
    except ValueError as exc:
        raise NeuVPNError(f"Ungültiges Subnetz: {exc}") from None
    if net.num_addresses < 4:
        raise NeuVPNError("Subnetz zu klein.")
    for server in dns or []:
        try:
            ipaddress.ip_address(server)
        except ValueError:
            raise NeuVPNError(f"Ungültiger DNS-Server: {server!r}") from None
    if not re.match(r"^[A-Za-z0-9_=+.-]{1,15}$", interface):
        raise NeuVPNError("Ungültiger Interface-Name.")
    priv, pub = keys.generate_keypair()
    return State(
        endpoint=endpoint,
        server_private_key=priv,
        server_public_key=pub,
        country=country.upper(),
        interface=interface,
        port=port,
        subnet=subnet,
        subnet6=subnet6,
        dns=list(DEFAULT_DNS) if dns is None else dns,
        wan_interface=wan_interface,
        mtu=mtu,
        client_isolation=client_isolation,
    )


# ---- persistence ------------------------------------------------------


def default_data_dir() -> Path:
    env = os.environ.get("NEUVPN_DIR")
    if env:
        return Path(env)
    if os.name == "posix" and os.geteuid() == 0:
        return Path("/etc/neuvpn")
    return Path.home() / ".neuvpn"


def write_secret(path: Path, content: str) -> None:
    """Atomically write a file readable only by the owner."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def load_state(data_dir: Path) -> State:
    path = data_dir / "state.json"
    if not path.exists():
        raise NeuVPNError(f"Kein Server eingerichtet in {data_dir}. Zuerst 'neuvpn init' ausführen.")
    with path.open(encoding="utf-8") as fh:
        return State.from_dict(json.load(fh))


def save_state(data_dir: Path, state: State) -> None:
    write_secret(data_dir / "state.json", json.dumps(state.to_dict(), indent=2) + "\n")
