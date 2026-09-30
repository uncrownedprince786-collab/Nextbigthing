"""Write the short factual lines the site shows.

Every sentence here is built from a number already in the database and names its source and
its as of date. Nothing is predicted and nothing is attributed to a cause. Where the data is
missing the line says so instead of rounding over the gap.

What this rewrite changes over the first version:

  * sentences compare an asset or product to its own peers instead of quoting a bare number
  * where several sources measure the same thing, the text says whether they agree, and says
    so plainly when they do not
  * the grade from jobs/confidence.py is carried onto each line, so a well measured claim and
    a thin one are not presented the same way
  * where a mean is a poor stand in for a typical peer, the line reports the median next to it
  * sentence construction branches on the data instead of following one path, so two
    industries with different stories do not get the same paragraph shape

Product status and demand score are computed exactly as before, so this file does not change
which products are ranked or how they are ordered. It only changes how the result is described.

Run: python jobs/analysis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import (  # noqa: E402
    PRE_AI_END,
    RISING_MONTHS,
    SCORED_SIGNALS,
    SOURCE_LABEL,
    db,
    mean,
    median,
    rows,
    step,
)
from confidence import (  # noqa: E402
    DOMINANT_SHARE_LIMIT,
    latest_counts,
    latest_signals,
    product_confidence,
    summarise,
)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

# The five signals and their source names now live in jobs/nbt.py so that
# jobs/confidence.py and this file cannot drift apart on what counts as a source.

# How far the mean of an industry may sit from its median before the average stops describing
# a typical peer. At 25 points the wording changes to name the spread.
SKEW_LIMIT = 25.0

SIZE_WORD = {"marketCap": "market capitalisation", "fundAssets": "fund size"}


# ------------------------------------------------------------------ helpers


def names_of(items) -> str:
    """Asset or product names in a readable list. Used for Ranking rows and Asset rows."""
    labels = [i["name"] for i in items]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def source_list(items) -> str:
    """Readable names of the demand sources in a list of signal rows.

    Kept separate from names_of on purpose: a Ranking row has a "source" column holding the
    data provider, so one generic helper for both would silently print "yahoo".
    """
    labels = [SOURCE_LABEL.get(i["source"], i["source"]) for i in items]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def count_of(n: int, singular: str, plural: str | None = None) -> str:
    return singular if n == 1 else (plural or singular + "s")



def save(cur, kind, headline, body, source, confidence="none", **keys) -> None:
    cur.execute(
        """
        INSERT INTO "Analysis"
          (kind, "industryId", "assetId", "productId", headline, body, "dataNote",
           confidence, source, "createdAt")
        VALUES (%s::"AnalysisKind",%s,%s,%s,%s,%s,%s,%s::"Confidence",%s, now())
        """,
        (
            kind,
            keys.get("industryId"),
            keys.get("assetId"),
            keys.get("productId"),
            headline,
            body,
            keys.get("dataNote"),
            confidence,
            source,
        ),
    )


def pct_text(value: float) -> str:
    return f"{value:+.0f}%"


def money(value: float, basis: str) -> str:
    unit = SIZE_WORD.get(basis, "size")
    if value >= 1e12:
        return f"${value / 1e12:.2f} trillion {unit}"
    if value >= 1e9:
        return f"${value / 1e9:.1f} billion {unit}"
    if value >= 1e6:
        return f"${value / 1e6:.0f} million {unit}"
    return f"${value:,.0f} {unit}"


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def moved_word(diff: int) -> str:
    if diff > 0:
        return f"{diff} place{'s' if diff != 1 else ''} higher"
    if diff < 0:
        return f"{-diff} place{'s' if -diff != 1 else ''} lower"
    return "the same rank"


def best_grade(grades: list) -> str:
    """Weakest link wins. One thinly measured number in a sentence makes the sentence thin."""
    for grade in ("none", "low", "medium", "high"):
        if grade in grades:
            return grade
    return "none"


GRADE_WORD = {
    "high": "well measured",
    "medium": "partly measured",
    "low": "thinly measured",
    "none": "not measured",
}


def period_end_at(cur, industry_id, basis, on_or_before=None):
    """Newest stored period end, optionally capped, so the pre-AI window is not confused
    with the current one."""
    got = rows(
        cur,
        """
        SELECT max("periodEnd") AS d FROM "Ranking"
        WHERE "industryId" = %s AND basis = %s::"RankingBasis"
          AND (%s::date IS NULL OR "periodEnd" <= %s::date)
        """,
        (industry_id, basis, on_or_before, on_or_before),
    )
    return got[0]["d"] if got else None


def period_end_latest(cur, industry_id, basis):
    got = rows(
        cur,
        """
        SELECT max("periodEnd") AS d FROM "Ranking"
        WHERE "industryId" = %s AND basis = %s::"RankingBasis"
        """,
        (industry_id, basis),
    )
    return got[0]["d"] if got else None


def ranking_table(cur, industry_id, basis, period_end, order="rank"):
    if period_end is None:
        return []
    return rows(
        cur,
        f"""
        SELECT r.rank, r.value, r."periodStart", r."periodEnd", r.note, r."sizeRank",
               r.confidence::text AS grade, r."confidenceNote",
               a.id AS aid, a.name, a.symbol, a."capBasis", a.source, a."assetType"
        FROM "Ranking" r JOIN "Asset" a ON a.id = r."assetId"
        WHERE r."industryId" = %s AND r.basis = %s::"RankingBasis" AND r."periodEnd" = %s
        ORDER BY r.{order}
        """,
        (industry_id, basis, period_end),
    )


# ------------------------------------------------------------------ industries


def industry_shift(cur, ind) -> None:
    now_rows = ranking_table(cur, ind["id"], "sizeNow", period_end_latest(cur, ind["id"], "sizeNow"))
    pre_rows = ranking_table(cur, ind["id"], "size", period_end_at(cur, ind["id"], "size"))
    pre_ret = ranking_table(
        cur, ind["id"], "totalReturn", period_end_at(cur, ind["id"], "totalReturn", PRE_AI_END)
    )
    post_ret = ranking_table(
        cur, ind["id"], "totalReturn", period_end_latest(cur, ind["id"], "totalReturn")
    )
    rising = ranking_table(cur, ind["id"], "rising", period_end_latest(cur, ind["id"], "rising"))

    parts: list[str] = []
    notes: list[str] = []
    grades: list = []
    sources: set[str] = set()

    # --- who leads now, and who led in 2021. Movement, not just position.
    if now_rows and pre_rows:
        before = {r["name"]: r for r in pre_rows}
        lead = now_rows[0]
        sources.add(lead["source"])
        grades += [lead["grade"], pre_rows[0]["grade"]]

        unmatched = [r for r in now_rows if r["name"] not in before]
        if unmatched:
            parts.append(
                f"{lead['name']} is the largest name in the list today. "
                f"{len(unmatched)} of the {len(now_rows)} ranked assets "
                f"{count_of(len(unmatched), 'has')} no stored size for the end of 2021, so the "
                f"two snapshots are not the same set of companies and only the rest can be "
                f"compared."
            )
            notes.append(
                f"{len(unmatched)} of {len(now_rows)} assets carrying a current size have no "
                "stored size for 2021-12-31, so the rank move is only reported for the others."
            )
        old = before.get(lead["name"])
        if old:
            move = old["rank"] - lead["rank"]
            if move > 0:
                parts.append(
                    f"It has climbed {moved_word(move)} than at the end of 2021, when the "
                    f"largest name in the list was {pre_rows[0]['name']}."
                )
            elif move < 0:
                parts.append(
                    f"{pre_rows[0]['name']} led at the end of 2021 and has since given way to "
                    f"{lead['name']}, which has dropped {moved_word(-move)} from where it was."
                )
            else:
                parts.append(
                    f"It also led at the end of 2021, so the name at the top has not changed."
                )

        matched = [r for r in now_rows if r["name"] in before]
        up = [r for r in matched if r["rank"] < before[r["name"]]["rank"]]
        down = [r for r in matched if r["rank"] > before[r["name"]]["rank"]]
        if up and not down:
            parts.append(
                f"Every asset that moved did so upward. {len(up)} of the {len(matched)} "
                f"comparable {count_of(len(matched), 'name')} gained a rank, led by "
                f"{names_of(up)}."
            )
        elif down and not up:
            parts.append(
                f"No asset gained a rank. {len(down)} of the {len(matched)} comparable "
                f"{count_of(len(matched), 'name')} fell, led by {names_of(down)}."
            )
        elif up and down:
            parts.append(
                f"The order churned in both directions. {len(up)} of the {len(matched)} "
                f"comparable {count_of(len(matched), 'name')} moved up, including "
                f"{names_of(up)}. {len(down)} moved down, including {names_of(down)}."
            )
    elif not now_rows:
        notes.append(
            "No size figure is stored for this industry at the current date, so there is no "
            "size ranking. Returns are shown instead."
        )
    elif not pre_rows:
        notes.append(
            "No size figure is stored for this industry at the end of 2021, so the pre-AI size "
            "ranking cannot be built. Returns are shown instead."
        )

    # --- returns, always with the peer context attached
    for label, table in (("from 2019 to 2021", pre_ret), ("since 2021", post_ret)):
        if not table:
            continue
        values = [r["value"] for r in table]
        sources |= {r["source"] for r in table}
        grades += [r["grade"] for r in table]
        avg = mean(values)
        med = median(values)
        best = max(table, key=lambda r: r["value"])
        worst = min(table, key=lambda r: r["value"])

        if abs(avg - med) > SKEW_LIMIT:
            parts.append(
                f"Across the {len(table)} assets measured, the average return {label} is "
                f"{pct_text(avg)} while the median is {pct_text(med)}, a gap of "
                f"{abs(avg - med):.0f} points. {best['name']} at {pct_text(best['value'])} is "
                f"what pulls the two apart, so the average here is not a figure most of the "
                f"list resembles."
            )
            notes.append(
                f"The industry average {label} is {abs(avg - med):.0f} points from the "
                "median, so averages for this industry describe the field loosely."
            )
        else:
            parts.append(
                f"Across the {len(table)} assets measured, the average return {label} is "
                f"{pct_text(avg)} and the median is {pct_text(med)}."
            )

        if best["value"] > 0 > worst["value"]:
            parts.append(
                f"{best['name']} returned {pct_text(best['value'])} {label} while "
                f"{worst['name']} returned {pct_text(worst['value'])}, so the same window "
                f"contains both a gainer and a loser."
            )
        else:
            side = "every one of them rose" if worst["value"] > 0 else "every one of them fell"
            parts.append(
                f"{side.capitalize()} over that window, from {best['name']} at "
                f"{pct_text(best['value'])} to {worst['name']} at {pct_text(worst['value'])}."
            )

    # --- current relative strength spread
    if rising:
        values = [r["value"] for r in rising]
        sources |= {r["source"] for r in rising}
        grades += [r["grade"] for r in rising]
        ahead = len([v for v in values if v > 0])
        parts.append(
            f"Measured against its own {len(rising)} peers over {RISING_MONTHS} months, "
            f"{ahead} gained ground and {len(rising) - ahead} gave some up. {rising[0]['name']} "
            f"leads by {pct_text(rising[0]['value'])} and {rising[-1]['name']} trails by "
            f"{pct_text(rising[-1]['value'])}."
        )
        if rising[0]["grade"] != "high":
            notes.append(
                "The relative strength ranking is "
                f"{GRADE_WORD.get(rising[0]['grade'], rising[0]['grade'])}, so the order is "
                "reported but rests on a weak comparator."
            )
            if rising[0]["confidenceNote"]:
                notes.append(rising[0]["confidenceNote"] + ".")

    if not parts:
        parts.append("Not enough stored data to describe this industry yet.")

    save(
        cur,
        "industryShift",
        f"{ind['name']}: what moved since 2021",
        " ".join(parts),
        ", ".join(sorted(sources)) or "Yahoo Finance, Binance, CoinPaprika",
        best_grade(grades),
        industryId=ind["id"],
        dataNote=" ".join(dict.fromkeys(notes)) if notes else None,
    )


def rising_note(cur, ind) -> None:
    """Spells out the relative strength formula, so the number is not a black box."""
    rising = ranking_table(cur, ind["id"], "rising", period_end_latest(cur, ind["id"], "rising"))
    if not rising:
        return
    top = ", ".join(f"{r['name']} {pct_text(r['value'])}" for r in rising[:3])
    body = (
        f"Each figure is the {RISING_MONTHS} month return minus the average {RISING_MONTHS} "
        f"month return of the other assets in this industry, so a positive number means the "
        f"asset beat its own industry and a negative one means it fell behind. Volume is used "
        f"as a second check where the source publishes it. Top of the list: {top}. The weakest "
        f"relative performer is {rising[-1]['name']} at {pct_text(rising[-1]['value'])}."
    )
    unconfirmed = [r for r in rising[:5] if "unavailable" in (r["note"] or "")]
    note = None
    if unconfirmed:
        note = (
            f"{len(unconfirmed)} of the top 5 have no volume trend stored, so the volume check "
            "could not be applied to them and their confidence is capped below high."
        )
    save(
        cur,
        "forwardLook",
        f"{ind['name']}: strongest {RISING_MONTHS} month movers",
        body,
        "Yahoo Finance, Binance",
        rising[0]["grade"],
        industryId=ind["id"],
        dataNote=note,
    )


def forward_look(cur, ind) -> None:
    """What the current data shows. The last sentence says plainly that it is not a forecast."""
    rising = ranking_table(cur, ind["id"], "rising", period_end_latest(cur, ind["id"], "rising"))
    post = ranking_table(
        cur, ind["id"], "totalReturn", period_end_latest(cur, ind["id"], "totalReturn")
    )
    if not rising:
        return
    news = rows(
        cur,
        """
        SELECT count(*) AS n, max("publishedAt") AS latest FROM "News"
        WHERE "industryId" = %s AND "publishedAt" > now() - interval '14 days'
        """,
        (ind["id"],),
    )[0]

    mid = rising[len(rising) // 2]
    parts = [
        f"The spread between the strongest and weakest {RISING_MONTHS} month performer here is "
        f"{rising[0]['value'] - rising[-1]['value']:.0f} percentage points. "
        f"{rising[0]['name']} is {rising[0]['value'] - mid['value']:.0f} points above the "
        f"middle of the list and {rising[-1]['name']} is {rising[-1]['value']:.0f}."
    ]
    if post:
        below = [r for r in post if r["value"] < 0]
        if below:
            parts.append(
                f"{len(below)} of the {len(post)} measured assets are below their 2021 level "
                f"today, including {', '.join(r['name'] for r in below[:3])}."
            )
        else:
            parts.append(
                f"All {len(post)} measured assets are above their 2021 level today."
            )
    parts.append(
        f"{news['n']} news items mentioning this industry were collected in the last 14 days."
        if news["n"]
        else "No news items for this industry were collected in the last 14 days."
    )
    parts.append(
        "This describes measured direction over a fixed window. It is not a forecast, and no "
        "part of it claims to know what happens next."
    )
    save(
        cur,
        "forwardLook",
        f"{ind['name']}: what the current data shows",
        " ".join(parts),
        "Yahoo Finance, Binance, Google News RSS",
        rising[0]["grade"],
        industryId=ind["id"],
        dataNote="No forecast is stored. The page shows what was measured and stops there.",
    )


# ------------------------------------------------------------------ assets


def asset_notes(cur) -> None:
    step("asset lines")
    for a in rows(
        cur,
        """
        SELECT x.id, x.name, x."capBasis", i.name AS industry
        FROM "Asset" x JOIN "Industry" i ON i.id = x."industryId"
        ORDER BY x.name
        """,
    ):
        by_basis: dict[str, list] = {}
        for r in rows(
            cur,
            """
            SELECT basis, rank, value, "periodStart", "periodEnd", note, "sizeRank",
                   confidence::text AS grade, "confidenceNote"
            FROM "Ranking" WHERE "assetId" = %s
            """,
            (a["id"],),
        ):
            by_basis.setdefault(r["basis"], []).append(r)

        totals = sorted(by_basis.get("totalReturn", []), key=lambda r: r["periodEnd"])
        pre = next((r for r in totals if r["periodEnd"] <= PRE_AI_END), None)
        post = next((r for r in reversed(totals) if r["periodEnd"] > PRE_AI_END), None)
        parts: list[str] = []
        notes: list[str] = []
        grades: list = []

        size_now = by_basis.get("sizeNow", [])
        if size_now:
            now = size_now[0]
            grades.append(now["grade"])
            parts.append(
                f"{money(now['value'], a['capBasis'])}, which ranks {ordinal(now['rank'])} in "
                f"{a['industry']} as of {now['periodEnd']}."
            )
            old = by_basis.get("size", [])
            if old:
                grades.append(old[0]["grade"])
                move = old[0]["rank"] - now["rank"]
                where = (
                    "it holds that position"
                    if move == 0
                    else f"so it sits {moved_word(move)} than it did"
                )
                parts.append(
                    f"At the end of 2021 it ranked {ordinal(old[0]['rank'])} in the same field, "
                    f"so {where}."
                )
                if now["grade"] != "high" and now["confidenceNote"]:
                    notes.append("Size rank: " + now["confidenceNote"] + ".")
        else:
            notes.append(
                "No size figure is stored for this asset, so it has no size rank. Return "
                "figures are still shown."
            )

        if pre and post:
            grades += [pre["grade"], post["grade"]]
            if pre["value"] > 0 > post["value"]:
                parts.append(
                    f"The price returned {pct_text(pre['value'])} from {pre['periodStart']} to "
                    f"{pre['periodEnd']} and then gave back {pct_text(post['value'])} from "
                    f"there to {post['periodEnd']}, so the earlier gain did not carry forward."
                )
            elif pre["value"] < 0 < post["value"]:
                parts.append(
                    f"The price fell {pct_text(pre['value'])} between {pre['periodStart']} and "
                    f"{pre['periodEnd']} and has since recovered {pct_text(post['value'])}, "
                    f"measured to {post['periodEnd']}."
                )
            elif pre["value"] > 0 and post["value"] > 0:
                parts.append(
                    f"The price returned {pct_text(pre['value'])} from {pre['periodStart']} to "
                    f"{pre['periodEnd']} and has added {pct_text(post['value'])} since, "
                    f"measured to {post['periodEnd']}. It rose in both windows."
                )
            else:
                parts.append(
                    f"The price returned {pct_text(pre['value'])} from {pre['periodStart']} to "
                    f"{pre['periodEnd']} and {pct_text(post['value'])} from there to "
                    f"{post['periodEnd']}."
                )
        elif post:
            grades.append(post["grade"])
            parts.append(
                f"Since {post['periodStart']} the price has returned {pct_text(post['value'])}, "
                f"measured to {post['periodEnd']}."
            )
            notes.append(
                "No stored return before 2022, so this asset has no pre-AI window to compare "
                "against and takes no part in the pre-AI ranking."
            )
        elif pre:
            grades.append(pre["grade"])
            parts.append(
                f"Between {pre['periodStart']} and {pre['periodEnd']} the price returned "
                f"{pct_text(pre['value'])}. No later window is stored."
            )
            notes.append("No stored return after 2021 for this asset.")

        rising = by_basis.get("rising", [])
        if rising:
            r = rising[0]
            grades.append(r["grade"])
            peer = rows(
                cur,
                """
                SELECT count(*) AS n, avg(x.value) AS avg_v FROM "Ranking" x
                JOIN "Asset" y ON y.id = x."assetId"
                WHERE x."industryId" = (SELECT "industryId" FROM "Asset" WHERE id = %s)
                  AND x."assetId" != %s AND x.basis = 'rising'::"RankingBasis"
                """,
                (a["id"], a["id"]),
            )[0]
            if peer["n"] and peer["avg_v"] is not None:
                parts.append(
                    f"Against the average of its {int(peer['n'])} peers in {a['industry']}, its "
                    f"{RISING_MONTHS} month return is {pct_text(r['value'])} where theirs "
                    f"averages {pct_text(peer['avg_v'])}, putting it {ordinal(r['rank'])} of "
                    f"{int(peer['n']) + 1} on relative strength."
                )
            if r["grade"] != "high" and r["confidenceNote"]:
                notes.append(r["confidenceNote"] + ".")

        if not parts:
            parts.append("No stored figures for this asset yet.")
        save(
            cur,
            "assetPosition",
            a["name"],
            " ".join(parts),
            "Yahoo Finance, Binance, CoinPaprika",
            best_grade(grades),
            assetId=a["id"],
            dataNote=" ".join(dict.fromkeys(notes)) if notes else None,
        )


# ------------------------------------------------------------------ products


def product_notes(cur) -> None:
    step("product lines")
    all_signals = latest_signals(cur)
    all_counts = latest_counts(cur)
    for p in rows(cur, 'SELECT id, slug, name FROM "Product" ORDER BY slug'):
        sigs = all_signals.get(p["id"], [])
        by_metric = {s["metric"]: s for s in sigs}
        by_metric.update(all_counts.get(p["id"], {}))

        measured: list[dict] = []
        for source, metric, _label in SCORED_SIGNALS:
            row = by_metric.get(metric)
            if row is not None:
                measured.append(row)

        note_bits: list[str] = []
        parts: list[str] = []

        if not measured:
            score = None
            status = "unknown"
            parts.append(
                "No demand source returned a value for this product, so nothing is claimed "
                "about it and it is left out of every ranking on the site."
            )
            note_bits.append(
                "No source answered, so this product is left out of every ranking on the site."
            )
            agree = 0
        else:
            s = summarise(measured, mean([r["value"] for r in measured]))
            score = s["mean"]
            up = [r for r in measured if r["value"] > 0]
            down = [r for r in measured if r["value"] < 0]
            flat = [r for r in measured if r["value"] == 0]
            agree = s["agree"]

            # Status keeps the original rule, so ranking order does not move.
            if len(up) == len(measured) and score >= 5:
                status = "rising"
            elif score >= 10:
                status = "rising"
            elif score > 0 and up and len(measured) >= 2:
                status = "early"
            else:
                status = "flat"

            # measured is every source that answered, including the ones reporting no
            # change at all, so the count in the sentence has to be len(measured). Counting
            # only up and down would claim fewer sources answered than actually did.
            if up and not down:
                if len(up) == 1:
                    # With one source there is nothing to agree with, so say that plainly
                    # instead of describing a single figure as a consensus.
                    parts.append(
                        f"Only {source_list(up)} answered, and it points up. The "
                        f"{pct_text(score)} average is that one source's reading, not a "
                        f"consensus, so the size of the number should not be read as strength "
                        f"of evidence."
                    )
                elif flat:
                    parts.append(
                        f"The {len(up)} sources that moved all point up: {source_list(up)}. "
                        f"With {len(flat)} of {len(measured)} sources reporting no change, the "
                        f"{pct_text(score)} average is a thinner read than the agreement alone "
                        f"suggests."
                    )
                else:
                    parts.append(
                        f"All {len(up)} sources that answered point up: {source_list(up)}. "
                        f"The {pct_text(score)} average is a case where the sources agree with "
                        f"each other, not just a single figure."
                    )
            elif down and not up:
                if len(down) == 1:
                    parts.append(
                        f"Only {source_list(down)} answered, and it points down. The "
                        f"{pct_text(score)} average is that one source's reading, not a "
                        f"consensus, so the size of the number should not be read as strength "
                        f"of evidence."
                    )
                elif flat:
                    parts.append(
                        f"The {len(down)} sources that moved all point down: "
                        f"{source_list(down)}. With {len(flat)} of {len(measured)} sources "
                        f"reporting no change, the {pct_text(score)} average is a thinner read "
                        f"than the agreement alone suggests."
                    )
                else:
                    parts.append(
                        f"All {len(down)} sources that answered point down: {source_list(down)}. "
                        f"They agree, and they point lower."
                    )
            elif up and down:
                parts.append(
                    f"The sources disagree: {source_list(up)} up, {source_list(down)} down. The "
                    f"{pct_text(score)} average of {len(measured)} figures is a weak read for that "
                    f"reason, and it should not be taken as a verdict."
                )
                note_bits.append(
                    "Sources point in opposite directions, which is why the demand score should "
                    "not be read as a single verdict."
                )
            else:
                parts.append(
                    f"No source shows a change either way in this window, so the average is "
                    f"{pct_text(score)}."
                )
            # When every source that answered moved the same way, the sentence above has not
            # named the flat ones yet. Otherwise it has already counted them, and repeating
            # it here just pads the paragraph.
            if flat and (up and down or not up and not down):
                parts.append(f"{source_list(flat)} returned no change at all.")

            for source, metric, label in SCORED_SIGNALS:
                row = by_metric.get(metric)
                if row is not None:
                    parts.append(f"{label}: {pct_text(row['value'])}.")

            raw = by_metric.get("reddit_posts_30d")
            if raw is not None:
                base = by_metric.get("reddit_posts_90d_base")
                base_text = f" against {int(base['value'])} in the 90 before" if base else ""
                parts.append(f"Reddit posts in the last 30 days: {int(raw['value'])}{base_text}.")
            trends = by_metric.get("trends_8w_vs_8w_pct")
            if trends:
                parts.append(f"Measured to the week ending {trends['periodEnd']}.")

            # When one source supplies most of the average, say so rather than letting the
            # total read as five sources weighing in. With a single source that is already
            # said above, and repeating it would pad the paragraph.
            if len(measured) > 1 and s["dominant_share"] > DOMINANT_SHARE_LIMIT:
                who = SOURCE_LABEL.get(s["dominant"]["source"], s["dominant"]["source"])
                parts.append(
                    f"{who} supplies {s['dominant_share'] * 100:.0f}% of that average, so the "
                    f"figure is close to that one source on its own. The median of the "
                    f"{len(measured)} readings is {pct_text(s['median'])}."
                )
                note_bits.append(
                    f"{who} supplies {s['dominant_share'] * 100:.0f}% of the demand average, so "
                    "the score should be read as that source's reading rather than as a "
                    "consensus."
                )
            elif abs(s["mean"] - s["median"]) > SKEW_LIMIT:
                parts.append(
                    f"The median of the {len(measured)} readings is {pct_text(s['median'])}, "
                    f"which is where a typical source sits."
                )

            # How this product sits against the other products on the site.
            peers = rows(
                cur,
                'SELECT count(*) AS n, percentile_cont(0.5) WITHIN GROUP (ORDER BY "demandScore") AS med '
                'FROM "Product" WHERE id != %s AND "demandScore" IS NOT NULL',
                (p["id"],),
            )[0]
            if peers["n"] and peers["med"] is not None:
                gap = score - peers["med"]
                if gap > 1:
                    parts.append(
                        f"That average is {gap:.0f} points above the median of the other "
                        f"{int(peers['n'])} products, so it reads stronger than a typical one."
                    )
                elif gap < -1:
                    parts.append(
                        f"That average is {-gap:.0f} points below the median of the other "
                        f"{int(peers['n'])} products."
                    )
                else:
                    parts.append(
                        f"That average sits at the median of the other {int(peers['n'])} products."
                    )

            answered = len(measured)
            if answered == 1:
                # One canonical disclosure for the single source case, covering both the
                # absence of agreement and the absence of any second reading.
                note_bits.append(
                    "One source answered, so there is no agreement to report and that one "
                    "reading is the whole average."
                )
            else:
                note_bits.append(
                    f"Average of {answered} sources: "
                    + source_list(measured)
                    + f". {agree} point{'s' if agree != 1 else ''} the same way as the average."
                )

        missing = [
            SOURCE_LABEL[src]
            for src, metric, _l in SCORED_SIGNALS
            if metric not in by_metric
        ]
        if missing:
            note_bits.append(
                "Did not answer: "
                + ", ".join(missing)
                + ". A missing source is not a zero, and it is not counted in the average."
            )

        note = " ".join(dict.fromkeys(note_bits)) if note_bits else None
        save(
            cur,
            "productDemand",
            f"{p['name']}: demand read",
            " ".join(parts) if parts else "No demand data stored for this product yet.",
            ", ".join(sorted({s["source"] for s in sigs})) or "none",
            "none",
            productId=p["id"],
            dataNote=note,
        )
        cur.execute(
            'UPDATE "Product" SET status = %s, "demandScore" = %s, "demandNote" = %s, '
            '"computedAt" = now() WHERE id = %s',
            (status, score, note, p["id"]),
        )



# ------------------------------------------------------------------ front page


def site_lead(cur) -> None:
    step("front page")
    top = rows(
        cur,
        """
        SELECT a.name, i.name AS industry, r.value
        FROM "Ranking" r
        JOIN "Asset" a ON a.id = r."assetId"
        JOIN "Industry" i ON i.id = a."industryId"
        WHERE r.basis = 'rising'::"RankingBasis" AND r.rank = 1
        ORDER BY r.value DESC LIMIT 3
        """,
    )
    latest = rows(
        cur,
        'SELECT max("periodEnd") AS d FROM "Ranking" WHERE basis = %s::"RankingBasis"',
        ("rising",),
    )[0]["d"]
    risers = rows(
        cur,
        """
        SELECT name, "demandScore" FROM "Product"
        WHERE status = 'rising' AND "demandScore" IS NOT NULL
        ORDER BY "demandScore" DESC LIMIT 3
        """,
    )
    total_products, thin = rows(
        cur,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE confidence IN ('low','none')) AS thin
        FROM "Product"
        """,
    )[0]
    body = (
        f"Data through {latest}. "
        + (
            "Strongest "
            + f"{RISING_MONTHS} "
            + "month relative performers: "
            + ", ".join(f"{r['name']} in {r['industry']} at {pct_text(r['value'])}" for r in top)
            + ". "
            if top
            else "No relative strength ranking is stored yet. "
        )
        + (
            "Products where every source that answered points up: "
            + ", ".join(f"{r['name']} at {pct_text(r['demandScore'])}" for r in risers)
            + ". "
            if risers
            else "No product currently has every source that answered pointing the same way. "
        )
        + (
            f"{thin} of {total_products} products have a thin or missing demand read and are "
            "labelled as such rather than ranked. "
            if thin
            else f"All {total_products} products have at least a partly measured demand read. "
        )
        + "Every figure names its source and its as of date, and a confidence grade says how "
        "well it is measured. Nothing here is a forecast."
    )
    save(cur, "siteLead", "What the data shows now", body, "all sources", "high")


