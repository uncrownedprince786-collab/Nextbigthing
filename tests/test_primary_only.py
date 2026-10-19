"""Prediction recording and grading must never silently fall back to a standby.

The failure this guards against is not a crash, it is a green run. A standby's copy of the shadow
tables lags the primary -- measured 2026-10-19, 599 rows on the primary against 581 on Aiven, the
18 missing ones including every 5-session prediction due to mature on 2026-10-23. A scorer that
failed over would have found none of them eligible and reported `nothing-matured`.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

import psycopg  # noqa: E402

import nbt  # noqa: E402


class PrimaryOnlyTest(unittest.TestCase):
    def test_a_reachable_primary_is_used_and_is_never_the_standby(self):
        with mock.patch.object(nbt, "primary_choice", return_value=("SUPABASE_DATABASE_URL", "postgres://p/db")), \
             mock.patch.object(nbt, "_connect", return_value=SimpleNamespace(tag="primary")) as c:
            conn = nbt.primary_db()
        self.assertEqual(conn.tag, "primary")
        self.assertEqual(c.call_args.args[0], "postgres://p/db")
        self.assertEqual(nbt.WRITING_TO, "primary")

    def test_a_full_pooler_is_retried_then_raised_and_never_failed_over(self):
        """The exact production condition: EMAXCONNSESSION from Supavisor."""
        err = psycopg.OperationalError(
            "connection failed: FATAL: (EMAXCONNSESSION) max clients reached in session mode")
        with mock.patch.object(nbt, "primary_choice", return_value=("SUPABASE_DATABASE_URL", "postgres://p/db")), \
             mock.patch.object(nbt, "_connect", side_effect=err) as c, \
             mock.patch.object(nbt.time, "sleep") as slept, \
             mock.patch.object(nbt, "standby_url") as standby:
            with self.assertRaises(RuntimeError) as raised:
                nbt.primary_db(retries=3, pause=0.0)
        self.assertEqual(c.call_count, 3, "it retries before giving up")
        self.assertEqual(slept.call_count, 2, "it pauses between attempts, not after the last")
        standby.assert_not_called()
        self.assertIn("must not fall back to a standby", str(raised.exception))

    def test_it_recovers_when_a_retry_succeeds(self):
        err = psycopg.OperationalError("max clients reached in session mode")
        with mock.patch.object(nbt, "primary_choice", return_value=("SUPABASE_DATABASE_URL", "postgres://p/db")), \
             mock.patch.object(nbt, "_connect", side_effect=[err, SimpleNamespace(tag="primary")]), \
             mock.patch.object(nbt.time, "sleep"):
            conn = nbt.primary_db(retries=3, pause=0.0)
        self.assertEqual(conn.tag, "primary")

    def test_a_credential_fault_is_raised_at_once_and_not_waited_on(self):
        """A wrong password is not a transient pooler; retrying it three times helps nobody."""
        err = psycopg.OperationalError("password authentication failed for user")
        with mock.patch.object(nbt, "primary_choice", return_value=("SUPABASE_DATABASE_URL", "postgres://p/db")), \
             mock.patch.object(nbt, "_connect", side_effect=err) as c, \
             mock.patch.object(nbt.time, "sleep") as slept:
            with self.assertRaises(psycopg.OperationalError):
                nbt.primary_db(retries=3, pause=0.0)
        self.assertEqual(c.call_count, 1)
        slept.assert_not_called()

    def test_no_primary_configured_names_the_variable(self):
        with mock.patch.object(nbt, "primary_choice", return_value=("SUPABASE_DATABASE_URL", "")):
            with self.assertRaises(KeyError):
                nbt.primary_db()

    def test_db_still_fails_over_for_the_lanes_that_want_it(self):
        """`primary_db` is an addition. The ingest lanes keep the behaviour they were built on."""
        err = psycopg.OperationalError("max clients reached in session mode")
        with mock.patch.object(nbt, "primary_choice", return_value=("SUPABASE_DATABASE_URL", "postgres://p/db")), \
             mock.patch.object(nbt, "_connect", side_effect=[err, SimpleNamespace(tag="standby")]), \
             mock.patch.object(nbt, "standby_url", return_value=("DATABASE_URL_FALLBACK", "postgres://s/db")):
            conn = nbt.db()
        self.assertEqual(conn.tag, "standby")


class TheShadowToolsUsePrimaryOnlyTest(unittest.TestCase):
    """Read as source, because importing them pulls in numpy and a model artifact."""

    def test_the_writer_the_scorer_and_the_live_read_all_ask_for_primary_db(self):
        for rel, needle in (
            ("tools/research/shadow_predict.py", "from nbt import primary_db"),
            ("tools/research/shadow_score.py", "from nbt import primary_db as _db"),
        ):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(needle, src, rel)

    def test_no_shadow_tool_still_imports_the_failing_over_db(self):
        for rel in ("tools/research/shadow_predict.py", "tools/research/shadow_score.py"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("from nbt import db\n", src, rel)
            self.assertNotIn("from nbt import db as _db", src, rel)


if __name__ == "__main__":
    unittest.main()
