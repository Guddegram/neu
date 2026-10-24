import unittest
from unittest import mock

from neuvpn import freeproxy, geo


class ParseTest(unittest.TestCase):
    def test_protocol_lines(self):
        text = "http://1.2.3.4:8080\nsocks4://5.6.7.8:1080\nhttps://9.9.9.9:999\nkaputt\n"
        self.assertEqual(freeproxy._parse_source(text),
                         [("1.2.3.4", 8080), ("9.9.9.9", 999)])  # socks + garbage skipped

    def test_geonode_json(self):
        text = ('{"data": [{"ip": "1.1.1.1", "port": "3128", "protocols": ["http"]},'
                '{"ip": "2.2.2.2", "port": "1080", "protocols": ["socks5"]},'
                '{"ip": "3.3.3.3", "protocols": ["https"]}]}')
        self.assertEqual(freeproxy._parse_source(text), [("1.1.1.1", 3128)])

    def test_broken_json(self):
        self.assertEqual(freeproxy._parse_source("{kaputt"), [])


class VerifyTest(unittest.TestCase):
    def test_only_https_services_are_used(self):
        for url in freeproxy.CHECK_URLS:
            self.assertTrue(url.startswith("https://"))  # a proxy can tamper with http

    def test_verified_when_all_agree(self):
        with mock.patch.object(geo, "lookup_consensus",
                               return_value=("190.1.2.3", {"AR"}, "Buenos Aires")) as lc:
            self.assertEqual(freeproxy.verify(("1.2.3.4", 8080), "ar"),
                             ("190.1.2.3", "Buenos Aires"))
        self.assertEqual(lc.call_args.kwargs["http_proxy"], ("1.2.3.4", 8080))
        self.assertEqual(lc.call_args.kwargs["urls"], freeproxy.CHECK_URLS)

    def test_rejected_on_disagreement_or_failure(self):
        with mock.patch.object(geo, "lookup_consensus", return_value=("x", {"AR", "BR"}, None)):
            self.assertIsNone(freeproxy.verify(("1.2.3.4", 80), "AR"))
        with mock.patch.object(geo, "lookup_consensus", side_effect=OSError("tot")):
            self.assertIsNone(freeproxy.verify(("1.2.3.4", 80), "AR"))


class FindTest(unittest.TestCase):
    def test_first_verified_proxy_wins_and_excluded_are_skipped(self):
        cands = [("1.1.1.1", 80), ("2.2.2.2", 80), ("3.3.3.3", 80)]

        def fake_verify(proxy, country, timeout=12.0):
            return ("200.0.0.1", "Quito") if proxy == ("3.3.3.3", 80) else None

        with mock.patch.object(freeproxy, "candidates", return_value=cands), \
                mock.patch.object(freeproxy, "verify", side_effect=fake_verify):
            result = freeproxy.find_proxy("EC", exclude={("2.2.2.2", 80)})
        self.assertEqual(result, (("3.3.3.3", 80), "200.0.0.1", "Quito"))

    def test_none_when_nothing_works(self):
        with mock.patch.object(freeproxy, "candidates", return_value=[("1.1.1.1", 80)]), \
                mock.patch.object(freeproxy, "verify", return_value=None):
            self.assertIsNone(freeproxy.find_proxy("EC"))

    def test_none_without_candidates(self):
        with mock.patch.object(freeproxy, "candidates", return_value=[]):
            self.assertIsNone(freeproxy.find_proxy("EC"))


if __name__ == "__main__":
    unittest.main()
