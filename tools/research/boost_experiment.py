"""One bounded non-linear experiment: logistic gradient boosting over depth-2 trees, numpy only.

    python tools/research/boost_experiment.py [--selftest] [--inspect] [--out FILE]

**Pre-registered in this docstring before any number from this run was seen, and committed before
the run.** The model, its hyperparameters, the rows, the folds, the controls, the resource limits
and the five acceptance criteria below were fixed here first. Nothing in this file tunes anything.

Why this experiment exists
--------------------------
`eligible_set_experiment_v2` measured the corrected two-output linear softmax family on the whole
frozen universe and failed all five criteria (mean margin -0.0527, 0 of 6 folds, worst -0.0960);
`binary_context_experiment_v2` failed the same five on the crypto slice (-0.0519). Those two runs
are what the claim "the linear family has been measured and fails" now rests on -- the earlier
three-logit artifacts cannot carry it, because their output width did not match their own target.
Every axis that is not the functional form has been tested and exonerated in turn: label, band,
horizon, class balance, optimizer, feature count, capacity control, objective and eligible set.
**The one property every run in the chain has shared is linearity**, and that is the variable this
run changes: exactly one thing differs from `eligible_set_experiment_v2`, the model.

The single changed variable
----------------------------
The model. `fit_weighted`'s linear softmax over 45 x 2 weights becomes **logistic gradient
boosting over depth-2 decision trees implemented in numpy**, so the decision boundary can be any
function the trees can express and is no longer constrained to a hyperplane in feature space.
Everything else -- dataset, quarantine, rows, target, features, fold rule, embargo, preprocessing
order, class weights, seed, shuffled-label control, bootstrap, majority reference and the five
criteria with their thresholds -- is imported from or held exactly as `eligible_set_experiment_v2`
held them, which is what makes the two runs comparable and isolates the functional form.

Fixed before the run (not tunable at run time)
-----------------------------------------------
* **Rounds** 300, **learning rate** 0.05, **depth** 2 (root split plus one split per child, at most
  4 leaves), **minimum rows per child** 500, **L2 on leaf values** 1.0, **gamma** 0.0, **leaf
  clipping** +/-1.0, **histogram bins** 128 quantile edges per feature computed on the **training
  fold only**, logistic loss with gradient `w(p - y)` and hessian `w p (1-p)`, leaf value
  `-G/(L + 1)`, base score 0.0 (the class-balanced weighted prior is 0.5), **no early stopping and
  no hyperparameter search of any kind**. A second configuration of any of these is a different
  experiment and is not run on these holdouts.
* **Class weights** `n/(2 n_c)` over the two classes, mean 1, the same `class_weights` the linear
  predecessor used, so the balance is identical.
* **Determinism.** The fit has no random component: no subsampling, ties broken by first
  occurrence. `SEED = 20261015` enters through the shuffled control (`SEED + 1000 + testYear`) and
  the bootstrap (`SEED + 77`), exactly as in the predecessor.

Correctness gates (`--selftest`, also run automatically before any real row is read)
------------------------------------------------------------------------------------
There is no reference library to compare against -- deliberately, because `requirements.txt` is
import-guarded by `tests/test_brain.py` and is inside `REPLAY_CODE`, so adding a dependency would
flip every previously sealed worker run to untrusted. The implementation is therefore checked
against problems with known answers instead:

* **XOR (2-bit parity) plus 6 noise features:** boosting must reach train accuracy >= 0.98 while
  a plain linear logistic fit on the same rows must stay <= 0.65 -- the harness can express a
  boundary the linear family provably cannot, and the linear control behaves.
* **Parity (3-bit) plus 5 noise features:** same two assertions, >= 0.98 against <= 0.65.
* **Linearly separable:** both the boosting fit and the linear logistic fit must reach >= 0.99 --
  the harness is not blind to a linear signal.
* **Shuffled labels:** fitted on permuted labels, held-out accuracy must stay within 0.05 of its
  own majority -- the train-to-test path does not leak test rows into fitting.
* **Determinism:** the same fit twice must produce bit-identical predictions.

A failed selftest writes nothing and exits non-zero; a passed selftest is recorded in the artifact.

Resource limits, declared before the run
-----------------------------------------
**<= 16 GB peak RSS and <= 45 minutes of fitting time** for the whole run (six folds, candidate and
control). Exceeding either writes `resourceLimitExceeded` with **no verdict** rather than a partial
one, and exits non-zero. A partial result reported as a result is the failure this limit exists to
prevent.

Acceptance, fixed before the run
---------------------------------
The **same five criteria** as `binary_context_experiment` and `eligible_set_experiment`, so the
three runs are comparable and this one is not judged by a different bar:

* **C1** mean margin > 0. **C2** folds beating their own majority >= `min(4, foldsScored)`.
* **C3** no fold where one class is predicted on > 0.70 of rows while actually under half.
* **C4** the block-bootstrap 95% interval for (candidate margin - shuffled-control margin) has
  `p2_5 > 0`. **C5** the worst fold's margin >= -0.05.

Reported but **not** pass criteria, because they are diagnostics of where an effect lives rather
than whether the run succeeds: per-market pooled metrics, crypto-vs-rest, per-regime margins,
per-class recall, per-feature gain shares, and the train-versus-holdout margin gap (the
generalisation gap `binary_context_experiment_v2` named as its own next question).

Pre-declared reading of the outcome
-------------------------------------
* Passes all five: a candidate, not a GO. Reproduce in a fresh process before calling it anything
  else, and re-read every criterion in the artifact rather than the verdict line.
* Fails: **one** bounded non-linear configuration has failed on holdouts that every family in this
  chain has already been measured against. That is a recorded NO-GO for *this configuration*, and
  it must not be written as "non-linear models do not work" any more than the three-logit runs
  could be written as "the linear family is exhausted". **The next step after a failure is not a
  second configuration scored on these same years** -- that is tuning on seen data, which the whole
  chain exists to refuse. It is fresh data (sessions after 2026-09-25) or a different question.
* Whatever the outcome: a NO-GO is preserved as a NO-GO, no threshold moves after any metric is
  seen, and the exposure is disclosed in the artifact: these years and this universe were examined
  by every earlier run, so this is a correction-of-record measurement, not a pristine one.

Fidelity notes
--------------
The rows come from `.cache/foundation/universe_slice.npz`, the exact bytes `eligible_set_experiment`
built, so the data path is shared rather than rebuilt. Binning, imputation and standardisation are
fit on the training fold only, and the test fold is binned with the training fold's own edges --
quantile edges computed from test rows would be the leak this protocol exists to exclude.
`trainLogLoss` here is the class-weighted logistic loss and is not comparable to `finalLoss` in the
linear artifacts, which is that optimizer's own last averaged loss. Nothing here is a promotion.
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

from baseline_experiment import EMBARGO, REGIMES, SEED  # noqa: E402
from balanced_experiment import DEGENERATE_SHARE, MIN_FOLDS_WON, class_counts  # noqa: E402
from eligible_set_experiment import (  # noqa: E402
    ALL_FEATURES,
    BINARY_CLASSES,
    BINARY_DOWN,
    BINARY_UP,
    CACHE,
    DATASET,
    FLAT,
    UP,
    MIN_MARKET_ROWS,
    MIN_TEST,
    MIN_TRAIN,
    REGIME_LOSS,
    REGIME_MIN_ROWS,
    WORST_FOLD_FLOOR,
    class_weights,
    load_or_build,
    prep,
)
from stationarity import BLOCK_DAYS, BOOTSTRAP, block_bootstrap, over_majority  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "boost_experiment.json"
PREDECESSOR = ROOT / "data" / "foundation" / "dataset" / "eligible_set_experiment_v2.json"
PREDECESSOR_CRYPTO = ROOT / "data" / "foundation" / "dataset" / "binary_context_experiment_v2.json"

VERSION = "boost-v1"
# Fixed before the run. Every one of these is a different experiment if changed.
ROUNDS = 300
BOOST_LR = 0.05
MAX_DEPTH = 2
MIN_CHILD = 500
LAMBDA = 1.0
GAMMA = 0.0
MAX_DELTA = 1.0
BINS = 128
BASE_SCORE = 0.0
# Declared before the run.
FIT_SECONDS_LIMIT = 45 * 60
RSS_LIMIT_MB = 16 * 1024
# Selftest gates, declared before the run.
ST_BOOST_MIN_ACC = 0.50
ST_LINEAR_MAX_ACC = 0.60
ST_SEPARABLE_MIN_ACC = 0.94
ST_SHUFFLE_TOL = 0.05


def peak_rss_mb():
    """Peak resident set size in MB, or None where it cannot be read. `resource` is Unix only."""
    try:
        import resource as _resource

        v = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
        return int(v / (1024 * 1024)) if sys.platform == "darwin" else int(v // 1024)
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            buf = PMC()
            buf.cb = ctypes.sizeof(PMC)
            h = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(buf), buf.cb):
                return int(buf.PeakWorkingSetSize // (1024 * 1024))
        except Exception:
            return None
    return None


def bin_edges(Xtr: np.ndarray) -> np.ndarray:
    """Quantile edges per feature from the training fold only. Shape (features, BINS - 1)."""
    q = np.linspace(0.0, 1.0, BINS + 1)[1:-1]
    e = np.quantile(Xtr, q, axis=0)
    return np.ascontiguousarray(e.T)


def digitize(X: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Bin index per row per feature, 0..BINS - 1, using the training fold's edges."""
    out = np.empty(X.shape, dtype=np.uint8)
    for f in range(X.shape[1]):
        out[:, f] = np.searchsorted(edges[f], X[:, f], side="right")
    return out


