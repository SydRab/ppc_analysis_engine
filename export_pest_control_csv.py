import os
import time
import pandas as pd
import numpy as np
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# Your target Pest Control ZIP codes
TARGET_ZIPS = [
    "56303", "21601", "07601", "07310", "46107", 
    "07094", "46307", "53406", "37013", "37129"
]

PEST_CONTROL_SEEDS = [
    "pest control near me", 
    "exterminator service", 
    "termite control"
]

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

def get_geo_target_id_for_zip(gads_client, customer_id, zip_code):
    ga_service = gads_client.get_service("GoogleAdsService")
    query = f"SELECT geo_target_constant.id, geo_target_constant.name FROM geo_target_constant WHERE geo_target_constant.name = '{zip_code}' AND geo_target_constant.country_code = 'US' AND geo_target_constant.target_type = 'Postal Code'"
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            return row.geo_target_constant.id
    except Exception:
        pass
    return None

def fetch_all_keyword_ideas_for_zip(gads_client, customer_id, geo_target_id, zip_code, seeds):
    gtc_service = gads_client.get_service("KeywordPlanIdeaService")
    geo_service = gads_client.get_service("GeoTargetConstantService")
    
    request = gads_client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = "languageConstants/1000" # English
    
    if geo_target_id:
        request.geo_target_constants.append(geo_service.geo_target_constant_path(str(geo_target_id)))
    else:
        request.geo_target_constants.append(geo_service.geo_target_constant_path("2840")) # Fallback US National

    request.include_adult_keywords = False
    request.keyword_plan_network = gads_client.get_type("KeywordPlanNetworkEnum").KeywordPlanNetwork.GOOGLE_SEARCH
    request.keyword_seed.keywords.extend(seeds)

    extracted_rows = []

    try:
        response = gtc_service.generate_keyword_ideas(request=request)
        for result in response:
            m = result.keyword_idea_metrics
            keyword_text = getattr(result, "text", "Unknown Keyword")
            
            low_bid = m.low_top_of_page_bid_micros / 1_000_000 if m.low_top_of_page_bid_micros else 0.0
            high_bid = m.high_top_of_page_bid_micros / 1_000_000 if m.high_top_of_page_bid_micros else 0.0
            avg_bid = round((low_bid + high_bid) / 2.0, 2)
            
            extracted_rows.append({
                "zip_code": zip_code,
                "geo_criteria_id": str(geo_target_id) if geo_target_id else "2840",
                "suggested_keyword": keyword_text,
                "avg_monthly_searches": m.avg_monthly_searches if m.avg_monthly_searches else 0,
                "competition_level": m.competition.name if m.competition else "UNKNOWN",
                "competition_index": m.competition_index if m.competition_index else 0,
                "low_top_of_page_bid_usd": round(low_bid, 2),
                "high_top_of_page_bid_usd": round(high_bid, 2),
                "avg_top_of_page_bid_usd": avg_bid
            })
    except GoogleAdsException as ex:
        print(f"    [!] API Exception for ZIP {zip_code}: {ex}")

    # If no specific keyword ideas returned, provide a fallback row for the ZIP
    if not extracted_rows:
        extracted_rows.append({
            "zip_code": zip_code,
            "geo_criteria_id": str(geo_target_id) if geo_target_id else "2840",
            "suggested_keyword": "NO_IDEAS_RETURNED",
            "avg_monthly_searches": 0,
            "competition_level": "UNKNOWN",
            "competition_index": 0,
            "low_top_of_page_bid_usd": 0.0,
            "high_top_of_page_bid_usd": 0.0,
            "avg_top_of_page_bid_usd": 0.0
        })

    return extracted_rows

def main():
    gads_client = get_gads_client()
    customer_id = os.environ.get("GADS_LOGIN_CUSTOMER_ID")

    print(f"[+] Querying Google Ads API for {len(TARGET_ZIPS)} target ZIP codes...")
    all_results = []

    for z in TARGET_ZIPS:
        print(f" -> Processing ZIP: {z}")
        geo_id = get_geo_target_id_for_zip(gads_client, customer_id, z)
        zip_metrics = fetch_all_keyword_ideas_for_zip(gads_client, customer_id, geo_id, z, PEST_CONTROL_SEEDS)
        all_results.extend(zip_metrics)
        time.sleep(0.4)

    final_df = pd.DataFrame(all_results)
    
    output_filename = "pest_control_api_raw_output.csv"
    final_df.to_csv(output_filename, index=False)
    print(f"[✓] Successfully exported raw API results to: {output_filename}")

if __name__ == "__main__":
    main()
