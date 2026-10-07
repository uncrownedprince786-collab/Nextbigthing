"""Daily prices, size on the snapshot dates, and news.

Sources, all free and public:
  Yahoo Finance (via yfinance)  daily OHLCV and share counts
  Yahoo chart API /v8/chart      the recent window when yfinance answers nothing — a second
                                 endpoint, not a second provider; see the comment above CHART
  Binance public klines          daily crypto closes
  CoinGecko market_chart         crypto market cap history and current cap
  CoinPaprika /v1/tickers        current coin list, supply, market cap
  Google News RSS                headlines per industry and per product

Nothing here is estimated. If a source does not answer for an asset, that asset gets
no row for that date and the UI says the data is missing.

Run: python jobs/prices.py
"""

from __future__ import annotations

import re
import sys
import time
import urllib.parse
import warnings
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import SNAPSHOTS, db, get_json, get, rows, step  # noqa: E402
from runlog import parse_chunk, slice_of  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

import pandas as pd
import yfinance as yf  # noqa: E402

START = date(2019, 1, 1)
YAHOO = "Yahoo Finance"
COINGECKO = "CoinGecko"
BINANCE = "Binance"
PAPRIKA = "CoinPaprika"
GNEWS = "Google News RSS"
PSX = "psx"
NEWS_PER_FEED = 12
# Asset feeds are narrower than the industry ones, so a smaller cap keeps the run short
# and stops one busy company filling its own page with the same week of coverage.
NEWS_PER_ASSET = 6

# How far back a stored headline may have been published, and the window the search asks for.
#
# **Google News RSS ranks a search by relevance and not by date.** That one fact is what had
# emptied this lane for every name whose coverage is thin, and it is invisible from the inside:
# the feed answers 200, parses, and hands back a hundred items, so every guard in rule 31 reads
# healthy. But the first six items of `"Hub Power" Pakistan` were published 24 Jul, 22 Jul,
# 28 Jul, 10 Aug, 4 Jun and — the one that gives it away — **5 Mar 2024**. A cap that keeps the
# first six keeps those six, `ON CONFLICT DO NOTHING` drops them as already stored, and the asset
# is left holding exactly `NEWS_PER_ASSET` rows for ever. Measured on 2026-10-07: HUBC, MEBL and
# SYS each held exactly 6 rows, newest 7 Sep, while the same query offered 97 items and the same
# query with a window offered eight published inside the fortnight. 21 PSX names and 3 FX pairs
# held nothing at all from the last 30 days.
#
# So the window is asked for in the query, with Google's own `when:` operator, **and checked
# again against each item's own `pubDate`**. Both halves, because the operator is a request and
# the date is the evidence: a provider that ignores or loosens it must not be able to put a 2024
# article into a reading of this month. Rule 2 — nothing is filled in — has a mirror image, which
# is that nothing stale is allowed to pass as current.
#
# 30 days and not 14: `jobs/human.py` measures tone over a 30 day window and attention over this
# 30 against the 30 before, so a shorter ingest window would starve the comparison it feeds. The
# slack exists because `when:30d` is Google's arithmetic on its own index and a few items land a
# day or two outside it; a stored item is allowed to be slightly older than the window, never
# months older.
NEWS_WINDOW_DAYS = 30
NEWS_WINDOW_SLACK_DAYS = 3

# Below this many recent on-target items from the primary feed, the next source in the chain is
# asked. 3 is `MIN_ITEMS` territory deliberately left well under it: `jobs/human.py` needs 8
# headlines before it will publish a tone direction, so a floor of 3 is not an attempt to reach
# a grade -- it is the point below which a name has so little that a second source is worth a
# request. Set at 8 the chain would fire for most of the PSX list on every run and spend four
# hundred requests chasing coverage that does not exist.
NEWS_FLOOR = 3

BING = "Bing News RSS"
YAHOO_RSS = "Yahoo Finance headline RSS"

# Hard ceiling on **fallback** requests per run, whatever the thin-name count says.
#
# Same idiom as `MAX_REQUESTS` in `jobs/intraday.py`, and here for a sharper reason: this lane
# has a `timeout-minutes` and the fallback chain is the first thing in it whose cost grows with
# the universe. `nbt.get` sleeps a second per host, so the primary pass alone has a floor of one
# second times 318 feeds, and every fallback adds to that. The 160 -> 240 asset expansion is what
# pushed `cron decision` past its own budget on three consecutive days, and because **GitHub
# reports a timed-out job as "cancelled"** it read as a scheduling quirk rather than as the
# outage it was. A lane that fetches per asset has to declare what it will spend.
#
# 150 against the ~100 names currently under `NEWS_FLOOR`: enough that the chain does its job
# today, and a cap so a future expansion or a primary blackout -- when *every* name falls through
# -- costs one capped run and not a killed lane. The primary pass is never capped, because that
# is the source every asset depends on and skipping it silently is the failure rule 31 exists to
# catch rather than one worth trading time for.
NEWS_FALLBACK_BUDGET = 150

SNAPSHOT_SET = set(SNAPSHOTS)


def yahoo_assets(cur) -> list[dict]:
    return rows(
        cur,
        """
        SELECT a.id, a.symbol, a."sourceRef", a."assetType"::text AS "assetType"
        FROM "Asset" a
        WHERE a.source = 'yahoo' ORDER BY a.symbol
        """,
    )


def crypto_assets(cur) -> list[dict]:
    return rows(
        cur,
        """
        SELECT a.id, a."sourceRef" FROM "Asset" a
        WHERE a.source = 'coinpaprika' ORDER BY a.symbol
        """,
    )


def last_on_or_before(series: list[tuple[date, float]], target: date):
    """Closest real observation at or before target. None when the source starts later."""
    hit = [v for day, v in series if day <= target]
    return hit[-1] if hit else None


def day_on_or_before(series: list[tuple[date, float]], target: date):
    hit = [day for day, v in series if day <= target]
    return hit[-1] if hit else None


# How much history an asset must already hold before it is treated as backfilled. Below
# this it gets the full download, because a half-filled series would leave permanent holes.
MIN_HISTORY_ROWS = 200

# How far back an incremental run re-reads. The provider revises recent days — a close is
# occasionally corrected and a volume frequently is — so the last fortnight is refetched and
# upserted rather than trusted. Everything older is settled and is never asked for again.
CORRECTION_DAYS = 14


def stored_coverage(cur) -> dict[str, tuple[int, date | None]]:
    """Rows and newest stored date per asset, so a run can ask only for what it lacks."""
    out: dict[str, tuple[int, date | None]] = {}
    for r in rows(
        cur,
        """
        SELECT "assetId" AS id, count(*) AS n, max(date) AS newest
        FROM "PriceSnapshot" WHERE source = %s GROUP BY "assetId"
        """,
        (YAHOO,),
    ):
        out[r["id"]] = (int(r["n"]), r["newest"])
    return out


# --- How thin an answer is still an answer ------------------------------------------------------
#
# `require_answer` only fires when a batch answered for *nothing*, and that is one of two ways the
# Yahoo lane has to fail. The other is a batch that answers for a handful: 3 of 80 passes the
# zero-check, stores three assets' worth of rows, prints "0 price rows" nowhere, and exits 0. On a
# provider whose download helper returns an empty frame for a throttled request and raises nothing,
# a partly-throttled request returns a partly-empty frame by exactly the same mechanism.
#
# The threshold is 0.75, and the reason is the market calendar. All 80 of these assets trade on one
# US calendar: either the exchange published a session and every one of them has a bar for it, or it
# did not and none of them do. Nothing in between is a property of the market. What *is* ordinary is
# a symbol-level absence — a ticker renamed, delisted, or newly listed and younger than the window —
# and that has run at 0 to 2 assets of 80, which is why the gate is not set at 1.0. 0.75 leaves room
# for 20 such absences, far more than has ever been seen, while the two failures actually observed
# in production land at 0.00 and 0.04. The gap between 0.04 and 0.75 is the whole margin, and it is
# wide enough that this number never has to be tuned against a normal day.
MIN_ANSWER_SHARE = 0.75


def answered_share(answered: int, asked: int) -> float:
    """Fraction of the batch that produced rows. An empty ask is a full answer, not a failure."""
    if not asked:
        return 1.0
    return answered / asked


def require_share(answered: int, asked: int, source: str = YAHOO) -> None:
    """Fail a thin batch the way `require_answer` fails an empty one.

    Same reasoning, one notch earlier: a batch that answered for a few assets is a fact about the
    provider and not about the market, because these assets share one trading calendar. Raises
    `SourceSilent` so `main` keeps the rows the other lanes wrote — see that docstring.
    """
    require_answer(answered, asked, source=source)
    share = answered_share(answered, asked)
    if asked and share < MIN_ANSWER_SHARE:
        print(
            f"{source} answered for only {answered} of {asked} assets "
            f"({share:.0%}, floor {MIN_ANSWER_SHARE:.0%}): these assets share one market "
            "calendar, so a partial answer is the provider and not the session"
        )
        raise SourceSilent(f"{source} answered for only {answered} of {asked} assets")


def day_shortfall(newest: dict[str, date | None]) -> tuple[date | None, list[str], list[str]]:
    """`(the day the batch reached, symbols with nothing, symbols that stop before that day)`.

    The day the batch reached is the *modal* newest day across the assets that answered, not the
    maximum. The maximum is the wrong statistic twice over: one asset carrying a bar for a session
    the rest have not got — a stale cache entry, a futures contract whose session ends later, a
    forming day for one exchange — would declare every other asset behind, and that is a report
    nobody can read. The mode is the session the market actually published, because these assets
    share one calendar; ties break to the later day, so a batch split evenly across two days is
    held to the newer one and the older half is named.

    Named separately from the storing loop because this is the whole partial-day judgement and it
    is worth testing without a frame, a database or a network.
    """
    answered = {sym: day for sym, day in newest.items() if day is not None}
    missing = sorted(sym for sym, day in newest.items() if day is None)
    if not answered:
        return None, missing, []
    tally: dict[date, int] = {}
    for day in answered.values():
        tally[day] = tally.get(day, 0) + 1
    # Most common, then latest: `max` over (count, day) does both in one pass.
    day = max(tally, key=lambda d: (tally[d], d))
    behind = sorted(sym for sym, had in answered.items() if had < day)
    return day, missing, behind


