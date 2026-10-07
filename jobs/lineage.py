"""Group stored headlines into stories, so counting information stops counting copies.

The problem, stated plainly
--------------------------
One report syndicated to twenty outlets is one piece of information. The catalyst flag
counted News rows, so it counted it as twenty, and deduping by url could never have caught
that: twenty outlets genuinely have twenty different urls. A wire pickup therefore looked
exactly like a story breaking, which is the single easiest way for this site to cry wolf.

So every count that is meant to measure *information* now counts lineages, and the raw item
count is kept beside it because the gap between the two is itself informative: four stories
across four publishers is a developing situation, and one story across twenty is a press
release.

The method, and why it is not a model
-------------------------------------
Deterministic and auditable, because §44 of the architecture puts numerical conclusions in
code rather than in a language model:

  * a title is lowercased, stripped of punctuation, and reduced to tokens
  * stopwords and the target's own name tokens are dropped, since every item about one
    company repeats the company's name and matching on it would merge unrelated stories
  * the remaining tokens become a set, and two items join the same lineage when their
    Jaccard overlap clears THRESHOLD inside WINDOW_HOURS
  * clustering is transitive, by union-find, so a chain of near-duplicates is one story

The threshold and window are stored on every cluster, so any grouping can be rechecked
against the rule that produced it.

What this does not claim
------------------------
`isOriginal` marks the earliest item in a cluster. That is a claim about publication order
in the stored data and nothing more: the real original may never have been collected, and a
syndicating outlet is routinely faster than the newsroom it copied.

Run: python jobs/lineage.py
Writes: NewsLineage, News.lineageId, News.isOriginal
"""

from __future__ import annotations

import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

# Jaccard overlap at which two headlines are the same story. Measured against real stored
# feeds: rewrites of one report share most of their distinctive tokens once the company name
# and stopwords are removed, while two genuinely different stories about one company rarely
# clear a third. Set deliberately above that.
THRESHOLD = 0.5

# How far apart two items may be and still be the same story. Syndication runs for a couple
# of days; beyond that the same wording is usually a follow-up, which is new information.
WINDOW_HOURS = 72

# Only recent items are reclustered on each run. Older clusters do not change, and rewriting
# them every night would be work with no result.
#
# The consequence, measured 2026-10-07 and written down because it reads as a backlog and is not
# one: `News` keeps 120 days and this window is 45, so a permanent remainder of rows carries no
# `lineageId` and never will. Of 1,045 such rows that day, **every one** fell into one of two
# groups and none was reachable:
#
#     606  no `assetId` and no `productId` -- the `targets` query below selects per target, so
#          industry-level items are never clustered at all
#     439  published more than LOOKBACK_DAYS ago, which this window deliberately skips
#
# So "un-lineaged rows exist" is not a signal that this job needs running again. The number to
# check is rows that are un-lineaged AND targeted AND inside the window; when that is zero, this
# job has done everything it can. It costs nothing downstream: `jobs/human.py` counts stories over
# a 30-day window, which sits inside this 45-day one, so every row it reads is clustered.
LOOKBACK_DAYS = 45

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "on", "in", "to", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being", "it",
    "its", "this", "that", "these", "those", "has", "have", "had", "will", "would",
    "can", "could", "may", "might", "should", "after", "before", "amid", "says", "say",
    "said", "new", "up", "down", "over", "under", "more", "most", "than", "about",
    "into", "out", "how", "why", "what", "when", "who", "stock", "stocks", "shares",
    "share", "price", "prices", "market", "markets", "report", "reports", "news",
}

TOKEN_RE = re.compile(r"[a-z0-9']+")


def tokens(title: str, drop: set[str]) -> set[str]:
    """Distinctive tokens of a headline.

    The target's own name tokens are dropped via `drop`: every item about one company
    repeats the company's name, so keeping it would push unrelated stories over the
    threshold on the strength of the subject they share.
    """
    out = {
        t
        for t in TOKEN_RE.findall((title or "").lower())
        if len(t) > 2 and t not in STOPWORDS and t not in drop
    }
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


class Union:
    """Union-find, so a chain of near-duplicates ends up as one story rather than several."""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[rj] = ri


