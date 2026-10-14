import base64
import unittest

from neuvpn import vpngate

OVPN = "dev tun\r\nproto udp\r\nremote 1.2.3.4 1195\r\ncipher AES-128-CBC\r\nauth SHA1\r\n"


def _row(host, ip, score, country_long, short, config=OVPN):
    b64 = base64.b64encode(config.encode()).decode()
    return f"{host},{ip},{score},12,52000000,{country_long},{short},5,864000000,100,1000,2weeks,Op {host},,{b64}"


SAMPLE = "\r\n".join([
    "*vpn_servers",
    "#HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,Uptime,"
    "TotalUsers,TotalTraffic,LogType,Operator,Message,OpenVPN_ConfigData_Base64",
    _row("public-vpn-1", "203.0.113.5", 100, "Japan", "JP"),
    _row("ro-low", "198.51.100.7", 1000, "Romania", "RO"),
    _row("ro-best", "198.51.100.8", 90000, "Romania", "RO"),
    "broken,line",
    "*",
    "",
])


class VpnGateTest(unittest.TestCase):
    def test_parse_and_filter_romania(self):
        servers = vpngate.parse_server_list(SAMPLE)
        self.assertEqual(len(servers), 3)
        ro = vpngate.filter_country(servers, "ro")
        self.assertEqual([s.hostname for s in ro], ["ro-best", "ro-low"])
        best = ro[0]
        self.assertEqual(best.ip, "198.51.100.8")
        self.assertEqual(best.country_long, "Romania")
        self.assertAlmostEqual(best.speed_mbps, 52.0)
        self.assertAlmostEqual(best.uptime_days, 10.0)

    def test_openvpn_config_is_patched_for_modern_clients(self):
        best = vpngate.filter_country(vpngate.parse_server_list(SAMPLE), "RO")[0]
        conf = best.openvpn_config()
        self.assertNotIn("\r", conf)
        self.assertIn("remote 1.2.3.4 1195", conf)
        self.assertIn("data-ciphers-fallback AES-128-CBC", conf)
        self.assertTrue(conf.startswith("# neuvpn"))

    def test_empty_list(self):
        self.assertEqual(vpngate.parse_server_list("*vpn_servers\n*\n"), [])
        self.assertEqual(vpngate.filter_country(vpngate.parse_server_list(SAMPLE), "MD"), [])


if __name__ == "__main__":
    unittest.main()
