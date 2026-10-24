"""Crypto headlines from the publishers themselves, with the article's own picture.

    python jobs/crypto_news.py
    python jobs/crypto_news.py --dry-run
    python jobs/crypto_news.py --feeds coindesk decrypt

Why this exists beside `jobs/prices.py`'s news lane
----------------------------------------------------
That lane searches Google News per asset, which is the right shape for a Karachi cement company
nobody writes a dedicated feed about. For crypto it produces links to
`news.google.com/rss/articles/CBMi...` -- Google's redirect, not the article. Measured on the
stored rows: **all 217** crypto items in the last week were redirects. Those pages carry no
article image, so `jobs/news_images.py` found an image for none of them, and every "read more"
sent a reader through Google instead of to the publisher.

The tokens cannot be unwrapped. Google's current format is opaque -- three were decoded by hand
and contained no url -- and scraping their internal endpoint to resolve one is both fragile and
not something to put in a scheduled job.

So crypto gets its own lane, reading the publishers' own RSS. Six of seven feeds carry the
article url *and* a `media:content` image in the feed itself, which means no per-article crawl at
all: one request per publisher, not one per story.

Matching a story to a coin
--------------------------
These are general crypto feeds, so each item has to be attributed. Two rules, both deliberately
strict, because a headline filed under the wrong coin is worse than one filed under none:

  * the coin's **full name** as a whole phrase -- "Bitcoin", "Pudgy Penguins";
  * its **ticker** as a whole uppercase word of three characters or more -- BTC, ETH, SOL.

A ticker that is also an ordinary English word (AI, ARK, ERA, ALT, GAS, SUN...) is refused on the
ticker rule alone and has to match on its name. Without that, "AI" files every artificial
intelligence story under Sleepless AI, which is the failure mode `prices.py` calls the token
guard.

An item matching nothing is dropped. An item matching more than four coins is dropped too: a
market-wrap listing a dozen tickers is about the market, not about any of them.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

from nbt import db, get, rows, step  # noqa: E402

#: Publisher feeds, checked 2026-10-24: every one answered, and every one but Bitcoin.com carries
#: an image in the feed. Named here rather than discovered, so a feed that dies is a visible
#: absence in the run's output instead of a silent reduction in coverage.
FEEDS = {
    "coindesk": ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    "cointelegraph": ("Cointelegraph", "https://cointelegraph.com/rss"),
    "decrypt": ("Decrypt", "https://decrypt.co/feed"),
    "theblock": ("The Block", "https://www.theblock.co/rss.xml"),
    "bitcoincom": ("Bitcoin.com", "https://news.bitcoin.com/feed/"),
    "cryptoslate": ("CryptoSlate", "https://cryptoslate.com/feed/"),
    "beincrypto": ("BeInCrypto", "https://beincrypto.com/feed/"),
}

#: Tickers that are also ordinary words, or so short that a whole-word match is still noise. These
#: may only be matched on their full name. The cost of being wrong here is a story filed under a
#: coin it is not about, which is worse than one filed under nothing.
AMBIGUOUS = {
    "AI", "ALT", "ARK", "ERA", "GAS", "SUN", "ONE", "NOT", "FOR", "ALL", "NEW", "NOW", "WIN",
    "TON", "ICE", "FUN", "HOT", "RED", "BOND", "CAKE", "CORE", "DASH", "DATA", "DUCK", "EDGE",
    "FLOW", "FORM", "GAME", "GODS", "HIGH", "HOLD", "IDEA", "JOBS", "KEY", "LIFE", "LINK",
    "LOOP", "MASK", "MOON", "MOVE", "OPEN", "ORDER", "PAID", "PEAK", "PLAY", "POWER", "RARE",
    "REAL", "RISE", "ROSE", "SAFE", "SAND", "SHOP", "SOUL", "STEP", "TIME", "TRUE", "VERY",
    "WAVE", "WELL", "WILD", "WORK", "ZERO", "CAW", "DIN", "ELF", "APT", "OP", "S", "T", "U",
}

#: How far back an item may be published and still be stored.
WINDOW_DAYS = 7

ITEM = re.compile(r"<item\b.*?</item>", re.S | re.I)


def tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}\b[^>]*>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{name}>", block, re.S | re.I)
    return unescape(m.group(1).strip()) if m else None


def image_of(block: str) -> str | None:
    for pat in (r'<media:content[^>]+url="([^"]+)"',
                r'<media:thumbnail[^>]+url="([^"]+)"',
                r'<enclosure[^>]+url="([^"]+)"[^>]*type="image'):
        m = re.search(pat, block, re.I)
        if m:
            u = unescape(m.group(1))
            if u.startswith("http") and len(u) <= 2000:
                return u
    # Some feeds put the hero image only in the description's HTML.
    desc = tag(block, "description") or ""
    m = re.search(r'<img[^>]+src="([^"]+)"', desc, re.I)
    if m and m.group(1).startswith("http"):
        return unescape(m.group(1))[:2000]
    return None


def published_of(block: str) -> datetime | None:
    for name in ("pubDate", "dc:date", "published", "updated"):
        raw = tag(block, name)
        if not raw:
            continue
        try:
            d = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            try:
                d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def matcher(coins: list[dict]):
    """A function from a headline to the coins it is about.

    Patterns are compiled once for all of them rather than per item: there are two thousand coins
    and a couple of hundred items, and compiling inside the loop is four hundred thousand regex
    builds to do the same work.
    """
    by_name = []
    by_ticker = []
    for c in coins:
        name = (c["name"] or "").strip()
        if len(name) >= 4 and name.upper() != c["ticker"]:
            by_name.append((re.compile(rf"\b{re.escape(name)}\b", re.I), c))
        t = c["ticker"]
        if len(t) >= 3 and t not in AMBIGUOUS:
            by_ticker.append((re.compile(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])"), c))

    def match(title: str) -> list[dict]:
        hit: dict[str, dict] = {}
        for pat, c in by_name:
            if pat.search(title):
                hit[c["id"]] = c
        for pat, c in by_ticker:
            if pat.search(title):
                hit[c["id"]] = c
        return list(hit.values())

    return match


INSERT = """
    INSERT INTO "News" ("assetId", title, url, publisher, "publishedAt", source,
                        "imageUrl", "imageCheckedAt", "createdAt")
    VALUES (%s,%s,%s,%s,%s,%s,%s, now(), now())
    ON CONFLICT ("assetId", url) WHERE "assetId" IS NOT NULL DO NOTHING
