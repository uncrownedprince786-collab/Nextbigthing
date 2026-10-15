"""The Open Data Pakistan KSE-100 file: fetch it once, test it hard, and do not clear it for use.

    python tools/foundation/kse100_opendata.py fetch
    python tools/foundation/kse100_opendata.py verify

What this is for
----------------
`dps.psx.com.pk/timeseries/eod/KSE100` reaches back only to 2021-10-15 and the frozen history
starts 2018-01-01. Open Data Pakistan publishes a KSE-100 file that covers the earlier years and,
unlike the exchange endpoint, carries a real high and low.

Why it is quarantined rather than used
--------------------------------------
Its own resource page states **"License: No License Provided"**. A file being downloadable is not
a grant of reuse, so it is kept as an unverified-licence candidate: the raw file stays out of Git
and out of any production table, and only this manifest -- counts, ranges, checksums and the
licence finding -- is committed. Clearing it is the owner's decision, not a side effect of it
having answered HTTP 200.

The seam that matters
---------------------
The file ends 2021-02-23 and the exchange endpoint begins 2021-10-15, so **the two do not
overlap**: there is no common session on which to compare them, and the interval between them is
covered by neither. That gap is reported rather than papered over, and no value is interpolated
across it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / ".cache" / "acquire" / "opendata"
OUT = ROOT / "data" / "foundation" / "psx_index"
PSX_CSV = OUT / "KSE100.csv"

URL = ("https://opendata.com.pk/dataset/572570b3-2d4f-46f4-83e0-4d860bf71bff/resource/"
       "12071eb8-c3ee-4686-a3d3-f7b49fab502d/download/stock-exchange-kse-100pakistan.csv")
PAGE = ("https://opendata.com.pk/dataset/572570b3-2d4f-46f4-83e0-4d860bf71bff/resource/"
        "12071eb8-c3ee-4686-a3d3-f7b49fab502d")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
REQUIRED_FROM = "2018-01-01"


def num(s: str) -> float | None:
    s = (s or "").strip().strip('"').replace(",", "")
    if not s or s in ("-", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse(blob: bytes) -> tuple[list[list], dict]:
    text = blob.decode("utf-8-sig", "replace")
    r = csv.reader(io.StringIO(text))
    header = next(r)
    why = {"unparseableDate": 0, "missingField": 0, "nonPositive": 0, "ohlcInconsistent": 0,
           "duplicateDate": 0}
    seen: dict[str, list] = {}
    for row in r:
        if len(row) < 7:
            why["missingField"] += 1
            continue
        try:
            # "23-Feb-21": a two-digit year, and the file spans 2008-2021, so the century is
            # unambiguous here -- but it is pinned rather than left to the platform's default.
            d = datetime.strptime(row[0].strip(), "%d-%b-%y").date()
            if d.year > 2030:
                d = d.replace(year=d.year - 100)
        except ValueError:
            why["unparseableDate"] += 1
            continue
        o, h, l, c, v = (num(row[1]), num(row[2]), num(row[3]), num(row[4]), num(row[6]))
        if None in (o, h, l, c):
            why["missingField"] += 1
            continue
        if min(o, h, l, c) <= 0 or (v is not None and v < 0):
            why["nonPositive"] += 1
            continue
        if h < l or c > h + 1e-6 or c < l - 1e-6 or o > h + 1e-6 or o < l - 1e-6:
            why["ohlcInconsistent"] += 1
            continue
        key = d.isoformat()
        if key in seen:
            why["duplicateDate"] += 1
            continue
        seen[key] = [key, o, h, l, c, v]
    return [seen[k] for k in sorted(seen)], why


def cross_check(rows: list[list]) -> dict:
    """Direction agreement against the stored PSX constituents, which come from the exchange's
    own closing files -- a different source from this file."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT / "jobs"))
    from nbt import db, rows as q

    by_date = {r[0]: r for r in rows}
    dates = [r[0] for r in rows if r[0] >= "2019-01-01"]
    sample = dates[::max(1, len(dates) // 12)][:12]
    conn = db()
    cur = conn.cursor()
    agree = tot = 0
    detail = []
    try:
        for d in sample:
            i = [x[0] for x in rows].index(d)
            if i == 0:
                continue
            prev = rows[i - 1][0]
            ir = by_date[d][4] / by_date[prev][4] - 1
            got = q(cur, 'SELECT a.symbol, p.date::text d, p.close FROM "PriceSnapshot" p '
                         'JOIN "Asset" a ON a.id = p."assetId" '
                         'WHERE a.currency = %s AND p.date IN (%s, %s)', ("PKR", prev, d))
            cur_m = {r["symbol"]: float(r["close"]) for r in got if r["d"] == d}
            pre_m = {r["symbol"]: float(r["close"]) for r in got if r["d"] == prev}
            rs = [cur_m[s] / pre_m[s] - 1 for s in cur_m if s in pre_m and pre_m[s] > 0]
            if len(rs) < 30:
                continue
            med = statistics.median(rs)
            tot += 1
            same = (ir >= 0) == (med >= 0)
            agree += same
            detail.append({"date": d, "indexPct": round(ir * 100, 2),
                           "marketMedianPct": round(med * 100, 2), "sameSign": same,
                           "constituents": len(rs)})
    finally:
        cur.close()
        conn.close()
    return {"method": ("index daily direction against the median return of stored PSX "
                       "constituents, which come from the exchange's closing files"),
            "sampled": tot, "agreed": agree, "detail": detail}


def cmd_fetch() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=120) as r:
        blob, status = r.read(), r.status
        last_mod = r.headers.get("Last-Modified")
        ctype = r.headers.get("Content-Type")
    (RAW / "kse100_opendata.csv").write_bytes(blob)
    rows, why = parse(blob)

    psx_first = psx_last = None
    if PSX_CSV.exists():
        pr = list(csv.reader(io.StringIO(PSX_CSV.read_text("utf-8"))))[1:]
        psx_first, psx_last = pr[0][0], pr[-1][0]
    overlap = [r[0] for r in rows if psx_first and r[0] >= psx_first]

    report = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sourceUrl": URL, "resourcePage": PAGE,
        "httpStatus": status, "contentType": ctype, "lastModified": last_mod,
        "bytes": len(blob), "sha256Raw": hashlib.sha256(blob).hexdigest(),
        "fields": ["Date", "Open", "High", "Low", "Close", "Change", "Volume"],
        "hasRealHighLow": True,
        "observations": len(rows), "distinctDates": len({r[0] for r in rows}),
        "rejected": why,
        "first": rows[0][0] if rows else None, "last": rows[-1][0] if rows else None,
        "psxEndpointRange": [psx_first, psx_last],
        "overlappingSessionsWithPsxEndpoint": len(overlap),
        "gapBetweenSources": (
            f"{rows[-1][0]} .. {psx_first}" if rows and psx_first and rows[-1][0] < psx_first
            else None),
        "coversFrozenStart": bool(rows) and rows[0][0] <= REQUIRED_FROM,
        "licence": {
            "statedOnResourcePage": "No License Provided",
            "consequence": ("publicly downloadable, no grant of reuse. Held as an unverified "
                            "candidate: the raw file is not committed and nothing is written to "
                            "a production table. Clearing it is the owner's decision."),
        },
    }
    try:
        report["crossCheckAgainstStoredConstituents"] = cross_check(rows)
    except Exception as e:  # noqa: BLE001
        report["crossCheckAgainstStoredConstituents"] = {"error": f"{type(e).__name__}: {e}"}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "kse100_opendata_candidate.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report, indent=1, default=str))


def cmd_verify() -> None:
    man = json.loads((OUT / "kse100_opendata_candidate.json").read_text("utf-8"))
    p = RAW / "kse100_opendata.csv"
    blob = p.read_bytes()
    rows, _ = parse(blob)
    print(json.dumps({"rawPresent": p.exists(),
                      "sha256Matches": hashlib.sha256(blob).hexdigest() == man["sha256Raw"],
                      "reparsedObservations": len(rows),
                      "claimed": man["observations"],
                      "licence": man["licence"]["statedOnResourcePage"]}, indent=1))


COMMANDS = {"fetch": cmd_fetch, "verify": cmd_verify}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    COMMANDS[sys.argv[1]]()
