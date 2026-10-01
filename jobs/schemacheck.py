"""Refuse to run data jobs against a database whose schema is behind the code.

Why this exists instead of a second `prisma migrate deploy`
-----------------------------------------------------------
`refresh.yml` used to apply migrations itself. Its comment said the schema was migrated
"here and nowhere else", and that stopped being true when `schema.yml` took the job — so on
any push that touched `refresh.yml`, two workflows in two different concurrency groups ran
`prisma migrate deploy` against one database in the same second. Nothing serialised them,
the schema run won, and the refresh run died at the migration with its data jobs skipped.
That is the failure recorded in run 36798989654.

Deleting the step fixes the race and reintroduces the hazard it was there for: a data job
cannot write a table that does not exist. So the refresh lane now *checks* rather than
migrates. The check holds no writer privilege, issues no DDL, needs no Node, and cannot
race anything, because comparing two lists is not a write.

Migration is one controlled path: `schema.yml`, and nowhere else.

What it compares
----------------
The migration directories in `prisma/migrations/` against the rows in
`_prisma_migrations`. A directory with no applied row means the deploy has not reached this
database yet, and the right thing is to stop with that said plainly rather than to run
fourteen jobs that will each fail on a missing relation.

A row in the database that the repository does not have is the opposite case — the database
is *ahead*, which happens when a scheduled run on an older checkout meets a database a newer
release has already migrated. That is reported and allowed: every job here writes through
`ON CONFLICT`, and an extra table nothing reads is harmless.

Exit codes
    0  the database has every migration this checkout knows about
    1  the database is behind, and the pending migration names are printed
    2  the check itself could not run, which is not the same answer as "behind"

Run: python jobs/schemacheck.py
Reads: _prisma_migrations
Writes: nothing
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

MIGRATIONS = Path(__file__).resolve().parent.parent / "prisma" / "migrations"


def on_disk(folder: Path) -> list[str]:
    """Migration names this checkout holds, in the order Prisma would apply them.

    Prisma names its folders with a sortable timestamp prefix, so lexical order is apply
    order. `migration_lock.toml` is not a migration and is skipped by the directory test
    rather than by name, so a future lock file cannot be mistaken for one.
    """
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_dir())


def pending(have: list[str], applied: set[str]) -> list[str]:
    """Migrations this checkout has that the database has not finished applying."""
    return [name for name in have if name not in applied]


def extra(have: list[str], applied: set[str]) -> list[str]:
    """Migrations the database has applied that this checkout does not contain."""
    return sorted(applied - set(have))


def main() -> None:
    have = on_disk(MIGRATIONS)
    if not have:
        print("  no migration directories found, so there is nothing to check against")
        print("  this is a broken checkout rather than a healthy database")
        raise SystemExit(2)

    step(f"check the database has all {len(have)} migrations this checkout knows about")

    try:
        conn = db()
    except Exception as e:  # noqa: BLE001 - a connection failure is not a schema answer
        print(f"  could not connect: {type(e).__name__}")
        print("  this says nothing about the schema, so it exits 2 rather than 1")
        raise SystemExit(2) from e

    cur = conn.cursor()
    try:
        # finished_at IS NULL is a migration that started and did not complete. Treating it
        # as applied would let the jobs run against a half-made schema.
        got = rows(
            cur,
            """
            SELECT migration_name FROM _prisma_migrations
            WHERE finished_at IS NOT NULL AND rolled_back_at IS NULL
            """,
        )
    except Exception as e:  # noqa: BLE001
        print(f"  could not read _prisma_migrations: {type(e).__name__}")
        print("  the database may never have been migrated at all")
        cur.close()
        conn.close()
        raise SystemExit(2) from e

    applied = {r["migration_name"] for r in got}
    missing = pending(have, applied)
    ahead = extra(have, applied)

    print(f"  {len(have)} in this checkout, {len(applied)} applied and finished")
    if ahead:
        # Not a failure. A scheduled run on an older checkout is allowed to use a database a
        # newer release has already migrated: every write here is an upsert, and a table
        # nothing reads is inert.
        print(f"  the database is ahead by {len(ahead)}, which is allowed:")
        for name in ahead:
            print(f"    {name}")

    cur.close()
    conn.close()

    if missing:
        print(f"  the database is BEHIND by {len(missing)}:")
        for name in missing:
            print(f"    {name}")
        print("  refusing to run data jobs against it. A job cannot write a table that is")
        print("  not there, and fourteen jobs each failing on a missing relation is a worse")
        print("  log than one line saying the deploy has not landed.")
        print("  schema.yml owns migration. Push to main, or dispatch it, and retry.")
        raise SystemExit(1)

    print("  the schema is current, so the data jobs can run")


if __name__ == "__main__":
    main()
