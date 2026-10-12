"""One row per slice of one job, written whether the slice succeeded or not.

The pipeline is many small jobs rather than one long one, and the price of that split is that
"did the data arrive" stops being answerable by looking at whether a run was green. A green
run can mean seven slices wrote nothing; a red one can mean six slices wrote everything and
the seventh hit a 429. `ChunkRun` is the answer instead, and this module is the only way a job
should write to it: a job that has to *remember* to log is a job that will not log on the path
that matters, which is the one where it raised.

Three properties are the whole point, and each one is here because of something that happened:

  * The row is written on the way out of the block, including the exception path, before the
    exception is re-raised. A failure that loses its own log line is exactly what this table
    exists to prevent.
  * The row is written on its own short-lived connection and committed immediately. The
    caller's transaction is not used and not touched. jobs/prices.py documents why in
    `SourceSilent`: psycopg rolls back the whole transaction on *any* exception leaving the
    `with` block, and one blocked source once discarded 37,537 rows another lane had already
    written. A log row that vanishes with the rollback it was meant to describe is worse than
    no log at all, because the table then reads as "nothing ran".
  * `note` can never be written empty. Not by convention — the writer refuses a blank note,
    and the context manager always has a fallback sentence built from the counts, so a caller
    that sets nothing still produces a line a human can read.

Usage:

    from runlog import chunk_run

    with chunk_run(job="cron-crypto", source="Binance", chunk="1/1", asked=10) as run:
        run.rows_written = 123
        run.newest = date(2026, 10, 2)
        run.note = "10 of 10 coins answered"

The chunk helpers below (`parse_chunk`, `slice_of`, `chunk_label`) live here rather than in
nbt.py so that a job and jobs/run.py agree on one implementation: the runner decides which
slice to ask for and the job decides which symbols that is, and those two answers have to be
the same answer or a retry covers something the first run already did.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Iterable, Sequence, TypeVar

from nbt import db, now, primary_choice, throttled_since

T = TypeVar("T")

# The four states `ChunkRun.status` is allowed to hold. Listed here so a typo is a failed
# lookup in this module rather than a string nobody ever queries for.
# `skipped` is the fifth, and it is the one that carries no judgement about the source.
#
# The other four are outcomes of asking. `skipped` says the lane did not ask, because
# `jobs/breaker.py` had the source open after consecutive non-answers. It has to be its own word
# rather than `empty`: `empty` means "asked and got none", which is what a block looks like and
# is exactly what the breaker counts. Filing a skip as empty would let the breaker read its own
# skips as further evidence and extend its own cooldown forever -- a gate that feeds itself, and
# one that would quietly delete a venue that had recovered hours earlier.
# `blocked` is the sixth, and it is the one the product-demand sources needed.
#
# A provider that answers HTTP 429 has told us something quite different from a provider that
# answered with nothing: the first says "not now, you are asking too fast", the second says
# "there is nothing there". `empty` conflated them, and that is how Reddit came to look like a
# quiet source rather than a throttled one -- 7 rows across 3 of 30 products, filed as though
# the other 27 simply had no posts. A throttle is also the one state where the right response is
# to ask again later rather than to investigate the data, so it has to be distinguishable from
# the outside.
STATUSES = ("ok", "partial", "empty", "failed", "skipped", "blocked")

# A note is one line for a human to read without opening a log. An exception's message is not
# bounded by anything — a psycopg error can carry a whole statement, and a requests error can
# carry a URL with a signed query string — so it is cut here. 400 characters is about four
# terminal lines, which is as much as anyone reads out of a status table before going to the
# log anyway.
NOTE_MAX = 400

_INSERT = """
    INSERT INTO "ChunkRun"
        (job, source, chunk, "rowsWritten", asked, newest, status, note, "durationMs", "startedAt")
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


# ---------------------------------------------------------------------------------------
# Slicing. Pure, so it is testable without a database and identical in the runner and the job.
# ---------------------------------------------------------------------------------------


