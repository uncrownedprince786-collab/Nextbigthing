"""Cross-database shadow evidence mapping must preserve prediction/outcome identity."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
import mirror  # noqa: E402


def prediction(pid: str, asset: str, *, version: str = "brain-v4-us", day: str = "2026-10-16") -> dict:
    from datetime import date
    return {
        "id": pid, "modelVersion": version, "modelSha256": "abc123", "strategy": "swing",
        "timeframe": "swing", "assetId": asset, "asOf": date.fromisoformat(day), "horizonSessions": 20,
    }


class ShadowPredictionCrossDatabaseIdentity(unittest.TestCase):
    def test_prediction_ids_map_through_natural_key_and_asset_translation(self):
        source = [prediction("source-id", "source-asset")]
        target = [prediction("target-id", "target-asset")]
        mapped = mirror.build_shadow_prediction_map_from_rows(
            source, target, {"source-asset": "target-asset"}
        )
        self.assertEqual(mapped, {"source-id": "target-id"})

    def test_different_model_or_session_does_not_match(self):
        source = [prediction("source-id", "source-asset")]
        target = [
            prediction("target-wrong-model", "target-asset", version="brain-v4-pk"),
            prediction("target-wrong-session", "target-asset", day="2026-10-17"),
        ]
        mapped = mirror.build_shadow_prediction_map_from_rows(
            source, target, {"source-asset": "target-asset"}
        )
        self.assertEqual(mapped, {})

    def test_missing_asset_mapping_does_not_guess_a_parent(self):
        mapped = mirror.build_shadow_prediction_map_from_rows(
            [prediction("source-id", "unknown-asset")],
            [prediction("target-id", "target-asset")],
            {},
        )
        self.assertEqual(mapped, {})

    def test_outcome_foreign_key_is_translated_and_unmatched_is_skipped(self):
        unmatched = set()
        row = {"id": "outcome-id", "predictionId": "source-id", "observedOn": "2026-10-16", "final": True}
        got = mirror.remap_row(
            row, ("predictionId", "observedOn", "final"), {}, unmatched,
            table="ShadowOutcome", shadow_prediction_map={"source-id": "target-id"},
        )
        self.assertEqual(got["predictionId"], "target-id")
        self.assertEqual(row["predictionId"], "source-id", "source evidence must not be mutated")

        unmatched = set()
        missing = mirror.remap_row(
            row, ("predictionId", "observedOn", "final"), {}, unmatched,
            table="ShadowOutcome", shadow_prediction_map={},
        )
        self.assertIsNone(missing)
        self.assertEqual(unmatched, {"prediction:source-id"})

    def test_shadow_parent_is_declared_before_outcome_child(self):
        self.assertLess(list(mirror.TABLES).index("ShadowPrediction"), list(mirror.TABLES).index("ShadowOutcome"))
        self.assertEqual(
            mirror.TABLES["ShadowPrediction"],
            ("modelVersion", "modelSha256", "strategy", "timeframe", "assetId", "asOf", "horizonSessions"),
        )


if __name__ == "__main__":
    unittest.main()
