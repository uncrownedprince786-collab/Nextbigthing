"""The promotion gate's arithmetic, including the measurement that prompted it."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))

import significance as sig  # noqa: E402


class BinomialLiftTest(unittest.TestCase):
    def test_the_commodity_reading_that_passed_the_old_gate_does_not_pass_this_one(self):
        """Measured 2026-10-19: 0.4438 against a 0.4410 baseline on 1,424 holdout rows.

        The old gate asked `0.4438 > 0.4410` and answered GO. That lift is four extra correct
        answers and about a fifth of one standard error.
        """
        r = sig.binomial_lift(correct=632, n=1424, baseline=0.4410)
        self.assertAlmostEqual(r["accuracy"], 0.4438, places=4)
        self.assertFalse(r["passes"])
        self.assertTrue(r["enoughData"])
        # The number that makes the old verdict legible rather than just wrong.
        self.assertLess(abs(r["z"]), 0.5)
        self.assertGreater(r["requiredAccuracy"], 0.46)

    def test_a_real_lift_on_the_same_sample_does_pass(self):
        """The gate is not simply refusing everything: move the accuracy up and it passes."""
        r = sig.binomial_lift(correct=int(0.50 * 1424), n=1424, baseline=0.4410)
        self.assertTrue(r["passes"])
        self.assertGreater(r["z"], sig.Z_95)

    def test_accuracy_below_the_baseline_never_passes(self):
        r = sig.binomial_lift(correct=400, n=1424, baseline=0.4410)
        self.assertFalse(r["passes"])
        self.assertLess(r["lift"], 0)

    def test_a_sample_too_small_for_the_approximation_is_refused_not_guessed(self):
        """A 100% accuracy on 10 rows is not evidence, and the gate says which it is."""
        r = sig.binomial_lift(correct=10, n=10, baseline=0.44)
        self.assertFalse(r["passes"])
        self.assertFalse(r["enoughData"])
        self.assertIn("under the", r["why"])

    def test_no_holdout_rows_is_reported_not_divided_by(self):
        r = sig.binomial_lift(correct=0, n=0, baseline=0.44)
        self.assertFalse(r["passes"])
        self.assertFalse(r["enoughData"])

    def test_a_degenerate_baseline_has_nothing_to_beat(self):
        """Every holdout row one class: the baseline is 1.0 and the test is meaningless."""
        r = sig.binomial_lift(correct=900, n=1000, baseline=1.0)
        self.assertFalse(r["passes"])
        self.assertFalse(r["enoughData"])

    def test_the_standard_error_is_taken_under_the_null(self):
        """Not at the observed accuracy: the test asks how surprising this is if nothing is there."""
        r = sig.binomial_lift(correct=632, n=1424, baseline=0.4410)
        expected = (0.4410 * 0.5590 / 1424) ** 0.5
        self.assertAlmostEqual(r["standardError"], round(expected, 4), places=4)


class McNemarTest(unittest.TestCase):
    def test_a_near_tie_between_two_models_on_the_same_rows_does_not_pass(self):
        """The paired shape of the price-only comparison: 60 vs 58 is not a difference."""
        r = sig.mcnemar(only_candidate_right=60, only_other_right=58)
        self.assertFalse(r["passes"])
        self.assertTrue(r["enoughData"])

    def test_a_decisive_paired_win_passes(self):
        r = sig.mcnemar(only_candidate_right=120, only_other_right=60)
        self.assertTrue(r["passes"])
        self.assertGreater(r["z"], sig.Z_95)

    def test_losing_the_pairing_never_passes_however_large(self):
        """A large |b - c| in the wrong direction is a large loss, not a significant win."""
        r = sig.mcnemar(only_candidate_right=60, only_other_right=120)
        self.assertFalse(r["passes"])
        self.assertLess(r["z"], 0)

    def test_two_models_that_never_disagree_carry_no_evidence(self):
        r = sig.mcnemar(only_candidate_right=0, only_other_right=0)
        self.assertFalse(r["passes"])
        self.assertFalse(r["enoughData"])
        self.assertEqual(r["discordant"], 0)

    def test_concordant_rows_are_not_counted(self):
        """Only the disagreements decide it, so the verdict cannot be moved by agreement."""
        a = sig.mcnemar(only_candidate_right=120, only_other_right=60)
        self.assertEqual(a["discordant"], 180)

    def test_too_few_disagreements_is_refused_not_guessed(self):
        r = sig.mcnemar(only_candidate_right=8, only_other_right=1)
        self.assertFalse(r["passes"])
        self.assertFalse(r["enoughData"])

    def test_the_continuity_correction_makes_it_conservative_not_backwards(self):
        """A one-row difference corrects to zero rather than to a negative numerator."""
        r = sig.mcnemar(only_candidate_right=21, only_other_right=20)
        self.assertEqual(r["z"], 0.0)
        self.assertFalse(r["passes"])


if __name__ == "__main__":
    unittest.main()
