"""Same target, same 44 features, whole frozen universe instead of crypto alone.

    python tools/research/eligible_set_experiment.py [--inspect] [--out FILE]

**Pre-registered before any number from this run was seen.** Target, folds, optimizer, features,
controls and the five acceptance criteria below were fixed here first.

The question this settles
--------------------------
Every 44-feature run in the chain drew its rows from `.cache/foundation/*_slice.npz`, and all
**three of those caches are crypto only** — `crypto_slice`, `ranking_slice`, `horizon_slice`, all
93,452 rows of the same market. Two verdicts named the eligible set as the next question and
neither answered it: `cross_sectional_ranking` failed and wrote *"next question is data/horizon (a
different outcome window or a widened eligible set)"*; `horizon_experiment` failed and wrote
*"eligible set / target family"*. `volband_experiment` then took the target-family half. This run
takes the other half.

Crypto was also the market where a specialist was tried and failed (`train_v3_crypto`), and
`signal_floor` measured its in-sample ceiling *there* — the most favourable slice available. If
the eligible set is the obstruction, widening it is where the effect must show.

**The single changed variable.** The eligible set: crypto alone becomes the **whole frozen
universe**, read from `.cache/foundation/dataset_v4/examples-v4-context-*.jsonl.gz` — the same
files the crypto caches were cut from, so the features, the label and the point-in-time rules are
identical by construction. Target, feature list, fold rule, embargo, optimizer, seed, controls and
criteria are all held exactly as `binary_context_experiment` held them, which makes the two runs
comparable and isolates the eligible set as the only difference.

**One thing this run can do that the crypto runs could not:** the v4 records carry `dataQuality`,
so the **quarantine is applied** here. The crypto caches carry no mask, which was recorded as a
fidelity limitation on all three prior runs. This run is therefore stricter than its predecessors
on that axis, and the dropped count is reported.

What is held identical
-----------------------
* **Target.** `keep = y != FLAT`, `yb = 1 if UP else 0` — `signal_floor.py` lines 102-104.
* **Features.** All 44 `ALL_FEATURES` in order: `pit.f` price features and `pit.ctx.f` context
  features, looked up exactly as `cross_sectional_ranking.build_cache` looks them up.
* **Rows.** `label20` in `CLASSES` and `mature20` true, the same filter as every prior run.
* **Folds.** `baseline_experiment`'s rule: one fold per test year 2021..2026, train on every row
  before `cut_pos - EMBARGO`, `EMBARGO` = 20 decision dates, drop a fold under 5,000 training or
  500 test rows.
* **Feature handling.** `stationarity.fit_window`'s order, which is the only correct one on data
  that can be NaN: impute from the **training** fold's column nan-mean, *then* take the training
  fold's standard deviation, replacing a zero with 1.
* **Optimizer.** `fit_weighted` imported unchanged from `balanced_experiment` at **`L2 = 1e-4`** —
  the fixed setting every prior run used, deliberately, because `regularisation_experiment` has
  just shown that selecting the penalty by inner validation made the result *worse*. The eligible
  set is the variable under test; the penalty stays where it was.
* **Seed.** `SEED = 20261015`, control seed `SEED + 1000 + testYear`.
* **Reference and uncertainty.** `over_majority` and `block_bootstrap` imported unchanged from
  `stationarity`; 20-decision-date blocks, 400 resamples.

Acceptance, fixed before the run
---------------------------------
The **same five criteria** as `binary_context_experiment` and `regularisation_experiment`, so the
three runs are comparable and this one is not judged by a different bar:

* **C1** mean margin > 0. **C2** folds beating their own majority >= `min(4, foldsScored)`.
  **C3** no fold where one class is predicted on > 0.70 of rows while actually under half.
  **C4** the block-bootstrap 95% interval for (candidate margin - shuffled-control margin) has
  `p2_5 > 0`. **C5** the worst fold's margin >= -0.05.

Reported but **not** pass criteria, because they are diagnostics of *where* an effect lives rather
than whether the run succeeds: per-market pooled metrics, and the crypto-vs-rest split that is the
whole point of the run.

Pre-declared reading of the outcome
-----------------------------------
* Passes all five: the eligible set was the obstruction. Reproduce in a fresh process before
  calling it anything else.
* Fails with crypto *better* than the rest: widening the eligible set made it worse, so the
  obstruction is not the eligible set either, and the linear family on this feature set is
  exhausted across every eligible set available — the remaining move is a non-linear model, which
  needs an owner decision on declaring an ML dependency while `requirements.txt` is
  trust-fingerprinted.
* Fails with crypto *worse* than the rest: the crypto slice was the hardest market and the
  prior verdicts over-generalised from it.

Fidelity notes
--------------
The parse is streamed from the v4 jsonl files and cached to `.cache/foundation/universe_slice.npz`
so this run and any follow-up read the same bytes. Quarantine rows are dropped before any split
and counted. Nothing here is a promotion.
"""

