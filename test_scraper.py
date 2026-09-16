import asyncio
import pandas as pd
from playwright.async_api import async_playwright

TEST_URL = "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Pest%2520Control%22%7D"

async def test_xvfb_export():
    async with async_playwright() as p:
        # Launch headed Chromium inside XVFB virtual display
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("\n--- DIAGNOSTIC TEST: Headed XVFB Virtual Display Export ---")
        try:
            await page.goto(TEST_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(10)

            # Move mouse across map canvas area to trigger hover events in real display context
            await page.mouse.move(720, 350)
            await asyncio.sleep(1)
            await page.mouse.click(720, 350, button="right")
            await asyncio.sleep(2)

            # Save screenshot to confirm overlay opened
            await page.screenshot(path="debug_viewport.png", full_page=True)

            # Intercept download stream
            async with page.expect_download(timeout=30000) as download_info:
                # Target exact text 'Export data' from visible overlay menu
                export_item = page.locator("body, .cdk-overlay-container, mat-menu").get_by_text("Export data", exact=True).first
                await export_item.click(force=True)
                await asyncio.sleep(1.5)

                # Confirm modal export
                confirm_btn = page.locator("mat-dialog-container button").filter(has_text="EXPORT").last
                await confirm_btn.click(force=True)

            download = await download_info.value
            saved_path = await download.path()

            df = pd.read_csv(saved_path)
            print(f"[✓] SUCCESS: Extracted {len(df)} rows via XVFB headed browser!")
            print(df.head(3))

        except Exception as e:
            print(f"[X] FAILED: {type(e).__name__} - {e}")
            await page.screenshot(path="debug_viewport.png", full_page=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_xvfb_export())
