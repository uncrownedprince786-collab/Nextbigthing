"""Write the short factual lines the site shows.

Every sentence here is built from a number already in the database and names the source
and the as of date. Nothing is predicted and nothing is attributed to a cause. Where the
data is missing the line says so instead of rounding over the gap.

Run: python jobs/analysis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import PRE_AI_END, db, mean, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE401
    pass

SOURCE_LABEL = {
    "googleTrends": "Google Trends",
    "wikipedia": "Wikipedia pageviews",
    "reddit": "Reddit",
    "hackerNews": "Hacker News",
    "googleNews": "Google News",
}
SIZE_WORD = {"marketCap": "market capitalisation", "fundAssets": "fund size"}


def save(cur, kind, headline, body, source, **keys) -> None:
    cur.execute(
        """
        INSERT INTO "Analysis"
          (kind, "industryId", "assetId", "productId", headline, body, "dataNote", source, "createdAt")
        VALUES (%s::"AnalysisKind",%s,%s,%s,%s,%s,%s,%s, now())
        """,
        (
            kind,
            keys.get("industryId"),
            keys.get("assetId"),
            keys.get("productId"),
            headline,
            body,
            keys.get("dataNote"),
            source,
        ),
    )


def money(value: float, basis: str) -> str:
    unit = SIZE_WORD.get(basis, "size")
    if value >= 1e12:
        return f"${value / 1e12:.2f} trillion {unit}"
    if value >= 1e9:
        return f"${value / 1e9:.1f} billion {unit}"
    if value >= 1e6:
        return f"${value / 1e6:.0f} million {unit}"
    return f"${value:,.0f} {unit}"


def pct_text(value: float) -> str:
    return f"{value:+.0f}%"


def ranking_table(cur, industry_id, basis, period_end, order="rank"):
    return rows(
        cur,
        f"""
        SELECT r.rank, r.value, r."periodStart", r."periodEnd", r.note, r."sizeRank",
               a.id AS aid, a.name, a.symbol, a."capBasis", a.source, a."assetType"
        FROM "Ranking" r JOIN "Asset" a ON a.id = r."assetId"
        WHERE r."industryId" = %s AND r.basis = %s::"RankingBasis" AND r."periodEnd" = %s
        ORDER BY r.{order}
        """,
        (industry_id, basis, period_end),
    )


# --------------------------------------------------------------- industries


def industry_shift(cur, ind) -> None:
    now_rows = ranking_table(cur, ind["id"], "sizeNow", period_end_at(cur, ind["id"], "sizeNow"))
    pre_rows = ranking_table(cur, ind["id"], "size", period_end_at(cur, ind["id"], "size"))
    pre_ret = ranking_table(
        cur, ind["id"], "totalReturn", period_end_at(cur, ind["id"], "totalReturn", PRE_AI_END)
    )
    post_ret = ranking_table(
        cur, ind["id"], "totalReturn", period_end_latest(cur, ind["id"], "totalReturn")
    )

    notes = []
    if now_rows and pre_rows:
        before = {r["name"]: r for r in pre_rows}
        climbed = [
            r for r in now_rows if r["name"] in before and r["rank"] < before[r["name"]]["rank"]
        ]
        fell = [
            r for r in now_rows if r["name"] in before and r["rank"] > before[r["name"]]["rank"]
        ]
        top_now = now_rows[0]
        old_rank = before.get(top_now["name"], {}).get("rank")
        if old_rank:
            notes.append(
                f"{top_now['name']} is largest today at rank {top_now['rank']}, "
                f"it was rank {old_rank} at the end of 2021."
            )
        if climbed:
            names = ", ".join(r["name"] for r in climbed[:3])
            notes.append(f"{len(climbed)} of {len(now_rows)} moved up since 2021, led by {names}.")
        if fell:
            names = ", ".join(r["name"] for r in fell[:3])
            notes.append(f"{len(fell)} moved down since 2021, including {names}.")

    if pre_ret and post_ret:
        pre_avg = mean([r["value"] for r in pre_ret])
        post_avg = mean([r["value"] for r in post_ret])
        best_pre = max(pre_ret, key=lambda r: r["value"])
        best_post = max(post_ret, key=lambda r: r["value"])
        notes.append(
            f"Average return across the list was {pct_text(pre_avg)} from 2019 to 2021, "
            f"led by {best_pre['name']} at {pct_text(best_pre['value'])}."
        )
        notes.append(
            f"Average return since 2021 is {pct_text(post_avg)}, led by "
            f"{best_post['name']} at {pct_text(best_post['value'])}."
        )
        worst_post = min(post_ret, key=lambda r: r["value"])
        notes.append(
            f"The weakest name since 2021 is {worst_post['name']} at "
            f"{pct_text(worst_post['value'])}."
        )

    data_note = None
    if not now_rows:
        data_note = (
            "No size figure is stored for this industry at the current date, so there is "
            "no size ranking. Returns are shown instead."
        )
    elif not pre_rows:
        data_note = (
            "No size figure is stored for this industry at the end of 2021, so the pre-AI "
            "size ranking cannot be built. Returns are shown instead."
        )

    headline = f"{ind['name']}: what moved since 2021"
    body = " ".join(notes) if notes else "Not enough stored data to describe this industry yet."
    save(cur, "industryShift", headline, body, "Yahoo Finance, Binance, CoinPaprika", industryId=ind["id"], dataNote=data_note)


def period_end_at(cur, industry_id, basis, on_or_before=None):
    """Newest stored period end, optionally capped, so the pre-AI window is not
    confused with the current one."""
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


def rising_note(cur, ind) -> None:
    rising = ranking_table(cur, ind["id"], "rising", period_end_latest(cur, ind["id"], "rising"))
    if not rising:
        return
    top = rising[:3]
    names = ", ".join(f"{r['name']} {pct_text(r['value'])}" for r in top)
    headline = f"{ind['name']}: strongest 24 month movers"
    body = (
        f"Ranking is the 24 month return minus the average return of the {len(rising)} assets "
        f"in this industry, so a positive number means the asset beat its own industry. "
        f"Top of the list: {names}. "
        f"The weakest relative performer is {rising[-1]['name']} at {pct_text(rising[-1]['value'])}."
    )
    unconfirmed = [r for r in rising[:5] if "unavailable" in (r["note"] or "")]
    note = None
    if unconfirmed:
        note = (
            f"{len(unconfirmed)} of the top 5 have no volume trend stored, so the volume "
            "check could not be applied to them."
        )
    save(cur, "forwardLook", headline, body, "Yahoo Finance, Binance", industryId=ind["id"], dataNote=note)


def forward_look(cur, ind) -> None:
    rising = ranking_table(cur, ind["id"], "rising", period_end_latest(cur, ind["id"], "rising"))
    post = ranking_table(
        cur, ind["id"], "totalReturn", period_end_latest(cur, ind["id"], "totalReturn")
    )
    if not rising or not post:
        return
    spread_top = rising[0]["value"]
    spread_low = rising[-1]["value"]
    dispersion = spread_top - spread_low

    news = rows(
        cur,
        """
        SELECT count(*) AS n, max("publishedAt") AS latest
        FROM "News" WHERE "industryId" = %s AND "publishedAt" > now() - interval '14 days'
        """,
        (ind["id"],),
    )[0]

    top = rising[0]
    bottom = rising[-1]
    parts = [
        f"Spread between the strongest and weakest 24 month performer in this list is "
        f"{dispersion:.0f} percentage points.",
        f"Strongest: {top['name']} at {pct_text(top['value'])} against the industry average. "
        f"Weakest: {bottom['name']} at {pct_text(bottom['value'])}.",
    ]
    if news["n"]:
        parts.append(
            f"{news['n']} news items mentioning this industry were published in the last 14 days."
        )
    else:
        parts.append("No news items for this industry were collected in the last 14 days.")
    body = " ".join(parts)
    save(
        cur,
        "forwardLook",
        f"{ind['name']}: what the current data shows",
        body + " This is a description of measured direction, not a forecast.",
        "Yahoo Finance, Binance, Google News RSS",
        industryId=ind["id"],
        dataNote="No forecast is stored. The page shows what was measured and stops there.",
    )


# --------------------------------------------------------------- assets


def asset_notes(cur) -> None:
    step("asset lines")
    assets = rows(cur, 'SELECT id, name FROM "Asset"')
    for a in assets:
        size_now = rows(
            cur,
            """
            SELECT r.rank, r.value, r."periodEnd", r."sizeRank", a."capBasis"
            FROM "Ranking" r JOIN "Asset" a ON a.id = r."assetId"
            WHERE r."assetId" = %s AND r.basis = 'sizeNow'::"RankingBasis"
            """,
            (a["id"],),
        )
        size_pre = rows(
            cur,
            """
            SELECT r.rank, r.value, r."periodEnd" FROM "Ranking" r
            WHERE r."assetId" = %s AND r.basis = 'size'::"RankingBasis"
            """,
            (a["id"],),
        )
        total = rows(
            cur,
            """
            SELECT value, "periodStart", "periodEnd" FROM "Ranking"
            WHERE "assetId" = %s AND basis = 'totalReturn'::"RankingBasis"
            ORDER BY "periodEnd" DESC
            """,
            (a["id"],),
        )
        rising = rows(
            cur,
            """
            SELECT value, rank, note FROM "Ranking"
            WHERE "assetId" = %s AND basis = 'rising'::"RankingBasis"
            """,
            (a["id"],),
        )
        total = sorted(total, key=lambda r: r["periodEnd"])
        pre = next((r for r in total if r["periodEnd"] <= PRE_AI_END), None)
        post = next((r for r in reversed(total) if r["periodEnd"] > PRE_AI_END), None)

        parts = []
        note = None
        if size_now:
            s = size_now[0]
            parts.append(
                f"Rank {s['rank']} in its industry today at {money(s['value'], s['capBasis'])}, "
                f"as of {s['periodEnd']}."
            )
            if size_pre:
                p = size_pre[0]
                move = p["rank"] - s["rank"]
                word = "up" if move > 0 else "down" if move < 0 else "unchanged"
                parts.append(
                    f"Rank {p['rank']} at the end of 2021, so rank is {word} "
                    f"{abs(move) if move else 0} places since then."
                )
        if pre:
            parts.append(
                f"Return from {pre['periodStart']} to {pre['periodEnd']} was {pct_text(pre['value'])}."
            )
        if post:
            parts.append(
                f"Return from {post['periodStart']} to {post['periodEnd']} was {pct_text(post['value'])}."
            )
        if rising:
            r = rising[0]
            parts.append(
                f"24 month return against its own industry average is {pct_text(r['value'])}, rank {r['rank']}."
            )
        if not size_now:
            note = (
                "No size figure is stored for this asset, so it has no size rank. "
                "Return figures are still shown."
            )
        body = " ".join(parts) if parts else "No stored figures for this asset yet."
        save(cur, "assetPosition", a["name"], body, "Yahoo Finance, Binance, CoinPaprika", assetId=a["id"], dataNote=note)


# --------------------------------------------------------------- products


def product_notes(cur) -> None:
    step("product lines")
    products = rows(cur, 'SELECT id, slug, name, summary FROM "Product" ORDER BY slug')
    for p in products:
        sigs = rows(
            cur,
            """
            SELECT source, metric, value, note, "periodEnd" FROM "ProductSignal"
            WHERE "productId" = %s
            """,
            (p["id"],),
        )
        parts = []
        changes = []
        for source, metric, label in (
            ("googleTrends", "trends_8w_vs_8w_pct", "Google Trends search interest, 8 weeks against the 8 before"),
            ("wikipedia", "wiki_views_8w_vs_8w_pct", "Wikipedia pageviews, 8 weeks against the 8 before"),
            ("hackerNews", "hn_stories_90d_change_pct", "Hacker News stories, last 90 days against the 90 before"),
            ("reddit", "reddit_posts_30d_change_pct", "Reddit posts, last 30 days against the 90 before"),
            ("googleNews", "gnews_articles_30d_change_pct", "Google News articles, last 30 days against the 30 before"),
        ):
            row = next((s for s in sigs if s["source"] == source and s["metric"] == metric), None)
            if row and row["value"] is not None:
                changes.append((label, row["value"]))
                parts.append(f"{label}: {pct_text(row['value'])}.")

        raw = next((s for s in sigs if s["source"] == "reddit" and s["metric"] == "reddit_posts_30d"), None)
        if raw and raw["value"] is not None:
            parts.append(f"Reddit posts in the last 30 days: {int(raw['value'])}.")
        trends_raw = next(
            (s for s in sigs if s["source"] == "googleTrends" and s["metric"] == "trends_8w_vs_8w_pct"),
            None,
        )
        if trends_raw:
            parts.append(f"Measured to the week ending {trends_raw['periodEnd']}.")

        note = None
        if not changes:
            note = "No demand source answered for this product, so it is left out of every list."
            score = None
            status = "unknown"
        else:
            score = mean([c[1] for c in changes])
            values = [c[1] for c in changes]
            up = sum(1 for v in values if v > 0)
            if up == len(values) and (score or 0) >= 5:
                status = "rising"
            elif (score or 0) >= 10:
                status = "rising"
            elif (score or 0) > 0 and up >= 1 and len(values) >= 2:
                status = "early"
            else:
                status = "flat"
            note = f"Average of {len(values)} sources: " + ", ".join(
                sorted({SOURCE_LABEL[s["source"]] for s in sigs if s["metric"].endswith("_pct")})
            )
            if len(values) == 1:
                note += ". One source only, so this is a weak signal."

        body = " ".join(parts) if parts else "No demand data stored for this product yet."
        headline = f"{p['name']}: demand read"
        save(cur, "productDemand", headline, body, ", ".join(sorted({s["source"] for s in sigs})) or "none", productId=p["id"], dataNote=note)

        cur.execute(
            'UPDATE "Product" SET status = %s, "demandScore" = %s, "demandNote" = %s, "computedAt" = now() WHERE id = %s',
            (status, score, note, p["id"]),
        )


def site_lead(cur) -> None:
    step("front page")
    top_risers = rows(
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
    risers = ", ".join(f"{r['name']} in {r['industry']} at {pct_text(r['value'])}" for r in top_risers)
    latest = rows(cur, 'SELECT max("periodEnd") AS d FROM "Ranking" WHERE basis = %s::"RankingBasis"', ("rising",))[0]["d"]
    products = rows(
        cur,
        """
        SELECT name, "demandScore" FROM "Product"
        WHERE status = 'rising' AND "demandScore" IS NOT NULL
        ORDER BY "demandScore" DESC LIMIT 3
        """,
    )
    prod_text = ", ".join(f"{p['name']} at {pct_text(p['demandScore'])}" for p in products)
    body = (
        f"Data through {latest}. "
        f"Strongest 24 month relative performers: {risers or 'not available'}. "
        f"Products with every demand source pointing up: {prod_text or 'none'}. "
        f"Every figure names its source and its as of date. Nothing here is a forecast."
    )
    save(cur, "siteLead", "What the data shows now", body, "all sources")


def main() -> None:
    conn = db()
    with conn, conn.cursor() as cur:
        cur.execute('DELETE FROM "Analysis"')
        industries = rows(cur, 'SELECT id, slug, name, summary FROM "Industry" ORDER BY sort')
        step("industries")
        for ind in industries:
            print(f"  {ind['name']}")
            industry_shift(cur, ind)
            rising_note(cur, ind)
            forward_look(cur, ind)
        asset_notes(cur)
        product_notes(cur)
        site_lead(cur)
        cur.execute('SELECT kind, count(*) AS n FROM "Analysis" GROUP BY kind ORDER BY kind')
        for got in cur.fetchall():
            print(f"{got['kind']:16} {got['n']}")
    conn.close()


if __name__ == "__main__":
    main()
