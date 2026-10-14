"""Earnings-shock events, with the announcement date taken from the SEC's own filing record.

    python tools/foundation/earnings_events.py

For each large US company in the universe, EDGAR's submissions record lists every Form 8-K and the
items it reported. Item 2.02 is "Results of Operations", the earnings release. The filing date is
the SEC's record of when the company made the announcement public, which makes it a primary
source for the date and independent of Wikipedia.

Selection is by price reaction, and that is stated on every row (`selection: price-screened`): of
each company's earnings releases, the ones whose reaction z-score is largest are kept, because a
corpus of events that moved nothing is no use for studying events that did. That makes the market
test trivially true for these rows, so it is NOT counted as a second evidence group here. What
verifies each one is the SEC record, and the row says so.

The reaction is the largest absolute return z-score (against the preceding 60 sessions) on the
filing date and the next session, since a release after the close moves the next day's price.

Output: `data/foundation/events/earnings.json`, merged into the corpus by events.py.
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
OUT = ROOT / "data" / "foundation" / "events" / "earnings.json"
UA = "NextBigThing-research claude.pro@thedg.group"

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "AMD", "INTC", "CRM", "ORCL",
           "ADBE", "JPM", "BAC", "XOM", "BA", "DIS", "NKE", "WMT", "COST", "HD", "KO", "PFE", "CAT",
           "GS", "UBER", "PYPL", "SBUX", "MU"]
PER_TICKER = 3
MIN_Z = 3.5


def get(url: str):
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


def earnings_filings(cik: int) -> list[dict]:
    """Item 2.02 8-Ks from the SEC submissions record, including the older-filings files."""
    base = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    j = get(base)
    if not j:
        return []
    blocks = [j["filings"]["recent"]]
    for f in j["filings"].get("files", []):
        time.sleep(0.15)
        extra = get("https://data.sec.gov/submissions/" + f["name"])
        if extra:
            blocks.append(extra)
    out = []
    for b in blocks:
        for acc, fd, form, items in zip(b["accessionNumber"], b["filingDate"], b["form"], b["items"]):
            if form == "8-K" and "2.02" in (items or "").split(","):
                out.append({"accession": acc, "filingDate": fd,
                            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"})
    return out


def main() -> None:
    from nbt import db
    cur = db().cursor()
    tick = get("https://www.sec.gov/files/company_tickers.json") or {}
    cik_of = {v["ticker"]: v["cik_str"] for v in tick.values()}
    events = []
    for sym in TICKERS:
        cur.execute('''SELECT p.date, p.close FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId"
                       WHERE a.symbol = %s AND p.source = 'Yahoo Finance' ORDER BY p.date''', (sym,))
        px = [(r["date"], float(r["close"])) for r in cur.fetchall()]
        if len(px) < 200 or sym not in cik_of:
            print(f"{sym}: skipped (prices {len(px)}, cik {sym in cik_of})")
            continue
        ret = {px[i][0]: px[i][1] / px[i - 1][1] - 1 for i in range(1, len(px))}
        days = sorted(ret)
        pos = {d: i for i, d in enumerate(days)}
        scored = []
        for f in earnings_filings(cik_of[sym]):
            d = date.fromisoformat(f["filingDate"])
            if not (date(2019, 1, 2) <= d <= date(2026, 9, 1)):
                continue
            best = None
            for x in (d, d + timedelta(days=1), d + timedelta(days=2), d + timedelta(days=3)):
                if x in pos and pos[x] >= 60 and (x == d or x > d):
                    prior = [ret[days[k]] for k in range(pos[x] - 60, pos[x])]
                    mean = sum(prior) / 60
                    sd = math.sqrt(sum((v - mean) ** 2 for v in prior) / 59) or 1e-9
                    z = (ret[x] - mean) / sd
                    if best is None or abs(z) > abs(best[1]):
                        best = (x, z, ret[x])
                    if x > d:
                        break
            if best:
                scored.append((abs(best[1]), f, best))
        scored.sort(key=lambda t: -t[0])
        kept = 0
        for _, f, (x, z, r) in scored:
            if kept >= PER_TICKER or abs(z) < MIN_Z:
                break
            events.append({
                "name": f"{sym} earnings release ({f['filingDate']})", "category": "earnings",
                "date": f["filingDate"], "instrument": sym, "cluster": f"earnings-{sym}-{f['filingDate']}",
                "selection": "price-screened",
                "official": [{"source": "SEC EDGAR submissions record, Form 8-K item 2.02",
                              "accession": f["accession"], "filingDate": f["filingDate"], "url": f["url"]}],
                "market": {"instrument": sym, "checked": True, "peakDate": x.isoformat(),
                           "z": round(z, 2), "returnPct": round(r * 100, 2), "moved": True},
                "evidenceGroups": ["official-document"], "tier": "B", "verified": True,
                "wikipedia": None, "wikidata": {"checked": False, "reason": "not applicable"},
            })
            kept += 1
        print(f"{sym}: {len(scored)} earnings releases found, kept {kept}", flush=True)
        time.sleep(0.2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "perTicker": PER_TICKER, "minAbsZ": MIN_Z, "events": events}, indent=1),
                   encoding="utf-8")
    print(len(events), "earnings events")


if __name__ == "__main__":
    main()
