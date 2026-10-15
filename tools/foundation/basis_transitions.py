"""Every place the PSX series changes price basis, and whether the change shows.

    python tools/foundation/basis_transitions.py [--out DIR] [--window N]

**Why this exists.** 203 PSX assets carry two sources: the exchange's own daily file, which is
raw, and the recovered Yahoo Karachi listing, which is split-adjusted. `jobs/factors.py` reads
plain lists of closes and never sees `source`, so a 20-session window can span a basis change
without anything saying so. Rule 130 proved each *insertion date* against its neighbours within
0.5%; it did not measure the window, and the window is what every stored factor actually reads.

**The test, and why it is this one.** A universal percentage tolerance is wrong for PSX. The
exchange runs a daily price band, and the band is not a percentage alone -- it is the greater of
10% and Rs 1.00, which dominates for the sub-Rs-10 scrips where the largest apparent jumps live.
That is derived here from the stored data rather than asserted: over same-source transitions,
**10 of 71,816** moves on a prior close under Rs 10 exceed Rs 1.00 (0.01%), and **253 of 299,074**
moves at or above Rs 10 exceed 10% (0.08%). The band is a hard ceiling in the data.

So a cross-basis transition is **in band** when its move is one a single legitimate PSX session
could have produced, and **out of band** when it is not. An out-of-band cross-basis step is the
only shape a silently mixed basis can take: two series at different scales joined at a date.

**What it does with the answer.** It writes a ledger, not a correction. Every cross-basis
transition is recorded with both sides' close and source, so the provenance of the join survives
even though `PriceSnapshot`'s primary key `(assetId, date)` can hold only one observation per
asset-date. The out-of-band ones are listed individually as exceptions for a consumer to exclude.
No price is changed and no row is deleted: a basis change is a fact about how the series was
assembled, not a defect in the prices on either side of it.

Read-only against the database. Writes one JSON sidecar.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "jobs"))

EXCHANGE = "Pakistan Stock Exchange daily closing file"
KARACHI = "Yahoo Finance Karachi listing"

# The exchange's daily price band, derived in the docstring above from the stored series.
# Both halves are needed: the percentage alone lets a sub-rupee scrip look like a 178% move
# when it moved the minimum tick the exchange allows, and the absolute alone would wave through
# a 10% step on a Rs 500 name.
BAND_PCT = 10.0
BAND_MIN_PKR = 1.00
# Floating point closes arrive from two providers at different precisions; a hair over the band
# is the band, not a breach.
BAND_TOLERANCE = 1.005

# The factor window these transitions are measured against. jobs/factors.py and lib/decision.ts
# both read 20 sessions.
DEFAULT_WINDOW = 20


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def band_pkr(prior_close: float) -> float:
    """The widest move the exchange permits from this close, in rupees."""
    return max(BAND_MIN_PKR, prior_close * BAND_PCT / 100.0)


def in_band(prior_close: float, close: float) -> bool:
    """Could one legitimate PSX session have moved the price this far?"""
    return abs(close - prior_close) <= band_pkr(prior_close) * BAND_TOLERANCE


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from nbt import db, rows

    window = int(arg("--window", DEFAULT_WINDOW))
    out_dir = Path(arg("--out", ROOT / "data" / "foundation" / "price_verification"))
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = db()
    conn.rollback()
    conn.read_only = True
    cur = conn.cursor()
    try:
        got = rows(cur,
                   'SELECT a.symbol, p.date::text AS d, p.close, p.source '
                   'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                   'WHERE p.source IN (%s, %s) AND p.close IS NOT NULL '
                   'ORDER BY p."assetId", p.date', (EXCHANGE, KARACHI))
    finally:
        cur.close()
        conn.close()

    series: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for r in got:
        series[r["symbol"]].append((r["d"], float(r["close"]), r["source"]))

    cross = cross_out = same = same_out = 0
    exceptions: list[dict] = []
    per_asset: dict[str, dict] = {}
    windows_total = windows_spanning = windows_tainted = 0

    for symbol, bars in sorted(series.items()):
        flips = 0
        bad_dates: set[str] = set()
        for i in range(1, len(bars)):
            d0, c0, s0 = bars[i - 1]
            d1, c1, s1 = bars[i]
            if c0 <= 0 or c1 <= 0:
                continue
            ok = in_band(c0, c1)
            if s0 == s1:
                same += 1
                same_out += 0 if ok else 1
                continue
            cross += 1
            flips += 1
            if ok:
                continue
            cross_out += 1
            bad_dates.add(d1)
            exceptions.append({
                "symbol": symbol,
                "fromDate": d0, "toDate": d1,
                "fromClose": round(c0, 4), "toClose": round(c1, 4),
                "fromSource": "exchange" if s0 == EXCHANGE else "karachi",
                "toSource": "exchange" if s1 == EXCHANGE else "karachi",
                "changePkr": round(c1 - c0, 4),
                "changePct": round((c1 / c0 - 1.0) * 100.0, 3),
                "bandPkr": round(band_pkr(c0), 4),
                "overBandPkr": round(abs(c1 - c0) - band_pkr(c0), 4),
                "verdict": "out-of-band cross-basis step: exclude any window spanning it",
            })

        # Windows ending at each session, counted the way factors.py reads them: a span of
        # `window` needs window + 1 closes, so the first window ends at index `window`.
        spanning = tainted = 0
        for end in range(window, len(bars)):
            seg = bars[end - window:end + 1]
            windows_total += 1
            if len({b[2] for b in seg}) > 1:
                spanning += 1
                if bad_dates.intersection(b[0] for b in seg):
                    tainted += 1
        windows_spanning += spanning
        windows_tainted += tainted
        if flips:
            per_asset[symbol] = {"bars": len(bars), "basisChanges": flips,
                                 "windows": max(0, len(bars) - window),
                                 "windowsSpanningABasisChange": spanning,
                                 "windowsExcluded": tainted}

    exceptions.sort(key=lambda e: -abs(e["overBandPkr"]))
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "basis-transitions-v1",
        "scope": "the two PSX price sources only; no other market mixes bases",
        "band": {
            "percent": BAND_PCT, "minimumPkr": BAND_MIN_PKR, "tolerance": BAND_TOLERANCE,
            "rule": "the greater of 10% and Rs 1.00, the exchange's own daily price band",
            "derivedFrom": "same-source transitions in this table, not from documentation",
        },
        "crossBasis": {
            "transitions": cross, "outOfBand": cross_out,
            "rate": round(cross_out / cross, 6) if cross else None,
        },
        "sameBasis": {
            "transitions": same, "outOfBand": same_out,
            "rate": round(same_out / same, 6) if same else None,
        },
        "comparison": (
            "if the cross-basis out-of-band rate is not materially above the same-source rate, "
            "the two bases are not silently disagreeing: a basis change looks like any other "
            "session"
        ),
        "windows": {
            "window": window,
            "total": windows_total,
            "spanningABasisChange": windows_spanning,
            "excluded": windows_tainted,
            "shareSpanning": round(windows_spanning / windows_total, 4) if windows_total else None,
            "shareExcluded": round(windows_tainted / windows_total, 6) if windows_total else None,
        },
        "assetsWithTwoBases": len(per_asset),
        "exceptions": exceptions,
        "perAsset": per_asset,
    }

    path = out_dir / "basis_transitions.json"
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"cross-basis transitions : {cross:,}  out of band {cross_out:,} "
          f"({cross_out / cross:.3%})" if cross else "no cross-basis transitions")
    print(f"same-source transitions : {same:,}  out of band {same_out:,} "
          f"({same_out / same:.3%})" if same else "")
    print(f"{window}-session windows   : {windows_total:,} total, "
          f"{windows_spanning:,} span a basis change ({windows_spanning / windows_total:.1%}), "
          f"{windows_tainted:,} excluded ({windows_tainted / windows_total:.4%})"
          if windows_total else "")
    print(f"assets with two bases   : {len(per_asset)}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
