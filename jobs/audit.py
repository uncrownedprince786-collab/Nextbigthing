"""The Brain measuring itself: what it cannot see, and whether its grades deserve belief.

Three things, all computed from stored rows.

Coverage
--------
A feed that quietly dies looks exactly like a quiet week. The second is a finding and the
first is a fault, and nothing in the data distinguishes them, so the gap between how often a
source *should* produce something and how long it has actually been silent is measured:

    gapRatio = actualGap / expectedInterval
    missRisk = 1 - exp(-criticality x gapRatio)

Criticality is a judgement and is stored beside the arithmetic rather than folded into it, so
a reader can disagree with the weight without having to recompute the measurement.

Calibration
-----------
A confidence grade is a claim about how often something holds, and until that claim is
checked the grade is decoration. So each grade is given an explicit claimed hit rate — a
declared starting point, not a measurement — and the loop measures what actually happened:

    Brier   = mean((p - y)^2)
    LogLoss = -mean(y log p + (1-y) log(1-p))

A grade that claims 65% and lands at 50% is a grade that needs lowering, and this is the only
machinery on the site capable of saying so. Nothing is published below MIN_BUCKET matured
rows, because a hit rate over four cases is the sort of number this exists to prevent.

Source reliability
------------------
A Beta posterior per source and question rather than a trust level in a config file:

    theta_s ~ Beta(alpha + successes, beta + observations - successes)
    E[theta_s] = (alpha + successes) / (alpha + beta + observations)

The prior is what stops a source with two observations looking perfect. Today there is
effectively one news source, so these rows are mechanism with thin data behind them, and the
job says so rather than printing a confident number.

Run: python jobs/audit.py
Writes: Coverage, Calibration, SourceReliability
"""

from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, one, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass


# What each source is expected to produce, and how much a silence there would matter.
# Intervals are generous where a market closes: a price source is not late on a Sunday.
#
#   table, source-matching SQL, label, expected interval in hours, criticality 0-1
WATCHED = (
    (
        "News", "source IS NOT NULL", "Google News RSS",
        36.0, 0.9,
    ),
    (
        "PriceSnapshot", "source = 'Yahoo Finance'", "Yahoo Finance daily closes",
        96.0, 1.0,
    ),
    (
        "PriceSnapshot", "source = 'Pakistan Stock Exchange daily closing file'",
        "PSX daily closing files", 96.0, 0.8,
    ),
    (
        "ProductSignal", "source IS NOT NULL", "product demand signals",
        240.0, 0.6,
    ),
    (
        "MarketplaceItem", "source IS NOT NULL", "Amazon Best Sellers",
        240.0, 0.4,
    ),
)

DATE_COLUMN = {
    "News": '"publishedAt"',
    "PriceSnapshot": "date",
    "ProductSignal": '"periodEnd"',
    "MarketplaceItem": '"periodEnd"',
}

STALE_AT = 1.5
SILENT_AT = 3.0

# The claim each grade makes about how often a directional reading goes the way it pointed.
# Declared, not measured: these are the starting values the calibration loop exists to test,
# and the honest thing is that they are visible and revisable rather than implicit. 0.5 is
# the null — a reading that claims nothing beyond a coin toss.
GRADE_CLAIM = {"high": 0.65, "medium": 0.575, "low": 0.525, "none": 0.5}

# Matured rows needed before a bucket's rate is published at all.
MIN_BUCKET = 10

# Horizons worth calibrating a news-driven reading over. A catalyst resolves in days.
CAL_HORIZONS = (1, 5, 30)


def coverage(cur, today: date) -> None:
    step("coverage: what the system cannot currently see")
    for table, where, label, expected, criticality in WATCHED:
        col = DATE_COLUMN[table]
        got = one(
            cur,
            f'SELECT count(*) AS n, max({col}) AS newest FROM "{table}" WHERE {where}',
        )
        newest = got["newest"]
        if not got["n"] or newest is None:
            gap_hours = expected * 10
            note = "nothing has ever been stored from this source"
        else:
            delta = one(
                cur,
                f"SELECT EXTRACT(EPOCH FROM (now() - %s::timestamp)) / 3600.0 AS h",
                (newest,),
            )
            gap_hours = max(0.0, float(delta["h"]))
            note = None

        ratio = gap_hours / expected if expected > 0 else 0.0
        miss = 1.0 - math.exp(-criticality * ratio)
        status = "healthy" if ratio <= STALE_AT else ("stale" if ratio <= SILENT_AT else "silent")
        if status != "healthy" and note is None:
            note = (
                f"expected something every {expected:.0f}h and the newest is {gap_hours:.0f}h "
                "old, so anything arriving in between has not been collected"
            )

        cur.execute(
            """
            INSERT INTO "Coverage" (source, "expectedIntervalHours", "actualGapHours",
                "gapRatio", criticality, "missRisk", status, rows, newest, note,
                "computedAt")
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            """,
            (
                label, expected, round(gap_hours, 2), round(ratio, 3), criticality,
                round(miss, 4), status, got["n"], newest, note,
            ),
        )
        print(
            f"  {label:34} {status:8} gap {gap_hours:7.1f}h  ratio {ratio:5.2f}  "
            f"miss risk {miss:5.1%}  rows {got['n']:,}"
        )


