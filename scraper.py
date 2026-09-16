import asyncio
import datetime
import json
import os
import pandas as pd
from playwright.async_api import async_playwright

CSV_FILE = "marketcall_data.csv"

# 14 Cleaned Category Embed URLs
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

def parse_batched_response(raw_text):
    """Parses Looker Studio batched JSON response into structured rows."""
    # Strip security prefix if present
    if raw_text.startswith(")]}'"):
        raw_text = raw_text[4:].strip()

    data = json.loads(raw_text)
    extracted_rows = []

    for item in data.get("dataResponse", []):
        for subset in item.get("dataSubset", []):
            table = subset.get("dataset", {}).get("tableDataset", {})
            column_info = table.get("columnInfo", [])
            headers = [col.get("name", f"col_{i}") for i, col in enumerate(column_info)]
            
            matrix = table.get("column", [])
            if matrix and len(matrix) > 0:
                num_rows = len(matrix[0].get("values", []))
                for row_idx in range(num_rows):
                    row_data = {}
                    for col_idx, col_data in enumerate(matrix):
                        col_name = headers[col_idx] if col_idx < len(headers) else f"col_{col_idx}"
                        vals = col_data.get("values", [])
                        row_data[col_name] = vals[row_idx] if row_idx < len(vals) else None
                    extracted_rows.append(row_data)

    return pd.DataFrame(extracted_rows)

async def scrape_category(page, category_name, url):
    scrape_date = datetime.date.today().isoformat()
    print(f"\n[+] Processing: {category_name}")

    captured_payloads = []

    async def handle_response(response):
        if "batchedData" in response.url:
            try:
                text = await response.text()
                if "dataResponse" in text:
                    captured_payloads.append(text)
            except Exception:
                pass

    page.on("response", handle_response)
    
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(6)  # Wait for API requests to complete

    if not captured_payloads:
        raise Exception("No batchedData payloads captured.")

    # Parse all captured network data frames for this category
    dfs = []
    for payload in captured_payloads:
        try:
            df_part = parse_batched_response(payload)
            if not df_part.empty:
                dfs.append(df_part)
        except Exception as parse_err:
            pass

    if dfs:
        combined_cat_df = pd.concat(dfs, ignore_index=True).drop_duplicates()
        combined_cat_df["Scraped_Date"] = scrape_date
        combined_cat_df["Offer_Category"] = category_name
        print(f"    Saved {len(combined_cat_df)} records for {category_name}.")
        return combined_cat_df
    else:
        raise Exception("Failed to parse tabular data from response payloads.")

async def main():
    all_dfs = []
    consecutive_failures = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
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
                
                # Fail-fast check: stop workflow early if 2 consecutive categories fail
                if consecutive_failures >= 2:
                    print("\n[!] Fail-fast triggered: 2 consecutive failures. Stopping job early.")
                    break

        await browser.close()

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        save_and_deduplicate(combined_df)

def save_and_deduplicate(new_df):
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        try:
            existing_df = pd.read_csv(CSV_FILE)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            deduped_df = combined_df.drop_duplicates(
                subset=[c for c in combined_df.columns if c != "Scraped_Date"], 
                keep="first"
            )
        except Exception:
            deduped_df = new_df
    else:
        deduped_df = new_df

    deduped_df.to_csv(CSV_FILE, index=False)
    print(f"\n[✓] Master dataset updated: {len(deduped_df)} total records saved in {CSV_FILE}.")

if __name__ == "__main__":
    asyncio.run(main())
