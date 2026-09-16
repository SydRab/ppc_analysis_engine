import asyncio
import datetime
import os
import pandas as pd
from playwright.async_api import async_playwright

URL = "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df8%22:%22include%25EE%2580%25801%25EE%2580%2580GTE%25EE%2580%258050%22%7D"
CSV_FILE = "marketcall_data.csv"

# Add all categories you want to scrape daily
CATEGORIES = [
    "Pest Control",
]


async def scrape_category_csv(page, category_name):
    """Selects a category filter and downloads the corresponding CSV dataset."""
    scrape_date = datetime.date.today().isoformat()
    print(f"\n--- Scraping Category: {category_name} ---")

    # 1. Click Offer Category Dropdown
    print("Opening Offer Category dropdown...")
    dropdown = page.locator("div").filter(has_text="Offer Category").last
    await dropdown.click(force=True)
    await asyncio.sleep(2)

    # 2. Select option from dynamic overlay
    print(f"Selecting category option: '{category_name}'...")
    option = page.locator(f"mat-option:has-text('{category_name}'), [role='option']:has-text('{category_name}')").first
    if await option.is_visible():
        await option.click()
        print(f"Selected '{category_name}'. Waiting for dashboard to update...")
        await asyncio.sleep(6)  # Wait for map data recalculation
    else:
        print(f"Warning: Category option '{category_name}' not found. Attempting export with current view...")

    # 3. Locate and hover over the map chart widget to reveal 3 dots
    print("Hovering over Map widget...")
    chart_container = page.locator("ggr-geo-chart, .component-container, canvas").first
    await chart_container.hover(force=True)
    await asyncio.sleep(1.5)

    # 4. Click 3-dots menu (more options)
    print("Clicking 3-dots options menu...")
    more_options_btn = page.locator("button[aria-label='More options'], .action-button, [data-ng-click*='showExport']").first
    await more_options_btn.click(force=True)
    await asyncio.sleep(1.5)

    # 5. Trigger Export and capture download stream
    print("Triggering Export modal and download...")
    async with page.expect_download(timeout=60000) as download_info:
        # Click Export from context menu
        await page.get_by_text("Export").first.click()
        await asyncio.sleep(1.5)

        # Click the final EXPORT button in the popup modal
        modal_export_btn = page.locator("button:has-text('Export'), .mat-button:has-text('EXPORT')").last
        await modal_export_btn.click()

    download = await download_info.value
    temp_path = await download.path()
    print(f"Successfully captured download for {category_name}.")

    # Read CSV and inject metadata columns
    df = pd.read_csv(temp_path)
    df["Scraped_Date"] = scrape_date
    df["Offer_Category"] = category_name

    return df


async def main():
    all_category_dfs = []

    async with async_playwright() as p:
        # Launch browser with custom viewport size to ensure chart action buttons render
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900}
        )
        page = await context.new_page()

        print("Navigating to Marketcall Looker Studio report...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_selector("body", timeout=60000)
        await asyncio.sleep(10)

        for category in CATEGORIES:
            try:
                cat_df = await scrape_category_csv(page, category)
                if cat_df is not None and not cat_df.empty:
                    all_category_dfs.append(cat_df)
            except Exception as e:
                print(f"Error scraping category '{category}': {e}")

        await browser.close()

    if all_category_dfs:
        combined_new_df = pd.concat(all_category_dfs, ignore_index=True)
        save_and_deduplicate(combined_new_df)
    else:
        print("No data extracted during this run.")


def save_and_deduplicate(new_df):
    """Appends new records to master CSV and deduplicates."""
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        print(f"Loading existing dataset from {CSV_FILE}...")
        try:
            existing_df = pd.read_csv(CSV_FILE)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            
            # Deduplicate matching records excluding Scraped_Date
            data_columns = [c for c in combined_df.columns if c != "Scraped_Date"]
            deduped_df = combined_df.drop_duplicates(subset=data_columns, keep="first")
        except pd.errors.EmptyDataError:
            deduped_df = new_df
    else:
        print("Creating new master CSV dataset...")
        deduped_df = new_df

    deduped_df.to_csv(CSV_FILE, index=False)
    print(f"Dataset updated. Total records saved: {len(deduped_df)}")


if __name__ == "__main__":
    asyncio.run(main())
