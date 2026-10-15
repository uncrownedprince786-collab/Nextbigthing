"""The historical research corpus: its dispositions, and that retention cannot delete it.

Dataset gates read committed artifacts and skip when one is absent, never pass.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "jobs"))

DATA = ROOT / "data" / "foundation" / "events"
MANIFEST = DATA / "press_evidence_manifest.json"
JSONL = DATA / "press_evidence.jsonl"

VALID = {"PRESS_EVIDENCE_FOUND", "OFFICIAL_SOURCE_ONLY", "SEARCHED_NO_MATCH",
         "SOURCE_LIMITED", "PENDING"}


class RetentionCannotTouchTheCorpus(unittest.TestCase):
    """Operational news freshness and historical research retention stay separate concerns."""

    def test_the_event_tables_are_never_pruned(self):
        import retention

        for table in ("Event", "EventLink", "EventImpact", "EventState"):
            self.assertIn(table, retention.NEVER_PRUNED, table)

    def test_retention_touches_no_foundation_artifact(self):
        src = (ROOT / "jobs" / "retention.py").read_text(encoding="utf-8")
        for needle in ("data/foundation", "press_evidence", ".jsonl"):
            self.assertNotIn(needle, src, needle)

    def test_the_corpus_is_not_stored_in_the_pruned_news_table(self):
        # If a future change writes press evidence into News, retention's 70-day rule would
        # delete the research corpus. The collectors must stay file-based.
        for tool in ("gdelt_evidence.py", "gkg_evidence.py", "evidence_dispositions.py"):
            src = (ROOT / "tools" / "foundation" / tool).read_text(encoding="utf-8")
            self.assertNotIn('INSERT INTO "News"', src, tool)


class Dispositions(unittest.TestCase):
    def setUp(self):
        if not MANIFEST.exists():
            self.skipTest("press_evidence_manifest.json not generated")
        self.m = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_every_event_has_exactly_one_valid_disposition(self):
        seen = set()
        for d in self.m["dispositions"]:
            self.assertIn(d["disposition"], VALID, d["name"])
            self.assertNotIn(d["eventId"], seen, "duplicate event id")
            seen.add(d["eventId"])
        self.assertEqual(len(seen), self.m["events"])

    def test_the_counts_add_up_to_the_corpus(self):
        self.assertEqual(sum(self.m["dispositionCounts"].values()), self.m["events"])

    def test_press_coverage_is_not_overstated(self):
        # The number of events with a disposition is not the number with evidence.
        found = self.m["dispositionCounts"].get("PRESS_EVIDENCE_FOUND", 0)
        self.assertEqual(found, self.m["eventsWithPressEvidence"])
        self.assertLessEqual(found, self.m["events"])

    def test_every_route_outcome_is_recorded_per_event(self):
        for d in self.m["dispositions"]:
            self.assertTrue(d["routes"], d["name"])
            for route, outcome in d["routes"].items():
                self.assertTrue(outcome, f"{d['name']} {route}")

    def test_a_found_event_actually_has_references(self):
        for d in self.m["dispositions"]:
            if d["disposition"] == "PRESS_EVIDENCE_FOUND":
                self.assertGreater(d["pressReferences"], 0, d["name"])


class ReferenceRecords(unittest.TestCase):
    def setUp(self):
        if not JSONL.exists():
            self.skipTest("press_evidence.jsonl not generated")
        self.rows = [json.loads(x) for x in JSONL.read_text(encoding="utf-8").splitlines() if x]

    def test_the_file_is_valid_jsonl_and_matches_its_checksum(self):
        import hashlib

        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(JSONL.read_bytes()).hexdigest(), m["sha256"])
        self.assertEqual(len(self.rows), m["pressReferenceRecords"])

    def test_no_record_claims_the_article_text_was_read(self):
        for r in self.rows:
            self.assertIn("reference only", r["accessStatus"])

    def test_every_record_carries_provenance_and_a_real_link(self):
        for r in self.rows:
            self.assertTrue(r["url"].startswith("http"), r["url"][:40])
            self.assertTrue(r["eventId"] and r["eventDate"] and r["retrievedAt"])
            self.assertIn(r["route"], ("gdelt-doc-api", "gdelt-gkg-archive"))

    def test_records_are_deduplicated(self):
        keys = [(r["eventId"], r["dedupeKey"]) for r in self.rows]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