def parse_chunk(text: str) -> tuple[int, int]:
    """"3/8" -> (3, 8), the third of eight slices. Raises ValueError on anything else.

    One-based on purpose. The flag is written by a person in a workflow file and read by a
    person in a failure, and "--chunk 0/8" reads as "none of eight" to everybody who is not
    the author of the indexing.
    """
    if not isinstance(text, str) or text.count("/") != 1:
        raise ValueError(f"chunk must look like 3/8, got {text!r}")
    left, right = text.split("/")
    # Not stripped: "3 /8" is a workflow expression that interpolated something unexpected, and
    # accepting it would hide the real problem behind a slice that happens to run.
    if not left.isdigit() or not right.isdigit():
        raise ValueError(f"chunk must look like 3/8, got {text!r}")
    index, total = int(left), int(right)
    if total < 1:
        raise ValueError(f"chunk {text!r} asks for {total} slices, which is not a number of slices")
    if not 1 <= index <= total:
        raise ValueError(f"chunk {text!r} asks for slice {index} of {total}")
    return index, total


def chunk_label(index: int, total: int) -> str:
    """The canonical string for the column. A job that is not chunked writes "1/1", never null."""
    return f"{index}/{total}"


def slice_of(
    items: Iterable[T], index: int, total: int, key: Callable[[T], Any] | None = None
) -> list[T]:
    """The `index`-of-`total` slice of `items`, as contiguous blocks of a sorted list.

    Sorted first, and that sort is the entire reason this function exists rather than being
    three lines at each call site. The work list usually arrives from a query, and a query
    without an ORDER BY may hand back the same rows in a different order on the next run —
    Postgres is free to. Slicing that order directly would put BTC in slice 2 this morning and
    slice 5 this afternoon, so a cursor saying "slices 1-4 are done" and a retry of slice 5
    would be talking about different sets, and something would be fetched twice while
    something else was never fetched at all. Sorting first makes the assignment a property of
    the symbol rather than of the order a query happened to return.

    For the same reason `key` must be unique over `items`. Python's sort is stable, which means
    ties keep their *input* order — exactly the order that is not stable between runs. A key
    with duplicates reintroduces the problem it was passed to solve, so sort by the identifier,
    not by the exchange or the sector.

    Contiguous blocks rather than round-robin because the block a slice covers is then
    describable in one sentence ("A through C"), which is what a human reads off a failed row.
    Sizes differ by at most one, and the floor-division arithmetic guarantees the N slices are
    disjoint and cover the whole list for every N, including N larger than the list, where the
    surplus slices are legitimately empty.
    """
    ordered = sorted(items, key=key) if key is not None else sorted(items)  # type: ignore[type-var]
    n = len(ordered)
    lo = ((index - 1) * n) // total
    hi = (index * n) // total
    return ordered[lo:hi]


# ---------------------------------------------------------------------------------------
# Status. Also pure: the judgement is the part worth testing, and it needs no connection.
# ---------------------------------------------------------------------------------------


def default_status(asked: int, rows_written: int, answered: int | None = None) -> str:
    """What a slice's status is when the job does not say.

    `empty` is the loud one: the slice asked for things and got none of them. That is the shape
    a blocked host takes — a throttled provider returns an empty result and raises nothing, so
    "blocked" and "a quiet market" are the same picture from inside the job, and the only
    honest thing to do is record it as the state that needs looking at.

    `partial` is counted in items answered, not rows written, because one item can produce many
    rows: ten coins can write a hundred and twenty three rows, so rows carry no information
    about how many coins answered. A job that does not count answers gets `ok`, and the note is
    where it says more.
    """
    if asked > 0 and rows_written == 0:
        return "empty"
    if answered is not None and asked > 0 and 0 < answered < asked:
        return "partial"
    return "ok"


@dataclass
class Slice:
    """The mutable record the `with` block fills in. Defaults are the honest no-op row."""

    job: str
    source: str
    chunk: str = "1/1"
    asked: int = 0
    rows_written: int = 0
    answered: int | None = None
    newest: date | datetime | None = None
    note: str = ""
    status: str | None = None          # set to override the default judgement

    def resolved_status(self) -> str:
        if self.status is not None:
            if self.status not in STATUSES:
                raise ValueError(f"status {self.status!r} is not one of {', '.join(STATUSES)}")
            return self.status
        return default_status(self.asked, self.rows_written, self.answered)

    def resolved_note(self) -> str:
        """The note, or a sentence built from the counts when the caller set none.

        This is the structural half of "note is never empty". The column is required and the
        writer refuses a blank, so the only way for a caller to be unable to log is for this to
        return something useful without being told anything.
        """
        if self.note and self.note.strip():
            return self.note.strip()[:NOTE_MAX]
        answered = "" if self.answered is None else f", {self.answered} answered"
        return (
            f"{self.source} slice {self.chunk}: {self.rows_written} rows from {self.asked} asked"
            f"{answered}. No note set by the job."
        )[:NOTE_MAX]


