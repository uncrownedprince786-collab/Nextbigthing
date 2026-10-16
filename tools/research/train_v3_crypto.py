"""Brain V3: a crypto-only candidate, pre-registered before it was run.

    python tools/research/train_v3_crypto.py [--cache FILE] [--out DIR]

The hypothesis, and why it is not just "crypto had the best number"
--------------------------------------------------------------------
`brain-v2-context` is a recorded NO-GO: 0.4167 against a 0.4388 largest-class share, predicting UP
on 92.19% of a holdout that was 38.67% UP. On the crypto slice of that same holdout it behaved
differently, and `crypto_evidence.py` was written to find out whether that difference was an
artefact before anything was registered. It is not:

    crypto holdout class share   DOWN 0.4723   FLAT 0.1234   UP 0.4043
    always-UP baseline           0.4043
    brain-v2-context on crypto   0.5143, +0.1100 over always-UP
    its predicted mix there      DOWN 6,180   FLAT 36   UP 13,004
    its DOWN recall there        0.4173, against 0.0826 across the whole holdout

So on crypto the multi-market model is **not** collapsed, the majority class is **DOWN** rather
than UP, and it still beats both the always-UP baseline and the majority class. A model that
degenerates everywhere else and discriminates here is evidence that the crypto rows carry signal
the rest of the population is drowning -- 93,452 crypto rows against 1,055,429 total, so the
multi-market fit is dominated by equities with different dynamics.

**The hypothesis**: a model trained on crypto alone will read crypto better than a model trained
on everything and evaluated on crypto.

**The one thing changed** is the training population. Features, target, horizon, split, embargo,
seed, hyperparameters and the imputation rule are all `brain-v2-context`'s, imported rather than
restated, so a difference in the result is attributable to the population and not to a knob.

What a pass here does and does not mean
----------------------------------------
The evaluation window, 2026-01-01 to 2026-09-25, has been scored before -- by the baseline
experiment, the balanced experiment and `brain-v2-context`. **It is diagnostic and never
independent.** Passing every criterion below therefore does **not** promote anything. It licenses
exactly one thing: freezing this candidate and starting its own prospective prediction stream,
with promotion decided later on matured forward outcomes against these same criteria.

Failing is a result, recorded and kept. It is not a reason to adjust a threshold and re-run.
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

from baseline_experiment import CLASSES, EMBARGO, FEATURES, L2, LR, SEED, STEPS, fit_softmax, metrics, predict  # noqa: E402
from context_features import VERSION as CTX_VERSION  # noqa: E402
from train_v1 import degeneracy, repo_head, sha256_file, sha256_text  # noqa: E402
from train_v2_context import ALL_FEATURES, CTX_FEATURES, confusion, fit_and_score  # noqa: E402

CACHE = ROOT / ".cache" / "foundation" / "crypto_slice.npz"
OUT_DIR = ROOT / "data" / "foundation" / "dataset"
BRAIN_DIR = ROOT / "data" / "foundation" / "brain" / "brain-v3-crypto"
TRAIN_END = "2025-12-31"
MODEL_VERSION = "brain-v3-crypto"

#: The numbers this candidate must beat, measured from the artifacts before this file was run and
#: recorded here so they cannot drift. `crypto_evidence.json` holds their derivation.
BASELINES = {
    "holdoutMajorityClass": {"class": "DOWN", "accuracy": 0.4723},
    "alwaysUp": 0.4043,
    "multiMarketOnCrypto": 0.5143,          # brain-v2-context, same rows, same window
    "priceOnlyCrypto": "fitted in this run on the same rows, 15 features",
}

#: Fixed before the run. Accuracy alone is not enough: the failure this project keeps meeting is a
#: model that scores by saying one word, so two of the four criteria are about the distribution of
#: the predictions rather than their average correctness.
CRITERIA = {
    "accuracyAboveHoldoutMajority": "strictly above 0.4723, the holdout's largest class (DOWN)",
    "beatsTheMultiMarketModelOnCrypto": "strictly above 0.5143, brain-v2-context on these rows",
    "notDegenerate": "no predicted class exceeds 0.7 of the holdout while being under half of it",
    "bothDirectionsPredicted": "recall at least 0.25 for DOWN and at least 0.25 for UP, so the "
                               "model is reading direction and not leaning on one side",
    "setBefore": "any number from this run was seen; see the commit that introduced this file",
}

#: Even if every criterion passes.
PROMOTION = (
    "NOT promoted on this evaluation under any outcome. The window 2026-01-01..2026-09-25 has been "
    "scored by the baseline experiment, the balanced experiment and brain-v2-context, so it is "
    "diagnostic and never independent. A pass licenses freezing the candidate and starting its own "
    "prospective prediction stream; promotion is decided later on matured forward outcomes against "
    "these same criteria."
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--brain", default=str(BRAIN_DIR))
    a = ap.parse_args()

    z = np.load(a.cache, allow_pickle=True)
    X, y, dates, syms = z["X"], z["y"], z["dates"], z["syms"]
    order = np.argsort(dates, kind="stable")
    X, y, dates, syms = X[order], y[order], dates[order], syms[order]
    print(f"crypto rows: {len(X):,}  symbols: {len(set(syms.tolist()))}")

    udates = np.unique(dates)
    didx = {d: i for i, d in enumerate(udates)}
    pos = np.asarray([didx[d] for d in dates])
    after = [d for d in udates if d > TRAIN_END]
    if not after:
        raise SystemExit("no sessions after the cutoff")
    cut = didx[after[0]]
    tr = np.where(pos < (cut - EMBARGO))[0]
    te = np.where(dates > TRAIN_END)[0]
    print(f"train {len(tr):,} to {udates[max(0, cut - EMBARGO - 1)]}  "
          f"holdout {len(te):,} from {dates[te][0]} to {dates[te][-1]}")

    price_cols = [ALL_FEATURES.index(f) for f in FEATURES]
    all_cols = list(range(len(ALL_FEATURES)))
    _, yp_price, _ = fit_and_score(X, y, tr, te, price_cols)
    W, yp, standard = fit_and_score(X, y, tr, te, all_cols)

    yt = y[te]
    m, m_price = metrics(yt, yp), metrics(yt, yp_price)
    majority = float(max((yt == i).mean() for i in range(len(CLASSES))))
    deg = degeneracy(yp, yt)
    rec = {c: m.get(f"recall_{c}") for c in CLASSES}

    checks = {
        "accuracyAboveHoldoutMajority": [m["accuracy"], BASELINES["holdoutMajorityClass"]["accuracy"],
                                         bool(m["accuracy"] > BASELINES["holdoutMajorityClass"]["accuracy"])],
        "beatsTheMultiMarketModelOnCrypto": [m["accuracy"], BASELINES["multiMarketOnCrypto"],
                                             bool(m["accuracy"] > BASELINES["multiMarketOnCrypto"])],
        "notDegenerate": [deg["degenerate"], False, not deg["degenerate"]],
        "bothDirectionsPredicted": [{"DOWN": rec["DOWN"], "UP": rec["UP"]}, 0.25,
                                    bool((rec["DOWN"] or 0) >= 0.25 and (rec["UP"] or 0) >= 0.25)],
    }
    passed = all(v[2] for v in checks.values())
    verdict = "GO" if passed else "NO-GO"

    by_year = {}
    for yr in sorted({d[:4] for d in dates[te]}):
        sel = np.asarray([d[:4] == yr for d in dates[te]])
        if sel.sum() < 200:
            continue
        by_year[yr] = {"n": int(sel.sum()), "accuracy": metrics(yt[sel], yp[sel])["accuracy"]}

    Path(a.brain).mkdir(parents=True, exist_ok=True)
    model_path = Path(a.brain) / "model.json"
    model = {
        "modelVersion": MODEL_VERSION, "kind": "multinomial logistic regression",
        "classes": list(CLASSES), "features": ALL_FEATURES, "featureOrderMatters": True,
        "contextFeatureVersion": CTX_VERSION,
        "population": "assetType == 'crypto' only",
        "missingValueRule": "training-fold mean, then training-fold standardisation",
        "standardisation": {**standard, "fittedOn": "the training span only"},
        "weights": [[float(x) for x in r] for r in W], "weightShape": list(W.shape),
        "biasRow": "the last row of weights is the intercept",
        "hyperparameters": {"seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2},
        "trainedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trainSpan": {"to": str(udates[max(0, cut - EMBARGO - 1)]), "rows": len(tr),
                      "embargoSessionsDropped": EMBARGO},
        "status": verdict, "productionApproved": False,
    }
    text = json.dumps(model, indent=1, sort_keys=True)
    model_path.write_text(text, encoding="utf-8")

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modelVersion": MODEL_VERSION,
        "artifact": {"path": str(model_path.relative_to(ROOT)).replace("\\", "/"),
                     "sha256": sha256_text(text)},
        "producedBy": "tools/research/train_v3_crypto.py",
        "configurationImportedFrom": "tools/research/baseline_experiment.py",
        "configurationSha256": sha256_file(HERE / "baseline_experiment.py"),
        "contextProducerSha256": sha256_file(ROOT / "tools" / "foundation" / "context_features.py"),
        "repoHead": repo_head(),
        "hypothesis": "a model trained on crypto alone reads crypto better than a model trained "
                      "on everything and evaluated on crypto",
        "theOneThingChanged": "the training population; features, target, horizon, split, embargo, "
                              "seed, hyperparameters and imputation are brain-v2-context's",
        "dataset": {"version": "examples-v4-context-2026-10-16-local",
                    "slice": "assetType == 'crypto'", "cache": str(a.cache),
                    "rowsTotal": int(len(X)), "symbols": int(len(set(syms.tolist()))),
                    "trainRows": int(len(tr)), "holdoutRows": int(len(te))},
        "task": {"label": "label20", "classes": list(CLASSES),
                 "horizonSessions": 20, "thresholdPct": 2.0,
                 "priceFeatures": list(FEATURES), "contextFeatures": CTX_FEATURES,
                 "featureCount": len(ALL_FEATURES), "outcomeFieldsUsedAsFeatures": 0},
        "hyperparameters": {"seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2,
                            "embargoSessions": EMBARGO},
        "baselines": BASELINES,
        "preDeclaredCriteria": CRITERIA,
        "criteriaMet": checks,
        "promotionRule": PROMOTION,
        "evaluation": {
            "holdout": {"from": str(dates[te][0]), "to": str(dates[te][-1]), "rows": m["n"],
                        "effectiveIndependentWindows": m["effectiveIndependentWindows"],
                        "distinctDecisionDates": int(len(set(dates[te].tolist()))),
                        "pristine": False,
                        "exposure": "scored by the baseline experiment, the balanced experiment "
                                    "and brain-v2-context; diagnostic, never independent"},
            "accuracy": m["accuracy"],
            "holdoutMajorityShare": round(majority, 4),
            "marginOverHoldoutMajority": round(m["accuracy"] - majority, 4),
            "marginOverMultiMarket": round(m["accuracy"] - BASELINES["multiMarketOnCrypto"], 4),
            "priceOnlyCrypto": m_price["accuracy"],
            "marginOverPriceOnlyCrypto": round(m["accuracy"] - m_price["accuracy"], 4),
            "perClass": {c: {"recall": m.get(f"recall_{c}"), "precision": m.get(f"precision_{c}")}
                         for c in CLASSES},
            "predictedMix": m["predictedMix"], "actualMix": m["actualMix"],
            "confusion": confusion(yt, yp), "degeneracy": deg, "byYear": by_year,
        },
        "verdict": verdict,
        "eligibleForPromotion": False,
        "limitations": [
            "direction only; no execution-cost, spread or borrow data exists, so nothing here is "
            "a profitability claim and no drawdown or turnover figure is given.",
            "the effective sample is rows / 20; the row count is not the sample size.",
            "crypto trades every day, so a 20-session window is 20 calendar days here and about "
            "28 for equities; the horizons are not the same length in wall-clock time.",
            "the holdout is not pristine; see evaluation.holdout.exposure.",
        ],
    }
    (Path(a.brain) / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "brain_v3_crypto_training.json").write_text(json.dumps(manifest, indent=1),
                                                               encoding="utf-8")

    print(f"\ncrypto candidate   {m['accuracy']:.4f}")
    print(f"price-only crypto  {m_price['accuracy']:.4f}")
    print(f"multi-market here  {BASELINES['multiMarketOnCrypto']:.4f}")
    print(f"holdout majority   {majority:.4f}   always-UP {BASELINES['alwaysUp']:.4f}")
    print(f"predicted mix {m['predictedMix']}  recall {rec}")
    for k, v in checks.items():
        print(f"  {'ok ' if v[2] else 'FAIL'} {k}: {v[0]} vs {v[1]}")
    print(f"\nVERDICT {verdict}; eligible for promotion: False")
    print(f"wrote {model_path} (sha256 {sha256_text(text)[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
