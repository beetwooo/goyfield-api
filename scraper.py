"""
Standalone Promo Codes Scraper for goyfield.moe
"""

import json
from playwright.sync_api import sync_playwright

REWARD_NAME_MAP = {
    "oroberyl": "Oroberyl",
    "tCreds": "T-Creds",
    "armsInspKit": "Arms INSP Kit",
    "intermediateCombatRecord": "Combat Record",
    "advancedCombatRecord": "Combat Record",
}


def extract_promo_codes():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        print("Loading https://goyfield.moe/ ...")
        page.goto("https://goyfield.moe/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(4000)

        result = page.evaluate(
            """
            () => {
                const rewardNameMap = {
                    oroberyl: 'Oroberyl',
                    tCreds: 'T-Creds',
                    armsInspKit: 'Arms INSP Kit',
                    intermediateCombatRecord: 'Combat Record',
                    advancedCombatRecord: 'Combat Record'
                };

                const promoSection = Array.from(document.querySelectorAll('div')).find((div) => {
                    const text = (div.textContent || '').replace(/\s+/g, ' ').trim();
                    return text.includes('Promo codes') && text.includes('ENDFIELDGIFT');
                });

                if (!promoSection) return {};

                const rows = Array.from(promoSection.querySelectorAll('div[class*="flex flex-col md:flex-row"]'));
                const promoData = {};

                for (const row of rows) {
                    const codeEl = Array.from(row.querySelectorAll('span')).find((span) => {
                        const text = (span.textContent || '').trim();
                        return /^[A-Z0-9]{4,}$/.test(text) && !/^\d+$/.test(text);
                    });

                    if (!codeEl) continue;

                    const code = (codeEl.textContent || '').trim();
                    if (!code || promoData[code]) continue;

                    const rewards = {};
                    const rewardButtons = Array.from(row.querySelectorAll('button')).filter((btn) => btn.querySelector('img'));

                    for (const btn of rewardButtons) {
                        const amountEl = btn.querySelector('span');
                        const imgEl = btn.querySelector('img');
                        if (!amountEl || !imgEl) continue;

                        const amount = (amountEl.textContent || '').trim();
                        const alt = (imgEl.getAttribute('alt') || '').trim();
                        if (!amount || !alt) continue;

                        const rewardName = rewardNameMap[alt] || alt;
                        rewards[rewardName] = amount;
                    }

                    if (Object.keys(rewards).length) {
                        promoData[code] = rewards;
                    }
                }

                return promoData;
            }
            """
        )

        browser.close()

        payload = {
            "promo_codes": result,
            "count": len(result),
        }
        print(json.dumps(payload, indent=2))
        return payload


if __name__ == "__main__":
    extract_promo_codes()
