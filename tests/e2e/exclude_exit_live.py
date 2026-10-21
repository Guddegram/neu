"""CI: with real tor running (neuvpn tor start), block the current exit like the app does
when a website locates it in another country, and check that tor really switches."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from neuvpn import geo, tor  # noqa: E402
from neuvpn.config import default_data_dir  # noqa: E402

paths = tor.TorPaths(default_data_dir() / "tor")
socks = ("127.0.0.1", tor.DEFAULT_SOCKS_PORT)
ip1, country1, _ = geo.lookup(socks=socks, timeout=60)
print(f"Ausgang vorher: {ip1} ({country1})")
tor.exclude_exit(paths, ip1)
conf = tor._control(paths, tor.DEFAULT_CONTROL_PORT, ["GETCONF ExcludeExitNodes"])
assert ip1 in conf, conf
print("Tor-Einstellung:", conf.splitlines()[1])
for _ in range(10):
    time.sleep(3)
    ip2, country2, _ = geo.lookup(socks=socks, timeout=60)
    if ip2 != ip1:
        break
print(f"Ausgang nachher: {ip2} ({country2})")
assert ip2 != ip1, "Tor benutzt den gesperrten Ausgang weiter"
assert ip1 in tor.excluded_exits(paths)
assert f"ExcludeExitNodes {ip1}" in tor.build_torrc(paths, "RO")
print("✔ Gesperrter Ausgang wird nicht mehr benutzt und bleibt für den nächsten Start gesperrt")
