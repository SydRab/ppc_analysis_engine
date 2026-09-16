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

    await page.goto(url, wait_until="networkidle", timeout=90000)
    await asyncio.sleep(10)

    # 1. Target the embedded iframe context
    frame = page.frame_locator("iframe").first if len(page.frames) > 1 else page

    # 2. Hover over map container inside the iframe context
    map_element = frame.locator("ggr-geo-chart, .component-container, canvas, svg").first
    await map_element.hover(force=True)
    await asyncio.sleep(2)

    # 3. Click the 3-dots action menu inside the iframe context
    more_options_btn = frame.locator(
        "button[aria-label='More options'], [aria-label='More options'], .action-button"
    ).first
    await more_options_btn.click(force=True)
    await asyncio.sleep(1.5)

    # 4. Trigger download and confirm modal
    async with page.expect_download(timeout=60000) as download_info:
        await page.locator(".cdk-overlay-container, .mat-menu-content").get_by_text("Export data").first.click()
        await asyncio.sleep(1.5)

        modal_export_btn = page.locator("mat-dialog-container button").filter(has_text="EXPORT").last
        await modal_export_btn.click()

    download = await download_info.value
    temp_path = await download.path()

    df = pd.read_csv(temp_path)
    df["Scraped_Date"] = scrape_date
    df["Offer_Category"] = category_name

    print(f"    Successfully extracted {len(df)} rows for {category_name}.")
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
    print(f"\n[✓] Master dataset updated: {len(deduped_df)} total records saved in {CSV_FILE}.")

if __name__ == "__main__":
    asyncio.run(main())
