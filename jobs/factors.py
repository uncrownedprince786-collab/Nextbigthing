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
  entryTrigger    the SQUEEZE_WINDOW dispersion against SQUEEZE_BASE of its own history, or
                  FLIP_SPAN + 1 closes and a volume ratio

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
# Comparable sessions needed before the volume baseline is split weekend-from-weekday. A
# twenty-session window holds about six weekend bars, so this cannot be MIN_VOLUME_BARS and
# still ever apply; four is the floor at which an average of weekend days is one.
MIN_COMPARABLE_BARS = 4

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

# --- the entry trigger ---------------------------------------------------------------------
#
# The one thing to know before reading the arithmetic: this is a fifth confirmation and it is
# **not** a replacement for the moving-average stack. brain.md rule 54 measured four candidate
# entry rules against the stack on identical terms and found three of them earlier and slightly
# better -- and all three far rarer. `squeeze_break` fires on 11,361 sessions against the
# stack's 223,667, 5% as often, and its margin over the stack (0.153R against 0.128R) is about
# two standard errors on that sample. Swapping the entry rule would have cut the pool from 467
# directions to a few dozen to buy an improvement the sample can barely see.
#
# So the two that beat the stack are stored beside it instead. They confirm a direction the
# stack already found, and they put a marker on the card saying this one was caught at the
# start -- which is what rule 51 says a reader is owed, the engine entering a median of 40
# sessions into a long.
#
# `inflection` and `breakout20` are deliberately not here. `inflection` fires before the stack
# exists every single time and pays *less* than the stack does, which is the finding that being
# early is only worth something if the thing being caught early is real; `breakout20` is a new
# extreme, which is the stack restated rather than an independent reading of it.
SQUEEZE_BASE = 120
SQUEEZE_WINDOW = 20
MIN_SQUEEZE_HISTORY = SQUEEZE_BASE // 2
# The bottom fifth of an asset's own dispersion history. Its own, and never a constant in
# percent: a quiet session for a coin is a loud one for a currency pair, and one number across
# five markets would make "compressed" mean five different things.
SQUEEZE_QUIET_AT = 0.20
# The move out of that compression, in units of the same dispersion. 1.5 is the stop width the
# backtest sized every candidate against, so the bar for "something just did" is the distance
# that would have been risked on it.
SQUEEZE_BREAKS_AT = 1.5

# The momentum flip. Five sessions is the project's existing short span (RETURN_SPANS), and the
# flip is the sign of that span changing between yesterday and today -- not a move, a turn.
FLIP_SPAN = 5
# **This differs from the backtest, and the difference is deliberate and in one direction.**
# `tools/research/entry_triggers.py` used a mean-based 20-session volume ratio because that was
# the cheapest thing to compute inside the sweep. The ratio stored here is this file's own
# `volume_ratio`, which is median-based and splits weekend sessions from weekday ones -- a
# strictly better measure, for the reasons its docstring gives at length. The consequence is
# that the live rule is slightly stricter than the measured one on a weekend bar and slightly
# looser on a skewed week, so the 0.146R measured for `vol_flip` describes a near neighbour of
# this rule rather than this rule. Reusing the stored ratio is still right: two definitions of
# "busy" inside one repository is the exact fault its docstring was written to end.
FLIP_VOLUME_AT = 1.2

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

# Calendar days of history read per asset. RANGE_WINDOW + SMA_LONG + Z_HISTORY sessions is the
# longest window anything above needs -- the squeeze reading wants SQUEEZE_BASE +
# 2 * SQUEEZE_WINDOW, which is 160 and well inside it, so this constant must not be shrunk
# towards the range window alone; the 7/5 and the slack cover weekends and holidays so the deepest
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


