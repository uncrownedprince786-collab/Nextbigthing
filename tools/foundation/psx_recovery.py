"""How much of the missing PSX daily history a free source could still supply.

    python tools/foundation/psx_recovery.py [--out DIR] [--limit N]

The stored PSX series comes from the exchange's own daily closing file and holds about twelve dates
a year before 2024 -- monthly, not daily -- becoming daily only in 2025. That is the largest source
gap in the universe and the per-asset coverage figure cannot see it, because it compares each asset
with a calendar built from the same sparse data.

Yahoo serves the Karachi listing as `SYMBOL.KA`, quoted in PKR on exchange KAR, and it is a
different provider from the exchange file. This asks it, for every stored PSX symbol, how many
daily sessions it would serve from 2019 against how many are stored, and reports the shortfall it
could close.

It writes nothing to any database and fetches no more than one request per symbol. Filling the gap
is a production write and belongs to the ingest lane that owns `PriceSnapshot`; what this produces
is the measurement that says whether doing so is worth it, and for which names.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
OUT = ROOT / "data" / "foundation" / "coverage"
BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/120.0 Safari/537.36")
FROM = date(2019, 1, 1)


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def karachi(symbol: str) -> dict[int, int] | None:
    """{year: daily bars Yahoo serves} for this Karachi listing, or None when it serves none."""
    p1 = int(datetime(FROM.year, FROM.month, FROM.day, tzinfo=timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}.KA"
           f"?period1={p1}&period2={int(time.time())}&interval=1d")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER})
        with urllib.request.urlopen(req, timeout=40) as r:
            j = json.loads(r.read())
        res = (j.get("chart") or {}).get("result")
        if not res:
            return None
        res = res[0]
        if res["meta"].get("currency") != "PKR":
            return None
        out: dict[int, int] = defaultdict(int)
        for t, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []):
            if c is not None:
                out[datetime.fromtimestamp(t, timezone.utc).date().year] += 1
        return dict(out) or None
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    from nbt import db
    out = Path(arg("--out") or OUT)
    limit = int(arg("--limit") or 0) or None
    cur = db().cursor()
    cur.execute('''SELECT a.symbol, extract(year from p.date)::int y, count(*) n
                   FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId"
                   WHERE p.source LIKE %s GROUP BY 1, 2 ORDER BY 1, 2''', ("Pakistan%",))
    stored: dict[str, dict[int, int]] = defaultdict(dict)
    for r in cur.fetchall():
        stored[r["symbol"]][r["y"]] = r["n"]
    symbols = sorted(stored)[:limit] if limit else sorted(stored)

    served = 0
    per_year_stored: dict[int, int] = defaultdict(int)
    per_year_available: dict[int, int] = defaultdict(int)
    unserved: list[str] = []
    detail: list[dict] = []
    for i, sym in enumerate(symbols, 1):
        got = karachi(sym)
        time.sleep(0.25)
        if got is None:
            unserved.append(sym)
            continue
        served += 1
        s_tot = sum(stored[sym].values())
        a_tot = sum(got.values())
        for y, n in stored[sym].items():
            per_year_stored[y] += n
        for y, n in got.items():
            per_year_available[y] += n
        detail.append({"symbol": sym, "stored": s_tot, "availableAtYahoo": a_tot,
                       "shortfall": max(0, a_tot - s_tot)})
        if i % 25 == 0:
            print(f"  {i}/{len(symbols)} probed, {served} served", flush=True)

    years = sorted(set(per_year_stored) | set(per_year_available))
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "psxSymbolsStored": len(symbols),
        "servedByYahooKarachi": served,
        "notServed": len(unserved),
        "notServedSymbols": unserved[:40],
        "storedBarsTotal": sum(per_year_stored.values()),
        "availableBarsTotal": sum(per_year_available.values()),
        "recoverableBars": max(0, sum(per_year_available.values()) - sum(per_year_stored.values())),
        "byYear": {str(y): {"stored": per_year_stored.get(y, 0),
                            "availableAtYahoo": per_year_available.get(y, 0)} for y in years},
        "worstShortfalls": sorted(detail, key=lambda d: -d["shortfall"])[:20],
        "whatThisIsAndIsNot": [
            "A measurement of what a second free provider would serve, not a repair.",
            "Filling the gap writes to PriceSnapshot and belongs to the ingest lane that owns it.",
            "Yahoo's Karachi close and the exchange file use different adjustment bases, which is "
            "why the independent verification compares them as returns rather than as levels.",
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "psx_recovery.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("worstShortfalls", "whatThisIsAndIsNot", "notServedSymbols")}, indent=1))


if __name__ == "__main__":
    main()