# --- Retrying the download ----------------------------------------------------------------------
#
# `nbt.get` retries, but `yf.download` does not go through it: yfinance opens its own session, with
# its own crumb-and-cookie handshake, and the lane's one shared retry budget never sees it. So the
# empty frame that stored 0 rows on a GitHub runner was never asked a second time.
#
# The bound is deliberately small, and the number that matters is the *lane total*, not the per-call
# one. This lane issues at most two downloads — one backfill batch, one incremental batch — and a
# retry of either re-requests every symbol in it. Two retried attempts per run, shared between both
# batches, with 5 and 20 second pauses: a completely dead Yahoo costs this lane 25 seconds of extra
# waiting and no more, against a normal runtime of several minutes. That ceiling is why the retry
# cannot multiply the runtime, and it is the same shape as `nbt.RETRY_HOST_BUDGET` — per-run, not
# per-call — for the same reason.
#
# A *thin* frame is deliberately not retried. Re-downloading 80 symbols to recover 3 is precisely
# the runtime multiplication this bound exists to prevent, and the chart-API fallback below repairs
# those three directly. Only an empty frame — nothing usable at all — is worth asking again for.
YAHOO_DOWNLOAD_ATTEMPTS = 3
YAHOO_DOWNLOAD_BACKOFF = (5, 20)
YAHOO_DOWNLOAD_BUDGET = 2

_download_spent = {"n": 0}


def download_retry_wait(attempt: int, spent: int) -> float | None:
    """Seconds to pause before attempt `attempt + 1`, or None when the budget says stop.

    Both ceilings in one place so the worst case is a number a test can assert rather than a
    property of a loop: at most `YAHOO_DOWNLOAD_BUDGET` retried attempts in a run, at most
    `YAHOO_DOWNLOAD_ATTEMPTS` attempts for any one call.
    """
    if attempt + 1 >= YAHOO_DOWNLOAD_ATTEMPTS:
        return None
    if spent >= YAHOO_DOWNLOAD_BUDGET:
        return None
    return float(YAHOO_DOWNLOAD_BACKOFF[attempt])


def yahoo_download(symbols: list[str], start: str):
    """`yf.download` with a bounded retry, because an empty frame is not an answer.

    yfinance signals a throttled or blocked request by returning an empty DataFrame, and raises
    for a transport error. Both are the same outcome here — no bars — and both are worth one or
    two more attempts inside the budget above. An exhausted budget returns the empty frame rather
    than raising: the caller's chart-API fallback and `require_share` decide what that means, and
    raising from here would be the single point of failure this whole change exists to remove.
    """
    frame = None
    for attempt in range(YAHOO_DOWNLOAD_ATTEMPTS):
        try:
            frame = yf.download(
                symbols,
                start=start,
                progress=False,
                auto_adjust=True,
                group_by="ticker",
                threads=4,
            )
        except Exception as e:  # noqa: BLE001 - a dead provider must not kill the lane
            print(f"  yf.download raised {type(e).__name__} for {len(symbols)} symbols")
            frame = None
        if frame is not None and len(frame):
            return frame
        wait = download_retry_wait(attempt, _download_spent["n"])
        if wait is None:
            print(
                f"  yf.download answered nothing for {len(symbols)} symbols and the retry "
                "budget for this run is spent"
            )
            break
        _download_spent["n"] += 1
        print(f"  yf.download answered nothing, retrying in {wait:.0f}s")
        time.sleep(wait)
    return frame if frame is not None else pd.DataFrame()


def fetch_yahoo(cur, chunk: tuple[int, int] | None = None) -> int:
    assets = yahoo_assets(cur)
    if not assets:
        return 0

    # The slice, applied to the symbol list and nothing else. `slice_of` sorts before cutting,
    # so a symbol lands in the same slice on every run even though the query has no ORDER BY —
    # without that a retry and the run it is retrying would disagree about what was covered.
    # Every other number below is then computed from the slice, so the step summary reports
    # what this slice did rather than what the whole lane would have done.
    if chunk:
        i, n = chunk
        assets = slice_of(assets, i, n, key=lambda a: a["symbol"])
        step(f"yahoo slice {i}/{n}: {len(assets)} of this lane's symbols")
        if not assets:
            # More slices than symbols. Not a failure, and not silence either: there was
            # nothing in this slice to ask for, so the silence guard must not fire on it.
            return 0

    # Incremental by default. The job used to download every ticker's history from 2019 on
    # every single run and replace the table wholesale, which is some seven years of daily
    # bars per asset per day for the sake of one new row each. An asset that already holds
    # its history is now asked only for the correction window.
    coverage = stored_coverage(cur)
    full: list[dict] = []
    recent: list[dict] = []
    for a in assets:
        have, newest = coverage.get(a["id"], (0, None))
        if have < MIN_HISTORY_ROWS or newest is None:
            full.append(a)
        else:
            recent.append(a)

    oldest_newest = min(
        (coverage[a["id"]][1] for a in recent if coverage.get(a["id"], (0, None))[1]),
        default=None,
    )
    step(
        f"yahoo daily history: {len(full)} full backfill, {len(recent)} incremental"
        + (f" from {oldest_newest - timedelta(days=CORRECTION_DAYS)}" if oldest_newest else "")
    )

    frames: list[tuple[list[dict], object, bool]] = []
    if full:
        frames.append(
            (full, yahoo_download([a["sourceRef"] for a in full], START.isoformat()), True)
        )
    if recent and oldest_newest:
        frames.append(
            (
                recent,
                yahoo_download(
                    [a["sourceRef"] for a in recent],
                    (oldest_newest - timedelta(days=CORRECTION_DAYS)).isoformat(),
                ),
                False,
            )
        )

    written = 0
    today = date.today()
    asked_total = 0
    answered_total = 0

    # Asked once for the whole lane and before anything is stored, so every frame in this run
    # judges the same session. Two probes taken either side of a bell would let one frame store a
    # day the other dropped, and the asymmetry would sit in the table looking like a feed fault.
    forming = forming_sessions(assets)

    for assets_part, frame, is_full in frames:
        stored, newest = _store_frame(cur, assets_part, frame, today, is_full, forming)
        written += stored

        # Partial-day detection, per asset and by name. Up to here a batch that answered for three
        # assets wrote three assets' worth of rows and said nothing about the other seventy-seven;
        # these two lists are what makes the difference between "the market was shut" and "the
        # provider throttled us" visible in the step's own output.
        day, missing, behind = day_shortfall(newest)
        if day:
            print(f"  batch reached {day}")
        if missing:
            print(f"  {len(missing)} with no bars at all: {', '.join(missing)}")
        if behind:
            # A partial final day. These assets answered, but their series stops before the day
            # the rest of the batch reached, so the newest close on their page would be stale
            # while every neighbour's is current — the exact asymmetry a reader notices first.
            print(f"  {len(behind)} stop before {day}: {', '.join(behind)}")

        # Never leave a known single point of failure. Whatever yfinance did not answer for is
        # asked again through a different endpoint before the batch is judged, so a crumb, cookie
        # or rate-limit failure on yfinance's side costs those assets their recent days rather
        # than blanking them.
        by_symbol = {a["sourceRef"]: a for a in assets_part}
        repair = [by_symbol[s] for s in missing + behind if s in by_symbol]
        if repair:
            rescued_rows, rescued = chart_repair(cur, repair, day)
            written += rescued_rows
        else:
            rescued = set()

        asked_total += len(assets_part)
        answered_total += sum(
            1 for sym, had in newest.items() if had is not None or sym in rescued
        )

    # One gate for the lane rather than one per frame. The backfill batch is usually a handful of
    # assets and the incremental one is the rest, so judging them separately would hold a two-asset
    # batch to the same share as an eighty-asset one and fail the lane on a coincidence.
    require_share(answered_total, asked_total)
    return written


class SourceSilent(Exception):
    """A source answered for nothing it was asked about.

    Deliberately not `SystemExit`. `main` holds one transaction across all three lanes and
    psycopg rolls a transaction back on *any* exception leaving the `with` block, so raising
    out of the crypto or news lane discarded the rows the Yahoo lane had already written —
    37,537 of them on a normal day. One blocked source must cost its own rows and no others.
    `main` catches this per lane, commits what did answer, and exits non-zero afterwards.
    """


def require_answer(stored: int, asked: int, source: str = YAHOO) -> None:
    """Fail when a whole batch came back empty, instead of finishing quietly with nothing.

    `yf.download` returns an empty DataFrame for a throttled or blocked request and raises
    nothing, so a blocked host looks exactly like a market with no new bars. That is how the
    nightly refresh stored 0 rows on a GitHub runner while the same fetch stored 37,537 from
    a laptop minutes later, and the step still exited 0. One asset answering nothing is data
    and is printed above; none of a batch answering is a fact about the provider, and rule 21
    keeps those apart.
    """
    if asked and stored == 0:
        print(
            f"no row from {source} for any of {asked} assets: treat it as unavailable "
            "from this host and re-verify it before trusting a later run"
        )
        raise SourceSilent(f"{source} answered for none of {asked} assets")


# --- The second endpoint for US closes ----------------------------------------------------------
#
# Be clear about what this is and is not. Yahoo is the only free source of US equity, ETF and
# commodity closes this project has found, and this is **not a second provider** — it is Yahoo's own
# chart API, the same company and the same data. Stooq was the candidate for a genuinely independent
# venue and it is out: it sits behind a JavaScript proof-of-work bot check, and we do not defeat bot
# protection. So the crypto lane's four-venue chain has no equivalent here, and pretending otherwise
# in a comment would be worse than having no fallback.
#
# What it *does* protect against is the failure that actually happened. `yf.download` is a scraper:
# it negotiates a crumb and a cookie against Yahoo's web endpoints, keeps its own session, and
# answers an empty DataFrame when any part of that handshake or its own rate limiting goes wrong —
# which is a yfinance-side failure, not a Yahoo-side one. The chart API is a different URL, a
# different authentication story (none), a different response shape and a different code path, and
# it answered full OHLCV current to the same day from the same host on which this was verified. A
# library that stops working is the likeliest way this lane goes dark, and this covers it.
#
# What it does **not** cover: Yahoo blocking this host, or Yahoo going down. Both endpoints die
# together in that case and the lane correctly reports silence. That is a known remaining single
# point of failure, and the honest mitigation is a second provider, not a second URL.
#
# Scope is the recent window only. `range=1mo` is about 21 sessions, which covers the correction
# window `CORRECTION_DAYS` asks for with room to spare; a seven-year backfill still has to come from
# yfinance, because paging this endpoint back to 2019 asset by asset is a different job.
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
CHART_RANGE = "1mo"
YAHOO_CHART = "Yahoo Finance chart API"


