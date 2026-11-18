#!/usr/bin/env python3
"""Pull every client's numbers from the Triple Whale SQL API into raw/<key>.json.

Env: TW_API_KEYS (JSON {client key: Triple Whale API key}, one key per shop) and/or
TW_API_KEY (fallback key used for any client not in TW_API_KEYS), plus CBO_CONFIG (JSON;
locally ./config.json). Per shop:
  summary  – daily blended spend / order revenue / orders / new customers (summary_metrics_tvf)
  meta     – daily Meta spend + Meta-reported value + visitors, total and for our tagged ads
  ads      – per-ad totals for yesterday / last 7 days / month to date / last month
  launches – first spend day + lifetime spend of every tagged ad (hit rate)
"""
import json, os, pathlib, sys, time
from datetime import datetime, timedelta, timezone
from urllib import request as urlreq
from urllib.error import HTTPError

API = "https://api.triplewhale.com/api/v2/orcabase/api/sql"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
META = "channel = 'facebook-ads' AND model = 'Triple Attribution' AND attribution_window = '7_days'"


def config():
    return json.loads(os.environ.get("CBO_CONFIG") or (ROOT / "config.json").read_text())


def sql(shop, query, start, end, key, tries=4):
    body = json.dumps({"shopId": shop, "query": query, "period": {"startDate": start, "endDate": end}}).encode()
    for attempt in range(tries):
        req = urlreq.Request(API, data=body, method="POST", headers={
            "x-api-key": key, "content-type": "application/json", "accept": "application/json",
            "user-agent": "Mozilla/5.0 (classbrands-operator refresh)"})
        try:
            with urlreq.urlopen(req, timeout=300) as r:
                data = json.load(r)
            if isinstance(data, dict):
                data = data.get("data") or data.get("rows") or []
            return data
        except HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(f"Triple Whale {e.code} for {shop}: {msg}")
    return []


