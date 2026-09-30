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

# A sample below this is stored but graded none: the row exists so the page can say how many
# matches there were, which is more useful than an empty panel.
MIN_MATCHES_LOW = 8
MIN_MATCHES_MEDIUM = 20
MIN_MATCHES_HIGH = 40

# The most recent days are skipped as match candidates for a horizon, because their outcome
# has not happened yet. Handled by construction below rather than by a date filter.


def series(cur, asset_id: str):
    return rows(
        cur,
        """
        SELECT date, close, volume FROM "PriceSnapshot"
        WHERE "assetId" = %s AND close IS NOT NULL
        ORDER BY date ASC
        """,
        (asset_id,),
    )


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


def similar(a: dict, b: dict) -> bool:
    """Every factor inside tolerance. A factor missing on either side is not a match.

    Missing is not treated as compatible: a day whose volume ratio could not be computed is
    not "close enough on volume", it is a day measured on fewer factors, and letting it in
    would silently loosen the rule for exactly the days with the least data behind them.
    """
    if abs(a["day"] - b["day"]) > DAY_TOL:
        return False
    if a["vol"] is None or b["vol"] is None:
        return False
    if abs(a["vol"] - b["vol"]) > VOL_TOL:
        return False
    if a["five"] is None or b["five"] is None:
        return False
    return abs(a["five"] - b["five"]) <= FIVE_TOL


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
    today = date.today()
    tol_note = (
        f"one day return within {DAY_TOL} points, volume ratio within {VOL_TOL} of its "
        f"{VOL_WINDOW} day average, five day return within {FIVE_TOL} points"
    )

    conn = db()
    cur = conn.cursor()
    try:
        assets = rows(cur, 'SELECT id, symbol FROM "Asset" ORDER BY symbol')
        step(f"near term analogs for {len(assets)} assets")
        written = thin = skipped = 0

        for a in assets:
            bars = series(cur, a["id"])
            if len(bars) < VOL_WINDOW + 30:
                skipped += 1
                continue

            latest = len(bars) - 1
            now = factors(bars, latest)
            if now is None or now["vol"] is None or now["five"] is None:
                skipped += 1
                continue

            for horizon in HORIZONS:
                moves: list[float] = []
                # Candidates stop far enough back that the outcome exists. The latest day
                # itself is never a candidate for its own comparison.
                for i in range(VOL_WINDOW, latest - horizon + 1):
                    past = factors(bars, i)
                    if past is None or not similar(now, past):
                        continue
                    got = forward(bars, i, horizon)
                    if got is not None:
                        moves.append(got)

                g, notes = ("none", ["no past day matched this setup"]) if not moves else grade(
                    len(moves), moves
                )
                cur.execute(
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
                    (
                        a["id"], today, horizon, now["day"], now["vol"], now["five"],
                        tol_note, len(moves), len([m for m in moves if m > 0]),
                        mean(moves), median(moves),
                        min(moves) if moves else None, max(moves) if moves else None,
                        g, "; ".join(notes).capitalize() if notes else None, ANALOG,
                    ),
                )
                written += 1
                if g == "none":
                    thin += 1
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
