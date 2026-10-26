"""How much of each label is its own, and not borrowed from its neighbours.

A fifteen-minute label on five-minute bars spans three bars, so consecutive rows share two of
their three. One price move decides three labels and the fit counts it three times. The row count
says 108,288 and the number of independent observations is nearer a third of that.

Left uncorrected this does not merely waste data, it **lies about confidence**. A boosted tree
fitted on heavily overlapping labels sees the same event repeatedly and reads agreement where
there is only repetition, so it overfits the busy stretches and the in-sample numbers flatter.
It matters most on exactly the target this repository has just adopted: triple-barrier labels
end when a barrier is touched, so their spans are *uneven* -- a volatile stretch produces short,
nearly-unique labels and a quiet one produces long, heavily-overlapping labels, and without a
correction the quiet stretches silently dominate the fit.

The fix is López de Prado's average uniqueness. For every bar, count how many labels are live
across it; a row's uniqueness is the mean of `1 / concurrency` over its own span. A label nobody
overlaps scores 1.0. One sharing every bar with two others scores about 0.33. Those become
sample weights.

What this is not
----------------
Not a fix for overlap in the *test* fold -- nothing is weighted there, because a holdout is
scored by what happened, not by how independent the rows were. And not a substitute for the
embargo between folds, which solves a different problem: uniqueness is about double-counting
inside one fold, the embargo is about information crossing between them. Both are needed and
neither implies the other.
"""

from __future__ import annotations

import numpy as np


def average_uniqueness(starts: np.ndarray, spans: np.ndarray, n_bars: int) -> np.ndarray:
    """Mean `1 / concurrency` over each label's own span.

    `starts` are bar indices into one coin's series, `spans` the number of bars each label
    actually occupies -- which for a triple-barrier label is the bar the barrier was touched on,
    not the horizon, because a label that ended early stops competing for the bars after it.
    """
    n = len(starts)
    if n == 0:
        return np.zeros(0, dtype=np.float64)

    # Concurrency per bar, by difference array: +1 where a label starts, -1 just past its end.
    # O(rows + bars) rather than the O(rows x span) of counting each label's bars directly, which
    # matters at 150,000 rows a coin.
    delta = np.zeros(n_bars + 2, dtype=np.float64)
    ends = np.minimum(starts + np.maximum(spans, 1), n_bars)
    np.add.at(delta, starts, 1.0)
    np.add.at(delta, ends, -1.0)
    concurrency = np.cumsum(delta)[:n_bars]
    # A bar no label covers has concurrency zero; it is never read, but guard the division.
    inv = np.where(concurrency > 0, 1.0 / np.maximum(concurrency, 1e-9), 0.0)

    # Mean of `inv` over each label's span, via a prefix sum for the same reason.
    prefix = np.concatenate([[0.0], np.cumsum(inv)])
    length = np.maximum(ends - starts, 1)
    return (prefix[ends] - prefix[starts]) / length


def weights_for(data: dict, usable: np.ndarray, spans: np.ndarray | None,
                bars_ahead: int) -> np.ndarray:
    """Sample weights over the whole concatenated matrix, one per row.

    Rows that are not usable get zero, which keeps the array aligned with `X` without them
    contributing. The weights are normalised to mean one over the usable rows, so the learning
    rate keeps the meaning it had before weighting -- a fit whose weights sum to a third of the
    row count would otherwise behave like a fit with a third of the step size.
    """
    out = np.zeros(len(data["ts"]), dtype=np.float64)
    offset = 0
    for _sym, meta in data["corpora"].items():
        _ts, _close, keep = meta["_series"]
        n = len(keep)
        if n == 0:
            continue
        here = usable[offset:offset + n]
        idx = np.flatnonzero(here)
        if len(idx):
            span = (spans[offset:offset + n][idx] if spans is not None
                    else np.full(len(idx), bars_ahead, dtype=np.int64))
            u = average_uniqueness(keep[idx], span.astype(np.int64),
                                   int(keep[-1]) + bars_ahead + 2)
            out[offset:offset + n][idx] = u
        offset += n
    live = out > 0
    if live.any():
        out[live] /= out[live].mean()
    return out
