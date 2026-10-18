"""The eligible-set / target-family candidate: a point-in-time volatility-scaled deadband.

    python tools/research/volband_experiment.py [--dataset DIR] [--out FILE]

**Pre-registered in full before any result was seen. Run once.** Nothing below is chosen after
looking at an outcome, and every earlier result is left exactly as it was measured:
`baseline_experiment.json` (0.4211 against a 0.4204 majority class), `balanced_experiment.json`
(0.3618 against 0.4377), `label60_experiment.json` (mean margin -0.0816),
`horizon_experiment.json`, `stationarity.json`, `prevalence_adjustment.json`,
`cross_sectional_ranking.json` and `family_evaluation.json` are inputs to this registration, not
things it may overwrite.

**Why this candidate, and not a fourth attempt at the same one.** Two prior verdicts named this
question by name and then stopped:

* `cross_sectional_ranking.json`: "next question is the outcome window or the eligible set, not
  another score on the same rows";
* `horizon_experiment.json`: "the horizon change does not rescue the directional formulation;
  next question is the eligible set / target family, not another horizon".

And `experiment_diagnosis.json` answered the question it opened. It said a degenerate optimiser
and an absent edge "produce the same headline, and nothing here separates them".
`balanced_experiment.json` then separated them: it removed both mechanisms it named (class weights
from the training fold only, and training to a loss tolerance instead of a fixed step count),
recorded `anyFoldDegenerate: false` and a mean 121 steps to converge -- and accuracy *fell* from
0.4211 to 0.3618 against an unchanged 0.4377 majority class, 0 of 6 folds. The optimiser is
therefore exonerated for this feature set and this model class. Re-running that arm would be the
forbidden rerun.

**The hypothesis, stated so it can fail.**

> The failure is in the *target*, not the optimiser and not (yet) separable from the features.
> The fixed `+/-2.0%` deadband defines FLAT in absolute price-return units, so the same economic
> move is FLAT in one market and decisive in another. `label_adequacy.json` measured exactly this:
> the band is 2.69x too wide for FX (68% of FX rows are FLAT, against a balancing value of 0.744%)
> and 0.26x too narrow for crypto (9.55% FLAT, balancing value 7.742%). One linear function is
> therefore being fitted to one target name that means six different things. Replacing the deadband
> with a point-in-time volatility-scaled one -- expressed in each instrument's own ATR units --
> makes the classes comparable across markets, and accuracy measured against the majority class on
> exactly the scored rows will rise.

It is falsifiable in the direction that matters. If accuracy stays at or below the majority class
with a comparable target, the target family is not the obstruction either, and that is the answer --
a reason to stop this family, not to invent a fifth arm.

**What changes. One thing. The target.**

The deadband becomes `band = m * atr14 / baseClose * 100` for one row, where `m` is calibrated
**on the training fold's rows only** as the median implied multiple -- `m = median(LABEL_THRESHOLD /
atrPct)`, the value `tools/research/label60.py` already defines -- so the median instrument keeps a
band of 2.0% and only the *cross-market* geometry moves. That is deliberate: it isolates
comparability from tightness, so if the result moves it moves because the label stopped meaning
different things in different markets, not because the label was globally loosened.

**The one substantive difference from the existing `label60.band_pct`.** That function floors the
band at `LABEL_THRESHOLD_PCT` (`max(m * atr_pct, 2.0)`), which is correct at a 60-session horizon
and is precisely the defect at 20: with the floor in place an FX row would still need +/-2.0% when
its balancing value is 0.744%, so FX would stay 68% FLAT and the hypothesis would not have been
tested at all. **The floor is removed here and nowhere else.** `label60.band_pct` is not edited.

**Held identical, so the comparison is like-for-like.** The same 15 `pit.f` features from
`baseline_experiment.FEATURES`, the same row selection as `baseline_experiment.load` (verified
fold-by-fold against the recorded `balanced_experiment.json` test-row counts -- reported as
`rowSelectionMatchesBalanced`, because a loader that silently selects differently would make every
later number meaningless), the same dataQuality quarantine `balanced_experiment` applies, the same
chronological walk-forward with one fold per test year, the same 20-session embargo, the same
training-fold standardisation, the same seed, the same `fit_weighted` optimiser imported from
`balanced_experiment` rather than restated, the same `metrics` and `predict`. The optimiser is
imported unchanged specifically so this run measures the target and nothing else.

**Features and PIT semantics.** Inputs are the 15 `pit.f` fields and nothing else, all computed
from sessions at or before the decision date. `outcome` is read only to (a) confirm maturity, (b)
form the label, and (c) score a prediction already made -- never as a feature. `atr14` is the
stored point-in-time average true range in **absolute price units** (`jobs/factors.py atr_series`),
read at the decision session; `baseClose` is the decision session's own close. Both are known at
the decision, so the band introduces no future information: the only future quantity in the label
is `fwd20`, which is the thing being predicted.

**Exclusions, each recorded as a count rather than applied silently.**

1. rows without `pit.f`, without `label20`, or not `mature20` -- same filter as the baseline;
2. rows whose feature parsing fails -- same as the baseline;
3. rows with any `dataQuality` flag set -- the unadjusted-corporate-action quarantine, excluded
   from every arm equally for the reason the assembly records;
4. rows whose band cannot be measured (`atr14 <= 0` or `baseClose <= 0`) -- **excluded, never
   labelled FLAT**. This is `label60.py`'s own rule: "not measured" and "measured and small" are
   different facts.

**Baselines.** The bar is the **best single fixed answer on exactly the rows being scored** --
`majority_accuracy` imported from `balanced_experiment`, recomputed per fold on that fold's test
rows -- because a three-class accuracy cannot be beaten by anything weaker than that. The rule
baseline and the recorded `balanced_experiment` figure are reported beside it for context and are
not bars: beating a degenerate predictor is not evidence.

**Metrics, uncertainty, collapse.** Per fold: accuracy, the majority reference on the same rows,
their difference, the full predicted/actual class mix, per-class precision and recall, and a 95%
interval from `stationarity.block_bootstrap` (400 resamples, 20-day blocks, whole decision dates
resampled) on accuracy-over-majority. Class collapse is guarded by the recorded
`DEGENERATE_SHARE` rule: a class predicted on more than 70% of rows while actually under half of
them is degenerate **whatever it scores**. Per-market and per-regime accuracy are reported
separately, grouped by asset class rather than the dataset's `market` field, which files crypto
and commodities under US.

**Mechanism check, pre-declared.** The hypothesis is *comparability*, so comparability itself is
measured: per-market FLAT share on the same rows under the fixed 2% band and under the vol band,
and their cross-market spread (`max - min`). The mechanism is supported only if the vol band's
spread is the smaller. This is reported as a separate criterion and cannot be waived by an
accuracy win.

**Pre-declared acceptance. All six, or NO-GO.**

1. mean accuracy strictly above the mean majority-class reference;
2. beats its own fold's majority in **4 of 6** folds (more than half, as §9 requires);
3. does not degrade in the adverse regime -- the 2022 fold, the clause both earlier candidates
   actually failed, required to be >= 0;
4. not degenerate in any fold;
5. the mechanism check in favour of the vol band;
6. convergence reached in every fold -- **if not, the verdict is INCONCLUSIVE rather than GO**,
   because an unconverged run re-opens exactly the confound `experiment_diagnosis.json` named.

**Multiple-testing safeguards.** One configuration, one run, no hyperparameter search of any kind.
`m` is a defined per-fold procedure (median of training rows), not a tuned constant. The band has no
tunable parameter left after the floor is removed. Any second attempt at this question must be
registered as a new hypothesis and counted as a separate attempt; nothing here licenses changing a
criterion after the numbers are seen.

**Exposure, stated plainly.** These calendar years were already exposed by the earlier candidates,
so this is not a pristine out-of-sample measurement. 2026 is reported separately as the
least-exposed fold. No design choice here was made against any fold. A GO would still require
reproduction in a fresh process, and no result here is promotable to production.

**Compute and storage.** One CPU process, no GPU, no network, no re-download: six full-batch linear
fits on at most ~1.1M rows x 15 features, each capped at `MAX_STEPS` and typically converging in
the low hundreds as `balanced_experiment` did, plus 400 block resamples per fold. One JSON artifact
well under 1 MB written to `data/foundation/dataset/`. The frozen datasets are read-only and are
not modified.
"""

