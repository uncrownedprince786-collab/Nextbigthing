"""Pakistan Stock Exchange daily closes, from the exchange's own published files.

Source, verified on 2026-09-30:

    https://dps.psx.com.pk/download/mkt_summary/YYYY-MM-DD.Z

is an archive holding one pipe delimited file, `closing11.lis`, a line per listed symbol:

    31DEC2021|OGDC|0820|Oil & Gas Dev.|84.20|87.30|84.15|86.20|3368560|84.94|||
    date      sym   sec  name           open  high  low   close volume   prev

No key, no cookie, no CAPTCHA. Probed one date at a time on 2026-10-03, the archive runs
back to 2013-11-04: that date and every trading day after it answer 200, while 2013-11-01
and every date before it answer 404 with an HTML error page. Weekends and public holidays
404 throughout. So depth was never the exchange's limit — it was this job's, which asked
for one file a month before the recent window and left every PSX asset with about 178
stored closes against the 220 jobs/horizons.py needs. See DEEP_DAYS.

The container changes partway through that range, which is the trap. 2019 onward is a ZIP;
2013-11 to 2018 is gzip, same `.Z` URL, same `closing11.lis` inside, same pipe layout. A
reader that only knew ZIP did not raise on a gzip file so much as report that day as a
market holiday, so the archive looked shallower than it is. unpack() sniffs the magic bytes
instead of branching on the date.

Two things this job will not do:

  * It does not invent a historical market capitalisation. The share count published on
    dps.psx.com.pk is a current figure with no history behind it, and multiplying today's
    share count by a 2021 price would produce a number that was never true. Size is
    therefore written only against the most recent close, exactly as crypto already works,
    and the pre-AI size table shows these sectors as having no figure rather than a wrong
    one.
  * It does not fill a missing trading day. A 404 is a day the exchange did not publish,
    which is a closed market, not a zero.

Run: python jobs/psx.py [recent|full]
    recent  the snapshot dates and the last 120 days. Enough for current price, the
            60 day volume check and the 24 month relative return.
    full    the above, plus every weekday back DEEP_DAYS so a longer horizon read can
            exist at all, plus a monthly grid over the years before that, which fills the
            price history chart. Historical files never change, so a date already stored
            is never asked for again and a rerun costs only the days that have newly aged
            out of the recent window.
"""

from __future__ import annotations

import gzip
import io
import re
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import RISING_MONTHS, SNAPSHOTS, db, get, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

PSX = "psx"
CLOSING = "Pakistan Stock Exchange daily closing file"
COMPANY = "Pakistan Stock Exchange company page"
BASE = "https://dps.psx.com.pk/download/mkt_summary"

# How far back the daily grid runs. 120 calendar days is about 85 trading days, which
# covers the 60 day average volume window on both sides of a long weekend.
RECENT_DAYS = 120
# A closed market gives a 404, so a target date walks backwards this many days looking for
# the last day that did trade. Eid and Muharram holidays can close the exchange for the
# better part of a week, and a run of public holidays either side of a weekend is the
# longest gap in the published files.
BACKTRACK = 9
HISTORY_FROM = date(2019, 1, 1)
# The first date the archive answers 200 for, pinned by probing single days rather than
# assumed. Nothing here reaches back this far yet; it is written down so the next person to
# want more history knows the floor is the exchange's and not a guess.
ARCHIVE_FROM = date(2013, 11, 4)

