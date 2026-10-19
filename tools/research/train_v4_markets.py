"""Brain V4: one candidate model per market, not one model wearing five market labels.

    python tools/research/train_v4_markets.py [--dataset DIR] [--out DIR] [--brain DIR]
    python tools/research/train_v4_markets.py --verify     # load each written artifact and re-predict

Why this exists
---------------
Every recorded prediction so far carries `marketSpecific = false`, and `shadow_markets.capability`
says so in words: one global model applied to five markets is five applications of one brain, not
five brains. `brain-v3-crypto` showed the shape of the fix -- train on one population, keep every
other knob that `brain-v2-context` fixed -- but it was written for a single market and read a
hand-built `.npz` cache. This file generalises that one honest experiment to all five markets and
reads the versioned dataset directly.

The one thing that changes, per market
-------------------------------------
The **training population**. Features (the 44 of `pit.f` + `pit.ctx`), the target (`label20` at the
shared 2% / 20-session rule of `tools/make_dataset.py`), the split (`train_end`, a 20-session
embargo), the seed, the step count, the learning rate, the L2 and the imputation rule (the training
fold's own mean, so an absent value standardises to zero) are all imported from `baseline_experiment`
and `train_v2_context` rather than restated. A difference between two markets here is attributable to
the population and not to a knob, and a difference from `brain-v2-context` is attributable to the
population and not to this file.

What this can and cannot mean
-----------------------------
The evaluation window, `2026-01-01..2026-09-25`, has been scored before -- by the baseline
experiment, the balanced experiment, `brain-v2-context` and `brain-v3-crypto`. **It is diagnostic
and never independent.** So no market is promoted on this evaluation, whatever it scores; a market
that passes only earns the right to freeze its candidate and start a prospective stream. Direction
only: no execution-cost, spread or borrow data exists, so nothing here is a profitability claim.

A market that cannot support the exercise says so
-------------------------------------------------
A candidate needs a training fold and a holdout. Where a market has too few rows to fit a model and
score it, this file **records the shortfall and writes no model** rather than fitting a model on a
handful of rows and reporting its accuracy as if it meant something. The thresholds are fixed here,
before the run, and a market that misses them is a limitation, not a gap to fill with a smaller
model.

Data-quality checks before a market is trusted
----------------------------------------------
Before fitting, each market reports its own row counts, distinct decision dates, class balance,
symbols, asset-type breakdown, context coverage and how many rows carry a stored `dataQuality`
flag -- so it can be seen that the rows belong to the market the model is named for, and how thin
the evidence is.
"""

from __future__ import annotations

import argparse
import array
import gzip
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))  # make_dataset, for the shared label rule

import make_dataset as md  # noqa: E402  (the one shared label rule)
import significance  # noqa: E402  (the gate's arithmetic, kept testable on its own)
from baseline_experiment import CLASSES, EMBARGO, FEATURES, L2, LR, SEED, STEPS, metrics, predict  # noqa: E402
from context_features import VERSION as CTX_VERSION  # noqa: E402
from shadow_markets import MARKETS  # noqa: E402  (the one order the five markets are named in)
from train_v1 import degeneracy, repo_head, sha256_file  # noqa: E402
from train_v2_context import ALL_FEATURES, CTX_FEATURES, confusion, fit_and_score  # noqa: E402

DEFAULT_DS = ROOT / ".cache" / "foundation" / "dataset_v4"
OUT_DIR = ROOT / "data" / "foundation" / "dataset"
BRAIN_ROOT = ROOT / "data" / "foundation" / "brain"
PREFIX = "examples-v4-context"
TRAIN_END = "2025-12-31"

#: The model artifact directory name per market, so a path says which market it is.
MARKET_DIR = {"US": "us", "PK": "pk", "FX": "fx", "Commodity": "commodity", "Crypto": "crypto"}


def artifact_name(market: str, horizon: int = 20) -> str:
    """The artifact family for a market and horizon.

    20 sessions keeps `brain-v4-<market>` exactly as it is: those names are written into stored
    `ShadowPrediction` rows, into every manifest the daily audit checks by digest, and into the
    UI's model column, and renaming them would orphan all of it. A different horizon is a
    different task -- different label, different threshold -- so it is a different family, not a
    second model sharing a name with the first.
    """
    return (f"brain-v4-{MARKET_DIR[market]}" if horizon == 20
            else f"brain-v5-h{horizon}-{MARKET_DIR[market]}")

