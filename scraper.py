"""
Goyfield.moe Records Scraper + Promo Codes
"""

import argparse
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

DOCS_DIR = "docs"
os.makedirs(DOCS_DIR, exist_ok=True)

SINGLE_BANNERS = {
    "Basic Headhunting":        f"{DOCS_DIR}/basic-headhunting.json",
    "New Horizons Headhunting": f"{DOCS_DIR}/new-horizons-headhunting.json",
}

MULTI_BANNERS = {
    "Special Headhunting": f"{DOCS_DIR}/special-headhunting.json",
    "Event Weapon":        f"{DOCS_DIR}/event-weapon.json",
    "Standard Weapon":     f"{DOCS_DIR}/standard-weapon.json",
}

ALL_BANNER_TYPES = list(SINGLE_BANNERS.keys()) + list(MULTI_BANNERS.keys())

DEBUG_DIR = "debug_screenshots"


def screenshot(page, name: str, debug: bool):
    if not debug:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, f"{name}.png")
    page.screenshot(path=path, full_page=True)


def clean(v):
    if v is None:
        return None
    s = str(v).replace(",", "").replace(" ", "").strip()
    if not s or s in ("-", "—", "N/A"):
        return None
    if "%" in s:
        return s
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return v


# ── Promo Codes with Reward Names ───────────────────────────────────────────

def extract_promo_codes(page) -> dict:
    try:
        text = page.evaluate("() => document.body.innerText")
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        promo_data = {}
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(r'^[A-Z0-9]{8,}$', line):
                code = line
                promo_data[code] = {}
                i += 1
                reward_idx = 1
                while i < len(lines) and reward_idx <= 8 and not re.match(r'^[A-Z0-9]{8,}$', lines[i]):
                    rline = lines[i]
                    if re.match(r'^\d', rline):
                        amount = rline.strip()
                        name = f"Reward_{reward_idx}"
                        # Look back for name
                        for back in range(1, 7):
                            if i - back >= 0:
                                prev = lines[i - back].lower()
                                if "oro" in prev or "beryl" in prev:
                                    name = "Oroberyl"
                                    break
                                elif "t-cred" in prev or "cred" in prev:
                                    name = "T-Creds"
                                    break
                                elif "combat" in prev:
                                    name = "Combat Record"
                                    break
                                elif "insp" in prev or "kit" in prev:
                                    name = "Arms INSP Kit"
                                    break
                        promo_data[code][name] = amount
                        reward_idx += 1
                    i += 1
                continue
            i += 1

        result = {
            "promo_codes": promo_data,
            "count": len(promo_data)
        }
        print(f"  Found {len(promo_data)} promo codes")
        return result

    except Exception as e:
        print(f"  Promo codes extraction failed: {e}")
        return {"promo_codes": {}, "count": 0}


# ── Main Scrape Function ──────────────────────────────────────────────────────

def scrape(debug: bool):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })

        # Promo Codes
        print("\n=== Extracting Promo Codes + Rewards ===")
        page.goto("https://goyfield.moe/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        promo_data = extract_promo_codes(page)
        with open(f"{DOCS_DIR}/promo-codes.json", "w", encoding="utf-8") as f:
            json.dump(promo_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved promo-codes.json")

        # Your banner scraping code here (copy from your original script)

        browser.close()

    print("\nDone!")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    scrape(debug=args.debug)
