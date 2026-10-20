"""Does the US five-session lift survive being tested properly? Blocked bootstrap and walk-forward.

    python tools/research/validate_lift.py [--market US] [--band 2.0] [--boot 2000]

What this is checking, and why the first number was never going to hold
-----------------------------------------------------------------------
`sweep.py` reported US / 5 sessions / 2.0% band at **0.3988 against a 0.3475 base rate, +5.1
points, z = 24.05 on 49,679 rows**. That z came from `significance.binomial_lift`, which assumes
49,679 **independent** trials. The holdout has nothing of the kind:

* **Cross-sectional dependence.** Those rows are about 279 symbols on each of 178 sessions. When
  the US market falls, most of them fall together, so a session is far closer to one observation
  than to 279. On its own that inflates the true standard error by roughly `sqrt(279)` -- about
  **17x**.
* **Overlapping windows.** A 5-session forward return computed every session shares four of its
  five days with the next row for the same symbol. Consecutive observations are not separate
  evidence; this costs roughly a further `sqrt(5)`, about **2.2x**.
* **Multiplicity and selection.** The arm was the best of **90** measured, and it was chosen after
  seeing all of them. A one-sided test at 0.05 applied ninety times expects four or five passes
  from noise alone.

Together those put the honest z somewhere near **0.6** before multiplicity is even applied. That
is an estimate, so this file measures it instead.

How it measures
---------------
**A date-blocked bootstrap.** Whole sessions are resampled with replacement and the lift is
recomputed on each resample. Resampling dates rather than rows keeps every within-session
correlation intact -- whatever structure ties 279 symbols together on one day travels with the
day -- and the spread of the resulting lifts is the sampling distribution the naive test should
have used. It assumes sessions are exchangeable, which overlapping 5-session windows still
violate slightly, so the interval it produces is if anything a little too narrow.

**Walk-forward on periods the model never saw.** The sweep scored one holdout. A lift that is real
should appear, with the same sign, when the same recipe is trained to the end of 2021 and tested
on 2022, trained to 2022 and tested on 2023, and so on. Each fold trains from scratch with the
same embargo; no fold's result influences another's design.

**Multiplicity.** The bootstrap p-value is reported raw and Bonferroni-adjusted for the 90 arms the
candidate was selected from. Bonferroni is conservative and that is the right direction here: the
arm was not pre-registered, it was picked for being the largest.

Nothing here can rescue a result. It can only fail to kill one.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

import sweep  # noqa: E402
import sweep_cache  # noqa: E402
from baseline_experiment import CLASSES, EMBARGO, FEATURES  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "validate_lift.json"

#: Arms measured in `sweep.json` + `sweep_balance.json`, which the candidate was the best of.
ARMS_SEARCHED = 90


def fit_and_predict(X, y, dates, train_end, family="logistic", feature_set="all"):
    """Train to `train_end` with the embargo, return `(yp, yte, te_dates)` or `None`."""
    tr, te, _ = sweep.chronological(dates, train_end, EMBARGO)
    if tr is None or len(tr) < sweep.MIN_TRAIN_ROWS or len(te) < sweep.MIN_HOLDOUT_ROWS:
        return None
    cols = ([ALL_FEATURES.index(f) for f in FEATURES] if feature_set == "price"
            else list(range(len(ALL_FEATURES))))
    Ztr, Zte = sweep.prepared(X, tr, te, cols)
    P = sweep.FAMILIES[family](Ztr, y[tr], Zte)
    # The baseline anyone could have run: the commonest class in the training fold, which is
    # knowable at the cutoff. Taken from `tr`, never from `te`.
    baseline_class = int(np.bincount(y[tr], minlength=len(CLASSES)).argmax())
    return P.argmax(axis=1), y[te], dates[te], baseline_class


def lift_by_date(yp, yte, dts, baseline_class: int):
    """Per-session `(model_rate, baseline_rate, n)`, the unit the bootstrap resamples.

    **The baseline is a fixed class chosen from the training fold, not that day's most common
    one.** The difference decides the sign of the answer, and the first version of this file got
    it wrong: it scored the model against the majority class *within each session*, which is an
    oracle -- it knows which way the market went that day, and no forecaster does. Measured
    against that, the model lost by 4.8 points in every walk-forward fold, which says only that
    the market moves together intraday and a constant predictor cannot exploit it either.

    The honest comparator is the one a person could actually have run on the morning: always
    predict the class that was commonest in the data available up to the cutoff. That is what
    `baseline_class` is, and it is held fixed across every session and every bootstrap resample.
    """
    out = {}
    for d in np.unique(dts):
        sel = dts == d
        yt = yte[sel]
        out[d] = (float((yp[sel] == yt).mean()),
                  float((yt == baseline_class).mean()),
                  int(sel.sum()))
    return out


def blocked_bootstrap(per_date: dict, draws: int, seed: int = 20261020):
    """Resample whole sessions with replacement; return the lift distribution.

    Each session is weighted by its row count when the overall rate is recomputed, so a thin
    session does not count as much as a full one -- the statistic being bootstrapped is the same
    row-weighted accuracy the sweep reported, not an average of per-day rates.
    """
    keys = list(per_date)
    acc = np.asarray([per_date[k][0] for k in keys])
    maj = np.asarray([per_date[k][1] for k in keys])
    n = np.asarray([per_date[k][2] for k in keys], dtype=np.float64)
    rng = np.random.default_rng(seed)
    lifts = np.empty(draws)
    idx_space = np.arange(len(keys))
    for b in range(draws):
        pick = rng.choice(idx_space, size=len(keys), replace=True)
        w = n[pick]
        lifts[b] = float((acc[pick] * w).sum() / w.sum() - (maj[pick] * w).sum() / w.sum())
    point = float((acc * n).sum() / n.sum() - (maj * n).sum() / n.sum())
    return point, lifts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--market", default="US")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--band", type=float, default=2.0, help="band scale, not percent")
    ap.add_argument("--family", default="logistic")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--cache", default=str(sweep_cache.DEFAULT_OUT))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    data = sweep_cache.load(Path(a.cache))
    d = data[a.market]
    y, usable = sweep.labels_for(d[f"fwd{a.horizon}"], a.horizon, a.band)
    X, dates, y = d["X"][usable], d["dates"][usable], y[usable]

    print(f"== {a.market} h{a.horizon} band x{a.band} {a.family} ==")

    # 1. Reproduce the headline, then re-test its standard error against the real unit of evidence.
    got = fit_and_predict(X, y, dates, sweep.TRAIN_END, a.family)
    if got is None:
        raise SystemExit("not enough rows")
    yp, yte, dts, base_cls = got
    per_date = lift_by_date(yp, yte, dts, base_cls)
    point, lifts = blocked_bootstrap(per_date, a.boot)
    se = float(lifts.std(ddof=1))
    z = point / se if se > 0 else 0.0
    # One-sided: how often does a resample fail to show a positive lift?
    p_raw = float((lifts <= 0).mean())
    p_bonf = min(1.0, p_raw * ARMS_SEARCHED)
    lo, hi = (float(np.percentile(lifts, 2.5)), float(np.percentile(lifts, 97.5)))

    print(f"  rows {len(yte):,} across {len(per_date)} sessions "
          f"({len(yte) / len(per_date):.0f} per session)")
    print(f"  baseline: always predict {CLASSES[base_cls]} (commonest in the training fold)")
    print(f"  lift {point:+.4f}")
    print(f"  date-blocked bootstrap: SE {se:.4f}  z {z:.2f}  95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"  one-sided p {p_raw:.4f}   Bonferroni over {ARMS_SEARCHED} arms: {p_bonf:.4f}")

    # 2. The same recipe on periods it has never been scored against.
    print("\n  walk-forward (same recipe, trained from scratch each fold):")
    folds = []
    for end in ("2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"):
        g = fit_and_predict(X, y, dates, end, a.family)
        if g is None:
            continue
        fyp, fyte, fdts, fbase = g
        nxt = str(int(end[:4]) + 1)
        keep = np.asarray([s.startswith(nxt) for s in fdts])
        if keep.sum() < sweep.MIN_HOLDOUT_ROWS:
            continue
        pd_ = lift_by_date(fyp[keep], fyte[keep], fdts[keep], fbase)
        p_, l_ = blocked_bootstrap(pd_, max(400, a.boot // 4))
        se_ = float(l_.std(ddof=1))
        folds.append({"trainEnd": end, "testYear": nxt, "rows": int(keep.sum()),
                      "sessions": len(pd_), "lift": round(p_, 4),
                      "bootSE": round(se_, 4), "z": round(p_ / se_, 2) if se_ else None})
        print(f"    train<={end}  test {nxt}: lift {p_:+.4f}  bootSE {se_:.4f}  "
              f"z {(p_ / se_ if se_ else 0):+.2f}  ({keep.sum():,} rows, {len(pd_)} sessions)")

    positive = [f for f in folds if f["lift"] > 0]
    print(f"\n  folds with a positive lift: {len(positive)} of {len(folds)}")
    survives = bool(p_bonf < 0.05 and len(positive) >= max(1, len(folds) - 1))
    print(f"  VERDICT: the lift {'SURVIVES' if survives else 'DOES NOT SURVIVE'} "
          f"blocked resampling, walk-forward and multiplicity")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "producedBy": "tools/research/validate_lift.py",
        "candidate": {"market": a.market, "horizon": a.horizon, "bandScale": a.band,
                      "family": a.family},
        "headline": {"rows": int(len(yte)), "sessions": len(per_date), "lift": round(point, 4)},
        "blockedBootstrap": {"draws": a.boot, "standardError": round(se, 4), "z": round(z, 2),
                             "ci95": [round(lo, 4), round(hi, 4)],
                             "pOneSided": round(p_raw, 4),
                             "pBonferroni": round(p_bonf, 4), "armsSearched": ARMS_SEARCHED},
        "walkForward": folds,
        "survives": survives,
        "note": ("the naive row-independent test reported z=24.05 on the same predictions; the "
                 "difference is entirely that rows are not independent observations"),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
