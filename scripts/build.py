#!/usr/bin/env python3
"""raw/<key>.json (Triple Whale) + config → public/data/latest.json (plain; encrypt_data.py encrypts it)."""
import calendar, json, os, pathlib
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "public" / "data"


def config():
    return json.loads(os.environ.get("CBO_CONFIG") or (ROOT / "config.json").read_text())


def f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def div(a, b):
    return a / b if b else None


def chg(a, b):
    return a / b - 1 if (a is not None and b) else None


def client_block(c, raw, target):
    end = date.fromisoformat(raw["end"])
    today = raw["today"]
    E, D = end.day, calendar.monthrange(end.year, end.month)[1]
    mstart = end.replace(day=1)
    pm_end = mstart - timedelta(days=1)
    pm_start = pm_end.replace(day=1)
    days = []
    for m in sorted(raw["meta"], key=lambda r: r["d"]):
        days.append({
            "d": m["d"][:10], "meta": f(m.get("meta_spend")), "rev": f(m.get("meta_rev")), "orders": f(m.get("meta_orders")),
            "imps": f(m.get("imps")), "clk": f(m.get("clk")), "nv": f(m.get("nv")), "vis": f(m.get("vis")),
            "ours": f(m.get("ours_spend")), "ours_rev": f(m.get("ours_meta_rev")), "ours_orders": f(m.get("ours_meta_orders")),
            "ours_nv": f(m.get("ours_nv")), "ours_vis": f(m.get("ours_vis")),
        })
    by = {x["d"]: x for x in days}
    full = [x for x in days if x["d"] <= raw["end"]]

    def tot(rows, k):
        return sum(x[k] for x in rows)

    def window(a, b):
        return [x for x in full if a <= x["d"] <= b]

    yd = by.get(raw["end"], {k: 0 for k in days[0]} if days else {})
    p7 = window((end - timedelta(days=7)).isoformat(), (end - timedelta(days=1)).isoformat())
    mtd = window(mstart.isoformat(), raw["end"])
    pm = window(pm_start.isoformat(), pm_end.isoformat())
    pm_same = window(pm_start.isoformat(), (pm_start + timedelta(days=E - 1)).isoformat())
    td = by.get(today)

    def kpis(rows):
        me, r, n, o = tot(rows, "meta"), tot(rows, "rev"), tot(rows, "orders"), tot(rows, "ours")
        im = tot(rows, "imps")
        return {
            "meta": me, "rev": r, "orders": n, "roas": div(r, me), "cpa": div(me, n), "aov": div(r, n),
            "cpm": div(me * 1000, im), "ctr": div(tot(rows, "clk"), im), "nvp": div(tot(rows, "nv"), tot(rows, "vis")),
            "ours": o, "ours_share": div(o, me), "ours_roas": div(tot(rows, "ours_rev"), o),
            "ours_cpa": div(o, tot(rows, "ours_orders")), "ours_nvp": div(tot(rows, "ours_nv"), tot(rows, "ours_vis")),
        }

    Y, M, P7, PM, PMS = kpis([yd] if yd else []), kpis(mtd), kpis(p7), kpis(pm), kpis(pm_same)
    avg7 = {k: (v / 7 if k in ("meta", "rev", "orders", "ours") else v) for k, v in P7.items()}
    runrate = M["ours"] / E * D if E else 0
    pace = runrate / target if target else None
    left = D - E
    s = {
        "as_of": raw["end"], "today": today, "days_elapsed": E, "days_in_month": D, "days_left": left,
        "y": Y, "avg7": avg7, "mtd": M, "pm": PM, "pm_same": PMS,
        "today_meta": td["meta"] if td else None, "today_rev": td["rev"] if td else None, "today_ours": td["ours"] if td else None,
        "y_vs7": {k: chg(Y[k], avg7[k]) for k in ("meta", "rev", "roas", "orders", "cpa", "cpm", "ctr", "ours", "nvp", "ours_nvp")},
        "mtd_vs_pm": {k: chg(M[k], PMS[k]) for k in ("meta", "rev", "roas", "orders", "cpa", "cpm", "ctr", "ours")},
        "runrate": runrate, "target": target, "pace": pace,
        "needed_per_day": max(0.0, (target - M["ours"]) / left) if left > 0 else 0.0,
        "rate": c["rate"], "base": c["base"],
        "fee_so_far": c["base"] + c["rate"] * M["ours"], "fee_proj": c["base"] + c["rate"] * runrate,
        "fee_target": c["base"] + c["rate"] * target, "fee_pm": c["base"] + c["rate"] * PM["ours"],
        "meta_runrate": M["meta"] / E * D if E else 0,
    }
    lvl = "ok" if (pace or 0) >= 1 else "warn" if (pace or 0) >= 0.5 else "bad"
    s["status_level"], s["status"] = lvl, {"ok": "On pace", "warn": "Behind target", "bad": "Far behind target"}[lvl]
    if M["ours"] == 0:
        s["status"], s["status_level"] = "No tagged spend", "bad"

    # Alerts: plain-language flags the operator should look at.
    alerts = []
    v = s["y_vs7"]
    if v["meta"] is not None and v["meta"] <= -0.2:
        alerts.append(["bad", f"Meta spend {abs(v['meta']):.0%} below its 7-day average"])
    if v["roas"] is not None and v["roas"] <= -0.15:
        alerts.append(["bad", f"Meta ROAS {abs(v['roas']):.0%} below its 7-day average"])
    if v["roas"] is not None and v["roas"] >= 0.15:
        alerts.append(["ok", f"Meta ROAS {v['roas']:.0%} above its 7-day average"])
    if Y["ours"] == 0 and M["ours"] > 0:
        alerts.append(["warn", "No spend on our creatives on the latest day"])
    if v["ours"] is not None and v["ours"] <= -0.3 and Y["ours"] > 0:
        alerts.append(["warn", f"Our creatives' spend {abs(v['ours']):.0%} below its 7-day average"])
    if v["ours"] is not None and v["ours"] >= 0.3:
        alerts.append(["ok", f"Our creatives' spend {v['ours']:.0%} above its 7-day average"])
    if pace is not None and pace < 0.5 and M["ours"] > 0:
        alerts.append(["bad", f"Our creatives pacing to {pace:.0%} of the ${target/1000:,.0f}K target"])
    s["alerts"] = alerts

    # Ads.
    biz = c.get("business_ids", {})
    ads = []
    for a in raw["ads"]:
        acct = str(a.get("account") or "")
        x = {
            "id": str(a["id"]), "name": a.get("name") or "", "adset": a.get("adset") or "", "campaign": a.get("campaign") or "",
            "act": acct, "biz": biz.get(acct, ""), "ours": int(f(a.get("ours"))) == 1,
            "spend_y": f(a.get("spend_y")), "spend_7": f(a.get("spend_7")), "spend_m": f(a.get("spend_m")), "spend_pm": f(a.get("spend_pm")),
            "roas_7": div(f(a.get("rev_7")), f(a.get("spend_7"))), "roas_m": div(f(a.get("rev_m")), f(a.get("spend_m"))),
            "cpa_7": div(f(a.get("spend_7")), f(a.get("orders_7"))), "cpa_m": div(f(a.get("spend_m")), f(a.get("orders_m"))),
            "nvp_7": div(f(a.get("nv_7")), f(a.get("vis_7"))), "nvp_m": div(f(a.get("nv_m")), f(a.get("vis_m"))),
            "ctr_7": div(f(a.get("clk_7")), f(a.get("imps_7"))),
        }
        ads.append(x)
    top = sorted([a for a in ads if a["spend_7"] > 0], key=lambda a: -a["spend_7"])[:15]
    ours = sorted([a for a in ads if a["ours"] and (a["spend_m"] > 0 or a["spend_7"] > 0)], key=lambda a: -a["spend_m"])[:40]
    total7 = sum(a["spend_7"] for a in ads)
    top_ad_share = div(top[0]["spend_7"], total7) if top else None
    s["top_ad_share_7"] = top_ad_share
    if top_ad_share and top_ad_share >= 0.3:
        alerts.append(["warn", f"One ad carries {top_ad_share:.0%} of Meta spend (last 7 days)"])

    # Launches + hit rate (our tagged ads, by first spend day).
    def cohort(a, b):
        rows = [r for r in raw["launches"] if a <= str(r.get("first_day"))[:10] <= b]
        return {"launched": len(rows), "hit_1k": sum(1 for r in rows if f(r.get("life_spend")) >= 1000),
                "hit_10k": sum(1 for r in rows if f(r.get("life_spend")) >= 10000)}
    s["launch_m"] = cohort(mstart.isoformat(), raw["end"])
    s["launch_pm"] = cohort(pm_start.isoformat(), pm_end.isoformat())

    chart = [{k: x[k] for k in ("d", "meta", "rev", "ours", "nv", "vis", "ours_nv", "ours_vis")} for x in full[-60:]]
    return {"key": c["key"], "name": c["name"], "shop": c["shop"], "tag_label": c.get("tag_label", ""),
            "summary": s, "daily": chart, "top": top, "ours": ours}


