"""Does macro context improve decision quality, when it is never allowed to pick a side?

    python tools/research/context_experiment.py [--dataset DIR] [--macro DIR] [--out DIR]

**Pre-registered before any result was seen.** Everything below -- the features, the folds, the
controls and the three numbers that decide it -- is fixed here and nothing in it is chosen after
looking at an outcome. The position-horizon result (`label60`, mean margin -0.0816) is a separate,
frozen experiment and is not re-run, re-tuned or referred to for a threshold.

**What is being asked.** `data/foundation/dataset/context_routing.json` gives the macro layer the
roles `decision-context` and `integrity-veto`, and `mayVote: false`. So the question cannot be
"does macro predict direction" -- it is not allowed to, and a market-wide series handed to 616
instruments as a per-asset feature is one fact counted 616 times (brain.md rule 156). The question
is the one its role permits: given a direction the approved features already produced, does macro
context tell us *when to act on it*?

**The candidate.** Two stages, and the macro stage can only ever withhold.

1. *Direction* comes from the baseline candidate model, imported from
   `tools/research/baseline_experiment.py` rather than restated -- same 15 `pit.f` features, same
   seed, same steps, same L2, same training-fold standardisation. Importing it is deliberate: a
   copy here could drift into a re-tuned base and read as context having helped.
2. *Qualification* is a second logistic model trained on macro context **only**, whose target is
   whether stage one's call was correct. It outputs a confidence; calls below a threshold are
   withheld. It never sees a price feature and never emits a direction, so no arrangement of its
   output can change UP into DOWN.

**Macro features: `chg` only, never levels.** One value per session, joined on date, so the state
is shared by every asset on that date and is not counted once per name. Levels are excluded because
most of these series trend -- a CPI index level is a proxy for the date, and a model given it can
learn the calendar and call it macro. The artifact is the rebuilt, verified one; the invalidated
file pairs a later revision with an earlier availability date and would make this read as context
having helped when what helped was hindsight.

**Controls, because filtering changes accuracy on its own.** Withholding the hard half of anything
raises accuracy on what is left, so the candidate is not compared against "no filter" alone:

* *coverage-matched random* -- withholds the same number of calls per fold at random, seeded. This
  is the control that matters. Beating it is the only evidence that *which* calls were withheld
  carried information.
* *no filter* -- stage one at full coverage, the honest status quo.
* *majority class on the retained rows* -- always predicting the commonest class among what was
  kept, which a filter can inflate by keeping an easy subset.

**Pre-declared criteria. All three, or it is a NO-GO.**

* mean accuracy on retained calls at least **+0.02** above the coverage-matched random control;
* the candidate beats that control in at least **5 of 6** folds;
* retained coverage at least **50%** -- a filter that keeps a handful of calls is not a decision
  system, however accurate it looks.

Chronological throughout: one fold per test year 2021..2026, training on everything before the cut
less a 20-session embargo, because a 20-session label makes consecutive rows share 19 of their 20
forward sessions. The macro qualifier is fitted on training folds only and its threshold is taken
from the training fold's own distribution, never from the test year.
"""

from __future__ import annotations

import gzip
import json
import sys
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
    STEPS,
    fit_softmax,
    load,
    predict,
)

# The share of training-fold calls the qualifier is asked to withhold. Fixed here, not searched:
# the experiment is whether *which* calls are withheld carries information, and tuning the amount
# against the test years would answer a different and easier question.
WITHHOLD_SHARE = 0.30

# Pre-declared, before any result was seen.
MIN_GAIN_OVER_RANDOM = 0.02
MIN_FOLDS_WON = 5
MIN_COVERAGE = 0.50


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def macro_by_date(macro_dir: Path) -> tuple[dict[str, dict[str, float]], list[str]]:
    """{session: {series: chg}} from the rebuilt artifact, and the series list in a fixed order.

    `chg` only. `v` is deliberately not read: see the module docstring -- a trending level is a
    proxy for the date.
    """
    path = macro_dir / "macro-sessions.jsonl.gz"
    rows: dict[str, dict[str, float]] = {}
    seen: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            state = {}
            for sid, cell in rec["m"].items():
                if "chg" in cell:
                    state[sid] = float(cell["chg"])
                    seen.add(sid)
            rows[rec["d"]] = state
    return rows, sorted(seen)


def macro_matrix(dates: np.ndarray, rows: dict[str, dict[str, float]], series: list[str]):
    """One row per example, carrying its session's macro state. Absent series are 0 and masked.

    A session with no macro row at all -- the artifact's grid comes from stored sessions, so a
    market trading on a day the grid does not hold is possible -- is marked unusable rather than
    given zeros, because zero is a real value for a change.
    """
    X = np.zeros((len(dates), len(series)), dtype=np.float64)
    have = np.zeros(len(dates), dtype=bool)
    for i, d in enumerate(dates):
        state = rows.get(str(d))
        if state is None:
            continue
        have[i] = True
        for j, sid in enumerate(series):
            v = state.get(sid)
            if v is not None:
                X[i, j] = v
    return X, have


