"""Is every coin in the training pool fit to carry a direction?

    python tools/research/crypto_readiness.py
    python tools/research/crypto_readiness.py --fail      # non-zero exit if any coin is unfit

This is the per-coin half of "is the brain ready". The other half -- how often it is right -- is
`crypto_ceiling.py`, and that one has a ceiling set by the market. This one does not. Every check
below is about whether the *inputs* for a coin are sound, and every one of them can and should
come back clean for all 140 coins. A wrong direction from a model that is 53% accurate is the
market being hard. A wrong direction because a coin's bars had a nine-hour hole patched over, or
because its ticker means two different assets on two exchanges, is this repository being careless,
and that is the error rate that can actually be driven to zero.

So the checks are deliberately ones with a right answer:

  * **bars exist, and enough of them.** Each horizon needs WARMUP bars to form features plus the
    forward window to label, and a fold split on top. A coin with three weeks of history cannot
    support a twenty-day call and must not be shown one.
  * **timestamps are strictly increasing and on the grid.** Out-of-order or duplicated bars mean
    the feature window is not the window it claims to be.
  * **gaps are counted, not patched.** A missing bar is fine and normal -- a venue goes down. What
    is not fine is a gap crossed silently, because the return across it is not a five-minute
    return. The matrix builder already refuses those rows; this counts them so a coin that is
    mostly hole is visible rather than merely quiet.
  * **prices are finite and positive, and the OHLC bracket holds** (low <= open, close <= high).
    A zero close propagates to an infinite return; a high below the close is a corrupt bar.
  * **the market is not dead.** A long run of identical closes is a delisted or untraded pair, and
    its "direction" is an artefact of nothing happening.
  * **it is not a dollar peg.** Measured elsewhere, flagged here, because a peg's direction is
    real, predictable and worth a fiftieth of the fee.

Nothing here is a model claim. It is the list of the ways a direction can be wrong for reasons
that have nothing to do with prediction, and it is meant to read empty.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from crypto_horizons import HORIZONS, ORDER  # noqa: E402
from intraday_features import WARMUP  # noqa: E402

CORPUS = ROOT / ".cache" / "foundation" / "intraday"
UNIVERSE = ROOT / "data" / "foundation" / "dataset" / "crypto_universe.json"
OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_readiness.json"

#: A coin needs the warm-up window, the forward window, and enough left over to be split into
#: train/validation/test and still have a testable holdout. Below this a horizon is refused.
MIN_ROWS_PER_HORIZON = 5_000

#: Identical closes for this many bars in a row means nothing is trading.
FLATLINE_BARS = 120


def read_bars(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ts, o, h, lo, c = [], [], [], [], []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            b = json.loads(line)
            ts.append(b["ts"]); o.append(b["o"]); h.append(b["h"])
            lo.append(b["l"]); c.append(b["c"])
    return (np.asarray(ts, dtype=np.int64), np.asarray(o, dtype=np.float64),
            np.asarray(h, dtype=np.float64), np.asarray(lo, dtype=np.float64),
            np.asarray(c, dtype=np.float64))


def longest_flat(c: np.ndarray) -> int:
    """Longest run of identical consecutive closes."""
    if len(c) < 2:
        return len(c)
    same = c[1:] == c[:-1]
    best = run = 0
    for s in same:
        run = run + 1 if s else 0
        best = max(best, run)
    return best + 1 if best else 1


def audit(symbol: str, interval: str, step_ms: int, pegged: set[str]) -> dict:
    path = CORPUS / f"{symbol}-{interval}.jsonl.gz"
    base = symbol.upper()[:-4] if symbol.upper().endswith("USDT") else symbol.upper()
    row: dict = {"symbol": symbol, "ticker": base, "interval": interval,
                 "pegged": base in pegged, "problems": []}
    if not path.exists():
        row["problems"].append("no bar file")
        return row

    ts, o, h, lo, c = read_bars(path)
    n = len(ts)
    row["bars"] = n
    if n == 0:
        row["problems"].append("bar file is empty")
        return row

    row["firstBar"] = datetime.fromtimestamp(ts[0] / 1000, timezone.utc).isoformat()
    row["lastBar"] = datetime.fromtimestamp(ts[-1] / 1000, timezone.utc).isoformat()
    row["spanDays"] = round((ts[-1] - ts[0]) / 86_400_000, 1)

    d = np.diff(ts)
    row["outOfOrder"] = int((d <= 0).sum())
    if row["outOfOrder"]:
        row["problems"].append(f"{row['outOfOrder']} non-increasing timestamps")

    off_grid = int((ts % step_ms != 0).sum())
    row["offGrid"] = off_grid
    if off_grid:
        row["problems"].append(f"{off_grid} timestamps not on the {interval} grid")

    # A gap is any step wider than one bar. Counted as bars missing, not as gap events, because
    # one nine-hour hole and a hundred one-bar blips are very different corpora.
    wide = d[d > step_ms]
    missing = int((wide // step_ms - 1).sum()) if len(wide) else 0
    expected = int((ts[-1] - ts[0]) // step_ms) + 1
    row["gapEvents"] = int(len(wide))
    row["barsMissing"] = missing
    row["completeness"] = round(n / expected, 5) if expected else 0.0
    row["largestGapBars"] = int(wide.max() // step_ms - 1) if len(wide) else 0

    bad = ~(np.isfinite(o) & np.isfinite(h) & np.isfinite(lo) & np.isfinite(c))
    nonpos = (o <= 0) | (h <= 0) | (lo <= 0) | (c <= 0)
    row["nonFinite"] = int(bad.sum())
    row["nonPositive"] = int(nonpos.sum())
    if bad.any():
        row["problems"].append(f"{int(bad.sum())} non-finite prices")
    if nonpos.any():
        row["problems"].append(f"{int(nonpos.sum())} non-positive prices")

    ok = ~bad & ~nonpos
    bracket = int((~((lo[ok] <= np.minimum(o[ok], c[ok])) &
                     (h[ok] >= np.maximum(o[ok], c[ok])))).sum())
    row["brokenOhlc"] = bracket
    if bracket:
        row["problems"].append(f"{bracket} bars where low/high do not bracket open/close")

    flat = longest_flat(c[ok]) if ok.any() else 0
    row["longestFlatRun"] = int(flat)
    if flat >= FLATLINE_BARS:
        row["problems"].append(f"{flat} identical closes in a row -- not trading")

    if row["pegged"]:
        row["problems"].append("dollar-pegged: direction is not tradable")

    # Which horizons this coin can actually support, on its own bar count.
    horizons = {}
    for k in ORDER:
        if HORIZONS[k]["interval"] != interval:
            continue
        need = WARMUP + HORIZONS[k]["bars"] + MIN_ROWS_PER_HORIZON
        horizons[k] = {"barsNeeded": int(need), "supported": bool(n >= need)}
    row["horizons"] = horizons
    unsupported = [k for k, v in horizons.items() if not v["supported"]]
    if unsupported:
        row["problems"].append(f"too short for {', '.join(unsupported)}")

    row["ready"] = not row["problems"]
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-coin data readiness for the training pool.")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--fail", action="store_true", help="exit non-zero if any coin is unfit")
    a = ap.parse_args()

    step_ms = {"5m": 300_000, "4h": 14_400_000}[a.interval]
    try:
        pegged = {x["ticker"].upper()
                  for x in json.loads(UNIVERSE.read_text(encoding="utf-8"))["assets"]
                  if x.get("pegged")}
    except (OSError, KeyError, ValueError):
        pegged = set()
        print("! universe unreadable; pegs will not be flagged", flush=True)

    symbols = sorted(p.name.split("-")[0] for p in CORPUS.glob(f"*-{a.interval}.jsonl.gz"))
    print(f"auditing {len(symbols)} coins at {a.interval}\n", flush=True)

    rows = []
    for i, s in enumerate(symbols, 1):
        r = audit(s, a.interval, step_ms, pegged)
        rows.append(r)
        if not r.get("ready"):
            print(f"  {i:>3}/{len(symbols)}  {s:<12} {'; '.join(r['problems'])}", flush=True)

    ready = [r for r in rows if r.get("ready")]
    unfit = [r for r in rows if not r.get("ready")]
    comp = [r["completeness"] for r in rows if "completeness" in r]
    span = [r["spanDays"] for r in rows if "spanDays" in r]

    print(f"\n=== {len(ready)} of {len(rows)} coins ready ===", flush=True)
    if comp:
        print(f"   bar completeness: min {min(comp):.4f}  median {np.median(comp):.4f}  "
              f"max {max(comp):.4f}", flush=True)
        print(f"   history span days: min {min(span):.0f}  median {np.median(span):.0f}  "
              f"max {max(span):.0f}", flush=True)
    for r in unfit:
        print(f"   UNFIT {r['symbol']:<12} {'; '.join(r['problems'])}", flush=True)

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_readiness.py",
        "what": ("per-coin data integrity for the training pool: the ways a direction can be "
                 "wrong for reasons that are not prediction"),
        "interval": a.interval,
        "minRowsPerHorizon": MIN_ROWS_PER_HORIZON,
        "flatlineBars": FLATLINE_BARS,
        "counts": {"audited": len(rows), "ready": len(ready), "unfit": len(unfit)},
        "coins": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}", flush=True)

    return 1 if (a.fail and unfit) else 0


if __name__ == "__main__":
    raise SystemExit(main())
