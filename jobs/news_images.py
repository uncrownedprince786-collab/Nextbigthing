"""Fill `News.imageUrl` from each article's own `og:image`.

    python jobs/news_images.py                 recent crypto items, newest first
    python jobs/news_images.py --limit 500
    python jobs/news_images.py --days 14 --all-markets
    python jobs/news_images.py --dry-run

A headline with a picture is read and a list of blue links is skimmed past. The stored rows carry
a title, a url and a publisher and no image, so the coin page drew the coin's own logo beside every
item -- honest, and the same picture nine times.

What it does, and what it is careful about
-------------------------------------------
For each article it fetches the page and reads the `og:image` (then `twitter:image`, then a bare
`<link rel="image_src">`) out of the `<head>`. Only the head: these pages are hundreds of kilobytes
of script and the meta tags are in the first few, so the read stops as soon as `</head>` arrives.

**Every outcome is recorded, including nothing.** `imageCheckedAt` is written whether an image was
found or not, which is what makes the job affordable to re-run: an article that publishes no
`og:image` never will, and without a settled "we looked" every run would re-fetch every one of
them for ever.

**It is a crawler, so it behaves like one.** `jobs/nbt.get` already carries the per-host delay, the
retry ladder and the 429/403 back-off the rest of this repository's fetching uses, and this goes
through it rather than around it. A publisher that blocks us is backed off and its items are left
unchecked rather than hammered.

**It never stores a url it has not resolved.** A relative `og:image` is joined against the page's
own address, and anything that is not http(s) after that is discarded -- a `data:` blob or a
`javascript:` string reaching an `<img src>` on a page we render is not a picture, it is an
injection with a `src` attribute.
"""

from __future__ import annotations

import argparse
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

from nbt import db, get, rows, step  # noqa: E402

#: Hosts a job must never be pointed at, however it came to be asked.
#:
#: `tests/test_brain.py` forbids building a fetch target straight out of a stored row, and it is
#: right to: the urls here arrive from news feeds, and a poisoned or merely wrong feed would have
#: this job -- which runs inside the network the database lives in -- fetch whatever it named.
#: So a stored url is validated into a public http(s) address before anything fetches it, and
#: anything that is not one is skipped and counted.
PRIVATE = (
    "localhost", "127.", "0.", "10.", "169.254.", "192.168.", "::1", "[::1]",
    "metadata.google.internal", "169.254.169.254",
)


def public_http_url(raw: str | None) -> str | None:
    """The url, if it is a plain public http(s) address; None otherwise."""
    if not raw or len(raw) > 2000:
        return None
    try:
        u = urlparse(raw)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.hostname:
        return None
    host = u.hostname.lower()
    if host.endswith(".local") or host.endswith(".internal"):
        return None
    if any(host == b.rstrip(".") or host.startswith(b) for b in PRIVATE):
        return None
    # 172.16.0.0/12
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            if 16 <= second <= 31:
                return None
        except (IndexError, ValueError):
            return None
    return raw

#: Read at most this much of a page. The meta tags live in the head and these pages are mostly
#: script; a megabyte of body to find a tag in the first two kilobytes is bandwidth nobody needs.
HEAD_BYTES = 200_000

META = [
    re.compile(rb'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]*content=["\']([^"\']+)["\']', re.I),
    re.compile(rb'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:image(?::url)?["\']', re.I),
    re.compile(rb'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]*content=["\']([^"\']+)["\']', re.I),
    re.compile(rb'<link[^>]+rel=["\']image_src["\'][^>]*href=["\']([^"\']+)["\']', re.I),
]


