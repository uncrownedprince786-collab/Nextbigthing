"""Product demand signals.

Five free sources, each asked the same two questions: is attention up in the recent
window compared with the window before it, and is it up year on year. A source that
does not answer produces no row, and the product is then shown with fewer sources.

  googleTrends  8 weeks vs the 8 before, and 26 weeks vs the 26 a year before
  wikipedia     same two windows on the product article
  hackerNews    stories over 10 points, last 90 days vs the 90 before
  googleNews    articles, last 30 days vs the 30 before
  reddit        posts from the public RSS search, last 30 days against the rate over
                the 90 days immediately before, both cut from the same year feed

Windows are anchored to the last complete week so a partial week cannot distort a
number. Reddit is the slowest and the most easily blocked, so it runs on its own flag.

Run: python jobs/signals.py [trends|wiki|hn|news|reddit]
"""

from __future__ import annotations

import os
import sys
import threading
import time
import urllib.parse
import warnings
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, get, get_json, mean, pct, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

from urllib3.util.retry import Retry  # noqa: E402

# pytrends still passes method_whitelist, which urllib3 2.x removed. Map it once here
# rather than pinning urllib3, because pinning would break every other job.
_orig_retry = Retry.__init__


def _retry_init(self, *a, **kw):
    if "method_whitelist" in kw:
        kw["allowed_methods"] = kw.pop("method_whitelist")
    return _orig_retry(self, *a, **kw)


Retry.__init__ = _retry_init

WIKI = "wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
TRENDS = "Google Trends"
WIKI_NAME = "Wikipedia pageviews"
HN = "Hacker News Algolia API"
GNEWS = "Google News RSS"
REDDIT = "Reddit public RSS search"

# Smallest base a count has to reach before a percentage change off it is published.
# Set from the measured data: of 30 products, 14 post 0 or 1 times in 30 days on the two
# subreddits searched, and 2 post more than 4. A change off a base of one is a rounding
# artifact, so below this floor only the raw counts are stored.
MIN_COUNT_BASE = 5

# The two Reddit windows, in days, and they have to be adjacent and comparable.
#
# The first version of this compared a 30 day count against a count taken from 180 to 90
# days ago. Two things were wrong with that. The windows were not adjacent, so the 60 days
# in between were measured by neither and a product that started being discussed two months
# ago fell in the gap. Worse, a 30 day count was divided by a 90 day count, which is not a
# change at all: a product posted about at a perfectly steady rate came out at -67% every
# single run, and the note printed underneath said so out loud without anyone reading it as
# the bug it was.
#
# Now the prior window ends where the recent one begins, and the comparison is made between
# two rates over the same length of time. A steady product reads 0%.
REDDIT_RECENT_DAYS = 30
REDDIT_PRIOR_DAYS = 90
# What the prior count has to be divided by to become a 30 day rate.
REDDIT_PRIOR_SCALE = REDDIT_PRIOR_DAYS / REDDIT_RECENT_DAYS

# Reddit from a GitHub runner, 2026-10-10: the first feed of the run neither answered nor failed for
# twenty minutes -- not one line printed -- until the step was killed, and the four sources before it
# were lost with it. A socket timeout only fires on silence, so a feed that trickles or stalls inside
# the handshake can hold a request open indefinitely. So each feed gets a wall-clock cap, the first feed
# to pass it ends Reddit for the run, and the source as a whole has a budget. Overridable per lane.
REDDIT_FEED_CAP_S = 90
REDDIT_BUDGET_MIN = float(os.environ.get("REDDIT_BUDGET_MIN") or 8.0)


def capped(fetch, cap_s: float):
    """(result, stuck): `fetch()` run with a wall-clock cap.

    The fetch runs on a daemon thread, so one that never returns is abandoned rather than waited for,
    and it cannot hold the process open at exit.
    """
    box: dict = {}
    worker = threading.Thread(target=lambda: box.setdefault("value", fetch()), daemon=True)
    worker.start()
    worker.join(cap_s)
    if worker.is_alive():
        return None, True
    return box.get("value"), False


def last_complete_week(today: date) -> date:
    """Sunday that is at least 7 days back, so the newest week is complete."""
    return today - timedelta(days=today.weekday() + 7)


