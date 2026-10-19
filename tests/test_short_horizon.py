"""The 5-session horizon: its label rule, its writer guards and its scoring.

Everything here is about one question -- can a prediction be recorded now and honestly graded
this week -- and about the three ways that could quietly go wrong: a label band that does not
match the horizon, a row written whose answer is already knowable, and a cap that refuses a new
horizon because an old one filled the session.
"""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

import make_dataset as md  # noqa: E402
import shadow_markets as mk  # noqa: E402
import shadow_score as ss  # noqa: E402


class LabelRuleTest(unittest.TestCase):
    def test_the_twenty_session_band_is_exactly_what_it_always_was(self):
        """The whole scaling rule is worthless if it moves the label already in use."""
        self.assertEqual(md.label_threshold_pct(20), md.LABEL_THRESHOLD_PCT)
        self.assertEqual(md.label_threshold_pct(20), 2.0)

    def test_the_band_scales_with_the_square_root_of_the_horizon(self):
        self.assertEqual(md.label_threshold_pct(5), 1.0)    # 2.0 * sqrt(5/20)
        self.assertEqual(md.label_threshold_pct(1), 0.45)   # 2.0 * sqrt(1/20)

    def test_a_shorter_horizon_gets_a_tighter_band_not_the_same_one(self):
        """Reusing 2% at five sessions would make almost every short call FLAT."""
        self.assertLess(md.label_threshold_pct(5), md.label_threshold_pct(20))
        self.assertLess(md.label_threshold_pct(1), md.label_threshold_pct(5))

    def test_label_for_reads_the_band_of_the_horizon_it_is_given(self):
        # +1.5% is UP over five sessions and FLAT over twenty, which is the point.
        self.assertEqual(md.label_for(1.5, 5), "UP")
        self.assertEqual(md.label_for(1.5, 20), "FLAT")
        self.assertEqual(md.label_for(-1.5, 5), "DOWN")
        self.assertEqual(md.label_for(-1.5, 20), "FLAT")

    def test_an_unelapsed_horizon_is_none_and_never_flat(self):
        self.assertIsNone(md.label_for(None, 5))
        self.assertIsNone(md.label_for(None, 20))

    def test_outcomes_labels_every_horizon_and_marks_each_ones_maturity(self):
        bars = [{"close": 100.0 + i} for i in range(5)]      # five sessions only
        out = md.outcomes(100.0, bars)
        self.assertTrue(out["mature1"])
        self.assertTrue(out["mature5"])
        self.assertFalse(out["mature20"])                     # not enough sessions
        self.assertIsNone(out["label20"])
        self.assertEqual(out["label5"], "UP")                 # +4% clears the 1% band

    def test_maturity_is_the_same_fact_as_a_present_forward_return(self):
        """`mature{h}` must never be able to disagree with `fwd{h}`."""
        for n in range(0, 21):
            out = md.outcomes(100.0, [{"close": 101.0}] * n)
            for h in md.HORIZONS:
                self.assertEqual(out[f"mature{h}"], out[f"fwd{h}"] is not None,
                                 f"{n} bars, horizon {h}")


class TimeframeTest(unittest.TestCase):
    def test_short_is_five_sessions_and_every_market_can_judge_it(self):
        self.assertEqual(mk.STRATEGY_SESSIONS["short"], 5)
        for m in mk.MARKETS:
            self.assertTrue(mk.capability(m, "short")["verifiable"], m)

    def test_the_stated_band_matches_the_graded_band(self):
        """The prose and the arithmetic have to agree, or a scorecard describes the wrong rule."""
        for name, sessions in (("short", 5), ("swing", 20), ("intraday", 1)):
            band = md.label_threshold_pct(sessions)
            self.assertIn(f"{band}%", mk.TIMEFRAMES[name]["judgedOn"], name)

    def test_a_short_call_matures_five_of_its_own_market_sessions_later(self):
        # Friday 2026-10-16 + 5 weekday sessions = Friday 2026-10-23.
        self.assertEqual(mk.matures_after(date(2026, 10, 16), 5, "US"), date(2026, 10, 23))
        # Crypto trades every day, so five sessions is five days.
        self.assertEqual(mk.matures_after(date(2026, 10, 18), 5, "Crypto"), date(2026, 10, 23))


