#!/usr/bin/env python3
"""Pull every client's numbers from the Triple Whale SQL API into raw/<key>.json.

Env: TW_API_KEYS (JSON {client key: Triple Whale API key}, one key per shop) and/or
TW_API_KEY (fallback key used for any client not in TW_API_KEYS), plus CBO_CONFIG (JSON;
locally ./config.json). Per shop:
  meta     – daily Meta spend, Meta-reported purchases and value, delivery and visitors,
             total and for our tagged ads (Meta only; no other channels or store totals)
  ads      – per-ad totals for yesterday / last 7 days / month to date / last month
  launches – first spend day + lifetime spend of every tagged ad (hit rate)
"""
import base64, gzip, hashlib, json, os, pathlib, re, sys, time
from datetime import datetime, timedelta, timezone
from urllib import request as urlreq
from urllib.error import HTTPError

API = "https://api.triplewhale.com/api/v2/orcabase/api/sql"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
META = "channel = 'facebook-ads' AND model = 'Triple Attribution' AND attribution_window = '7_days'"
LEDGER_URL = "https://deniskims11.github.io/classbrands-operator/data/ledger.json"
LEDGER_OUT = ROOT / "public" / "data" / "ledger.json"
# Ads launched from this day on also count as ours when they reuse one of our videos or images.
# Older ads go by their names only.
MEDIA_MATCH_FROM = "2026-11-18"


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


def ledger_key(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000, 32)


def load_ledger(password):
    """Our ad IDs and media from earlier runs. Triple Whale only keeps an ad's latest name, so this is
    what keeps a renamed ad ours. It lives encrypted on the site, next to the dashboard data."""
    if not password:
        return {}
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        req = urlreq.Request(f"{LEDGER_URL}?t={int(time.time())}", headers={"user-agent": "Mozilla/5.0 (classbrands-operator refresh)"})
        with urlreq.urlopen(req, timeout=60) as r:
            p = json.load(r)
    except HTTPError as e:
        if e.code == 404:
            print("ledger: none yet, starting one", flush=True)
            return {}
        sys.exit(f"Could not read the ad ID ledger ({e.code}) — keeping the live dashboard as it is")
    b = base64.b64decode
    raw = AESGCM(ledger_key(password, b(p["salt"]))).decrypt(b(p["iv"]), b(p["data"]), None)
    return json.loads(gzip.decompress(raw))


def save_ledger(ledger, password):
    if not password:
        return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(ledger_key(password, salt)).encrypt(iv, gzip.compress(json.dumps(ledger, separators=(",", ":")).encode()), None)
    b = lambda x: base64.b64encode(x).decode()
    LEDGER_OUT.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_OUT.write_text(json.dumps({"encrypted": 1, "salt": b(salt), "iv": b(iv), "data": b(ct)}))


def media_key(row):
    return row.get("vhash") or re.sub(r"\?.*", "", row.get("img") or "")


def resolve_ours(rows, entry, today):
    """Update one client's ledger entry from this run's ads and return the ad IDs that count as ours.
    Once an ad ID is ours it stays ours. New ads reusing our media join it."""
    ads, media = dict(entry.get("ads") or {}), set(entry.get("media") or [])
    for r in rows:
        if int(float(r.get("tagged") or 0)):
            ads.setdefault(r["id"], today)
    for r in rows:
        if r["id"] in ads and media_key(r):
            media.add(media_key(r))
    matched = 0
    for r in rows:
        if r["id"] not in ads and media_key(r) in media and str(r.get("first_day"))[:10] >= MEDIA_MATCH_FROM:
            ads[r["id"]] = today
            matched += 1
    entry.update(ads=ads, media=sorted(media))
    return set(ads), matched


def main():
    password = os.environ.get("DASHBOARD_PASSWORD") or ""
    ledger = load_ledger(password)
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
            rows = sql(shop, f"""
                SELECT toString(ad_id) AS id, max(toUInt8({tag})) AS tagged,
                  argMaxIf(video_content_hash, event_date, video_content_hash != '') AS vhash,
                  argMaxIf(ad_image_url, event_date, ad_image_url != '') AS img,
                  toString(minIf(event_date, spend > 0)) AS first_day
                FROM pixel_joined_tvf()
                WHERE {META} AND event_date BETWEEN '{lookback}' AND '{t}'
                GROUP BY id HAVING sum(spend) > 0""", lookback.isoformat(), t, key)
            entry = ledger.setdefault(c["key"], {})
            ours, matched = resolve_ours(rows, entry, t)
            named = sum(1 for r in rows if int(float(r.get("tagged") or 0)))
            print(f"  ours: {len(ours)} ad IDs ({named} by name now, {matched} new by same media)", flush=True)
            if ours:
                tag = f"({c['tag_sql']} OR toString(ad_id) IN (" + ",".join(f"'{i}'" for i in sorted(ours)) + "))"
            meta = sql(shop, f"""
                SELECT toString(event_date) AS d,
                  sum(spend) AS meta_spend, sum(channel_reported_conversion_value) AS meta_rev,
                  sum(channel_reported_conversions) AS meta_orders,
                  sum(new_visitors) AS nv, sum(unique_visitors) AS vis,
                  sum(impressions) AS imps, sum(outbound_clicks) AS clk,
                  sumIf(spend, {tag}) AS ours_spend,
                  sumIf(channel_reported_conversion_value, {tag}) AS ours_meta_rev,
                  sumIf(channel_reported_conversions, {tag}) AS ours_meta_orders,
                  sumIf(new_visitors, {tag}) AS ours_nv, sumIf(unique_visitors, {tag}) AS ours_vis
                FROM pixel_joined_tvf()
                WHERE {META} AND event_date BETWEEN '{s}' AND '{t}'
                GROUP BY d ORDER BY d""", s, t, key)
            W = lambda a, b: f"event_date BETWEEN '{a}' AND '{b}'"
            ads = sql(shop, f"""
                SELECT toString(ad_id) AS id,
                  argMax(ad_name, event_date) AS name, argMax(adset_name, event_date) AS adset,
                  argMax(campaign_name, event_date) AS campaign,
                  argMaxIf(ad_image_url, event_date, ad_image_url != '') AS img,
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
                WHERE {META} AND event_date BETWEEN '{lookback}' AND '{e}' AND {tag}
                GROUP BY ad_id HAVING life_spend > 0""", lookback.isoformat(), e, key)
        except RuntimeError as err:
            print(f"  FAILED: {err}", flush=True)
            failures.append(c["name"])
            continue
        if not meta:
            print("  no Meta rows", flush=True)
            failures.append(c["name"])
            continue
        (RAW / f"{c['key']}.json").write_text(json.dumps({
            "key": c["key"], "shop": shop, "end": e, "today": t, "meta": meta,
            "ads": ads, "launches": launches}))
        f = lambda rows, k: sum(float(r.get(k) or 0) for r in rows)
        y = [r for r in meta if r["d"] == e]
        print(f"  {len(meta)} days · {e}: Meta spend ${f(y, 'meta_spend'):,.0f}, Meta revenue ${f(y, 'meta_rev'):,.0f} · "
              f"ads {len(ads)} ({sum(int(float(a.get('ours') or 0)) for a in ads)} ours) · launches {len(launches)}", flush=True)
    (RAW / "fetched_at.txt").write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if len(failures) == len(cfg["clients"]):
        sys.exit("Every shop failed — keeping the live dashboard as it is")
    save_ledger(ledger, password)
    if failures:
        print(f"::warning::No fresh data for: {', '.join(failures)}")


if __name__ == "__main__":
    main()
