"""One row per asset per session holding the plain measurements of its stored closes.

Every number here is arithmetic over `PriceSnapshot` rows that already exist. Nothing is
fetched, nothing is modelled, and nothing is inferred: the job exists so the decision rules
and the pages stop recomputing the same six quantities from the same closes in six slightly
different ways, which is how `r20` came to mean three different windows across the repository.

The one rule that matters
-------------------------
A factor that could not be computed is null. Never zero.

Zero is a measurement here and it is a real one: a volume ratio of 0 says the venue
published a session in which nothing traded, and a drawdown of 0 says the close *is* the
trailing high. Null says nobody could look — too few bars, no volume column, too few peers.
The decision rules treat the two differently, and a zero written where a null belongs feeds
them a confident answer that was never measured. That is why `bars` is stored beside every
field: a reader who sees `r20` null and `bars` 15 knows exactly why, and a reader who sees
`r20` filled over 22 bars can decide not to trust it.

Windows, and the minimum bars each needs
----------------------------------------
  r1, r5, r20     the span itself, so span + 1 closes
  returnZ         r1 against the daily returns of the Z_HISTORY sessions before it
  volumeRatio     today's volume over the average of the VOLUME_WINDOW sessions before it
  sma20, sma50    SMA_SHORT and SMA_LONG closes
  rangePct        position inside the trailing RANGE_WINDOW closes
  drawdownPct     percent below the high of that same trailing window
  peerMedianR20   the median r20 of the other assets in the same Industry

Look-ahead
----------
A row dated D may only be computed from closes at or before D. This is the only bug in this
file that would corrupt every measured hit rate the project publishes while leaving the rows
looking perfect, so it is held in two places rather than one:

  * every read is bounded by `date <= %s` / `"periodEnd" <= %s` against the session being
    written, and
  * `compute` applies the same cutoff itself to whatever series it is handed, so the pure
    function is correct even if a caller passes it a longer series. `tests/test_brain.py`
    exercises exactly that: the same bars with and without later sessions must agree.

Run: python jobs/factors.py
Writes: AssetFactor
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, median, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

COMPUTED = "Stored closes and volumes"

# --- windows -------------------------------------------------------------------------------

# The return spans, in sessions. A span of n needs n + 1 closes: the close at D and the close
# n sessions back. 20 is the project's existing medium window (setup.py FAST), so a reader
# comparing a factor row against a setup row is comparing the same window.
RETURN_SPANS = (1, 5, 20)

# Daily returns the r1 band is measured against, and the floor below which the band is not
# published at all. 60 sessions is about a quarter, long enough to contain both quiet and busy
# weeks for the same name; 30 is the smallest baseline where a median and a MAD describe a
# distribution rather than a handful of days. human.py accepts 7 for news rates because a feed
# publishes something most days, whereas 7 daily returns is one week and one week is noise.
Z_HISTORY = 60
MIN_Z_HISTORY = 30

# The smallest MAD the band may be divided by, in percentage points. A halted name, or one
# pegged for weeks, produces MAD 0, and dividing by it turns a half-percent move into an
# infinite score. 0.05 points is below the daily movement of anything actually trading, so the
# floor only ever binds where the series is genuinely flat, and the result stays finite.
MAD_FLOOR_PCT = 0.05

# Volume baseline. The average is taken over the sessions *before* D rather than including it,
# which is what analogs.py and setup.py already do and the only reading that means what a
# reader expects: "twice its own average" has to compare against a norm the day itself did not
# inflate. Half the window is allowed to be missing because several venues publish volume
# intermittently, and refusing the ratio outright would discard a usable comparison; fewer than
# MIN_VOLUME_BARS of them and there is no average worth dividing by.
VOLUME_WINDOW = 20
MIN_VOLUME_BARS = 10

# The two moving averages the rest of the project already uses, kept identical on purpose:
# setup.py reads trend from the same pair, and two jobs disagreeing about what "the 20 day
# mean" is would be unreadable on a page showing both.
SMA_SHORT = 20
SMA_LONG = 50

# The trailing range. 120 sessions is roughly six months, matching setup.py's RANGE_WINDOW so
# "near the top of its range" means one thing across the site. A shorter history is measured
# over what exists down to MIN_RANGE_BARS, because the position of a close inside its last
# three months is still a fact; below 20 sessions it is a fact about a fortnight and is
# refused. `bars` is stored so a reader can always tell which of the two they are looking at.
RANGE_WINDOW = 120
MIN_RANGE_BARS = 20

# Peers needed before a peer median is published. Five is the smallest count where the median
# is a single middle name with two either side of it: at four it is the average of the middle
# two and one listing moves it, and at three it *is* one listing, which is a quote rather than
# an industry. The asset itself is never one of its own peers.
MIN_PEERS = 5

# How far ahead a dated item is still context for these windows. Beyond half a year the
# distance says nothing about the next few sessions and a non-null number invites the rules to
# weigh it, so it is left null. NOTE ON UNITS: the schema calls this field sessions, and
# sessions after D cannot be counted from stored rows without reading past D, which is the one
# thing this job may not do. Calendar days to the dated item are therefore what is written, and
# this comment is the only honest place to say so.
EVENT_HORIZON_DAYS = 180

# A news count older than this is not a reading about the recent window, so it is not borrowed
# as one. Null then means news was never checked for this asset as of this session, which the
# rules report differently from checked-and-none.
NEWS_MAX_AGE_DAYS = 7

# Calendar days of history read per asset. RANGE_WINDOW + SMA_LONG sessions is the longest
# window anything above needs; the 7/5 and the slack cover weekends and holidays so the deepest
# window is still full. Bounded rather than open-ended because the read is one statement across
# every asset and an unbounded one would grow with the price table forever.
HISTORY_DAYS = int((RANGE_WINDOW + SMA_LONG + Z_HISTORY) * 7 / 5) + 30

# Rows per write, and per commit. Not one transaction for the run: events.py held a single
# transaction across roughly 100k round trips and Neon's pooler closed it underneath, losing
# work that had already succeeded. 200 rows is one statement per 200 assets — a whole run of
# today's 160 in one, and five for the 1,000 the table is sized for — small enough that a
# dropped connection costs at most one batch and large enough that latency is not the job.
BATCH_ROWS = 200


# --- pure formulas -------------------------------------------------------------------------
#
# Everything below takes plain lists of numbers and returns a number or None. No cursor, no
# row dicts, no dates. This is what makes the arithmetic testable with no database and no
# network, which is how the rest of this repository is tested.


def simple_return(closes: list[float], span: int) -> float | None:
    """Percent change over `span` sessions. None when the closes to measure it are not there.

    `closes` is oldest first and ends at the session being described. A span of n reads
    closes[-1] against closes[-1 - n], so n + 1 closes are required: a 20 session return over
    20 bars does not exist, and returning the 19 session return instead would mislabel it.
    """
    if span <= 0 or len(closes) < span + 1:
        return None
    base = closes[-1 - span]
    if base is None or base <= 0:
        # A zero or negative base is not a 100% move, it is an unusable denominator.
        return None
    return (closes[-1] / base - 1.0) * 100.0


def daily_returns(closes: list[float]) -> list[float]:
    """Session-over-session percent changes, oldest first. Unusable bases are dropped.

    Dropped rather than zero-filled: a gap where a close was 0 is a session the series cannot
    describe, and a 0.0 in its place would be counted as a flat day by the median below.
    """
    out: list[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev is None or cur is None or prev <= 0:
            continue
        out.append((cur / prev - 1.0) * 100.0)
    return out


def robust_z(value: float | None, history: list[float]) -> float | None:
    """(x - median) / (1.4826 * MAD), or None when the baseline cannot support it.

    The same statistic human.py applies to news rates, for the same reason: one earnings gap
    inside the window drags a mean and a standard deviation far enough that every later move
    reads as ordinary, and a median and a MAD do not move at all. The 1.4826 puts the MAD on
    the scale of a standard deviation for normal data; returns are not normal, which is why
    this is a robust deviation score and never a probability.
    """
    if value is None or len(history) < MIN_Z_HISTORY:
        return None
    med = median(history)
    if med is None:
        return None
    mad = median([abs(h - med) for h in history])
    if mad is None:
        return None
    scale = 1.4826 * mad
    if scale < MAD_FLOOR_PCT:
        scale = MAD_FLOOR_PCT
    return (value - med) / scale


def volume_ratio(volumes: list[float | None]) -> float | None:
    """Latest volume over the average of the VOLUME_WINDOW sessions before it.

    None when the venue published no volume for the latest session, or when too few of the
    baseline sessions have one. A venue that publishes no volume at all is not a quiet venue,
    and 0.0 here would say the opposite.
    """
    if len(volumes) < 2 or volumes[-1] is None:
        return None
    latest = float(volumes[-1])
    baseline = [float(v) for v in volumes[-1 - VOLUME_WINDOW : -1] if v is not None]
    if len(baseline) < MIN_VOLUME_BARS:
        return None
    avg = sum(baseline) / len(baseline)
    if avg <= 0:
        # Every baseline session published a zero. The ratio would be undefined, and the
        # measurement a reader wants from that is "no volume", which is the null.
        return None
    return latest / avg


def sma(closes: list[float], window: int) -> float | None:
    """Simple moving average of the last `window` closes, or None when there are fewer.

    A 50 day average over 38 closes is a 38 day average wearing the wrong label, which is
    exactly the kind of quiet mislabelling the null exists to prevent.
    """
    if window <= 0 or len(closes) < window:
        return None
    tail = closes[-window:]
    return sum(tail) / len(tail)


def trailing_window(closes: list[float]) -> list[float] | None:
    """The closes rangePct and drawdownPct are measured over, or None when too short."""
    if len(closes) < MIN_RANGE_BARS:
        return None
    return closes[-RANGE_WINDOW:]


def range_pct(closes: list[float]) -> float | None:
    """Where the close sits in its trailing range: 0 at the low, 100 at the high.

    None when the window is too short, and also when the high equals the low. A series that
    never moved has no position inside its range — 0, 50 and 100 would all be defensible,
    which is the sign that the honest answer is that there is nothing to report.
    """
    window = trailing_window(closes)
    if not window:
        return None
    hi, lo = max(window), min(window)
    if hi <= lo:
        return None
    return (closes[-1] - lo) / (hi - lo) * 100.0


def drawdown_pct(closes: list[float]) -> float | None:
    """Percent below the trailing high. Always <= 0, and 0 when the close is the high.

    The high is inside the window the close belongs to, so the ratio cannot exceed 1 and the
    result cannot be positive. `min(0.0, ...)` is there only because floating point can hand
    back +1e-14 for a close that *is* the high, and a positive drawdown on a page would read
    as a bug in the measurement rather than in the last bit of a float.
    """
    window = trailing_window(closes)
    if not window:
        return None
    hi = max(window)
    if hi <= 0:
        return None
    return min(0.0, (closes[-1] / hi - 1.0) * 100.0)


def peer_median_r20(peer_returns: list[float]) -> float | None:
    """Median 20 session return across the peers that have one, or None below the floor.

    Below MIN_PEERS the median is not refused because it is imprecise — it is refused because
    it is a different measurement. "The industry is up 6%" taken over three names is those
    three names, and relStrength computed against it would describe a comparison that was
    never made.
    """
    usable = [r for r in peer_returns if r is not None]
    if len(usable) < MIN_PEERS:
        return None
    return median(usable)


def rel_strength(own_r20: float | None, peer_median: float | None) -> float | None:
    """This asset's 20 session return minus its peer group's. None if either side is missing.

    Not "minus zero" when the peer side is unknown: that would publish the asset's own return
    a second time under a name that claims it was compared against something.
    """
    if own_r20 is None or peer_median is None:
        return None
    return own_r20 - peer_median


def compute(bars: list[dict], period_end: date, peer_returns: list[float] | None = None) -> dict:
    """Every price factor for one asset as of `period_end`, from `bars`.

    `bars` are rows carrying `date`, `close` and optionally `volume`, in any order. The cutoff
    is applied here rather than trusted from the caller: a factor dated D computed from a
    close after D would make every hit rate this project measures a lie, and the cheapest
    place to make that impossible is the function that does the arithmetic. Sorting is by date
    so a caller that hands over rows in storage order gets the same answer.

    `bars` is the count of closes at or before `period_end`, and it is reported whether or not
    anything else could be computed — it is how a reader tells a missing measurement from a
    short history.
    """
    usable = sorted(
        (b for b in bars if b.get("date") is not None and b.get("close") is not None
         and b["date"] <= period_end),
        key=lambda b: b["date"],
    )
    closes = [float(b["close"]) for b in usable]
    volumes = [None if b.get("volume") is None else float(b["volume"]) for b in usable]

    out: dict = {"bars": len(closes)}
    for span in RETURN_SPANS:
        out[f"r{span}"] = simple_return(closes, span)

    # The baseline for the band excludes the move being judged: the latest return is the
    # observation, and leaving it inside the window it is measured against pulls the median
    # towards it and shrinks exactly the score that was asked for. Same construction as the
    # recent-against-baseline split in human.py.
    prior = daily_returns(closes[:-1])
    out["returnZ"] = robust_z(out.get("r1"), prior[-Z_HISTORY:])

    out["volumeRatio"] = volume_ratio(volumes)
    out["sma20"] = sma(closes, SMA_SHORT)
    out["sma50"] = sma(closes, SMA_LONG)
    out["rangePct"] = range_pct(closes)
    out["drawdownPct"] = drawdown_pct(closes)

    peer_med = peer_median_r20(peer_returns or [])
    out["peerMedianR20"] = peer_med
    out["relStrength"] = rel_strength(out.get("r20"), peer_med)
    out["peers"] = len([r for r in (peer_returns or []) if r is not None])
    return out


def event_in_days(period_end: date, event_day: date | None) -> int | None:
    """Days from the session to the next dated item, or None when there is nothing near.

    See EVENT_HORIZON_DAYS for why this is a day count and not a session count.
    """
    if event_day is None:
        return None
    gap = (event_day - period_end).days
    if gap < 0 or gap > EVENT_HORIZON_DAYS:
        return None
    return gap


def news_stories(period_end: date, reading_end: date | None, stories: int | None) -> int | None:
    """The stored story count, if the reading it came from is recent enough to describe D."""
    if reading_end is None or stories is None:
        return None
    if (period_end - reading_end).days > NEWS_MAX_AGE_DAYS:
        return None
    return int(stories)


# --- the I/O shell -------------------------------------------------------------------------
#
# Four statements for the whole run, none of them inside a loop. 160 assets today and up to
# 1,000 later: a query per asset would be four thousand round trips against a pooled remote
# database, which is minutes of pure latency for arithmetic that takes milliseconds.


def read_history(cur, period_end: date) -> dict[str, list[dict]]:
    """Every close and volume any asset needs, in one statement, grouped by asset.

    Bounded twice: `date <= %s` is the look-ahead cutoff, and the lower bound keeps the read
    proportional to the windows rather than to the age of the table.
    """
    floor = date.fromordinal(period_end.toordinal() - HISTORY_DAYS)
    got = rows(
        cur,
        """
        SELECT "assetId", date, close, volume
        FROM "PriceSnapshot"
        WHERE close IS NOT NULL AND date <= %s AND date >= %s
        ORDER BY "assetId", date ASC
        """,
        (period_end, floor),
    )
    series: dict[str, list[dict]] = {}
    for r in got:
        series.setdefault(r["assetId"], []).append(r)
    return series


def read_events(cur, period_end: date) -> dict[str, date]:
    """The next scheduled dated item per asset, at or after the session, in one statement."""
    got = rows(
        cur,
        """
        SELECT DISTINCT ON (l."assetId") l."assetId", e.date
        FROM "Event" e
        JOIN "EventLink" l ON l."eventId" = e.id
        WHERE l."assetId" IS NOT NULL AND e.scheduled = true AND e.date >= %s
        ORDER BY l."assetId", e.date ASC
        """,
        (period_end,),
    )
    return {r["assetId"]: r["date"] for r in got}


def read_news(cur, period_end: date) -> dict[str, dict]:
    """The newest news reading per asset as of the session, in one statement.

    `"periodEnd" <= %s` rather than `<` because a reading whose window ends on D describes D,
    and strictly less would throw away the only reading that is actually about this session.
    What it must never do is take a reading dated after D, which is what the bound stops.
    """
    got = rows(
        cur,
        """
        SELECT DISTINCT ON ("assetId") "assetId", "periodEnd", "recentStories"
        FROM "HumanSignal"
        WHERE "assetId" IS NOT NULL AND "periodEnd" <= %s
        ORDER BY "assetId", "periodEnd" DESC
        """,
        (period_end,),
    )
    return {r["assetId"]: r for r in got}


def flush(conn, cur, payload: list[tuple]) -> int:
    """Write one batch and commit it. Idempotent on (assetId, periodEnd).

    The upsert is what makes a rerun on the same day an update rather than a second row, and
    the commit per batch is what keeps a dropped pooler connection from costing the whole run.
    """
    if not payload:
        return 0
    cur.executemany(
        """
        INSERT INTO "AssetFactor" ("assetId", "periodEnd", r1, r5, r20, "returnZ",
            "volumeRatio", "peerMedianR20", "relStrength", peers, sma20, sma50, "rangePct",
            "drawdownPct", "eventInDays", "newsStories", bars, source, "computedAt")
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT ("assetId", "periodEnd") DO UPDATE SET
            r1 = EXCLUDED.r1, r5 = EXCLUDED.r5, r20 = EXCLUDED.r20,
            "returnZ" = EXCLUDED."returnZ", "volumeRatio" = EXCLUDED."volumeRatio",
            "peerMedianR20" = EXCLUDED."peerMedianR20",
            "relStrength" = EXCLUDED."relStrength", peers = EXCLUDED.peers,
            sma20 = EXCLUDED.sma20, sma50 = EXCLUDED.sma50,
            "rangePct" = EXCLUDED."rangePct", "drawdownPct" = EXCLUDED."drawdownPct",
            "eventInDays" = EXCLUDED."eventInDays",
            "newsStories" = EXCLUDED."newsStories", bars = EXCLUDED.bars,
            source = EXCLUDED.source, "computedAt" = now()
        """,
        payload,
    )
    conn.commit()
    return len(payload)


def session_end(series: dict[str, list[dict]], fallback: date) -> date:
    """The newest stored close across every asset, which is the session being described.

    Today's date is the wrong anchor: the job runs before a close on a holiday and on a
    weekend, and dating a row to a day with no session in it would make `periodEnd` a claim
    about a day nothing was measured on. The newest stored close is a day that exists.
    """
    newest = [bars[-1]["date"] for bars in series.values() if bars]
    return max(newest) if newest else fallback


def main() -> None:
    conn = db()
    cur = conn.cursor()
    try:
        assets = rows(cur, 'SELECT id, symbol, "industryId" FROM "Asset" ORDER BY symbol')
        period_end = date.today()
        series = read_history(cur, period_end)
        period_end = session_end(series, period_end)
        events = read_events(cur, period_end)
        news = read_news(cur, period_end)

        step(f"price factors for {len(assets)} assets as of {period_end}")

        # Every asset's own r20 first, because a peer median is the other assets' r20 and
        # cannot be built while the first asset is still being measured.
        own_r20: dict[str, float | None] = {}
        for a in assets:
            own_r20[a["id"]] = simple_return(
                [float(b["close"]) for b in series.get(a["id"], []) if b["date"] <= period_end],
                20,
            )

        by_industry: dict[str, list[str]] = {}
        for a in assets:
            if a["industryId"]:
                by_industry.setdefault(a["industryId"], []).append(a["id"])

        payload: list[tuple] = []
        written = thin = 0
        for a in assets:
            bars = series.get(a["id"], [])
            group = by_industry.get(a["industryId"], []) if a["industryId"] else []
            peer_returns = [own_r20[p] for p in group if p != a["id"] and own_r20.get(p) is not None]

            f = compute(bars, period_end, peer_returns)
            n = news.get(a["id"]) or {}
            if f["bars"] < SMA_LONG + 1:
                # Still written. A row saying "11 closes, and here is the one return they
                # support" is how the rules learn to refuse this asset, whereas no row at all
                # is indistinguishable from the job never having run.
                thin += 1

            payload.append(
                (
                    a["id"], period_end, f["r1"], f["r5"], f["r20"], f["returnZ"],
                    f["volumeRatio"], f["peerMedianR20"], f["relStrength"], f["peers"],
                    f["sma20"], f["sma50"], f["rangePct"], f["drawdownPct"],
                    event_in_days(period_end, events.get(a["id"])),
                    news_stories(period_end, n.get("periodEnd"), n.get("recentStories")),
                    f["bars"], COMPUTED,
                )
            )
            if len(payload) >= BATCH_ROWS:
                written += flush(conn, cur, payload)
                payload = []

        written += flush(conn, cur, payload)
        print(
            f"  {written} rows written for {period_end}, {thin} of them from fewer than "
            f"{SMA_LONG + 1} closes, which the row reports in bars rather than hiding"
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