def write(cur, product_id, source, metric, value, period_end, evidence=None, note=None):
    if value is None:
        return
    cur.execute(
        """
        INSERT INTO "ProductSignal"
          ("productId", source, metric, value, evidence, "periodEnd", note, "createdAt")
        VALUES (%s,%s::"SignalSource",%s,%s,%s,%s,%s, now())
        ON CONFLICT ("productId", source, metric, "periodEnd") DO UPDATE
        SET value = EXCLUDED.value, evidence = EXCLUDED.evidence, note = EXCLUDED.note
        """,
        (product_id, source, metric, value, evidence, period_end, note),
    )


# ---------------------------------------------------------------- Google Trends


def trends_signals(cur) -> None:
    from pytrends.request import TrendReq

    step("google trends")
    products = rows(
        cur,
        'SELECT id, slug, name, "trendsTerm" FROM "Product" WHERE "trendsTerm" <> \'\'',
    )
    anchor = last_complete_week(date.today())
    bucket = {}
    for p in products:
        bucket.setdefault(p["trendsTerm"], []).append(p)

    terms = list(bucket)
    got = 0
    for i in range(0, len(terms), 5):
        chunk = terms[i : i + 5]
        for window, timeframe in (("12m", "today 12-m"), ("5y", "today 5-y")):
            frame = None
            for attempt in range(3):
                try:
                    pt = TrendReq(
                        hl="en-US", tz=0, timeout=(10, 30), retries=1, backoff_factor=0.5
                    )
                    pt.build_payload(chunk, timeframe=timeframe, geo="")
                    frame = pt.interest_over_time()
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  trends attempt {attempt + 1} failed: {type(e).__name__}")
                    time.sleep(20 * (attempt + 1))
            if frame is None or frame.empty:
                print(f"  no trends data for {chunk} {window}")
                continue

            frame = frame.drop(columns=[c for c in ("isPartial",) if c in frame])
            for term in chunk:
                if term not in frame:
                    continue
                series = sorted(
                    (idx.date(), float(v)) for idx, v in frame[term].items() if v == v
                )
                if not series:
                    continue
                if window == "12m":
                    metric = "trends_8w_vs_8w_pct"
                    value = pct(*last_windows(series, 8, 8, anchor))
                    note = f"{TRENDS}, weekly index, 8 weeks to {anchor} against the 8 before"
                else:
                    metric = "trends_26w_yoy_pct"
                    value = pct(*last_windows_yoy(series))
                    note = f"{TRENDS}, weekly index, last 26 weeks against the 26 a year before"
                for p in bucket[term]:
                    write(cur, p["id"], "googleTrends", metric, value, anchor, note=note)
                got += 1
        time.sleep(8)
    print(f"  trends series written: {got}")


def last_windows(series, n_recent, n_prior, anchor):
    upto = [v for day, v in series if day <= anchor]
    recent = upto[-n_recent:]
    prior = upto[-2 * n_recent : -n_recent]
    return mean(recent), mean(prior)


def last_windows_yoy(series, n_weeks: int = 26):
    if not series:
        return None, None
    latest = series[-1][0]
    cutoff_recent = latest - timedelta(days=7 * n_weeks)
    cutoff_prior = latest - timedelta(days=14 * n_weeks)
    recent = [v for day, v in series if day > cutoff_recent]
    prior = [v for day, v in series if cutoff_prior < day <= cutoff_recent]
    return mean(recent), mean(prior)


# ---------------------------------------------------------------- Wikipedia


def wiki_signals(cur) -> None:
    step("wikipedia pageviews")
    products = rows(cur, 'SELECT id, slug, "wikiTitle" FROM "Product" WHERE "wikiTitle" <> \'\'')
    anchor = last_complete_week(date.today())
    start = (anchor - timedelta(days=730)).strftime("%Y%m%d")
    end = anchor.strftime("%Y%m%d")
    got = 0
    for p in products:
        url = (
            f"https://{WIKI}/en.wikipedia/all-access/user/"
            f"{urllib.parse.quote(p['wikiTitle'].replace(' ', '_'))}/daily/{start}/{end}"
        )
        blob = get_json(url, cache_key=f"wiki-{p['wikiTitle']}", ttl=20 * 3600)
        if not blob or not blob.get("items"):
            print(f"  no pageviews for {p['wikiTitle']}")
            continue
        series = sorted(
            (
                datetime.strptime(it["timestamp"][:8], "%Y%m%d").date(),
                float(it["views"]),
            )
            for it in blob["items"]
        )
        write(
            cur,
            p["id"],
            "wikipedia",
            "wiki_views_8w_vs_8w_pct",
            pct(*last_windows(series, 8, 8, anchor)),
            anchor,
            note=f"{WIKI_NAME}, {p['wikiTitle']}",
        )
        write(
            cur,
            p["id"],
            "wikipedia",
            "wiki_views_26w_yoy_pct",
            pct(*last_windows_yoy(series)),
            anchor,
            note=f"{WIKI_NAME}, {p['wikiTitle']}",
        )
        got += 1
    print(f"  products with pageviews: {got}")


