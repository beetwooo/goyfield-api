"""
Goyfield.moe Records Scraper + Promo Codes
"""

import argparse
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Output directory
DOCS_DIR = "docs"
os.makedirs(DOCS_DIR, exist_ok=True)

# Banner config
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
    print(f"  [debug] {path}")


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


# Improved Promo Codes Extractor
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

                for offset in range(12):
                    if i + offset >= len(lines):
                        break
                    rline = lines[i + offset]
                    if re.match(r'^\d', rline):
                        amount = rline.strip()
                        context = " ".join(lines[max(0, i+offset-4):i+offset+4]).lower()
                        name = "Unknown"
                        if any(x in context for x in ["oro", "beryl"]):
                            name = "Oroberyl"
                        elif any(x in context for x in ["t-cred", "tcred", "cred"]):
                            name = "T-Creds"
                        elif "combat" in context:
                            name = "Combat Record"
                        elif any(x in context for x in ["insp", "kit"]):
                            name = "Arms INSP Kit"
                        promo_data[code][name] = amount
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


# GET_STATS_JS and other original functions
GET_STATS_JS = r"""
() => {
    const raw = (document.body.innerText || '').split('\n')
        .map(l => l.trim()).filter(l => l.length > 0);

    function findNth(n, ...labels) {
        let found = 0;
        for (let i = 0; i < raw.length; i++) {
            for (const label of labels) {
                const sameLine = raw[i].startsWith(label + ' ') || raw[i].startsWith(label + '\t');
                const nextLine = raw[i] === label;
                if (sameLine || nextLine) {
                    found++;
                    if (found === n) {
                        return sameLine ? raw[i].slice(label.length).trim()
                                       : (i + 1 < raw.length ? raw[i + 1] : null);
                    }
                    break;
                }
            }
        }
        return null;
    }

    const rate6  = findNth(1, 'Rate');
    const count6 = findNth(1, 'Count');
    const pity6  = findNth(1, 'Median Pity', 'Median');
    const won6   = findNth(1, 'Won 50:50', 'Won 25:75', 'Won');
    const rate5  = findNth(2, 'Rate');
    const count5 = findNth(2, 'Count');

    function find(...labels) { return findNth(1, ...labels); }

    let featured_img = null;
    for (const img of document.querySelectorAll('img')) {
        const src = img.getAttribute('src') || '';
        if (src.includes('/operators/preview/') || src.includes('/weapons/preview/')) {
            featured_img = src.startsWith('http') ? src : 'https://goyfield.moe' + src;
            break;
        }
    }

    return {
        total_users:    find('Total Users'),
        total_pulls:    find('Total Pulls'),
        oroberyl_spent: find('Oroberyl Spent'),
        total_obtained: find('Total Obtained', 'TOTAL OBTAINED'),
        rate6, count6, pity6, won6,
        rate5, count5,
        featured_img,
        _raw: raw,
    };
}
"""

def get_stats(page) -> dict:
    return page.evaluate(GET_STATS_JS)


def build_entry(raw: dict, include_obtained: bool = False, debug: bool = False) -> dict:
    entry = {
        "Total Users":    clean(raw.get("total_users")),
        "Total Pulls":    clean(raw.get("total_pulls")),
        "Oroberyl Spent": clean(raw.get("oroberyl_spent")),
        "6-Star": {
            "Rate":        raw.get("rate6"),
            "Count":       clean(raw.get("count6")),
            "Median Pity": clean(raw.get("pity6")),
            "Won":         raw.get("won6"),
        },
        "5-Star": {
            "Rate":  raw.get("rate5"),
            "Count": clean(raw.get("count5")),
        },
    }
    if include_obtained:
        entry["Total Obtained"] = clean(raw.get("total_obtained"))
        entry["Featured Image"] = raw.get("featured_img")
    return entry


def js_click_by_text(page, target: str) -> bool:
    return page.evaluate("""(target) => {
        for (const el of document.querySelectorAll('*')) {
            if (el.children.length > 0) continue;
            if ((el.innerText || '').trim() === target) { el.click(); return true; }
        }
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === target) { el.click(); return true; }
        }
        return false;
    }""", target)


def get_banner_type_button(page):
    for label in ALL_BANNER_TYPES:
        btn = page.locator(f'button:has-text("{label}")').first
        try:
            if btn.is_visible(timeout=1000):
                return btn, label
        except Exception:
            pass
    raise RuntimeError("Could not find the banner-type selector button on the page")


