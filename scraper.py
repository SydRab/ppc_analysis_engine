import asyncio
import datetime
import os
import pandas as pd
from playwright.async_api import async_playwright

CSV_FILE = "marketcall_data.csv"

# 14 Cleaned Category Embed URLs (No minimum bid amount filter)
CATEGORY_URLS = {
    "Pest Control": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Pest%2520Control%22%7D",
    "Roofing": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Roofing%22%7D",
    "Life / Final Expense": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Life%2520%252F%2520Final%2520Expense%22%7D",
    "Windows": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Windows%22%7D",
    "Water Damage": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Water%2520Damage%22%7D",
    "HVAC": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580HVAC%22%7D",
    "Plumbing": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Plumbing%22%7D",
    "Appliance Repair": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Appliance%2520Repair%22%7D",
    "Garage Doors": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Garage%2520Doors%22%7D",
    "Home": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Home%22%7D",
    "Mold Remediation": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Mold%2520Remediation%22%7D",
    "Bathroom Remodeling": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Bathroom%2520Remodeling%22%7D",
    "Electrical": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Electrical%22%7D",
    "Gutters": "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Gutters%22%7D"
}

async def scrape_category(page, category_name, url):
    scrape_date = datetime.date.today().isoformat()
    print(f"\n[+] Processing: {category_name}")

    await page.goto(url, wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_selector("body", timeout=60000)
    await asyncio.sleep(12)

    # 1. Hover over the map visual container to reveal the 3-dots button
    chart_widget = page.locator("ggr-geo-chart, .component-container, canvas").first
    await chart_widget.hover(force=True)
    await asyncio.sleep(2)

    # 2. Click the 3-dots options menu button
    more_options_btn = page.locator("button[aria-label='More options'], [aria-label='More options']").first
    await more_options_btn.click(force=True)
    await asyncio.sleep(1.5)

    # 3. Capture file download stream
    async with page.expect_download(timeout=60000) as download_info:
        # Click "Export data" inside the overlay menu
        await page.locator(".cdk-overlay-container, .mat-menu-content").get_by_text("Export data").click()
        await asyncio.sleep(1.5)

        # Click the blue EXPORT button in the popup modal (CSV is selected by default)
        modal_export_btn = page.locator("mat-dialog-container button").filter(has_text="EXPORT").last
        await modal_export_btn.click()

    download = await download_info.value
    temp_path = await download.path()

    df = pd.read_csv(temp_path)
    df["Scraped_Date"] = scrape_date
    df["Offer_Category"] = category_name

    print(f"    Saved {len(df)} rows for {category_name}.")
    return df

async def main():
    all_dfs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900}
        )
        page = await context.new_page()

        for category_name, url in CATEGORY_URLS.items():
            try:
                df = await scrape_category(page, category_name, url)
                if df is not None and not df.empty:
                    all_dfs.append(df)
            except Exception as e:
                print(f"    [!] Error scraping {category_name}: {e}")

        await browser.close()

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        save_and_deduplicate(combined_df)

def save_and_deduplicate(new_df):
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        try:
            existing_df = pd.read_csv(CSV_FILE)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            data_cols = [c for c in combined_df.columns if c != "Scraped_Date"]
            deduped_df = combined_df.drop_duplicates(subset=data_cols, keep="first")
        except Exception:
            deduped_df = new_df
    else:
        deduped_df = new_df

    deduped_df.to_csv(CSV_FILE, index=False)
    print(f"\n[✓] Updated {CSV_FILE} with {len(deduped_df)} total records.")

if __name__ == "__main__":
    asyncio.run(main())
