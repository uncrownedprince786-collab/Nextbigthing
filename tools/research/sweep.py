"""The improvement loop: a grid over families, horizons, label bands and feature sets, measured once each.

    python tools/research/sweep.py --arm all          # the whole grid
    python tools/research/sweep.py --arm bands        # what accuracy costs in information
    python tools/research/sweep.py --arm selective    # accuracy at coverage

Why a grid and not another pre-registered single experiment
-----------------------------------------------------------
There are a dozen one-shot experiments in this directory, each honestly designed and each
answering one question at fifteen minutes of dataset parsing apiece. That cadence is why the model
work has moved one hypothesis at a time, and it is why "is a stronger model possible" has never
been answered as a question about the *space* rather than about a particular point in it.

`sweep_cache.py` removes the parse, so the grid costs about what one arm used to. Every arm here
uses the same chronological split, the same embargo and the same training-fold-only imputation and
standardisation as `train_v4_markets.py`, so a difference between two arms is the thing that
differs between them.

What is being asked
-------------------
**families** -- is the linear model the limit? Logistic regression against depth-2 gradient
boosting and a class-weighted variant, same features, same split.

**horizons** -- 1, 5 and 20 sessions, since a horizon is a different question and not a knob.

**bands** -- the one that decides the 90% conversation. The label calls a move UP or DOWN when it
clears a threshold and FLAT otherwise. Widen that threshold and FLAT swallows the distribution,
the majority-class baseline climbs, and *accuracy climbs with it* while the model says less and
less. This arm measures the curve: accuracy against the majority share it is standing on. A number
that only moves because the question got easier is not an improvement, and this is how to see that
rather than argue about it.

**features** -- price-only against price-plus-context, to attribute any lift.

**selective** -- the honest route to a high number. Abstain below a confidence threshold and report
**accuracy at coverage**: if the model is right 65% of the time on the 10% of rows it is most sure
about, that is a usable research signal and it is reported as "65% at 10% coverage", never as 65%.
Coverage is always printed beside the accuracy, because an accuracy without it is a selection
effect.

Honesty rules this file keeps
-----------------------------
* The holdout is scored once per arm. No arm's result changes another arm's design.
* Imputation means and standard deviations come from the training fold only.
* The embargo is `EMBARGO` sessions, dropped between fold and holdout.
* A majority-class baseline and a price-only baseline are computed for every arm, and an arm that
  does not beat both by more than sampling noise (`significance.py`) is reported as not beating
  them. The verdict is arithmetic, not a reading.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

import make_dataset as md  # noqa: E402
import significance  # noqa: E402
import sweep_cache  # noqa: E402
from baseline_experiment import CLASSES, EMBARGO, FEATURES, SEED  # noqa: E402
from shadow_markets import MARKETS  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "sweep.json"
TRAIN_END = "2025-12-31"
MIN_TRAIN_ROWS = 2000
MIN_HOLDOUT_ROWS = 200


# ---------------------------------------------------------------- splitting and preparation

def chronological(dates: np.ndarray, train_end: str, embargo: int = EMBARGO):
    """`(train_idx, holdout_idx)` with `embargo` whole sessions dropped between them.

    The embargo is in *sessions*, not rows: a session is one date, and dropping rows would leak
    the rest of a partially-used day into the fold it was supposed to be kept out of.
    """
    order = np.argsort(dates, kind="stable")
    udates = np.unique(dates)
    cut = int(np.searchsorted(udates, train_end, side="right"))
    if cut <= embargo or cut >= len(udates):
        return None, None, order
    pos = np.searchsorted(udates, dates)
    tr = np.where(pos < cut - embargo)[0]
    te = np.where(pos >= cut)[0]
    return tr, te, order


def prepared(X: np.ndarray, tr: np.ndarray, te: np.ndarray, cols: list[int]):
    """Impute and standardise from the training fold alone, exactly as train_v4_markets does."""
    Xtr, Xte = X[np.ix_(tr, cols)], X[np.ix_(te, cols)]
    mu = np.nanmean(Xtr, axis=0)
    mu = np.where(np.isnan(mu), 0.0, mu)
    Xtr = np.where(np.isnan(Xtr), mu, Xtr)
    Xte = np.where(np.isnan(Xte), mu, Xte)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    return (Xtr - mu) / sd, (Xte - mu) / sd


# ---------------------------------------------------------------- model families

def fit_logistic(Ztr, ytr, Zte, *, steps=400, lr=0.5, l2=1e-4, k=3):
    """Multinomial logistic regression by full-batch gradient descent. The incumbent."""
    rng = np.random.default_rng(SEED)
    W = rng.normal(0, 0.01, size=(Ztr.shape[1] + 1, k)).astype(np.float64)
    A = np.hstack([Ztr, np.ones((len(Ztr), 1))])
    Y = np.zeros((len(ytr), k)); Y[np.arange(len(ytr)), ytr] = 1.0
    n = len(A)
    for _ in range(steps):
        logits = A @ W
        logits -= logits.max(axis=1, keepdims=True)
        P = np.exp(logits); P /= P.sum(axis=1, keepdims=True)
        W -= lr * ((A.T @ (P - Y)) / n + l2 * W)
    B = np.hstack([Zte, np.ones((len(Zte), 1))])
    logits = B @ W
    logits -= logits.max(axis=1, keepdims=True)
    P = np.exp(logits); P /= P.sum(axis=1, keepdims=True)
    return P


def fit_boost(Ztr, ytr, Zte, *, rounds=60, lr=0.2, k=3, bins=16, min_leaf=50):
    """Logistic gradient boosting over depth-2 trees, numpy only.

    Depth 2 and sixteen quantile bins on purpose: enough to express "this feature matters only
    when that one is extreme", which is the interaction a linear model cannot hold, and little
    enough to fit a million rows in seconds without a tree library.
    """
    n, p = Ztr.shape
    edges = [np.quantile(Ztr[:, j], np.linspace(0, 1, bins + 1)[1:-1]) for j in range(p)]
    Btr = np.stack([np.searchsorted(edges[j], Ztr[:, j]) for j in range(p)], axis=1)
    Bte = np.stack([np.searchsorted(edges[j], Zte[:, j]) for j in range(p)], axis=1)
    Y = np.zeros((n, k)); Y[np.arange(n), ytr] = 1.0
    Ftr = np.zeros((n, k)); Fte = np.zeros((len(Zte), k))
    rng = np.random.default_rng(SEED)
    for _ in range(rounds):
        P = np.exp(Ftr - Ftr.max(axis=1, keepdims=True))
        P /= P.sum(axis=1, keepdims=True)
        G = Y - P                                        # negative gradient
        cols = rng.choice(p, size=max(1, p // 3), replace=False)
        for c in range(k):
            g = G[:, c]
            best = None
            for j in cols:
                sums = np.bincount(Btr[:, j], weights=g, minlength=bins + 1)
                cnts = np.bincount(Btr[:, j], minlength=bins + 1).astype(np.float64)
                cl, cr = np.cumsum(cnts)[:-1], cnts.sum() - np.cumsum(cnts)[:-1]
                sl, sr = np.cumsum(sums)[:-1], sums.sum() - np.cumsum(sums)[:-1]
                ok = (cl >= min_leaf) & (cr >= min_leaf)
                if not ok.any():
                    continue
                gain = np.where(ok, sl ** 2 / np.maximum(cl, 1) + sr ** 2 / np.maximum(cr, 1), -np.inf)
                t = int(np.argmax(gain))
                if best is None or gain[t] > best[0]:
                    best = (gain[t], j, t, sl[t] / max(cl[t], 1), sr[t] / max(cr[t], 1))
            if best is None:
                continue
            _, j, t, vl, vr = best
            Ftr[:, c] += lr * np.where(Btr[:, j] <= t, vl, vr)
            Fte[:, c] += lr * np.where(Bte[:, j] <= t, vl, vr)
    P = np.exp(Fte - Fte.max(axis=1, keepdims=True))
    P /= P.sum(axis=1, keepdims=True)
    return P


def fit_balanced(Ztr, ytr, Zte, *, steps=400, lr=0.5, l2=1e-4, k=3):
    """Logistic regression with inverse-frequency class weights.

    The weakness this is aimed at, measured in the first sweep: US h5 at a 2% band beat its base
    rate by 5.1 points at 24 standard errors, and did it with **DOWN recall of 0.008**. It had
    learned to separate UP from FLAT and was blind to the downside -- 291 DOWN calls out of 49,679
    rows. A model that cannot say SHORT is half a research tool, and the cause is that the loss
    counts a missed DOWN exactly as cheaply as the class is rare.

    Weighting each class by the inverse of its training frequency makes a missed DOWN cost what it
    is worth. It is the one change from `fit_logistic`; everything else -- steps, rate, L2, seed,
    the features, the split -- is held, so a difference between the two is the weighting.

    Measured: it lifts Commodity's DOWN recall 0.210 -> 0.424 and US's balanced accuracy
    0.3867 -> 0.3968 at the 3.0% band, and changes no verdict -- the paired comparison against
    the price-only model still fails in every market.
    """
    rng = np.random.default_rng(SEED)
    W = rng.normal(0, 0.01, size=(Ztr.shape[1] + 1, k)).astype(np.float64)
    A = np.hstack([Ztr, np.ones((len(Ztr), 1))])
    Y = np.zeros((len(ytr), k)); Y[np.arange(len(ytr)), ytr] = 1.0
    counts = np.bincount(ytr, minlength=k).astype(np.float64)
    # A class absent from the fold gets weight 1 rather than an infinity.
    w = np.where(counts > 0, len(ytr) / (k * np.maximum(counts, 1)), 1.0)
    sw = w[ytr][:, None]
    n = sw.sum()
    for _ in range(steps):
        logits = A @ W
        logits -= logits.max(axis=1, keepdims=True)
        P = np.exp(logits); P /= P.sum(axis=1, keepdims=True)
        W -= lr * ((A.T @ (sw * (P - Y))) / n + l2 * W)
    B = np.hstack([Zte, np.ones((len(Zte), 1))])
    logits = B @ W
    logits -= logits.max(axis=1, keepdims=True)
    P = np.exp(logits); P /= P.sum(axis=1, keepdims=True)
    return P


#: The families in the grid. A two-layer network was measured here and then removed: it landed
#: within sampling noise of logistic regression in all five markets (US 0.4112, PK 0.4671,
#: Crypto 0.4733, Commodity 0.4565, FX 0.7409 at h5/x1.0), the installed torch is compiled against
#: numpy 1.x and its array bridge raises under numpy 2.2.1, and declaring a 200 MB dependency in
#: requirements.txt -- which `tests/test_brain.py` rightly demands of every third-party import --
#: would put that download in every CI run to buy a result already known to be flat. The
#: measurement is kept in brain.md rule 190; the dependency is not kept.
FAMILIES = {"logistic": fit_logistic, "boost": fit_boost, "balanced": fit_balanced}


# ---------------------------------------------------------------- scoring

def score(P: np.ndarray, yte: np.ndarray, *, baseline_acc: float, rival_correct=None) -> dict:
    """Accuracy, the baseline it stands on, class recalls, and whether the lift survives noise."""
    yp = P.argmax(axis=1)
    correct = (yp == yte)
    n = len(yte)
    acc = float(correct.mean())
    out = {
        "n": int(n),
        "accuracy": round(acc, 4),
        "majorityShare": round(float(baseline_acc), 4),
        "predictedMix": {c: int((yp == i).sum()) for i, c in enumerate(CLASSES)},
        "recall": {c: (round(float(correct[yte == i].mean()), 4) if (yte == i).any() else None)
                   for i, c in enumerate(CLASSES)},
        "balancedAccuracy": round(float(np.mean([
            correct[yte == i].mean() for i in range(len(CLASSES)) if (yte == i).any()])), 4),
    }
    out["vsMajority"] = significance.binomial_lift(int(correct.sum()), n, baseline_acc)
    if rival_correct is not None:
        b = int((correct & ~rival_correct).sum())
        c = int((~correct & rival_correct).sum())
        out["vsPriceOnly"] = significance.mcnemar(b, c)
    return out


def selective(P: np.ndarray, yte: np.ndarray, coverages=(1.0, 0.5, 0.25, 0.1, 0.05)) -> list[dict]:
    """Accuracy on the rows the model is most confident about, with coverage always beside it.

    This is the one route to a high number that is not a trick, and it is only not a trick when
    the coverage is reported. "87% correct" means nothing; "87% correct on the 5% of sessions it
    was most sure about" is a usable statement about a research tool.
    """
    conf = P.max(axis=1)
    yp = P.argmax(axis=1)
    order = np.argsort(-conf)
    rows = []
    for cov in coverages:
        k = max(1, int(len(yte) * cov))
        sel = order[:k]
        rows.append({
            "coverage": cov,
            "n": int(k),
            "accuracy": round(float((yp[sel] == yte[sel]).mean()), 4),
            "minConfidence": round(float(conf[sel].min()), 4),
            # The base rate *within the selected slice*, so a high accuracy on an easy slice is
            # visible as an easy slice rather than read as skill.
            "majorityShareInSlice": round(float(max(
                (yte[sel] == i).mean() for i in range(len(CLASSES)))), 4),
        })
    return rows


# ---------------------------------------------------------------- the arms

def labels_for(fwd: np.ndarray, horizon: int, scale: float) -> tuple[np.ndarray, np.ndarray]:
    """`(y, usable)` -- the class index per row and which rows have a matured forward return.

    `scale` multiplies the shared threshold. 1.0 is the project's own band; the band arm moves it
    to measure what accuracy costs in information.
    """
    t = md.label_threshold_pct(horizon) * scale
    usable = ~np.isnan(fwd)
    y = np.full(len(fwd), CLASSES.index("FLAT"), dtype=np.int64)
    y[fwd >= t] = CLASSES.index("UP")
    y[fwd <= -t] = CLASSES.index("DOWN")
    return y, usable


def run_one(data: dict, market: str, horizon: int, scale: float, family: str,
            feature_set: str) -> dict | None:
    """One arm: one market, horizon, band, family and feature set, scored once."""
    d = data[market]
    fwd = d[f"fwd{horizon}"]
    y, usable = labels_for(fwd, horizon, scale)
    X, dates = d["X"][usable], d["dates"][usable]
    y = y[usable]
    tr, te, _ = chronological(dates, TRAIN_END)
    if tr is None or len(tr) < MIN_TRAIN_ROWS or len(te) < MIN_HOLDOUT_ROWS:
        return None
    cols = ([ALL_FEATURES.index(f) for f in FEATURES] if feature_set == "price"
            else list(range(len(ALL_FEATURES))))
    Ztr, Zte = prepared(X, tr, te, cols)
    yte = y[te]
    base = float(max((yte == i).mean() for i in range(len(CLASSES))))

    price_cols = [ALL_FEATURES.index(f) for f in FEATURES]
    Ptr_p, Pte_p = prepared(X, tr, te, price_cols)
    rival = fit_logistic(Ptr_p, y[tr], Pte_p)
    rival_correct = (rival.argmax(axis=1) == yte)

    t0 = time.time()
    P = FAMILIES[family](Ztr, y[tr], Zte)
    if P is None:
        return None
    res = score(P, yte, baseline_acc=base, rival_correct=rival_correct)
    res.update({
        "market": market, "horizon": horizon, "bandScale": scale,
        "bandPct": round(md.label_threshold_pct(horizon) * scale, 4),
        "family": family, "featureSet": feature_set,
        "trainRows": int(len(tr)), "seconds": round(time.time() - t0, 1),
        "selective": selective(P, yte),
    })
    res["beatsBothBaselines"] = bool(
        res["vsMajority"]["passes"] and res.get("vsPriceOnly", {}).get("passes"))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(sweep_cache.DEFAULT_OUT))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--arm", default="all",
                    choices=["all", "families", "horizons", "bands", "features", "selective",
                             "balance"])
    ap.add_argument("--markets", default=",".join(MARKETS))
    a = ap.parse_args()

    data = sweep_cache.load(Path(a.cache))
    markets = [m for m in a.markets.split(",") if m in data]
    grid: list[tuple] = []
    if a.arm in ("all", "families"):
        for m in markets:
            for fam in FAMILIES:
                grid.append((m, 5, 1.0, fam, "all"))
    if a.arm in ("all", "horizons"):
        for m in markets:
            for h in md.HORIZONS:
                grid.append((m, h, 1.0, "boost", "all"))
    if a.arm in ("all", "bands"):
        for m in markets:
            for s in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0):
                grid.append((m, 5, s, "logistic", "all"))
    if a.arm in ("all", "features"):
        for m in markets:
            for fs in ("price", "all"):
                grid.append((m, 5, 1.0, "boost", fs))
    if a.arm == "balance":
        # The follow-up to the first sweep's one real lead. Bands 2.0 and 3.0 because that is
        # where the classes are balanced enough for there to be something to predict -- at x1.0
        # the US holdout is 98% one predicted class and the question does not arise.
        for m in markets:
            for s in (2.0, 3.0):
                for fam in ("logistic", "balanced", "boost"):
                    grid.append((m, 5, s, fam, "all"))
    seen, rows = set(), []
    for cfg in grid:
        if cfg in seen:
            continue
        seen.add(cfg)
        m, h, s, fam, fs = cfg
        r = run_one(data, m, h, s, fam, fs)
        if r is None:
            print(f"  {m:<10} h{h:<3} band x{s:<4} {fam:<9} {fs:<6} SKIPPED (too few rows)")
            continue
        rows.append(r)
        flag = "BEATS BOTH" if r["beatsBothBaselines"] else ""
        print(f"  {m:<10} h{h:<3} band x{s:<4} {fam:<9} {fs:<6} "
              f"acc {r['accuracy']:.4f}  maj {r['majorityShare']:.4f}  "
              f"bal {r['balancedAccuracy']:.4f}  n {r['n']:>6}  {r['seconds']:>5.1f}s {flag}")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "producedBy": "tools/research/sweep.py",
        "trainEnd": TRAIN_END, "embargoSessions": EMBARGO,
        "status": "measurement only; no candidate is promoted here",
        "arms": rows,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    winners = [r for r in rows if r["beatsBothBaselines"]]
    print(f"\n  {len(rows)} arms measured, {len(winners)} beat both baselines beyond noise")
    for r in sorted(winners, key=lambda r: -r["accuracy"])[:10]:
        print(f"    {r['market']:<10} h{r['horizon']:<3} x{r['bandScale']:<4} {r['family']:<9} "
              f"acc {r['accuracy']:.4f} vs maj {r['majorityShare']:.4f}")
    print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