def write(
    *,
    job: str,
    source: str,
    chunk: str,
    rows_written: int,
    asked: int,
    newest: date | datetime | None,
    status: str,
    note: str,
    duration_ms: int,
    started_at: datetime | None = None,
) -> bool:
    """Write one row on a connection of its own and commit it. True when the row landed.

    Its own connection, not the caller's: see the module docstring. The commit is immediate and
    unconditional, which is what makes the row survive the caller's transaction rolling back a
    second later — by then this connection is already closed and the row is already visible to
    everyone else.

    A failure to log is printed and swallowed. Two reasons, both deliberate. On the exception
    path the caller's exception is the one worth re-raising and must not be replaced by a
    secondary database error from the logger; on the happy path a diagnostics row that could
    not be written is not a reason to fail a run that did its actual work.
    """
    if not note or not note.strip():
        # Unreachable through `chunk_run`, which always has a fallback. Kept because the
        # model's own comment says a failed chunk with no note is the thing this table exists
        # to stop, and a direct caller should be told rather than quietly allowed.
        raise ValueError("ChunkRun.note is required; a row with no note is the bug this prevents")
    if status not in STATUSES:
        raise ValueError(f"status {status!r} is not one of {', '.join(STATUSES)}")
    # The primary as every other lane picks it (brain.md rule 97), not `DATABASE_URL` alone:
    # since Supabase became the primary a deployment can legitimately have no `DATABASE_URL` at
    # all, and this gate would then silently log nothing while every lane ran normally -- an
    # empty status table that looks exactly like a stopped pipeline.
    if not primary_choice()[1]:
        # A local run with no database still runs the job; it just cannot log. Said out loud so
        # an empty table is never mistaken for a pipeline that stopped running.
        print(f"  [runlog] no database configured, not logging {job} {source} {chunk} ({status})")
        return False

    conn = None
    try:
        conn = db()
        with conn.cursor() as cur:
            cur.execute(
                _INSERT,
                (
                    job, source, chunk, rows_written, asked, newest, status,
                    note.strip()[:NOTE_MAX], duration_ms, started_at or now(),
                ),
            )
        conn.commit()
        return True
    except Exception as e:  # noqa: BLE001 - a logger that can raise is a logger that hides bugs
        print(f"  [runlog] could not write the {job} {source} {chunk} row: {type(e).__name__}: {e}")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


@contextmanager
def lane_run(*, job: str, source: str, table: str, date_col: str | None = None, asked: int = 0,
             where: str | None = None):
    """Wrap a whole lane and record one honest row for it, without touching its internals.

    Written for the eight lanes that had no stored run record at all -- psx, intraday, live,
    marketplace, geo, upcoming and the rest -- where `prices.py` was the only job calling this
    module. A missing row is indistinguishable from a lane that never ran, so `lib/health.ts`
    could not see most of the pipeline.

    It measures the lane from the outside: the row count of the table the lane writes, before
    and after, and the newest value of `date_col` when the lane dates its rows. That needs no
    change inside the lane, which is the point -- these files open and close their own
    connections at times chosen around long network phases, and threading a logger through them
    would be a large edit for a diagnostic.

    **Two brief connections, never one held open.** The "before" count is taken and the
    connection closed; the lane runs with no connection of ours open; the "after" count and the
    row itself go on a second one. Holding a session open across a lane's network phase is the
    exact fault these jobs are built to avoid, and a logger must not reintroduce it.

    `where` narrows the count to the lane's own rows when a table has several writers --
    `PriceSnapshot` takes US, PSX and crypto closes from three different lanes, and counting the
    whole table would credit one lane with another's work whenever two overlap.

    A throttled provider is recorded as `blocked` rather than `empty`: see STATUSES.
    """
    def count() -> tuple[int, object]:
        try:
            conn = db()
            try:
                with conn.cursor() as cur:
                    col = f', max({date_col}) AS newest' if date_col else ", NULL AS newest"
                    clause = f" WHERE {where}" if where else ""
                    cur.execute(f'SELECT count(*) AS n{col} FROM "{table}"{clause}')
                    # `nbt.db()` hands back dict rows, so these are keys and not positions.
                    row = cur.fetchone()
                    return (row["n"] or 0), row["newest"]
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001 - a diagnostic must never fail the lane
            print(f"  [runlog] could not count {table}: {type(e).__name__}")
            return 0, None

    before, _ = count()
    mark = throttled_since()
    with chunk_run(job=job, source=source, asked=asked) as run:
        yield run
        after, newest = count()
        blocks = throttled_since(mark)
        if run.rows_written == 0:
            run.rows_written = max(after - before, 0)
        if run.newest is None:
            run.newest = newest
        if blocks and run.status is None:
            run.status = "blocked"
            worst = max(blocks.items(), key=lambda kv: kv[1])
            run.note = run.note or (
                f"{source}: throttled {sum(blocks.values())} times ({worst[0]} x{worst[1]}); "
                f"{run.rows_written} rows written"
            )
        if not run.note:
            run.note = f"{source}: {run.rows_written} rows written into {table}"


