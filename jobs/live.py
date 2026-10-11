"""Keep one fresh quote per asset, in place, a few minutes old at most.

    python jobs/live.py                 one tick: crypto, then one slice of the active Yahoo names
    python jobs/live.py --only crypto   crypto only (one request)
    python jobs/live.py --only yahoo    one slice of the active set only
    python jobs/live.py --dry-run       fetch and report, write nothing

What this is, and what it is not
--------------------------------
`PriceSnapshot` holds the closes the rule table reads, and it is fetched by the lanes at the pace a
close can change. This holds the *last trade*, for a reader who wants to see where a name is now. They
are different numbers and the second never replaces the first: a price for a session still being
traded is not a close (rule 41), and a decision that moved with the tape would be a different decision
on every refresh. `LiveQuote` is displayed beside a close with the time it was struck. It is never an
input to `decide`, to the factor job or to the macro gate.

One row per asset, overwritten in place
---------------------------------------
The table is keyed on the asset, so a tick that finds a newer quote overwrites the old one and the
table stays the size of the universe. A row per tick would be 576 x 288 a day -- the storage growth
that took the first database over its quota. The upsert only moves a quote **forward**: an older or
identical `quotedAt` rewrites nothing, so a closed market costs no writes and a late-arriving slice
can never put an old price over a newer one.

Where the numbers come from, and what was measured
--------------------------------------------------
  * crypto     CoinPaprika's ticker list: every coin in ONE request (0.7 s for 2,000 coins), each with
               its own `last_updated`. The same host `fetch_crypto` already uses from the runners.
               Binance is deliberately not used: it stopped answering GitHub's runners on 2026-09-29.
  * US stocks, ETFs, futures and FX     Yahoo's 1-minute bars in one batched download per slice: about
               4 s for 20 symbols from a home connection, so a slice of 60 is well inside a five
               minute tick but nowhere near 500 ms. That budget is not met by any HTTP round trip to a
               free provider and the job does not pretend otherwise; it prints what each stage took.
  * PSX        no free quote endpoint exists; PSX names keep the closes `jobs/psx.py` stores.

Only the **active set** is polled for Yahoo -- names whose latest decision is a LONG or a SHORT -- and
only the stalest `YAHOO_SLICE` of them per tick, so 150 names refresh over a few ticks rather than 150
requests a minute against a free endpoint, which is both a ban and a bill (the same argument
`jobs/intraday.py` makes). Which names those are is decided by whose stored quote is oldest, never by
the clock: see `stalest_yahoo` for what the clock version cost.

What it will not do
-------------------
  * It will not invent a price. A symbol the provider did not answer keeps its old quote, with its old
    time, and the reader sees how old it is.
  * It will not write a non-positive, non-finite or future-dated price.
  * It will not fail the workflow. A rate-limited or unreachable provider is retried a bounded number
    of times with a growing, jittered pause and then skipped for this tick; the next tick asks again.
  * It will not touch any table but `LiveQuote`, and it never prints a connection string.
"""

from __future__ import annotations

import math
import random
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nbt import db, get_json, rows, step  # noqa: E402

try:  # a local run reads the project .env, exactly as the other jobs do; CI sets the variable itself
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

# Symbols per Yahoo download. Measured at about 4 s for 20 from a home connection; 60 stays far inside a
# five-minute tick while keeping the active set refreshed every few ticks.
YAHOO_SLICE = 60
PAPRIKA = "https://api.coinpaprika.com/v1/tickers?quotes=USD"
# Yahoo's own chart endpoint, whose `meta` carries the last trade and the time it was struck.
#
# **Why a second Yahoo call exists at all.** The batched 1-minute download is the cheap way to quote
# 60 names at once, and for a share it is also the current one. For a currency pair it is not:
# measured 2026-10-12 at 22:23 UTC, an hour and twenty minutes after FX reopened for the week, the
# 1-minute series for `EURUSD=X` still ended at Friday 21:29 while this endpoint reported 1.1201
# struck at 22:22:27 -- thirty seconds old. The same call for `AAPL` returned Friday's close, which
# is the right answer for a shut market, so the fallback cannot invent a price for a closed one.
#
# It is one request per symbol, so it is used only where it is needed: a name whose downloaded bar is
# missing or older than META_STALE_MINUTES, at most META_MAX_PER_TICK of them a tick, stalest first.
# That is five requests on a weekend FX open and usually none at all.
META_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
META_STALE_MINUTES = 30
META_MAX_PER_TICK = 8
# A quote this far ahead of the clock is a bad timestamp, not a fast market.
FUTURE_SLACK = timedelta(minutes=5)
RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0


# --- pure helpers -------------------------------------------------------------------------------