#: Fixed before the run. A candidate needs at least this much to fit and at least this much to
#: score; a market under either is recorded as a limitation with its counts and no model is written.
#: `MIN_HOLDOUT_ROWS` matches the 200-row floor the recorded experiments already use before they
#: will report a group at all.
MIN_TRAIN_ROWS = 2000
MIN_HOLDOUT_ROWS = 200

#: The acceptance checks, mirrored from brain-v2-context and brain-v3-crypto so a pass means the
#: same thing it meant there: beat the holdout majority, beat the price-only fit on the same rows,
#: do not collapse onto one class, and predict both directions. They are stated here, in the same
#: file and the same run that produced the numbers, so a pass is a **diagnostic** signal and not a
#: pre-registered result. Only a frozen candidate's own prospective stream can promote a market.
CRITERIA = {
    "accuracyAboveHoldoutMajority": "strictly above the holdout's largest-class share",
    "beatsThePriceOnlyModel": "strictly above the price-only fit on the same rows and split",
    "notDegenerate": "no predicted class exceeds 0.7 of the holdout while being under half of it",
    "bothDirectionsPredicted": "recall at least 0.2 for both DOWN and UP",
}


def market_of_row(asset_type: str | None, market: str | None) -> str:
    """The market a dataset row belongs to, in the site's own vocabulary.

    The same rule as `lib/decisionInput.marketOf` and `shadow_markets.market_of`: the asset type
    decides wherever it is unambiguous (crypto, forex, commodity), and a stock is split by the
    stored `market` field, which is `PK` for the Pakistan Stock Exchange and `US` otherwise. Kept
    local and small so a change here is visible, and pinned by `tests/test_market_models.py`.
    """
    t = (asset_type or "").strip().lower()
    if t == "crypto":
        return "Crypto"
    if t == "forex":
        return "FX"
    if t == "commodity":
        return "Commodity"
    return "PK" if (market or "").strip().upper() == "PK" else "US"


def load(ds: Path, prefix: str = PREFIX, horizon: int = 20) -> dict[str, dict]:
    """Every usable row, grouped by market, in one pass over the versioned dataset.

    A row is usable exactly when `train_v2_context.load` would keep it: price features present, a
    matured `label{horizon}` in CLASSES. The feature vector is assembled the same way -- a value from
    `pit.f` or, failing that, `pit.ctx.f`; a direction word mapped to +/-1; an absent value kept as
    NaN so the training fold's mean can replace it after the split. Accumulating into
    `array('d')` per market rather than a list of lists keeps the whole dataset from becoming a
    million Python float objects at once.
    """
    files = sorted(ds.glob(f"{prefix}-*.jsonl.gz"))
    if not files:
        raise SystemExit(f"no {prefix}-*.jsonl.gz in {ds}")
    per: dict[str, dict] = {
        m: {"x": array.array("d"), "y": [], "dates": [], "symbols": set(),
            "assetTypes": Counter(), "ctx": 0, "flagged": 0}
        for m in MARKETS
    }
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                pit = r.get("pit") or {}
                p, o = pit.get("f"), r.get("outcome") or {}
                # Derived rather than read, because the frozen dataset was assembled when only
                # `label20` was written: every row carries `fwd1`, `fwd5` and `fwd20` (make_dataset
                # HORIZONS), and a shorter label is that forward return put through the one shared
                # rule. A stored label is preferred when the dataset has one, so a rebuilt dataset
                # and this loader can never disagree about a row. `fwd{h} is None` is the maturity
                # test, exactly as it is in `outcomes`.
                fwd = o.get(f"fwd{horizon}")
                label = o.get(f"label{horizon}") or md.label_for(fwd, horizon)
                if not p or label not in CLASSES or fwd is None:
                    continue
                c = (pit.get("ctx") or {}).get("f") or {}
                row = []
                ok = True
                for k in ALL_FEATURES:
                    v = p.get(k) if k in p else c.get(k)
                    if isinstance(v, str):
                        v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
                    if v is None:
                        row.append(float("nan"))
                        continue
                    try:
                        row.append(float(v))
                    except (TypeError, ValueError):
                        ok = False
                        break
                if not ok:
                    continue
                m = market_of_row(r.get("assetType"), r.get("market"))
                b = per[m]
                b["x"].extend(row)
                b["y"].append(CLASSES.index(label))
                b["dates"].append(r["asOf"])
                b["symbols"].add(r.get("symbol"))
                b["assetTypes"][r.get("assetType")] += 1
                b["ctx"] += 1 if c else 0
                b["flagged"] += 1 if any((r.get("dataQuality") or {}).values()) else 0
    for m, b in per.items():
        b["X"] = np.frombuffer(b["x"], dtype=np.float64).reshape(-1, len(ALL_FEATURES)).astype(np.float32)
        b["y"] = np.asarray(b["y"], dtype=np.int64)
        b["dates"] = np.asarray(b["dates"])
        b["rows"] = int(len(b["y"]))
    return per


