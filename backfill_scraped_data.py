"""One-off: load marketcall_data.csv rows that never reached BigQuery (upload failures since 24 Sep 2026).

The CSV was deduplicated across days, so these dates are partial: only zips whose data changed
appear on each date. Rows are flagged is_backfill = TRUE. Dates already in BigQuery are skipped,
so running this twice does not create duplicates.
"""
import sys
import pandas as pd
import bq_scraped

KEY_PATH = "gcp_key.json"
CSV_FILE = "marketcall_data.csv"
START_DATE = "2026-09-24"


def main():
    client = bq_scraped.get_client(KEY_PATH)

    existing = {
        row.Scraped_Date.isoformat()
        for row in client.query(
            f"SELECT DISTINCT Scraped_Date FROM `{bq_scraped.TABLE_ID}` WHERE Scraped_Date >= '{START_DATE}'"
        ).result()
    }
    print(f"[+] Dates already in BigQuery since {START_DATE}: {sorted(existing) or 'none'}")

    df = pd.read_csv(CSV_FILE)
    df = df[(df["Scraped_Date"] >= START_DATE) & (~df["Scraped_Date"].isin(existing))]
    if df.empty:
        print("[✓] Nothing to backfill.")
        return

    print(f"[+] Backfilling {len(df)} rows across {df['Scraped_Date'].nunique()} dates "
          f"({df['Scraped_Date'].min()} to {df['Scraped_Date'].max()})")
    rows = bq_scraped.upload(client, bq_scraped.prepare(df, is_backfill=True))
    print(f"[✓] Uploaded {rows} backfill rows to {bq_scraped.TABLE_ID}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[!] Backfill failed: {e}")
        sys.exit(1)
