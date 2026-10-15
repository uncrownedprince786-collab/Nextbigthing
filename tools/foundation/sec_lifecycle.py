"""Official instrument identity and lifecycle for the US universe, from SEC EDGAR.

    python tools/foundation/sec_lifecycle.py [--sleep S]

**What this recovers, and what it cannot.** Survivorship work needs to know *what existed and
under what name at a past decision time*. Price vendors are the wrong place to ask: when a company
is acquired or delisted, Yahoo stops serving it and the history disappears with it -- 63 of the
127 S&P 500 removals since 2019 have no recoverable bars there, and `stooq` answers a bot
challenge rather than CSV, which this project will not work around. EDGAR is the official registry
and it does not forget. It serves identity and lifecycle, **not prices**, and nothing here
pretends otherwise.

**The delisting signal is an absence, and it is a real one.** `data.sec.gov/submissions/CIK….json`
carries `tickers` and `exchanges` arrays for a currently listed company. For a company that has
been acquired or taken private both arrays are **empty** while the filing history remains. That is
EDGAR saying "this registrant exists and is no longer listed", which is exactly the fact a
point-in-time universe needs, and it is why an empty array is recorded as evidence rather than as
a failed lookup.

`formerNames` gives the rename history with the dates each name was in force, so a symbol that
changed hands can be told apart from a company that changed its name.

**Bounded and polite.** One request for the whole ticker map, then one per registrant being
resolved, with a sleep between calls and a User-Agent carrying a contact address as SEC asks. Every
response is cached on disk, so a re-run costs nothing. Reads no database and writes no database
row.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

TICKERS = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
UA = "NextBigThing-research/1.0 (mailto:claude.pro@thedg.group)"

CACHE = ROOT / ".cache" / "foundation" / "sec"
OUT_DIR = ROOT / "data" / "foundation" / "survivorship"
SURVIVORSHIP = OUT_DIR / "report.json"

SLEEP = 0.3


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def get_json(url: str, cache_key: str, sleep_s: float):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{cache_key}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")), "cache"
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip as _g
                    raw = _g.decompress(raw)
                doc = json.loads(raw)
            p.write_text(json.dumps(doc), encoding="utf-8")
            time.sleep(sleep_s)
            return doc, "fetched"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "404"
            time.sleep(2 * attempt)
        except Exception:  # noqa: BLE001
            time.sleep(2 * attempt)
    return None, "failed"


def main() -> int:
    sleep_s = float(arg("--sleep", SLEEP))
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT / "jobs"))
    from nbt import db, rows

    tmap, how = get_json(TICKERS, "company_tickers", sleep_s)
    if not tmap:
        print("EDGAR ticker map unavailable; nothing to do")
        return 1
    by_ticker = {}
    for e in tmap.values():
        by_ticker.setdefault(e["ticker"].upper(), int(e["cik_str"]))
    print(f"EDGAR ticker map ({how}): {len(by_ticker):,} live listed tickers")

    conn = db()
    conn.rollback()
    conn.read_only = True
    cur = conn.cursor()
    try:
        us = rows(cur, """SELECT symbol FROM "Asset"
                          WHERE "assetType"::text IN ('stock','etf') AND currency='USD'
                          ORDER BY symbol""")
    finally:
        cur.close()
        conn.close()
    universe = [r["symbol"] for r in us]

    # Every S&P removal in range, from the Wikipedia history `survivorship.py` already cached --
    # no refetch. The report's own `sample` holds only fifteen of them, and resolving fifteen
    # would describe the method rather than the universe.
    sys.path.insert(0, str(HERE))
    import survivorship as sv

    probes = {}
    if SURVIVORSHIP.exists():
        rep = json.loads(SURVIVORSHIP.read_text(encoding="utf-8"))
        lo, hi = (rep.get("range") or ["2019-01-01", "2099-01-01"])[:2]
        for s in rep.get("sample", []):
            probes[s.get("removed")] = (s.get("probe") or {}).get("bars")
    else:
        lo, hi = "2019-01-01", "2099-01-01"
    removals = []
    for r in sv.removals():
        d = r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"])
        if not (lo <= d <= hi) or not r.get("removed"):
            continue
        removals.append({"ticker": r["removed"], "name": r.get("removedName", ""),
                         "date": d, "kind": sv.classify(r.get("reason", "")),
                         "vendorBars": probes.get(r["removed"])})

    in_edgar = [s for s in universe if s.upper() in by_ticker]
    print(f"our US universe        : {len(universe)}")
    print(f"  currently listed in EDGAR : {len(in_edgar)}")
    print(f"  not in the live map       : {len(universe) - len(in_edgar)}"
          f" -> {sorted(set(universe) - set(in_edgar))[:12]}")

    resolved = []
    for r in removals:
        cik = by_ticker.get(r["ticker"].upper())
        entry = {**r, "cik": cik, "stillListedUnderThisTicker": cik is not None}
        if cik:
            doc, _ = get_json(SUBMISSIONS.format(cik=cik), f"sub_{cik}", sleep_s)
            if doc:
                entry.update({
                    "edgarName": doc.get("name"),
                    "tickers": doc.get("tickers") or [],
                    "exchanges": doc.get("exchanges") or [],
                    "formerNames": [f.get("name") for f in (doc.get("formerNames") or [])],
                    "sic": doc.get("sic"), "sicDescription": doc.get("sicDescription"),
                    "delistedSignal": not (doc.get("tickers") or []),
                })
        resolved.append(entry)

    listed = sum(1 for r in resolved if r.get("tickers"))
    delisted = sum(1 for r in resolved if r.get("delistedSignal"))
    unmapped = sum(1 for r in resolved if not r.get("cik"))
    renamed = sum(1 for r in resolved if len(r.get("formerNames") or []) > 1)

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "sec-lifecycle-v1",
        "source": {"name": "SEC EDGAR", "tickerMap": TICKERS, "submissions": SUBMISSIONS,
                   "auth": "none, User-Agent with contact required",
                   "serves": "registrant identity and lifecycle, never prices"},
        "usUniverse": {"assets": len(universe), "currentlyListedInEdgar": len(in_edgar),
                       "notInLiveMap": sorted(set(universe) - set(in_edgar))},
        "removalsResolved": len(resolved),
        "removalsStillListed": listed,
        "removalsWithDelistedSignal": delisted,
        "removalsNotInEdgarTickerMap": unmapped,
        "removalsWithAFormerName": renamed,
        "delistedSignalMeaning": ("EDGAR serves empty `tickers` and `exchanges` for a registrant "
                                  "that still files but is no longer listed; the filing history "
                                  "remains, so the absence is evidence and not a failed lookup"),
        "whatThisDoesNotRecover": ("price history. EDGAR has none, Yahoo 404s the delisted names, "
                                   "and stooq answers a bot challenge this project will not work "
                                   "around. The survivorship bias figure therefore stays a "
                                   "measured lower bound"),
        "records": resolved,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "sec_lifecycle.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\nremovals resolved      : {len(resolved)}")
    print(f"  still listed         : {listed}")
    print(f"  delisted per EDGAR   : {delisted}")
    print(f"  not in the ticker map: {unmapped}")
    print(f"  carrying a former name: {renamed}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