def collapse_analysis(yt: np.ndarray, yp: np.ndarray) -> dict:
    """Whether the candidate reads direction or just leans on one class.

    Reports the predicted and actual shares, the direction tally, and a plain `collapsed` flag: a
    class that takes more than 0.7 of the predictions while being under half of the holdout is the
    failure this project keeps meeting, and it is stated as a fact rather than left for a reader to
    infer from a mix.
    """
    n = len(yt)
    idx = {c: i for i, c in enumerate(CLASSES)}
    pred_share = {c: (float((yp == i).sum()) / n if n else 0.0) for c, i in idx.items()}
    actual_share = {c: (float((yt == i).sum()) / n if n else 0.0) for c, i in idx.items()}
    top = max(pred_share, key=lambda c: pred_share[c]) if n else None
    collapsed = bool(n and pred_share[top] > 0.7 and actual_share[top] < 0.5)
    return {
        "predictedShare": {c: round(v, 4) for c, v in pred_share.items()},
        "actualShare": {c: round(v, 4) for c, v in actual_share.items()},
        "predictedUp": int((yp == idx["UP"]).sum()),
        "predictedDown": int((yp == idx["DOWN"]).sum()),
        "predictedFlat": int((yp == idx["FLAT"]).sum()),
        "dominantPredictedClass": top,
        "collapsed": collapsed,
        "note": "collapsed means one class takes >0.7 of the predictions while being <0.5 of the "
                "holdout, which is scoring by leaning on a class rather than reading direction",
    }


def load_model(brain_dir: Path) -> dict:
    """Read a written model.json back from disk, as a separate process would."""
    return json.loads((brain_dir / "model.json").read_text(encoding="utf-8"))


def predict_matrix(model: dict, X: np.ndarray) -> np.ndarray:
    """Predict from a loaded artifact alone: stored feature order, mean, sd and weights.

    Deliberately does not look at the dataset or the training code, so the fresh-process parity
    check below tests the artifact and not the process that wrote it. Arithmetic is kept in float32
    to match `fit_and_score`, so re-scoring the same matrix reproduces the same labels.
    """
    cols = [ALL_FEATURES.index(f) for f in model["features"]]
    Xs = np.asarray(X, dtype=np.float32)[:, cols]
    mu = np.asarray(model["standardisation"]["mean"], dtype=np.float32)
    sd = np.asarray(model["standardisation"]["sd"], dtype=np.float32)
    # Impute before standardising, exactly as the fit did: a stored artifact cannot tell an absent
    # value from an observed one, so the training fold's mean stands in for it. Without this a NaN
    # row standardises to NaN and `argmax` returns class 0 on a row that carries no reading at all.
    Xs = np.where(np.isnan(Xs), mu, Xs)
    Z = (Xs - mu) / sd
    W = np.asarray(model["weights"], dtype=np.float32)
    Zb = np.hstack([Z, np.ones((len(Z), 1), dtype=np.float32)])
    return Zb @ W