# How deep the dense daily stretch runs, in calendar days.
#
# The number this has to clear is jobs/horizons.py: MIN_LONG = LONG_SLOW + 20 = 220 stored
# closes before it will write a longer horizon read at all, and it asks for LONG_RANGE + 40
# = 540 so the 500 session range and the 200 day average are both read from a full window.
# The sentence it publishes against every one of those reads says "across two years", so
# stopping at the 220 minimum would make that line untrue for PSX while it is true for every
# US asset.
#
# PSX trades Monday to Friday and closes for roughly thirteen public holidays a year, so a
# calendar year yields about 248 sessions and 540 sessions needs about 795 calendar days.
# 820 is that with a fortnight of slack, so a year with a long Eid and a long Muharram still
# clears 540 rather than landing just under it.
DEEP_DAYS = 820
# jobs/horizons.py's MIN_LONG, restated so this job can report whether it has cleared it.
# Not imported: that would make a price fetcher load the reasoning job and everything under
# it to print one line. A test pins the two together instead, so the copy cannot drift.
LONGER_MIN_CLOSES = 220
# What counts as a date already filled, as a fraction of the symbols being tracked. A run
# that died mid-batch left a date holding a handful of rows and must be asked for again; a
# quiet session on which a few small caps genuinely did not trade must not be, or every run
# would refetch the same dates forever. Two thirds separates the two cases cleanly: no real
# PSX session leaves a third of this list untraded, and a half finished batch is far below it.
FILLED_FRACTION = 2 / 3
# How many new dense files one run may fetch.
#
# Measured on the first deep run rather than chosen: this host answered the 121 recent days
# and all 471 deep weekdays, then began refusing at the connection level. Every request after
# roughly six hundred in one session came back URLError, which spent the retry budget in
# jobs/nbt.py and left the monthly grid behind it failing too. Nothing was lost — a stored
# date is never refetched and nothing here deletes — but a run that provokes a refusal is a
# run whose later steps are decided by the exchange rather than by this job.
#
# So the dense pass takes a bounded bite. 250 keeps a run's total under four hundred, well
# inside what did answer, and costs nothing in reach: deep_dates walks newest first and skips
# what is stored, so two runs cover the whole of DEEP_DAYS and every run after that pays only
# for the days that have newly aged out of the recent window.
DEEP_FETCH_BUDGET = 250

# The two containers the archive uses behind the same `.Z` name. Sniffed, not inferred from
# the date, because the crossover is the exchange's business and a date it ever re-publishes
# in the other format still has to read.
ZIP_MAGIC = b"PK\x03\x04"
GZIP_MAGIC = b"\x1f\x8b"


def file_url(day: date) -> str:
    return f"{BASE}/{day.isoformat()}.Z"


def unpack(raw: bytes) -> str | None:
    """The `closing11.lis` text inside one archive, or None if this is not an archive.

    A 404 from this host is an HTML error page rather than an empty body, so the magic byte
    check is also what stops an error page being parsed as a very short trading day.
    """
    try:
        if raw.startswith(ZIP_MAGIC):
            zf = zipfile.ZipFile(io.BytesIO(raw))
            return zf.read(zf.namelist()[0]).decode("utf-8", "replace")
        if raw.startswith(GZIP_MAGIC):
            return gzip.decompress(raw).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - a corrupt archive is a missing day, not a crash
        return None
    return None


def ttl_for(day: date, today: date) -> int:
    """A published file for a past day never changes, so old ones are cached for a year.

    Only the last fortnight is refetched, which is what keeps a `full` rerun cheap.
    """
    return 3600 * 6 if (today - day).days <= 14 else 3600 * 24 * 365


def read_day(
    day: date, today: date, keep: frozenset[str] | None = None
) -> dict[str, dict] | None:
    """One day's closing file as {symbol: row}, or None when the exchange published nothing.

    `keep` is the symbol set being tracked, and rows outside it are dropped as they are read.
    The whole exchange is about 600 symbols against the 70 this project follows, and a dense
    DEEP_DAYS stretch holds every one of those days in memory at once while the network phase
    runs. Keeping all 600 is the difference between tens of megabytes and hundreds.

    Published-but-nothing-of-ours is therefore a real outcome, and it returns an empty dict
    rather than None. The two must stay distinct: None means the market was closed and the
    caller should keep walking backwards, while {} means the market traded and it should stop.
    Collapsing them is how a backtrack walks straight past a real session.
    """
    raw = get(file_url(day), cache_key=f"psx-{day.isoformat()}", ttl=ttl_for(day, today))
    if not raw:
        return None
    text = unpack(raw)
    if text is None:
        print(f"  {day}: unreadable archive, {len(raw)} bytes")
        return None

    out: dict[str, dict] = {}
    for line in text.splitlines():
        f = line.split("|")
        if len(f) < 10 or not f[1]:
            continue
        symbol = f[1].strip().upper()
        if keep is not None and symbol not in keep:
            continue
        try:
            close = float(f[7])
            volume = float(f[8])
        except ValueError:
            continue
        # A symbol that did not trade is published with a zero close. That is a market
        # state, not a price, and storing it would put a vertical drop in the chart.
        if close <= 0:
            continue

        # open, high and low sit at 4, 5 and 6 and were being dropped. A zero here is the
        # same "did not trade" marker the close uses, so it becomes None rather than a price.
        def bar(idx: int) -> float | None:
            try:
                v = float(f[idx])
            except (ValueError, IndexError):
                return None
            return v if v > 0 else None

        out[symbol] = {
            "open": bar(4),
            "high": bar(5),
            "low": bar(6),
            "close": close,
            "volume": volume,
            "name": f[3].strip(),
        }
    return out


