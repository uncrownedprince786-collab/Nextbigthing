"""The supervised dataset: targets defined before generation, and nothing labelled early.

`tools/make_dataset.py` keeps three things apart -- the reconstructed candidate, what the live
rule engine said, and what the price then did. These pin the parts that would quietly corrupt a
dataset if they drifted: an immature horizon counted as an outcome, a threshold moved after the
fact, or the engine's verdict used as a filter.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "jobs"))

import make_dataset as md  # noqa: E402


class ForwardOutcomes(unittest.TestCase):
    @staticmethod
    def bars(closes):
        return [{"close": c} for c in closes]

    def test_an_immature_horizon_is_null_and_not_flat(self):
        # Three sessions stored: +1 and +5 are knowable, +20 is not. Null, never 0.0.
        o = md.outcomes(100.0, self.bars([101.0, 102.0, 103.0]))
        self.assertIsNotNone(o["fwd1"])
        self.assertIsNone(o["fwd5"])
        self.assertIsNone(o["fwd20"])
        self.assertIsNone(o["label20"])
        self.assertFalse(o["mature20"])

    def test_returns_are_measured_in_sessions_from_the_base_close(self):
        o = md.outcomes(100.0, self.bars([110.0] + [100.0] * 19))
        self.assertAlmostEqual(o["fwd1"], 10.0, places=4)
        self.assertAlmostEqual(o["fwd20"], 0.0, places=4)

    def test_mfe_and_mae_are_the_window_extremes(self):
        o = md.outcomes(100.0, self.bars([105.0, 90.0, 101.0] + [100.0] * 17))
        self.assertAlmostEqual(o["mfe"], 5.0, places=4)
        self.assertAlmostEqual(o["mae"], -10.0, places=4)

    def test_the_label_band_is_fixed_and_excludes_noise(self):
        # The threshold is a module constant, declared before any row was generated.
        self.assertEqual(md.LABEL_THRESHOLD_PCT, 2.0)
        up = md.outcomes(100.0, self.bars([100.0] * 19 + [103.0]))
        flat = md.outcomes(100.0, self.bars([100.0] * 19 + [101.0]))
        down = md.outcomes(100.0, self.bars([100.0] * 19 + [97.0]))
        self.assertEqual(up["label20"], "UP")
        self.assertEqual(flat["label20"], "FLAT")
        self.assertEqual(down["label20"], "DOWN")

    def test_a_move_inside_the_band_is_flat_even_though_its_sign_is_positive(self):
        o = md.outcomes(100.0, self.bars([100.0] * 19 + [101.9]))
        self.assertGreater(o["fwd20"], 0)
        self.assertEqual(o["label20"], "FLAT")


class PlanOutcomes(unittest.TestCase):
    @staticmethod
    def bars(closes):
        return [{"close": c} for c in closes]

    def test_a_non_directional_candidate_has_no_plan(self):
        r = md.plan_outcome("wait", 100.0, 110.0, 90.0, self.bars([120.0]))
        self.assertIsNone(r["entryHit"])
        self.assertIsNone(r["stopHit"])

    def test_a_long_records_which_level_a_close_reached_first(self):
        hit = md.plan_outcome("buy", 100.0, 110.0, 90.0, self.bars([105.0, 111.0]))
        self.assertTrue(hit["entryHit"])
        self.assertEqual(hit["sessionsHeld"], 2)
        stopped = md.plan_outcome("buy", 100.0, 110.0, 90.0, self.bars([89.0, 111.0]))
        self.assertTrue(stopped["stopHit"])
        self.assertFalse(stopped["entryHit"])

    def test_neither_reached_is_recorded_as_neither(self):
        r = md.plan_outcome("buy", 100.0, 110.0, 90.0, self.bars([100.0, 101.0]))
        self.assertFalse(r["entryHit"])
        self.assertFalse(r["stopHit"])


class DatasetContract(unittest.TestCase):
    SRC = (ROOT / "tools" / "make_dataset.py").read_text(encoding="utf-8")

    def test_the_engine_verdict_is_a_field_and_not_a_filter(self):
        # An example is emitted whatever the rules decided; the verdict rides along.
        self.assertIn('"engineDecision"', self.SRC)
        self.assertIn("not used to filter this dataset", self.SRC)

    def test_continuous_and_categorical_targets_are_kept_apart(self):
        self.assertIn('"continuous": ["fwd1", "fwd5", "fwd20", "mfe", "mae"]', self.SRC)
        self.assertIn('"definedBeforeGeneration": True', self.SRC)

    def test_the_limitations_are_carried_on_every_row_and_in_the_manifest(self):
        self.assertIn('"survivorship": "current-universe-only"', self.SRC)
        self.assertIn("NOT a survivorship-bias-free sample", self.SRC)
        self.assertIn("inputsOmitted", self.SRC)

    def test_nothing_is_written_to_a_database(self):
        for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
            self.assertNotIn(forbidden, self.SRC, forbidden)


if __name__ == "__main__":
    unittest.main()
