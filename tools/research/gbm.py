"""A histogram gradient-boosted tree for binary logistic loss, in numpy.

    model = fit(X, y, bins=64, rounds=300, depth=3, lr=0.05, l2=1.0)
    p = predict_proba(model, X_test)

Why this is written out rather than imported
--------------------------------------------
The repository declares every third-party import it uses (`tests/test_brain.py` fails on an
undeclared one) and the Python side is pinned to numpy, pandas, requests and psycopg. Adding
LightGBM or scikit-learn to serve one model would put a 40 MB wheel and a compiled extension into
a lane whose whole point is that it runs anywhere; and the existing brains are all hand-rolled
numpy softmax fits (`baseline_experiment.fit_softmax`), so a boosted tree written the same way
sits beside them rather than beside a new dependency.

It is also the reason a linear model was not simply accepted. Every recorded crypto brain is a
regularised softmax and every one of them collapsed onto one class: the features that carry
short-horizon information -- taker imbalance against volatility, range position against trend age
-- interact, and a linear model in those features cannot express the interaction. Whether a tree
finds anything is a question this answers with a measurement, not an assumption.

What it is
----------
Standard second-order boosting, the form LightGBM and XGBoost both implement:

  * features are pre-binned into quantile bins once, so a split search is a histogram scan
    rather than a sort;
  * each round fits one depth-limited tree to the gradient and hessian of the logistic loss;
  * a split's gain is the usual `G^2 / (H + l2)` improvement, with a minimum-hessian floor so a
    leaf is never fitted on a handful of rows;
  * leaves hold `-G / (H + l2)`, shrunk by the learning rate.

Histograms are built with one `bincount` over `node_rows * n_features` combined indices rather
than one per feature, and a sibling's histogram is the parent's minus its brother's -- the two
optimisations that make the difference between a minute and an hour on 300,000 rows.

Determinism
-----------
No sampling, no randomness: the same matrix and the same arguments produce the same trees, so a
retrained artifact that differs is a data change and never a seed.
"""

from __future__ import annotations

import numpy as np


def quantile_bins(X: np.ndarray, bins: int = 64) -> np.ndarray:
    """Bin edges per feature, from the training fold's own quantiles.

    Returns `(n_features, bins - 1)` of upper edges. Quantiles rather than equal width because a
    log return is concentrated near zero with long tails, and equal-width bins would put 99% of
    the rows in one bucket and spend the rest of the resolution on outliers.
    """
    qs = np.linspace(0, 1, bins + 1)[1:-1]
    edges = np.quantile(X, qs, axis=0).T.astype(np.float32)
    # A constant or near-constant feature yields repeated edges, which would make several bins
    # unreachable. Made strictly increasing so `searchsorted` still partitions, at the cost of
    # those bins staying empty -- which is the truth about that feature.
    for j in range(edges.shape[0]):
        row = edges[j]
        for k in range(1, len(row)):
            if row[k] <= row[k - 1]:
                row[k] = np.nextafter(row[k - 1], np.float32(np.inf))
    return edges