@contextmanager
def chunk_run(
    *,
    job: str,
    source: str,
    chunk: str = "1/1",
    asked: int = 0,
    note: str = "",
    status: str | None = None,
):
    """Time a slice, yield a record to fill in, and write exactly one row on the way out.

    One row on every path. On a clean exit the status is whatever the job set or whatever the
    counts imply; on an exception it is `failed`, the note becomes the exception's type and
    message, the row is written, and the exception is re-raised unchanged so the step still
    exits non-zero and the workflow still goes red. Recording a failure is not handling it.

    `chunk` is validated rather than trusted: a malformed label would be written to a column
    the freshness panel groups by, and a slice filed under "3 /8" is a slice nobody finds.
    """
    index, total = parse_chunk(chunk)
    run = Slice(job=job, source=source, chunk=chunk_label(index, total), asked=asked, note=note)
    if status is not None:
        run.status = status
    started = time.monotonic()
    # Two clocks on purpose. monotonic measures the duration and cannot be dragged by an NTP
    # step mid-slice; the wall clock is what goes in startedAt, because a slice that ran twenty
    # minutes and then failed belongs next to the rest of the 14:00 work rather than at 14:20.
    started_at = now()
    try:
        yield run
    except BaseException as e:  # noqa: BLE001 - everything gets logged, nothing gets swallowed
        # The job's own note is kept when it set one before raising: it usually says how far the
        # slice got, which the exception does not.
        head = run.note.strip() + " | " if run.note and run.note.strip() else ""
        run.note = f"{head}{type(e).__name__}: {e}"
        write(
            job=run.job, source=run.source, chunk=run.chunk, rows_written=run.rows_written,
            asked=run.asked, newest=run.newest, status="failed", note=run.resolved_note(),
            duration_ms=int((time.monotonic() - started) * 1000), started_at=started_at,
        )
        raise
    write(
        job=run.job, source=run.source, chunk=run.chunk, rows_written=run.rows_written,
        asked=run.asked, newest=run.newest, status=run.resolved_status(),
        note=run.resolved_note(), duration_ms=int((time.monotonic() - started) * 1000),
        started_at=started_at,
    )


def recent(limit: int = 40) -> Sequence[dict]:
    """The last `limit` rows, newest first. For reading the table from a shell, not for jobs."""
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT job, source, chunk, "rowsWritten", asked, newest, status, note,'
                ' "durationMs", "startedAt" FROM "ChunkRun" ORDER BY "startedAt" DESC LIMIT %s',
                (limit,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def main() -> None:
    """`python jobs/runlog.py` prints the recent rows, so a failure is readable without a UI."""
    for row in recent():
        print(
            f"{row['startedAt']:%Y-%m-%d %H:%M}  {row['status']:<7} {row['job']:<16}"
            f" {row['source']:<18} {row['chunk']:<5} {row['rowsWritten']:>6} rows"
            f" of {row['asked']:>4} asked  {row['note']}"
        )


if __name__ == "__main__":
    main()
