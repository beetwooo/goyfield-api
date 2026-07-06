import re
import json
from playwright.sync_api import sync_playwright

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

                while i < len(lines) and not re.match(r'^[A-Z0-9]{8,}$', lines[i]):
                    current = lines[i]
                    if re.match(r'^\d', current):  # This is a number line
                        amount = current.strip()
                        # Look for name in previous line
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
                                name = prev  # fallback to previous line as name
                        promo_data[code][name] = amount
                    i += 1
                continue
            i += 1

        result = {
            "promo_codes": promo_data,
            "count": len(promo_data)
        }
        print(f"  Found {len(promo_data)} promo codes with rewards")
        return result

    except Exception as e:
        print(f"  Promo codes extraction failed: {e}")
        return {"promo_codes": {}, "count": 0}


if __name__ == "__main__":
    test_promo()
