"""What the rest of the market was doing at the instant a coin's bar closed.

Every feature in `crypto-intraday-f1` is computed from one coin's own bars. That is a real gap,
and it is the largest one left: most of an altcoin's five-minute move is Bitcoin's move, so the
pooled model is being asked to read idiosyncratic direction without being shown the factor the
move is idiosyncratic *to*. A +0.4% bar is a different event when Bitcoin is +0.5% than when
Bitcoin is flat, and nothing in f1 can tell those apart.

This adds the factor and the coin's relationship to it:

  * **the factor itself** -- Bitcoin's own returns, volatility and range position, so the model
    can condition on the market regime rather than only on the coin;
  * **the residual** -- the coin's return minus Bitcoin's over the same windows, which is the part
    of the move that is actually about this coin;
  * **the link** -- a rolling beta and correlation to Bitcoin, so the model knows how much of the
    factor should be expected to show up in this coin at all.

Point-in-time, by the same construction as f1
----------------------------------------------
Bitcoin's bar at timestamp `t` closes at the same instant as the coin's bar at `t`. Reading it is
therefore not look-ahead: both are observable at the decision instant. The alignment is by exact
timestamp and nothing is interpolated or carried forward -- a coin bar with no Bitcoin bar at the
same open is marked unusable and dropped, because a context feature forward-filled across a
Binance outage is a claim that the market did not move.

Bitcoin itself
--------------
For BTCUSDT the context series *is* its own series, so the residuals are exactly zero and the beta
is exactly one. That is left as it is rather than special-cased: it is the truth about those rows,
it is consistent between training and serving, and a tree that learns "beta is exactly 1" has
learned "this is the factor coin", which is a real thing to know about a row.
"""

from __future__ import annotations

import numpy as np

#: Appended after the 41 f1 features, in this order.
CONTEXT_FEATURES: list[str] = [
    # the factor's own state
    "mktR1", "mktR12", "mktR48", "mktR288",
    "mktVol48", "mktPos288",
    # this coin against the factor
    "relR1", "relR12", "relR48",
    "beta48", "corr48",
]

N_CONTEXT = len(CONTEXT_FEATURES)

#: Bumped with any change to the list above or the arithmetic below.
VERSION = "crypto-market-c1"

EPS = 1e-12

#: The rolling window the beta and correlation are fitted over, in bars.
LINK_WINDOW = 48


def _roll_sum(a: np.ndarray, n: int) -> np.ndarray:
    """Trailing sum of `n` values ending at each index; NaN before the window fills."""
    out = np.full(len(a), np.nan)
    if len(a) < n:
        return out
    c = np.concatenate([[0.0], np.cumsum(a)])
    out[n - 1:] = c[n:] - c[:-n]
    return out


def _roll_mean(a: np.ndarray, n: int) -> np.ndarray:
    return _roll_sum(a, n) / n


def _ret(logc: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(logc), np.nan)
    if len(logc) > k:
        out[k:] = logc[k:] - logc[:-k]
    return out