def session_bounds(meta: dict) -> tuple[date, int, int] | None:
    """The session the provider is currently reporting: `(its day, start epoch, end epoch)`.

    The day is the session's date **in the exchange's own timezone**, taken from the `gmtoffset`
    the payload carries rather than from a timezone database — the same choice `jobs/intraday.py`
    makes, and for the same reason.

    It has to be the exchange's date and not the UTC one, because for some venues they are
    different days and the bar is stamped with the exchange's. Measured 2026-10-07 on `AUDUSD=X`:
    Yahoo reports the currency session as `2026-10-06T23:00Z -> 2026-10-07T22:59Z`, which is the
    London day 2026-10-07, and the bar it is writing is stamped 2026-10-07. Reading the UTC date
    of the start gives 10-06 — a day that is already closed — so a guard built on it would drop
    the wrong bar and keep the forming one, which is the opposite of its purpose.
    """
    regular = ((meta or {}).get("currentTradingPeriod") or {}).get("regular") or {}
    start, end = regular.get("start"), regular.get("end")
    if not start or not end:
        return None
    offset = (meta or {}).get("gmtoffset") or 0
    local = datetime.fromtimestamp(int(start) + int(offset), tz=timezone.utc).date()
    return local, int(start), int(end)


# How far behind a session's end the provider's own progress marker may be and still be read as
# progress through that session.
#
# `regularMarketTime` is the provider saying how far into the session its data reaches, and inside
# a live session it is the sharpest signal available: it is why a payload fetched mid-session can
# be judged without consulting a clock at all. But it is only a signal while it is current, and it
# is not always current. Measured 2026-10-07 on `HUBC.KA`: Yahoo returned a session ending
# 2026-10-07T11:00Z with a `regularMarketTime` of **2024-07-23** — twenty-six months behind. Read
# as progress that says the session is still open, and it would say so for ever, so a guard
# trusting it alone would stop storing that venue's closes permanently and silently.
#
# One session's length is the natural bound: a marker inside the session it describes is progress,
# and a marker from before that session began is not a measurement of it at all. A day of slack is
# added on top for a provider that is merely catching up after the bell.
STALE_MARKER_GRACE = 24 * 3600


def chart_forming_day(meta: dict) -> date | None:
    """The session date whose daily bar is still being written, or None once it has closed.

    At `interval=1d` the endpoint returns the day in progress as an ordinary bar stamped at the
    session open, with the open, high and low so far and a close that is really the last trade.
    Stored as a close it is a price that never happened, and tomorrow's run would overwrite it
    with the real one — which is exactly the silent wrong number this file exists to avoid.

    Two independent reasons to call a session unfinished, because neither input is trustworthy
    alone:

    * **Our clock has not reached the session's end.** The end is a published fact about the
      exchange and the clock is ours, so this holds whatever the provider says about itself.
    * **The provider's own marker sits inside the session.** This is what catches the minutes
      after the bell, when the session has ended by the clock but the final bar has not landed
      yet. Trusted only while the marker is plausibly current — see `STALE_MARKER_GRACE`.
    """
    bounds = session_bounds(meta)
    if bounds is None:
        return None
    day, _start, end = bounds

    if datetime.now(timezone.utc).timestamp() < end:
        return day

    seen = (meta or {}).get("regularMarketTime")
    if seen and 0 < end - int(seen) <= STALE_MARKER_GRACE:
        return day

    return None


def chart_meta(sym: str) -> dict:
    """The `meta` block for one symbol, which is where the session bounds live.

    One request, and `nbt.get`'s cache makes it one per symbol per run however often it is asked
    for. The TTL is short on purpose: this is the one thing in the payload that changes *within*
    a session, and a six-hour cache of it — the TTL `chart_bars` correctly uses for bars that
    never change once closed — would answer "still trading" hours after the close.
    """
    payload = get_json(
        f"{CHART}{urllib.parse.quote(sym)}?range=1d&interval=1d",
        cache_key=f"yahoo-session-{sym}",
        ttl=300,
        headers={"Accept": "application/json"},
    )
    result = ((payload or {}).get("chart") or {}).get("result") or [{}]
    return (result[0] or {}).get("meta") or {}


def forming_sessions(assets: list[dict]) -> dict[str, date]:
    """Which day, if any, is still being traded — one entry per asset type being stored.

    The daily download comes through `yf.download`, which hands back bars and no session
    metadata, so the bar for a session still in progress is indistinguishable from a closed one
    by looking at the frame. This asks the chart endpoint, which does carry that metadata, for
    **one** symbol per asset type and applies the answer to every asset of that type.

    One probe per type rather than per symbol because the answer is a property of the exchange's
    calendar and not of the instrument: every US listing here trades the same NYSE/Nasdaq session,
    and every pair the same continuous currency day. A hundred and fifty-five probes would be a
    hundred and fifty-four requests spent re-learning the same fact.

    A probe that fails returns no entry for its type, which means nothing is dropped. That is the
    deliberate direction to fail in: this guard exists to stop a partial bar being written, and a
    guard that cannot reach the provider must not also be able to stop the lane storing anything.
    """
    out: dict[str, date] = {}
    probes: dict[str, str] = {}
    for a in assets:
        kind = a.get("assetType") or "equity"
        probes.setdefault(kind, a["sourceRef"])
    for kind, sym in sorted(probes.items()):
        try:
            day = chart_forming_day(chart_meta(sym))
        except Exception as exc:  # noqa: BLE001 — a failed probe must not stop the lane
            print(f"  session probe for {kind} ({sym}) failed: {type(exc).__name__}: {exc}")
            continue
        if day:
            out[kind] = day
            print(f"  {kind}: {sym} says {day} is still trading, so its bar is not a close")
        else:
            print(f"  {kind}: {sym} says the last session has closed")
    return out


def parse_chart(payload) -> list[tuple]:
    """Yahoo's chart body to the same `(day, open, high, low, close, volume)` shape as a venue.

    Three things this has to get right, each one a real way to store a wrong number:

    * The arrays are parallel and padded. A session the provider has no data for is a null in
      every array rather than a missing element, so a bar is kept only when open, high, low and
      close are all present. Counting a null close as an observation would manufacture a price.
    * The series is adjusted, because the rows beside it are. `yf.download(auto_adjust=True)`
      back-adjusts OHLC for splits and dividends; this endpoint returns the raw quote plus a
      parallel `adjclose`. Splicing a raw close into an adjusted series puts a step in the chart
      at the last corporate action. So each bar is scaled by its own `adjclose / close` ratio,
      which is the same adjustment applied to the same bar, and leaves the bar internally
      consistent — scaling the close alone could push it outside its own high and low.
    * The forming day is dropped, per `chart_forming_day`.

    Volume is left alone: Yahoo already reports split-adjusted volume and `auto_adjust` does not
    touch it, so scaling it here would disagree with every row yfinance wrote.
    """
    chart = (payload or {}).get("chart") or {}
    if chart.get("error"):
        return []
    results = chart.get("result") or []
    if not results:
        return []
    r = results[0]
    stamps = r.get("timestamp") or []
    ind = r.get("indicators") or {}
    quote = (ind.get("quote") or [{}])[0]
    adj = ((ind.get("adjclose") or [{}])[0] or {}).get("adjclose") or []
    forming = chart_forming_day(r.get("meta") or {})

    out = []
    for i, ts in enumerate(stamps):
        def at(seq):
            return seq[i] if i < len(seq) else None

        op, hi, lo = at(quote.get("open") or []), at(quote.get("high") or []), at(quote.get("low") or [])
        close = at(quote.get("close") or [])
        if op is None or hi is None or lo is None or close is None:
            continue
        day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        if forming is not None and day >= forming:
            continue
        ratio = 1.0
        a = at(adj)
        if a is not None and close:
            ratio = float(a) / float(close)
        vol = at(quote.get("volume") or [])
        out.append(
            (
                day,
                float(op) * ratio,
                float(hi) * ratio,
                float(lo) * ratio,
                float(close) * ratio,
                None if vol is None else float(vol),
            )
        )
    return sorted(out)


def chart_bars(sym: str) -> list[tuple]:
    """The recent window for one symbol. A futures ticker like `GC=F` has to be quoted."""
    return parse_chart(
        get_json(
            f"{CHART}{urllib.parse.quote(sym)}?range={CHART_RANGE}&interval=1d",
            cache_key=f"yahoo-chart-{sym}",
            # Six hours. A closed session's daily bar never changes, and a rerun within the day
            # must not re-ask the provider for a number it already gave.
            ttl=6 * 3600,
            headers={"Accept": "application/json"},
        )
    )