def calibration(cur) -> None:
    step("calibration: do the grades deserve belief")
    for horizon in CAL_HORIZONS:
        col = f"move{horizon}Pct"
        # A directional reading "hits" when the move went the way the wording pointed. A
        # neutral reading makes no directional claim, so it is excluded rather than scored
        # as wrong: scoring it either way would be inventing a claim it did not make.
        got = rows(
            cur,
            f"""
            SELECT l.confidence::text AS grade, l."{col}" AS move, h.tone::text AS tone
            FROM "SignalLog" l
            JOIN "HumanSignal" h
              ON h."targetRef" = l."targetRef" AND h."periodEnd" = l."issuedOn"
            WHERE l.kind = 'humanSignal' AND l."{col}" IS NOT NULL
              AND h.tone IS NOT NULL AND h.tone <> 'neutral'
            """,
        )
        buckets: dict[str, list[int]] = {}
        for r in got:
            hit = 1 if (float(r["move"]) > 0) == (r["tone"] == "positive") else 0
            buckets.setdefault(r["grade"], []).append(hit)

        if not buckets:
            print(f"  {horizon:>2}d: no matured directional readings yet, nothing to score")
            continue

        for grade, hits in sorted(buckets.items()):
            n = len(hits)
            p = GRADE_CLAIM.get(grade, 0.5)
            if n < MIN_BUCKET:
                cur.execute(
                    """
                    INSERT INTO "Calibration" (population, "horizonDays", bucket, predicted,
                        actual, n, brier, "logLoss", note, "computedAt")
                    VALUES (%s,%s,%s,%s,NULL,%s,NULL,NULL,%s, now())
                    """,
                    (
                        "humanSignal direction", horizon, grade, p, n,
                        f"{n} matured readings, below the {MIN_BUCKET} needed to publish a "
                        "rate, so none is",
                    ),
                )
                print(f"  {horizon:>2}d {grade:7} n={n:<4} below floor, withheld")
                continue

            actual = sum(hits) / n
            brier = sum((p - y) ** 2 for y in hits) / n
            eps = 1e-9
            logloss = -sum(
                y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)) for y in hits
            ) / n
            gap = actual - p
            note = (
                f"claimed {p:.0%}, landed {actual:.0%} over {n}. "
                + (
                    "the claim is too high and should come down"
                    if gap < -0.05
                    else "the claim is too low for what this grade delivered"
                    if gap > 0.05
                    else "the claim holds within five points"
                )
            )
            cur.execute(
                """
                INSERT INTO "Calibration" (population, "horizonDays", bucket, predicted,
                    actual, n, brier, "logLoss", note, "computedAt")
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                """,
                (
                    "humanSignal direction", horizon, grade, p, round(actual, 4), n,
                    round(brier, 4), round(logloss, 4), note,
                ),
            )
            print(
                f"  {horizon:>2}d {grade:7} n={n:<4} claimed {p:.0%} actual {actual:.0%} "
                f"brier {brier:.3f}"
            )


def reliability(cur) -> None:
    step("source reliability")
    for horizon in CAL_HORIZONS:
        col = f"move{horizon}Pct"
        got = rows(
            cur,
            f"""
            SELECT h.source AS source,
                   count(*) AS n,
                   count(*) FILTER (
                       WHERE (l."{col}" > 0) = (h.tone::text = 'positive')
                   ) AS hits
            FROM "SignalLog" l
            JOIN "HumanSignal" h
              ON h."targetRef" = l."targetRef" AND h."periodEnd" = l."issuedOn"
            WHERE l.kind = 'humanSignal' AND l."{col}" IS NOT NULL
              AND h.tone IS NOT NULL AND h.tone <> 'neutral'
            GROUP BY h.source
            """,
        )
        if not got:
            print(f"  {horizon:>2}d: nothing matured, no posterior to update")
            continue
        for r in got:
            alpha, beta = 2.0, 2.0
            n, hits = int(r["n"]), int(r["hits"])
            expected = (alpha + hits) / (alpha + beta + n)
            cur.execute(
                """
                INSERT INTO "SourceReliability" (source, "eventClass", alpha, beta,
                    observations, successes, expected, criterion, "updatedAt")
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (source, "eventClass") DO UPDATE
                SET observations = EXCLUDED.observations, successes = EXCLUDED.successes,
                    expected = EXCLUDED.expected, "updatedAt" = now()
                """,
                (
                    r["source"], f"direction at {horizon}d", alpha, beta, n, hits,
                    round(expected, 4),
                    "the price move went the way the headline wording pointed",
                ),
            )
            print(
                f"  {horizon:>2}d {r['source'][:40]:42} {hits}/{n} -> E[theta] "
                f"{expected:.3f}"
            )


def main() -> None:
    today = date.today()
    conn = db()
    cur = conn.cursor()
    try:
        coverage(cur, today)
        conn.commit()
        calibration(cur)
        conn.commit()
        reliability(cur)
        conn.commit()
        print(
            "\nnothing above is a verdict on the site. Coverage says what was not collected, "
            "calibration says whether the grades held, and both are measurements with their "
            "own sample sizes attached."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
