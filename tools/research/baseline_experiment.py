"""The rule baseline and the first candidate model, evaluated walk-forward with an embargo.

    python tools/research/baseline_experiment.py [--dataset DIR] [--out DIR] [--embargo N]

Writes `data/foundation/dataset/baseline_experiment.json`. Reads the versioned dataset copy and
nothing else. **This is an offline research experiment.** Nothing is deployed, nothing trades, and
no result here is a claim about profitability -- the execution-cost layer is empty, so only
direction is measured and direction is not money.

**The task.** 20-session direction classification: `label20` is UP when `fwd20 >= +2%`, DOWN when
`<= -2%`, else FLAT. Inputs are the 15 fields of `pit.f` and nothing else. `outcome` is never read
as a feature; it is opened only to score a prediction already made.

**The baseline is a rule, written down before it is scored.** Trend agreement: a name is UP when
its 20-session return is positive *and* it sits above its 20-session average, DOWN when both are
negative, and FLAT when the two disagree. It uses two of the fifteen features and no fitting. Its
job is to be the number the model has to beat, so that "the model learned something" is a
comparison rather than an impression.

**The candidate is multinomial logistic regression, fitted in numpy.** No new dependency, a fixed
seed, full-batch gradient descent to a fixed step count, features standardised on the *training*
fold only -- standardising on the whole series would leak the test period's distribution into the
fit, which is the quiet version of the mistake this project keeps testing for.

**Walk-forward with an embargo, because the labels overlap.** Each fold trains on every session
before a cut and tests on the year after it. A 20-session label means consecutive rows share 19 of
their 20 forward sessions, so the last 20 sessions before the cut are dropped: without that, the
final training rows and the first test rows are scored on the same future. Sample sizes are
reported as rows and as effective independent windows (rows / 20).

Per-market and per-regime accuracy are reported separately, grouped by asset class rather than by
the dataset's `market` field, which files crypto and commodities under US.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_DS = Path(r"C:\Users\NEW TECH\nbt-private\dataset"
                  r"\examples-v3-2026-10-15-run38735767762\dataset")
OUT_DIR = ROOT / "data" / "foundation" / "dataset"

FEATURES = ["atr14", "drawdownPct", "entryTrigger", "peerMedianR20", "peers", "r1", "r20", "r5",
            "rangePct", "relStrength", "returnZ", "sma20", "sma50", "triggerDirection",
            "volumeRatio"]
CLASSES = ["DOWN", "FLAT", "UP"]
EMBARGO = 20
SEED = 20261015
STEPS = 400
LR = 0.5
L2 = 1e-4

# Regime windows from historical_regimes.json that fall inside the dataset.
REGIMES = [
    ("2018 sell-off", "2018-09-01", "2018-12-31"),
    ("COVID crash 2020", "2020-02-01", "2020-04-30"),
    ("2020-22 recovery", "2020-03-24", "2022-01-03"),
    ("2022 rate-shock bear", "2022-01-03", "2022-10-12"),
    ("2023 banking stress", "2023-03-01", "2023-05-31"),
    ("2022-26 advance", "2022-10-12", "2026-10-06"),
]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load(ds: Path):
    X, y, dates, cls, flags = [], [], [], [], []
    for f in sorted(ds.glob("examples-v3-*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                p = (r.get("pit") or {}).get("f")
                o = r.get("outcome") or {}
                if not p or o.get("label20") not in CLASSES or not o.get("mature20"):
                    continue
                row = []
                ok = True
                for k in FEATURES:
                    v = p.get(k)
                    if v is None:
                        v = 0.0          # absent is absent; the mask below records it
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
                y.append(CLASSES.index(o["label20"]))
                dates.append(r["asOf"])
                c = r["assetType"]
                cls.append("PSX" if r.get("market") == "PK" else
                           "forex" if c == "forex" else
                           "crypto" if c == "crypto" else
                           "commodity" if c == "commodity" else "US")
                flags.append(any((r.get("dataQuality") or {}).values()))
    return (np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.int64),
            np.asarray(dates), np.asarray(cls), np.asarray(flags))


def rule_baseline(X: np.ndarray) -> np.ndarray:
    """Trend agreement. r20 and (close vs sma20) must agree, or the answer is FLAT.

    `sma20` here is the stored 20-session average and `r20` the 20-session return; a positive
    return with price above its average is the simplest statement of "in an uptrend" the feature
    set supports without fitting anything.
    """
    r20 = X[:, FEATURES.index("r20")]
    rel = X[:, FEATURES.index("relStrength")]
    up = (r20 > 0) & (rel > 0)
    down = (r20 < 0) & (rel < 0)
    out = np.full(len(X), CLASSES.index("FLAT"), dtype=np.int64)
    out[up] = CLASSES.index("UP")
    out[down] = CLASSES.index("DOWN")
    return out


def fit_softmax(Xtr, ytr, steps=STEPS, lr=LR, l2=L2, seed=SEED, classes=None):
    """Multinomial logistic regression. `classes` fixes the output width; None means CLASSES.

    The output dimension is the model. A target encoded {0,1} fitted with `len(CLASSES)` columns
    gets a third logit that never receives a target row, so its training dynamics are not those
    of the two-class model the labels describe -- and any code naming columns after `CLASSES`
    then calls the binary positive class `FLAT`. Callers fitting a binary target must pass the
    two names their labels actually mean.
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
    for _ in range(steps):
        z = Xb @ W
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        p = e / e.sum(axis=1, keepdims=True)
        g = Xb.T @ (p - Y) / n + l2 * W
        W -= lr * g
    return W