def switch_banner_type(page, target: str, debug: bool):
    for attempt in range(3):
        btn, current = get_banner_type_button(page)
        if current == target:
            print(f"  Already on: {target}")
            return
        print(f"  Switching '{current}' → '{target}' (attempt {attempt + 1})")
        btn.click()
        page.wait_for_timeout(2500)
        clicked = js_click_by_text(page, target)
        if clicked:
            page.wait_for_timeout(3000)
            try:
                _, new_current = get_banner_type_button(page)
                if new_current == target:
                    print(f"  Switched to: {target}")
                    return
            except Exception:
                pass
        else:
            print(f"  '{target}' not in DOM, retrying…")
            page.wait_for_timeout(2000)
    screenshot(page, f"switch_failed_{target.replace(' ', '_')}", debug)
    raise RuntimeError(f"Could not switch to '{target}' after 3 attempts")


def get_sub_banner_trigger(page):
    for btn in page.locator("button").filter(has=page.locator("img")).all():
        try:
            text = btn.inner_text().strip()
            if not any(t in text for t in ALL_BANNER_TYPES) and text:
                return btn
        except Exception:
            pass
    raise RuntimeError("Could not find sub-banner trigger button")


def get_sub_banner_names(page, default_name: str) -> list[str]:
    return page.evaluate("""(def) => {
        const names = [];
        const seen = new Set();
        for (const el of document.querySelectorAll('li, [role="option"], [role="menuitem"]')) {
            const t = (el.innerText || '').trim();
            if (t && t.length > 1 && !seen.has(t)) {
                seen.add(t);
                names.push(t);
            }
        }
        return names;
    }""", default_name)


def scrape_sub_banners(page, debug: bool) -> dict:
    result = {}
    trigger = get_sub_banner_trigger(page)
    default_name = trigger.inner_text().strip()
    print(f"  Default sub-banner: {default_name}")

    screenshot(page, default_name, debug)
    result[default_name] = build_entry(get_stats(page), include_obtained=True, debug=debug)
    print(f"  {default_name}")

    trigger.click()
    page.wait_for_timeout(2000)
    all_names = get_sub_banner_names(page, default_name)
    other_names = [n for n in all_names if n != default_name]
    print(f"  Other sub-banners: {other_names}")

    for name in other_names:
        try:
            if not page.locator("li").first.is_visible():
                trigger = get_sub_banner_trigger(page)
                trigger.click()
                page.wait_for_timeout(2000)
            if not js_click_by_text(page, name):
                for li in page.locator("li").all():
                    if name in li.inner_text():
                        li.click()
                        break
            page.wait_for_timeout(3000)
            screenshot(page, name, debug)
            result[name] = build_entry(get_stats(page), include_obtained=True, debug=debug)
            print(f"  {name}")
        except Exception as e:
            print(f"  Error on {name}: {e}")
            screenshot(page, f"error_{name}", debug)
            result[name] = None
    return result


# Main Scrape Function
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

        # Banner scraping
        print(f"Loading https://goyfield.moe/records/global …")
        page.goto("https://goyfield.moe/records/global", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        try:
            for label in ("Accept", "Decline", "Accept all", "Got it"):
                btn = page.get_by_role("button", name=label).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    page.wait_for_timeout(1000)
                    print(f"  Cookie banner dismissed")
                    break
        except Exception:
            pass

        screenshot(page, "initial", debug)

        # Single banners
        for banner_label, filename in SINGLE_BANNERS.items():
            print(f"\n{'='*60}")
            print(f"  {banner_label} (single)")
            print(f"{'='*60}")
            try:
                switch_banner_type(page, banner_label, debug)
                page.wait_for_timeout(2000)
                screenshot(page, banner_label, debug)
                data = {banner_label: build_entry(get_stats(page), debug=debug)}
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  Saved {filename}")
            except Exception as e:
                print(f"  Error: {e}")
                screenshot(page, f"error_{banner_label}", debug)
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump({"error": str(e)}, f, indent=2)

        # Multi banners
        for banner_label, filename in MULTI_BANNERS.items():
            print(f"\n{'='*60}")
            print(f"  {banner_label} (multi)")
            print(f"{'='*60}")
            try:
                switch_banner_type(page, banner_label, debug)
                page.wait_for_timeout(2000)
                sub_data = scrape_sub_banners(page, debug)
                data = {banner_label: sub_data}
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  Saved {filename}")
            except Exception as e:
                print(f"  Error: {e}")
                screenshot(page, f"error_{banner_label}", debug)
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump({"error": str(e)}, f, indent=2)

        browser.close()

    print("\nDone!")


def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        print("Playwright WORKS")
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scrape goyfield.moe")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    if args.test:
        test()
    else:
        scrape(debug=args.debug)
