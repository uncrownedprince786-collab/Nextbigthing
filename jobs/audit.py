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

What may be watched is its own rule, and a narrow one. A source earns a row here only once
somebody has confirmed against the live source that it answers, because the panel has exactly
two things to say about an empty table — "this feed is broken" or nothing — and saying the
first about a feed that was never built is the one way this measurement can lie. Watching a
source that answers but whose table is empty is correct and useful: that reads as a job that
did not finish, and is the sentence `ProductRegion` is here to make the panel say.

Watching one venue of a multi-venue chain breaks the same rule from the other end. See
CRYPTO_VENUES: the chain is healthy and its first venue has been dead for a year.

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


# The crypto close chain, as `jobs/prices.py` writes it into `PriceSnapshot.source`. Restated
# here rather than imported because no job in this directory imports another, and audit.py has
# no business pulling in a 1300 line fetcher to read four strings. If a venue is added to
# `prices.CLOSE_VENUES` it has to be added here too, or its rows stop being watched.
#
# Watching the *chain* and not one venue is the whole point, and it is not a style choice. On
# 2026-10-03 the stored crypto closes were:
#
#     Coinbase   20,918 rows, newest 2026-10-02   <- the venue answering today
#     Binance     6,491 rows, newest 2025-10-21   <- blocked from CI since 2026-09-29
#
# A row watching `source = 'Binance'` would therefore read "silent, 8,000 hours" while every
# coin on the site has a close from yesterday, and a row watching Coinbase alone would read
# silent on the first day the chain legitimately falls through to Kraken. Either one is a false
# alarm about a healthy feed, which is the failure this table exists to avoid making. The
# question Coverage can actually answer is "did *any* venue produce a close", so that is the
# question asked.
CRYPTO_VENUES = ("Binance", "Coinbase", "Kraken", "Bitstamp")
CRYPTO_VENUE_SQL = "source IN (" + ", ".join(f"'{v}'" for v in CRYPTO_VENUES) + ")"

# Crypto is the one price source with no weekend. Yahoo and the PSX get 96 hours because a
# Friday close is still the newest thing that exists on a Monday morning and a holiday can
# stretch that; an exchange that trades every hour of every day owes a close every day, so the
# only slack this needs is for a lane that ran late. 48 hours is one missed daily run.
CRYPTO_INTERVAL_HOURS = 48.0