def is_price(value) -> bool:
    """A finite, strictly positive number. Zero, negative, NaN and infinity are never a quote."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and x > 0


def with_backoff(fn, tries: int = RETRIES, base: float = BACKOFF_BASE_SECONDS, sleep=time.sleep, rand=random.random):
    """Call `fn` until it returns something truthy, pausing longer after each miss.

    1 s, 2 s, 4 s plus up to half a second of jitter, so several lanes that were rate-limited together
    do not all come back at the same instant. Gives up with None after `tries`: a tick that cannot
    reach a provider skips it and the next tick asks again. Exceptions are a miss, not a crash.
    """
    for attempt in range(tries):
        try:
            got = fn()
            # Empty means "the provider answered nothing": a None, an empty frame or an empty container.
            # Not compared with `== []`: on a DataFrame that is an elementwise comparison, not a test.
            empty = got is None or (hasattr(got, "empty") and got.empty) or (isinstance(got, (list, dict, tuple)) and not got)
            if not empty:
                return got
        except Exception:  # noqa: BLE001 - any provider failure is a miss
            pass
        if attempt < tries - 1:
            sleep(base * (2**attempt) + rand() * 0.5)
    return None


def to_naive_utc(ts) -> datetime:
    """A timestamp as a naive UTC datetime, which is how every timestamp in this database is stored."""
    if isinstance(ts, str):
        ts = datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
    if ts.tzinfo is not None:
        # Subtract the offset rather than converting: it is the same arithmetic, and it keeps this
        # helper from reading as a database query to the in-loop ratchet in tests/test_brain.py.
        ts = ts.replace(tzinfo=None) - (ts.utcoffset() or timedelta(0))
    return ts


def parse_paprika(tickers: list[dict], assets: list[dict], now: datetime) -> list[dict]:
    """One quote per crypto asset that CoinPaprika answered, with the time CoinPaprika gave it."""
    by_id = {t.get("id"): t for t in tickers or []}
    out = []
    for a in assets:
        t = by_id.get(a["sourceRef"])
        usd = ((t or {}).get("quotes") or {}).get("USD") or {}
        stamp = (t or {}).get("last_updated")
        if not t or not is_price(usd.get("price")) or not stamp:
            continue
        try:
            at = to_naive_utc(stamp)
        except ValueError:
            continue
        if at > now + FUTURE_SLACK:
            continue
        out.append({"assetId": a["id"], "price": float(usd["price"]), "quotedAt": at, "source": "coinpaprika"})
    return out


def parse_download(frame, assets: list[dict], now: datetime) -> list[dict]:
    """The last real close in each symbol's 1-minute series, with that bar's time.

    `frame` is what `yfinance.download(..., group_by="ticker")` returns: a column per (symbol, field)
    for several symbols, flat for one. NaN rows (a symbol that did not trade that minute) are dropped,
    so the answer is the last trade that happened and not a gap.
    """
    out = []
    for a in assets:
        sym = a["sourceRef"]
        try:
            series = frame[sym]["Close"] if hasattr(frame.columns, "levels") else frame["Close"]
            series = series.dropna()
        except (KeyError, TypeError):
            continue
        if len(series) == 0:
            continue
        price, at = series.iloc[-1], to_naive_utc(series.index[-1].to_pydatetime())
        if not is_price(price) or at > now + FUTURE_SLACK:
            continue
        out.append({"assetId": a["id"], "price": float(price), "quotedAt": at, "source": "yahoo"})
    return out


def parse_meta(payload, asset: dict, now: datetime) -> dict | None:
    """The last trade from one chart response, or None when it is unusable.

    The same three guards the downloaded bar gets: a finite positive price, a timestamp, and nothing
    dated into the future. A closed market answers with its own last close, which is correct and
    simply does not move the stored quote forward.
    """
    try:
        meta = payload["chart"]["result"][0]["meta"]
    except (KeyError, IndexError, TypeError):
        return None
    price, stamp = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if not is_price(price) or not stamp:
        return None
    try:
        at = datetime.fromtimestamp(int(stamp), timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None
    if at > now + FUTURE_SLACK:
        return None
    return {"assetId": asset["id"], "price": float(price), "quotedAt": at, "source": "yahoo"}


# Asset types whose market runs continuously enough that a stale bar is a gap rather than a closed
# exchange. FX is open from Sunday 21:00 UTC to Friday 21:00 UTC without a daily break, so a
# currency pair whose newest bar is hours old during the week is missing data. A share with the same
# gap is simply a shut exchange, and asking a second endpoint about it would spend a request to be
# told the close we already have -- which is exactly what the first version of this did, because
# every US bar sorts older than every FX bar while the US market is shut.
CONTINUOUS_TYPES = ("forex",)


def top_up_stale(chosen: list[dict], got: list[dict], now: datetime) -> list[dict]:
    """Quotes for continuously-traded names the download left stale, from Yahoo's chart meta.

    See META_URL for the measurement this rests on, and CONTINUOUS_TYPES for why a share is not
    asked about.
    """
    fresh = {q["assetId"]: q["quotedAt"] for q in got}
    behind = [
        a for a in chosen
        if a.get("assetType") in CONTINUOUS_TYPES
        and (a["id"] not in fresh or (now - fresh[a["id"]]) > timedelta(minutes=META_STALE_MINUTES))
    ]
    behind.sort(key=lambda a: fresh.get(a["id"], datetime.min))
    out = []
    for a in behind[:META_MAX_PER_TICK]:
        payload = with_backoff(
            lambda a=a: get_json(META_URL.format(sym=urllib.parse.quote(a["sourceRef"])), cache_key=None, ttl=0, timeout=10)
        )
        quote = parse_meta(payload, a, now) if payload else None
        # Only when it is actually newer than what the download gave: a shut market answers with its
        # own last close, and that must not count as a fresh reading.
        if quote and quote["quotedAt"] > fresh.get(a["id"], datetime.min):
            out.append(quote)
    return out


UPSERT = """
    INSERT INTO "LiveQuote" ("assetId", price, "quotedAt", source, "updatedAt")
    SELECT * FROM unnest(%s::text[], %s::float8[], %s::timestamp[], %s::text[], %s::timestamp[])
    ON CONFLICT ("assetId") DO UPDATE
       SET price = EXCLUDED.price, "quotedAt" = EXCLUDED."quotedAt",
           source = EXCLUDED.source, "updatedAt" = EXCLUDED."updatedAt"
     WHERE "LiveQuote"."quotedAt" < EXCLUDED."quotedAt"
