"""The vectorised twin of `intraday_features.features_at`, and the check that they agree.

`features_at` is the definition: one row, readable, and the thing `lib/intradayFeatures.ts` is
tested against. Running it over four hundred thousand bars would take an hour, so this module
computes the same matrix with cumulative sums, convolutions and monotonic-deque extrema -- and
`verify_against_reference` re-runs the readable version on a random sample of rows and fails the
build if any component differs by more than a tolerance.

Three implementations of one feature set now exist (readable Python, fast Python, TypeScript) and
exactly two tests tie them together: this sample check, and `tests/intradayParity.test.ts`. Without
them, the model would eventually be trained on one feature set and served another, which is the
failure mode that is invisible in every metric until the forecasts stop working.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from intraday_features import FEATURES, N_FEATURES, WARMUP, features_at

EPS = 1e-12


def _roll_sum(a: np.ndarray, n: int) -> np.ndarray:
    """Sum of the `n` values ending at each index (NaN before the window is full)."""
    cs = np.concatenate([[0.0], np.cumsum(a, dtype=np.float64)])
    out = np.full(len(a), np.nan)
    out[n - 1:] = cs[n:] - cs[:-n]
    return out


def _roll_mean(a: np.ndarray, n: int) -> np.ndarray:
    return _roll_sum(a, n) / n


def _roll_std(a: np.ndarray, n: int) -> np.ndarray:
    """Sample standard deviation (n - 1 denominator) of the `n` values ending at each index."""
    s1 = _roll_sum(a, n)
    s2 = _roll_sum(a * a, n)
    var = (s2 - s1 * s1 / n) / (n - 1)
    return np.sqrt(np.maximum(var, 0.0))


def _roll_max(a: np.ndarray, n: int) -> np.ndarray:
    """Maximum of the `n` values ending at each index, via a monotonic deque: O(len(a))."""
    out = np.full(len(a), np.nan)
    dq: deque[int] = deque()
    for i, v in enumerate(a):
        while dq and a[dq[-1]] <= v:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        if i >= n - 1:
            out[i] = a[dq[0]]
    return out


def _roll_min(a: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(a), np.nan)
    dq: deque[int] = deque()
    for i, v in enumerate(a):
        while dq and a[dq[-1]] >= v:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        if i >= n - 1:
            out[i] = a[dq[0]]
    return out


def _ema_window(c: np.ndarray, span: int, length: int) -> np.ndarray:
    """`_ema(closes[-length:], span)` for every index, as one convolution.

    The recurrence seeded on the window's first close expands to a fixed weight per position, so
    the whole series is a single dot product with a kernel of that length. `length` is the number
    of closes in the window, which is `span` for the 12 and 48 cases and `WARMUP + 1` for the 288
    case -- `features_at` passes the whole window there, and that difference is load-bearing.
    """
    k = 2.0 / (span + 1.0)
    w = np.empty(length, dtype=np.float64)
    w[0] = (1 - k) ** (length - 1)
    for j in range(1, length):
        w[j] = k * (1 - k) ** (length - 1 - j)
    out = np.full(len(c), np.nan)
    # A series shorter than the window has no value at any index, which is a real case: a coin
    # listed six weeks ago has fewer than 289 four-hour bars. `np.convolve(..., "valid")` on a
    # kernel longer than the signal returns the *reversed* shorter convolution rather than
    # nothing, so this is guarded here rather than left to broadcast into a wrong answer.
    if len(c) < length:
        return out
    out[length - 1:] = np.convolve(c, w[::-1], mode="valid")
    return out


def build(bars: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """`(X, ts, valid, step_ms)` for every bar in the series.

    `X[i]` is the feature vector readable at the close of `bars[i]`; `valid[i]` is False where the
    window is short or spans a gap. Invalid rows keep whatever the arithmetic produced and are
    never used -- the mask is the gate, so a caller that forgets it gets NaNs rather than a
    plausible-looking row computed across an outage.
    """
    n = len(bars)
    if n < WARMUP + 2:
        # Too short for any row, and for `step` itself. Answered as "nothing usable here" rather
        # than by a cascade of shape errors further down: a newly listed coin is a normal input.
        return (np.zeros((n, N_FEATURES), dtype=np.float32),
                np.asarray([b["ts"] for b in bars], dtype=np.int64),
                np.zeros(n, dtype=bool),
                300_000)
    ts = np.asarray([b["ts"] for b in bars], dtype=np.int64)
    C = np.asarray([b["c"] for b in bars], dtype=np.float64)
    H = np.asarray([b["h"] for b in bars], dtype=np.float64)
    L = np.asarray([b["l"] for b in bars], dtype=np.float64)
    O = np.asarray([b["o"] for b in bars], dtype=np.float64)
    V = np.asarray([b["v"] for b in bars], dtype=np.float64)
    TB = np.asarray([b.get("tb", b["v"] / 2.0) for b in bars], dtype=np.float64)
    NT = np.asarray([max(b.get("n", 0) or 0, 0) for b in bars], dtype=np.float64)

    step = int(np.median(np.diff(ts))) if n > 1 else 300_000

    lc = np.log(np.maximum(C, EPS))
    ret_g = np.full(n, 0.0)
    ret_g[1:] = lc[1:] - lc[:-1]

    def ret(k: int) -> np.ndarray:
        out = np.full(n, np.nan)
        out[k:] = lc[k:] - lc[:-k]
        return out

    vol12, vol48, vol288 = _roll_std(ret_g, 12), _roll_std(ret_g, 48), _roll_std(ret_g, 288)

    def pos(k: int) -> np.ndarray:
        hi, lo = _roll_max(H, k), _roll_min(L, k)
        rng = hi - lo
        return np.where(rng > EPS, (C - lo) / np.where(rng > EPS, rng, 1.0), 0.5)

    prevC = np.concatenate([[C[0]], C[:-1]])
    TR = np.maximum.reduce([H - L, np.abs(H - prevC), np.abs(L - prevC)])
    TR[0] = H[0] - L[0]
    atr14 = _roll_mean(TR, 14)
    atr288 = _roll_mean(TR, 288)

    dif = np.concatenate([[0.0], C[1:] - C[:-1]])
    gain14 = _roll_sum(np.maximum(dif, 0.0), 14)
    loss14 = _roll_sum(np.maximum(-dif, 0.0), 14)
    denom = gain14 + loss14
    rsi14 = np.where(denom > EPS, gain14 / np.where(denom > EPS, denom, 1.0), 0.5)

    def vol_ratio(k: int) -> np.ndarray:
        m = _roll_mean(V, k)
        return np.log((V + EPS) / (m + EPS))

    def tbi(k: int) -> np.ndarray:
        v = _roll_sum(V, k) if k > 1 else V.copy()
        t = _roll_sum(TB, k) if k > 1 else TB.copy()
        return np.where(v > EPS, 2.0 * t / np.where(v > EPS, v, 1.0) - 1.0, 0.0)

    sizes = np.where(NT > 0, V / np.where(NT > 0, NT, 1.0), 0.0)
    tsz48 = np.log((sizes + EPS) / (_roll_mean(sizes, 48) + EPS))

    rng = H - L
    safe = np.where(rng > EPS, rng, 1.0)
    body = np.where(rng > EPS, (C - O) / safe, 0.0)
    up_wick = np.where(rng > EPS, (H - np.maximum(O, C)) / safe, 0.0)
    dn_wick = np.where(rng > EPS, (np.minimum(O, C) - L) / safe, 0.0)
    body12 = _roll_mean(body, 12)

    sign = np.sign(ret_g)
    persist6, persist24 = _roll_mean(sign, 6), _roll_mean(sign, 24)

    m48 = _roll_mean(ret_g, 48)
    sd48 = _roll_std(ret_g, 48)
    cen = ret_g - 0.0
    # Third central moment with the *sample* sd in the denominator and an n divisor, matching
    # `features_at.skew` term for term rather than using any standard definition.
    s1 = _roll_sum(cen, 48)
    s2 = _roll_sum(cen * cen, 48)
    s3 = _roll_sum(cen * cen * cen, 48)
    m3 = (s3 - 3 * m48 * s2 + 3 * m48 * m48 * s1 - 48 * m48 ** 3) / 48
    skew48 = np.where(sd48 > EPS, m3 / np.where(sd48 > EPS, sd48, 1.0) ** 3, 0.0)

    hi288, lo288 = _roll_max(H, 288), _roll_min(L, 288)
    d24h_high = np.log(np.maximum(hi288, EPS) / np.maximum(C, EPS))
    d24h_low = np.log(np.maximum(C, EPS) / np.maximum(lo288, EPS))

    close_ms = ts + step
    minute = (close_ms // 60000) % 1440
    dow = ((close_ms // 86_400_000) + 4) % 7
    tod = 2 * math.pi * minute / 1440.0
    dw = 2 * math.pi * dow / 7.0

    ema12 = _ema_window(C, 12, 12)
    ema48 = _ema_window(C, 48, 48)
    ema288 = _ema_window(C, 288, WARMUP + 1)

    cols = {
        "r1": ret(1), "r3": ret(3), "r6": ret(6), "r12": ret(12), "r24": ret(24),
        "r48": ret(48), "r96": ret(96), "r288": ret(288),
        "vol12": vol12, "vol48": vol48, "vol288": vol288,
        "rz12": ret(12) / (vol12 * math.sqrt(12) + EPS),
        "rz48": ret(48) / (vol48 * math.sqrt(48) + EPS),
        "pos12": pos(12), "pos48": pos(48), "pos288": pos(288),
        "ema12d": (C - ema12) / C, "ema48d": (C - ema48) / C, "ema288d": (C - ema288) / C,
        "atr14": atr14 / C, "atrRatio": atr14 / (atr288 + EPS),
        "rsi14": rsi14,
        "vol_r48": vol_ratio(48), "vol_r288": vol_ratio(288),
        "tbi1": tbi(1), "tbi12": tbi(12), "tbi48": tbi(48),
        "tsz48": tsz48,
        "body": body, "upWick": up_wick, "dnWick": dn_wick, "body12": body12,
        "persist6": persist6, "persist24": persist24,
        "skew48": skew48,
        "d24hHigh": d24h_high, "d24hLow": d24h_low,
        "todSin": np.sin(tod), "todCos": np.cos(tod),
        "dowSin": np.sin(dw), "dowCos": np.cos(dw),
    }
    missing = set(FEATURES) - set(cols)
    extra = set(cols) - set(FEATURES)
    if missing or extra:
        raise AssertionError(f"matrix/feature mismatch: missing {missing}, extra {extra}")

    X = np.empty((n, N_FEATURES), dtype=np.float32)
    for j, name in enumerate(FEATURES):
        X[:, j] = np.nan_to_num(cols[name], nan=0.0, posinf=0.0, neginf=0.0)

    valid = np.zeros(n, dtype=bool)
    idx = np.arange(n)
    long_enough = idx >= WARMUP
    valid[long_enough] = (ts[long_enough] - ts[idx[long_enough] - WARMUP]) == WARMUP * step
    return X, ts, valid, step


def verify_against_reference(bars: list[dict], X: np.ndarray, valid: np.ndarray,
                             sample: int = 150, tol: float = 2e-6,
                             seed: int = 7) -> dict:
    """Re-run the readable implementation on random valid rows and compare, component by component.

    The tolerance is float32-sized: `X` is stored as float32 and `features_at` returns float64, so
    an exact comparison would fail on rounding alone. Anything above it is a real divergence.
    """
    rng = np.random.default_rng(seed)
    rows = np.flatnonzero(valid)
    if len(rows) == 0:
        return {"checked": 0, "worst": None, "ok": True}
    pick = rng.choice(rows, size=min(sample, len(rows)), replace=False)
    worst = 0.0
    worst_at = None
    for i in pick:
        ref = features_at(bars, int(i))
        if ref is None:
            raise AssertionError(f"reference refused row {i} the matrix marked valid")
        for j, (a, b) in enumerate(zip(ref, X[i])):
            scale = max(1.0, abs(a))
            d = abs(a - float(b)) / scale
            if d > worst:
                worst, worst_at = d, (int(i), FEATURES[j], a, float(b))
    if worst > tol:
        raise AssertionError(
            f"vectorised matrix disagrees with intraday_features.features_at: "
            f"{worst_at[1]} at row {worst_at[0]} is {worst_at[2]!r} vs {worst_at[3]!r} "
            f"(relative {worst:.3g} > {tol})")
    return {"checked": int(len(pick)), "worstRelativeDiff": float(worst), "tolerance": tol,
            "ok": True}
