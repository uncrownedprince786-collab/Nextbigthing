"""A binary UP/DOWN directional model per crypto horizon, trained and tested chronologically.

    python tools/research/train_crypto_short.py --symbols BTCUSDT --tag btc
    python tools/research/train_crypto_short.py --symbols BTCUSDT ETHUSDT ... --tag crypto
    python tools/research/train_crypto_short.py --symbols BTCUSDT --tag btc --horizons m5 m15

Why binary, and why this replaces the three-class model for these horizons
--------------------------------------------------------------------------
Every recorded crypto brain is three-class -- DOWN / FLAT / UP with a percentage band -- and every
one of them is a recorded NO-GO for the same reason. `brain-v4-crypto` predicted DOWN on 18,644 of
19,220 holdout rows and scored 0.4736 against a 0.4723 largest-class share: a thirteen-basis-point
margin bought by naming one class. `brain-v5-h5-crypto` predicted DOWN on 18,987 of 19,220. The
FLAT class never survives -- its recall is 0.0004 and 0.0016 in those two runs -- so what the band
actually does is remove the rows the model could have been judged on and leave a two-class problem
with a third label nobody predicts.

So the task here is stated as what it is: **the sign of the forward return**. No band, no third
class, no "FLAT converted to a direction". A row whose forward return is exactly zero carries no
direction and is dropped, counted, and reported -- at five minutes on a 420,000-bar series that is
a handful of rows, and at any longer horizon it is none.

This is not a softer target. A three-class model can score by naming the largest class; a binary
one on a near-even split cannot, because the largest class *is* about half. The baseline this has
to beat is therefore roughly 0.50 and the margin is the whole result.

What is measured, and what the gates are
----------------------------------------
Fixed here, before the run, and written into every manifest:

  * **accuracy above the test majority** -- the test fold's own larger class, which is the number
    a model that says one word would score.
  * **both directions predicted** -- neither class above 0.80 of the predictions. A model that
    calls UP on 97% of rows has not read direction, whatever it scores.
  * **a day-blocked bootstrap** of (accuracy - majority) whose 95% interval excludes zero. Blocked
    by UTC day because overlapping label windows make adjacent rows anything but independent, and
    an i.i.d. bootstrap on 400,000 overlapping rows reports a certainty that is not there.
  * **walk-forward consistency** -- the test fold cut into five chronological blocks, with the
    count of blocks whose accuracy is above that block's own majority.

The headline number is accuracy on **every** test row. A coverage curve by confidence is reported
beside it, because a reader is entitled to know whether the model is better on the rows it is
surest about -- but abstention is never allowed to produce the headline. "90% on the 2% of rows we
felt best about" is not 90% directional accuracy and is not reported as though it were.

Leakage
-------
The split is chronological with an embargo of `WARMUP + horizon` bars between folds, so no
training row's label window reaches into validation and no validation row's feature window reaches
back into training. Binning edges, standardisation constants and the early-stopping round are all
fitted on the training and validation folds only; the test fold is read exactly once, at the end,
by `evaluate`.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import gbm  # noqa: E402
from crypto_horizons import HORIZONS, ORDER, horizons_for  # noqa: E402
from crypto_matrix import prepare_cached  # noqa: E402
from intraday_features import FEATURES, VERSION as FEATURE_VERSION, WARMUP  # noqa: E402
from market_context import CONTEXT_FEATURES, VERSION as CONTEXT_VERSION  # noqa: E402
from intraday_matrix import build, verify_against_reference  # noqa: E402

CORPUS = ROOT / ".cache" / "foundation" / "intraday"
BRAIN_ROOT = ROOT / "data" / "foundation" / "brain"
OUT_DIR = ROOT / "data" / "foundation" / "dataset"

#: Fixed before the run.
GATES = {
    "aboveTestMajority": "accuracy strictly above the test fold's own larger class",
    "bothDirectionsPredicted": "neither predicted class above 0.80 of the test fold",
    "bootstrapExcludesZero": "95% day-blocked bootstrap interval for (accuracy - majority) "
                             "strictly above zero",
    "walkForwardMajority": "above its own block majority in at least 4 of 5 chronological blocks",
}

#: The historical acceptance target the project set. Stated here so a manifest records what the
#: run was aiming at as well as what it reached; nothing in this file adjusts a threshold to meet
#: it, and `acceptanceTargetMet` is simply the measurement against it.
ACCEPTANCE_TARGET = 0.90

TRAIN_SHARE, VAL_SHARE = 0.70, 0.15
SEED = 11


#: Where the universe builder records which tickers are dollar-pegged.
UNIVERSE = ROOT / "data" / "foundation" / "dataset" / "crypto_universe.json"


def drop_pegged(symbols: list[str]) -> list[str]:
    """Remove dollar-pegged coins from a training pool.

    A stablecoin's five-minute direction is not a market opinion, it is oscillation in the fourth
    decimal of a dollar. The model can be genuinely, repeatably right about it -- a peg really does
    mean-revert -- and that is exactly what makes it dangerous: those rows arrive at the top of the
    conviction tail, on moves around 0.01% of price, which is a fiftieth of the round-trip fee.

    This is the second time. RLUSD, FDUSD and USDC once came out as the strongest signals on the
    board at p=0.668, which is why `pegged` exists on the universe in the first place. The serving
    path has honoured it since; the training pool never did, because the pool is built by globbing
    the bar cache and the flag was never consulted. BFUSD and RWUSD were in the 140-coin pool.

    Missing or unreadable universe file is not fatal: the pool passes through unfiltered and says
    so, because a training run that dies over a metadata file is worse than one that trains on two
    stablecoins and tells you.
    """
    try:
        assets = json.loads(UNIVERSE.read_text(encoding="utf-8"))["assets"]
    except (OSError, KeyError, ValueError) as e:
        print(f"   ! could not read {UNIVERSE.name} ({e}); pool not filtered for pegs", flush=True)
        return symbols
    pegged = {a["ticker"].upper() for a in assets if a.get("pegged")}
    kept, dropped = [], []
    for s in symbols:
        # Pool symbols are venue instruments ("BFUSDUSDT"); the flag is on the bare ticker.
        base = s.upper()[:-4] if s.upper().endswith("USDT") else s.upper()
        (dropped if base in pegged else kept).append(s)
    if dropped:
        print(f"   dropped {len(dropped)} pegged: {', '.join(dropped)}", flush=True)
    return kept


def repo_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_bars(symbol: str, interval: str) -> list[dict]:
    path = CORPUS / f"{symbol}-{interval}.jsonl.gz"
    if not path.exists():
        raise SystemExit(f"no corpus at {path}; run tools/foundation/crypto_intraday.py first")
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            out.append(json.loads(line))
    return out


def corpus_report(symbol: str, interval: str) -> dict:
    p = CORPUS / f"{symbol}-{interval}.manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, steps: int = 400,
                 lr: float = 0.5) -> dict:
    """L2 logistic regression by full-batch gradient descent on standardised inputs.

    The same shape as `baseline_experiment.fit_softmax` with two classes, kept so the boosted tree
    below is measured against a linear model fitted the way every other brain in this repository
    was fitted -- a comparison between two methods, not between this file and someone else's.
    """
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-8] = 1.0
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1), dtype=np.float64)])
    w = np.zeros(Z.shape[1])
    n = len(y)
    for _ in range(steps):
        p = 1.0 / (1.0 + np.exp(-(Z @ w)))
        g = Z.T @ (p - y) / n
        g[:-1] += l2 * w[:-1] / n
        w -= lr * g
    return {"kind": "logistic", "mean": mu.tolist(), "sd": sd.tolist(), "w": w.tolist()}


def logistic_proba(model: dict, X: np.ndarray) -> np.ndarray:
    mu = np.asarray(model["mean"])
    sd = np.asarray(model["sd"])
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    return 1.0 / (1.0 + np.exp(-(Z @ np.asarray(model["w"]))))


def day_blocked_bootstrap(correct: np.ndarray, baseline_correct: np.ndarray, days: np.ndarray,
                          draws: int = 2000, seed: int = SEED) -> dict:
    """Resample whole UTC days, not rows.

    Adjacent rows share a label window and an overlapping feature window, so they are not
    independent observations and an i.i.d. bootstrap would understate the interval by an order of
    magnitude. A day is the unit that is close to exchangeable here.
    """
    rng = np.random.default_rng(seed)
    uniq, inv = np.unique(days, return_inverse=True)
    k = len(uniq)
    # Per-day sums, so a draw is a weighted combination rather than a re-scan of every row.
    n_day = np.bincount(inv, minlength=k).astype(np.float64)
    c_day = np.bincount(inv, weights=correct.astype(np.float64), minlength=k)
    b_day = np.bincount(inv, weights=baseline_correct.astype(np.float64), minlength=k)
    diffs = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, k, size=k)
        n = n_day[pick].sum()
        diffs[i] = (c_day[pick].sum() - b_day[pick].sum()) / n if n else 0.0
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    sd = float(diffs.std(ddof=1))
    point = float((correct.sum() - baseline_correct.sum()) / len(correct))
    return {
        "blocks": int(k),
        "draws": draws,
        "pointEstimate": round(point, 6),
        "ci95": [round(float(lo), 6), round(float(hi), 6)],
        "sd": round(sd, 6),
        "z": round(point / sd, 4) if sd > 0 else None,
        "excludesZero": bool(lo > 0),
    }


def coverage_curve(p: np.ndarray, y: np.ndarray) -> list[dict]:
    """Accuracy against coverage as the confidence floor rises.

    Reported, never used for the headline. The point of showing it is that a reader can see
    whether a 'HIGH confidence' band would be earned or manufactured -- if accuracy is flat as
    coverage falls, the model's probabilities carry no information about its own reliability.
    """
    conf = np.abs(p - 0.5)
    pred = (p >= 0.5).astype(int)
    out = []
    for floor in (0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20):
        sel = conf >= floor
        n = int(sel.sum())
        if n < 200:
            out.append({"minMargin": floor, "rows": n, "coverage": round(n / len(y), 5),
                        "accuracy": None, "note": "under 200 rows, not reported"})
            continue
        out.append({
            "minMargin": floor,
            "rows": n,
            "coverage": round(n / len(y), 5),
            "accuracy": round(float((pred[sel] == y[sel]).mean()), 5),
            "majorityHere": round(float(max(y[sel].mean(), 1 - y[sel].mean())), 5),
        })
    return out


def calibration(p: np.ndarray, y: np.ndarray, buckets: int = 10) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, buckets + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    out = []
    for i in range(buckets):
        sel = (p >= edges[i]) & (p < edges[i + 1])
        n = int(sel.sum())
        if n < 50:
            continue
        out.append({
            "bucket": i,
            "rows": n,
            "meanPredicted": round(float(p[sel].mean()), 5),
            "observedUpRate": round(float(y[sel].mean()), 5),
        })
    return out


def walk_forward(p: np.ndarray, y: np.ndarray, blocks: int = 5) -> dict:
    pred = (p >= 0.5).astype(int)
    edges = np.linspace(0, len(y), blocks + 1).astype(int)
    rows = []
    above = 0
    for i in range(blocks):
        a, b = edges[i], edges[i + 1]
        if b - a < 100:
            continue
        yy, pp = y[a:b], pred[a:b]
        acc = float((pp == yy).mean())
        maj = float(max(yy.mean(), 1 - yy.mean()))
        above += 1 if acc > maj else 0
        rows.append({"block": i, "rows": int(b - a), "accuracy": round(acc, 5),
                     "majority": round(maj, 5), "above": bool(acc > maj)})
    return {"blocks": rows, "blocksAboveMajority": above, "blocksScored": len(rows)}


def evaluate(p: np.ndarray, y: np.ndarray, days: np.ndarray) -> dict:
    pred = (p >= 0.5).astype(int)
    acc = float((pred == y).mean())
    up_rate = float(y.mean())
    majority = max(up_rate, 1 - up_rate)
    majority_class = "UP" if up_rate >= 0.5 else "DOWN"
    base_correct = (y == (1 if majority_class == "UP" else 0)).astype(float)
    boot = day_blocked_bootstrap((pred == y).astype(float), base_correct, days)
    wf = walk_forward(p, y)
    pred_up = float(pred.mean())
    return {
        "rows": int(len(y)),
        "accuracy": round(acc, 5),
        "testMajority": round(majority, 5),
        "testMajorityClass": majority_class,
        "marginOverMajority": round(acc - majority, 5),
        "alwaysUpAccuracy": round(up_rate, 5),
        "actualUpRate": round(up_rate, 5),
        "predictedUpShare": round(pred_up, 5),
        "predictedDownShare": round(1 - pred_up, 5),
        "upRecall": round(float((pred[y == 1] == 1).mean()) if (y == 1).any() else 0.0, 5),
        "downRecall": round(float((pred[y == 0] == 0).mean()) if (y == 0).any() else 0.0, 5),
        "upPrecision": round(float((y[pred == 1] == 1).mean()) if (pred == 1).any() else 0.0, 5),
        "downPrecision": round(float((y[pred == 0] == 0).mean()) if (pred == 0).any() else 0.0, 5),
        "blockedBootstrap": boot,
        "walkForward": wf,
        "coverageCurve": coverage_curve(p, y),
        "calibration": calibration(p, y),
    }


def gates_for(ev: dict) -> dict:
    mix_ok = max(ev["predictedUpShare"], ev["predictedDownShare"]) <= 0.80
    wf = ev["walkForward"]
    checks = {
        "aboveTestMajority": ev["accuracy"] > ev["testMajority"],
        "bothDirectionsPredicted": bool(mix_ok),
        "bootstrapExcludesZero": bool(ev["blockedBootstrap"]["excludesZero"]),
        "walkForwardMajority": wf["blocksScored"] > 0 and wf["blocksAboveMajority"] >= min(4, wf["blocksScored"]),
    }
    return checks


def prepare(symbols: list[str], interval: str, stride: int = 1) -> dict:
    """Features, timestamps and closes for every symbol at one interval, concatenated.

    Rows from different symbols are kept with their own timestamps and the split is made on time
    across the pool, so a multi-symbol fit still trains on the past and tests on the future rather
    than training on Ethereum's 2026 to predict Bitcoin's 2024.
    """
    Xs, ts_all, close_all, sym_all = [], [], [], []
    corpora = {}
    parity = {}
    for s in symbols:
        bars = load_bars(s, interval)
        X, ts, valid, step = build(bars)
        if not valid.any():
            # A coin with fewer bars than the feature window contributes nothing and is recorded
            # as contributing nothing. Dropping it silently would make a pooled fit's symbol list
            # a claim about coverage that the rows do not support.
            corpora[s] = {"bars": len(bars), "usableRows": 0, "stepMs": int(step),
                          "excluded": "fewer bars than the feature window needs",
                          "_series": (ts, np.asarray([b["c"] for b in bars], dtype=np.float64),
                                      np.zeros(0, dtype=np.int64))}
            continue
        parity[s] = verify_against_reference(bars, X, valid, sample=60)
        closes = np.asarray([b["c"] for b in bars], dtype=np.float64)
        # Striding is how a pooled fit over thirty coins stays inside memory. It keeps every
        # `stride`-th usable row, which thins the sample evenly across the whole period rather
        # than cutting a span out of it -- adjacent 5-minute rows share most of a 24-hour feature
        # window anyway, so what is dropped is mostly redundancy. The labels and the split are
        # unaffected: the forward close is still read from the full, unstrided series.
        keep = np.flatnonzero(valid)[:: max(1, stride)]
        Xs.append(X[keep])
        ts_all.append(ts[keep])
        close_all.append(closes[keep])
        sym_all.append(np.full(len(keep), s))
        corpora[s] = {
            "bars": len(bars), "usableRows": int(len(keep)), "stepMs": int(step),
            "manifest": {k: v for k, v in corpus_report(s, interval).items()
                         if k in ("completeness", "gapRuns", "missingBars", "first", "last",
                                  "rejected", "conflictingDuplicates", "crossVenue")},
        }
        # The per-symbol forward closes have to stay per symbol: a concatenated close array would
        # let the last row of one coin take its label from the first row of the next.
        full_close = closes
        full_ts = ts
        corpora[s]["_series"] = (full_ts, full_close, keep)
    return {
        "X": np.vstack(Xs),
        "ts": np.concatenate(ts_all),
        "close": np.concatenate(close_all),
        "symbol": np.concatenate(sym_all),
        "corpora": corpora,
        "parity": parity,
    }


def labels_for(data: dict, bars_ahead: int) -> tuple[np.ndarray, np.ndarray, int]:
    """`(y, usable, zeroMoves)` -- 1 for UP, 0 for DOWN, and the mask of rows whose label matured.

    The forward close is taken from the symbol's own series by index, and only when the bar
    `bars_ahead` later is exactly that many intervals later. A row whose forward window spans a
    venue gap has no label: the return across an outage is a different measurement from the return
    across `bars_ahead` bars of trading.
    """
    y = np.zeros(len(data["ts"]), dtype=np.int64)
    usable = np.zeros(len(data["ts"]), dtype=bool)
    zero_moves = 0
    offset = 0
    for s, meta in data["corpora"].items():
        full_ts, full_close, keep = meta["_series"]
        n = len(keep)
        step = meta["stepMs"]
        fwd_idx = keep + bars_ahead
        ok = fwd_idx < len(full_close)
        aligned = np.zeros(n, dtype=bool)
        aligned[ok] = (full_ts[fwd_idx[ok]] - full_ts[keep[ok]]) == bars_ahead * step
        here = np.zeros(n, dtype=bool)
        fwd = np.zeros(n)
        fwd[aligned] = full_close[fwd_idx[aligned]] - full_close[keep[aligned]]
        here[aligned] = fwd[aligned] != 0.0
        zero_moves += int((aligned & (fwd == 0.0)).sum())
        y[offset:offset + n] = (fwd > 0).astype(np.int64)
        usable[offset:offset + n] = here
        offset += n
    return y, usable, zero_moves


def split(ts: np.ndarray, bars_ahead: int, step_ms: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Chronological train / validation / test, with an embargo in time between folds.

    The embargo is `(WARMUP + bars_ahead)` intervals, which is long enough that a training row's
    label window cannot reach a validation feature window and vice versa. It is expressed in time
    rather than in row counts because the pool may hold several symbols.
    """
    order = np.argsort(ts, kind="stable")
    sorted_ts = ts[order]
    cut1 = sorted_ts[int(len(sorted_ts) * TRAIN_SHARE)]
    cut2 = sorted_ts[int(len(sorted_ts) * (TRAIN_SHARE + VAL_SHARE))]
    embargo = (WARMUP + bars_ahead) * step_ms
    tr = ts <= cut1 - embargo
    va = (ts > cut1) & (ts <= cut2 - embargo)
    te = ts > cut2
    meta = {
        "trainEnd": datetime.fromtimestamp(cut1 / 1000, timezone.utc).isoformat(),
        "valEnd": datetime.fromtimestamp(cut2 / 1000, timezone.utc).isoformat(),
        "embargoBars": WARMUP + bars_ahead,
        "embargoMinutes": int((WARMUP + bars_ahead) * step_ms / 60000),
        "testFrom": datetime.fromtimestamp(float(ts[te].min()) / 1000, timezone.utc).isoformat() if te.any() else None,
        "testTo": datetime.fromtimestamp(float(ts[te].max()) / 1000, timezone.utc).isoformat() if te.any() else None,
    }
    return tr, va, te, meta


