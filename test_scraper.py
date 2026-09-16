import asyncio
import pandas as pd
from playwright.async_api import async_playwright

TEST_URL = "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Pest%2520Control%22%7D"

async def test_export_flow():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("\n--- DIAGNOSTIC TEST: Direct Page Menu Trigger ---")
        try:
            await page.goto(TEST_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(10)

            # 1. Target map visual directly on the main page (No iframe wrapper)
            map_visual = page.locator("ggr-geo-chart, .component-container, canvas, svg").first
            
            # 2. Move mouse & right-click map visual to mount the overlay menu
            await map_visual.hover(force=True)
            await asyncio.sleep(1)
            await map_visual.click(button="right", force=True)
            await asyncio.sleep(1.5)

            # 3. Intercept download stream
            async with page.expect_download(timeout=30000) as download_info:
                # Target exact text "Export data" overlay element
                export_item = page.locator("body, .cdk-overlay-container, mat-menu").get_by_text("Export data", exact=True).first
                await export_item.click(force=True)
                await asyncio.sleep(1.5)

                # Target modal dialog EXPORT button
                confirm_btn = page.locator("mat-dialog-container button").filter(has_text="EXPORT").last
                await confirm_btn.click(force=True)

            download = await download_info.value
            temp_path = await download.path()

            df = pd.read_csv(temp_path)
            print(f"[✓] SUCCESS: Downloaded CSV with {len(df)} rows!")
            print("Sample Output:")
            print(df.head(3))

        except Exception as e:
            print(f"[X] FAILED: {type(e).__name__} - {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_export_flow())
