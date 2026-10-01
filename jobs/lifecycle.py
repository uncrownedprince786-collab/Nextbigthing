"""Move dated events through their life, and freeze what was true before each one.

The gap this closes: a scheduled date whose day had passed simply stayed `scheduled = true`
forever. The system could remember that an earnings report was coming and then learn nothing
at all from the one that happened.

States
------
    discovered   a source published the date, nothing checked yet
    upcoming     confirmed, and more than APPROACHING_DAYS away
    approaching  inside that window
    live         the date is today
    resolved     the day has passed and the move after it has been measured
    historical   resolved long enough ago to be evidence rather than news

Why the before-state is frozen
------------------------------
Once an event has passed, every table here holds the post-event world. Asking "what did we
know before the report" by querying current data silently answers with information that did
not exist then, and that is look-ahead bias — not a mistake somebody makes, a mistake the
schema invites. So at resolution a `before` row is written from observations dated *strictly
earlier* than the event, and an `after` row once the window has elapsed.

Rows are never rewritten. A correction becomes a new row with a later `computedAt`, so the
record of what the system believed at the time survives its own revisions.

Nothing here invents an event. It only advances and measures events another job discovered.

Run: python jobs/lifecycle.py
Writes: Event.lifecycle, Event.resolvedAt, EventState
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, one, pct, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

LIFECYCLE = "Measured from stored observations dated before and after the event"

# Inside this many days an event is worth showing prominently rather than listing.
APPROACHING_DAYS = 7

# How long after the date the post-event measurement is taken. Matches the shorter window
# events.py already uses, so the two describe the same thing.
WINDOW_DAYS = 14

# How far either side of a target date a close may be taken from, for weekends and holidays.
MAX_DRIFT_DAYS = 5

# After this long a resolved event stops being news and becomes evidence. It changes nothing
# about the data; it changes which list the event belongs on.
HISTORICAL_AFTER_DAYS = 120

# Sessions the trailing return and volume ratio are measured over.
TRAIL = 20


def close_near(cur, asset_id: str, target: date, before_only: bool = False):
    """Stored close nearest a target date, within MAX_DRIFT_DAYS.

    `before_only` is the look-ahead guard: for a pre-event reading it refuses to look
    forward at all, because the nearest close to an event date is very often the day after
    it, and that day already contains the event.
    """
    if before_only:
        return one(
            cur,
            """
            SELECT date, close, volume FROM "PriceSnapshot"
            WHERE "assetId" = %s AND date < %s AND close IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """,
            (asset_id, target),
        )
    return one(
        cur,
        """
        SELECT date, close, volume FROM "PriceSnapshot"
        WHERE "assetId" = %s AND date BETWEEN %s AND %s AND close IS NOT NULL
        ORDER BY abs(date - %s::date) ASC, date ASC LIMIT 1
        """,
        (
            asset_id,
            target - timedelta(days=MAX_DRIFT_DAYS),
            target + timedelta(days=MAX_DRIFT_DAYS),
            target,
        ),
    )


def context_before(cur, asset_id: str, cutoff: date) -> dict:
    """Everything the system knew about an asset strictly before a date.

    Every query here carries a `< cutoff`. That is the whole point of the function: it is the
    one place where a date filter is the difference between evidence and hindsight.
    """
    trail = rows(
        cur,
        """
        SELECT close, volume FROM "PriceSnapshot"
        WHERE "assetId" = %s AND date < %s AND close IS NOT NULL
        ORDER BY date DESC LIMIT %s
        """,
        (asset_id, cutoff, TRAIL + 1),
    )
    trailing = None
    vol_ratio = None
    if len(trail) >= TRAIL + 1:
        newest, oldest = float(trail[0]["close"]), float(trail[TRAIL]["close"])
        trailing = pct(newest, oldest)
        vols = [float(r["volume"]) for r in trail[1:] if r["volume"]]
        if vols and trail[0]["volume"]:
            avg = sum(vols) / len(vols)
            if avg > 0:
                vol_ratio = float(trail[0]["volume"]) / avg

    signal = one(
        cur,
        """
        SELECT tone::text AS tone, "recentStories", catalyst FROM "HumanSignal"
        WHERE "assetId" = %s AND "periodEnd" < %s
        ORDER BY "periodEnd" DESC LIMIT 1
        """,
        (asset_id, cutoff),
    )
    setup = one(
        cur,
        """
        SELECT state FROM "AssetSetup"
        WHERE "assetId" = %s AND "periodEnd" < %s
        ORDER BY "periodEnd" DESC LIMIT 1
        """,
        (asset_id, cutoff),
    )
    return {
        "trailingPct": trailing,
        "volumeRatio": vol_ratio,
        "tone": signal["tone"] if signal else None,
        "stories": signal["recentStories"] if signal else None,
        "catalyst": signal["catalyst"] if signal else None,
        "setupState": setup["state"] if setup else None,
    }


def write_state(cur, event_id: str, asset_id: str, phase: str, asOf: date, bar, ctx: dict,
                change: float | None, window: int | None) -> None:
    cur.execute(
        """
        INSERT INTO "EventState" ("eventId", "assetId", phase, "asOf", close, volume,
            "volumeRatio", "trailingPct", tone, stories, catalyst, "setupState",
            "changePct", "windowDays", source, "computedAt")
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT ("eventId", "assetId", phase) DO NOTHING
        """,
        (
            event_id, asset_id, phase, asOf,
            float(bar["close"]) if bar and bar["close"] is not None else None,
            float(bar["volume"]) if bar and bar["volume"] is not None else None,
            ctx.get("volumeRatio"), ctx.get("trailingPct"), ctx.get("tone"),
            ctx.get("stories"), ctx.get("catalyst"), ctx.get("setupState"),
            change, window, LIFECYCLE,
        ),
    )


def main() -> None:
    today = date.today()
    conn = db()
    cur = conn.cursor()
    try:
        step("advance dated events through their life")
        events = rows(
            cur,
            """
            SELECT id, slug, name, date, lifecycle, scheduled, "resolvedAt"
            FROM "Event" ORDER BY date
            """,
        )
        moved: dict[str, int] = {}
        froze = measured = 0

        for e in events:
            when: date = e["date"]
            current = e["lifecycle"]

            if not e["scheduled"]:
                target = "historical"
            elif when > today + timedelta(days=APPROACHING_DAYS):
                target = "upcoming"
            elif when > today:
                target = "approaching"
            elif when == today:
                target = "live"
            elif when < today - timedelta(days=HISTORICAL_AFTER_DAYS):
                target = "historical"
            else:
                target = "resolved"

            # A past scheduled event needs its before-state frozen, exactly once, and its
            # after-state measured when the window has elapsed. ON CONFLICT DO NOTHING on
            # EventState is what makes this safe to run twice.
            if e["scheduled"] and when < today:
                linked = rows(
                    cur,
                    'SELECT "assetId" FROM "EventLink" WHERE "eventId" = %s '
                    'AND "assetId" IS NOT NULL',
                    (e["id"],),
                )
                for link in linked:
                    asset_id = link["assetId"]
                    before = close_near(cur, asset_id, when, before_only=True)
                    if not before:
                        continue
                    ctx = context_before(cur, asset_id, when)
                    write_state(cur, e["id"], asset_id, "before", before["date"], before,
                                ctx, None, None)
                    froze += 1

                    if when + timedelta(days=WINDOW_DAYS) <= today:
                        after = close_near(cur, asset_id, when + timedelta(days=WINDOW_DAYS))
                        if after:
                            change = pct(float(after["close"]), float(before["close"]))
                            # The after row carries no context: the question it answers is
                            # what the price did, and filling it with today's news reading
                            # would mix the two phases this table exists to separate.
                            write_state(cur, e["id"], asset_id, "after", after["date"],
                                        after, {}, change, WINDOW_DAYS)
                            measured += 1

            if target != current:
                cur.execute(
                    'UPDATE "Event" SET lifecycle = %s, "resolvedAt" = '
                    'CASE WHEN %s IN (%s, %s) AND "resolvedAt" IS NULL THEN now() '
                    'ELSE "resolvedAt" END WHERE id = %s',
                    (target, target, "resolved", "historical", e["id"]),
                )
                moved[f"{current}->{target}"] = moved.get(f"{current}->{target}", 0) + 1
        conn.commit()

        if moved:
            for k, v in sorted(moved.items()):
                print(f"  {k:28} {v}")
        else:
            print("  no event changed state")
        print(f"  froze {froze} before-states, measured {measured} after-states")

        for got in rows(
            cur,
            'SELECT lifecycle, count(*) AS n FROM "Event" GROUP BY lifecycle ORDER BY lifecycle',
        ):
            print(f"  now {got['lifecycle']:12} {got['n']:>4}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
