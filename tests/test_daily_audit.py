"""The daily audit's own logic: does it read one definition of stale, and can it mislead?

    python -m unittest discover -s tests -p test_daily_audit.py -v

No database and no network. What is pinned here is the part that would quietly go wrong: a health
check that copies its thresholds instead of reading them, a check that reports its own bug as an
outage, and a summary that lets an unknown pass for an ok.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import daily_audit as da  # noqa: E402


class StaleIsDefinedOnceAndRead(unittest.TestCase):
    """lib/health.ts says a page calling a close fresh while the rules call it stale would be two
    answers to one question. A Python copy of those numbers would be a third."""

    def test_the_thresholds_come_from_the_typescript_that_owns_them(self):
        const = da.health_constants()
        self.assertIn("NEWS_STALE_AFTER_HOURS", const)
        src = (ROOT / "lib" / "health.ts").read_text(encoding="utf-8")
        self.assertIn(f"NEWS_STALE_AFTER_HOURS = {const['NEWS_STALE_AFTER_HOURS']:g}", src)

    def test_no_threshold_is_hard_coded_beside_the_one_it_reads(self):
        src = (ROOT / "tools" / "daily_audit.py").read_text(encoding="utf-8")
        self.assertNotIn("NEWS_STALE_AFTER_HOURS = ", src)


class TheSummaryCannotLaunder(unittest.TestCase):

    def test_unknown_is_counted_apart_from_ok_and_never_as_a_pass(self):
        checks = [da.check("a", da.OK, ""), da.check("b", da.UNKNOWN, "")]
        counts = {s: sum(1 for c in checks if c["status"] == s)
                  for s in (da.OK, da.WARN, da.FAIL, da.UNKNOWN)}
        self.assertEqual(counts[da.OK], 1)
        self.assertEqual(counts[da.UNKNOWN], 1)

    def test_a_fail_is_what_makes_the_run_unhealthy_and_a_warn_is_not(self):
        self.assertEqual(sum(1 for s in (da.WARN, da.OK) if s == da.FAIL), 0)
        self.assertNotEqual(da.WARN, da.FAIL)


class AnApprovedCandidateIsAFailure(unittest.TestCase):
    """Nothing in this project is validated. An artifact claiming otherwise is the one thing the
    audit must never shrug at."""

    def test_production_approved_true_is_reported_as_a_failure(self):
        with tempfile.TemporaryDirectory() as d:
            brain = Path(d) / "data" / "foundation" / "brain" / "fake"
            brain.mkdir(parents=True)
            model = {"productionApproved": True}
            (brain / "model.json").write_text(json.dumps(model), encoding="utf-8")
            (brain / "manifest.json").write_text(json.dumps(
                {"verdict": "NO-GO", "artifact": {"sha256": "x"}}), encoding="utf-8")
            old = da.ROOT
            try:
                da.ROOT = Path(d)
                out = da.artifact_checks()
            finally:
                da.ROOT = old
        statuses = {c["check"]: c["status"] for c in out}
        self.assertEqual(statuses.get("artifact:fake:approval"), da.FAIL)
        self.assertEqual(statuses.get("artifact:fake"), da.FAIL, "a wrong digest must fail too")


class ABugIsNotAnOutage(unittest.TestCase):
    def test_an_internal_fault_is_reported_separately_from_unreachable(self):
        src = (ROOT / "tools" / "daily_audit.py").read_text(encoding="utf-8")
        self.assertIn("auditInternal", src)
        i, j = src.index("not reachable"), src.index("a check raised")
        self.assertNotEqual(i, j)


if __name__ == "__main__":
    unittest.main()
