"""Same target, same 44 features, whole frozen universe instead of crypto alone.

    python tools/research/eligible_set_experiment.py [--inspect] [--out FILE]

**Pre-registered before any number from this run was seen.** Target, folds, optimizer, features,
controls and the five acceptance criteria below were fixed here first.

Correction this version exists for (v1 -> v2)
----------------------------------------------
`eligible-set-v1` and its predecessor `binary-context-v1` fitted this two-class target with
**three output columns**, because `fit_weighted` sized its matrix from `len(CLASSES)` == 3, and
their saved `predictedMix`/`actualMix` indexed into `CLASSES`, so binary index 1 -- the positive
class -- was written out as `FLAT` and `UP` as 0 on every fold. v2 fits two columns named
`["DOWN", "UP"]`, asserts the matrix is `(features + 1) * 2`, and builds both mixes with
`class_counts` against those same two names. Dataset, quarantine, rows, markets, features, folds,
embargo, preprocessing order, `L2`, seed, controls, criteria and thresholds are unchanged, and both
v1 artifacts are preserved untouched on disk.

**Exposure, stated plainly:** these calendar years and this universe were previously examined by
v1 and by every earlier run, so this corrected run re-measures an already-observed holdout. It is
not a pristine independent result, and no threshold was moved after any metric was seen.

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
* **Optimizer.** `fit_weighted` imported from `balanced_experiment`, called with
  `classes=BINARY_CLASSES` so the matrix is built for two outputs, at **`L2 = 1e-4`** —
  the fixed setting every prior run used, deliberately, because `regularisation_experiment` has
  just shown that selecting the penalty by inner validation made the result *worse*. The eligible
  set is the variable under test; the penalty stays where it was. (v1 called it without `classes`
  and so trained three columns on two labels; that is the defect being corrected.)
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
  obstruction is not the eligible set either. Whether that ends the linear family is a separate
  question and must be answered against **this** corrected two-class fit, not against the runs
  that preceded it: v1's reading -- "the linear family on this feature set is exhausted across
  every eligible set available" -- was written for a model whose output width did not match its
  own target, so it does not prove a proper two-class linear model is exhausted. If this
  corrected baseline also fails, the next step is **one** bounded, pre-registered non-linear
  experiment, specified with fixed criteria, baselines and resource limits before it runs and
  before any ML dependency is declared while `requirements.txt` is trust-fingerprinted.
* Fails with crypto *worse* than the rest: the crypto slice was the hardest market and the
  prior verdicts over-generalised from it.
* Whatever the outcome: a NO-GO is preserved as a NO-GO, no threshold moves after any metric
  is seen, and the fact that this holdout was examined before is disclosed rather than treated
  as fresh evidence.

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
    class_counts,
    fit_weighted,
)
from stationarity import BLOCK_DAYS, BOOTSTRAP, block_bootstrap, over_majority  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

DATASET = ROOT / ".cache" / "foundation" / "dataset_v4"
CACHE = ROOT / ".cache" / "foundation" / "universe_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "eligible_set_experiment_v2.json"
PREDECESSOR = ROOT / "data" / "foundation" / "dataset" / "binary_context_experiment_v2.json"
PREDECESSOR_V1 = ROOT / "data" / "foundation" / "dataset" / "binary_context_experiment.json"

VERSION = "eligible-set-v2"
MIN_TRAIN, MIN_TEST = 5000, 500
WORST_FOLD_FLOOR = -0.05
REGIME_MIN_ROWS, REGIME_LOSS = 1000, -0.05
MIN_MARKET_ROWS = 200
# Indices into the *loaded* three-class labels, used only to read rows out of the dataset.
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
    # Explicit two-class encoding: the dataset's UP becomes BINARY_UP, every other row that
    # survives the FLAT drop is DOWN. Written out rather than implied so the label array and
    # BINARY_CLASSES cannot drift apart -- that drift is what named the positive class FLAT in v1.
    yb = np.where(y == UP, BINARY_UP, BINARY_DOWN).astype(np.int64)
    assert set(np.unique(yb).tolist()) <= {BINARY_DOWN, BINARY_UP}
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
        W, steps, loss = fit_weighted(Ztr, yb[tr], class_weights(yb[tr]), l2=L2, seed=SEED,
                                      classes=BINARY_CLASSES)
        if W.shape != (Ztr.shape[1] + 1, N_BINARY):
            raise SystemExit(f"expected {(Ztr.shape[1] + 1, N_BINARY)}, got {W.shape}")
        yp = predict(W, Zte)
        if yp.min() < 0 or yp.max() >= N_BINARY:
            raise SystemExit(f"prediction outside {BINARY_CLASSES}: {yp.min()}..{yp.max()}")

        rng = np.random.default_rng(SEED + 1000 + cut_year)
        Wc, steps_c, _ = fit_weighted(Ztr, rng.permutation(yb[tr]), class_weights(yb[tr]),
                                      l2=L2, seed=SEED + 500, classes=BINARY_CLASSES)
        yc = predict(Wc, Zte)

        acc, maj, over = over_majority(yb[te], yp)
        acc_c, maj_c, over_c = over_majority(yb[te], yc)
        pred_mix = np.bincount(yp, minlength=N_BINARY) / len(yp)
        act_mix = np.bincount(yb[te], minlength=N_BINARY) / len(yb[te])
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
                      "predictedMix": class_counts(yp, BINARY_CLASSES),
                      "actualMix": class_counts(yb[te], BINARY_CLASSES),
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

    pred_mean, pred_mean_v1 = None, None
    if PREDECESSOR.exists():
        pj = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
        pred_mean = pj.get("summary", {}).get("meanMargin")
    if PREDECESSOR_V1.exists():
        pj1 = json.loads(PREDECESSOR_V1.read_text(encoding="utf-8"))
        pred_mean_v1 = pj1.get("summary", {}).get("meanMargin")

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
        "correctionOf": {
            "artifact": "eligible_set_experiment.json",
            "version": "eligible-set-v1",
            "preservedUnchanged": True,
            "defect": "eligible-set-v1 fitted this two-class target with three output columns, "
                      "because fit_weighted sized its matrix from len(CLASSES) == 3. Labels {0,1} "
                      "used columns 0 and 1, the column CLASSES calls UP never received a target "
                      "row, and predictedMix/actualMix indexed into CLASSES so the binary positive "
                      "class was written out as FLAT while UP was written as 0 on every fold. The "
                      "same defect was in its predecessor, binary-context-v1.",
            "scope": "correctness repair of the model output dimension and of the reported class "
                     "names only. Dataset, quarantine, rows, markets, features, folds, embargo, "
                     "preprocessing order, L2, seed, controls and the five criteria with their "
                     "thresholds are untouched. The conclusion of eligible-set-v1 -- widening the "
                     "eligible set did not help, so the obstruction is not the eligible set -- is "
                     "re-measured here, not assumed.",
            "exposure": "these calendar years and this universe were previously examined by v1, so "
                        "this corrected run re-measures an already-observed holdout and is not a "
                        "pristine independent result. No threshold was changed after any metric "
                        "was seen."},
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
                   "construction": "signal_floor.py lines 102-104",
                   "classes": list(BINARY_CLASSES),
                   "encodingNote": "BINARY_CLASSES[1] is UP and is reported as UP; the dataset's "
                                   "three-class FLAT rows are dropped before encoding"},
        "model": {"optimizer": "fit_weighted imported from balanced_experiment, called with "
                               "classes=BINARY_CLASSES so the matrix is built for two outputs",
                  "outputClasses": list(BINARY_CLASSES),
                  "outputDimension": N_BINARY,
                  "weightMatrixShape": [int(len(ALL_FEATURES) + 1), N_BINARY],
                  "corrects": "eligible-set-v1's three-column fit on a two-class target",
                  "l2": L2, "learningRate": LR, "tolerance": 1e-6, "maxSteps": MAX_STEPS,
                  "l2HeldFixedBecause": "regularisation_experiment showed inner-validation "
                                        "selection made the result worse; the eligible set is "
                                        "the variable under test (that finding came from v1, "
                                        "measured with the same three-column defect this version "
                                        "corrects, so it is cited as reported, not as settled)",

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
                    "predecessorCryptoMeanMarginV1": pred_mean_v1,
                    "deltaVsPredecessor": (round(mean_margin - pred_mean, 4)
                                           if pred_mean is not None else None)},
        "byMarket": by_market,
        "cryptoVsRest": {"crypto": crypto, "everythingElse": rest},
        "byRegime": regimes,
        "fidelityLimitations": [
            "the eligible set changed and nothing else, but the crypto caches carried no "
            "dataQuality mask while this run does apply quarantine, so this run is stricter "
            "than its predecessors on that axis",
            "this holdout was examined by eligible-set-v1 and is re-measured here, so it is a "
            "correction of an observed result, not a fresh independent one"],
        "verdict": verdict,
        "failingCriteria": failing,
        "nextQuestion": ("the corrected two-class linear baseline has now been measured on this "
                         "eligible set and failed, so any claim that the linear family is "
                         "exhausted rests on that corrected measurement rather than on the "
                         "three-logit runs before it. The next step is one bounded, "
                         "pre-registered non-linear experiment, specified before it runs and "
                         "before any ML dependency is added"
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
