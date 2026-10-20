"""The feature vector a short-horizon crypto model reads, defined once.

This module is the **only** definition of those features. `train_crypto_short.py` fits on what it
produces and `lib/intradayFeatures.ts` recomputes it in the serving path; `tests/intradayParity.test.ts`
feeds both the same bars and fails if any component differs by more than 1e-9. Two implementations
of one feature set is how a model comes to be served inputs it was never trained on, and the parity
fixture is what makes that a test failure rather than a silent accuracy loss.

Point-in-time by construction
-----------------------------
`features_at(bars, i)` reads `bars[:i + 1]` and nothing else. There is no centred window, no
forward fill from a later bar and no normalisation computed over the whole series -- every
standardisation constant is fitted on the training fold alone and stored in the artifact. The
label is built separately, in the trainer, so a feature function cannot accidentally see it.

Scale-free on purpose
---------------------
Every component is a ratio, a z-score, a bounded fraction or an angle. A model fitted on $20,000
Bitcoin must read $82,000 Bitcoin as the same instrument, and a feature denominated in dollars
would make four years of history a four-year trend in the input rather than in the market.

Why these and not more
----------------------
Each block answers one question that is answerable from a kline and is not already answered by
another block: where price has been (returns), how violently (volatility and range), where it sits
in its own recent range (position), who was crossing the spread (taker imbalance -- the one piece
of order flow a public kline carries), how busy it was (volume and trade size), what the bar
itself looked like (body and wicks), and when in the week it is (crypto's weekly seasonality is
real and a 24/7 market has no session dummies to carry it).
"""

from __future__ import annotations

import math

#: The longest lookback any feature uses. A row is only emitted once this many bars precede it, so
#: no feature is ever computed from a short window and quietly compared with one computed from a
#: full one.
WARMUP = 288

#: Bumped whenever the list below changes in any way. Stored on every artifact and every recorded
#: forecast, so a row can always be traced to the feature set that produced it.
VERSION = "crypto-intraday-f1"

EPS = 1e-12

#: The feature names, in the exact order `features_at` returns them. The serving path reads this
#: order out of the model artifact rather than assuming it.
FEATURES: list[str] = [
    # returns over widening windows, in log space so they add
    "r1", "r3", "r6", "r12", "r24", "r48", "r96", "r288",
    # realised volatility of 1-bar returns
    "vol12", "vol48", "vol288",
    # return scaled by its own recent volatility: the move that matters is the surprising one
    "rz12", "rz48",
    # where the close sits inside its own recent range, 0 at the low and 1 at the high
    "pos12", "pos48", "pos288",
    # distance from exponential averages, as a fraction of price
    "ema12d", "ema48d", "ema288d",
    # average true range, and whether the range is expanding
    "atr14", "atrRatio",
    # relative strength index on this interval
    "rsi14",
    # volume against its own average, logged because volume is lognormal
    "vol_r48", "vol_r288",
    # taker buy imbalance: 2 * (taker buy volume / volume) - 1, so 0 is balanced
    "tbi1", "tbi12", "tbi48",
    # average trade size against its own average
    "tsz48",
    # the bar's own shape
    "body", "upWick", "dnWick", "body12",
    # how persistent the recent direction has been
    "persist6", "persist24",
    # realised skew of the last 48 one-bar returns
    "skew48",
    # distance from the 24h extremes
    "d24hHigh", "d24hLow",
    # where in the week it is: crypto has no session, so the clock is a feature not a dummy
    "todSin", "todCos", "dowSin", "dowCos",
]

N_FEATURES = len(FEATURES)


def _log(a: float, b: float) -> float:
    """log(a / b), bounded. Both are positive closes, so the guard is for corrupt input only."""
    if a <= 0 or b <= 0:
        return 0.0
    return math.log(a / b)


