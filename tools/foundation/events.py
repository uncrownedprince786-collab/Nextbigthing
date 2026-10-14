"""Verify the candidate events and build the corpus.

    python tools/foundation/events.py            # verify everything not yet verified (resumable)
    python tools/foundation/events.py --redo     # discard cached verdicts

Each candidate from events_src.py is checked three ways, and the result is stored with its
evidence rather than as a bare yes:

1. Wikipedia text. The search phrase finds up to four articles; the first one whose body contains
   the claimed date, written out in full, wins. Stored: title, URL, revision id, whether the date
   is in the lead, and a hash of the text that matched. No match means the event is not verified,
   however well known it is.
2. Wikidata. The article's item is read for point-in-time, start, end, inception and publication
   dates. A claim within a day of the candidate date counts. Many items carry none; that is
   recorded as "no structured date", not as a failure.
3. Market reaction, from this repository's own prices. For the event's instrument, the largest
   absolute daily-return z-score (against the preceding 60 returns) in the window from one day
   before to three days after the date. This is evidence the date is the date something moved,
   not evidence the event caused it.

Tiers: A = article match + Wikidata date + a z-score of at least 2; B = article match + one of the
other two; C = article match only; X = no article match. Only A and B count as verified. Wikipedia
and Wikidata are not independent of each other, which is why the market test is part of A.

Resumable: verdicts are cached per event in `.cache/foundation/events_verdicts.json`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "jobs"))
from events_src import E  # noqa: E402

CACHE = ROOT / ".cache" / "foundation" / "events_verdicts.json"
OUT = ROOT / "data" / "foundation" / "events"
UA = "NextBigThing-research/1.0 (mailto:claude.pro@thedg.group)"
WIKI = "https://en.wikipedia.org/w/api.php"


def api(url: str):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=45) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(2 * (i + 1))
    return None


def date_forms(d: date) -> list[str]:
    return [f"{d:%B} {d.day}, {d.year}", f"{d.day} {d:%B} {d.year}"]


def wikipedia(ev: dict) -> dict | None:
    d = date.fromisoformat(ev["date"])
    hits = (api(f"{WIKI}?action=query&list=search&format=json&srlimit=4&srsearch="
                + urllib.parse.quote(ev["query"])) or {}).get("query", {}).get("search", [])
    for h in hits:
        j = api(f"{WIKI}?action=query&format=json&prop=extracts|pageprops|info&explaintext=1"
                f"&inprop=url&ppprop=wikibase_item&titles=" + urllib.parse.quote(h["title"]))
        time.sleep(0.2)
        page = next(iter(((j or {}).get("query", {}).get("pages", {}) or {}).values()), None)
        if not page or "extract" not in page:
            continue
        text = page["extract"]
        pos = [text.find(f) for f in date_forms(d) if f in text]
        if pos:
            return {"title": page["title"], "url": page.get("fullurl"), "revid": page.get("lastrevid"),
                    "dateInLead": min(pos) < 3000, "textSha256": hashlib.sha256(text.encode()).hexdigest()[:16],
                    "qid": (page.get("pageprops") or {}).get("wikibase_item")}
    return None


def wikidata(qid: str | None, d: date) -> dict:
    if not qid:
        return {"checked": False, "reason": "no Wikidata item"}
    j = api(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
    try:
        claims = j["entities"][qid]["claims"]
    except (TypeError, KeyError):
        return {"checked": False, "reason": "entity unreadable"}
    found = []
    for prop in ("P585", "P580", "P582", "P571", "P577"):
        for c in claims.get(prop, []):
            try:
                t = c["mainsnak"]["datavalue"]["value"]["time"]  # +2020-03-11T00:00:00Z
                found.append((prop, date.fromisoformat(t[1:11])))
            except (KeyError, ValueError):
                continue
    if not found:
        return {"checked": False, "reason": "no structured date on the item"}
    near = [p for p, x in found if abs((x - d).days) <= 1]
    return {"checked": True, "match": bool(near), "properties": sorted(set(near)),
            "dates": sorted({x.isoformat() for _, x in found})[:4]}


# ---------- market reaction from the database ----------
_series: dict[str, dict[date, float]] = {}


def load_series() -> None:
    from nbt import db
    cur = db().cursor()
    cur.execute('''SELECT date, avg(r) r FROM (
                     SELECT p.date, p.close / lag(p.close) OVER (PARTITION BY p."assetId" ORDER BY p.date) - 1 r
                     FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId"
                     WHERE a."assetType"::text = 'stock' AND p.source = 'Yahoo Finance') x
                   WHERE r IS NOT NULL AND abs(r) < 0.4 GROUP BY date ORDER BY date''')
    _series["MKT"] = {r["date"]: float(r["r"]) for r in cur.fetchall()}
    cur.execute('''SELECT date, avg(r) r FROM (
                     SELECT p.date, p.close / lag(p.close) OVER (PARTITION BY p."assetId" ORDER BY p.date) - 1 r
                     FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId"
                     WHERE p.source ILIKE 'Pakistan%') x
                   WHERE r IS NOT NULL AND abs(r) < 0.4 GROUP BY date ORDER BY date''')
    _series["PSX"] = {r["date"]: float(r["r"]) for r in cur.fetchall()}
    cur.execute('''SELECT a.symbol, p.date, p.close FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId"
                   WHERE a.symbol IN ('CL=F','GC=F') OR a.symbol LIKE '%USD%' OR a.symbol LIKE 'USD%'
                      OR a.symbol IN ('btc-bitcoin','eth-ethereum')
                      OR a.symbol IN ('GME','NVDA','BA','TSLA','MSFT','META','NFLX','GOOGL','CRWD','INTC','ORCL')
                   ORDER BY a.symbol, p.date''')
    prev: dict[str, float] = {}
    alias = {"CL=F": "OIL", "GC=F": "GOLD", "btc-bitcoin": "BTC", "eth-ethereum": "ETH"}
    for r in cur.fetchall():
        k = alias.get(r["symbol"], r["symbol"])
        c = float(r["close"])
        if k in prev and prev[k] > 0 and abs(c / prev[k] - 1) < 0.6:
            _series.setdefault(k, {})[r["date"]] = c / prev[k] - 1
        prev[k] = c


def reaction(key: str, d: date) -> dict:
    s = _series.get(key)
    used = key
    if not s:
        s, used = _series.get("MKT", {}), "MKT (fallback)"
    days = sorted(s)
    window = [x for x in days if d - timedelta(days=1) <= x <= d + timedelta(days=3)]
    if not window:
        return {"instrument": used, "checked": False, "reason": "no price data in the window"}
    best = None
    for x in window:
        prior = [s[y] for y in days if y < x][-60:]
        if len(prior) < 30:
            continue
        mean = sum(prior) / len(prior)
        sd = math.sqrt(sum((v - mean) ** 2 for v in prior) / (len(prior) - 1)) or 1e-9
        z = (s[x] - mean) / sd
        if best is None or abs(z) > abs(best[1]):
            best = (x, z, s[x])
    if best is None:
        return {"instrument": used, "checked": False, "reason": "not enough history before the window"}
    return {"instrument": used, "checked": True, "peakDate": best[0].isoformat(),
            "z": round(best[1], 2), "returnPct": round(best[2] * 100, 2), "moved": abs(best[1]) >= 2.0}


def tier(wiki, wd, px) -> str:
    if not wiki:
        return "X"
    wd_ok = bool(wd.get("match"))
    px_ok = bool(px.get("moved"))
    if wd_ok and px_ok:
        return "A"
    if wd_ok or px_ok:
        return "B"
    return "C"


def main() -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    cache = {} if "--redo" in sys.argv or not CACHE.exists() else json.loads(CACHE.read_text(encoding="utf-8"))
    load_series()
    for n, ev in enumerate(E, 1):
        key = f"{ev['date']}|{ev['name']}"
        if key in cache:
            continue
        d = date.fromisoformat(ev["date"])
        w = wikipedia(ev)
        wd = wikidata(w["qid"], d) if w else {"checked": False, "reason": "no article"}
        px = reaction(ev["instrument"], d)
        cache[key] = {"wikipedia": w, "wikidata": wd, "market": px, "tier": tier(w, wd, px)}
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
        print(f"{n:3} {cache[key]['tier']} {ev['date']} {ev['name'][:60]}", flush=True)
        time.sleep(0.2)
    rows = []
    for ev in E:
        v = cache[f"{ev['date']}|{ev['name']}"]
        rows.append({**ev, **v, "verified": v["tier"] in ("A", "B")})
    ver = [r for r in rows if r["verified"]]
    cats = defaultdict(lambda: {"candidates": 0, "verified": 0})
    for r in rows:
        cats[r["category"]]["candidates"] += 1
        cats[r["category"]]["verified"] += r["verified"]
    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidates": len(rows), "verifiedEvents": len(ver),
        "distinctVerifiedClusters": len({r["cluster"] for r in ver}),
        "byTier": {t: sum(r["tier"] == t for r in rows) for t in "ABCX"},
        "byCategory": dict(cats),
        "unverified": [{"name": r["name"], "date": r["date"], "tier": r["tier"]} for r in rows if not r["verified"]],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "events.json").write_text(json.dumps({"summary": summary, "events": rows}, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "unverified"}, indent=1))
    print(len(summary["unverified"]), "not verified")


if __name__ == "__main__":
    main()
