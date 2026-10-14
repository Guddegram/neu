"""CI (macOS): open ipinfo.io in real Safari and Chrome and check the country.

Usage: mac_browsers.py RO     -> both browsers must show Romania
       mac_browsers.py !RO    -> both browsers must NOT show Romania (VPN off)
"""

import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By

URL = "https://ipinfo.io/json"


def read_country(driver) -> tuple[str | None, str | None, str]:
    driver.set_page_load_timeout(120)
    for attempt in range(3):
        try:
            driver.get(URL)
            text = driver.find_element(By.TAG_NAME, "body").text
            country = re.search(r'"country"\s*:\s*"([A-Z]{2})"', text)
            if country:
                ip = re.search(r'"ip"\s*:\s*"([^"]+)"', text)
                return country.group(1), ip.group(1) if ip else None, text
        except Exception as exc:  # page load through Tor can time out once
            text = f"{type(exc).__name__}: {exc}"
        time.sleep(5)
    return None, None, text


def main() -> int:
    expect = sys.argv[1]
    negate = expect.startswith("!")
    code = expect.lstrip("!")
    failed = False
    for name, factory in (("Safari", webdriver.Safari), ("Chrome", webdriver.Chrome)):
        driver = factory()
        try:
            country, ip, raw = read_country(driver)
        finally:
            driver.quit()
        ok = (country is not None and country != code) if negate else country == code
        print(f"{'✔' if ok else '✘'} {name}: IP {ip}, Land {country}")
        if not ok:
            print("   Seiteninhalt:", raw[:300])
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