from __future__ import annotations

import argparse
import gzip
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

from baseline_experiment import CLASSES, EMBARGO, L2, LR, REGIMES, SEED, predict  # noqa: E402
from balanced_experiment import (  # noqa: E402
    DEGENERATE_SHARE,
    MAX_STEPS,
    MIN_FOLDS_WON,
    fit_weighted,
)
from stationarity import BLOCK_DAYS, BOOTSTRAP, block_bootstrap, over_majority  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

DATASET = ROOT / ".cache" / "foundation" / "dataset_v4"
CACHE = ROOT / ".cache" / "foundation" / "universe_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "eligible_set_experiment.json"
PREDECESSOR = ROOT / "data" / "foundation" / "dataset" / "binary_context_experiment.json"

VERSION = "eligible-set-v1"
MIN_TRAIN, MIN_TEST = 5000, 500
WORST_FOLD_FLOOR = -0.05
REGIME_MIN_ROWS, REGIME_LOSS = 1000, -0.05
MIN_MARKET_ROWS = 200
FLAT, UP = CLASSES.index("FLAT"), CLASSES.index("UP")
N_CLASSES = len(CLASSES)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_with_labels(ds: Path) -> dict:
    """Same as `build`, but keeps the label too."""
    rows, ys, markets, flagged, dates = [], [], [], [], []
    dropped_bad_label = dropped_parse = 0
    files = sorted(ds.glob("examples-v4-context-*.jsonl.gz"))
    if not files:
        raise SystemExit(f"no examples-v4-context-*.jsonl.gz under {ds}")
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                pit = r.get("pit") or {}
                p, o = pit.get("f"), r.get("outcome") or {}
                if not p or o.get("label20") not in CLASSES or not o.get("mature20"):
                    dropped_bad_label += 1
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
                    dropped_parse += 1
                    continue
                rows.append(row)
                ys.append(CLASSES.index(o["label20"]))
                markets.append(r.get("assetType") or "unknown")
                dates.append(r["asOf"])
                dq = r.get("dataQuality") or {}
                flagged.append(bool(any(dq.values())) if dq else False)
    if not rows:
        raise SystemExit("no usable rows in the v4 dataset")
    return {
        "X": np.asarray(rows, dtype=np.float64),
        "y": np.asarray(ys, dtype=np.int64),
        "dates": np.asarray(dates),
        "market": np.asarray(markets),
        "flagged": np.asarray(flagged, dtype=bool),
        "dropped": {"badOrImmatureLabel": dropped_bad_label, "unparseable": dropped_parse},
        "files": [f.name for f in files],
    }


def load_or_build(ds: Path, cache: Path) -> dict:
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        d = {k: z[k] for k in ("X", "y", "dates", "market", "flagged")}
        d["dropped"] = json.loads(str(z["dropped"]))
        d["files"] = [str(x) for x in z["files"]]
        print(f"loaded cached universe slice: {len(d['X']):,} rows")
        return d
    print(f"reading every market from {ds} ...")
    d = build_with_labels(ds)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, X=d["X"], y=d["y"], dates=d["dates"], market=d["market"],
                        flagged=d["flagged"],
                        dropped=np.asarray(json.dumps(d["dropped"])),
                        files=np.asarray(d["files"]))
    print(f"rows {len(d['X']):,}  cached to {cache.name}")
    return d


def prep(Xtr, Xte):
    """Impute from the training fold, then scale on the training fold. `stationarity.fit_window`."""
    mu = np.nanmean(Xtr, axis=0)
    mu = np.where(np.isnan(mu), 0.0, mu)
    Xtr = np.where(np.isnan(Xtr), mu, Xtr)
    Xte = np.where(np.isnan(Xte), mu, Xte)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    return (Xtr - mu) / sd, (Xte - mu) / sd


