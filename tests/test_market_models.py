"""Brain V4: one candidate per market, and the artifact is the model.

    python -m unittest tests.test_market_models -v

Three things are pinned here, and each is a way the per-market work could quietly be fake:

* the market rule -- a coin is not a US stock even though its industry says US;
* the artifact -- every written `brain-v4-*` model loads from its own file alone, carries the
  contract's feature order and class list, and gives the same answer twice;
* the honest floor -- a market with too little data is recorded as untrained rather than fitted on
  a handful of rows and reported as if the number meant something.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import train_v4_markets as tv  # noqa: E402


class TheMarketRule(unittest.TestCase):
    def test_an_instrument_decides_its_market(self):
        self.assertEqual(tv.market_of_row("crypto", "US"), "Crypto")
        self.assertEqual(tv.market_of_row("commodity", "US"), "Commodity")
        self.assertEqual(tv.market_of_row("forex", "US"), "FX")

    def test_a_stock_is_split_by_its_stored_market(self):
        self.assertEqual(tv.market_of_row("stock", "PK"), "PK")
        self.assertEqual(tv.market_of_row("stock", "US"), "US")
        self.assertEqual(tv.market_of_row("etf", "US"), "US")

    def test_a_missing_market_falls_to_us_and_never_to_pk(self):
        # The default is stated in shadow_markets.market_of: an unknown name is a US name, never a
        # silent Pakistan one.
        self.assertEqual(tv.market_of_row("stock", None), "US")
        self.assertEqual(tv.market_of_row(None, None), "US")


class TheCollapseCheck(unittest.TestCase):
    def test_it_flags_a_prediction_that_leans_on_one_class(self):
        yt = np.array([0, 0, 1, 2, 2, 2, 0, 1, 2, 0])          # UP is not the majority
        yp = np.array([2, 2, 2, 2, 2, 2, 2, 2, 2, 2])          # everything predicted UP
        ca = tv.collapse_analysis(yt, yp)
        self.assertTrue(ca["collapsed"])
        self.assertEqual(ca["dominantPredictedClass"], "UP")

    def test_a_spread_of_predictions_is_not_collapsed(self):
        yt = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0])
        yp = np.array([0, 0, 1, 1, 2, 2, 0, 1, 2, 1])
        self.assertFalse(tv.collapse_analysis(yt, yp)["collapsed"])

    def test_the_class_that_is_the_actual_majority_is_not_a_collapse(self):
        # FX is ~68% FLAT; a model that reads FLAT is right, not degenerate, so the rule must not
        # mistake "predicts the true majority" for "leans on a class".
        yt = np.array([1, 1, 1, 1, 1, 1, 1, 1, 0, 2])
        yp = np.array([1, 1, 1, 1, 1, 1, 1, 1, 0, 2])
        self.assertFalse(tv.collapse_analysis(yt, yp)["collapsed"])


class TheDataFloor(unittest.TestCase):
    def test_a_market_below_the_floor_is_not_trained(self):
        n = 10
        b = {"X": np.zeros((n, len(tv.ALL_FEATURES)), dtype=np.float32),
             "y": np.zeros(n, dtype=np.int64),
             "dates": np.array(["2026-01-01"] * n),
             "symbols": {"X"}, "assetTypes": {"stock": n}, "ctx": 0, "flagged": 0, "rows": n}
        res = tv.fit_market("US", b, "2025-12-31")
        self.assertFalse(res["trained"])
        self.assertIn("data floor", res["reason"])


class TheWrittenArtifacts(unittest.TestCase):
    """Reads what `train_v4_markets.py` actually wrote, so these skip before it has run."""

    def setUp(self):
        self.aggregate_path = ROOT / "data" / "foundation" / "dataset" / "brain_v4_markets.json"
        if not self.aggregate_path.exists():
            self.skipTest("brain_v4_markets.json not generated")
        self.aggregate = json.loads(self.aggregate_path.read_text(encoding="utf-8"))

    def _trained(self):
        return {k: v for k, v in self.aggregate["markets"].items() if v.get("trained")}

    def test_every_market_is_accounted_for(self):
        self.assertEqual(set(self.aggregate["markets"]), set(tv.MARKETS))

    def test_a_trained_market_has_a_model_and_manifest_with_a_matching_digest(self):
        for name, info in self._trained().items():
            d = ROOT / "data" / "foundation" / "brain" / f"brain-v4-{tv.MARKET_DIR[name]}"
            model_file, manifest_file = d / "model.json", d / "manifest.json"
            self.assertTrue(model_file.exists(), f"{name} claims trained but has no model.json")
            self.assertTrue(manifest_file.exists(), f"{name} has no manifest.json")
            digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact"]["sha256"], digest,
                             f"{name}'s manifest digest does not match its model bytes")

    def test_a_loaded_model_carries_the_contract_and_is_not_approved(self):
        for name in self._trained():
            d = ROOT / "data" / "foundation" / "brain" / f"brain-v4-{tv.MARKET_DIR[name]}"
            m = tv.load_model(d)
            self.assertEqual(m["features"], tv.ALL_FEATURES, f"{name} feature order drifted")
            self.assertEqual(m["classes"], tv.CLASSES)
            self.assertEqual(m["market"], name)
            self.assertEqual(len(m["weights"]), len(tv.ALL_FEATURES) + 1)
            self.assertEqual(len(m["standardisation"]["mean"]), len(tv.ALL_FEATURES))
            self.assertEqual(len(m["standardisation"]["sd"]), len(tv.ALL_FEATURES))
            self.assertFalse(m["productionApproved"],
                             "a candidate that passed only a diagnostic holdout is not approved")

    def test_the_same_input_gives_the_same_answer_twice(self):
        probe = np.linspace(-1.0, 1.0, 5 * len(tv.ALL_FEATURES),
                            dtype=np.float32).reshape(5, -1)
        for name in self._trained():
            d = ROOT / "data" / "foundation" / "brain" / f"brain-v4-{tv.MARKET_DIR[name]}"
            m = tv.load_model(d)
            a = tv.predict_matrix(m, probe).argmax(axis=1)
            b = tv.predict_matrix(m, probe).argmax(axis=1)
            self.assertTrue(np.array_equal(a, b), f"{name}'s prediction is not deterministic")

    def test_a_trained_market_reports_the_full_per_class_breakdown(self):
        for name in self._trained():
            d = ROOT / "data" / "foundation" / "brain" / f"brain-v4-{tv.MARKET_DIR[name]}"
            ev = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["evaluation"]
            for c in tv.CLASSES:
                self.assertIn(c, ev["confusion"])
                self.assertIn("recall", ev["perClass"][c])
            self.assertIn("collapseAnalysis", ev)


if __name__ == "__main__":
    unittest.main()
