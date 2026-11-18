"""Read each brand's ad naming into the dashboard's creative fields.

parse(key, name, adset, campaign) returns a dict with any of: creative_no, product, angle,
concept, icp, format, funnel, strategist, editor, hook, batch, creative_key, display and
structured (True when the name followed the brand's convention).
Every Meta ad of a creative is parsed; the build keeps the first value found, highest spend first.
"""
import re

COPY = re.compile(r"\s*[-–]\s*Copy(\s*\d+)?\s*", re.I)
SEP = re.compile(r"\s+-\s*|\s*-\s+")
DATE = re.compile(r"^\d{1,2}/\d{1,2}(/\d{2,4})?$")


def clean(name):
    return re.sub(r"\s+", " ", COPY.sub(" ", name or "")).strip(" -")


def norm_person(v, aliases=None):
    if not v or v.strip().upper() in ("NONE", "NA", "N/A"):
        return None
    v = v.strip()
    return (aliases or {}).get(v.lower(), v[:1].upper() + v[1:] if v.islower() or v.isupper() else v)


# --- Haritaki / First Eye ----------------------------------------------------------------
# Product - Title - Angle - ICP - Funnel - Format - WS - har-<id>.v1 - Strategist - Hook - Creator - VV - ...
HAR_PEOPLE = {}   # spelling fixes, from the private config


def haritaki(name, adset, campaign):
    n = clean(name)
    parts = [p.strip() for p in SEP.split(n)]
    i = next((k for k, p in enumerate(parts) if re.search(r"\.v\d+$", p, re.I)), None)
    if i is not None and i >= 6 and len(parts) > i + 1:
        stem = re.sub(r"\.v\d+$", "", parts[i], flags=re.I)
        hook = parts[i + 2] if len(parts) > i + 2 and parts[i + 2].upper() != "NONE" else None
        return {"structured": True, "creative_no": stem, "creative_key": stem.upper(), "product": parts[0],
                "concept": " - ".join(parts[1:i - 5]), "angle": parts[i - 5], "icp": parts[i - 4],
                "funnel": parts[i - 3].upper() if parts[i - 3].upper() in ("TOF", "MOF", "BOF") else None,
                "format": parts[i - 2], "strategist": norm_person(parts[i + 1], HAR_PEOPLE), "hook": hook,
                "editor": norm_person(parts[i + 3]) if len(parts) > i + 3 else None, "display": n}
    m = re.match(r"(Top\s*\d+)", n, re.I)
    if m:
        t = re.sub(r"\s+", "", m.group(1)).title()
        return {"concept": t, "creative_key": t.upper(), "batch": "Top ads (renamed 10/25)", "display": t}
    if n.lower().startswith("oldscalingcampad"):
        return {"batch": "Old scaling campaign (renamed 10/26)", "display": "Old scaling ad"}
    return {"display": n}


# --- Blushe ------------------------------------------------------------------------------
# 10.13.26 | 7RW | KBJ > concept - RYAN Hk-02 *L-10.14.26   (ad set often ends in the strategist)
BLU_LP = {"5MP": "5 Most Popular", "7RW": "7 Reasons Why", "7RWT": "7 Reasons Why Tubing"}
BLU_PAGE = {"TBE", "BCP", "KBJ", "BC"}
BLU_PERSON = re.compile(r"(?!x)x")   # never matches until configure() supplies the team's names
BLU_MARK = re.compile(r"\*?L-\d+\.\d+\.\d+|🏆|⬆️?|_?(?<!\d)\d{1,2}\.\d{1,2}\.\d{2}(?!\d)|\.mp4?\b", re.I)
BLU_HOOK = re.compile(r"\bH(?:oo)?k[\s-]*0?(\d+)\b", re.I)


def blushe(name, adset, campaign):
    n = re.sub(r"^\[PURGE\]\s*-\s*", "", clean(name), flags=re.I)
    out = {}
    if ">" in n:
        left, text = n.split(">", 1)
    else:
        bits = [b.strip() for b in n.split("|")]
        left, text = (" | ".join(bits[:-1]), bits[-1]) if len(bits) > 1 else ("", n)
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2})", left)
    if m:
        out["batch"] = f"{int(m.group(1))}.{int(m.group(2))}.{m.group(3)}"
    for code in re.findall(r"[A-Z0-9]{2,5}", left.upper()):
        if code in BLU_LP:
            out["icp"] = BLU_LP[code]
        elif code in BLU_PAGE:
            out["product"] = code
    h = BLU_HOOK.search(text)
    if h:
        out["hook"] = "H" + h.group(1)
    who = BLU_PERSON.search(text)
    title = BLU_HOOK.sub(" ", BLU_MARK.sub(" ", BLU_PERSON.sub(" ", text)))
    title = re.sub(r"(\s*-\s*)+$", "", re.sub(r"\s+", " ", title)).strip(" -_.|")
    set_who = BLU_PERSON.search(adset or "")
    w = set_who or who
    if w:
        out["strategist"] = "Denis" if w.group(1).lower().startswith("den") else w.group(1).title()
    if who and set_who and who.group(1).lower() != set_who.group(1).lower():
        out["editor"] = who.group(1).title()
    if title and ">" in n or (title and len(n.split("|")) > 1):
        out.update(structured=True, concept=title, creative_key=re.sub(r"\W+", "", title).upper(),
                   display=f"{title} · {out['hook']}" if out.get("hook") else title)
    else:
        out["display"] = title or n
    return out


