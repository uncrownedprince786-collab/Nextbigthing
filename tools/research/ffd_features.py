"""Where price actually sits, in a form a tree can use.

The 41 price features are all returns, which is differencing at d = 1. That is stationary and it
is amnesiac: after it, a coin at $101 that has spent a month between $95 and $105 and a coin at
$101 that just fell from $400 look identical. Measured on Ethereum's own log price, the ordinary
return keeps a correlation of **0.0025** with the level it came from. Fractionally differenced at
d = 0.2 the series is still stationary by an Augmented Dickey-Fuller test -- t = -3.87 against a
critical value of -2.86 -- and keeps **0.9982**.

So this block is the memory the return threw away.

Scale, and why the raw transform cannot be served
--------------------------------------------------
Fractionally differenced log price keeps the level, which is the point and also the problem: on a
pooled model Bitcoin arrives near log(80,000) = 11.3 and a meme coin near log(0.000001) = -13.8,
and a tree would split on which coin it was looking at rather than on anything about the market.

So the series is z-scored against its own trailing window per coin. That keeps the *shape* of the
memory -- how far price sits from where it has been, in units of how much it usually moves -- and
discards the absolute level, which was never the useful part. A per-coin model could use the raw
transform; one block that works for both is better than two that disagree.

Point in time by construction. The FFD weights look backwards only, the z-score window is
trailing, and the first `window + lookback` rows have no value and are marked unusable rather
than filled.
"""

from __future__ import annotations

import numpy as np

from frac_diff import ffd_weights

#: The differencing order. Chosen by ADF on Ethereum's log price as the smallest that passes --
#: every increment above it gives up memory for stationarity already achieved.
D = 0.2

#: Trailing bars the z-score is taken over. 288 five-minute bars is a day: long enough that the
#: scale is stable, short enough that "far from where it has been" means recently.
Z_WINDOW = 288

FFD_FEATURES: list[str] = [
    "ffdZ",        # the fractionally differenced log price, z-scored against its own day
    "ffdZ12",      # its change over 12 bars -- how fast the memory is moving
    "ffdZ96",      # and over 96, a slower read of the same thing
    "ffdSlope",    # linear slope of ffdZ over the last 48 bars
]

VERSION = "crypto-ffd-f1"


def ffd_for(close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`(X, ok)` -- the FFD block per bar, and which rows have one.

    `ok` is False for the warm-up rows the transform and the z-score window need. They are
    dropped by the caller rather than imputed: a zero here would read as "exactly average",
    which is a claim, not an absence.
    """
    n = len(close)
    X = np.zeros((n, len(FFD_FEATURES)), dtype=np.float64)
    ok = np.zeros(n, dtype=bool)
    if n < Z_WINDOW + 2:
        return X, ok

    logp = np.log(np.maximum(np.asarray(close, dtype=np.float64), 1e-12))
    w = ffd_weights(D)
    width = len(w)
    if n < width + Z_WINDOW:
        return X, ok

    fd = np.full(n, np.nan)
    fd[width - 1:] = np.lib.stride_tricks.sliding_window_view(logp, width) @ w

    # Trailing mean and standard deviation of the transform, by prefix sums so the cost does not
    # grow with the window.
    valid = np.isfinite(fd)
    v = np.where(valid, fd, 0.0)
    c1 = np.concatenate([[0.0], np.cumsum(v)])
    c2 = np.concatenate([[0.0], np.cumsum(v * v)])
    cnt = np.concatenate([[0.0], np.cumsum(valid.astype(np.float64))])

    idx = np.arange(n)
    lo = np.maximum(0, idx - Z_WINDOW + 1)
    k = cnt[idx + 1] - cnt[lo]
    mean = np.where(k > 0, (c1[idx + 1] - c1[lo]) / np.maximum(k, 1), 0.0)
    var = np.where(k > 1, (c2[idx + 1] - c2[lo]) / np.maximum(k, 1) - mean * mean, 0.0)
    sd = np.sqrt(np.maximum(var, 0.0))

    z = np.where((sd > 1e-12) & valid, (fd - mean) / np.maximum(sd, 1e-12), 0.0)
    ready = valid & (k >= Z_WINDOW)

    X[:, 0] = z
    X[12:, 1] = z[12:] - z[:-12]
    X[96:, 2] = z[96:] - z[:-96]

    # Slope of z over the trailing 48 bars, as a plain least-squares fit against 0..47. The
    # design never changes, so the denominator is a constant and this is one dot product.
    span = 48
    if n > span:
        t = np.arange(span, dtype=np.float64)
        t -= t.mean()
        denom = float(t @ t)
        windows = np.lib.stride_tricks.sliding_window_view(z, span)
        X[span - 1:, 3] = (windows @ t) / denom

    ok[:] = ready
    ok[: max(width + Z_WINDOW, 96, span)] = False
    return X, ok
