import asyncio
import datetime
import os
import pandas as pd
from playwright.async_api import async_playwright

# Target Marketcall Looker Studio Embed URL
URL = "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Pest%2520Control%22,%22df8%22:%22include%25EE%2580%25801%25EE%2580%2580GTE%25EE%2580%258050%22%7D"
CSV_FILE = "marketcall_data.csv"


async def scrape_looker_studio():
    """Automates Looker Studio UI export to download the raw map/table CSV file."""
    temp_csv_path = None
    scrape_date = datetime.date.today().isoformat()

    async with async_playwright() as p:
        # Launch headless browser with download support enabled
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        print("Navigating to Marketcall Looker Studio report...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=90000)

        # Wait for the HTML body and pause for dynamic Looker Studio JS rendering
        await page.wait_for_selector("body", timeout=60000)
        await asyncio.sleep(10)

        try:
            # 1. Hover over the map visual header to reveal the 3-dots action menu
            print("Locating map visualization...")
            map_element = page.locator("div.ng-star-inserted").filter(
                has_text="Average Bid by Zip Code"
            ).first
            await map_element.hover()
            await asyncio.sleep(1)

            # 2. Click the 3-dots options menu button
            print("Opening context menu...")
            more_options_btn = page.locator(
                "button[aria-label='More options'], .action-button, [data-ng-click*='showExport']"
            ).first
            await more_options_btn.click()
            await asyncio.sleep(1)

            # 3. Trigger export flow and capture downloaded CSV file
            print("Triggering Export option...")
            async with page.expect_download(timeout=60000) as download_info:
                # Click 'Export' in the context dropdown menu
                await page.get_by_text("Export").click()
                await asyncio.sleep(1)

                # Click the final 'Export' confirmation button inside the modal dialog
                modal_export_btn = page.locator(
                    "button:has-text('Export'), .mat-button:has-text('EXPORT')"
                ).last
                await modal_export_btn.click()

            download = await download_info.value
            temp_csv_path = await download.path()
            print("Download captured successfully.")

        except Exception as e:
            print(f"Failed to download export file: {e}")

        await browser.close()

    # Read the downloaded CSV content and format rows for deduplication
    rows_data = []
    if temp_csv_path and os.path.exists(temp_csv_path):
        downloaded_df = pd.read_csv(temp_csv_path)
        # Convert dataframe rows to raw lists with Scraped_Date prepended
        for row in downloaded_df.values.tolist():
            rows_data.append([scrape_date] + [str(val) for val in row])

    return rows_data


def save_and_deduplicate(new_data):
    """Saves scraped rows to CSV and removes duplicate records."""
    if not new_data:
        print("No data extracted during this run.")
        return

    # Determine maximum columns
    max_cols = max(len(r) for r in new_data)
    column_names = ["Scraped_Date"] + [
        f"Col_{i}" for i in range(1, max_cols)
    ]

    new_df = pd.DataFrame(new_data, columns=column_names[:max_cols])

    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        print(f"Loading existing dataset from {CSV_FILE}...")
        try:
            existing_df = pd.read_csv(CSV_FILE)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            data_columns = [c for c in combined_df.columns if c != "Scraped_Date"]
            deduped_df = combined_df.drop_duplicates(subset=data_columns, keep="first")
        except pd.errors.EmptyDataError:
            deduped_df = new_df
    else:
        print("No existing or valid CSV found. Creating new dataset...")
        deduped_df = new_df

    deduped_df.to_csv(CSV_FILE, index=False)
    print(f"Dataset updated. Total records saved: {len(deduped_df)}")


if __name__ == "__main__":
    scraped_rows = asyncio.run(scrape_looker_studio())
    save_and_deduplicate(scraped_rows)
