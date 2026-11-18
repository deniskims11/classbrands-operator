#!/usr/bin/env python3
"""LOCAL PREVIEW ONLY: writes synthetic raw/<key>.json so the page can be checked without a Triple Whale key."""
import json, pathlib, random
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)
random.seed(7)
end = date(2026, 11, 16)
cfg = json.loads((ROOT / "config.json").read_text())
SCALE = {"har": (66000, 0.98, 0.05), "nr": (24000, 4.2, 0.0), "blu": (46000, 1.45, 0.03), "seo": (9000, 1.55, 0.35)}
for c in cfg["clients"]:
    base, roas, share = SCALE[c["key"]]
    meta = []
    for i in range(90, -2, -1):
        d = end - timedelta(days=i)
        b = base * random.uniform(0.85, 1.15) * (0.7 if i == -1 else 1)
        m = b * 0.9
        o = m * share * random.uniform(0.7, 1.3)
        meta.append({"d": d.isoformat(), "meta_spend": m, "meta_rev": m * roas * .6, "meta_orders": m / 70, "nv": m / 7, "vis": m / 3, "imps": m * 50, "clk": m * .6,
                     "ours_spend": o, "ours_meta_rev": o * roas * .55, "ours_meta_orders": o / 80,
                     "ours_nv": o / 5, "ours_vis": o / 2.6})
    ads = []
    for k in range(60):
        s7 = base * 7 * random.paretovariate(1.6) / 60
        ours = k % 4 == 0
        ads.append({"id": str(120250000000000000 + k), "name": f"Sample ad {k + 1} - {'Denis' if ours else 'Team'} - Hook {k % 5 + 1}",
                    "adset": f"Sample ad set {k % 9}", "campaign": "Sample campaign", "account": "0", "ours": 1 if ours else 0,
                    "spend_y": s7 / 7, "spend_7": s7, "spend_m": s7 * 2.2, "spend_pm": s7 * 3, "rev_7": s7 * roas * .6, "rev_m": s7 * 2.2 * roas * .6,
                    "orders_7": s7 / 70, "orders_m": s7 * 2.2 / 70, "nv_7": s7 / 6, "vis_7": s7 / 3, "nv_m": s7 / 2.7, "vis_m": s7 / 1.4,
                    "imps_7": s7 * 50, "clk_7": s7 * .6})
    launches = [{"id": str(k), "name": "x", "first_day": (end - timedelta(days=random.randint(0, 60))).isoformat(),
                 "life_spend": random.paretovariate(1.2) * 300} for k in range(40)]
    (RAW / f"{c['key']}.json").write_text(json.dumps({"key": c["key"], "shop": c["shop"], "end": end.isoformat(),
        "today": (end + timedelta(days=1)).isoformat(), "meta": meta, "ads": ads, "launches": launches}))
(RAW / "fetched_at.txt").write_text("2026-11-17T22:00:00Z")
print("sample raw written")
