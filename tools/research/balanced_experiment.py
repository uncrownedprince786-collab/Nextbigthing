"""The diagnosed candidate: class-balanced and trained to convergence, measured once.

    python tools/research/balanced_experiment.py [--dataset DIR] [--out FILE]

**Pre-registered in full before any result was seen. Run once.** Nothing below is chosen after
looking at an outcome, and the earlier results are not touched: `baseline_experiment.json`
(0.4211 against a 0.4204 majority class) and `label60_experiment.json` (mean margin -0.0816) stay
exactly as they were measured.

**Why another candidate is justified at all.** Not because the last one failed -- that is the
reason *not* to re-run something. `experiment_diagnosis.json` measured *how* it failed, from its own
recorded prediction mixes: it called UP on 78.5% of rows where 41.1% actually were, and FLAT on 3.6%
where 19.7% were, and its accuracy tracks each test year's UP base rate to a mean absolute 0.0215.
That is a near-constant predictor, and it gives an independent, falsifiable hypothesis:

> The recorded 0.4211 measures an optimiser that collapsed to one class, not the information in the
> features. Remove the two mechanisms that cause the collapse and the measured accuracy will change.

It is falsifiable in the direction that matters: if accuracy stays at the base rate with the
collapse removed, the features carry no edge and that is the answer, not a reason for a third
attempt.

**The two mechanisms, and the two changes. Nothing else moves.**

1. *The middle class is never predicted.* Three classes with a FLAT band holding a fifth of the
   rows, trained under an unweighted softmax: the cheapest descent is toward the largest class, and
   FLAT lies between the other two in feature space. Fixed with class weights inversely proportional
   to **training-fold** class frequency -- never the test fold's, which would be leakage.
2. *It may never have converged.* 400 full-batch steps at a fixed rate was a number chosen before
   any loss curve was seen. Fixed by training until the relative change in training loss falls below
   `TOL`, with a hard cap, and by **recording the step count and the final loss** so convergence is
   evidence in the artifact rather than an assumption in a comment.

Everything else is held identical to the baseline so the comparison is like-for-like: the same 15
`pit.f` features, the same chronological walk-forward with one fold per test year, the same
20-session embargo, the same training-fold standardisation, the same seed, and `load()` imported
from `baseline_experiment.py` rather than restated so row selection and feature handling cannot
drift.

**The reference.** For a three-class accuracy the best single fixed answer *is* the majority class,
so that is the bar, computed on exactly the test rows. The recorded candidate's 0.4211 is reported
beside it for context and is not a bar -- beating a degenerate predictor is not evidence.

**Pre-declared acceptance. All three, or NO-GO.**

* mean accuracy strictly above the mean majority-class reference;
* beats its own fold's majority class in **more than half** the folds (4 of 6);
* **does not degrade in the adverse regime** -- the 2022 fold, which is the §9 clause both earlier
  candidates actually failed.

**And a degeneracy guard, which no accuracy number can substitute for.** A candidate that predicts
one class on more than `DEGENERATE_SHARE` of rows while that class is actually under half of them is
recorded as degenerate **whatever it scores**, because that is the defect this candidate exists to
remove and it must not be able to pass by reproducing it.

Exposure, stated plainly: these calendar years were already exposed by the earlier candidate, so
this is not a pristine out-of-sample measurement. 2026 is reported separately as the least-exposed
fold. No design choice here was made against any of them.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baseline_experiment import (  # noqa: E402
    CLASSES,
    EMBARGO,
    FEATURES,
    L2,
    LR,
    SEED,
    load,
    metrics,
    predict,
)

# Convergence, not a step count: stop when the training loss stops moving.
TOL = 1e-6
MAX_STEPS = 20_000
# Pre-declared acceptance.
MIN_FOLDS_WON = 4
# A class predicted on more than this share of rows, while actually under half, is degenerate.
DEGENERATE_SHARE = 0.70
ADVERSE_FOLD = 2022


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def fit_weighted(Xtr, ytr, weights, lr=LR, l2=L2, seed=SEED, tol=TOL, max_steps=MAX_STEPS,
                 classes=None):
    """Full-batch softmax with per-class weights, trained until the loss stops moving.

    Returns the weights, the step count reached and the final loss, so the artifact can show that
    the fit converged rather than asserting it.

    `classes` fixes the output width and defaults to the three-class `CLASSES`, which is the path
    this experiment was written for and is byte-for-byte the same fit as before the parameter
    existed. A caller whose target is binary must pass its own two names: fitting {0,1} labels with
    three columns trains an extra logit that never receives a target, and that is a different model
    from the one the labels describe.
    """
    rng = np.random.default_rng(seed)
    n, d = Xtr.shape
    k = len(CLASSES) if classes is None else len(classes)
    labels = np.asarray(ytr)
    if labels.size and (labels.min() < 0 or labels.max() >= k):
        raise ValueError(f"label outside the {k} output classes: "
                         f"range {labels.min()}..{labels.max()}")
    W = rng.normal(0, 0.01, size=(d + 1, k))
    Xb = np.hstack([Xtr, np.ones((n, 1))])
    Y = np.zeros((n, k))
    Y[np.arange(n), labels] = 1.0
    # One weight per row, from its own class. Normalised to mean 1 so the learning rate keeps its
    # meaning and `l2` is not effectively rescaled by the class balance.
    w = np.asarray(weights, dtype=np.float64)[labels]
    w = w / w.mean()
    wcol = w[:, None]

    previous = np.inf
    steps = 0
    loss = np.inf
    for steps in range(1, max_steps + 1):
        z = Xb @ W
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        p = e / e.sum(axis=1, keepdims=True)
        loss = float(-(w * np.log((p * Y).sum(axis=1) + 1e-12)).sum() / w.sum() + l2 * np.sum(W * W) / 2)
        g = Xb.T @ ((p - Y) * wcol) / w.sum() + l2 * W
        W -= lr * g
        if previous - loss < tol * max(1.0, abs(previous)):
            break
        previous = loss
    return W, steps, loss


def class_counts(values, classes) -> dict:
    """How many of `values` fall in each of `classes`, named by those classes, in order.

    The saved `actualMix` and `predictedMix` of every binary run went through `CLASSES` instead,
    so a target encoded {0,1} had its positive class written out as `FLAT` and its real `UP` count
    written as 0 on every fold. The range check is the guard: a label that no name in `classes`
    covers is an error here, never a silently mis-named bucket.
    """
    v = np.asarray(values)
    if v.size and (v.min() < 0 or v.max() >= len(classes)):
        raise ValueError(f"value outside {list(classes)}: range {v.min()}..{v.max()}")
    return {c: int((v == i).sum()) for i, c in enumerate(classes)}


def majority_accuracy(y: np.ndarray) -> float:
    """The best single fixed answer on exactly these rows."""
    return float(np.bincount(y, minlength=len(CLASSES)).max() / len(y)) if len(y) else 0.0


def main() -> int:
    ds = Path(arg("--dataset") or (ROOT / ".cache" / "foundation" / "dataset_full"))
    out = Path(arg("--out") or (ROOT / "data" / "foundation" / "dataset" / "balanced_experiment.json"))
    freeze_path = ROOT / "data" / "foundation" / "dataset" / "dataset_freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8")) if freeze_path.exists() else {}

    print("loading dataset ...", flush=True)
    t0 = time.time()
    X, y, dates, cls, flags = load(ds)
    print(f"  {len(X):,} rows in {time.time() - t0:.0f}s", flush=True)

    # Quarantine, for the reason the assembly records it: a window crossing an unadjusted corporate
    # action carries a move no holder experienced. Excluded from every arm equally.
    keep = ~flags
    X, y, dates, cls = X[keep], y[keep], dates[keep], cls[keep]
    print(f"  {len(X):,} rows after quarantine", flush=True)

    udates = np.unique(dates)
    folds = []
    for year in range(2021, 2027):
        cut = f"{year}-01-01"
        cut_pos = int(np.searchsorted(udates, cut))
        pos = np.searchsorted(udates, dates)
        tr = pos < (cut_pos - EMBARGO)
        te = (dates >= cut) & (dates <= f"{year}-12-31")
        if tr.sum() < 1000 or te.sum() < 100:
            continue

        mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
        sd[sd == 0] = 1.0
        Xtr, Xte = (X[tr] - mu) / sd, (X[te] - mu) / sd

        # Class weights from the TRAINING fold only.
        counts = np.bincount(y[tr], minlength=len(CLASSES)).astype(np.float64)
        counts[counts == 0] = 1.0
        weights = counts.sum() / (len(CLASSES) * counts)

        W, steps, loss = fit_weighted(Xtr, y[tr], weights)
        pred = predict(W, Xte)
        m = metrics(y[te], pred)
        maj = majority_accuracy(y[te])

        pm = {c: int((pred == i).sum()) for i, c in enumerate(CLASSES)}
        am = {c: int((y[te] == i).sum()) for i, c in enumerate(CLASSES)}
        n_te = int(te.sum())
        worst_share = max(pm.values()) / n_te
        worst_class = max(pm, key=lambda c: pm[c])
        degenerate = worst_share > DEGENERATE_SHARE and am[worst_class] / n_te < 0.5

        folds.append({
            "testYear": year,
            "trainRows": int(tr.sum()),
            "testRows": n_te,
            "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
            "embargoSessionsDropped": EMBARGO,
            "classWeights": {c: round(float(weights[i]), 4) for i, c in enumerate(CLASSES)},
            "stepsToConverge": steps,
            "finalTrainingLoss": round(loss, 6),
            "converged": steps < MAX_STEPS,
            "accuracy": m["accuracy"],
            "majorityClassAccuracy": round(maj, 4),
            "margin": round(m["accuracy"] - maj, 4),
            "beatsMajority": m["accuracy"] > maj,
            "predictedMix": pm,
            "actualMix": am,
            "largestPredictedShare": round(worst_share, 4),
            "degenerate": bool(degenerate),
            "recall": {c: m.get(f"recall_{c}") for c in CLASSES},
            "precision": {c: m.get(f"precision_{c}") for c in CLASSES},
        })
        print(f"  fold {year}: acc {m['accuracy']} · majority {maj:.4f} · margin {m['accuracy'] - maj:+.4f} "
              f"· {steps} steps · largest predicted share {worst_share:.3f}", flush=True)

    mean = lambda k: round(float(np.mean([f[k] for f in folds])), 4)  # noqa: E731
    won = sum(1 for f in folds if f["beatsMajority"])
    adverse = next((f for f in folds if f["testYear"] == ADVERSE_FOLD), None)
    any_degenerate = any(f["degenerate"] for f in folds)

    criteria = {
        "meanAccuracyAboveMajority": [mean("accuracy"), mean("majorityClassAccuracy"),
                                      mean("accuracy") > mean("majorityClassAccuracy")],
        "foldsBeatingTheirOwnMajority": [won, MIN_FOLDS_WON, won >= MIN_FOLDS_WON],
        "doesNotDegradeInTheAdverseRegime": [
            adverse["margin"] if adverse else None, 0.0,
            bool(adverse and adverse["margin"] >= 0)],
        "notDegenerate": [any_degenerate, False, not any_degenerate],
    }
    ok = all(v[2] for v in criteria.values())

    report = {
        "version": "balanced-experiment-v1",
        "status": "offline research experiment; nothing deployed, nothing traded",
        "hypothesis": ("the recorded 0.4211 measures an optimiser that collapsed to one class, not the "
                       "information in the features; removing the collapse will change the measured accuracy"),
        "changesFromTheBaseline": [
            "class weights inversely proportional to TRAINING-fold class frequency",
            "trained to convergence on the training loss instead of a fixed 400 steps, with the step "
            "count and final loss recorded as evidence",
        ],
        "heldIdentical": [
            "the same 15 pit.f features", "the same chronological walk-forward, one fold per test year",
            "the same 20-session embargo", "training-fold standardisation", "the same seed",
            "row selection and feature handling, by importing load() from baseline_experiment.py",
        ],
        "dataVersion": {
            "dataset": freeze.get("version", "unknown"),
            "frozenAt": freeze.get("frozenAt"),
            "blockingGatesGreen": freeze.get("blockingGatesGreen"),
            "rowsWithFeatures": (freeze.get("rows") or {}).get("withPointInTimeFeatures"),
            "repoHead": freeze.get("repoHead"),
        },
        "config": {"model": "multinomial logistic regression, numpy, full batch, class-weighted",
                   "seed": SEED, "learningRate": LR, "l2": L2, "tolerance": TOL, "maxSteps": MAX_STEPS,
                   "embargoSessions": EMBARGO, "features": FEATURES},
        "exposure": ("these calendar years were already exposed by the earlier candidate, so this is not "
                     "a pristine out-of-sample measurement; 2026 is the least-exposed fold and is reported "
                     "separately. No design choice here was made against any fold."),
        "preDeclaredCriteria": {
            "meanAccuracyAboveMajority": "strictly above",
            "foldsBeatingTheirOwnMajority": MIN_FOLDS_WON,
            "adverseRegimeFold": ADVERSE_FOLD,
            "degeneracyGuard": f"no class predicted on more than {DEGENERATE_SHARE} of rows while actually under half",
            "setBefore": "any result was seen",
        },
        "folds": folds,
        "leastExposedFold": next((f for f in folds if f["testYear"] == 2026), None),
        "summary": {
            "folds": len(folds),
            "meanAccuracy": mean("accuracy"),
            "meanMajorityClassAccuracy": mean("majorityClassAccuracy"),
            "meanMargin": mean("margin"),
            "foldsBeatingMajority": won,
            "meanStepsToConverge": mean("stepsToConverge"),
            "anyFoldDegenerate": any_degenerate,
            "recordedBaselineForContext": 0.4211,
        },
        "criteriaMet": criteria,
        "verdict": "GO" if ok else "NO-GO",
    }

    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "criteriaMet": criteria,
                      "verdict": report["verdict"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
