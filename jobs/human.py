"""Read what the public discussion around each asset and product currently looks like.

Three separate readings, deliberately not blended into one number:

  * tone, counted from a fixed word list over headlines
  * attention, this window's item count against the window immediately before it
  * a hype flag, which is only ever attention rising and promotional wording together

Everything here comes out of News rows the site already stored, so this job makes no request
of its own. It can only describe coverage already held, which also means a target whose feed
was rate limited shows fewer items rather than a quieter world, and the note says so.

What this is not
----------------
It is not sentiment analysis. It is a word list run over headlines, and the difference
matters enough to be repeated on every surface that shows it:

  * headlines only, never article bodies
  * no negation handling, so "not a record year" counts the positive word
  * no sarcasm, no irony, no context
  * the list was written for market wording, so it reads a product headline less well

That is why the counts are stored next to the direction and why the direction is withheld
entirely below MIN_ITEMS. A tone computed on three headlines is three headlines.

Run: python jobs/human.py
Writes: HumanSignal, and one SignalLog row per target so accuracy.py can come back later.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import (  # noqa: E402
    db,
    one,
    pct,
    rows,
    step,
)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass


# The measured window, and the equal window before it that attention is compared against.
WINDOW_DAYS = 30

# Below this many headlines no tone direction is published. One article is more than an
# eighth of a reading built on eight, and a direction set by one article is that article.
# The counts are still stored, because a reader can check 3 positive against 1 negative and
# see for themselves that it is four headlines.
MIN_ITEMS = 8

# Below this many items in the prior window, velocity is left null. Dividing by 2 turns one
# extra article into +50%, which is arithmetic rather than a change in attention.
MIN_PRIOR_ITEMS = 5

# How far the net tone has to sit from zero before it is called a direction. A net of one
# headline in eight is 12.5%, so the band keeps a single article from deciding.
NEUTRAL_BAND = 0.15

# How much the item count has to move before attention is called rising or falling. News
# counts are noisy week to week and a feed that returned one page instead of two looks like
# a collapse in interest, so the band is wide on purpose.
ATTENTION_BAND = 25.0

# Share of headlines carrying promotional wording before the hype flag can be raised, and
# it is raised only when attention is rising at the same time. Promotional wording on its
# own is a publisher's house style; promotional wording arriving with a jump in coverage is
# the thing worth naming.
HYPE_SHARE_LIMIT = 0.20

# One publisher supplying more than this share of a window makes the window that
# publisher's coverage rather than a survey of coverage. Disclosed, and caps the grade.
DOMINANT_PUBLISHER_LIMIT = 0.5

# Grade thresholds. Principle 1: several independent sources beat one strong source, so
# publisher spread counts as much as volume here.
HIGH_ITEMS = 25
HIGH_PUBLISHERS = 10
MEDIUM_ITEMS = 15
MEDIUM_PUBLISHERS = 4


# Directional wording. Kept to words whose direction does not flip with context, which is
# why some obvious candidates are absent: "cut" is negative about guidance and positive
# about interest rates, "halt" is negative about a plant and neutral about a trading halt.
# An ambiguous word adds noise to both counts and removes nothing from either.
POSITIVE_TERMS = (
    "beats", "beat", "surges", "surged", "jumps", "jumped", "rallies", "rallied",
    "soars", "soared", "climbs", "climbed", "rises", "rose", "gains", "gained",
    "record high", "all-time high", "upgrade", "upgraded", "outperforms", "outperformed",
    "tops", "topped", "boosts", "boosted", "expands", "expanded", "wins", "won",
    "approved", "approval", "breakthrough", "strong demand", "raises guidance",
)

NEGATIVE_TERMS = (
    "misses", "missed", "plunges", "plunged", "slumps", "slumped", "sinks", "sank",
    "tumbles", "tumbled", "falls", "fell", "drops", "dropped", "slides", "slid",
    "downgrade", "downgraded", "underperforms", "underperformed", "loses", "lost",
    "losses", "warns", "warned", "warning", "recall", "recalled", "lawsuit", "sues",
    "probe", "investigation", "fined", "delays", "delayed", "layoffs", "bankruptcy",
    "weak demand", "cuts guidance", "profit warning",
)

# Promotional and clickbait wording. These are patterns of the article, not claims about the
# asset, which is exactly why they are counted separately from tone: "3 stocks to buy before
# it is too late" is not positive news, it is someone selling a click.
HYPE_TERMS = (
    "skyrocket", "to the moon", "moonshot", "explodes", "exploding", "parabolic",
    "next big", "must buy", "must-buy", "no-brainer", "screaming buy", "hidden gem",
    "get rich", "millionaire", "best stock", "top pick", "should you buy",
    "before it's too late", "before it is too late", "is it too late", "you need to buy",
    "will make you", "life-changing", "can't miss", "cannot miss",
)


def count_terms(text: str, terms: tuple[str, ...]) -> int:
    """How many of the terms appear. Counted once per term, not once per occurrence.

    A headline that repeats a word is still one headline saying it, and counting the
    repetition would let one loud headline outvote several quiet ones.
    """
    low = text.lower()
    return sum(1 for t in terms if t in low)


def classify(title: str) -> str:
    """positive, negative or neutral for one headline.

    A headline carrying both directions is neutral rather than assigned to whichever side
    has more matches. "Revenue beats but guidance misses" is genuinely both, and picking a
    winner on match count would be inventing a judgement the wording does not support.
    """
    up = count_terms(title, POSITIVE_TERMS)
    down = count_terms(title, NEGATIVE_TERMS)
    if up and down:
        return "neutral"
    if up:
        return "positive"
    if down:
        return "negative"
    return "neutral"


def news_window(cur, column: str, target_id: str, start: datetime, end: datetime):
    return rows(
        cur,
        f"""
        SELECT title, publisher FROM "News"
        WHERE "{column}" = %s AND "publishedAt" >= %s AND "publishedAt" < %s
        """,
        (target_id, start, end),
    )


def base_close(cur, asset_id: str, on: date):
    """The latest stored close at or before a date, with the date it is actually from.

    Returned as stored rather than carried forward to the asking date, so the accuracy log
    records which observation a later move was measured from.
    """
    return one(
        cur,
        """
        SELECT date, close FROM "PriceSnapshot"
        WHERE "assetId" = %s AND date <= %s AND close IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """,
        (asset_id, on),
    )


def grade(items: int, publishers: int, top_share: float | None) -> tuple[str, list[str]]:
    """How well evidenced the reading is. About the evidence, never about the direction."""
    notes: list[str] = []
    if items < MIN_ITEMS:
        return "none", [
            f"Only {items} headlines in the window, below the {MIN_ITEMS} needed to read a "
            "direction, so the counts are stored and no tone is published"
        ]

    if items >= HIGH_ITEMS and publishers >= HIGH_PUBLISHERS:
        g = "high"
    elif items >= MEDIUM_ITEMS and publishers >= MEDIUM_PUBLISHERS:
        g = "medium"
    else:
        g = "low"
        notes.append(
            f"{items} headlines from {publishers} publishers, which is thin enough that the "
            "direction rests on a handful of items"
        )

    # Principle 1 again. Volume from one publisher is one source however large it is.
    if top_share is not None and top_share > DOMINANT_PUBLISHER_LIMIT and g == "high":
        g = "medium"
        notes.append(
            f"one publisher supplied {top_share * 100:.0f}% of the headlines, so this "
            "describes that publisher's coverage more than the coverage as a whole"
        )
    elif top_share is not None and top_share > DOMINANT_PUBLISHER_LIMIT:
        notes.append(
            f"one publisher supplied {top_share * 100:.0f}% of the headlines"
        )

    return g, notes


def read_target(cur, column: str, target_id: str, name: str, end: date):
    """Compute one target's reading. Returns None when the target has no coverage at all."""
    end_dt = datetime.combine(end, datetime.min.time())
    start_dt = end_dt - timedelta(days=WINDOW_DAYS)
    prior_dt = start_dt - timedelta(days=WINDOW_DAYS)

    items = news_window(cur, column, target_id, start_dt, end_dt)
    prior = news_window(cur, column, target_id, prior_dt, start_dt)

    if not items and not prior:
        return None

    positive = negative = neutral = 0
    hype_items = 0
    publishers: dict[str, int] = {}
    for r in items:
        title = r["title"] or ""
        kind = classify(title)
        if kind == "positive":
            positive += 1
        elif kind == "negative":
            negative += 1
        else:
            neutral += 1
        if count_terms(title, HYPE_TERMS):
            hype_items += 1
        p = (r["publisher"] or "unknown").strip()
        publishers[p] = publishers.get(p, 0) + 1

    n = len(items)
    top_share = (max(publishers.values()) / n) if n else None

    tone = None
    tone_score = None
    if n >= MIN_ITEMS:
        tone_score = (positive - negative) / n
        if tone_score > NEUTRAL_BAND:
            tone = "positive"
        elif tone_score < -NEUTRAL_BAND:
            tone = "negative"
        else:
            tone = "neutral"

    # Attention. Null rather than zero when the prior window is too thin to divide by: a
    # missing comparison is not a finding of no change.
    velocity = None
    attention = "unknown"
    if len(prior) >= MIN_PRIOR_ITEMS:
        velocity = pct(float(n), float(len(prior)))
        if velocity is not None:
            if velocity >= ATTENTION_BAND:
                attention = "rising"
            elif velocity <= -ATTENTION_BAND:
                attention = "falling"
            else:
                attention = "flat"

    hype_share = (hype_items / n) if n else None
    hype_flag = bool(
        attention == "rising" and hype_share is not None and hype_share >= HYPE_SHARE_LIMIT
    )
    hype_note = None
    if hype_flag:
        hype_note = (
            f"{hype_items} of {n} headlines use promotional wording while coverage is "
            "rising. This describes how the story is being written, not the asset: heavily "
            "promoted and overvalued are different claims and only the first is measured here"
        )
    elif hype_share is not None and hype_share >= HYPE_SHARE_LIMIT:
        hype_note = (
            f"{hype_items} of {n} headlines use promotional wording, but coverage is not "
            "rising, so this reads as house style rather than a surge"
        )

    g, notes = grade(n, len(publishers), top_share)
    if tone is not None and positive and negative and abs(tone_score) <= NEUTRAL_BAND:
        notes.append(
            f"{positive} headlines worded positively against {negative} negatively, which "
            "is a split rather than a direction"
        )

    return {
        "items": n,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "tone": tone,
        "toneScore": tone_score,
        "priorItems": len(prior),
        "velocityPct": velocity,
        "attention": attention,
        "hypeTerms": hype_items,
        "hypeShare": hype_share,
        "hypeFlag": hype_flag,
        "hypeNote": hype_note,
        "confidence": g,
        "confidenceNote": "; ".join(notes).capitalize() if notes else None,
        "publishers": len(publishers),
        "name": name,
    }


