"""
Goyfield.moe Records Scraper
============================
Based on the original working scraper structure.

Setup:
    pip install playwright
    playwright install chromium

Run:
    python scraper.py
    python scraper.py --debug    # saves screenshots on each step
"""

import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Banner config ─────────────────────────────────────────────────────────────

# Single-view banners (no sub-banner dropdown)
SINGLE_BANNERS = {
    "Basic Headhunting":        "basic-headhunting.json",
    "New Horizons Headhunting": "new-horizons-headhunting.json",
}

# Multi sub-banner types (have a character/weapon picker)
MULTI_BANNERS = {
    "Special Headhunting": "special-headhunting.json",
    "Event Weapon":        "event-weapon.json",
    "Standard Weapon":     "standard-weapon.json",
}

ALL_BANNER_TYPES = list(SINGLE_BANNERS.keys()) + list(MULTI_BANNERS.keys())

DEBUG_DIR = "debug_screenshots"


# ── Debug helper ──────────────────────────────────────────────────────────────

def screenshot(page, name: str, debug: bool):
    if not debug:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  [debug] {path}")


# ── Value cleaner ─────────────────────────────────────────────────────────────

def clean(v):
    """'2,342' → 2342, '1.567%' → '1.567%', None → None"""
    if v is None:
        return None
    s = str(v).replace(",", "").replace(" ", "").replace("\xa0", "").replace("\u202f", "").strip()
    if not s or s in ("-", "—", "N/A"):
        return None
    if "%" in s:
        return s  # keep percentages as strings
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return v  # return original if unparseable


# ── DOM scraping (runs inside the browser) ────────────────────────────────────