def chart_repair(cur, assets: list[dict], reached: date | None) -> tuple[int, set[str]]:
    """Ask the chart API for the assets yfinance did not answer for. Upsert only, never replace.

    `(rows written, symbols recovered)`. Replace is not an option and the reason is the same
    invariant `_store_frame` and `fetch_crypto` both state: this window is about 21 sessions, and
    deleting an asset's rows to rewrite it from here would destroy six years of history to recover
    three days. Every row is upserted, so a day yfinance later answers for is overwritten by it.

    One insert for the whole repair set, after the loop. A query per asset inside this loop is the
    shape the in-loop query budget exists to stop, and this loop is already per-asset over HTTP.

    The rows carry `YAHOO_CHART`, not `YAHOO`, because a row says who produced the number in it.
    The consequence is deliberate: `stored_coverage` counts `YAHOO` rows only, so an asset repaired
    from here still looks un-backfilled to the next run and is still asked for its correction
    window — which is what should happen, since a 21-session window is not a backfill.
    """
    buffer: list[tuple] = []
    rescued: set[str] = set()
    for a in assets:
        sym = a["sourceRef"]
        try:
            bars = chart_bars(sym)
        except Exception as e:  # noqa: BLE001 - one symbol must not cost the repair
            print(f"    {YAHOO_CHART} raised {type(e).__name__} for {sym}")
            continue
        if not bars:
            print(f"    {YAHOO_CHART} had nothing for {sym} either")
            continue
        if reached and bars[-1][0] < reached:
            # It answered, but no further than yfinance did. Worth storing and worth saying: this
            # is the case where the asset really has not traded, not the case where we were
            # throttled, and the two must not read the same in the log.
            print(f"    {YAHOO_CHART} for {sym} also stops at {bars[-1][0]}")
        buffer.extend(
            (a["id"], day, op, hi, lo, close, vol, None, YAHOO_CHART)
            for day, op, hi, lo, close, vol in bars
        )
        rescued.add(sym)
        print(f"    {sym:7} {len(bars)} days recovered from {YAHOO_CHART}")

    insert_snapshots(cur, buffer, replace=False)
    return len(buffer), rescued


def _store_frame(
    cur, assets, frame, today: date, is_full: bool, forming: dict[str, date] | None = None,
) -> tuple[int, dict]:
    """Write one downloaded frame. `is_full` decides replace-versus-upsert.

    A full backfill replaces the asset's rows, because it is authoritative for the whole
    series. An incremental run must never delete: it only holds the correction window, and
    replacing from it would destroy six years of history to save one fetch.

    Returns `(rows written, newest stored day per symbol)`. The second value is what the caller
    needs for partial-day detection, and it is collected here because this is the only place that
    sees the frame per asset. A symbol the frame had no usable column for maps to None rather than
    being left out, so the caller can tell "answered nothing" from "was never asked".

    `forming` maps an asset type to the session that is still being traded, per
    `forming_sessions`. A bar for that day is dropped rather than stored: at `interval=1d` the
    provider reports the live session as an ordinary bar, and its "close" is the last trade so
    far. The cost of storing it is not one soft number — it is read as a **closed session** by
    everything downstream. Measured 2026-10-07, with the US lane fetching at 13:50 UTC and the
    session running 13:30-20:00: AAPL's stored bar for the day held 8.0M shares against 30-50M on
    every neighbouring day, and across 155 US names the newest bar's volume ran at a median of
    **0.21x its own 20-session average**. `VOLUME_CONFIRMS_AT` asks for 1.2x, so the volume leg of
    every US setup failed on arithmetic that had nothing to do with the market: `jobs/setup.py`
    withheld the direction, and `lib/decision.ts` answered WAIT under gate `incomplete` for 90 of
    155 US names. PSX, which comes from its own closing file and is only ever written after the
    bell, read 0.84x the same day — a normal number, and the control that identifies the cause.

    `newest` deliberately reports the newest day **stored**, not the newest the frame offered, so
    dropping the forming bar shows up in the caller's shortfall report as what it is rather than
    being hidden.
    """
    written = 0
    newest: dict[str, date | None] = {a["sourceRef"]: None for a in assets}

    # An empty frame has no `Close` column, and `dropna(subset=["Close"])` raises `KeyError` on
    # it rather than returning nothing. That exception is not `SourceSilent`, so psycopg would
    # roll back the single transaction `main` holds and the crypto and news lanes' rows would go
    # with it — the precise failure `SourceSilent` was introduced to stop. The blocked-provider
    # case has to leave through the guard, not through a column lookup.
    if frame is None or not len(frame):
        print(f"  the frame came back empty for all {len(assets)} symbols")
        return 0, newest

    for a in assets:
        sym = a["sourceRef"]
        try:
            part = frame[sym] if isinstance(frame.columns, pd.MultiIndex) else frame
        except KeyError:
            print(f"  no column for {sym}")
            continue
        part = part.dropna(subset=["Close"])
        if part.empty:
            print(f"  empty history for {sym}")
            continue

        is_forex = a.get("assetType") == "forex"
        open_session = (forming or {}).get(a.get("assetType") or "equity")

        closes: list[tuple[date, float]] = []
        volumes: dict[date, float] = {}
        bars: dict[date, tuple[float | None, float | None, float | None]] = {}

        def num(value):
            """A float, or None for the NaN the source uses for a field it did not publish."""
            return float(value) if value == value and value is not None else None

        dropped_forming = False
        for stamp, row in part.iterrows():
            day = stamp.date()
            # The session still trading. Not an error and not silence: the bar simply does not
            # exist yet, and the asset keeps the close it already had until the bell.
            if open_session is not None and day >= open_session:
                dropped_forming = True
                continue
            closes.append((day, float(row["Close"])))
            vol = row.get("Volume")
            # A currency pair has no published volume and Yahoo answers 0 for every bar of
            # every pair -- FX is over the counter, so there is no consolidated tape to report.
            # Storing that 0 would be writing down a measurement that was never taken, which
            # hard rule 2 forbids, and it would be read as real by three separate places:
            # `avg_volume` in jobs/rank.py averages only non-null volumes and would return 0,
            # `write_rising` uses the volume trend as its second check, and VOLUME_CONFIRMS_AT
            # in lib/decision.ts compares a session against its own average -- 0/0. A null says
            # "not published" and every one of those already handles a null correctly.
            if vol == vol and not (is_forex and not vol):  # not NaN, not an FX placeholder
                volumes[day] = float(vol)
            # The source has always sent these; the job used to drop them on the floor.
            bars[day] = (num(row.get("Open")), num(row.get("High")), num(row.get("Low")))

        if not closes:
            # Everything the frame offered was the forming session. `continue` rather than a
            # write of nothing, because `is_full` would otherwise DELETE the asset's whole
            # stored series and replace it with no rows at all.
            print(f"  {sym:7} nothing closed yet ({open_session} still trading)")
            continue

        if is_full:
            cur.execute('DELETE FROM "PriceSnapshot" WHERE "assetId" = %s', (a["id"],))

        # Share count history, forward filled, so size on a past date uses the share
        # count that was in force on that date. Absent share data means no size row.
        #
        # An incremental run only holds the correction window, so it only recomputes the
        # caps that fall inside it. The snapshot-date caps were written by the backfill and
        # are left alone — asking for a share series covering 2019 on every run is the same
        # waste the price download just stopped doing.
        shares = share_series(sym)
        cap_rows = []
        wanted = SNAPSHOTS + [today] if is_full else [today]
        for snap in wanted:
            close = last_on_or_before(closes, snap)
            if close is None:
                continue
            day = day_on_or_before(closes, snap)
            sh = last_on_or_before(shares, snap) if shares else None
            if sh is None:
                continue
            cap_rows.append((day, close * sh))

        cap_by_day = {day: val for day, val in cap_rows}

        buffer = [
            (
                a["id"], day,
                *bars.get(day, (None, None, None)),
                close, volumes.get(day), cap_by_day.get(day), YAHOO,
            )
            for day, close in closes
        ]
        insert_snapshots(cur, buffer, replace=is_full)
        written += len(buffer)
        # `max`, not the last row: the frame has always come back in date order, but the newest
        # day is the claim being made here and it should not depend on that holding.
        newest[sym] = max(day for day, _ in closes) if closes else None
        print(
            f"  {sym:7} {len(closes)} days to {newest[sym]}, {len(cap_by_day)} size points"
            + ("" if is_full else " (incremental)")
            + (f", {open_session} still trading" if dropped_forming else "")
        )
        time.sleep(0.4)

    return written, newest


_share_cache: dict[str, list[tuple[date, float]]] = {}


def share_series(sym: str) -> list[tuple[date, float]]:
    if sym in _share_cache:
        return _share_cache[sym]
    out: list[tuple[date, float]] = []
    try:
        s = yf.Ticker(sym).get_shares_full(start=START.isoformat())
    except Exception as e:  # noqa: BLE001
        print(f"  shares failed {sym}: {type(e).__name__}")
        s = None
    if s is not None and len(s):
        for stamp, val in s.items():
            if val == val and val:
                out.append((stamp.date(), float(val)))
    _share_cache[sym] = out
    return out


def crypto_rows(asset_id, bars, cap_by_day, source) -> list[tuple]:
    """Daily crypto bars in `PriceSnapshot` column order.

    This exists because the row was built inline as six fields — asset, date, close, volume,
    cap, source — while `insert_snapshots` had grown to the table's nine, and COPY unpacks
    nine names. Every crypto insert raised `ValueError: not enough values to unpack` from
    2026-10-01 until it was fixed, and nothing caught it: the arity is only checked when the
    loop runs, which needs a database. A named builder with a test is the cheap guard.

    `bars` is the normalised shape every venue parser returns — `(day, open, high, low,
    close, volume)` — and `source` is the venue that actually answered, not a constant. The
    row has to carry its own provenance now that three venues can supply it: a reader asking
    why Monday's close differs from the exchange they watch is owed the name of the exchange
    it came from.
    """
    return [
        (asset_id, day, op, hi, lo, close, vol, cap_by_day.get(day), source)
        for day, op, hi, lo, close, vol in bars
    ]


def insert_snapshots(cur, buffer: list[tuple], replace: bool = True) -> None:
    if not buffer:
        return
    if replace:
        # COPY is much faster and the rows for this asset were just deleted, so there is
        # nothing to conflict with.
        with cur.copy(
            'COPY "PriceSnapshot" ("assetId", date, open, high, low, close, volume, '
            '"marketCap", source) FROM STDIN'
        ) as cp:
            for asset_id, day, op, hi, lo, close, vol, cap, source in buffer:
                cp.write_row((asset_id, day, op, hi, lo, close, vol, cap, source))
        return

    # Incremental: upsert, and keep an existing marketCap when this run has none for that
    # day. COALESCE matters — an incremental run computes a cap only for today, and without
    # it every snapshot-date cap would be overwritten with null on the first daily run.
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