def dense_dates(today: date) -> list[date]:
    """Every day of the recent stretch. Most are trading days, so all of them are asked
    for and the weekends simply come back as a 404."""
    return [today - timedelta(days=i) for i in range(RECENT_DAYS + 1)]


def deep_start(today: date) -> date:
    """The oldest day the dense stretch reaches, floored at the era this job reads."""
    return max(HISTORY_FROM, today - timedelta(days=DEEP_DAYS))


def deep_dates(today: date, known: frozenset[date] = frozenset()) -> list[date]:
    """Every weekday between the dense stretch and the recent window, minus what is stored.

    Two subtractions, and both are the difference between a run that costs a quarter of an
    hour once and one that costs it every week.

    Weekends are dropped rather than asked for and 404ed. The recent window still asks for
    all seven days, because there the 404s are what prove the host is answering at all and
    the silence guard counts on them; out here, 230 guaranteed misses are just six minutes of
    the exchange's time and ours.

    `known` is the dates already stored deeply enough to be finished. Historical files never
    change, so a date that is in the database is a date that never needs fetching again, and
    skipping it is what makes the second run cheap without relying on the disk cache having
    survived between them. The recent window is deliberately outside this: the last days are
    still being revised, and they are refetched on their own TTL.

    What this cannot skip is a public holiday. The exchange published no file, so there is no
    row, so nothing marks the day as settled and every later run asks again. Measured against
    the filled window that is 23 requests a run, which is cheaper than the alternative: a
    table of days known to be empty is a second record of what the archive says, and it would
    go stale the first time the exchange backfilled a date it had missed.

    Newest first, and capped at DEEP_FETCH_BUDGET: a run cut short, by its own budget or by
    the host, has left the most useful depth behind rather than a hole next to the present.
    """
    out: list[date] = []
    first, last = deep_start(today), today - timedelta(days=RECENT_DAYS + 1)
    day = last
    while day >= first and len(out) < DEEP_FETCH_BUDGET:
        # weekday() 5 and 6 are Saturday and Sunday. The exchange has never published either.
        if day.weekday() < 5 and day not in known:
            out.append(day)
        day -= timedelta(days=1)
    return out