def main() -> None:
    conn = db()
    with conn, conn.cursor() as cur:
        cur.execute('DELETE FROM "Analysis"')
        step("industries")
        for ind in rows(cur, 'SELECT id, slug, name, summary FROM "Industry" ORDER BY sort'):
            print(f"  {ind['name']}")
            industry_shift(cur, ind)
            rising_note(cur, ind)
            forward_look(cur, ind)
        asset_notes(cur)
        product_notes(cur)

        # Product demand scores and statuses now exist, so the grades can be worked out
        # from them. Doing it here rather than in a separate pass means the prose above and
        # the stored grade come from the same numbers in the same run.
        graded, _ = product_confidence(cur)
        cur.execute(
            """
            UPDATE "Analysis" a SET confidence = p.confidence
            FROM "Product" p WHERE p.id = a."productId" AND a.kind = 'productDemand'::"AnalysisKind"
            """
        )

        site_lead(cur)
        print(f"{graded} products graded")
        for got in rows(
            cur,
            'SELECT kind::text AS k, count(*) AS n, count(*) FILTER (WHERE confidence = %s) AS high '
            'FROM "Analysis" GROUP BY kind ORDER BY kind',
            ("high",),
        ):
            print(f"{got['k']:16} {got['n']:>4}")
    conn.close()


if __name__ == "__main__":
    main()
