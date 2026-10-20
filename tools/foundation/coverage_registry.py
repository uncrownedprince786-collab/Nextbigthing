"""Why this asset has no direction yet — per asset, per horizon, precomputed.

The problem
-----------
The asset page had one sentence for every asset without a recorded prediction: "Nothing recorded
yet." That is a blank tile. It is true and it is useless, because it does not distinguish between
an asset with 60 sessions of history that *cannot* be read at a 20-session horizon, an asset whose
last bar is three weeks old, an asset the recorder has simply not reached yet, and an asset whose
market has no validated lane at all. Four different situations, one shrug.

This writes the answer ahead of time. For every asset and every horizon the site offers, it
records whether the data is there, and when it is not, which specific thing is missing. The web
layer then reads a file instead of asking the database four questions per page view -- the gate is
a lookup in a precomputed table, not a query.

What eligibility means
----------------------
A prediction at horizon `h` needs two different things, and they are kept apart because they fail
apart:

* **Enough history to compute the features.** The longest lookback in the feature set is `sma50`,
  so a reading needs at least `FEATURE_WINDOW` stored sessions before the decision date. Fewer than
  that and no feature vector exists -- this is a hard floor, not a quality preference.
* **History recent enough to be a reading about now.** A decision taken from a bar three weeks old
  is a decision about three weeks ago. `STALE_AFTER_SESSIONS` is counted against the asset's own
  market calendar -- the sessions on which a quorum of that market's assets have a bar -- because
  a weekday rule calls every holiday a gap and crypto trades on Sunday.

The horizon itself does not change the history floor: `h` sessions of *future* are needed to grade
a prediction, not to make one. So a short horizon and a long one are equally servable from the
same history, and the registry says so rather than implying a depth requirement that does not
exist.

What this does not do
---------------------
Write to the database, fetch anything, or decide whether a direction is shown. Eligibility is
about the data; whether a lane is validated is a separate question answered by
`signal_validation.json`, and the asset page needs both. Keeping them in separate files is the
same split `marketCapability` makes against `signalValidation`: able to be read is not the same as
proven worth reading.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

OUT = ROOT / "data" / "foundation" / "dataset" / "coverage_registry.json"

#: Sessions of history a feature vector needs. `sma50` is the longest lookback in the price
#: feature set, so this is its window and not a round number chosen for comfort.
FEATURE_WINDOW = 50

#: Sessions after which the newest stored bar is too old to call a reading current. Three sessions
#: tolerates a provider being a day or two behind without calling a live asset stale.
STALE_AFTER_SESSIONS = 3

#: Share of a market's assets that must have a bar for a date to count as one of its sessions.
#: Below this the calendar itself is uncertain, which `coverage_gaps.py` calls quorum-thin.
QUORUM = 0.5

#: The horizons the site offers, in sessions. Kept in step with `lib/marketMarkets.ts`.
HORIZONS = (1, 5, 20, 60)

#: The status words, narrowest first. Exactly one applies to an asset at a horizon, and each names
#: a different missing thing -- which is the entire point of the file.
#:   ready            -- the data supports a reading now
#:   thin-history     -- fewer than FEATURE_WINDOW stored sessions; no feature vector exists
#:   stale            -- history exists but the newest bar is too old to be about now
#:   no-history       -- nothing stored at all
#:   feature-gap      -- the bars are there and the recorder still refuses the row, because a
#:                       feature the model needs is not observed for this asset. Bars are not the
#:                       only input: 12 US assets have 1,960 sessions each and are refused anyway
#:                       (COPX, 9 of 44 features imputed). Without this status the registry calls
#:                       them ready and a page built on it promises a reading that never arrives.
STATUSES = ("ready", "thin-history", "stale", "no-history", "feature-gap")


def market_of(asset_type: str | None, source: str | None) -> str:
    """The research vocabulary, via the recorder's own mapping so the two cannot diverge.

    `shadow_markets.market_of` is deliberately the one used here rather than
    `train_v4_markets.market_of_row`: the recorder is what decides which model writes a row for an
    asset, so a registry that classified assets differently would explain the wrong gap. `Asset`
    has no market column -- PSX is read off `source`.
    """
    sys.path.insert(0, str(ROOT / "tools" / "research"))
    import shadow_markets as mk
    return mk.market_of(asset_type, source)


def recorder_verdicts(report: Path) -> dict[str, dict]:
    """Per-symbol quality from a `shadow_predict.py` run, read rather than recomputed.

    The feature gate lives in the recorder -- which features are critical is read from the
    training manifest's own null shares, not hard-coded -- and reimplementing it here would give
    the registry a second opinion that could drift from the one that actually decides. So this
    reads the recorder's report. A dry run (no `--write`) produces it without touching the
    database.
    """
    doc = json.loads(report.read_text(encoding="utf-8"))
    out = {}
    for r in doc.get("records", []):
        out[r["symbol"]] = {
            "quality": r.get("quality"),
            "imputedCount": r.get("imputedCount"),
            "missingCritical": r.get("missingCritical"),
        }
    return out


def build(cur, verdicts: dict[str, dict] | None = None) -> dict:
    # One pass for the per-asset facts. Counting and taking the extremes in SQL rather than
    # streaming half a million bars into Python: the registry needs three numbers per asset.
    cur.execute(
        'SELECT a.symbol, a.source, a."assetType"::text AS asset_type, '
        '       count(p.date) AS bars, '
        '       max(p.date)::text AS newest, min(p.date)::text AS oldest '
        'FROM "Asset" a LEFT JOIN "PriceSnapshot" p ON p."assetId" = a.id '
        'GROUP BY a.symbol, a.source, a."assetType" '
        'ORDER BY a.symbol')
    assets = cur.fetchall()

    # The trading calendar, taken from the data per market rather than assumed from weekdays. A
    # single query returns, for each market and date, how many of that market's assets have a bar;
    # the quorum filter then decides which dates are sessions.
    cur.execute(
        'SELECT a.source, a."assetType"::text AS asset_type, p.date::text AS d, '
        '       count(*) AS n '
        'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
        'GROUP BY a.source, a."assetType", p.date '
        'ORDER BY p.date')
    per_day = cur.fetchall()

    totals: dict[str, int] = defaultdict(int)
    for r in assets:
        totals[market_of(r["asset_type"], r["source"])] += 1

    counted: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in per_day:
        counted[market_of(r["asset_type"], r["source"])][r["d"]] += int(r["n"])

    calendars: dict[str, list[str]] = {}
    for mkt, days in counted.items():
        need = max(1, int(QUORUM * totals.get(mkt, 1)))
        calendars[mkt] = sorted(d for d, n in days.items() if n >= need)

    out: dict[str, dict] = {}
    by_status: dict[str, int] = defaultdict(int)
    for r in assets:
        mkt = market_of(r["asset_type"], r["source"])
        cal = calendars.get(mkt, [])
        bars = int(r["bars"] or 0)
        newest = r["newest"]

        if bars == 0 or newest is None:
            status, behind = "no-history", None
        else:
            # Sessions of this market's calendar after the asset's newest bar. Counted against the
            # market, so an asset that stopped trading is stale and a market that is closed is not.
            behind = sum(1 for d in cal if d > newest)
            if bars < FEATURE_WINDOW:
                status = "thin-history"
            elif behind > STALE_AFTER_SESSIONS:
                status = "stale"
            else:
                status = "ready"

        # The recorder's own verdict overrides a `ready` read from bar counts alone. It is the
        # thing that actually decides whether a row gets written, so where the two disagree the
        # recorder is right and the registry was measuring the wrong input.
        v = (verdicts or {}).get(r["symbol"])
        if status == "ready" and v and v.get("quality") == "refused":
            status = "feature-gap"

        by_status[status] += 1
        entry = {
            "market": mkt,
            "bars": bars,
            "oldest": r["oldest"],
            "newest": newest,
            "sessionsBehind": behind,
            "status": status,
            # Stated per horizon even though the history floor does not vary with it, because the
            # site asks per horizon and a reader should not have to know that it does not vary.
            # When a horizon ever gains its own requirement this is where it goes.
            "horizons": {str(h): status for h in HORIZONS},
        }
        if status == "feature-gap":
            missing = v.get("missingCritical") or []
            entry["imputedCount"] = v.get("imputedCount")
            entry["why"] = (
                f"the {bars} stored sessions are enough, but the recorder refuses this asset: "
                + ("; ".join(missing) if missing
                   else f"{v.get('imputedCount')} of the model's features are not observed"))
        elif status == "thin-history":
            entry["why"] = (f"{bars} stored sessions; a feature vector needs {FEATURE_WINDOW} "
                            f"because the longest lookback is sma50")
        elif status == "stale":
            entry["why"] = (f"the newest stored bar is {newest}, {behind} {mkt} sessions ago; a "
                            f"reading from it would be about then, not now")
        elif status == "no-history":
            entry["why"] = "no stored bars for this asset"
        out[r["symbol"]] = entry

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "producedBy": "tools/foundation/coverage_registry.py",
        "featureWindowSessions": FEATURE_WINDOW,
        "staleAfterSessions": STALE_AFTER_SESSIONS,
        "quorum": QUORUM,
        "horizons": list(HORIZONS),
        "statuses": list(STATUSES),
        "whatThisIsNot": ("eligibility of the data, not permission to show a direction; a "
                          "validated lane is a separate question answered by "
                          "signal_validation.json"),
        "marketCalendarSessions": {m: len(c) for m, c in calendars.items()},
        "assetsByStatus": dict(by_status),
        "assets": out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--recorder-report", type=Path, default=None,
                    help="a shadow_predict.py report whose per-asset quality verdicts are merged "
                         "in; without it an asset refused on feature quality reads as ready")
    a = ap.parse_args()

    if "DATABASE_URL" not in os.environ:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
    from nbt import db

    verdicts = recorder_verdicts(a.recorder_report) if a.recorder_report else None
    with db() as conn, conn.cursor() as cur:
        doc = build(cur, verdicts)
    doc["recorderReport"] = str(a.recorder_report) if a.recorder_report else None
    a.out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")

    n = len(doc["assets"])
    print(f"coverage registry: {n} assets")
    for s in STATUSES:
        c = doc["assetsByStatus"].get(s, 0)
        if c:
            print(f"  {s:14s} {c:5d}  ({c / n:.1%})")
    print("  market calendars: "
          + ", ".join(f"{m} {k}" for m, k in sorted(doc["marketCalendarSessions"].items())))
    print(f"  wrote {a.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