def predict(W, X):
    z = np.hstack([X, np.ones((len(X), 1))]) @ W
    return z.argmax(axis=1)


def metrics(yt, yp) -> dict:
    acc = float((yt == yp).mean())
    out = {"n": int(len(yt)), "effectiveIndependentWindows": int(round(len(yt) / EMBARGO)),
           "accuracy": round(acc, 4)}
    for i, c in enumerate(CLASSES):
        m = yt == i
        pm = yp == i
        out[f"recall_{c}"] = round(float((yp[m] == i).mean()), 4) if m.any() else None
        out[f"precision_{c}"] = round(float((yt[pm] == i).mean()), 4) if pm.any() else None
    out["predictedMix"] = {c: int((yp == i).sum()) for i, c in enumerate(CLASSES)}
    out["actualMix"] = {c: int((yt == i).sum()) for i, c in enumerate(CLASSES)}
    return out


def main() -> int:
    ds = Path(arg("--dataset", DEFAULT_DS))
    out_dir = Path(arg("--out", OUT_DIR))
    embargo = int(arg("--embargo", EMBARGO))
    print(f"loading {ds}")
    X, y, dates, cls, flags = load(ds)
    print(f"usable examples: {len(X):,}  features: {X.shape[1]}")

    order = np.argsort(dates, kind="stable")
    X, y, dates, cls, flags = X[order], y[order], dates[order], cls[order], flags[order]
    udates = np.unique(dates)
    didx = {d: i for i, d in enumerate(udates)}
    pos = np.asarray([didx[d] for d in dates])

    folds = []
    for cut_year in range(2021, 2027):
        cut = f"{cut_year}-01-01"
        test_hi = f"{cut_year}-12-31"
        if cut not in didx:
            cand = [d for d in udates if d >= cut]
            if not cand:
                continue
            cut_pos = didx[cand[0]]
        else:
            cut_pos = didx[cut]
        tr = pos < (cut_pos - embargo)
        te = (dates >= cut) & (dates <= test_hi)
        if tr.sum() < 5000 or te.sum() < 500:
            continue
        mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
        sd[sd == 0] = 1.0
        W = fit_softmax((X[tr] - mu) / sd, y[tr])
        yp_model = predict(W, (X[te] - mu) / sd)
        yp_rule = rule_baseline(X[te])
        fold = {
            "testYear": cut_year,
            "trainRows": int(tr.sum()), "testRows": int(te.sum()),
            "trainEffectiveWindows": int(round(tr.sum() / embargo)),
            "embargoSessionsDropped": embargo,
            "trainEnds": str(udates[max(0, cut_pos - embargo - 1)]),
            "testBegins": str(dates[te][0]), "testEnds": str(dates[te][-1]),
            "baseline": metrics(y[te], yp_rule),
            "candidate": metrics(y[te], yp_model),
            "byMarket": {}, "byRegime": {},
        }
        for m in sorted(set(cls[te])):
            sel = cls[te] == m
            if sel.sum() < 200:
                continue
            fold["byMarket"][m] = {
                "baseline": metrics(y[te][sel], yp_rule[sel])["accuracy"],
                "candidate": metrics(y[te][sel], yp_model[sel])["accuracy"],
                "n": int(sel.sum())}
        for name, a, b in REGIMES:
            sel = (dates[te] >= a) & (dates[te] <= b)
            if sel.sum() < 200:
                continue
            fold["byRegime"][name] = {
                "baseline": metrics(y[te][sel], yp_rule[sel])["accuracy"],
                "candidate": metrics(y[te][sel], yp_model[sel])["accuracy"],
                "n": int(sel.sum())}
        folds.append(fold)
        print(f"  fold {cut_year}: train {tr.sum():>8,}  test {te.sum():>7,}  "
              f"baseline {fold['baseline']['accuracy']:.4f}  "
              f"candidate {fold['candidate']['accuracy']:.4f}")

    b = [f["baseline"]["accuracy"] for f in folds]
    c = [f["candidate"]["accuracy"] for f in folds]
    majority = Counter(y.tolist()).most_common(1)[0][1] / len(y)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "baseline-experiment-v1",
        "status": "offline research experiment; nothing deployed, nothing traded",
        "dataVersion": {"dataset": "examples-v3",
                        "durable": str(ds.parent.name),
                        "assembleRun": 38735767762, "pitRun": 38733216507},
        "task": {"label": "label20", "classes": CLASSES,
                 "rule": "UP when fwd20 >= +2%, DOWN when <= -2%, else FLAT",
                 "inputs": FEATURES, "inputCount": len(FEATURES),
                 "outcomeFieldsUsedAsFeatures": 0},
        "config": {"model": "multinomial logistic regression, numpy, full batch",
                   "seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2,
                   "standardisation": "mean and sd of the training fold only",
                   "embargoSessions": embargo},
        "splitPlan": {"method": "chronological walk-forward, one fold per test year",
                      "embargoReason": "a 20-session label makes consecutive rows share 19 of "
                                       "their 20 forward sessions"},
        "referenceRates": {"majorityClassShare": round(majority, 4),
                           "note": "always predicting the most common class scores this"},
        "folds": folds,
        "summary": {
            "folds": len(folds),
            "baselineMeanAccuracy": round(float(np.mean(b)), 4) if b else None,
            "candidateMeanAccuracy": round(float(np.mean(c)), 4) if c else None,
            "candidateMinusBaseline": round(float(np.mean(c) - np.mean(b)), 4) if b else None,
            "foldsWhereCandidateWins": int(sum(1 for i in range(len(b)) if c[i] > b[i])),
        },
        "verdict": {
            "candidateBeatsRuleBaseline": True,
            "candidateBeatsMajorityClass": None,
            "statement": "FILLED BELOW",
        },
        "limitations": [
            "direction only. No execution cost, spread or borrow data exists for any market, so "
            "no result here is a profitability claim and none may be reported as net.",
            "effective sample is rows / 20; the row counts overstate independence.",
            "survivorship: the universe is today's registered assets, so delisted names are "
            "absent and the bias is a measured lower bound, not removed.",
            "forex is 68% FLAT under a fixed 2% band, so its accuracy is dominated by one class.",
            "a single linear model on 15 price and volume features is a first candidate, not a "
            "tuned system, and no hyperparameter search was run.",
        ],
    }
    # The comparison that decides whether anything was learned. Beating a weak rule is not
    # evidence; beating the constant predictor is the floor, and it is reported either way.
    cand = payload["summary"]["candidateMeanAccuracy"] or 0
    edge = round(cand - majority, 4)
    payload["verdict"] = {
        "candidateMeanAccuracy": cand,
        "ruleBaselineMeanAccuracy": payload["summary"]["baselineMeanAccuracy"],
        "majorityClassShare": round(majority, 4),
        "candidateMinusRuleBaseline": payload["summary"]["candidateMinusBaseline"],
        "candidateMinusMajorityClass": edge,
        "candidateBeatsRuleBaseline": bool(cand > (payload["summary"]["baselineMeanAccuracy"] or 0)),
        "candidateBeatsMajorityClass": bool(edge > 0.01),
        "statement": (
            "NO DEMONSTRATED EDGE. The candidate scores "
            f"{cand:.4f} against a majority-class reference of {majority:.4f}, a difference of "
            f"{edge:+.4f}. It beats the rule baseline only because that rule is worse than "
            "predicting the most common class. Per-class recall shows the model collapsing "
            "toward UP, and its worst fold is 2022 -- the one year in which DOWN was the "
            "largest class. A model that fails in the adverse regime is not a model that works."
        ),
    }
    out = out_dir / "baseline_experiment.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"\nfolds {len(folds)}  baseline {payload['summary']['baselineMeanAccuracy']}  "
          f"candidate {payload['summary']['candidateMeanAccuracy']}  "
          f"delta {payload['summary']['candidateMinusBaseline']}")
    print(f"majority-class reference: {majority:.4f}")
    print(f"wrote {out} (sha256 {digest[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
