import re
import json
from playwright.sync_api import sync_playwright

def test_promo():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        
        print("Loading page...")
        page.goto("https://goyfield.moe/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(8000)  # Give more time for dynamic content

        text = page.evaluate("() => document.body.innerText")
        print("--- First 500 characters of page text ---")
        print(text[:500])
        print("--- End of preview ---")

        # Simple extraction
        codes = re.findall(r'\b[A-Z0-9]{8,}\b', text)
        codes = list(dict.fromkeys(codes))

        print(f"\nFound codes: {codes}")

        browser.close()


if __name__ == "__main__":
    test_promo()