def main():
    keys = json.loads(os.environ.get("TW_API_KEYS") or "{}")
    fallback = os.environ.get("TW_API_KEY")
    if not keys and not fallback:
        sys.exit("Neither TW_API_KEYS nor TW_API_KEY is set")
    cfg = config()
    # Latest full day in US time (shops report in their own US time zone).
    us_now = datetime.now(timezone.utc) - timedelta(hours=8)
    today = us_now.date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=89)
    mstart = end.replace(day=1)
    pm_end = mstart - timedelta(days=1)
    pm_start = pm_end.replace(day=1)
    lookback = end - timedelta(days=180)
    s, e, t = start.isoformat(), end.isoformat(), today.isoformat()
    d7 = (end - timedelta(days=6)).isoformat()
    d35 = min(pm_start, end - timedelta(days=34)).isoformat()
    RAW.mkdir(exist_ok=True)
    failures = []
    for c in cfg["clients"]:
        shop, tag = c["shop"], f"({c['tag_sql']})"
        print(f"== {c['name']} ({shop})", flush=True)
        key = keys.get(c["key"]) or fallback
        if not key:
            print(f"   no API key for {c['key']}", flush=True)
            failures.append(c["name"])
            continue
        try:
            summary = sql(shop, f"""
                SELECT toString(event_date) AS d,
                  sum(spend) AS blended_spend,
                  sumIf(spend, platform = 'facebook-ads') AS meta_spend,
                  sum(gross_product_sales) - sum(discount_amount_for_product) + sum(shipping_price) + sum(taxes) AS order_rev,
                  sumIf(orders, platform = 'shopify') AS shop_orders,
                  sumIf(new_customer_orders, platform = 'shopify') AS nc_orders,
                  sumIf(new_customer_revenue, platform = 'shopify') AS nc_revenue,
                  sum(total_refunded_price) AS refunds
                FROM summary_metrics_tvf()
                WHERE event_date BETWEEN '{s}' AND '{t}'
                GROUP BY d ORDER BY d""", s, t, key)
            meta = sql(shop, f"""
                SELECT toString(event_date) AS d,
                  sum(spend) AS meta_spend, sum(channel_reported_conversion_value) AS meta_rev,
                  sum(channel_reported_conversions) AS meta_orders,
                  sum(new_visitors) AS nv, sum(unique_visitors) AS vis,
                  sumIf(spend, {tag}) AS ours_spend,
                  sumIf(channel_reported_conversion_value, {tag}) AS ours_meta_rev,
                  sumIf(channel_reported_conversions, {tag}) AS ours_meta_orders,
                  sumIf(new_customer_orders, {tag}) AS ours_nc_orders,
                  sumIf(new_visitors, {tag}) AS ours_nv, sumIf(unique_visitors, {tag}) AS ours_vis
                FROM pixel_joined_tvf()
                WHERE {META} AND event_date BETWEEN '{s}' AND '{t}'
                GROUP BY d ORDER BY d""", s, t, key)
            W = lambda a, b: f"event_date BETWEEN '{a}' AND '{b}'"
            ads = sql(shop, f"""
                SELECT toString(ad_id) AS id,
                  argMax(ad_name, event_date) AS name, argMax(adset_name, event_date) AS adset,
                  argMax(campaign_name, event_date) AS campaign,
                  replaceOne(toString(argMax(account_id, event_date)), 'act_', '') AS account,
                  max(toUInt8({tag})) AS ours,
                  sumIf(spend, event_date = '{e}') AS spend_y,
                  sumIf(spend, {W(d7, e)}) AS spend_7, sumIf(spend, {W(mstart, e)}) AS spend_m,
                  sumIf(spend, {W(pm_start, pm_end)}) AS spend_pm,
                  sumIf(channel_reported_conversion_value, {W(d7, e)}) AS rev_7,
                  sumIf(channel_reported_conversion_value, {W(mstart, e)}) AS rev_m,
                  sumIf(channel_reported_conversions, {W(d7, e)}) AS orders_7,
                  sumIf(channel_reported_conversions, {W(mstart, e)}) AS orders_m,
                  sumIf(new_visitors, {W(d7, e)}) AS nv_7, sumIf(unique_visitors, {W(d7, e)}) AS vis_7,
                  sumIf(new_visitors, {W(mstart, e)}) AS nv_m, sumIf(unique_visitors, {W(mstart, e)}) AS vis_m,
                  sumIf(impressions, {W(d7, e)}) AS imps_7, sumIf(outbound_clicks, {W(d7, e)}) AS clk_7
                FROM pixel_joined_tvf()
                WHERE {META} AND event_date BETWEEN '{d35}' AND '{e}'
                GROUP BY ad_id
                HAVING spend_7 > 0 OR spend_m > 0 OR spend_pm > 0""", d35, e, key)
            launches = sql(shop, f"""
                SELECT toString(ad_id) AS id, argMax(ad_name, event_date) AS name,
                  toString(minIf(event_date, spend > 0)) AS first_day, sum(spend) AS life_spend
                FROM pixel_joined_tvf()
                WHERE {META} AND event_date BETWEEN '{lookback}' AND '{e}' AND ({c['tag_sql']})
                GROUP BY ad_id HAVING life_spend > 0""", lookback.isoformat(), e, key)
        except RuntimeError as err:
            print(f"  FAILED: {err}", flush=True)
            failures.append(c["name"])
            continue
        if not summary:
            print("  no summary rows", flush=True)
            failures.append(c["name"])
            continue
        (RAW / f"{c['key']}.json").write_text(json.dumps({
            "key": c["key"], "shop": shop, "end": e, "today": t, "summary": summary, "meta": meta,
            "ads": ads, "launches": launches}))
        f = lambda rows, k: sum(float(r.get(k) or 0) for r in rows)
        y = [r for r in summary if r["d"] == e]
        print(f"  {len(summary)} days · {e}: blended ${f(y, 'blended_spend'):,.0f}, order rev ${f(y, 'order_rev'):,.0f} · "
              f"ads {len(ads)} ({sum(int(float(a.get('ours') or 0)) for a in ads)} ours) · launches {len(launches)}", flush=True)
    (RAW / "fetched_at.txt").write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if len(failures) == len(cfg["clients"]):
        sys.exit("Every shop failed — keeping the live dashboard as it is")
    if failures:
        print(f"::warning::No fresh data for: {', '.join(failures)}")


if __name__ == "__main__":
    main()
