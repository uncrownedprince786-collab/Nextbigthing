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


#: Free space inside the heaps, which `pg_database_size` counts as used and a writer can spend
#: without the database growing by a byte. Measured with `pgstattuple`; `NULL`-safe and skipped
#: entirely when the extension is unavailable, because a budget that cannot be computed must fall
#: back to the pessimistic number rather than to no number.
_REUSABLE_SQL = """
SELECT coalesce(sum((s).free_space + (s).dead_tuple_len), 0) / 1048576.0 AS mb
FROM (
  SELECT pgstattuple(c.oid) AS s
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
    AND pg_total_relation_size(c.oid) > 2 * 1024 * 1024
) t
"""


def reusable_mb(conn) -> float | None:
    """Megabytes inside the heaps that a new row can be written into, or `None` if unmeasurable.

    `pgstattuple` has to read every page of every table it is asked about, so this is restricted to
    the tables big enough for the answer to matter (over 2 MB). The ones left out are a rounding
    error against a 500 MB plan and they are left out in the *pessimistic* direction: unmeasured
    free space counts as used.
    """
    try:
        cur = conn.cursor()
        cur.execute(_REUSABLE_SQL)
        row = cur.fetchone()
        cur.close()
    except Exception:  # noqa: BLE001 -- no extension, no permission, no measurement
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    if row is None:
        return None
    return float(row["mb"] if isinstance(row, dict) else row[0])


def headroom_mb(conn, limit_mb: float = FREE_TIER_MB) -> tuple[float, float]:
    """`(headroomMB, sizeMB)` for the connection's database against the free-tier cap.

    **`sizeMB` is the disk footprint; `headroomMB` is room to write, and they are not the same
    question.** `pg_database_size` counts every page the database has ever extended into, including
    the pages a delete freed and Postgres will reuse before extending again. A writer wants to know
    whether its row will push the *footprint* up, and a row that lands in free space does not.

    Measured on the primary 2026-10-19, which is why this exists: `pg_database_size` read **486.0
    MB** of a 500 MB plan -- 97.2%, under the 8 MB floor, and the shadow lane had been refusing
    every write for days. The same database held **64.7 MB** of reusable free space and 0.5 MB of
    dead tuples, so **420.8 MB was live and 79.2 MB was free**. PriceSnapshot alone accounted for
    39.1 MB of it. The store was never full; the number watching it could not tell the difference
    between a page in use and a page already given back.

    So the headroom returned is against the *effective* size, and `sizeMB` keeps reporting the
    footprint, which is the figure the provider bills and alerts on. When free space cannot be
    measured -- no `pgstattuple`, no permission -- the two collapse to the old pessimistic
    behaviour, which refuses more than it needs to and never less.

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
    free = reusable_mb(conn)
    effective = size if free is None else max(0.0, size - free)
    return limit_mb - effective, size


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
        # Both numbers, because they answer different questions and a refusal that printed only
        # the footprint sent a previous session hunting for space that was already free.
        "reason": (f"{headroom:.1f} MB of writable headroom below the {min_mb:.0f} MB floor "
                   f"(database footprint {size:.0f} MB of a {FREE_TIER_MB:.0f} MB plan); "
                   f"not recording"),
        "headroomMB": round(headroom, 1),
        "sizeMB": round(size, 1),
    }
