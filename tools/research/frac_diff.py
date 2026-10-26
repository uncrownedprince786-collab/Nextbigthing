"""Make the price series stationary without making it forget.

Every price feature here is a return: `price[t] / price[t-k] - 1`. That is a **full** difference,
d = 1, and it does exactly two things -- it makes the series stationary, which a tree needs, and
it destroys the level information, which the tree might have used. After differencing, a coin at
$101 that spent a month between $95 and $105 and a coin at $101 that just fell from $400 are
indistinguishable. Every model in this repository has been blind to that.

Fractional differentiation is the middle ground. Differencing at a fractional order `d` applies
the binomial expansion of `(1 - B)^d`:

    (1 - B)^d = 1 - dB + d(d-1)/2! B^2 - d(d-1)(d-2)/3! B^3 + ...

At d = 1 the weights collapse to `[1, -1]` and you have an ordinary return. At d = 0 they are
`[1]` and you have the raw price. Between the two the weights decay slowly, so the transformed
series keeps a long memory of past levels **and** still passes a stationarity test. The smallest
d that passes is the one that gives up the least memory.

Fixed width, not expanding
---------------------------
The weights are truncated once they fall below a threshold, so every row is computed from the
same number of past bars. An expanding window would give early rows a different transform from
late ones, which is a quiet form of the same drift the embargo exists to prevent -- the model
would learn a feature whose definition changes with position in the series.

Point in time by construction: a row at `t` reads bars at `t`, `t-1`, `t-2`... and nothing after.

The ADF test here
-----------------
`stationary_d` walks d upward and returns the first that passes an Augmented Dickey-Fuller test.
The test is implemented here rather than pulled from statsmodels, which this repository does not
depend on: an OLS of the differenced series on its lagged level and a few lagged differences,
with the t-statistic on the level coefficient compared against MacKinnon's critical values. It is
the standard specification, and the critical values are the published ones for the no-trend case.
"""

from __future__ import annotations

import numpy as np

#: Weights smaller than this are dropped, fixing the window width.
WEIGHT_FLOOR = 1e-4

#: MacKinnon critical values for the ADF t-statistic, constant without trend, large sample.
ADF_CRITICAL = {0.01: -3.43, 0.05: -2.86, 0.10: -2.57}


def ffd_weights(d: float, floor: float = WEIGHT_FLOOR) -> np.ndarray:
    """Binomial weights for `(1 - B)^d`, truncated where they stop mattering.

    Computed by the recurrence `w[k] = -w[k-1] * (d - k + 1) / k` rather than from factorials,
    which overflow long before the weights become negligible.
    """
    w = [1.0]
    k = 1
    while True:
        nxt = -w[-1] * (d - k + 1) / k
        if abs(nxt) < floor or k > 10_000:
            break
        w.append(nxt)
        k += 1
    return np.asarray(w[::-1], dtype=np.float64)


def frac_diff(series: np.ndarray, d: float, floor: float = WEIGHT_FLOOR) -> np.ndarray:
    """Fractionally differenced series, NaN for the first `len(weights) - 1` rows.

    Those rows genuinely have no value -- the transform needs that much history -- and NaN says so
    rather than a zero that a tree would split on.
    """
    x = np.asarray(series, dtype=np.float64)
    w = ffd_weights(d, floor)
    width = len(w)
    out = np.full(len(x), np.nan)
    if len(x) < width:
        return out
    # One dot product per row via a strided view: the same arithmetic as a loop, without it.
    windows = np.lib.stride_tricks.sliding_window_view(x, width)
    out[width - 1:] = windows @ w
    return out


def adf_tstat(x: np.ndarray, lags: int = 4) -> float:
    """Augmented Dickey-Fuller t-statistic on the lagged level, constant and no trend.

    Regresses `diff(x)[t]` on a constant, `x[t-1]`, and `lags` lagged differences, and returns
    the t-statistic of the `x[t-1]` coefficient. More negative is more stationary.
    """
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if len(x) < lags + 20:
        return np.nan
    dx = np.diff(x)
    n = len(dx) - lags
    if n <= lags + 2:
        return np.nan
    y = dx[lags:]
    cols = [np.ones(n), x[lags:-1]]
    for i in range(1, lags + 1):
        cols.append(dx[lags - i:-i])
    Z = np.column_stack(cols)
    # Least squares with the normal equations; the design is tiny and well conditioned here.
    beta, *_ = np.linalg.lstsq(Z, y, rcond=None)
    resid = y - Z @ beta
    dof = n - Z.shape[1]
    if dof <= 0:
        return np.nan
    s2 = float(resid @ resid) / dof
    try:
        xtx_inv = np.linalg.inv(Z.T @ Z)
    except np.linalg.LinAlgError:
        return np.nan
    se = float(np.sqrt(s2 * xtx_inv[1, 1]))
    return float(beta[1] / se) if se > 0 else np.nan


def stationary_d(series: np.ndarray, candidates: tuple[float, ...] = (
        0.1, 0.2, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
        alpha: float = 0.05) -> tuple[float | None, list[dict]]:
    """The smallest `d` whose transform passes ADF, and the whole curve.

    Smallest rather than safest: every increment of d gives up memory, so the point is to buy
    stationarity as cheaply as possible. The curve is returned so the choice can be read rather
    than taken on trust.
    """
    crit = ADF_CRITICAL.get(alpha, -2.86)
    curve = []
    chosen = None
    for d in candidates:
        fd = frac_diff(series, d)
        t = adf_tstat(fd)
        ok = bool(np.isfinite(t) and t < crit)
        # Correlation with the original series: what the transform kept.
        keep = fd[np.isfinite(fd)]
        orig = np.asarray(series, dtype=np.float64)[-len(keep):] if len(keep) else np.zeros(0)
        corr = (float(np.corrcoef(keep, orig)[0, 1])
                if len(keep) > 2 and np.std(keep) > 0 and np.std(orig) > 0 else float("nan"))
        curve.append({"d": d, "adf": round(float(t), 4) if np.isfinite(t) else None,
                      "passes": ok, "correlationWithLevel": round(corr, 4)
                      if np.isfinite(corr) else None,
                      "window": int(len(ffd_weights(d)))})
        if ok and chosen is None:
            chosen = d
    return chosen, curve