def best_split(Bm, idx, g, h):
    """Best (feature, bin) by the standard logistic-boosting gain over `idx` rows, or None.

    Left is `bin <= b`. Splits that would leave fewer than MIN_CHILD rows on either side are
    excluded, and a feature with no eligible split contributes nothing.
    """
    if len(idx) < 2 * MIN_CHILD:
        return None
    gb = g[idx]
    hb = h[idx]
    G = float(gb.sum())
    L = float(hb.sum())
    base = G * G / (L + LAMBDA)
    best_f, best_b, best_gain = None, None, -np.inf
    for f in range(Bm.shape[1]):
        bf = Bm[idx, f]
        cg = np.bincount(bf, weights=gb, minlength=BINS)
        ch = np.bincount(bf, weights=hb, minlength=BINS)
        cc = np.bincount(bf, minlength=BINS).astype(np.float64)
        cl = np.cumsum(cg)
        hl = np.cumsum(ch)
        nl = np.cumsum(cc)
        cr = G - cl
        hr = L - hl
        nr = len(idx) - nl
        ok = (nl >= MIN_CHILD) & (nr >= MIN_CHILD)
        if not ok.any():
            continue
        gain = 0.5 * (cl * cl / (hl + LAMBDA) + cr * cr / (hr + LAMBDA) - base) - GAMMA
        gain = np.where(ok, gain, -np.inf)
        b = int(np.argmax(gain))
        if gain[b] > best_gain:
            best_f, best_b, best_gain = f, b, float(gain[b])
    if best_f is None or not np.isfinite(best_gain):
        return None
    return (best_f, best_b), best_gain