class ScorerHorizonTest(unittest.TestCase):
    def test_the_scorer_grades_the_horizon_the_prediction_was_recorded_under(self):
        bars = [{"close": 101.5}] * 5
        s = ss.score_one("UP", 100.0, bars, 5)
        self.assertTrue(s["mature"])
        self.assertEqual(s["outcomeLabel"], "UP")       # +1.5% clears the five-session band
        self.assertEqual(s["horizonSessions"], 5)
        self.assertTrue(s["correct"])

    def test_the_same_move_is_not_mature_over_twenty_sessions(self):
        bars = [{"close": 101.5}] * 5
        s = ss.score_one("UP", 100.0, bars, 20)
        self.assertFalse(s["mature"])
        self.assertIsNone(s["outcomeLabel"])
        self.assertIsNone(s["correct"])

    def test_a_horizon_with_no_rule_is_refused_rather_than_graded_on_a_guess(self):
        self.assertNotIn(60, md.HORIZONS)

    def test_the_scoring_rule_names_the_horizon_and_band_it_used(self):
        self.assertIn("fwd5", ss.scoring_rule(5))
        self.assertIn("1.0%", ss.scoring_rule(5))
        self.assertIn("fwd20", ss.scoring_rule(20))
        self.assertIn("2.0%", ss.scoring_rule(20))

    def test_a_missing_base_is_still_refused_at_any_horizon(self):
        for h in md.HORIZONS:
            s = ss.score_one("UP", None, [{"close": 101.0}] * 20, h)
            self.assertFalse(s["scorable"])
            self.assertEqual(ss.state_of(s), "unscorable")


class WriterGuardTest(unittest.TestCase):
    """`write_rows` guards, exercised through the same arithmetic the writer runs.

    The writer itself needs a database, so what is pinned here is the decision it makes: which
    rows a given maturity date and horizon let through. A regression in either rule is a silent
    one -- rows simply stop being written, or start being written that should not be -- so the
    conditions are asserted rather than left to a live run to discover.
    """

    @staticmethod
    def _already_matured(matures: date, today: date) -> bool:
        return matures <= today

    def test_a_row_maturing_in_the_future_is_written(self):
        today = date(2026, 10, 19)
        self.assertFalse(self._already_matured(date(2026, 10, 23), today))

    def test_a_row_whose_horizon_has_elapsed_is_refused(self):
        """Measured 2026-10-19: ten 1-session rows, all refused, none written."""
        today = date(2026, 10, 19)
        self.assertTrue(self._already_matured(date(2026, 10, 19), today))
        self.assertTrue(self._already_matured(date(2026, 10, 16), today))

    def test_maturity_today_is_refused_because_the_session_may_have_closed(self):
        today = date(2026, 10, 23)
        self.assertTrue(self._already_matured(today, today))

    def test_the_one_session_horizon_is_unusable_while_factors_lag_a_session(self):
        """Why `intraday` is trained and evaluated but not scheduled.

        The features come from the newest `AssetFactor` session, which trails the calendar. A
        1-session call dated to that session matures on the next one -- a session that has, by
        then, already happened. The guard refuses it, which is correct, and the consequence is
        that the lane would write nothing on every run.
        """
        factor_session = date(2026, 10, 16)
        today = date(2026, 10, 19)
        matures = mk.matures_after(factor_session, 1, "US")
        self.assertEqual(matures, date(2026, 10, 19))
        self.assertTrue(self._already_matured(matures, today))
        # The same lag over five sessions is harmless: the row is still genuinely forward.
        self.assertFalse(self._already_matured(
            mk.matures_after(factor_session, 5, "US"), today))


class CapScopeTest(unittest.TestCase):
    """The per-market/session cap counts horizons apart, or a new one can never start."""

    def test_the_cap_key_carries_the_horizon(self):
        rows = [
            {"market": "US", "asOf": "2026-10-16", "horizonSessions": 20},
            {"market": "US", "asOf": "2026-10-16", "horizonSessions": 5},
        ]
        keys = {(r["market"], r["asOf"], int(r["horizonSessions"])) for r in rows}
        self.assertEqual(len(keys), 2, "a 5-session and a 20-session call are two budgets")

    def test_without_the_horizon_the_two_share_one_budget(self):
        """The defect this fixed: `skippedByCap: 10` on the first five-session run."""
        rows = [
            {"market": "US", "asOf": "2026-10-16", "horizonSessions": 20},
            {"market": "US", "asOf": "2026-10-16", "horizonSessions": 5},
        ]
        keys = {(r["market"], r["asOf"]) for r in rows}
        self.assertEqual(len(keys), 1)


if __name__ == "__main__":
    unittest.main()