def context_for(coin_ts: np.ndarray, coin_close: np.ndarray,
                mkt_ts: np.ndarray, mkt_close: np.ndarray,
                mkt_high: np.ndarray, mkt_low: np.ndarray,
                warmup: int) -> tuple[np.ndarray, np.ndarray]:
    """`(C, usable)` -- the context block for every coin bar, and which rows have one.

    `C[i]` is readable at the close of the coin's bar `i`. `usable[i]` is False where the market
    series has no bar at that timestamp, or where either series is still inside its warm-up.

    Both series are assumed ascending by timestamp with one bar per interval; the caller has
    already checked that for the coin, and the market series comes from the same collector.
    """
    n = len(coin_ts)
    C = np.full((n, N_CONTEXT), np.nan, dtype=np.float32)
    usable = np.zeros(n, dtype=bool)
    if n == 0 or len(mkt_ts) == 0:
        return C, usable

    # Exact-timestamp alignment. `searchsorted` finds where each coin bar would sit in the market
    # series; a position whose timestamp does not match exactly is a bar the market series does
    # not have, and is left unusable rather than filled from a neighbour.
    pos = np.searchsorted(mkt_ts, coin_ts)
    inside = pos < len(mkt_ts)
    hit = np.zeros(n, dtype=bool)
    hit[inside] = mkt_ts[pos[inside]] == coin_ts[inside]
    if not hit.any():
        return C, usable

    m_log = np.log(np.maximum(mkt_close, EPS))
    c_log = np.log(np.maximum(coin_close, EPS))

    m_r1 = np.full(len(mkt_close), 0.0)
    m_r1[1:] = m_log[1:] - m_log[:-1]
    c_r1 = np.full(n, 0.0)
    c_r1[1:] = c_log[1:] - c_log[:-1]

    m_ret = {k: _ret(m_log, k) for k in (1, 12, 48, 288)}
    c_ret = {k: _ret(c_log, k) for k in (1, 12, 48)}

    # Realised volatility and range position of the factor, on the factor's own index.
    m_var = _roll_mean(m_r1 ** 2, 48) - _roll_mean(m_r1, 48) ** 2
    m_vol48 = np.sqrt(np.maximum(m_var, 0.0))

    m_hi = np.full(len(mkt_close), np.nan)
    m_lo = np.full(len(mkt_close), np.nan)
    if len(mkt_close) >= 288:
        # Rolling 288-bar extremes via a strided view: one pass, no Python loop over 400k bars.
        hw = np.lib.stride_tricks.sliding_window_view(mkt_high, 288)
        lw = np.lib.stride_tricks.sliding_window_view(mkt_low, 288)
        m_hi[287:] = hw.max(axis=1)
        m_lo[287:] = lw.min(axis=1)
    rng = m_hi - m_lo
    m_pos288 = np.where(rng > EPS, (mkt_close - m_lo) / np.where(rng > EPS, rng, 1.0), 0.5)

    # Beta and correlation of the coin's 1-bar returns against the factor's, over LINK_WINDOW
    # bars, computed on the coin's index with the factor's aligned returns beside it.
    aligned_m_r1 = np.zeros(n)
    aligned_m_r1[hit] = m_r1[pos[hit]]
    sx = _roll_mean(aligned_m_r1, LINK_WINDOW)
    sy = _roll_mean(c_r1, LINK_WINDOW)
    sxx = _roll_mean(aligned_m_r1 ** 2, LINK_WINDOW)
    syy = _roll_mean(c_r1 ** 2, LINK_WINDOW)
    sxy = _roll_mean(aligned_m_r1 * c_r1, LINK_WINDOW)
    cov = sxy - sx * sy
    var_x = np.maximum(sxx - sx * sx, 0.0)
    var_y = np.maximum(syy - sy * sy, 0.0)
    beta = np.where(var_x > EPS, cov / np.where(var_x > EPS, var_x, 1.0), 0.0)
    denom = np.sqrt(var_x * var_y)
    corr = np.where(denom > EPS, cov / np.where(denom > EPS, denom, 1.0), 0.0)
    # A rolling beta on 48 five-minute bars is a noisy statistic and its tails are not information.
    # Clipped so one 48-bar window of near-zero market variance cannot hand the tree a split on
    # a beta of 400.
    beta = np.clip(beta, -5.0, 5.0)
    corr = np.clip(corr, -1.0, 1.0)

    j = pos.copy()
    j[~hit] = 0
    block = np.column_stack([
        m_ret[1][j], m_ret[12][j], m_ret[48][j], m_ret[288][j],
        m_vol48[j], m_pos288[j],
        c_ret[1] - m_ret[1][j], c_ret[12] - m_ret[12][j], c_ret[48] - m_ret[48][j],
        beta, corr,
    ]).astype(np.float32)

    ok = hit & np.isfinite(block).all(axis=1)
    ok &= np.arange(n) >= warmup
    C[ok] = block[ok]
    usable = ok
    return C, usable
