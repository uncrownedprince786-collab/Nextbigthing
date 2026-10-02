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

SNAPSHOT_SET = set(SNAPSHOTS)


def yahoo_assets(cur) -> list[dict]:
    return rows(
        cur,
        """
        SELECT a.id, a.symbol, a."sourceRef" FROM "Asset" a
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
    for assets_part, frame, is_full in frames:
        stored, newest = _store_frame(cur, assets_part, frame, today, is_full)
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


def chart_forming_day(meta: dict) -> date | None:
    """The session that has not closed yet, whose daily bar is therefore partial.

    At `interval=1d` the endpoint returns the day in progress as an ordinary bar stamped at the
    session open, with the open, high and low so far and a close that is really the last trade.
    Stored as a close it is a price that never happened, and tomorrow's run would overwrite it
    with the real one — which is exactly the silent wrong number this file exists to avoid.

    The signal is in `meta`: `currentTradingPeriod.regular` gives today's session bounds and
    `regularMarketTime` gives how far through it the provider has got. Still inside the session
    means the bar for that session's day is forming. Returns None once it has closed, which is
    the normal case for a nightly run.
    """
    regular = ((meta or {}).get("currentTradingPeriod") or {}).get("regular") or {}
    start, end = regular.get("start"), regular.get("end")
    seen = (meta or {}).get("regularMarketTime")
    if not start or not end or not seen:
        return None
    if seen >= end:
        return None
    return datetime.fromtimestamp(int(start), tz=timezone.utc).date()


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


def _store_frame(cur, assets, frame, today: date, is_full: bool) -> tuple[int, dict]:
    """Write one downloaded frame. `is_full` decides replace-versus-upsert.

    A full backfill replaces the asset's rows, because it is authoritative for the whole
    series. An incremental run must never delete: it only holds the correction window, and
    replacing from it would destroy six years of history to save one fetch.

    Returns `(rows written, newest stored day per symbol)`. The second value is what the caller
    needs for partial-day detection, and it is collected here because this is the only place that
    sees the frame per asset. A symbol the frame had no usable column for maps to None rather than
    being left out, so the caller can tell "answered nothing" from "was never asked".
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

        closes: list[tuple[date, float]] = []
        volumes: dict[date, float] = {}
        bars: dict[date, tuple[float | None, float | None, float | None]] = {}

        def num(value):
            """A float, or None for the NaN the source uses for a field it did not publish."""
            return float(value) if value == value and value is not None else None

        for stamp, row in part.iterrows():
            day = stamp.date()
            closes.append((day, float(row["Close"])))
            vol = row.get("Volume")
            if vol == vol:  # not NaN
                volumes[day] = float(vol)
            # The source has always sent these; the job used to drop them on the floor.
            bars[day] = (num(row.get("Open")), num(row.get("High")), num(row.get("Low")))

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
    else:
        base = f'"{a["name"]}"'
    return f"{base} {hint}" if hint else base


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
    asked = 0
    parsed = 0

    def ingest(url, cache_key, insert_sql, params_fn, cap=NEWS_PER_FEED):
        nonlocal written, asked, parsed
        asked += 1
        raw = get(url, cache_key=cache_key, ttl=3600)
        if not raw:
            return
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            print("  bad rss")
            return
        parsed += 1
        kept_here = 0
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
            cur.execute(
                insert_sql,
                params_fn(when, title, link, publisher),
            )
            written += cur.rowcount if cur.rowcount > 0 else 0
            kept_here += 1
        print(f"  {kept_here} from {cache_key}")

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
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(term)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        ingest(
            url,
            f"gnews-ind-{ind['slug']}",
            news_sql,
            lambda w, t, l, p, i=ind: (i["id"], t, l, p, w, GNEWS),
        )

    for prod in products:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(f'"{prod["name"]}"')
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        ingest(
            url,
            f"gnews-pr-{prod['id']}",
            prod_sql,
            lambda w, t, l, p, pr=prod: (pr["id"], t, l, p, w, GNEWS),
        )

    # Asset pages. An article is stored once per target, so the same story can appear on an
    # asset, a product and an industry at once, which is what a reader of each page wants.
    # The query stays narrow anyway: naming the company is what finds the coverage stories
    # for that company rather than generic news about its industry.
    empty = []
    for a in assets:
        term = asset_news_term(a)
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(term)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        before = written
        ingest(
            url,
            # Versioned: the feed is cached by key, so a term that changes has to change
            # the key too or a stale response is reused for the rest of the hour.
            f"gnews-as-v2-{a['symbol']}",
            asset_sql,
            lambda w, t, l, p, x=a: (x["id"], t, l, p, w, GNEWS),
            cap=NEWS_PER_ASSET,
        )
        if written == before:
            empty.append(a["symbol"])
    if empty:
        print(f"  {len(empty)} assets matched no new article: {', '.join(empty)}")

    # Before the sweep, not after: a host that got no feed at all must not go on to
    # delete four months of stored articles on the strength of nothing.
    require_answer(parsed, asked, source=GNEWS)

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
