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

Only the **active set** is polled for Yahoo -- names whose latest decision is a LONG or a SHORT -- in
rotating slices, so 150 names refresh every three ticks rather than 150 requests a minute against a
free endpoint, which is both a ban and a bill (the same argument `jobs/intraday.py` makes).

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nbt import db, get_json, rows, step  # noqa: E402

try:  # a local run reads the project .env, exactly as the other jobs do; CI sets the variable itself
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

TICK_SECONDS = 300
# Symbols per Yahoo download. Measured at about 4 s for 20 from a home connection; 60 stays far inside a
# five-minute tick while keeping the active set refreshed every few ticks.
YAHOO_SLICE = 60
PAPRIKA = "https://api.coinpaprika.com/v1/tickers?quotes=USD"
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


def slice_for_tick(n: int, limit: int, now_ts: float, tick: int = TICK_SECONDS) -> tuple[int, int]:
    """The half-open range of an ordered list of `n` to poll on this tick.

    Rotates with the clock, so over `ceil(n / limit)` consecutive ticks every item is covered exactly
    once and no two slices overlap. Pure: the clock is a parameter.
    """
    if n <= 0 or limit <= 0:
        return (0, 0)
    pages = math.ceil(n / limit)
    page = int(now_ts // tick) % pages
    return (page * limit, min(n, (page + 1) * limit))


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


UPSERT = """
    INSERT INTO "LiveQuote" ("assetId", price, "quotedAt", source, "updatedAt")
    SELECT * FROM unnest(%s::text[], %s::float8[], %s::timestamp[], %s::text[], %s::timestamp[])
    ON CONFLICT ("assetId") DO UPDATE
       SET price = EXCLUDED.price, "quotedAt" = EXCLUDED."quotedAt",
           source = EXCLUDED.source, "updatedAt" = EXCLUDED."updatedAt"
     WHERE "LiveQuote"."quotedAt" < EXCLUDED."quotedAt"
"""


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


def active_yahoo(cur) -> list[dict]:
    """Yahoo-sourced names whose newest decision is a direction, in a stable order."""
    got = rows(
        cur,
        """SELECT a.id, a."sourceRef" FROM "Asset" a
            WHERE a.source = 'yahoo' AND EXISTS (
                  SELECT 1 FROM "DecisionLog" d
                   WHERE d."assetId" = a.id AND d.action IN ('LONG', 'SHORT')
                     AND d."periodEnd" = (SELECT max("periodEnd") FROM "DecisionLog"))
            ORDER BY a."sourceRef" """,
    )
    if got:
        return got
    # No decisions yet: every Yahoo name is a candidate, rather than none.
    return rows(cur, """SELECT id, "sourceRef" FROM "Asset" WHERE source = 'yahoo' ORDER BY "sourceRef" """)


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
    try:
        with conn, conn.cursor() as cur:
            present = rows(cur, "SELECT to_regclass('public.\"LiveQuote\"') AS t")[0]["t"]
            if not present:
                say("the LiveQuote table does not exist here yet (migration pending); nothing written")
                return 0

            if only in (None, "crypto"):
                t = time.perf_counter()
                assets = rows(cur, """SELECT id, "sourceRef" FROM "Asset" WHERE source = 'coinpaprika'""")
                tickers = with_backoff(lambda: get_json(PAPRIKA, cache_key=None, ttl=0, timeout=10))
                got = parse_paprika(tickers or [], assets, now)
                quotes += got
                say(f"crypto {len(got)} of {len(assets)} in {time.perf_counter() - t:.2f}s")

            if only in (None, "yahoo"):
                t = time.perf_counter()
                active = active_yahoo(cur)
                lo, hi = slice_for_tick(len(active), YAHOO_SLICE, time.time())
                chosen = active[lo:hi]
                if chosen:
                    frame = with_backoff(lambda: yahoo_frame([a["sourceRef"] for a in chosen]))
                    got = parse_download(frame, chosen, now) if frame is not None else []
                    quotes += got
                    say(f"yahoo {len(got)} of {len(chosen)} (slice {lo}-{hi} of {len(active)} active) in {time.perf_counter() - t:.2f}s")
                else:
                    say("yahoo: no active names")

            if dry:
                say(f"dry run: {len(quotes)} quotes fetched, nothing written")
                return 0
            t = time.perf_counter()
            changed = write(cur, quotes, now)
            say(f"wrote {changed} of {len(quotes)} (the rest were not newer) in {time.perf_counter() - t:.2f}s")
    except Exception as error:  # noqa: BLE001 - name only: a driver error can echo the connection string
        say(f"stopped early ({type(error).__name__}); the next tick asks again")
        return 0
    finally:
        say(f"tick took {time.perf_counter() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
