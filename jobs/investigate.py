"""When something moves unusually, go and look — then say what was found and what was not.

The catalyst flag answers "did news arrive". This answers the question after it: something
moved, so what evidence bears on it, and what is absent?

The absences are the output, not a gap in it
--------------------------------------------
A large move with nothing published behind it is the ordinary case, not the exceptional one.
A system that prints nothing then has told the reader less than one that says: we looked at
company news, the sector, the calendar, the related names and the volume, and found a sector
move and no company story. So `notFound` is a stored field with content in it, and every
check writes a row whether or not it found anything.

Three statuses, because an absent row would collapse three different answers into one:
`found`, `absent` (checked, genuinely none) and `unavailable` (could not be checked). "No
news" and "the news source did not answer" look the same in a row count and mean opposite
things.

Targeted, never the universe
----------------------------
It reads this asset, its own industry peers, its bounded graph neighbourhood and its own
calendar — all from stored rows, with no network request at all. That is what makes it
affordable: an investigation costs a handful of indexed queries, so it can run on every
material move every night.

Competing hypotheses, and which ones arithmetic can settle
----------------------------------------------------------
Four: market, sector, specific, news. The first three are *measured directly* by
`jobs/attribution.py` — exclusive by construction, summing to the move — so no inference is
performed on them, because the evidence defines them rather than bearing on them and any
Bayesian update would be circular. The fourth is the one that genuinely needs evidence, and
also the one no arithmetic can confirm: a story dated before a move is a sequence.

The prior on each is a **measured base rate** — how often that component has actually led
across every stored attribution row — not a number chosen by hand. The posterior stays null
and every row says why.

Nothing here says an event caused a move. The output is phrased as what the move was shared
with or preceded by, and the test suite checks the generated text for the words brain.md
rule 10 bans.

Run: python jobs/investigate.py
Reads: PriceSnapshot, MoveAttribution, News, NewsLineage, HumanSignal, Event, EventLink,
       GraphRelevance, AssetAnalog, IntradayBar, ProductAssetLink, ProductSignal
Writes: Investigation, InvestigationFinding, InvestigationHypothesis
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

INVESTIGATION = "Targeted read of stored evidence around a measured move"

# What counts as worth investigating. Robust rather than a fixed percentage, because a 3% day
# is ordinary for one of these names and extraordinary for another.
RETURN_HISTORY = 60
ROBUST_Z = 2.5
MOVE_FLOOR = 2.0        # below this the move is not material whatever its z score says
VOLUME_RATIO = 2.0
# How far back a story may be dated and still be part of the sequence around today's move.
NEWS_WINDOW_DAYS = 3
CALENDAR_DAYS = 10
ANALOG_MIN = 8
# Investigations per run. Bounded so a volatile day cannot turn one job into hundreds of
# queries; the most unusual moves are investigated first.
MAX_INVESTIGATIONS = 40

HYPOTHESES = {
    "market": "The move is what everything quoted in its exchange group did.",
    "sector": "The move is what its own industry did beyond the group.",
    "specific": "Neither the group nor the industry accounts for it, so it is particular to this asset.",
    "news": "A dated story or scheduled item preceded the move.",
}


def robust_z(value: float, history: list[float]) -> float | None:
    """(value - median) / (1.4826 * MAD), with a floor so a flat history cannot divide by zero.

    The same construction jobs/human.py uses on news rates, for the same reason: a mean and a
    standard deviation over daily returns are dragged around by the single largest day in the
    window, which is exactly the day being tested.
    """
    if len(history) < 20:
        return None
    mid = median(history)
    if mid is None:
        return None
    mad = median([abs(x - mid) for x in history])
    scale = 1.4826 * (mad or 0.0)
    if scale <= 0:
        # A history with no dispersion at all. Any departure is unusual, but dividing by zero
        # would make every quiet asset a permanent finding, so the scale floors at a tenth of
        # a percent and the score is honest about being large.
        scale = 0.1
    return (value - mid) / scale


def candidates(cur, today: date) -> list[dict]:
    """Assets whose latest stored day is unusual for them, most unusual first.

    One query over a window function rather than one query per asset: 160 round trips to
    compute a z score that only needs each asset's own last sixty returns is the kind of cost
    that turns a nightly job into a queue.
    """
    got = rows(
        cur,
        """
        WITH rets AS (
            SELECT p."assetId", p.date, p.close, p.volume,
                   (p.close / nullif(lag(p.close) OVER w, 0) - 1) * 100 AS pct,
                   avg(p.volume) OVER (PARTITION BY p."assetId" ORDER BY p.date
                                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avgvol
            FROM "PriceSnapshot" p
            WHERE p.close IS NOT NULL
            WINDOW w AS (PARTITION BY p."assetId" ORDER BY p.date)
        ),
        latest AS (
            SELECT "assetId", max(date) AS d FROM rets WHERE pct IS NOT NULL GROUP BY "assetId"
        )
        SELECT a.id, a.symbol, a.name, a."industryId", r.date, r.pct, r.volume, r.avgvol,
               (SELECT array_agg(h.pct) FROM (
                    SELECT pct FROM rets x
                    WHERE x."assetId" = a.id AND x.pct IS NOT NULL AND x.date < r.date
                    ORDER BY x.date DESC LIMIT %s
               ) h) AS history
        FROM latest l
        JOIN rets r ON r."assetId" = l."assetId" AND r.date = l.d
        JOIN "Asset" a ON a.id = l."assetId"
        """,
        (RETURN_HISTORY,),
    )

    flagged = {
        r["assetId"]
        for r in rows(
            cur,
            """
            SELECT "assetId" FROM "HumanSignal"
            WHERE catalyst = true AND "assetId" IS NOT NULL
              AND "periodEnd" = (SELECT max("periodEnd") FROM "HumanSignal")
            """,
        )
    }

    out = []
    for r in got:
        pct = float(r["pct"]) if r["pct"] is not None else None
        hist = [float(x) for x in (r["history"] or []) if x is not None]
        z = robust_z(pct, hist) if pct is not None else None
        vol_ratio = None
        if r["volume"] and r["avgvol"] and float(r["avgvol"]) > 0:
            vol_ratio = float(r["volume"]) / float(r["avgvol"])

        trigger = detail = None
        if pct is not None and z is not None and abs(z) >= ROBUST_Z and abs(pct) >= MOVE_FLOOR:
            trigger = "move"
            detail = (
                f"its latest day moved {pct:+.1f}%, which is {abs(z):.1f} times its own "
                f"typical daily spread over the last {len(hist)} sessions"
            )
        elif vol_ratio is not None and vol_ratio >= VOLUME_RATIO:
            trigger = "volume"
            detail = (
                f"it traded {vol_ratio:.1f} times its own 20 day average volume, with a price "
                f"change of {pct:+.1f}%" if pct is not None else
                f"it traded {vol_ratio:.1f} times its own 20 day average volume"
            )
        elif r["id"] in flagged:
            trigger = "catalyst"
            detail = (
                "news started arriving on it at several times its own baseline rate, which is "
                "worth looking at whether or not the price moved"
            )
        if not trigger:
            continue
        out.append({**r, "pct": pct, "z": z, "vol_ratio": vol_ratio,
                    "trigger": trigger, "detail": detail})

    out.sort(key=lambda r: -(abs(r["z"]) if r["z"] is not None else 0.0))
    return out[:MAX_INVESTIGATIONS]


def base_rates(cur) -> dict[str, float]:
    """How often each component has actually led, across every stored attribution row.

    A measured base rate, which is what makes it usable as a prior at all. A prior chosen by
    hand here would be the manufactured number this project exists not to produce.
    """
    got = rows(
        cur,
        'SELECT leader, count(*) AS n FROM "MoveAttribution" WHERE leader IS NOT NULL '
        "GROUP BY leader",
    )
    total = sum(int(r["n"]) for r in got)
    if not total:
        return {}
    return {r["leader"]: int(r["n"]) / total for r in got}


def news_around(cur, asset_id: str, when: date) -> list[dict]:
    """Stories dated in the window around the move, counted as stories and not as copies.

    Grouped by `lineageId`, because twenty outlets carrying one wire report is one piece of
    information. The earliest item in each cluster carries the time, so the sequence question
    is asked against when the story first appeared rather than when the last outlet rewrote it.
    """
    return rows(
        cur,
        """
        SELECT coalesce(n."lineageId", n.id) AS story,
               min(n."publishedAt") AS first_seen,
               count(*) AS copies,
               (array_agg(n.title ORDER BY n."publishedAt"))[1] AS title,
               (array_agg(n.publisher ORDER BY n."publishedAt"))[1] AS publisher
        FROM "News" n
        WHERE n."assetId" = %s AND n."publishedAt" >= %s AND n."publishedAt" < %s
        GROUP BY story
        ORDER BY first_seen DESC
        """,
        (asset_id, when - timedelta(days=NEWS_WINDOW_DAYS), when + timedelta(days=1)),
    )


def intraday_timing(cur, asset_id: str, when: date) -> dict | None:
    """Which part of the session carried the move, from stored five minute bars.

    Timing evidence, and labelled as nothing more. Knowing a move happened in the first ten
    minutes rather than spread through the afternoon narrows what could be behind it; it does
    not say what was.
    """
    bars = rows(
        cur,
        """
        SELECT ts, open, high, low, close, volume FROM "IntradayBar"
        WHERE "assetId" = %s AND interval = 5 AND "sessionDate" = %s AND phase = 'regular'
        ORDER BY ts
        """,
        (asset_id, when),
    )
    if len(bars) < 6:
        return None
    first = float(bars[0]["open"])
    biggest = None
    for i in range(1, len(bars)):
        move = abs(float(bars[i]["close"]) / float(bars[i - 1]["close"]) - 1.0) * 100.0
        if biggest is None or move > biggest["move"]:
            biggest = {"move": move, "ts": bars[i]["ts"], "index": i}
    span = len(bars)
    where = "the first half hour" if biggest["index"] <= 6 else (
        "the last half hour" if biggest["index"] >= span - 6 else "the middle of the session"
    )
    return {
        "bars": span,
        "open": first,
        "biggest": biggest["move"],
        "at": biggest["ts"],
        "where": where,
    }


def investigate_one(cur, a: dict, rates: dict[str, float], today: date) -> dict:
    """Run every check for one asset and return the findings, hypotheses and the wording.

    Pure-ish: it reads, it does not write. The writing happens in main so that one asset
    failing a query cannot leave a half-written investigation behind.
    """
    when = a["date"]
    findings: list[dict] = []
    found_bits: list[str] = []
    absent_bits: list[str] = []

    def record(kind, status, detail, source=None, observed=None):
        findings.append({"kind": kind, "status": status, "detail": detail,
                         "sourceName": source, "observedAt": observed})
        if status == "found":
            found_bits.append(detail)
        elif status == "absent":
            absent_bits.append(detail)

    # --- what changed
    record(
        "volume",
        "found" if a["vol_ratio"] is not None else "unavailable",
        (
            f"it traded {a['vol_ratio']:.1f} times its own 20 day average volume"
            if a["vol_ratio"] is not None
            else "no volume is stored for the latest day, so activity could not be checked"
        ),
        "stored daily bars",
    )

    # --- company news, as stories rather than copies
    stories = news_around(cur, a["id"], when)
    if stories:
        top = stories[0]
        record(
            "news", "found",
            (
                f"{len(stories)} distinct "
                + ("story" if len(stories) == 1 else "stories")
                + f" within {NEWS_WINDOW_DAYS} days, the most recent being "
                + f"“{top['title'][:110]}”"
                + (f" carried by {top['copies']} outlets" if int(top["copies"]) > 1 else "")
            ),
            top["publisher"], top["first_seen"],
        )
    else:
        record(
            "news", "absent",
            f"no story is stored for it within {NEWS_WINDOW_DAYS} days of the move",
            "stored news items",
        )

    # --- the measured decomposition
    attrib = one(
        cur,
        """
        SELECT "totalPct", "marketPct", "sectorPct", "specificPct", leader, "leaderMargin",
               peers, "groupSize", headline
        FROM "MoveAttribution" WHERE "assetId" = %s ORDER BY "periodEnd" DESC LIMIT 1
        """,
        (a["id"],),
    )
    if attrib:
        record(
            "attribution", "found", attrib["headline"],
            "measured medians over stored closes",
        )
        if attrib["sectorPct"] is not None:
            same_way = (
                attrib["sectorPct"] > 0 and (a["pct"] or 0) > 0
            ) or (attrib["sectorPct"] < 0 and (a["pct"] or 0) < 0)
            record(
                "peers", "found",
                (
                    f"its own industry moved {float(attrib['sectorPct']):+.1f} points beyond "
                    f"the group over the window, {'the same way' if same_way else 'the other way'}"
                ),
                f"{attrib['peers']} industry peers",
            )
        else:
            record(
                "peers", "unavailable",
                "fewer than three industry peers have the history to take a median from, so "
                "the industry and asset specific parts could not be separated",
                "stored closes",
            )
    else:
        record(
            "attribution", "unavailable",
            "no move decomposition is stored for it yet, so the market and industry shares "
            "could not be read",
            "jobs/attribution.py",
        )

    # --- the calendar
    soon = one(
        cur,
        """
        SELECT e.name, e.date, e.category FROM "Event" e
        JOIN "EventLink" l ON l."eventId" = e.id
        WHERE l."assetId" = %s AND e.scheduled = true
          AND e.date BETWEEN %s AND %s
        ORDER BY abs(e.date - %s::date) LIMIT 1
        """,
        (a["id"], when - timedelta(days=CALENDAR_DAYS), when + timedelta(days=CALENDAR_DAYS),
         when),
    )
    if soon:
        days = (soon["date"] - when).days
        record(
            "calendar", "found",
            (
                f"{soon['name']} is dated {abs(days)} days "
                + ("after" if days > 0 else "before" if days < 0 else "on")
                + " the move"
            ),
            "stored scheduled dates", None,
        )
    else:
        record(
            "calendar", "absent",
            f"no scheduled date for it falls within {CALENDAR_DAYS} days of the move",
            "stored scheduled dates",
        )

    # --- the bounded graph neighbourhood
    near = rows(
        cur,
        """
        SELECT path, score, hops, "edgeKind" FROM "GraphRelevance"
        WHERE "assetId" = %s AND "periodEnd" = (
            SELECT max("periodEnd") FROM "GraphRelevance"
        ) ORDER BY score DESC LIMIT 2
        """,
        (a["id"],),
    )
    if near:
        record(
            "graph", "found",
            f"it sits {near[0]['hops']} step away from something with a catalyst flagged: "
            + near[0]["path"],
            "stored relationship rows",
        )
    else:
        record(
            "graph", "absent",
            "nothing within two recorded relationships of it has a catalyst flagged",
            "stored relationship rows",
        )

    # --- what has followed days like this before
    analog = one(
        cur,
        """
        SELECT matches, positive, "medianPct", "minPct", "maxPct" FROM "AssetAnalog"
        WHERE "assetId" = %s AND "horizonDays" = 5 ORDER BY "periodEnd" DESC LIMIT 1
        """,
        (a["id"],),
    )
    if analog and analog["matches"] and int(analog["matches"]) >= ANALOG_MIN:
        share = int(analog["positive"]) / int(analog["matches"])
        record(
            "analog", "found",
            (
                f"{analog['positive']} of {analog['matches']} similar past days rose over the "
                f"next five sessions, about {share:.0%}, with a median of "
                f"{float(analog['medianPct']):+.1f}%"
            ),
            "stored daily history",
        )
    else:
        record(
            "analog", "absent",
            f"fewer than {ANALOG_MIN} comparable past days are stored, so there is no base "
            "rate to read against",
            "stored daily history",
        )

    # --- when in the session it happened
    timing = intraday_timing(cur, a["id"], when)
    if timing:
        record(
            "intraday", "found",
            (
                f"the largest five minute change of the session, {timing['biggest']:.1f}%, "
                f"came in {timing['where']}"
            ),
            "stored five minute bars", timing["at"],
        )
    else:
        record(
            "intraday", "unavailable",
            "no intraday bars are stored for that session, so the timing within the day could "
            "not be checked",
            "stored five minute bars",
        )

    # --- linked product demand
    prod = rows(
        cur,
        """
        SELECT p.name, l.relation FROM "ProductAssetLink" l
        JOIN "Product" p ON p.id = l."productId"
        WHERE l."assetId" = %s LIMIT 2
        """,
        (a["id"],),
    )
    if prod:
        record(
            "product", "found",
            f"it is linked to {prod[0]['name']}: {prod[0]['relation']}",
            "stored product links",
        )
    else:
        record("product", "absent", "no product is linked to it", "stored product links")

    # --- hypotheses
    hypotheses = []
    parts = {
        "market": attrib["marketPct"] if attrib else None,
        "sector": attrib["sectorPct"] if attrib else None,
        "specific": attrib["specificPct"] if attrib else None,
    }
    for label in ("market", "sector", "specific"):
        mag = float(parts[label]) if parts[label] is not None else None
        supporting, contradicting = [], []
        if mag is not None:
            supporting.append(f"the measured share is {mag:+.1f} points of the move")
            if attrib and attrib["leader"] == label:
                supporting.append(
                    f"it is the largest of the three, by {float(attrib['leaderMargin']):.2f} "
                    "times the next"
                    if attrib["leaderMargin"] else "it is the largest of the three"
                )
            else:
                contradicting.append("another component is larger")
        else:
            contradicting.append(
                "the share could not be measured, because too few industry peers have history"
            )
        hypotheses.append({
            "label": label,
            "statement": HYPOTHESES[label],
            "priorBase": rates.get(label),
            "priorNote": (
                f"{rates[label]:.0%} of every stored move decomposition has been led by this "
                "component. A measured base rate across the population, not a declared prior"
            ) if label in rates else
            "no decomposition has named a leader yet, so there is no base rate to read",
            "magnitude": mag,
            "supporting": "; ".join(supporting) or "none",
            "contradicting": "; ".join(contradicting) or "none",
            "posterior": None,
            "posteriorNote": (
                "No posterior is computed. For this hypothesis the evidence is the measurement "
                "itself, so a Bayesian update would be circular rather than informative: the "
                "share is not evidence about the share"
            ),
        })

    news_support, news_against = [], []
    if stories:
        earliest = stories[-1]["first_seen"]
        news_support.append(
            f"{len(stories)} distinct stories are dated within {NEWS_WINDOW_DAYS} days, the "
            f"earliest on {earliest:%Y-%m-%d %H:%M}"
        )
        if timing:
            news_support.append(
                f"the session's largest five minute change came in {timing['where']}"
            )
        news_against.append(
            "a story dated before a move is a sequence and not a cause, and nothing stored "
            "here can separate the two"
        )
    else:
        news_against.append(
            f"no story is stored within {NEWS_WINDOW_DAYS} days, so there is nothing to place "
            "before the move"
        )
    if soon:
        news_support.append(f"a scheduled item, {soon['name']}, is dated nearby")
    hypotheses.append({
        "label": "news",
        "statement": HYPOTHESES["news"],
        "priorBase": None,
        "priorNote": (
            "no base rate exists for this one: measuring how often a story precedes a move "
            "would need matured outcome rows, and none have matured"
        ),
        "magnitude": None,
        "supporting": "; ".join(news_support) or "none",
        "contradicting": "; ".join(news_against) or "none",
        "posterior": None,
        "posteriorNote": (
            "No posterior is computed. A likelihood ratio needs a measured P(evidence | "
            "hypothesis), and the outcome log has no matured rows to measure it from"
        ),
    })

    # --- the wording. Shared-with and preceded-by only; never a cause.
    leading = attrib["leader"] if attrib else None
    move_words = (
        f"moved {a['pct']:+.1f}% on its latest stored day" if a["pct"] is not None
        else "was flagged without a measured price change"
    )
    headline = f"{a['name']} {move_words}, which is unusual for it."
    if a["trigger"] == "volume":
        headline = (
            f"{a['name']} traded {a['vol_ratio']:.1f} times its usual volume on its latest "
            "stored day."
        )
    elif a["trigger"] == "catalyst":
        headline = f"News started arriving on {a['name']} faster than its own baseline."

    if leading == "specific" and not stories:
        points = (
            "The move is not explained by its exchange group or its own industry, and no "
            "story is stored for it. On the available evidence it is unexplained."
        )
    elif leading == "specific" and stories:
        points = (
            "The move is mostly particular to this asset rather than shared with its group or "
            f"its industry, and {len(stories)} stored "
            + ("story is" if len(stories) == 1 else "stories are")
            + " dated just before or around it."
        )
    elif leading in ("market", "sector"):
        points = (
            "Most of the move is shared with "
            + ("everything in its exchange group" if leading == "market"
               else "its own industry")
            + ", so it is better read as a move in that group than as something about this "
            "asset."
        )
    else:
        points = (
            "No single component of the move is far enough ahead of the others to lead, so "
            "the evidence does not point one way."
        )

    unconfirmed_bits = [
        "nothing here establishes that any story or date moved the price; the system measures "
        "what moved together and what was dated nearby"
    ]
    if stories:
        unconfirmed_bits.append(
            "whether the stored stories reached the market before or after the move cannot be "
            "settled from a publication timestamp alone"
        )
    if not attrib or attrib["sectorPct"] is None:
        unconfirmed_bits.append(
            "the industry share of the move is unmeasured, so part of it is unattributed"
        )

    grade = "none"
    strong = sum(1 for f in findings if f["status"] == "found")
    if strong >= 6:
        grade = "high"
    elif strong >= 4:
        grade = "medium"
    elif strong >= 2:
        grade = "low"

    return {
        "findings": findings,
        "hypotheses": hypotheses,
        "headline": headline,
        "found": " | ".join(found_bits) or "nothing was found by any check",
        "notFound": " | ".join(absent_bits) or "every check found something",
        "pointsToward": points,
        "unconfirmed": " | ".join(unconfirmed_bits),
        "leading": leading,
        "confidence": grade,
        "confidenceNote": (
            f"{strong} of {len(findings)} checks found evidence; the rest were absent or could "
            "not be read. The grade describes how much was found, never how certain the "
            "explanation is"
        ),
    }


def main() -> None:
    today = date.today()
    conn = db()
    cur = conn.cursor()
    try:
        step("find the assets whose latest day is unusual for them")
        picked = candidates(cur, today)
        print(f"  {len(picked)} to investigate, most unusual first")
        if not picked:
            print(
                "  nothing moved unusually against its own history. That is the ordinary "
                "state and the right answer on most days."
            )
            return

        rates = base_rates(cur)
        if rates:
            print(
                "  measured base rates for the priors: "
                + ", ".join(f"{k} {v:.0%}" for k, v in sorted(rates.items()))
            )
        else:
            print("  no attribution leader is stored yet, so the hypotheses carry no base rate")

        triggers: dict[str, int] = {}
        leading: dict[str, int] = {}
        unexplained = 0

        for a in picked:
            result = investigate_one(cur, a, rates, today)
            cur.execute(
                """
                INSERT INTO "Investigation" ("assetId", "periodEnd", trigger, "triggerDetail",
                    "movePct", "robustZ", "volumeRatio", headline, found, "notFound",
                    "pointsToward", unconfirmed, "leading", confidence, "confidenceNote",
                    source, "computedAt")
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::"Confidence",%s,%s,now())
                ON CONFLICT ("assetId", "periodEnd") DO UPDATE SET
                    trigger = EXCLUDED.trigger, "triggerDetail" = EXCLUDED."triggerDetail",
                    "movePct" = EXCLUDED."movePct", "robustZ" = EXCLUDED."robustZ",
                    "volumeRatio" = EXCLUDED."volumeRatio", headline = EXCLUDED.headline,
                    found = EXCLUDED.found, "notFound" = EXCLUDED."notFound",
                    "pointsToward" = EXCLUDED."pointsToward",
                    unconfirmed = EXCLUDED.unconfirmed,
                    -- Quoted: LEADING is a reserved word in Postgres, used by TRIM. Unquoted
                    -- it is a syntax error, which is how this was found in production.
                    "leading" = EXCLUDED."leading",
                    confidence = EXCLUDED.confidence,
                    "confidenceNote" = EXCLUDED."confidenceNote", "computedAt" = now()
                RETURNING id
                """,
                (
                    # The day the move happened, which `investigate_one` has used as `when`
                    # for every check since it was written. The row said `today` instead, so a
                    # run from a UTC+5 host before the US close dated 283 investigations to
                    # 2026-10-08 -- a day with no stored close in it -- while every finding
                    # inside them was measured against 10-07. The file's own claim, recorded in
                    # tests/test_brain.py, is that it "investigates a move on the day it is
                    # seen"; now it does.
                    a["id"], a["date"] or today, a["trigger"], a["detail"], a["pct"], a["z"],
                    a["vol_ratio"], result["headline"], result["found"], result["notFound"],
                    result["pointsToward"], result["unconfirmed"], result["leading"],
                    result["confidence"], result["confidenceNote"], INVESTIGATION,
                ),
            )
            inv_id = cur.fetchone()["id"]

            for f in result["findings"]:
                cur.execute(
                    """
                    INSERT INTO "InvestigationFinding" ("investigationId", kind, status,
                        detail, "sourceName", "observedAt")
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT ("investigationId", kind) DO UPDATE SET
                        status = EXCLUDED.status, detail = EXCLUDED.detail,
                        "sourceName" = EXCLUDED."sourceName",
                        "observedAt" = EXCLUDED."observedAt"
                    """,
                    (inv_id, f["kind"], f["status"], f["detail"], f["sourceName"],
                     f["observedAt"]),
                )
            for h in result["hypotheses"]:
                cur.execute(
                    """
                    INSERT INTO "InvestigationHypothesis" ("investigationId", label, statement,
                        "priorBase", "priorNote", magnitude, supporting, contradicting,
                        posterior, "posteriorNote")
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT ("investigationId", label) DO UPDATE SET
                        statement = EXCLUDED.statement, "priorBase" = EXCLUDED."priorBase",
                        "priorNote" = EXCLUDED."priorNote", magnitude = EXCLUDED.magnitude,
                        supporting = EXCLUDED.supporting,
                        contradicting = EXCLUDED.contradicting,
                        posterior = EXCLUDED.posterior,
                        "posteriorNote" = EXCLUDED."posteriorNote"
                    """,
                    (inv_id, h["label"], h["statement"], h["priorBase"], h["priorNote"],
                     h["magnitude"], h["supporting"], h["contradicting"], h["posterior"],
                     h["posteriorNote"]),
                )
            triggers[a["trigger"]] = triggers.get(a["trigger"], 0) + 1
            if result["leading"]:
                leading[result["leading"]] = leading.get(result["leading"], 0) + 1
            if "unexplained" in result["pointsToward"]:
                unexplained += 1
            conn.commit()

        for k, n in sorted(triggers.items()):
            print(f"  triggered by {k:<9} {n}")
        for k, n in sorted(leading.items()):
            print(f"  led by {k:<14} {n}")
        print(f"  {unexplained} moves are unexplained by the available evidence, and say so")
        print(
            "  no posterior is stored on any hypothesis. The reason is on every row: for the "
            "measured components an update would be circular, and for the news hypothesis "
            "there is no matured outcome to measure a likelihood from."
        )
        print(
            "  nothing here says an event caused a move. It reports what moved together and "
            "what was dated nearby."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
