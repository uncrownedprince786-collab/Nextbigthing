"""Survivorship profile of the stored universe, and what it leaves out.

    python tools/foundation/survivorship.py

Three questions, each answered from evidence and none by assumption:

1. What does the universe contain? Read-only aggregate counts from the database: how many assets
   have a series that ends before today (a delisting would look like that), how many start late,
   and how many names have data in each year.
2. What did it leave out? S&P 500 removals since 2019 from Wikipedia's "Historical components"
   page, matched by symbol against the universe, and classified by the stated reason.
3. Can the missing names be recovered? A probe of Yahoo's chart endpoint for each absent symbol,
   counting how many return daily bars from 2019 on. Prices themselves stay in `.cache` (ignored);
   only counts and summary statistics are written to the repository.

The answer to (1) decides how to read everything else: a universe in which every series reaches
today contains no failure, no delisting and no takeover, so any backtest on it is run on
survivors.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
CACHE = ROOT / ".cache" / "foundation"
OUT = ROOT / "data" / "foundation" / "survivorship"
UA = "NextBigThing-research/1.0 (contact claude.pro@thedg.group)"
FROM, TO = date(2019, 1, 2), date(2026, 9, 1)


def fetch(url: str) -> bytes:
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 400):
                raise
            time.sleep(2 * (i + 1))
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 * (i + 1))
    raise RuntimeError(url)


def clean(cell: str) -> str:
    cell = re.sub(r"<ref[^>]*?/>|<ref.*?</ref>", "", cell, flags=re.S)
    cell = re.sub(r"\{\{[^}|]*\|([^}|]*)[^}]*\}\}", r"\1", cell)
    cell = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", cell)
    return re.sub(r"\s+", " ", cell.replace("'''", "")).strip()


def removals() -> list[dict]:
    path = CACHE / "sp500_hist.wt"
    CACHE.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(fetch("https://en.wikipedia.org/w/index.php?title=Historical_components_of_the_S%26P_500&action=raw"))
    text = path.read_text(encoding="utf-8")
    out = []
    for block in text.split("\n|-")[1:]:
        cells = [clean(c) for c in re.split(r"\n\|\|?", block) if c.strip()]
        if len(cells) < 6:
            continue
        try:
            d = datetime.strptime(cells[0].replace(",", ""), "%B %d %Y").date()
        except ValueError:
            continue
        added, added_name, removed, removed_name, reason = cells[1], cells[2], cells[3], cells[4], cells[5]
        out.append({"date": d, "added": added, "removed": removed, "removedName": removed_name, "reason": reason})
    return out


def classify(reason: str) -> str:
    r = reason.lower()
    if re.search(r"bankrupt|chapter 11|insolven", r):
        return "bankruptcy"
    if re.search(r"acquir|merge|buyout|take.?private|purchase|combined", r):
        return "acquired-or-merged"
    if re.search(r"spin|split", r):
        return "spin-off"
    if re.search(r"market cap|capitalization|size|representation", r):
        return "market-cap-drift"
    return "other"


def universe() -> dict:
    from nbt import db
    cur = db().cursor()
    cur.execute('SELECT symbol FROM "Asset"')
    symbols = {r["symbol"].upper() for r in cur.fetchall()}
    cur.execute('''WITH s AS (SELECT "assetId", min(date) f, max(date) l FROM "PriceSnapshot" GROUP BY 1)
                   SELECT a."assetType"::text t, a.active, count(*) n,
                          count(*) FILTER (WHERE s.l < current_date - 10) ends_before_today,
                          count(*) FILTER (WHERE s.f > %s) starts_after_2019
                   FROM "Asset" a LEFT JOIN s ON s."assetId" = a.id GROUP BY 1, 2 ORDER BY 1, 2''', (FROM,))
    prof = [{k: (int(v) if isinstance(v, (int,)) or str(v).isdigit() else v) for k, v in r.items()} for r in cur.fetchall()]
    cur.execute('''SELECT extract(year from date)::int y, count(DISTINCT "assetId") n
                   FROM "PriceSnapshot" GROUP BY 1 ORDER BY 1''')
    years = {int(r["y"]): int(r["n"]) for r in cur.fetchall()}
    return {"symbols": symbols, "profile": prof, "assetsWithDataByYear": years}


def probe(sym: str) -> dict:
    """Does Yahoo still serve daily bars for this symbol from 2019 on? Counts only."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) +
           f"?period1={int(datetime(2019, 1, 1, tzinfo=timezone.utc).timestamp())}"
           f"&period2={int(time.time())}&interval=1d")  # range=max silently returns monthly bars
    try:
        j = json.loads(fetch(url))
        res = j["chart"]["result"][0]
        ts = res.get("timestamp") or []
        closes = res["indicators"]["quote"][0].get("close") or []
        pts = [(datetime.fromtimestamp(t, timezone.utc).date(), c) for t, c in zip(ts, closes) if c is not None]
        pts = [(d, c) for d, c in pts if d >= FROM]
        if not pts:
            return {"bars": 0}
        return {"bars": len(pts), "first": pts[0][0].isoformat(), "last": pts[-1][0].isoformat(),
                "totalReturnPct": round((pts[-1][1] / pts[0][1] - 1) * 100, 1)}
    except urllib.error.HTTPError as e:
        return {"bars": 0, "http": e.code}
    except Exception as e:  # noqa: BLE001
        return {"bars": 0, "error": type(e).__name__}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    u = universe()
    rem = [r for r in removals() if FROM <= r["date"] <= TO and r["removed"]]
    for r in rem:
        r["kind"] = classify(r["reason"])
        r["inUniverse"] = r["removed"].upper() in u["symbols"]
    absent = [r for r in rem if not r["inUniverse"]]
    kinds: dict[str, dict] = {}
    for r in rem:
        k = kinds.setdefault(r["kind"], {"removed": 0, "absentFromUniverse": 0, "recoverable": 0})
        k["removed"] += 1
        k["absentFromUniverse"] += not r["inUniverse"]
    seen: dict[str, dict] = {}
    for r in absent:
        if r["removed"] not in seen:
            seen[r["removed"]] = probe(r["removed"])
            time.sleep(0.4)
        r["probe"] = seen[r["removed"]]
        # At least a year of bars after 2019 counts as recoverable for a history test.
        if r["probe"].get("bars", 0) >= 250:
            kinds[r["kind"]]["recoverable"] += 1
    recov = [r for r in absent if r["probe"].get("bars", 0) >= 250]
    rets = [r["probe"]["totalReturnPct"] for r in recov if "totalReturnPct" in r["probe"]]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "range": [FROM.isoformat(), TO.isoformat()],
        "universe": {"profile": u["profile"], "assetsWithDataByYear": u["assetsWithDataByYear"],
                     "assetsThatEndBeforeToday": sum(p["ends_before_today"] for p in u["profile"]),
                     "assets": sum(p["n"] for p in u["profile"])},
        "sp500RemovalsInRange": len(rem),
        "removalsAbsentFromUniverse": len(absent),
        "removalsPresentInUniverse": len(rem) - len(absent),
        "byReason": kinds,
        "absentWithAtLeastOneYearOfRecoverableBars": len(recov),
        "absentWithNoRecoverableHistory": len(absent) - len(recov),
        "recoverableTotalReturnPct": {
            "n": len(rets), "median": sorted(rets)[len(rets) // 2] if rets else None,
            "mean": round(sum(rets) / len(rets), 1) if rets else None},
        "caveats": [
            "Removal reasons are classified from Wikipedia's free text and are approximate.",
            "A symbol can be re-used by a different company; recoverable bars are not matched by identifier.",
            "Total return is price-only, over only the bars Yahoo still serves, and is not a bias estimate.",
            "S&P 500 removals are a sample of failures and takeovers, not the whole delisted population.",
        ],
        "sample": [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in absent[:15]],
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("sample", "caveats")}, indent=1, default=str))


if __name__ == "__main__":
    main()