# What each source is expected to produce, and how much a silence there would matter.
# Intervals are generous where a market closes: a price source is not late on a Sunday.
#
# Every entry below was checked against the production database on 2026-10-03 before being
# kept, because a watched source that has never stored a row does not report "this job has not
# run", it reports a broken feed — and a panel that cries wolf about a feed nobody built is
# worse than one that stays quiet. Row counts at that check: News 2,120; Yahoo 152,539;
# PSX 12,487; ProductSignal 339; crypto 27,409 across two venues; MarketplaceItem 270.
#
#   table, source-matching SQL, label, expected interval in hours, criticality 0-1
WATCHED = (
    (
        "News", "source IS NOT NULL", "Google News RSS",
        36.0, 0.9,
    ),
    # One row per market behind the Yahoo fetch (brain.md rule 94). It was one row for US shares, funds,
    # commodities and currency pairs together, so a weekend's handful of FX bars was the "newest day":
    # on 2026-10-11 it held 5 records against a weekday median of 315 and the stocks and commodities
    # pages printed "partial" over a complete Friday. Split, each market is judged on its own rows and
    # its own calendar, and a silence in one does not mark the others silent. The combined row is still
    # written, as the worst of the three, naming which market it is (`yahoo_summary`).
    (
        "PriceSnapshot",
        "source = 'Yahoo Finance' AND \"assetId\" IN (SELECT id FROM \"Asset\" WHERE \"assetType\" IN ('stock', 'etf'))",
        "Yahoo Finance daily closes (US)", 96.0, 1.0,
    ),
    (
        "PriceSnapshot",
        "source = 'Yahoo Finance' AND \"assetId\" IN (SELECT id FROM \"Asset\" WHERE \"assetType\" = 'commodity')",
        "Yahoo Finance daily closes (Commodity)", 96.0, 1.0,
    ),
    (
        "PriceSnapshot",
        "source = 'Yahoo Finance' AND \"assetId\" IN (SELECT id FROM \"Asset\" WHERE \"assetType\" = 'forex')",
        "Yahoo Finance daily closes (FX)", 96.0, 0.8,
    ),
    (
        "PriceSnapshot", "source = 'Pakistan Stock Exchange daily closing file'",
        "PSX daily closing files", 96.0, 0.8,
    ),
    # Crypto had no row here at all, which meant the one price source that had actually gone
    # dark — Binance, blocked from CI on 2026-09-29 — was the only source the freshness panel
    # could not see. Criticality matches Yahoo's: ten of the site's assets are crypto and every
    # reading on them is computed from these closes, so a silence here is not a quiet week.
    (
        "PriceSnapshot", CRYPTO_VENUE_SQL, "crypto daily closes",
        CRYPTO_INTERVAL_HOURS, 1.0,
    ),
    (
        "ProductSignal", "source IS NOT NULL", "product demand signals",
        240.0, 0.6,
    ),
    # The regional breakdown `jobs/geo.py` writes. It passes the same honesty test as the rest,
    # but for a different reason: the *table* was empty on 2026-10-03 while the *source* is
    # live and answering — trends.google.com returned 175 countries, 51 US states and 5 PK
    # provinces to a plain request that morning. So an empty table here is a job that did not
    # finish, not a feed that does not exist, and that is exactly the sentence this row makes
    # the panel say out loud instead of leaving the source off the page entirely.
    #
    # 240 hours because geo only runs in the weekly lane: one skipped week is late, not dead.
    # Criticality 0.5 — below the price feeds because nothing on the site decides anything from
    # a regional breakdown, above nothing because its absence is the whole geography section.
    (
        "ProductRegion", "source IS NOT NULL", "Google Trends regional breakdown",
        240.0, 0.5,
    ),
    # Amazon stays watched because the source is real, which was re-verified rather than
    # assumed: on 2026-10-03 all nine category pages in `jobs/marketplace.py` answered 200
    # with 30 parseable positions each, no CAPTCHA and no sign in, and the job stored 270 rows.
    # Before that run the table held nothing, so this row was reporting a feed that had never
    # produced anything — the exact false alarm described above. It is reporting a real feed now.
    #
    # 240 hours rather than 24 even though the weekly lane runs it: a bestseller chart is a
    # courtesy read of a public page, Amazon blocks a share of those requests outright, and a
    # category list that is a few days old is still a true statement about the day it was read.
    # What this interval is for is noticing that the page stopped answering *at all*.
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
    "ProductRegion": '"periodEnd"',
}

STALE_AT = 1.5
SILENT_AT = 3.0

# Sources whose market keeps a weekday calendar (rule 94). Their partial test counts only Monday to Friday:
# a Saturday or Sunday is an expected non-session, never a thin day, and a weekday holiday holds no rows
# for the market at all, so the newest session it compares is the last real one. Crypto trades every day
# and is not here.
WEEKDAY_SESSIONS = frozenset({
    "Yahoo Finance daily closes (US)",
    "Yahoo Finance daily closes (Commodity)",
    "Yahoo Finance daily closes (FX)",
    "PSX daily closing files",
})
YAHOO_MARKETS = ("US", "Commodity", "FX")
STATUS_ORDER = ("healthy", "partial", "stale", "silent")


