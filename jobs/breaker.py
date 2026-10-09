"""Stop asking a source that has stopped answering, and start again when it might have recovered.

The retry logic in `nbt.get` is per-process: `RETRY_HOST_BUDGET` stops one run from spending its
whole timeout on a dead host, and then the dictionary that held the count is thrown away with the
process. So a source that was blocked all of yesterday is asked again from scratch today, at full
budget, by every lane that touches it. That is the right behaviour for a blip and the wrong one
for an outage, and nothing in the pipeline could tell the two apart, because nothing remembered.

This remembers. It is a circuit breaker with three states, and the whole of its input is the
`ChunkRun` rows the fetch lanes already write:

    closed      the source is answering. Fetch normally.
    open        it has failed `OPEN_AFTER` slices in a row and the cooldown has not elapsed.
                Skip it, write a row saying so, and let the other lanes run.
    half-open   the cooldown has elapsed. Allow exactly one slice through as a probe. If it
                answers the breaker closes; if it does not, the cooldown starts again, longer.

**Nothing is stored.** The state is derived from `ChunkRun` on demand, for the reason
`tools/scorecard.py` gives for deriving its scores: a second copy of the truth is a thing that
drifts from the first. It also means the breaker cannot get stuck in a state nobody can see --
every input to it is a row a human can read, and the freshness panel reads the same rows.

What it deliberately does NOT do
--------------------------------
It does not substitute anything for the data that did not arrive. No last-known value carried
forward as though it were today's, no interpolation across the gap, no approximation of a missing
venue from a correlated one. The site's first principle is that no number is invented, and a
synthesised close is the most dangerous possible invention here: it is indistinguishable from a
real one downstream, it would pass every staleness gate precisely *because* it is freshly dated,
and the decision rules would then read it as evidence. A source that did not answer must reach
the reader as a source that did not answer -- which is what `SourceSilent`, `Coverage` and gate 3
of the rule table already exist to do. This file only stops the pointless asking in between.

Run: imported by the fetch lanes. `python jobs/breaker.py` prints the current state of every
source it has history for, which is the one thing worth looking at when a lane goes quiet.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half-open"

# Consecutive non-answers before the breaker opens.
#
# Three, and not one. A single empty slice is an ordinary event: a rerun inside the cache hour
# legitimately writes nothing, a venue can drop one request, and a market can be shut. Opening on
# one would make the breaker the outage. Three consecutive slices across a lane's schedule is
# hours of silence, which is the shape of a block rather than of a bad minute.
OPEN_AFTER = 3

# The first cooldown, and how it grows. A source down for three slices might be back in an hour;
# one down for twenty is not coming back inside one, and asking it every hour for a day is the
# cost this file exists to remove. The growth is per failure past the threshold.
COOLDOWN_BASE_MIN = 60

# **The ceiling, and it is the most important constant here.** An unbounded backoff is how a
# source that recovers is never asked again: at the eleventh doubling the next probe is a month
# away, and the breaker has quietly become a permanent deletion of that venue. Twelve hours means
# every source is probed at least twice a day however long it has been down, so a recovery is
# noticed within one day in the worst case and the breaker can only ever delay a fetch, never
# cancel one for good.
COOLDOWN_MAX_MIN = 720

# How far back the history is read. An outage from three weeks ago is not evidence about now, and
# without a window the breaker would hold open on rows whose source has been healthy since.
LOOKBACK_DAYS = 14

# The statuses that count as the source having answered. `partial` is deliberately among them:
# "some of the assets answered" is the ordinary state of a chunked lane against a venue that rate
# limits, and treating it as a failure would open the breaker on a working source. `empty` is the
# one that must be loud -- it is "asked for things and got none", which is what a block looks
# like -- and it is counted as a non-answer here for exactly that reason.
ANSWERED = ("ok", "partial")

# A slice this breaker itself skipped. Counted as neither an answer nor a failure: it is this
# module's own footprint, and a breaker that reads its own skips as evidence extends its own
# cooldown on every run until the ceiling, then holds there forever -- which would delete a
# venue that recovered hours after the first outage. The streak is read straight through them,
# so the cooldown is always measured from the last time the source was actually asked.
IGNORED = ("skipped",)


@dataclass(frozen=True)
class Breaker:
    """What to do about one source right now, and why, in words a log line can carry."""

    source: str
    state: str
    # How many slices in a row did not answer.
    failures: int
    # Minutes until the next probe is allowed. 0 when one is allowed now.
    wait_minutes: float
    reason: str

    @property
    def may_fetch(self) -> bool:
        """Closed and half-open both fetch; only `open` skips.

        Half-open fetches on purpose: a probe IS a fetch, and a breaker that never let one
        through would be a switch rather than a breaker.
        """
        return self.state != OPEN


def cooldown_minutes(failures: int) -> float:
    """How long to wait after `failures` consecutive non-answers, in minutes.

    Doubles per failure past `OPEN_AFTER` and stops at `COOLDOWN_MAX_MIN`. Returns 0 below the
    threshold, where there is nothing to wait for.
    """
    if failures < OPEN_AFTER:
        return 0.0
    over = failures - OPEN_AFTER
    # Capped before the shift so a source down for a year does not compute 2**365 on the way to
    # being clamped. The exponent is bounded by how many doublings fit under the ceiling.
    doublings = min(over, 20)
    return min(float(COOLDOWN_BASE_MIN * (2 ** doublings)), float(COOLDOWN_MAX_MIN))


def consecutive_failures(history: list[dict]) -> tuple[int, datetime | None]:
    """How many of the most recent slices did not answer, and when the newest of them started.

    `history` is `ChunkRun` rows for one source, newest first. Counting stops at the first slice
    that answered, which is what makes this *consecutive* rather than a failure rate: a source
    that answers one slice in three is degraded and is not blocked, and a breaker is the wrong
    instrument for degraded.
    """
    failures = 0
    newest: datetime | None = None
    for row in history:
        status = row.get("status")
        if status in IGNORED:
            continue
        if status in ANSWERED:
            break
        failures += 1
        if newest is None:
            newest = row.get("startedAt")
    return failures, newest


def state_of(source: str, history: list[dict], now: datetime) -> Breaker:
    """The breaker for one source, from its own recent slices. Pure: no cursor, no clock.

    `now` is passed in rather than read, for the same reason `decide` in lib/decision.ts takes
    `today`: a function that reads the clock cannot be tested at a boundary, and the boundary is
    the entire content of a cooldown.
    """
    failures, last_failure = consecutive_failures(history)

    if failures < OPEN_AFTER:
        # Includes the no-history case, and that is the right answer rather than a lucky one: a
        # source nobody has asked yet is not a broken source. Every rule in this project reads an
        # absent measurement as missing evidence and never as evidence against.
        if not history:
            return Breaker(source, CLOSED, 0, 0.0, "no slices recorded yet, so nothing is known against it")
        return Breaker(
            source, CLOSED, failures, 0.0,
            f"{failures} consecutive non-answers, under the {OPEN_AFTER} that open it",
        )

    cooldown = cooldown_minutes(failures)
    if last_failure is None:
        # Failures counted but no timestamp on any of them. The honest reading is that the
        # cooldown cannot be measured, and an unmeasurable cooldown must not hold the breaker
        # shut -- that would be a gate resting on an absence.
        return Breaker(
            source, HALF_OPEN, failures, 0.0,
            f"{failures} consecutive non-answers with no recorded time, so one probe is allowed",
        )

    elapsed = (now - last_failure).total_seconds() / 60.0
    if elapsed >= cooldown:
        return Breaker(
            source, HALF_OPEN, failures, 0.0,
            f"{failures} consecutive non-answers, and the {cooldown:.0f} minute cooldown has "
            f"elapsed, so one probe is allowed",
        )
    return Breaker(
        source, OPEN, failures, cooldown - elapsed,
        f"{failures} consecutive non-answers; next probe in {cooldown - elapsed:.0f} minutes",
    )


def read_history(cur, source: str, now: datetime, limit: int = 40) -> list[dict]:
    """The recent slices for one source, newest first. One statement, bounded two ways.

    Bounded by both a window and a row count on purpose. The window is what makes an old outage
    stop counting; the count is what stops a lane that slices eight ways an hour from reading a
    thousand rows to answer a yes-or-no question.
    """
    cur.execute(
        """
        SELECT status, "startedAt" FROM "ChunkRun"
         WHERE source = %s AND "startedAt" >= %s
         ORDER BY "startedAt" DESC
         LIMIT %s
        """,
        (source, now - timedelta(days=LOOKBACK_DAYS), limit),
    )
    return list(cur.fetchall())


def breaker_for(cur, source: str, now: datetime | None = None) -> Breaker:
    """The breaker for one source, read from the database.

    **Never raises.** A breaker that cannot read its own history must not be the thing that stops
    a fetch: the whole point of this file is to make a lane more survivable, and a resilience
    layer that can itself take the lane down has made things worse. An unreadable history is
    treated exactly like an empty one -- closed, fetch normally -- which is the behaviour the
    pipeline had before this module existed.
    """
    when = now or datetime.now(timezone.utc)
    try:
        return state_of(source, read_history(cur, source, when), when)
    except Exception as e:  # noqa: BLE001
        print(f"  [breaker] could not read history for {source}: {type(e).__name__}: {e}")
        return Breaker(source, CLOSED, 0, 0.0, "breaker history unreadable, so the source is asked as usual")


def read_all(cur, now: datetime) -> dict[str, list[dict]]:
    """Every source's recent slices in one statement, newest first within each source.

    One statement and not one per source, which matters for a reason beyond speed here: a loop
    issuing a read per source is the shape the query ratchet in tests/test_brain.py exists to
    catch, and it cannot see this one -- it follows a module-level helper one hop, and
    `main` -> `breaker_for` -> `read_history` is two. So the loop is removed rather than
    excused, which is the answer that does not depend on a guard noticing.
    """
    cur.execute(
        """
        SELECT source, status, "startedAt" FROM "ChunkRun"
         WHERE "startedAt" >= %s
         ORDER BY source ASC, "startedAt" DESC
        """,
        (now - timedelta(days=LOOKBACK_DAYS),),
    )
    out: dict[str, list[dict]] = {}
    for row in cur.fetchall():
        out.setdefault(row["source"], []).append(row)
    return out


def main() -> int:
    """Print every source's breaker. The first thing to look at when a lane goes quiet."""
    from nbt import db  # noqa: PLC0415 - imported here so the pure half needs no database

    now = datetime.now(timezone.utc)
    conn = db()
    cur = conn.cursor()
    history = read_all(cur, now)
    if not history:
        print(
            f"No ChunkRun rows in the last {LOOKBACK_DAYS} days. Either no fetch lane has run, "
            "or none of them is logging its slices."
        )
        conn.close()
        return 0
    print(f"{'source':34} {'state':10} {'fails':>6} {'wait':>8}  why")
    print("-" * 110)
    for source in sorted(history):
        b = state_of(source, history[source], now)
        print(f"{b.source:34} {b.state:10} {b.failures:>6} {b.wait_minutes:>7.0f}m  {b.reason}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
