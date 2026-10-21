import json
import os
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import http.server
import unittest
from pathlib import Path
from unittest import mock

from neuvpn import geo, tor
from tests.test_cli import run

# Stand-in for the tor binary: reports bootstrap progress on stdout (like real
# tor with "Log notice stdout") and runs until terminated.
FAKE_TOR = r'''#!{python}
import signal, sys, time
assert "Log notice stdout" in open(sys.argv[sys.argv.index("-f") + 1]).read()
if "{mode}" == "crash":
    print("[err] Could not bind to 127.0.0.1:9055", flush=True)
    sys.exit(1)
signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
import os
marker = os.path.join(os.path.dirname(sys.argv[sys.argv.index("-f") + 1]), "stalled-once")
if "{mode}" == "stall-once" and not os.path.exists(marker):
    open(marker, "w").close()
    print("[notice] Bootstrapped 50% (loading_descriptors): x", flush=True)
    while True:
        time.sleep(1)
for p in (0, 50, 100):
    print(f"[notice] Bootstrapped {{p}}% (x): x", flush=True)
    if "{mode}" == "hang" and p == 50:
        break
    time.sleep(0.1)
while True:
    time.sleep(1)
'''


class TorrcTest(unittest.TestCase):
    def test_romania_exit_only(self):
        paths = tor.TorPaths(Path("/tmp/x y"))
        torrc = tor.build_torrc(paths, "RO")
        self.assertIn("ExitNodes {ro}", torrc)
        self.assertIn("StrictNodes 1", torrc)
        self.assertIn("SocksPort 127.0.0.1:9055", torrc)
        self.assertIn("# neuvpn-http-proxy 127.0.0.1:9056", torrc)
        self.assertNotIn("HTTPTunnelPort", torrc)
        self.assertEqual(tor.torrc_ports(torrc), {"socks": ("127.0.0.1", 9055),
                                                  "http": ("127.0.0.1", 9056),
                                                  "control": ("127.0.0.1", 9057)})
        self.assertIn('DataDirectory "/tmp/x y/tor-data"', torrc)
        self.assertNotIn("SocksPolicy", torrc)

    def test_share_restricts_to_private_networks(self):
        torrc = tor.build_torrc(tor.TorPaths(Path("/t")), "ro", share=True)
        self.assertIn("SocksPort 0.0.0.0:9055", torrc)
        self.assertIn("SocksPolicy accept 192.168.0.0/16", torrc)
        self.assertTrue(torrc.rstrip().endswith("SocksPolicy reject *"))
        self.assertIn("ControlPort 127.0.0.1:9057", torrc)  # control stays local

    def test_invalid_country(self):
        for bad in ("", "ROU", "1x"):
            with self.assertRaises(tor.TorError):
                tor.build_torrc(tor.TorPaths(Path("/t")), bad)

    def test_bootstrap_percent(self):
        log = "a\n[notice] Bootstrapped 5% (conn): x\n[notice] Bootstrapped 89% (ap_conn): y\n"
        self.assertEqual(tor.bootstrap_percent(log), 89)
        self.assertEqual(tor.bootstrap_percent(""), 0)


class TorProcessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = tor.TorPaths(Path(self.tmp.name) / "tor dir")
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()

    def _fake_tor(self, mode="ok"):
        path = self.bin / "tor"
        path.write_text(FAKE_TOR.format(python=sys.executable, mode=mode))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return mock.patch.object(tor, "find_tor", return_value=str(path))

    def _free_port(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def test_start_reports_progress_and_stop(self):
        port = self._free_port()
        http_port = self._free_port()
        torrc = tor.build_torrc(self.paths, "RO", port, http_port, port)
        seen = []
        with self._fake_tor():
            pid = tor.start(self.paths, torrc, timeout=10, progress=seen.append)
        self.assertEqual(seen[-1], 100)
        self.assertEqual(tor.running_pid(self.paths), pid)
        # the HTTP proxy for phones runs next to tor and accepts connections
        socket.create_connection(("127.0.0.1", http_port), timeout=5).close()
        http_pid = int(self.paths.http_pid.read_text())
        with self.assertRaises(tor.TorError):
            tor.start(self.paths, torrc)  # already running
        self.assertTrue(tor.stop(self.paths))
        self.assertIsNone(tor.running_pid(self.paths))
        self.assertFalse(self.paths.http_pid.exists())
        with self.assertRaises(ConnectionRefusedError):
            socket.create_connection(("127.0.0.1", http_port), timeout=5)
        try:
            os.kill(http_pid, 0)
            os.waitpid(http_pid, os.WNOHANG)  # reap if it is our zombie child
        except (ProcessLookupError, ChildProcessError):
            pass
        self.assertFalse(tor.stop(self.paths))

    def test_crash_and_timeout_are_reported(self):
        port = self._free_port()
        torrc = tor.build_torrc(self.paths, "RO", port, self._free_port(), port)
        with self._fake_tor("crash"), self.assertRaises(tor.TorError) as ctx:
            tor.start(self.paths, torrc, timeout=10)
        self.assertIn("Could not bind", str(ctx.exception))
        with self._fake_tor("hang"), self.assertRaises(tor.TorError):
            tor.start(self.paths, torrc, timeout=1)
        self.assertIsNone(tor.running_pid(self.paths))

    def test_stalled_bootstrap_is_restarted(self):
        port = self._free_port()
        torrc = tor.build_torrc(self.paths, "RO", port, self._free_port(), port)
        seen, restarts = [], []
        with self._fake_tor("stall-once"):
            tor.start(self.paths, torrc, timeout=20, progress=seen.append, stall_timeout=1,
                      on_restart=restarts.append)
        self.assertEqual(restarts, [50])
        self.assertEqual(seen[-1], 100)
        tor.stop(self.paths)

    def test_busy_port_is_detected(self):
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            torrc = tor.build_torrc(self.paths, "RO", port, port + 1, port + 2)
            with self._fake_tor(), self.assertRaises(tor.TorError) as ctx:
                tor.start(self.paths, torrc)
        self.assertIn(str(port), str(ctx.exception))


@unittest.skipUnless(shutil.which("tor"), "tor not installed")
class RealTorTest(unittest.TestCase):
    """Starts the real tor binary with our torrc (path with spaces, like macOS home folders)."""

    def test_real_tor_accepts_config_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = tor.TorPaths(Path(tmp) / "Mein Ordner" / "tor")
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            torrc = tor.build_torrc(paths, "RO", port, port + 1, port + 2)
            try:
                tor.start(paths, torrc, timeout=4)
                tor.stop(paths)  # bootstrapped already (fast network) – fine too
            except tor.TorError as exc:
                # no internet for tor here: it must still be running and logging, not crash
                self.assertIn("nicht rechtzeitig", str(exc))
            log = paths.log.read_text()
            self.assertIn("Opened Socks listener", log)
            self.assertIn("Bootstrapped", log)
            self.assertIsNone(tor.running_pid(paths))


class MacProxyTest(unittest.TestCase):
    LISTING = "An asterisk (*) denotes that a network service is disabled.\nWi-Fi\n*Thunderbolt Bridge\nUSB LAN\n"

    def test_services_and_commands(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            out = self.LISTING if "-listallnetworkservices" in cmd else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(tor.subprocess, "run", fake_run):
            paths = tor.TorPaths(Path(tmp))
            self.assertEqual(tor.set_mac_system_proxy(paths, 9055, 9056, True), ["Wi-Fi", "USB LAN"])
            self.assertIn(["networksetup", "-setsocksfirewallproxy", "Wi-Fi", "127.0.0.1", "9055"], calls)
            self.assertIn(["networksetup", "-setsecurewebproxystate", "USB LAN", "on"], calls)
            calls.clear()
            self.assertEqual(tor.set_mac_system_proxy(paths, 0, 0, False), ["Wi-Fi", "USB LAN"])
            self.assertEqual(
                calls,
                [["networksetup", "-setsocksfirewallproxystate", "Wi-Fi", "off"],
                 ["networksetup", "-setsecurewebproxystate", "Wi-Fi", "off"],
                 ["networksetup", "-setsocksfirewallproxystate", "USB LAN", "off"],
                 ["networksetup", "-setsecurewebproxystate", "USB LAN", "off"]],
            )
            self.assertFalse(paths.proxy_state.exists())

    def test_failed_commands_ask_for_password_once(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            ok = cmd[0] == "osascript"  # plain networksetup fails ("requires admin")
            return subprocess.CompletedProcess(cmd, 0 if ok else 14, stdout="", stderr="")

        with mock.patch.object(tor.subprocess, "run", fake_run), \
                mock.patch.object(tor.sys.stdin, "isatty", return_value=False):
            results = tor._networksetup_all([["-a", "Wi-Fi"], ["-b", "it's"]])
        self.assertEqual(results, [True, True])
        self.assertEqual(calls[:2], [["networksetup", "-a", "Wi-Fi"], ["networksetup", "-b", "it's"]])
        self.assertEqual(len(calls), 3)  # one password dialog for both commands
        self.assertEqual(calls[2][:2], ["osascript", "-e"])
        self.assertEqual(calls[2][2], "do shell script \"'networksetup' '-a' 'Wi-Fi' && "
                                      "'networksetup' '-b' 'it'\\\\''s'\" with administrator privileges")

    def test_recover_proxy_after_crash(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(tor, "is_mac", return_value=True), \
                mock.patch.object(tor, "set_mac_system_proxy") as setp:
            paths = tor.TorPaths(Path(tmp))
            self.assertFalse(tor.recover_system_proxy(paths))  # nothing to do
            paths.proxy_state.write_text("Wi-Fi")
            self.assertTrue(tor.recover_system_proxy(paths))  # proxy on, tor gone
            setp.assert_called_once_with(paths, 0, 0, enable=False)


class _GeoHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"ip": "185.1.2.3", "country": "RO", "city": "Bucharest", "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _fake_socks_server(connections):
    """Minimal SOCKS5 server (no auth, CONNECT by domain name) relaying to localhost."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()

    def pipe(a, b):
        try:
            while data := a.recv(4096):
                b.sendall(data)
        except OSError:
            pass
        finally:
            for s in (a, b):  # shutdown, not just close: the other thread still blocks in recv
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def serve():
        while True:
            try:
                client, _ = srv.accept()
            except OSError:
                return
            assert client.recv(3) == b"\x05\x01\x00"
            client.sendall(b"\x05\x00")
            head = client.recv(5)
            assert head[:4] == b"\x05\x01\x00\x03"
            host = client.recv(head[4]).decode()
            port = struct.unpack(">H", client.recv(2))[0]
            connections.append((host, port))
            upstream = socket.create_connection(("127.0.0.1", port))
            client.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("127.0.0.1") + struct.pack(">H", 1080))
            threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
            threading.Thread(target=pipe, args=(upstream, client), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return srv


class SocksGeoTest(unittest.TestCase):
    def test_lookup_through_socks5(self):
        web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _GeoHandler)
        threading.Thread(target=web.serve_forever, daemon=True).start()
        self.addCleanup(web.shutdown)
        connections = []
        socks = _fake_socks_server(connections)
        self.addCleanup(socks.close)
        url = f"http://geo.example:{web.server_port}/json?x=1"
        with mock.patch("socket.create_connection", wraps=socket.create_connection) as cc:
            result = geo.lookup(urls=[url], socks=socks.getsockname())
        self.assertEqual(result, ("185.1.2.3", "RO", "Bucharest"))
        # the hostname is resolved by the proxy (no local DNS lookup / leak)
        self.assertEqual(connections, [("geo.example", web.server_port)])
        self.assertEqual(cc.call_args_list[0].args[0], socks.getsockname())

    def test_cli_check_with_socks(self):
        with mock.patch.object(geo, "lookup", return_value=("185.1.2.3", "RO", None)) as lookup:
            code, out, _ = run("check", "--socks", "127.0.0.1:9055", "--expect", "RO")
        self.assertEqual(code, 0)
        self.assertEqual(lookup.call_args.kwargs["socks"], ("127.0.0.1", 9055))
        self.assertEqual(run("check", "--socks", "nonsense")[0], 2)


class NewIdentityTest(unittest.TestCase):
    def test_newnym_via_control_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = tor.TorPaths(Path(tmp))
            paths.data.mkdir()
            (paths.data / "control_auth_cookie").write_bytes(b"\x01\x02")
            srv = socket.socket()
            srv.bind(("127.0.0.1", 0))
            srv.listen()
            received = []

            def serve():
                conn, _ = srv.accept()
                received.append(conn.recv(4096))
                conn.sendall(b"250 OK\r\n250 OK\r\n250 closing connection\r\n")
                conn.close()

            t = threading.Thread(target=serve)
            t.start()
            tor.new_identity(paths, srv.getsockname()[1])
            t.join()
            srv.close()
        self.assertEqual(received[0], b"AUTHENTICATE 0102\r\nSIGNAL NEWNYM\r\nQUIT\r\n")


class TorCliTest(unittest.TestCase):
    def test_stop_and_status_when_not_running(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"NEUVPN_DIR": tmp}):
            code, out, _ = run("tor", "stop")
            self.assertEqual(code, 0)
            self.assertIn("lief nicht", out)
            code, out, _ = run("tor", "status")
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
