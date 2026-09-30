"""Dated items that have not happened yet, so a reader is not surprised by a date.

The purpose is memory, not prediction: an earnings report on a known day is the commonest
way a price moves for a reason that was public and forgettable weeks in advance. This job
remembers them.

Source, verified live on 2026-10-01 through yfinance, which is already a dependency and
needs no key:

    Ticker.calendar -> {"Earnings Date": [date], "Dividend Date": date,
                        "Ex-Dividend Date": date, ...}

Confirmed answering for NVDA (earnings 2026-11-18), AAPL (2026-10-30), JPM (2026-10-13).

Rules this job holds to
-----------------------
  * Nothing is invented. A date is written only when the source published it. No estimate is
    derived from last year's date plus a quarter, which would be a fabricated schedule
    wearing a real one's clothes.
  * A scheduled date is marked `scheduled = true` and stays marked after its day passes,
    because a scheduled item whose day has gone is not the same thing as a recorded fact.
  * The provider calls some of these estimated and they move. `notes` says so on the row
    rather than in a footnote somewhere else.
  * No claim is attached about what a date will do to a price. The event is stored; the
    measurement of what followed is jobs/events.py' business, after the fact.

Run: python jobs/upcoming.py
Writes: Event (scheduled), EventLink
"""

from __future__ import annotations

import sys
import time
import warnings
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

warnings.filterwarnings("ignore")

import yfinance as yf  # noqa: E402

CALENDAR = "Yahoo Finance company calendar"

# How far ahead to keep. Beyond a quarter the provider's dates are mostly placeholders that
# move, and a date that moves is worse than no date: it is a reminder set for the wrong day.
HORIZON_DAYS = 120

# What the calendar publishes, and how each one is worded on the site. The relation text is
# factual about why the date is attached, never about what it will do.
KINDS = (
    ("Earnings Date", "earnings", "Scheduled earnings report", "reports earnings on this date"),
    ("Ex-Dividend Date", "dividend", "Ex-dividend date", "trades ex-dividend on this date"),
    ("Dividend Date", "dividend", "Dividend payment date", "pays its dividend on this date"),
)

NOTE = (
    "Published by the provider as a scheduled or expected date. Companies move these, and "
    "the provider does not always publish a time, so treat the day as the claim and not the "
    "hour"
)


def as_dates(value) -> list[date]:
    """Whatever the provider returned, as a list of plain dates. Unparseable means absent."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    out: list[date] = []
    for item in items:
        if isinstance(item, date):
            out.append(item)
        elif hasattr(item, "date"):
            try:
                out.append(item.date())
            except Exception:  # noqa: BLE001
                continue
    return out


def slug_for(symbol: str, category: str, day: date) -> str:
    return f"{symbol.lower()}-{category}-{day.isoformat()}"


def main() -> None:
    today = date.today()
    horizon = today + timedelta(days=HORIZON_DAYS)

    # Phase 1: ask, hang up. This job is minutes of network work.
    conn = db()
    with conn, conn.cursor() as cur:
        assets = rows(
            cur,
            'SELECT id, symbol, name, "sourceRef" FROM "Asset" '
            "WHERE source = 'yahoo' AND \"assetType\" IN ('stock','etf') ORDER BY symbol",
        )
    conn.close()

    if not assets:
        print("no Yahoo-sourced assets, nothing to do")
        return

    step(f"company calendars for {len(assets)} assets")
    found: list[tuple] = []
    silent = 0
    for a in assets:
        try:
            cal = yf.Ticker(a["sourceRef"]).calendar
        except Exception as e:  # noqa: BLE001
            print(f"  {a['symbol']:7} calendar failed: {type(e).__name__}")
            silent += 1
            time.sleep(0.5)
            continue
        if not isinstance(cal, dict):
            silent += 1
            time.sleep(0.5)
            continue

        got = 0
        for key, category, title, relation in KINDS:
            for day in as_dates(cal.get(key)):
                # Only forward, and only inside the horizon. A past date from this source is
                # not a recorded event, it is a stale schedule.
                if day < today or day > horizon:
                    continue
                found.append((a, category, title, relation, day))
                got += 1
        if got:
            print(f"  {a['symbol']:7} {got} dated items")
        else:
            silent += 1
        time.sleep(0.5)

    # Phase 2: write on a fresh connection.
    step("write")
    conn = db()
    cur = conn.cursor()
    try:
        events = links = 0
        for a, category, title, relation, day in found:
            slug = slug_for(a["symbol"], category, day)
            cur.execute(
                """
                INSERT INTO "Event" (slug, name, summary, date, category, source,
                                     "sourceUrl", notes, scheduled, sort)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,true,0)
                ON CONFLICT (slug) DO UPDATE
                SET name = EXCLUDED.name, summary = EXCLUDED.summary,
                    date = EXCLUDED.date, notes = EXCLUDED.notes,
                    scheduled = true, source = EXCLUDED.source,
                    "sourceUrl" = EXCLUDED."sourceUrl"
                RETURNING id
                """,
                (
                    slug,
                    f"{a['name']}: {title.lower()}",
                    f"{title} for {a['name']} ({a['symbol']}) on {day.isoformat()}, as "
                    "published by the provider's company calendar.",
                    day,
                    category,
                    CALENDAR,
                    f"https://finance.yahoo.com/quote/{a['sourceRef']}",
                    NOTE,
                ),
            )
            event_id = cur.fetchone()["id"]
            events += 1

            cur.execute(
                """
                INSERT INTO "EventLink" ("eventId", "assetId", "productId", relation,
                                         "targetRef")
                VALUES (%s,%s,NULL,%s,%s)
                ON CONFLICT ("eventId", "targetRef") DO UPDATE
                SET relation = EXCLUDED.relation
                """,
                (event_id, a["id"], f"{a['name']} {relation}", a["id"]),
            )
            links += 1
        conn.commit()
        print(f"  {events} scheduled events, {links} links, {silent} assets published none")

        cur.execute(
            """
            SELECT category, count(*) AS n, min(date) AS lo, max(date) AS hi
            FROM "Event" WHERE scheduled = true AND date >= %s
            GROUP BY category ORDER BY category
            """,
            (today,),
        )
        for got in cur.fetchall():
            print(f"  upcoming {got['category']:10} {got['n']:>4} from {got['lo']} to {got['hi']}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
