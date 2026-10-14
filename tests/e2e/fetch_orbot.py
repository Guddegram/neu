"""CI: download the newest Orbot release APK from GitHub (guardianproject/orbot)."""

import json
import os
import sys
import urllib.request


def pick(assets: list[dict]) -> dict:
    apks = [a for a in assets if a["name"].endswith(".apk")]
    for words in (("universal", "release"), ("x86_64",), ("universal",), ()):
        for asset in apks:
            name = asset["name"].lower()
            if all(w in name for w in words) and "nightly" not in name and "debug" not in name:
                return asset
    raise SystemExit("Kein APK im Release gefunden: " + ", ".join(a["name"] for a in assets))


def main(out: str) -> None:
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    req = urllib.request.Request(
        "https://api.github.com/repos/guardianproject/orbot/releases/latest", headers=headers
    )
    release = json.load(urllib.request.urlopen(req, timeout=60))
    asset = pick(release["assets"])
    print(f"Orbot {release['tag_name']} ({release['published_at']}): {asset['name']}")
    urllib.request.urlretrieve(asset["browser_download_url"], out)


if __name__ == "__main__":
    main(sys.argv[1])
