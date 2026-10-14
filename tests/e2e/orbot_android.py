"""CI (Android emulator): Orbot exactly like a user does it.

Install Orbot, tap "Connect" (VPN mode), tap "Change exit", choose Romania,
then check the public IP – through Orbot's SOCKS port and in Chrome (VPN mode,
i.e. what every app on the phone sees).
"""

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PKG = "org.torproject.android"
# dialogs that may show up on first start (Android, Orbot, Chrome first-run)
DISMISS = [
    r"Allow", r"OK", r"Got it", r"Skip", r"Next", r"Continue", r"Connect Anyway",
    r"Accept & continue", r"No thanks", r"Use without an account", r"Not now",
]
_last_screen: list[str] = []


def adb(*args: str, check: bool = True, timeout: int = 60) -> str:
    result = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def screen() -> list[tuple[str, int, int]]:
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml", check=False)
    raw = adb("shell", "cat", "/sdcard/ui.xml", check=False)
    try:
        root = ET.fromstring(raw[raw.find("<"):])
    except ET.ParseError:
        return []
    nodes = []
    for node in root.iter("node"):
        label = (node.get("text") or node.get("content-desc") or "").strip()
        bounds = [int(v) for v in re.findall(r"\d+", node.get("bounds", ""))]
        if label and len(bounds) == 4:
            x1, y1, x2, y2 = bounds
            nodes.append((label, (x1 + x2) // 2, (y1 + y2) // 2))
    labels = [n[0] for n in nodes]
    global _last_screen
    if labels != _last_screen:
        print("   Bildschirm:", " | ".join(labels)[:700], flush=True)
        _last_screen = labels
    return nodes


def find(nodes, pattern: str):
    rx = re.compile(pattern, re.IGNORECASE)
    return next((n for n in nodes if rx.fullmatch(n[0])), None)


def tap(node) -> None:
    print(f"   tippe: {node[0]!r}", flush=True)
    adb("shell", "input", "tap", str(node[1]), str(node[2]))


def wait_for(pattern: str, timeout: int, tap_it: bool = True, dismiss=DISMISS, scroll=False):
    deadline = time.time() + timeout
    while time.time() < deadline:
        nodes = screen()
        target = find(nodes, pattern)
        if target:
            if tap_it:
                tap(target)
            return target
        extra = next((n for p in dismiss for n in nodes if re.fullmatch(p, n[0], re.I)), None)
        if extra:
            tap(extra)
        elif scroll:
            adb("shell", "input", "swipe", "540", "1900", "540", "1100", "400")
        time.sleep(2)
    raise TimeoutError(f"'{pattern}' nicht gefunden")


def country_via_socks() -> str | None:
    adb("forward", "tcp:19050", "tcp:9050")
    out = subprocess.run(
        ["curl", "-sS", "--max-time", "60", "--socks5-hostname", "127.0.0.1:19050",
         "https://ipinfo.io/json"],
        capture_output=True, text=True,
    )
    print("   ipinfo über Orbot-SOCKS:", (out.stdout or out.stderr).replace("\n", " ")[:200])
    m = re.search(r'"country"\s*:\s*"([A-Z]{2})"', out.stdout)
    return m.group(1) if m else None


def country_in_chrome() -> str | None:
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d",
        "https://ipinfo.io/json", "-p", "com.android.chrome")
    deadline = time.time() + 120
    while time.time() < deadline:
        nodes = screen()
        text = " ".join(n[0] for n in nodes)
        m = re.search(r'"?country"?\s*:\s*"?([A-Z]{2})"?', text)
        if m:
            return m.group(1)
        extra = next((n for p in DISMISS for n in nodes if re.fullmatch(p, n[0], re.I)), None)
        if extra:
            tap(extra)
        time.sleep(3)
    return None


def main(apk: str) -> int:
    print("== Orbot installieren", flush=True)
    adb("install", "-r", "-g", apk, timeout=300)
    adb("shell", "appops", "set", PKG, "ACTIVATE_VPN", "allow")  # = "OK" im VPN-Dialog

    print("== Orbot öffnen und 'Connect' tippen", flush=True)
    adb("shell", "am", "start", "-n", f"{PKG}/.OrbotActivity")
    wait_for(r"Connect", 120)
    print("== Warten bis verbunden ('Change exit' erscheint)", flush=True)
    wait_for(r"Change exit", 600, tap_it=False, dismiss=[d for d in DISMISS if d != r"Next"])

    before = country_via_socks()
    print(f"   Ausgangsland vor der Auswahl: {before}")

    print("== 'Change exit' › Romania", flush=True)
    wait_for(r"Change exit", 30)
    wait_for(r".*Romania", 60, dismiss=[], scroll=True)
    time.sleep(20)

    for attempt in range(6):
        socks_country = country_via_socks()
        if socks_country == "RO":
            break
        time.sleep(15)
    else:
        print("✘ Orbot-SOCKS kommt nicht aus Rumänien")
        return 1
    print("✔ Orbot (SOCKS) kommt aus Rumänien")

    print("== Chrome auf dem Handy (VPN-Modus: alle Apps)", flush=True)
    chrome = country_in_chrome()
    if chrome != "RO":
        print(f"✘ Chrome zeigt Land {chrome}")
        return 1
    print("✔ Chrome (VPN-Modus) kommt aus Rumänien")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