def claim_text(r: dict, end: date) -> str:
    """The reading in plain observational English. No future tense, by construction."""
    bits = [
        f"Coverage of {r['name']} in the {WINDOW_DAYS} days to {end.isoformat()}: "
        f"{r['items']} headlines from {r['publishers']} publishers, "
        f"{r['positive']} worded positively and {r['negative']} negatively."
    ]
    if r["priorItems"] >= MIN_PRIOR_ITEMS and r["velocityPct"] is not None:
        bits.append(
            f"That is {r['velocityPct']:+.0f}% against {r['priorItems']} headlines in the "
            f"{WINDOW_DAYS} days before, so attention is {r['attention']}."
        )
    else:
        bits.append(
            f"The {WINDOW_DAYS} days before hold {r['priorItems']} headlines, too few to "
            "compare against, so no change in attention is reported."
        )
    if r["tone"] is None:
        bits.append(
            f"Fewer than {MIN_ITEMS} headlines, so no tone direction is published."
        )
    else:
        bits.append(f"Net wording reads {r['tone']}.")
    if r["hypeFlag"]:
        bits.append("Promotional wording is rising with the coverage.")
    bits.append(
        "Counted from a fixed word list over headlines only, which cannot see negation or "
        "context."
    )
    return " ".join(bits)


