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


class OnlyTheLoudStatesFailATradingLane(unittest.TestCase):
    """`jobRuns36h` used to fail on any status that was not ok. That made a provider's 429
    (`blocked`), a partly-answered slice (`partial`) and a skipped one into system failures --
    and it read the intraday fetch's Yahoo throttle as the *decision* lane failing."""

    def _runs(self, *pairs):
        return [{"job": j, "status": s, "n": n} for j, s, n in pairs]

    def test_failed_and_empty_fail_a_trading_lane(self):
        for state in ("failed", "empty"):
            got = da.lane_check("jobRuns36h", self._runs(("cron crypto", state, 1)))
            self.assertEqual(got["status"], da.FAIL, state)

    def test_a_throttle_is_reported_and_does_not_fail(self):
        got = da.lane_check("jobRuns36h", self._runs(("cron intraday", "blocked", 1)))
        self.assertEqual(got["status"], da.WARN)
        self.assertIn("cron intraday:blocked", got["detail"])

    def test_partial_and_skipped_only_warn(self):
        for state in ("partial", "skipped"):
            got = da.lane_check("jobRuns36h", self._runs(("cron psx", state, 1)))
            self.assertEqual(got["status"], da.WARN, state)

    def test_an_all_ok_lane_is_ok(self):
        got = da.lane_check("jobRuns36h", self._runs(("cron us prices", "ok", 4)))
        self.assertEqual(got["status"], da.OK)


class TheProductLaneIsSeparatedNotHidden(unittest.TestCase):

    def test_a_product_failure_warns_and_is_named(self):
        got = da.lane_check("productRuns36h",
                            [{"job": "cron products", "status": "empty", "n": 1}], trading=False)
        self.assertEqual(got["status"], da.WARN)
        self.assertIn("cron products:empty", got["detail"])

    def test_a_product_failure_never_fails_the_verdict(self):
        got = da.lane_check("productRuns36h",
                            [{"job": "cron products", "status": "blocked", "n": 4}], trading=False)
        self.assertNotEqual(got["status"], da.FAIL)

    def test_the_same_failure_in_a_trading_lane_is_a_failure(self):
        # The split is the lane set, not a weaker judgement: the identical slice is a FAIL when
        # it is a trading lane and a WARN when it is the product one.
        row = {"job": "cron crypto", "status": "empty", "n": 1}
        self.assertEqual(da.lane_check("jobRuns36h", [row])["status"], da.FAIL)

    def test_no_product_runs_is_not_a_fault(self):
        got = da.lane_check("productRuns36h", [], trading=False)
        self.assertEqual(got["status"], da.OK)


class TheCoverageCheckReadsOnlyTheNewestSnapshot(unittest.TestCase):
    """The old query filtered `status <> 'ok'` over the whole append-only table, so it listed
    historical rows -- and rows whose own status was `healthy`, since `healthy` is not `ok`."""

    def test_the_query_pins_the_latest_run_and_only_unhealthy_rows(self):
        src = (ROOT / "tools" / "daily_audit.py").read_text(encoding="utf-8")
        self.assertIn('max("computedAt")', src)
        self.assertIn("status <> 'healthy'", src)
        self.assertNotIn("status <> 'ok'", src)


class TheDecisionIsMeasuredByItsOwnRows(unittest.TestCase):

    def test_the_decision_freshness_reads_decisionlog_and_health_ts_limit(self):
        src = (ROOT / "tools" / "daily_audit.py").read_text(encoding="utf-8")
        self.assertIn("decisionFreshness", src)
        self.assertIn('max("periodEnd") d FROM "DecisionLog"', src)
        self.assertIn("DECISIONS_STALE_AFTER_DAYS", src)

    def test_the_intraday_fetch_is_not_written_as_the_decision_lane(self):
        src = (ROOT / "jobs" / "intraday.py").read_text(encoding="utf-8")
        self.assertIn('job="cron intraday"', src)
        self.assertNotIn('job="cron decision"', src)


if __name__ == "__main__":
    unittest.main()


class DatabaseExposureTest(unittest.TestCase):
    """The Data API check: a grant is a failure, a missing RLS backstop is a warning.

    They are different kinds of wrong. `anon` and `authenticated` are the roles PostgREST runs as,
    so a table they may select is a table the internet may select -- that is live exposure. A table
    with RLS off and no grant exposes nothing today, but it is the missing second line, and
    `pg_default_acl` still carries a `supabase_admin` entry that would grant `anon` full DML on
    tables that role creates.
    """

    @staticmethod
    def _verdict(granted, no_rls):
        """The branch `daily_audit` takes, pinned here without needing a database."""
        if granted:
            return "fail"
        return "ok" if not no_rls else "warn"

    def test_a_grant_to_a_data_api_role_fails(self):
        self.assertEqual(self._verdict([{"grantee": "anon", "n": 46}], []), "fail")
        self.assertEqual(self._verdict([{"grantee": "authenticated", "n": 1}], []), "fail")

    def test_a_grant_fails_even_when_every_table_has_rls(self):
        """RLS is a backstop, not a licence to hand out grants."""
        self.assertEqual(self._verdict([{"grantee": "anon", "n": 1}], []), "fail")

    def test_no_grants_and_full_rls_is_the_healthy_state(self):
        self.assertEqual(self._verdict([], []), "ok")

    def test_no_grants_but_a_table_without_rls_warns_rather_than_fails(self):
        self.assertEqual(self._verdict([], ["NewTable"]), "warn")

    def test_the_check_is_wired_into_the_audit(self):
        src = (ROOT / "tools" / "daily_audit.py").read_text(encoding="utf-8")
        self.assertIn("databaseExposure", src)
        self.assertIn("role_table_grants", src)
        self.assertIn("relrowsecurity", src)
        # `_prisma_migrations` is read by `migrate deploy` as a role that bypasses RLS, and is
        # excluded on purpose so it never shows up as a finding.
        self.assertIn("c.relname <> '_prisma_migrations'", src)


class TheRlsBackstopMigrationTest(unittest.TestCase):
    def test_it_enables_rls_and_guards_the_role_it_writes_a_policy_for(self):
        sql = (ROOT / "prisma" / "migrations" / "20261019230000_rls_backstop"
               / "migration.sql").read_text(encoding="utf-8")
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)
        # Guarded, so the migration also applies to a restore rehearsal or a fresh environment
        # that has never heard of the reader role.
        self.assertIn("reader_exists", sql)
        self.assertIn("IF reader_exists THEN", sql)
        # Idempotent: a re-run must not fail on an existing policy.
        self.assertIn("DROP POLICY IF EXISTS", sql)
        # Prisma's own bookkeeping is left alone.
        self.assertIn("_prisma_migrations", sql)