def volume_ratio(
    volumes: list[float | None], dates: list[date] | None = None
) -> float | None:
    """Latest volume over the **median** of the VOLUME_WINDOW comparable sessions before it.

    The median, and not the mean, for the reason `robust_z` in this same file already gives for
    returns: "one earnings gap in the window otherwise widens the band enough to call every
    later move ordinary". Volume is worse than returns in this respect, because its skew is one
    sided -- a session can be five times its normal size and cannot be less than zero -- so the
    mean of a twenty session window sits above the typical session in essentially every window,
    and the ratio it produces is biased below 1 on an ordinary day.

    Measured 2026-10-07 over 15,411 asset-sessions, every non-FX asset across the last 60
    complete sessions, as the median of all the ratios produced:

        market        by mean   by median
        PSX             0.614       0.827
        Commodity       0.756       1.003
        US              0.874       0.955
        Crypto          0.931       1.063

    The bias is the smaller half of the problem. The larger half is that it is **uneven between
    markets**, so one constant does not mean one thing: `VOL_ACTIVE` at 1.2 was asking a Karachi
    name to trade at about twice its typical session and a coin at about 1.3 times its own, and
    nothing said so. A threshold whose strictness depends on which market it is applied to is
    not a threshold, and the gate it feeds cannot be reasoned about from its own constant.

    Against the median the centre lands between 0.83 and 1.06 everywhere, so 1.2x means roughly
    the same thing in every market -- about twenty percent busier than a typical session, which
    is what the constant has always claimed to mean. The share of sessions clearing it goes from
    20% to 29% pooled, and that is a correction and not a loosening: the sessions it admits are
    the ones that were always above a typical day and were being measured against an inflated
    denominator.

    `jobs/analogs.py` keeps its own mean-based volume ratio deliberately. That one is a
    similarity key for matching one past day to another, not a judgement about whether a session
    was busy, and changing what it means would silently re-cut every stored analog set.

    None when the venue published no volume for the latest session, or when too few of the
    baseline sessions have one. A venue that publishes no volume at all is not a quiet venue,
    and 0.0 here would say the opposite.

    **Comparable, not merely preceding.** With `dates` given, the baseline is drawn only from
    sessions on the same side of the weekend as the latest one. This is a correction, not a
    refinement: a market that trades seven days a week is far quieter at the weekend than in
    the week — measured over the last 120 sessions, Saturday and Sunday run at 0.86 and 0.73
    of a trailing average that is five sevenths weekdays, and for BTC and ETH at 0.42 to 0.51
    — so a Saturday bar divided by a weekday-dominated average does not report a quiet market,
    it reports the calendar. Every one of the ten stored coins failed the `setup.py` volume
    gate on a Saturday bar at 0.11x to 0.52x while its trend read up, which is how this was
    found. Splitting the baseline compares a weekend day against weekend days and a weekday
    against weekdays, and the ratio means the same thing in both.

    For a five-day market this is a no-op by construction: every session is a weekday, so the
    split leaves the baseline whole and no equity ratio moves. That is the point — the fix is
    stated once for every market and only bites where a market actually trades at the weekend.

    Falls back to the unsplit baseline when the comparable one is too thin, because two
    weekend bars are a worse denominator than twenty mixed ones. Without `dates` the baseline
    is unsplit, which is the behaviour every caller had before this parameter existed.
    """
    if len(volumes) < 2 or volumes[-1] is None:
        return None
    latest = float(volumes[-1])
    aligned = dates if dates is not None and len(dates) == len(volumes) else [None] * len(volumes)
    window = list(zip(volumes[-1 - VOLUME_WINDOW : -1], aligned[-1 - VOLUME_WINDOW : -1]))

    # The unsplit baseline, and the threshold it has always had. A split baseline that turns out
    # too thin falls back to this, so the two guards are deliberately different numbers: ten
    # mixed sessions is the floor for a median to mean anything, while four comparable ones is
    # the most a twenty-session window can offer for a weekend and is still a weekend reading.
    baseline = [float(v) for v, _ in window if v is not None]
    enough = MIN_VOLUME_BARS
    if aligned[-1] is not None:
        weekend = aligned[-1].weekday() >= 5
        alike = [
            float(v) for v, d in window
            if v is not None and d is not None and (d.weekday() >= 5) == weekend
        ]
        if len(alike) >= MIN_COMPARABLE_BARS:
            baseline, enough = alike, MIN_COMPARABLE_BARS
    if len(baseline) < enough:
        return None
    typical = median(baseline)
    if typical is None or typical <= 0:
        # More than half the baseline sessions published a zero, so the typical session in this
        # window had no volume. The ratio would be undefined or absurd, and the measurement a
        # reader wants from that is "no volume", which is the null. Note this is a weaker trigger
        # than the mean's was: a mean needed every session to be zero, a median needs half, which
        # is the right place for it -- a name that traded on four of twenty sessions has no
        # typical session to compare against.
        return None
    return latest / typical


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


def dispersion(returns: list[float]) -> float | None:
    """How widely a run of daily returns is spread, in percentage points. None under three.

    The population standard deviation, which is what `tools/research/entry_triggers.py`
    measured every candidate rule against and therefore what the stored thresholds mean. Three
    returns is the floor at which a spread is a spread rather than a gap between two numbers.

    Not the robust statistic `robust_z` uses, and the difference is the point of each. A MAD is
    for asking whether *one* observation is unusual against a history one outlier must not be
    allowed to widen. This asks how wide the recent window itself was, and the outliers in it
    are part of the answer: a fortnight containing one 9% session was not a quiet fortnight.
    """
    if len(returns) < 3:
        return None
    mean = sum(returns) / len(returns)
    return (sum((r - mean) ** 2 for r in returns) / len(returns)) ** 0.5