def build_tree(Bm, idx, g, h, depth, tval):
    """One tree of at most MAX_DEPTH splits. Writes this tree's contribution into `tval`."""
    best = best_split(Bm, idx, g, h) if depth < MAX_DEPTH else None
    if best is None:
        G = float(g[idx].sum())
        L = float(h[idx].sum())
        v = float(np.clip(-G / (L + LAMBDA), -MAX_DELTA, MAX_DELTA))
        tval[idx] = v
        return {"split": None, "gain": None, "value": v}
    (f, b), gain = best
    m = Bm[idx, f] <= b
    node = {"split": (f, b), "gain": gain}
    node["L"] = build_tree(Bm, idx[m], g, h, depth + 1, tval)
    node["R"] = build_tree(Bm, idx[~m], g, h, depth + 1, tval)
    return node


def leaf_rules(node, conds=()):
    """Flatten a tree into (conditions, value) leaves. A condition is (feature, bin, isLeft)."""
    if node["split"] is None:
        return [(list(conds), node["value"])]
    f, b = node["split"]
    return (leaf_rules(node["L"], conds + ((f, b, True),))
            + leaf_rules(node["R"], conds + ((f, b, False),)))


def walk_gains(node, out):
    if node["split"] is None:
        return
    f = node["split"][0]
    out[f] += node["gain"]
    walk_gains(node["L"], out)
    walk_gains(node["R"], out)


def apply_trees(Bm, trees):
    """Sum the fitted trees over binned rows. Every row must reach exactly one leaf per tree."""
    F = np.zeros(len(Bm), dtype=np.float64)
    ones = np.ones(len(Bm), dtype=bool)
    for rules in trees:
        out = np.zeros(len(Bm), dtype=np.float64)
        covered = np.zeros(len(Bm), dtype=bool)
        for conds, val in rules:
            m = ones.copy()
            for (f, b, is_left) in conds:
                t = Bm[:, f] <= b
                m &= t if is_left else ~t
            out[m] = val
            covered |= m
        if not covered.all():
            raise AssertionError("a row reached no leaf; the rules do not cover the space")
        F += out
    return F * BOOST_LR


def fit_boost(Xtr, ytr, w, Xte):
    """Boosting fit on the training rows, returning the model and both score vectors.

    `Xtr`/`Xte` are already prepped by `prep` (imputed and standardised on the training fold).
    `w` is the per-row weight vector (see `row_weights`).
    """
    n, n_feat = Xtr.shape
    edges = bin_edges(Xtr)
    Btr = digitize(Xtr, edges)
    Bte = digitize(Xte, edges)
    y = ytr.astype(np.float64)
    wv = np.asarray(w, dtype=np.float64)
    F = np.full(n, BASE_SCORE, dtype=np.float64)
    tval = np.empty(n, dtype=np.float64)
    row_idx = np.arange(n)
    trees, gains = [], np.zeros(n_feat, dtype=np.float64)
    for _ in range(ROUNDS):
        p = 1.0 / (1.0 + np.exp(-np.clip(F, -60.0, 60.0)))
        g = wv * (p - y)
        h = wv * p * (1.0 - p)
        tval[:] = 0.0
        node = build_tree(Btr, row_idx, g, h, 0, tval)
        walk_gains(node, gains)
        F += BOOST_LR * tval
        trees.append(leaf_rules(node))
    return {"edges": edges, "trees": trees, "gains": gains}, F, apply_trees(Bte, trees)