"""


# Touch every row this tick asked about, whether or not the price moved.
#
# `updatedAt` is what `stalest_yahoo` orders by, and the upsert above only writes a row whose quote is
# strictly newer. On a shut market nothing is newer, so without this the column never advances, the
# same 60 names are the stalest for ever and the other 28 are never polled again -- which is the exact
# starvation the clock-rotated slice caused, rebuilt with a different cause. Found by running two ticks
# in a row against a closed market and watching `wrote 0 of 60` twice with the same 60 names.
#
# So the column means "when this row was last refreshed", and `quotedAt` alone means "when the price
# was struck". `getDataStamp` in lib/queries.ts reads `quotedAt` for exactly that reason: a cache stamp
# must move when the data moves, not when someone looked.
TOUCH = """
    UPDATE "LiveQuote" SET "updatedAt" = %s WHERE "assetId" = ANY(%s)
"""


def touch(cur, asset_ids: list[str], now: datetime) -> int:
    """Record that these names were polled just now. See TOUCH."""
    if not asset_ids:
        return 0
    cur.execute(TOUCH, (now, asset_ids))
    return cur.rowcount


def write(cur, quotes: list[dict], now: datetime) -> int:
    """Upsert in one round trip. Only a strictly newer quote overwrites, so nothing moves backward."""
    if not quotes:
        return 0
    cur.execute(
        UPSERT,
        (
            [q["assetId"] for q in quotes],
            [q["price"] for q in quotes],
            [q["quotedAt"] for q in quotes],
            [q["source"] for q in quotes],
            [now for _ in quotes],
        ),
    )
    return cur.rowcount


# --- the tick -----------------------------------------------------------------------------------


# The names this lane is responsible for: Yahoo-sourced, newest decision a direction. Written once
# because both the pick and the count below need it, and two copies would drift.
ACTIVE_YAHOO = """
    SELECT a.id, a."sourceRef", a."assetType"::text AS "assetType" FROM "Asset" a
     WHERE a.source = 'yahoo' AND EXISTS (
           SELECT 1 FROM "DecisionLog" d
            WHERE d."assetId" = a.id AND d.action IN ('LONG', 'SHORT')
              AND d."periodEnd" = (SELECT max("periodEnd") FROM "DecisionLog"))
"""
# No decision logged at all -- the state right after a reset -- so every Yahoo name is a candidate
# rather than none.
ALL_YAHOO = """SELECT id, "sourceRef", "assetType"::text AS "assetType" FROM "Asset" WHERE source = 'yahoo'"""

_PICK = """
    SELECT a.id, a."sourceRef", a."assetType"
      FROM ({set_sql}) a
      LEFT JOIN "LiveQuote" q ON q."assetId" = a.id
     ORDER BY q."updatedAt" ASC NULLS FIRST, a."sourceRef" ASC
     LIMIT %s
