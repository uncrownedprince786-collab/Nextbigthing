"""Pakistan Stock Exchange daily closes, from the exchange's own published files.

Source, verified on 2026-09-30:

    https://dps.psx.com.pk/download/mkt_summary/YYYY-MM-DD.Z

is a ZIP holding one pipe delimited file, `closing11.lis`, with a line per listed symbol:

    31DEC2021|OGDC|0820|Oil & Gas Dev.|84.20|87.30|84.15|86.20|3368560|84.94|||
    date      sym   sec  name           open  high  low   close volume   prev

No key, no cookie, no CAPTCHA, and files exist back to at least 2019-12-31, which covers
every snapshot date the site ranks on. It is the exchange's own end of day record rather
than a scrape of a rendered page, so a layout change cannot silently alter a number.

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
    full    the above plus a monthly grid back to 2019, which fills the price history
            chart. Historical files never change, so this is cached hard and a rerun is
            nearly free.
"""

from __future__ import annotations

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


def file_url(day: date) -> str:
    return f"{BASE}/{day.isoformat()}.Z"


def ttl_for(day: date, today: date) -> int:
    """A published file for a past day never changes, so old ones are cached for a year.

    Only the last fortnight is refetched, which is what keeps a `full` rerun cheap.
    """
    return 3600 * 6 if (today - day).days <= 14 else 3600 * 24 * 365


def read_day(day: date, today: date) -> dict[str, dict] | None:
    """One day's closing file as {symbol: row}, or None when the market did not trade."""
    raw = get(file_url(day), cache_key=f"psx-{day.isoformat()}", ttl=ttl_for(day, today))
    if not raw:
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        text = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - a corrupt archive is a missing day, not a crash
        print(f"  {day}: unreadable archive, {type(e).__name__}")
        return None

    out: dict[str, dict] = {}
    for line in text.splitlines():
        f = line.split("|")
        if len(f) < 10 or not f[1]:
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

        out[f[1].strip().upper()] = {
            "open": bar(4),
            "high": bar(5),
            "low": bar(6),
            "close": close,
            "volume": volume,
            "name": f[3].strip(),
        }
    return out or None


def dense_dates(today: date) -> list[date]:
    """Every day of the recent stretch. Most are trading days, so all of them are asked
    for and the weekends simply come back as a 404."""
    return [today - timedelta(days=i) for i in range(RECENT_DAYS + 1)]


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
        # backfill would be nearly 2,000.
        cursor = HISTORY_FROM
        while cursor < today:
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

    # --- phase 1: what to fill. A question, and then the connection goes away.
    conn = db()
    with conn, conn.cursor() as cur:
        assets = rows(
            cur,
            'SELECT id, symbol, name FROM "Asset" WHERE source = %s ORDER BY symbol',
            (PSX,),
        )
    conn.close()

    if not assets:
        print("no PSX assets seeded, nothing to do")
        return
    by_symbol = {a["symbol"].upper(): a for a in assets}
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
            cache[day] = read_day(day, today)
        return cache[day]

    def resolve(anchor: date) -> date | None:
        """The last published day on or before an anchor, or None if the run of
        closed days is longer than BACKTRACK."""
        for back in range(BACKTRACK + 1):
            day = anchor - timedelta(days=back)
            if day < HISTORY_FROM or day > today:
                continue
            if load(day):
                return day
        return None

    # Newest first, so a run cut short still leaves current prices behind.
    targets: list[date] = sorted(
        {d for d in dense_dates(today) if load(d)}
        | {r for a in anchor_dates(today, mode) if (r := resolve(a))},
        reverse=True,
    )

    traded = 0
    latest_day: date | None = None
    latest_rows: dict[str, dict] = {}
    batches: list[list[tuple]] = []
    buffer: list[tuple] = []

    for day in targets:
        got = cache[day]
        if not got:
            continue
        traded += 1
        if latest_day is None or day > latest_day:
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
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