def class_weights(ytr: np.ndarray) -> np.ndarray:
    counts = np.bincount(ytr, minlength=2).astype(float)
    n = len(ytr)
    return np.asarray([n / (2 * counts[0]), n / (2 * counts[1])])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--inspect", action="store_true",
                    help="parse, report markets/labels/quarantine and the fold plan; fit nothing")
    a = ap.parse_args()

    d = load_or_build(Path(a.dataset), Path(a.cache))
    X, y, dates, market, flagged = d["X"], d["y"], d["dates"], d["market"], d["flagged"]
    if X.shape[1] != len(ALL_FEATURES):
        raise SystemExit(f"rows have {X.shape[1]} columns, ALL_FEATURES has {len(ALL_FEATURES)}")

    keep = ~flagged
    X, y, dates, market = X[keep], y[keep], dates[keep], market[keep]
    print(f"cache files: {', '.join(d['files'])[:120]}")
    print(f"rows parsed {int((~keep).sum() + len(y)):,}  quarantine dropped {int((~keep).sum()):,}"
          f"  kept {len(y):,}")
    print(f"markets: " + ", ".join(f"{m}={int((market == m).sum()):,}"
                                   for m in sorted(set(market.tolist()))))
    # Captured before FLAT rows are dropped, so the artifact's counts describe the eligible set.
    rows_after_quarantine = len(y)
    market_counts = {m: int((market == m).sum()) for m in sorted(set(market.tolist()))}

    order = np.argsort(dates, kind="stable")
    X, y, dates, market = X[order], y[order], dates[order], market[order]

    if a.inspect:
        keepy = y != FLAT
        yb = y[keepy]
        print(f"after dropping FLAT: {int(keepy.sum()):,}  UP "
              f"{float((yb == UP).mean()):.4f} / DOWN {float((yb != UP).mean()):.4f}")
        udates = np.unique(dates)
        didx = {x: i for i, x in enumerate(udates)}
        pos = np.asarray([didx[x] for x in dates])
        print("\nfold plan (nothing fitted, nothing written):")
        for cut_year in range(2021, 2027):
            cut = f"{cut_year}-01-01"
            cand = [x for x in udates if x >= cut]
            if not cand:
                continue
            cut_pos = didx.get(cut, didx[cand[0]])
            tr = pos < (cut_pos - EMBARGO)
            te = (dates >= cut) & (dates <= f"{cut_year}-12-31")
            fits = tr.sum() >= MIN_TRAIN and te.sum() >= MIN_TEST
            print(f"  {cut_year}: train {tr.sum():>8,} test {te.sum():>8,}  "
                  f"{'fits' if fits else 'SKIPPED'}  train ends "
                  f"{udates[max(0, cut_pos - EMBARGO - 1)]}")
        return 0

    keepy = y != FLAT
    X, y, dates, market = X[keepy], y[keepy], dates[keepy], market[keepy]
    udates = np.unique(dates)
    didx = {x: i for i, x in enumerate(udates)}
    pos = np.asarray([didx[x] for x in dates])
    yb = (y == UP).astype(np.int64)
    print(f"rows for the binary target: {len(yb):,}  UP {yb.mean():.4f}")

    folds, pool = [], {"y": [], "yp": [], "yc": [], "dates": [], "market": []}
    for cut_year in range(2021, 2027):
        cut = f"{cut_year}-01-01"
        cand = [d for d in udates if d >= cut]
        if not cand:
            continue
        cut_pos = didx.get(cut, didx[cand[0]])
        tr = pos < (cut_pos - EMBARGO)
        te = (dates >= cut) & (dates <= f"{cut_year}-12-31")
        if tr.sum() < MIN_TRAIN or te.sum() < MIN_TEST:
            continue

        Ztr, Zte = prep(X[tr], X[te])
        W, steps, loss = fit_weighted(Ztr, yb[tr], class_weights(yb[tr]), l2=L2, seed=SEED)
        if W.shape != (Ztr.shape[1] + 1, N_CLASSES):
            raise SystemExit(f"expected {(Ztr.shape[1] + 1, N_CLASSES)}, got {W.shape}")
        yp = predict(W, Zte)

        rng = np.random.default_rng(SEED + 1000 + cut_year)
        Wc, steps_c, _ = fit_weighted(Ztr, rng.permutation(yb[tr]), class_weights(yb[tr]),
                                      l2=L2, seed=SEED + 500)
        yc = predict(Wc, Zte)

        acc, maj, over = over_majority(yb[te], yp)
        acc_c, maj_c, over_c = over_majority(yb[te], yc)
        pred_mix = np.bincount(yp, minlength=N_CLASSES) / len(yp)
        act_mix = np.bincount(yb[te], minlength=N_CLASSES) / len(yb[te])
        worst_i = int(pred_mix.argmax())
        degenerate = bool(pred_mix[worst_i] > DEGENERATE_SHARE and act_mix[worst_i] < 0.5)

        folds.append({"testYear": cut_year, "trainRows": int(tr.sum()),
                      "testRows": int(te.sum()),
                      "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
                      "testBegins": str(dates[te][0]), "testEnds": str(dates[te][-1]),
                      "steps": int(steps), "converged": bool(steps < MAX_STEPS),
                      "finalLoss": round(loss, 6),
                      "accuracy": acc, "majority": maj, "margin": over,
                      "beatsMajority": bool(over > 0),
                      "shuffledControlAccuracy": acc_c, "shuffledControlMargin": over_c,
                      "candidateMinusControl": round(over - over_c, 4),
                      "predictedMix": {CLASSES[i]: int((yp == i).sum()) for i in range(N_CLASSES)},
                      "actualMix": {CLASSES[i]: int((yb[te] == i).sum()) for i in range(N_CLASSES)},
                      "worstPredictedShare": round(float(pred_mix[worst_i]), 4),
                      "actualShareOfWorstPredicted": round(float(act_mix[worst_i]), 4),
                      "degenerate": degenerate,
                      "controlSteps": int(steps_c)})
        pool["y"].append(yb[te])
        pool["yp"].append(yp)
        pool["yc"].append(yc)
        pool["dates"].append(dates[te])
        pool["market"].append(market[te])
        print(f"  fold {cut_year}: acc {acc:.4f}  majority {maj:.4f}  margin {over:+.4f}  "
              f"control {over_c:+.4f}  steps {steps}{'  DEGENERATE' if degenerate else ''}",
              flush=True)

    if not folds:
        raise SystemExit("no fold met the pre-declared minimums")

    y_all = np.concatenate(pool["y"])
    yp_all = np.concatenate(pool["yp"])
    yc_all = np.concatenate(pool["yc"])
    d_all = np.concatenate(pool["dates"])
    m_all = np.concatenate(pool["market"])
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

    def pooled(sel):
        n = int(sel.sum())
        if n < MIN_MARKET_ROWS:
            return None
        a_r, m_r, o_r = over_majority(y_all[sel], yp_all[sel])
        return {"rows": n, "accuracy": a_r, "majority": m_r, "margin": o_r}

    by_market = {m: pooled(m_all == m) for m in sorted(set(m_all.tolist()))}
    by_market = {k: v for k, v in by_market.items() if v}
    crypto = pooled(m_all == "crypto")
    rest = pooled(m_all != "crypto")

    regimes = []
    for name, lo, hi in REGIMES:
        sel = (d_all >= lo) & (d_all <= hi)
        r = pooled(sel)
        if r and r["rows"] >= 200:
            regimes.append({"regime": name, **r,
                            "qualification": bool(r["rows"] >= REGIME_MIN_ROWS
                                                  and r["margin"] <= REGIME_LOSS)})

    pred_mean = None
    if PREDECESSOR.exists():
        pj = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
        pred_mean = pj.get("summary", {}).get("meanMargin")

    qualified = [r["regime"] for r in regimes if r["qualification"]]
    if not failing:
        verdict = ("GO-CANDIDATE: the whole frozen universe clears every criterion that the "
                   "crypto-only eligible set failed. Worth reproducing in a fresh process; not a "
                   "promotion.")
    else:
        verdict = f"NO-GO: {', '.join(failing)} failed the criteria fixed before this run."
    if crypto and rest:
        if crypto["margin"] > rest["margin"]:
            verdict += (" Crypto was the *better* eligible set of the two, so widening it did not "
                        "help and the obstruction is not the eligible set.")
        else:
            verdict += (" The non-crypto rows were the better eligible set, so the prior verdicts "
                        "over-generalised from the crypto slice.")
    if qualified:
        verdict += f" Qualification: adverse in {', '.join(qualified)}."

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": VERSION,
        "question": "does widening the eligible set from crypto to the whole frozen universe "
                    "change the binary/44 result?",
        "whyNotARerun": "all three 44-feature caches are crypto only; two verdicts named the "
                        "eligible set as the next question and neither answered it. Target, "
                        "features, folds, optimizer and criteria are held exactly as "
                        "binary_context_experiment held them",
        "data": {"dataset": str(Path(a.dataset).relative_to(ROOT)),
                 "files": d["files"],
                 "rowsParsed": int(rows_after_quarantine + int((~keep).sum())),
                 "quarantineDropped": int((~keep).sum()),
                 "quarantine": "any(dataQuality) true drops the row before any split",
                 "rowsKept": rows_after_quarantine,
                 "rowsAfterDroppingFlat": int(len(yb)),
                 "markets": market_counts,
                 "dateRange": [str(min(dates)), str(max(dates))],
                 "features": len(ALL_FEATURES),
                 "droppedDuringParse": d["dropped"]},
        "target": {"label": "binary UP vs DOWN, FLAT dropped", "up": 1, "down": 0,
                   "construction": "signal_floor.py lines 102-104"},
        "model": {"optimizer": "fit_weighted imported unchanged from balanced_experiment",
                  "l2": L2, "learningRate": LR, "tolerance": 1e-6, "maxSteps": MAX_STEPS,
                  "l2HeldFixedBecause": "regularisation_experiment showed inner-validation "
                                         "selection made the result worse; the eligible set is "
                                         "the variable under test",
                  "convergedFolds": sum(1 for f in folds if f["converged"]),
                  "ofFolds": len(folds)},
        "protocol": {"folds": "baseline_experiment's rule: one fold per test year 2021..2026",
                     "embargoDecisionDates": EMBARGO, "seed": SEED,
                     "imputation": "training-fold column nan-mean, then training-fold standard "
                                   "deviation (stationarity.fit_window order)",
                     "standardisation": "training-fold only",
                     "minTrainRows": MIN_TRAIN, "minTestRows": MIN_TEST,
                     "uncertainty": f"moving-block bootstrap, {BLOCK_DAYS}-date blocks, "
                                    f"{BOOTSTRAP} resamples, candidate minus shuffled control",
                     "reference": "over_majority imported unchanged from stationarity"},
        "criteria": criteria,
        "criteriaSource": "the same five criteria as binary_context_experiment, fixed in this "
                          "docstring before any number from this run was seen",
        "diagnosticsNotCriteria": ["byMarket", "cryptoVsRest", "byRegime"],
        "folds": folds,
        "summary": {"foldsScored": len(folds), "foldsWon": won, "foldsRequired": need,
                    "meanMargin": round(mean_margin, 4),
                    "meanShuffledControlMargin": round(float(np.mean(controls)), 4),
                    "worstFoldMargin": round(worst_margin, 4),
                    "worstFoldYear": int(folds[int(np.argmin(margins))]["testYear"]),
                    "degenerateFolds": degenerate_folds,
                    "anyFoldDegenerate": bool(degenerate_folds),
                    "pooledRows": int(len(y_all)), "bootstrap": boot,
                    "predecessorCryptoMeanMargin": pred_mean,
                    "deltaVsPredecessor": (round(mean_margin - pred_mean, 4)
                                           if pred_mean is not None else None)},
        "byMarket": by_market,
        "cryptoVsRest": {"crypto": crypto, "everythingElse": rest},
        "byRegime": regimes,
        "fidelityLimitations": [
            "the eligible set changed and nothing else, but the crypto caches carried no "
            "dataQuality mask while this run does apply quarantine, so this run is stricter "
            "than its predecessors on that axis",
            "three-column softmax with no FLAT targets, matching signal_floor's construction"],
        "verdict": verdict,
        "failingCriteria": failing,
        "nextQuestion": ("the linear family on this feature set is exhausted across every "
                         "eligible set available; the remaining move is a non-linear model, "
                         "which needs an owner decision on declaring an ML dependency while "
                         "requirements.txt is trust-fingerprinted"
                         if failing else
                         "reproduce in a fresh process, then read the by-market table for where "
                         "the effect lives"),
        "notAPromotion": "a passing verdict is a candidate for reproduction, never a GO",
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\n{'year':<6}{'acc':>9}{'majority':>10}{'margin':>10}{'control':>10}{'steps':>8}")
    for f in folds:
        print(f"{f['testYear']:<6}{f['accuracy']:>9.4f}{f['majority']:>10.4f}"
              f"{f['margin']:>+10.4f}{f['shuffledControlMargin']:>+10.4f}{f['steps']:>8}")
    print(f"\nmean margin {mean_margin:+.4f}  worst {worst_margin:+.4f}  won {won}/{len(folds)}"
          f" (needed {need})")
    if pred_mean is not None:
        print(f"predecessor (crypto only) mean {pred_mean:+.4f}   "
              f"delta {mean_margin - pred_mean:+.4f}")
    for name, v in by_market.items():
        print(f"  market {name:<12} n {v['rows']:>8,}  acc {v['accuracy']:.4f}  "
              f"maj {v['majority']:.4f}  margin {v['margin']:+.4f}")
    if crypto and rest:
        print(f"  crypto {crypto['margin']:+.4f}   everything else {rest['margin']:+.4f}")
    print(f"\n{verdict}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
