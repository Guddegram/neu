import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from neuvpn import cli, geo
from tests.test_vpngate import SAMPLE


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {"NEUVPN_DIR": str(self.dir / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_full_workflow(self):
        code, out, _ = run("init", "--endpoint", "vpn.example.ro")
        self.assertEqual(code, 0)
        self.assertIn("Rumänien", out)
        code, _, err = run("init", "--endpoint", "other")
        self.assertEqual(code, 2)
        self.assertIn("--force", err)

        self.assertEqual(run("add", "handy")[0], 0)
        self.assertEqual(run("add", "laptop")[0], 0)
        conf = (self.dir / "data" / "clients" / "handy.conf").read_text()
        self.assertIn("Endpoint = vpn.example.ro:51820", conf)

        code, out, _ = run("list")
        self.assertIn("handy", out)
        self.assertIn("10.8.0.3", out)

        code, out, _ = run("show", "handy")
        self.assertEqual(out, conf)
        out_file = self.dir / "handy-export.conf"
        run("show", "handy", "--out", str(out_file))
        self.assertEqual(out_file.read_text(), conf)

        wg_dir = self.dir / "wg"
        with mock.patch.object(cli, "_interface_running", return_value=False):
            code, out, _ = run("apply", "--wg-dir", str(wg_dir))
        self.assertEqual(code, 0)
        server_conf = (wg_dir / "wg0.conf").read_text()
        self.assertEqual(server_conf.count("[Peer]"), 2)

        run("disable", "laptop")
        _, out, _ = run("server-config")
        self.assertEqual(out.count("[Peer]"), 1)
        run("enable", "laptop")
        run("remove", "handy")
        _, out, _ = run("server-config")
        self.assertEqual(out.count("[Peer]"), 1)
        self.assertFalse((self.dir / "data" / "clients" / "handy.conf").exists())
        self.assertEqual(run("remove", "handy")[0], 2)

    def test_commands_without_init_fail_cleanly(self):
        code, _, err = run("add", "x")
        self.assertEqual(code, 2)
        self.assertIn("neuvpn init", err)

    def test_free_from_file(self):
        csv_file = self.dir / "list.csv"
        csv_file.write_text(SAMPLE)
        out_dir = self.dir / "profiles"
        code, out, _ = run("free", "--from-file", str(csv_file), "--out-dir", str(out_dir))
        self.assertEqual(code, 0)
        self.assertIn("2 kostenlose Server in Rumänien", out)
        files = sorted(p.name for p in out_dir.iterdir())
        self.assertEqual(files, ["vpngate-ro-ro-best.ovpn", "vpngate-ro-ro-low.ovpn"])
        code, out, _ = run("free", "--from-file", str(csv_file), "--country", "MD", "--list")
        self.assertEqual(code, 1)

    def test_check(self):
        with mock.patch.object(geo, "lookup", return_value=("5.2.3.4", "RO", "Bucharest")):
            code, out, _ = run("check")
        self.assertEqual(code, 0)
        self.assertIn("Rumänien", out)
        with mock.patch.object(geo, "lookup", return_value=("8.8.8.8", "DE", None)), \
                mock.patch("time.sleep"):  # check wiederholt 3x, ohne echte Wartezeit
            self.assertEqual(run("check")[0], 1)

    def test_geo_parsing(self):
        self.assertEqual(geo.parse_geo({"ip": "1.1.1.1", "country": "RO", "city": "Iași"}),
                         ("1.1.1.1", "RO", "Iași"))
        self.assertEqual(geo.parse_geo(json.loads('{"query": "2.2.2.2", "countryCode": "ro", '
                                                  '"country": "Romania"}')), ("2.2.2.2", "RO", None))
        self.assertEqual(geo.parse_geo({"ip": "3.3.3.3", "country": "Romania", "country_iso": "RO"})[1], "RO")


if __name__ == "__main__":
    unittest.main()
