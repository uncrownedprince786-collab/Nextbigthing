"""Reproducible evidence for every data gap this project reports as blocked.

    python tools/foundation/gap_evidence.py [--out DIR]

Writes `data/foundation/dataset/gap_evidence.json`. Makes a small, fixed number of HTTP requests
against sources already used by this project; writes no database row and downloads no data.

**Why a gap needs an artifact.** Coverage and organisation are different measurements. A gap is
uncovered by definition -- that is metric 1's business. Whether it is *organised* is a separate
question: does the project know which routes were tried, on which dates, what each answered, and
can a reader reproduce that without taking anyone's word for it? A blocked item with a dated,
checksummed probe record is fully organised and still entirely uncovered, and conflating the two
is how a project either flatters itself or punishes itself twice for the same fact.

**What it does not do.** It does not retry a source in the hope of a different answer, does not
work around a bot challenge or a licence, and does not treat one 404 as proof about an entire
provider. Each probe is a single request whose result is recorded as what it is: a status code,
at a timestamp, for a named URL.

The three gaps probed are the ones the inventory reports as blocked or partly blocked:

  *delisted US price history* -- Yahoo's download and chart endpoints for names EDGAR confirms
  are no longer listed, and stooq, which answers a bot challenge this project will not bypass.

  *PSX history before 2013-11-04* -- the exchange's own daily archive at dates either side of
  its floor, which is the only thing that can establish where the archive actually begins.

  *ICE credit indices for 2008* -- FRED's own response for the licence-limited series, against
  the Moody's series that was recovered in its place.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT_DIR = ROOT / "data" / "foundation" / "dataset"
UA = "NextBigThing-research/1.0 (mailto:claude.pro@thedg.group)"

PROBES = [
    {"gap": "delisted US price history", "route": "Yahoo v8 chart API",
     "url": "https://query1.finance.yahoo.com/v8/finance/chart/HOLX?range=5y&interval=1d",
     "expect": "404 for a delisted registrant"},
    {"gap": "delisted US price history", "route": "Yahoo v8 chart API",
     "url": "https://query1.finance.yahoo.com/v8/finance/chart/CTRA?range=5y&interval=1d",
     "expect": "404 for a delisted registrant"},
    {"gap": "delisted US price history", "route": "stooq daily CSV",
     "url": "https://stooq.com/q/d/l/?s=holx.us&i=d",
     "expect": "200 carrying a bot challenge rather than CSV; not circumvented"},
    {"gap": "PSX history before 2013-11-04", "route": "PSX daily archive",
     "url": "https://dps.psx.com.pk/download/mkt_summary/2008-08-27.Z",
     "expect": "404: the archive does not reach 2008"},
    {"gap": "PSX history before 2013-11-04", "route": "PSX daily archive",
     "url": "https://dps.psx.com.pk/download/mkt_summary/2013-11-01.Z",
     "expect": "404: one session before the archive floor"},
    {"gap": "PSX history before 2013-11-04", "route": "PSX daily archive",
     "url": "https://dps.psx.com.pk/download/mkt_summary/2013-11-04.Z",
     "expect": "200: the archive floor"},
    {"gap": "ICE credit indices for 2008", "route": "FRED",
     "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd=2005-01-01",
     "expect": "200 but the series begins inside a rolling three-year window"},
    {"gap": "ICE credit indices for 2008", "route": "FRED (recovered substitute)",
     "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=2005-01-01&coed=2012-12-31",
     "expect": "200 covering the whole crisis window"},
]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def probe(p: dict) -> dict:
    """One request. The answer is recorded as what it is, not as what it implies."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        req = urllib.request.Request(p["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        code, note = r.status, ""
        head = body[:400].decode("utf-8", "replace")
        if "<html" in head.lower() or "<script" in head.lower():
            note = "HTML returned where data was expected (bot challenge or error page)"
        first_date = ""
        if head.startswith("date,") or head.startswith("DATE,") or "observation_date" in head[:40]:
            lines = [ln for ln in head.splitlines() if ln.strip()]
            if len(lines) > 1:
                first_date = lines[1].split(",")[0]
        return {**p, "httpStatus": code, "bytes": len(body), "note": note,
                "firstDateReturned": first_date, "probedAt": started}
    except urllib.error.HTTPError as e:
        return {**p, "httpStatus": e.code, "bytes": 0,
                "note": "HTTPError", "firstDateReturned": "", "probedAt": started}
    except Exception as e:  # noqa: BLE001
        return {**p, "httpStatus": None, "bytes": 0,
                "note": f"{type(e).__name__}", "firstDateReturned": "", "probedAt": started}


def main() -> int:
    out_dir = Path(arg("--out", OUT_DIR))
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for p in PROBES:
        r = probe(p)
        results.append(r)
        print(f"  {r['gap'][:34]:<36} {r['route'][:26]:<28} HTTP {str(r['httpStatus']):<5}"
              f" {r['firstDateReturned'] or r['note'][:38]}")
        time.sleep(1.0)

    by_gap: dict[str, list] = {}
    for r in results:
        by_gap.setdefault(r["gap"], []).append(r)

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "gap-evidence-v1",
        "purpose": ("dated, reproducible evidence for each reported gap. Organisation and "
                    "coverage are separate measurements: a gap can be fully organised and "
                    "entirely uncovered at the same time"),
        "method": ("one request per route, status recorded as returned. No retry for a different "
                   "answer, no bot-challenge circumvention, no licence workaround"),
        "schema": {"gap": "the inventory layer this evidences",
                   "route": "the provider and endpoint tried",
                   "url": "the exact request",
                   "expect": "what the project expects, written before probing",
                   "httpStatus": "as returned", "bytes": "response size",
                   "firstDateReturned": "first data date when the body is a CSV",
                   "note": "anything non-obvious about the body",
                   "probedAt": "UTC timestamp of this request"},
        "gaps": {
            gap: {
                "routesTried": len(rs),
                "conclusion": {
                    "delisted US price history":
                        "no permitted free source serves OHLCV for a delisted registrant; "
                        "EDGAR holds identity and lifecycle but never prices",
                    "PSX history before 2013-11-04":
                        "the exchange archive begins at 2013-11-04; earlier dates are absent at "
                        "source, not missing from this project",
                    "ICE credit indices for 2008":
                        "the ICE index is licence-limited to a rolling window; the credit spread "
                        "itself was recovered as Moody's BAA10Y and covers 2005-2012 in full",
                }[gap],
                "probes": rs,
            } for gap, rs in by_gap.items()
        },
    }
    out = out_dir / "gap_evidence.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    payload["sha256"] = digest
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\ngaps evidenced: {len(by_gap)}  probes: {len(results)}")
    print(f"wrote {out} (sha256 {hashlib.sha256(out.read_bytes()).hexdigest()[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