def fit_market(name: str, b: dict, train_end: str, horizon: int = 20) -> dict | None:
    """Fit and evaluate one market, or return a limitation dict when it cannot be fitted.

    Returns a tuple-shaped dict with the model, the manifest and the in-process holdout labels, or
    None when the data floor is not met.
    """
    X, y, dates = b["X"], b["y"], b["dates"]
    order = np.argsort(dates, kind="stable")
    X, y, dates = X[order], y[order], dates[order]
    udates = np.unique(dates)
    didx = {d: i for i, d in enumerate(udates)}
    pos = np.asarray([didx[d] for d in dates])
    after = [d for d in udates if d > train_end]
    if not after:
        return {"market": name, "trained": False, "reason": f"no session after {train_end}",
                "rows": int(len(y))}
    cut = didx[after[0]]
    tr = np.where(pos < (cut - EMBARGO))[0]
    te = np.where(dates > train_end)[0]
    if len(tr) < MIN_TRAIN_ROWS or len(te) < MIN_HOLDOUT_ROWS:
        return {"market": name, "trained": False,
                "reason": f"below the data floor (train {len(tr)} < {MIN_TRAIN_ROWS} or "
                          f"holdout {len(te)} < {MIN_HOLDOUT_ROWS})",
                "rows": int(len(y)), "trainRows": int(len(tr)), "holdoutRows": int(len(te))}

    price_cols = [ALL_FEATURES.index(f) for f in FEATURES]
    all_cols = list(range(len(ALL_FEATURES)))
    _, yp_price, _ = fit_and_score(X, y, tr, te, price_cols)
    W, yp, standard = fit_and_score(X, y, tr, te, all_cols)

    yt = y[te]
    m, m_price = metrics(yt, yp), metrics(yt, yp_price)
    majority = float(max((yt == i).mean() for i in range(len(CLASSES))))
    deg = degeneracy(yp, yt)
    ca = collapse_analysis(yt, yp)

    by_year = {}
    for yr in sorted({d[:4] for d in dates[te]}):
        sel = np.asarray([d[:4] == yr for d in dates[te]])
        if sel.sum() < MIN_HOLDOUT_ROWS:
            continue
        by_year[yr] = {"n": int(sel.sum()), "accuracy": metrics(yt[sel], yp[sel])["accuracy"],
                       "priceOnly": metrics(yt[sel], yp_price[sel])["accuracy"],
                       "majority": round(float(max((yt[sel] == i).mean()
                                                   for i in range(len(CLASSES)))), 4)}

    # Both comparisons are now tested rather than compared, because a bare `>` cannot tell a real
    # difference from a small one. See tools/research/significance.py for the measurement that
    # prompted this: Commodity passed the old gate on a 0.0028 lift worth 0.21 standard errors.
    #
    # The two tests are different on purpose. The majority share is a constant derived from the
    # holdout labels, so it is a one-sample proportion test; the price-only model answers the same
    # rows as the candidate, so its errors are correlated with the candidate's and the paired
    # McNemar test on the rows where they disagree is the one that does not understate the noise.
    n_holdout = int(len(yt))
    maj_test = significance.binomial_lift(int((yp == yt).sum()), n_holdout, majority)
    both = np.asarray(yp == yt), np.asarray(yp_price == yt)
    paired = significance.mcnemar(int((both[0] & ~both[1]).sum()),
                                  int((~both[0] & both[1]).sum()))

    checks = {
        # The first two entries keep their old shape -- measured, compared-against, verdict -- so
        # every existing reader of a manifest still finds the numbers where they were. The third
        # is the test, and it is what the verdict now comes from.
        "accuracyAboveHoldoutMajority": [m["accuracy"], round(majority, 4), maj_test["passes"],
                                         maj_test],
        "beatsThePriceOnlyModel": [m["accuracy"], m_price["accuracy"], paired["passes"], paired],
        "notDegenerate": [deg["degenerate"], False, not deg["degenerate"]],
        "bothDirectionsPredicted": [
            {"DOWN": m.get("recall_DOWN"), "UP": m.get("recall_UP")}, 0.2,
            bool((m.get("recall_DOWN") or 0) >= 0.2 and (m.get("recall_UP") or 0) >= 0.2)],
    }
    verdict = "GO" if all(v[2] for v in checks.values()) else "NO-GO"

    # The 20-session family keeps the names it has, so every stored prediction, manifest and
    # audit line that refers to `brain-v4-us` still refers to the same thing. A different horizon
    # is a different task and gets its own family rather than a second model under one name.
    model_version = artifact_name(name, horizon)
    model = {
        "modelVersion": model_version, "kind": "multinomial logistic regression",
        "classes": list(CLASSES), "features": ALL_FEATURES, "featureOrderMatters": True,
        "contextFeatureVersion": CTX_VERSION, "market": name,
        "population": f"market == {name}",
        "missingValueRule": "training-fold mean, then training-fold standardisation",
        "standardisation": {**standard, "fittedOn": "the training span only"},
        "weights": [[float(x) for x in r] for r in W], "weightShape": list(W.shape),
        "biasRow": "the last row of weights is the intercept",
        "hyperparameters": {"seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2},
        "trainedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trainSpan": {"to": str(udates[max(0, cut - EMBARGO - 1)]), "rows": int(len(tr)),
                      "embargoSessionsDropped": EMBARGO},
        "status": verdict, "productionApproved": False,
    }
    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modelVersion": model_version, "market": name,
        "artifact": {"path": None, "sha256": None},  # filled by the caller after writing
        "producedBy": "tools/research/train_v4_markets.py",
        "configurationImportedFrom": "tools/research/baseline_experiment.py",
        "configurationSha256": sha256_file(HERE / "baseline_experiment.py"),
        "contextProducerSha256": sha256_file(ROOT / "tools" / "foundation" / "context_features.py"),
        "repoHead": repo_head(),
        "theOneThingChanged": "the training population; features, target, horizon, split, embargo, "
                              "seed, hyperparameters and imputation are brain-v2-context's",
        "dataset": {"prefix": PREFIX, "market": name,
                    "rows": int(len(y)), "trainRows": int(len(tr)), "holdoutRows": int(len(te)),
                    "distinctDecisionDates": int(len(set(dates.tolist()))),
                    "holdoutDecisionDates": int(len(set(dates[te].tolist()))),
                    "symbols": int(len(b["symbols"])),
                    "assetTypes": dict(b["assetTypes"]),
                    "contextShare": round(b["ctx"] / len(y), 4) if len(y) else 0.0,
                    "rowsCarryingADataQualityFlag": int(b["flagged"])},
        "task": {"label": f"label{horizon}", "classes": list(CLASSES),
                 "horizonSessions": horizon,
                 "labelThresholdPct": md.label_threshold_pct(horizon),
                 "thresholdPct": 2.0, "priceFeatures": list(FEATURES),
                 "contextFeatures": CTX_FEATURES, "featureCount": len(ALL_FEATURES),
                 "outcomeFieldsUsedAsFeatures": 0},
        "hyperparameters": {"seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2,
                            "embargoSessions": EMBARGO},
        "acceptanceCriteria": CRITERIA,
        "criteriaPreRegisteredBeforeRun": False,
        "criteriaProvenance": "written with this trainer in the same run as the numbers, mirrored "
                              "from brain-v2-context and brain-v3-crypto; a pass is diagnostic and "
                              "promotes nothing -- a frozen candidate's prospective stream decides",
        "criteriaMet": checks,
        # The inference tool refuses to predict when a feature the model usually SAW is missing, so
        # each market's own experience of a column has to travel with the artifact. Read over this
        # market's rows, which is the only population the candidate knows.
        "nullShareByFeature": {ALL_FEATURES[i]: round(float(np.isnan(X[:, i]).mean()), 4)
                               for i in range(len(ALL_FEATURES))},
        "evaluation": {
            "holdout": {"from": str(dates[te][0]), "to": str(dates[te][-1]), "rows": m["n"],
                        "effectiveIndependentWindows": m["effectiveIndependentWindows"],
                        "pristine": False,
                        "exposure": "2026-01-01..2026-09-25 has been scored by the baseline "
                                    "experiment, the balanced experiment, brain-v2-context and "
                                    "brain-v3-crypto; diagnostic, never independent"},
            "accuracy": m["accuracy"], "holdoutMajorityShare": round(majority, 4),
            "marginOverHoldoutMajority": round(m["accuracy"] - majority, 4),
            "priceOnlyAccuracy": m_price["accuracy"],
            "marginOverPriceOnly": round(m["accuracy"] - m_price["accuracy"], 4),
            "perClass": {c: {"recall": m.get(f"recall_{c}"), "precision": m.get(f"precision_{c}")}
                         for c in CLASSES},
            "predictedMix": m["predictedMix"], "actualMix": m["actualMix"],
            "confusion": confusion(yt, yp), "degeneracy": deg,
            "collapseAnalysis": ca, "byYear": by_year},
        "verdict": verdict, "eligibleForPromotion": False,
        "promotionRule": "NOT promoted on this evaluation under any outcome; a pass licenses "
                         "freezing the candidate and starting a prospective stream",
        "limitations": [
            "direction only; no execution-cost, spread or borrow data exists, so nothing here is a "
            "profitability claim.",
            "the effective sample is rows / 20; the row count is not the sample size.",
            "survivorship: the universe is today's registered assets.",
            "the holdout is not pristine; see evaluation.holdout.exposure.",
            "an absent feature takes the training fold's mean; the model cannot tell an imputed "
            "value from an observed one.",
        ] + ([f"thin population: {len(b['symbols'])} symbols, so a pass could be a few names' "
              "behaviour rather than a market reading."] if len(b["symbols"]) < 20 else []),
    }
    return {"market": name, "trained": True, "model": model, "manifest": manifest,
            "checks": checks, "verdict": verdict, "accuracy": m["accuracy"],
            "yp": yp, "yt": yt, "Xte": X[te], "collapse": ca, "metrics": m}


