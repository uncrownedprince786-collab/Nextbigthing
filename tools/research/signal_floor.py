"""Can these features separate the classes even when allowed to cheat?

    python tools/research/signal_floor.py [--cache FILE] [--out FILE]

The question this settles
--------------------------
`label_adequacy.py` showed the +/-2% band is not the problem for 94% of the rows -- it is too
*narrow* for five of six markets, not too wide, and only forex (5% of rows) is badly served. So
the label is not the binding constraint, and the remaining suspect is the feature set.

Three candidates have failed by collapsing onto their training majority. That is consistent with
two very different things, and out-of-sample accuracy cannot tell them apart:

* the features carry signal but it does not generalise; or
* the features carry no usable signal about this target at all.

**The in-sample fit separates them.** A model fitted and scored on the *same* rows is allowed to
memorise, overfit, and exploit anything present. If it still cannot beat the majority class on
the data it just trained on, then the separation is not there to be found -- no split, no
regularisation choice and no relabelling will conjure it. This is a floor, not an estimate of
performance, and it is deliberately the one number in this project that is *supposed* to be
optimistic.

So three fits, all on identical rows, all scored in-sample:

1. **three-class**, the shipped target;
2. **binary UP vs DOWN**, FLAT dropped -- removes the band question entirely;
3. **shuffled labels**, the control: whatever this scores is what the same model extracts from
   noise at this sample size and feature count, and any real result must clear it.

The third is the one that makes the first two interpretable. A linear model with 44 columns on
tens of thousands of rows will beat the majority class a little on pure noise; without measuring
that, a small in-sample gain reads as signal when it is capacity.

Run on the cached crypto slice because it is already on disk and because crypto is the market
where a specialist was tried and failed -- if anywhere had signal to find, the evidence pointed
here. Nothing here is an evaluation; no holdout is involved and none of these numbers may be
reported as performance.
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

from baseline_experiment import CLASSES, FEATURES, SEED, fit_softmax, predict  # noqa: E402
from balanced_experiment import class_counts  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

CACHE = ROOT / ".cache" / "foundation" / "crypto_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "signal_floor_v2.json"
# The model's own labels for the FLAT-dropped cell. Index 1 is the positive class.
BINARY_CLASSES = ("DOWN", "UP")


def fit_in_sample(X: np.ndarray, y: np.ndarray, cols: list[int], classes) -> dict:
    """Fit and score on the same rows. Imputation and standardisation from those rows too.

    `classes` is the model's own label set in index order: it fixes the width of the fit *and*
    names every count returned here, so the two cannot disagree. Historically the width came from
    `len(CLASSES)` inside `fit_softmax` while the `k` argument only sized `majorityClass` and
    `predictedMix` -- a two-class cell was therefore fitted three-wide, its extra logit had no
    target row, and a prediction that landed on it would have been outside the reported range.
    The three-class cells pass `CLASSES` and fit exactly as before.
    """
    names = list(classes)
    Xa = X[:, cols]
    mu = np.nanmean(Xa, axis=0)
    mu = np.where(np.isnan(mu), 0.0, mu)
    Xa = np.where(np.isnan(Xa), mu, Xa)
    sd = Xa.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (Xa - mu) / sd
    W = fit_softmax(Z, y, classes=names)
    yp = predict(W, Z)
    acc = float((y == yp).mean())
    majority = float(max((y == i).mean() for i in range(len(names))))
    # Both mixes run through the same named, range-checked helper: a count can only be written
    # under a name `classes` actually contains.
    pred_mix = class_counts(yp, names)
    act_mix = class_counts(y, names)
    return {"rows": int(len(y)), "features": len(cols),
            "outputDimension": len(names),
            "outputClasses": names,
            "inSampleAccuracy": round(acc, 4),
            "majorityClass": round(majority, 4),
            "overMajority": round(acc - majority, 4),
            "predictedMix": pred_mix,
            "actualMix": act_mix,
            "classesPredicted": int(sum(1 for v in pred_mix.values() if v > 0))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    z = np.load(a.cache, allow_pickle=True)
    X, y = z["X"], z["y"]
    print(f"rows {len(X):,}  columns {X.shape[1]}")

    price_cols = [ALL_FEATURES.index(f) for f in FEATURES]
    all_cols = list(range(len(ALL_FEATURES)))

    res = {}
    res["threeClass_allFeatures"] = fit_in_sample(X, y, all_cols, CLASSES)
    res["threeClass_priceOnly"] = fit_in_sample(X, y, price_cols, CLASSES)

    keep = y != CLASSES.index("FLAT")
    yb = np.where(y[keep] == CLASSES.index("UP"), 1, 0).astype(np.int64)
    res["binaryUpDown_allFeatures"] = fit_in_sample(X[keep], yb, all_cols, BINARY_CLASSES)

    rng = np.random.default_rng(SEED)
    res["shuffledControl_threeClass"] = fit_in_sample(X, rng.permutation(y), all_cols, CLASSES)
    res["shuffledControl_binary"] = fit_in_sample(X[keep], rng.permutation(yb), all_cols,
                                                  BINARY_CLASSES)

    # The comparison that matters: a real fit must clear what the same model gets from noise.
    real3 = res["threeClass_allFeatures"]["overMajority"]
    noise3 = res["shuffledControl_threeClass"]["overMajority"]
    realb = res["binaryUpDown_allFeatures"]["overMajority"]
    noiseb = res["shuffledControl_binary"]["overMajority"]
    verdict = (
        "the features separate the classes in-sample by more than this model extracts from "
        "shuffled labels, so signal exists and the failure is generalisation"
        if (real3 - noise3) > 0.02 or (realb - noiseb) > 0.02 else
        "the features do NOT separate the classes in-sample beyond what the same model gets from "
        "shuffled labels. No split, regularisation or relabelling can recover a separation that "
        "is not present when the model is allowed to cheat"
    )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "signal-floor-v2",
        "correctionOf": {
            "artifact": "signal_floor.json",
            "version": "signal-floor-v1",
            "preservedUnchanged": True,
            "defect": "the binary cells were fitted three-wide, because fit_softmax sized its "
                      "matrix from len(CLASSES) == 3 while the k argument only sized "
                      "majorityClass and predictedMix. A third logit trained on no target row, "
                      "and predictedMix was keyed 0/1 for those cells while the three-class "
                      "cells were keyed 0/1/2.",
            "scope": "output dimension and reported class names only. Rows, features, splits, "
                     "seeds, preprocessing and every reported metric are unchanged, and the "
                     "three-class cells still fit CLASSES exactly as before; their numbers are "
                     "expected to be identical to v1.",
            "exposure": "this artifact is an in-sample diagnostic already examined in v1; the "
                        "holdout periods used against it were examined too. Nothing here is a "
                        "new independent result."},
        "what": "in-sample fits, deliberately optimistic; a floor on what is findable, never a "
                "performance estimate",
        "slice": "crypto, from the examples-v4-context cache",
        "results": res,
        "realMinusNoise": {"threeClass": round(real3 - noise3, 4),
                           "binary": round(realb - noiseb, 4)},
        "verdict": verdict,
        "notAnEvaluation": "no holdout is involved; none of these numbers may be reported as "
                           "performance",
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\n{'fit':<30}{'rows':>9}{'acc':>9}{'majority':>10}{'over':>9}{'classes':>9}")
    for k, v in res.items():
        print(f"{k:<30}{v['rows']:>9,}{v['inSampleAccuracy']:>9.4f}{v['majorityClass']:>10.4f}"
              f"{v['overMajority']:>+9.4f}{v['classesPredicted']:>9}")
    print(f"\nreal minus noise: three-class {real3 - noise3:+.4f}   binary {realb - noiseb:+.4f}")
    print(f"\n{verdict}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
