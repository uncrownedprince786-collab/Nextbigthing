"""The within-band measurement must not be able to flatter itself.

`within_band_direction.py` asks whether a row the model calls FLAT still carries a direction. The
answer on 2026-10-20 was no, and the value of that answer depends entirely on the measurement being
honest: the artifact it scores must be the one it names, the split must be the trainer's own, the
comparator must be a constant a person could have run, and the gate must require every test to
pass rather than any one of them.

Each of those is asserted here, and the gate is probed with results that pass some tests and fail
others -- because a gate that lets a candidate through on two of three is how a noisy arm becomes
a published direction.
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

import within_band_direction as wb  # noqa: E402
from baseline_experiment import EMBARGO  # noqa: E402

READING = json.loads(
    (ROOT / "data" / "foundation" / "dataset" / "within_band_direction.json")
    .read_text(encoding="utf-8"))


class TheSplitIsTheTrainersTest(unittest.TestCase):
    """A holdout that leaks is the easiest way to manufacture an edge, so the split is pinned."""

    @staticmethod
    def _dates(n_days: int) -> np.ndarray:
        return np.asarray([f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n_days)])

    def test_the_holdout_is_strictly_after_the_cutoff(self):
        dates = self._dates(120)
        tr, te = wb.holdout_split(dates, "2025-03-01")
        self.assertTrue(all(d > "2025-03-01" for d in dates[te]))
        self.assertTrue(all(d <= "2025-03-01" for d in dates[tr]))

    def test_the_embargo_is_applied_and_is_the_trainers_own(self):
        """Sessions immediately before the cutoff are dropped, not trained on.

        A 20-session forward label read on the last training day overlaps the first holdout days,
        so without the embargo the model is fitted on the answer it is about to be tested with.
        """
        dates = self._dates(120)
        tr, te = wb.holdout_split(dates, "2025-03-01")
        gap = [d for d in dates if d <= "2025-03-01" and d not in set(dates[tr])]
        self.assertEqual(len(gap), EMBARGO,
                         "the embargoed sessions are exactly the trainer's EMBARGO")
        self.assertEqual(len(set(dates[tr]) & set(dates[te])), 0)

    def test_no_session_after_the_cutoff_is_refused_rather_than_guessed(self):
        with self.assertRaises(SystemExit):
            wb.holdout_split(self._dates(10), "2099-01-01")


class TheArtifactMustBeTheOneItClaimsTest(unittest.TestCase):
    """The 2026-10-20 defect, guarded at the point of measurement.

    A measurement attributed to the wrong model is worse than no measurement: it is evidence with
    a false owner, which is exactly what shipped. So the evaluator reads the band out of the
    artifact's own manifest and refuses to proceed when it disagrees with the one requested.
    """

    def test_a_mislabelled_band_is_refused(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            # The name says 2.0x; the manifest says 1.0x. One of them is wrong and the evaluator
            # must not pick a winner.
            d = root / wb.tv.artifact_name("US", 5, 2.0)
            d.mkdir(parents=True)
            (d / "model.json").write_text("{}", encoding="utf-8")
            (d / "manifest.json").write_text(
                json.dumps({"task": {"bandScale": 1.0, "labelThresholdPct": 1.0},
                            "artifact": {"sha256": "x"}}), encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                wb.evaluate("US", 5, 2.0, Path(td), "2025-12-31", 10, 1, brain_root=root)
            self.assertIn("was fitted at", str(cm.exception))

    def test_a_missing_artifact_is_refused(self):
        with TemporaryDirectory() as td:
            with self.assertRaises(SystemExit) as cm:
                wb.evaluate("US", 5, 2.0, Path(td), "2025-12-31", 10, 1, brain_root=Path(td))
            self.assertIn("train it before measuring it", str(cm.exception))


class TheGateRequiresEveryTestTest(unittest.TestCase):
    """Any one test failing means no direction is served."""

    @staticmethod
    def _passes(lo: float, paired: bool, p_adj: float) -> bool:
        # The same expression the evaluator uses, kept here so a change to it has to be stated
        # twice -- once in the tool and once as an intention.
        return bool(lo > 0 and paired and p_adj < 0.05)

    def test_all_three_are_needed(self):
        self.assertTrue(self._passes(0.01, True, 0.01))
        self.assertFalse(self._passes(-0.001, True, 0.01), "an interval spanning zero")
        self.assertFalse(self._passes(0.01, False, 0.01), "the paired test failing")
        self.assertFalse(self._passes(0.01, True, 0.20), "multiplicity swallowing the result")

    def test_the_gate_matches_the_tool(self):
        src = (ROOT / "tools" / "research" / "within_band_direction.py").read_text(
            encoding="utf-8")
        self.assertIn("lo > 0 and paired.get(\"passes\") and p_adj < 0.05", src)

    def test_the_bonferroni_adjustment_is_applied_not_just_reported(self):
        src = (ROOT / "tools" / "research" / "within_band_direction.py").read_text(
            encoding="utf-8")
        self.assertIn("p_adj = min(1.0, p_raw * max(arms, 1))", src)


class TheRecordedResultSaysWhatTheSiteSaysTest(unittest.TestCase):
    """The card's wording is derived from this artifact, so the artifact has to support it."""

    def test_direction_inside_the_band_is_recorded_as_noise(self):
        self.assertEqual(READING["verdict"], "NO-GO")
        ci = READING["tests"]["blockedBootstrap"]["ci95"]
        self.assertLess(ci[0], 0.0)
        self.assertGreater(ci[1], 0.0, "the interval spans zero, which is why no side is served")

    def test_the_magnitude_claim_is_real_and_weak(self):
        m = READING["magnitude"]
        self.assertTrue(m["holds"], "the card calls this a real edge")
        self.assertGreater(m["lift"], 0.0)
        self.assertLess(m["precisionOnRowsCalledFlat"], 0.5,
                        "the card says it is wrong more often than right")
        self.assertGreater(m["precisionOnRowsCalledFlat"], m["rateAcrossAllHoldoutRows"])

    def test_the_comparator_is_a_constant_and_not_the_sessions_own_majority(self):
        """The oracle baseline cost this project a wrong sign once; it is named here."""
        self.assertIn(READING["baseline"]["side"], ("UP", "DOWN"))
        self.assertIn("shareInTrainFold", READING["baseline"])

    def test_excluded_rows_are_counted_rather_than_dropped_silently(self):
        self.assertIn("zeroReturnRowsExcluded", READING)
        self.assertEqual(
            READING["n"],
            READING["holdoutFlatRows"] - READING["zeroReturnRowsExcluded"],
            "every FLAT holdout row is either measured or accounted for")

    def test_the_reading_names_the_model_it_was_measured_on(self):
        self.assertEqual(READING["modelVersion"], "brain-v5-h5b20-us")
        self.assertEqual(READING["bandScale"], 2.0)
        man = json.loads(
            (ROOT / "data" / "foundation" / "brain" / READING["modelVersion"] / "manifest.json")
            .read_text(encoding="utf-8"))
        self.assertEqual(READING["artifactSha256"], man["artifact"]["sha256"],
                         "the reading is pinned to the artifact bytes, not just its name")


if __name__ == "__main__":
    unittest.main()
