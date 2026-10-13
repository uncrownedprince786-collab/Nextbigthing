"""What a trade would have cost, so a gross R can be read as a net one.

    from costs import net_r, ROUND_TRIP_BPS, SCENARIOS

`tools/trade_sim.py` grades every published call as a trade and says, in its own docstring, that
"R is gross: no spread, commission, borrow or slippage is modelled, because none of it is stored".
That is honest and it is also the reason a positive result there cannot be called profitable. This
file supplies the missing half.

**Every number here is an assumption, and none of it is measured.** The database stores daily
closes; it stores no quote, no fill, no commission and no borrow rate, so there is nothing to
measure against. What this gives is a stated, sourced-by-reasoning band -- low, base and high --
and a sensitivity readout across the three, so a result can be reported as "survives the base
case and dies in the high case" rather than as a single invented number.

Why basis points of notional, applied twice
-------------------------------------------
A round trip crosses the spread on the way in and on the way out, pays commission on both, and
slips on both. Expressing each as basis points of the fill price and doubling is the simplest
model that is honest about being a model. It deliberately does not vary with size, time of day,
or volatility, because none of those are stored either, and a cost model with parameters nobody
can calibrate is a worse lie than a flat one.

The bands below are ordinary retail-execution magnitudes for liquid names, not quotes from any
venue, and they are set wide rather than precise:

  * **US equities and ETFs** -- commission is frequently zero at retail; the cost is the spread
    and the slippage. PSX is wider and less liquid, and carries statutory charges this file does
    not attempt to itemise.
  * **Crypto** -- taker fees dominate and are the same either side; the spread on majors is thin
    and on small caps is not.
  * **FX** -- quoted as spread only; commission is usually built into it.
  * **Commodities** -- futures-like costs, dominated by the spread on the front month.

Shorting
--------
A short pays borrow for every session it is held. `borrow_bps_per_session` is a flat stand-in for
a rate that really varies by name and by day, and for a hard-to-borrow name it is far too low.
Where a market does not permit retail shorting at all, `shortable=False` says so and `net_r`
refuses to price it rather than returning a number that implies the trade was possible.
"""

from __future__ import annotations

from dataclasses import dataclass

SCENARIOS = ("low", "base", "high")


@dataclass(frozen=True)
class CostBand:
    """One side of a round trip, in basis points of the fill price, plus the borrow it carries."""

    spread_bps: float
    commission_bps: float
    slippage_bps: float
    borrow_bps_per_session: float = 0.0
    shortable: bool = True

    @property
    def one_way_bps(self) -> float:
        return self.spread_bps + self.commission_bps + self.slippage_bps


# asset type -> scenario -> band. `assetType` values are the ones stored on `Asset`.
ROUND_TRIP_BPS: dict[str, dict[str, CostBand]] = {
    "stock": {
        "low":  CostBand(spread_bps=1.0, commission_bps=0.0, slippage_bps=1.0, borrow_bps_per_session=0.1),
        "base": CostBand(spread_bps=3.0, commission_bps=0.5, slippage_bps=3.0, borrow_bps_per_session=0.4),
        "high": CostBand(spread_bps=10.0, commission_bps=2.0, slippage_bps=10.0, borrow_bps_per_session=2.0),
    },
    "etf": {
        "low":  CostBand(spread_bps=1.0, commission_bps=0.0, slippage_bps=1.0, borrow_bps_per_session=0.1),
        "base": CostBand(spread_bps=2.0, commission_bps=0.5, slippage_bps=2.0, borrow_bps_per_session=0.3),
        "high": CostBand(spread_bps=6.0, commission_bps=2.0, slippage_bps=6.0, borrow_bps_per_session=1.5),
    },
    "crypto": {
        "low":  CostBand(spread_bps=2.0, commission_bps=5.0, slippage_bps=3.0, borrow_bps_per_session=1.0),
        "base": CostBand(spread_bps=6.0, commission_bps=10.0, slippage_bps=8.0, borrow_bps_per_session=3.0),
        "high": CostBand(spread_bps=25.0, commission_bps=20.0, slippage_bps=30.0, borrow_bps_per_session=10.0),
    },
    "forex": {
        "low":  CostBand(spread_bps=0.5, commission_bps=0.0, slippage_bps=0.5),
        "base": CostBand(spread_bps=1.5, commission_bps=0.3, slippage_bps=1.5),
        "high": CostBand(spread_bps=5.0, commission_bps=1.0, slippage_bps=5.0),
    },
    "commodity": {
        "low":  CostBand(spread_bps=1.0, commission_bps=0.5, slippage_bps=1.0),
        "base": CostBand(spread_bps=4.0, commission_bps=1.0, slippage_bps=4.0),
        "high": CostBand(spread_bps=15.0, commission_bps=3.0, slippage_bps=15.0),
    },
}

# Markets where this file will not price a short, because a retail account generally cannot take
# one. Saying "unshortable" is more useful than returning a net R for a trade nobody could place.
NO_RETAIL_SHORT_MARKETS = {"PSX"}


def band_for(asset_type: str, scenario: str) -> CostBand:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}, not {scenario!r}")
    table = ROUND_TRIP_BPS.get(asset_type)
    if table is None:
        raise ValueError(f"no cost band for assetType {asset_type!r}")
    return table[scenario]


def round_trip_cost(fill: float, asset_type: str, scenario: str, *, short: bool, sessions: int) -> float:
    """The cost of one round trip, in the price's own units.

    Two crossings of `one_way_bps`, plus borrow for every session a short was held. A long pays no
    borrow. `sessions` below zero is a caller error, not a free trade.
    """
    if fill <= 0:
        raise ValueError("fill must be positive")
    if sessions < 0:
        raise ValueError("sessions cannot be negative")
    band = band_for(asset_type, scenario)
    cost = fill * (band.one_way_bps / 10_000.0) * 2
    if short:
        cost += fill * (band.borrow_bps_per_session / 10_000.0) * sessions
    return cost


def net_r(
    gross_r: float | None,
    *,
    fill: float,
    risk: float,
    asset_type: str,
    short: bool,
    sessions: int,
    scenario: str = "base",
    market: str | None = None,
) -> float | None:
    """`gross_r` less the round trip, expressed in the same R units.

    `risk` is the distance from fill to stop, which is what one R is worth, so a cost in price
    units divides by it. Returns `None` when the gross result is unknown or when the trade could
    not have been placed -- never 0.0, which would read as a flat trade rather than as no answer.
    """
    if gross_r is None:
        return None
    if short and market in NO_RETAIL_SHORT_MARKETS:
        return None
    if risk <= 0:
        return None
    cost = round_trip_cost(fill, asset_type, scenario, short=short, sessions=sessions)
    return round(gross_r - cost / risk, 4)


def sensitivity(
    gross_r: float | None,
    *,
    fill: float,
    risk: float,
    asset_type: str,
    short: bool,
    sessions: int,
    market: str | None = None,
) -> dict[str, float | None]:
    """Net R under every scenario, so a result is reported as a band and not as one number."""
    return {
        s: net_r(gross_r, fill=fill, risk=risk, asset_type=asset_type, short=short,
                 sessions=sessions, scenario=s, market=market)
        for s in SCENARIOS
    }