def image_in(raw: bytes, page_url: str) -> str | None:
    """The first image the page advertises, resolved against the page, or None."""
    head = raw[:HEAD_BYTES]
    cut = head.lower().find(b"</head>")
    if cut != -1:
        head = head[:cut]
    for pat in META:
        m = pat.search(head)
        if not m:
            continue
        try:
            found = unescape(m.group(1).decode("utf-8", "replace")).strip()
        except Exception:  # noqa: BLE001
            continue
        if not found:
            continue
        resolved = urljoin(page_url, found)
        scheme = urlparse(resolved).scheme
        # Anything that is not http(s) after resolution is discarded. A `data:` blob or a
        # `javascript:` string reaching an <img src> on a page we render is not a picture.
        if scheme in ("http", "https") and len(resolved) <= 2000:
            return resolved
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Fill News.imageUrl from each article's og:image.")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--days", type=int, default=7,
                    help="only items published inside this window; older ones are not shown")
    ap.add_argument("--all-markets", action="store_true",
                    help="by default only crypto assets, which is where the images are shown")
    ap.add_argument("--recheck-days", type=int, default=0,
                    help="also re-look at items checked more than this many days ago (0 = never)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    conn = db()
    cur = conn.cursor()
    found = missing = failed = 0
    try:
        step("articles with no image yet")
        where = ['n."publishedAt" >= now() - make_interval(days => %s)']
        params: list[object] = [a.days]
        if a.recheck_days > 0:
            where.append('(n."imageCheckedAt" IS NULL OR n."imageCheckedAt" < '
                         'now() - make_interval(days => %s))')
            params.append(a.recheck_days)
        else:
            where.append('n."imageCheckedAt" IS NULL')
        if not a.all_markets:
            where.append("asset.\"assetType\" = 'crypto'")
        params.append(a.limit)
        due = rows(cur, f'''
            SELECT n.id, n.url, n.title
              FROM "News" n
              JOIN "Asset" asset ON asset.id = n."assetId"
             WHERE {" AND ".join(where)}
             ORDER BY n."publishedAt" DESC
             LIMIT %s
        ''', tuple(params))
        print(f"  {len(due)} to look at")

        # Collected and written once at the end rather than a statement per article. A crawl of
        # three hundred pages is three hundred round trips against a pooler capped at two
        # connections if each result is written as it arrives, and `tests/test_brain.py` forbids
        # an in-loop query for exactly that reason.
        pending: list[tuple] = []
        skipped = 0
        for n in due:
            target = public_http_url(n["url"])
            if target is None:
                # Not a public web address. Marked as checked so it is never asked again, and
                # counted so a feed that is producing them is visible rather than silent.
                skipped += 1
                pending.append((None, n["id"]))
                continue
            raw = get(target, timeout=15)
            if raw is None:
                # The page did not answer. Deliberately NOT marked as checked: a blocked host or a
                # timeout is a thing that may work next run, and writing a settled "no image" for
                # it would make the failure permanent.
                failed += 1
                continue
            img = image_in(raw, target)
            if img:
                found += 1
            else:
                missing += 1
            if a.dry_run:
                print(f"  {'IMG ' if img else 'none'} {n['title'][:60]}")
                continue
            pending.append((img, n["id"]))

        if pending and not a.dry_run:
            cur.executemany(
                'UPDATE "News" SET "imageUrl" = %s, "imageCheckedAt" = now() WHERE id = %s',
                pending,
            )
            conn.commit()
        print(f"  {found} with an image, {missing} publish none, {failed} unreachable, "
              f"{skipped} not a public web address")

        total = rows(cur, '''
            SELECT count(*) FILTER (WHERE n."imageUrl" IS NOT NULL) AS with_image,
                   count(*) FILTER (WHERE n."imageCheckedAt" IS NOT NULL) AS checked,
                   count(*) AS recent
              FROM "News" n JOIN "Asset" a ON a.id = n."assetId"
             WHERE a."assetType" = 'crypto'
               AND n."publishedAt" >= now() - interval '7 days'
        ''')[0]
        print(f"  crypto, last 7 days: {total['with_image']} of {total['recent']} have an image "
              f"({total['checked']} looked at)")
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
