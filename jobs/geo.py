"""Where attention for each product sits geographically, from Google Trends' own breakdown.

Resolutions, as verified against the live source on 2026-10-01 with a real product term:

    COUNTRY, worldwide      works, 175 countries returned a non-zero value
    REGION, inside US       works, 51 states
    REGION, inside PK       works, 5 provinces
    CITY, inside US         returns an EMPTY frame

So the site publishes countries and regions, and states plainly that city demand is not
available from a free source. It does not substitute a metro guess for the metro data that
does not exist.

What a value is
---------------
Not a volume. Trends returns 0-100 normalised inside the area asked about, so 100 means
"the highest in this list" and carries no information about how many searches that was.
Values from different lists are not comparable, and values for different products are not
comparable with each other either.

The consequence is the small-denominator problem, arriving through a different door from the
Reddit counts. On the term used to verify this, Tonga scored 87 and St. Helena 75 against the
Netherlands at 59; Wyoming scored 100 against California at 24. Those are not findings about
Tongan or Wyoming demand, they are what a normalised share does when the denominator is
small. Nothing here can correct it without population data this site does not carry, so
SMALL_AREA_NOTE is attached to every published table instead, and a top-ranked area is never
described as the place demand is concentrated on the strength of its rank alone.

Run: python jobs/geo.py
Writes: ProductRegion
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

from urllib3.util.retry import Retry  # noqa: E402

# pytrends still passes method_whitelist, which urllib3 2.x removed. Same shim as
# jobs/signals.py, for the same reason: pinning urllib3 would break every other job.
_orig_retry = Retry.__init__


def _retry_init(self, *a, **kw):
    if "method_whitelist" in kw:
        kw["allowed_methods"] = kw.pop("method_whitelist")
    return _orig_retry(self, *a, **kw)


Retry.__init__ = _retry_init

TRENDS = "Google Trends regional breakdown"
TIMEFRAME = "today 12-m"

# What to ask for. Worldwide countries, then states inside each market the site covers, so a
# reader on the Pakistan pages gets a breakdown of their own market rather than only the US.
BREAKDOWNS = (
    ("country", "", "COUNTRY"),
    ("region", "US", "REGION"),
    ("region", "PK", "REGION"),
)

# How many places to keep per list. The tail of a Trends breakdown is mostly zeros and
# single digits, and storing 175 rows per product per run would be mostly noise.
KEEP = 15

# Trends rate limits hard. One term per request here, so the run is 30 products times three
# breakdowns; the delay is what keeps that from turning into a wall of 429s.
DELAY = 8.0
ATTEMPTS = 3


def fetch(term: str, resolution: str, geo: str):
    """One breakdown, or None when the source would not answer.

    None is a missing measurement. It is never turned into an empty table that would read as
    "no interest anywhere", which is a different and much stronger claim.
    """
    from pytrends.request import TrendReq

    for attempt in range(ATTEMPTS):
        try:
            pt = TrendReq(hl="en-US", tz=0, timeout=(10, 30), retries=1, backoff_factor=0.5)
            pt.build_payload([term], timeframe=TIMEFRAME, geo=geo)
            frame = pt.interest_by_region(resolution=resolution, inc_low_vol=True)
            if frame is None or frame.empty or term not in frame.columns:
                # An empty frame is the source's way of saying it holds nothing at this
                # resolution. That is the answer for CITY, and it is recorded as absent.
                return []
            got = [
                (str(name), float(value))
                for name, value in frame[term].items()
                if value and float(value) > 0
            ]
            got.sort(key=lambda kv: kv[1], reverse=True)
            return got
        except Exception as e:  # noqa: BLE001
            print(f"    attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:70]}")
            time.sleep(15 * (attempt + 1))
    return None


def save(cur, product_id: str, scope: str, geo: str, places: list, end: date) -> int:
    written = 0
    for i, (name, value) in enumerate(places[:KEEP], start=1):
        cur.execute(
            """
            INSERT INTO "ProductRegion" ("productId", scope, geo, name, value, rank,
                                         "periodEnd", timeframe, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT ("productId", scope, geo, name, "periodEnd") DO UPDATE
            SET value = EXCLUDED.value, rank = EXCLUDED.rank,
                timeframe = EXCLUDED.timeframe, source = EXCLUDED.source
            """,
            (product_id, scope, geo, name, value, i, end, TIMEFRAME, TRENDS),
        )
        written += 1
    return written


def main() -> None:
    end = date.today()

    # Phase 1: ask what to fetch, then hang up. Same rule psx.py follows: this job spends
    # minutes on the network and a transaction held open across that is a session sitting
    # idle in transaction, which serverless Postgres closes underneath the run.
    conn = db()
    with conn, conn.cursor() as cur:
        products = rows(
            cur,
            'SELECT id, name, "trendsTerm" FROM "Product" '
            "WHERE \"trendsTerm\" <> '' ORDER BY name",
        )
    conn.close()

    if not products:
        print("no products carry a Trends term, nothing to do")
        return

    step(f"regional breakdown for {len(products)} products")
    collected: list[tuple] = []
    refused = 0
    for p in products:
        print(f"  {p['name']}")
        for scope, geo, resolution in BREAKDOWNS:
            places = fetch(p["trendsTerm"], resolution, geo)
            where = geo or "worldwide"
            if places is None:
                print(f"    {scope} {where}: no answer, left unmeasured")
                refused += 1
            elif not places:
                print(f"    {scope} {where}: source holds nothing at this resolution")
            else:
                print(f"    {scope} {where}: {len(places)} places, top {places[0][0]}")
                collected.append((p["id"], scope, geo, places))
            time.sleep(DELAY)

    # Phase 2: a fresh connection, writes only, committed per product.
    step("write")
    conn = db()
    cur = conn.cursor()
    try:
        written = 0
        for product_id, scope, geo, places in collected:
            written += save(cur, product_id, scope, geo, places, end)
            conn.commit()
        print(f"  {written} rows over {len(collected)} breakdowns, {refused} unanswered")
        cur.execute(
            """
            SELECT scope, geo, count(*) AS n, count(DISTINCT "productId") AS products
            FROM "ProductRegion" WHERE "periodEnd" = %s
            GROUP BY scope, geo ORDER BY scope, geo
            """,
            (end,),
        )
        for got in cur.fetchall():
            print(
                f"  {got['scope']:8} {got['geo'] or 'worldwide':10} "
                f"{got['n']:>5} rows over {got['products']:>3} products"
            )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
