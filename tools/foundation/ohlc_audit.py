"""Every stored bar whose range cannot hold its own close, classified by what caused it.

    python tools/foundation/ohlc_audit.py [--out DIR]

`jobs/ohlc.py` stops these at the door from now on. This is the other half: what is already
stored, why each row is the way it is, and which rows a consumer should not read a range from.

**Nothing is written to the database and no price is altered.** The rows stay exactly as the
sources published them -- that is the raw history, and rule 130's principle is that a row is
still correct about everything it does not contradict. What this produces is a ledger of the
range exceptions, so the quarantine is a fact a reader can look up rather than a silent edit.

The classes, and why they are not one class:

  float-noise        The close is outside the range by less than 1e-9 of the bound it passed.
                     Yahoo's equity bars are the whole of this group and every one of them sits
                     at about 1.7e-15 -- IEEE754, not a measurement. The range is fine.
  collapsed-range    high == low and the close is neither. The exchange's thin-session artefact;
                     1,912 of the PSX file's 2,659 contradictions. The close stands, the range
                     describes nothing.
  incoherent-range   high != low and the close still falls outside. Yahoo's currency pairs are
                     most of this, at a median of 3.6 basis points, because the FX close is a
                     different snapshot from the range around it.
  inverted-range     high < low. None found in the stored history; kept because a class that is
                     empty today is the one worth noticing when it stops being empty.

`expected` separates a known property of a feed from something new. An expected exception is
still quarantined; it is simply not a surprise, and only the unexpected ones are worth a person's
attention.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "jobs"))

from ohlc import (  # noqa: E402
    FLOAT, FLOAT_NOISE, NO_RANGE, OK, UNTRUSTWORTHY, breach, classify, is_expected,
)

# Individual rows are listed up to this many per (source, class); beyond it the ledger keeps the
# count and the worst examples. A file nobody can open is not evidence.
SAMPLE_PER_GROUP = 50


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from nbt import db, rows

    out_dir = Path(arg("--out", ROOT / "data" / "foundation" / "price_verification"))
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = db()
    conn.rollback()
    conn.read_only = True
    cur = conn.cursor()
    try:
        got = rows(cur,
                   'SELECT a.symbol, a."assetType"::text AS kind, p.date::text AS d, '
                   'p.open, p.high, p.low, p.close, p.source '
                   'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                   'WHERE p.high IS NOT NULL AND p.low IS NOT NULL '
                   'AND (p.close > p.high OR p.close < p.low OR p.high < p.low) '
                   'ORDER BY a.symbol, p.date')
        total = rows(cur, 'SELECT count(*) AS n FROM "PriceSnapshot"')[0]["n"]
    finally:
        cur.close()
        conn.close()

    groups: dict[tuple, list[dict]] = defaultdict(list)
    counts: Counter = Counter()
    by_year: Counter = Counter()
    for r in got:
        verdict = classify(r["high"], r["low"], r["close"])
        if verdict in (OK, NO_RANGE):
            # The query found a contradiction this comparison cannot: the breach is smaller than
            # one unit in the last place of the value as it arrives here, so Postgres sees the
            # two doubles differ and a parsed Python float sees them equal. 47 rows, every one a
            # Yahoo equity bar, which with the 2 above makes all 49 of that feed's contradictions
            # float representation. Counted, not dropped -- the totals have to reconcile.
            verdict = FLOAT
            counts["sub-ulp"] += 1
        b = breach(r["high"], r["low"], r["close"])
        expected = is_expected(verdict, r["source"], r["kind"])
        counts[verdict] += 1
        counts[f"{verdict}:{'expected' if expected else 'unexpected'}"] += 1
        if verdict in UNTRUSTWORTHY:
            counts["quarantined"] += 1
            by_year[r["d"][:4]] += 1
        groups[(r["source"], r["kind"], verdict, expected)].append({
            "symbol": r["symbol"], "date": r["d"],
            "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"],
            "breach": round(b, 12),
        })

    ledger = []
    for (source, kind, verdict, expected), items in sorted(
            groups.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda x: -x["breach"])
        ledger.append({
            "source": source, "assetType": kind, "class": verdict,
            "expected": expected,
            "quarantined": verdict in UNTRUSTWORTHY,
            "rows": len(items),
            "medianBreach": round(items[len(items) // 2]["breach"], 12),
            "worstBreach": round(items[0]["breach"], 12),
            "reason": REASONS.get((kind, verdict), REASONS.get(verdict, "")),
            "sample": items[:SAMPLE_PER_GROUP],
            "sampleIsComplete": len(items) <= SAMPLE_PER_GROUP,
        })

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "ohlc-quarantine-v1",
        "rule": ("a bar whose close falls outside its own published range has an untrustworthy "
                 "range, not an untrustworthy close; the close is never altered"),
        "floatNoiseFloor": FLOAT_NOISE,
        "scanned": total,
        "contradictions": sum(v for k, v in counts.items()
                              if ":" not in k and k not in ("quarantined", "sub-ulp")),
        "reconciliation": {
            "databaseComparisonFinds": len(got),
            "quarantined": counts["quarantined"],
            "floatRepresentation": counts[FLOAT],
            "ofWhichBelowOneUlp": counts["sub-ulp"],
            "note": ("quarantined + floatRepresentation must equal databaseComparisonFinds; "
                     "a sub-ULP breach is visible to Postgres and not to a parsed double"),
        },
        "quarantinedRanges": counts["quarantined"],
        "quarantinedShare": round(counts["quarantined"] / total, 8) if total else None,
        "byClass": {k: v for k, v in sorted(counts.items())
                    if ":" not in k and k not in ("quarantined", "sub-ulp")},
        "byClassAndExpectation": {k: v for k, v in sorted(counts.items()) if ":" in k},
        "quarantinedByYear": dict(sorted(by_year.items())),
        "ledger": ledger,
    }
    path = out_dir / "ohlc_quarantine.json"
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"scanned {total:,} bars")
    for k, v in sorted(counts.items()):
        if ":" not in k and k not in ("quarantined", "sub-ulp"):
            print(f"  {k:<20} {v:>6,}")
    print(f"  {'quarantined ranges':<20} {counts['quarantined']:>6,} "
          f"({counts['quarantined'] / total:.4%})")
    unexpected = sum(v for k, v in counts.items() if k.endswith(":unexpected"))
    print(f"  {'unexpected':<20} {unexpected:>6,}")
    print(f"  reconcile: {counts['quarantined']:,} quarantined + {counts[FLOAT]:,} float "
          f"= {counts['quarantined'] + counts[FLOAT]:,} against {len(got):,} the database finds")
    print(f"wrote {path}")


REASONS = {
    FLOAT: "float representation, not a measurement; the range is usable",
    "collapsed-range": ("the source published one value as both high and low and a close that is "
                        "neither, so the range describes no session"),
    "incoherent-range": "the close falls outside a range that is not degenerate",
    ("forex", "incoherent-range"): ("Yahoo's FX close is a different snapshot from the range "
                                    "around it; a property of the feed, on about 8% of sessions"),
    ("forex", "collapsed-range"): "an FX session Yahoo quoted at one price with a differing close",
    ("stock", "collapsed-range"): ("the exchange's thin-session artefact: one price printed into "
                                   "both range columns"),
    ("stock", "incoherent-range"): (
        "the exchange's published close sits outside a real traded range: 358 above the high and "
        "389 below the low, 65% of them by 2% or less, and half on sessions whose whole range is "
        "within 2% of its own low. Consistent with a closing price computed on a different basis "
        "from the intraday range, but the mechanism is not established from the stored data and "
        "the exchange's own specification would be needed to settle it. Quarantined on that "
        "uncertainty, not on a diagnosis"),
    "inverted-range": "high below low; the source contradicted itself outright",
}

if __name__ == "__main__":
    main()
