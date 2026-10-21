import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk

    tk.Tk().destroy()
    HAVE_TK = True
except Exception:  # no tkinter or no display
    HAVE_TK = False

from neuvpn import geo, tor
from tests.test_tor import FAKE_TOR


@unittest.skipUnless(HAVE_TK, "tkinter/display not available")
class GuiTest(unittest.TestCase):
    def setUp(self):
        from neuvpn import gui

        self.gui = gui
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.bundle = base / "tor-bundle"
        (self.bundle / "tor").mkdir(parents=True)
        (self.bundle / "data").mkdir()
        (self.bundle / "data" / "geoip").write_text("")
        (self.bundle / "data" / "geoip6").write_text("")
        self.status = base / "status.json"
        env = {"NEUVPN_DIR": str(base / "data"), "NEUVPN_TOR_BUNDLE": str(self.bundle),
               "NEUVPN_GUI_STATUS": str(self.status)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        lookup = mock.patch.object(geo, "lookup", return_value=("185.1.2.3", "RO", "Bucharest"))
        self.lookup = lookup.start()
        self.addCleanup(lookup.stop)
        self.root = tk.Tk()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        tor.stop(tor.TorPaths(Path(os.environ["NEUVPN_DIR"]) / "tor"))
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def fake_tor(self, mode="ok"):
        path = self.bundle / "tor" / "tor"
        path.write_text(FAKE_TOR.format(python=sys.executable, mode=mode))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def wait_for(self, app, state, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.root.update()
            if app.state == state and not app.busy:
                return
            time.sleep(0.05)
        self.fail(f"Zustand {state!r} nicht erreicht (ist {app.state!r}, {app.info})")

    def test_on_new_ip_off(self):
        self.fake_tor()
        app = self.gui.App(self.root)
        self.assertEqual(app.state, "off")
        self.assertEqual(app.button.cget("text"), "Einschalten")
        app.toggle()
        self.wait_for(app, "on")
        self.assertEqual(app.title.cget("text"), "An – Rumänien")
        self.assertIn("185.1.2.3, Bucharest", app.detail.cget("text"))
        self.assertEqual(app.button.cget("text"), "Ausschalten")
        self.assertEqual(json.loads(self.status.read_text())["state"], "on")
        torrc = app.paths.torrc.read_text()
        self.assertIn("ExitNodes {ro}", torrc)
        self.assertIn(f'GeoIPFile "{self.bundle / "data" / "geoip"}"', torrc)  # bundled tor
        self.assertTrue(tor.running_pid(app.paths))

        app.new_ip()  # fake tor has no control port: must not crash, IP is checked again
        self.wait_for(app, "on")
        self.assertGreaterEqual(self.lookup.call_count, 2)

        app.toggle()
        self.wait_for(app, "off")
        self.assertIsNone(tor.running_pid(app.paths))
        self.assertEqual(app.button.cget("text"), "Einschalten")

    def test_cancel_while_connecting(self):
        self.fake_tor("hang")
        app = self.gui.App(self.root)
        app.toggle()
        self.wait_for_connecting(app)
        self.assertEqual(app.button.cget("text"), "Abbrechen")
        self.assertEqual(str(app.button.cget("state")), "normal")
        app.toggle()
        self.wait_for(app, "off")
        self.assertIsNone(tor.running_pid(app.paths))

    def wait_for_connecting(self, app):
        deadline = time.time() + 10
        while time.time() < deadline and not (app.state == "connecting" and tor.running_pid(app.paths)):
            self.root.update()
            time.sleep(0.05)
        self.assertEqual(app.state, "connecting")

    def test_error_is_shown(self):
        self.fake_tor("crash")
        app = self.gui.App(self.root)
        app.toggle()
        self.wait_for(app, "error")
        self.assertIn("Could not bind", app.detail.cget("text"))
        self.assertEqual(app.button.cget("text"), "Nochmal versuchen")

    def test_closing_the_window_switches_off(self):
        self.fake_tor()
        app = self.gui.App(self.root)
        app.toggle()
        self.wait_for(app, "on")
        app.quit()
        self.assertIsNone(tor.running_pid(app.paths))
        self.assertEqual(json.loads(self.status.read_text())["state"], "closed")

    def test_share_shows_phone_settings(self):
        self.fake_tor()
        with mock.patch.object(tor, "lan_addresses", return_value=["192.168.1.50"]):
            app = self.gui.App(self.root)
            app.share.set(True)
            app.toggle()
            self.wait_for(app, "on")
        self.assertIn("Server 192.168.1.50   Port 9056", app.share_info.cget("text"))
        self.assertIn("SocksPort 0.0.0.0:9055", app.paths.torrc.read_text())
        self.assertEqual(str(app.share_box.cget("state")), "disabled")  # only changeable when off
        app.toggle()
        self.wait_for(app, "off")


if __name__ == "__main__":
    unittest.main()
