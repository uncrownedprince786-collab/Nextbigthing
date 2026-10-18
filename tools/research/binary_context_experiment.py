"""Binary target, 44 context features, converged class-balanced fit, scored out-of-sample.

    python tools/research/binary_context_experiment.py [--inspect] [--out FILE]

**Pre-registered before any number from this run was seen.** The target, folds, optimizer,
features, controls and the five acceptance criteria below were fixed here first; the run may only
confirm or refute them.

The question this settles
--------------------------
`signal_floor.py` measured an in-sample ceiling for four cells and reported that the **binary
UP-vs-DOWN target on all 44 features is the strongest of them** (+0.0361 over majority, against
+0.0037 for the shipped three-class/15-feature cell), while every out-of-sample run so far has
scored the *three-class* target. The chain's standing diagnosis is that the features do carry
separation in-sample and the failure is generalisation -- so the cell with the largest in-sample
headroom, scored honestly out-of-sample with a fit that actually converges, is the one experiment
that has never been run.

It is not a rerun. Every prior out-of-sample run on this cache (`stationarity`,
`prevalence_adjustment`, `cross_sectional_ranking`, `horizon_experiment`, `train_v3_crypto`)
carried the three-class `label20` target; `balanced_experiment` carried three classes on 15 price
features. None dropped FLAT and scored UP-vs-DOWN with a converged fit.

What is held identical
-----------------------
* **Data.** `.cache/foundation/crypto_slice.npz` -- the exact input `signal_floor` used, so the
  in-sample bound it reports is comparable to what this run measures out-of-sample. Its sha256 is
  recorded in the artifact.
* **Row selection.** `keep = y != FLAT`, `yb = 1 if UP else 0` -- `signal_floor.py` lines 102-104.
* **Features.** All 44 `ALL_FEATURES` in order, point-in-time as stored.
* **Folds.** `baseline_experiment`'s rule unchanged: one fold per test year 2021..2026, train on
  every row before `cut_pos - EMBARGO`, EMBARGO = 20 decision dates, drop a fold under 5,000
  training or 500 test rows.
* **Feature handling.** Imputation from the training fold's column nan-mean and standardisation
  from the training fold's own mean and standard deviation only; a zero standard deviation is
  replaced by 1.
* **Optimizer.** `fit_weighted` from `balanced_experiment`: full-batch softmax, per-class weights
  normalised to mean 1, stopped when the loss stops moving (TOL 1e-6, MAX_STEPS 20,000), so the
  artifact can show convergence rather than assert it. Class weights are `n / (2 * n_c)` over the
  two classes present.
* **Seed.** `SEED = 20261015` throughout, plus `SEED + 1000 + testYear` for the control.
* **Reference.** `over_majority` from `stationarity`, which is the comparator every prior run used.
* **Uncertainty.** `block_bootstrap` from `stationarity`: 20-decision-date blocks, 400 resamples.

Correction this version exists for (v1 -> v2)
----------------------------------------------
`binary-context-v1` fitted this two-class target with **three output columns**, because
`fit_weighted` sized its weight matrix from `len(CLASSES)` and that is 3. Two consequences, both
verified against the preserved v1 artifact:

* **The optimizer was not the model the labels describe.** Labels {0,1} occupy columns 0 and 1,
  column 2 (the one `CLASSES` calls UP) never receives a target row, and the three-way softmax
  normalisation and its gradients differ from a genuine two-class fit. With `predict` taking the
  argmax of *logits*, that column could still win a row; it did not, but its presence changed the
  training trajectory the whole measurement rests on.
* **The saved mixes named the wrong classes.** `predictedMix` and `actualMix` indexed into
  `CLASSES`, so binary index 1 -- the positive class -- was written out as `FLAT`, and `UP` was
  written as 0 on **every fold** of v1 while the real UP rows sat under `FLAT`.

v2 fits two columns named `["DOWN", "UP"]`, builds both mixes with `class_counts` against those
same two names, and asserts the weight matrix is `(features + 1) * 2`. Everything else -- cache,
rows, features, folds, embargo, preprocessing order, class-weight policy, seed, controls and the
**five acceptance criteria and their thresholds** -- is unchanged. `binary-context-v1` is preserved
untouched on disk; this writes `binary_context_experiment_v2.json`.

**Exposure, stated plainly:** these calendar years were previously examined by v1 and by every
earlier run on this cache, so a corrected number here is *not* a pristine independent result. The
repair re-measures an already-observed holdout; it does not tune against it, and no threshold was
moved after any metric was seen.

Controls
--------
1. **Majority on the same test rows** -- the reference. A positive margin over it is the whole
   claim.
2. **Shuffled training labels**, same optimizer, same folds, scored on the real test rows -- what
   this pipeline extracts from noise at this sample size and feature count. The candidate must
   clear it with a block-bootstrap interval.

Acceptance, fixed before the run
---------------------------------
All five must hold, or the result is NO-GO with the failing criteria named:

* **C1** mean margin (accuracy - majority) over scored folds > 0.
* **C2** folds beating their own majority >= `min(MIN_FOLDS_WON, foldsScored)`, where
  `MIN_FOLDS_WON = 4` is imported unchanged from `balanced_experiment`.
* **C3** no degenerate fold: one class predicted on more than `DEGENERATE_SHARE` (0.70) of a
  fold's test rows while that class is actually under half of them.
* **C4** the block-bootstrap 95% interval for (candidate margin - shuffled-control margin) has
  `p2_5 > 0`.
* **C5** the worst fold's margin >= -0.05.

A regime from `baseline_experiment.REGIMES` holding >= 1,000 test rows with margin <= -0.05 does
not fail the run; it is named in the verdict as a qualification.

Fidelity limitations, declared in advance
------------------------------------------
* The cache carries `X`, `y`, `dates` and `syms` only -- no `dataQuality` mask -- so the quarantine
  `balanced_experiment` applies cannot be reproduced here. Rows are selected exactly as
  `signal_floor` selected them, which is the claim under test.
* The slice is crypto only: one market, 93,452 rows. A result here is a result about that slice and
  says nothing about the other markets.

Nothing here is a promotion. A passing verdict means the family is worth reproducing in a fresh
process, and nothing more.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from baseline_experiment import CLASSES, EMBARGO, REGIMES, SEED, predict  # noqa: E402
from balanced_experiment import (  # noqa: E402
    DEGENERATE_SHARE,
    MIN_FOLDS_WON,
    class_counts,
    fit_weighted,
)
from stationarity import BLOCK_DAYS, BOOTSTRAP, block_bootstrap, over_majority  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

CACHE = ROOT / ".cache" / "foundation" / "crypto_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "binary_context_experiment_v2.json"
SIGNAL_FLOOR = ROOT / "data" / "foundation" / "dataset" / "signal_floor.json"
SIGNAL_FLOOR_V2 = ROOT / "data" / "foundation" / "dataset" / "signal_floor_v2.json"

VERSION = "binary-context-v2"
MIN_TRAIN, MIN_TEST = 5000, 500
WORST_FOLD_FLOOR = -0.05
REGIME_MIN_ROWS = 1000
REGIME_LOSS = -0.05
# Indices into the *cache's* three-class labels, used only to read rows out of it.
DOWN, FLAT, UP = CLASSES.index("DOWN"), CLASSES.index("FLAT"), CLASSES.index("UP")
# The model's own labels. Index 1 is the positive class and must never be reported as FLAT.
BINARY_CLASSES = ("DOWN", "UP")
BINARY_DOWN, BINARY_UP = 0, 1
N_BINARY = len(BINARY_CLASSES)
assert BINARY_CLASSES[BINARY_DOWN] == "DOWN" and BINARY_CLASSES[BINARY_UP] == "UP"
assert "FLAT" not in BINARY_CLASSES


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def plan(dates: np.ndarray) -> list[dict]:
    """The folds `baseline_experiment` would choose, without fitting anything."""
    order = np.argsort(dates, kind="stable")
    d = dates[order]
    udates = np.unique(d)
    didx = {x: i for i, x in enumerate(udates)}
    pos = np.asarray([didx[x] for x in d])
    rows = []
    for cut_year in range(2021, 2027):
        cut = f"{cut_year}-01-01"
        cand = [x for x in udates if x >= cut]
        if not cand:
            continue
        cut_pos = didx.get(cut, didx[cand[0]])
        tr = pos < (cut_pos - EMBARGO)
        te = (d >= cut) & (d <= f"{cut_year}-12-31")
        rows.append({"testYear": cut_year, "trainRows": int(tr.sum()), "testRows": int(te.sum()),
                     "fits": bool(tr.sum() >= MIN_TRAIN and te.sum() >= MIN_TEST),
                     "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
                     "testBegins": str(d[te][0]) if te.any() else None,
                     "testEnds": str(d[te][-1]) if te.any() else None})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--inspect", action="store_true",
                    help="print the data and the fold plan, fit nothing, write nothing")
    a = ap.parse_args()

    cache = Path(a.cache)
    z = np.load(cache, allow_pickle=True)
    X, y, dates = z["X"], z["y"], z["dates"]
    print(f"cache {cache.name}  rows {len(X):,}  columns {X.shape[1]}  "
          f"dates {min(dates)} .. {max(dates)}")

    if X.shape[1] != len(ALL_FEATURES):
        raise SystemExit(f"cache has {X.shape[1]} columns, ALL_FEATURES has {len(ALL_FEATURES)}")

    keep = y != FLAT
    # Explicit two-class encoding: the cache's UP becomes BINARY_UP, everything else that is not
    # FLAT is DOWN. Written out rather than implied so the label array and BINARY_CLASSES cannot
    # drift apart -- that drift is exactly what named the positive class FLAT in v1.
    yb = np.where(y[keep] == UP, BINARY_UP, BINARY_DOWN).astype(np.int64)
    Xb, db = X[keep], dates[keep]
    share_up = float(yb.mean())
    assert set(np.unique(yb).tolist()) <= {BINARY_DOWN, BINARY_UP}
    print(f"rows kept after dropping FLAT: {len(Xb):,}  ({keep.sum() / len(y):.1%} of the slice)"
          f"   class balance UP {share_up:.4f} / DOWN {1 - share_up:.4f}")

    if a.inspect:
        print("\nfold plan (nothing fitted, nothing written):")
        for r in plan(db):
            flag = "fits" if r["fits"] else "SKIPPED (too few rows)"
            print(f"  {r['testYear']}: train {r['trainRows']:>6,}  test {r['testRows']:>5,}"
                  f"  {flag}  train ends {r['trainEnds']}")
        return 0

    order = np.argsort(db, kind="stable")
    Xb, yb, db = Xb[order], yb[order], db[order]
    udates = np.unique(db)
    didx = {d: i for i, d in enumerate(udates)}
    pos = np.asarray([didx[d] for d in db])

    folds, pool = [], {"y": [], "yp": [], "yc": [], "dates": []}
    for cut_year in range(2021, 2027):
        cut = f"{cut_year}-01-01"
        cand = [d for d in udates if d >= cut]
        if not cand:
            continue
        cut_pos = didx.get(cut, didx[cand[0]])
        tr = pos < (cut_pos - EMBARGO)
        te = (db >= cut) & (db <= f"{cut_year}-12-31")
        if tr.sum() < MIN_TRAIN or te.sum() < MIN_TEST:
            continue

        Xtr, Xte = Xb[tr], Xb[te]
        mu = np.nanmean(Xtr, axis=0)
        mu = np.where(np.isnan(mu), 0.0, mu)
        Xtr = np.where(np.isnan(Xtr), mu, Xtr)
        Xte = np.where(np.isnan(Xte), mu, Xte)
        sd = Xtr.std(axis=0)
        sd[sd == 0] = 1.0
        Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd

        counts = np.bincount(yb[tr], minlength=2).astype(float)
        weights = np.asarray([len(yb[tr]) / (2 * counts[0]), len(yb[tr]) / (2 * counts[1])])

        W, steps, loss = fit_weighted(Ztr, yb[tr], weights, classes=BINARY_CLASSES)
        if W.shape != (Ztr.shape[1] + 1, N_BINARY):
            raise SystemExit(f"expected {(Ztr.shape[1] + 1, N_BINARY)}, got {W.shape}")
        yp = predict(W, Zte)
        if yp.min() < 0 or yp.max() >= N_BINARY:
            raise SystemExit(f"prediction outside {BINARY_CLASSES}: {yp.min()}..{yp.max()}")

        # Capacity control: the same fit on permuted training labels, scored on real test rows.
        rng = np.random.default_rng(SEED + 1000 + cut_year)
        Wc, steps_c, _ = fit_weighted(Ztr, rng.permutation(yb[tr]), weights, classes=BINARY_CLASSES)
        yc = predict(Wc, Zte)

        acc, maj, over = over_majority(yb[te], yp)
        acc_c, maj_c, over_c = over_majority(yb[te], yc)
        pred_mix = np.bincount(yp, minlength=N_BINARY) / len(yp)
        act_mix = np.bincount(yb[te], minlength=N_BINARY) / len(yb[te])
        worst = int(pred_mix.argmax())
        degenerate = bool(pred_mix[worst] > DEGENERATE_SHARE and act_mix[worst] < 0.5)

        fold = {"testYear": cut_year, "trainRows": int(tr.sum()), "testRows": int(te.sum()),
                "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
                "testBegins": str(db[te][0]), "testEnds": str(db[te][-1]),
                "steps": int(steps), "converged": bool(steps < 20_000), "finalLoss": round(loss, 6),
                "accuracy": acc, "majority": maj, "margin": over,
                "beatsMajority": bool(over > 0),
                "shuffledControlAccuracy": acc_c, "shuffledControlMargin": over_c,
                "candidateMinusControl": round(over - over_c, 4),
                "predictedMix": class_counts(yp, BINARY_CLASSES),
                "actualMix": class_counts(yb[te], BINARY_CLASSES),
                "worstPredictedShare": round(float(pred_mix[worst]), 4),
                "actualShareOfWorstPredicted": round(float(act_mix[worst]), 4),
                "degenerate": degenerate,
                "controlSteps": int(steps_c)}
        folds.append(fold)
        pool["y"].append(yb[te])
        pool["yp"].append(yp)
        pool["yc"].append(yc)
        pool["dates"].append(db[te])
        print(f"  fold {cut_year}: acc {acc:.4f}  majority {maj:.4f}  margin {over:+.4f}  "
              f"control {over_c:+.4f}  steps {steps}{'  DEGENERATE' if degenerate else ''}",
              flush=True)

    if not folds:
        raise SystemExit("no fold met the pre-declared minimums")

    y_all = np.concatenate(pool["y"])
    yp_all = np.concatenate(pool["yp"])
    yc_all = np.concatenate(pool["yc"])
    d_all = np.concatenate(pool["dates"])
    boot = block_bootstrap(d_all, y_all, yp_all, yc_all, np.random.default_rng(SEED + 77))

    won = sum(1 for f in folds if f["beatsMajority"])
    need = min(MIN_FOLDS_WON, len(folds))
    margins = [f["margin"] for f in folds]
    controls = [f["shuffledControlMargin"] for f in folds]
    mean_margin = float(np.mean(margins))
    worst_margin = float(min(margins))
    degenerate_folds = [f["testYear"] for f in folds if f["degenerate"]]
    p25 = boot.get("p2_5")

    criteria = {
        "C1_meanMarginPositive": [round(mean_margin, 4), "> 0", mean_margin > 0],
        "C2_foldsWon": [won, f">= {need}", won >= need],
        "C3_noDegenerateFold": [degenerate_folds, "== []", not degenerate_folds],
        "C4_controlIntervalExcludesZero": [p25, "> 0", (p25 is not None and p25 > 0)],
        "C5_worstFoldMargin": [round(worst_margin, 4), f">= {WORST_FOLD_FLOOR}",
                               worst_margin >= WORST_FOLD_FLOOR],
    }
    failing = [k for k, v in criteria.items() if not v[2]]

    regimes = []
    for name, lo, hi in REGIMES:
        sel = (d_all >= lo) & (d_all <= hi)
        n = int(sel.sum())
        if n < 200:
            continue
        a_r, m_r, o_r = over_majority(y_all[sel], yp_all[sel])
        regimes.append({"regime": name, "rows": n, "accuracy": a_r, "majority": m_r,
                        "margin": o_r,
                        "qualification": bool(n >= REGIME_MIN_ROWS and o_r <= REGIME_LOSS)})

    bound, bound_source = None, None
    if SIGNAL_FLOOR_V2.exists():
        sf = json.loads(SIGNAL_FLOOR_V2.read_text(encoding="utf-8"))
        bound = (sf.get("results", {}).get("binaryUpDown_allFeatures") or {}).get("overMajority")
        bound_source = f"{SIGNAL_FLOOR_V2.name}, two-class binary cell"
    bound_v1 = None
    if SIGNAL_FLOOR.exists():
        sf1 = json.loads(SIGNAL_FLOOR.read_text(encoding="utf-8"))
        bound_v1 = (sf1.get("results", {}).get("binaryUpDown_allFeatures") or {}).get("overMajority")

    qualified = [r["regime"] for r in regimes if r["qualification"]]
    if not failing:
        verdict = ("GO-CANDIDATE: the binary target on 44 context features beats its own majority "
                   "out-of-sample with a converged fit and clears the shuffled control with a "
                   "block-bootstrap interval excluding zero. This is a family worth reproducing in "
                   "a fresh process; it is not a promotion.")
    else:
        verdict = f"NO-GO: {', '.join(failing)} failed the criteria fixed before this run."
    if qualified:
        verdict += f" Qualification: adverse in {', '.join(qualified)}."

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": VERSION,
        "question": "does the binary UP-vs-DOWN target on all 44 context features beat its own "
                    "majority out-of-sample with a converged class-balanced fit?",
        "whyNotARerun": "every prior out-of-sample run on this cache carried the three-class "
                        "label20 target; no prior run dropped FLAT and scored UP-vs-DOWN "
                        "out-of-sample. v2 is not a rerun of that family either: it corrects "
                        "binary-context-v1's three-output fit and its mis-named mixes",
        "correctionOf": {
            "artifact": "binary_context_experiment.json",
            "version": "binary-context-v1",
            "preservedUnchanged": True,
            "defect": "v1 fitted this two-class target with three output columns, because "
                      "fit_weighted sized its matrix from len(CLASSES) == 3. Labels {0,1} used "
                      "columns 0 and 1, the column CLASSES calls UP never received a target row, "
                      "and predictedMix/actualMix indexed into CLASSES so the binary positive "
                      "class was written out as FLAT while UP was written as 0 on every fold.",
            "scope": "correctness repair of the model output dimension and of the reported class "
                     "names only; criteria, thresholds and protocol untouched",
            "exposure": "these calendar years were previously examined by v1 and by every earlier "
                        "run on this cache, so this corrected run re-measures an already-observed "
                        "holdout and is not a pristine independent result. No threshold was "
                        "changed after any metric was seen."},
        "data": {"cache": str(cache.relative_to(ROOT)) if cache.is_relative_to(ROOT) else str(cache),
                 "sha256": sha256(cache), "bytes": cache.stat().st_size,
                 "slice": "crypto", "rowsInCache": int(len(X)),
                 "rowsAfterDroppingFlat": int(len(Xb)),
                 "flatsDropped": int((~keep).sum()),
                 "upShare": round(share_up, 4), "dateRange": [str(min(db)), str(max(db))],
                 "features": len(ALL_FEATURES)},
        "target": {"label": "binary UP vs DOWN, FLAT dropped", "up": 1, "down": 0,
                   "construction": "signal_floor.py lines 102-104",
                   "classes": list(BINARY_CLASSES),
                   "encodingNote": "BINARY_CLASSES[1] is UP and is reported as UP; the cache's "
                                   "three-class FLAT rows are dropped before encoding"},
        "model": {"optimizer": "fit_weighted imported from balanced_experiment, called with "
                               "classes=BINARY_CLASSES so the matrix is built for two outputs",
                  "outputClasses": list(BINARY_CLASSES),
                  "outputDimension": N_BINARY,
                  "weightMatrixShape": [int(X.shape[1] + 1), N_BINARY],
                  "corrects": "binary-context-v1's three-column fit on a two-class target",
                  "classWeights": "n / (2 * n_c) over the two classes present, normalised to mean "
                                  "1 inside fit_weighted",
                  "tolerance": 1e-6, "maxSteps": 20_000,
                  "convergedFolds": sum(1 for f in folds if f["converged"]),
                  "ofFolds": len(folds)},
        "protocol": {"folds": "baseline_experiment's rule: one fold per test year 2021..2026",
                     "embargoDecisionDates": EMBARGO, "seed": SEED,
                     "controlSeed": f"SEED + 1000 + testYear",
                     "imputation": "training-fold column nan-mean",
                     "standardisation": "training-fold mean and standard deviation only",
                     "minTrainRows": MIN_TRAIN, "minTestRows": MIN_TEST,
                     "uncertainty": f"moving-block bootstrap over decision dates, {BLOCK_DAYS}-date "
                                    f"blocks, {BOOTSTRAP} resamples, candidate minus shuffled "
                                    "control",
                     "reference": "over_majority imported unchanged from stationarity"},
        "criteria": criteria,
        "criteriaSource": "fixed in this docstring before any number from this run was seen",
        "folds": folds,
        "summary": {"foldsScored": len(folds), "foldsWon": won, "foldsRequired": need,
                    "meanMargin": round(mean_margin, 4),
                    "meanShuffledControlMargin": round(float(np.mean(controls)), 4),
                    "worstFoldMargin": round(worst_margin, 4),
                    "worstFoldYear": int(folds[int(np.argmin(margins))]["testYear"]),
                    "degenerateFolds": degenerate_folds,
                    "anyFoldDegenerate": bool(degenerate_folds),
                    "pooledRows": int(len(y_all)),
                    "bootstrap": boot,
                    "inSampleBoundFromSignalFloor": bound,
                    "inSampleBoundSource": bound_source,
                    "inSampleBoundNote": "signal_floor's in-sample binary/44 over-majority, "
                                         "measured by the corrected two-class cell; a holdout "
                                         "number is expected to be smaller, not larger",
                    "inSampleBoundFromSignalFloorV1": bound_v1,
                    "inSampleBoundV1Note": "the same bound as measured by the historical "
                                           "three-column construction, kept for disclosure; its "
                                           "reported mix summed to the row count, so no column-2 "
                                           "prediction occurred even though the third logit was "
                                           "trained"},
        "byRegime": regimes,
        "regimeClause": f"reported, not a pass criterion; a regime with >= {REGIME_MIN_ROWS} rows "
                        f"and margin <= {REGIME_LOSS} is named in the verdict",
        "fidelityLimitations": [
            "the cache carries no dataQuality mask, so the quarantine balanced_experiment applies "
            "cannot be reproduced here",
            "crypto only: one market, 93,452 rows in the cache",
            "this holdout was examined by binary-context-v1 and is re-measured here, so it is a "
            "correction of an observed result, not a fresh independent one"],
        "verdict": verdict,
        "failingCriteria": failing,
        "nextQuestion": ("the generalisation gap itself: what changes the margin, given the "
                         "in-sample bound says the separation is present"
                         if failing else
                         "reproduce in a fresh process, then test whether the same cell holds "
                         "outside the crypto slice"),
        "notAPromotion": "a passing verdict is a candidate for reproduction, never a GO",
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\n{'year':<6}{'acc':>9}{'majority':>10}{'margin':>10}{'control':>10}{'steps':>8}")
    for f in folds:
        print(f"{f['testYear']:<6}{f['accuracy']:>9.4f}{f['majority']:>10.4f}"
              f"{f['margin']:>+10.4f}{f['shuffledControlMargin']:>+10.4f}{f['steps']:>8}")
    print(f"\nmean margin {mean_margin:+.4f}   worst {worst_margin:+.4f} ({folds[int(np.argmin(margins))]['testYear']})"
          f"   won {won}/{len(folds)} (needed {need})")
    print(f"shuffled control mean {float(np.mean(controls)):+.4f}   "
          f"bootstrap p2.5 {p25}  p97.5 {boot.get('p97_5')}")
    if bound is not None:
        print(f"in-sample bound from signal_floor: {bound:+.4f}")
    print(f"\n{verdict}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