# ---------------------------------------------------------------- Hacker News


def hn_signals(cur) -> None:
    step("hacker news")
    products = rows(cur, 'SELECT id, slug, name, "trendsTerm" FROM "Product"')
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    d90, d180 = int((now - timedelta(days=90)).timestamp()), int(
        (now - timedelta(days=180)).timestamp()
    )
    got = 0
    for p in products:
        term = p["trendsTerm"] or p["name"]
        url = (
            "https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=1&query="
            + urllib.parse.quote(term)
            + f"&numericFilters=created_at_i>{d90},points>10"
        )
        recent = (get_json(url, cache_key=f"hn-r-{p['slug']}", ttl=12 * 3600) or {}).get(
            "nbHits"
        )
        url_old = (
            "https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=1&query="
            + urllib.parse.quote(term)
            + f"&numericFilters=created_at_i>{d180},created_at_i<={d90},points>10"
        )
        prior = (get_json(url_old, cache_key=f"hn-p-{p['slug']}", ttl=12 * 3600) or {}).get(
            "nbHits"
        )
        if recent is None:
            continue
        write(
            cur,
            p["id"],
            "hackerNews",
            "hn_stories_90d",
            float(recent),
            date.today(),
            note=f"{HN}, stories over 10 points, last 90 days",
        )
        write(
            cur,
            p["id"],
            "hackerNews",
            "hn_stories_90d_change_pct",
            pct(float(recent), float(prior)) if prior is not None else None,
            date.today(),
            note=f"{HN}, last 90 days against the 90 days before",
        )
        got += 1
    print(f"  products with a Hacker News count: {got}")


# ---------------------------------------------------------------- Google News


def gnews_signals(cur) -> None:
    step("google news")
    products = rows(cur, 'SELECT id, slug, name FROM "Product"')
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    windows = {"30d": (now - timedelta(days=30), now), "60d": (now - timedelta(days=60), now - timedelta(days=30))}
    got = 0
    for p in products:
        counts = {}
        for label, (lo, hi) in windows.items():
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote(f'"{p["name"]}" when:{days_ago(lo)}d..{days_ago(hi)}d')
                + "&hl=en-US&gl=US&ceid=US:en"
            )
            raw = get(url, cache_key=f"gn-{p['slug']}-{label}", ttl=20 * 3600)
            if not raw:
                continue
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            counts[label] = sum(1 for it in root.iter() if it.tag.endswith("item"))
        if "30d" not in counts:
            continue
        write(
            cur,
            p["id"],
            "googleNews",
            "gnews_articles_30d",
            float(counts["30d"]),
            date.today(),
            note=f"{GNEWS}, search for the exact product name",
        )
        write(
            cur,
            p["id"],
            "googleNews",
            "gnews_articles_30d_change_pct",
            pct(float(counts["30d"]), float(counts.get("60d"))),
            date.today(),
            note=f"{GNEWS}, last 30 days against the 30 days before",
        )
        got += 1
    print(f"  products with a news count: {got}")


def days_ago(when: datetime) -> int:
    return (datetime.now(timezone.utc).replace(tzinfo=None) - when).days


# ---------------------------------------------------------------- Reddit