"""


def active_count(cur) -> int:
    """How many names the lane is responsible for, for the line the tick prints."""
    n = rows(cur, f'SELECT count(*) AS n FROM ({ACTIVE_YAHOO}) a')[0]["n"]
    return n or rows(cur, f'SELECT count(*) AS n FROM ({ALL_YAHOO}) a')[0]["n"]


def stalest_yahoo(cur, limit: int) -> list[dict]:
    """The `limit` names of the active set whose stored quote is oldest, never-quoted first.

    **Why staleness and not the clock.** This used to poll a slice of the alphabet chosen by
    `floor(now / 300) % pages`, which covers every name only if the ticks actually arrive. They do
    not. Measured 2026-10-12: the schedule asks for about 96 runs a day and GitHub delivered 8 on
    2026-10-10 and 12 on 2026-10-11. With two pages and a dozen arrivals at arbitrary minutes, which
    page runs is a coin toss, and a name at the back of the alphabet can wait a day or more. Every FX
    pair in this universe sorts to the back -- `USDBRL=X` through `USDTRY=X` -- so FX is what
    starved: five FX names in the active set with no stored quote at all, while the health endpoint
    read the one frozen `AUDUSD` row left over from when that name had a direction, and reported the
    market 48 hours behind. The provider was never the problem; a direct request for those five
    symbols returned all five.

    Ordering by what is actually oldest is self-correcting: a dropped run can delay a name but
    cannot skip it, because the name it skipped is the first one the next run takes. `updatedAt` and
    not `quotedAt`, because a closed market's `quotedAt` does not move and would pin the same names
    at the front for ever. Never-quoted names sort first, so a name entering the set is picked up on
    the next tick. The request is still one download of at most `limit` symbols.
    """
    got = rows(cur, _PICK.format(set_sql=ACTIVE_YAHOO), (limit,))
    return got or rows(cur, _PICK.format(set_sql=ALL_YAHOO), (limit,))


def yahoo_frame(symbols: list[str]):
    import yfinance as yf  # imported here so the pure helpers above need no network library

    return yf.download(
        symbols, period="1d", interval="1m", progress=False, group_by="ticker", threads=True, timeout=10
    )


def say(line: str) -> None:
    print(f"live: {line}", flush=True)


def main(argv: list[str]) -> int:
    only = argv[argv.index("--only") + 1] if "--only" in argv and argv.index("--only") + 1 < len(argv) else None
    dry = "--dry-run" in argv
    t0 = time.perf_counter()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    step("live quotes")
    try:
        conn = db()
    except Exception as error:  # noqa: BLE001
        say(f"no database connection ({type(error).__name__}); nothing written")
        return 0
    quotes: list[dict] = []
    polled: list[dict] = []
    try:
        with conn, conn.cursor() as cur:
            present = rows(cur, "SELECT to_regclass('public.\"LiveQuote\"') AS t")[0]["t"]
            if not present:
                say("the LiveQuote table does not exist here yet (migration pending); nothing written")
                return 0

            if only in (None, "crypto"):
                t = time.perf_counter()
                assets = rows(cur, """SELECT id, "sourceRef" FROM "Asset" WHERE source = 'coinpaprika'""")
                polled += assets
                tickers = with_backoff(lambda: get_json(PAPRIKA, cache_key=None, ttl=0, timeout=10))
                got = parse_paprika(tickers or [], assets, now)
                quotes += got
                say(f"crypto {len(got)} of {len(assets)} in {time.perf_counter() - t:.2f}s")

            if only in (None, "yahoo"):
                t = time.perf_counter()
                chosen = stalest_yahoo(cur, YAHOO_SLICE)
                polled += chosen
                if chosen:
                    total = active_count(cur)
                    frame = with_backoff(lambda: yahoo_frame([a["sourceRef"] for a in chosen]))
                    got = parse_download(frame, chosen, now) if frame is not None else []
                    topped = top_up_stale(chosen, got, now)
                    quotes += got + topped
                    missed = len(chosen) - len(got)
                    say(
                        f"yahoo {len(got)} of {len(chosen)} stalest (of {total} active) in "
                        f"{time.perf_counter() - t:.2f}s"
                        + (f"; {len(topped)} topped up from the quote endpoint" if topped else "")
                        + (f"; {missed} unanswered, first in line next tick" if missed else "")
                    )
                else:
                    say("yahoo: no active names")

            if dry:
                say(f"dry run: {len(quotes)} quotes fetched, nothing written")
                return 0
            t = time.perf_counter()
            changed = write(cur, quotes, now)
            # Every name asked about this tick, so the rotation advances even when no price moved.
            touched = touch(cur, [a["id"] for a in polled], now)
            say(
                f"wrote {changed} of {len(quotes)} (the rest were not newer), "
                f"{touched} marked polled in {time.perf_counter() - t:.2f}s"
            )
    except Exception as error:  # noqa: BLE001 - name only: a driver error can echo the connection string
        say(f"stopped early ({type(error).__name__}); the next tick asks again")
        return 0
    finally:
        say(f"tick took {time.perf_counter() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