# --- Daily crypto closes, from whichever venue answers ------------------------------------------
#
# Binance was the only source of crypto closes, and on 2026-09-29 it stopped answering from GitHub
# runners while answering normally from a laptop. The guard did its job and failed the step loudly,
# which is why the nightly refresh has been red ever since — correctly, and uselessly: a guard that
# reports a blocked venue every night without a second venue to try is a smoke alarm wired to no
# exit. One venue for a number the whole crypto half of the site depends on was the defect.
#
# So the chain. Each venue is tried in order and the first that returns bars wins; the row records
# which one answered, because a reader comparing Monday's close against the exchange they watch is
# owed the name of the exchange it came from. The venues are ordered by history depth: Binance and
# Coinbase can page back to 2019, Kraken holds roughly the last 720 days, and Bitstamp is last
# because it lists the fewest of these coins. All four are public, keyless and already inside the
# fetch helper's cache and per-host delay.
#
# Silence still fails. `require_answer` now fires only when *no* venue answered for *any* coin,
# which is the fact worth failing on: one coin missing from one exchange is ordinary, and every
# venue refusing every coin is a host-level block that a human has to look at.

COINBASE = "Coinbase"
KRAKEN = "Kraken"
BITSTAMP = "Bitstamp"

# Kraken renames two of these: bitcoin is XBT and dogecoin is XDG. It also answers under a key
# that is not the pair you asked for — `XBTUSD` comes back as `XXBTZUSD` — so the parser takes
# whatever single series the response holds rather than looking the name up.
KRAKEN_ALIAS = {"BTC": "XBT", "DOGE": "XDG"}


def parse_binance(payload) -> list[tuple]:
    """Binance klines to `(day, open, high, low, close, volume)`.

    A kline is `[openTime, open, high, low, close, volume, ...]` with millisecond times.
    """
    out = []
    for b in payload or []:
        day = datetime.fromtimestamp(b[0] / 1000, tz=timezone.utc).date()
        out.append((day, float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5])))
    return out


def parse_coinbase(payload) -> list[tuple]:
    """Coinbase candles to the same shape.

    A candle is `[time, low, high, open, close, volume]` in seconds — note that low and high
    come *before* open, which is not the order any other venue here uses and is exactly the
    kind of thing that silently swaps two columns. Returned newest first, so this sorts.
    """
    out = []
    for c in payload or []:
        day = datetime.fromtimestamp(c[0], tz=timezone.utc).date()
        out.append((day, float(c[3]), float(c[2]), float(c[1]), float(c[4]), float(c[5])))
    return sorted(out)


def parse_kraken(payload) -> list[tuple]:
    """Kraken OHLC to the same shape.

    The body is `{"error": [...], "result": {"<PAIR>": [[time, open, high, low, close, vwap,
    volume, count], ...], "last": <int>}}`. `last` is a cursor and not a series, so it is
    skipped; the pair key is whatever is left, because Kraken does not echo the name asked for.
    """
    if not payload or payload.get("error"):
        return []
    result = payload.get("result") or {}
    series = next((v for k, v in result.items() if k != "last" and isinstance(v, list)), None)
    out = []
    for c in series or []:
        day = datetime.fromtimestamp(int(c[0]), tz=timezone.utc).date()
        out.append((day, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[6])))
    return sorted(out)


def parse_bitstamp(payload) -> list[tuple]:
    """Bitstamp OHLC to the same shape. Body is `{"data": {"ohlc": [{...}, ...]}}`."""
    rows = ((payload or {}).get("data") or {}).get("ohlc") or []
    out = []
    for c in rows:
        day = datetime.fromtimestamp(int(c["timestamp"]), tz=timezone.utc).date()
        out.append(
            (day, float(c["open"]), float(c["high"]), float(c["low"]),
             float(c["close"]), float(c["volume"]))
        )
    return sorted(out)


def binance_bars(sym: str) -> list[tuple]:
    """Paged forward from 2019; a klines page holds at most 1000 rows."""
    bars: list[tuple] = []
    cursor = 1546300800000
    for page in range(8):
        payload = get_json(
            f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1d"
            f"&startTime={cursor}&limit=1000",
            cache_key=f"binance-{sym}-{cursor}",
            ttl=6 * 3600 if page == 0 else 30 * 24 * 3600,
        )
        if not payload:
            break
        bars.extend(parse_binance(payload))
        cursor = payload[-1][0] + 86400000
        if len(payload) < 1000:
            break
    return bars


def coinbase_bars(sym: str) -> list[tuple]:
    """Paged backwards in windows, because Coinbase caps an explicit range at 300 aggregations.

    Measured, not assumed: a 300-day span returns 301 rows and HTTP 200, a 301-day span returns
    HTTP 400 "Count of aggregations requested exceeds 300". The window below is 290 to leave
    margin. With no range at all the endpoint returns 350 rows, which is more than the capped
    maximum and is the kind of inconsistency that makes a loop sized from the default fail on
    its second page.

    An empty array means "before this product was listed", not a failure — Coinbase answers 200
    with `[]` for a window older than the listing — so an empty page ends the walk.
    """
    bars: dict = {}
    end = datetime.now(timezone.utc)
    for page in range(14):
        start = end - timedelta(days=290)
        payload = get_json(
            f"https://api.exchange.coinbase.com/products/{sym}-USD/candles"
            f"?granularity=86400&start={start.date().isoformat()}&end={end.date().isoformat()}",
            cache_key=f"coinbase-{sym}-{end.date().isoformat()}",
            ttl=6 * 3600 if page == 0 else 30 * 24 * 3600,
        )
        rows = parse_coinbase(payload)
        if not rows:
            break
        for r in rows:
            bars[r[0]] = r
        end = start
        if start.year < 2019:
            break
    return [bars[d] for d in sorted(bars)]


def kraken_bars(sym: str) -> list[tuple]:
    """Roughly the last 720 days. `since` only moves forward, so there is no paging back."""
    pair = KRAKEN_ALIAS.get(sym, sym)
    return parse_kraken(
        get_json(
            f"https://api.kraken.com/0/public/OHLC?pair={pair}USD&interval=1440",
            cache_key=f"kraken-{pair}",
            ttl=6 * 3600,
        )
    )


def bitstamp_bars(sym: str) -> list[tuple]:
    return parse_bitstamp(
        get_json(
            f"https://www.bitstamp.net/api/v2/ohlc/{sym.lower()}usd/?step=86400&limit=1000",
            cache_key=f"bitstamp-{sym}",
            ttl=6 * 3600,
        )
    )


# Ordered by history depth, deepest first. The label is what lands in `PriceSnapshot.source`.
CLOSE_VENUES = (
    (BINANCE, binance_bars),
    (COINBASE, coinbase_bars),
    (KRAKEN, kraken_bars),
    (BITSTAMP, bitstamp_bars),
)
CRYPTO_CHAIN = "Binance, Coinbase, Kraken or Bitstamp"


# How stale a venue's newest bar may be before the chain keeps looking. Two days matches the
# freshness rule the decision panel applies to crypto, so a venue whose answer would make every
# coin read "data stale" is not treated as having answered.
CRYPTO_FRESH_DAYS = 2


def crypto_closes(sym: str, today: date | None = None) -> tuple[str | None, list[tuple]]:
    """The first venue with a *current* series, and its bars.

    First-non-empty is the obvious rule and the wrong one. A venue can answer with a series
    that stops days ago — which is exactly what Binance did on 2026-09-29, and what a cached
    page does — and taking it because it was first would store a stale close, pass the silence
    guard, and leave every coin reading "data stale" on the panel with nothing explaining why.
    So a venue has to be both answering and current to win.

    When no venue is current, the deepest non-empty answer is still returned rather than
    nothing: stale rows are worth storing, the freshness gate in the decision rules will catch
    them, and the alternative is throwing away history to make a point. The caller is told
    which venue it came from either way.
    """
    today = today or datetime.now(timezone.utc).date()
    fallback: tuple[str, list[tuple]] | None = None
    for name, fetch in CLOSE_VENUES:
        try:
            bars = fetch(sym)
        except Exception as e:  # noqa: BLE001
            # A venue raising is the same outcome as a venue answering nothing: try the next
            # one. It is printed rather than swallowed, because a venue that starts raising
            # every night is a thing to fix even while the chain hides it.
            print(f"    {name} raised {type(e).__name__} for {sym}")
            continue
        if not bars:
            continue
        if (today - bars[-1][0]).days <= CRYPTO_FRESH_DAYS:
            return name, bars
        print(f"    {name} answered {sym} but stops at {bars[-1][0]}, trying the next venue")
        if fallback is None or len(bars) > len(fallback[1]):
            fallback = (name, bars)
    return fallback if fallback else (None, [])


