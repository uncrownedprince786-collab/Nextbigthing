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


def closes(cur, asset_id: str):
    return rows(
        cur,
        """
        SELECT date, close, volume FROM "PriceSnapshot"
        WHERE "assetId" = %s AND close IS NOT NULL
        ORDER BY date DESC LIMIT %s
        """,
        (asset_id, RANGE_WINDOW + SLOW),
    )


def industry_relative(cur, asset_id: str, industry_id: str) -> float | None:
    """The asset's 20 day return minus the mean 20 day return of its own industry.

    Peers only, and the asset's own industry only, so a rupee listing is never measured
    against a dollar one. None when too few peers have the history to average.
    """
    got = rows(
        cur,
        """
        WITH bounds AS (
            SELECT a.id,
                   max(p.date) AS newest
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
                     WHERE "assetId" = b.id
                       AND date <= b.newest - (%s * interval '1 day')
                     ORDER BY date DESC LIMIT 1) AS base
            FROM bounds b
        )
        SELECT id, last, base FROM rets WHERE last IS NOT NULL AND base IS NOT NULL AND base > 0
        """,
        (industry_id, FOR_DAYS),
    )
    if len(got) < 3:
        return None
    pcts = {r["id"]: (float(r["last"]) / float(r["base"]) - 1.0) * 100.0 for r in got}
    mine = pcts.get(asset_id)
    if mine is None:
        return None
    peers = [v for k, v in pcts.items() if k != asset_id]
    if not peers:
        return None
    return mine - (sum(peers) / len(peers))


# Calendar days used to reach back roughly FAST trading days.
FOR_DAYS = 28


def main() -> None:
    today = date.today()
    conn = db()
    cur = conn.cursor()
    try:
        assets = rows(
            cur, 'SELECT id, symbol, name, "industryId" FROM "Asset" ORDER BY symbol'
        )
        step(f"measured conditions for {len(assets)} assets")
        tally = {"buy": 0, "short": 0, "wait": 0, "none": 0}
        skipped = 0

        for a in assets:
            bars = closes(cur, a["id"])
            if len(bars) < SLOW + 2:
                skipped += 1
                continue

            series = list(reversed(bars))
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

            rel = industry_relative(cur, a["id"], a["industryId"])

            signal = one(
                cur,
                """
                SELECT tone::text AS tone, catalyst, "changeKind", "recentStories"
                FROM "HumanSignal" WHERE "assetId" = %s
                ORDER BY "periodEnd" DESC LIMIT 1
                """,
                (a["id"],),
            )
            analog = one(
                cur,
                """
                SELECT matches, positive, "medianPct", "minPct", "maxPct"
                FROM "AssetAnalog" WHERE "assetId" = %s AND "horizonDays" = 5
                ORDER BY "periodEnd" DESC LIMIT 1
                """,
                (a["id"],),
            )
            soon = one(
                cur,
                """
                SELECT e.name, e.date FROM "Event" e
                JOIN "EventLink" l ON l."eventId" = e.id
                WHERE l."assetId" = %s AND e.scheduled = true AND e.date >= %s
                ORDER BY e.date ASC LIMIT 1
                """,
                (a["id"], today),
            )

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
            entry, invalid = (low, high) if state == "short" else (high, low)
            if state == "short":
                entry_note = (
                    f"the lowest close of the last {FAST} sessions. A close below it would be a "
                    "move past where it recently held"
                )
                invalid_note = (
                    f"the highest close of the last {FAST} sessions. A close above it means the "
                    "trend these conditions were read from is no longer there"
                )
            else:
                entry_note = (
                    f"the highest close of the last {FAST} sessions. A close above it would be "
                    "a move past where it recently stalled"
                )
                invalid_note = (
                    f"the lowest close of the last {FAST} sessions. A close below it means the "
                    "trend these conditions were read from is no longer there"
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

            cur.execute(
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
                (
                    a["id"], today, HORIZON, state, head,
                    " | ".join(conds), " | ".join(missing) or "none", " | ".join(against) or "none",
                    entry, entry_note, invalid, invalid_note,
                    range_note, grade, "; ".join(note_bits).capitalize() or None, RULES,
                ),
            )
            tally[state] += 1
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
