"""Whether the measured conditions around an asset currently add up to a recognised setup.

Every state here comes out of explicit rules over stored numbers. There is no model in it and
no judgement in it, and the row keeps everything needed to rederive the state by hand: each
condition that was tested including the ones that failed, the inputs that were unavailable,
and the conditions pointing the other way.

Three rules this job holds to, and the third is the one that matters
--------------------------------------------------------------------
  * A condition that could not be evaluated is recorded as unavailable, never as satisfied.
    A setup built on three passes and two inputs the database did not have is not a setup,
    and `missing` is what stops it being presented as one.
  * Conditions that disagree go in `against` and are shown. The easy way to produce a clean
    signal is to drop the data that spoils it, which is the one thing this project exists not
    to do.
  * Entry and invalidation are levels computed from stored closes with the window stated.
    They are not targets and not predictions. The invalidation is the measurable condition
    under which the reason for the state has stopped being true, which is the only part of a
    setup that protects anybody.

It describes conditions. It is not advice and it does not say what will happen.

Inputs, all from stored rows
----------------------------
  trend      close against its own 20 and 50 day means
  position   where the close sits inside its 120 day range
  volume     today against the 20 day average
  relative   20 day return minus the asset's own industry's mean 20 day return
  news       catalyst flag and headline tone from HumanSignal
  history    the 5 day analog row: how often similar past days were followed by a rise
  calendar   whether a scheduled date falls inside the horizon

Run: python jobs/setup.py
Writes: AssetSetup
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, one, rows, step  # noqa: E402
from factors import volume_ratio  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

RULES = "Rule-based over stored closes, volumes, news readings and analogs"

# Windows. Named because the horizon label has to mean the windows actually used: calling a
# read "swing" while computing it from three days would be a lie told by a constant.
FAST = 20
SLOW = 50
RANGE_WINDOW = 120

# Thresholds, each with the reason it is where it is.
VOL_ACTIVE = 1.2        # 20% above its own average is active rather than merely non-quiet
REL_EDGE = 1.0          # percentage points of 20 day outperformance against its own industry

# How far apart the two averages must be before `bias` reports a side, as a percentage of the
# slower one.
#
# Two averages are never exactly equal, so without a floor this condition would report a side on
# every single row including ones where the gap is a rounding difference. 0.25% is a quarter of
# one percent of the slow average -- small enough that it does not suppress a real separation and
# large enough that a cross that happened this morning does not read as a position. Measured over
# the 123 directionless swing rows on 2026-10-09, 4 fell inside it.
BIAS_MIN_GAP = 0.25

# How far the invalidation sits from the entry, in standard deviations of the asset's own daily
# return over the FAST window.
#
# **What it replaces.** The stop was the far end of the 20-session close range: for a long, the
# entry was the window high and the stop the window low, so the risk taken was the whole recent
# range. Measured 2026-10-09 over the 475 current swing rows, that distance has a median of
# **10.4% of the price**, quartiles 6.6% to 15.8%. Against the targets `horizons.py` measures,
# the median reward came to 0.41x the risk: the typical call risked two and a half times what it
# stood to make.
#
# **Why 1.5 and not tighter.** Backtested over 174,277 long setups and 104,336 short ones across
# the whole stored history -- entry at the window extreme with price already there, first touch
# over the next 20 sessions, outcome in units of the risk taken:
#
#     stop            R:R    target hit   stopped    mean R
#     window extreme  0.37        58.5%     18.3%     0.030
#     0.75 sigma      2.67        37.5%     61.1%     0.401
#     1.0 sigma       2.00        41.0%     56.8%     0.263
#     1.5 sigma       1.33        46.8%     49.2%     0.139
#     2.0 sigma       1.00        50.9%     42.8%     0.082
#     3.0 sigma       0.67        55.9%     32.4%     0.033
#
# Mean expectancy rises all the way to the tightest stop tested, and that is exactly why the
# tightest was not taken. The simulation walks **daily closes**, so a stop is only recorded as hit
# when a close finishes beyond it -- every intraday touch is missed, and the tighter the stop the
# more of them there are. The 0.75 sigma row is therefore the most optimistic line in the table
# and the least trustworthy. 1.5 improves the ratio to 1.33x and the mean outcome to 0.139R
# against 0.030R, which is four and a half times the current rule, while still finishing roughly
# half its trades at the target rather than turning the engine into a lottery with a good average.
#
# It can only ever tighten. The level is bounded by the window extreme below, so an asset whose
# recent range is narrower than 1.5 of its own daily moves keeps the range as its stop rather
# than being handed a wider one than it had.
STOP_SIGMAS = 1.5
ANALOG_SHARE = 0.55     # share of similar past days that rose, before history counts as support
ANALOG_MIN = 8          # matches needed before that share is used at all
EVENT_SOON_DAYS = 14    # a scheduled date inside this is context for a swing read

# How many of the three confirmations a directional setup needs beside its trend.
#
# 2, measured rather than chosen. On 2026-10-06, across all 267 assets: requiring all three
# produced 2 buy setups and 0 short; requiring two produced 39 and 11; requiring one produced 70
# and 76. The last is half the universe declared directional on the same day, which is not a
# signal. The first had never produced a single short in the life of the table, because the news
# tone reads negative for 3% of assets and volume sits above its average for 9%.
CONFIRMS_NEEDED = 2

HORIZON = "swing"       # the only horizon these windows support; see the note above


def all_closes(cur) -> dict[str, list[dict]]:
    """{assetId: the newest RANGE_WINDOW + SLOW closes, newest first} for every asset.

    One statement for the universe instead of one per asset. The window and the ordering are
    the same as the per-asset read it replaces -- `row_number()` numbers each asset's own rows
    newest first and the cut is the same figure -- so the series handed to the rules below is
    identical, row for row, to the one it got before.

    Reading the whole universe at once costs memory in exchange for round trips: about 331
    assets times 120 rows of three columns, which is small, against 331 network waits that on
    a host outside the database's region were most of this job's eleven minutes.
    """
    got = rows(
        cur,
        """
        SELECT "assetId", date, close, volume FROM (
            SELECT "assetId", date, close, volume,
                   row_number() OVER (PARTITION BY "assetId" ORDER BY date DESC) AS rn
            FROM "PriceSnapshot" WHERE close IS NOT NULL
        ) ranked
        WHERE rn <= %s
        ORDER BY "assetId", date DESC
        """,
        (RANGE_WINDOW + SLOW,),
    )
    out: dict[str, list[dict]] = {}
    for r in got:
        out.setdefault(r["assetId"], []).append(r)
    return out


def all_signals(cur) -> dict[str, dict]:
    """The newest HumanSignal per asset."""
    return {r["assetId"]: r for r in rows(
        cur,
        """
        SELECT DISTINCT ON ("assetId") "assetId", tone::text AS tone, catalyst,
               "changeKind", "recentStories"
        FROM "HumanSignal" WHERE "assetId" IS NOT NULL
        ORDER BY "assetId", "periodEnd" DESC
        """,
    )}


def all_analogs(cur) -> dict[str, dict]:
    """The newest five day analog set per asset. Horizon 5 is the one a swing read is
    answerable on, which is the rule `tools/decide.mjs` and `lib/decisionInput.ts` both use."""
    return {r["assetId"]: r for r in rows(
        cur,
        """
        SELECT DISTINCT ON ("assetId") "assetId", matches, positive, "medianPct",
               "minPct", "maxPct"
        FROM "AssetAnalog" WHERE "horizonDays" = 5
        ORDER BY "assetId", "periodEnd" DESC
        """,
    )}


def all_next_events(cur, today) -> dict[str, dict]:
    """The soonest scheduled event per asset at or after `today`. A diary has one order and
    it is not "newest written"."""
    return {r["assetId"]: r for r in rows(
        cur,
        """
        SELECT DISTINCT ON (l."assetId") l."assetId", e.name, e.date
        FROM "EventLink" l JOIN "Event" e ON e.id = l."eventId"
        WHERE l."assetId" IS NOT NULL AND e.scheduled = true AND e.date >= %s
        ORDER BY l."assetId", e.date ASC
        """,
        (today,),
    )}


def all_industry_relative(cur) -> dict[str, float]:
    """{assetId: its FOR_DAYS return minus the mean of its own industry's}, in one statement.

    The per-asset version re-read an entire industry's returns for every member of it, so a
    nineteen name industry asked for the same nineteen returns nineteen times. The arithmetic
    is unchanged: peers only, the asset's own industry only, and nothing returned where fewer
    than three names in the industry have the history -- the floor the per-asset version
    applied with `len(got) < 3`.
    """
    got = rows(
        cur,
        """
        WITH bounds AS (
            SELECT a.id, a."industryId", max(p.date) AS newest
            FROM "Asset" a
            JOIN "PriceSnapshot" p ON p."assetId" = a.id AND p.close IS NOT NULL
            GROUP BY a.id, a."industryId"
        ),
        rets AS (
            SELECT b.id, b."industryId",
                   (SELECT close FROM "PriceSnapshot"
                     WHERE "assetId" = b.id AND date = b.newest) AS last,
                   (SELECT close FROM "PriceSnapshot"
                     WHERE "assetId" = b.id
                       AND date <= b.newest - (%s * interval '1 day')
                     ORDER BY date DESC LIMIT 1) AS base
            FROM bounds b
        )
        SELECT id, "industryId", (last / base - 1) * 100 AS pct
        FROM rets WHERE last IS NOT NULL AND base IS NOT NULL AND base > 0
        """,
        (FOR_DAYS,),
    )
    by_industry: dict[str, list[tuple[str, float]]] = {}
    for r in got:
        by_industry.setdefault(r["industryId"], []).append((r["id"], float(r["pct"])))
    out: dict[str, float] = {}
    for members in by_industry.values():
        if len(members) < 3:
            continue
        for asset_id, mine in members:
            peers = [v for k, v in members if k != asset_id]
            if peers:
                out[asset_id] = mine - (sum(peers) / len(peers))
    return out


# Calendar days used to reach back roughly FAST trading days.
FOR_DAYS = 28


def sigma_pct(series: list[dict]) -> float | None:
    """Standard deviation of this asset's daily return over the FAST window, in percent.

    Close to close rather than a true range, because this job reads closes and nothing else --
    `jobs/horizons.py` has the highs and lows and computes a real ATR there. The two measure the
    same thing at slightly different scales, and what matters here is only that the figure is the
    asset's own: 1.5 of a currency pair's daily moves and 1.5 of a small cap's are different
    distances in percent and the same distance in the terms the instrument trades in.

    None under three usable returns, or when the result is zero -- a flat series gives a stop at
    the entry, which is not a stop. The caller then keeps the window extreme.
    """
    closes = [float(b["close"]) for b in series[-(FAST + 1):]]
    rets = [
        (closes[i] / closes[i - 1] - 1.0) * 100.0
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]
    if len(rets) < 3:
        return None
    mean = sum(rets) / len(rets)
    sd = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5
    return sd if sd > 0 else None


def stop_level(
    entry: float, high: float, low: float, sigma: float | None, state: str
) -> tuple[float, str]:
    """The level at which this read is wrong, and the sentence that says what it is.

    `STOP_SIGMAS` of the asset's own daily dispersion from the entry, and **never wider than the
    window extreme**. The bound is what makes this a tightening and nothing else: an asset whose
    recent range is narrower than 1.5 of its own daily moves keeps the range, so no setup ends up
    risking more than it did before this existed.

    Falls back to the window extreme with its original wording when the dispersion could not be
    measured, which is the honest answer rather than a stop placed on an assumed volatility.
    """
    if state == "short":
        if sigma is None:
            return high, (
                f"the highest close of the last {FAST} sessions. A close above it means the "
                "trend these conditions were read from is no longer there"
            )
        level = min(high, entry * (1 + STOP_SIGMAS * sigma / 100.0))
        if level >= high:
            return high, (
                f"the highest close of the last {FAST} sessions, which is nearer than "
                f"{STOP_SIGMAS} of this asset's own daily moves. A close above it means the "
                "trend these conditions were read from is no longer there"
            )
        return level, (
            f"{STOP_SIGMAS} times this asset's own daily move of {sigma:.2f}% above the entry, "
            f"reaching {level:.2f}. A close above it means the trend these conditions were read "
            "from is no longer there"
        )

    if sigma is None:
        return low, (
            f"the lowest close of the last {FAST} sessions. A close below it means the trend "
            "these conditions were read from is no longer there"
        )
    level = max(low, entry * (1 - STOP_SIGMAS * sigma / 100.0))
    if level <= low:
        return low, (
            f"the lowest close of the last {FAST} sessions, which is nearer than {STOP_SIGMAS} "
            "of this asset's own daily moves. A close below it means the trend these conditions "
            "were read from is no longer there"
        )
    return level, (
        f"{STOP_SIGMAS} times this asset's own daily move of {sigma:.2f}% below the entry, "
        f"reaching {level:.2f}. A close below it means the trend these conditions were read from "
        "is no longer there"
    )


def main() -> None:
    # Two different dates, and conflating them is how a row comes to describe a day that never
    # traded. `today` is the calendar, and only the event lookups below may use it: "what is
    # scheduled from here on" is a question about now, not about the last session.
    #
    # `period_end` is the session these conditions were measured over, and it is the newest close
    # actually stored. `jobs/factors.py` already states the rule in `session_end`: "Today's date is
    # the wrong anchor: the job runs before a close on a holiday and on a weekend, and dating a row
    # to a day with no session in it would make `periodEnd` a claim about a day nothing was
    # measured on." That file obeys it and this one did not.
    #
    # Measured 2026-10-07: every close, factor and decision was dated 10-07 while every swing setup
    # read 10-08, because this job ran from a UTC+5 host after 19:00 UTC and `date.today()` had
    # already rolled. The rows described 10-07 closes under tomorrow's date. On a UTC runner it
    # goes wrong less often and in the same way -- every weekend and every holiday.
    today = date.today()
    conn = db()
    cur = conn.cursor()
    try:
        # The newest close anywhere, kept only as the fallback for an asset whose own series
        # somehow has no date. Each row below is dated to *that asset's* newest close, which is
        # a stricter reading of the same sentence: the two exchanges here do not close together,
        # and Karachi publishes its file hours before New York finishes trading. On any run
        # between those two moments the site-wide maximum is a session a US name has not had
        # yet, so a global anchor over-dates every US row by a day -- the same fault as reading
        # the calendar, arriving by a different route.
        newest_anywhere = one(cur, 'SELECT max(date) AS d FROM "PriceSnapshot"')["d"] or today
        assets = rows(
            cur, 'SELECT id, symbol, name, "industryId" FROM "Asset" ORDER BY symbol'
        )
        # Five reads for the whole universe, taken before the loop rather than five per asset
        # inside it. Nothing about the rules changed; what changed is that the job stopped
        # waiting on the network 1,655 times to answer questions whose answers are the same
        # for every member of an industry.
        series_by_asset = all_closes(cur)
        signal_by_asset = all_signals(cur)
        analog_by_asset = all_analogs(cur)
        event_by_asset = all_next_events(cur, today)
        relative_by_asset = all_industry_relative(cur)
        step(f"measured conditions for {len(assets)} assets")
        payload: list[tuple] = []
        tally = {"buy": 0, "short": 0, "wait": 0, "none": 0}
        skipped = 0

        for a in assets:
            bars = series_by_asset.get(a["id"], [])
            if len(bars) < SLOW + 2:
                skipped += 1
                continue

            series = list(reversed(bars))
            # This asset's own newest close: the session these conditions describe.
            period_end = series[-1]["date"] or newest_anywhere
            last = float(series[-1]["close"])
            fast_mean = sum(float(b["close"]) for b in series[-FAST:]) / FAST
            slow_mean = sum(float(b["close"]) for b in series[-SLOW:]) / SLOW

            window = series[-RANGE_WINDOW:] if len(series) >= RANGE_WINDOW else series
            hi = max(float(b["close"]) for b in window)
            lo = min(float(b["close"]) for b in window)
            position = ((last - lo) / (hi - lo)) if hi > lo else None

            # One implementation of one idea — rule 36. This used to average the twenty
            # sessions before the latest one inline, which is the same statement `factors.py`
            # makes and was the same statement with one difference: it had no dates, so it
            # could not tell a quiet market from a Saturday. Every stored coin failed this gate
            # on a weekend bar while its trend read up. `volume_ratio` takes the dates and
            # compares weekend with weekend; for US and PSX the split is a no-op.
            vol_ratio = volume_ratio(
                [None if b["volume"] is None else float(b["volume"]) for b in series],
                [b["date"] for b in series],
            )

            rel = relative_by_asset.get(a["id"])
            signal = signal_by_asset.get(a["id"])
            analog = analog_by_asset.get(a["id"])
            soon = event_by_asset.get(a["id"])

            # --- conditions, each recorded with its value and its verdict
            conds: list[str] = []
            missing: list[str] = []
            against: list[str] = []

            up_trend = last > fast_mean > slow_mean
            down_trend = last < fast_mean < slow_mean
            conds.append(
                f"trend: close {last:.2f} vs {FAST}d {fast_mean:.2f} vs {SLOW}d "
                f"{slow_mean:.2f} ({'up' if up_trend else 'down' if down_trend else 'mixed'})"
            )

            # The side a `mixed` trend is on, which is a measurement and was being thrown away.
            #
            # `trend` needs all three of close, fast mean and slow mean to line up, and when they
            # do not it records `mixed` -- correctly, because the three do not agree. But `mixed`
            # was then the end of the sentence, and it is not: the two averages are still one
            # above the other, and which one is a fact about the series rather than an opinion.
            # Measured 2026-10-09 over the 123 `none`-state swing rows the decision lane was
            # refusing: 55 had the 20 day average above the 50 day, 64 below, and only 4 were
            # equal to two decimal places. 119 of 123 had a measurable side that nothing read.
            #
            # It is written as its own condition rather than by changing what `trend` reports,
            # for two reasons. The `trend` token is parsed by `verdicts()` in jobs/thesis.py as
            # well as by lib/setupConditions.ts -- rule 23 -- and widening its vocabulary would
            # change what a held thesis means on every asset. And the two are genuinely different
            # findings: a trend is three things agreeing, a bias is two, and a reader is owed the
            # difference rather than having the weaker one promoted into the stronger one's word.
            #
            # Deliberately only when the trend is mixed. Under an up or down trend this would say
            # the same thing a second time, and a condition that merely repeats its neighbour is
            # noise in a string two parsers read.
            if not up_trend and not down_trend and slow_mean:
                gap = (fast_mean / slow_mean - 1.0) * 100.0
                if abs(gap) >= BIAS_MIN_GAP:
                    conds.append(
                        f"bias: {FAST}d average {abs(gap):.2f}% "
                        f"{'above' if gap > 0 else 'below'} the {SLOW}d "
                        f"({'up' if gap > 0 else 'down'})"
                    )
                else:
                    conds.append(
                        f"bias: {FAST}d and {SLOW}d averages within {BIAS_MIN_GAP}% of each "
                        "other, so neither is above the other by enough to read (mixed)"
                    )

            if vol_ratio is None:
                missing.append("volume against its average (no volume stored)")
            else:
                conds.append(
                    f"volume: {vol_ratio:.2f}x its {FAST}d average "
                    f"({'pass' if vol_ratio >= VOL_ACTIVE else 'fail'})"
                )
                if vol_ratio < VOL_ACTIVE and up_trend:
                    against.append(
                        f"trading is only {vol_ratio:.2f} times its own average, so the move "
                        "is not being carried by unusual activity"
                    )

            if rel is None:
                missing.append("return against its industry (too few peers with history)")
            else:
                conds.append(
                    f"relative: {rel:+.1f} points against its industry over {FAST} days "
                    f"({'pass' if rel >= REL_EDGE else 'fail'})"
                )
                if rel < 0 and up_trend:
                    against.append(
                        f"it is {abs(rel):.1f} points behind its own industry over {FAST} "
                        "days, so the sector is doing the work"
                    )

            if position is not None:
                conds.append(
                    f"position: {position:.0%} of the way up its {RANGE_WINDOW} day range"
                )
                if position > 0.95 and up_trend:
                    against.append(
                        "the close is at the very top of its stored range, so there is no "
                        "recent level above it to measure against"
                    )

            news_support = False
            if not signal:
                missing.append("news reading (no stored coverage)")
            else:
                conds.append(
                    f"news: tone {signal['tone'] or 'none'}, catalyst "
                    f"{'yes' if signal['catalyst'] else 'no'}, {signal['recentStories']} "
                    "recent stories"
                )
                news_support = bool(signal["catalyst"]) or signal["tone"] == "positive"
                if signal["tone"] == "negative" and up_trend:
                    against.append(
                        "the headline wording is net negative while the price is rising"
                    )

            hist_support = None
            if not analog or not analog["matches"]:
                missing.append("historical analogs (no similar past day stored)")
            elif int(analog["matches"]) < ANALOG_MIN:
                conds.append(
                    f"history: only {analog['matches']} similar past days, below the "
                    f"{ANALOG_MIN} needed to use"
                )
            else:
                share = int(analog["positive"]) / int(analog["matches"])
                hist_support = share >= ANALOG_SHARE
                conds.append(
                    f"history: {analog['positive']} of {analog['matches']} similar days rose "
                    f"over 5 sessions ({share:.0%}, {'pass' if hist_support else 'fail'})"
                )
                if share < 0.45 and up_trend:
                    against.append(
                        f"only {share:.0%} of similar past days were followed by a rise"
                    )

            if soon:
                days = (soon["date"] - today).days
                conds.append(f"calendar: {soon['name']} in {days} days")
                if days <= EVENT_SOON_DAYS:
                    against.append(
                        f"a scheduled date falls in {days} days, which can move the price for "
                        "a reason unrelated to the conditions above"
                    )

            # --- the rules. Written out rather than scored, so they are arguable.
            #
            # The trend is mandatory and the other three are counted. It used to be an AND of
            # all four, and that rule could not fire: measured across the whole universe on
            # 2026-10-06, volume sat at or above its own average for only 9% of assets and the
            # news tone read negative for 3%, so the conjunction produced 2 buy setups and -- in
            # the entire history of the table -- not one short. A rule that answers "no" 264
            # times out of 266 is not being careful, it is being silent, and a reader cannot
            # tell those apart.
            #
            # Two of three, and not one of three, because one is where it stops being evidence:
            # the same measurement puts trend-plus-one at 146 of 267 names, which is over half
            # the universe called directional at once. Two of three gives 50. That is the shape
            # brain.md principle 1 asks for -- several independent readings agreeing beats one
            # strong one -- and it is the same standard `lib/decision.ts` already applies when it
            # separates High from Medium on whether volume *or* the analogs confirm.
            #
            # A missing input cannot count toward the two. That is what keeps this honest rather
            # than merely looser: an asset with no stored volume does not get a free pass, it
            # gets one fewer way to qualify, and `missing` already says so on the row. It also
            # unblocks a whole asset class by accident of being correct -- a currency pair has no
            # published volume at all, so under the old conjunction no FX pair could ever have
            # produced a swing setup.
            up_confirms = [
                ("trading is unusually active", vol_ratio is not None and vol_ratio >= VOL_ACTIVE),
                ("it is ahead of its own industry", rel is not None and rel >= REL_EDGE),
                ("the news reading supports it", news_support),
            ]
            down_confirms = [
                ("trading is unusually active", vol_ratio is not None and vol_ratio >= VOL_ACTIVE),
                ("it is behind its own industry", rel is not None and rel <= -REL_EDGE),
                ("the headline wording is negative", bool(signal and signal["tone"] == "negative")),
            ]
            up_met = [label for label, ok in up_confirms if ok]
            down_met = [label for label, ok in down_confirms if ok]

            def _head(direction: str, met: list[str], confirms: list) -> str:
                absent = [label for label, ok in confirms if not ok]
                line = f"Price is {direction} both its averages, and " + ", ".join(met) + "."
                if absent:
                    line += " Not confirmed by: " + ", ".join(absent) + "."
                return line

            if up_trend and len(up_met) >= CONFIRMS_NEEDED and hist_support is not False:
                state = "buy"
                head = _head("above", up_met, up_confirms)
            elif down_trend and len(down_met) >= CONFIRMS_NEEDED and hist_support is not True:
                state = "short"
                head = _head("below", down_met, down_confirms)
            elif up_trend or down_trend:
                state = "wait"
                failed = []
                if vol_ratio is not None and vol_ratio < VOL_ACTIVE:
                    failed.append("trading is not unusually active")
                if rel is not None and abs(rel) < REL_EDGE:
                    failed.append("it is moving with its industry rather than apart from it")
                if not news_support and up_trend:
                    failed.append("no catalyst or positive wording in the news")
                head = (
                    "The direction is clear but the conditions are not all present: "
                    + (", ".join(failed) if failed else "some inputs are unavailable")
                    + "."
                )
            else:
                state = "none"
                head = (
                    "Price is between its averages, so there is no clear direction to "
                    "measure conditions against."
                )

            # Levels, from stored closes, with the window said out loud — and mirrored for a
            # short, which they were not.
            #
            # The entry is the level the move has to clear for the setup to be happening, and the
            # invalidation is the level at which the reason for it has stopped being true. For an
            # up read that is the window's high and its low. For a down read it is the other way
            # round, and this block used to hand a `short` row the same pair as a `buy` row: the
            # entry above the price and the stop below it.
            #
            # That is not a cosmetic swap, it inverts what the page tells a reader to do. WTL read
            # SHORT at Rs.1.00 and the panel printed "Exit if wrong Rs.0.99 — past this level the
            # reason above no longer holds", so the stop sat 1% *below* a short: the side the
            # trade needs price to reach. A short is wrong when price rises.
            #
            # `run_targets` in jobs/horizons.py has always branched on `state` when it picks a
            # structural level, so the repository already contained the correct form of this
            # statement and two of its three level-writers disagreed with it.
            recent = series[-FAST:]
            high = max(float(b["close"]) for b in recent)
            low = min(float(b["close"]) for b in recent)
            entry = low if state == "short" else high
            invalid, invalid_note = stop_level(entry, high, low, sigma_pct(series), state)
            if state == "short":
                entry_note = (
                    f"the lowest close of the last {FAST} sessions. A close below it would be a "
                    "move past where it recently held"
                )
            else:
                entry_note = (
                    f"the highest close of the last {FAST} sessions. A close above it would be "
                    "a move past where it recently stalled"
                )
            range_note = None
            if analog and analog["matches"] and int(analog["matches"]) >= ANALOG_MIN:
                range_note = (
                    f"over 5 sessions, similar past days ran from {float(analog['minPct']):+.1f}% "
                    f"to {float(analog['maxPct']):+.1f}% with a median of "
                    f"{float(analog['medianPct']):+.1f}%. A measured range, not a target"
                )

            grade = "none"
            if state in ("buy", "short"):
                # Three of three and nothing arguing the other way is the only `high`. Two of
                # three is a real setup with a named gap in it, which is what `medium` has always
                # meant on this site, so the count is carried into the grade rather than left for
                # a reader to infer from the headline.
                met = len(up_met) if state == "buy" else len(down_met)
                grade = "high" if met == len(up_confirms) and not (missing or against) else "medium"
            elif state == "wait":
                grade = "low"
            note_bits = []
            if missing:
                note_bits.append(
                    f"{len(missing)} of the inputs could not be evaluated, so this rests on "
                    "fewer conditions than the rules describe"
                )
            if against:
                note_bits.append(f"{len(against)} conditions point the other way")

            payload.append(
                (
                    a["id"], period_end, HORIZON, state, head,
                    " | ".join(conds), " | ".join(missing) or "none",
                    " | ".join(against) or "none",
                    entry, entry_note, invalid, invalid_note,
                    range_note, grade, "; ".join(note_bits).capitalize() or None, RULES,
                )
            )
            tally[state] += 1

        # One statement for every row, after the loop. It was an execute and a commit per
        # asset, which is two network waits each; psycopg pipelines an executemany into one.
        # The conflict clause is unchanged, so a rerun on the same session is still an update
        # rather than a second row.
        cur.executemany(
                """
                INSERT INTO "AssetSetup" ("assetId", "periodEnd", horizon, state, headline,
                    conditions, missing, against, "entryLevel", "entryNote",
                    "invalidateLevel", "invalidateNote", "rangeNote", confidence,
                    "confidenceNote", source, "computedAt")
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::"Confidence",%s,%s,now())
                ON CONFLICT ("assetId", "periodEnd", horizon) DO UPDATE SET
                    state = EXCLUDED.state, headline = EXCLUDED.headline,
                    conditions = EXCLUDED.conditions, missing = EXCLUDED.missing,
                    against = EXCLUDED.against, "entryLevel" = EXCLUDED."entryLevel",
                    "entryNote" = EXCLUDED."entryNote",
                    "invalidateLevel" = EXCLUDED."invalidateLevel",
                    "invalidateNote" = EXCLUDED."invalidateNote",
                    "rangeNote" = EXCLUDED."rangeNote", confidence = EXCLUDED.confidence,
                    "confidenceNote" = EXCLUDED."confidenceNote", "computedAt" = now()
                """,
                payload,
        )
        conn.commit()

        print(
            f"  buy {tally['buy']}, short {tally['short']}, wait {tally['wait']}, "
            f"no clear setup {tally['none']}, {skipped} without enough history"
        )
        print(
            "  states describe measured conditions. They are not advice and they do not say "
            "what will happen."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