def fetch_crypto(cur) -> int:
    step("crypto history")
    assets = crypto_assets(cur)
    tickers = get_json(
        "https://api.coinpaprika.com/v1/tickers?quotes=USD",
        cache_key="paprika-tickers",
        ttl=12 * 3600,
    ) or []
    by_id = {t["id"]: t for t in tickers}

    # How many rows each coin already has, in one query rather than one per coin. The depth is
    # needed to decide replace-versus-upsert below, and asking inside the loop is the shape the
    # in-loop query budget exists to stop.
    depth = {
        r["assetId"]: r["n"]
        for r in rows(
            cur,
            'SELECT "assetId", count(*) AS n FROM "PriceSnapshot" '
            'WHERE "assetId" = ANY(%s) GROUP BY "assetId"',
            ([a["id"] for a in assets],),
        )
    }

    written = 0
    answered = 0
    used: dict[str, int] = {}
    for a in assets:
        cid = a["sourceRef"]
        meta = by_id.get(cid)
        sym = (meta or {}).get("symbol") or cid.split("-")[0].upper()

        source, bars = crypto_closes(sym)

        # No venue answered for this coin. That is data about the coin, not about the host, so
        # it costs this coin its rows and nothing else; `require_answer` below decides whether
        # the whole lane was blocked. The check sits before the market cap because CoinPaprika
        # is not geo-blocked and the exchanges are, so the one host where `bars` is empty is
        # exactly the host where a cap is present, and dating a cap off an empty series raised
        # IndexError instead of reporting a blocked source.
        if not bars:
            print(f"  {cid}: no closes from {CRYPTO_CHAIN}, skipped")
            continue

        # Market cap. CoinPaprika publishes today's market cap for every coin. No free source
        # publishes circulating supply by year, so no historical cap is stored rather than one
        # backfilled from today's supply. That is why the crypto industry is ranked by return
        # and not by size. Cap stays on CoinPaprika whichever venue supplied the closes.
        today_cap = ((meta or {}).get("quotes", {}).get("USD", {}) or {}).get("market_cap")
        cap_by_day = {}
        if today_cap:
            cap_by_day[bars[-1][0]] = float(today_cap)

        # Never shrink the stored series. Binance and Coinbase page back to 2019; Kraken holds
        # about 720 days and Bitstamp less. Deleting six years of history and rewriting it from
        # a shallow venue would lose the rows every analog and horizon in the brain is measured
        # over — and it would look like a successful run. So a replace only happens when the
        # fetch is at least as deep as what is stored; otherwise the new days are upserted on
        # top. This is the same invariant `_store_frame` states for the Yahoo lane.
        stored = depth.get(a["id"], 0)
        replace = len(bars) >= stored
        if replace:
            cur.execute('DELETE FROM "PriceSnapshot" WHERE "assetId" = %s', (a["id"],))

        buffer = crypto_rows(a["id"], bars, cap_by_day, source)
        insert_snapshots(cur, buffer, replace=replace)
        written += len(buffer)
        answered += 1
        used[source] = used.get(source, 0) + 1
        how = "replaced" if replace else f"kept {stored} stored, upserted"
        print(f"  {sym:6} {len(bars):5} days from {source:9} ({how}), {len(cap_by_day)} size point")

    if used:
        print("  venues that answered: " + ", ".join(f"{k} x{v}" for k, v in sorted(used.items())))

    # One coin answering nothing is data and is printed above. No coin answering from any venue
    # is a fact about this host, and it is the only condition worth failing the step for: with
    # four public venues tried in turn, that can no longer mean one exchange is geo-blocked.
    require_answer(answered, len(assets), source=CRYPTO_CHAIN)
    return written


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


NEWS_TERMS = {
    "mega-cap-tech": "Nvidia Microsoft Apple AI spending",
    "semiconductors": "semiconductor chip export controls",
    "crypto": "bitcoin crypto market ETF",
    "precious-metals": "gold silver price central bank",
    "energy": "oil natural gas OPEC energy demand",
    "healthcare": "FDA obesity drug pharma earnings",
    "financials": "bank interest rates earnings credit",
}

# A bare company name is often the wrong search. "Apple" returns fruit and airlines,
# "Meta" returns metadata, "Oracle" returns crypto price prediction, and a metal ETF's
# name rarely appears in a headline. These give the feed a word that means the company.
ASSET_NEWS_HINTS = {
    "AAPL": "iPhone",
    "AMZN": "AWS",
    "GOOGL": "Google",
    "META": "Zuckerberg",
    "ORCL": "cloud",
    "avax-avalanche": "AVAX",
    "COPX": "copper",
    "CPER": "copper",
    "GC=F": "gold",
    "GLD": "gold",
    "IAU": "gold",
    "PALL": "palladium",
    "PPLT": "platinum",
    "SI=F": "silver",
    "SIVR": "silver",
    "SLV": "silver",
    "NFLX": "streaming",
    "TSLA": "electric vehicle",
    "NVO": "insulin",
    "LLY": "GLP-1",
    "JPM": "banking",
    "BAC": "banking",
    "C": "bank",
    "GS": "investment bank",
    "MS": "investment bank",
    "WFC": "bank",
    "AXP": "credit card",
    "BLK": "asset management",
    "SCHW": "brokerage",
    "PGR": "insurance",
    "XOM": "oil",
    "CVX": "oil",
    "COP": "oil",
    "EOG": "oil",
    "MPC": "refining",
    "PSX": "refining",
    "VLO": "refining",
    "OXY": "oil",
    "SHEL": "oil",
    "SLB": "oilfield services",
    "MU": "memory chips",
    "LRCX": "chip equipment",
    "KLAC": "chip equipment",
    "AMGN": "biotech",
    "GILD": "antiviral",
    "ISRG": "surgical robot",
    "DHR": "medical devices",
    "ABBV": "pharma",
    "MRK": "vaccine",
    "VRTX": "biotech",
    "TSM": "foundry",
    "ASML": "lithography",
    "ARM": "chip design",
    "QCOM": "mobile chips",
    "INTC": "foundry",
    "AMD": "accelerator",
    "TXN": "analog chips",
}


def asset_news_term(a: dict) -> str:
    """A search that names this asset. Each kind needs a different key."""
    kind = a["assetType"]
    hint = ASSET_NEWS_HINTS.get(a["symbol"])
    if a.get("source") == PSX:
        # A PSX ticker is three to six letters that mean something else in English news:
        # "PSO" and "MARI" and "ILP" all return unrelated results, and the company names
        # are shared with firms in other countries. The country word is what separates
        # Pakistani coverage from the rest, and it is how the local press writes it.
        return f'"{a["name"]}" Pakistan'
    if kind == "etf":
        # A fund's formal name is almost never quoted in a headline, and the brand is
        # written in lower case, so a quoted "abrdn Silver Shares" returns nothing at all.
        # The ticker is what financial news prints, so lead with that.
        base = f'"{a["symbol"]}"'
    elif kind == "crypto":
        base = a["name"]
    elif kind == "commodity":
        # A futures contract is named by its underlying in every headline, never by symbol.
        return hint or a["name"]
    elif kind == "forex":
        # The stored name is "US Dollar / Pakistani Rupee", which no headline has ever been
        # written in. The press names a pair either by its two currencies or by the ticker, so
        # the search is built from the symbol -- "USD PKR exchange rate" -- which matches both
        # the wire style ("USD/PKR") and the plain style ("dollar rupee"). Quoting it would be
        # worse: the quoted form appears in rate tables and almost never in a story.
        sym = a["symbol"]
        return f"{sym[:3]} {sym[3:]} exchange rate"
    else:
        base = f'"{a["name"]}"'
    return f"{base} {hint}" if hint else base


def gnews_url(term: str, *, window_days: int = NEWS_WINDOW_DAYS) -> str:
    """The Google News RSS url for a search, date-windowed.

    Every feed in this lane is built here so the window cannot be on some queries and off
    others. A term that reaches Google without `when:` is answered by relevance over the whole
    index, which is the failure `NEWS_WINDOW_DAYS` describes.
    """
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(f"{term} when:{window_days}d")
        + "&hl=en-US&gl=US&ceid=US:en"
    )


def bing_url(term: str) -> str:
    """Bing News RSS for a search.

    No date operator, and none is needed: the feed answers newest-first and `ingest` checks
    every item's own `pubDate` against the window anyway. Verified 2026-10-07 — 11 items for
    `"Lucky Cement" Pakistan`, the first being that week's GEPCO privatisation story, which is
    the kind of local company news the primary feed was ranking below a 2024 article.
    """
    return "https://www.bing.com/news/search?q=" + urllib.parse.quote(term) + "&format=RSS"


def yahoo_rss_url(symbol: str) -> str:
    """Yahoo Finance's own headline feed for one ticker.

    Verified 2026-10-07: 18 items for AAPL. It is last in the chain and offered to listed US
    names only, because it answered **nothing at all** for `USDPKR=X`, and for a Karachi ticker
    (`SYS.KA`) it answered with three stories about core banking at other banks entirely -- real
    articles, not about the company asked for, which is what the token guard is there to catch.
    """
    return (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s="
        + urllib.parse.quote(symbol)
        + "&region=US&lang=en-US"
    )


def fallback_feeds(a: dict) -> list[tuple[str, str]]:
    """The sources to try for this asset, in order, after the primary came back thin.

    Rule 2 says a source that stops answering is marked unavailable and not silently
    substituted. This is the other case: the primary answers, and for some names it answers
    thinly. So the substitution is not silent — each item is stored under the name of the source
    that produced it, the run prints which assets needed a fallback and how many feeds each
    source answered, and `brain.md` records what every one of them was verified to do.

    Ordered per kind rather than one list for everything, because what a source is good for
    differs by instrument and a chain that ignores that spends requests to learn it again every
    run. The PSX names go to Bing with the country word, which is where the local press is
    indexed. A dollar pair asks about the quote currency, since "exchange rate" headlines name
    the currency and not the code. Yahoo's per-ticker feed is offered only to US listings, for
    the reason in `yahoo_rss_url`.
    """
    kind = a["assetType"]
    symbol = a["symbol"]
    name = a["name"]

    if a.get("source") == PSX:
        return [(BING, bing_url(f'"{name}" Pakistan'))]
    if kind == "forex":
        # The pair's own name, which reads "US Dollar / Pakistani Rupee", is the only place the
        # currency words are stored. Asking Bing for "Pakistani Rupee exchange rate" finds the
        # rupee coverage that "USD PKR exchange rate" ranks a conversion table above.
        quote_side = [p.strip() for p in name.split("/")][-1]
        return [(BING, bing_url(f"{quote_side} exchange rate"))]
    if kind == "crypto":
        return [(BING, bing_url(f"{name} {symbol} price"))]
    if kind in ("etf", "commodity"):
        hint = ASSET_NEWS_HINTS.get(symbol)
        return [(BING, bing_url(f"{hint} price" if hint else f'"{symbol}"'))]
    # A listed company: both sources, Bing first for the same reason it leads everywhere else --
    # it answers a name, where Yahoo answers a ticker and will hand back the sector's news.
    return [(BING, bing_url(f'"{name}"')), (YAHOO_RSS, yahoo_rss_url(symbol))]


# Trailing words that say what legal form a company takes rather than which company it is.
#
# The press writes "Indus Motor", not "Indus Motor Company"; "Systems Limited" keeps its second
# word because that is how it is always printed, and the trim is applied as an *extra* token
# rather than a replacement, so both forms match. Only the corporate form is trimmed and never
# an industry word: "Kohinoor Industries" and "Kohinoor Textile Mills" are two listed companies,
# and trimming either to "Kohinoor" would file one's coverage against the other.
CORPORATE_SUFFIXES = ("company", "limited", "ltd", "ltd.", "corporation", "corp", "corp.",
                      "inc", "inc.", "plc", "holdings", "co.")

