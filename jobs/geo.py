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

Fill or explicit empty, never a silent zero
-------------------------------------------
This job used to end three ways and report two of them as success: it filled the table, or the
source refused it and it exited 0 with nothing written, or something stopped it before its one
final write and it lost a run it had already done. The last two are the ones that mattered,
because `ProductRegion` sat at zero rows for weeks under a note claiming the job "works but
keeps being cancelled", and both halves of that note were true at once.

So three changes, and all three are about the ending rather than the fetching:

  * every product is committed as it is collected, so an interrupted run keeps what it got
  * the fetch phase has a budget (FETCH_BUDGET_MINUTES) and stops on its own terms, naming the
    products it never asked about, instead of being killed mid-run by the lane deadline
  * a run that stored nothing exits non-zero with the reason — refused, or answered and empty —
    which are different facts about the source and must not collapse into one blank table

Run: python jobs/geo.py
Writes: ProductRegion
"""

from __future__ import annotations

import os
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

# How long to wait before asking again, times the attempt number. A refused breakdown therefore
# costs 15 + 30 + 45 = 90 seconds before it is given up on, which is what makes the budget below
# necessary rather than cautious: a run where a third of the breakdowns are refused spends more
# time sleeping off refusals than it spends fetching.
RETRY_SLEEP = 15.0

# The ceiling on the whole fetch phase, in minutes, and the reason this job stopped being a
# source of zero rows.
#
# `.github/workflows/refresh.yml` gives the weekly lane 90 minutes for twenty-two steps, and its
# own comment names "the 90 minute deadlock a hung geo fetch once caused". Ninety breakdowns at
# 8 seconds of courtesy delay is twelve minutes before a single request is counted, and measured
# against the live source on 2026-10-03 the real figure was far worse: Trends begins refusing
# part way through a run of this size, and every refusal adds RETRY_SLEEP's 90 seconds on top.
# So the job was reliably still fetching when the lane ran out of time.
#
# 45 minutes is half the lane. A job that cannot finish inside half the lane it shares with
# twenty-one others should stop and report what it got, which it can now afford to do because
# every product is committed as it is collected.
#
# Checked before every breakdown rather than only between products, which is the second version
# of this guard and the one that is true. The first checked between products on the reasoning
# that a product's three breakdowns belong together, and measured against a rate limited Trends
# on 2026-10-03 that let the run reach 75 minutes while still on its second product: a single
# refused breakdown can cost many minutes, so "one product's overshoot" is not a small number.
#
# Abandoning a product part way is fine, which was the thing the first version got wrong. A
# ProductRegion row is a place inside one (scope, geo) list and nothing reads across lists, so a
# product with a country breakdown and no US breakdown is a product with one fewer table, not a
# corrupt one. That already happens whenever PK returns nothing. What is not fine is leaving it
# unsaid, so a part-asked product is named in the summary.
# Overridable with GEO_FETCH_BUDGET_MIN: the products lane runs geo in a 35 minute job after the
# marketplace fetch and sets 18 there; 45 was longer than that job, so geo never wrote a row.
FETCH_BUDGET_MINUTES = float(os.environ.get("GEO_FETCH_BUDGET_MIN") or 45.0)


def why(exc: BaseException) -> str:
    """The HTTP status behind a pytrends exception, when there is one to find.

    This exists because the log was unreadable in exactly the way that matters. pytrends asks
    through urllib3 with its own Retry attached, so a rate limit does not arrive as anything
    recognisable: urllib3 exhausts its retries and raises `RetryError`, the status is gone, and
    the job printed "attempt 1 failed: RetryError: HTTPSConnectionPool..." for hours. Three days
    of that log is what let the cause be written down as "queue churn".

    Asked directly on 2026-10-03 the same endpoint answered `429 Too Many Requests` with
    `<title>Error 429 (Too Many Requests)!!1</title>`, which is a different problem with a
    different fix from a timeout or a DNS failure. So the chain is walked for a status, and the
    run says 429 when it means 429.
    """
    seen: list[BaseException] = []
    node: BaseException | None = exc
    while node is not None and node not in seen:
        seen.append(node)
        for attr in ("status", "code", "status_code"):
            value = getattr(getattr(node, "response", node), attr, None)
            if isinstance(value, int) and 100 <= value < 600:
                return f"HTTP {value}"
        node = node.__cause__ or node.__context__

    # No status survived the retry wrapper. Fall back to the text, which still carries it often
    # enough to be worth reading: pytrends puts "429" in the message of its own rate limit error.
    text = " ".join(str(e) for e in seen)
    for code in ("429", "503", "502", "403", "500"):
        if code in text:
            return f"HTTP {code} (read out of the message, not a status field)"
    return type(exc).__name__


def fetch(term: str, resolution: str, geo: str):
    """One breakdown, or None when the source would not answer.

    None is a missing measurement. It is never turned into an empty table that would read as
    "no interest anywhere", which is a different and much stronger claim.
    """
    from pytrends.request import TrendReq

    for attempt in range(ATTEMPTS):
        try:
            # retries=0 on purpose, and it is the other half of why this job used to be
            # unreadable and unbounded. pytrends hands its `retries` to urllib3, so with
            # retries=1 every attempt below was itself several requests with their own backoff
            # — two retry policies stacked, which is both why the status never survived to be
            # printed (see why()) and why one "attempt" could sit on the network for minutes.
            # The loop in this function is the retry policy; urllib3 does not need a second one.
            pt = TrendReq(hl="en-US", tz=0, timeout=(10, 30), retries=0, backoff_factor=0)
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
            print(
                f"    attempt {attempt + 1} failed: {why(e)} "
                f"({type(e).__name__}: {str(e)[:60]})"
            )
            time.sleep(RETRY_SLEEP * (attempt + 1))
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


def store(product_id: str, collected: list[tuple], end: date) -> int:
    """One product's breakdowns, committed, on a connection that is opened and closed here.

    This replaces a second phase that held every product's results in memory and wrote the lot
    at the end, and it is the reason `ProductRegion` stood at zero rows while the source was
    verified working. The two facts were never in conflict: Trends answers, and the job
    collected real breakdowns for forty minutes, and then anything that stopped it before the
    final write — a lane deadline, a cancellation, an unhandled error anywhere in the loop —
    threw away the entire run. A job whose output is all-or-nothing after forty minutes on a
    rate limited source will produce nothing most of the time, and it did.

    Committing per product costs one connect and close per product, roughly thirty over a run,
    which is nothing beside the eight second courtesy delay between fetches. What it buys is
    that a run killed at minute forty keeps the thirty-nine minutes it had already earned.

    Short-lived on purpose, and for the original reason: the network waits happen outside this
    function, so no transaction is ever open while a source is answering slowly. That is what
    used to leave a session idle in transaction for Neon's pooler to drop underneath the run.
    """
    if not collected:
        return 0
    conn = db()
    cur = conn.cursor()
    try:
        written = 0
        for scope, geo, places in collected:
            written += save(cur, product_id, scope, geo, places, end)
        conn.commit()
        return written
    finally:
        cur.close()
        conn.close()


def summarise(end: date) -> None:
    """What is actually in the table for today, read back rather than counted in memory."""
    conn = db()
    cur = conn.cursor()
    try:
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


def main() -> None:
    end = date.today()

    # Ask what to fetch, then hang up. Same rule psx.py follows: this job spends minutes on the
    # network and a transaction held open across that is a session sitting idle in transaction,
    # which serverless Postgres closes underneath the run.
    conn = db()
    with conn, conn.cursor() as cur:
        # Least recently covered first, and the ordering is the whole point of this query.
        #
        # This was `ORDER BY name` under a fetch budget, which is a combination that cannot
        # work: the budget is reached partway down a fixed list, and the next run starts at the
        # same end of the same list. Measured 2026-10-07, after this job had been running for
        # weeks: all 30 products carry a Trends term, and exactly 9 had any region rows at all
        # -- Air fryer, Coffee grinder, Dash cam, Drone delivery, Electric bike, Espresso
        # machine, EV charging, GPU compute, Heat pump. They are the first nine alphabetically.
        # The 21 products from "Home battery" onward had **never** been asked about and never
        # would be, and nothing in the run said so: each run reported its own budget cut
        # honestly and then threw the position away.
        #
        # So the list is ordered by how stale each product's own coverage is, nulls first. A
        # product never covered sorts above every covered one, and among covered ones the
        # oldest goes first. The budget then rotates: the names the last run could not reach are
        # at the top of this one. Over a few runs every product is covered, and from then on the
        # job always refreshes the oldest reading rather than re-asking about the freshest.
        #
        # `name` stays as the tiebreak so the order is still deterministic — two products with
        # the same coverage date must not swap places between runs and re-split the budget
        # differently each time.
        products = rows(
            cur,
            """
            SELECT p.id, p.name, p."trendsTerm"
              FROM "Product" p
              LEFT JOIN (
                SELECT "productId", max("periodEnd") AS covered
                  FROM "ProductRegion" GROUP BY "productId"
              ) r ON r."productId" = p.id
             WHERE p."trendsTerm" <> ''
             ORDER BY r.covered ASC NULLS FIRST, p.name
            """,
        )
    conn.close()

    if not products:
        # Not an empty measurement. Nothing was asked of the source, so there is nothing to
        # record about it, and this is a seeding problem rather than a coverage one.
        print("no products carry a Trends term, nothing to do")
        return

    step(f"regional breakdown for {len(products)} products")
    # Printed because the order is now load-bearing and invisible otherwise. A run that always
    # names the same first product is the fault this ordering fixes, reappearing.
    print(
        "  least recently covered first: "
        + ", ".join(p["name"] for p in products[:4])
        + (" ..." if len(products) > 4 else "")
    )
    deadline = time.monotonic() + FETCH_BUDGET_MINUTES * 60
    written = refused = holds_nothing = answered = 0
    unfetched: list[str] = []

    for p in products:
        collected: list[tuple] = []
        skipped = 0
        printed = False
        for scope, geo, resolution in BREAKDOWNS:
            if time.monotonic() > deadline:
                # Out of budget. What was not asked is counted separately from what did not
                # answer, because only the second says anything about the source, and a run that
                # reported them together would be blaming Trends for the clock.
                skipped += 1
                continue
            if not printed:
                print(f"  {p['name']}")
                printed = True
            places = fetch(p["trendsTerm"], resolution, geo)
            where = geo or "worldwide"
            if places is None:
                print(f"    {scope} {where}: no answer, left unmeasured")
                refused += 1
            elif not places:
                print(f"    {scope} {where}: source holds nothing at this resolution")
                holds_nothing += 1
            else:
                print(f"    {scope} {where}: {len(places)} places, top {places[0][0]}")
                answered += 1
                collected.append((scope, geo, places))
            time.sleep(DELAY)

        n = store(p["id"], collected, end)
        written += n
        if n:
            print(f"    committed {n} rows")
        if skipped:
            unfetched.append(
                f"{p['name']} ({len(BREAKDOWNS) - skipped} of {len(BREAKDOWNS)} asked)"
            )

    step("what today holds")
    print(
        f"  {written} rows written. {answered} breakdowns answered, {refused} were refused, "
        f"{holds_nothing} the source holds nothing for"
    )
    if unfetched:
        print(
            f"  {len(unfetched)} products were cut short by the "
            f"{FETCH_BUDGET_MINUTES:.0f} minute fetch budget, so the source was never asked "
            "about them and nothing here is a statement about their demand: "
            + ", ".join(unfetched[:6])
            + (" ..." if len(unfetched) > 6 else "")
        )
    summarise(end)

    # Rule 31. A run that stored nothing has to say which of two very different things happened,
    # and then fail, because the alternative is what this job used to do: print some refusals,
    # exit 0, and leave the table empty with a green tick next to it. The freshness panel reads
    # an empty `ProductRegion` as "not answering" either way — see `WATCHED` in jobs/audit.py —
    # and this is the reason that goes with it.
    if written == 0:
        if refused and not answered:
            raise SystemExit(
                f"\nnothing stored: every one of the {refused} breakdowns asked for was refused "
                "by trends.google.com after "
                f"{ATTEMPTS} attempts. That is a rate limit or a block on this host, not an "
                "absence of search interest, and no table here may be read as 'no interest "
                "anywhere'. Re-verify the source before trusting the next run."
            )
        if holds_nothing and not answered:
            raise SystemExit(
                f"\nnothing stored: the source answered all {holds_nothing} breakdowns and held "
                "no data at any of these resolutions. This is an explicit empty rather than a "
                "failure to reach it, and it is a change in what Trends publishes: the country "
                "and region breakdowns were verified non-empty on 2026-10-03, so re-verify "
                "BREAKDOWNS against the live source."
            )
        if refused and holds_nothing:
            raise SystemExit(
                f"\nnothing stored: of the breakdowns asked for, {refused} were refused and "
                f"{holds_nothing} were answered empty, and none returned a place. Both halves "
                "need reading before the next run is trusted, because only the first is a "
                "statement about reaching the source."
            )
        raise SystemExit(
            f"\nnothing stored because nothing was asked: the {FETCH_BUDGET_MINUTES:.0f} minute "
            f"fetch budget was already spent when the first of {len(products)} products came up. "
            "This says nothing at all about Trends. Something before this job in the lane took "
            "the time, or the budget is set below what one product costs."
        )


if __name__ == "__main__":
    main()
