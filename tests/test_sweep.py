"""Guards on the sweep harness, which is only worth running if it cannot flatter itself.

A grid that searches many arms is a machine for finding a good-looking number, so the parts that
decide what "good" means are the parts that need pinning: the chronological split and its embargo,
the label derived from the shared rule rather than a local copy, and the selective-prediction
report that must never state an accuracy without the coverage it was measured at.
"""

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

import make_dataset as md  # noqa: E402
import sweep  # noqa: E402
from baseline_experiment import CLASSES, EMBARGO  # noqa: E402


def _dates(days: int) -> np.ndarray:
    """One row per session, as the dataset stores them: ISO strings, sorted."""
    return np.asarray([f"2025-{1 + d // 28:02d}-{1 + d % 28:02d}" for d in range(days)])


class ChronologicalSplitTest(unittest.TestCase):
    def test_no_holdout_row_predates_any_training_row(self):
        dates = _dates(200)
        tr, te, _ = sweep.chronological(dates, "2025-04-01")
        self.assertIsNotNone(tr)
        # Python's max, not numpy's: numpy 2 has no maximum loop for fixed-width strings.
        self.assertLess(max(dates[tr].tolist()), min(dates[te].tolist()))

    def test_the_embargo_removes_whole_sessions_before_the_boundary(self):
        dates = _dates(200)
        tr, te, _ = sweep.chronological(dates, "2025-04-01", embargo=EMBARGO)
        gap = len(set(dates)) - len(set(dates[tr])) - len(set(dates[te]))
        self.assertEqual(gap, EMBARGO, "exactly the embargo's sessions are dropped")

    def test_a_larger_embargo_drops_more(self):
        dates = _dates(200)
        a, _, _ = sweep.chronological(dates, "2025-04-01", embargo=5)
        b, _, _ = sweep.chronological(dates, "2025-04-01", embargo=40)
        self.assertGreater(len(a), len(b))

    def test_a_boundary_with_no_room_for_the_embargo_is_refused(self):
        tr, te, _ = sweep.chronological(_dates(200), "2025-01-02", embargo=EMBARGO)
        self.assertIsNone(tr)
        self.assertIsNone(te)

    def test_a_boundary_past_every_date_is_refused_rather_than_scoring_nothing(self):
        tr, te, _ = sweep.chronological(_dates(50), "2099-01-01")
        self.assertIsNone(tr)


class LabelDerivationTest(unittest.TestCase):
    def test_the_band_comes_from_the_shared_rule_at_scale_one(self):
        fwd = np.asarray([2.5, -2.5, 0.0, np.nan], dtype=np.float32)
        y, usable = sweep.labels_for(fwd, 20, 1.0)
        self.assertEqual(md.label_threshold_pct(20), 2.0)
        self.assertEqual(list(y[:3]), [CLASSES.index("UP"), CLASSES.index("DOWN"),
                                       CLASSES.index("FLAT")])
        self.assertFalse(usable[3], "an unmatured forward return is not a row")

    def test_a_wider_band_turns_decided_rows_into_flat(self):
        fwd = np.asarray([2.5, -2.5], dtype=np.float32)
        wide, _ = sweep.labels_for(fwd, 20, 2.0)      # band 4.0%
        self.assertEqual(list(wide), [CLASSES.index("FLAT")] * 2)

    def test_scaling_the_band_scales_the_threshold_and_nothing_else(self):
        for h in md.HORIZONS:
            for s in (0.5, 1.0, 3.0):
                fwd = np.asarray([md.label_threshold_pct(h) * s], dtype=np.float32)
                y, _ = sweep.labels_for(fwd, h, s)
                self.assertEqual(y[0], CLASSES.index("UP"), f"h{h} x{s} at exactly the band is UP")

    def test_an_unmatured_row_is_never_silently_flat(self):
        y, usable = sweep.labels_for(np.asarray([np.nan] * 5, dtype=np.float32), 5, 1.0)
        self.assertFalse(usable.any())


