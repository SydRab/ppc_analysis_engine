"""On-demand check: current Keyword Planner CPCs for the live campaign's keywords, per state we target.

Pulls the campaign's keywords and the states of its targeted zips straight from Google Ads,
asks Keyword Planner for historical metrics per state, and writes keyword_cpc_check.csv.
Bids come back in account currency (INR) and are also shown in USD.
"""
import os
import time
import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

CUSTOMER_ID = os.environ.get("CHECK_CUSTOMER_ID", "1494941625")
CAMPAIGN_ID = os.environ.get("CHECK_CAMPAIGN_ID", "24317376214")
USD_INR = float(os.environ.get("USD_INR", "95"))


def client():
    return GoogleAdsClient.load_from_dict({
        "developer_token": "DEVELOPER_TOKEN_NOT_REQUIRED",
        "client_id": os.environ["GADS_CLIENT_ID"],
        "client_secret": os.environ["GADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ["GADS_LOGIN_CUSTOMER_ID"],
        "use_proto_plus": True,
    })


def gaql(c, query):
    return list(c.get_service("GoogleAdsService").search(customer_id=CUSTOMER_ID, query=query))


def main():
    c = client()

    keywords = sorted({
        r.ad_group_criterion.keyword.text for r in gaql(c, f"""
            SELECT ad_group_criterion.keyword.text FROM ad_group_criterion
            WHERE campaign.id = {CAMPAIGN_ID} AND ad_group_criterion.type = 'KEYWORD'
              AND ad_group_criterion.negative = FALSE AND ad_group_criterion.status != 'REMOVED'""")
    })
    print(f"[+] {len(keywords)} keywords in campaign")

    zip_ids = [r.campaign_criterion.location.geo_target_constant.split("/")[-1] for r in gaql(c, f"""
        SELECT campaign_criterion.location.geo_target_constant FROM campaign_criterion
        WHERE campaign.id = {CAMPAIGN_ID} AND campaign_criterion.type = 'LOCATION'
          AND campaign_criterion.negative = FALSE""")]
    zips = gaql(c, f"""
        SELECT geo_target_constant.canonical_name
        FROM geo_target_constant WHERE geo_target_constant.id IN ({",".join(zip_ids)})""")
    state_names = pd.Series([z.geo_target_constant.canonical_name.split(",")[-2] for z in zips
                             if len(z.geo_target_constant.canonical_name.split(",")) >= 3])
    zip_counts = state_names.value_counts()
    states = gaql(c, f"""
        SELECT geo_target_constant.resource_name, geo_target_constant.name FROM geo_target_constant
        WHERE geo_target_constant.country_code = 'US' AND geo_target_constant.target_type = 'State'
          AND geo_target_constant.name IN ({",".join("'" + s + "'" for s in zip_counts.index)})""")
    print(f"[+] {len(zip_ids)} zips across {len(states)} states")

    kp = c.get_service("KeywordPlanIdeaService")
    rows = []
    for s in states:
        name = s.geo_target_constant.name
        req = c.get_type("GenerateKeywordHistoricalMetricsRequest")
        req.customer_id = CUSTOMER_ID
        req.keywords.extend(keywords)
        req.language = "languageConstants/1000"
        req.geo_target_constants.append(s.geo_target_constant.resource_name)
        req.keyword_plan_network = c.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
        for attempt in range(4):
            try:
                resp = kp.generate_keyword_historical_metrics(request=req)
                break
            except Exception as ex:
                if "RESOURCE_EXHAUSTED" in str(ex) and attempt < 3:
                    time.sleep(30 * (attempt + 1))
                else:
                    raise
        for r in resp.results:
            m = r.keyword_metrics
            rows.append({
                "state": name,
                "zips_in_state": int(zip_counts.get(name, 0)),
                "keyword": r.text,
                "avg_monthly_searches": m.avg_monthly_searches,
                "low_bid_inr": m.low_top_of_page_bid_micros / 1e6,
                "high_bid_inr": m.high_top_of_page_bid_micros / 1e6,
                "competition": m.competition.name,
            })
        print(f"    {name}: {len(resp.results)} keywords returned")
        time.sleep(1)

    df = pd.DataFrame(rows)
    df["low_bid_usd"] = (df.low_bid_inr / USD_INR).round(2)
    df["high_bid_usd"] = (df.high_bid_inr / USD_INR).round(2)
    df.to_csv("keyword_cpc_check.csv", index=False)

    has = df[df.high_bid_inr > 0]
    print(f"\n[+] Rows with bid data: {len(has)} of {len(df)}")
    if len(has):
        w = has.avg_monthly_searches.clip(lower=10)
        print(f"    Search-weighted high top-of-page bid: ${(has.high_bid_usd * w).sum() / w.sum():.2f}")
        print(f"    Search-weighted low top-of-page bid:  ${(has.low_bid_usd * w).sum() / w.sum():.2f}")
        print(f"    Median high bid: ${has.high_bid_usd.median():.2f}")
    vol = df.groupby("keyword").avg_monthly_searches.sum().sort_values(ascending=False)
    print(f"\n[+] Total monthly searches, all keywords x states: {int(df.avg_monthly_searches.sum())}")
    print(f"    Keywords with 0 searches in every state: {(vol == 0).sum()} of {len(vol)}")
    print("    Top keywords by searches (summed over states):")
    for k, v in vol.head(15).items():
        print(f"      {v:>6}  {k}")
    if len(has):
        print("    Rows with bid data:")
        for _, r in has.sort_values("avg_monthly_searches", ascending=False).iterrows():
            print(f"      {r.state:<15} {r.keyword:<45} searches {r.avg_monthly_searches:>5}  low ${r.low_bid_usd:.2f}  high ${r.high_bid_usd:.2f}")
    print("[✓] Saved keyword_cpc_check.csv")


if __name__ == "__main__":
    main()