def factors_text(r: dict) -> str:
    return (
        f"items={r['items']}; publishers={r['publishers']}; "
        f"positive={r['positive']}; negative={r['negative']}; neutral={r['neutral']}; "
        f"toneScore={'' if r['toneScore'] is None else format(r['toneScore'], '.3f')}; "
        f"priorItems={r['priorItems']}; "
        f"velocityPct={'' if r['velocityPct'] is None else format(r['velocityPct'], '.1f')}; "
        f"attention={r['attention']}; hypeTerms={r['hypeTerms']}; "
        f"hypeFlag={'yes' if r['hypeFlag'] else 'no'}; window={WINDOW_DAYS}d"
    )


def save_signal(cur, column: str, target_id: str, r: dict, end: date) -> None:
    other = "productId" if column == "assetId" else "assetId"
    cur.execute(
        f"""
        INSERT INTO "HumanSignal" ("{column}", "{other}", "targetRef", "periodEnd",
            "windowDays", items, positive, negative, neutral, tone, "toneScore",
            "priorItems", "velocityPct", attention, "hypeTerms", "hypeShare", "hypeFlag",
            "hypeNote", confidence, "confidenceNote", source, "computedAt")
        VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s::"Tone", %s, %s, %s, %s, %s, %s,
                %s, %s, %s::"Confidence", %s, %s, now())
        ON CONFLICT ("targetRef", "periodEnd", "windowDays") DO UPDATE SET
            items = EXCLUDED.items, positive = EXCLUDED.positive,
            negative = EXCLUDED.negative, neutral = EXCLUDED.neutral,
            tone = EXCLUDED.tone, "toneScore" = EXCLUDED."toneScore",
            "priorItems" = EXCLUDED."priorItems", "velocityPct" = EXCLUDED."velocityPct",
            attention = EXCLUDED.attention, "hypeTerms" = EXCLUDED."hypeTerms",
            "hypeShare" = EXCLUDED."hypeShare", "hypeFlag" = EXCLUDED."hypeFlag",
            "hypeNote" = EXCLUDED."hypeNote", confidence = EXCLUDED.confidence,
            "confidenceNote" = EXCLUDED."confidenceNote", "computedAt" = now()
        """,
        (
            target_id, target_id, end, WINDOW_DAYS, r["items"], r["positive"],
            r["negative"], r["neutral"], r["tone"], r["toneScore"], r["priorItems"],
            r["velocityPct"], r["attention"], r["hypeTerms"], r["hypeShare"],
            r["hypeFlag"], r["hypeNote"], r["confidence"], r["confidenceNote"],
            "Google News RSS, as stored in News",
        ),
    )


