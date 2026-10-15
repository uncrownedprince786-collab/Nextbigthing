"""The 60-session terminal-movement label, and the rule that fixes its band.

    from tools.research.label60 import band_pct, label_of, calibrate_m

**What this labels, and what it does not.** `label60` is a *terminal movement* label: it compares
one number -- the close 60 stored sessions after `asOf` -- against the close at `asOf`. It says
nothing about the path in between, so it is **not** a statement that a trade would have survived
its stop. `plan_outcome` in `tools/make_dataset.py` is the path-dependent label and stays separate.
Describing this one in reward-to-risk terms would claim semantics it cannot deliver.

**Units.** `jobs/factors.py atr()` returns the average true range **in price units**, while
`fwd{h}` is a **percentage**. A band built from ATR must therefore be divided by the same base the
return is measured from before the two can be compared at all:

    band_pct = m * atr14 / base * 100

The denominator is `base` -- the newest close on or before `asOf`, which is what `fwd60` divides by
-- and not a separately fetched price, so no second reference enters the comparison.

**Why `m` is calibrated rather than chosen.** An earlier proposal set the band at `1.2 x atr14` on
the grounds that `MIN_REWARD_RISK = 1.2`. That does not hold: reward:risk is measured *from the
entry level* against a stop placed one ATR beyond the *entry zone* (`lib/quality.ts`,
`lib/resolve.ts bufferStop`), while `fwd60` is measured from the as-of close, and roughly 30% of
dataset rows carry no setup and so have no entry zone at all. A ratio is not a multiplier.

So `m` is not derived from a trading rule. It is calibrated for **continuity with the frozen
`label20` band**: for each instrument, the multiple of its own ATR that `LABEL_THRESHOLD_PCT = 2.0`
already represents, taken at the median. That uses one frozen constant and one point-in-time
feature -- no outcome, no label, no model -- so it cannot be tuned toward a result, and it answers
what a single index proxy could not: what multiple the existing band implies across the real
universe. `calibrate_m` must be given **training-period rows only**, and the value frozen before
any evaluation.

The band carries a floor of `LABEL_THRESHOLD_PCT`, so an instrument whose ATR collapses toward
zero cannot have every rounding error labelled directional.
"""

from __future__ import annotations

import statistics
from typing import Iterable

#: The frozen 20-session band, from `tools/make_dataset.py`. The floor, and the anchor `m` is
#: calibrated against. Not re-derived here so the two cannot drift apart.
LABEL_THRESHOLD_PCT = 2.0

#: Sessions in the horizon this module labels.
HORIZON = 60

UP, DOWN, FLAT = "UP", "DOWN", "FLAT"


def band_pct(atr14: float | None, base: float | None, m: float) -> float | None:
    """The deadband for one row, as a percentage of `base`.

    `None` when the inputs cannot produce one -- a missing ATR, a non-positive base. A missing
    band makes the row ineligible; it never becomes a FLAT label, because "not measured" and
    "measured and small" are different facts.
    """
    if atr14 is None or base is None:
        return None
    if not (base > 0) or not (atr14 > 0):
        return None
    return max(m * atr14 / base * 100.0, LABEL_THRESHOLD_PCT)


def label_of(fwd60: float | None, band: float | None) -> str | None:
    """UP, DOWN or FLAT for one row, or `None` when the row is not labellable.

    `fwd60` is a percentage, as `tools/make_dataset.py outcomes()` produces it. `None` means the
    60-session window is immature -- fewer than 60 forward sessions are stored -- and such a row
    is **excluded**, never labelled FLAT.
    """
    if fwd60 is None or band is None:
        return None
    if fwd60 >= band:
        return UP
    if fwd60 <= -band:
        return DOWN
    return FLAT


def implied_multiple(atr14: float | None, base: float | None) -> float | None:
    """The ATR multiple that the frozen 2% band already represents for one instrument."""
    if atr14 is None or base is None or not (base > 0) or not (atr14 > 0):
        return None
    atr_pct = atr14 / base * 100.0
    return LABEL_THRESHOLD_PCT / atr_pct


def calibrate_m(rows: Iterable[tuple[float | None, float | None]]) -> float | None:
    """Median implied multiple over `(atr14, base)` pairs from **training-period rows only**.

    Returns `None` when nothing usable was supplied, which the caller must treat as "cannot
    calibrate" rather than substituting a default silently.
    """
    vals = [v for v in (implied_multiple(a, b) for a, b in rows) if v is not None]
    return statistics.median(vals) if vals else None
