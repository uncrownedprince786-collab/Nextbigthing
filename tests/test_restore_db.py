"""What the restore has to keep true, in the parts that need no database.

The end-to-end rehearsal runs against a disposable Postgres and is documented in
tools/README.md. What is held here is the reasoning the rehearsal cannot cover on its own: that a
record is split the way Postgres wrote it, that an SQL NULL never becomes an empty string on the
way back, and that the target checks refuse before anything can be written.
"""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools"))

import restore_db  # noqa: E402

NEON = "postgresql://u:p@ep-x-pooler.us-east-2.aws.neon.tech/neondb"
SUPA = "postgresql://postgres.abc:p@aws-0-x.pooler.supabase.com:5432/postgres"
LOCAL = "postgresql://postgres:p@127.0.0.1:55434/nbt_rehearsal"


def records(blob: bytes) -> list[bytes]:
    return list(restore_db.csv_records(io.BytesIO(blob)))


class SplittingRecords(unittest.TestCase):
    def test_a_plain_row_is_one_record(self):
        self.assertEqual(records(b"a,b,c\n1,2,3\n"), [b"a,b,c", b"1,2,3"])

    def test_a_newline_inside_quotes_does_not_end_the_record(self):
        # COPY ... TO STDOUT (FORMAT csv) writes an embedded newline raw, inside quotes. Splitting
        # on b"\n" would cut this row in half and compare the halves to nothing.
        self.assertEqual(records(b'1,"two\nlines",3\n'), [b'1,"two\nlines",3'])

    def test_carriage_returns_are_not_kept(self):
        self.assertEqual(records(b"a,b\r\n1,2\r\n"), [b"a,b", b"1,2"])

    def test_a_final_record_without_a_newline_still_arrives(self):
        self.assertEqual(records(b"a,b\n1,2"), [b"a,b", b"1,2"])

    def test_a_doubled_quote_inside_a_field_is_carried_through(self):
        self.assertEqual(records(b'1,"say ""hi""",3\n'), [b'1,"say ""hi""",3'])


class NullIsNotAnEmptyString(unittest.TestCase):
    """The reason this file never parses a value into Python.

    Postgres writes an SQL NULL as an unquoted empty field and an empty string as `""`. Both decode
    to `''` through csv.reader, so a parsed comparison would call a restore correct that had turned
    every NULL into an empty string.
    """

    def test_the_two_are_different_bytes_and_different_digests(self):
        as_null = records(b"1,,3\n")
        as_empty = records(b'1,"",3\n')
        self.assertNotEqual(as_null, as_empty)
        self.assertNotEqual(
            restore_db.content_digest(iter(as_null)),
            restore_db.content_digest(iter(as_empty)),
        )


class TheContentDigest(unittest.TestCase):
    def test_it_does_not_depend_on_row_order(self):
        # COPY has no ORDER BY, so a restored table may hand its rows back in another order while
        # holding exactly the same rows.
        a = restore_db.content_digest(iter([b"1,x", b"2,y", b"3,z"]))
        b = restore_db.content_digest(iter([b"3,z", b"1,x", b"2,y"]))
        self.assertEqual(a, b)

    def test_it_notices_one_changed_row(self):
        a = restore_db.content_digest(iter([b"1,x", b"2,y"]))
        b = restore_db.content_digest(iter([b"1,x", b"2,Y"]))
        self.assertNotEqual(a, b)

    def test_it_notices_a_missing_row(self):
        a = restore_db.content_digest(iter([b"1,x", b"2,y"]))
        b = restore_db.content_digest(iter([b"1,x"]))
        self.assertNotEqual(a, b)

    def test_a_duplicated_row_is_not_mistaken_for_the_original(self):
        # Two identical rows XOR back to the empty digest, so the count is carried beside it.
        self.assertEqual(restore_db.content_digest(iter([b"1,x", b"1,x"]))[0], 2)
        self.assertNotEqual(
            restore_db.content_digest(iter([b"1,x", b"1,x"])),
            restore_db.content_digest(iter([])),
        )


class ChoosingTheTarget(unittest.TestCase):
    def refuses(self, env, fragment, allow_remote=False):
        with mock.patch.dict(restore_db.os.environ, env, clear=True):
            with self.assertRaises(SystemExit) as raised:
                restore_db.target_url(allow_remote)
        self.assertIn(fragment, str(raised.exception))

    def test_an_unset_target_is_refused(self):
        self.refuses({"DATABASE_URL": NEON}, "RESTORE_DATABASE_URL is not set")

    def test_it_never_falls_back_to_the_application_database(self):
        # The whole point: no value for the target must ever resolve to the primary.
        self.refuses({"DATABASE_URL": NEON, "SUPABASE_DATABASE_URL": SUPA}, "is not set")

    def test_the_primary_as_a_target_is_refused(self):
        self.refuses(
            {"DATABASE_URL": NEON, "SUPABASE_DATABASE_URL": SUPA, "RESTORE_DATABASE_URL": SUPA},
            "same database as SUPABASE_DATABASE_URL",
        )

    def test_a_standby_as_a_target_is_refused(self):
        self.refuses(
            {"DATABASE_URL": NEON, "SUPABASE_DATABASE_URL": SUPA, "RESTORE_DATABASE_URL": NEON},
            "same database as",
        )

    def test_the_pooled_and_direct_endpoints_of_one_database_are_the_same_database(self):
        direct = NEON.replace("-pooler", "")
        self.refuses(
            {"DATABASE_URL": NEON, "RESTORE_DATABASE_URL": direct},
            "same database as DATABASE_URL",
        )

    def test_a_remote_target_needs_saying_so(self):
        self.refuses(
            {"DATABASE_URL": LOCAL, "RESTORE_DATABASE_URL": "postgresql://u:p@db.example.com/x"},
            "not this machine",
        )

    def test_a_local_target_that_is_nothing_else_is_accepted(self):
        env = {"DATABASE_URL": NEON, "SUPABASE_DATABASE_URL": SUPA, "RESTORE_DATABASE_URL": LOCAL}
        with mock.patch.dict(restore_db.os.environ, env, clear=True):
            self.assertEqual(restore_db.target_url(False), LOCAL)


class WhatIsNotRestored(unittest.TestCase):
    def test_prisma_bookkeeping_is_left_to_the_migration(self):
        # The target is migrated before a restore, which fills this table by applying the same
        # history. Writing the backup's copy on top of it would duplicate every row.
        self.assertEqual(restore_db.MIGRATION_TABLE, "_prisma_migrations")


class NothingIsPrinted(unittest.TestCase):
    def test_a_connection_string_never_reaches_the_output(self):
        shown = restore_db.where(SUPA)
        self.assertNotIn("p@", shown)
        self.assertNotIn("postgres.abc", shown)
        self.assertEqual(shown, "aws-0-x.pooler.supabase.com:5432/postgres")

    def test_something_that_is_not_a_url_is_not_echoed(self):
        self.assertEqual(restore_db.where("not a url at all secret"), "<unreadable>")


if __name__ == "__main__":
    unittest.main()
