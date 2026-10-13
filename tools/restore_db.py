"""Read a cloud_backup artifact back into a database, and prove what landed.

    python tools/restore_db.py plan <dir>       what would be restored, and in what order
    python tools/restore_db.py verify <dir>     the artifact alone: files, checksums, row counts
    python tools/restore_db.py restore <dir>    restore into RESTORE_DATABASE_URL, then read it back

`tools/cloud_backup.py` writes a directory of `<table>.csv.gz` beside a `manifest.json`, each file
produced by `COPY ... TO STDOUT (FORMAT csv, HEADER)` from one `REPEATABLE READ, READ ONLY` snapshot.
brain.md rule 101 called this the recovery path and named this file; until now the file did not
exist, so the backups were verified and unreadable. This reads them back.

Why the CSV is restored byte for byte
-------------------------------------
Postgres CSV writes an SQL NULL as an *unquoted* empty field and an empty string as `""`. Parsing
those into Python collapses both to `''`, so this file never parses a value. It splits the stream
into records at the byte level, honouring quotes, and hands the bytes to `COPY ... FROM STDIN` with
the column list the manifest recorded. What Postgres wrote is what Postgres reads.

What it refuses to do
---------------------
Nothing here writes to a database unless `RESTORE_DATABASE_URL` names one, and it is checked against
every database the environment knows about first. There is no fall back to `DATABASE_URL`: a restore
that silently found the primary is the failure this tool exists to make impossible. The target must
already be migrated to the schema the backup was taken at, and every table it covers must be empty.
Nothing is dropped, truncated or deleted to make a restore fit.

The load is one transaction. A restore that fails leaves a target with nothing in it rather than a
half-filled one that reads like a recovery.
"""

from __future__ import annotations

import gzip
import json
import os
import sys
import urllib.parse
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools"))

from nbt import database_key, primary_choice  # noqa: E402

import cloud_backup  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

# Prisma's own bookkeeping. It is in the backup because it is a public table, and it is never
# restored: the target has to be migrated before a restore, which fills this table with the same
# history by applying it. Writing the backup's copy on top would duplicate every row.
MIGRATION_TABLE = "_prisma_migrations"

# Hosts a rehearsal may write. A restore is the one operation that can overwrite a database, so the
# default is that it may only reach this machine; --allow-remote is deliberately not a thing a
# rehearsal needs.
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", ""}

TARGET_VAR = "RESTORE_DATABASE_URL"
KNOWN_VARS = ("DATABASE_URL", "SUPABASE_DATABASE_URL", "DATABASE_URL_FALLBACK", "DIRECT_DATABASE_URL")


def say(line: str) -> None:
    print(f"restore: {line}", flush=True)


def where(url: str) -> str:
    """Host and database only. A connection string is never printed."""
    try:
        u = urllib.parse.urlsplit(url)
        if not u.hostname:
            return "<unreadable>"
        port = f":{u.port}" if u.port else ""
        return f"{u.hostname}{port}/{(u.path or '').lstrip('/') or '?'}"
    except Exception:  # noqa: BLE001
        return "<unreadable>"


# --- the artifact -------------------------------------------------------------------------------


def read_manifest(directory: Path) -> dict:
    path = directory / "manifest.json"
    if not path.exists():
        raise SystemExit(f"refusing: no manifest.json in {directory}")
    return json.loads(path.read_text(encoding="utf-8"))


def csv_records(stream):
    """Yield one CSV record at a time as raw bytes, quotes honoured, newline stripped.

    A record is not a line: a quoted field may hold newlines, and `COPY ... TO STDOUT (FORMAT csv)`
    writes them unescaped. Splitting on b"\\n" would cut such a row in half and compare halves.
    """
    buf = bytearray()
    in_quotes = False
    quote, cr, lf = 0x22, 0x0D, 0x0A
    while True:
        chunk = stream.read(1 << 16)
        if not chunk:
            break
        for byte in chunk:
            if byte == quote:
                in_quotes = not in_quotes
                buf.append(byte)
            elif byte == lf and not in_quotes:
                if buf and buf[-1] == cr:
                    del buf[-1]
                yield bytes(buf)
                buf.clear()
            else:
                buf.append(byte)
    if buf:
        yield bytes(buf)


def content_digest(records) -> tuple[int, int]:
    """(row count, order-independent digest) over raw record bytes.

    XOR of per-record SHA-256 digests. Order-independent on purpose: `COPY TO STDOUT` has no ORDER
    BY, so a restored table may hand its rows back in a different physical order while holding
    exactly the same rows. Constant memory, which matters for the table with 791,033 rows in it.
    """
    import hashlib

    total = 0
    acc = bytearray(32)
    for record in records:
        digest = hashlib.sha256(record).digest()
        for i in range(32):
            acc[i] ^= digest[i]
        total += 1
    return total, int.from_bytes(acc, "big")


