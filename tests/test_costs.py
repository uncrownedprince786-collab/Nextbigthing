"""The cost model: what a trade would have cost, and what it refuses to price.

`tools/trade_sim.py` reports gross R and says so. These pin the half that turns a gross result
into a net one -- and, as much, the cases where returning a number would be worse than returning
nothing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import costs  # noqa: E402


class TheCostBands(unittest.TestCase):
    def test_every_stored_asset_type_has_a_band_in_every_scenario(self):
        # The five values `Asset.assetType` can take; a missing one would raise at grading time.
        for t in ("stock", "etf", "crypto", "forex", "commodity"):
            for s in costs.SCENARIOS:
                self.assertIsInstance(costs.band_for(t, s), costs.CostBand, f"{t}/{s}")

    def test_the_bands_are_ordered_low_base_high(self):
        for t in costs.ROUND_TRIP_BPS:
            lo, base, hi = (costs.band_for(t, s).one_way_bps for s in costs.SCENARIOS)
            self.assertLess(lo, base, t)
            self.assertLess(base, hi, t)

    def test_an_unknown_asset_type_or_scenario_raises_rather_than_guessing(self):
        with self.assertRaises(ValueError):
            costs.band_for("tulips", "base")
        with self.assertRaises(ValueError):
            costs.band_for("stock", "optimistic")


class TheRoundTrip(unittest.TestCase):
    def test_a_long_pays_two_crossings_and_no_borrow(self):
        # base stock: 3 + 0.5 + 3 = 6.5 bps one way, twice, on a 100 fill.
        c = costs.round_trip_cost(100.0, "stock", "base", short=False, sessions=20)
        self.assertAlmostEqual(c, 100.0 * (6.5 / 10_000) * 2, places=10)

    def test_a_short_pays_borrow_for_every_session_held(self):
        flat = costs.round_trip_cost(100.0, "stock", "base", short=False, sessions=10)
        held = costs.round_trip_cost(100.0, "stock", "base", short=True, sessions=10)
        self.assertGreater(held, flat)
        self.assertAlmostEqual(held - flat, 100.0 * (0.4 / 10_000) * 10, places=10)

    def test_a_longer_short_costs_more_than_a_shorter_one(self):
        a = costs.round_trip_cost(100.0, "crypto", "base", short=True, sessions=1)
        b = costs.round_trip_cost(100.0, "crypto", "base", short=True, sessions=30)
        self.assertGreater(b, a)

    def test_nonsense_inputs_raise(self):
        with self.assertRaises(ValueError):
            costs.round_trip_cost(0.0, "stock", "base", short=False, sessions=1)
        with self.assertRaises(ValueError):
            costs.round_trip_cost(100.0, "stock", "base", short=False, sessions=-1)


class TheNetResult(unittest.TestCase):
    def test_cost_is_charged_in_R_by_dividing_by_the_risk(self):
        # risk 2.0 on a 100 fill: base stock round trip is 0.13, so 0.065 R.
        n = costs.net_r(1.0, fill=100.0, risk=2.0, asset_type="stock", short=False, sessions=5)
        self.assertAlmostEqual(n, 1.0 - 0.13 / 2.0, places=4)

    def test_a_tight_stop_is_hurt_more_by_the_same_cost(self):
        wide = costs.net_r(1.0, fill=100.0, risk=10.0, asset_type="stock", short=False, sessions=5)
        tight = costs.net_r(1.0, fill=100.0, risk=0.5, asset_type="stock", short=False, sessions=5)
        self.assertGreater(wide, tight)

    def test_an_unknown_gross_stays_unknown(self):
        # None is "no answer". Returning 0.0 would read as a flat trade, which is a different claim.
        self.assertIsNone(costs.net_r(None, fill=100.0, risk=2.0, asset_type="stock",
                                      short=False, sessions=1))

    def test_a_short_on_a_market_that_cannot_be_shorted_is_not_priced(self):
        self.assertIsNone(costs.net_r(1.0, fill=100.0, risk=2.0, asset_type="stock",
                                      short=True, sessions=5, market="PSX"))
        # the same call long is priced normally
        self.assertIsNotNone(costs.net_r(1.0, fill=100.0, risk=2.0, asset_type="stock",
                                         short=False, sessions=5, market="PSX"))

    def test_a_nonpositive_risk_is_not_priced(self):
        self.assertIsNone(costs.net_r(1.0, fill=100.0, risk=0.0, asset_type="stock",
                                      short=False, sessions=1))

    def test_net_is_always_below_gross(self):
        for t in costs.ROUND_TRIP_BPS:
            n = costs.net_r(1.0, fill=100.0, risk=2.0, asset_type=t, short=False, sessions=5)
            self.assertLess(n, 1.0, t)


class TheSensitivityBand(unittest.TestCase):
    def test_it_reports_all_three_scenarios_worst_last(self):
        band = costs.sensitivity(1.0, fill=100.0, risk=1.0, asset_type="crypto",
                                 short=True, sessions=10)
        self.assertEqual(set(band), set(costs.SCENARIOS))
        self.assertGreater(band["low"], band["base"])
        self.assertGreater(band["base"], band["high"])

    def test_a_thin_edge_can_survive_the_base_case_and_die_in_the_high_one(self):
        # The reason the band exists at all: one number would have hidden this.
        # crypto short, 0.5R gross, risk 2.0, held 5 sessions: the base round trip plus borrow
        # costs ~0.10R and the high one ~1.0R, so the same trade is a win and a loss depending
        # only on which execution assumption is used.
        band = costs.sensitivity(0.50, fill=100.0, risk=2.0, asset_type="crypto",
                                 short=True, sessions=5)
        self.assertGreater(band["base"], 0)
        self.assertLess(band["high"], 0)


if __name__ == "__main__":
    unittest.main()
