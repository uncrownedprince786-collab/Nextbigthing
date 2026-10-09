"""What measurably followed the past days that most resembled each asset's latest day.

The question this answers, stated exactly, because a looser version of it would be a
forecast: given the closest past days on the factors the database actually holds, what did
the next day and the next week do, how often was it up, and how wide was the spread.

It does not say what happens next. The same setup appears in the sample with both outcomes
and usually a large range between them, which is precisely why the count, the spread and the
extremes are stored beside the average instead of under it. An average of +0.4% over 60
matches that ran from -9% to +11% is not a signal, and a reader has to be able to see that.

Factors
-------
Only what is stored, and only what is comparable across time:

  * the one day return into the day
  * volume as a multiple of its own trailing 20 day average, so a thin stock and a heavy one
    are measured on the same scale
  * the five day return, for the short trend the day sits in

Deliberately not used: absolute price, absolute volume, market cap. All three make two eras
of the same asset incomparable, and matching on them would mostly recover "days near this
price" rather than days that looked like this one.

Matching
--------
A past day matches when every factor is inside its tolerance. Not a distance score with a
cutoff: a tolerance per factor is auditable, and `toleranceNote` stores the window the row
was built with so a figure can be checked later against the rule that produced it.

Forward windows are trading days as stored, not calendar days, so a Friday setup measures to
the next session rather than to a weekend with no close in it.

Run: python jobs/analogs.py
Writes: AssetAnalog
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, mean, median, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

ANALOG = "Stored closes and volumes"

HORIZONS = (1, 5)

# Trailing window the volume multiple is measured against.
VOL_WINDOW = 20

# Tolerances. Wide enough to find a sample, narrow enough that "similar" means something:
# a day up 2% and a day up 6% are not the same day, and matching them would turn the result
# into the asset's unconditional average return, which is a different and useless figure.
DAY_TOL = 1.25          # percentage points either side of the one day return
VOL_TOL = 0.45          # multiples either side of the volume ratio
FIVE_TOL = 5.0          # percentage points either side of the five day return

# The window used on the no-volume path, in standard deviations of the asset's own returns.
#
# Not a fourth hand-picked constant: 0.8 is where the dispersion-scaled window lands closest to
# the three above on the instruments they were sized for. A US equity's daily return has a sigma
# near 1.5 points, and 0.8 of that is 1.2 against the 1.25 `DAY_TOL` uses. So an asset matched
# this way is matched about as tightly as an equity is, measured in its own units instead of in
# somebody else's percentage points. See `tolerances`.
SIGMA_TOL = 0.8

# A sample below this is stored but graded none: the row exists so the page can say how many
# matches there were, which is more useful than an empty panel.
MIN_MATCHES_LOW = 8
MIN_MATCHES_MEDIUM = 20
MIN_MATCHES_HIGH = 40

# The most recent days are skipped as match candidates for a horizon, because their outcome
# has not happened yet. Handled by construction below rather than by a date filter.


# Assets whose whole history is read in one statement. This job needs every stored close --
# an analog is a past day, and cutting the window would cut the matches -- so the whole
# universe at once is the wrong trade: at a deeper history that is millions of rows held in
# memory to compute one row per asset. A chunk is the middle: one round trip per CHUNK assets
# instead of one per asset, with the memory bounded by the chunk rather than by the pool.
CHUNK = 25


def series_for(cur, asset_ids: list[str]) -> dict[str, list[dict]]:
    """{assetId: every stored close, oldest first} for a chunk of assets."""
    out: dict[str, list[dict]] = {a: [] for a in asset_ids}
    for r in rows(
        cur,
        """
        SELECT "assetId", date, close, volume FROM "PriceSnapshot"
        WHERE "assetId" = ANY(%s) AND close IS NOT NULL
        ORDER BY "assetId", date ASC
        """,
        (asset_ids,),
    ):
        out[r["assetId"]].append(r)
    return out


def factors(bars: list[dict], i: int):
    """The setup at index i, or None when there is not enough history behind it."""
    if i < VOL_WINDOW:
        return None
    prev = float(bars[i - 1]["close"])
    if prev <= 0:
        return None
    day_ret = (float(bars[i]["close"]) / prev - 1.0) * 100.0

    vols = [float(b["volume"]) for b in bars[i - VOL_WINDOW : i] if b["volume"]]
    vol_ratio = None
    if len(vols) >= VOL_WINDOW // 2 and bars[i]["volume"]:
        avg = sum(vols) / len(vols)
        if avg > 0:
            vol_ratio = float(bars[i]["volume"]) / avg

    five = None
    base5 = float(bars[i - 5]["close"]) if i >= 5 else 0.0
    if base5 > 0:
        five = (float(bars[i]["close"]) / base5 - 1.0) * 100.0

    return {"day": day_ret, "vol": vol_ratio, "five": five}


def forward(bars: list[dict], i: int, horizon: int):
    """Measured return from index i to i+horizon, or None when that day is not stored."""
    j = i + horizon
    if j >= len(bars):
        return None
    base = float(bars[i]["close"])
    if base <= 0:
        return None
    return (float(bars[j]["close"]) / base - 1.0) * 100.0


def similar(a: dict, b: dict, tol: dict) -> bool:
    """Every factor inside tolerance. A factor missing on either side is not a match.

    Missing is not treated as compatible: a day whose volume ratio could not be computed is
    not "close enough on volume", it is a day measured on fewer factors, and letting it in
    would silently loosen the rule for exactly the days with the least data behind them.

    `tol` carries the three tolerances and whether volume is one of the factors at all. That
    second part is the exception and it is narrow: an instrument whose venue publishes no volume
    *anywhere in its stored history* is matched on the two return factors. See `tolerances`.
    """
    if abs(a["day"] - b["day"]) > tol["day"]:
        return False
    if tol["use_volume"]:
        if a["vol"] is None or b["vol"] is None:
            return False
        if abs(a["vol"] - b["vol"]) > tol["vol"]:
            return False
    if a["five"] is None or b["five"] is None:
        return False
    return abs(a["five"] - b["five"]) <= tol["five"]


def stdev(xs: list[float]) -> float | None:
    """Population standard deviation, or None under three values."""
    xs = [x for x in xs if x is not None]
    if len(xs) < 3:
        return None
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def tolerances(bars: list[dict]) -> dict | None:
    """The matching rule for one asset: three tolerances and whether volume is a factor.

    **Why an asset needs its own rule at all.** Until now there was one: three constants, sized
    against US equities. For an instrument that publishes no volume this did not merely fit
    badly, it excluded the instrument entirely -- `similar` refused every pair of days because
    neither carried a volume ratio, so all 27 currency pairs were skipped and held **zero** stored
    analogs while every other class was near-complete. Two of the four things that can confirm a
    direction were permanently absent for them, and 24 of 27 sat in WAIT as a result.

    A currency pair has no consolidated tape. That is a fact about the instrument and no amount
    of re-running fixes it, so the choice is between matching those days on the factors that do
    exist and never matching them at all. This matches them, and `toleranceNote` on every row
    records that volume was not among the factors -- a reader comparing an FX row to an equity row
    is told they were built by different rules.

    **The tolerances are then scaled to the asset's own dispersion, and this is the part that
    makes it honest.** `DAY_TOL` is 1.25 percentage points. A US equity moves about 1.5 points on
    a typical day, so that is a meaningful window. EURUSD moves about 0.35, so 1.25 points is
    roughly three and a half typical days in either direction -- it would match nearly every day
    in the series to nearly every other, and return the asset's unconditional average return
    wearing the word "similar". That is rule 42 exactly: a constant compared against the wrong
    scale is a different constant in every market.

    So on this path the window is **0.8 standard deviations of the asset's own daily return**,
    which is the same shape of window in every market, and the five-day window is the same
    multiple of the five-day dispersion. 0.8 is chosen to land near the equity constant on an
    equity: at a 1.5 point daily sigma it gives 1.2 points, against the 1.25 that path uses.

    Returns None when the series is too short or too flat to measure a dispersion from, in which
    case the asset keeps no analog row rather than getting one built on a tolerance of zero.
    """
    has_volume = any(b["volume"] for b in bars)
    if has_volume:
        return {"day": DAY_TOL, "vol": VOL_TOL, "five": FIVE_TOL, "use_volume": True}

    days, fives = [], []
    for i in range(1, len(bars)):
        prev = float(bars[i - 1]["close"])
        if prev > 0:
            days.append((float(bars[i]["close"]) / prev - 1.0) * 100.0)
        if i >= 5:
            base = float(bars[i - 5]["close"])
            if base > 0:
                fives.append((float(bars[i]["close"]) / base - 1.0) * 100.0)

    day_sd, five_sd = stdev(days), stdev(fives)
    if not day_sd or not five_sd:
        return None
    return {
        "day": SIGMA_TOL * day_sd,
        "vol": None,
        "five": SIGMA_TOL * five_sd,
        "use_volume": False,
    }


def tolerance_note(tol: dict) -> str:
    """What the row was built with, in the words the stored column keeps."""
    if tol["use_volume"]:
        return (
            f"one day return within {DAY_TOL} points, volume ratio within {VOL_TOL} of its "
            f"{VOL_WINDOW} day average, five day return within {FIVE_TOL} points"
        )
    return (
        f"one day return within {tol['day']:.2f} points and five day return within "
        f"{tol['five']:.2f} points, each {SIGMA_TOL} standard deviations of this asset's own "
        "returns; volume was not a factor because no venue publishes volume for this instrument"
    )


def grade(matches: int, moves: list[float]) -> tuple[str, list[str]]:
    notes: list[str] = []
    if matches < MIN_MATCHES_LOW:
        return "none", [
            f"only {matches} past days matched, too few to describe what followed them"
        ]
    if matches >= MIN_MATCHES_HIGH:
        g = "high"
    elif matches >= MIN_MATCHES_MEDIUM:
        g = "medium"
    else:
        g = "low"
        notes.append(f"{matches} matches, so the average rests on a small sample")

    up = len([m for m in moves if m > 0])
    share = up / len(moves)
    # A near even split is the most common honest outcome and the easiest thing to
    # misread from an average alone, so it is said in words and it caps the grade.
    if 0.4 <= share <= 0.6:
        if g == "high":
            g = "medium"
        notes.append(
            f"{up} of {len(moves)} matches went up, which is close to an even split: the "
            "average describes the middle of two groups rather than a tendency"
        )

    spread = max(moves) - min(moves)
    avg = mean(moves) or 0.0
    if spread > 8 * max(abs(avg), 0.25):
        if g == "high":
            g = "medium"
        notes.append(
            f"outcomes ran from {min(moves):+.1f}% to {max(moves):+.1f}%, a spread far wider "
            "than the average, so the average is not a typical case"
        )
    return g, notes


def main() -> None:
    # The calendar, kept only as the fallback for an asset with no stored close -- which cannot
    # happen below, because a row is only written after `series` returned bars. Every row's
    # `periodEnd` is the date of the bar the comparison was actually made from; see the note in
    # the loop. `jobs/setup.py` states the same rule at length and `jobs/factors.py` owns it.
    today = date.today()

    conn = db()
    cur = conn.cursor()
    try:
        assets = rows(cur, 'SELECT id, symbol FROM "Asset" ORDER BY symbol')
        step(f"near term analogs for {len(assets)} assets")
        written = thin = skipped = 0
        payload: list[tuple] = []
        bars_by_asset: dict[str, list[dict]] = {}

        for index, a in enumerate(assets):
            if a["id"] not in bars_by_asset:
                chunk = [x["id"] for x in assets[index : index + CHUNK]]
                bars_by_asset = series_for(cur, chunk)
            bars = bars_by_asset.get(a["id"], [])
            if len(bars) < VOL_WINDOW + 30:
                skipped += 1
                continue

            # The matching rule for this asset, decided from its own stored series. An
            # instrument with no published volume anywhere in its history is matched on the two
            # return factors, at a window scaled to its own dispersion; everything else keeps
            # the three constants exactly as before. See `tolerances`.
            tol = tolerances(bars)
            if tol is None:
                skipped += 1
                continue
            tol_note = tolerance_note(tol)

            latest = len(bars) - 1
            now = factors(bars, latest)
            # `vol` is only required where it is a factor. Requiring it unconditionally is what
            # skipped every currency pair before this: the latest day of a pair has no volume
            # ratio, so the asset was dropped before a single candidate was considered.
            if now is None or now["five"] is None:
                skipped += 1
                continue
            if tol["use_volume"] and now["vol"] is None:
                skipped += 1
                continue

            # The session this comparison was made from, not the day the job ran. `now` is the
            # setup on `bars[latest]`, so that bar's date is what the row describes. Dating it to
            # the calendar put 3,524 rows on 2026-10-08, a day on which nothing traded and no
            # close is stored, because this job was run from a UTC+5 host before the US close.
            # Every reader of this table takes the newest `periodEnd` per asset, so a row dated
            # forward does not merely read oddly -- it wins.
            period_end = bars[latest]["date"] or today

            for horizon in HORIZONS:
                moves: list[float] = []
                # Candidates stop far enough back that the outcome exists. The latest day
                # itself is never a candidate for its own comparison.
                for i in range(VOL_WINDOW, latest - horizon + 1):
                    past = factors(bars, i)
                    if past is None or not similar(now, past, tol):
                        continue
                    got = forward(bars, i, horizon)
                    if got is not None:
                        moves.append(got)

                g, notes = ("none", ["no past day matched this setup"]) if not moves else grade(
                    len(moves), moves
                )
                payload.append(
                    (
                        a["id"], period_end, horizon, now["day"], now["vol"], now["five"],
                        tol_note, len(moves), len([m for m in moves if m > 0]),
                        mean(moves), median(moves),
                        min(moves) if moves else None, max(moves) if moves else None,
                        g, "; ".join(notes).capitalize() if notes else None, ANALOG,
                    )
                )
                written += 1
                if g == "none":
                    thin += 1

        # One statement for every row the loop produced. It was an execute per asset per
        # horizon and a commit per asset, which on a host outside the database's region was
        # seven minutes of waiting to write 662 rows.
        cur.executemany(
                    """
                    INSERT INTO "AssetAnalog" ("assetId", "periodEnd", "horizonDays",
                        "dayReturnPct", "volumeRatio", "fiveDayPct", "toleranceNote",
                        matches, positive, "meanPct", "medianPct", "minPct", "maxPct",
                        confidence, "confidenceNote", source, "computedAt")
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::"Confidence",%s,%s,now())
                    ON CONFLICT ("assetId", "periodEnd", "horizonDays") DO UPDATE SET
                        "dayReturnPct" = EXCLUDED."dayReturnPct",
                        "volumeRatio" = EXCLUDED."volumeRatio",
                        "fiveDayPct" = EXCLUDED."fiveDayPct",
                        "toleranceNote" = EXCLUDED."toleranceNote",
                        matches = EXCLUDED.matches, positive = EXCLUDED.positive,
                        "meanPct" = EXCLUDED."meanPct", "medianPct" = EXCLUDED."medianPct",
                        "minPct" = EXCLUDED."minPct", "maxPct" = EXCLUDED."maxPct",
                        confidence = EXCLUDED.confidence,
                        "confidenceNote" = EXCLUDED."confidenceNote",
                        "computedAt" = now()
                    """,
                    payload,
        )
        conn.commit()

        print(
            f"  {written} rows written, {thin} with too few matches to grade, "
            f"{skipped} assets without enough stored history"
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
