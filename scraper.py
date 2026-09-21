import asyncio
import datetime
import os
import pandas as pd
from playwright.async_api import async_playwright
from google.cloud import bigquery
from google.oauth2 import service_account

CSV_FILE = "marketcall_data.csv"
KEY_PATH = "gcp_key.json"

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

    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(10)

    # Hover and right-click to mount the Angular overlay menu inside XVFB
    await page.mouse.move(720, 350)
    await asyncio.sleep(1)
    await page.mouse.click(720, 350, button="right")
    await asyncio.sleep(2)

    # Trigger download stream
    async with page.expect_download(timeout=30000) as download_info:
        export_item = page.locator("body, .cdk-overlay-container, mat-menu").get_by_text("Export data", exact=True).first
        await export_item.click(force=True)
        await asyncio.sleep(1.5)

        confirm_btn = page.locator("mat-dialog-container button").filter(has_text="EXPORT").last
        await confirm_btn.click(force=True)

    download = await download_info.value
    saved_path = await download.path()

    df = pd.read_csv(saved_path)
    df["Scraped_Date"] = scrape_date
    df["Offer_Category"] = category_name
    print(f"    Saved {len(df)} records for {category_name}.")
    return df

async def main():
    all_dfs = []
    consecutive_failures = 0

    async with async_playwright() as p:
        # Launch headed browser within XVFB virtual framebuffer
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for category_name, url in CATEGORY_URLS.items():
            try:
                df = await scrape_category(page, category_name, url)
                if df is not None and not df.empty:
                    all_dfs.append(df)
                    consecutive_failures = 0
            except Exception as e:
                print(f"    [!] Error scraping {category_name}: {e}")
                consecutive_failures += 1
                
                # Fail-Fast logic: Exit early if 2 consecutive categories fail
                if consecutive_failures >= 2:
                    print("\n[!] Fail-fast triggered: 2 consecutive failures. Stopping pipeline.")
                    break

        await browser.close()

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        save_and_deduplicate(combined_df)
        upload_to_bigquery(combined_df)

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

def upload_to_bigquery(new_df):
    if not os.path.exists(KEY_PATH):
        print("\n[!] GCP key file (gcp_key.json) not found. Skipping BigQuery upload.")
        return

    try:
        credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
        client = bigquery.Client(credentials=credentials, project=credentials.project_id)

        # Target BigQuery table
        table_id = f"{credentials.project_id}.github_ppc_marketcall_db.daily_scraped_data"

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            autodetect=True,
            column_name_character_map="V2"  # Handles special characters in headers
        )

        job = client.load_table_from_dataframe(new_df, table_id, job_config=job_config)
        job.result()  # Wait for upload completion
        print(f"[✓] Successfully uploaded {len(new_df)} new rows to BigQuery table: {table_id}")
    except Exception as e:
        print(f"[!] BigQuery upload failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