"""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Crypto headlines from the publishers themselves.")
    ap.add_argument("--feeds", nargs="*", default=sorted(FEEDS))
    ap.add_argument("--days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--max-coins-per-item", type=int, default=4,
                    help="an item naming more coins than this is about the market, not a coin")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    conn = db()
    cur = conn.cursor()
    try:
        step("the coins this site covers")
        coins = rows(cur, '''
            SELECT id, symbol, name,
                   upper(split_part(symbol, '-', 1)) AS ticker
              FROM "Asset" WHERE "assetType" = 'crypto'
        ''')
        print(f"  {len(coins)} coins")
        match = matcher(coins)

        step("publisher feeds")
        cutoff = datetime.now(timezone.utc) - timedelta(days=a.days)
        pending: list[tuple] = []
        seen: set[tuple[str, str]] = set()
        stats = {"items": 0, "stale": 0, "unmatched": 0, "tooBroad": 0, "withImage": 0}
        for key in a.feeds:
            if key not in FEEDS:
                print(f"  {key}: unknown feed, skipped")
                continue
            publisher, url = FEEDS[key]
            raw = get(url, timeout=25)
            if raw is None:
                print(f"  {publisher}: no answer")
                continue
            body = raw.decode("utf-8", "replace")
            blocks = ITEM.findall(body)
            kept = 0
            for b in blocks:
                stats["items"] += 1
                link = tag(b, "link")
                title = tag(b, "title")
                if not link or not title or not link.startswith("http"):
                    continue
                when = published_of(b)
                if when is None or when < cutoff:
                    stats["stale"] += 1
                    continue
                hits = match(title)
                if not hits:
                    stats["unmatched"] += 1
                    continue
                if len(hits) > a.max_coins_per_item:
                    stats["tooBroad"] += 1
                    continue
                img = image_of(b)
                if img:
                    stats["withImage"] += 1
                for c in hits:
                    sig = (c["id"], link)
                    if sig in seen:
                        continue
                    seen.add(sig)
                    pending.append((c["id"], title[:500], link, publisher, when,
                                    f"rss:{key}", img))
                    kept += 1
            print(f"  {publisher}: {len(blocks)} items, {kept} attributed")

        if a.dry_run:
            name_of = {c["id"]: c["ticker"] for c in coins}
            for p in pending[:24]:
                print(f"    [{name_of.get(p[0], '?'):<6}] {p[3]:<13} "
                      f"{p[1][:58]:<60} img={'yes' if p[6] else 'no'}")
            print(f"  would store {len(pending)} rows")
        else:
            # One statement, not one per row: `tests/test_brain.py` forbids a query inside a loop
            # and a feed sweep is a few hundred rows.
            cur.executemany(INSERT, pending)
            conn.commit()
            print(f"  stored {len(pending)} rows (duplicates ignored)")
        print(f"  seen {stats['items']}, {stats['stale']} outside {a.days}d, "
              f"{stats['unmatched']} named no coin, {stats['tooBroad']} named too many, "
              f"{stats['withImage']} carried an image")

        total = rows(cur, '''
            SELECT count(*) AS recent,
                   count(*) FILTER (WHERE n."imageUrl" IS NOT NULL) AS with_image
              FROM "News" n JOIN "Asset" a ON a.id = n."assetId"
             WHERE a."assetType" = 'crypto'
               AND n."publishedAt" >= now() - make_interval(days => %s)
        ''', (a.days,))[0]
        print(f"  crypto, last {a.days} days: {total['with_image']} of {total['recent']} "
              f"have an image")
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
