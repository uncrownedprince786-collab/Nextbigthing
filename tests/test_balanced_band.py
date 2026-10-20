"""The per-market band must be a labelling decision, not a search for a better number.

The temptation this file guards against is precise. Choosing a label band per market is exactly
the kind of move that can manufacture an accuracy figure: pick the band that scores best and the
holdout has been used to tune the problem. So the rule is pinned here -- a quantile of the
training fold's own return distribution, nothing to do with any model's score -- and so is the
consequence, which is that the band must be *reported*, because accuracy under a +/-0.36% band and
accuracy under a +/-2.0% band are answers to different questions.

The finding this recorded is also pinned, because it is the kind that gets quietly forgotten: FX
scored 0.9361 under the shared band by answering FLAT to all of it, and under a fair band it
scores 0.3848 against a 0.3830 majority. The high number was the band, not the model.
"""

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

import balanced_band as bb  # noqa: E402
from baseline_experiment import CLASSES, EMBARGO  # noqa: E402

RESULT = json.loads(
    (ROOT / "data" / "foundation" / "dataset" / "balanced_band_markets.json")
    .read_text(encoding="utf-8"))


class TheBandComesFromTheTrainFoldAloneTest(unittest.TestCase):
    def test_the_band_balances_the_three_classes(self):
        rng = np.random.default_rng(7)
        fwd = rng.normal(0.0, 3.0, 50_000)
        band = bb.band_from_train_fold(fwd)
        y = bb.label_at(fwd, band)
        for i, c in enumerate(CLASSES):
            share = float((y == i).mean())
            self.assertAlmostEqual(share, 1 / 3, delta=0.02, msg=f"{c} holds {share:.4f}")

    def test_the_band_is_symmetric(self):
        """One number bounds both sides, so a skewed market does not get a tilted band."""
        fwd = np.asarray([-9.0, -4.0, -0.1, 0.2, 5.0, 11.0, 12.0, 13.0])
        band = bb.band_from_train_fold(fwd)
        y_pos = bb.label_at(np.asarray([band, band - 1e-6]), band)
        y_neg = bb.label_at(np.asarray([-band, -(band - 1e-6)]), band)
        self.assertEqual(y_pos[0], CLASSES.index("UP"))
        self.assertEqual(y_neg[0], CLASSES.index("DOWN"))
        self.assertEqual(y_pos[1], CLASSES.index("FLAT"))
        self.assertEqual(y_neg[1], CLASSES.index("FLAT"))

    def test_a_tiny_band_is_floored(self):
        """A band inside the spread labels noise as a class; the floor refuses that."""
        self.assertEqual(bb.band_from_train_fold(np.zeros(1000)), bb.MIN_BAND_PCT)

    def test_the_band_does_not_depend_on_any_score(self):
        """`band_from_train_fold` takes returns and nothing else -- no model, no labels, no y."""
        import inspect
        params = list(inspect.signature(bb.band_from_train_fold).parameters)
        self.assertEqual(params, ["fwd_train"],
                         "a second argument here would be the beginning of tuning")

    def test_the_holdout_is_embargoed_and_after_the_cutoff(self):
        dates = np.asarray([f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(120)])
        tr, te = bb.split_indices(dates, "2025-03-01")
        self.assertTrue(all(d > "2025-03-01" for d in dates[te]))
        dropped = [d for d in dates if d <= "2025-03-01" and d not in set(dates[tr])]
        self.assertEqual(len(dropped), EMBARGO)


class TheResultIsReportedHonestlyTest(unittest.TestCase):
    def test_every_market_records_the_band_it_was_judged_under(self):
        for market, r in RESULT["markets"].items():
            if not r.get("trained"):
                continue
            with self.subTest(market=market):
                self.assertIn("bandPct", r)
                self.assertGreaterEqual(r["bandPct"], bb.MIN_BAND_PCT)
                self.assertIn("quantile", r["bandChosenFrom"])

    def test_each_market_is_read_against_its_own_majority(self):
        """Not against the old number, and not against another market's."""
        for market, r in RESULT["markets"].items():
            if not r.get("trained"):
                continue
            with self.subTest(market=market):
                self.assertIn("holdoutMajorityShare", r)
                measured, baseline, passed, test = r["checks"]["accuracyAboveHoldoutMajority"]
                self.assertEqual(baseline, r["holdoutMajorityShare"])
                # One-way: a pass must at least beat the baseline, but beating it is not a pass.
                # The gate is a significance test, and US is exactly why the distinction matters
                # -- 0.3823 against 0.3791 is ahead and still not evidence of anything.
                if passed:
                    self.assertGreater(measured, baseline,
                                       f"{market} passed while scoring at or below its baseline")
                self.assertEqual(passed, bool(test["passes"]),
                                 "the verdict is the test's, not a bare comparison")

    def test_the_artifact_states_that_accuracies_are_not_comparable(self):
        self.assertIn("not comparable", RESULT["comparability"])

    def test_the_fx_result_is_recorded_as_a_band_artefact_not_a_model(self):
        """The number that would otherwise look like 94% accuracy.

        Under the shared 2.0% band FX predicted FLAT on 1.0 of rows and scored 0.9361 -- the
        holdout majority share, exactly. Under a band that balances the classes it scores near
        chance. If a future run ever makes FX look strong again, this is the comparison to redo.
        """
        fx = RESULT["markets"]["FX"]
        self.assertTrue(fx["trained"])
        self.assertLess(fx["bandPct"], 1.0, "a fair FX band is well under the shared 2.0%")
        self.assertLess(fx["accuracy"], 0.5, "FX is near chance once the classes are balanced")
        self.assertLess(fx["predictedMix"]["FLAT"], 0.9,
                        "the all-FLAT collapse is what the band fixed")

    def test_nothing_here_claims_promotion(self):
        self.assertIn("nothing here is promoted", RESULT["promotionRule"])
        for market, r in RESULT["markets"].items():
            with self.subTest(market=market):
                self.assertNotEqual(r.get("verdict"), "APPROVED")

    def test_no_market_is_claimed_to_beat_its_baseline_without_the_test_agreeing(self):
        """A verdict of GO requires every check, and each check carries its own test."""
        for market, r in RESULT["markets"].items():
            if not r.get("trained"):
                continue
            with self.subTest(market=market):
                if r["verdict"] == "GO":
                    for name, c in r["checks"].items():
                        self.assertTrue(c[2], f"{market} is GO while {name} fails")


if __name__ == "__main__":
    unittest.main()
