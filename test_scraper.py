import asyncio
import json
import pandas as pd
from playwright.async_api import async_playwright

TEST_URL = "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Pest%2520Control%22%7D"

async def test_post_hydration_capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("\n--- DIAGNOSTIC TEST: Post-Hydration Stream Interception ---")
        hydrated_payloads = []

        async def handle_response(response):
            if "batchedData" in response.url:
                try:
                    text = await response.text()
                    if text.startswith(")]}'"):
                        text = text[4:].strip()
                    
                    data = json.loads(text)
                    # Filter out empty initial frames, keep populated arrays
                    for item in data.get("dataResponse", []):
                        for subset in item.get("dataSubset", []):
                            cols = subset.get("dataset", {}).get("tableDataset", {}).get("column", [])
                            for col in cols:
                                vals = col.get("values", [])
                                if len(vals) > 0:
                                    hydrated_payloads.append(data)
                                    print(f"[✓] Captured hydrated array frame with {len(vals)} items!")
                                    break
                except Exception:
                    pass

        page.on("response", handle_response)

        # Navigate and wait until network traffic completely settles
        await page.goto(TEST_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(6)

        if hydrated_payloads:
            print(f"[✓] SUCCESS: Caught {len(hydrated_payloads)} populated network payloads after component hydration!")
        else:
            print("[X] FAILED: Post-hydration network listener caught no populated data arrays.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_post_hydration_capture())
