"""Brain V2: the same model, the same split, and context features added to the input.

    python tools/research/train_v2_context.py [--dataset DIR] [--out DIR] [--train-end DATE]

The experiment, stated before it was run
----------------------------------------
`brain-v1` learned nothing from fifteen price and volume fields: 0.4107 against a 0.4388
largest-class share, collapsed onto UP. The open question was never "is that model good" -- it is
recorded as NO-GO -- but **whether the information was missing or merely absent from the input**.
Six context layers existed, were point-in-time aware, and reached no feature vector.

So this run changes exactly one thing. Two models are fitted **in the same process, on the same
rows, with the same split, seed and hyperparameters**, differing only in their columns:

  * **price-only** -- the fifteen `pit.f` fields, the baseline's own list, imported unchanged.
  * **context** -- those fifteen plus the twenty-nine of `pit.ctx`.

Fitting both here rather than comparing against the recorded 0.4107 is deliberate: the imputation
below differs from the baseline experiment's, and a comparison where two things changed answers
nothing. The recorded figure is still reported beside them, as the historical result it is.

Missing values
--------------
`baseline_experiment.load` substitutes 0.0 for an absent field, which after standardisation is not
"no information" but a displacement whose size depends on the column. Context is absent far more
often than price is -- `ctx_priorMedianFwd20` is null on roughly 40% of rows -- so that treatment
would have handed the context model a column of loud, meaningless signal. Here an absent value
takes the **training fold's mean**, which standardises to exactly zero, and the null share of every
feature is recorded. Both models get the same treatment, so the comparison survives it.

This is an imputation and it is visible: a model cannot tell an imputed value from an observed
one, which is why `ctx_*` features carrying their own age and count fields matters -- those say how
stale and how sparse the evidence was, in columns the model can actually use.

What a result here can and cannot mean
--------------------------------------
Direction only. No execution-cost, spread or borrow data exists for any market in this project, so
nothing here is a profitability claim and no drawdown or turnover figure would mean anything
attached to a three-class label. The holdout is **not pristine** -- every calendar year in this
dataset has been scored by a recorded experiment -- so a win here would be a reason to design a
clean test, not a reason to promote anything. The criteria below were fixed before the run and are
not to be moved afterwards.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from baseline_experiment import CLASSES, EMBARGO, FEATURES, L2, LR, SEED, STEPS, fit_softmax, metrics, predict  # noqa: E402
from context_features import VERSION as CTX_VERSION, ContextSource  # noqa: E402
from train_v1 import degeneracy, repo_head, sha256_file, sha256_text  # noqa: E402

DEFAULT_DS = ROOT / ".cache" / "foundation" / "dataset_v4"
OUT_DIR = ROOT / "data" / "foundation" / "dataset"
BRAIN_DIR = ROOT / "data" / "foundation" / "brain" / "brain-v2-context"
TRAIN_END = "2025-12-31"
MODEL_VERSION = "brain-v2-context"

CTX_FEATURES = ContextSource.feature_names()
ALL_FEATURES = list(FEATURES) + list(CTX_FEATURES)

#: Fixed before the run, and not to be moved after seeing a number. The first three are the
#: criteria `brain-v1` was judged by, restated so a passing score means the same thing it did
#: then. The fourth is this experiment's own question, and it is the one that can only be
#: answered by the pair fitted here.
CRITERIA = {
    "accuracyAboveHoldoutMajority": "strictly above the holdout's largest-class share",
    "notDegenerate": "no predicted class exceeds 0.7 of the holdout while being under half of it",
    "adverseClassIsPredicted": "recall for DOWN is at least 0.2",
    "beatsThePriceOnlyModel": "accuracy strictly above the price-only model fitted here on the "
                              "same rows, same split, same seed",
    "setBefore": "any number from this run was seen",
}


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load(ds: Path, prefix: str = "examples-v4-context"):
    """Rows with price features, a matured label, and their context block if one is present.

    A missing value is carried as `np.nan` rather than 0.0; the fold's own mean replaces it
    later, after the split, so no test-fold value ever informs an imputation.
    """
    X, y, dates, cls, has_ctx = [], [], [], [], []
    files = sorted(ds.glob(f"{prefix}-*.jsonl.gz"))
    if not files:
        raise SystemExit(f"no {prefix}-*.jsonl.gz in {ds}")
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                pit = r.get("pit") or {}
                p, o = pit.get("f"), r.get("outcome") or {}
                if not p or o.get("label20") not in CLASSES or not o.get("mature20"):
                    continue
                c = (pit.get("ctx") or {}).get("f") or {}
                row = []
                ok = True
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
                y.append(CLASSES.index(o["label20"]))
                dates.append(r["asOf"])
                t = r["assetType"]
                cls.append("PSX" if r.get("market") == "PK" else
                           "forex" if t == "forex" else "crypto" if t == "crypto" else
                           "commodity" if t == "commodity" else "US")
                has_ctx.append(bool(c))
    return (np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.int64),
            np.asarray(dates), np.asarray(cls), np.asarray(has_ctx))


def fit_and_score(X, y, tr, te, cols: list[int]) -> tuple[np.ndarray, np.ndarray, dict]:
    """One model over `cols`. Imputation and standardisation come from the training fold alone."""
    Xtr, Xte = X[np.ix_(tr, cols)], X[np.ix_(te, cols)]
    mu = np.nanmean(Xtr, axis=0)
    mu = np.where(np.isnan(mu), 0.0, mu)          # a column absent in the whole fold is zero
    Xtr = np.where(np.isnan(Xtr), mu, Xtr)
    Xte = np.where(np.isnan(Xte), mu, Xte)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd
    W = fit_softmax(Ztr, y[tr])
    return W, predict(W, Zte), {"mean": [float(v) for v in mu], "sd": [float(v) for v in sd]}


def confusion(yt, yp) -> dict:
    return {a: {b: int(((yt == i) & (yp == j)).sum()) for j, b in enumerate(CLASSES)}
            for i, a in enumerate(CLASSES)}


def main() -> int:
    ds = Path(arg("--dataset", DEFAULT_DS))
    out_dir = Path(arg("--out", OUT_DIR))
    brain_dir = Path(arg("--brain", BRAIN_DIR))
    train_end = arg("--train-end", TRAIN_END)

    print(f"loading {ds}")
    X, y, dates, cls, has_ctx = load(ds)
    print(f"usable examples: {len(X):,}  columns: {X.shape[1]}  "
          f"with a context block: {int(has_ctx.sum()):,} ({has_ctx.mean():.4f})")
    if not len(X):
        raise SystemExit("no usable examples")

    order = np.argsort(dates, kind="stable")
    X, y, dates, cls, has_ctx = X[order], y[order], dates[order], cls[order], has_ctx[order]
    udates = np.unique(dates)
    didx = {d: i for i, d in enumerate(udates)}
    pos = np.asarray([didx[d] for d in dates])

    after = [d for d in udates if d > train_end]
    if not after:
        raise SystemExit(f"no sessions after {train_end}")
    cut = didx[after[0]]
    tr = np.where(pos < (cut - EMBARGO))[0]
    te = np.where(dates > train_end)[0]
    print(f"train {len(tr):,} to {udates[max(0, cut - EMBARGO - 1)]}  "
          f"holdout {len(te):,} from {dates[te][0]} to {dates[te][-1]}")

    price_cols = [ALL_FEATURES.index(f) for f in FEATURES]
    all_cols = list(range(len(ALL_FEATURES)))
    _, yp_price, _ = fit_and_score(X, y, tr, te, price_cols)
    W, yp_ctx, standard = fit_and_score(X, y, tr, te, all_cols)

    yt = y[te]
    m_ctx, m_price = metrics(yt, yp_ctx), metrics(yt, yp_price)
    majority = float(max((yt == i).mean() for i in range(len(CLASSES))))
    train_major = int(np.bincount(y[tr], minlength=len(CLASSES)).argmax())
    const = float((yt == train_major).mean())
    deg = degeneracy(yp_ctx, yt)
    recall_down = m_ctx.get(f"recall_{CLASSES[0]}")

    checks = {
        "accuracyAboveHoldoutMajority": [m_ctx["accuracy"], round(majority, 4),
                                         bool(m_ctx["accuracy"] > majority)],
        "notDegenerate": [deg["degenerate"], False, not deg["degenerate"]],
        "adverseClassIsPredicted": [recall_down, 0.2, bool((recall_down or 0) >= 0.2)],
        "beatsThePriceOnlyModel": [m_ctx["accuracy"], m_price["accuracy"],
                                   bool(m_ctx["accuracy"] > m_price["accuracy"])],
    }
    passed = all(v[2] for v in checks.values())
    verdict = "GO" if passed else "NO-GO"

    by_year, by_market = {}, {}
    for yr in sorted({d[:4] for d in dates[te]}):
        sel = np.asarray([d[:4] == yr for d in dates[te]])
        if sel.sum() < 200:
            continue
        by_year[yr] = {"n": int(sel.sum()), "context": metrics(yt[sel], yp_ctx[sel])["accuracy"],
                       "priceOnly": metrics(yt[sel], yp_price[sel])["accuracy"],
                       "majority": round(float(max((yt[sel] == i).mean()
                                                   for i in range(len(CLASSES)))), 4)}
    for mk in sorted(set(cls[te])):
        sel = cls[te] == mk
        if sel.sum() < 200:
            continue
        by_market[mk] = {"n": int(sel.sum()), "context": metrics(yt[sel], yp_ctx[sel])["accuracy"],
                         "priceOnly": metrics(yt[sel], yp_price[sel])["accuracy"],
                         "majority": round(float(max((yt[sel] == i).mean()
                                                     for i in range(len(CLASSES)))), 4)}

    nulls = {ALL_FEATURES[i]: round(float(np.isnan(X[:, i]).mean()), 4)
             for i in range(len(ALL_FEATURES))}

    brain_dir.mkdir(parents=True, exist_ok=True)
    model_path = brain_dir / "model.json"
    model = {
        "modelVersion": MODEL_VERSION,
        "kind": "multinomial logistic regression",
        "classes": list(CLASSES),
        "features": ALL_FEATURES,
        "featureOrderMatters": True,
        "contextFeatureVersion": CTX_VERSION,
        "missingValueRule": "training-fold mean, then training-fold standardisation",
        "standardisation": {**standard, "fittedOn": "the training span only"},
        "weights": [[float(x) for x in row] for row in W],
        "weightShape": list(W.shape),
        "biasRow": "the last row of weights is the intercept",
        "hyperparameters": {"seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2},
        "trainedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trainSpan": {"to": str(udates[max(0, cut - EMBARGO - 1)]), "rows": len(tr),
                      "embargoSessionsDropped": EMBARGO},
        "status": verdict,
        "productionApproved": False,
    }
    text = json.dumps(model, indent=1, sort_keys=True)
    model_path.write_text(text, encoding="utf-8")
    model_sha = sha256_text(text)

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modelVersion": MODEL_VERSION,
        "artifact": {"path": str(model_path.relative_to(ROOT)).replace("\\", "/"),
                     "sha256": model_sha},
        "producedBy": "tools/research/train_v2_context.py",
        "configurationImportedFrom": "tools/research/baseline_experiment.py",
        "configurationSha256": sha256_file(HERE / "baseline_experiment.py"),
        "contextProducerSha256": sha256_file(ROOT / "tools" / "foundation" / "context_features.py"),
        "repoHead": repo_head(),
        "dataset": {"dir": str(ds), "prefix": "examples-v4-context",
                    "rowsUsed": int(len(X)), "rowsWithContextBlock": int(has_ctx.sum()),
                    "contextShare": round(float(has_ctx.mean()), 4)},
        "task": {"label": "label20", "classes": list(CLASSES),
                 "priceFeatures": list(FEATURES), "contextFeatures": CTX_FEATURES,
                 "featureCount": len(ALL_FEATURES), "outcomeFieldsUsedAsFeatures": 0},
        "hyperparameters": {"seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2,
                            "embargoSessions": EMBARGO},
        "preDeclaredCriteria": CRITERIA,
        "criteriaMet": checks,
        "evaluation": {
            "holdout": {"from": str(dates[te][0]), "to": str(dates[te][-1]), "rows": m_ctx["n"],
                        "effectiveIndependentWindows": m_ctx["effectiveIndependentWindows"],
                        "pristine": False,
                        "exposure": "every calendar year in this dataset has been scored by a "
                                    "recorded experiment, so this is a comparison between two "
                                    "models and not an independent validation of either."},
            "context": {"accuracy": m_ctx["accuracy"],
                        "perClass": {c: {"recall": m_ctx.get(f"recall_{c}"),
                                         "precision": m_ctx.get(f"precision_{c}")}
                                     for c in CLASSES},
                        "predictedMix": m_ctx["predictedMix"], "actualMix": m_ctx["actualMix"],
                        "confusion": confusion(yt, yp_ctx), "degeneracy": deg},
            "priceOnly": {"accuracy": m_price["accuracy"],
                          "perClass": {c: {"recall": m_price.get(f"recall_{c}"),
                                           "precision": m_price.get(f"precision_{c}")}
                                       for c in CLASSES},
                          "predictedMix": m_price["predictedMix"],
                          "confusion": confusion(yt, yp_price),
                          "degeneracy": degeneracy(yp_price, yt)},
            "contextMinusPriceOnly": round(m_ctx["accuracy"] - m_price["accuracy"], 4),
            "holdoutMajorityShare": round(majority, 4),
            "marginOverHoldoutMajority": round(m_ctx["accuracy"] - majority, 4),
            "trainMajorityConstantOnHoldout": round(const, 4),
            "byYear": by_year, "byMarket": by_market,
            "recordedBrainV1ForContext": {
                "accuracy": 0.4107, "majority": 0.4388, "margin": -0.0281,
                "note": "a different imputation rule and a different dataset build; reported as "
                        "the historical result it is, not as this run's baseline."},
        },
        "nullShareByFeature": nulls,
        "verdict": verdict,
        "eligibleForPromotion": False,
        "limitations": [
            "direction only. No execution cost, spread or borrow data exists for any market, so "
            "nothing here is a profitability claim and a drawdown or turnover figure attached to "
            "a three-class label would not mean anything.",
            "the effective sample is rows / 20; the row count is not the sample size.",
            "survivorship: the universe is today's registered assets.",
            "an absent feature takes the training fold's mean; a model cannot tell an imputed "
            "value from an observed one, which is why the age and count columns matter.",
            "the holdout is not pristine; see evaluation.holdout.exposure.",
        ],
    }
    (brain_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "brain_v2_context_training.json").write_text(json.dumps(manifest, indent=1),
                                                            encoding="utf-8")

    print(f"\ncontext   {m_ctx['accuracy']:.4f}")
    print(f"priceOnly {m_price['accuracy']:.4f}   difference {m_ctx['accuracy'] - m_price['accuracy']:+.4f}")
    print(f"majority  {majority:.4f}   margin {m_ctx['accuracy'] - majority:+.4f}")
    for k, v in checks.items():
        print(f"  {'ok ' if v[2] else 'FAIL'} {k}: {v[0]} vs {v[1]}")
    print(f"\nVERDICT {verdict}; eligible for promotion: False")
    print(f"wrote {model_path} (sha256 {model_sha[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
