"""Cap the tables that write a row per asset per session, so the database stops growing forever.

The arithmetic nobody had done
------------------------------
Measured 2026-10-08: 339 MB of a 500 MB tier, and 1,934 rows a session arriving at 684 bytes a
row. That is about four months to full at 331 assets, and the pool is meant to grow. Nothing
here was ever deleted except the intraday bars, which `jobs/intraday.py` has swept since it was
written, and the three tables that rewrite themselves in full every run.

So the choice is not whether to prune but what the readers actually need, and the answer is
different for each table. Two groups:

**The memory.** `DecisionLog`, `SignalLog`, `AssetThesis`, `ThesisCheck`, `EventState`,
`Calibration`, `Coverage`, `SourceReliability`, `PriceSnapshot`. These are what the system said
and what followed, and the accuracy loop measures over sixty days and will measure over longer.
Deleting any of them would be deleting the evidence the whole project exists to accumulate.
**Nothing in this file touches them.** `PriceSnapshot` in particular is the permanent record:
every analog, every trend and every target is derived from it.

**The working set.** `AssetSetup`, `AssetAnalog`, `AssetFactor`, `MoveAttribution`,
`Investigation`, `HumanSignal`, `News`. Every reader of these takes the newest row per asset --
`DISTINCT ON ("assetId") ... ORDER BY "periodEnd" DESC` appears in `tools/decide.mjs`,
`lib/queries.ts` and half the jobs. Yesterday's row is read by nothing once today's exists.

Two of them do have a reader that looks back, and the windows below are set by those readers
rather than by taste:

  * `jobs/thesis.py` walks an asset's run of `AssetSetup` rows to find the session a state
    first appeared on. It is the only consumer of that history, and it needs the run, not the
    archive -- the opening day it finds is then copied into `AssetThesis`, which this file
    never prunes, so the record of when a reason began survives the pruning of the rows it was
    derived from.
  * `jobs/lineage.py` clusters `News` over LOOKBACK_DAYS and `jobs/human.py` reads two
    consecutive WINDOW_DAYS windows. The floor here is well clear of both.

Run: python jobs/retention.py [--dry-run] [--reclaim]
Writes: deletes from the working-set tables only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, one, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

# table -> (date column, days kept, why that number)
#
# A window is a measurement of what reads the table, not a preference. Where a reader looks
# back, the window is that reader's own reach with room to spare; where nothing does, it is
# short enough to bound the table and long enough that a lane which fails for a week does not
# come back to an empty history.
KEEP = {
    "AssetSetup": (
        '"periodEnd"', 14,
        "jobs/thesis.py walks the run of these rows to find the session a state first "
        "appeared on, and the opening day it finds is copied into AssetThesis, which is "
        "never pruned. A run that reaches the edge of this window is matched to the thesis "
        "that already holds its real opening day rather than re-opened -- see the note in "
        "thesis.py. This is the largest table of the group at about 1.3 kB a row, so at 470 "
        "assets each extra day of it costs about 1.8 MB of a 500 MB tier",
    ),
    "AssetAnalog": (
        '"periodEnd"', 7,
        "every reader takes the newest row per asset; a week is kept so a lane that failed for a few days still has yesterday to compare against",
    ),
    "AssetFactor": (
        '"periodEnd"', 7,
        "every reader takes the newest row per asset; a week is kept so a lane that failed for a few days still has yesterday to compare against",
    ),
    "MoveAttribution": (
        '"periodEnd"', 7,
        "jobs/investigate.py reads base rates across the table, which 60 days of readings "
        "supports as well as a year of them",
    ),
    "Investigation": (
        '"periodEnd"', 14,
        "its findings and hypotheses cascade with it; the panel reads the newest per asset",
    ),
    "HumanSignal": (
        '"periodEnd"', 7,
        "jobs/setup.py and the panel read the newest per asset; SignalLog keeps the record "
        "of what was published and is not pruned",
    ),
    "News": (
        '"publishedAt"', 70,
        "jobs/lineage.py clusters over 45 days and jobs/human.py reads two 30 day "
        "windows, so 70 clears the deepest reader with ten days to spare",
    ),
}

# Named so the list is a statement rather than an omission. If a table is added to the schema
# it belongs in one of the two lists, and the test in tests/test_brain.py says so.
NEVER_PRUNED = (
    "PriceSnapshot", "DecisionLog", "SignalLog", "AssetThesis", "ThesisCheck", "EventState",
    "EventImpact", "EventLink", "Event", "Calibration", "Coverage", "SourceReliability",
    "Asset", "Industry", "Product", "ProductSignal", "ProductRegion", "ProductAssetLink",
    "MarketplaceItem", "GraphRelevance", "InvestigationFinding", "InvestigationHypothesis",
    "AnalogMatch", "Analysis", "Ranking", "NewsLineage", "IntradayBar", "IntradaySession",
    "ChunkRun", "SetupTarget",
)


# An index page that is half empty costs the tier exactly as much as a full one.
#
# `PriceSnapshot` is never pruned and never should be, but it is rewritten: a full refetch of an
# asset deletes its rows and COPYs them back, and 141,310 deletes had passed through it by
# 2026-10-12. B-tree pages do not re-pack themselves after that. Measured that day,
# `PriceSnapshot_pkey` held 93.7 MB at an average leaf density of 51.65% -- about 45 MB of a 500 MB
# tier spent on empty space, and a third of everything the database was using.
#
# `REINDEX ... CONCURRENTLY` is the one form of this that is safe beside running lanes: it builds
# the replacement alongside the live index and takes no lock that blocks reads or writes, unlike
# the `VACUUM FULL` above, which is why that one is kept behind `--reclaim` and this is not. It
# cannot run inside a transaction, so this is called after the commit the vacuum needs anyway.
#
# Only indexes that are both large and loose are touched. A small index rebuilt nightly would cost
# more in churn than the pages it returns.
REINDEX_MIN_BYTES = 8 * 1024 * 1024
REINDEX_MAX_DENSITY = 75.0


def reindex_bloated(cur) -> None:
    """Rebuild the indexes that have gone loose enough to be worth the write."""
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgstattuple")
    except Exception as e:  # noqa: BLE001
        # Without it there is no way to tell a loose index from a tight one, and rebuilding
        # every index on a schedule to find out is the cost this is meant to avoid.
        print(f"  index density unavailable ({str(e).splitlines()[0][:80]}), nothing rebuilt")
        return
    looked = rows(
        cur,
        """
        SELECT i.relname AS name, pg_relation_size(i.oid) AS bytes
        FROM pg_index x
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        WHERE t.relnamespace = 'public'::regnamespace
          AND x.indisvalid AND i.relam = (SELECT oid FROM pg_am WHERE amname = 'btree')
          AND pg_relation_size(i.oid) >= %s
        ORDER BY pg_relation_size(i.oid) DESC
        """,
        (REINDEX_MIN_BYTES,),
    )
    print(f"\n  {len(looked)} indexes over {REINDEX_MIN_BYTES // 1024 // 1024} MB")
    for r in looked:
        # Quoted, because these names are mixed case: `pgstatindex('PriceSnapshot_pkey')`
        # resolves through regclass, which folds an unquoted name to lower case and then
        # cannot find it.
        quoted = '"' + r["name"].replace('"', '""') + '"'
        density = one(cur, "SELECT avg_leaf_density AS d FROM pgstatindex(%s)", (quoted,))["d"]
        if density is None or float(density) >= REINDEX_MAX_DENSITY:
            print(f"  {r['name']:<34}{r['bytes'] / 1024 / 1024:>7.1f} MB  {float(density or 0):.1f}% full, left alone")
            continue
        before = r["bytes"]
        cur.execute(f'REINDEX INDEX CONCURRENTLY "{r["name"]}"')
        now = one(cur, "SELECT pg_relation_size(%s) AS b", (quoted,))["b"]
        print(
            f"  {r['name']:<34}{before / 1024 / 1024:>7.1f} MB  {float(density):.1f}% full, "
            f"rebuilt to {now / 1024 / 1024:.1f} MB"
        )


def main() -> int:
    dry = "--dry-run" in sys.argv
    conn = db()
    cur = conn.cursor()
    try:
        # --indexes-only is the half of this job that deletes nothing: it rebuilds loose
        # indexes and returns their empty pages to the tier. Separate because the sweep above
        # is a data change that wants a person's intent behind it, and this is not.
        if "--indexes-only" in sys.argv:
            step("rebuild the loose indexes")
            before = one(cur, "SELECT pg_database_size(current_database()) AS b")["b"]
            conn.commit()
            conn.autocommit = True
            reindex_bloated(cur)
            conn.autocommit = False
            after = one(cur, "SELECT pg_database_size(current_database()) AS b")["b"]
            print(
                f"\n  database {before / 1024 / 1024:.0f} MB -> {after / 1024 / 1024:.0f} MB "
                f"({(before - after) / 1024 / 1024:+.0f} MB). No row was deleted."
            )
            return 0

        step("cap the per-session working set" + (" (dry run)" if dry else ""))
        before = one(cur, "SELECT pg_database_size(current_database()) AS b")["b"]
        total = 0
        for table, (column, days, why) in KEEP.items():
            # The cutoff is measured from the newest row in the table, not from the calendar.
            # A lane that has not run for a week must not have its window silently shortened
            # by the clock, and a restore from backup must not delete everything it restored.
            newest = one(cur, f'SELECT max({column}) AS d FROM "{table}"')["d"]
            if newest is None:
                print(f"  {table:<18} empty")
                continue
            doomed = one(
                cur,
                f'SELECT count(*) AS n FROM "{table}" '
                f"WHERE {column} < %s - (%s * interval '1 day')",
                (newest, days),
            )["n"]
            kept = one(cur, f'SELECT count(*) AS n FROM "{table}"')["n"] - doomed
            print(f"  {table:<18} keep {days:>3}d  {kept:>7} rows, remove {doomed}")
            if doomed and not dry:
                cur.execute(
                    f'DELETE FROM "{table}" '
                    f"WHERE {column} < %s - (%s * interval '1 day')",
                    (newest, days),
                )
                conn.commit()
            total += doomed

        if dry:
            print(f"\n  {total} rows would be removed. Nothing was written.")
            return 0

        # A plain VACUUM, not VACUUM FULL.
        #
        # FULL rewrites the table and hands its pages back to the operating system, which is
        # the larger saving and the wrong trade on a schedule: it takes an ACCESS EXCLUSIVE
        # lock, and this job runs beside lanes that do not share its concurrency group. The
        # first run of it took the news fetch down mid-request -- "server closed the connection
        # unexpectedly" -- and the same lock would stall the website's own reads.
        #
        # A plain VACUUM takes no such lock and still does what this file exists for: the pages
        # the delete freed become reusable, so the table stops growing rather than shrinking.
        # Growth was the unbounded thing; the shrink is a one-off.
        #
        # --reclaim runs the FULL version on purpose, for a human who has stopped the lanes.
        reclaim = "--reclaim" in sys.argv
        print("\n  " + ("rewriting the tables to hand their pages back"
                        if reclaim else "marking the freed pages reusable"))
        # A commit first, because VACUUM cannot run inside a transaction and the deletes above
        # leave one open.
        conn.commit()
        conn.autocommit = True
        for table in KEEP:
            cur.execute(f'VACUUM ({"FULL, " if reclaim else ""}ANALYZE) "{table}"')
        # Still outside a transaction, which REINDEX CONCURRENTLY needs for the same reason
        # VACUUM does.
        reindex_bloated(cur)
        conn.autocommit = False

        after = one(cur, "SELECT pg_database_size(current_database()) AS b")["b"]
        print(
            f"  {total} rows removed, {(before - after) / 1024 / 1024:.0f} MB returned, "
            f"database now {after / 1024 / 1024:.0f} MB"
        )
        print(
            "  nothing in the accuracy loop was touched: DecisionLog, SignalLog, AssetThesis, "
            "ThesisCheck, EventState and the whole of PriceSnapshot are kept in full"
        )
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