GET_STATS_JS = r"""
() => {
    const raw = (document.body.innerText || '').split('\n')
        .map(l => l.trim()).filter(l => l.length > 0);

    // Find the Nth occurrence of a label (same-line or next-line value)
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
                    break; // matched this label, move to next line
                }
            }
        }
        return null;
    }

    // 6-star = 1st occurrence of each label
    // 5-star = 2nd occurrence of each label
    const rate6  = findNth(1, 'Rate');
    const count6 = findNth(1, 'Count');
    const pity6  = findNth(1, 'Median Pity', 'Median');
    const won6   = findNth(1, 'Won 50:50', 'Won 25:75', 'Won');
    const rate5  = findNth(2, 'Rate');
    const count5 = findNth(2, 'Count');

    // Generic single-occurrence finder
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
    raw = page.evaluate(GET_STATS_JS)
    return raw


def build_entry(raw: dict, include_obtained: bool = False, debug: bool = False) -> dict:
    if debug:
        print(f"    [raw sample] {raw.get('_raw', [])[:30]}")
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
        entry["Total Obtained"]   = clean(raw.get("total_obtained"))
        entry["Featured Image"]   = raw.get("featured_img")
    return entry


# ── Click helpers ─────────────────────────────────────────────────────────────

def js_click_by_text(page, target: str) -> bool:
    """Click the first element whose trimmed innerText exactly matches target."""
    return page.evaluate("""(target) => {
        // Prefer leaf nodes (most precise)
        for (const el of document.querySelectorAll('*')) {
            if (el.children.length > 0) continue;
            if ((el.innerText || '').trim() === target) { el.click(); return true; }
        }
        // Fallback: any element
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === target) { el.click(); return true; }
        }
        return false;
    }""", target)


# ── Banner type switcher ──────────────────────────────────────────────────────

def get_banner_type_button(page):
    """Return the button that shows the currently selected banner type."""
    for label in ALL_BANNER_TYPES:
        btn = page.locator(f'button:has-text("{label}")').first
        try:
            if btn.is_visible(timeout=1000):
                return btn, label
        except Exception:
            pass
    raise RuntimeError("Could not find the banner-type selector button on the page")


def switch_banner_type(page, target: str, debug: bool):
    """Switch to a banner type by clicking its option in the type picker."""
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
                    print(f"  ✓ Switched to: {target}")
                    return
                print(f"  Still on '{new_current}', retrying…")
            except Exception:
                pass
        else:
            print(f"  '{target}' not in DOM, retrying…")
            page.wait_for_timeout(2000)

    screenshot(page, f"switch_failed_{target.replace(' ', '_')}", debug)
    raise RuntimeError(f"Could not switch to '{target}' after 3 attempts")


# ── Sub-banner helpers ────────────────────────────────────────────────────────

def get_sub_banner_trigger(page):
    """
    Find the sub-banner picker button.
    It has an <img> inside and its text is NOT one of the top-level banner types.
    """
    for btn in page.locator("button").filter(has=page.locator("img")).all():
        try:
            text = btn.inner_text().strip()
            if not any(t in text for t in ALL_BANNER_TYPES) and text:
                return btn
        except Exception:
            pass
    raise RuntimeError("Could not find sub-banner trigger button")


def get_sub_banner_names(page, default_name: str) -> list[str]:
    """Open the sub-banner dropdown and collect all option names."""
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
    """Scrape every sub-banner for the currently active banner type."""
    result = {}

    trigger = get_sub_banner_trigger(page)
    default_name = trigger.inner_text().strip()
    print(f"  Default sub-banner: {default_name}")

    # Scrape the default (already visible) sub-banner
    screenshot(page, default_name, debug)
    result[default_name] = build_entry(get_stats(page), include_obtained=True, debug=debug)
    print(f"  ✓ {default_name}")

    # Open the dropdown and collect other names
    trigger.click()
    page.wait_for_timeout(2000)
    all_names = get_sub_banner_names(page, default_name)
    other_names = [n for n in all_names if n != default_name]
    print(f"  Other sub-banners: {other_names}")

    for name in other_names:
        try:
            # Re-open dropdown if closed
            if not page.locator("li").first.is_visible():
                trigger = get_sub_banner_trigger(page)
                trigger.click()
                page.wait_for_timeout(2000)

            # Click the option
            if not js_click_by_text(page, name):
                # Fallback: find a <li> containing the name
                for li in page.locator("li").all():
                    if name in li.inner_text():
                        li.click()
                        break

            page.wait_for_timeout(3000)
            screenshot(page, name, debug)
            result[name] = build_entry(get_stats(page), include_obtained=True, debug=debug)
            print(f"  ✓ {name}")

        except Exception as e:
            print(f"  ✗ {name}: {e}")
            screenshot(page, f"error_{name}", debug)
            result[name] = None

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape(debug: bool):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_extra_http_headers({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })

        print(f"Loading https://goyfield.moe/records/global …")
        page.goto("https://goyfield.moe/records/global", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        # ── Dismiss cookie banner if present ─────────────────────────────────
        try:
            for label in ("Accept", "Decline", "Accept all", "Got it"):
                btn = page.get_by_role("button", name=label).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    page.wait_for_timeout(1000)
                    print(f"  [cookie] Dismissed via '{label}'")
                    break
        except Exception:
            pass

        screenshot(page, "initial", debug)

        # ── Single banners ────────────────────────────────────────────────────
        for banner_label, filename in SINGLE_BANNERS.items():
            print(f"\n{'━'*60}")
            print(f"  ▶ {banner_label} (single)")
            print(f"{'━'*60}")
            try:
                switch_banner_type(page, banner_label, debug)
                page.wait_for_timeout(2000)
                screenshot(page, banner_label, debug)

                data = {banner_label: build_entry(get_stats(page), debug=debug)}
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  💾 Saved → {filename}")

            except Exception as e:
                print(f"  ✗ Error: {e}")
                screenshot(page, f"error_{banner_label}", debug)
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump({"error": str(e)}, f, indent=2)

        # ── Multi sub-banner banners ───────────────────────────────────────────
        for banner_label, filename in MULTI_BANNERS.items():
            print(f"\n{'━'*60}")
            print(f"  ▶ {banner_label} (multi)")
            print(f"{'━'*60}")
            try:
                switch_banner_type(page, banner_label, debug)
                page.wait_for_timeout(2000)

                sub_data = scrape_sub_banners(page, debug)
                data = {banner_label: sub_data}
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  💾 Saved → {filename}")

            except Exception as e:
                print(f"  ✗ Error: {e}")
                screenshot(page, f"error_{banner_label}", debug)
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump({"error": str(e)}, f, indent=2)

        browser.close()

    print("\n✅ Done! Output files:")
    for fn in list(SINGLE_BANNERS.values()) + list(MULTI_BANNERS.values()):
        if os.path.exists(fn):
            print(f"   {fn}  ({os.path.getsize(fn)} bytes)")


def test():
    """Quick sanity-check: just launches Chromium and exits."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        print("WORKS")
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scrape goyfield.moe/records/global")
    ap.add_argument("--debug", action="store_true", help="Save screenshots at each step")
    ap.add_argument("--test",  action="store_true", help="Playwright sanity check and exit")
    args = ap.parse_args()

    if args.test:
        test()
    else:
        scrape(debug=args.debug)