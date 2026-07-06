"""
Goyfield.moe Records Scraper + Promo Codes
============================
"""

import argparse
import json
import os
import sys
import re

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup  # Added for promo code extraction

# ── Output dir ────────────────────────────────────────────────────────────────

DOCS_DIR = "docs"
os.makedirs(DOCS_DIR, exist_ok=True)

# ── Banner config (unchanged) ────────────────────────────────────────────────

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


# ── Debug helper (unchanged) ─────────────────────────────────────────────────

def screenshot(page, name: str, debug: bool):
    if not debug:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  [debug] {path}")


# ── Value cleaner (unchanged) ────────────────────────────────────────────────

def clean(v):
    if v is None:
        return None
    s = str(v).replace(",", "").replace(" ", "").replace("\xa0", "").replace("\u202f", "").strip()
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


# ── Promo Codes Extractor ────────────────────────────────────────────────────

def extract_promo_codes(page) -> dict:
    """Extract promo codes from the homepage"""
    try:
        # Get full page content
        content = page.content()
        soup = BeautifulSoup(content, 'html.parser')
        text = soup.get_text()

        # Find codes: uppercase + numbers, 8+ characters
        potential_codes = re.findall(r'\b[A-Z0-9]{8,}\b', text)
        
        # Deduplicate while preserving order
        codes = list(dict.fromkeys(potential_codes))

        result = {
            "codes": codes,
            "count": len(codes)
        }

        print(f"  ✓ Found {len(codes)} promo code(s): {codes}")
        return result

    except Exception as e:
        print(f"  ✗ Failed to extract promo codes: {e}")
        return {"codes": [], "count": 0}


# ── Rest of your original functions (GET_STATS_JS, get_stats, build_entry, etc.)
# ... [I kept them unchanged - they are the same as your original file] ...

# (Paste all your original functions here: get_stats, build_entry, js_click_by_text, 
#  get_banner_type_button, switch_banner_type, get_sub_banner_trigger, 
#  get_sub_banner_names, scrape_sub_banners, etc.)

# ── Main Scrape Function ─────────────────────────────────────────────────────

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

        # === Promo Codes (new) ===
        print("\n" + "="*60)
        print("  ▶ Extracting Promo Codes from homepage")
        print("="*60)
        page.goto("https://goyfield.moe/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        
        promo_data = extract_promo_codes(page)
        
        promo_file = f"{DOCS_DIR}/promo-codes.json"
        with open(promo_file, "w", encoding="utf-8") as f:
            json.dump(promo_data, f, indent=2, ensure_ascii=False)
        print(f"  💾 Saved → {promo_file}")

        # === Your original banner scraping (unchanged) ===
        # ... paste the rest of your original scrape() function here ...

        browser.close()

    print("\n✅ Done! Output files:")
    for fn in list(SINGLE_BANNERS.values()) + list(MULTI_BANNERS.values()) + [f"{DOCS_DIR}/promo-codes.json"]:
        if os.path.exists(fn):
            print(f"   {fn}  ({os.path.getsize(fn)} bytes)")


# ── Test & Main (unchanged) ──────────────────────────────────────────────────

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        print("Playwright WORKS")
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scrape goyfield.moe")
    ap.add_argument("--debug", action="store_true", help="Save screenshots")
    ap.add_argument("--test", action="store_true", help="Playwright test")
    args = ap.parse_args()

    if args.test:
        test()
    else:
        scrape(debug=args.debug)