# Titles that are a rate table rather than an article.
#
# The workflow has been called "rss ingest, dedupe, junk filter" since it was written and no
# junk filter existed. Narrowing the news window is what made one necessary: `USDSEK` came back
# with six items inside the window, every one of them "Convert 1 USDC (USD Coin) to SEK (Swedish
# Krona) - Bybit". Each genuinely names the currency, each is recent, and none is news — they are
# a conversion widget with a date on it. Stored, they would be six headlines of neutral wording
# feeding a tone read and six items feeding an attention count, which is how a currency comes to
# look well covered and reads flat for ever.
#
# Kept to the one shape that was actually measured, matched at the start of a title so a story
# *about* a conversion is not caught by a word in the middle of its headline.
JUNK_TITLE_PREFIXES = ("convert ",)


def is_junk_headline(title: str) -> bool:
    """A title that carries a date and a currency and is not a story. See JUNK_TITLE_PREFIXES."""
    low = title.strip().lower()
    return any(low.startswith(p) for p in JUNK_TITLE_PREFIXES)


def news_matcher(a: dict) -> re.Pattern[str]:
    """Does a headline name this asset? One matcher, so the rule is stated once.

    Two kinds of token, matched by two different rules, because a company name and a ticker
    fail in opposite directions:

    * **A name or an underlying word** is matched case-insensitively anywhere in the title.
      "Hub Power Company Reports PKR 33M Loss" names the company in plain words.
    * **A ticker** is matched as a whole word and **case-sensitively**, which a substring test
      got badly wrong. `SYS` as a lowercase substring matched "Micro Irrigation **Sys**tem
      Market", "Organic Recycling **Sys**tems" and "Indias Biogas **Sys**tem" — five of the six
      items it would have stored for Systems Limited were about other companies entirely.
      Tickers are printed in capitals ("SYS Insider Buy"), and nothing else in a headline is, so
      the case is the signal that separates a ticker from an English word that contains it.
    """
    phrases = [re.escape(t) for t in news_match_tokens(a) if t]
    symbol = (a["symbol"] or "").strip()
    parts = []
    if phrases:
        parts.append("(?i:" + "|".join(phrases) + ")")
    if symbol:
        parts.append(r"\b" + re.escape(symbol) + r"\b")
    # An asset with neither is impossible from the seed, and a pattern matching everything would
    # be the worst of the three outcomes, so it matches nothing instead.
    return re.compile("|".join(parts) if parts else r"(?!)")


def news_match_tokens(a: dict) -> tuple[str, ...]:
    """Lowercase phrases, any one of which means a headline is about this asset.

    The ticker is deliberately **not** here: it is matched by a different rule, stated in
    `news_matcher`, which is the only thing that should be reading these.

    This is the other half of narrowing the window, and it is needed *because* of the
    narrowing. Relevance ranking over a month rather than over the index promotes weaker
    matches to the top: `"Systems Limited" Pakistan when:14d` returns an Indian biogas story
    and a Lockheed Martin procurement piece in its first six. Stored against SYS those become
    input to a tone word-list and an attention count, so they are not noise on a page — they
    are a reading of a company built out of articles about someone else.

    **Any token, not all.** A headline names a company one way, not every way: "Hub Power
    Company Reports PKR 33M Loss" carries the name and not the ticker, "SYS Insider Buy"
    carries the ticker and not the name. Requiring both would drop each of them.

    Derived from the same facts `asset_news_term` builds the query from, and for the same
    reason the terms live in one function: a guard that disagrees with the query it is guarding
    would silently drop a whole kind of asset, and the kind most likely to be dropped is the one
    with the least coverage to begin with.
    """
    kind = a["assetType"]
    symbol = (a["symbol"] or "").lower()
    name = (a["name"] or "").lower()
    hint = (ASSET_NEWS_HINTS.get(a["symbol"]) or "").lower()

    def without_corporate_form(n: str) -> str:
        """"Indus Motor Company" -> "indus motor". Empty when there is nothing safe to trim.

        **Two words have to survive.** Trimming to a single word turns a company name into an
        English one: "Systems Limited" becomes "systems", which matched "Organic Recycling
        Systems" and "Micro Irrigation System Market" -- the same class of false match the
        ticker rule exists to stop, arriving by the other door. A one-word remainder is not a
        name, so the trim is refused and the full name stays the only phrase token.
        """
        words = n.split()
        while len(words) > 2 and words[-1] in CORPORATE_SUFFIXES:
            words.pop()
        trimmed = " ".join(words)
        return trimmed if trimmed != n else ""

    if kind == "forex":
        # The stored name is "US Dollar / Pakistani Rupee". The press writes the pair either as
        # the codes ("USD/PKR") or as the currencies ("rupee", "krona", "ringgit"), and the word
        # that distinguishes one pair from another is the *quote* currency, because every pair
        # here is quoted against the dollar. So the last word of the right-hand side is the token
        # that matters, taken from the stored name rather than from a second table of currency
        # words that would have to be kept in step with the seed.
        parts = [p.strip() for p in name.split("/")]
        quote_word = parts[-1].split()[-1] if parts and parts[-1] else ""
        base_word = parts[0].split()[-1] if len(parts) > 1 and parts[0] else ""
        tokens = [f"{symbol[:3]}/{symbol[3:]}", quote_word]
        # "dollar" alone would match every FX story ever written, so the base currency is only
        # accepted next to the quote currency's own word, which the pair form above already is.
        if base_word and quote_word:
            tokens.append(f"{base_word} {quote_word}")
        return tuple(t for t in tokens if t)

    if kind in ("etf", "commodity"):
        # A fund or a futures contract is named in headlines by its underlying, which is exactly
        # what the hint holds. The formal fund name is not a useful token -- a quoted "abrdn
        # Silver Shares" matches no headline ever written.
        return tuple(t for t in (hint,) if t)

    if a.get("source") == PSX:
        # The full company name, plus the form the press actually prints. "Indus Motor Company"
        # appeared in no headline inside the window; "Indus Motor" is how it is written, and the
        # trim is what finds it. The ticker is matched separately and by case, because a Karachi
        # ticker is three to six letters that mean other things in English -- "PSO", "MARI",
        # "ILP", and "SYS" inside "System".
        return tuple(t for t in (name, without_corporate_form(name)) if t)

    if kind == "crypto":
        # The stored name is the coin ("Bitcoin"), and the ticker is how a price story names it.
        return tuple(t for t in (name,) if t)

    # A listed company. The first significant word of the name is what a headline carries --
    # "Apple" for "Apple Inc.", "Lockheed" for "Lockheed Martin Corp" -- and the quoted search
    # has already decided which company is being asked about, so this only has to establish that
    # the company is named at all.
    #
    # The hint is a token here and not only a search word, because for several names it *is* how
    # the press writes the company: Alphabet is "Google" in every headline, and a guard holding
    # only "alphabet" would drop the coverage the hint was added to find.
    head = name.split()[0] if name else ""
    return tuple(t for t in (head, hint) if t)


