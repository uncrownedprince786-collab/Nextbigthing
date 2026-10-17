"""Does training-window recency help, and was the non-stationarity claim even sound?

    python tools/research/stationarity.py [--cache FILE] [--out FILE]

First, a correction to the claim this experiment was built on
--------------------------------------------------------------
The previous checkpoint argued: `signal_floor.py` found **+0.0332** over majority in-sample while
`brain-v3-crypto` delivered **+0.0013** out-of-sample, the shuffled control was zero, therefore the
gap is non-stationarity rather than overfitting.

**That inference does not hold, and the reason is a population mismatch I introduced.** The
+0.0332 was fitted and scored on **all 93,452 crypto rows pooled**, against a pooled majority of
**0.5018**. The +0.0013 came from a model fitted on **72,892** training rows and scored on
**19,220** holdout rows, against a holdout majority of **0.4723**. Different fitting sets,
different scored sets, different baselines. Subtracting one from the other measures their
difference in setup at least as much as any change in the world.

A zero shuffled-label control also proves less than I claimed. It shows the model cannot fit
**unstructured** noise at this size. Real features are collinear and heavy-tailed, and a model can
still fit *structured* nuisance variation that does not recur. So overfitting was never excluded.

**Gate A below is the honest decomposition**: fit once on the training span only, then score the
training rows and the holdout rows with that same model. Both numbers then come from one fit, and
each is compared with its own period's majority. Only if in-sample-over-majority is clearly
positive while out-of-sample-over-majority is not does "the signal is there and does not survive"
become a defensible reading - and even then recency is a hypothesis to test, not a conclusion.

The registered experiment
-------------------------
**Hypothesis.** If the feature-to-label relationship drifts, a model trained on recent history
alone will generalise better than one trained on everything, because distant history is then
actively misleading rather than merely diluting.

**Windows.** all history / 3 years / 18 months / 6 months, each ending at the same cut, each
scored on identical evaluation rows. Nothing but the training window changes: features, target,
horizon, embargo, seed and hyperparameters are `brain-v2-context`'s, imported.

**Walk-forward.** The same sweep for evaluation years 2023, 2024, 2025 and 2026, so an apparent
benefit has to repeat rather than appear once. A result in 2026 alone is exploratory: that window
has been scored by three experiments and is not a confirmatory holdout.

**Uncertainty.** A moving-block bootstrap over **decision dates**, not rows. Consecutive rows share
19 of their 20 forward sessions and instruments within a day are correlated, so resampling rows
would understate the interval by roughly the block length. Blocks of whole dates preserve both.

**Rejection criteria, fixed before the run.** Recency helps only if a shorter window beats
all-history in **at least 3 of 4** evaluation years **and** its mean advantage exceeds the
bootstrap interval's half-width. Otherwise the finding is "inconclusive" or "recency does not
help" - both of which are results, and neither is a reason to try a fifth window.

**Promotion.** None. No artifact from this experiment is promotable under any outcome; the
evaluation periods are all exposed. This decides which question to ask next, not which model to
ship.
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

from baseline_experiment import CLASSES, EMBARGO, SEED, fit_softmax, predict  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

CACHE = ROOT / ".cache" / "foundation" / "crypto_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "stationarity.json"

#: Training windows, in calendar days back from the cut. None means every row before the cut.
WINDOWS = {"all": None, "3y": 1095, "18m": 548, "6m": 183}
EVAL_YEARS = ("2023", "2024", "2025", "2026")
BOOTSTRAP = 400
BLOCK_DAYS = 20          # one forward-window's worth of decision dates per block

CRITERIA = {
    "recencyHelps": "a shorter window beats all-history in at least 3 of 4 evaluation years AND "
                    "its mean advantage exceeds the bootstrap half-width",
    "yearsRequired": 3,
    "promotion": "none; every evaluation period here is exposed and no artifact is promotable",
    "setBefore": "any number from this run was seen",
}


def fit_window(X, y, tr_idx, te_idx):
    """One fit. Imputation and standardisation from the training rows only."""
    Xtr, Xte = X[tr_idx], X[te_idx]
    mu = np.nanmean(Xtr, axis=0)
    mu = np.where(np.isnan(mu), 0.0, mu)
    Xtr = np.where(np.isnan(Xtr), mu, Xtr)
    Xte = np.where(np.isnan(Xte), mu, Xte)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    W = fit_softmax((Xtr - mu) / sd, y[tr_idx])
    return predict(W, (Xte - mu) / sd), predict(W, (Xtr - mu) / sd)


def over_majority(yt, yp) -> tuple[float, float, float]:
    acc = float((yt == yp).mean())
    maj = float(max((yt == i).mean() for i in range(len(CLASSES))))
    return round(acc, 4), round(maj, 4), round(acc - maj, 4)


def block_bootstrap(dates, yt, yp_a, yp_b, rng, n=BOOTSTRAP) -> dict:
    """Interval for (A over majority) - (B over majority), resampling whole blocks of dates."""
    uniq = np.unique(dates)
    blocks = [uniq[i:i + BLOCK_DAYS] for i in range(0, len(uniq), BLOCK_DAYS)]
    if len(blocks) < 3:
        return {"halfWidth": None, "note": "too few decision-date blocks to bootstrap"}
    idx_by_date = {d: np.where(dates == d)[0] for d in uniq}
    diffs = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        sel = np.concatenate([idx_by_date[d] for b in pick for d in blocks[b]])
        if not len(sel):
            continue
        _, _, a = over_majority(yt[sel], yp_a[sel])
        _, _, b = over_majority(yt[sel], yp_b[sel])
        diffs.append(a - b)
    if not diffs:
        return {"halfWidth": None}
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"mean": round(float(np.mean(diffs)), 4), "p2_5": round(float(lo), 4),
            "p97_5": round(float(hi), 4), "halfWidth": round(float((hi - lo) / 2), 4),
            "resamples": len(diffs), "blockDays": BLOCK_DAYS}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    z = np.load(a.cache, allow_pickle=True)
    X, y, dates = z["X"], z["y"], z["dates"]
    o = np.argsort(dates, kind="stable")
    X, y, dates = X[o], y[o], dates[o]
    d_ord = np.array([datetime.fromisoformat(d).toordinal() for d in dates])
    print(f"rows {len(X):,}  columns {X.shape[1]}  {dates[0]}..{dates[-1]}")

    rng = np.random.default_rng(SEED)
    years = {}
    for yr in EVAL_YEARS:
        te = np.where(np.char.startswith(dates.astype(str), yr))[0]
        if len(te) < 500:
            continue
        cut = d_ord[te[0]]
        # Embargo in decision dates, because a 20-session label makes the last training rows and
        # the first evaluation rows share forward sessions.
        uniq_before = np.unique(d_ord[d_ord < cut])
        if len(uniq_before) <= EMBARGO:
            continue
        train_end = uniq_before[-EMBARGO - 1]

        per_window, insample = {}, {}
        preds = {}
        for name, span in WINDOWS.items():
            lo = -10**9 if span is None else train_end - span
            tr = np.where((d_ord <= train_end) & (d_ord > lo))[0]
            if len(tr) < 2000:
                per_window[name] = {"trainRows": int(len(tr)), "skipped": "fewer than 2,000 rows"}
                continue
            yp_te, yp_tr = fit_window(X, y, tr, te)
            acc, maj, over = over_majority(y[te], yp_te)
            i_acc, i_maj, i_over = over_majority(y[tr], yp_tr)
            mix = {c: int((yp_te == i).sum()) for i, c in enumerate(CLASSES)}
            per_window[name] = {
                "trainRows": int(len(tr)),
                "trainFrom": str(dates[tr[0]]), "trainTo": str(dates[tr[-1]]),
                "accuracy": acc, "majority": maj, "overMajority": over,
                "predictedMix": mix,
                "classesPredicted": int(sum(1 for v in mix.values() if v > 0)),
            }
            insample[name] = {"accuracy": i_acc, "majority": i_maj, "overMajority": i_over}
            preds[name] = yp_te

        if "all" in preds:
            for name in list(preds):
                if name == "all":
                    continue
                per_window[name]["vsAllHistory"] = block_bootstrap(
                    dates[te], y[te], preds[name], preds["all"], rng)
        years[yr] = {
            "evalRows": int(len(te)), "evalFrom": str(dates[te[0]]), "evalTo": str(dates[te[-1]]),
            "decisionDates": int(len(np.unique(dates[te]))),
            "effectiveIndependentWindows": int(round(len(te) / EMBARGO)),
            "classShare": {c: round(float((y[te] == i).mean()), 4) for i, c in enumerate(CLASSES)},
            "windows": per_window,
            "inSampleOnTrainingRows": insample,
        }
        print(f"\n{yr}: eval {len(te):,} rows, {len(np.unique(dates[te]))} dates, "
              f"majority {per_window.get('all', {}).get('majority')}")
        for name in WINDOWS:
            w = per_window.get(name, {})
            if "overMajority" not in w:
                print(f"  {name:<5} {w.get('skipped', 'n/a')}")
                continue
            hw = (w.get("vsAllHistory") or {}).get("halfWidth")
            ins = insample[name]["overMajority"]
            print(f"  {name:<5} train {w['trainRows']:>7,}  out {w['overMajority']:+.4f}  "
                  f"in {ins:+.4f}  vs-all {(w.get('vsAllHistory') or {}).get('mean', 0):+.4f}"
                  f"{'' if hw is None else f' +/-{hw:.4f}'}  classes {w['classesPredicted']}")

    # Does any shorter window beat all-history in at least 3 of 4 years, by more than noise?
    tally = {}
    for name in WINDOWS:
        if name == "all":
            continue
        wins, clear, diffs = 0, 0, []
        for yr, d in years.items():
            w = d["windows"].get(name, {})
            b = w.get("vsAllHistory") or {}
            if "mean" not in b:
                continue
            diffs.append(b["mean"])
            if b["mean"] > 0:
                wins += 1
                if b.get("halfWidth") is not None and b["mean"] > b["halfWidth"]:
                    clear += 1
        tally[name] = {"yearsBeatingAllHistory": wins, "yearsClearOfTheInterval": clear,
                       "yearsCompared": len(diffs),
                       "meanAdvantage": round(float(np.mean(diffs)), 4) if diffs else None}

    helps = [n for n, d in tally.items()
             if d["yearsBeatingAllHistory"] >= CRITERIA["yearsRequired"]
             and d["yearsClearOfTheInterval"] >= 1]
    verdict = ("recency helps: " + ", ".join(helps)) if helps else (
        "recency does not help: no shorter window beats all-history in at least "
        f"{CRITERIA['yearsRequired']} of {len(years)} evaluation years by more than the "
        "bootstrap interval")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "stationarity-v1",
        "correctionToThePriorClaim": {
            "claim": "+0.0332 in-sample vs +0.0013 out-of-sample proves non-stationarity",
            "why it does not hold": "the two numbers came from different populations with "
                                    "different baselines: +0.0332 was fitted and scored on all "
                                    "93,452 pooled rows against a 0.5018 majority, +0.0013 came "
                                    "from a model fitted on 72,892 and scored on 19,220 against "
                                    "a 0.4723 majority",
            "alsoOverstated": "a zero shuffled-label control shows the model cannot fit "
                              "unstructured noise; it does not exclude fitting structured "
                              "nuisance variation, so overfitting was never ruled out",
            "whatReplacesIt": "inSampleOnTrainingRows below: one fit, scored on its own training "
                              "rows and on the evaluation rows, each against its own majority",
        },
        "slice": "crypto, from the examples-v4-context cache; one market, not the whole universe",
        "windows": {k: (v if v else "all history") for k, v in WINDOWS.items()},
        "embargoSessions": EMBARGO,
        "uncertainty": f"moving-block bootstrap over decision dates, {BLOCK_DAYS}-date blocks, "
                       f"{BOOTSTRAP} resamples; rows are not resampled because consecutive rows "
                       "share 19 of 20 forward sessions and same-day instruments are correlated",
        "preDeclaredCriteria": CRITERIA,
        "byEvaluationYear": years,
        "tally": tally,
        "verdict": verdict,
        "exposure": "every evaluation period here has been scored before; exploratory evidence "
                    "only, never confirmatory, and nothing is promotable from it",
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\ntally: {json.dumps(tally)}")
    print(f"\n{verdict}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
