"""Does averaging several models read direction better than the best single one?

    python tools/research/crypto_ensemble.py --tag btc --horizon m5
    python tools/research/crypto_ensemble.py --tag crypto --horizon m5

Measured on the **validation** fold. The test fold is not loaded, not scored and not mentioned:
this tries several things, and a sweep that reads the holdout has spent it.

Why an ensemble is worth measuring and not just assuming
---------------------------------------------------------
Averaging decorrelated models is the oldest reliable gain in applied prediction, and it is one of
the few levers left here that is not "more data". But it is not free and it is not guaranteed:
boosted trees fitted on the same rows with slightly different hyper-parameters are highly
correlated, and averaging highly correlated models buys almost nothing while costing a multiple of
the fit time and the artifact size. Whether these particular models are decorrelated enough is a
measurement.

What is averaged
----------------
Probabilities, not votes. A vote throws away the margin, and the margin is what the conviction
floor reads -- an ensemble that votes would be an ensemble the serving path cannot band.

Three sources of disagreement, each cheap and each genuinely different:

  * **depth** -- a depth-3 and a depth-5 tree make different mistakes on the same rows;
  * **the feature subset** -- one member fitted without the order-flow block disagrees with one
    fitted with it wherever that block is doing the work;
  * **the row sample** -- each member sees a different contiguous majority of the training fold,
    which is bagging in time rather than at random, because adjacent rows share a feature window
    and a random bag would leak a row's neighbours into its own out-of-bag.

The comparison is against the best single member on the same fold, not against the current
artifact: if the ensemble only beats a weaker member it has shown nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import gbm  # noqa: E402
from crypto_capacity import conviction_curve, feature_columns  # noqa: E402
from crypto_horizons import HORIZONS  # noqa: E402
from crypto_matrix import prepare_cached  # noqa: E402
from crypto_conviction import training_config  # noqa: E402
from train_crypto_short import labels_for, split  # noqa: E402

OUT_DIR = ROOT / "data" / "foundation" / "dataset"

#: The members. Each differs from the others in a way that makes it wrong about different rows.
#: `rowsFrom` keeps a contiguous tail of the training fold -- bagging in time, because adjacent
#: rows share a feature window and a random bag would put a row's own neighbours out of bag.
MEMBERS = [
    {"depth": 3, "rounds": 700, "lr": 0.05, "l2": 2.0, "features": "context", "rowsFrom": 0.0},
    {"depth": 5, "rounds": 500, "lr": 0.05, "l2": 2.0, "features": "context", "rowsFrom": 0.0},
    {"depth": 4, "rounds": 600, "lr": 0.04, "l2": 4.0, "features": "noflow", "rowsFrom": 0.0},
    {"depth": 3, "rounds": 700, "lr": 0.05, "l2": 2.0, "features": "context", "rowsFrom": 0.25},
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure an ensemble against its best member.")
    ap.add_argument("--tag", required=True, choices=["btc", "crypto"])
    ap.add_argument("--horizon", required=True, choices=list(HORIZONS))
    ap.add_argument("--verbose", type=int, default=0)
    a = ap.parse_args()

    h = HORIZONS[a.horizon]
    cfg = training_config(a.tag, a.horizon)
    print(f"== {a.tag} {a.horizon} on {len(cfg['symbols'])} symbols, stride {cfg['stride']}, "
          f"context={cfg['context']}", flush=True)
    data = prepare_cached(cfg["symbols"], h["interval"], cfg["stride"], context=cfg["context"])
    y, usable, _ = labels_for(data, h["bars"])
    ts = data["ts"]
    step_ms = next(iter(data["corpora"].values()))["stepMs"]
    tr_m, va_m, _te, split_meta = split(ts, h["bars"], step_ms)
    tr = np.flatnonzero(tr_m & usable)
    va = np.flatnonzero(va_m & usable)
    # Chronological, so "the last 75% of training" means the most recent 75% and not a scatter.
    tr = tr[np.argsort(ts[tr], kind="stable")]
    print(f"   train {len(tr):,}  validation {len(va):,}  (test fold not loaded)", flush=True)

    yva = y[va].astype(np.int64)
    probs = []
    results = []
    for i, m in enumerate(MEMBERS):
        cols, names = feature_columns(m["features"])
        rows = tr[int(len(tr) * m["rowsFrom"]):]
        Xtr = data["X"][rows][:, cols].astype(np.float64)
        ytr = y[rows].astype(np.float64)
        Xva = data["X"][va][:, cols].astype(np.float64)
        t0 = time.time()
        tree = gbm.fit(Xtr, ytr, rounds=m["rounds"], depth=m["depth"], lr=m["lr"], l2=m["l2"],
                       X_val=Xva, y_val=yva.astype(np.float64), early_stop=40, verbose=a.verbose)
        p = gbm.predict_proba(tree, Xva)
        acc = float(((p >= 0.5).astype(int) == yva).mean())
        probs.append(p)
        results.append({**m, "featureCount": len(names), "rows": int(len(rows)),
                        "roundsKept": tree["roundsKept"], "fitSeconds": round(time.time() - t0, 1),
                        "validationAccuracy": round(acc, 5)})
        print(f"   member {i}: depth {m['depth']} {m['features']}({len(names)}) "
              f"rows {len(rows):,}  acc {acc:.5f}  {time.time() - t0:.0f}s", flush=True)

    P = np.vstack(probs)
    mean_p = P.mean(axis=0)
    up = float(yva.mean())
    majority = max(up, 1 - up)
    ens_acc = float(((mean_p >= 0.5).astype(int) == yva).mean())
    best = max(r["validationAccuracy"] for r in results)
    # How much the members actually disagree. An ensemble of four copies of one model is one
    # model, and this is the number that says whether that is what was built.
    corr = np.corrcoef(P)
    off = corr[np.triu_indices(len(P), k=1)]

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_ensemble.py",
        "measuredOn": "the validation fold only; the test fold is not read by this file",
        "tag": a.tag, "horizon": a.horizon,
        "symbols": len(cfg["symbols"]), "stride": cfg["stride"], "context": cfg["context"],
        "rows": {"train": int(len(tr)), "validation": int(len(va))},
        "split": split_meta,
        "members": results,
        "bestMember": round(best, 5),
        "ensemble": round(ens_acc, 5),
        "gainOverBestMember": round(ens_acc - best, 5),
        "validationMajority": round(majority, 5),
        "meanPairwiseCorrelation": round(float(off.mean()), 4),
        "ensembleConvictionCurve": conviction_curve(mean_p, yva),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"crypto_ensemble_{a.tag}_{a.horizon}.json"
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")

    print(f"\n   best member {best:.5f}   ensemble {ens_acc:.5f}   "
          f"gain {ens_acc - best:+.5f}   (majority {majority:.5f})")
    print(f"   mean pairwise correlation between members: {off.mean():.4f}")
    at = [c for c in doc["ensembleConvictionCurve"] if c["minMargin"] == 0.06]
    if at and at[0]["accuracy"]:
        print(f"   ensemble @0.06 floor: {at[0]['accuracy']:.4f} on {at[0]['coverage']:.1%}")
    print(f"   wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