class SelectiveReportTest(unittest.TestCase):
    """An accuracy without its coverage is a selection effect wearing a number's clothes."""

    @staticmethod
    def _probs(conf_order, preds, k=3):
        P = np.full((len(preds), k), 0.01)
        for i, (c, p) in enumerate(zip(conf_order, preds)):
            P[i] = (1.0 - c) / (k - 1)
            P[i, p] = c
        return P

    def test_every_row_carries_the_coverage_it_was_measured_at(self):
        P = self._probs([0.9, 0.8, 0.7, 0.6], [0, 0, 0, 0])
        yte = np.asarray([0, 0, 1, 1])
        for row in sweep.selective(P, yte):
            self.assertIn("coverage", row)
            self.assertIn("accuracy", row)
            self.assertIn("n", row)
            self.assertIn("majorityShareInSlice", row)

    def test_full_coverage_accuracy_equals_plain_accuracy(self):
        P = self._probs([0.9, 0.8, 0.7, 0.6], [0, 0, 0, 0])
        yte = np.asarray([0, 0, 1, 1])
        full = [r for r in sweep.selective(P, yte) if r["coverage"] == 1.0][0]
        self.assertAlmostEqual(full["accuracy"], 0.5, places=4)
        self.assertEqual(full["n"], 4)

    def test_a_confident_slice_is_reported_with_its_own_base_rate(self):
        """So a high number on an easy slice reads as an easy slice, not as skill."""
        P = self._probs([0.99, 0.98, 0.51, 0.50], [0, 0, 0, 0])
        yte = np.asarray([0, 0, 1, 1])
        half = [r for r in sweep.selective(P, yte) if r["coverage"] == 0.5][0]
        self.assertAlmostEqual(half["accuracy"], 1.0, places=4)
        self.assertAlmostEqual(half["majorityShareInSlice"], 1.0, places=4)

    def test_coverage_never_reports_more_rows_than_exist(self):
        P = self._probs([0.9, 0.8], [0, 0])
        for row in sweep.selective(P, np.asarray([0, 1])):
            self.assertLessEqual(row["n"], 2)
            self.assertGreaterEqual(row["n"], 1)


class ScoreReportTest(unittest.TestCase):
    def test_a_score_always_carries_the_baseline_it_stands_on(self):
        P = np.asarray([[0.8, 0.1, 0.1]] * 10)
        yte = np.zeros(10, dtype=np.int64)
        r = sweep.score(P, yte, baseline_acc=1.0)
        self.assertEqual(r["accuracy"], 1.0)
        self.assertEqual(r["majorityShare"], 1.0)
        self.assertIn("vsMajority", r)
        self.assertFalse(r["vsMajority"]["passes"],
                         "matching a degenerate baseline is not beating it")

    def test_balanced_accuracy_exposes_a_single_class_predictor(self):
        """Predicting one class on an imbalanced holdout scores well and knows nothing."""
        yte = np.asarray([0] * 90 + [1] * 10)
        P = np.tile(np.asarray([0.9, 0.05, 0.05]), (100, 1))
        r = sweep.score(P, yte, baseline_acc=0.9)
        self.assertAlmostEqual(r["accuracy"], 0.9, places=4)
        self.assertLess(r["balancedAccuracy"], 0.55, "balanced accuracy sees through it")

    def test_the_paired_comparison_is_reported_when_a_rival_is_given(self):
        yte = np.asarray([0, 1, 0, 1] * 25)
        P = np.tile(np.asarray([0.9, 0.05, 0.05]), (100, 1))
        rival = np.zeros(100, dtype=bool)
        r = sweep.score(P, yte, baseline_acc=0.5, rival_correct=rival)
        self.assertIn("vsPriceOnly", r)
        self.assertIn("discordant", r["vsPriceOnly"])


if __name__ == "__main__":
    unittest.main()
