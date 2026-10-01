"""Read the same asset on three time horizons, and attach a measured target range to each.

    python jobs/horizons.py            intraday and longer term reads, then targets for all
    python jobs/horizons.py intraday   the intraday read only
    python jobs/horizons.py longer     the longer term read only
    python jobs/horizons.py targets    target ranges for every stored setup row

Why three reads and not one
---------------------------
The same asset can honestly read `buy` on the hour and `wait` on the quarter, because the two
are computed from different windows and answer different questions. Forcing one state across
every horizon would mean picking a window and calling it the truth. So each horizon gets its
own `AssetSetup` row, keyed by `horizon`, and the page shows them side by side including when
they disagree.

  intraday  five minute bars from the current and previous session
  swing     daily closes over 20 and 50 sessions — written by jobs/setup.py, not here
  longer    daily closes over 100 and 200 sessions, inside a two year range

`setup.py` owns `swing` and is left alone. This job writes the other two in exactly the same
row shape and the same condition-string format, which is not a cosmetic choice: `thesis.py`
parses that format to decide whether a reason still holds, so a new horizon written in a new
format would silently produce theses with nothing to compare.

Intraday is actual intraday
---------------------------
Every intraday condition is computed from `IntradayBar`, never from a daily bar relabelled.
The session's own structure is the point: where price sits against the session range, whether
the last bars broke the prior session's high, how the current bar's volume compares with the
same asset's own recent five minute bars, and how far the move has travelled against its own
measured bar-by-bar volatility. A daily close cannot answer any of those.

An asset with no stored intraday bars gets **no intraday row at all** rather than a row built
from daily data. That is the §9 rule applied to a horizon: absent is recorded as absent.

Targets
-------
Three independent methods, each from stored numbers, and the disagreement between them is
preserved rather than averaged:

  structure   the next level above/below where price recently turned
  volatility  a multiple of the asset's own average true range over the window
  analog      the measured distribution of what followed similar past days

A target is only written when the setup also has an invalidation level, because reward with
no risk behind it is a number with no decision attached. Where the three methods disagree
materially the rows say so and the UI shows the spread; §31 forbids averaging a disagreement
into a false certainty.

Run: python jobs/horizons.py [intraday|longer|targets]
Reads: IntradayBar, IntradaySession, PriceSnapshot, AssetAnalog, AssetSetup, HumanSignal, Event
Writes: AssetSetup (horizon intraday and longer), SetupTarget
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, median, one, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

INTRADAY_RULES = "Rule-based over stored five minute bars"
LONGER_RULES = "Rule-based over stored daily closes across two years"
TARGET_SOURCE = "Measured from stored bars, stored volatility and stored analog outcomes"

# --- intraday windows, in five minute bars. 12 bars is an hour, 78 is a US session.
BAR = 5
FAST_BARS = 12
SLOW_BARS = 36
SESSION_BARS = 78
MIN_BARS = SLOW_BARS + 6

# --- longer term windows, in sessions.
LONG_FAST = 100
LONG_SLOW = 200
LONG_RANGE = 500
MIN_LONG = LONG_SLOW + 20

# Thresholds, each with its reason.
VOL_ACTIVE = 1.3        # intraday volume runs noisier than daily, so this sits above setup.py's 1.2
BREAK_PAD = 0.001       # a break must clear the level by a tenth of a percent, not touch it
LONG_REL_EDGE = 5.0     # percentage points over 100 sessions before an industry edge counts
ATR_WINDOW = 14
ATR_MULTIPLE = 2.0      # the target distance in multiples of the asset's own true range
STRUCTURE_LOOKBACK = 120
ANALOG_MIN = 8
# Two target ranges whose near edges sit further apart than this share of the wider range are
# reported as disagreeing rather than as one answer.
DISAGREE_AT = 0.5


# ----------------------------------------------------------------------------- shared helpers


def true_range(bars: list[dict], window: int) -> float | None:
    """Average true range over the last `window` bars, from stored highs, lows and closes.

    True range rather than the close-to-close standard deviation, because a gap between one
    bar's close and the next bar's open is real movement and a close-only measure cannot see
    it. None when there is not enough history, never a default.
    """
    if len(bars) < window + 1:
        return None
    spans = []
    for i in range(len(bars) - window, len(bars)):
        prev_close = float(bars[i - 1]["close"])
        hi, lo = float(bars[i]["high"]), float(bars[i]["low"])
        spans.append(max(hi - lo, abs(hi - prev_close), abs(lo - prev_close)))
    return sum(spans) / len(spans) if spans else None


def pivots(bars: list[dict], lookback: int) -> tuple[list[float], list[float]]:
    """(highs, lows) where the series actually turned, within the lookback.

    A turn is a bar whose high is the highest of its two neighbours either side, which is the
    simplest definition that does not require a parameter nobody can justify. These are the
    levels a structural target is measured to: places price has already stopped at once.
    """
    window = bars[-lookback:] if len(bars) > lookback else bars
    highs, lows = [], []
    for i in range(2, len(window) - 2):
        h = [float(b["high"]) for b in window[i - 2 : i + 3]]
        lo = [float(b["low"]) for b in window[i - 2 : i + 3]]
        if h[2] == max(h):
            highs.append(h[2])
        if lo[2] == min(lo):
            lows.append(lo[2])
    return highs, lows


def next_level(levels: list[float], price: float, above: bool) -> float | None:
    """The nearest level beyond the current price, or None when price is past all of them.

    None rather than the furthest level: once price has cleared every stored turn there is no
    measured level left to aim at, and inventing one by extrapolation is the fake precision
    §42 forbids.
    """
    beyond = [v for v in levels if (v > price * (1 + BREAK_PAD) if above else v < price * (1 - BREAK_PAD))]
    if not beyond:
        return None
    return min(beyond) if above else max(beyond)


def grade_for(state: str, missing: list[str], against: list[str]) -> str:
    """The same grading rule setup.py uses, so one horizon is never graded more generously
    than another for the same evidence."""
    if state in ("buy", "short"):
        return "medium" if missing or against else "high"
    return "low" if state == "wait" else "none"


def note_for(missing: list[str], against: list[str]) -> str | None:
    bits = []
    if missing:
        bits.append(
            f"{len(missing)} of the inputs could not be evaluated, so this rests on fewer "
            "conditions than the rules describe"
        )
    if against:
        bits.append(f"{len(against)} conditions point the other way")
    return "; ".join(bits).capitalize() or None


def write_setup(cur, asset_id: str, when: date, horizon: str, state: str, head: str,
                conds: list[str], missing: list[str], against: list[str],
                entry: float | None, entry_note: str | None,
                invalid: float | None, invalid_note: str | None,
                range_note: str | None, rules: str) -> str:
    """Upsert one setup row and return its id. Same table and shape as jobs/setup.py."""
    grade = grade_for(state, missing, against)
    cur.execute(
        """
        INSERT INTO "AssetSetup" ("assetId", "periodEnd", horizon, state, headline,
            conditions, missing, against, "entryLevel", "entryNote", "invalidateLevel",
            "invalidateNote", "rangeNote", confidence, "confidenceNote", source, "computedAt")
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
        RETURNING id
        """,
        (
            asset_id, when, horizon, state, head,
            " | ".join(conds), " | ".join(missing) or "none", " | ".join(against) or "none",
            entry, entry_note, invalid, invalid_note, range_note,
            grade, note_for(missing, against), rules,
        ),
    )
    return cur.fetchone()["id"]


# ----------------------------------------------------------------------------------- intraday


def intraday_read(bars: list[dict], prior_high: float | None, prior_low: float | None):
    """(state, headline, conditions, missing, against, entry, invalidation).

    Pure: every input is a list of stored bars, so the whole intraday rule set is testable
    without a database or a provider.
    """
    conds: list[str] = []
    missing: list[str] = []
    against: list[str] = []

    closes = [float(b["close"]) for b in bars]
    last = closes[-1]
    fast = sum(closes[-FAST_BARS:]) / FAST_BARS
    slow = sum(closes[-SLOW_BARS:]) / SLOW_BARS

    up = last > fast > slow
    down = last < fast < slow
    conds.append(
        f"trend: last {last:.2f} vs {FAST_BARS * BAR}min {fast:.2f} vs {SLOW_BARS * BAR}min "
        f"{slow:.2f} ({'up' if up else 'down' if down else 'mixed'})"
    )

    # Session position. The session's own high and low, not the day's daily bar, because the
    # question is where in today's trading this price sits.
    session = [b for b in bars if b["sessionDate"] == bars[-1]["sessionDate"]]
    if len(session) >= 3:
        hi = max(float(b["high"]) for b in session)
        lo = min(float(b["low"]) for b in session)
        if hi > lo:
            pos = (last - lo) / (hi - lo)
            conds.append(f"session: {pos:.0%} of the way up today's range so far")
            if pos > 0.97 and up:
                against.append(
                    "price is at the very top of today's range, so there is no level above it "
                    "inside this session to measure against"
                )
    else:
        missing.append("position in today's range (too few bars in this session)")

    # Volume against the asset's own recent five minute bars. Absent volume is recorded as
    # absent, never as quiet.
    vols = [float(b["volume"]) for b in bars[-SLOW_BARS - 1 : -1] if b["volume"] is not None]
    last_vol = bars[-1]["volume"]
    if not vols or last_vol is None:
        missing.append("volume against its own recent bars (the provider sent no volume)")
    else:
        avg = sum(vols) / len(vols)
        if avg <= 0:
            missing.append("volume against its own recent bars (no traded volume stored)")
        else:
            ratio = float(last_vol) / avg
            conds.append(
                f"volume: {ratio:.2f}x its own last {len(vols)} bars "
                f"({'pass' if ratio >= VOL_ACTIVE else 'fail'})"
            )
            if ratio < VOL_ACTIVE and up:
                against.append(
                    f"the latest bar traded only {ratio:.2f} times its own recent average, so "
                    "the move is not being carried by unusual activity"
                )

    # Break of the previous session's extreme, which is the one level everyone watching this
    # asset intraday can see.
    broke_up = broke_down = False
    if prior_high is None or prior_low is None:
        missing.append("the previous session's range (no earlier session is stored)")
    else:
        broke_up = last > prior_high * (1 + BREAK_PAD)
        broke_down = last < prior_low * (1 - BREAK_PAD)
        conds.append(
            f"break: previous session {prior_low:.2f} to {prior_high:.2f} "
            f"({'up' if broke_up else 'down' if broke_down else 'inside'})"
        )
        if up and not broke_up:
            against.append(
                f"price has not cleared the previous session's high of {prior_high:.2f}, so "
                "the move is still inside a range it has already traded"
            )

    atr = true_range(bars, ATR_WINDOW)
    if atr is None:
        missing.append("bar-by-bar volatility (too few bars)")
    else:
        conds.append(f"volatility: average {ATR_WINDOW}-bar range {atr:.2f}")

    # --- the rules, written out rather than scored
    core_up = [up, broke_up, last_vol is not None and vols and
               float(last_vol) / (sum(vols) / len(vols)) >= VOL_ACTIVE]
    core_down = [down, broke_down, last_vol is not None and vols and
                 float(last_vol) / (sum(vols) / len(vols)) >= VOL_ACTIVE]

    if all(core_up):
        state = "buy"
        head = (
            "Price is above both intraday averages, it has cleared the previous session's "
            "high, and the latest bars are trading more than usual."
        )
    elif all(core_down):
        state = "short"
        head = (
            "Price is below both intraday averages, it has broken the previous session's low, "
            "and the latest bars are trading more than usual."
        )
    elif up or down:
        state = "wait"
        short_of = []
        if not (broke_up or broke_down):
            short_of.append("it has not broken out of the previous session's range")
        if last_vol is not None and vols and float(last_vol) / (sum(vols) / len(vols)) < VOL_ACTIVE:
            short_of.append("the latest bars are not trading more than usual")
        head = (
            "The intraday direction is clear but the conditions are not all present: "
            + (", ".join(short_of) if short_of else "some inputs are unavailable")
            + "."
        )
    else:
        state = "none"
        head = (
            "Price is between its intraday averages, so there is no clear direction to measure "
            "conditions against within the session."
        )

    # Entry and invalidation from the session's own structure, with the window stated.
    entry = max(float(b["high"]) for b in bars[-FAST_BARS:])
    invalid = min(float(b["low"]) for b in bars[-FAST_BARS:])
    return state, head, conds, missing, against, entry, invalid


def run_intraday(cur, today: date) -> int:
    step("read the intraday conditions from stored five minute bars")
    assets = rows(
        cur,
        """
        SELECT DISTINCT a.id, a.symbol FROM "Asset" a
        JOIN "IntradayBar" b ON b."assetId" = a.id AND b.interval = %s
        ORDER BY a.symbol
        """,
        (BAR,),
    )
    written = skipped = 0
    tally: dict[str, int] = {}
    for a in assets:
        bars = rows(
            cur,
            """
            SELECT ts, "sessionDate", open, high, low, close, volume, phase
            FROM "IntradayBar"
            WHERE "assetId" = %s AND interval = %s AND phase = 'regular'
            ORDER BY ts DESC LIMIT %s
            """,
            (a["id"], BAR, SESSION_BARS * 2),
        )
        bars = list(reversed(bars))
        if len(bars) < MIN_BARS:
            skipped += 1
            continue

        newest_session = bars[-1]["sessionDate"]
        prior = [b for b in bars if b["sessionDate"] < newest_session]
        prior_high = max((float(b["high"]) for b in prior), default=None)
        prior_low = min((float(b["low"]) for b in prior), default=None)

        state, head, conds, missing, against, entry, invalid = intraday_read(
            bars, prior_high, prior_low
        )

        # The completeness record decides whether this read may be trusted at all. A partial
        # session is named in `missing` rather than quietly producing a confident read, which
        # is the whole point of storing the session status.
        sess = one(
            cur,
            """
            SELECT status, note FROM "IntradaySession"
            WHERE "assetId" = %s AND interval = %s ORDER BY "sessionDate" DESC LIMIT 1
            """,
            (a["id"], BAR),
        )
        if sess and sess["status"] in ("partial", "stale", "failed"):
            missing.append(f"a complete session ({sess['status']}: {sess['note'][:90]})")

        write_setup(
            cur, a["id"], today, "intraday", state, head, conds, missing, against,
            entry,
            f"the highest price of the last {FAST_BARS * BAR} minutes of regular trading",
            invalid,
            f"the lowest price of the last {FAST_BARS * BAR} minutes. Below it, the intraday "
            "trend these conditions were read from is no longer there",
            None, INTRADAY_RULES,
        )
        tally[state] = tally.get(state, 0) + 1
        written += 1
    for state, n in sorted(tally.items()):
        print(f"  intraday {state:<6} {n}")
    print(f"  {written} intraday reads, {skipped} without enough stored bars")
    return written


# ------------------------------------------------------------------------------- longer term


def longer_read(bars: list[dict], rel: float | None):
    """(state, headline, conditions, missing, against, entry, invalidation) on daily closes.

    A deliberately different question from the swing read: not "is it moving" but "where does
    this sit in its own multi-year history, and has that changed". The windows are 100 and 200
    sessions inside a two year range, so a three week move cannot flip it.
    """
    conds: list[str] = []
    missing: list[str] = []
    against: list[str] = []

    closes = [float(b["close"]) for b in bars]
    last = closes[-1]
    fast = sum(closes[-LONG_FAST:]) / LONG_FAST
    slow = sum(closes[-LONG_SLOW:]) / LONG_SLOW

    up = last > fast > slow
    down = last < fast < slow
    conds.append(
        f"trend: close {last:.2f} vs {LONG_FAST}d {fast:.2f} vs {LONG_SLOW}d {slow:.2f} "
        f"({'up' if up else 'down' if down else 'mixed'})"
    )

    window = closes[-LONG_RANGE:] if len(closes) >= LONG_RANGE else closes
    hi, lo = max(window), min(window)
    pos = (last - lo) / (hi - lo) if hi > lo else None
    if pos is None:
        missing.append("position in its multi-year range (the range has no width)")
    else:
        conds.append(f"position: {pos:.0%} of the way up its {len(window)} session range")
        if pos < 0.25 and up:
            against.append(
                "the trend has turned up but price is still in the bottom quarter of its own "
                "multi-year range, so most of the decline has not been recovered"
            )

    # The 200 day mean's own direction. A price above a falling long mean is a different
    # situation from a price above a rising one, and the sign of that slope is the cheapest
    # honest way to tell them apart.
    if len(closes) >= LONG_SLOW + 20:
        earlier = sum(closes[-LONG_SLOW - 20 : -20]) / LONG_SLOW
        rising = slow > earlier
        conds.append(
            f"long mean: {LONG_SLOW}d average {'rising' if rising else 'falling'} over the "
            f"last 20 sessions ({'pass' if rising == up else 'fail'})"
        )
        if up and not rising:
            against.append(
                f"price is above a {LONG_SLOW} day average that is still falling, so the "
                "longer trend has not turned yet"
            )
    else:
        missing.append(f"the direction of the {LONG_SLOW} day average (not enough history)")

    if rel is None:
        missing.append("return against its industry over 100 sessions (too few peers)")
    else:
        conds.append(
            f"relative: {rel:+.1f} points against its industry over {LONG_FAST} sessions "
            f"({'pass' if rel >= LONG_REL_EDGE else 'fail'})"
        )
        if rel < 0 and up:
            against.append(
                f"it is {abs(rel):.1f} points behind its own industry over {LONG_FAST} "
                "sessions, so the sector is doing the work"
            )

    core_up = [up, pos is not None and pos > 0.5, rel is not None and rel >= LONG_REL_EDGE]
    core_down = [down, pos is not None and pos < 0.5, rel is not None and rel <= -LONG_REL_EDGE]

    if all(core_up):
        state = "buy"
        head = (
            "Price is above both long averages, in the upper half of its multi-year range, "
            "and ahead of its own industry over a hundred sessions."
        )
    elif all(core_down):
        state = "short"
        head = (
            "Price is below both long averages, in the lower half of its multi-year range, "
            "and behind its own industry over a hundred sessions."
        )
    elif up or down:
        state = "wait"
        short_of = []
        if pos is not None and ((up and pos <= 0.5) or (down and pos >= 0.5)):
            short_of.append("it has not yet crossed the middle of its own multi-year range")
        if rel is not None and abs(rel) < LONG_REL_EDGE:
            short_of.append("it is moving with its industry rather than apart from it")
        head = (
            "The long direction is clear but the conditions are not all present: "
            + (", ".join(short_of) if short_of else "some inputs are unavailable")
            + "."
        )
    else:
        state = "none"
        head = (
            "Price is between its long averages, so there is no multi-year direction to "
            "measure conditions against."
        )

    highs, lows = pivots(bars, STRUCTURE_LOOKBACK)
    entry = next_level(highs, last, above=True) or max(closes[-LONG_FAST:])
    invalid = next_level(lows, last, above=False) or min(closes[-LONG_FAST:])
    return state, head, conds, missing, against, entry, invalid


def industry_relative_long(cur, asset_id: str, industry_id: str) -> float | None:
    """The asset's 100 session return minus its own industry's mean, peers only.

    The same shape as jobs/setup.py's 20 day version and for the same reason: an industry
    comparison must never cross a currency, so it is taken inside one industry or not at all.
    """
    got = rows(
        cur,
        """
        WITH bounds AS (
            SELECT a.id, max(p.date) AS newest
            FROM "Asset" a
            JOIN "PriceSnapshot" p ON p."assetId" = a.id AND p.close IS NOT NULL
            WHERE a."industryId" = %s
            GROUP BY a.id
        ),
        rets AS (
            SELECT b.id,
                   (SELECT close FROM "PriceSnapshot"
                     WHERE "assetId" = b.id AND date = b.newest) AS last,
                   (SELECT close FROM "PriceSnapshot"
                     WHERE "assetId" = b.id AND date <= b.newest - (%s * interval '1 day')
                     ORDER BY date DESC LIMIT 1) AS base
            FROM bounds b
        )
        SELECT id, last, base FROM rets
        WHERE last IS NOT NULL AND base IS NOT NULL AND base > 0
        """,
        (industry_id, int(LONG_FAST * 1.45)),
    )
    if len(got) < 3:
        return None
    pcts = {r["id"]: (float(r["last"]) / float(r["base"]) - 1.0) * 100.0 for r in got}
    mine = pcts.get(asset_id)
    if mine is None:
        return None
    peers = [v for k, v in pcts.items() if k != asset_id]
    return mine - (sum(peers) / len(peers)) if peers else None


def run_longer(cur, today: date) -> int:
    step("read the longer term conditions from stored daily closes")
    assets = rows(cur, 'SELECT id, symbol, "industryId" FROM "Asset" ORDER BY symbol')
    written = skipped = 0
    tally: dict[str, int] = {}
    for a in assets:
        bars = rows(
            cur,
            """
            SELECT date, open, high, low, close, volume FROM "PriceSnapshot"
            WHERE "assetId" = %s AND close IS NOT NULL
            ORDER BY date DESC LIMIT %s
            """,
            (a["id"], LONG_RANGE + 40),
        )
        bars = list(reversed(bars))
        # High and low are needed for the structural levels. Rows stored before OHLC existed
        # have only a close, so they are filled with the close for the pivot test rather than
        # dropped — a close is a real traded price and the level it marks is real.
        for b in bars:
            if b["high"] is None:
                b["high"] = b["close"]
            if b["low"] is None:
                b["low"] = b["close"]
        if len(bars) < MIN_LONG:
            skipped += 1
            continue

        rel = industry_relative_long(cur, a["id"], a["industryId"])
        state, head, conds, missing, against, entry, invalid = longer_read(bars, rel)
        write_setup(
            cur, a["id"], today, "longer", state, head, conds, missing, against,
            entry,
            f"the nearest price above where the series last turned within {STRUCTURE_LOOKBACK} "
            "sessions, or the highest close of the last 100 when it has cleared them all",
            invalid,
            "the nearest level below where the series last turned. Below it, the multi-year "
            "structure these conditions were read from has changed",
            None, LONGER_RULES,
        )
        tally[state] = tally.get(state, 0) + 1
        written += 1
    for state, n in sorted(tally.items()):
        print(f"  longer {state:<6} {n}")
    print(f"  {written} longer term reads, {skipped} without {MIN_LONG} stored closes")
    return written


# ----------------------------------------------------------------------------------- targets


def target_rows(entry: float, invalid: float, direction: str, atr: float | None,
                level: float | None, analog: dict | None) -> list[dict]:
    """Every target range the stored data supports, one row per method.

    Returns an empty list rather than a guess when nothing supports one. The `direction`
    decides which way the range points, so a short setup is never handed an upside target.
    """
    out: list[dict] = []
    risk = abs(entry - invalid)
    if risk <= 0:
        return out
    sign = 1.0 if direction == "buy" else -1.0

    # Each range holds the target only, never the entry. Spanning entry-to-target would make
    # the near edge of the range the entry itself, which reads as a reward of zero and is the
    # bug this comment replaces.
    if level is not None:
        out.append({
            "method": "structure",
            "low": level, "high": level,
            "note": (
                f"the nearest price where the series already turned, {level:.2f}. A single "
                "level it has stopped at before, not a forecast that it will stop there again"
            ),
        })

    if atr is not None and atr > 0:
        reach = entry + sign * ATR_MULTIPLE * atr
        out.append({
            "method": "volatility",
            "low": reach, "high": reach,
            "note": (
                f"{ATR_MULTIPLE:.0f} times its own average {ATR_WINDOW}-period range of "
                f"{atr:.2f}, reaching {reach:.2f}. A single distance this asset typically "
                "covers, not a direction it must go"
            ),
        })

    if analog and analog.get("matches") and int(analog["matches"]) >= ANALOG_MIN:
        lo_pct, hi_pct = float(analog["medianPct"]), float(analog["maxPct"])
        if direction == "short":
            lo_pct, hi_pct = float(analog["minPct"]), float(analog["medianPct"])
        a = entry * (1 + lo_pct / 100.0)
        b = entry * (1 + hi_pct / 100.0)
        low, high = sorted((a, b))
        out.append({
            "method": "analog",
            "low": low, "high": high,
            "note": (
                f"what actually followed {analog['matches']} similar past days: a median of "
                f"{float(analog['medianPct']):+.1f}% and a range to "
                f"{(hi_pct if direction == 'buy' else lo_pct):+.1f}%. A measured distribution, "
                "not a projection"
            ),
        })

    for row in out:
        near = row["low"] if direction == "buy" else row["high"]
        row["distancePct"] = (near / entry - 1.0) * 100.0
        row["rewardRisk"] = abs(near - entry) / risk

    # Preserve disagreement rather than averaging it.
    #
    # Measured as the spread between the methods' reward distances, as a share of the largest
    # of them: "the methods' targets differ by this much of the furthest one's distance". That
    # is scale free and reads in plain words, where dividing by the price would make a 1% and a
    # 40% target look similar on an expensive asset.
    if len(out) > 1:
        reaches = [abs((r["low"] if direction == "buy" else r["high"]) - entry) for r in out]
        furthest = max(reaches)
        spread = (max(reaches) - min(reaches)) / furthest if furthest > 0 else 0.0
        for row in out:
            row["agreement"] = spread
    return out


def run_targets(cur) -> int:
    step("attach measured target ranges to every stored setup")
    setups = rows(
        cur,
        """
        SELECT s.id, s."assetId", s.horizon, s.state, s."entryLevel", s."invalidateLevel",
               a.symbol
        FROM "AssetSetup" s JOIN "Asset" a ON a.id = s."assetId"
        WHERE s."periodEnd" = (
            SELECT max("periodEnd") FROM "AssetSetup" x WHERE x.horizon = s.horizon
        )
        AND s.state IN ('buy','short')
        AND s."entryLevel" IS NOT NULL AND s."invalidateLevel" IS NOT NULL
        ORDER BY a.symbol, s.horizon
        """,
    )
    print(f"  {len(setups)} directional setups have both an entry and an invalidation")
    if not setups:
        print(
            "  no target is written for a wait or no-clear-setup read, because a target with "
            "no stated entry is a number with no decision attached to it"
        )
        return 0

    written = 0
    disagreeing = 0
    for s in setups:
        if s["horizon"] == "intraday":
            bars = list(reversed(rows(
                cur,
                """
                SELECT high, low, close FROM "IntradayBar"
                WHERE "assetId" = %s AND interval = %s AND phase = 'regular'
                ORDER BY ts DESC LIMIT %s
                """,
                (s["assetId"], BAR, SESSION_BARS * 2),
            )))
        else:
            bars = list(reversed(rows(
                cur,
                """
                SELECT high, low, close FROM "PriceSnapshot"
                WHERE "assetId" = %s AND close IS NOT NULL
                ORDER BY date DESC LIMIT %s
                """,
                (s["assetId"], STRUCTURE_LOOKBACK + 40),
            )))
            for b in bars:
                if b["high"] is None:
                    b["high"] = b["close"]
                if b["low"] is None:
                    b["low"] = b["close"]
        if len(bars) < ATR_WINDOW + 3:
            continue

        atr = true_range(bars, ATR_WINDOW)
        highs, lows = pivots(bars, STRUCTURE_LOOKBACK)
        entry = float(s["entryLevel"])
        level = next_level(highs if s["state"] == "buy" else lows, entry,
                           above=s["state"] == "buy")
        analog = one(
            cur,
            """
            SELECT matches, positive, "medianPct", "minPct", "maxPct"
            FROM "AssetAnalog" WHERE "assetId" = %s AND "horizonDays" = 5
            ORDER BY "periodEnd" DESC LIMIT 1
            """,
            (s["assetId"],),
        ) if s["horizon"] != "intraday" else None

        got = target_rows(entry, float(s["invalidateLevel"]), s["state"], atr, level, analog)
        if not got:
            continue
        if got[0].get("agreement", 0) >= DISAGREE_AT:
            disagreeing += 1
        for row in got:
            cur.execute(
                """
                INSERT INTO "SetupTarget" ("setupId", method, low, high, "distancePct",
                    "rewardRisk", agreement, note, source, "computedAt")
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT ("setupId", method) DO UPDATE SET
                    low = EXCLUDED.low, high = EXCLUDED.high,
                    "distancePct" = EXCLUDED."distancePct",
                    "rewardRisk" = EXCLUDED."rewardRisk", agreement = EXCLUDED.agreement,
                    note = EXCLUDED.note, "computedAt" = now()
                """,
                (
                    s["id"], row["method"], row["low"], row["high"], row.get("distancePct"),
                    row.get("rewardRisk"), row.get("agreement"), row["note"], TARGET_SOURCE,
                ),
            )
            written += 1
    print(f"  {written} target ranges stored")
    print(
        f"  {disagreeing} setups have methods that disagree by {DISAGREE_AT:.0%} or more of "
        "the wider range. The disagreement is stored and shown, never averaged away."
    )
    return written


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    today = date.today()
    conn = db()
    cur = conn.cursor()
    try:
        if which in ("all", "intraday"):
            run_intraday(cur, today)
            conn.commit()
        if which in ("all", "longer"):
            run_longer(cur, today)
            conn.commit()
        if which in ("all", "targets"):
            run_targets(cur)
            conn.commit()
        print(
            "\n  the same asset may read differently on each horizon. That is not a "
            "contradiction: each is computed from a different window and answers a different "
            "question."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