def cluster(items: list[dict], drop: set[str]) -> list[list[dict]]:
    """Group one target's items into stories.

    Items arrive sorted by publication time, which is what keeps this from being the O(n^2)
    scan it looks like. Two items can only be the same story inside WINDOW_HOURS, so the
    inner loop stops at the first item past the window rather than walking to the end: every
    item after it is further away still. The work is therefore proportional to how many items
    share a three day window, not to how many the feed has ever produced.

    The second guard is cheaper again. Two headlines with no distinctive token in common
    cannot clear any positive threshold, so the intersection is checked before the union is
    built.
    """
    n = len(items)
    sets = [tokens(it["title"], drop) for it in items]
    u = Union(n)
    window = WINDOW_HOURS * 3600
    compared = 0

    for i in range(n):
        if not sets[i]:
            continue
        for j in range(i + 1, n):
            gap = (items[j]["publishedAt"] - items[i]["publishedAt"]).total_seconds()
            if gap > window:
                break
            if not sets[j] or not (sets[i] & sets[j]):
                continue
            compared += 1
            if jaccard(sets[i], sets[j]) >= THRESHOLD:
                u.join(i, j)

    groups: dict[int, list[dict]] = {}
    for i, it in enumerate(items):
        groups.setdefault(u.find(i), []).append(it)
    return list(groups.values())


def main() -> None:
    rule = f"jaccard>={THRESHOLD} within {WINDOW_HOURS}h on non-stopword title tokens"

    conn = db()
    cur = conn.cursor()
    try:
        step("cluster stored headlines into stories")
        targets = rows(
            cur,
            """
            SELECT "assetId" AS id, 'asset' AS kind FROM "News"
            WHERE "assetId" IS NOT NULL GROUP BY "assetId"
            UNION ALL
            SELECT "productId" AS id, 'product' AS kind FROM "News"
            WHERE "productId" IS NOT NULL GROUP BY "productId"
            """,
        )
        if not targets:
            print("  no targeted news stored, nothing to cluster")
            return

        names = {}
        for t in rows(cur, 'SELECT id, name, symbol FROM "Asset"'):
            names[t["id"]] = f"{t['name']} {t['symbol']}"
        for t in rows(cur, 'SELECT id, name FROM "Product"'):
            names[t["id"]] = t["name"]

        total_items = total_stories = 0
        for t in targets:
            column = "assetId" if t["kind"] == "asset" else "productId"
            items = rows(
                cur,
                f"""
                SELECT id, title, publisher, "publishedAt" FROM "News"
                WHERE "{column}" = %s AND "publishedAt" > now() - interval '{LOOKBACK_DAYS} days'
                ORDER BY "publishedAt" ASC
                """,
                (t["id"],),
            )
            if not items:
                continue

            drop = tokens(names.get(t["id"], ""), set())
            groups = cluster(items, drop)
            total_items += len(items)
            total_stories += len(groups)

            for group in groups:
                group.sort(key=lambda it: it["publishedAt"])
                publishers = {(it["publisher"] or "unknown").strip() for it in group}
                cur.execute(
                    """
                    INSERT INTO "NewsLineage" ("targetRef", "firstSeen", "lastSeen", items,
                                               publishers, headline, rule, "computedAt")
                    VALUES (%s,%s,%s,%s,%s,%s,%s, now())
                    RETURNING id
                    """,
                    (
                        t["id"], group[0]["publishedAt"], group[-1]["publishedAt"],
                        len(group), len(publishers), group[0]["title"][:300], rule,
                    ),
                )
                lineage_id = cur.fetchone()["id"]
                cur.execute(
                    'UPDATE "News" SET "lineageId" = %s, "isOriginal" = (id = %s) '
                    "WHERE id = ANY(%s)",
                    (lineage_id, group[0]["id"], [it["id"] for it in group]),
                )
            conn.commit()

        # Clusters from earlier runs over the same window are now superseded. Removed rather
        # than left to accumulate, because a stale cluster would be counted twice.
        cur.execute(
            """
            DELETE FROM "NewsLineage" l
            WHERE NOT EXISTS (
                SELECT 1 FROM "News" n WHERE n."lineageId" = l.id
            )
            """
        )
        removed = cur.rowcount
        conn.commit()

        ratio = (total_items / total_stories) if total_stories else 0.0
        print(
            f"  {total_items} items in the last {LOOKBACK_DAYS} days grouped into "
            f"{total_stories} stories, {ratio:.2f} items per story"
        )
        print(f"  {removed} superseded clusters removed")
        print(
            "  a ratio near 1 means little syndication; a high ratio means the item count "
            "was mostly copies"
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
