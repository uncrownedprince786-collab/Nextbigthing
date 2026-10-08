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

Run: python jobs/retention.py [--dry-run]
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


def main() -> int:
    dry = "--dry-run" in sys.argv
    conn = db()
    cur = conn.cursor()
    try:
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

        # Deleting rows does not return the pages to the operating system; it marks them
        # reusable. On a tier measured in megabytes that distinction is the whole point, so
        # the space is reclaimed rather than left for the next insert to grow into.
        print("\n  reclaiming the pages")
        conn.autocommit = True
        for table in KEEP:
            cur.execute(f'VACUUM (FULL, ANALYZE) "{table}"')
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