def main():
    cfg = config()
    target = cfg.get("target_monthly", 150000)
    clients = []
    for c in cfg["clients"]:
        p = RAW / f"{c['key']}.json"
        if not p.exists():
            print(f"missing raw for {c['name']}")
            continue
        clients.append(client_block(c, json.loads(p.read_text()), target))
    if not clients:
        raise SystemExit("no client data")
    # Totals across clients.
    T = {}
    add = lambda path: sum((cl["summary"][path[0]][path[1]] if len(path) == 2 else cl["summary"][path[0]]) or 0 for cl in clients)
    for per in ("y", "mtd", "pm", "pm_same"):
        T[per] = {k: add((per, k)) for k in ("meta", "rev", "orders", "ours")}
        t = T[per]
        t["roas"], t["cpa"], t["ours_share"] = div(t["rev"], t["meta"]), div(t["meta"], t["orders"]), div(t["ours"], t["meta"])
    T["avg7"] = {k: add(("avg7", k)) for k in ("meta", "rev", "orders", "ours")}
    T["avg7"]["roas"], T["avg7"]["cpa"] = div(T["avg7"]["rev"], T["avg7"]["meta"]), div(T["avg7"]["meta"], T["avg7"]["orders"])
    T["y_vs7"] = {k: chg(T["y"][k], T["avg7"][k]) for k in ("meta", "rev", "ours", "roas", "cpa")}
    T["mtd_vs_pm"] = {k: chg(T["mtd"][k], T["pm_same"][k]) for k in ("meta", "rev", "ours", "roas", "cpa")}
    for k in ("runrate", "target", "needed_per_day", "fee_so_far", "fee_proj", "fee_target", "fee_pm", "base", "today_meta", "today_rev", "meta_runrate"):
        T[k] = add((k,))
    T["pace"] = div(T["runrate"], T["target"])
    T["as_of"] = max(cl["summary"]["as_of"] for cl in clients)
    T["days_left"] = clients[0]["summary"]["days_left"]
    gen = (RAW / "fetched_at.txt").read_text().strip() if (RAW / "fetched_at.txt").exists() else datetime.now(timezone.utc).isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps({"generated_at": gen, "totals": T, "clients": clients}, separators=(",", ":")))
    print(f"latest.json: {len(clients)} clients, as of {T['as_of']}, ours MTD ${T['mtd']['ours']:,.0f}, Meta MTD ${T['mtd']['meta']:,.0f}")


if __name__ == "__main__":
    main()