def backup_content(directory: Path, table: str) -> tuple[int, int]:
    """Row count and digest of what the backup holds for one table, header skipped."""
    with gzip.open(directory / f"{table}.csv.gz", "rb") as fh:
        records = csv_records(fh)
        next(records, None)  # the header is not a row
        return content_digest(records)


def backup_header(directory: Path, table: str) -> list[str]:
    """The column names the file actually carries, read from its first record."""
    import csv
    import io

    with gzip.open(directory / f"{table}.csv.gz", "rb") as fh:
        first = next(csv_records(fh), b"")
    return next(csv.reader(io.StringIO(first.decode("utf-8"))), [])


# --- the target ---------------------------------------------------------------------------------


def target_url(allow_remote: bool) -> str:
    """The database to restore into, or a refusal explaining exactly which rule stopped it."""
    url = (os.environ.get(TARGET_VAR) or "").strip()
    if not url:
        raise SystemExit(
            f"refusing: {TARGET_VAR} is not set. A restore never falls back to DATABASE_URL, "
            "because a restore that found the primary on its own is the accident this prevents."
        )

    key = database_key(url)
    primary_var, primary = primary_choice()
    for name in dict.fromkeys((primary_var, *KNOWN_VARS)):
        other = (os.environ.get(name) or "").strip() if name not in (primary_var,) else primary
        if other and database_key(other) == key:
            raise SystemExit(
                f"refusing: {TARGET_VAR} is the same database as {name} ({where(url)}). "
                "A rehearsal never restores over a database something else is using."
            )

    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    local = host in LOCAL_HOSTS or host.endswith(".localhost") or host.endswith(".test")
    if not local and not allow_remote:
        raise SystemExit(
            f"refusing: {TARGET_VAR} points at {host}, which is not this machine. Restoring is the "
            "one operation here that can overwrite a database, so a remote target needs "
            "--allow-remote and a reason to pass it."
        )
    if not local:
        say(f"WARNING: --allow-remote was given; the target is {where(url)}")
    return url


def connect(url: str):
    return psycopg.connect(url, connect_timeout=30)


def target_tables(cur) -> dict[str, list[str]]:
    """Every public table in the target with its column names, from the catalogue, not the manifest."""
    cur.execute(
        """
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name, c.ordinal_position
        """
    )
    out: dict[str, list[str]] = {}
    for table, column in cur.fetchall():
        out.setdefault(table, []).append(column)
    return out


def row_counts(cur) -> dict[str, int]:
    """Exact row count for every public table, in one statement.

    One query rather than one per table: `tests/test_brain.py` ratchets in-loop queries down and
    a restore touches 44 tables, so counting them one at a time is exactly the shape that ratchet
    exists to stop. `query_to_xml` runs the count inside the server and hands all of them back.
    """
    cur.execute(
        """
        SELECT t.table_name,
               (xpath('/row/c/text()',
                      query_to_xml(format('SELECT count(*) AS c FROM public.%I', t.table_name),
                                   false, true, '')))[1]::text::bigint AS n
        FROM information_schema.tables t
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        """
    )
    return {name: int(n) for name, n in cur.fetchall()}


def load_order(cur, tables: list[str]) -> tuple[list[str], list[str]]:
    """Tables sorted so a parent is loaded before its children. Returns (order, cycles).

    Read from `pg_constraint` in the target rather than from the schema file, because the target is
    what the rows have to satisfy. Self-references are not ordering problems: a row pointing at its
    own table is satisfied by the same COPY that inserts it, provided the parent row is in the file.
    """
    cur.execute(
        """
        SELECT con.conrelid::regclass::text AS child, con.confrelid::regclass::text AS parent
        FROM pg_constraint con
        JOIN pg_namespace n ON n.oid = con.connamespace
        WHERE con.contype = 'f' AND n.nspname = 'public'
        """
    )
    wanted = set(tables)

    def plain(name: str) -> str:
        return name.split(".")[-1].strip('"')

    parents: dict[str, set[str]] = {t: set() for t in tables}
    for child, parent in cur.fetchall():
        child, parent = plain(child), plain(parent)
        if child in wanted and parent in wanted and child != parent:
            parents[child].add(parent)

    order: list[str] = []
    placed: set[str] = set()
    remaining = set(tables)
    while remaining:
        ready = sorted(t for t in remaining if parents[t] <= placed)
        if not ready:
            return order, sorted(remaining)
        order += ready
        placed |= set(ready)
        remaining -= set(ready)
    return order, []