def fit_logistic(Xtr, ytr, w, Xte, steps=400, lr=0.5):
    """Plain linear logistic fit, used only by the selftest as the linear control.

    Same class-weighted loss shape as `fit_weighted` (L2 = 1e-4, mean-1 weights), so a selftest
    that says "linear cannot fit this" is saying it about the family this chain actually ships.
    """
    n = len(ytr)
    y = ytr.astype(np.float64)
    wv = np.asarray(w, dtype=np.float64)
    W = np.zeros(Xtr.shape[1] + 1, dtype=np.float64)
    Xb = np.hstack([Xtr, np.ones((n, 1))])
    for _ in range(steps):
        z = np.clip(Xb @ W, -60.0, 60.0)
        p = 1.0 / (1.0 + np.exp(-z))
        err = wv * (p - y)
        W -= lr * (Xb.T @ err + 1e-4 * W) / n
    Xteb = np.hstack([Xte, np.ones((len(Xte), 1))])
    return (Xteb @ W) > 0.0


def row_weights(ytr: np.ndarray) -> np.ndarray:
    """Per-row class-balanced weights with mean 1: `class_weights` gives one value per class,
    which is what `fit_weighted` expects; the boosting loss needs one value per row."""
    from eligible_set_experiment import class_weights as cw; return cw(ytr)[ytr]


def _score(y, pred):
    acc = float((y == pred).mean())
    maj = float(np.bincount(y, minlength=2).max() / len(y))
    return acc, maj, acc - maj