def save_log(cur, column: str, target_id: str, r: dict, end: date) -> None:
    """Record the reading so accuracy.py can measure what followed it.

    A reading with no published direction is still logged. Whether quiet, split coverage is
    followed by anything is exactly the sort of question this table exists to answer, and
    logging only the confident readings would make the eventual hit rate flattering.
    """
    other = "productId" if column == "assetId" else "assetId"
    base = base_close(cur, target_id, end) if column == "assetId" else None
    status = "open" if base else "unmeasurable"
    cur.execute(
        f"""
        INSERT INTO "SignalLog" (kind, "{column}", "{other}", "targetRef", "issuedOn",
            claim, factors, confidence, "baseDate", "baseClose", status)
        VALUES ('humanSignal', %s, NULL, %s, %s, %s, %s, %s::"Confidence", %s, %s, %s)
        ON CONFLICT (kind, "targetRef", "issuedOn") DO UPDATE SET
            claim = EXCLUDED.claim, factors = EXCLUDED.factors,
            confidence = EXCLUDED.confidence, "baseDate" = EXCLUDED."baseDate",
            "baseClose" = EXCLUDED."baseClose"
        """,
        (
            target_id, target_id, end, claim_text(r, end), factors_text(r),
            r["confidence"], base["date"] if base else None,
            base["close"] if base else None, status,
        ),
    )


def main() -> None:
    end = date.today()
    conn = db()
    with conn, conn.cursor() as cur:
        for column, table, label in (
            ("assetId", "Asset", "assets"),
            ("productId", "Product", "products"),
        ):
            step(f"human signal for {label}")
            targets = rows(cur, f'SELECT id, name FROM "{table}" ORDER BY name')
            written = skipped = flagged = 0
            for t in targets:
                r = read_target(cur, column, t["id"], t["name"], end)
                if r is None:
                    skipped += 1
                    continue
                save_signal(cur, column, t["id"], r, end)
                save_log(cur, column, t["id"], r, end)
                written += 1
                if r["hypeFlag"]:
                    flagged += 1
            print(
                f"  {label}: {written} read, {skipped} with no stored coverage, "
                f"{flagged} hype flagged"
            )


if __name__ == "__main__":
    main()
