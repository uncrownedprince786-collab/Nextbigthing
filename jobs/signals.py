"""Product demand signals.

Five free sources, each asked the same two questions: is attention up in the recent
window compared with the window before it, and is it up year on year. A source that
does not answer produces no row, and the product is then shown with fewer sources.

  googleTrends  8 weeks vs the 8 before, and 26 weeks vs the 26 a year before
  wikipedia     same two windows on the product article
  hackerNews    stories over 10 points, last 90 days vs the 90 before
  googleNews    articles, last 30 days vs the 30 before
  reddit        posts from the public RSS search, last 30 days vs the 30 before

Windows are anchored to the last complete week so a partial week cannot distort a
number. Reddit is the slowest and the most easily blocked, so it runs on its own flag.

Run: python jobs/signals.py [trends|wiki|hn|news|reddit]
"""

from __future__ import annotations

import sys
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
    """
    step("reddit")
    products = rows(
        cur, 'SELECT id, slug, name, "trendsTerm", subreddits FROM "Product"'
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    got = 0
    for p in products:
        subs = [s.strip() for s in (p["subreddits"] or "").split(",") if s.strip()]
        if not subs:
            continue
        term = p["trendsTerm"] or p["name"]
        recent = prior = 0
        answered = False
        evidence = None
        for sub in subs[:2]:
            url = (
                f"https://www.reddit.com/r/{sub}/search.rss?q="
                + urllib.parse.quote(term)
                + "&restrict_sr=1&sort=top&t=year"
            )
            raw = get(url, cache_key=f"rd-{p['slug']}-{sub}-year", ttl=20 * 3600)
            if not raw:
                continue
            answered = True
            recent += count_recent(raw, now - timedelta(days=30), now)
            prior += count_recent(
                raw, now - timedelta(days=180), now - timedelta(days=90)
            )
            if evidence is None:
                evidence = first_recent(raw, now - timedelta(days=30))
        if not answered:
            print(f"  {p['slug']}: reddit did not answer")
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
            "reddit_posts_30d_change_pct",
            pct(float(recent), float(prior)) if prior else None,
            date.today(),
            note=f"{REDDIT}, last 30 days against the 90 days before, both cut from the year feed",
        )
        got += 1
    print(f"  products with a Reddit count: {got}")


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
    with conn, conn.cursor() as cur:
        for name in todo:
            if name in RUNNERS:
                RUNNERS[name](cur)
            else:
                print(f"unknown source {name}, choose from {', '.join(RUNNERS)}")
    conn.close()


if __name__ == "__main__":
    main()
