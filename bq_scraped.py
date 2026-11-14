"""Upload Marketcall scraper data to BigQuery (github_ppc_marketcall_db.daily_scraped_data).

Column names are mapped to the existing table schema explicitly, so BigQuery never
sees the raw Looker Studio headers ("Latitude, Longitude" has a comma, which BigQuery rejects).
"""
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

TABLE_ID = "ppc-scraper-analysis.github_ppc_marketcall_db.daily_scraped_data"

COLUMN_MAP = {
    "Latitude, Longitude": "Latitude_Longitude",
    "zip_code": "zip_code",
    "Number of bids": "Number_of_bids",
    "Average Bid": "Average_Bid",
    "Scraped_Date": "Scraped_Date",
    "Offer_Category": "Offer_Category",
}

SCHEMA = [
    bigquery.SchemaField("Latitude_Longitude", "STRING"),
    bigquery.SchemaField("zip_code", "INT64"),
    bigquery.SchemaField("Number_of_bids", "INT64"),
    bigquery.SchemaField("Average_Bid", "FLOAT64"),
    bigquery.SchemaField("Scraped_Date", "DATE"),
    bigquery.SchemaField("Offer_Category", "STRING"),
    bigquery.SchemaField("is_backfill", "BOOL"),  # TRUE = loaded later from the deduplicated CSV (partial day)
]


def get_client(key_path):
    credentials = service_account.Credentials.from_service_account_file(key_path)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


def prepare(df, is_backfill=False):
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(f"Scraped data is missing expected columns: {missing}. Got: {list(df.columns)}")
    out = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP).copy()
    out["Latitude_Longitude"] = out["Latitude_Longitude"].astype(str)
    out["zip_code"] = pd.to_numeric(out["zip_code"], errors="coerce").astype("Int64")
    out["Number_of_bids"] = pd.to_numeric(out["Number_of_bids"], errors="coerce").astype("Int64")
    out["Average_Bid"] = pd.to_numeric(out["Average_Bid"], errors="coerce").astype(float)
    out["Scraped_Date"] = pd.to_datetime(out["Scraped_Date"]).dt.date
    out["Offer_Category"] = out["Offer_Category"].astype(str)
    out["is_backfill"] = is_backfill
    return out


def upload(client, df):
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
    )
    job = client.load_table_from_dataframe(df, TABLE_ID, job_config=job_config)
    job.result()
    return len(df)
