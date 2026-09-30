"""Public marketplace rankings, kept separate from the demand score.

A search trend and a bestseller rank are not the same claim. One says people are looking,
the other says a listing is outselling the others in its category. Averaging them would
produce a number whose meaning depends on which sources happened to answer, so marketplace
rows live in their own table and never enter `Product.demandScore`.

What is stored is exactly what the category page published on the day it was read: the
positions on the first page, the listing title, and its id. A listing's move between runs
is computed from the previous stored run of the same category, so the first run reports no
movement at all rather than inventing a baseline.

Sources, as verified on 2026-09-30:

  Amazon Best Sellers  `amazon.com/Best-Sellers/zgbs/<category>/` returns the first 30
                       positions in server rendered markup, with the rank in each item's
                       own link. No sign in, no CAPTCHA, nothing solved or bypassed. Only
                       the first page is read, because the rank counter restarts on page
                       two and a guessed offset would mislabel every row on it.
  eBay                 Not used. `ebay.com/sch/i.html` with the sold and completed filters
                       returns 403 to an ordinary request. There is no free public
                       endpoint behind it, so eBay is absent rather than estimated.

Nothing here identifies a product to buy. A bestseller rank describes one listing's
position in one category on one marketplace on one day, which is a fact about that listing
and not a measure of a product category's demand.

Run: python jobs/marketplace.py
"""

from __future__ import annotations

import html
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, get, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

AMAZON = "amazonBestSellers"
SOURCE = "Amazon Best Sellers, first page of the category"
BASE = "https://www.amazon.com/Best-Sellers/zgbs"

# Amazon's own category slugs, chosen to overlap the product list rather than to be a
# complete map of the store. A category nobody on this site sells into is noise.
#
# Every slug below was fetched and parsed before being added, which is not pedantry: an
# unrecognised slug does not 404, it quietly serves a different category's list. Asking
# for `tools` returns nothing parseable and asking for `hi` returns the electronics chart,
# so a typo here would store one category's rankings under another category's name and
# nothing in the output would look wrong. Verify a new slug by fetching it before adding it.
CATEGORIES = [
    ("home-garden", "Home and Kitchen"),
    ("kitchen", "Kitchen and Dining"),
    ("electronics", "Electronics"),
    ("hpc", "Health and Household"),
    ("sporting-goods", "Sports and Outdoors"),
    ("office-products", "Office Products"),
    ("automotive", "Automotive"),
    ("lawn-garden", "Garden and Outdoor"),
    ("appliances", "Appliances"),
]

# One item block on the page, which carries its own rank inside the product link.
ITEM_SPLIT = re.compile(r'(?=<div id="p13n-asin-index-)')
ASIN_RE = re.compile(r'data-asin="([A-Z0-9]{10})"')
RANK_RE = re.compile(r"_sccl_(\d+)")
LINK_RE = re.compile(r'href="(/[^"]*?/dp/[A-Z0-9]{10}[^"]*?)"')
TITLE_RE = re.compile(r'line-clamp-[^"]*">([^<]{5,300})<')
ALT_RE = re.compile(r'<img[^>]+alt="([^"]{5,300})"')


def parse(page: str) -> list[dict]:
    """Rank, title, id and link for each item the category page rendered."""
    out: list[dict] = []
    seen: set[str] = set()
    for block in ITEM_SPLIT.split(page)[1:]:
        asin = ASIN_RE.search(block)
        rank = RANK_RE.search(block)
        # Some items carry the title only in the image alt text, so both are tried before
        # the row is given up on. A row with no title is dropped rather than stored as an
        # id, because an id alone tells a reader nothing they can check.
        title = TITLE_RE.search(block) or ALT_RE.search(block)
        link = LINK_RE.search(block)
        if not (asin and rank and title):
            continue
        if asin.group(1) in seen:
            continue
        seen.add(asin.group(1))
        out.append(
            {
                "rank": int(rank.group(1)),
                "itemRef": asin.group(1),
                "title": html.unescape(title.group(1)).strip()[:300],
                "url": (
                    f"https://www.amazon.com{link.group(1).split('/ref=')[0]}"
                    if link
                    else f"https://www.amazon.com/dp/{asin.group(1)}"
                ),
            }
        )
    return out


def previous_period(cur, category: str, today: date):
    got = rows(
        cur,
        """
        SELECT max("periodEnd") AS d FROM "MarketplaceItem"
        WHERE marketplace = %s AND "categorySlug" = %s AND "periodEnd" < %s
        """,
        (AMAZON, category, today),
    )
    return got[0]["d"] if got and got[0]["d"] else None


def main() -> None:
    today = date.today()
    conn = db()
    with conn, conn.cursor() as cur:
        step("amazon best sellers")
        total = blocked = 0
        for slug, name in CATEGORIES:
            raw = get(
                f"{BASE}/{slug}/",
                cache_key=f"amz-bs-{slug}-{today.isoformat()}",
                ttl=20 * 3600,
                headers={
                    # The category page is served to an ordinary browser request and to
                    # nothing else. This is the plain identification an ordinary browser
                    # sends; no cookie, no session, nothing solved.
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            if not raw:
                blocked += 1
                print(f"  {slug}: no response, so no rows for this category today")
                continue

            items = parse(raw.decode("utf-8", "replace"))
            if not items:
                # A page that answered but rendered nothing parseable means the markup
                # changed. That is a source to re-verify, not a category with no sellers,
                # so it is reported loudly and stored as nothing.
                blocked += 1
                print(f"  {slug}: page returned but no items parsed, markup may have changed")
                continue

            prev_end = previous_period(cur, slug, today)
            prev: dict[str, int] = {}
            if prev_end:
                prev = {
                    r["itemRef"]: r["rank"]
                    for r in rows(
                        cur,
                        """
                        SELECT "itemRef", rank FROM "MarketplaceItem"
                        WHERE marketplace = %s AND "categorySlug" = %s AND "periodEnd" = %s
                        """,
                        (AMAZON, slug, prev_end),
                    )
                }

            for it in items:
                cur.execute(
                    """
                    INSERT INTO "MarketplaceItem"
                      (marketplace, "categorySlug", "categoryName", rank, title, url,
                       "itemRef", "periodEnd", "previousRank", source, "createdAt")
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                    ON CONFLICT (marketplace, "categorySlug", "periodEnd", "itemRef")
                    DO UPDATE SET rank = EXCLUDED.rank, title = EXCLUDED.title,
                        url = EXCLUDED.url, "previousRank" = EXCLUDED."previousRank"
                    """,
                    (
                        AMAZON, slug, name, it["rank"], it["title"], it["url"],
                        it["itemRef"], today, prev.get(it["itemRef"]), SOURCE,
                    ),
                )
                total += 1
            new = sum(1 for it in items if it["itemRef"] not in prev)
            print(
                f"  {slug}: {len(items)} positions"
                + (
                    f", {new} not in the run of {prev_end}"
                    if prev_end
                    else ", first run so no movement is reported"
                )
            )

        print(f"\n{total} marketplace rows stored" + (f", {blocked} categories unavailable" if blocked else ""))
        if blocked == len(CATEGORIES):
            # Every category failing is a source problem, and the run should say so
            # rather than finish quietly with nothing written.
            print("no category answered: treat Amazon as unavailable and re-verify it")
            raise SystemExit(1)
    conn.close()


if __name__ == "__main__":
    main()
