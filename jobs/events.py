"""What the market did in the window after a dated event.

This is the one part of the site where the reader is most likely to supply a causal story
the data does not contain, so the rules here are tighter than anywhere else:

  * The event list is seeded by hand from the public record, with a source URL for the
    date. Nothing detects events, because a detector would be picking the events that fit
    the moves, which is the whole error this section exists to avoid.
  * An impact row is a price change between two stored closes over a fixed window that
    begins on the event date. That is all it is.
  * The job never writes that the event caused the move, and `jobs/analysis.py` builds its
    sentences from the same rule. Assets move for reasons that have nothing to do with any
    headline, and in a 30 day window most of them did.
  * An asset with no stored close near either end of the window gets no row, so an event
    predating the stored history produces an empty section rather than a short one that
    looks complete.

The honest claim available from a price series is "these were the largest measured moves
in the window", and that is the only claim stored.

Run: python jobs/events.py
Writes: Event (idempotent seed), EventImpact (deleted and rebuilt each run)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, one, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

MEASURED = "measured from stored closes"

# The window measured after each event, in days. Two lengths, because a move that shows up
# at 14 days and has gone by 30 is a different observation from one still there at 30, and
# showing both stops a single window being read as the answer.
WINDOWS = (14, 30)

# How far from the ideal date a stored close may sit before the row is dropped. A close
# four trading days from the window end is still that window; one three weeks away is a
# different measurement wearing its label.
MAX_DRIFT_DAYS = 6

# Enough assets have to be measurable for a ranking of the largest movers to mean anything.
PEERS_HIGH = 40
PEERS_MEDIUM = 15

# slug, name, date, category, summary, source, sourceUrl
#
# Dates are the ones in the public record, each checkable at the URL beside it. The
# summaries say what happened and stop there: no line here explains a market, because the
# moment a seed file starts explaining, every number under it inherits the explanation.
EVENTS = [
    (
        "russia-invades-ukraine",
        "Russia's invasion of Ukraine begins",
        date(2022, 2, 24),
        "conflict",
        "Russian forces entered Ukraine on 24 February 2022. Sanctions on Russian banks "
        "and energy exports followed over the weeks after.",
        "Wikipedia, Russian invasion of Ukraine",
        "https://en.wikipedia.org/wiki/Russian_invasion_of_Ukraine",
    ),
    (
        "chatgpt-launch",
        "ChatGPT is released publicly",
        date(2022, 11, 30),
        "technology",
        "OpenAI released ChatGPT as a free public research preview on 30 November 2022.",
        "Wikipedia, ChatGPT",
        "https://en.wikipedia.org/wiki/ChatGPT",
    ),
    (
        "svb-failure",
        "Silicon Valley Bank is closed by regulators",
        date(2023, 3, 10),
        "market",
        "California regulators closed Silicon Valley Bank on 10 March 2023 and the FDIC "
        "was appointed receiver. Signature Bank was closed two days later.",
        "Wikipedia, Collapse of Silicon Valley Bank",
        "https://en.wikipedia.org/wiki/Collapse_of_Silicon_Valley_Bank",
    ),
    (
        "israel-hamas-war",
        "The Gaza war begins",
        date(2023, 10, 7),
        "conflict",
        "Hamas launched an attack on southern Israel on 7 October 2023 and Israel "
        "declared war the following day.",
        "Wikipedia, Gaza war",
        "https://en.wikipedia.org/wiki/Gaza_war",
    ),
    (
        "nvidia-blackwell",
        "NVIDIA announces the Blackwell architecture",
        date(2024, 3, 18),
        "technology",
        "NVIDIA announced the Blackwell GPU architecture at its GTC conference on "
        "18 March 2024.",
        "Wikipedia, Blackwell (microarchitecture)",
        "https://en.wikipedia.org/wiki/Blackwell_(microarchitecture)",
    ),
    (
        "fed-first-cut-2024",
        "The Federal Reserve cuts rates for the first time since 2020",
        date(2024, 9, 18),
        "policy",
        "The Federal Open Market Committee lowered the federal funds target range by "
        "0.5 percentage points on 18 September 2024, its first cut since March 2020.",
        "Federal Reserve, FOMC statement of 18 September 2024",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20240918a.htm",
    ),
    (
        "deepseek-r1",
        "DeepSeek releases R1",
        date(2025, 1, 27),
        "technology",
        "DeepSeek's R1 model reached the top of the US App Store free chart on "
        "27 January 2025, the day of a broad selloff in AI related equities.",
        "Wikipedia, DeepSeek",
        "https://en.wikipedia.org/wiki/DeepSeek",
    ),
    (
        "us-tariffs-2025",
        "The United States announces broad reciprocal tariffs",
        date(2025, 4, 2),
        "policy",
        "The US administration announced a baseline tariff on imports with higher rates "
        "for named trading partners on 2 April 2025.",
        "Wikipedia, Tariffs in the second Trump administration",
        "https://en.wikipedia.org/wiki/Tariffs_in_the_second_Trump_administration",
    ),
]


def seed(cur) -> None:
    step("events")
    for sort, (slug, name, when, category, summary, source, url) in enumerate(EVENTS, 1):
        cur.execute(
            """
            INSERT INTO "Event" (slug, name, summary, date, category, source,
                                 "sourceUrl", sort, "createdAt")
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (slug) DO UPDATE
            SET name = EXCLUDED.name, summary = EXCLUDED.summary, date = EXCLUDED.date,
                category = EXCLUDED.category, source = EXCLUDED.source,
                "sourceUrl" = EXCLUDED."sourceUrl", sort = EXCLUDED.sort
            """,
            (slug, name, summary, when, category, source, url, sort),
        )
    print(f"  {len(EVENTS)} events seeded")


def close_near(cur, asset_id: str, target: date):
    """The stored close nearest to a target date, within MAX_DRIFT_DAYS either side.

    Either side, not just before: an event dated to a Saturday has its nearest close on the
    Monday, and refusing to look forward would silently shift every weekend event's window
    start back into the previous week.
    """
    return one(
        cur,
        """
        SELECT date, close, volume FROM "PriceSnapshot"
        WHERE "assetId" = %s AND date BETWEEN %s AND %s
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


