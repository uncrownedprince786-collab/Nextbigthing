"""The shadow scorecard grades on the shared label rule and refuses to grade what it cannot.

    python -m unittest discover -s tests -p test_shadow_score.py -v

Stdlib unittest, no database: `score_one` and `aggregate` are pure, and they are the whole of the
judgement this file makes. Three properties matter, each a way the scorer could lie:

* the label is the one the model was trained on (`tools/make_dataset`), not a local re-statement
  that could drift;
* an unelapsed horizon is `awaiting`, never a wrong direction;
* with nothing matured, `accuracy` is `null`, not `0`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.insert(0, str(ROOT / "tools"))

import shadow_score as ss  # noqa: E402
from make_dataset import LABEL_THRESHOLD_PCT  # noqa: E402

BARS_UP = [{"close": 100 + i} for i in range(1, 21)]        # 20 sessions, ends +20%


class TheLabelRuleIsTheTrainedOne(unittest.TestCase):

    def test_the_threshold_is_shared_not_copied(self):
        self.assertEqual(ss.LABEL_THRESHOLD_PCT, LABEL_THRESHOLD_PCT)

    def test_the_boundaries_are_inclusive_like_the_trained_rule(self):
        self.assertEqual(ss.forward_label(2.0), "UP")
        self.assertEqual(ss.forward_label(-2.0), "DOWN")
        self.assertEqual(ss.forward_label(1.99), "FLAT")
        self.assertEqual(ss.forward_label(-1.99), "FLAT")

    def test_a_null_forward_return_has_no_label(self):
        self.assertIsNone(ss.forward_label(None))


class OneScoreIsRightOrWrongOrNeither(unittest.TestCase):

    def test_a_matured_correct_call(self):
        s = ss.score_one("UP", 100.0, BARS_UP)
        self.assertTrue(s["scorable"])
        self.assertTrue(s["mature"])
        self.assertEqual(s["outcomeLabel"], "UP")
        self.assertTrue(s["correct"])

    def test_a_matured_wrong_call_is_wrong_and_not_merely_unscored(self):
        s = ss.score_one("DOWN", 100.0, BARS_UP)
        self.assertTrue(s["mature"])
        self.assertFalse(s["correct"])

    def test_an_unelapsed_horizon_is_awaiting_not_a_miss(self):
        s = ss.score_one("DOWN", 100.0, BARS_UP[:5])          # only 5 of 20 sessions elapsed
        self.assertFalse(s["scorable"])
        self.assertFalse(s["mature"])
        self.assertIsNone(s["correct"])

    def test_no_reference_price_is_reported_not_invented(self):
        s = ss.score_one("UP", None, BARS_UP)
        self.assertFalse(s["scorable"])
        self.assertIn("reference close", s["reason"])


class AggregationCountsApartAndNeverInventsANumber(unittest.TestCase):

    def test_accuracy_is_null_over_nothing(self):
        agg = ss.aggregate([])
        self.assertIsNone(agg["accuracy"])
        self.assertEqual(agg["graded"], 0)

    def test_awaiting_matured_and_graded_are_three_separate_counts(self):
        rows = [
            {"scorable": True, "mature": True, "predicted": "UP",
             "outcomeLabel": "UP", "correct": True},
            {"scorable": True, "mature": True, "predicted": "DOWN",
             "outcomeLabel": "UP", "correct": False},
            {"scorable": False, "mature": False, "predicted": "UP", "outcomeLabel": None},
        ]
        agg = ss.aggregate(rows)
        self.assertEqual(agg["total"], 3)
        self.assertEqual(agg["awaiting"], 1)
        self.assertEqual(agg["matured"], 2)
        self.assertEqual(agg["graded"], 2)
        self.assertEqual(agg["correct"], 1)
        self.assertEqual(agg["accuracy"], 0.5)

    def test_an_unscorable_row_does_not_break_the_tally(self):
        # The exact shape `build` appends for a horizon with no rule: no outcomeLabel, no correct.
        rows = [{"scorable": False, "mature": False, "predicted": "UP",
                 "outcomeLabel": None, "reason": "no rule"},
                {"scorable": False, "mature": False, "predicted": None, "outcomeLabel": None}]
        agg = ss.aggregate(rows)
        self.assertEqual(agg["graded"], 0)
        self.assertIsNone(agg["accuracy"])
        self.assertEqual(agg["byPredicted"], {"UP": 1})


if __name__ == "__main__":
    unittest.main()