# --- checks -------------------------------------------------------------------------------------


def preflight(directory: Path, manifest: dict, cur) -> tuple[list[str], list[str], list[str]]:
    """Everything that must hold before a single row is written. Returns (tables, order, problems)."""
    problems: list[str] = []

    if manifest.get("status") != "verified":
        problems.append(
            f"the manifest says status={manifest.get('status')!r}; only a verified backup is restored"
        )

    in_backup = {t for t in manifest.get("tables", {}) if t != MIGRATION_TABLE}
    present = target_tables(cur)
    in_target = {t for t in present if t != MIGRATION_TABLE}

    missing_here = sorted(in_backup - in_target)
    missing_there = sorted(in_target - in_backup)
    if missing_here:
        problems.append(f"the target has no table for: {', '.join(missing_here)}")
    if missing_there:
        problems.append(
            f"the backup does not cover: {', '.join(missing_there)} -- restoring it would leave "
            "those tables empty while the rest looked complete"
        )

    if MIGRATION_TABLE in present:
        cur.execute(
            sql.SQL("SELECT migration_name FROM {} ORDER BY finished_at DESC NULLS LAST LIMIT 1").format(
                sql.Identifier(MIGRATION_TABLE)
            )
        )
        row = cur.fetchone()
        at = row[0] if row else None
        if at is None:
            problems.append("the target has no applied migrations; prepare the schema first")
        elif manifest.get("schema_version") not in (None, "unknown") and at != manifest["schema_version"]:
            problems.append(
                f"the target is at migration {at!r} and the backup was taken at "
                f"{manifest['schema_version']!r}"
            )
    else:
        problems.append(f"the target has no {MIGRATION_TABLE}; it has not been migrated")

    for table in sorted(in_backup & in_target):
        declared = manifest["tables"][table].get("columns") or []
        actual = present[table]
        if set(declared) != set(actual):
            problems.append(
                f"{table}: columns differ: backup has {len(declared)}, target has {len(actual)}"
            )
            continue
        on_disk = backup_header(directory, table)
        if on_disk != declared:
            problems.append(f"{table}: the file header does not match the manifest columns")

    held = row_counts(cur)
    problems += [
        f"{table}: the target already holds {held[table]:,} rows. Nothing is deleted to make "
        "room; restore into an empty database."
        for table in sorted(in_backup & in_target)
        if held.get(table)
    ]

    tables = sorted(in_backup & in_target)
    order, cycles = load_order(cur, tables)
    if cycles:
        problems.append(
            f"foreign keys form a cycle across {', '.join(cycles)}; no load order satisfies them "
            "and this tool does not disable constraints to get around it"
        )
    return tables, order, problems


# --- the restore --------------------------------------------------------------------------------


def copy_table(cur, directory: Path, table: str, columns: list[str]) -> None:
    """Stream one file into one table, header dropped, columns named explicitly."""
    statement = sql.SQL("COPY {} ({}) FROM STDIN (FORMAT csv)").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    with gzip.open(directory / f"{table}.csv.gz", "rb") as fh:
        records = csv_records(fh)
        next(records, None)  # drop the header; the columns are named above instead
        with cur.copy(statement) as cp:
            for record in records:
                cp.write(record + b"\n")


def readback(cur, table: str, columns: list[str]) -> tuple[int, int]:
    """Row count and digest of what the target now holds, in the backup's column order."""
    statement = sql.SQL("COPY (SELECT {} FROM {}) TO STDOUT (FORMAT csv)").format(
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        sql.Identifier(table),
    )

    class Reader:
        """`csv_records` wants a .read(); psycopg hands its chunks out by iteration."""

        def __init__(self, copy):
            self.chunks = iter(copy)

        def read(self, _n):
            try:
                return bytes(next(self.chunks))
            except StopIteration:
                return b""

    with cur.copy(statement) as cp:
        return content_digest(csv_records(Reader(cp)))


