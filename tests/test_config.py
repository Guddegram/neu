import ipaddress
import os
import stat
import tempfile
import unittest
from pathlib import Path

from neuvpn import keys
from neuvpn.config import NeuVPNError, load_state, new_state, save_state


def _sections(text):
    """Parse a wg-quick config into a list of (section, {key: [values]})."""
    sections = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            sections.append((line.strip("[]"), {}))
            continue
        key, _, value = line.partition("=")
        sections[-1][1].setdefault(key.strip(), []).append(value.strip())
    return sections


class StateTest(unittest.TestCase):
    def test_defaults_are_romania_and_full_tunnel(self):
        state = new_state("vpn.example.ro")
        self.assertEqual(state.country, "RO")
        state.add_client("handy")
        client = _sections(state.render_client("handy"))
        self.assertEqual(client[1][1]["AllowedIPs"], ["0.0.0.0/0, ::/0"])
        self.assertEqual(client[1][1]["Endpoint"], ["vpn.example.ro:51820"])
        self.assertEqual(client[0][1]["DNS"], ["9.9.9.9, 149.112.112.112"])

    def test_ip_allocation_and_reuse(self):
        state = new_state("1.2.3.4", subnet="10.9.0.0/29")
        names = ["a", "b", "c", "d", "e"]
        for n in names:
            state.add_client(n)
        self.assertEqual([state.clients[n].address for n in names],
                         ["10.9.0.2", "10.9.0.3", "10.9.0.4", "10.9.0.5", "10.9.0.6"])
        with self.assertRaises(NeuVPNError):
            state.add_client("f")  # /29 has 6 hosts, .1 is the server
        state.remove_client("c")
        self.assertEqual(state.add_client("f").address, "10.9.0.4")

    def test_ipv6_addresses(self):
        state = new_state("1.2.3.4", subnet6="fd00:1::/64")
        c = state.add_client("x")
        self.assertEqual(c.address6, "fd00:1::2")
        server = _sections(state.render_server())
        self.assertEqual(server[0][1]["Address"], ["10.8.0.1/24, fd00:1::1/64"])
        self.assertEqual(server[1][1]["AllowedIPs"], ["10.8.0.2/32, fd00:1::2/128"])

    def test_server_config_peers_match_clients(self):
        state = new_state("1.2.3.4")
        a = state.add_client("a")
        b = state.add_client("b")
        state.get_client("b").enabled = False
        sections = _sections(state.render_server())
        iface = sections[0][1]
        self.assertEqual(keys.public_key(iface["PrivateKey"][0]), state.server_public_key)
        self.assertEqual(iface["ListenPort"], ["51820"])
        peers = [s[1] for s in sections if s[0] == "Peer"]
        self.assertEqual(len(peers), 1)  # disabled client is not rendered
        self.assertEqual(peers[0]["PublicKey"], [a.public_key])
        self.assertEqual(peers[0]["PresharedKey"], [a.preshared_key])
        self.assertNotIn(b.public_key, state.render_server())
        # every PostUp rule has a matching PostDown rule
        ups = [h.replace(" -I ", " -X ").replace(" -A ", " -X ") for h in iface["PostUp"] if "sysctl" not in h]
        downs = [h.replace(" -D ", " -X ") for h in iface["PostDown"]]
        self.assertEqual(sorted(ups), sorted(downs))
        self.assertTrue(any("MASQUERADE" in h and "10.8.0.0/24" in h for h in iface["PostUp"]))

    def test_client_config_keys_pair_with_server(self):
        state = new_state("1.2.3.4")
        state.add_client("a")
        client = _sections(state.render_client("a"))
        self.assertEqual(keys.public_key(client[0][1]["PrivateKey"][0]), state.clients["a"].public_key)
        self.assertEqual(client[1][1]["PublicKey"], [state.server_public_key])

    def test_wan_interface_and_isolation_options(self):
        state = new_state("1.2.3.4", wan_interface="eth0", client_isolation=False)
        server = state.render_server()
        self.assertIn("-s 10.8.0.0/24 -o eth0 -j MASQUERADE", server)
        self.assertNotIn("-i %i -o %i -j DROP", server)

    def test_ipv6_endpoint_is_bracketed(self):
        state = new_state("2001:db8::1")
        state.add_client("a")
        self.assertIn("Endpoint = [2001:db8::1]:51820", state.render_client("a"))

    def test_validation(self):
        for kwargs in ({"endpoint": ""}, {"endpoint": "x", "port": 0}, {"endpoint": "x", "subnet": "10.0.0.1/24"},
                       {"endpoint": "x", "dns": ["nope"]}, {"endpoint": "x", "interface": "bad name"}):
            with self.assertRaises(NeuVPNError, msg=kwargs):
                new_state(**kwargs)
        state = new_state("x")
        for bad in ("", "../etc", "a b", "x" * 40):
            with self.assertRaises(NeuVPNError):
                state.add_client(bad)
        with self.assertRaises(NeuVPNError):
            state.add_client("ok", allowed_ips="not-a-net")
        state.add_client("ok")
        with self.assertRaises(NeuVPNError):
            state.add_client("ok")
        with self.assertRaises(NeuVPNError):
            state.remove_client("missing")

    def test_persistence_roundtrip_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            state = new_state("1.2.3.4", subnet6="fd00::/64")
            state.add_client("a")
            save_state(data_dir, state)
            mode = stat.S_IMODE(os.stat(data_dir / "state.json").st_mode)
            self.assertEqual(mode, 0o600)
            loaded = load_state(data_dir)
            self.assertEqual(loaded.render_server(), state.render_server())
            self.assertEqual(loaded.render_client("a"), state.render_client("a"))
            with self.assertRaises(NeuVPNError):
                load_state(Path(tmp) / "missing")

    def test_addresses_inside_subnet(self):
        state = new_state("x", subnet="172.20.0.0/24")
        net = ipaddress.ip_network("172.20.0.0/24")
        for i in range(20):
            self.assertIn(ipaddress.ip_address(state.add_client(f"c{i}").address), net)


if __name__ == "__main__":
    unittest.main()