def avg_volume(cur, asset_id: str, end: date, days: int = 20):
    got = one(
        cur,
        """
        SELECT avg(volume) AS v FROM "PriceSnapshot"
        WHERE "assetId" = %s AND date <= %s AND date > %s AND volume IS NOT NULL
        """,
        (asset_id, end, end - timedelta(days=days)),
    )
    return got["v"] if got and got["v"] else None


def grade(peers: int, drift: int, volume_known: bool) -> tuple[str, str]:
    """How well measured one impact row is. Never how meaningful it is."""
    bits = [
        f"a price change between two stored closes {peers} assets could also be measured "
        f"over"
    ]
    if drift:
        bits.append(
            f"the nearest stored closes sit {drift} days from the exact window, because "
            f"the market was shut on the dates themselves"
        )
    if not volume_known:
        bits.append("no volume was published for this asset, so turnover is not reported")

    if peers >= PEERS_HIGH and drift <= 3 and volume_known:
        return "high", "; ".join(bits)
    if peers >= PEERS_MEDIUM:
        return "medium", "; ".join(bits)
    return "low", "; ".join(bits)


def measure(cur, event) -> int:
    assets = rows(cur, 'SELECT id, symbol, name FROM "Asset" ORDER BY symbol')
    written = 0

    for window in WINDOWS:
        target_end = event["date"] + timedelta(days=window)
        if target_end > date.today():
            # A window that has not finished yet would be measured against a shorter run of
            # days than its label claims.
            print(f"  {event['slug']} {window}d: window has not closed yet, skipped")
            continue

        measured = []
        for a in assets:
            start = close_near(cur, a["id"], event["date"])
            end = close_near(cur, a["id"], target_end)
            if not start or not end or not start["close"]:
                continue
            if end["date"] <= start["date"]:
                # The two anchors resolved to the same close, so there is no window here.
                continue
            change = (end["close"] / start["close"] - 1.0) * 100.0
            v0 = avg_volume(cur, a["id"], start["date"])
            v1 = avg_volume(cur, a["id"], end["date"])
            vol_change = (v1 / v0 - 1.0) * 100.0 if v0 and v1 else None
            drift = abs((start["date"] - event["date"]).days) + abs(
                (end["date"] - target_end).days
            )
            measured.append((a, start, end, change, vol_change, drift))

        peers = len(measured)
        measured.sort(key=lambda t: abs(t[3]), reverse=True)
        for rank, (a, start, end, change, vol_change, drift) in enumerate(measured, 1):
            g, note = grade(peers, drift, vol_change is not None)
            cur.execute(
                """
                INSERT INTO "EventImpact"
                  ("eventId", "assetId", "windowDays", "startDate", "startClose",
                   "endDate", "endClose", "changePct", "volumeChangePct", rank,
                   confidence, "confidenceNote", source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::"Confidence",%s,%s)
                ON CONFLICT ("eventId", "assetId", "windowDays") DO UPDATE
                SET "startDate" = EXCLUDED."startDate", "startClose" = EXCLUDED."startClose",
                    "endDate" = EXCLUDED."endDate", "endClose" = EXCLUDED."endClose",
                    "changePct" = EXCLUDED."changePct",
                    "volumeChangePct" = EXCLUDED."volumeChangePct",
                    rank = EXCLUDED.rank, confidence = EXCLUDED.confidence,
                    "confidenceNote" = EXCLUDED."confidenceNote"
                """,
                (
                    event["id"], a["id"], window, start["date"], start["close"],
                    end["date"], end["close"], change, vol_change, rank, g, note, MEASURED,
                ),
            )
            written += 1
        print(f"  {event['slug']} {window}d: {peers} assets measurable")
    return written


def main() -> None:
    conn = db()
    with conn, conn.cursor() as cur:
        seed(cur)

        step("impacts")
        # Rebuilt rather than updated, because the asset list and the stored history both
        # change between runs and a stale row would keep a rank it no longer holds.
        cur.execute('DELETE FROM "EventImpact"')
        total = 0
        for event in rows(cur, 'SELECT id, slug, date FROM "Event" ORDER BY sort'):
            total += measure(cur, event)
        print(f"\n{total} impact rows written")

        for got in rows(
            cur,
            """
            SELECT e.slug, i."windowDays" AS w, count(*) AS n
            FROM "EventImpact" i JOIN "Event" e ON e.id = i."eventId"
            GROUP BY e.slug, i."windowDays" ORDER BY e.slug, w
            """,
        ):
            print(f"  {got['slug']:28} {got['w']:>3}d {got['n']:>4}")
    conn.close()


if __name__ == "__main__":
    main()
