import asyncio
import json
from playwright.async_api import async_playwright

TEST_URL = "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Pest%2520Control%22%7D"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("\n=== PAYLOAD STRUCTURAL INSPECTION ===")

        async def handle_response(response):
            if "batchedData" in response.url:
                try:
                    text = await response.text()
                    if text.startswith(")]}'"):
                        text = text[4:].strip()
                    
                    data = json.loads(text)
                    print("\n[✓] Intercepted batchedData Payload")
                    
                    for idx, resp in enumerate(data.get("dataResponse", [])):
                        print(f"--- DataResponse [{idx}] ---")
                        for sub_idx, sub in enumerate(resp.get("dataSubset", [])):
                            table = sub.get("dataset", {}).get("tableDataset", {})
                            cols = table.get("column", [])
                            print(f"  Subset [{sub_idx}] Columns Count: {len(cols)}")
                            if cols:
                                sample_vals = cols[0].get("values", [])[:5]
                                print(f"  Column 0 Sample Values: {sample_vals}")

                except Exception as e:
                    print(f"[!] Parsing error: {e}")

        page.on("response", handle_response)
        await page.goto(TEST_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