def squeeze_break(closes: list[float]) -> str | None:
    """"up", "down", or None: did the latest session expand out of a compression?

    Two parts, and the second is what the first exists to qualify. **Quiet**: the dispersion of
    the last SQUEEZE_WINDOW daily returns sits in the bottom SQUEEZE_QUIET_AT of the
    SQUEEZE_BASE sessions of its own dispersion history. **Broke**: the latest return is more
    than SQUEEZE_BREAKS_AT of that same dispersion, in either direction.

    **This does not contradict brain.md rule 46, and the distinction is the whole of why the
    rule is here.** Rule 46 measured compression as a standing state and found it followed by
    *smaller* moves -- so "it is quiet, therefore something will happen" is measurably false.
    This measures the expansion bar **out of** a compression, which is a different event: not
    that something will happen, but that something just did, out of a base narrow enough for
    the move to be worth reading. A quiet asset that stays quiet never fires this.

    None when the history is too short to judge compression against. A name with 40 closes is
    not uncompressed, it is unmeasured, and every rule in this file says so with a null.
    """
    rets = daily_returns(closes)
    # A dispersion over fewer than SQUEEZE_WINDOW returns is a shorter window wearing this
    # one's label, which is the mislabelling `sma` refuses two hundred lines above.
    if len(rets) < SQUEEZE_WINDOW:
        return None
    latest = rets[-1]
    # The window ends at the latest session and includes it, which is what the backtest
    # measured: the bar that broke out is part of the fortnight it broke out of. Its history
    # is the dispersions of the SQUEEZE_BASE windows **ending where this one begins**, so the
    # two never overlap -- a window compared against a history containing itself would call
    # every expansion ordinary, because the expansion would already be in the baseline.
    window = dispersion(rets[-SQUEEZE_WINDOW:])
    if window is None or window <= 0:
        return None
    last_end = len(rets) - SQUEEZE_WINDOW
    history = [
        d
        for d in (
            dispersion(rets[end - SQUEEZE_WINDOW : end])
            for end in range(max(SQUEEZE_WINDOW, last_end - SQUEEZE_BASE + 1), last_end + 1)
        )
        if d is not None
    ]
    if len(history) < MIN_SQUEEZE_HISTORY:
        return None
    if sum(1 for d in history if d <= window) / len(history) > SQUEEZE_QUIET_AT:
        return None
    if latest > SQUEEZE_BREAKS_AT * window:
        return "up"
    if latest < -SQUEEZE_BREAKS_AT * window:
        return "down"
    return None


def volume_flip(closes: list[float], ratio: float | None) -> str | None:
    """"up", "down", or None: did five-session momentum change sign on a busy session?

    The sign of the FLIP_SPAN return today against the sign it carried yesterday, and only when
    the session that turned it traded at FLIP_VOLUME_AT of its own typical size. Both halves
    are required and neither is interesting alone: momentum crosses zero constantly on a drifting
    name, and a busy session that continues the direction it already had is not a turn.

    The boundary is `> 0 >=` rather than `> 0 >`, so a flip out of a flat five sessions counts
    and a flip out of a rising one does not. Exactly zero yesterday is the honest edge of "was
    not going this way", and the mirror holds on the short side.

    None when no volume is published for the name, which is the state of every currency pair:
    the rule cannot be judged there rather than failing there.
    """
    if ratio is None or ratio < FLIP_VOLUME_AT:
        return None
    now = simple_return(closes, FLIP_SPAN)
    prior = simple_return(closes[:-1], FLIP_SPAN)
    if now is None or prior is None:
        return None
    if now > 0 >= prior:
        return "up"
    if now < 0 <= prior:
        return "down"
    return None