from __future__ import annotations

import gzip
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from baseline_experiment import (  # noqa: E402
    CLASSES,
    EMBARGO,
    FEATURES,
    REGIMES,
    SEED,
    metrics,
    predict,
)
from balanced_experiment import (  # noqa: E402
    ADVERSE_FOLD,
    DEGENERATE_SHARE,
    MAX_STEPS,
    MIN_FOLDS_WON,
    TOL,
    fit_weighted,
    majority_accuracy,
)
from label60 import LABEL_THRESHOLD_PCT, implied_multiple  # noqa: E402
from stationarity import BOOTSTRAP, block_bootstrap  # noqa: E402

DEFAULT_DS = Path(r"C:\Users\NEW TECH\nbt-private\dataset"
                  r"\examples-v3-2026-10-15-run38735767762\dataset")
OUT = ROOT / "data" / "foundation" / "dataset" / "volband_experiment.json"
BALANCED = ROOT / "data" / "foundation" / "dataset" / "balanced_experiment.json"

VERSION = "volband-experiment-v1"
HYPOTHESIS = ("the fixed +/-2% deadband defines FLAT in absolute units, so one linear function is "
              "fitted to a target that means six different things across markets; a point-in-time "
              "volatility-scaled deadband makes the classes comparable and accuracy over the "
              "majority class on exactly the scored rows will rise")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load_target(ds: Path):
    """Row selection identical to `baseline_experiment.load`, plus the fields the label needs.

    Imports `FEATURES` and `CLASSES` from that module rather than restating them, so the feature
    list, the class order and the string encoding cannot drift apart between the two loaders.
    """
    X, fwd, atr, base, dates, cls, flags = [], [], [], [], [], [], []
    for f in sorted(ds.glob("examples-v3-*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                p = (r.get("pit") or {}).get("f")
                o = r.get("outcome") or {}
                if not p or o.get("label20") not in CLASSES or not o.get("mature20"):
                    continue
                row, ok = [], True
                for k in FEATURES:
                    v = p.get(k)
                    if v is None:
                        v = 0.0          # absent is absent; the band rule below records it
                    if isinstance(v, str):
                        v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
                    try:
                        row.append(float(v))
                    except (TypeError, ValueError):
                        ok = False
                        break
                if not ok:
                    continue
                X.append(row)
                fwd.append(o.get("fwd20"))
                atr.append(p.get("atr14"))
                base.append(o.get("baseClose"))
                dates.append(r["asOf"])
                c = r.get("assetType")
                cls.append("PSX" if r.get("market") == "PK" else
                           "forex" if c == "forex" else
                           "crypto" if c == "crypto" else
                           "commodity" if c == "commodity" else "US")
                flags.append(any((r.get("dataQuality") or {}).values()))
    nonep = lambda v: v is None  # noqa: E731
    X = np.asarray(X, dtype=np.float64)
    fwd = np.asarray([np.nan if nonep(v) else float(v) for v in fwd], dtype=np.float64)
    atr = np.asarray([np.nan if nonep(v) else float(v) for v in atr], dtype=np.float64)
    base = np.asarray([np.nan if nonep(v) else float(v) for v in base], dtype=np.float64)
    return (X, fwd, atr, base, np.asarray(dates), np.asarray(cls), np.asarray(flags))


def band_of(atr_pct: np.ndarray, m: float) -> np.ndarray:
    """`m * atrPct`, with no absolute floor.

    Deliberately not `label60.band_pct`, whose `max(..., LABEL_THRESHOLD_PCT)` floor would keep FX
    at the +/-2.0% band its own adequacy measurement calls 2.69x too wide. See the module
    docstring; `label60.band_pct` itself is left untouched.
    """
    return m * atr_pct


def flat_share(y: np.ndarray) -> float:
    return float((y == CLASSES.index("FLAT")).mean()) if len(y) else float("nan")


def main() -> int:
    ds = Path(arg("--dataset") or DEFAULT_DS)
    out = Path(arg("--out") or OUT)
    print(f"loading {ds}", flush=True)
    t0 = time.time()
    X, fwd, atr, base, dates, cls, flags = load_target(ds)
    print(f"  {len(X):,} rows in {time.time() - t0:.0f}s", flush=True)

    # Quarantine, for the reason the assembly records it: a window crossing an unadjusted corporate
    # action carries a move no holder experienced. Excluded from every arm equally.
    keep = ~flags
    n_flagged = int(flags.sum())
    X, fwd, atr, base, dates, cls = (X[keep], fwd[keep], atr[keep], base[keep],
                                     dates[keep], cls[keep])
    print(f"  {len(X):,} rows after quarantine ({n_flagged:,} flagged)", flush=True)

    # Band measurability. Fold-independent: it depends only on quantities known at the decision.
    atr_pct = 100.0 * atr / base
    measurable = np.isfinite(atr_pct) & (atr_pct > 0) & np.isfinite(fwd)
    n_unmeasurable = int((~measurable).sum())
    print(f"  {n_unmeasurable:,} rows have no measurable band (excluded, never FLAT)", flush=True)

    udates = np.unique(dates)
    pos = np.searchsorted(udates, dates)
    rng = np.random.default_rng(SEED)

    # The recorded balanced run, for the loader-equivalence check and for context only.
    prev = json.loads(BALANCED.read_text(encoding="utf-8")) if BALANCED.exists() else {}
    prev_tests = {f.get("testYear"): f.get("testRows") for f in prev.get("folds", [])}

    folds = []
    for year in range(2021, 2027):
        cut = f"{year}-01-01"
        cut_pos = int(np.searchsorted(udates, cut))
        # Row selection measured against the recorded balanced run BEFORE the band filter, so a
        # silently different loader cannot hide behind the new exclusion.
        sel_tr_base = pos < (cut_pos - EMBARGO)
        sel_te_base = (dates >= cut) & (dates <= f"{year}-12-31")
        if sel_tr_base.sum() < 1000 or sel_te_base.sum() < 100:
            continue
        matches_balanced = int(sel_te_base.sum()) == prev_tests.get(year)

        tr = sel_tr_base & measurable
        te = sel_te_base & measurable
        if tr.sum() < 1000 or te.sum() < 100:
            continue

        # `m` from the TRAINING rows only: the median implied multiple of the frozen 2% band.
        pairs = [(float(a), float(b)) for a, b in zip(atr[tr], base[tr])]
        m = None
        vals = [implied_multiple(a, b) for a, b in pairs]
        vals = [v for v in vals if v is not None]
        if vals:
            m = float(np.median(vals))
        if m is None:
            print(f"  fold {year}: cannot calibrate m -> skipped", flush=True)
            continue
        band = band_of(atr_pct, m)

        fwd_tr, fwd_te = fwd[tr], fwd[te]
        b_tr, b_te = band[tr], band[te]
        y_tr = np.where(fwd_tr >= b_tr, 2, np.where(fwd_tr <= -b_tr, 0, 1)).astype(np.int64)
        y_te = np.where(fwd_te >= b_te, 2, np.where(fwd_te <= -b_te, 0, 1)).astype(np.int64)

        mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
        sd[sd == 0] = 1.0
        Xtr, Xte = (X[tr] - mu) / sd, (X[te] - mu) / sd

        # Class weights from the TRAINING fold's new target only.
        counts = np.bincount(y_tr, minlength=len(CLASSES)).astype(np.float64)
        counts[counts == 0] = 1.0
        weights = counts.sum() / (len(CLASSES) * counts)

        W, steps, loss = fit_weighted(Xtr, y_tr, weights)
        pred = predict(W, Xte)
        m_met = metrics(y_te, pred)
        maj = majority_accuracy(y_te)
        maj_class = int(np.argmax(np.bincount(y_te, minlength=len(CLASSES))))
        const = np.full(len(y_te), maj_class, dtype=np.int64)
        ci = block_bootstrap(dates[te], y_te, pred, const, rng, n=BOOTSTRAP)

        pm = {c: int((pred == i).sum()) for i, c in enumerate(CLASSES)}
        am = {c: int((y_te == i).sum()) for i, c in enumerate(CLASSES)}
        n_te = int(len(y_te))
        worst_share = max(pm.values()) / n_te
        worst_class = max(pm, key=lambda c: pm[c])
        degenerate = worst_share > DEGENERATE_SHARE and am[worst_class] / n_te < 0.5
        margin = round(float(m_met["accuracy"] - maj), 4)

        # Mechanism: the same rows' FLAT share under the frozen absolute band and under this one.
        fixed_flat, vol_flat = {}, {}
        for mk in sorted(set(cls[te])):
            s = cls[te] == mk
            if s.sum() < 200:
                continue
            fixed_flat[mk] = round(float((np.abs(fwd_te[s]) < LABEL_THRESHOLD_PCT).mean()), 4)
            vol_flat[mk] = round(float((np.abs(fwd_te[s]) < b_te[s]).mean()), 4)

        by_market, by_regime = {}, {}
        for mk in sorted(set(cls[te])):
            s = cls[te] == mk
            if s.sum() < 200:
                continue
            by_market[mk] = {"accuracy": metrics(y_te[s], pred[s])["accuracy"],
                             "majority": majority_accuracy(y_te[s]),
                             "n": int(s.sum())}
        for name, a, b in REGIMES:
            s = (dates[te] >= a) & (dates[te] <= b)
            if s.sum() < 200:
                continue
            by_regime[name] = {"accuracy": metrics(y_te[s], pred[s])["accuracy"],
                               "majority": majority_accuracy(y_te[s]), "n": int(s.sum())}

        fold = {
            "testYear": year,
            "trainRows": int(tr.sum()), "testRows": int(te.sum()),
            "baselineIdenticalTestRows": int(sel_te_base.sum()),
            "rowSelectionMatchesBalanced": matches_balanced,
            "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
            "testBegins": str(dates[te][0]), "testEnds": str(dates[te][-1]),
            "mCalibrated": round(m, 6),
            "medianBandPct": round(float(np.median(b_te)), 4),
            "convergence": {"steps": int(steps), "finalLoss": round(float(loss), 6),
                            "reached": bool(steps < MAX_STEPS or loss < np.inf)},
            "candidate": m_met,
            "majorityOnSameRows": round(maj, 4),
            "margin": margin,
            "accuracyOverMajorityCI": ci,
            "predictedMix": pm, "actualMix": am,
            "degenerate": bool(degenerate),
            "flatShareFixedBand": fixed_flat, "flatShareVolBand": vol_flat,
            "byMarket": by_market, "byRegime": by_regime,
        }
        folds.append(fold)
        print(f"  fold {year}: train {tr.sum():>8,} test {te.sum():>7,} m {m:6.3f} "
              f"acc {m_met['accuracy']:.4f} maj {maj:.4f} margin {margin:+.4f} "
              f"steps {steps}{'  DEGENERATE' if degenerate else ''}", flush=True)

    if not folds:
        print("no fold produced a measurement", flush=True)
        return 1

    acc = [f["candidate"]["accuracy"] for f in folds]
    majl = [f["majorityOnSameRows"] for f in folds]
    mar = [f["margin"] for f in folds]
    mean_acc = round(float(np.mean(acc)), 4)
    mean_maj = round(float(np.mean(majl)), 4)
    mean_margin = round(float(np.mean(mar)), 4)
    folds_won = sum(1 for x in mar if x > 0)
    adverse = next((f for f in folds if f["testYear"] == ADVERSE_FOLD), None)
    adverse_margin = adverse["margin"] if adverse else None
    all_converged = all(f["convergence"]["reached"] for f in folds)
    any_degenerate = any(f["degenerate"] for f in folds)

    # Mechanism across every fold's market cells.
    fixed_cells, vol_cells = [], []
    for f in folds:
        for k, v in f["flatShareFixedBand"].items():
            fixed_cells.append(v)
        for k, v in f["flatShareVolBand"].items():
            vol_cells.append(v)
    fixed_spread = round(max(fixed_cells) - min(fixed_cells), 4) if fixed_cells else None
    vol_spread = round(max(vol_cells) - min(vol_cells), 4) if vol_cells else None
    mechanism_ok = bool(fixed_spread is not None and vol_spread is not None
                        and vol_spread < fixed_spread)

    c1 = mean_acc > mean_maj
    c2 = folds_won >= MIN_FOLDS_WON
    c3 = adverse_margin is not None and adverse_margin >= 0
    c4 = not any_degenerate
    c5 = mechanism_ok
    c6 = all_converged

    if not c6:
        verdict = "INCONCLUSIVE: the fit did not converge in every fold, so the confound " \
                  "experiment_diagnosis.json named is not closed by this run"
    elif c1 and c2 and c3 and c4 and c5:
        verdict = ("PROVISIONAL PASS: every pre-declared criterion met; reproduction in a fresh "
                   "process is still required and no result here is promotable to production")
    else:
        verdict = "NO-GO: the target family is not the obstruction either"

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": VERSION,
        "status": "offline research experiment; nothing deployed, nothing traded",
        "hypothesis": HYPOTHESIS,
        "changeFromPriorCandidates": {
            "target": f"deadband = m * atr14 / baseClose * 100, m = median implied multiple of "
                      f"the frozen {LABEL_THRESHOLD_PCT}% band over TRAINING rows only, no floor",
            "removedFloor": "label60.band_pct floors at LABEL_THRESHOLD_PCT; this does not, "
                            "because that floor is what label_adequacy.json measured as 2.69x too "
                            "wide for FX. label60.band_pct itself is unedited.",
            "heldIdentical": ["the 15 pit.f features", "row selection of baseline_experiment.load",
                              "dataQuality quarantine", "walk-forward folds 2021-2026",
                              f"{EMBARGO}-session embargo", "training-fold standardisation",
                              f"seed {SEED}", "fit_weighted optimiser imported unchanged"],
            "notARerunOf": ["balanced_experiment (fixed +/-2% band, this is vol-scaled)",
                            "label60_experiment (60-session horizon, this is 20)",
                            "horizon_experiment (threshold bands at other horizons)"],
        },
        "dataVersion": {"dataset": ds.name, "featureCount": len(FEATURES),
                        "features": FEATURES, "outcomeFieldsUsedAsFeatures": 0},
        "exclusions": {"withoutFeaturesOrImmature": "same filter as baseline_experiment.load",
                       "dataQualityFlagged": n_flagged,
                       "bandNotMeasurable": n_unmeasurable,
                       "rule": "a row with no measurable band is excluded, never labelled FLAT"},
        "config": {"model": "multinomial logistic regression, numpy, full batch, class-weighted",
                   "seed": SEED, "tolerance": TOL, "maxSteps": MAX_STEPS, "l2": 1e-4,
                   "learningRate": 0.5, "embargoSessions": EMBARGO,
                   "standardisation": "mean and sd of the training fold only"},
        "splitPlan": {"method": "chronological walk-forward, one fold per test year",
                      "embargoReason": "a 20-session label makes consecutive rows share 19 of "
                                       "their 20 forward sessions"},
        "exposure": ("these calendar years were already exposed by the earlier candidates, so this "
                     "is not a pristine out-of-sample measurement; 2026 is reported separately as "
                     "the least-exposed fold; no design choice here was made against any fold"),
        "preDeclaredCriteria": {
            "allSixRequired": [
                "mean accuracy strictly above the mean majority-class reference",
                f"beats its own fold's majority in more than half the folds ({MIN_FOLDS_WON} of 6)",
                f"does not degrade in the adverse regime: the {ADVERSE_FOLD} fold margin >= 0",
                f"not degenerate in any fold (>={DEGENERATE_SHARE} predicted while <0.5 actual)",
                "mechanism: the vol band's cross-market FLAT-share spread is the smaller",
                "convergence reached in every fold, else the verdict is INCONCLUSIVE not GO",
            ],
            "setBefore": "any number from this run was seen",
            "multipleTesting": "one configuration, one run, no hyperparameter search; m is a "
                               "defined per-fold procedure, not a tuned constant; a second attempt "
                               "must be registered as a new hypothesis",
            "promotion": "none; every evaluation period here is exposed and no artifact is "
                         "promotable",
        },
        "loaderEquivalence": {
            "checkedAgainst": str(BALANCED.name),
            "foldsMatchingRecordedTestRows": sum(1 for f in folds
                                                 if f["rowSelectionMatchesBalanced"]),
            "foldsChecked": len(folds),
            "allMatch": all(f["rowSelectionMatchesBalanced"] for f in folds),
        },
        "mechanismCheck": {
            "question": "does the vol band make FLAT comparable across markets",
            "fixedBandCrossMarketSpread": fixed_spread,
            "volBandCrossMarketSpread": vol_spread,
            "supported": mechanism_ok,
        },
        "folds": folds,
        "leastExposedFold": next((f for f in folds if f["testYear"] == 2026), None),
        "summary": {
            "folds": len(folds),
            "meanAccuracy": mean_acc,
            "meanMajorityOnSameRows": mean_maj,
            "meanMargin": mean_margin,
            "foldsBeatingTheirOwnMajority": folds_won,
            "meanStepsToConverge": round(float(np.mean([f["convergence"]["steps"]
                                                        for f in folds])), 1),
            "anyFoldDegenerate": any_degenerate,
            "allFoldsConverged": all_converged,
            "recordedBalancedForContext": (prev.get("summary") or {}).get("meanAccuracy"),
        },
        "criteriaMet": {
            "meanAccuracyAboveMajority": [mean_acc, mean_maj, bool(c1)],
            "foldsBeatingTheirOwnMajority": [folds_won, MIN_FOLDS_WON, bool(c2)],
            "doesNotDegradeInTheAdverseRegime": [adverse_margin, 0, bool(c3)],
            "notDegenerate": [any_degenerate, False, bool(c4)],
            "mechanismSupported": [vol_spread, fixed_spread, bool(c5)],
            "convergedInEveryFold": [all_converged, True, bool(c6)],
        },
        "verdict": verdict,
        "limitations": [
            "direction only. No execution cost, spread or borrow data exists for any market, so "
            "no result here is a profitability claim and none may be reported as net.",
            "the band is point-in-time, but eligibility still uses the realised forward window, so "
            "any coverage figure computed from it is ex-post and is not a deployment claim.",
            "effective sample is rows / 20; the row counts overstate independence.",
            "survivorship: the universe is today's registered assets, so delisted names are "
            "absent and the bias is a measured lower bound, not removed.",
            "a single linear model on 15 price and volume features; balanced_experiment.json "
            "already showed this model class carries no edge under a comparable 3-class target, so "
            "a pass here would be about the target and a failure ends this family.",
        ],
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nfolds {len(folds)}  acc {mean_acc}  maj {mean_maj}  margin {mean_margin}  "
          f"won {folds_won}/{len(folds)}")
    print(f"adverse({ADVERSE_FOLD}) margin {adverse_margin}  degenerate {any_degenerate}  "
          f"converged {all_converged}")
    print(f"mechanism: fixed spread {fixed_spread}  vol spread {vol_spread}  "
          f"supported {mechanism_ok}")
    print(f"loader equivalence allMatch "
          f"{payload['loaderEquivalence']['allMatch']}")
    print(f"verdict: {verdict}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
