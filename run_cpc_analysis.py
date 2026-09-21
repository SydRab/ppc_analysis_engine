import os
import json
import pandas as pd
import numpy as np
from datetime import date
from google.cloud import bigquery
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# BigQuery Table Definitions
GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "ppc-scraper-analysis")
BQ_DATASET = "github_ppc_marketcall_db"
RAW_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.daily_scraped_data"
EVALUATED_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.evaluated_top_5pc_zips"

# Default seed keywords per category for Google Ads Keyword Planner API
CATEGORY_SEED_KEYWORDS = {
    "Pest Control": ["pest control near me", "exterminator service", "termite control"],
    "Roofing": ["roof repair near me", "roofing contractor", "roof replacement"],
    "Life / Final Expense": ["final expense insurance", "burial insurance quotes", "life insurance quotes"],
    "Windows": ["window replacement near me", "window installation contractor", "new windows cost"],
    "Water Damage": ["water damage restoration", "flood cleanup service", "water mitigation"],
    "HVAC": ["hvac repair near me", "ac repair service", "heating installation"],
    "Plumbing": ["emergency plumber near me", "plumbing repair", "drain cleaning service"],
    "Appliance Repair": ["appliance repair near me", "refrigerator repair service", "washer dryer repair"],
    "Garage Doors": ["garage door repair near me", "garage door installation", "broken garage door spring"],
    "Home": ["home repair services", "handyman near me", "home maintenance"],
    "Mold Remediation": ["mold remediation near me", "mold removal service", "black mold inspection"],
    "Bathroom Remodeling": ["bathroom remodel contractors", "bathroom renovation cost", "walk in tub installation"],
    "Electrical": ["electrician near me", "emergency electrician", "electrical panel repair"],
    "Gutters": ["gutter installation near me", "gutter repair service", "seamless gutters cost"]
}

def get_bq_client():
    """Initializes BigQuery client using GCP_SA_KEY_JSON secret from GitHub Actions."""
    sa_json = os.environ.get("GCP_SA_KEY_JSON")
    if sa_json:
        info = json.loads(sa_json)
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=GCP_PROJECT)

