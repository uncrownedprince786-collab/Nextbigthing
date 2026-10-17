"""Is the +/-2% 20-session label the thing holding the brain back, or is it the features?

    python tools/research/label_adequacy.py [--full DIR] [--out FILE]

Why this question is worth a bounded investigation
---------------------------------------------------
Three candidates have now failed on these features, and all three failed the same way -- by
collapsing onto whichever class was the majority of *their* training population. `brain-v1`
predicted UP on 74.7%, `brain-v2-context` on 92.2%, `brain-v3-crypto` predicted DOWN on 97.0%.
`RESUME.md` records a measured hint that the target may be the problem: the forex slice is about
68% FLAT under a fixed +/-2% band, which is a label that almost never fires on a market that
rarely moves 2% in twenty sessions.

That is a real observation and it is not yet a conclusion. There are two competing explanations
and they call for opposite responses:

* **The label is unsuitable.** A fixed band applied to markets with different volatilities makes
  the task trivially imbalanced in some and noisy in others. Fix the label and the features may
  have been fine all along.
* **The features carry no directional signal at this horizon.** Then every relabelling is
  cosmetic: the numbers move because the base rates move, and nothing has been learned.

**Collapse onto the majority class is the signature of the second, not the first.** A model
fighting a badly-calibrated target usually still discriminates somewhere; a model with no usable
signal takes the base rate, which is exactly what all three did. So this file sets out to find
evidence that could distinguish them rather than to confirm the comfortable answer.

What is measured here
---------------------
Read-only, from `full-history-v2.jsonl.gz` -- the outcomes artifact, not the 240 MB feature
dataset, because none of this needs a feature.

1. Label distribution by asset class and by year, with denominators.
2. The forward-return distribution behind it: |fwd20| quantiles per class, and what share of rows
   clear the 2% band at all.
3. Per-class difficulty: the band that *would* split each market into thirds, which says how far
   the fixed band is from balanced for each.
4. Effective independent windows -- rows / 20, because consecutive rows share 19 of their 20
   forward sessions.
5. **The economic check that decides it.** The 2% band was not arbitrary: `make_dataset.py`
   records it as "roughly a typical 20-session round-trip cost plus slippage", so a move inside
   it is not tradeable even when its sign is right. A volatility-normalised band would relabel
   sub-cost moves as UP or DOWN. This measures how much of each market's "signal" under a
   normalised band would be moves too small to trade.

A note on honesty about the data used
--------------------------------------
Every statistic here is computed over the **whole** history, including the 2026 window that three
experiments have already scored. That is legitimate for *describing a label* -- a class balance
is a property of the data, not a result obtained by fitting to it -- but it is **not** an
evaluation and nothing here may be reported as one. Where a per-asset volatility is used, it is a
full-sample figure and would need a point-in-time estimate before any feature could use it; that
is flagged in the output rather than quietly ignored.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_FULL = ROOT / ".cache" / "foundation" / "full"
OUT = ROOT / "data" / "foundation" / "dataset" / "label_adequacy.json"

BAND = 2.0          # the shipped threshold, percent
EMBARGO = 20


def quantile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


def stdev(xs: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def balanced_band(moves: list[float]) -> float | None:
    """The symmetric band that would put a third of this market in each class.

    Not a proposal -- a measurement of how far the fixed band sits from balanced here.
    """
    if len(moves) < 100:
        return None
    a = sorted(abs(m) for m in moves)
    return a[int(0.333 * (len(a) - 1))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--full", default=str(DEFAULT_FULL))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    f = next(iter(sorted(Path(a.full).glob("full-history-v*.jsonl.gz"))))
    print(f"reading {f.name}")

    by_cls: dict[str, list[float]] = defaultdict(list)
    labels: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_year: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_asset: dict[str, list[float]] = defaultdict(list)
    asset_cls: dict[str, str] = {}
    rows = immature = 0

    for line in gzip.open(f, "rt", encoding="utf-8"):
        r = json.loads(line)
        o = r.get("outcome") or {}
        cls = "PSX" if r.get("market") == "PK" else r.get("assetType") or "?"
        if not o.get("mature20"):
            immature += 1
            continue
        fwd = o.get("fwd20")
        lab = o.get("label20")
        if fwd is None or lab is None:
            continue
        rows += 1
        by_cls[cls].append(float(fwd))
        labels[cls][lab] += 1
        by_year[r["asOf"][:4]][lab] += 1
        per_asset[r["symbol"]].append(float(fwd))
        asset_cls[r["symbol"]] = cls

    out_cls = {}
    for cls, moves in sorted(by_cls.items()):
        n = len(moves)
        counts = dict(labels[cls])
        absm = [abs(m) for m in moves]
        bb = balanced_band(moves)
        over = sum(1 for m in absm if m >= BAND) / n
        out_cls[cls] = {
            "rows": n,
            "effectiveIndependentWindows": int(round(n / EMBARGO)),
            "labelCounts": counts,
            "labelShares": {k: round(v / n, 4) for k, v in counts.items()},
            "flatShare": round(counts.get("FLAT", 0) / n, 4),
            "shareClearingTheBand": round(over, 4),
            "absFwd20": {q: round(quantile(absm, p), 3)
                         for q, p in (("p25", .25), ("p50", .5), ("p75", .75), ("p90", .9))},
            "fwd20Sd": round(stdev(moves) or 0.0, 3),
            "bandThatWouldBalanceThisMarket": None if bb is None else round(bb, 3),
            "fixedBandVsBalanced": None if bb is None else round(BAND / bb, 2),
        }

    # The economic check: under a per-asset volatility band, how much of what becomes
    # directional is a move too small to pay for its own round trip?
    norm = {}
    for cls in sorted(by_cls):
        syms = [s for s, c in asset_cls.items() if c == cls]
        sub_cost = total = 0
        for s in syms:
            moves = per_asset[s]
            sd = stdev(moves)
            if not sd or len(moves) < 60:
                continue
            thr = 0.5 * sd                       # a representative normalised band
            for m in moves:
                if abs(m) >= thr:
                    total += 1
                    if abs(m) < BAND:
                        sub_cost += 1
        norm[cls] = {
            "assetsUsed": len([s for s in syms if len(per_asset[s]) >= 60]),
            "rowsBecomingDirectional": total,
            "ofWhichBelowTheCostBand": sub_cost,
            "shareBelowCostBand": round(sub_cost / total, 4) if total else None,
        }

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "label-adequacy-v1",
        "source": str(f),
        "rowsMeasured": rows, "immatureExcluded": immature,
        "shippedLabel": {"band": BAND, "horizonSessions": 20,
                         "justification": "make_dataset.py: roughly a typical 20-session "
                                          "round-trip cost plus slippage, so a move inside it is "
                                          "not tradeable even when its sign is right"},
        "byAssetClass": out_cls,
        "byYear": {y: dict(c) for y, c in sorted(by_year.items())},
        "volatilityNormalisedBandCheck": {
            "rule": "per-asset band of 0.5 x the full-sample sd of its own fwd20",
            "caveat": "full-sample sd, so this is descriptive only; a feature would need a "
                      "point-in-time estimate",
            "byAssetClass": norm,
        },
        "dataUse": "descriptive statistics over the whole history, including windows already "
                   "scored by three experiments. Legitimate for describing a label, which is a "
                   "property of the data; NOT an evaluation and not to be reported as one.",
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\nrows {rows:,}  (immature excluded {immature:,})\n")
    print(f"{'class':<11}{'rows':>9}{'FLAT':>8}{'UP':>8}{'DOWN':>8}{'|fwd20| p50':>12}"
          f"{'sd':>8}{'balanced band':>15}{'fixed/balanced':>16}")
    for cls, d in out_cls.items():
        s = d["labelShares"]
        print(f"{cls:<11}{d['rows']:>9,}{s.get('FLAT', 0):>8.3f}{s.get('UP', 0):>8.3f}"
              f"{s.get('DOWN', 0):>8.3f}{d['absFwd20']['p50']:>12.2f}{d['fwd20Sd']:>8.2f}"
              f"{str(d['bandThatWouldBalanceThisMarket']):>15}"
              f"{str(d['fixedBandVsBalanced']):>16}")
    print("\nunder a 0.5-sd per-asset band, share of newly-directional rows that are "
          "sub-cost (<2%):")
    for cls, d in norm.items():
        print(f"  {cls:<11} {d['shareBelowCostBand']}   "
              f"({d['ofWhichBelowTheCostBand']:,} of {d['rowsBecomingDirectional']:,})")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
