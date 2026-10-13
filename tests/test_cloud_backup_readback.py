"""`read_back` has to give the same answer the whole-file version gave, without holding the file.

Decompressing a table into one bytes and decoding it to one str peaked this process at 546 MB on
`PriceSnapshot` alone -- 24 MB on disk, 102 MB decompressed. That is the ceiling of the backup lane
and of any restore that verifies first, and it grows with the table. The chunked version is flat, so
what these hold is that it still counts and hashes exactly what the old one did, including the cases
where a naive line count would be wrong.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools"))

import cloud_backup  # noqa: E402


def the_old_way(raw: bytes) -> tuple[list[str], int, str]:
    """What the function did before: the whole file in memory, counted by csv.reader."""
    reader = csv.reader(io.StringIO(raw.decode("utf-8")))
    header = next(reader, [])
    return header, sum(1 for _ in reader), hashlib.sha256(raw).hexdigest()


class ReadBackMatchesTheWholeFileVersion(unittest.TestCase):
    def both(self, raw: bytes):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.csv.gz"
            with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as gz:
                gz.write(raw)
            return the_old_way(raw), cloud_backup.read_back(path)

    def test_a_plain_table(self):
        old, new = self.both(b"id,name\n1,a\n2,b\n3,c\n")
        self.assertEqual(old, new)
        self.assertEqual(new[1], 3)

    def test_an_empty_table_is_header_only(self):
        old, new = self.both(b"id,name\n")
        self.assertEqual(old, new)
        self.assertEqual(new[1], 0)

    def test_a_newline_inside_quotes_is_not_a_row(self):
        # The case a naive count of b"\n" gets wrong: one record, two newlines in the file.
        old, new = self.both(b'id,note\n1,"two\nlines"\n')
        self.assertEqual(old, new)
        self.assertEqual(new[1], 1)

    def test_several_newlines_inside_one_field(self):
        old, new = self.both(b'id,note\n1,"a\nb\nc\nd"\n2,plain\n')
        self.assertEqual(old, new)
        self.assertEqual(new[1], 2)

    def test_a_doubled_quote_does_not_unbalance_the_parity(self):
        # "" is an escaped quote inside a quoted field: the state flips twice and stays inside.
        old, new = self.both(b'id,note\n1,"say ""hi"" now"\n2,"x\ny"\n')
        self.assertEqual(old, new)
        self.assertEqual(new[1], 2)

    def test_null_and_empty_string_are_both_carried(self):
        old, new = self.both(b'id,a,b\n1,,""\n')
        self.assertEqual(old, new)

    def test_unicode_survives_the_chunking(self):
        raw = "id,note\n1,日本語 éàü\n".encode("utf-8")
        old, new = self.both(raw)
        self.assertEqual(old, new)

    def test_quoted_newlines_keep_counting_across_chunk_boundaries(self):
        # The reader works in 1 MiB chunks and carries the quote state between them. This writes
        # well over one chunk with a quoted newline every hundredth row, so the parity has to
        # survive many boundaries rather than one contrived field.
        rows, quoted = [], 0
        for i in range(40_000):
            if i % 100 == 0:
                rows.append(b'%d,"a\nb"\n' % i)
                quoted += 1
            else:
                rows.append(b"%d,plain-row-with-some-length\n" % i)
        raw = b"id,note\n" + b"".join(rows)
        self.assertGreater(len(raw), 1 << 20, "the fixture has to cross a chunk boundary")
        old, new = self.both(raw)
        self.assertEqual(old, new)
        self.assertEqual(new[1], 40_000)
        self.assertGreater(quoted, 100)

    def test_the_header_is_parsed_not_split(self):
        header, rows, _ = cloud_backup.read_back(self.written(b'"id","a,b",c\n1,2,3\n'))
        self.assertEqual(header, ["id", "a,b", "c"])
        self.assertEqual(rows, 1)

    def written(self, raw: bytes) -> Path:
        d = tempfile.mkdtemp()
        path = Path(d) / "t.csv.gz"
        with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as gz:
            gz.write(raw)
        return path


class ItDoesNotHoldTheFile(unittest.TestCase):
    def test_a_file_larger_than_the_chunk_is_read_in_pieces(self):
        # Not a memory assertion -- that is measured in tools/README.md -- but it does prove the
        # reader never needs the whole file to answer, by handing it one bigger than its chunk.
        body = b"".join(b"%d,row\n" % i for i in range(200_000))
        path = self.pathfor(b"id,name\n" + body)
        header, rows, sha = cloud_backup.read_back(path)
        self.assertEqual(header, ["id", "name"])
        self.assertEqual(rows, 200_000)
        self.assertEqual(sha, hashlib.sha256(b"id,name\n" + body).hexdigest())

    def pathfor(self, raw: bytes) -> Path:
        d = tempfile.mkdtemp()
        path = Path(d) / "big.csv.gz"
        with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as gz:
            gz.write(raw)
        return path


if __name__ == "__main__":
    unittest.main()
