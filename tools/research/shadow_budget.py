"""The free tier is 500 MB and nothing in Postgres enforces it. This is where a writer stops.

`data/foundation/dataset/shadow_storage_budget.json` measures the store and records the policy: on
the free plan the headroom at checkpoint 40 was 16.9 MB, the shadow tables are kilobytes, and a
full-universe daily stream would exhaust the plan in about two weeks. The JSON is a measurement, so
it cannot refuse anything; the writers that feed the shadow stream can, and this is the one place
that decision is made so `shadow_predict.py` and `shadow_score.py` agree on what "full" means.

The cap is a plan limit, not a database one: `pg_database_size` will happily report a size past 500
MB, and the writes that took it there will succeed. That is exactly why the floor exists -- to stop
the schedule before the store is full, rather than in the run that fills it. It is set well below
the cap so it never fires in ordinary operation.
"""

from __future__ import annotations

#: The Supabase free plan, the figure the storage budget and the health audit both use.
FREE_TIER_MB = 500.0

#: Refuse to write new evidence with less than this much room left. Above the kilobytes a bounded
#: run spends and below the 16.9 MB the primary held at checkpoint 40, so it is a backstop against a
#: runaway caller, not a limit on the schedule.
MIN_HEADROOM_MB = 8.0

#: `pg_database_size` is the same figure `tools/daily_audit.py` and the storage budget record, so a
#: writer and the monitor watching it cannot disagree about how full the store is.
_SIZE_SQL = 'SELECT pg_database_size(current_database())/1048576.0 AS mb'


def headroom_mb(conn, limit_mb: float = FREE_TIER_MB) -> tuple[float, float]:
    """`(headroomMB, sizeMB)` for the connection's database against the free-tier cap.

    Works with either cursor shape: `jobs/nbt.py` hands back dict rows, and a test may hand back
    tuples, so both are read rather than assuming one.
    """
    cur = conn.cursor()
    cur.execute(_SIZE_SQL)
    row = cur.fetchone()
    cur.close()
    if row is None:
        raise RuntimeError("pg_database_size returned no row")
    size = float(row["mb"] if isinstance(row, dict) else row[0])
    return limit_mb - size, size


def refuse_if_full(conn, min_mb: float = MIN_HEADROOM_MB) -> dict | None:
    """Return a refusal payload when the store is below `min_mb` of headroom, else `None`.

    The payload is shaped like the writers' own results (`{"written": 0, "status": ...}`) so a
    caller can record it without special-casing. `min_mb <= 0` disables the check, for a run that
    has deliberately decided to spend the last of the headroom (the tests, or a manual run).
    """
    if min_mb <= 0:
        return None
    headroom, size = headroom_mb(conn)
    if headroom >= min_mb:
        return None
    return {
        "written": 0,
        "status": "refused",
        "reason": (f"{headroom:.1f} MB of headroom below the {min_mb:.0f} MB floor "
                   f"(database {size:.0f} MB of a {FREE_TIER_MB:.0f} MB plan); not recording"),
        "headroomMB": round(headroom, 1),
        "sizeMB": round(size, 1),
    }