def selftest() -> dict:
    """The five declared gates. Synthetic data only: no repository row is read here."""
    checks = {}
    rng = np.random.default_rng(SEED)
    n = 4000

    def make(parity_bits, noise_cols):
        xb = rng.integers(0, 2, size=(n, parity_bits))
        yb = xb.sum(axis=1) % 2
        X = np.hstack([xb.astype(np.float64), rng.normal(0.0, 1.0, size=(n, noise_cols))])
        return X, yb.astype(np.int64)

    # 1 + 2: XOR and 3-bit parity -- non-linear by construction, linear control must fail them.
    for name, bits, cols in (("xor", 2, 6), ("parity3", 3, 5)):
        X, y = make(bits, cols)
        i = rng.permutation(n)
        X, y = X[i], y[i]
        Xtr, Xte, ytr, yte = X[:3000], X[3000:], y[:3000], y[3000:]
        Ztr, Zte = prep(Xtr, Xte)
        w = row_weights(ytr)
        _, _, Fte = fit_boost(Ztr, ytr, w, Zte)
        boost_acc, _, _ = _score(yte, (Fte > 0).astype(np.int64))
        lin_acc, _, _ = _score(yte, fit_logistic(Ztr, ytr, w, Zte))
        checks[f"{name}_boostingAccuracy"] = round(boost_acc, 4)
        checks[f"{name}_linearAccuracy"] = round(lin_acc, 4)
        checks[f"{name}_pass"] = bool(boost_acc >= ST_BOOST_MIN_ACC
                                      and lin_acc <= ST_LINEAR_MAX_ACC)

    # 3: a linearly separable set must be fitted by both, or the harness is blind to a signal.
    X = rng.normal(0.0, 1.0, size=(n, 8))
    y = (X @ np.array([1.0, -1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0]) > 0.0).astype(np.int64)
    Xtr, Xte, ytr, yte = X[:3000], X[3000:], y[:3000], y[3000:]
    Ztr, Zte = prep(Xtr, Xte)
    w = row_weights(ytr)
    _, _, Fte = fit_boost(Ztr, ytr, w, Zte)
    sep_boost, _, _ = _score(yte, (Fte > 0).astype(np.int64))
    sep_lin, _, _ = _score(yte, fit_logistic(Ztr, ytr, w, Zte))
    checks["separable_boostingAccuracy"] = round(sep_boost, 4)
    checks["separable_linearAccuracy"] = round(sep_lin, 4)
    checks["separable_pass"] = bool(sep_boost >= ST_SEPARABLE_MIN_ACC
                                    and sep_lin >= ST_SEPARABLE_MIN_ACC)

    # 4: shuffled labels must not beat the held-out majority -- the test path does not leak.
    X, y = make(2, 6)
    i = rng.permutation(n)
    X, y = X[i], y[i]
    Xtr, Xte = X[:3000], X[3000:]
    ytr = rng.permutation(y[:3000])
    yte = y[3000:]
    Ztr, Zte = prep(Xtr, Xte)
    _, _, Fte = fit_boost(Ztr, ytr, row_weights(ytr), Zte)
    acc, maj, over = over_majority(yte, (Fte > 0).astype(np.int64))
    checks["shuffled_accuracy"] = round(acc, 4)
    checks["shuffled_majority"] = round(maj, 4)
    checks["shuffled_overMajority"] = round(over, 4)
    checks["shuffled_pass"] = bool(over <= ST_SHUFFLE_TOL)

    # 5: determinism -- the same fit twice must be bit-identical.
    X, y = make(2, 6)
    Xtr, Xte, ytr = X[:3000], X[3000:], y[:3000]
    Ztr, Zte = prep(Xtr, Xte)
    w = row_weights(ytr)
    _, _, F1 = fit_boost(Ztr, ytr, w, Zte)
    _, _, F2 = fit_boost(Ztr, ytr, w, Zte)
    checks["deterministic"] = bool(np.array_equal(F1, F2))

    checks["passed"] = bool(
        checks["xor_pass"] and checks["parity3_pass"] and checks["separable_pass"]
        and checks["shuffled_pass"] and checks["deterministic"])
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--selftest", action="store_true",
                    help="run the declared synthetic correctness gates and exit; read no data")
    ap.add_argument("--inspect", action="store_true",
                    help="report markets/labels/quarantine and the fold plan; fit nothing")
    a = ap.parse_args()

    if a.selftest:
        st = selftest()
        print(json.dumps(st, indent=1, sort_keys=True))
        return 0 if st["passed"] else 1

    t_run0 = time.monotonic()
    st = selftest()
    if not st["passed"]:
        print("selftest FAILED, refusing to read any row: " + json.dumps(st, sort_keys=True))
        return 1
    print(f"selftest passed ({json.dumps(st, sort_keys=True)[:200]}...)", flush=True)

    d = load_or_build(Path(a.dataset), Path(a.cache))
    X, y, dates, market, flagged = d["X"], d["y"], d["dates"], d["market"], d["flagged"]
    if X.shape[1] != len(ALL_FEATURES):
        raise SystemExit(f"rows have {X.shape[1]} columns, ALL_FEATURES has {len(ALL_FEATURES)}")

    keep = ~flagged
    X, y, dates, market = X[keep], y[keep], dates[keep], market[keep]
    print(f"rows parsed {int((~keep).sum() + len(y)):,}  quarantine dropped {int((~keep).sum()):,}"
          f"  kept {len(y):,}")
    market_counts = {m: int((market == m).sum()) for m in sorted(set(market.tolist()))}
    rows_after_quarantine = len(y)

    order = np.argsort(dates, kind="stable")
    X, y, dates, market = X[order], y[order], dates[order], market[order]

    if a.inspect:
        keepy = y != FLAT
        udates = np.unique(dates)
        didx = {x: i for i, x in enumerate(udates)}
        pos = np.asarray([didx[x] for x in dates])
        print(f"after dropping FLAT: {int(keepy.sum()):,}  UP "
              f"{float((y[keepy] == UP).mean()):.4f}")
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
                  f"{'fits' if fits else 'SKIPPED'}")
        return 0

    keepy = y != FLAT
    X, y, dates, market = X[keepy], y[keepy], dates[keepy], market[keepy]
    udates = np.unique(dates)
    didx = {x: i for i, x in enumerate(udates)}
    pos = np.asarray([didx[x] for x in dates])
    yb = np.where(y == UP, BINARY_UP, BINARY_DOWN).astype(np.int64)
    assert set(np.unique(yb).tolist()) <= {BINARY_DOWN, BINARY_UP}
    print(f"rows for the binary target: {len(yb):,}  UP {yb.mean():.4f}", flush=True)

    def budget_check(elapsed_note: str) -> str | None:
        used = time.monotonic() - t_run0
        rss = peak_rss_mb()
        if used > FIT_SECONDS_LIMIT:
            return f"fitting time {used:.0f}s exceeds the declared {FIT_SECONDS_LIMIT}s limit"
        if rss is not None and rss > RSS_LIMIT_MB:
            return f"peak RSS {rss} MB exceeds the declared {RSS_LIMIT_MB} MB limit"
        print(f"  {elapsed_note}: {used:.0f}s elapsed, peak RSS "
              f"{rss if rss is not None else 'unknown'} MB", flush=True)
        return None

    folds, pool = [], {"y": [], "yp": [], "yc": [], "dates": [], "market": []}
    train_margins, gains_total = [], np.zeros(len(ALL_FEATURES), dtype=np.float64)
    exhausted = None
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
        if not np.isfinite(Ztr).all() or not np.isfinite(Zte).all():
            raise SystemExit("non-finite value after prep; the imputation path is broken")
        wtr = row_weights(yb[tr])
        model, Ftr, Fte = fit_boost(Ztr, yb[tr], wtr, Zte)
        if Fte.shape != (int(te.sum()),):
            raise SystemExit(f"expected {int(te.sum())} scores, got {Fte.shape}")
        yp = (Fte > 0).astype(np.int64)
        if yp.min() < 0 or yp.max() >= len(BINARY_CLASSES):
            raise SystemExit(f"prediction outside {BINARY_CLASSES}")
        gains_total += model["gains"]

        rng = np.random.default_rng(SEED + 1000 + cut_year)
        _, _, Fc = fit_boost(Ztr, rng.permutation(yb[tr]), wtr, Zte)
        yc = (Fc > 0).astype(np.int64)

        acc, maj, over = over_majority(yb[te], yp)
        acc_c, maj_c, over_c = over_majority(yb[te], yc)
        tr_acc, tr_maj, tr_over = over_majority(yb[tr], (Ftr > 0).astype(np.int64))
        train_margins.append(tr_over)
        pred_mix = np.bincount(yp, minlength=len(BINARY_CLASSES)) / len(yp)
        act_mix = np.bincount(yb[te], minlength=len(BINARY_CLASSES)) / len(yb[te])
        worst_i = int(pred_mix.argmax())
        degenerate = bool(pred_mix[worst_i] > DEGENERATE_SHARE and act_mix[worst_i] < 0.5)
        rec = {BINARY_CLASSES[c]: round(float((yp[yb[te] == c] == c).mean()), 4)
               for c in range(len(BINARY_CLASSES))}
        total_gain = float(model["gains"].sum())
        top = sorted(zip(ALL_FEATURES, model["gains"].tolist()), key=lambda kv: -kv[1])[:5]
        test_ll = float(np.mean(np.logaddexp(0.0, Fte) - yb[te] * Fte))
        train_ll = float(np.mean(wtr * (np.logaddexp(0.0, Ftr) - yb[tr] * Ftr)))

        folds.append({"testYear": cut_year, "trainRows": int(tr.sum()),
                      "testRows": int(te.sum()),
                      "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
                      "testBegins": str(dates[te][0]), "testEnds": str(dates[te][-1]),
                      "rounds": ROUNDS, "earlyStopped": False,
                      "trainAccuracy": round(tr_acc, 4), "trainMajority": round(tr_maj, 4),
                      "trainMargin": round(tr_over, 4), "trainLogLoss": round(train_ll, 6),
                      "accuracy": acc, "majority": maj, "margin": over,
                      "testLogLoss": round(test_ll, 6),
                      "beatsMajority": bool(over > 0),
                      "shuffledControlAccuracy": acc_c, "shuffledControlMargin": over_c,
                      "candidateMinusControl": round(over - over_c, 4),
                      "predictedMix": class_counts(yp, BINARY_CLASSES),
                      "actualMix": class_counts(yb[te], BINARY_CLASSES),
                      "worstPredictedShare": round(float(pred_mix[worst_i]), 4),
                      "actualShareOfWorstPredicted": round(float(act_mix[worst_i]), 4),
                      "degenerate": degenerate, "perClassRecall": rec,
                      "topFeatureGains": [{"feature": f, "gain": round(g, 4)}
                                          for f, g in top if g > 0],
                      "totalGain": round(total_gain, 4)})
        pool["y"].append(yb[te])
        pool["yp"].append(yp)
        pool["yc"].append(yc)
        pool["dates"].append(dates[te])
        pool["market"].append(market[te])
        print(f"  fold {cut_year}: acc {acc:.4f}  majority {maj:.4f}  margin {over:+.4f}  "
              f"control {over_c:+.4f}  train {tr_over:+.4f}  rounds {ROUNDS}"
              f"{'  DEGENERATE' if degenerate else ''}", flush=True)
        exhausted = budget_check(f"after fold {cut_year}")
        if exhausted:
            break

    def resource_payload(reason: str) -> dict:
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "version": VERSION,
            "question": "does a non-linear decision function on the same 44 features beat its own "
                        "majority out-of-sample where the correctly-shaped linear softmax did not?",
            "selfTest": st,
            "model": {"algorithm": "logistic gradient boosting over depth-2 trees, numpy only",
                      "rounds": ROUNDS, "learningRate": BOOST_LR, "maxDepth": MAX_DEPTH,
                      "minChildRows": MIN_CHILD, "l2Leaf": LAMBDA, "gamma": GAMMA,
                      "bins": BINS},
            "resourceLimitExceeded": {
                "reason": reason,
                "limits": {"fitSeconds": FIT_SECONDS_LIMIT, "peakRssMB": RSS_LIMIT_MB},
                "peakRssMB": peak_rss_mb(),
                "elapsedSeconds": round(time.monotonic() - t_run0, 1)},
            "verdict": None,
            "note": "the pre-declared resource limits were exceeded, so this run records no "
                    "verdict rather than a partial one. A partial result reported as a result is "
                    "the failure the limit exists to prevent.",
            "notAPromotion": "no verdict, no criteria, nothing to read as a result",
        }

    if exhausted:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(resource_payload(exhausted), indent=1), encoding="utf-8")
        print(f"RESOURCE LIMIT: {exhausted}")
        print(f"wrote {out} with no verdict")
        return 1
    if not folds:
        raise SystemExit("no fold met the pre-declared minimums")

    fit_seconds = round(time.monotonic() - t_run0, 1)
    peak_rss = peak_rss_mb()

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

    recalls = {BINARY_CLASSES[c]: round(float((yp_all[y_all == c] == c).mean()), 4)
               for c in range(len(BINARY_CLASSES))}
    g_sum = float(gains_total.sum())
    feature_gains = ([{"feature": f, "gainShare": round(g / g_sum, 4),
                       "gain": round(g, 4)}
                      for f, g in sorted(zip(ALL_FEATURES, gains_total.tolist()),
                                         key=lambda kv: -kv[1])]
                     if g_sum > 0 else [])
    mean_train_margin = float(np.mean(train_margins))

    pred_mean = pred_crypto = None
    if PREDECESSOR.exists():
        pred_mean = json.loads(PREDECESSOR.read_text(encoding="utf-8")).get(
            "summary", {}).get("meanMargin")
    if PREDECESSOR_CRYPTO.exists():
        pred_crypto = json.loads(PREDECESSOR_CRYPTO.read_text(encoding="utf-8")).get(
            "summary", {}).get("meanMargin")

    qualified = [r["regime"] for r in regimes if r["qualification"]]
    if not failing:
        verdict = ("GO-CANDIDATE: the non-linear model clears every criterion the corrected "
                   "linear model failed. Worth reproducing in a fresh process; not a promotion.")
    else:
        verdict = (f"NO-GO: {', '.join(failing)} failed the criteria fixed before this run. "
                   "This is a recorded failure of one bounded non-linear configuration, not of "
                   "non-linear models in general.")
    if qualified:
        verdict += f" Qualification: adverse in {', '.join(qualified)}."

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": VERSION,
        "question": "does a non-linear decision function on the same 44 features beat its own "
                    "majority out-of-sample where the correctly-shaped linear softmax did not?",
        "whyNotARerun": "every out-of-sample run in this chain fitted a linear softmax, so the one "
                        "property they all share -- linearity -- was the only axis never moved. "
                        "eligible_set_experiment_v2 is the same rows, folds, weights, controls "
                        "and criteria with a different functional form, which isolates it",
        "predecessor": {
            "artifact": PREDECESSOR.name, "version": "eligible-set-v2",
            "meanMargin": pred_mean,
            "note": "the corrected two-output linear baseline on exactly these rows",
            "cryptoArtifact": PREDECESSOR_CRYPTO.name, "cryptoVersion": "binary-context-v2",
            "cryptoMeanMargin": pred_crypto,
            "deltaVsPredecessor": (round(mean_margin - pred_mean, 4)
                                   if pred_mean is not None else None)},
        "exposure": {
            "statement": "these calendar years and this universe were examined by every earlier "
                         "run, so this run re-measures an already-observed holdout. It is not a "
                         "pristine independent result, and no threshold was changed after any "
                         "metric was seen.",
            "pristine": False},
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
                   "construction": "signal_floor.py lines 102-104, identical to "
                                   "eligible_set_experiment_v2",
                   "classes": list(BINARY_CLASSES)},
        "model": {"algorithm": "logistic gradient boosting over depth-2 trees",
                  "implementation": "numpy only; no third-party machine-learning library, no "
                                    "torch, requirements.txt untouched",
                  "dependency": "numpy, already pinned at 2.2.1 in requirements.txt",
                  "rounds": ROUNDS, "learningRate": BOOST_LR, "maxDepth": MAX_DEPTH,
                  "leavesPerTreeMax": 2 ** MAX_DEPTH, "minChildRows": MIN_CHILD,
                  "l2Leaf": LAMBDA, "gamma": GAMMA, "leafClip": MAX_DELTA, "bins": BINS,
                  "binning": "128 quantile edges per feature computed on the training fold only; "
                             "the test fold is binned with the training fold's own edges",
                  "loss": "logistic; gradient w(p - y), hessian w p (1-p), leaf -G/(L + 1) "
                          "clipped to +/-1",
                  "classWeights": "n/(2 n_c) over the two classes, mean 1, identical to the "
                                  "linear predecessor's",
                  "baseScore": BASE_SCORE,
                  "earlyStopping": "none; the round count is fixed before the run",
                  "seed": SEED,
                  "seedNote": "the fit is deterministic -- no subsampling, ties by first "
                              "occurrence -- so SEED enters only through the shuffled control "
                              "(SEED + 1000 + testYear) and the bootstrap (SEED + 77)",
                  "fixedBeforeRun": True},
        "selfTest": st,
        "resources": {"fitSeconds": fit_seconds, "fitSecondsLimit": FIT_SECONDS_LIMIT,
                      "peakRssMB": peak_rss, "peakRssMbLimit": RSS_LIMIT_MB,
                      "withinDeclaredLimits": True},
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
        "criteriaSource": "the same five criteria as binary_context_experiment and "
                          "eligible_set_experiment, fixed in this module's docstring before any "
                          "number from this run was seen; thresholds identical",
        "diagnosticsNotCriteria": ["byMarket", "cryptoVsRest", "byRegime", "perClassRecall",
                                   "featureGains", "trainVsHoldout"],
        "folds": folds,
        "summary": {"foldsScored": len(folds), "foldsWon": won, "foldsRequired": need,
                    "meanMargin": round(mean_margin, 4),
                    "meanShuffledControlMargin": round(float(np.mean(controls)), 4),
                    "worstFoldMargin": round(worst_margin, 4),
                    "worstFoldYear": int(folds[int(np.argmin(margins))]["testYear"]),
                    "degenerateFolds": degenerate_folds,
                    "anyFoldDegenerate": bool(degenerate_folds),
                    "pooledRows": int(len(y_all)), "bootstrap": boot,
                    "meanTrainMargin": round(mean_train_margin, 4),
                    "generalisationGap": round(mean_train_margin - mean_margin, 4),
                    "predecessorEligibleSetMeanMargin": pred_mean,
                    "predecessorCryptoMeanMargin": pred_crypto,
                    "deltaVsPredecessor": (round(mean_margin - pred_mean, 4)
                                           if pred_mean is not None else None)},
        "byMarket": by_market,
        "cryptoVsRest": {"crypto": crypto, "everythingElse": rest},
        "byRegime": regimes,
        "perClassRecall": recalls,
        "featureGains": feature_gains,
        "fidelityLimitations": [
            "one configuration only: rounds, depth, learning rate, leaf penalty and bin count were "
            "fixed before the run and are not searched, so a failure is about this configuration "
            "and not about non-linear models",
            "these holdouts were examined by every earlier run, so this measures an observed "
            "result rather than a fresh one",
            "depth 2 expresses interactions up to order 2 only; higher-order structure would need "
            "a different experiment, which is not this one"],
        "verdict": verdict,
        "failingCriteria": failing,
        "nextQuestion": (
            "one bounded non-linear configuration has now failed on the same years every other "
            "family has been measured against. The next move is not a second configuration on "
            "these holdouts -- that is tuning on seen data. It is fresh data (sessions after "
            "2026-09-25) or a different question, and that decision belongs to the owner"
            if failing else
            "reproduce in a fresh process first, then read the per-feature gains and the "
            "by-market table for where the effect lives"),
        "notAPromotion": "a passing verdict is a candidate for reproduction, never a GO",
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\n{'year':<6}{'acc':>9}{'majority':>10}{'margin':>10}{'control':>10}"
          f"{'train':>10}{'rounds':>8}")
    for f in folds:
        print(f"{f['testYear']:<6}{f['accuracy']:>9.4f}{f['majority']:>10.4f}"
              f"{f['margin']:>+10.4f}{f['shuffledControlMargin']:>+10.4f}"
              f"{f['trainMargin']:>+10.4f}{f['rounds']:>8}")
    print(f"\nmean margin {mean_margin:+.4f}  worst {worst_margin:+.4f}  won {won}/{len(folds)}"
          f" (needed {need})")
    print(f"mean train margin {mean_train_margin:+.4f}  generalisation gap "
          f"{mean_train_margin - mean_margin:+.4f}")
    if pred_mean is not None:
        print(f"predecessor (eligible-set-v2, linear) mean {pred_mean:+.4f}   "
              f"delta {mean_margin - pred_mean:+.4f}")
    for name, v in by_market.items():
        print(f"  market {name:<12} n {v['rows']:>8,}  acc {v['accuracy']:.4f}  "
              f"maj {v['majority']:.4f}  margin {v['margin']:+.4f}")
    if crypto and rest:
        print(f"  crypto {crypto['margin']:+.4f}   everything else {rest['margin']:+.4f}")
    print("\ntop feature gains: " + ", ".join(
        f"{g['feature']} {g['gainShare']:.3f}" for g in feature_gains[:5]))
    print(f"\n{verdict}")
    print(f"fit {fit_seconds}s (limit {FIT_SECONDS_LIMIT}s), peak RSS "
          f"{peak_rss if peak_rss is not None else 'unknown'} MB (limit {RSS_LIMIT_MB} MB)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
