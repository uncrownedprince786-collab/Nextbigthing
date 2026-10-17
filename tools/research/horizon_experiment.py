"""Outcome-horizon experiment: does the 5-session target carry signal where the 20-session did not?

    python tools/research/horizon_experiment.py [--dataset DIR] [--cache FILE] [--out FILE]

The registered experiment
-------------------------
Registered 2026-10-18, before any number from this run was seen. It is the next question declared
in `BRAIN-CORPUS-COVERAGE-2026-10-17.md` section 10 and `WORKSTREAMS-2026-10-17.md` section 6 after
three families came back negative on the crypto slice: the training-window family (`stationarity.py`,
verdict in `stationarity.json`), the point-in-time prior-correction family (`prevalence_adjustment.py`,
verdict in `prevalence_adjustment.json`), and the 20-session cross-sectional form
(`cross_sectional_ranking.py`, verdict in `cross_sectional_ranking.json`). All three held the target
horizon fixed at 20 sessions. **The horizon is the one dimension not yet varied.** This test varies
it, and only it.

**Question.** At a **5-session** horizon, does the primary directional formulation (a single
3-class softmax over the features) carry out-of-sample skill where the identical 20-session
formulation did not?

**Target.** `label5` = UP when `fwd5 >= +LABEL5_THRESH%`, DOWN when `fwd5 <= -LABEL5_THRESH%`, else
FLAT, with `LABEL5_THRESH = 1.0`. The threshold is fixed, not tuned: the 20-session task's threshold
is ±2.0% (`make_dataset.py`), and forward-return scale goes as the square root of the horizon, so
`2.0 * sqrt(5/20) = 1.0`. The 20-session target is the recorded `label20` from the frozen rows.

**Eligible rows and the two populations.** Crypto rows from the frozen examples-v4-context dataset
(`.cache/foundation/dataset_v4/*.jsonl.gz`) with `label20` in the three classes and `mature20` true
— **the exact slice `stationarity.json` used**, so the 20-session side is a fidelity-guarded
re-derivation, not a new population. The 5-session side uses the subset of those rows that also
carry a resolved `fwd5`; the count that does not is reported, never imputed.

**Features.** The same 44 `ALL_FEATURES`, point-in-time. Imputation (training-fold column mean) and
standardisation (training-fold sd) come from the training rows only.

**Walk-forward, leakage-safe, horizon-isolated.** Evaluation years 2023, 2024, 2025, 2026. For each
year the cut is the first decision date of the year; `train_end` is the 20th-last distinct decision
date strictly before the cut, and the training set is every row with decision date <= `train_end`.
Both horizons use **the same split and the same 20-decision-date embargo** so the horizon is the
only thing that changes. (A 5-session label would need only a 5-session embargo; using 20 is the
conservative choice and keeps the 20-session guard exact. Recorded here before the run.)

Sides, each a single all-history fit on its own target and the same features:
* **h5** -- softmax on `label5` (the candidate).
* **h20** -- softmax on `label20` (the existing formulation; fidelity-guarded against
  `stationarity.json`'s recorded all-window accuracy and predicted mix for each year -- any
  mismatch beyond 5e-4 aborts the run).
* **majority** -- a constant predictor, each horizon's own training-fold majority class.
* **shuffled** -- paired control: the h5 fit retrained on the training labels permuted once (fixed
  seed), so the pipeline's structure is identical but carries no real label information.

**Metrics, per evaluation year, per horizon.**
* out-of-sample accuracy, majority share, and **accuracy over majority** (the headline);
* **predicted class mix** (degeneracy guard: the 20-session model predicted 0 FLAT rows every year);
* per-class recall and precision;
* in-sample over-majority on the training rows (the in-sample-to-OOS gap);
* **h5 versus h20** by accuracy-over-majority (chance-corrected, since the two targets have
  different class balances, so raw accuracy is not comparable across them);
* uncertainty -- the same moving-block bootstrap over decision dates, 20-date blocks, 400
  resamples, imported verbatim from `stationarity.py`, applied to (h5 over majority) minus
  (majority over majority) per year.

**Baselines.** (1) each horizon's own majority class; (2) the recorded 20-session all-history
numbers (re-derived here under the fidelity guard, cited in `stationarity.json`); (3) the shuffled
control; (4) the three completed experiments' verdicts, cited, never rerun.

**Rejection / progression criteria, fixed before the run.** The 5-session horizon counts as a
promising direction only if **all three** hold:
(a) h5 beats its own year's majority in **at least 3 of 4** evaluation years;
(b) h5's mean accuracy-over-majority across the four years **exceeds the mean bootstrap half-width**;
(c) h5's mean accuracy-over-majority **exceeds h20's** -- the shorter horizon actually helps.
Failing any of (a)-(c) is the result: the horizon change does not rescue the directional
formulation, both horizons are negative, and the next question is the **eligible set / target
family** (not another horizon, and not a rerun of any completed experiment).

**Promotion.** None under any outcome: every evaluation period here has been scored before, the
evidence is exploratory and never confirmatory, and no artifact is promotable. A pristine
prospective window would still be required before any candidate.

**Not repeated.** This does not rerun the corpus-widening, recency-window, prevalence-adjustment or
cross-sectional-ranking experiments; those are cited from their artifacts for context only.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from baseline_experiment import CLASSES, EMBARGO, SEED, fit_softmax  # noqa: E402
from stationarity import BLOCK_DAYS, BOOTSTRAP, block_bootstrap, over_majority  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

DATASET = ROOT / ".cache" / "foundation" / "dataset_v4"
CACHE = ROOT / ".cache" / "foundation" / "horizon_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "horizon_experiment.json"
STATIONARITY = ROOT / "data" / "foundation" / "dataset" / "stationarity.json"

EVAL_YEARS = ("2023", "2024", "2025", "2026")
LABEL5_THRESH = 1.0            # percent; 2.0 * sqrt(5/20), fixed before the run
RNG_SHUFFLE = SEED + 21        # h5 shuffled-label control
RNG_BOOT = SEED + 22           # h5-vs-majority bootstrap

CRITERIA = {
    "promisingIfAllHold": [
        "(a) h5 beats its own year's majority in >= 3 of 4 evaluation years",
        "(b) h5's mean accuracy-over-majority exceeds the mean bootstrap half-width",
        "(c) h5's mean accuracy-over-majority exceeds h20's (the horizon helps)",
    ],
    "failing": "the horizon change does not rescue the directional formulation; both horizons are "
               "negative -> next question is the eligible set / target family, not another horizon",
    "setBefore": "any number from this run was seen (registered 2026-10-18)",
    "promotion": "none; every evaluation period is exposed and no artifact is promotable",
}


def build_cache(ds: Path, prefix: str = "examples-v4-context") -> dict:
    """The exact stationarity slice, plus fwd5/fwd20 (the filter on label20/mature20 is unchanged)."""
    X, fwd5, fwd20, y, dates, syms = [], [], [], [], [], []
    for f in sorted(ds.glob(f"{prefix}-*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("assetType") != "crypto":
                    continue
                pit = r.get("pit") or {}
                p, o = pit.get("f"), r.get("outcome") or {}
                if not p or o.get("label20") not in CLASSES or not o.get("mature20"):
                    continue
                c = (pit.get("ctx") or {}).get("f") or {}
                row, ok = [], True
                for k in ALL_FEATURES:
                    v = p.get(k) if k in p else c.get(k)
                    if isinstance(v, str):
                        v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
                    if v is None:
                        row.append(np.nan)
                        continue
                    try:
                        row.append(float(v))
                    except (TypeError, ValueError):
                        ok = False
                        break
                if not ok:
                    continue
                X.append(row)
                f5 = o.get("fwd5")
                fwd5.append(float(f5) if f5 is not None else np.nan)
                fwd20.append(float(o["fwd20"]) if o.get("fwd20") is not None else np.nan)
                y.append(CLASSES.index(o["label20"]))
                dates.append(r["asOf"])
                syms.append(r["symbol"])
    return {"X": np.asarray(X, dtype=np.float64), "fwd5": np.asarray(fwd5, dtype=np.float64),
            "fwd20": np.asarray(fwd20, dtype=np.float64), "y": np.asarray(y, dtype=np.int64),
            "dates": np.asarray(dates), "syms": np.asarray(syms)}


def load(args) -> dict:
    cache = Path(args.cache)
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        d = {k: z[k] for k in ("X", "fwd5", "fwd20", "y", "dates", "syms")}
        print(f"loaded cached horizon slice: {len(d['X']):,} rows")
        return d
    print(f"reading crypto rows from {args.dataset} ...")
    d = build_cache(Path(args.dataset))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **d)
    print(f"rows {len(d['X']):,}  cached to {cache}")
    return d


def label_from_fwd(fwd: np.ndarray, thr: float) -> tuple[np.ndarray, np.ndarray]:
    ok = ~np.isnan(fwd)
    lab = np.full(len(fwd), -1, dtype=np.int64)
    lab[ok & (fwd >= thr)] = CLASSES.index("UP")
    lab[ok & (fwd <= -thr)] = CLASSES.index("DOWN")
    lab[ok & (fwd < thr) & (fwd > -thr)] = CLASSES.index("FLAT")
    return lab, ok


def fit_predict(X, y, tr, te):
    """One all-history fit; imputation and standardisation from the training rows only."""
    Xtr, Xte = X[tr], X[te]
    mu = np.nanmean(Xtr, axis=0)
    mu = np.where(np.isnan(mu), 0.0, mu)
    Xtr = np.where(np.isnan(Xtr), mu, Xtr)
    Xte = np.where(np.isnan(Xte), mu, Xte)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    W = fit_softmax((Xtr - mu) / sd, y[tr])
    z_te = np.hstack([(Xte - mu) / sd, np.ones((len(te), 1))]) @ W
    z_tr = np.hstack([(Xtr - mu) / sd, np.ones((len(tr), 1))]) @ W
    return z_te.argmax(axis=1), z_tr.argmax(axis=1)


def per_class(yt, yp) -> dict:
    out = {}
    for i, c in enumerate(CLASSES):
        m, pm = yt == i, yp == i
        out[c] = {"recall": round(float((yp[m] == i).mean()), 4) if m.any() else None,
                  "precision": round(float((yt[pm] == i).mean()), 4) if pm.any() else None,
                  "predicted": int(pm.sum())}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    d = load(a)
    X, fwd5, y, dates = d["X"], d["fwd5"], d["y"], d["dates"]
    if X.shape[1] != len(ALL_FEATURES):
        raise SystemExit(f"cache has {X.shape[1]} columns, ALL_FEATURES has {len(ALL_FEATURES)}")
    o = np.argsort(dates, kind="stable")
    X, fwd5, y, dates = X[o], fwd5[o], y[o], dates[o]
    d_ord = np.array([datetime.fromisoformat(str(x)).toordinal() for x in dates])
    lab5, has5 = label_from_fwd(fwd5, LABEL5_THRESH)
    missing5 = int((~has5).sum())
    print(f"rows {len(X):,}  columns {X.shape[1]}  {dates[0]}..{dates[-1]}  "
          f"rows without fwd5: {missing5:,}")

    recorded = json.loads(STATIONARITY.read_text(encoding="utf-8"))["byEvaluationYear"]

    years = {}
    for yr in EVAL_YEARS:
        te_all = np.where(np.char.startswith(dates.astype(str), yr))[0]
        if len(te_all) < 500:
            continue
        cut = d_ord[te_all[0]]
        uniq_before = np.unique(d_ord[d_ord < cut])
        if len(uniq_before) <= EMBARGO:
            continue
        train_end = uniq_before[-EMBARGO - 1]
        tr_all = np.where(d_ord <= train_end)[0]

        # h20 -- fidelity-guarded re-derivation of the recorded all-history numbers.
        yp20, yp20_tr = fit_predict(X, y, tr_all, te_all)
        acc20, maj20, over20 = over_majority(y[te_all], yp20)
        mix20 = {c: int((yp20 == i).sum()) for i, c in enumerate(CLASSES)}
        rec = recorded[yr]["windows"]["all"]
        if abs(acc20 - rec["accuracy"]) > 5e-4 or mix20 != rec["predictedMix"]:
            raise SystemExit(
                f"{yr}: h20 refit does not reproduce stationarity.json "
                f"(acc {acc20} vs {rec['accuracy']}, mix {mix20} vs {rec['predictedMix']})")
        i20_acc, i20_maj, i20_over = over_majority(y[tr_all], yp20_tr)

        # h5 -- the candidate, on the subset with a resolved fwd5.
        te = te_all[has5[te_all]]
        tr = tr_all[has5[tr_all]]
        yp5, yp5_tr = fit_predict(X, lab5, tr, te)
        acc5, maj5, over5 = over_majority(lab5[te], yp5)
        mix5 = {c: int((yp5 == i).sum()) for i, c in enumerate(CLASSES)}
        i5_acc, i5_maj, i5_over = over_majority(lab5[tr], yp5_tr)

        # majority constant predictor for h5, and the shuffled-label control.
        maj_class5 = int(np.bincount(lab5[tr], minlength=len(CLASSES)).argmax())
        yp_maj5 = np.full(len(te), maj_class5, dtype=np.int64)
        rng = np.random.default_rng(RNG_SHUFFLE)
        yp5_shuf, _ = fit_predict(X, lab5[tr][rng.permutation(len(tr))], tr, te)
        shuf_acc, _, shuf_over = over_majority(lab5[te], yp5_shuf)

        # Uncertainty on (h5 over majority) as (h5) - (majority predictor), per-year.
        boot = block_bootstrap(dates[te], lab5[te], yp5, yp_maj5,
                               np.random.default_rng(RNG_BOOT))

        years[yr] = {
            "evalRowsH20": int(len(te_all)), "evalRowsH5": int(len(te)),
            "trainRowsH20": int(len(tr_all)), "trainRowsH5": int(len(tr)),
            "classShareH5": {c: round(float((lab5[te] == i).mean()), 4)
                             for i, c in enumerate(CLASSES)},
            "h20": {"accuracy": acc20, "majority": maj20, "overMajority": over20,
                    "predictedMix": mix20, "perClass": per_class(y[te_all], yp20),
                    "inSampleOverMajority": i20_over},
            "h5": {"accuracy": acc5, "majority": maj5, "overMajority": over5,
                   "predictedMix": mix5, "perClass": per_class(lab5[te], yp5),
                   "inSampleOverMajority": i5_over,
                   "majorityClass": CLASSES[maj_class5]},
            "shuffledControl": {"accuracy": shuf_acc, "overMajority": shuf_over},
            "h5MinusH20OverMajority": round(over5 - over20, 4),
            "h5VsMajorityBootstrap": boot,
        }
        print(f"\n{yr}: h20 over {over20:+.4f} (acc {acc20})   h5 over {over5:+.4f} (acc {acc5}, "
              f"maj {maj5})   h5-h20 {over5 - over20:+.4f}   boot +/-"
              f"{(boot.get('halfWidth') if boot.get('halfWidth') is not None else float('nan')):.4f}")
        print(f"  h5 mix {mix5}  shuffled over {shuf_over:+.4f}")

    advs, hws = [], {}
    for yr in EVAL_YEARS:
        dd = years.get(yr)
        if not dd:
            continue
        advs.append((yr, dd["h5"]["overMajority"]))
        hws[yr] = (dd["h5VsMajorityBootstrap"] or {}).get("halfWidth")
    wins = sum(1 for _, adv in advs if adv > 0)
    mean5 = round(float(np.mean([adv for _, adv in advs])), 4)
    mean20 = round(float(np.mean([years[yr]["h20"]["overMajority"] for yr in EVAL_YEARS
                                  if yr in years])), 4)
    hw_vals = [hws[yr] for yr in EVAL_YEARS if yr in hws and hws[yr] is not None]
    mean_hw = round(float(np.mean(hw_vals)), 4) if hw_vals else None
    crit_a = wins >= 3
    crit_b = (mean_hw is not None) and (mean5 > mean_hw)
    crit_c = mean5 > mean20
    holds = crit_a and crit_b and crit_c

    verdict = (
        "the 5-session horizon is promising: it clears all three criteria" if holds else
        "the 5-session horizon is negative: the horizon change does not rescue the directional "
        "formulation; next question is the eligible set / target family")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "horizon-experiment-v1",
        "registeredIn": "this file's docstring, 2026-10-18, before any run",
        "question": "at a 5-session horizon, does the primary directional formulation carry "
                    "out-of-sample skill where the identical 20-session formulation did not",
        "target": f"label5 = UP/DOWN at +/-{LABEL5_THRESH}% fwd5, else FLAT; "
                  f"threshold = 2.0*sqrt(5/20), fixed before the run",
        "slice": "crypto rows of the frozen examples-v4-context dataset; same filter as "
                 "stationarity.json (label20 in classes, mature20), plus fwd5 for the h5 target",
        "rowsWithoutFwd5": missing5,
        "embargoSessions": EMBARGO,
        "horizonIsolation": "identical split and identical 20-decision-date embargo for both "
                            "horizons, so the target horizon is the only thing that changes",
        "fidelityGuard": "the h20 refit must reproduce stationarity.json's recorded all-window "
                         "accuracy and predicted mix per year; any mismatch >5e-4 aborts",
        "uncertainty": f"moving-block bootstrap over decision dates, {BLOCK_DAYS}-date blocks, "
                       f"{BOOTSTRAP} resamples, imported verbatim from stationarity.py",
        "preDeclaredCriteria": CRITERIA,
        "byEvaluationYear": years,
        "criteria": {
            "meanOverMajorityH5": mean5, "meanOverMajorityH20": mean20,
            "meanHalfWidth": mean_hw,
            "(a) h5 beats majority in >=3 of 4 years": {"holds": crit_a, "wins": wins,
                                                       "perYear": [[y, v] for y, v in advs]},
            "(b) h5 mean over majority > mean halfWidth": {"holds": crit_b},
            "(c) h5 mean over majority > h20 mean over majority": {"holds": crit_c},
            "allHold": holds,
        },
        "citedNotRerun": {
            "recency": "stationarity.json: no shorter window beats all-history in >=3 of 4 years",
            "prevalence": "prevalence_adjustment.json: fails all three, 0 of 4 years",
            "ranking": "cross_sectional_ranking.json: fails (a), (b), (d) at 20 sessions",
            "corpusWidening": "BRAIN-CORPUS-COVERAGE section 9: 6.00% own-scope, do not widen",
        },
        "verdict": verdict,
        "exposure": "every evaluation period here has been scored before; exploratory evidence "
                    "only, never confirmatory, and nothing is promotable from it",
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\ncriteria: {json.dumps(payload['criteria'], indent=1)}")
    print(f"\n{verdict}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
