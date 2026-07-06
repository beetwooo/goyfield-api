"""
Standalone Promo Codes Scraper for goyfield.moe
"""

import re
import json
from playwright.sync_api import sync_playwright

def extract_promo_codes():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        
        print("Loading https://goyfield.moe/ ...")
        page.goto("https://goyfield.moe/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(6000)  # Wait for dynamic content

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
                
                while i < len(lines) and not re.match(r'^[A-Z0-9]{8,}$', lines[i]):
                    current = lines[i]
                    if re.match(r'^\d', current):
                        amount = current.strip()
                        name = "Unknown"
                        if i > 0:
                            prev = lines[i-1].strip()
                            if "Oroberyl" in prev or "oro" in prev.lower():
                                name = "Oroberyl"
                            elif "T-Cred" in prev or "cred" in prev.lower():
                                name = "T-Creds"
                            elif "Combat Record" in prev:
                                name = "Combat Record"
                            elif "INSP Kit" in prev or "kit" in prev.lower():
                                name = "Arms INSP Kit"
                            else:
                                name = prev  # fallback
                        promo_data[code][name] = amount
                    i += 1
                continue
            i += 1

        result = {
            "promo_codes": promo_data,
            "count": len(promo_data)
        }

        print(json.dumps(result, indent=2))
        browser.close()
        return result


if __name__ == "__main__":
    extract_promo_codes()
