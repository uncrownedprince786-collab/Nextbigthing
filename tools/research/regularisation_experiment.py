"""Does capacity control close the generalisation gap? L2 chosen by inner validation, test year untouched.

    python tools/research/regularisation_experiment.py [--inspect] [--out FILE]

**Pre-registered before any number from this run was seen.** The grid, the inner split, the
selection metric, the tie-break, the folds, the controls and the five acceptance criteria below
were fixed here first.

The question this settles
--------------------------
Eleven registered experiments have returned NO-GO, and between them they have exonerated the
label (`label60`, `horizon`), the band (`label_adequacy`, `volband`), the class balance
(`balanced`), the optimizer (`balanced`, and again in `binary_context` where every fold converged
in 1,016-2,016 steps against a 20,000 ceiling), and the feature count (`signal_floor` measured the
separation in-sample). What none of them has ever varied is the model's **capacity**: every run
used the same `L2 = 1e-4` and `LR = 0.5` with no regularisation choice at all.

`binary_context_experiment` then quantified the gap the diagnosis had only asserted: an in-sample
bound of **+0.0361** against an out-of-sample mean of **-0.0527**. Separation present when the
model may memorise, absent when it may not, is the textbook signature of under-regularisation. It
is the one remaining explanation that no run has tested.

**Which cell is tested.** The binary UP-vs-DOWN target on all 44 features -- not the shipped
three-class target -- because `signal_floor` measured that cell's in-sample separation at +0.0361
against +0.0037 for the three-class/15 cell. Regularising a target that shows almost no
in-sample separation cannot tell capacity from absence; the cell with the headroom can. The
fixed-`L2` result for this exact cell is `binary_context_experiment.json`, and it is read at run
time as the thing this run must beat.

How the choice is made without touching the test year
------------------------------------------------------
Selecting `L2` by test-year performance would be tuning against the holdout, which is the mistake
this project keeps testing for. So the choice is made **inside each training window only**:

1. The training window's **rows**, in date order, are split 80/20: the last 20% become the inner
   validation block. Splitting by row rather than by unique date matters on this slice -- row
   density grows with the asset count, so a date split left the inner training block with 555
   rows while the fit it is meant to inform saw 66,390, and a penalty chosen for 555 rows is the
   wrong penalty for 66,390. `--inspect` printed that imbalance before anything was fitted.
2. The inner training block ends `EMBARGO` (20) decision dates before that block begins, because
   the labels overlap. The embargo is still counted in decision dates, which is what the overlap
   requires; the rows in between are dropped.
3. Every grid value is fitted on the inner training block and scored on the inner validation
   block, and the score is the **margin over the inner validation majority** -- the same quantity
   the outer criterion uses, so the selection optimises generalisation rather than raw accuracy.
4. **Tie-break, fixed in advance:** among every grid value within **0.002** of the best inner
   margin, the **largest** `L2` wins. When the evidence cannot separate two settings, the more
   regularised one is taken.
5. The winner is refitted on the **whole** training window and scores the test year exactly once.

The grid is fixed and small, deliberately: `[1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0]`. It spans four
orders of magnitude from the setting every prior run used (the first entry, so "no change" is
always a legal outcome of the selection) up to a penalty strong enough to flatten the fit.

Held identical from `binary_context_experiment`
-----------------------------------------------
`.cache/foundation/crypto_slice.npz` (sha256 recorded), `keep = y != FLAT`, all 44
`ALL_FEATURES`, `baseline_experiment`'s fold rule (2021-2026, `EMBARGO` 20, min 5,000/500),
training-fold-only imputation and standardisation, `fit_weighted` imported from `balanced_experiment`
(TOL 1e-6, MAX_STEPS 20,000, only `l2` varying), `SEED = 20261015`,
`over_majority` and `block_bootstrap` from `stationarity`, the shuffled-label control, and a
weight matrix built for the two classes this target actually has (`classes=BINARY_CLASSES`).

Correction this version exists for (v1 -> v2)
----------------------------------------------
`regularisation-v1`, like `binary-context-v1` and `eligible-set-v1`, fitted this two-class target
with **three output columns**, because `fit_weighted` sized its matrix from `len(CLASSES)` == 3,
and its `predictedMix`/`actualMix` indexed into `CLASSES`, so binary index 1 -- the positive class
-- was written out as `FLAT` and `UP` as 0 on every fold. v2 builds two columns named
`["DOWN", "UP"]` and reports both mixes through `class_counts` against those names. The grid,
inner split, tie-break, seed, controls, criteria and thresholds are unchanged, and
`regularisation_experiment.json` (v1) is preserved untouched on disk.

**Exposure, stated plainly:** these calendar years were previously examined by v1, so a corrected
run re-measures an already-observed holdout rather than producing fresh independent evidence, and
no threshold moves after any metric is seen.

Acceptance, fixed before the run
---------------------------------
The **same five criteria as `binary_context_experiment`**, so the two runs are comparable and the
predecessor is not judged by a different bar:

* **C1** mean margin over scored folds > 0.
* **C2** folds beating their own majority >= `min(MIN_FOLDS_WON, foldsScored)`, `MIN_FOLDS_WON = 4`
  imported unchanged.
* **C3** no degenerate fold: one class predicted on more than `DEGENERATE_SHARE` (0.70) of a
  fold's test rows while actually under half of them.
* **C4** the block-bootstrap 95% interval for (candidate margin - shuffled-control margin) has
  `p2_5 > 0`.
* **C5** the worst fold's margin >= -0.05.

**Improvement over the predecessor is reported but is not a pass criterion.** A run that improves
on `-0.0527` and still fails C1 has still failed; a run that passes all five does so on the five.

If selection consistently picks the smallest `L2`, that is a finding in itself: capacity control
does not explain the gap, and the next question is the eligible set rather than the model. It does
**not** by itself establish that the linear family is exhausted -- that claim has to be judged
against a fit whose output dimension matches its target, which is what v2 corrects.

Fidelity limitations, declared in advance
------------------------------------------
Identical to the predecessor: no `dataQuality` mask in the cache so quarantine cannot be
reproduced; crypto only. One addition -- the 2021
fold's inner *training* block is the smallest in the run, because the slice held few assets early
and row density grows over time, so its selected `L2` is the least reliable choice in the run; it
is reported per fold for exactly that reason.

Nothing here is a promotion. A passing verdict means capacity control is worth reproducing in a
fresh process, and nothing more.
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

from baseline_experiment import CLASSES, EMBARGO, LR, REGIMES, SEED, predict  # noqa: E402
from balanced_experiment import (  # noqa: E402
    DEGENERATE_SHARE,
    MAX_STEPS,
    MIN_FOLDS_WON,
    class_counts,
    fit_weighted,
)
from stationarity import BLOCK_DAYS, BOOTSTRAP, block_bootstrap, over_majority  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

CACHE = ROOT / ".cache" / "foundation" / "crypto_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "regularisation_experiment_v2.json"
PREDECESSOR = ROOT / "data" / "foundation" / "dataset" / "binary_context_experiment_v2.json"
PREDECESSOR_V1 = ROOT / "data" / "foundation" / "dataset" / "binary_context_experiment.json"

VERSION = "regularisation-v2"
L2_GRID = [1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0]
INNER_VAL_SHARE = 0.20
TIE_BREAK_MARGIN = 0.002
MIN_TRAIN, MIN_TEST = 5000, 500
WORST_FOLD_FLOOR = -0.05
REGIME_MIN_ROWS, REGIME_LOSS = 1000, -0.05
# Indices into the *cache's* three-class labels, used only to read rows out of it.
FLAT, UP = CLASSES.index("FLAT"), CLASSES.index("UP")
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


def class_weights(ytr: np.ndarray) -> np.ndarray:
    counts = np.bincount(ytr, minlength=2).astype(float)
    n = len(ytr)
    return np.asarray([n / (2 * counts[0]), n / (2 * counts[1])])


def fit_score(Ztr, ytr, Zte, yte, l2: float, seed: int = SEED):
    """One fit at one `l2`. Returns the predictions and the honest numbers behind them.

    Every caller here passes the two-class target, so the fit is built two-wide
    (`classes=BINARY_CLASSES`). v1 called `fit_weighted` without that argument and trained three
    columns on labels {0,1}; this version corrects the width, nothing else.
    """
    W, steps, loss = fit_weighted(Ztr, ytr, class_weights(ytr), l2=l2, seed=seed,
                                  classes=BINARY_CLASSES)
    if W.shape != (Ztr.shape[1] + 1, N_BINARY):
        raise SystemExit(f"expected {(Ztr.shape[1] + 1, N_BINARY)}, got {W.shape}")
    yp = predict(W, Zte)
    if yp.min() < 0 or yp.max() >= N_BINARY:
        raise SystemExit(f"prediction outside {BINARY_CLASSES}: {yp.min()}..{yp.max()}")
    acc, maj, over = over_majority(yte, yp)
    return yp, {"accuracy": acc, "majority": maj, "margin": over,
                "steps": int(steps), "converged": bool(steps < MAX_STEPS),
                "finalLoss": round(loss, 6)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--inspect", action="store_true",
                    help="print the data, the grid and the inner-split plan; fit nothing")
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
    # FLAT is DOWN, so the label array and BINARY_CLASSES cannot drift apart.
    yb = np.where(y[keep] == UP, BINARY_UP, BINARY_DOWN).astype(np.int64)
    Xb, db = X[keep], dates[keep]
    assert set(np.unique(yb).tolist()) <= {BINARY_DOWN, BINARY_UP}
    print(f"rows after dropping FLAT: {len(Xb):,}   UP {yb.mean():.4f} / "
          f"DOWN {1 - yb.mean():.4f}")
    print(f"grid (fixed before the run): {L2_GRID}   "
          f"selection: inner margin, tie-break to the largest L2 within {TIE_BREAK_MARGIN}")

    order = np.argsort(db, kind="stable")
    Xb, yb, db = Xb[order], yb[order], db[order]

    if a.inspect:
        udates = np.unique(db)
        didx = {d: i for i, d in enumerate(udates)}
        pos = np.asarray([didx[d] for d in db])
        print("\nfold plan and its inner split (nothing fitted, nothing written):")
        for cut_year in range(2021, 2027):
            cut = f"{cut_year}-01-01"
            cand = [d for d in udates if d >= cut]
            if not cand:
                continue
            cut_pos = didx.get(cut, didx[cand[0]])
            tr = pos < (cut_pos - EMBARGO)
            te = (db >= cut) & (db <= f"{cut_year}-12-31")
            fits = tr.sum() >= MIN_TRAIN and te.sum() >= MIN_TEST
            if not fits:
                print(f"  {cut_year}: SKIPPED (train {tr.sum():,} test {te.sum():,})")
                continue
            dtr = db[tr]
            utr = np.unique(dtr)
            ipos = np.searchsorted(utr, dtr)
            row_split = int(len(dtr) * (1 - INNER_VAL_SHARE))
            sd_idx = int(np.searchsorted(utr, dtr[row_split]))
            itr_end = max(sd_idx - EMBARGO, 1)
            itr = ipos < itr_end
            iva = ipos >= sd_idx
            print(f"  {cut_year}: train {tr.sum():>6,} test {te.sum():>5,}  "
                  f"inner-train {itr.sum():>6,} (ends {utr[itr_end - 1]})  "
                  f"inner-val {iva.sum():>5,} (from {utr[sd_idx]})  "
                  f"embargo {itr_end and sd_idx - itr_end} date(s) dropped")
        return 0

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

        Xtr, Xte, dtr = Xb[tr], Xb[te], db[tr]
        mu = np.nanmean(Xtr, axis=0)
        mu = np.where(np.isnan(mu), 0.0, mu)
        Xtr = np.where(np.isnan(Xtr), mu, Xtr)
        Xte = np.where(np.isnan(Xte), mu, Xte)
        sd = Xtr.std(axis=0)
        sd[sd == 0] = 1.0
        Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd

        # --- the choice, made entirely inside the training window -------------------------
        # Split by ROW quantile, not by unique-date quantile: the slice's row density grows with
        # the asset count, so a date split would leave the inner training block with a few hundred
        # rows while the fit it is meant to inform sees tens of thousands. The embargo is still
        # measured in decision dates, because that is what the overlapping labels require.
        utr = np.unique(dtr)
        ipos = np.searchsorted(utr, dtr)
        row_split = int(len(dtr) * (1 - INNER_VAL_SHARE))
        sd_idx = int(np.searchsorted(utr, dtr[row_split]))
        itr_end = max(sd_idx - EMBARGO, 1)
        itr = ipos < itr_end
        iva = ipos >= sd_idx
        sweep = []
        for l2 in L2_GRID:
            _, r = fit_score(Ztr[itr], yb[tr][itr], Ztr[iva], yb[tr][iva], l2,
                             seed=SEED + 100)
            sweep.append({"l2": l2, **r})
        best = max(s["margin"] for s in sweep)
        eligible = [s for s in sweep if s["margin"] >= best - TIE_BREAK_MARGIN]
        chosen = max(eligible, key=lambda s: s["l2"])
        l2_chosen = chosen["l2"]

        yp, cand = fit_score(Ztr, yb[tr], Zte, yb[te], l2_chosen)
        rng = np.random.default_rng(SEED + 1000 + cut_year)
        yc, ctrl = fit_score(Ztr, rng.permutation(yb[tr]), Zte, yb[te], l2_chosen,
                             seed=SEED + 500)

        pred_mix = np.bincount(yp, minlength=N_BINARY) / len(yp)
        act_mix = np.bincount(yb[te], minlength=N_BINARY) / len(yb[te])
        worst_i = int(pred_mix.argmax())
        degenerate = bool(pred_mix[worst_i] > DEGENERATE_SHARE and act_mix[worst_i] < 0.5)

        fold = {"testYear": cut_year, "trainRows": int(tr.sum()), "testRows": int(te.sum()),
                "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
                "testBegins": str(db[te][0]), "testEnds": str(db[te][-1]),
                "innerSplit": {"validationShare": INNER_VAL_SHARE,
                               "splitBy": "training-row quantile; embargo measured in decision "
                                          "dates, because the labels overlap",
                               "innerTrainRows": int(itr.sum()),
                               "innerValRows": int(iva.sum()),
                               "innerTrainEnds": str(utr[itr_end - 1]),
                               "innerValBegins": str(utr[sd_idx]),
                               "embargoDatesDropped": int(sd_idx - itr_end)},
                "sweep": sweep, "selectedL2": l2_chosen,
                "selectedBecause": (f"inner margin {chosen['margin']:+.4f} was within "
                                    f"{TIE_BREAK_MARGIN} of the best {best:+.4f}, and the "
                                    "largest such L2 is taken"),
                "unchangedFromPredecessor": bool(l2_chosen == L2_GRID[0]),
                "candidateAccuracy": cand["accuracy"],
                "candidateMajority": cand["majority"],
                "candidateMargin": cand["margin"],
                "candidateSteps": cand["steps"],
                "converged": cand["converged"],
                "finalLoss": cand["finalLoss"],
                "shuffledControlAccuracy": ctrl["accuracy"],
                "shuffledControlMargin": ctrl["margin"],
                "candidateMinusControl": round(cand["margin"] - ctrl["margin"], 4),
                "predictedMix": class_counts(yp, BINARY_CLASSES),
                "actualMix": class_counts(yb[te], BINARY_CLASSES),
                "worstPredictedShare": round(float(pred_mix[worst_i]), 4),
                "actualShareOfWorstPredicted": round(float(act_mix[worst_i]), 4),
                "degenerate": degenerate,
                "beatsMajority": bool(cand["margin"] > 0),
                "controlSteps": ctrl["steps"]}
        folds.append(fold)
        pool["y"].append(yb[te])
        pool["yp"].append(yp)
        pool["yc"].append(yc)
        pool["dates"].append(db[te])
        print(f"  fold {cut_year}: L2 {l2_chosen:g}  acc {cand['accuracy']:.4f}  "
              f"majority {cand['majority']:.4f}  margin {cand['margin']:+.4f}  "
              f"control {ctrl['margin']:+.4f}  steps {cand['steps']}"
              f"{'  DEGENERATE' if degenerate else ''}", flush=True)

    if not folds:
        raise SystemExit("no fold met the pre-declared minimums")

    y_all = np.concatenate(pool["y"])
    yp_all = np.concatenate(pool["yp"])
    yc_all = np.concatenate(pool["yc"])
    d_all = np.concatenate(pool["dates"])
    boot = block_bootstrap(d_all, y_all, yp_all, yc_all, np.random.default_rng(SEED + 77))

    won = sum(1 for f in folds if f["beatsMajority"])
    need = min(MIN_FOLDS_WON, len(folds))
    margins = [f["candidateMargin"] for f in folds]
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

    pred_mean, pred_mean_v1 = None, None
    if PREDECESSOR.exists():
        pj = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
        pred_mean = pj.get("summary", {}).get("meanMargin")
    if PREDECESSOR_V1.exists():
        pj1 = json.loads(PREDECESSOR_V1.read_text(encoding="utf-8"))
        pred_mean_v1 = pj1.get("summary", {}).get("meanMargin")

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

    chosen_l2s = [f["selectedL2"] for f in folds]
    qualified = [r["regime"] for r in regimes if r["qualification"]]
    if not failing:
        verdict = ("GO-CANDIDATE: capacity control chosen by inner validation clears every "
                   "criterion the fixed-L2 run failed. Worth reproducing in a fresh process; "
                   "not a promotion.")
    else:
        verdict = f"NO-GO: {', '.join(failing)} failed the criteria fixed before this run."
    if chosen_l2s.count(L2_GRID[0]) == len(chosen_l2s):
        verdict += (" Selection never left the smallest L2: capacity control does not explain "
                    "the gap.")
    if qualified:
        verdict += f" Qualification: adverse in {', '.join(qualified)}."

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": VERSION,
        "question": "is the generalisation failure under-regularisation?",
        "whyNotARerun": "no prior run varied capacity; every one used fixed L2=1e-4. This is the "
                        "same folds and target as binary_context_experiment with the penalty "
                        "selected inside the training window",
        "correctionOf": {
            "artifact": "regularisation_experiment.json",
            "version": "regularisation-v1",
            "preservedUnchanged": True,
            "defect": "regularisation-v1 fitted this two-class target with three output columns, "
                      "because fit_weighted sized its matrix from len(CLASSES) == 3, and its "
                      "predictedMix/actualMix indexed into CLASSES so binary index 1 -- the "
                      "positive class -- was written out as FLAT while UP was written as 0. The "
                      "same defect was in its predecessor, binary-context-v1.",
            "scope": "correctness repair of the output dimension and of the reported class names "
                     "only: grid, inner split, tie-break, seed, controls, criteria and thresholds "
                     "untouched.",
            "exposure": "these calendar years were previously examined by regularisation-v1, so a "
                        "corrected run here would re-measure an already-observed holdout rather "
                        "than produce fresh independent evidence. No threshold moves after any "
                        "metric is seen."},
        "data": {"cache": str(cache.relative_to(ROOT)) if cache.is_relative_to(ROOT) else str(cache),
                 "sha256": sha256(cache), "bytes": cache.stat().st_size,
                 "slice": "crypto", "rowsInCache": int(len(X)),
                 "rowsAfterDroppingFlat": int(len(Xb)),
                 "upShare": round(float(yb.mean()), 4),
                 "dateRange": [str(min(db)), str(max(db))],
                 "features": len(ALL_FEATURES)},
        "target": {"label": "binary UP vs DOWN, FLAT dropped", "up": 1, "down": 0,
                   "classes": list(BINARY_CLASSES),
                   "encodingNote": "BINARY_CLASSES[1] is UP and is reported as UP; the cache's "
                                   "three-class FLAT rows are dropped before encoding"},
        "selection": {"grid": L2_GRID, "innerValidationShare": INNER_VAL_SHARE,
                      "innerEmbargoDecisionDates": EMBARGO,
                      "metric": "margin over the inner validation majority",
                      "tieBreak": f"largest L2 within {TIE_BREAK_MARGIN} of the best inner margin",
                      "testYearTouched": "once, by the refitted winner only",
                      "selectedL2ByFold": {str(f["testYear"]): f["selectedL2"] for f in folds},
                      "selectedAtSmallest": sum(1 for v in chosen_l2s if v == L2_GRID[0]),
                      "ofFolds": len(folds)},
        "model": {"optimizer": "fit_weighted imported from balanced_experiment, called with "
                               "classes=BINARY_CLASSES so the matrix is built for two outputs",
                  "outputClasses": list(BINARY_CLASSES),
                  "outputDimension": N_BINARY,
                  "corrects": "regularisation-v1's three-column fit on a two-class target",
                  "learningRate": LR, "tolerance": 1e-6, "maxSteps": MAX_STEPS,
                  "convergedFolds": sum(1 for f in folds if f["converged"]),
                  "ofFolds": len(folds)},
        "protocol": {"folds": "baseline_experiment's rule: one fold per test year 2021..2026",
                     "embargoDecisionDates": EMBARGO, "seed": SEED,
                     "imputation": "training-fold column nan-mean",
                     "standardisation": "training-fold mean and standard deviation only",
                     "minTrainRows": MIN_TRAIN, "minTestRows": MIN_TEST,
                     "uncertainty": f"moving-block bootstrap over decision dates, {BLOCK_DAYS}-date "
                                    f"blocks, {BOOTSTRAP} resamples, candidate minus shuffled "
                                    "control",
                     "reference": "over_majority imported unchanged from stationarity"},
        "criteria": criteria,
        "criteriaSource": "the same five criteria binary_context_experiment declared, fixed in "
                          "this docstring before any number from this run was seen",
        "improvementMeasurement": {
            "predecessor": "binary_context_experiment_v2.json",
            "predecessorMeanMargin": pred_mean,
            "predecessorV1": "binary_context_experiment.json",
            "predecessorMeanMarginV1": pred_mean_v1,
            "thisMeanMargin": round(mean_margin, 4),
            "delta": (round(mean_margin - pred_mean, 4) if pred_mean is not None else None),
            "note": "reported, not a pass criterion: a run that improves and still fails C1 has "
                    "still failed"},
        "folds": folds,
        "summary": {"foldsScored": len(folds), "foldsWon": won, "foldsRequired": need,
                    "meanMargin": round(mean_margin, 4),
                    "meanShuffledControlMargin": round(float(np.mean(controls)), 4),
                    "worstFoldMargin": round(worst_margin, 4),
                    "worstFoldYear": int(folds[int(np.argmin(margins))]["testYear"]),
                    "degenerateFolds": degenerate_folds,
                    "anyFoldDegenerate": bool(degenerate_folds),
                    "pooledRows": int(len(y_all)),
                    "bootstrap": boot},
        "byRegime": regimes,
        "fidelityLimitations": [
            "the cache carries no dataQuality mask, so quarantine cannot be reproduced",
            "crypto only: one market, 93,452 rows in the cache",
            "the 2021 fold's inner training block is the smallest in the run, so its selected "
            "L2 is the least reliable choice; reported per fold for that reason"],
        "verdict": verdict,
        "failingCriteria": failing,
        "nextQuestion": ("if capacity control does not explain the gap either, the next question "
                         "stays the eligible set outside crypto -- and, separately, whether the "
                         "linear family itself is exhausted, which only a fit of the correct "
                         "output dimension can answer"
                         if failing else
                         "reproduce in a fresh process, then test the selected capacity on the "
                         "shipped three-class target"),
        "notAPromotion": "a passing verdict is a candidate for reproduction, never a GO",
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\n{'year':<6}{'L2':>9}{'acc':>9}{'majority':>10}{'margin':>10}{'control':>10}{'steps':>8}")
    for f in folds:
        print(f"{f['testYear']:<6}{f['selectedL2']:>9g}{f['candidateAccuracy']:>9.4f}"
              f"{f['candidateMajority']:>10.4f}{f['candidateMargin']:>+10.4f}"
              f"{f['shuffledControlMargin']:>+10.4f}{f['candidateSteps']:>8}")
    print(f"\nselected L2 per fold: {chosen_l2s}")
    print(f"mean margin {mean_margin:+.4f}   worst {worst_margin:+.4f}   won {won}/{len(folds)}"
          f" (needed {need})")
    if pred_mean is not None:
        print(f"predecessor (fixed L2=1e-4) mean {pred_mean:+.4f}   delta {mean_margin - pred_mean:+.4f}")
    print(f"bootstrap p2.5 {p25}  p97.5 {boot.get('p97_5')}")
    print(f"\n{verdict}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