def standardise(train: np.ndarray, *others: np.ndarray):
    mu = train.mean(axis=0)
    sd = train.std(axis=0)
    sd[sd == 0] = 1.0
    return [(a - mu) / sd for a in (train, *others)]


def confidence(W, X) -> np.ndarray:
    """P(stage one was right), from the qualifier's two-class output."""
    z = np.hstack([X, np.ones((len(X), 1))]) @ W
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return (e / e.sum(axis=1, keepdims=True))[:, 1]


def main() -> int:
    ds = Path(arg("--dataset") or (ROOT / ".cache" / "foundation" / "assembled_test"))
    macro_dir = Path(arg("--macro") or (ROOT / ".cache" / "foundation" / "macro_rebuild"))
    out = Path(arg("--out") or (ROOT / "data" / "foundation" / "dataset"))
    out.mkdir(parents=True, exist_ok=True)

    print("loading dataset ...", flush=True)
    X, y, dates, cls, flags = load(ds)
    print(f"  {len(X):,} rows", flush=True)

    macro_rows, series = macro_by_date(macro_dir)
    macro_manifest = json.loads((macro_dir / "manifest.json").read_text(encoding="utf-8"))
    M, have_macro = macro_matrix(dates, macro_rows, series)
    print(f"  macro: {len(series)} series with a change, {int(have_macro.sum()):,} rows joined "
          f"({have_macro.mean():.1%})", flush=True)

    # Quarantine, for the reason assemble.py records it: a window crossing an unadjusted corporate
    # action carries a move no holder experienced. Excluded from every arm equally.
    keep = ~flags & have_macro
    X, y, dates, cls, M = X[keep], y[keep], dates[keep], cls[keep], M[keep]
    print(f"  {len(X):,} rows after quarantine and the macro join", flush=True)

    udates = np.unique(dates)
    rng = np.random.default_rng(SEED)
    folds = []

    for cut_year in range(2021, 2027):
        cut = f"{cut_year}-01-01"
        cut_pos = int(np.searchsorted(udates, cut))
        pos = np.searchsorted(udates, dates)
        tr = pos < (cut_pos - EMBARGO)
        te = (dates >= cut) & (dates <= f"{cut_year}-12-31")
        if tr.sum() < 1000 or te.sum() < 100:
            continue

        # --- stage one: direction, from the approved features only ---------------------------
        Xtr, Xte = standardise(X[tr], X[te])
        W = fit_softmax(Xtr, y[tr], steps=STEPS, lr=LR, l2=L2, seed=SEED)
        pred_tr, pred_te = predict(W, Xtr), predict(W, Xte)
        right_tr = (pred_tr == y[tr]).astype(np.int64)
        right_te = (pred_te == y[te])

        # --- stage two: qualification, from macro context only ---------------------------------
        Mtr, Mte = standardise(M[tr], M[te])
        Q = fit_softmax(Mtr, right_tr, steps=STEPS, lr=LR, l2=L2, seed=SEED + 1)
        conf_tr = confidence(Q, Mtr)
        conf_te = confidence(Q, Mte)
        # The threshold comes from the training fold's own distribution, never the test year.
        threshold = float(np.quantile(conf_tr, WITHHOLD_SHARE))
        acted = conf_te >= threshold

        n_te = int(te.sum())
        n_acted = int(acted.sum())
        coverage = n_acted / n_te if n_te else 0.0

        # --- the controls ----------------------------------------------------------------------
        # Coverage-matched random: the same number of calls withheld, chosen at random.
        idx = rng.permutation(n_te)[:n_acted]
        random_acted = np.zeros(n_te, dtype=bool)
        random_acted[idx] = True

        retained = y[te][acted]
        majority = 0.0
        if len(retained):
            counts = np.bincount(retained, minlength=len(CLASSES))
            majority = float(counts.max() / counts.sum())

        fold = {
            "testYear": cut_year,
            "trainRows": int(tr.sum()),
            "testRows": n_te,
            "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
            "embargoSessionsDropped": EMBARGO,
            "coverage": round(coverage, 4),
            "qualifierThreshold": round(threshold, 6),
            "candidateAccuracy": round(float(right_te[acted].mean()), 4) if n_acted else None,
            "randomControlAccuracy": round(float(right_te[random_acted].mean()), 4) if n_acted else None,
            "noFilterAccuracy": round(float(right_te.mean()), 4),
            "majorityClassOnRetained": round(majority, 4),
        }
        fold["candidateMinusRandom"] = (
            round(fold["candidateAccuracy"] - fold["randomControlAccuracy"], 4)
            if n_acted else None
        )
        folds.append(fold)
        print(f"  fold {cut_year}: coverage {coverage:.2%}  candidate {fold['candidateAccuracy']}  "
              f"random {fold['randomControlAccuracy']}  no-filter {fold['noFilterAccuracy']}", flush=True)

    scored = [f for f in folds if f["candidateMinusRandom"] is not None]
    mean_candidate = float(np.mean([f["candidateAccuracy"] for f in scored]))
    mean_random = float(np.mean([f["randomControlAccuracy"] for f in scored]))
    mean_nofilter = float(np.mean([f["noFilterAccuracy"] for f in scored]))
    mean_coverage = float(np.mean([f["coverage"] for f in scored]))
    gain = mean_candidate - mean_random
    won = int(sum(1 for f in scored if f["candidateMinusRandom"] > 0))

    passed = {
        "gainOverRandomAtLeast": [round(gain, 4), MIN_GAIN_OVER_RANDOM, gain >= MIN_GAIN_OVER_RANDOM],
        "foldsWonAtLeast": [won, MIN_FOLDS_WON, won >= MIN_FOLDS_WON],
        "coverageAtLeast": [round(mean_coverage, 4), MIN_COVERAGE, mean_coverage >= MIN_COVERAGE],
    }
    ok = all(v[2] for v in passed.values())

    report = {
        "version": "context-experiment-v1",
        "status": "offline research experiment; nothing deployed, nothing traded",
        "question": ("does macro context, which may never pick a side, improve decision quality by "
                     "telling us when to act on a direction the approved features already produced"),
        "policy": {
            "macroRole": "decision-context and integrity-veto; mayVote false (context_routing.json)",
            "howItIsHeldThere": ("the qualifier sees macro only, emits a confidence only, and can "
                                 "withhold a call but never change its direction"),
            "perAssetDuplication": ("avoided: macro is joined on date, so a market-wide series is one "
                                    "value per session and not one per name"),
            "levelsExcluded": "chg only; a trending level is a proxy for the date",
            "positionHorizonResult": "label60 mean margin -0.0816, frozen, not re-run and not re-tuned here",
        },
        "dataVersion": {
            "dataset": "examples-v3",
            "macroArtifactSha256": macro_manifest["sha256"],
            "macroSessions": macro_manifest["sessions"],
            "macroVerifiedBy": "tools/foundation/macro_pit_verify.py",
        },
        "config": {
            "directionModel": "imported from tools/research/baseline_experiment.py, unchanged",
            "features": FEATURES, "featureCount": len(FEATURES),
            "macroFeatures": series, "macroFeatureCount": len(series),
            "seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2,
            "embargoSessions": EMBARGO, "withholdShare": WITHHOLD_SHARE,
            "thresholdFrom": "the training fold's own confidence distribution",
        },
        "preDeclaredCriteria": {
            "gainOverCoverageMatchedRandom": MIN_GAIN_OVER_RANDOM,
            "foldsWonOfSix": MIN_FOLDS_WON,
            "minimumCoverage": MIN_COVERAGE,
            "setBefore": "any result was seen",
        },
        "folds": folds,
        "summary": {
            "folds": len(scored),
            "meanCoverage": round(mean_coverage, 4),
            "candidateMeanAccuracy": round(mean_candidate, 4),
            "coverageMatchedRandomMeanAccuracy": round(mean_random, 4),
            "noFilterMeanAccuracy": round(mean_nofilter, 4),
            "candidateMinusRandom": round(gain, 4),
            "foldsWon": won,
        },
        "criteriaMet": passed,
        "verdict": "GO" if ok else "NO-GO",
        "statement": (
            f"NO DEMONSTRATED EDGE. Withholding the calls the macro qualifier was least confident in "
            f"scores {mean_candidate:.4f} on the {mean_coverage:.1%} of calls it kept, against "
            f"{mean_random:.4f} for withholding the same number at random -- a difference of "
            f"{gain:+.4f} where {MIN_GAIN_OVER_RANDOM} was required, and it wins {won} folds of "
            f"{len(scored)} where {MIN_FOLDS_WON} were required. The filter is not selecting the calls "
            f"that were going to be right; it is selecting a subset, and a random subset of the same "
            f"size does as well. Note also that full coverage scores {mean_nofilter:.4f}, so the "
            f"direction model it is filtering has no edge of its own to concentrate -- this measures "
            f"whether macro context adds decision quality, and the answer is that it does not."
            if not ok else
            f"The qualifier scores {mean_candidate:.4f} against {mean_random:.4f} for coverage-matched "
            f"random withholding, {gain:+.4f}, winning {won} of {len(scored)} folds at "
            f"{mean_coverage:.1%} coverage. All three pre-declared criteria are met."
        ),
        "notDeployed": ("a NO-GO is recorded and nothing is wired into a live decision path. The macro "
                        "layer keeps the role it already had: decision-context and integrity-veto, "
                        "never a vote." if not ok else "pending review"),
    }
    (out / "context_experiment.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "criteriaMet": passed,
                      "verdict": report["verdict"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
