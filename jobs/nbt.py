"""Shared helpers for every NextBigThing data job.

Three rules live here so no job can break them:
  * every HTTP call goes through get(), which caches to disk and sleeps between calls
  * every number written to Postgres carries the source that produced it
  * nothing is ever filled in. A source that did not answer produces no row.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
CACHE.mkdir(exist_ok=True)

USER_AGENT = (
    "NextBigThing/1.0 (open source market data reader; "
    "contact: set CONTACT_EMAIL in the repository .env)"
)
CONTACT = os.environ.get("CONTACT_EMAIL", "nextbigthing@example.invalid")

# Last close on or before this date, for each snapshot the product compares.
SNAPSHOTS = [
    date(2019, 12, 31),
    date(2021, 12, 31),
    date(2023, 12, 29),
    date(2025, 12, 31),
]
PRE_AI_END = date(2021, 12, 31)
RISING_MONTHS = 24

# The only five signals that make up a product demand score, as (source, metric, label).
# Long window Trends and Wikipedia rows are stored for the record but deliberately not
# scored, so a product that has both an 8 week and a 26 week reading is never counted as
# two independent sources. Defined once here because jobs/confidence.py and jobs/analysis.py
# both have to agree on exactly this list.
SCORED_SIGNALS = (
    ("googleTrends", "trends_8w_vs_8w_pct", "Google Trends search interest, 8 weeks against the 8 before"),
    ("wikipedia", "wiki_views_8w_vs_8w_pct", "Wikipedia pageviews, 8 weeks against the 8 before"),
    ("hackerNews", "hn_stories_90d_change_pct", "Hacker News stories, 90 days against the 90 before"),
    ("reddit", "reddit_posts_30d_change_pct", "Reddit posts, the last 30 days against the rate over the 90 days before"),
    ("googleNews", "gnews_articles_30d_change_pct", "Google News articles, 30 days against the 30 before"),
)

# A source whose name is used in a sentence with a verb needs to agree with that verb.
SOURCE_LABEL = {
    "googleTrends": "Google Trends",
    "wikipedia": "Wikipedia pageviews",
    "reddit": "Reddit",
    "hackerNews": "Hacker News",
    "googleNews": "Google News",
}

# Counts that feed a product read. A source that has not returned a value is not counted
# here, and it is never treated as a zero.
PRODUCT_SOURCES_HIGH = 4
PRODUCT_SOURCES_MEDIUM = 2

_ctx = ssl.create_default_context()

# Per host minimum seconds between requests. Measured, not guessed: these hosts
# return 429 for anything faster.
HOST_DELAY = {
    "www.reddit.com": 9.0,
    "old.reddit.com": 9.0,
    "trends.google.com": 6.0,
    "en.wikipedia.org": 1.5,
    "api.coingecko.com": 6.0,
    "api.coinpaprika.com": 1.5,
    "hn.algolia.com": 1.0,
    "news.google.com": 2.0,
    "data.sec.gov": 0.5,
    # The exchange's own file server. It answers quickly and a full backfill is a few
    # hundred small files, but it is a national exchange rather than a CDN, so it gets
    # the same courtesy as the rest.
    "dps.psx.com.pk": 1.5,
    "www.amazon.com": 4.0,
    # The quote API jobs/intraday.py reads. Measured: it tolerates roughly a request a second
    # for small volumes and starts answering 429 above that. 1.5s with a per-run request
    # ceiling in the job is what keeps an intraday run inside the free allowance.
    "query1.finance.yahoo.com": 1.5,
    # The crypto close venues. Each is asked once per coin, ten coins a run, and all four
    # publish a rate limit well above that; the delays below are the conservative end of what
    # each documents, so a run cannot trip a limit even when every coin falls through to the
    # last venue. Declared rather than defaulted because a venue added without a delay is a
    # venue nobody chose a rate for.
    "api.binance.com": 0.5,
    "api.exchange.coinbase.com": 0.5,
    "api.kraken.com": 1.0,
    "www.bitstamp.net": 1.0,
}
_last_hit: dict[str, float] = {}


def _host_delay(url: str) -> float:
    host = urllib.parse.urlparse(url).netloc.lower()
    return HOST_DELAY.get(host, 1.0)


# Transient codes worth asking again for. 403 is not here: a block is an answer, and asking
# again just spends the lane's time confirming it.
RETRY_ON = (429, 500, 502, 503, 504)
RETRIES = 2                    # three attempts in all
RETRY_BACKOFF = (3, 12)        # seconds before the second and third attempt

# The ceiling that makes retrying safe. Without it a source that is down costs every URL its
# full backoff — 15 seconds times a few hundred feeds is the daily lane's whole timeout spent
# on a host that is not answering. After this many retried attempts the host gets one try per
# URL for the rest of the run, which is how it behaved before retries existed.
RETRY_HOST_BUDGET = 8
_retry_spent: dict[str, int] = {}


def may_retry(host: str, attempt: int, spent: dict[str, int] | None = None) -> bool:
    """Whether to ask `host` again, charged against its budget for this run."""
    if attempt >= RETRIES:
        return False
    book = _retry_spent if spent is None else spent
    if book.get(host, 0) >= RETRY_HOST_BUDGET:
        return False
    book[host] = book.get(host, 0) + 1
    return True


def get(
    url: str,
    *,
    cache_key: str | None = None,
    ttl: int = 6 * 3600,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> bytes | None:
    """Fetch with an on-disk cache and a per-host delay. None on any failure.

    A transient failure is retried up to RETRIES times with a growing pause, because losing a
    feed for the day to one 503 is worse than waiting fifteen seconds. A host that keeps
    failing stops being retried once it has spent RETRY_HOST_BUDGET, so a dead source cannot
    consume the lane.
    """
    host = urllib.parse.urlparse(url).netloc.lower()
    key = cache_key or url
    path = CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    if path.exists():
        blob = json.loads(path.read_text("utf-8"))
        if time.time() - blob["at"] < ttl:
            return b64decode(blob["body"])

    wait = _host_delay(url) - (time.time() - _last_hit.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)

    hdrs = {
        "User-Agent": f"{USER_AGENT} {CONTACT}" if host.endswith("reddit.com") else USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        hdrs.update(headers)

    raw = None
    for attempt in range(RETRIES + 1):
        # Stamped when the request *leaves*, not when the answer arrives.
        #
        # HOST_DELAY is a minimum gap between requests, and measuring it from the end of the
        # previous one made the real gap `delay + however long that host took to answer`. For
        # Google News at a 2 second delay and roughly a second of latency, every feed cost
        # three seconds instead of two -- and the news lane asks for 548 of them, so a third of
        # its runtime was the job waiting on a clock it had already satisfied.
        #
        # The host sees exactly the same rate either way: one request every HOST_DELAY seconds
        # at most. What changes is that this process stops idling between them. A request that
        # takes *longer* than the delay still spaces the next one naturally, because the gap is
        # measured from a point already in the past.
        _last_hit[host] = time.time()
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            # 429 means back off hard for this host for the rest of the run.
            if e.code in (429, 403, 503):
                _last_hit[host] = time.time() + 30
                print(f"  blocked {host} {e.code}, backing off 30s")
            if e.code in RETRY_ON and may_retry(host, attempt):
                print(f"  retry {attempt + 1} of {RETRIES} after {e.code} {url[:80]}")
                time.sleep(RETRY_BACKOFF[attempt])
                continue
            print(f"  FAIL {e.code} {url[:100]}")
            return None
        except Exception as e:  # noqa: BLE001 - a dead source must not kill a job
            # A timeout or a reset is the case retrying was added for.
            if may_retry(host, attempt):
                print(f"  retry {attempt + 1} of {RETRIES} after {type(e).__name__} {url[:80]}")
                time.sleep(RETRY_BACKOFF[attempt])
                continue
            print(f"  FAIL {type(e).__name__} {url[:100]}")
            return None
    if raw is None:
        return None

    path.write_text(
        json.dumps({"at": time.time(), "url": url, "body": b64encode(raw)}), "utf-8"
    )
    return raw


def b64decode(text: str) -> bytes:
    import base64

    return base64.b64decode(text)


def b64encode(raw: bytes) -> str:
    import base64

    return base64.b64encode(raw).decode()


def get_json(url: str, **kw):
    raw = get(url, **kw)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        print(f"  FAIL json decode {url[:100]}")
        return None


def db():
    url = os.environ["DATABASE_URL"]
    # libpq does not know Prisma's channel_binding parameter. Keepalives matter because
    # these jobs sit idle between statements while a source answers slowly, and Neon's
    # pooler drops idle connections.
    q = urllib.parse.urlsplit(url)
    params = urllib.parse.parse_qsl(q.query)
    params = [(k, v) for k, v in params if k != "channel_binding"]
    params += [
        ("keepalives", "1"),
        ("keepalives_idle", "20"),
        ("keepalives_interval", "5"),
        ("keepalives_count", "3"),
    ]
    url = urllib.parse.urlunsplit(
        (q.scheme, q.netloc, q.path, urllib.parse.urlencode(params), q.fragment)
    )
    conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=20)
    conn.execute("SET TIME ZONE 'UTC'")
    return conn


class Link:
    """A database connection that survives the server closing it.

    Written for the news lane and useful to any job shaped like it. That job spends hours
    asking feeds for headlines and only milliseconds writing them, so its connection sits idle
    almost all of the time -- and a pooled Postgres closes an idle connection inside a long
    transaction. Measured twice on 2026-10-08 at 477 assets: "server closed the connection
    unexpectedly" at around 323 names, both times, losing every row the lane had collected
    because the whole run was one transaction.

    Two properties, and both matter:

      * **A write is retried once on a dropped connection, against a fresh one.** A drop is an
        ordinary event here, not a fault to fail the lane for.
      * **The caller commits as it goes.** This class cannot make a three-hour transaction
        safe; it makes a dropped connection cost one asset instead of the whole afternoon. A
        caller that still holds everything open until the end gets a reconnect and an empty
        transaction, which is the same loss with extra steps.

    It deliberately does not retry reads. Every read in these jobs happens at the start of a
    run, while the connection is new, and a read that fails there is a fault worth stopping on.
    """

    def __init__(self):
        self.conn = db()
        self.cur = self.conn.cursor()

    def _revive(self) -> None:
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001 — it is already gone; this is tidiness
            pass
        self.conn = db()
        self.cur = self.conn.cursor()

    def execute(self, sql, params=None):
        try:
            self.cur.execute(sql, params or ())
        except psycopg.OperationalError as e:
            print(f"  database connection lost ({type(e).__name__}), reconnecting")
            self._revive()
            self.cur.execute(sql, params or ())
        return self.cur.rowcount

    def commit(self) -> None:
        try:
            self.conn.commit()
        except psycopg.OperationalError:
            # Nothing to salvage: the server has the rows or it does not, and a commit that
            # cannot reach it means it does not. The next write reconnects and carries on.
            print("  database connection lost at commit, reconnecting")
            self._revive()

    def close(self) -> None:
        try:
            self.cur.close()
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass


def rows(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def one(cur, sql, params=None):
    got = rows(cur, sql, params)
    return got[0] if got else None


def d(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def ymd(value: date) -> str:
    return value.isoformat()


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def pct(a: float, b: float) -> float | None:
    """Percent change from b to a. None when b is unusable, never zero-filled."""
    if b is None or a is None or b == 0:
        return None
    return (a / b - 1.0) * 100.0


def mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def median(xs: list[float]) -> float | None:
    """Middle value. Unlike the mean this is not dragged around by a single outlier, which
    matters here because a 8000% crypto return would otherwise describe nobody's peers."""
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def step(label: str) -> None:
    print(f"\n== {label}", flush=True)
