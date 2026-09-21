import os
import json
import pandas as pd
import numpy as np
from datetime import date
from google.cloud import bigquery
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# BigQuery Definitions
GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "ppc-scraper-analysis")
BQ_DATASET = "github_ppc_marketcall_db"
RAW_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.daily_scraped_data"
EVALUATED_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.evaluated_top_5pc_zips"

# Seed keywords per offer category for Google Ads Keyword Planner API
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
    sa_json = os.environ.get("GCP_SA_KEY_JSON")
    if sa_json:
        info = json.loads(sa_json)
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=GCP_PROJECT)

def get_gads_client():
    credentials = {
        "developer_token": "DEVELOPER_TOKEN_NOT_REQUIRED",
        "client_id": os.environ.get("GADS_CLIENT_ID"),
        "client_secret": os.environ.get("GADS_CLIENT_SECRET"),
        "refresh_token": os.environ.get("GADS_REFRESH_TOKEN"),
        "login_customer_id": os.environ.get("GADS_LOGIN_CUSTOMER_ID"),
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(credentials)

def build_zip_to_criteria_id_map(gads_client, customer_id, target_zips):
    """
    Uses Google Ads API GeoTargetConstantService to dynamically look up 
    Criteria IDs for 5-digit US Postal Codes.
    """
    print(f"[+] Looking up Criteria IDs for {len(target_zips)} ZIP codes via Google Ads API...")
    gtc_service = gads_client.get_service("GeoTargetConstantService")
    
    mapping = {}
    batch_size = 25
    target_zips_padded = [str(z).zfill(5) for z in target_zips]
    
    for i in range(0, len(target_zips_padded), batch_size):
        batch = target_zips_padded[i:i + batch_size]
        try:
            request = gads_client.get_type("SuggestGeoTargetConstantsRequest")
            request.locale = "en"
            request.country_code = "US"
            request.location_names.names.extend(batch)
            
            response = gtc_service.suggest_geo_target_constants(request=request)
            for suggestion in response.geo_target_constant_suggestions:
                gtc = suggestion.geo_target_constant
                if gtc.target_type == "Postal Code" and gtc.country_code == "US":
                    # Extract numeric ID from 'geoTargetConstants/1014221'
                    cid = gtc.resource_name.split("/")[-1]
                    mapping[gtc.name] = cid
        except Exception as e:
            print(f"    [!] Warning: Failed batch geo lookup ({e})")
            
    print(f"[✓] Successfully mapped {len(mapping)} / {len(target_zips)} unique ZIP codes to Google Criteria IDs.")
    return mapping

def fetch_zip_level_gads_data(gads_client, customer_id, criteria_id, seed_keywords):
    """
    Queries KeywordPlanIdeaService targeted specifically at a ZIP Criteria ID.
    Returns Low, Mid, High CPCs, Monthly Search Volume, and Competition Index.
    """
    geo_service = gads_client.get_service("GeoTargetConstantService")
    gtc_service = gads_client.get_service("KeywordPlanIdeaService")
    
    request = gads_client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    
    # Direct string resource path (Fixes: LanguageConstantService deprecation error in v25)
    request.language = "languageConstants/1000"  # English
    
    target_geo = criteria_id if criteria_id else "2840"
    request.geo_target_constants.append(geo_service.geo_target_constant_path(target_geo))
    request.include_adult_keywords = False
    request.keyword_plan_network = gads_client.get_type("KeywordPlanNetworkEnum").KeywordPlanNetwork.GOOGLE_SEARCH
    request.keyword_seed.keywords.extend(seed_keywords)

    low_bids, high_bids = [], []
    monthly_searches, comp_indexes, comp_levels = [], [], []

    try:
        response = gtc_service.generate_keyword_ideas(request=request)
        for result in response:
            m = result.keyword_idea_metrics
            if m.low_top_of_page_bid_micros:
                low_bids.append(m.low_top_of_page_bid_micros / 1_000_000)
            if m.high_top_of_page_bid_micros:
                high_bids.append(m.high_top_of_page_bid_micros / 1_000_000)
            if m.avg_monthly_searches:
                monthly_searches.append(m.avg_monthly_searches)
            if m.competition_index:
                comp_indexes.append(m.competition_index)
            if m.competition:
                comp_levels.append(m.competition.name)
    except GoogleAdsException as ex:
        print(f"    [!] API Exception for Criteria ID {criteria_id}: {ex}")

    avg_low = float(np.mean(low_bids)) if low_bids else 0.0
    avg_high = float(np.mean(high_bids)) if high_bids else 0.0
    avg_mid = (avg_low + avg_high) / 2.0
    total_volume = int(np.sum(monthly_searches)) if monthly_searches else 0
    avg_comp_idx = int(np.mean(comp_indexes)) if comp_indexes else 0
    top_comp_level = comp_levels[0] if comp_levels else "UNKNOWN"

    return {
        "api_cpc_low": round(avg_low, 2),
        "api_cpc_mid": round(avg_mid, 2),
        "api_cpc_high": round(avg_high, 2),
        "avg_monthly_searches": total_volume,
        "competition_index": avg_comp_idx,
        "competition_level": top_comp_level
    }

def process_daily_cpc_analysis(target_date=None):
    bq_client = get_bq_client()
    if target_date is None:
        target_date = date.today().isoformat()

    print(f"\n[+] Processing Scraped_Date = '{target_date}' from BigQuery...")
    query = f"SELECT * FROM `{RAW_TABLE}` WHERE Scraped_Date = '{target_date}'"
    df = bq_client.query(query).to_dataframe()

    if df.empty:
        print(f"[!] No records found for date {target_date}.")
        return

    df.columns = [c.replace(" ", "_").replace(",", "_") for c in df.columns]

    # --- 1. DUAL TOP 5% QUANTILE FILTERING ---
    df["payout_quantile_95"] = df.groupby("Offer_Category")["Average_Bid"].transform(lambda x: x.quantile(0.95))
    df["is_top_5_percent"] = df["Average_Bid"] >= df["payout_quantile_95"]

    df["activity_score"] = df["Average_Bid"] * df["Number_of_bids"]
    df["activity_quantile_95"] = df.groupby("Offer_Category")["activity_score"].transform(lambda x: x.quantile(0.95))
    df["is_high_activity"] = df["activity_score"] >= df["activity_quantile_95"]

    top_df = df[df["is_top_5_percent"] | df["is_high_activity"]].copy()
    top_df["zip_code"] = top_df["zip_code"].astype(str).str.zfill(5)

    print(f"[+] Total raw rows: {len(df)} | Qualified Top 5% ZIP targets: {len(top_df)}")

    # --- 2. MAP ZIP TO GOOGLE CRITERIA IDS ---
    gads_client = get_gads_client()
    customer_id = os.environ.get("GADS_LOGIN_CUSTOMER_ID")

    zip_map = build_zip_to_criteria_id_map(gads_client, customer_id, top_df["zip_code"].unique())
    top_df["geo_criteria_id"] = top_df["zip_code"].map(zip_map).fillna("2840")

    # --- 3. FETCH ZIP-LEVEL GOOGLE ADS API METRICS ---
    api_results = []
    print(f"[+] Fetching hyper-local Google Ads metrics per ZIP code...")
    
    for idx, row in top_df.iterrows():
        cat = row["Offer_Category"]
        cid = row["geo_criteria_id"]
        seeds = CATEGORY_SEED_KEYWORDS.get(cat, ["services near me", f"{cat.lower()} contractor"])
        
        metrics = fetch_zip_level_gads_data(gads_client, customer_id, cid, seeds)
        api_results.append(metrics)

    res_df = pd.DataFrame(api_results)
    for col in res_df.columns:
        top_df[col] = res_df[col].values

    # --- 4. BENCHMARK CALCULATIONS & EXPLICIT REASONING ---
    # 12x Rule Limits
    top_df["limit_12x_cpc"] = (top_df["Average_Bid"] / 12.0).round(2)
    top_df["status_12x_low"] = np.where(top_df["api_cpc_low"] <= top_df["limit_12x_cpc"], "PASS", "FAIL")
    top_df["status_12x_mid"] = np.where(top_df["api_cpc_mid"] <= top_df["limit_12x_cpc"], "PASS", "FAIL")
    top_df["status_12x_high"] = np.where(top_df["api_cpc_high"] <= top_df["limit_12x_cpc"], "PASS", "FAIL")

    # 2.24% Funnel Math (Breakeven & Target 30% Margin)
    top_df["breakeven_funnel_cpc"] = (top_df["Average_Bid"] * 0.0224).round(2)
    top_df["target_30margin_funnel_cpc"] = (top_df["Average_Bid"] * 0.01568).round(2)
    top_df["status_funnel_low"] = np.where(top_df["api_cpc_low"] <= top_df["target_30margin_funnel_cpc"], "PASS", "FAIL")
    top_df["status_funnel_mid"] = np.where(top_df["api_cpc_mid"] <= top_df["target_30margin_funnel_cpc"], "PASS", "FAIL")
    top_df["status_funnel_high"] = np.where(top_df["api_cpc_high"] <= top_df["target_30margin_funnel_cpc"], "PASS", "FAIL")

    # Clear Decision Tier and Reason Assignment
    conditions = [
        # Filter 1: Zero Demand
        top_df["avg_monthly_searches"] == 0,
        # Filter 2: Fully Profitable (Validated at High Bid)
        (top_df["status_12x_high"] == "PASS") & (top_df["status_funnel_high"] == "PASS"),
        # Filter 3: Marginal Profitability (Low or Mid Bid Only)
        (top_df["status_12x_low"] == "PASS") | (top_df["status_funnel_low"] == "PASS")
    ]
    
    tier_choices = [
        "Non-Viable (Exclude ZIP)",
        "Profitable (High Bid Validated)",
        "Marginal (Low/Mid Bid Only)"
    ]
    
    reason_choices = [
        "REASON: NO_SEARCH_DEMAND (High payout but zero monthly search volume in Google)",
        "REASON: HIGH_BID_VALIDATED_PROFITABLE (Passes 12x limit & 30% margin target on high CPC)",
        "REASON: LOW_BID_ONLY_PROFITABLE (Profitable on Low/Mid bid, but High CPC exceeds margin)"
    ]
    
    top_df["ZIP_Viability_Tier"] = np.select(conditions, tier_choices, default="Non-Viable (Exclude ZIP)")
    top_df["Viability_Reason"] = np.select(conditions, reason_choices, default="REASON: CPC_EXCEEDS_12X_AND_FUNNEL (Live CPCs exceed both 12x limit and funnel margin)")

    output_df = top_df.drop(columns=["payout_quantile_95", "activity_score", "activity_quantile_95"], errors="ignore")

    # --- 5. APPEND TO BIGQUERY ---
    print(f"[+] Streaming {len(output_df)} ZIP-evaluated rows to BigQuery: {EVALUATED_TABLE}...")
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=bigquery.TimePartitioning(field="Scraped_Date")
    )
    job = bq_client.load_table_from_dataframe(output_df, EVALUATED_TABLE, job_config=job_config)
    job.result()
    print(f"[✓] Successfully finished ZIP analysis for date: {target_date}")

if __name__ == "__main__":
    process_daily_cpc_analysis()