def partial_verdict(counts: list[int]) -> tuple[bool, int, float] | None:
    """Whether the newest session is thin against the median of the ones before it: (thin, newest, median),
    or None when there is too little history to judge. `counts` are per session, newest first, and hold only
    days that are sessions for the market -- which is what makes a weekend never thin."""
    if len(counts) < 4:
        return None
    latest_n, prior = counts[0], sorted(counts[1:])
    mid = len(prior) // 2
    med = prior[mid] if len(prior) % 2 else (prior[mid - 1] + prior[mid]) / 2
    if med < PARTIAL_MIN_MEDIAN:
        return None
    return latest_n < PARTIAL_AT * med, latest_n, med


def yahoo_summary(per_market: dict[str, tuple[str, str | None]]) -> tuple[str, str | None]:
    """The combined Yahoo row: the worst market's status, and a note naming every market not healthy."""
    if not per_market:
        return "silent", "no Yahoo market was checked"
    worst = max((s for s, _ in per_market.values()), key=STATUS_ORDER.index)
    hurt = [f"{m}: {s}" + (f" ({n})" if n else "") for m, (s, n) in per_market.items() if s != "healthy"]
    return worst, ("; ".join(hurt) if hurt else None)

# Partial detection. A source that answers with a fraction of what it normally carries is
# the failure mode that looks healthiest: rows arrive, nothing errors, and the numbers quietly
# describe a smaller world. So the newest day's record count is compared with the median of
# the days before it, and a day far below that is reported as partial rather than complete.
#
# The median, not the mean, because one bumper day in the comparison window would otherwise
# make every ordinary day look thin.
PARTIAL_AT = 0.5        # share of the recent median below which a day is called partial
PARTIAL_LOOKBACK = 10   # days of history the median is taken over
PARTIAL_MIN_MEDIAN = 4  # below this the median is too small to judge a shortfall against

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
    yahoo: dict[str, tuple[str, str | None]] = {}
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

        # Partial beats healthy. A day that arrived on time with half its usual content is
        # not a healthy day, and calling it one is how a shrinking feed goes unnoticed. For a market
        # with a weekday calendar only its weekdays are counted (rule 94): a weekend is not a session.
        if status == "healthy" and got["n"] and newest is not None:
            sessions = " AND EXTRACT(ISODOW FROM " + col + "::timestamp) < 6" if label in WEEKDAY_SESSIONS else ""
            daily = rows(
                cur,
                f"""
                SELECT count(*) AS n
                FROM "{table}" WHERE {where}{sessions}
                  AND {col} > (%s::timestamp - (%s * interval '1 day'))
                GROUP BY date_trunc('day', {col}::timestamp)
                ORDER BY date_trunc('day', {col}::timestamp) DESC
                """,
                (newest, PARTIAL_LOOKBACK + 3),
            )
            verdict = partial_verdict([int(d["n"]) for d in daily])
            if verdict and verdict[0]:
                _, latest_n, med = verdict
                status = "partial"
                note = (
                    f"the newest session holds {latest_n} records against a recent median of "
                    f"{med:.0f}. The source answered, so nothing failed, but it carried "
                    "well under its usual amount and anything missing from it is not here"
                )
        if label.startswith("Yahoo Finance daily closes ("):
            yahoo[label[len("Yahoo Finance daily closes ("):-1]] = (status, note)

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
    # The combined Yahoo row, kept for every reader of the old label: the worst market, named.
    status, note = yahoo_summary(yahoo)
    got = one(cur, 'SELECT count(*) AS n, max(date) AS newest FROM "PriceSnapshot" WHERE source = %s', ("Yahoo Finance",))
    cur.execute(
        """
        INSERT INTO "Coverage" (source, "expectedIntervalHours", "actualGapHours",
            "gapRatio", criticality, "missRisk", status, rows, newest, note,
            "computedAt")
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        """,
        ("Yahoo Finance daily closes", 96.0, 0.0, 0.0, 1.0, 0.0, status, got["n"], got["newest"], note),
    )
    print(f"  {'Yahoo Finance daily closes':34} {status:8} (worst of {', '.join(YAHOO_MARKETS)})")


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