# --- Seora -------------------------------------------------------------------------------
# Ad set: Title - Dennis - [Black|White|WW -] 10/28 [- Copy]; ad: 122 - H2, T-216, Mother of the bride
SEO_GENERIC = re.compile(r"^(\d+|H[A-E]|H\d+|V\d+|Ad\d+|Voice \d+|Video \d+|Hook \d+)$", re.I)
SEO_HOOK = re.compile(r"\s*-\s*(H[A-E]|H\d+|V\d+|Ad\d+)\s*$", re.I)
SEO_AUD = re.compile(r"^(VC\b|ATC\b|Inactive|Batch \d|retargeting|Hero|slightly|Adset\b|Ad set\b)", re.I)
SEO_BATCH = re.compile(r"^(Task \d+|T-?\d+)$", re.I)
SEO_CODE = re.compile(r"^(T-?\d+|Brief \d+|\d+)$", re.I)
SEO_CODES = set()   # strategist initials used in ad set names, from the private config


def seora(name, adset, campaign):
    n = clean(name)
    h = SEO_HOOK.search(n)
    stem = SEO_HOOK.sub("", n).strip()
    out = {"display": n}
    if h:
        out["hook"] = h.group(1).upper()
    if SEO_CODE.match(stem):
        out["creative_no"] = stem
    s = clean(adset)
    title = None
    who = re.search(r"(?<![A-Za-z])(denn?is)(?![A-Za-z])", s, re.I)
    parts = [p.strip() for p in SEP.split(s)]
    if who:
        out["strategist"] = "Dennis"
        title = s[:who.start()].strip(" -:")
    elif len(parts) >= 3 and parts[1].lower() in SEO_CODES and not SEO_AUD.match(s):
        out["strategist"] = parts[1].upper()
        title = parts[0]
    for p in parts:
        if p.lower() in ("black", "white"):
            out["icp"] = p.title()
    if title and SEO_BATCH.match(title):
        out["batch"] = title
        title = None
    generic = not stem or SEO_GENERIC.match(stem)
    concept = title or (None if generic or SEO_CODE.match(stem) else stem)
    if concept:
        out.update(structured=bool(title or who), concept=concept)
        out["creative_key"] = re.sub(r"\W+", "", (concept + ("|" + stem if SEO_CODE.match(stem) else ""))).upper()
        same = n.lower().startswith(concept.lower()[:8])
        out["display"] = n if same else f"{concept} · {n}"
    elif generic:
        out["display"] = f"{parts[0]} · {n}" if parts and parts[0] else n
    c = (campaign or "").lower()
    out["product"] = "Time Reverse Cream" if "time reverse" in c else "Brightening Cream" if "bright" in c else None
    out["funnel"] = "BOF" if c.startswith("bof") else "TOF" if c.startswith("tof") else None
    if "50+" in c:
        out.setdefault("icp", "50+")
    text = f"{s} {n}".lower()
    out["format"] = ("Animated" if re.search(r"animat|pixar", text) else "Song" if re.search(r"\bsong\b", text)
                     else "Skit" if "skit" in text else None)
    return out


PARSERS = {"har": haritaki, "blu": blushe, "seo": seora}
LABELS = {"blu": {"product": "Facebook Page", "icp": "Landing Page Code", "batch": "Launch Batch"},
          "seo": {"icp": "Audience"}}


def configure(client):
    """Team names stay in the private config (CBO_CONFIG), not in this public repo."""
    global BLU_PERSON, SEO_CODES
    n = client.get("naming") or {}
    HAR_PEOPLE.clear()
    HAR_PEOPLE.update(n.get("aliases") or {})
    SEO_CODES = {x.lower() for x in n.get("codes") or []}
    if n.get("people"):
        BLU_PERSON = re.compile(r"(?<![A-Za-z])(" + "|".join(map(re.escape, n["people"])) + r")(?![A-Za-z])", re.I)


def parse(key, name, adset, campaign):
    fn = PARSERS.get(key)
    return {k: v for k, v in (fn(name, adset, campaign) if fn else {"display": clean(name)}).items() if v not in (None, "")}
