"""Come back to each logged reading and measure what actually happened after it.

This is the half of the accuracy loop that cannot be rushed. jobs/human.py writes a reading
on the day it is generated; this job returns 30 and 60 days later and stores the price move
that followed, measured from the close the log recorded at the time.

It stores a measurement and nothing else. A move that followed a reading is not a score for
that reading: coverage turning positive and a price rising in the same month is two things
happening, and this table is the record that has to exist before anyone can honestly say
whether the two have travelled together. Principle 7 asks for the check; principle 4 forbids
dressing the result up as a rule.

Nothing is filled in. A row whose window has not elapsed stays open, a row with no price
series stays unmeasurable, and a row whose window falls in a gap in the stored prices keeps
its null rather than borrowing a nearby close beyond MAX_DRIFT_DAYS.

Run: python jobs/accuracy.py
Writes: SignalLog.move30Pct, measured30On, move60Pct, measured60On, status
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import (  # noqa: E402
    db,
    mean,
    median,
    one,
    pct,
    rows,
    step,
)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass


HORIZONS = (30, 60)

# How far either side of the target day a close may be taken from. A 30 day window landing
# on a weekend or a holiday has its nearest close a day or two out; five days covers a long
# weekend without quietly turning a 30 day measurement into a 37 day one.
MAX_DRIFT_DAYS = 5

# Below this many measured rows no rate is printed. The whole point of the log is to make a
# claim checkable, and a rate over four rows is not checkable. This is the same judgement
# MIN_COUNT_BASE makes about Reddit counts, applied to the accuracy figures themselves.
MIN_MEASURED = 20


def close_near(cur, asset_id: str, target: date):
    """The stored close nearest a target date, within MAX_DRIFT_DAYS either side.

    Either side rather than only before, for the same reason events.py looks both ways: a
    window ending on a Saturday has its nearest observation on the Monday, and refusing to
    look forward would silently shorten every weekend window.
    """
    return one(
        cur,
        """
        SELECT date, close FROM "PriceSnapshot"
        WHERE "assetId" = %s AND date BETWEEN %s AND %s AND close IS NOT NULL
        ORDER BY abs(date - %s::date) ASC, date ASC
        LIMIT 1
        """,
        (
            asset_id,
            target - timedelta(days=MAX_DRIFT_DAYS),
            target + timedelta(days=MAX_DRIFT_DAYS),
            target,
        ),
    )


def measure(cur, today: date) -> dict[str, int]:
    counts = {"measured30": 0, "measured60": 0, "still_open": 0, "no_close": 0}

    pending = rows(
        cur,
        """
        SELECT id, "assetId", "issuedOn", "baseClose", "move30Pct", "move60Pct", status
        FROM "SignalLog"
        WHERE "baseClose" IS NOT NULL AND "assetId" IS NOT NULL
          AND status IN ('open', 'measured30')
        ORDER BY "issuedOn"
        """,
    )

    for r in pending:
        updates: list[tuple[str, object]] = []
        status = r["status"]

        for horizon in HORIZONS:
            col = f"move{horizon}Pct"
            if r[col] is not None:
                continue
            target = r["issuedOn"] + timedelta(days=horizon)
            if target > today:
                continue
            got = close_near(cur, r["assetId"], target)
            if not got:
                # The window has passed but no close sits near it. Left null on purpose:
                # this is a hole in the stored prices, not a move of zero.
                counts["no_close"] += 1
                continue
            move = pct(float(got["close"]), float(r["baseClose"]))
            if move is None:
                counts["no_close"] += 1
                continue
            updates.append((col, move))
            updates.append((f"measured{horizon}On", got["date"]))
            status = f"measured{horizon}"
            counts[f"measured{horizon}"] += 1

        if not updates:
            counts["still_open"] += 1
            continue

        sets = ", ".join(f'"{c}" = %s' for c, _ in updates)
        cur.execute(
            f'UPDATE "SignalLog" SET {sets}, status = %s WHERE id = %s',
            (*[v for _, v in updates], status, r["id"]),
        )

    # A product reading can never be measured against a price it does not have. Marked once
    # so the table does not carry rows that look pending forever.
    cur.execute(
        """
        UPDATE "SignalLog" SET status = 'unmeasurable'
        WHERE "baseClose" IS NULL AND status = 'open'
        """,
    )
    return counts


def report(cur) -> None:
    """Print what the log currently supports, and say plainly when that is nothing yet."""
    for horizon in HORIZONS:
        col = f"move{horizon}Pct"
        done = rows(
            cur,
            f'SELECT "{col}" AS m, factors FROM "SignalLog" WHERE "{col}" IS NOT NULL',
        )
        if len(done) < MIN_MEASURED:
            print(
                f"  {horizon} day: {len(done)} measured rows, below the {MIN_MEASURED} "
                "needed to report a rate. Nothing published."
            )
            continue

        moves = [float(r["m"]) for r in done]
        up = len([m for m in moves if m > 0])
        rising = [
            float(r["m"]) for r in done if "attention=rising" in (r["factors"] or "")
        ]
        print(
            f"  {horizon} day: {len(done)} measured, {up} of them positive, "
            f"mean {mean(moves):+.1f}%, median {median(moves):+.1f}%"
        )
        if len(rising) >= MIN_MEASURED:
            r_up = len([m for m in rising if m > 0])
            print(
                f"    of the {len(rising)} where attention was rising, {r_up} were "
                f"followed by a positive move, mean {mean(rising):+.1f}%"
            )
        else:
            print(
                f"    attention-rising subset has {len(rising)} rows, too few to split out"
            )


def main() -> None:
    today = date.today()
    conn = db()
    with conn, conn.cursor() as cur:
        step("measure what followed each logged reading")
        counts = measure(cur, today)
        print(
            f"  newly measured: {counts['measured30']} at 30 days, "
            f"{counts['measured60']} at 60 days"
        )
        print(
            f"  still open: {counts['still_open']}, "
            f"windows with no nearby close: {counts['no_close']}"
        )
        step("what the log supports so far")
        report(cur)


if __name__ == "__main__":
    main()