def apply_bins(X: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Bin codes `(n, d)` as uint8, using the stored edges."""
    n, d = X.shape
    out = np.empty((n, d), dtype=np.uint8)
    for j in range(d):
        out[:, j] = np.searchsorted(edges[j], X[:, j].astype(np.float32), side="left")
    return out


def _hist(codes: np.ndarray, rows: np.ndarray, g: np.ndarray, h: np.ndarray,
          bins: int, offsets: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gradient, hessian and count histograms for every feature at once.

    `codes[rows] + offsets` flattens (feature, bin) into one index space, so three `bincount`
    calls replace `3 * n_features` of them.
    """
    sub = codes[rows].astype(np.int32) + offsets
    flat = sub.ravel()
    size = offsets.shape[1] * bins
    gh = np.bincount(flat, weights=np.repeat(g[rows], offsets.shape[1]), minlength=size)
    hh = np.bincount(flat, weights=np.repeat(h[rows], offsets.shape[1]), minlength=size)
    ch = np.bincount(flat, minlength=size)
    shape = (offsets.shape[1], bins)
    return gh.reshape(shape), hh.reshape(shape), ch.reshape(shape)


def _best_split(gh: np.ndarray, hh: np.ndarray, ch: np.ndarray, l2: float,
                min_child: float, min_rows: int) -> tuple[float, int, int]:
    """The (gain, feature, bin) of the best split, or gain <= 0 when none qualifies."""
    gl = np.cumsum(gh, axis=1)[:, :-1]
    hl = np.cumsum(hh, axis=1)[:, :-1]
    cl = np.cumsum(ch, axis=1)[:, :-1]
    gt = gh.sum(axis=1, keepdims=True) - gl
    ht = hh.sum(axis=1, keepdims=True) - hl
    ct = ch.sum(axis=1, keepdims=True) - cl
    parent = (gl + gt) ** 2 / (hl + ht + l2)
    gain = 0.5 * (gl ** 2 / (hl + l2) + gt ** 2 / (ht + l2) - parent)
    ok = (hl >= min_child) & (ht >= min_child) & (cl >= min_rows) & (ct >= min_rows)
    gain = np.where(ok, gain, -np.inf)
    j = int(np.argmax(gain))
    f, b = divmod(j, gain.shape[1])
    best = float(gain[f, b])
    return (best, f, b) if np.isfinite(best) else (0.0, -1, -1)


def _grow(codes: np.ndarray, rows: np.ndarray, g: np.ndarray, h: np.ndarray, depth: int,
          bins: int, offsets: np.ndarray, l2: float, min_child: float, min_rows: int,
          hist: tuple | None = None) -> dict:
    """One tree node, recursively. Leaf value is the Newton step on the rows that reach it."""
    gh, hh, ch = hist if hist is not None else _hist(codes, rows, g, h, bins, offsets)
    if depth == 0 or len(rows) < 2 * min_rows:
        G, H = float(gh.sum()), float(hh.sum())
        return {"leaf": -G / (H + l2), "n": int(len(rows))}
    gain, f, b = _best_split(gh, hh, ch, l2, min_child, min_rows)
    if gain <= 0.0:
        G, H = float(gh.sum()), float(hh.sum())
        return {"leaf": -G / (H + l2), "n": int(len(rows))}
    go_left = codes[rows, f] <= b
    left, right = rows[go_left], rows[~go_left]
    lh = _hist(codes, left, g, h, bins, offsets)
    # The sibling trick: the right child's histogram is the parent's minus the left child's, so a
    # tree of depth d costs d histogram passes over the data rather than 2^d.
    rh = (gh - lh[0], hh - lh[1], ch - lh[2])
    return {
        "f": int(f), "b": int(b), "gain": float(gain), "n": int(len(rows)),
        "l": _grow(codes, left, g, h, depth - 1, bins, offsets, l2, min_child, min_rows, lh),
        "r": _grow(codes, right, g, h, depth - 1, bins, offsets, l2, min_child, min_rows, rh),
    }


def _apply(tree: dict, codes: np.ndarray) -> np.ndarray:
    """Leaf value per row, iteratively over a stack of (node, row index) pairs."""
    out = np.zeros(len(codes), dtype=np.float64)
    stack = [(tree, np.arange(len(codes)))]
    while stack:
        node, rows = stack.pop()
        if len(rows) == 0:
            continue
        if "leaf" in node:
            out[rows] = node["leaf"]
            continue
        go_left = codes[rows, node["f"]] <= node["b"]
        stack.append((node["l"], rows[go_left]))
        stack.append((node["r"], rows[~go_left]))
    return out


def fit(X: np.ndarray, y: np.ndarray, *, bins: int = 64, rounds: int = 300, depth: int = 3,
        lr: float = 0.05, l2: float = 1.0, min_child: float = 50.0, min_rows: int = 200,
        X_val: np.ndarray | None = None, y_val: np.ndarray | None = None,
        early_stop: int = 40, verbose: int = 0) -> dict:
    """Fit a boosted tree. With a validation fold, stops at its best round.

    Early stopping is on validation **log loss**, not accuracy: accuracy on a near-balanced binary
    target moves in steps of one row and picks a round by noise, where the loss is continuous and
    says whether the probabilities are improving.
    """
    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y, dtype=np.float64)
    edges = quantile_bins(X, bins)
    codes = apply_bins(X, edges)
    offsets = (np.arange(X.shape[1], dtype=np.int32) * bins)[None, :]

    base = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))
    f0 = float(np.log(base / (1 - base)))
    score = np.full(len(y), f0)

    codes_val = apply_bins(np.asarray(X_val, dtype=np.float32), edges) if X_val is not None else None
    score_val = np.full(len(y_val), f0) if y_val is not None else None

    trees: list[dict] = []
    best_loss, best_round, since = np.inf, 0, 0
    all_rows = np.arange(len(y))
    for t in range(rounds):
        p = 1.0 / (1.0 + np.exp(-score))
        g = p - y
        h = np.maximum(p * (1 - p), 1e-6)
        tree = _grow(codes, all_rows, g, h, depth, bins, offsets, l2, min_child, min_rows)
        trees.append(tree)
        score += lr * _apply(tree, codes)
        if codes_val is not None:
            score_val += lr * _apply(tree, codes_val)
            pv = np.clip(1.0 / (1.0 + np.exp(-score_val)), 1e-9, 1 - 1e-9)
            loss = float(-np.mean(y_val * np.log(pv) + (1 - y_val) * np.log(1 - pv)))
            if verbose and (t + 1) % verbose == 0:
                acc = float(((pv >= 0.5).astype(int) == y_val).mean())
                print(f"    round {t + 1:4d}  val logloss {loss:.6f}  val acc {acc:.4f}", flush=True)
            if loss < best_loss - 1e-7:
                best_loss, best_round, since = loss, t + 1, 0
            else:
                since += 1
                if since >= early_stop:
                    break
    kept = best_round if codes_val is not None and best_round else len(trees)
    return {
        "kind": "gbm-logistic",
        "bias": f0,
        "lr": lr,
        "edges": edges.tolist(),
        "bins": bins,
        "trees": trees[:kept],
        "roundsFitted": len(trees),
        "roundsKept": kept,
        "valLogLoss": None if best_loss == np.inf else best_loss,
    }


def predict_score(model: dict, X: np.ndarray) -> np.ndarray:
    """The raw additive score (log odds) for each row."""
    edges = np.asarray(model["edges"], dtype=np.float32)
    codes = apply_bins(np.asarray(X, dtype=np.float32), edges)
    s = np.full(len(X), float(model["bias"]))
    lr = float(model["lr"])
    for tree in model["trees"]:
        s += lr * _apply(tree, codes)
    return s


def predict_proba(model: dict, X: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-predict_score(model, X)))
