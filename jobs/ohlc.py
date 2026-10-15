"""Whether a bar's published range can hold its own close, and what to do when it cannot.

A bar whose close sits outside `[low, high]` is not a wrong price -- it is a range that cannot
describe the session its close belongs to. The two halves have to be treated differently, and
that is the whole of this module:

* **The close is the trustworthy datum.** Every factor in `jobs/factors.py` reads closes and
  nothing else, and the close is what the exchange and the provider both publish as the session's
  result. It is never adjusted here to satisfy an arithmetic rule. Changing a valid close to fit
  a range would be inventing a measurement to protect a weaker one.
* **The range is dropped when it contradicts the close.** `None` already means "not published"
  on this table -- `jobs/prices.py` stores a null rather than Yahoo's placeholder `0` for FX
  volume, for exactly this reason -- so a range that cannot be true is stored as the absence it
  is, and the published values are kept in the quarantine ledger instead.

**Why the thresholds are these.** Measured over the 6,858 affected rows in the stored history:

| market / source | breaches | share that are `high == low` | median breach |
| --- | --- | --- | --- |
| Yahoo, equities and funds | 49 | 1 | 1.7e-15, every one |
| Yahoo, currency pairs | 4,150 | 330 | 3.6e-04 |
| PSX exchange daily file | 2,659 | 1,912 | 2.3e-02 |

Those are three different facts, so they get three different expectations rather than one
tolerance. Yahoo's equity bars are coherent to the last bit: all 49 breaches are at 1.7e-15, which
is float representation and not a measurement, so the floor below which nothing is reported is set
there and not at a round number chosen for comfort. Yahoo's currency bars breach on about 8% of
sessions at a median of 3.6 basis points, because the FX close is a different snapshot from the
range around it -- a property of the feed, counted and expected, not an anomaly per row. The
exchange file is the serious one: 72% of its breaches are a range collapsed to a single value that
is not the close, at a median of 2.3%, and it is still happening -- 763 in 2024, 514 in 2025, 163
in 2026.

Nothing here reads the database or the network, so it is testable without either.
"""

from __future__ import annotations

# Below this relative breach the range and the close disagree only in the last bits of a float.
# Set from the measurement above (Yahoo equities top out at 1.7e-15), not from a round number.
FLOAT_NOISE = 1e-9

# What each source is known to do, so a lane can tell a familiar artefact from a new fault.
# `expected` is the share of bars where a breach is a property of the feed rather than news.
EXPECTED = {
    "Pakistan Stock Exchange daily closing file": "collapsed-range",
    "Yahoo Finance Karachi listing": None,
    "Coinbase": None,
    "Kraken": None,
}
# Currency pairs are the exception that is not a source but an asset class: the same Yahoo feed
# is coherent for equities and not for FX, so the expectation is keyed on what is being quoted.
FOREX_EXPECTED = "snapshot-mismatch"

OK = "ok"
NO_RANGE = "no-range"
FLOAT = "float-noise"
INVERTED = "inverted-range"
COLLAPSED = "collapsed-range"
INCOHERENT = "incoherent-range"

# The verdicts that mean the range cannot be trusted to describe the session.
UNTRUSTWORTHY = (INVERTED, COLLAPSED, INCOHERENT)


def breach(high: float | None, low: float | None, close: float | None) -> float:
    """How far outside its own range the close sits, relative to the bound it passed.

    Relative to the bound and not to the close, so the figure answers "by what fraction is this
    bound wrong". Zero when the close is inside, or when the comparison cannot be made. A
    non-positive bound falls back to an absolute difference: a negative settlement price is real
    (`CL=F` on 2020-04-20) and a ratio against it would be meaningless, not merely large.
    """
    if high is None or low is None or close is None:
        return 0.0
    if low <= close <= high:
        return 0.0
    bound, gap = (high, close - high) if close > high else (low, low - close)
    return abs(gap / bound) if bound > 0 else abs(gap)


def classify(high: float | None, low: float | None, close: float | None) -> str:
    """One word for what this bar's range is, from the range and the close alone."""
    if close is None:
        return NO_RANGE
    if high is None or low is None:
        return NO_RANGE
    if high < low:
        return INVERTED
    if low <= close <= high:
        return OK
    if breach(high, low, close) <= FLOAT_NOISE:
        return FLOAT
    return COLLAPSED if high == low else INCOHERENT


def is_expected(verdict: str, source: str | None, asset_type: str | None) -> bool:
    """Has this source produced this shape of breach before, in volume, for a known reason?

    An expected breach is still recorded; it is not still alarming. The distinction is what lets
    a lane stay quiet about the exchange's thin sessions and say something when Yahoo's equity
    bars -- coherent to the last bit across 604,946 rows -- stop being coherent.
    """
    if verdict in (OK, NO_RANGE, FLOAT):
        return True
    if asset_type == "forex":
        return verdict in (COLLAPSED, INCOHERENT) and FOREX_EXPECTED is not None
    return EXPECTED.get(source or "") == verdict


def guard(open_: float | None, high: float | None, low: float | None, close: float | None):
    """`(open, high, low, verdict)` with a range that contradicts its close removed.

    The close is returned untouched by the caller and is deliberately not a return value here:
    nothing in this function is allowed to change it. `open` travels with the range because an
    open outside the same range is the same defect seen from the other side, and keeping one half
    of a discredited bar would leave a reader thinking the bar was checked and passed.
    """
    verdict = classify(high, low, close)
    if verdict in UNTRUSTWORTHY:
        return None, None, None, verdict
    return open_, high, low, verdict
