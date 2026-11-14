"""
Cost per qualified call (CPQC) alert for Pest_US_Search_ZipArbitrage_V1.

Runs on a schedule (GitHub Actions). For "today" (US Pacific, the Ads account time zone) it:
  1. gets spend so far from the Google Ads API
  2. counts qualified calls and payout from BigQuery (marketcall.calls_latest, filled by the postback)
  3. emails an alert (Resend) if:
       - qualified calls >= 1 and spend / qualified calls > CPQC_ALERT_USD, or
       - qualified calls == 0 and spend > CPQC_ALERT_USD (already paying more than one call is worth)
Each alert type is sent at most once per day (logged in marketcall.alert_log).
If the Google Ads API call fails, it falls back to yesterday's final numbers from marketcall.daily_profit.

Env: GCP_SA_KEY_JSON, GADS_CLIENT_ID, GADS_CLIENT_SECRET, GADS_REFRESH_TOKEN, GADS_LOGIN_CUSTOMER_ID,
     RESEND_API_KEY, ALERT_EMAIL_TO, CPQC_ALERT_USD (default 40)
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from google.cloud import bigquery

PROJECT = "ppc-scraper-analysis"
CUSTOMER_ID = "1494941625"
CAMPAIGN_ID = 24317376214
THRESHOLD = float(os.environ.get("CPQC_ALERT_USD", "40"))
ACCOUNT_TZ = ZoneInfo("America/Los_Angeles")


def bq():
    info = json.loads(os.environ["GCP_SA_KEY_JSON"])
    return bigquery.Client.from_service_account_info(info, project=PROJECT)


def usd_inr(client):
    rows = list(client.query(f"SELECT value FROM `{PROJECT}.marketcall.settings` WHERE key = 'usd_inr' LIMIT 1").result())
    return float(rows[0].value) if rows else 95.0


def today_spend_inr():
    from google.ads.googleads.client import GoogleAdsClient
    gads = GoogleAdsClient.load_from_dict({
        "developer_token": "DEVELOPER_TOKEN_NOT_REQUIRED",  # developer tokens were sunset on 9 Sep 2026; Google ignores this value
        "client_id": os.environ["GADS_CLIENT_ID"],
        "client_secret": os.environ["GADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ.get("GADS_LOGIN_CUSTOMER_ID") or None,
        "use_proto_plus": True,
    })
    query = f"""
        SELECT metrics.cost_micros, metrics.clicks
        FROM campaign
        WHERE campaign.id = {CAMPAIGN_ID} AND segments.date DURING TODAY
    """
    cost, clicks = 0, 0
    for batch in gads.get_service("GoogleAdsService").search_stream(customer_id=CUSTOMER_ID, query=query):
        for r in batch.results:
            cost += r.metrics.cost_micros
            clicks += r.metrics.clicks
    return cost / 1e6, clicks


def today_calls(client, day):
    q = f"""
        SELECT COUNT(*) AS calls, COUNTIF(is_qualified) AS qualified,
               SUM(IF(is_qualified, earn, 0)) AS payout
        FROM `{PROJECT}.marketcall.calls_latest`
        WHERE call_date = DATE('{day.isoformat()}')
    """
    r = list(client.query(q).result())[0]
    return r.calls or 0, r.qualified or 0, float(r.payout or 0)


def already_sent(client, day, alert_type):
    q = f"""SELECT COUNT(*) AS n FROM `{PROJECT}.marketcall.alert_log`
            WHERE alert_day = DATE('{day.isoformat()}') AND alert_type = '{alert_type}'"""
    return list(client.query(q).result())[0].n > 0


def log_alert(client, day, alert_type, value, details):
    client.insert_rows_json(f"{PROJECT}.marketcall.alert_log", [{
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "alert_day": day.isoformat(),
        "alert_type": alert_type,
        "value": value,
        "details": details,
    }])


def send_email(subject, html):
    key, to = os.environ.get("RESEND_API_KEY"), os.environ.get("ALERT_EMAIL_TO")
    if not key or not to:
        print("RESEND_API_KEY / ALERT_EMAIL_TO not set, printing instead:\n", subject)
        return
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({"from": "GHD Payout Alerts <onboarding@resend.dev>", "to": [to],
                         "subject": subject, "html": html}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        print("email sent", resp.status)


def main():
    client = bq()
    fx = usd_inr(client)
    day = datetime.now(ACCOUNT_TZ).date()
    source = "today so far (Google Ads API)"
    try:
        spend_inr, clicks = today_spend_inr()
    except Exception as e:
        print("Google Ads API failed, falling back to yesterday from BigQuery:", e)
        rows = list(client.query(f"""
            SELECT day, spend_inr, clicks FROM `{PROJECT}.marketcall.daily_profit`
            WHERE day < CURRENT_DATE('America/Los_Angeles') ORDER BY day DESC LIMIT 1""").result())
        if not rows:
            print("No data yet.")
            return
        day, spend_inr, clicks = rows[0].day, float(rows[0].spend_inr), rows[0].clicks
        source = f"yesterday final ({day}, BigQuery)"

    calls, qualified, payout = today_calls(client, day)
    spend_usd = spend_inr / fx
    cpqc = spend_usd / qualified if qualified else None
    print(f"{day}: spend ${spend_usd:.2f} (₹{spend_inr:.0f}), clicks {clicks}, calls {calls}, qualified {qualified}, payout ${payout:.2f}, CPQC {cpqc}")

    alert_type, headline = None, None
    if qualified and cpqc > THRESHOLD:
        alert_type, headline = "cpqc_high", f"Cost per qualified call ${cpqc:.2f} is above ${THRESHOLD:.0f}"
    elif not qualified and spend_usd > THRESHOLD:
        alert_type, headline = "spend_no_qualified", f"${spend_usd:.2f} spent with 0 qualified calls (limit ${THRESHOLD:.0f})"

    if not alert_type:
        print("Within limits, no alert.")
        return
    if already_sent(client, day, alert_type):
        print("Alert already sent today.")
        return

    html = f"""<div style="font-family:Arial,sans-serif;font-size:14px">
      <p><b>{headline}</b></p>
      <table>
        <tr><td>Period</td><td><b>{source}</b></td></tr>
        <tr><td>Spend</td><td><b>${spend_usd:.2f} (₹{spend_inr:,.0f})</b></td></tr>
        <tr><td>Clicks</td><td><b>{clicks}</b></td></tr>
        <tr><td>Calls / qualified</td><td><b>{calls} / {qualified}</b></td></tr>
        <tr><td>Payout</td><td><b>${payout:.2f}</b></td></tr>
        <tr><td>Profit</td><td><b>${payout - spend_usd:.2f}</b></td></tr>
      </table>
      <p style="color:#777;font-size:12px">Payouts update as Marketcall finalises calls, so check again later today before pausing.</p>
    </div>"""
    send_email(f"[GHD] {headline}", html)
    log_alert(client, day, alert_type, cpqc if cpqc else spend_usd, headline)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("cpqc_alert failed:", e)
        sys.exit(1)