def _std(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _ema(closes: list[float], span: int) -> float:
    """EMA over the window, seeded on the window's first close.

    Seeded rather than carried forward across the whole series on purpose: a value that depends on
    where the series started is not reproducible from a serving window of the last few hundred
    bars, and the serving path has exactly that window. Over `span` bars the seed's weight is
    (1 - 2/(span+1))^span, under 14% at any span used here, and the trainer and the server both
    carry it identically.
    """
    k = 2.0 / (span + 1.0)
    e = closes[0]
    for c in closes[1:]:
        e = c * k + e * (1 - k)
    return e


def _rsi(closes: list[float], period: int = 14) -> float:
    """Wilder's RSI over the last `period + 1` closes, as a 0..1 fraction."""
    gains = 0.0
    losses = 0.0
    for a, b in zip(closes[-period - 1:-1], closes[-period:]):
        d = b - a
        if d >= 0:
            gains += d
        else:
            losses -= d
    if gains + losses <= EPS:
        return 0.5
    return gains / (gains + losses)


def features_at(bars: list[dict], i: int) -> list[float] | None:
    """The feature vector read at the close of `bars[i]`, or None when the window is short.

    `bars` must be ascending by `ts`, one per interval, with no gaps inside the window -- the
    caller checks that, because a gap is a data-quality fact worth reporting rather than something
    a feature function should paper over.
    """
    if i < WARMUP or i >= len(bars):
        return None
    w = bars[i - WARMUP: i + 1]          # WARMUP + 1 bars, ending at the decision bar
    closes = [b["c"] for b in w]
    highs = [b["h"] for b in w]
    lows = [b["l"] for b in w]
    opens = [b["o"] for b in w]
    vols = [b["v"] for b in w]
    tbs = [b.get("tb", b["v"] / 2.0) for b in w]
    trades = [max(b.get("n", 0) or 0, 0) for b in w]
    c = closes[-1]

    rets = [_log(closes[j], closes[j - 1]) for j in range(1, len(closes))]

    def ret(n: int) -> float:
        return _log(c, closes[-1 - n])

    vol12, vol48, vol288 = _std(rets[-12:]), _std(rets[-48:]), _std(rets)

    def pos(n: int) -> float:
        hi, lo = max(highs[-n:]), min(lows[-n:])
        return (c - lo) / (hi - lo) if hi - lo > EPS else 0.5

    # True range, Wilder's definition, so a gap between bars counts as range.
    trs = []
    for j in range(len(w) - 14, len(w)):
        tr = max(highs[j] - lows[j], abs(highs[j] - closes[j - 1]), abs(lows[j] - closes[j - 1]))
        trs.append(tr)
    atr14 = sum(trs) / len(trs)
    trs288 = []
    for j in range(1, len(w)):
        trs288.append(max(highs[j] - lows[j], abs(highs[j] - closes[j - 1]),
                          abs(lows[j] - closes[j - 1])))
    atr288 = sum(trs288) / len(trs288)

    def vol_ratio(n: int) -> float:
        m = sum(vols[-n:]) / n
        return math.log((vols[-1] + EPS) / (m + EPS))

    def tbi(n: int) -> float:
        v = sum(vols[-n:])
        t = sum(tbs[-n:])
        return (2.0 * t / v - 1.0) if v > EPS else 0.0

    sizes = [vols[j] / trades[j] if trades[j] > 0 else 0.0 for j in range(len(w))]
    msize = sum(sizes[-48:]) / 48
    tsz48 = math.log((sizes[-1] + EPS) / (msize + EPS))

    def shape(j: int) -> tuple[float, float, float]:
        rng = highs[j] - lows[j]
        if rng <= EPS:
            return 0.0, 0.0, 0.0
        body = (closes[j] - opens[j]) / rng
        up = (highs[j] - max(opens[j], closes[j])) / rng
        dn = (min(opens[j], closes[j]) - lows[j]) / rng
        return body, up, dn

    body, up_wick, dn_wick = shape(len(w) - 1)
    body12 = sum(shape(j)[0] for j in range(len(w) - 12, len(w))) / 12

    def persist(n: int) -> float:
        s = [1.0 if r > 0 else -1.0 if r < 0 else 0.0 for r in rets[-n:]]
        return sum(s) / n

    def skew(n: int) -> float:
        xs = rets[-n:]
        m = sum(xs) / n
        sd = _std(xs)
        if sd <= EPS:
            return 0.0
        return sum(((x - m) / sd) ** 3 for x in xs) / n

    hi24, lo24 = max(highs[-288:]), min(lows[-288:])

    ts = w[-1]["ts"]
    # Bar *close* time is the decision instant: the open time plus one interval. The interval is
    # read off the series rather than assumed, so a 15m corpus is not labelled with 5m clock angles.
    step = w[-1]["ts"] - w[-2]["ts"]
    close_ms = ts + step
    minute_of_day = (close_ms // 60000) % 1440
    dow = ((close_ms // 86400000) + 4) % 7      # 1970-01-01 was a Thursday
    tod = 2 * math.pi * minute_of_day / 1440.0
    dw = 2 * math.pi * dow / 7.0

    return [
        ret(1), ret(3), ret(6), ret(12), ret(24), ret(48), ret(96), ret(288),
        vol12, vol48, vol288,
        ret(12) / (vol12 * math.sqrt(12) + EPS),
        ret(48) / (vol48 * math.sqrt(48) + EPS),
        pos(12), pos(48), pos(288),
        (c - _ema(closes[-12:], 12)) / c,
        (c - _ema(closes[-48:], 48)) / c,
        (c - _ema(closes, 288)) / c,
        atr14 / c,
        atr14 / (atr288 + EPS),
        _rsi(closes, 14),
        vol_ratio(48), vol_ratio(288),
        tbi(1), tbi(12), tbi(48),
        tsz48,
        body, up_wick, dn_wick, body12,
        persist(6), persist(24),
        skew(48),
        _log(hi24, c), _log(c, lo24),
        math.sin(tod), math.cos(tod), math.sin(dw), math.cos(dw),
    ]


def contiguous(bars: list[dict], i: int, step_ms: int, back: int = WARMUP) -> bool:
    """True when the `back + 1` bars ending at `i` are consecutive at `step_ms`.

    A feature window spanning an outage mixes two different markets into one 24-hour range, so a
    row over a gap is dropped at training and refused at serving. Both sides call this, so the two
    cannot disagree about what counts as a usable window.
    """
    if i < back:
        return False
    return bars[i]["ts"] - bars[i - back]["ts"] == back * step_ms
