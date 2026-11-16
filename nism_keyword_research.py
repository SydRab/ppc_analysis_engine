"""On-demand Keyword Planner research for any keyword list across Indian locations.

Built for the MTA NISM coaching check: monthly searches, competition and top-of-page
bids for seed keywords in India, Karnataka and major Karnataka cities, plus the top
related keyword ideas at India level. Writes keyword_research.csv and keyword_ideas.csv.

Uses the same Google Ads API credentials as keyword_cpc_check.py. Keyword Planner
data is not account-specific, so it runs on RESEARCH_CUSTOMER_ID (default: the
Rabbani account) and touches no client campaign.
"""
import os
import time
import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

CUSTOMER_ID = os.environ.get("RESEARCH_CUSTOMER_ID", "1494941625")

DEFAULT_SEEDS = [
    "nism certification", "nism exam", "nism exam preparation", "nism course",
    "nism coaching", "nism classes", "nism training", "nism certification online",
    "nism series 8", "nism series viii", "nism equity derivatives",
    "nism v a", "nism mutual fund exam", "nism series 15", "nism research analyst",
    "nism investment adviser", "nism mock test", "nism study material",
    "nism registration", "nism exam fees", "nism coaching near me",
    "nism exam centre", "nism certification bangalore", "nism coaching bangalore",
]

# Names Google uses for these places can be old or new spellings, so try both.
CITY_NAMES = ["Bengaluru", "Bangalore", "Mysuru", "Mysore", "Hubballi", "Hubli",
              "Mangaluru", "Mangalore", "Belagavi", "Belgaum"]


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


def with_retry(fn):
    for attempt in range(4):
        try:
            return fn()
        except Exception as ex:
            if "RESOURCE_EXHAUSTED" in str(ex) and attempt < 3:
                time.sleep(30 * (attempt + 1))
            else:
                raise


def locations(c):
    """India, Karnataka, and whichever Karnataka city names Google recognises."""
    locs = [("India", "geoTargetConstants/2356")]
    names = ",".join("'" + n + "'" for n in CITY_NAMES + ["Karnataka"])
    rows = gaql(c, f"""
        SELECT geo_target_constant.resource_name, geo_target_constant.name,
               geo_target_constant.canonical_name, geo_target_constant.target_type
        FROM geo_target_constant
        WHERE geo_target_constant.country_code = 'IN'
          AND geo_target_constant.name IN ({names})
          AND geo_target_constant.status = 'ENABLED'""")
    seen = set()
    for r in rows:
        g = r.geo_target_constant
        if "Karnataka" not in g.canonical_name:
            continue
        if g.target_type not in ("City", "State"):
            continue
        if g.canonical_name in seen:
            continue
        seen.add(g.canonical_name)
        locs.append((f"{g.name} ({g.target_type})", g.resource_name))
    return locs


def historical(c, keywords, geo):
    kp = c.get_service("KeywordPlanIdeaService")
    req = c.get_type("GenerateKeywordHistoricalMetricsRequest")
    req.customer_id = CUSTOMER_ID
    req.keywords.extend(keywords)
    req.language = "languageConstants/1000"  # English
    req.geo_target_constants.append(geo)
    req.keyword_plan_network = c.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    return with_retry(lambda: kp.generate_keyword_historical_metrics(request=req)).results


def ideas(c, seeds, geo, limit=60):
    kp = c.get_service("KeywordPlanIdeaService")
    req = c.get_type("GenerateKeywordIdeasRequest")
    req.customer_id = CUSTOMER_ID
    req.language = "languageConstants/1000"
    req.geo_target_constants.append(geo)
    req.include_adult_keywords = False
    req.keyword_plan_network = c.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    req.keyword_seed.keywords.extend(seeds[:20])  # API allows up to 20 seed keywords
    out = []
    for r in with_retry(lambda: kp.generate_keyword_ideas(request=req)):
        m = r.keyword_idea_metrics
        out.append({
            "keyword": r.text,
            "avg_monthly_searches": m.avg_monthly_searches,
            "competition": m.competition.name,
            "low_bid_inr": m.low_top_of_page_bid_micros / 1e6,
            "high_bid_inr": m.high_top_of_page_bid_micros / 1e6,
        })
    df = pd.DataFrame(out)
    return df.sort_values("avg_monthly_searches", ascending=False).head(limit) if len(df) else df


def main():
    c = client()
    seeds = [k.strip() for k in os.environ.get("SEED_KEYWORDS", "").split(",") if k.strip()] or DEFAULT_SEEDS
    locs = locations(c)
    print(f"[+] {len(seeds)} seed keywords, {len(locs)} locations: {[n for n, _ in locs]}")

    rows = []
    for name, geo in locs:
        for r in historical(c, seeds, geo):
            m = r.keyword_metrics
            trend = [(v.year, v.month.name, v.monthly_searches) for v in m.monthly_search_volumes]
            rows.append({
                "location": name,
                "keyword": r.text,
                "avg_monthly_searches": m.avg_monthly_searches,
                "competition": m.competition.name,
                "low_bid_inr": round(m.low_top_of_page_bid_micros / 1e6, 2),
                "high_bid_inr": round(m.high_top_of_page_bid_micros / 1e6, 2),
                "last_12_months": "; ".join(f"{y}-{mo[:3]}:{s}" for y, mo, s in trend[-12:]),
            })
        print(f"    {name}: done")
        time.sleep(1)

    df = pd.DataFrame(rows)
    df.to_csv("keyword_research.csv", index=False)

    print("\n[+] Total monthly searches across all seed keywords, by location:")
    for loc, v in df.groupby("location").avg_monthly_searches.sum().sort_values(ascending=False).items():
        print(f"      {v:>8}  {loc}")

    for loc in df.location.unique():
        sub = df[df.location == loc].sort_values("avg_monthly_searches", ascending=False)
        sub = sub[sub.avg_monthly_searches > 0]
        print(f"\n[+] {loc}: keywords with searches")
        for _, r in sub.iterrows():
            print(f"      {r.avg_monthly_searches:>7}  {r.keyword:<40} {r.competition:<8} "
                  f"bid Rs{r.low_bid_inr:.0f}-{r.high_bid_inr:.0f}")

    india = df[df.location == "India"]
    if len(india):
        print("\n[+] India monthly trend (all seed keywords summed):")
        months = {}
        for t in india.last_12_months:
            for part in filter(None, t.split("; ")):
                k, v = part.rsplit(":", 1)
                months[k] = months.get(k, 0) + int(v)
        for k, v in months.items():
            print(f"      {k}: {v}")

    idf = ideas(c, seeds, "geoTargetConstants/2356")
    idf.to_csv("keyword_ideas.csv", index=False)
    print(f"\n[+] Top related keyword ideas, India ({len(idf)}):")
    for _, r in idf.iterrows():
        print(f"      {r.avg_monthly_searches:>7}  {r.keyword:<45} {r.competition:<8} "
              f"bid Rs{r.low_bid_inr:.0f}-{r.high_bid_inr:.0f}")
    print("[✓] Saved keyword_research.csv and keyword_ideas.csv")


if __name__ == "__main__":
    main()
