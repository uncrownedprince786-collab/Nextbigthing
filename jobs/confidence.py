"""Decide how much weight each stored number can carry.

The rules are deliberately blunt, and every one of them is about the evidence, not about
whether the answer looks good:

  * a ranking measured against few peers is not the same as one measured against many
  * a rising row whose volume check could not run is weaker than one that passed
  * a product read by a single source is never high, no matter how large the number
  * sources that disagree with the average pull the grade down, not up
  * a price measured over a short window is weaker than one measured over a long window

Nothing here forecasts. Confidence describes how well the number is measured, and a High
grade is not a prediction and never appears in the same sentence as a future tense.

Run: python jobs/confidence.py
Writes: Ranking.confidence, Ranking.confidenceNote, Product.confidence,
        Product.sourcesAnswered, Product.sourcesAgree, Product.confidenceNote
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import (  # noqa: E402
    PRODUCT_SOURCES_HIGH,
    PRODUCT_SOURCES_MEDIUM,
    RISING_MONTHS,
    SCORED_SIGNALS,
    SOURCE_LABEL,
    db,
    rows,
    step,
)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

GRADES = ("high", "medium", "low", "none")


def pct_text_short(v: float) -> str:
    return f"{v:+.0f}"


# Raw count rows. Shown on the page so a percentage can be read with its denominator, but
# never scored: a count and the percentage derived from it are one source, not two.
EXTRA_METRICS = ("reddit_posts_30d", "reddit_posts_90d_base")

# How many peers in an industry make a relative ranking worth a full grade.
PEER_HIGH = 8
PEER_MEDIUM = 5

# How far the mean of an industry may sit from its median before the mean stops being a
# fair description of a typical peer. Measured on the stored data: Energy and Mega Cap Tech
# each have a mean about 90 points from the median, driven by one asset.
SKEW_LIMIT = 25.0

# Share of a demand average one source may supply before the average is treated as that
# source's reading rather than five agreeing ones. Measured on the stored data: 6 of the 8
# largest product scores are over half a single source, and Standing desk is 92% Hacker News.
DOMINANT_SHARE_LIMIT = 0.6

# Smallest Reddit base that can support a percentage worth grading on. One post against a
# base of 6 is 17%, so a reading built on a base this low is mostly a count of individual
# posts. The percentage is still published because 2 against 6 really is -67%; what is not
# justified is calling that a high confidence demand read. Measured on the stored data, the
# largest base across all 30 products is 15, so this caps the grade for most of them.
THIN_BASE = 10




def grade_rank(peers: int) -> int:
    """More peers means a more meaningful relative position."""
    if peers >= PEER_HIGH:
        return 2
    if peers >= PEER_MEDIUM:
        return 1
    return 0


def ranking_confidence(cur) -> tuple[int, int]:
    """Grade every Ranking row from its own inputs."""
    step("ranking confidence")

    written = 0
    # How far each industry's mean relative return sits from its own median. This is the
    # comparator the rising rank is actually built on, so a mean that no typical peer
    # resembles can be detected instead of quietly deciding the order.
    rising_values: dict[str, list[float]] = {}
    for r in rows(
        cur,
        """
        SELECT "industryId", value FROM "Ranking"
        WHERE basis = 'rising'::"RankingBasis"
        """,
    ):
        rising_values.setdefault(r["industryId"], []).append(r["value"])
    skew_by_industry: dict[str, float] = {}
    for ind, vals in rising_values.items():
        if len(vals) < 2:
            continue
        skew_by_industry[ind] = abs(statistics.mean(vals) - statistics.median(vals))

    for basis in ("size", "sizeNow", "totalReturn", "rising"):
        got = rows(
            cur,
            """
            SELECT r.id, r."industryId", r.note, r.value, r."periodStart", r."periodEnd",
                   a."assetType", a."capBasis"
            FROM "Ranking" r JOIN "Asset" a ON a.id = r."assetId"
            WHERE r.basis = %s::"RankingBasis"
            """,
            (basis,),
        )
        if not got:
            continue

        # peer count per industry for this basis, taken from the rows themselves
        peers: dict[str, int] = {}
        for r in got:
            peers[r["industryId"]] = peers.get(r["industryId"], 0) + 1

        for r in got:
            n_peers = peers.get(r["industryId"], 1)
            note = r["note"] or ""
            reasons: list[str] = []

            if basis in ("size", "sizeNow"):
                # A size row is a single published figure, so its grade is about the
                # quality of that figure, not about agreement between sources.
                if r["capBasis"] == "none":
                    grade = "none"
                    reasons.append(
                        "this asset has no size figure, so it is ranked on price return only"
                    )
                elif n_peers >= PEER_HIGH:
                    grade = "high"
                    reasons.append(
                        f"a published size figure measured against {n_peers} assets in the industry"
                    )
                else:
                    grade = "medium" if n_peers >= PEER_MEDIUM else "low"
                    reasons.append(
                        f"a published size figure, but only {n_peers} assets in this "
                        "industry carry one, so the rank sits in a small field"
                    )

            elif basis == "totalReturn":
                # Two prices, both stored, window length is the only variable that matters.
                if n_peers >= PEER_HIGH and r["periodStart"]:
                    grade = "high"
                    reasons.append(
                        "two stored closes measured against "
                        f"{n_peers} assets over the full stored window"
                    )
                else:
                    grade = "medium" if n_peers >= PEER_MEDIUM else "low"
                    reasons.append(
                        f"two stored closes, but only {n_peers} assets were measured"
                    )

            else:  # rising
                # This is the relative ranking, so it is graded hardest. It needs enough
                # peers, a volume check that actually ran, and a comparator that a
                # typical peer would recognise.
                skew = skew_by_industry.get(r["industryId"])
                if "volume trend unavailable" in note:
                    if n_peers >= PEER_HIGH:
                        grade = "medium"
                        reasons.append(
                            f"a {RISING_MONTHS} month relative return against "
                            f"{n_peers} peers, but the source published no volume series, "
                            "so the second check could not run"
                        )
                    else:
                        grade = "low"
                        reasons.append(
                            f"a relative return over {n_peers} peers with no volume "
                            "series available to cross check it"
                        )
                elif n_peers >= PEER_HIGH and (skew is None or skew <= SKEW_LIMIT):
                    grade = "high"
                    reasons.append(
                        f"a {RISING_MONTHS} month return measured against the average of "
                        f"{n_peers} peers and confirmed by a rising 60 day average volume"
                    )
                else:
                    if skew is not None and skew > SKEW_LIMIT:
                        # The mean is a poor stand in for a typical peer here, so a rank
                        # built on it is reported but not treated as well evidenced.
                        grade = "medium" if n_peers >= PEER_HIGH else "low"
                        reasons.append(
                            f"a relative return against {n_peers} peers, but the industry "
                            f"average sits {skew:.0f} points from the median, so one or two "
                            "assets pull the figure a typical peer does not resemble"
                        )
                    elif n_peers >= PEER_MEDIUM:
                        grade = "medium"
                        reasons.append(
                            f"a relative return against {n_peers} peers with a volume check "
                            "that ran, in a smaller field than the high grade requires"
                        )
                    else:
                        grade = "low"
                        reasons.append(
                            f"only {n_peers} peers could be measured, so the industry average "
                            "it is compared against rests on very few assets"
                        )


            cur.execute(
                """
                UPDATE "Ranking" SET confidence = %s::"Confidence", "confidenceNote" = %s
                WHERE id = %s
                """,
                (grade, "; ".join(reasons), r["id"]),
            )
            written += cur.rowcount
        print(f"  {basis}: {len(got)} rows")
    return written, 0


def latest_signals(cur) -> dict[str, list[dict]]:
    """Latest stored value per product, source and metric.

    A metric can have more than one stored row: Reddit is collected on more than one day
    and the newer reading is the current one. Reading the first row instead of the newest
    would show a stale figure, so the newest wins every time.

    The five scored metrics come back, plus the raw count rows that let the page show a
    denominator instead of a bare percentage.
    """
    metrics = tuple(m for _s, m, _l in SCORED_SIGNALS) + EXTRA_METRICS
    got = rows(
        cur,
        """
        SELECT DISTINCT ON ("productId", source, metric)
               "productId", source, metric, value, "periodEnd"
        FROM "ProductSignal"
        WHERE metric = ANY(%s::text[])
        ORDER BY "productId", source, metric, "periodEnd" DESC
        """,
        (list(metrics),),
    )
    scored = {m for _s, m, _l in SCORED_SIGNALS}
    grouped: dict[str, list[dict]] = {}
    for s in got:
        # Raw counts are kept so the page can print them. Only the scored metrics take part
        # in agreement, otherwise a count and its own percentage would count as two voices.
        if s["value"] is not None and s["metric"] in scored:
            grouped.setdefault(s["productId"], []).append(s)
    return grouped


def latest_counts(cur) -> dict[str, dict]:
    """Latest raw count rows per product, keyed by metric. Display only, never scored."""
    got = rows(
        cur,
        """
        SELECT DISTINCT ON ("productId", metric) "productId", metric, value
        FROM "ProductSignal"
        WHERE metric = ANY(%s::text[])
        ORDER BY "productId", metric, "periodEnd" DESC
        """,
        (list(EXTRA_METRICS),),
    )
    counts: dict[str, dict] = {}
    for s in got:
        if s["value"] is not None:
            counts.setdefault(s["productId"], {})[s["metric"]] = s
    return counts



def summarise(measured: list[dict], score: float | None) -> dict:
    """Everything the grade and the prose both need, worked out once.

    Both jobs/confidence.py and jobs/analysis.py call this, so the grade a reader sees and
    the sentence they read underneath it cannot disagree.
    """
    answered = len(measured)
    # A source reading exactly zero answered and reported no change. It is not a vote
    # down. Counting it as one used to make "the sources split 3 up and 1 down" appear
    # over a product where the fourth source had simply not moved, and it capped that
    # product's grade at medium for a disagreement that never happened. The three counts
    # are taken independently so they cannot silently sum to something else.
    up = sum(1 for s in measured if s["value"] > 0)
    down = sum(1 for s in measured if s["value"] < 0)
    flat = sum(1 for s in measured if s["value"] == 0)
    values = [s["value"] for s in measured]

    # Which single source is carrying the average, and by how much. Measured on the stored
    # data: 6 of the 8 largest demand scores are over half one source, and Standing desk is
    # 92% Hacker News. A mean like that is one reading wearing the costume of five.
    dominant = None
    dominant_share = 0.0
    if values:
        total = sum(abs(v) for v in values)
        if total:
            top = max(measured, key=lambda s: abs(s["value"]))
            dominant = top
            dominant_share = abs(top["value"]) / total

    return {
        "answered": answered,
        "up": up,
        "down": down,
        "flat": flat,
        "agree": agreement(measured, score)[1],
        "mean": statistics.mean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "dominant": dominant,
        "dominant_share": dominant_share,
        "split": up > 0 and down > 0,
        # One sided means nothing pointed the other way. A source at zero did not point the
        # other way, so it does not break the agreement, but it is not evidence for the
        # direction either, which is why the sentence built from this says how many of the
        # sources actually moved.
        "one_sided": answered > 0 and (up == 0) != (down == 0),
    }


def agreement(measured: list[dict], score: float | None) -> tuple[int, int, int]:
    """How many sources point the same way as the average.

    Returns (answered, agree, up). Agreement is measured against the average, not against
    whichever side happens to be bigger: three sources down and one up is a minority
    position even though three is the larger number.

    A source at exactly zero agrees with neither direction. It answered, so it stays in the
    denominator, but it is not counted as agreeing with a rise or a fall it did not report.
    """
    answered = len(measured)
    up = sum(1 for s in measured if s["value"] > 0)
    down = sum(1 for s in measured if s["value"] < 0)
    if answered == 0 or score is None:
        return answered, 0, up
    if score > 0:
        return answered, up, up
    if score < 0:
        return answered, down, up
    return answered, 0, up


def product_confidence(cur) -> tuple[int, int]:
    """Grade the demand read from how many sources answered and whether they agree."""
    step("product confidence")

    products = rows(
        cur,
        """
        SELECT p.id, p.name, p."demandScore"
        FROM "Product" p ORDER BY p.slug
        """,
    )
    grouped = latest_signals(cur)
    counts = latest_counts(cur)

    written = 0
    for p in products:
        sigs = grouped.get(p["id"], [])
        s = summarise(sigs, p["demandScore"])
        answered, agree, up, down = s["answered"], s["agree"], s["up"], s["down"]
        score = p["demandScore"]
        possible = len(SCORED_SIGNALS)
        dominated = s["dominant_share"] > DOMINANT_SHARE_LIMIT
        # The Reddit percentage is published whenever its base clears the signals floor, but
        # a base under THIN_BASE means the change is a handful of individual posts, so it
        # cannot carry a high grade however many sources happen to agree on direction.
        reddit = next(
            (x for x in sigs if x["metric"] == "reddit_posts_30d_change_pct" and x["value"] is not None),
            None,
        )
        base_row = counts.get(p["id"], {}).get("reddit_posts_90d_base")
        thin_base = (
            reddit is not None
            and base_row is not None
            and base_row["value"] is not None
            and base_row["value"] < THIN_BASE
        )
        # One source owning most of the average is a caveat on the size of the number, not
        # on its direction: three sources can all point up while one supplies nearly all of
        # the magnitude. That still grades on agreement. What does cap the grade is the
        # average and the median landing on opposite sides of zero, because then the total
        # does not describe what a typical source said.
        sign_conflict = (
            s["mean"] is not None
            and s["median"] is not None
            and (s["mean"] > 0) != (s["median"] > 0)
        )

        if answered == 0:
            grade = "none"
            note = "no demand source returned a value, so there is nothing to weigh"
        else:
            ratio = agree / answered
            # A split caps the grade at medium however lopsided it is: three up and one down is
            # a real disagreement, and calling it high would contradict the sentence printed
            # underneath it.
            if (
                answered >= PRODUCT_SOURCES_HIGH
                and ratio >= 0.75
                and not s["split"]
                and not sign_conflict
                and not thin_base
            ):
                grade = "high"
            elif answered >= PRODUCT_SOURCES_MEDIUM and ratio >= 0.5:
                grade = "medium"
            else:
                grade = "low"

            reasons = [f"{answered} of {possible} demand sources returned a value"]
            if s["flat"] and not up and not down:
                reasons.append(
                    f"every source that answered reported no change, so there is a reading "
                    f"here but no direction in it"
                )
            elif s["split"]:
                reasons.append(
                    f"the sources split {up} up and {down} down, so the grade is capped at "
                    "medium however strong the average is"
                )
            elif answered == 1:
                # There is nothing to agree with, so do not describe a lone reading as
                # agreement. It is also the whole of the average.
                reasons.append(
                    "with one source there is no agreement to report, and that source is the "
                    "whole of the average"
                )
            elif s["one_sided"] and s["flat"]:
                # Nothing pointed the other way, but not everything moved, and saying "all
                # of them agree" over a set where some reported no change claims more
                # agreement than there is.
                moved = up or down
                reasons.append(
                    f"the {moved} that moved all point the same way, and the other "
                    f"{s['flat']} reported no change"
                )
            elif s["one_sided"]:
                reasons.append(f"all {answered} point the same way as the average")
            elif ratio >= 0.5:
                reasons.append(
                    f"{agree} of {answered} point the same way, so the read is mixed"
                )
            else:
                reasons.append("no majority points the same way as the average")
            if sign_conflict:
                reasons.append(
                    f"the average is {pct_text_short(s['mean'])} but the median is "
                    f"{pct_text_short(s['median'])}, so the total falls on the other side of zero "
                    "from a typical source and the grade is capped at medium"
                )
            elif dominated and answered > 1:
                name = SOURCE_LABEL.get(s["dominant"]["source"], s["dominant"]["source"])
                reasons.append(
                    f"{name} supplies {s['dominant_share'] * 100:.0f}% of the total, so the size "
                    "of the number is close to that one source alone, though the direction is "
                    "agreed"
                )
            if answered < possible:
                reasons.append("a source that did not answer is not counted as agreement")
            if thin_base:
                base_n = int(base_row["value"])
                reasons.append(
                    f"Reddit rests on a base of {base_n} posts, where a single post is "
                    f"{100 / base_n:.0f}%, so the percentage is published but the grade is "
                    f"capped at medium"
                )
            note = "; ".join(reasons)

        cur.execute(
            """
            UPDATE "Product"
            SET confidence = %s::"Confidence", "sourcesAnswered" = %s,
                "sourcesAgree" = %s, "confidenceNote" = %s
            WHERE id = %s
            """,
            (grade, answered, agree, note, p["id"]),
        )
        written += cur.rowcount
    print(f"  {len(products)} products graded")
    return written, 0



def main() -> None:
    # "rankings" grades only the ranking rows. jobs/run.py calls that between jobs/rank.py and
    # jobs/analysis.py, because the written lines quote the grades. Product grades are not
    # done here in that order: they depend on the demand score that jobs/analysis.py has just
    # recomputed, so analysis.py grades products itself from the same helper functions.
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which not in ("all", "rankings", "products"):
        print(f"unknown target {which}, choose from all, rankings, products")
        raise SystemExit(2)

    conn = db()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        a = b = 0
        if which in ("all", "rankings"):
            a, _ = ranking_confidence(cur)
        if which in ("all", "products"):
            b, _ = product_confidence(cur)
        print()
        if a:
            for got in rows(
                cur,
                'SELECT confidence::text AS g, count(*) AS n FROM "Ranking" GROUP BY confidence ORDER BY n DESC',
            ):
                print(f"ranking   {got['g']:8} {got['n']:>4}")
        if b:
            for got in rows(
                cur,
                'SELECT confidence::text AS g, count(*) AS n FROM "Product" GROUP BY confidence ORDER BY n DESC',
            ):
                print(f"product   {got['g']:8} {got['n']:>4}")
        print(f"\n{a} ranking rows and {b} products graded")
    conn.close()


if __name__ == "__main__":
    main()