def get_gads_client():
    """Initializes Google Ads API client using environment secrets."""
    credentials = {
        "developer_token": "DEVELOPER_TOKEN_NOT_REQUIRED",
        "client_id": os.environ.get("GADS_CLIENT_ID"),
        "client_secret": os.environ.get("GADS_CLIENT_SECRET"),
        "refresh_token": os.environ.get("GADS_REFRESH_TOKEN"),
        "login_customer_id": os.environ.get("GADS_LOGIN_CUSTOMER_ID"),
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(credentials)

def fetch_cpc_for_category(gads_client, customer_id, seed_keywords):
    """
    Queries Google Ads API KeywordPlanIdeaService to retrieve Low, Mid, and High 
    top-of-page CPC bid estimates (converted from micros to USD).
    """
    geo_service = gads_client.get_service("GeoTargetConstantService")
    gtc_service = gads_client.get_service("KeywordPlanIdeaService")
    
    request = gads_client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = gads_client.get_service("LanguageConstantService").language_constant_path("1000")
    request.geo_target_constants.append(geo_service.geo_target_constant_path("2840")) # United States
    request.include_adult_keywords = False
    request.keyword_plan_network = gads_client.get_type("KeywordPlanNetworkEnum").KeywordPlanNetwork.GOOGLE_SEARCH
    request.keyword_seed.keywords.extend(seed_keywords)

    low_bids, high_bids = [], []
    try:
        response = gtc_service.generate_keyword_ideas(request=request)
        for result in response:
            m = result.keyword_idea_metrics
            if m.low_top_of_page_bid_micros:
                low_bids.append(m.low_top_of_page_bid_micros / 1_000_000)
            if m.high_top_of_page_bid_micros:
                high_bids.append(m.high_top_of_page_bid_micros / 1_000_000)
    except GoogleAdsException as ex:
        print(f"    [!] Google Ads API Exception: {ex}")

    avg_low = float(np.mean(low_bids)) if low_bids else 0.0
    avg_high = float(np.mean(high_bids)) if high_bids else 0.0
    avg_mid = (avg_low + avg_high) / 2.0
    return round(avg_low, 2), round(avg_mid, 2), round(avg_high, 2)

def process_daily_cpc_analysis(target_date=None):
    """Primary pipeline orchestration function."""
    bq_client = get_bq_client()
    if target_date is None:
        target_date = date.today().isoformat()

    print(f"\n[+] Querying BigQuery partition: Scraped_Date = '{target_date}'...")
    query = f"SELECT * FROM `{RAW_TABLE}` WHERE Scraped_Date = '{target_date}'"
    df = bq_client.query(query).to_dataframe()

    if df.empty:
        print(f"[!] No records found in {RAW_TABLE} for date {target_date}.")
        return

    # Standardize column naming
    df.columns = [c.replace(" ", "_").replace(",", "_") for c in df.columns]

    # --- STEP 1: DUAL-DIMENSION TOP 5% FILTERING ---
    # 1A. Top 5% Payout Quantile (per Offer_Category)
    df["payout_quantile_95"] = df.groupby("Offer_Category")["Average_Bid"].transform(lambda x: x.quantile(0.95))
    df["is_top_5_percent"] = df["Average_Bid"] >= df["payout_quantile_95"]

    # 1B. Top 5% Activity Score (Average_Bid * Number_of_bids) -> Updated to 0.95 Quantile
    df["activity_score"] = df["Average_Bid"] * df["Number_of_bids"]
    df["activity_quantile_95"] = df.groupby("Offer_Category")["activity_score"].transform(lambda x: x.quantile(0.95))
    df["is_high_activity"] = df["activity_score"] >= df["activity_quantile_95"]

    # Filter high-value targets (Must meet Top 5% Payout OR Top 5% Activity)
    top_df = df[df["is_top_5_percent"] | df["is_high_activity"]].copy()
    print(f"[+] Total raw rows: {len(df)} | Qualified for API evaluation (Top 5% Rules): {len(top_df)}")

    # --- STEP 2: GOOGLE ADS API CPC EXTRACTION ---
    gads_client = get_gads_client()
    customer_id = os.environ.get("GADS_LOGIN_CUSTOMER_ID")

    api_results = {}
    unique_categories = top_df["Offer_Category"].unique()
    print(f"[+] Querying Google Ads API for {len(unique_categories)} offer categories...")

    for cat in unique_categories:
        seeds = CATEGORY_SEED_KEYWORDS.get(cat, ["services near me", f"{cat.lower()} contractor"])
        low, mid, high = fetch_cpc_for_category(gads_client, customer_id, seeds)
        api_results[cat] = {"low": low, "mid": mid, "high": high}
        print(f"    -> Category: {cat:20s} | Low CPC: ${low:6.2f} | Mid CPC: ${mid:6.2f} \vert{} High CPC:${high:6.2f}")

    top_df["api_cpc_low"] = top_df["Offer_Category"].map(lambda c: api_results.get(c, {}).get("low", 0.0))
    top_df["api_cpc_mid"] = top_df["Offer_Category"].map(lambda c: api_results.get(c, {}).get("mid", 0.0))
    top_df["api_cpc_high"] = top_df["Offer_Category"].map(lambda c: api_results.get(c, {}).get("high", 0.0))

    # --- STEP 3: BENCHMARK & VIABILITY MATH ---
    # Benchmark Rule 1: 12x Rule Limit (Max Allowed CPC = Marketcall Payout / 12)
    top_df["limit_12x_cpc"] = (top_df["Average_Bid"] / 12.0).round(2)
    top_df["status_12x_low"] = np.where(top_df["api_cpc_low"] <= top_df["limit_12x_cpc"], "PASS", "FAIL")
    top_df["status_12x_mid"] = np.where(top_df["api_cpc_mid"] <= top_df["limit_12x_cpc"], "PASS", "FAIL")
    top_df["status_12x_high"] = np.where(top_df["api_cpc_high"] <= top_df["limit_12x_cpc"], "PASS", "FAIL")

    # Benchmark Rule 2: 2.24% Conversion Funnel Math
    # Breakeven CPC = Payout * 2.24% | Target (30% Margin) CPC = Payout * 1.568%
    top_df["breakeven_funnel_cpc"] = (top_df["Average_Bid"] * 0.0224).round(2)
    top_df["target_30margin_funnel_cpc"] = (top_df["Average_Bid"] * 0.01568).round(2)
    top_df["status_funnel_low"] = np.where(top_df["api_cpc_low"] <= top_df["target_30margin_funnel_cpc"], "PASS", "FAIL")
    top_df["status_funnel_mid"] = np.where(top_df["api_cpc_mid"] <= top_df["target_30margin_funnel_cpc"], "PASS", "FAIL")
    top_df["status_funnel_high"] = np.where(top_df["api_cpc_high"] <= top_df["target_30margin_funnel_cpc"], "PASS", "FAIL")

    # Final Viability Tier Classification
    conditions = [
        (top_df["status_12x_high"] == "PASS") & (top_df["status_funnel_high"] == "PASS"),
        (top_df["status_12x_low"] == "PASS") | (top_df["status_funnel_low"] == "PASS")
    ]
    choices = ["Profitable (High Bid Validated)", "Marginal (Low/Mid Bid Only)"]
    top_df["ZIP_Viability_Tier"] = np.select(conditions, choices, default="Non-Viable (Exclude ZIP)")

    # Ensure zip_code is formatted as string for schema consistency
    top_df["zip_code"] = top_df["zip_code"].astype(str)

    # Remove temporary calculation columns
    output_df = top_df.drop(columns=["payout_quantile_95", "activity_score", "activity_quantile_95"], errors="ignore")

    # --- STEP 4: BIGQUERY APPEND ---
    print(f"[+] Writing {len(output_df)} evaluated rows to BigQuery: {EVALUATED_TABLE}...")
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=bigquery.TimePartitioning(field="Scraped_Date")
    )
    job = bq_client.load_table_from_dataframe(output_df, EVALUATED_TABLE, job_config=job_config)
    job.result()  # Wait for job completion
    print(f"[✓] Successfully processed and stored date: {target_date}")

if __name__ == "__main__":
    process_daily_cpc_analysis()