def cmd_plan(directory: Path, allow_remote: bool) -> int:
    manifest = read_manifest(directory)
    print(f"artifact   {directory}")
    print(f"run        {manifest.get('run_id')}  status={manifest.get('status')}")
    print(f"schema     {manifest.get('schema_version')}")
    print(
        f"holds      {len(manifest.get('tables', {}))} tables, "
        f"{manifest.get('row_count', 0):,} rows, {manifest.get('gz_bytes', 0) / 1e6:.1f} MB"
    )
    url = target_url(allow_remote)
    print(f"target     {where(url)}  (from {TARGET_VAR})")
    with connect(url) as conn, conn.cursor() as cur:
        tables, order, problems = preflight(directory, manifest, cur)
    print(f"would load {len(tables)} tables, parents first:")
    print("           " + ", ".join(order[:12]) + (" ..." if len(order) > 12 else ""))
    print(f"skipped    {MIGRATION_TABLE} (the target is migrated, not restored into)")
    if problems:
        print("\nthis artifact would NOT be restored:")
        for p in problems:
            print("   -", p)
        return 1
    print("\nready: every check passed. Nothing has been written.")
    return 0


def cmd_restore(directory: Path, allow_remote: bool) -> int:
    manifest = read_manifest(directory)

    ok, checked, problems = cloud_backup.verify(directory)
    say(f"artifact: {ok} of {checked} files match the manifest")
    if problems:
        for p in problems:
            print("   -", p)
        say("FAILED before touching the target: the artifact does not verify")
        return 1

    url = target_url(allow_remote)
    say(f"target: {where(url)}")
    conn = connect(url)
    try:
        with conn.cursor() as cur:
            tables, order, checks = preflight(directory, manifest, cur)
            if checks:
                for p in checks:
                    print("   -", p)
                say("FAILED: the target is not ready. Nothing was written.")
                return 1

            # One transaction for the whole load. A failure anywhere rolls the lot back, so a
            # target is either empty or complete and never something in between that reads like
            # a recovery.
            say(f"loading {len(order)} tables in one transaction")
            for table in order:
                copy_table(cur, directory, table, manifest["tables"][table]["columns"])

            # Counted once, for every table, while the transaction is still open: a count that
            # disagrees with the manifest rolls the whole load back rather than committing a
            # target that is short a table and looks finished.
            loaded = row_counts(cur)
            short = [
                f"{t}: loaded {loaded.get(t, 0):,}, the backup says {manifest['tables'][t]['rows']:,}"
                for t in order
                if loaded.get(t, 0) != manifest["tables"][t]["rows"]
            ]
            if short:
                conn.rollback()
                for s in short:
                    print("   -", s)
                say("FAILED: row counts disagree with the backup. Rolled back; nothing was kept.")
                return 1
            for table in order:
                print(f"   {table:28} {loaded.get(table, 0):>9,}")
            conn.commit()
            say("committed")

        # Read the target back and compare content, not just counts. This is a different claim
        # from the file checksum above: that one says the file is the file, this one says the
        # database now holds what the file holds.
        say("reading the target back")
        bad: list[str] = []
        total = 0
        with conn.cursor() as cur:
            for table in order:
                columns = manifest["tables"][table]["columns"]
                want_rows, want_digest = backup_content(directory, table)
                got_rows, got_digest = readback(cur, table, columns)
                total += got_rows
                if (got_rows, got_digest) != (want_rows, want_digest):
                    bad.append(
                        f"{table}: restored {got_rows:,} rows digest {got_digest:032x}, "
                        f"backup {want_rows:,} rows digest {want_digest:032x}"
                    )
        if bad:
            for b in bad:
                print("   -", b)
            say("FAILED: the target does not hold what the backup holds")
            return 1

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT contype::text, count(*) FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'public' GROUP BY contype ORDER BY contype
                """
            )
            shape = ", ".join(f"{k}={v}" for k, v in cur.fetchall())
            cur.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
            indexes = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.relkind='S' AND n.nspname='public'"
            )
            sequences = cur.fetchone()[0]
    finally:
        conn.close()

    say(f"constraints {shape}; indexes {indexes}; sequences {sequences}")
    if sequences:
        say(f"NOTE: {sequences} sequences exist and were not advanced; check them before inserting")
    say(f"VERIFIED: {len(order)} tables, {total:,} rows, content digests equal")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("plan", "verify", "restore"):
        print(__doc__)
        return 2
    allow_remote = "--allow-remote" in argv
    rest = [a for a in argv[1:] if not a.startswith("--")]
    if not rest:
        print(f"{argv[0]} needs the path to a backup directory")
        return 2
    directory = Path(rest[0])
    if not directory.is_dir():
        print(f"no such directory: {directory}")
        return 2

    if argv[0] == "verify":
        ok, checked, problems = cloud_backup.verify(directory)
        print(f"{ok} of {checked} files verified")
        for p in problems:
            print("   -", p)
        return 0 if not problems else 1
    if argv[0] == "plan":
        return cmd_plan(directory, allow_remote)
    return cmd_restore(directory, allow_remote)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