def train_one(data: dict, key: str, tag: str, rounds: int, depth: int,
              verbose: int = 0) -> dict:
    h = HORIZONS[key]
    bars_ahead = h["bars"]
    y, usable, zero_moves = labels_for(data, bars_ahead)
    X, ts = data["X"], data["ts"]
    step_ms = next(iter(data["corpora"].values()))["stepMs"]

    tr_m, va_m, te_m, split_meta = split(ts, bars_ahead, step_ms)
    tr = np.flatnonzero(tr_m & usable)
    va = np.flatnonzero(va_m & usable)
    te = np.flatnonzero(te_m & usable)
    if len(tr) < 5000 or len(va) < 1000 or len(te) < 1000:
        return {"horizon": key, "trained": False,
                "reason": f"below the data floor (train {len(tr)}, val {len(va)}, test {len(te)})"}

    # The folds stay in the dtype the matrix is stored in, which is float32.
    #
    # They used to be cast to float64 here, and that cast was the single largest allocation in the
    # run: on the 140-coin pool it made a 438 MB copy of the training fold so that `gbm.fit` could
    # immediately cast it back to float32 and bin it into 55 MB of uint8 codes. Three full
    # materialisations of the same numbers, two of them thrown away -- about 845 MB of peak for no
    # arithmetic at all, on a machine with under 2 GB free. That is what drove the run into swap
    # and held it at 42% of a core.
    #
    # Nothing about the fitted model changes. float32 -> float64 -> float32 is exact, so the GBM
    # sees the identical values it saw before, and `fit_logistic` standardises into float64 itself,
    # so its arithmetic is unchanged too -- it simply upcasts the rows it needs instead of being
    # handed a second copy of all of them.
    Xtr, ytr = X[tr], y[tr].astype(np.float64)
    Xva, yva = X[va], y[va].astype(np.float64)
    Xte, yte = X[te], y[te]

    t0 = time.time()
    lin = fit_logistic(Xtr, ytr)
    p_va_lin = logistic_proba(lin, Xva)
    lin_val_acc = float(((p_va_lin >= 0.5).astype(int) == yva).mean())

    tree = gbm.fit(Xtr, ytr, rounds=rounds, depth=depth, lr=0.05, l2=2.0,
                   X_val=Xva, y_val=yva, early_stop=30, verbose=verbose)
    p_va_gbm = gbm.predict_proba(tree, Xva)
    gbm_val_acc = float(((p_va_gbm >= 0.5).astype(int) == yva).mean())

    # The choice is made on the validation fold and recorded, so the test fold is read once.
    chosen = "gbm" if gbm_val_acc >= lin_val_acc else "logistic"
    model = tree if chosen == "gbm" else lin
    p_te = gbm.predict_proba(tree, Xte) if chosen == "gbm" else logistic_proba(lin, Xte)

    days = (ts[te] // 86_400_000).astype(np.int64)
    ev = evaluate(p_te, yte, days)
    checks = gates_for(ev)

    # The linear model on the same test rows, for the record: a tree that does not beat it has not
    # earned the extra machinery, and the comparison has to be on the same fold to mean anything.
    p_te_lin = logistic_proba(lin, Xte)
    lin_acc = float(((p_te_lin >= 0.5).astype(int) == yte).mean())

    return {
        "horizon": key,
        "trained": True,
        "interval": h["interval"],
        "barsAhead": bars_ahead,
        "minutesAhead": h["minutes"],
        "chosenModel": chosen,
        "fitSeconds": round(time.time() - t0, 1),
        "rows": {"train": int(len(tr)), "validation": int(len(va)), "test": int(len(te)),
                 "zeroMoveRowsDropped": zero_moves},
        "split": split_meta,
        "validation": {"logisticAccuracy": round(lin_val_acc, 5),
                       "gbmAccuracy": round(gbm_val_acc, 5),
                       "gbmRoundsKept": tree["roundsKept"],
                       "gbmRoundsFitted": tree["roundsFitted"]},
        "evaluation": ev,
        "linearOnTheSameTestRows": round(lin_acc, 5),
        "gates": checks,
        "gatesMet": all(checks.values()),
        "acceptanceTarget": ACCEPTANCE_TARGET,
        "acceptanceTargetMet": bool(ev["accuracy"] >= ACCEPTANCE_TARGET),
        "_model": model,
        "_p_test": p_te,
        "_y_test": yte,
    }


def compact_tree(node: dict) -> dict:
    """The tree without its diagnostics.

    `gain` and `n` are written by the fitter because they are what a split search produced and are
    worth having while a model is being judged; the serving path never reads either, and they are
    about half the bytes of the artifact the web layer loads on a cold start. The manifest keeps
    the diagnostics that matter about the fit; the model keeps only what predicts.
    """
    if "leaf" in node:
        return {"leaf": round(float(node["leaf"]), 7)}
    return {"f": node["f"], "b": node["b"], "l": compact_tree(node["l"]),
            "r": compact_tree(node["r"])}


def write_artifact(tag: str, key: str, res: dict, data: dict, symbols: list[str]) -> dict:
    """Write the model and its manifest.

    `res["rowStride"]` is set by the caller from the run's own argument. It used to be read as
    `res.get("stride", 1)` off a dict that never carried the key, so every pooled manifest in the
    repository records a stride of 1 for a fit that actually used 5. The models are unaffected --
    the stride only ever thinned the training sample -- but the record was wrong, and a corpus
    record that cannot be trusted is worth less than no record.
    """
    name = f"brain-c1-{tag}-{key}"
    d = BRAIN_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    feature_names = res["featureNames"]
    model = {
        "modelVersion": name,
        "featureSchema": res["featureSchema"],
        "features": feature_names,
        "warmupBars": WARMUP,
        "interval": res["interval"],
        "barsAhead": res["barsAhead"],
        "minutesAhead": res["minutesAhead"],
        "classes": ["DOWN", "UP"],
        "model": (
            {**res["_model"], "trees": [compact_tree(t) for t in res["_model"]["trees"]]}
            if res["_model"].get("kind") == "gbm-logistic"
            else res["_model"]
        ),
    }
    text = json.dumps(model, separators=(",", ":"), sort_keys=True)
    (d / "model.json").write_text(text, encoding="utf-8")
    digest = sha256_text(text)
    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "modelVersion": name,
        "market": "Crypto",
        "symbols": symbols,
        "artifact": {"file": "model.json", "sha256": digest,
                     "bytes": len(text.encode("utf-8"))},
        "producedBy": "tools/research/train_crypto_short.py",
        "repoHead": repo_head(),
        "featureSchema": res["featureSchema"],
        "featureCount": len(feature_names),
        "task": {
            "classes": ["DOWN", "UP"],
            "label": "sign of the forward close-to-close return",
            "band": "none -- there is no FLAT class and no row is converted into a direction",
            "horizonKey": key,
            "interval": res["interval"],
            "barsAhead": res["barsAhead"],
            "minutesAhead": res["minutesAhead"],
        },
        "corpus": {s: {k: v for k, v in m.items() if not k.startswith("_")}
                   for s, m in data["corpora"].items()},
        "rowStride": res["rowStride"],
        "featureParityWithReference": data["parity"],
        "rows": res["rows"],
        "split": res["split"],
        "chosenModel": res["chosenModel"],
        "validation": res["validation"],
        "preRegisteredGates": GATES,
        "gates": res["gates"],
        "gatesMet": res["gatesMet"],
        "acceptanceTarget": ACCEPTANCE_TARGET,
        "acceptanceTargetMet": res["acceptanceTargetMet"],
        "evaluation": res["evaluation"],
        "linearOnTheSameTestRows": res["linearOnTheSameTestRows"],
        "verdict": "GO" if res["gatesMet"] else "NO-GO",
        "limitations": [
            "The test fold is a historical holdout. It is unseen by this fit, and it is still a "
            "backtest: no forecast in it was made before the data existed.",
            "Direction only. No transaction cost, spread, funding or slippage is in any number "
            "here, and nothing here is a profitability claim.",
            "Binance USDT pairs. The cross-venue check in the corpus manifest records how far "
            "these closes sit from a second exchange's.",
        ],
    }
    (d / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return {"name": name, "sha256": digest, "dir": str(d), "manifest": manifest}


def main() -> int:
    ap = argparse.ArgumentParser(description="Train binary crypto direction models per horizon.")
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--tag", required=True, help="artifact family tag, e.g. btc or crypto")
    ap.add_argument("--horizons", nargs="*", default=ORDER)
    ap.add_argument("--stride", type=int, default=1,
                    help="keep every Nth usable row; for a pooled fit over many coins")
    ap.add_argument("--rounds", type=int, default=400)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--context", action="store_true",
                    help="fit on the market-factor block as well (tools/research/market_context.py)")
    ap.add_argument("--verbose", type=int, default=0)
    ap.add_argument("--keep-pegged", action="store_true",
                    help="train on dollar-pegged coins too; off by default, see drop_pegged()")
    a = ap.parse_args()

    if not a.keep_pegged:
        a.symbols = drop_pegged(a.symbols)

    keys = [k for k in a.horizons if k in HORIZONS]
    summary = {"generatedAt": datetime.now(timezone.utc).isoformat(), "tag": a.tag,
               "symbols": a.symbols, "repoHead": repo_head(), "rowStride": a.stride,
               "marketContext": bool(a.context), "horizons": {}}

    for interval in sorted({HORIZONS[k]["interval"] for k in keys}):
        here = [k for k in keys if k in horizons_for(interval)]
        print(f"\n== {interval} corpus for {', '.join(a.symbols)}: {', '.join(here)}", flush=True)
        t0 = time.time()
        # Through the cache. `crypto_matrix.prepare_cached` builds exactly what `prepare` below
        # builds -- the same exclusions, the same stride, the same parity check against
        # `intraday_features.features_at` -- and keys the result on the content of every corpus
        # file that went into it, so an edited feature definition or a recollected coin produces a
        # different matrix rather than a stale one. Rebuilding thirty coins' features from JSONL
        # on every run was most of a fit's wall clock, and it is the same matrix every time.
        data = prepare_cached(a.symbols, interval, stride=a.stride, context=a.context)
        print(f"   {len(data['ts']):,} usable rows in {time.time() - t0:.1f}s "
              f"(parity worst {max((p['worstRelativeDiff'] for p in data['parity'].values()), default=0):.2g})",
              flush=True)
        for key in here:
            print(f"   -- {key} ({HORIZONS[key]['label']})", flush=True)
            res = train_one(data, key, a.tag, a.rounds, a.depth, verbose=a.verbose)
            res["rowStride"] = a.stride
            res["featureSchema"] = (f"{FEATURE_VERSION}+{CONTEXT_VERSION}" if a.context
                                    else FEATURE_VERSION)
            res["featureNames"] = (list(FEATURES) + list(CONTEXT_FEATURES) if a.context
                                   else list(FEATURES))
            if not res.get("trained"):
                print(f"      not trained: {res['reason']}")
                summary["horizons"][key] = res
                continue
            ev = res["evaluation"]
            written = write_artifact(a.tag, key, res, data, a.symbols)
            print(f"      {res['chosenModel']}  test acc {ev['accuracy']:.4f}  "
                  f"majority {ev['testMajority']:.4f}  margin {ev['marginOverMajority']:+.4f}  "
                  f"boot95 [{ev['blockedBootstrap']['ci95'][0]:+.4f},"
                  f"{ev['blockedBootstrap']['ci95'][1]:+.4f}]  "
                  f"up-share {ev['predictedUpShare']:.2f}  "
                  f"wf {ev['walkForward']['blocksAboveMajority']}/{ev['walkForward']['blocksScored']}  "
                  f"-> {written['name']} {'GO' if res['gatesMet'] else 'NO-GO'}")
            summary["horizons"][key] = {k: v for k, v in res.items() if not k.startswith("_")}
            summary["horizons"][key]["artifact"] = {"modelVersion": written["name"],
                                                    "sha256": written["sha256"]}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"crypto_short_{a.tag}.json"
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
