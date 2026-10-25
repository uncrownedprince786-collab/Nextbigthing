"""What the leveraged crowd is paying to hold its position, at the instant a bar closed.

Every feature the brain reads today is derived from candles -- the coin's own in
`crypto-intraday-f1`, Bitcoin's in `crypto-market-c1`. Candles are the market's **output**: the
record of what price did. The information that moves the next fifteen minutes is its **input**:
who is positioned which way, how leveraged they are, and what it costs them to stay there. A
model reading only candles is reading the scoreboard and inferring the game.

Funding is the cheapest honest window on that, and the only one with enough history to train on.
On a perpetual future, longs pay shorts (or the reverse) every eight hours to keep the contract
pinned to spot. Strongly positive funding means longs are crowded and paying rent to stay long --
both a sentiment reading and, more usefully, squeeze fuel, because crowded leveraged positions
are what turn an ordinary move into a cascade. None of that is recoverable from a price series.

The five-minute positioning series -- open interest, long/short ratio, taker ratio -- are richer
and Binance keeps only thirty days of them, so they cannot train a model on three years of
candles. `jobs/crypto_positioning.py` accumulates them forward for a later generation. Funding
reaches back to 2020 and is available for 132 of the 140 pool coins, so it can be used now.

Point-in-time, which for an eight-hourly series means the last *settled* value
-------------------------------------------------------------------------------
A funding rate is published when it settles. The value in force at a bar closing at `t` is the
most recent settlement **at or before** `t`, and never the next one -- that is the whole
look-ahead risk in this block and it is handled by a right-side `searchsorted` and nothing else.
A bar before the coin's first settlement has no funding and is marked unusable rather than
imputed to zero: zero is a real funding rate and means something quite different from "unknown".

Eight hours is slow beside a five-minute bar, so these are regime variables rather than triggers.
They say what the crowd has been doing, not what the next bar will do.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FUNDING = ROOT / ".cache" / "foundation" / "funding"

#: Named in the order they are produced. Appended to the feature vector after the context block.
FUNDING_FEATURES: list[str] = [
    "fundRate",        # the rate in force, as a fraction per 8h
    "fundRate3",       # mean of the last 3 settlements (one day)
    "fundRate9",       # mean of the last 9 (three days)
    "fundZ",           # the current rate against this coin's own trailing mean and spread
    "fundTrend",       # current minus the 3-settlement mean: crowding building or unwinding
    "fundFlips",       # sign changes in the last 9, a measure of positioning indecision
    "fundAgeBars",     # how long ago the rate settled, in bars -- freshness, not a prediction
]

VERSION = "crypto-funding-f1"

#: Settlements used for the trailing statistics. Nine is three days, long enough to describe a
#: positioning regime and short enough that it is still about now.
TRAIL = 9


def load_funding(symbol: str) -> tuple[np.ndarray, np.ndarray] | None:
    """`(timestamps, rates)` sorted ascending, or None when this coin has no perpetual."""
    p = FUNDING / f"{symbol}-funding.jsonl.gz"
    if not p.exists():
        return None
    ts, rate = [], []
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            ts.append(int(r["ts"]))
            rate.append(float(r["rate"]))
    if len(ts) < TRAIL + 1:
        return None
    a = np.asarray(ts, dtype=np.int64)
    b = np.asarray(rate, dtype=np.float64)
    order = np.argsort(a, kind="stable")
    return a[order], b[order]


def funding_for(coin_ts: np.ndarray, symbol: str,
                step_ms: int) -> tuple[np.ndarray, np.ndarray]:
    """`(X, ok)` -- the funding block for each coin bar, and which rows are usable.

    `ok` is False for bars before this coin's first settlement. Those rows are dropped by the
    caller rather than filled: a zero funding rate is a real and common state, so imputing zero
    for "we have no reading" would teach the model that the two are the same thing.
    """
    n = len(coin_ts)
    X = np.zeros((n, len(FUNDING_FEATURES)), dtype=np.float64)
    ok = np.zeros(n, dtype=bool)

    loaded = load_funding(symbol)
    if loaded is None:
        return X, ok
    f_ts, f_rate = loaded

    # The last settlement at or before each bar. `side="right"` then minus one: a settlement
    # exactly at the bar's close counts, a settlement after it never does.
    idx = np.searchsorted(f_ts, coin_ts, side="right") - 1
    have = idx >= 0
    if not have.any():
        return X, ok

    # Trailing statistics per settlement, computed once over the settlement series and then read
    # off by index -- far cheaper than a window per bar, and identical arithmetic.
    k = len(f_rate)
    cum = np.concatenate([[0.0], np.cumsum(f_rate)])

    def trail_mean(j: np.ndarray, w: int) -> np.ndarray:
        lo = np.maximum(0, j - w + 1)
        return (cum[j + 1] - cum[lo]) / (j - lo + 1)

    m3 = trail_mean(np.arange(k), 3)
    m9 = trail_mean(np.arange(k), TRAIL)
    # Spread over the same trailing window, for the z-score.
    sq = np.concatenate([[0.0], np.cumsum(f_rate * f_rate)])
    lo9 = np.maximum(0, np.arange(k) - TRAIL + 1)
    cnt9 = np.arange(k) - lo9 + 1
    var9 = np.maximum(0.0, (sq[np.arange(k) + 1] - sq[lo9]) / cnt9 - m9 * m9)
    sd9 = np.sqrt(var9)

    # Sign flips inside the trailing window: positioning that keeps changing its mind.
    sign = np.sign(f_rate)
    flip = np.concatenate([[0.0], (sign[1:] != sign[:-1]).astype(np.float64)])
    cflip = np.concatenate([[0.0], np.cumsum(flip)])
    flips9 = cflip[np.arange(k) + 1] - cflip[lo9]

    j = idx[have]
    sd = sd9[j]
    X[have, 0] = f_rate[j]
    X[have, 1] = m3[j]
    X[have, 2] = m9[j]
    # Spread of exactly zero means a perfectly flat funding regime, where the z-score is not
    # defined and zero is the honest value: the rate is exactly its own mean.
    X[have, 3] = np.where(sd > 1e-12, (f_rate[j] - m9[j]) / np.maximum(sd, 1e-12), 0.0)
    X[have, 4] = f_rate[j] - m3[j]
    X[have, 5] = flips9[j]
    X[have, 6] = (coin_ts[have] - f_ts[j]) / step_ms
    ok[have] = True
    return X, ok