def entry_trigger(closes: list[float], ratio: float | None) -> tuple[str | None, str | None]:
    """Which entry rule fired on the latest session, and which way. `(None, None)` for neither.

    `squeeze_break` is preferred when both fire, because it measured better (0.153R against
    0.146R) and because it is the one that cannot be read off another stored factor: a reader
    with `r5` and `volumeRatio` in front of them can reconstruct a flip, and nothing on the page
    says how wide the last fortnight was against its own history.

    When the two fire in opposite directions the preference still decides, and that is correct
    rather than merely simple: they are not two votes to be netted, they are two different
    events, and the better-measured one is the one the card should name. The engine reads a
    rule and a direction, so a disagreement cannot reach it as a confirmation of both.
    """
    squeeze = squeeze_break(closes)
    if squeeze is not None:
        return "squeeze_break", squeeze
    flip = volume_flip(closes, ratio)
    if flip is not None:
        return "vol_flip", flip
    return None, None


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

    out["volumeRatio"] = volume_ratio(volumes, [b["date"] for b in usable])
    # Reads the ratio just computed rather than taking its own, which is the whole of why
    # `entry_trigger` is handed one instead of the volumes: see FLIP_VOLUME_AT.
    out["entryTrigger"], out["triggerDirection"] = entry_trigger(closes, out["volumeRatio"])
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

    **A row whose every measurement is unchanged is not written at all**, which is what the
    `WHERE ... IS DISTINCT FROM` on the conflict clause is for. This is not a micro-optimisation
    and it is not about duplicate rows -- the unique key already made those impossible. It is
    about what Postgres does with an UPDATE that changes nothing: it writes a new row version
    anyway, marks the old one dead, and journals both. The nightly lane and a rerun inside the
    same session together rewrite all 477 rows whether or not a single number moved, so on a
    weekend or a holiday -- when `session_end` returns the same stored close and every factor is
    by definition identical -- the whole table is duplicated into dead tuples for nothing. On a
    tier whose ceiling is storage and compute, that is the cheapest write to stop making.

    The row comparison deliberately excludes `computedAt`, which is `now()` and would therefore
    differ on every run and defeat the whole clause. The consequence is worth stating because it
    changes what that column means: it is now **when this reading last changed**, not when the
    job last ran. Nothing reads it -- freshness comes from `periodEnd`, which is part of the key
    -- and "the job ran" is a question `ChunkRun` answers properly now that the lanes write it.
    """
    if not payload:
        return 0
    cur.executemany(
        """
        INSERT INTO "AssetFactor" ("assetId", "periodEnd", r1, r5, r20, "returnZ",
            "volumeRatio", "peerMedianR20", "relStrength", peers, sma20, sma50, "rangePct",
            "drawdownPct", "eventInDays", "newsStories", "entryTrigger", "triggerDirection",
            bars, source, "computedAt")
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT ("assetId", "periodEnd") DO UPDATE SET
            r1 = EXCLUDED.r1, r5 = EXCLUDED.r5, r20 = EXCLUDED.r20,
            "returnZ" = EXCLUDED."returnZ", "volumeRatio" = EXCLUDED."volumeRatio",
            "peerMedianR20" = EXCLUDED."peerMedianR20",
            "relStrength" = EXCLUDED."relStrength", peers = EXCLUDED.peers,
            sma20 = EXCLUDED.sma20, sma50 = EXCLUDED.sma50,
            "rangePct" = EXCLUDED."rangePct", "drawdownPct" = EXCLUDED."drawdownPct",
            "eventInDays" = EXCLUDED."eventInDays",
            "newsStories" = EXCLUDED."newsStories",
            "entryTrigger" = EXCLUDED."entryTrigger",
            "triggerDirection" = EXCLUDED."triggerDirection", bars = EXCLUDED.bars,
            source = EXCLUDED.source, "computedAt" = now()
        WHERE (
            "AssetFactor".r1, "AssetFactor".r5, "AssetFactor".r20, "AssetFactor"."returnZ",
            "AssetFactor"."volumeRatio", "AssetFactor"."peerMedianR20",
            "AssetFactor"."relStrength", "AssetFactor".peers, "AssetFactor".sma20,
            "AssetFactor".sma50, "AssetFactor"."rangePct", "AssetFactor"."drawdownPct",
            "AssetFactor"."eventInDays", "AssetFactor"."newsStories",
            "AssetFactor"."entryTrigger", "AssetFactor"."triggerDirection",
            "AssetFactor".bars, "AssetFactor".source
        ) IS DISTINCT FROM (
            EXCLUDED.r1, EXCLUDED.r5, EXCLUDED.r20, EXCLUDED."returnZ",
            EXCLUDED."volumeRatio", EXCLUDED."peerMedianR20",
            EXCLUDED."relStrength", EXCLUDED.peers, EXCLUDED.sma20,
            EXCLUDED.sma50, EXCLUDED."rangePct", EXCLUDED."drawdownPct",
            EXCLUDED."eventInDays", EXCLUDED."newsStories",
            EXCLUDED."entryTrigger", EXCLUDED."triggerDirection",
            EXCLUDED.bars, EXCLUDED.source
        )
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
                    f["entryTrigger"], f["triggerDirection"],
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