def anchor_dates(today: date, mode: str) -> list[date]:
    """Dates the site needs a close *near*, rather than on.

    Each of these is resolved by walking backwards to the last day the exchange published,
    so a snapshot that lands on Eid costs two requests rather than ten. Asking for all
    BACKTRACK days of every anchor would be roughly 900 requests for the monthly grid
    alone, nearly all of them 404s.
    """
    out = [snap for snap in SNAPSHOTS if snap <= today]
    out.append(today - timedelta(days=RISING_MONTHS * 30))

    if mode == "full":
        # One reading a month draws a seven year line in about 90 files, where a daily
        # backfill would be nearly 2,000. It stops where deep_dates starts: inside that
        # stretch every day is already being asked for, and a monthly anchor there would
        # only add backtracking work over days the dense pass has read anyway.
        stop = deep_start(today)
        cursor = HISTORY_FROM
        while cursor < stop:
            out.append(cursor)
            year, month = cursor.year + (cursor.month // 12), cursor.month % 12 + 1
            cursor = date(year, month, 1)

    return [d for d in out if HISTORY_FROM <= d <= today]


# The Equity Profile block is plain server rendered markup:
#   <div class="stats_label">Shares</div><div class="stats_value">4,300,928,400</div>
# The label is matched exactly, because "Free Float" sits in the same block with the same
# classes and a looser pattern picks it up instead.
SHARES_RE = re.compile(
    r'stats_label">\s*Shares\s*</div>\s*<div class="stats_value">\s*([\d,]+)'
)


def shares_outstanding(symbol: str) -> float | None:
    """Current share count from the company page. There is no history behind this figure.

    Used only against the newest close. Applying it to an older price would invent a market
    capitalisation for a date whose share count nobody published.
    """
    raw = get(
        f"https://dps.psx.com.pk/company/{symbol}",
        cache_key=f"psx-company-{symbol}",
        ttl=3600 * 24 * 7,
    )
    if not raw:
        return None
    html = raw.decode("utf-8", "replace")
    m = SHARES_RE.search(html)
    if not m:
        # Some listings publish no share count at all. That asset keeps its price and its
        # returns and simply has no size figure, which the industry page states in words.
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return n if n > 0 else None


def insert(cur, buffer: list[tuple]) -> int:
    if not buffer:
        return 0
    cur.executemany(
        """
        INSERT INTO "PriceSnapshot" ("assetId", date, open, high, low, close, volume,
                                     "marketCap", source)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT ("assetId", date) DO UPDATE
        SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, volume = EXCLUDED.volume,
            "marketCap" = COALESCE(EXCLUDED."marketCap", "PriceSnapshot"."marketCap"),
            source = EXCLUDED.source
        """,
        buffer,
    )
    return len(buffer)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "recent"
    if mode not in ("recent", "full"):
        print(f"unknown mode {mode}, choose recent or full")
        raise SystemExit(2)

    today = date.today()

    # The three phases below exist because of one rule: no database connection is held open
    # while this job is on the network. `full` spends the better part of ten minutes fetching,
    # and a transaction left open across that is a session sitting idle in transaction for
    # minutes at a time. Serverless Postgres closes those, and the failure surfaces as an
    # exception on the *next* statement, which rolls the whole run back — minutes of fetching
    # discarded, and nothing stored to show for it.
    #
    # So: ask what to fetch, hang up. Fetch. Reconnect and write.

    # --- phase 1: what to fill. Two questions, and then the connection goes away.
    conn = db()
    with conn, conn.cursor() as cur:
        assets = rows(
            cur,
            'SELECT id, symbol, name FROM "Asset" WHERE source = %s ORDER BY symbol',
            (PSX,),
        )
        # Which dates in the dense stretch are already filled. Asked once, as a set, rather
        # than per date in the fetch loop: the whole point of the phase split is that no
        # connection is open while the network is being used, and a query per day would be
        # six hundred round trips before a single file is fetched.
        filled = []
        if assets:
            filled = rows(
                cur,
                """
                SELECT date FROM "PriceSnapshot"
                WHERE source = %s AND date >= %s
                GROUP BY date HAVING count(*) >= %s
                """,
                (CLOSING, deep_start(today), max(1, int(len(assets) * FILLED_FRACTION))),
            )
    conn.close()

    if not assets:
        print("no PSX assets seeded, nothing to do")
        return
    by_symbol = {a["symbol"].upper(): a for a in assets}
    wanted = frozenset(by_symbol)
    known = frozenset(r["date"] for r in filled)
    print(f"  {len(by_symbol)} PSX symbols to fill")

    # --- phase 2: every request this job makes, with nothing to time out behind it.
    step(f"daily closing files ({mode})")
    cache: dict[date, dict | None] = {}
    asked = 0

    def load(day: date):
        """One day, read once however many callers want it."""
        nonlocal asked
        if day not in cache:
            asked += 1
            cache[day] = read_day(day, today, wanted)
        return cache[day]

    def resolve(anchor: date) -> date | None:
        """The last published day on or before an anchor, or None if the run of
        closed days is longer than BACKTRACK."""
        for back in range(BACKTRACK + 1):
            day = anchor - timedelta(days=back)
            if day < HISTORY_FROM or day > today:
                continue
            # `is not None` and not truthiness: a published day on which none of the tracked
            # symbols traded is still a published day, and walking past it would land this
            # anchor on an older close while reporting it as the nearest one.
            if load(day) is not None:
                return day
        return None

    # The order these three run in is the order a run that dies halfway leaves something
    # useful behind: current prices first, then depth newest first, then the old monthly line.
    found: set[date] = {d for d in dense_dates(today) if load(d) is not None}

    deep = deep_dates(today, known) if mode == "full" else []
    if deep:
        print(
            f"  {len(deep)} weekdays to fetch between {deep[-1]} and {deep[0]}"
            + (
                f", the per-run cap, so the rest back to {deep_start(today)} follows next run"
                if len(deep) >= DEEP_FETCH_BUDGET
                else f", which reaches {deep_start(today)}"
            )
        )
        found |= {d for d in deep if load(d) is not None}

    found |= {r for a in anchor_dates(today, mode) if (r := resolve(a))}

    # Newest first, so a write cut short still leaves current prices behind.
    targets: list[date] = sorted(found, reverse=True)

    traded = 0
    latest_day: date | None = None
    latest_rows: dict[str, dict] = {}
    batches: list[list[tuple]] = []
    buffer: list[tuple] = []

    for day in targets:
        got = cache[day]
        if got is None:
            continue
        traded += 1
        if got and (latest_day is None or day > latest_day):
            latest_day, latest_rows = day, got
        for sym, a in by_symbol.items():
            row = got.get(sym)
            if not row:
                # The symbol did not trade that day, or was not listed yet. Either way
                # there is no close to store.
                continue
            buffer.append(
                (
                    a["id"], day, row["open"], row["high"], row["low"],
                    row["close"], row["volume"], None, CLOSING,
                )
            )
        if len(buffer) >= 2000:
            batches.append(buffer)
            buffer = []
    if buffer:
        batches.append(buffer)
    print(f"  {traded} trading days read, {asked} dates requested")
    if asked and traded == 0:
        # RECENT_DAYS is 120, so the window asked about is four months. An exchange with no
        # published day in four months is not a holiday, it is the source refusing this host,
        # and a run that reports it is worth more than one that writes nothing and exits 0.
        # The same line jobs/prices.py draws for Yahoo and Binance, and jobs/marketplace.py
        # for Amazon.
        print(
            f"no closing file from PSX for any of {asked} dates: treat it as unavailable from "
            "this host and re-verify it before trusting a later run"
        )
        raise SystemExit(1)

    step("share counts")
    shares_by_symbol: dict[str, float] = {}
    missing = 0
    if latest_day is None:
        print("  no trading day found, so no size figure is written")
    else:
        for sym in by_symbol:
            if sym not in latest_rows:
                continue
            shares = shares_outstanding(sym)
            if shares is None:
                missing += 1
                continue
            shares_by_symbol[sym] = shares

    # --- phase 3: a fresh connection, and writes only. Committed per batch so a connection
    # lost late in the run keeps the prices already written rather than discarding them.
    step("write")
    conn = db()
    cur = conn.cursor()
    try:
        stored = 0
        for batch in batches:
            stored += insert(cur, batch)
            conn.commit()
        print(f"  {stored} rows written over {traded} trading days")

        sized = 0
        for sym, shares in shares_by_symbol.items():
            cur.execute(
                """
                UPDATE "PriceSnapshot" SET "marketCap" = %s
                WHERE "assetId" = %s AND date = %s
                """,
                (latest_rows[sym]["close"] * shares, by_symbol[sym]["id"], latest_day),
            )
            sized += cur.rowcount
        conn.commit()

        if latest_day is not None:
            print(
                f"  market cap on {latest_day} for {sized} assets"
                + (f", {missing} publish no share count" if missing else "")
            )
            print(
                "  no size figure is written for any earlier date: the published share "
                "count has no history, so an older one would be invented"
            )

        cur.execute(
            """
            SELECT count(*) AS n, min(date) AS lo, max(date) AS hi
            FROM "PriceSnapshot" WHERE source = %s
            """,
            (CLOSING,),
        )
        got = cur.fetchone()
        print(f"\nPSX snapshots stored: {got['n']} from {got['lo']} to {got['hi']}")

        # Depth per symbol, because the count above cannot tell a deep history from a wide
        # one. This is the number that decides whether a longer horizon read exists at all,
        # so the run says it out loud rather than leaving it to be discovered in horizons.
        cur.execute(
            """
            SELECT min(n) AS lo, round(avg(n)) AS avg, max(n) AS hi,
                   count(*) FILTER (WHERE n >= %s) AS deep, count(*) AS assets
            FROM (SELECT count(*) AS n FROM "PriceSnapshot" p
                  JOIN "Asset" a ON a.id = p."assetId"
                  WHERE a.source = %s AND p.close IS NOT NULL
                  GROUP BY p."assetId") t
            """,
            (LONGER_MIN_CLOSES, PSX),
        )
        d = cur.fetchone()
        print(
            f"closes per symbol: {d['lo']} lowest, {d['avg']} average, {d['hi']} highest. "
            f"{d['deep']} of {d['assets']} now carry the {LONGER_MIN_CLOSES} "
            "jobs/horizons.py needs for a longer horizon read"
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