def verify_written(brain_root: Path) -> int:
    """Load every written artifact from disk and re-predict a fixed matrix, twice.

    A fresh-process smoke test: it proves the artifact is loadable with nothing but its own file,
    that its feature and class lists match the contract, and that the same input gives the same
    answer on a second call. It needs no dataset, so it can run anywhere the artifacts do.
    """
    dirs = sorted(p for p in brain_root.glob("brain-v4-*") if (p / "model.json").exists())
    if not dirs:
        print("no brain-v4-* artifacts to verify")
        return 0
    probe = np.linspace(-1.0, 1.0, 7 * len(ALL_FEATURES), dtype=np.float32).reshape(7, -1)
    problems = 0
    for d in dirs:
        m = load_model(d)
        ok = (list(m["features"]) == list(ALL_FEATURES) and list(m["classes"]) == list(CLASSES)
              and len(m["weights"]) == len(ALL_FEATURES) + 1)
        a = predict_matrix(m, probe).argmax(axis=1)
        b = predict_matrix(m, probe).argmax(axis=1)
        deterministic = bool(np.array_equal(a, b))
        if not (ok and deterministic):
            problems += 1
        print(f"  {m['modelVersion']:<16} features_ok={ok} deterministic={deterministic} "
              f"status={m.get('status')}")
    print(f"verified {len(dirs)} artifact(s); problems {problems}")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(DEFAULT_DS))
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--brain", default=str(BRAIN_ROOT))
    ap.add_argument("--train-end", default=TRAIN_END)
    ap.add_argument("--horizon", type=int, default=20, choices=sorted(md.HORIZONS),
                    help="forward sessions the candidate is trained to call (default 20). A "
                         "shorter horizon writes its own brain-v5-h<N>-<market> family and "
                         "leaves the 20-session artifacts untouched")
    ap.add_argument("--verify", action="store_true",
                    help="load each written brain-v4-* artifact and re-predict a fixed matrix")
    a = ap.parse_args()

    brain_root = Path(a.brain)
    if a.verify:
        return verify_written(brain_root)

    ds = Path(a.dataset)
    print(f"loading {ds}")
    per = load(ds, horizon=a.horizon)
    total = sum(b["rows"] for b in per.values())
    print(f"usable rows: {total:,}  across {len(MARKETS)} markets")

    results, limitations = {}, {}
    for name in MARKETS:
        b = per[name]
        print(f"\n{name}: {b['rows']:,} rows, {len(b['symbols'])} symbols, "
              f"context {b['ctx']:,}")
        res = fit_market(name, b, a.train_end, a.horizon)
        if not res["trained"]:
            limitations[name] = res
            print(f"  NOT TRAINED - {res['reason']} (rows {res.get('rows')})")
            continue
        brain_dir = brain_root / artifact_name(name, a.horizon)
        brain_dir.mkdir(parents=True, exist_ok=True)
        model_path = brain_dir / "model.json"
        text = json.dumps(res["model"], indent=1, sort_keys=True)
        # newline="" so the bytes on disk are exactly utf-8 of `text` on every platform: the digest
        # below is over the file, and a Windows newline translation would make it platform-dependent.
        model_path.write_text(text, encoding="utf-8", newline="")
        res["manifest"]["artifact"] = {
            "path": str(model_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(model_path)}
        (brain_dir / "manifest.json").write_text(json.dumps(res["manifest"], indent=1),
                                                 encoding="utf-8")
        loaded = load_model(brain_dir)
        yp_fresh = predict_matrix(loaded, res["Xte"]).argmax(axis=1)
        parity = float((yp_fresh == res["yp"]).mean())
        res["freshProcessParity"] = parity
        results[name] = res
        mm = res["metrics"]
        ca = res["collapse"]
        ev = res["manifest"]["evaluation"]
        print(f"  accuracy {mm['accuracy']:.4f}  majority {ev['holdoutMajorityShare']:.4f}  "
              f"priceOnly {ev['priceOnlyAccuracy']:.4f}  verdict {res['verdict']}")
        print(f"  predicted mix {mm['predictedMix']}  collapsed={ca['collapsed']}  "
              f"fresh-process parity {parity:.4f}")
        if parity < 0.999:
            print(f"  WARNING: loaded artifact disagrees with the fitted model on "
                  f"{(1 - parity) * 100:.2f}% of holdout rows")

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    aggregate = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "producedBy": "tools/research/train_v4_markets.py",
        "trainEnd": a.train_end, "embargoSessions": EMBARGO,
        "horizonSessions": a.horizon,
        "labelThresholdPct": md.label_threshold_pct(a.horizon),
        "markets": {
            name: ({
                "trained": True, "modelVersion": r["model"]["modelVersion"],
                "artifact": r["manifest"]["artifact"],
                "accuracy": r["metrics"]["accuracy"],
                "holdoutMajorityShare": r["manifest"]["evaluation"]["holdoutMajorityShare"],
                "priceOnlyAccuracy": r["manifest"]["evaluation"]["priceOnlyAccuracy"],
                "verdict": r["verdict"], "checks": r["checks"],
                "predictedMix": r["metrics"]["predictedMix"],
                "collapse": r["collapse"], "freshProcessParity": r["freshProcessParity"],
            } if r["trained"] else {"trained": False, "reason": r["reason"], "rows": r["rows"]})
            for name, r in {**limitations, **results}.items()
        },
        "promotionRule": "no market is promoted on this evaluation; see each manifest.",
    }
    # One file per horizon. The 20-session run keeps writing `brain_v4_markets.json`, which the
    # daily audit, brain.md and every earlier checkpoint refer to by name; a shorter horizon is a
    # separate evaluation and must not overwrite the evidence for a different task.
    agg_name = ("brain_v4_markets.json" if a.horizon == 20
                else f"brain_v5_h{a.horizon}_markets.json")
    (out_dir / agg_name).write_text(json.dumps(aggregate, indent=1),
                                                   encoding="utf-8")

    print("\n== per-market summary ==")
    for name in MARKETS:
        r = results.get(name)
        if not r:
            print(f"  {name:<10} NOT TRAINED - {limitations[name]['reason']}")
            continue
        print(f"  {name:<10} {r['model']['modelVersion']:<16} acc {r['accuracy']:.4f}  "
              f"{r['verdict']}  collapsed={r['collapse']['collapsed']}")
    # `agg_name`, not the literal: a 1-session run reported writing `brain_v4_markets.json` while
    # correctly writing `brain_v5_h1_markets.json`, and a run that misreports where its evidence
    # went is a run whose evidence nobody can find.
    print(f"\nwrote artifacts under {brain_root} and {out_dir / agg_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

