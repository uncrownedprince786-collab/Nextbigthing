"""A badge must never be backed by evidence from a different model. This is the guard.

The defect, 2026-10-20
----------------------
The site printed `LONG / MEDIUM` on the US five-session lane beside evidence from
`validate_lift.json`: a 6.3-point lift at a blocked-bootstrap z of 8.98. That evidence was
measured at a **2.0x** label band. The artifact being served, `brain-v5-h5-us`, was trained at
the default **1.0x**. The registry keyed its lane on market, horizon and side alone, so the band
was absent and nothing compared the two.

They were not near-duplicates. The served 1.0x model called UP on **271 of 271** US instruments --
an always-UP predictor -- where the validated 2.0x model calls UP on 182 and FLAT on 89. The
mismatch was found only because somebody looked at the predicted mix.

What is asserted here
---------------------
Every validated lane is checked against the artifact's own **manifest**, not its directory name,
because a misnamed directory is exactly what a name check cannot catch: model version, market,
horizon, label band, the threshold the shared rule implies at that band, the artifact digest, the
feature identity, and that the candidate the evidence came from resolves to this very artifact.

`test_the_original_band_mismatch_is_rejected` is the regression fixture: it rebuilds the broken
lane from 2026-10-20 and fails if the checker ever stops catching it.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

import make_dataset as md  # noqa: E402
import signal_validation as sv  # noqa: E402

BRAIN = ROOT / "data" / "foundation" / "brain"
DATASET = ROOT / "data" / "foundation" / "dataset"
REGISTRY = json.loads((DATASET / "signal_validation.json").read_text(encoding="utf-8"))
LIFT = json.loads((DATASET / "validate_lift.json").read_text(encoding="utf-8"))
VALIDATED = [l for l in REGISTRY["lanes"] if l.get("validated")]


class EveryValidatedLaneMatchesItsArtifactTest(unittest.TestCase):
    def test_at_least_one_lane_is_validated(self):
        """A vacuously passing identity suite would be worse than none."""
        self.assertGreaterEqual(len(VALIDATED), 1)

    def test_every_validated_lane_agrees_with_its_manifest(self):
        for lane in VALIDATED:
            with self.subTest(lane=f"{lane['market']}/h{lane['horizonSessions']}/{lane['side']}"):
                problems = sv.verify_lane(lane, BRAIN, LIFT["candidate"])
                self.assertEqual(problems, [], "; ".join(problems))

    def test_the_validated_candidate_resolves_to_the_artifact_the_lane_names(self):
        """The band in the evidence and the band in the artifact name are the same band."""
        resolved = sv.artifact_for(LIFT["candidate"])
        for lane in VALIDATED:
            self.assertEqual(lane["modelVersion"], resolved)

    def test_the_lane_records_the_band_the_evidence_was_measured_at(self):
        for lane in VALIDATED:
            self.assertEqual(lane.get("bandScale"), LIFT["candidate"].get("bandScale"))
            self.assertEqual(lane["evidence"].get("bandScale"),
                             LIFT["candidate"].get("bandScale"))

    def test_the_threshold_is_the_shared_rule_and_not_a_typed_number(self):
        for lane in VALIDATED:
            man = json.loads((BRAIN / lane["modelVersion"] / "manifest.json")
                             .read_text(encoding="utf-8"))
            expected = round(
                md.label_threshold_pct(lane["horizonSessions"]) * lane["bandScale"], 4)
            self.assertEqual(man["task"]["labelThresholdPct"], expected)

    def test_no_lane_points_at_an_artifact_claiming_production_approval(self):
        for lane in VALIDATED:
            man = json.loads((BRAIN / lane["modelVersion"] / "manifest.json")
                             .read_text(encoding="utf-8"))
            self.assertFalse(man.get("productionApproved"),
                             "nothing here is production-approved and a badge is not a promotion")


class TheCheckerCatchesEachWayIdentityCanDriftTest(unittest.TestCase):
    """Each assertion breaks one field and proves the checker notices."""

    @staticmethod
    def _lane(**over):
        base = dict(VALIDATED[0])
        base["evidence"] = dict(base["evidence"])
        base.update(over)
        return base

    def test_the_original_band_mismatch_is_rejected(self):
        """The regression fixture: the exact broken lane from 2026-10-20.

        A lane naming `brain-v5-h5-us` -- the 1.0x artifact -- while carrying evidence measured at
        a 2.0x band. This is what shipped, and it must never pass again.
        """
        broken = self._lane(modelVersion="brain-v5-h5-us", bandScale=2.0)
        problems = sv.verify_lane(broken, BRAIN, LIFT["candidate"])
        self.assertTrue(problems, "the 1.0x-vs-2.0x mismatch was not caught")
        joined = " ".join(problems)
        self.assertIn("bandScale", joined)

    def test_a_lane_with_no_model_version_covers_nothing(self):
        lane = self._lane()
        lane.pop("modelVersion")
        problems = sv.verify_lane(lane, BRAIN, LIFT["candidate"])
        self.assertTrue(problems)
        self.assertIn("names no modelVersion", " ".join(problems))

    def test_a_wrong_horizon_is_rejected(self):
        problems = sv.verify_lane(self._lane(horizonSessions=20), BRAIN, LIFT["candidate"])
        self.assertTrue(any("horizonSessions" in p for p in problems))

    def test_a_wrong_market_is_rejected(self):
        problems = sv.verify_lane(self._lane(market="PK"), BRAIN, LIFT["candidate"])
        self.assertTrue(any("market" in p for p in problems))

    def test_a_missing_artifact_is_rejected(self):
        problems = sv.verify_lane(self._lane(modelVersion="brain-v9-does-not-exist"), BRAIN,
                                  LIFT["candidate"])
        self.assertTrue(any("no manifest" in p for p in problems))

    def test_evidence_from_a_different_band_than_the_artifact_is_rejected(self):
        """The field the original defect hid in, isolated."""
        lane = self._lane()
        lane["evidence"]["bandScale"] = 1.0  # artifact is 2.0x
        problems = sv.verify_lane(lane, BRAIN, LIFT["candidate"])
        self.assertTrue(any("2026-10-20 defect" in p for p in problems))

    def test_a_candidate_resolving_elsewhere_is_rejected(self):
        """Evidence gathered on one configuration cannot licence another's artifact."""
        other = dict(LIFT["candidate"])
        other["bandScale"] = 1.0
        problems = sv.verify_lane(VALIDATED[0], BRAIN, other)
        self.assertTrue(any("different artifact" in p for p in problems))

    def test_the_checker_is_not_trivially_permissive(self):
        """A guard that passes everything is not a guard."""
        self.assertEqual(sv.verify_lane(VALIDATED[0], BRAIN, LIFT["candidate"]), [])
        self.assertNotEqual(
            sv.verify_lane(self._lane(bandScale=1.0), BRAIN, LIFT["candidate"]), [])


class ArtifactNamingMatchesTheTrainerTest(unittest.TestCase):
    """`signal_validation.artifact_for` and `train_v4_markets.artifact_name` must agree.

    They are two implementations of one rule, and the registry naming an artifact the trainer
    would never write is the same class of fault by another route.
    """

    def test_the_two_naming_rules_agree_across_the_grid(self):
        import train_v4_markets as tv
        for market in ("US", "PK", "FX", "Commodity", "Crypto"):
            for horizon in md.HORIZONS:
                for band in (1.0, 2.0, 3.0):
                    want = tv.artifact_name(market, horizon, band)
                    got = sv.artifact_for(
                        {"market": market, "horizon": horizon, "bandScale": band})
                    self.assertEqual(got, want, f"{market}/h{horizon}/x{band}")

    def test_the_twenty_session_default_family_is_unchanged(self):
        import train_v4_markets as tv
        self.assertEqual(tv.artifact_name("US", 20, 1.0), "brain-v4-us")
        self.assertEqual(sv.artifact_for({"market": "US", "horizon": 20, "bandScale": 1.0}),
                         "brain-v4-us")


if __name__ == "__main__":
    unittest.main()