def reddit_signals(cur) -> None:
    """One request per subreddit per product.

    Reddit's public search RSS only offers preset windows, and the 30 day window caps
    at 25 results, so a capped count cannot be compared with an uncapped one. The year
    feed is read once and the windows are cut from the entry dates instead, which keeps
    both counts on the same footing.

    The two windows are adjacent and the longer one is converted to a rate before the
    comparison, so a product discussed at an unchanged rate reads 0% rather than -67%.
    """
    step("reddit")
    products = rows(
        cur, 'SELECT id, slug, name, "trendsTerm", subreddits FROM "Product"'
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    got = 0
    deadline = time.monotonic() + REDDIT_BUDGET_MIN * 60
    stalled = False
    for n, p in enumerate(products):
        if stalled or time.monotonic() > deadline:
            # Not asked is not the same as asked and empty: these products keep whatever Reddit
            # count they already had, with its own date, and nothing is cleared for them.
            why = "a feed stalled" if stalled else f"the {REDDIT_BUDGET_MIN:.0f} minute budget was spent"
            print(f"  reddit stopped: {why}; {len(products) - n} products not asked this run")
            break
        subs = [s.strip() for s in (p["subreddits"] or "").split(",") if s.strip()]
        if not subs:
            continue
        term = p["trendsTerm"] or p["name"]
        recent = prior = 0
        answered: list[str] = []
        missing: list[str] = []
        evidence = None
        for sub in subs[:2]:
            url = (
                f"https://www.reddit.com/r/{sub}/search.rss?q="
                + urllib.parse.quote(term)
                + "&restrict_sr=1&sort=top&t=year"
            )
            raw, stuck = capped(
                lambda url=url, key=f"rd-{p['slug']}-{sub}-year": get(url, cache_key=key, ttl=20 * 3600),
                REDDIT_FEED_CAP_S,
            )
            if stuck:
                print(f"  r/{sub}: no answer within {REDDIT_FEED_CAP_S} s, so Reddit is not answering this runner")
                stalled = True
                break
            if not raw:
                # A blocked subreddit is not the same as a subreddit with nothing to report.
                missing.append(f"r/{sub}")
                continue
            answered.append(f"r/{sub}")
            # Adjacent windows: the prior one ends exactly where the recent one begins, so
            # no day is counted twice and no day falls between them uncounted.
            recent += count_recent(raw, now - timedelta(days=REDDIT_RECENT_DAYS), now)
            prior += count_recent(
                raw,
                now - timedelta(days=REDDIT_RECENT_DAYS + REDDIT_PRIOR_DAYS),
                now - timedelta(days=REDDIT_RECENT_DAYS),
            )
            if evidence is None:
                evidence = first_recent(raw, now - timedelta(days=REDDIT_RECENT_DAYS))
        if stalled:
            continue
        if missing:
            # Counting only the subreddits that answered would understate the product and look
            # like a collapse in discussion, and next week the same product might be counted
            # across both subreddits, so the two numbers would not be comparable at all.
            # Better to publish nothing than to publish a partial count.
            #
            # The same period's rows are cleared, because anything already stored for today was
            # written by a run that did not insist on all subreddits answering, so its value is
            # a partial count and its note claims the full set. A stale value that looks current
            # is worse than a visible gap. Older periods keep their own rows and dates, and the
            # confidence grade already falls when the count is old.
            cur.execute(
                'DELETE FROM "ProductSignal" WHERE "productId" = %s AND source = %s::"SignalSource" '
                'AND "periodEnd" = %s',
                (p["id"], "reddit", date.today()),
            )
            dropped = cur.rowcount
            print(
                f"  {p['slug']}: no Reddit count, {', '.join(missing)} did not answer"
                + (f" (used {', '.join(answered)})" if answered else "")
                + (f", dropped {dropped} unverified rows" if dropped else "")
            )
            continue
        write(
            cur,
            p["id"],
            "reddit",
            "reddit_posts_30d",
            float(recent),
            date.today(),
            evidence=evidence,
            note=f"{REDDIT} in r/{', r/'.join(subs[:2])}, top posts of the last year",
        )
        write(
            cur,
            p["id"],
            "reddit",
            "reddit_posts_90d_base",
            float(prior),
            date.today(),
            note=f"{REDDIT}, the {REDDIT_PRIOR_DAYS} days immediately before the "
            f"{REDDIT_RECENT_DAYS} day window, in r/{', r/'.join(subs[:2])}",
        )
        # A percentage is only published when the window it is measured against actually
        # holds something. Most of these products post a handful of times a year on the two
        # subreddits searched, so a "change" from 1 post to 0 posts comes out as -100% and
        # reads as collapsing demand when it means the product is barely discussed there.
        # Below the floor the raw counts are stored and no percentage is invented.
        if prior >= MIN_COUNT_BASE:
            # The prior count covers three times as many days, so it is turned into a rate
            # over the same 30 days before the two are compared. Dividing a 30 day count by
            # a 90 day count would report a steady product as a third of its former self.
            prior_rate = float(prior) / REDDIT_PRIOR_SCALE
            write(
                cur,
                p["id"],
                "reddit",
                "reddit_posts_30d_change_pct",
                pct(float(recent), prior_rate),
                date.today(),
                note=(
                    f"{REDDIT}, {int(recent)} posts in the last {REDDIT_RECENT_DAYS} days "
                    f"against {prior_rate:.1f}, which is the {int(prior)} posts of the "
                    f"{REDDIT_PRIOR_DAYS} days before at the same rate per "
                    f"{REDDIT_RECENT_DAYS} days"
                ),
            )
        else:
            # Rows written before this floor existed still hold percentages built on a base
            # of one or two. Leaving them would keep the artifact alive, so they go.
            cur.execute(
                'DELETE FROM "ProductSignal" WHERE "productId" = %s AND source = %s::"SignalSource" '
                "AND metric = 'reddit_posts_30d_change_pct'",
                (p["id"], "reddit"),
            )
            print(
                f"  {p['slug']}: {int(recent)} posts now against {int(prior)} in the "
                f"{REDDIT_PRIOR_DAYS} days before, under the {MIN_COUNT_BASE} floor, "
                f"so no percentage is published"
            )
        got += 1
    searched = sum(
        1 for p in products if [s for s in (p["subreddits"] or "").split(",") if s.strip()]
    )
    print(
        f"  products with a Reddit count: {got} of {searched} searched"
        f" ({searched - got} without one)"
    )

    # An earlier version of this job counted the subreddits that happened to answer and
    # labelled the result with the full list, so a rate limited run left a partial count
    # behind claiming complete coverage. Anything still stored that way is unverifiable,
    # and a percentage whose base was never recorded cannot be checked by a reader, so it
    # is removed rather than shown. A product with nothing left simply shows no Reddit
    # figure until a run fetches all of its subreddits.
    for metric, why in (
        ("reddit_posts_30d_change_pct", "has no base to be checked against"),
        ("reddit_posts_30d", "is a partial count from a rate limited run"),
    ):
        cur.execute(
            """
            DELETE FROM "ProductSignal" v
            WHERE v.source = 'reddit' AND v.metric = %s
              AND NOT EXISTS (
                SELECT 1 FROM "ProductSignal" b
                WHERE b."productId" = v."productId" AND b.source = 'reddit'
                  AND b.metric = 'reddit_posts_90d_base'
                  AND b."periodEnd" = v."periodEnd"
              )
            """,
            (metric,),
        )
        if cur.rowcount:
            print(f"  removed {cur.rowcount} {metric} rows that {why}")


def _items(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return
    for it in root.iter():
        if it.tag.endswith("entry"):
            yield it


def count_recent(raw, lo: datetime, hi: datetime) -> int:
    n = 0
    for entry in _items(raw):
        stamp = None
        for c in entry:
            tag = c.tag.split("}")[-1]
            if tag == "updated" and c.text:
                stamp = c.text
        if not stamp:
            continue
        when = datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
        if lo <= when <= hi:
            n += 1
    return n


def first_recent(raw, since: datetime):
    """Title and URL of the newest post inside the window, as evidence a reader can check."""
    best = None
    for entry in _items(raw):
        title = url = stamp = None
        for c in entry:
            tag = c.tag.split("}")[-1]
            if tag == "title" and c.text:
                title = c.text.strip()
            elif tag == "updated" and c.text:
                stamp = c.text
            elif tag in ("id", "link") and c.get("href"):
                url = c.get("href")
        if not (title and url and stamp):
            continue
        when = datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
        if when >= since and (best is None or when > best[0]):
            best = (when, title, url)
    if best is None:
        return None
    return f"{best[1]} ({best[0].date()}) {best[2]}"


RUNNERS = {
    "trends": trends_signals,
    "wiki": wiki_signals,
    "hn": hn_signals,
    "news": gnews_signals,
    "reddit": reddit_signals,
}


def main() -> None:
    todo = sys.argv[1:] or ["wiki", "hn", "news"]
    conn = db()
    try:
        with conn.cursor() as cur:
            for name in todo:
                if name in RUNNERS:
                    RUNNERS[name](cur)
                    # Kept as soon as each source finishes. The whole run was one transaction, so a
                    # lane cut off at its time limit during the fifth source threw away the four
                    # finished before it -- which is how eight runs in a row stored nothing.
                    conn.commit()
                else:
                    print(f"unknown source {name}, choose from {', '.join(RUNNERS)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