def fetch_news(cur) -> int:
    step("news")
    written = 0
    industries = rows(cur, 'SELECT id, slug FROM "Industry"')
    products = rows(cur, 'SELECT id, name FROM "Product"')
    assets = rows(
        cur, 'SELECT id, symbol, name, "assetType", source FROM "Asset" ORDER BY symbol'
    )

    # Two counters, because they answer different questions. `written` is new rows, which is
    # legitimately 0 on a rerun inside the cache hour — every article is already stored and
    # ON CONFLICT DO NOTHING reports nothing. `parsed` is feeds that answered with readable
    # RSS, and that being 0 across every feed is Google News refusing this host.
    #
    # Kept **per source**, which rule 31 is the reason for. One pair of counters across a
    # primary and its fallbacks is the counter that cannot see the fault it exists to catch: a
    # Google News blackout would be answered by Bing on the thin names, the mixed `parsed`
    # would come back healthy, and the lane would report a good run while the source every
    # asset depends on had gone silent. A fallback must never be able to vouch for a primary.
    tally: dict[str, list[int]] = {}

    def note(source: str, *, answered: bool) -> None:
        row = tally.setdefault(source, [0, 0])
        row[0] += 1
        if answered:
            row[1] += 1

    def ingest(url, cache_key, insert_sql, params_fn, cap=NEWS_PER_FEED, matcher=None,
               source=GNEWS):
        """Read one feed and store the items that are both recent and about this target.

        Returns the number of items stored or already held -- that is, the items that passed
        both guards -- so a caller can tell a feed that answered thinly from one that answered
        with a month of someone else's news. `written` cannot answer that: it counts *new* rows
        and is legitimately 0 for a target whose six items are all already stored.
        """
        nonlocal written
        raw = get(url, cache_key=cache_key, ttl=3600)
        if not raw:
            note(source, answered=False)
            return 0
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            note(source, answered=False)
            print("  bad rss")
            return 0
        note(source, answered=True)
        # Naive UTC, like every other timestamp here, and built the way rule 27 requires: an
        # aware `now` converted to UTC and then stripped, never a local clock read.
        oldest_allowed = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=NEWS_WINDOW_DAYS + NEWS_WINDOW_SLACK_DAYS
        )
        kept_here = 0
        stale = 0
        off_target = 0
        junk = 0
        for item in root.iter():
            if not item.tag.endswith("item") or kept_here >= cap:
                continue
            gett = {c.tag.split("}")[-1]: (c.text or "").strip() for c in item}
            title = gett.get("title", "")
            link = gett.get("link", "")
            pub = gett.get("pubDate", "")
            if not title or not link:
                continue
            publisher = title.rsplit(" - ", 1)[-1] if " - " in title else ""
            try:
                # strptime in this Python rejects a bare "GMT", so name the offset.
                when = datetime.strptime(
                    pub.replace("GMT", "+0000").replace("UTC", "+0000"),
                    "%a, %d %b %Y %H:%M:%S %z",
                ).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue
            # The window, checked rather than trusted. See NEWS_WINDOW_DAYS: the query asks for
            # it and this is what makes it true of the stored row.
            if when < oldest_allowed:
                stale += 1
                continue
            # A rate table with a date on it is not a story, whatever it names. Applied to every
            # feed, because a conversion widget is junk on an industry page too.
            if is_junk_headline(title):
                junk += 1
                continue
            # Is the headline about this target at all? Only asset feeds pass a matcher: an
            # industry feed is a search for a subject rather than for a name, and a product feed
            # is already a quoted product name, so there is nothing to check them against.
            if matcher is not None and not matcher.search(title):
                off_target += 1
                continue
            cur.execute(
                insert_sql,
                params_fn(when, title, link, publisher, source),
            )
            written += cur.rowcount if cur.rowcount > 0 else 0
            kept_here += 1
        dropped = ""
        if stale or off_target or junk:
            dropped = f" (dropped {stale} stale, {off_target} off-target, {junk} junk)"
        print(f"  {kept_here} from {cache_key}{dropped}")
        return kept_here

    news_sql = """
        INSERT INTO "News" ("industryId", title, url, publisher, "publishedAt", source, "createdAt")
        VALUES (%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT ("industryId", url)
        WHERE "assetId" IS NULL AND "productId" IS NULL AND "industryId" IS NOT NULL
        DO NOTHING
    """
    prod_sql = """
        INSERT INTO "News" ("productId", title, url, publisher, "publishedAt", source, "createdAt")
        VALUES (%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT ("productId", url)
        WHERE "productId" IS NOT NULL AND "assetId" IS NULL DO NOTHING
    """
    asset_sql = """
        INSERT INTO "News" ("assetId", title, url, publisher, "publishedAt", source, "createdAt")
        VALUES (%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT ("assetId", url) WHERE "assetId" IS NOT NULL DO NOTHING
    """

    for ind in industries:
        term = NEWS_TERMS.get(ind["slug"], ind["slug"])
        ingest(
            gnews_url(term),
            # Versioned with the window: the response is cached by key, so a query that has
            # gained `when:` has to ask under a new key or the hour's stale answer is reused.
            f"gnews-ind-v2-{ind['slug']}",
            news_sql,
            lambda w, t, l, p, s, i=ind: (i["id"], t, l, p, w, s),
        )

    for prod in products:
        ingest(
            gnews_url(f'"{prod["name"]}"'),
            f"gnews-pr-v2-{prod['id']}",
            prod_sql,
            lambda w, t, l, p, s, pr=prod: (pr["id"], t, l, p, w, s),
        )

    # Asset pages. An article is stored once per target, so the same story can appear on an
    # asset, a product and an industry at once, which is what a reader of each page wants.
    # The query stays narrow anyway: naming the company is what finds the coverage stories
    # for that company rather than generic news about its industry.
    #
    # Each asset walks the chain until it has `NEWS_FLOOR` recent on-target items. The chain is
    # ordered by how much each source is trusted to be *about* the name asked for, which is not
    # the same as how much coverage it holds: Google first because it indexes the local press,
    # then Bing, then Yahoo's own per-ticker feed. Every item carries the name of the source
    # that produced it, so a reader and `coverage_report` can both see which of them answered.
    empty = []
    fell_through = []
    fallback_budget = NEWS_FALLBACK_BUDGET
    budget_spent_on = 0
    for a in assets:
        matcher = news_matcher(a)
        kept = ingest(
            gnews_url(asset_news_term(a)),
            # Versioned: the feed is cached by key, so a term that changes has to change
            # the key too or a stale response is reused for the rest of the hour.
            f"gnews-as-v3-{a['symbol']}",
            asset_sql,
            lambda w, t, l, p, s, x=a: (x["id"], t, l, p, w, s),
            cap=NEWS_PER_ASSET,
            matcher=matcher,
        )
        if kept < NEWS_FLOOR and fallback_budget > 0:
            for source, url in fallback_feeds(a):
                if fallback_budget <= 0:
                    break
                fallback_budget -= 1
                kept += ingest(
                    url,
                    f"{source.split()[0].lower()}-as-v1-{a['symbol']}",
                    asset_sql,
                    lambda w, t, l, p, s, x=a: (x["id"], t, l, p, w, s),
                    cap=NEWS_PER_ASSET - kept,
                    matcher=matcher,
                    source=source,
                )
                if kept >= NEWS_FLOOR:
                    break
            if kept:
                fell_through.append(a["symbol"])
            budget_spent_on += 1
        if not kept:
            empty.append(a["symbol"])
    spent = NEWS_FALLBACK_BUDGET - fallback_budget
    if spent:
        print(f"  fallback requests: {spent} of {NEWS_FALLBACK_BUDGET} budget, over {budget_spent_on} assets")
    if fallback_budget <= 0:
        # Not a failure, and said out loud rather than inferred from a short list. Every name
        # past this point kept whatever the primary gave it.
        print(
            f"  fallback ceiling of {NEWS_FALLBACK_BUDGET} reached, so later thin assets were "
            "left with the primary feed alone"
        )
    if fell_through:
        print(
            f"  {len(fell_through)} assets needed a fallback source: "
            f"{', '.join(fell_through)}"
        )
    if empty:
        # Reworded, because the old sentence measured the wrong thing. It said "matched no new
        # article" on a `written` of 0, which is also what a target whose six items are all
        # already stored looks like — so the busiest names appeared in a list of the emptiest.
        print(f"  {len(empty)} assets have no recent article from any source: {', '.join(empty)}")

    # Before the sweep, not after: a host that got no feed at all must not go on to
    # delete four months of stored articles on the strength of nothing.
    #
    # Google only. A fallback is asked about thin names alone, so its own `asked` is a handful
    # of feeds on a good day and a hundred on a bad one -- a denominator that moves with the
    # health of the primary, which makes it useless as a measure of anything. See `tally`.
    g_asked, g_parsed = tally.get(GNEWS, [0, 0])
    require_answer(g_parsed, g_asked, source=GNEWS)
    for source, (s_asked, s_parsed) in sorted(tally.items()):
        if source != GNEWS:
            print(f"  {source}: {s_parsed} of {s_asked} feeds answered")

    cur.execute('DELETE FROM "News" WHERE "publishedAt" < now() - interval \'120 days\'')
    return written


def coverage_line(source: str, n: int, newest, today: date) -> str:
    """One source's state in a line: rows, newest date, and how far behind that is.

    The age is what makes it readable at a glance. A source that answered but is four days
    stale is a different problem from one that answered nothing, and the count alone hides
    it — the table stood at 123 MB of rows while Binance had stopped days earlier.
    """
    if not n or newest is None:
        return f"  {source:40} no rows at all"
    behind = (today - newest).days
    age = "today" if behind <= 0 else ("yesterday" if behind == 1 else f"{behind} days behind")
    return f"  {source:40} {n:>8} rows, newest {newest} ({age})"


def coverage_report(cur) -> None:
    """Per source, not just the total, printed at the end of every run.

    A single total is what let a dead source hide: `PriceSnapshot` keeps growing from the
    lanes that still work. Yahoo, Binance and the PSX closing files each get their own line,
    so the newest date and count asked for after a refresh are in the step's own output.
    """
    step("coverage by source")
    today = date.today()
    for r in rows(
        cur,
        """
        SELECT source, count(*) AS n, max(date) AS newest
        FROM "PriceSnapshot" GROUP BY source ORDER BY source
        """,
    ):
        print(coverage_line(r["source"], int(r["n"]), r["newest"], today))


def fail_on_silent(silent: list[str]) -> None:
    """Exit non-zero once the writes are committed, naming every source that said nothing.

    Called after the transaction closes, never inside it. A step that reports a blocked
    source and keeps the rows the other sources returned is what the refresh lane needs: the
    group goes on, the site serves what landed, and the log names what to re-verify.
    """
    if not silent:
        return
    print()
    print(f"{len(silent)} source(s) answered for nothing: " + "; ".join(silent))
    print("the rows the other sources returned are committed and kept")
    raise SystemExit(1)


def main() -> None:
    conn = db()
    # `--chunk 2/4` means "the second of four slices of this lane's work". The runner passes it
    # only to jobs whose source contains the literal `--chunk`, which is why the flag is parsed
    # here rather than tolerated silently: a lane that ignored it would fetch the whole source
    # once per slice, which for four slices four times a day is sixteen full downloads of the
    # same eighty symbols and four writers racing on the same rows.
    argv = list(sys.argv[1:])
    chunk = None
    if "--chunk" in argv:
        at = argv.index("--chunk")
        if at + 1 >= len(argv):
            print("--chunk needs a value like 2/4")
            raise SystemExit(2)
        try:
            chunk = parse_chunk(argv[at + 1])
        except ValueError as e:
            print(f"--chunk: {e}")
            raise SystemExit(2) from e
        del argv[at:at + 2]

    todo = set(argv) or {"yahoo", "crypto", "news"}
    silent: list[str] = []
    with conn, conn.cursor() as cur:
        # Each lane is caught on its own. A SourceSilent is our own exception and not a
        # database error, so the transaction is still usable and the next lane can write.
        if "yahoo" in todo:
            try:
                n1 = fetch_yahoo(cur, chunk=chunk)
                step("yahoo total")
                print(f"  {n1} price rows")
            except SourceSilent as e:
                silent.append(str(e))
        if "crypto" in todo:
            try:
                n2 = fetch_crypto(cur)
                print(f"  {n2} crypto price rows")
            except SourceSilent as e:
                silent.append(str(e))
        if "news" in todo:
            try:
                n3 = fetch_news(cur)
                print(f"  {n3} news rows written")
            except SourceSilent as e:
                silent.append(str(e))

        cur.execute('SELECT count(*) AS n, max(date) AS latest FROM "PriceSnapshot"')
        got = cur.fetchone()
        print(f"\nPriceSnapshot rows: {got['n']}, latest {got['latest']}")
        cur.execute('SELECT count(*) AS n FROM "News"')
        print(f"News rows: {cur.fetchone()['n']}")
        coverage_report(cur)
    conn.close()

    # After the commit, never before it.
    fail_on_silent(silent)


if __name__ == "__main__":
    main()
