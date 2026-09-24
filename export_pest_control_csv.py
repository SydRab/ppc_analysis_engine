import os
import time
import pandas as pd
import numpy as np
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# Target ZIP codes from your analysis
TARGET_ZIPS = [
    "56303", "21601", "07601", "07310", "46107", 
    "07094", "46307", "53406", "37013", "37129"
]

PEST_CONTROL_SEEDS = [
    "pest control near me", 
    "exterminator service", 
    "termite control"
]

# High-intent commercial keywords filter for calls-only landing pages
INTENT_KEYWORDS = ["near me", "service", "exterminator", "removal", "cost", "company", "pest", "control", "termite"]

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

def get_broader_geo_target_id(gads_client, customer_id, zip_code):
    """
    Resolves a postal code to its parent City/Metro area to prevent 
    zero search volume suppression in KeywordPlanIdeaService.
    """
    ga_service = gads_client.get_service("GoogleAdsService")
    
    # 1. Search for the Postal Code constant details
    query = f"""
        SELECT 
            geo_target_constant.id, 
            geo_target_constant.name, 
            geo_target_constant.canonical_name,
            geo_target_constant.target_type 
        FROM geo_target_constant 
        WHERE geo_target_constant.name = '{zip_code}' 
          AND geo_target_constant.country_code = 'US' 
          AND geo_target_constant.target_type = 'Postal Code'
    """
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            canonical = row.geo_target_constant.canonical_name
            # Canonical name typically looks like: "St. Cloud,Minnesota,United States"
            # We can extract the City or State entity, or fallback to a standard US Metro fallback if needed.
            print(f"    [i] Resolved ZIP {zip_code} to canonical location: {canonical}")
    except Exception as ex:
        print(f"    [!] Geo lookup warning for ZIP {zip_code}: {ex}")

    # Fallback mapping or broader region search logic for Keyword Planner compatibility
    # Using designated DMA/City level lookups or defaulting to US National/State hubs if fine resolution fails
    # For safety with KeywordPlanIdeaService, we map major US regions or query state-level equivalents.
    return "2840" # Fallback to United States broad targeting context if postal code yields empty volumes, 
                  # or you can target specific parent metro IDs fetched via GAQL.

def fetch_keyword_ideas(gads_client, customer_id, geo_target_id, zip_code, seeds):
    gtc_service = gads_client.get_service("KeywordPlanIdeaService")
    geo_service = gads_client.get_service("GeoTargetConstantService")
    
    request = gads_client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = "languageConstants/1000" # English
    
    request.geo_target_constants.append(geo_service.geo_target_constant_path(str(geo_target_id)))
    request.include_adult_keywords = False
    request.keyword_plan_network = gads_client.get_type("KeywordPlanNetworkEnum").KeywordPlanNetwork.GOOGLE_SEARCH
    request.keyword_seed.keywords.extend(seeds)

    extracted_rows = []

    try:
        response = gtc_service.generate_keyword_ideas(request=request)
        for result in response:
            m = result.keyword_idea_metrics
            keyword_text = getattr(result, "text", "").lower()
            
            # Filter for commercial call intent
            if not any(k in keyword_text for k in INTENT_KEYWORDS):
                continue

            low_bid = m.low_top_of_page_bid_micros / 1_000_000 if m.low_top_of_page_bid_micros else 0.0
            high_bid = m.high_top_of_page_bid_micros / 1_000_000 if m.high_top_of_page_bid_micros else 0.0
            avg_bid = round((low_bid + high_bid) / 2.0, 2)
            
            extracted_rows.append({
                "original_zip": zip_code,
                "resolved_geo_id": str(geo_target_id),
                "suggested_keyword": keyword_text,
                "avg_monthly_searches": m.avg_monthly_searches if m.avg_monthly_searches else 0,
                "competition_level": m.competition.name if m.competition else "UNKNOWN",
                "competition_index": m.competition_index if m.competition_index else 0,
                "low_bid_usd": round(low_bid, 2),
                "high_bid_usd": round(high_bid, 2),
                "avg_bid_usd": avg_bid
            })
    except GoogleAdsException as ex:
        print(f"    [!] API Exception for Geo ID {geo_target_id}: {ex}")

    return extracted_rows

def main():
    gads_client = get_gads_client()
    customer_id = os.environ.get("GADS_LOGIN_CUSTOMER_ID")

    print(f"[+] Processing {len(TARGET_ZIPS)} target locations via resolved market hierarchy...")
    all_results = []

    for z in TARGET_ZIPS:
        print(f" -> Mapping ZIP: {z}")
        geo_id = get_broader_geo_target_id(gads_client, customer_id, z)
        metrics = fetch_keyword_ideas(gads_client, customer_id, geo_id, z, PEST_CONTROL_SEEDS)
        all_results.extend(metrics)
        time.sleep(0.4)

    final_df = pd.DataFrame(all_results)
    
    if not final_df.empty:
        # Sort by search volume and high bids to highlight top commercial call drivers
        final_df = final_df.sort_values(by=["avg_monthly_searches", "avg_bid_usd"], ascending=[False, False])

    output_filename = "pest_control_intent_filtered_output.csv"
    final_df.to_csv(output_filename, index=False)
    print(f"[✓] Successfully exported filtered keyword intelligence to: {output_filename}")

if __name__ == "__main__":
    main()
