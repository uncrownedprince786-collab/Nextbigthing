"""Gates on the historical regime library, the 2008 package and the source inventory.

Dataset gates read committed artifacts and skip when one is absent, never pass.
"""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
F = ROOT / "data" / "foundation"
HIST = F / "dataset" / "historical_regimes.json"
INV = F / "dataset" / "source_inventory.json"
CRISIS = F / "crisis_2008"

VALID_STATUS = {"COMPLETE", "PARTIAL", "MISSING", "SOURCE_BLOCKED", "LICENSE_BLOCKED",
                "NOT_APPLICABLE"}


class HistoricalRegimes(unittest.TestCase):
    def setUp(self):
        if not HIST.exists():
            self.skipTest("historical_regimes.json not generated")
        self.d = json.loads(HIST.read_text(encoding="utf-8"))

    def test_the_known_drawdowns_match_the_historical_record(self):
        # If the detector drifts, these are the numbers that move first.
        want = {"1929 crash and Great Depression": (-90, -80),
                "1987 crash": (-40, -28),
                "2000-02 dot-com bear market": (-55, -44),
                "2007-09 Global Financial Crisis": (-60, -50),
                "COVID crash 2020": (-38, -30)}
        got = {e["episode"]: e["deepestEquityDrawdownPct"] for e in self.d["namedEpisodes"]}
        for name, (lo, hi) in want.items():
            self.assertIn(name, got, name)
            self.assertIsNotNone(got[name], name)
            self.assertTrue(lo <= got[name] <= hi, f"{name}: {got[name]} not in [{lo}, {hi}]")

    def test_pre_2018_episodes_are_not_claimed_as_training_data(self):
        for e in self.d["namedEpisodes"]:
            if e["window"][1] < self.d["trainingDataStarts"]:
                self.assertFalse(e["inTrainingData"], e["episode"])

    def test_a_series_too_young_for_an_episode_says_so(self):
        for e in self.d["namedEpisodes"]:
            for sym, v in e["perSeries"].items():
                self.assertIn(v["status"], ("MEASURED", "SERIES_STARTS_AFTER_EPISODE",
                                            "NO_OBSERVATIONS_IN_WINDOW"), f"{e['episode']} {sym}")


class Crisis2008(unittest.TestCase):
    def setUp(self):
        p = CRISIS / "manifest.json"
        if not p.exists():
            self.skipTest("crisis_2008 package not generated")
        self.m = json.loads(p.read_text(encoding="utf-8"))

    def test_the_package_does_not_claim_to_be_training_data(self):
        self.assertIn("NOT training data", self.m["purpose"])
        self.assertIn("2018", self.m["trainingStatus"])

    def test_every_series_file_matches_its_recorded_checksum(self):
        import hashlib

        for sid, v in self.m["macroAndBankingSeries"].items():
            if v.get("status") != "COMPLETE":
                continue
            p = CRISIS / f"{sid}.csv"
            self.assertTrue(p.exists(), sid)
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), v["sha256"], sid)

    def test_the_crisis_is_actually_in_the_numbers(self):
        def series(name):
            with (CRISIS / name).open(encoding="utf-8") as fh:
                return [(r["observation_date"], float(r["value"])) for r in csv.DictReader(fh)]

        unrate = series("UNRATE.csv")
        self.assertGreaterEqual(max(v for _, v in unrate), 9.5)
        ted = series("TEDRATE.csv")
        peak = max(ted, key=lambda x: x[1])
        self.assertGreater(peak[1], 3.0)
        self.assertTrue(peak[0].startswith("2008"), peak)

    def test_an_ex_post_label_is_flagged_as_one(self):
        usrec = self.m["macroAndBankingSeries"]["USREC"]
        self.assertFalse(usrec["pointInTimeReady"])
        self.assertIn("never be a feature", usrec["pitNote"])

    def test_the_licence_gap_is_recorded_rather_than_filled(self):
        self.assertIn("BAMLH0A0HYM2", self.m["licenseBlocked"])

    def test_the_chronology_says_what_each_date_means(self):
        c = json.loads((CRISIS / "chronology.json").read_text(encoding="utf-8"))
        kinds = {e["dateMeans"] for e in c["entries"]}
        self.assertTrue(kinds <= {"announcement", "effective", "filing", "market observation",
                                  "retrospective description"}, kinds)
        self.assertIn("retrospective description", kinds)
        for e in c["entries"]:
            self.assertTrue(e["source"], e["event"])


class SourceInventory(unittest.TestCase):
    def setUp(self):
        if not INV.exists():
            self.skipTest("source_inventory.json not generated")
        self.d = json.loads(INV.read_text(encoding="utf-8"))

    def test_every_layer_has_a_valid_status_and_all_three_answers(self):
        for x in self.d["layers"]:
            self.assertIn(x["status"], VALID_STATUS, x["layer"])
            for k in ("downloaded", "validated", "joinedIntoTraining"):
                self.assertIn(k, x, f"{x['layer']} missing {k}")

    def test_a_blocked_layer_is_not_also_claimed_as_downloaded(self):
        for x in self.d["layers"]:
            if x["status"] in ("SOURCE_BLOCKED", "LICENSE_BLOCKED", "MISSING"):
                self.assertFalse(x["downloaded"], x["layer"])
                self.assertFalse(x["joinedIntoTraining"], x["layer"])

    def test_nothing_is_joined_without_being_validated(self):
        for x in self.d["layers"]:
            if x["joinedIntoTraining"]:
                self.assertTrue(x["validated"], x["layer"])
                self.assertTrue(x["downloaded"], x["layer"])

    def test_the_counts_add_up(self):
        self.assertEqual(sum(self.d["summary"]["byStatus"].values()), len(self.d["layers"]))


if __name__ == "__main__":
    unittest.main()
