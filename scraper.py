import asyncio
import datetime
import os
import pandas as pd
from playwright.async_api import async_playwright

# Target Marketcall Looker Studio Embed URL
URL = "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Pest%2520Control%22,%22df8%22:%22include%25EE%2580%25801%25EE%2580%2580GTE%25EE%2580%258050%22%7D"
CSV_FILE = "marketcall_data.csv"


async def scrape_looker_studio():
    """Scrapes dynamic table data from Looker Studio using Playwright."""
    rows_data = []
    scrape_date = datetime.date.today().isoformat()

    async with async_playwright() as p:
        # Launch headless browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("Navigating to Marketcall Looker Studio report...")

        # Change wait_until to domcontentloaded so navigation doesn't block on continuous background network calls
        await page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        
        # Wait for the actual Looker Studio canvas element to render
        await page.wait_for_selector("div.ggr-canvas", timeout=60000)
        
        # Give Looker Studio JS visuals time to completely render canvas/tables
        await page.wait_for_timeout(12000)

        # Extract table rows dynamically rendered in the DOM
        # Looker Studio renders interactive tables using standard ARIA roles
        rows = await page.query_selector_all(
            "div[role='table'] div[role='row'], div.tableBody div.row"
        )

        if rows:
            print(f"Found {len(rows)} table rows.")
            for row in rows:
                cells = await row.query_selector_all(
                    "[role='cell'], [role='gridcell'], .tableCell"
                )
                cell_values = [
                    (await cell.inner_text()).strip().replace("\n", " ")
                    for cell in cells
                ]
                if cell_values and any(cell_values):
                    rows_data.append([scrape_date] + cell_values)
        else:
            print("Standard table elements not detected. Extracting grid text fallback...")
            # Fallback: Scrape visual text blocks if rendered inside SVG/Canvas wrappers
            extracted_text = await page.evaluate(
                """() => {
                const nodes = Array.from(document.querySelectorAll('.cell, [role="cell"], .ng-star-inserted'));
                return nodes.map(n => n.innerText.trim()).filter(t => t.length > 0);
            }"""
            )

            # Group extracted sequential items if extracted flat
            if extracted_text:
                print(f"Extracted {len(extracted_text)} total text tokens.")
                # Save raw structured snapshot if strict rows aren't separated
                rows_data.append([scrape_date, " | ".join(extracted_text)])

        await browser.close()

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
