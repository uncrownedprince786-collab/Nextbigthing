"""Market classification, timeframe profiles and the session calendar.

    python -m unittest discover -s tests -p test_shadow_markets.py -v

Stdlib unittest, no database, no network, no artifact: this pins the vocabulary and the calendar
rule that a shadow prediction's market and maturity depend on. The defect it guards against is
concrete -- the first shadow path filed FX, commodities and crypto as "US" -- so the first class
below is a table of the exact mistypings that used to happen.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))

import shadow_markets as mk  # noqa: E402


class MarketIsReadFromTypeThenSource(unittest.TestCase):

    def test_each_type_maps_to_its_own_market(self):
        self.assertEqual(mk.market_of("crypto", "coinpaprika"), "Crypto")
        self.assertEqual(mk.market_of("forex", "yahoo"), "FX")
        self.assertEqual(mk.market_of("commodity", "yahoo"), "Commodity")
        self.assertEqual(mk.market_of("etf", "yahoo"), "US")

    def test_the_shared_type_is_split_by_source(self):
        # The one value two markets share: psx is Pakistan, yahoo is US.
        self.assertEqual(mk.market_of("stock", "psx"), "PK")
        self.assertEqual(mk.market_of("stock", "yahoo"), "US")

    def test_the_old_case_expression_would_have_been_wrong(self):
        # `source == 'psx' -> PK else US` filed all three of these under US.
        self.assertNotEqual(mk.market_of("forex", "yahoo"), "US")
        self.assertNotEqual(mk.market_of("commodity", "yahoo"), "US")
        self.assertNotEqual(mk.market_of("crypto", "coinpaprika"), "US")

    def test_a_crypto_source_alone_is_enough(self):
        self.assertEqual(mk.market_of(None, "coinpaprika"), "Crypto")

    def test_an_unknown_name_falls_to_us_and_never_to_pk(self):
        self.assertEqual(mk.market_of(None, None), "US")
        self.assertEqual(mk.market_of("warrant", "unknown"), "US")


class TheTimeframeProfilesAreOrderedAndStated(unittest.TestCase):

    def test_scalp_cannot_be_judged_from_daily_closes(self):
        self.assertFalse(mk.TIMEFRAMES["scalp"]["dailyClosesCanJudge"])
        self.assertEqual(mk.TIMEFRAMES["scalp"]["sessions"], 0)

    def test_swing_is_the_trained_twenty_session_horizon(self):
        self.assertEqual(mk.TIMEFRAMES["swing"]["sessions"], 20)
        self.assertTrue(mk.TIMEFRAMES["swing"]["dailyClosesCanJudge"])

    def test_strategy_sessions_mirror_the_profiles(self):
        for name, spec in mk.TIMEFRAMES.items():
            self.assertEqual(mk.STRATEGY_SESSIONS[name], spec["sessions"])


class CapabilitySaysWhatTheDataCanJudge(unittest.TestCase):

    def test_swing_is_verifiable_in_every_market(self):
        for m in mk.MARKETS:
            self.assertTrue(mk.capability(m, "swing")["verifiable"], m)

    def test_scalp_is_unverifiable_in_every_market(self):
        for m in mk.MARKETS:
            self.assertFalse(mk.capability(m, "scalp")["verifiable"], m)

    def test_the_matrix_covers_every_pair(self):
        matrix = mk.market_capability_matrix()
        self.assertEqual(len(matrix), len(mk.MARKETS) * len(mk.TIMEFRAMES))
        keys = {(r["market"], r["timeframe"]) for r in matrix}
        self.assertEqual(keys, {(m, t) for m in mk.MARKETS for t in mk.TIMEFRAMES})

    def test_an_unknown_market_or_timeframe_is_refused(self):
        with self.assertRaises(ValueError):
            mk.capability("Mars", "swing")
        with self.assertRaises(ValueError):
            mk.capability("US", "fortnight")


class SessionsFollowTheMarketsOwnCalendar(unittest.TestCase):
    # 2026-10-16 is a Friday; 17/18 are the weekend; 19 is the Monday.
    FRI = date(2026, 10, 16)

    def test_zero_sessions_after_is_the_same_day(self):
        self.assertEqual(mk.sessions_after(self.FRI, 0, "US"), self.FRI)

    def test_a_weekday_market_skips_the_weekend(self):
        self.assertEqual(mk.sessions_after(self.FRI, 1, "US"), date(2026, 10, 19))
        self.assertEqual(mk.sessions_after(self.FRI, 5, "US"), date(2026, 10, 23))

    def test_crypto_does_not_skip_the_weekend(self):
        self.assertEqual(mk.sessions_after(self.FRI, 1, "Crypto"), date(2026, 10, 17))
        self.assertEqual(mk.sessions_after(self.FRI, 3, "Crypto"), date(2026, 10, 19))

    def test_twenty_us_sessions_are_about_four_weeks(self):
        self.assertEqual(mk.sessions_after(self.FRI, 20, "US"), date(2026, 11, 13))

    def test_sessions_between_counts_only_this_markets_sessions(self):
        self.assertEqual(mk.sessions_between(self.FRI, date(2026, 10, 19), "US"), 1)
        self.assertEqual(mk.sessions_between(self.FRI, date(2026, 10, 19), "Crypto"), 3)
        self.assertEqual(mk.sessions_between(date(2026, 10, 19), self.FRI, "US"), 0)

    def test_a_negative_horizon_is_a_mistake_not_a_date(self):
        with self.assertRaises(ValueError):
            mk.sessions_after(self.FRI, -1, "US")


class MarketProfilesStateTheCalendar(unittest.TestCase):

    def test_only_crypto_trades_weekends(self):
        for m in mk.MARKETS:
            self.assertEqual(mk.market_profile(m)["tradesOnWeekends"], m == "Crypto", m)


if __name__ == "__main__":
    unittest.main()
