"""Metric 2 must stay what the frozen scope says it is, and its evidence must stay resolvable."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

D = ROOT / "data" / "foundation" / "dataset"
SCOPE = D / "acceptance_scope.json"
INV = D / "source_inventory.json"
SCORE = D / "foundation_score.json"
GAPS = D / "gap_evidence.json"


class FrozenScopeIsFrozen(unittest.TestCase):
    def test_the_six_attributes_and_denominator_are_unchanged(self):
        m = json.loads(SCOPE.read_text(encoding="utf-8"))["metricDefinitions"][
            "2_organisationAndValidation"]
        self.assertEqual(m["sixAttributes"],
                         ["sourceLineage", "schema", "dateRange", "qualityChecks",
                          "reproducibleLocation", "checksumOrBackup"])
        self.assertIn("including the blocked ones", m["denominator"])

    def test_the_weights_still_sum_to_one(self):
        s = json.loads(SCOPE.read_text(encoding="utf-8"))
        self.assertAlmostEqual(sum(d["weight"] for d in s["domains"]), 1.0, places=6)


class OrganisationIsEvidenced(unittest.TestCase):
    def setUp(self):
        if not INV.exists():
            self.skipTest("source_inventory.json not generated")
        self.inv = json.loads(INV.read_text(encoding="utf-8"))

    def test_every_layer_carries_all_six_attributes(self):
        from organisation_attributes import SIX

        for x in self.inv["layers"]:
            attrs = x.get("organisation") or {}
            for k in SIX:
                self.assertTrue(attrs.get(k), f"{x['layer']} missing {k}")

    def test_every_referenced_repo_path_resolves(self):
        # An attribute naming a file that is not there is an assertion, not evidence.
        for x in self.inv["layers"]:
            attrs = x.get("organisation") or {}
            for key in ("reproducibleLocation", "checksumOrBackup"):
                for tok in (attrs.get(key, "")).replace(",", " ").split():
                    tok = tok.strip("();")
                    if "/" in tok and tok.endswith((".py", ".json", ".yml", ".jsonl")):
                        self.assertTrue((ROOT / tok).exists(),
                                        f"{x['layer']} -> {tok} does not exist")

    def test_blocked_layers_are_organised_but_never_counted_as_covered(self):
        for x in self.inv["layers"]:
            if x["status"] in ("SOURCE_BLOCKED", "LICENSE_BLOCKED"):
                self.assertTrue(x["organisationComplete"], x["layer"])
                self.assertFalse(x["downloaded"], x["layer"])
                self.assertFalse(x["joinedIntoTraining"], x["layer"])

    def test_the_blocked_gaps_have_dated_probe_evidence(self):
        if not GAPS.exists():
            self.skipTest("gap_evidence.json not generated")
        g = json.loads(GAPS.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(g["gaps"]), 3)
        for _name, blob in g["gaps"].items():
            self.assertTrue(blob["probes"])
            for pr in blob["probes"]:
                self.assertTrue(pr["probedAt"])
                self.assertTrue(pr["url"].startswith("http"))


class ScoreIsolation(unittest.TestCase):
    def setUp(self):
        if not SCORE.exists():
            self.skipTest("foundation_score.json not generated")
        self.s = json.loads(SCORE.read_text(encoding="utf-8"))

    def test_organisation_is_reported_apart_from_coverage_and_readiness(self):
        m = self.s["headlineMetrics"]
        for k in ("1_dataCoverage", "2_organisationAndValidation", "3_trainingReadiness",
                  "contextLayerIntegration"):
            self.assertIn(k, m)
        self.assertNotEqual(m["2_organisationAndValidation"]["score"],
                            m["contextLayerIntegration"]["score"])

    def test_the_denominator_is_still_every_layer(self):
        m = self.s["headlineMetrics"]["2_organisationAndValidation"]
        self.assertEqual(m["denominator"], len(self.s["domains"]) + 10)  # 18 layers

    def test_the_superseded_proxy_is_still_reported(self):
        m = self.s["headlineMetrics"]["2_organisationAndValidation"]
        self.assertIn("previousProxyImplementation", m)


if __name__ == "__main__":
    unittest.main()
