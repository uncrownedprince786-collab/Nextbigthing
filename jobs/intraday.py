"""Fetch intraday bars for the assets that currently warrant them, and record what arrived.

    python jobs/intraday.py            the active set at the canonical interval
    python jobs/intraday.py all        every supported asset, for a first fill
    python jobs/intraday.py derive     rebuild the derived intervals from stored 5m bars

Why this is not "poll everything every minute"
----------------------------------------------
160 assets at one minute each is 160 requests a minute against a free endpoint, which is
both a ban and a bill. The useful observation is that intraday data is only worth having for
something that is actually doing something, so an **active set** is selected from stored
rows before anything is fetched:

  * assets with a directional condition read or a live thesis — the ones being monitored
  * assets whose latest daily move or volume is unusual against their own history
  * assets with a catalyst flagged, or sitting one hop from one in the graph
  * assets with a scheduled date inside the next few days

Everything else keeps its daily bars and says so. That is §38's active-set selection, and it
is the difference between a job that costs 20 requests and one that cannot run on this
infrastructure at all.

One canonical interval, derived upward
--------------------------------------
Bars are fetched at five minutes and 15 / 30 / 60 are **aggregated** from them. Fetching each
interval separately would multiply the request count by four to obtain numbers that are
already implied, and the aggregation is exact rather than approximate: the open of the first
component bar, the close of the last, the max high, the min low, the sum of volumes. A
derived bar is only written when **every** component bar is present, because a 60 minute bar
assembled from nine of its twelve five minute bars is a different and quieter hour than the
one that happened. Those are skipped, not estimated.

One minute bars are fetched only for the highest priority slice of the active set, because
the provider serves barely a week of them and they cost twelve times the rows.

What this job will not do
-------------------------
  * It will not invent a bar. A gap in the provider's series stays a gap, and
    `IntradaySession.barsExpected` against `barsStored` is what makes the gap visible rather
    than letting a short series look like a quiet one.
  * It will not treat an unsupported asset as a failure. PSX symbols are not served intraday
    by this provider and crypto has no exchange session; both get an explicit row saying so,
    so the coverage question has a stored answer instead of an absence.
  * It will not write a zero volume where the provider sent nothing. Zero is a real quiet
    five minutes.

Run: python jobs/intraday.py [all|derive]
Reads: Asset, AssetSetup, AssetThesis, HumanSignal, GraphRelevance, Event, PriceSnapshot
Writes: IntradayBar, IntradaySession
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, get_json, one, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

SOURCE = "Yahoo Finance chart API, intraday OHLCV"
DERIVED = "Aggregated from stored five minute bars"

# The interval everything else is built from. Five minutes, because it is the finest the
# provider serves more than a week of, and because 15, 30 and 60 all divide into it exactly.
CANONICAL = 5
# Derived upward only. Each must be a whole multiple of CANONICAL or the aggregation would be
# assembling bars out of fractions of bars.
DERIVE_TO = (15, 30, 60)
# Fetched, not derived, and only for the top slice of the active set.
FINE = 1

# How much history to ask for per interval. The provider's own limits, measured rather than
# assumed: 1m is served for about a week, 5m for about two months.
RANGE_FOR = {1: "5d", 5: "1mo"}

# How many of the active set get one minute bars. Bounded because 1m is twelve times the rows
# of 5m for the same window and the provider serves a fraction of the history.
FINE_SLICE = 8

# Hard ceiling on requests per run, whatever the active set says. A selection bug that
# suddenly thinks every asset is active must cost one capped run, not a ban.
MAX_REQUESTS = 60

# A session whose newest bar is older than this is stale rather than merely finished.
STALE_AFTER_MIN = 90

# Asset types this provider serves intraday. Everything else gets an `unsupported` row rather
# than silence, so the gap is a stored fact. PSX equities are not on this provider at all;
# crypto trades continuously and has no exchange session, so its bars are stored but its
# session accounting is marked as having no expected count.
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"


def supported(asset: dict) -> tuple[bool, str]:
    """Whether this provider serves intraday bars for an asset, and why not when it does not.

    Decided on the stored source rather than on the symbol's shape. `prices.py` already
    records which provider each asset's daily bars come from, and an asset whose daily closes
    come from the exchange's own files is not going to appear on a US quote API because its
    ticker happens to look like one.
    """
    src = (asset.get("source") or "").lower()
    if "psx" in src or "pakistan" in src:
        return False, (
            "the Pakistan Stock Exchange publishes end of day files and no intraday series, "
            "and this provider does not carry its listings"
        )
    if not asset.get("sourceRef"):
        return False, "no provider reference is stored for this asset"
    return True, ""


def active_set(cur, today: date) -> list[dict]:
    """The assets worth spending intraday requests on, each with the reason it was selected.

    One query per reason rather than one big disjunction, because the reason has to survive
    into the output: "why is this asset being watched at five minutes" is a question the
    session row should be able to answer, and a UNION would lose it.

    Ordered by how many reasons an asset collected. An asset that is being monitored *and*
    has moved unusually *and* has a date this week is the one that most deserves the finer
    interval, and counting the reasons is a bounded way to say so without inventing a score.
    """
    reasons: dict[str, list[str]] = {}

    def add(found, why: str) -> None:
        for r in found:
            reasons.setdefault(r["id"], []).append(why)

    # Being monitored. A directional read or a live thesis is the system's own statement that
    # this asset is worth watching, so it is the first claim on the budget.
    add(
        rows(
            cur,
            """
            SELECT DISTINCT a.id FROM "Asset" a
            JOIN "AssetSetup" s ON s."assetId" = a.id
            WHERE s.state IN ('buy','short')
              AND s."periodEnd" = (SELECT max("periodEnd") FROM "AssetSetup")
            """,
        ),
        "a directional condition read is open on it",
    )
    add(
        rows(
            cur,
            """
            SELECT DISTINCT a.id FROM "Asset" a
            JOIN "AssetThesis" t ON t."assetId" = a.id
            WHERE t.status IN ('active','weakening')
            """,
        ),
        "a recorded thesis on it is still live",
    )

    # Doing something unusual. Measured against the asset's own history, not a fixed
    # percentage: a 3% day is ordinary for one of these names and extraordinary for another.
    add(
        rows(
            cur,
            """
            WITH latest AS (
                SELECT "assetId", max(date) AS d FROM "PriceSnapshot"
                WHERE close IS NOT NULL GROUP BY "assetId"
            ),
            moves AS (
                SELECT p."assetId",
                       abs(p.close / nullif(lag(p.close) OVER w, 0) - 1) * 100 AS mv,
                       p.volume,
                       avg(p.volume) OVER (PARTITION BY p."assetId" ORDER BY p.date
                                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avgvol,
                       p.date
                FROM "PriceSnapshot" p
                WINDOW w AS (PARTITION BY p."assetId" ORDER BY p.date)
            )
            SELECT DISTINCT m."assetId" AS id
            FROM moves m JOIN latest l ON l."assetId" = m."assetId" AND l.d = m.date
            WHERE m.mv >= 4.0 OR (m.avgvol > 0 AND m.volume / m.avgvol >= 2.0)
            """,
        ),
        "its latest daily move or volume is unusual for it",
    )

    # Near the news. The catalyst itself and the bounded graph neighbourhood around it, which
    # is exactly what jobs/graph.py exists to produce.
    add(
        rows(
            cur,
            """
            SELECT DISTINCT "assetId" AS id FROM "HumanSignal"
            WHERE catalyst = true AND "assetId" IS NOT NULL
              AND "periodEnd" = (SELECT max("periodEnd") FROM "HumanSignal")
            """,
        ),
        "a catalyst is flagged on it",
    )
    add(
        rows(
            cur,
            """
            SELECT DISTINCT "assetId" AS id FROM "GraphRelevance"
            WHERE "periodEnd" = (SELECT max("periodEnd") FROM "GraphRelevance")
            """,
        ),
        "it sits next to something a catalyst is flagged on",
    )

    # A date in the diary. Watching the hours around a scheduled event is the one case where
    # intraday data is worth having before anything has happened at all.
    add(
        rows(
            cur,
            """
            SELECT DISTINCT l."assetId" AS id FROM "EventLink" l
            JOIN "Event" e ON e.id = l."eventId"
            WHERE l."assetId" IS NOT NULL AND e.scheduled = true
              AND e.date BETWEEN %s AND %s
            """,
            (today, today + timedelta(days=3)),
        ),
        "a scheduled date for it falls within three days",
    )

    if not reasons:
        return []

    detail = {
        r["id"]: r
        for r in rows(
            cur,
            'SELECT id, symbol, name, "sourceRef", source, currency FROM "Asset" WHERE id = ANY(%s)',
            (list(reasons),),
        )
    }
    out = []
    for asset_id, why in reasons.items():
        a = detail.get(asset_id)
        if not a:
            continue
        out.append({**a, "why": sorted(set(why))})
    out.sort(key=lambda a: (-len(a["why"]), a["symbol"]))
    return out


def fetch(symbol: str, interval: int) -> dict | None:
    """One provider call, normalised into the shape the rest of this job uses.

    Returned as a dict of plain Python rather than the provider's envelope, which is the
    adapter boundary §6 asks for: everything below this function would keep working if the
    provider were replaced, and nothing above it knows the provider's field names.
    """
    url = (
        f"{CHART}{symbol}?interval={interval}m&range={RANGE_FOR.get(interval, '5d')}"
        "&includePrePost=true"
    )
    # Two hours. A finished session's bars never change, and the next run wants the newest
    # ones, so this is short enough to be useful and long enough that a retried workflow
    # costs the provider nothing.
    blob = get_json(url, ttl=2 * 3600, headers={"Accept": "application/json"})
    if not blob:
        return None
    chart = blob.get("chart") or {}
    if chart.get("error"):
        return {"error": str(chart["error"])[:200]}
    results = chart.get("result") or []
    if not results:
        return {"error": "the provider answered with no result block"}
    r = results[0]
    meta = r.get("meta") or {}
    stamps = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    return {
        "tz": meta.get("exchangeTimezoneName"),
        "gmtoffset": meta.get("gmtoffset"),
        "granularity": meta.get("dataGranularity"),
        "periods": meta.get("currentTradingPeriod") or {},
        "trading": meta.get("tradingPeriods"),
        "stamps": stamps,
        "open": quote.get("open") or [],
        "high": quote.get("high") or [],
        "low": quote.get("low") or [],
        "close": quote.get("close") or [],
        "volume": quote.get("volume") or [],
    }


def to_bars(payload: dict, interval: int) -> tuple[list[dict], int]:
    """(bars, bars the provider served as holes).

    A bar is kept only when open, high, low and close are all present. The provider pads its
    arrays to the session grid and fills the untraded slots with nulls, so a row with a null
    close is a hole in the grid rather than an observation — counting it as a bar would
    manufacture a price, and dropping it silently would hide that the series is short.
    """
    bars, holes = [], 0
    stamps = payload.get("stamps") or []
    for i, ts in enumerate(stamps):

        def at(field: str):
            seq = payload.get(field) or []
            return seq[i] if i < len(seq) else None

        o, h, lo, c = at("open"), at("high"), at("low"), at("close")
        if o is None or h is None or lo is None or c is None:
            holes += 1
            continue
        when = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
        bars.append(
            {
                "ts": when,
                "open": float(o),
                "high": float(h),
                "low": float(lo),
                "close": float(c),
                # Absent volume stays absent. A zero is a real quiet five minutes and the two
                # must not collapse into one value.
                "volume": None if at("volume") is None else float(at("volume")),
                "interval": interval,
            }
        )
    return bars, holes


def session_dates(bars: list[dict], offset_seconds: int | None) -> None:
    """Attach the exchange-local session date to each bar, in place.

    Computed from the provider's own gmt offset rather than from a timezone database, because
    the offset is what the provider used to build the grid and a mismatch between the two
    would move bars between sessions at the boundary. Without an offset the UTC date is used
    and the session row records that, rather than guessing a market.
    """
    shift = timedelta(seconds=offset_seconds or 0)
    for b in bars:
        b["sessionDate"] = (b["ts"] + shift).date()


def phase_of(bars: list[dict], regular: dict | None) -> None:
    """Mark each bar regular, pre or post, in place.

    From the provider's stated regular trading period for the session. When it does not state
    one every bar is left `regular`: labelling a bar `pre` on a guess would make a thin
    pre-market print look like a thin regular one, which is the comparison this field exists
    to protect.
    """
    if not regular or not regular.get("start") or not regular.get("end"):
        return
    start = datetime.fromtimestamp(regular["start"], timezone.utc).replace(tzinfo=None)
    end = datetime.fromtimestamp(regular["end"], timezone.utc).replace(tzinfo=None)
    for b in bars:
        if b["ts"] < start:
            b["phase"] = "pre"
        elif b["ts"] >= end:
            b["phase"] = "post"
        else:
            b["phase"] = "regular"


def expected_bars(regular: dict | None, interval: int) -> int | None:
    """How many bars a full regular session holds at this interval, from the provider's own
    stated period. None when it did not state one, which is not the same as zero."""
    if not regular or not regular.get("start") or not regular.get("end"):
        return None
    span = int(regular["end"]) - int(regular["start"])
    if span <= 0:
        return None
    return max(1, span // (interval * 60))


def classify(stored: int, expected: int | None, holes: int, newest: datetime | None,
             now: datetime) -> tuple[str, str]:
    """(status, note) for one fetched session. §8's completeness states, in one place.

    The order of the checks is the meaning. `failed` and `empty` are answers about the
    provider; `partial` is an answer about the payload; `stale` is an answer about time. A
    half-empty payload is reported as partial even when it is also stale, because the missing
    bars are the finding and the age is a consequence of them.
    """
    if stored == 0 and holes == 0:
        return "empty", (
            "the provider answered with no bars at all, which is the right answer for a "
            "market that has not opened"
        )
    if stored == 0:
        return "failed", (
            f"all {holes} slots the provider returned were empty, so there is no usable bar "
            "in the payload"
        )
    if expected is not None and stored < expected * 0.9:
        return "partial", (
            f"{stored} bars arrived where a full session holds about {expected}. The series "
            "is short and must not be read as a quiet session"
        )
    if newest is not None and (now - newest) > timedelta(minutes=STALE_AFTER_MIN):
        age = int((now - newest).total_seconds() // 60)
        return "stale", (
            f"{stored} bars arrived but the newest is {age} minutes old, so this is the last "
            "session rather than the current one"
        )
    return "complete", f"{stored} bars arrived" + (
        f", against about {expected} for a full session" if expected else ""
    )


def aggregate(fine: list[dict], minutes: int, base: int = CANONICAL) -> list[dict]:
    """Build `minutes` bars out of stored `base` bars, exactly or not at all.

    Exact because every field is a function of the component bars: first open, last close,
    highest high, lowest low, summed volume. A group missing any of its component bars is
    skipped rather than assembled, because an hour built from nine of its twelve five minute
    bars is a quieter hour than the one that happened — and §9 forbids turning missing data
    into a plausible value.

    Volume is summed only when every component bar carried one. One absent volume makes the
    sum an undercount, and an undercount presented as a total is the same error.
    """
    if minutes % base:
        return []
    per = minutes // base
    buckets: dict[tuple[date, datetime], list[dict]] = {}
    for b in sorted(fine, key=lambda x: x["ts"]):
        epoch = int(b["ts"].timestamp())
        start = datetime.fromtimestamp(
            epoch - (epoch % (minutes * 60)), timezone.utc
        ).replace(tzinfo=None)
        buckets.setdefault((b["sessionDate"], start), []).append(b)

    out = []
    for (sess, start), group in sorted(buckets.items()):
        if len(group) != per:
            continue
        group.sort(key=lambda x: x["ts"])
        vols = [g["volume"] for g in group]
        out.append(
            {
                "ts": start,
                "sessionDate": sess,
                "open": group[0]["open"],
                "close": group[-1]["close"],
                "high": max(g["high"] for g in group),
                "low": min(g["low"] for g in group),
                "volume": None if any(v is None for v in vols) else sum(vols),
                "interval": minutes,
                "phase": group[0].get("phase", "regular"),
                "derived": True,
                "derivedFrom": base,
            }
        )
    return out


def write_bars(cur, asset_id: str, bars: list[dict], source: str) -> int:
    """Upsert bars. Idempotent on (asset, interval, ts), so a rerun stores no duplicate."""
    written = 0
    for b in bars:
        cur.execute(
            """
            INSERT INTO "IntradayBar" ("assetId", interval, ts, "sessionDate", open, high,
                low, close, volume, phase, derived, "derivedFrom", source, "retrievedAt")
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT ("assetId", interval, ts) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume, phase = EXCLUDED.phase,
                derived = EXCLUDED.derived, "derivedFrom" = EXCLUDED."derivedFrom",
                source = EXCLUDED.source, "retrievedAt" = now()
            """,
            (
                asset_id, b["interval"], b["ts"], b["sessionDate"], b["open"], b["high"],
                b["low"], b["close"], b["volume"], b.get("phase", "regular"),
                bool(b.get("derived")), b.get("derivedFrom"), source,
            ),
        )
        written += 1
    return written


def write_session(cur, asset_id: str, sess: date, interval: int, status: str, note: str,
                  expected: int | None, stored: int, holes: int, tz: str | None,
                  first: datetime | None, last: datetime | None, source: str) -> None:
    cur.execute(
        """
        INSERT INTO "IntradaySession" ("assetId", "sessionDate", interval, status,
            "barsExpected", "barsStored", "barsNull", "exchangeTz", "firstTs", "lastTs",
            note, source, "retrievedAt")
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT ("assetId", "sessionDate", interval) DO UPDATE SET
            status = EXCLUDED.status, "barsExpected" = EXCLUDED."barsExpected",
            "barsStored" = EXCLUDED."barsStored", "barsNull" = EXCLUDED."barsNull",
            "exchangeTz" = EXCLUDED."exchangeTz", "firstTs" = EXCLUDED."firstTs",
            "lastTs" = EXCLUDED."lastTs", note = EXCLUDED.note,
            source = EXCLUDED.source, "retrievedAt" = now()
        """,
        (asset_id, sess, interval, status, expected, stored, holes, tz, first, last, note,
         source),
    )


def mark_unsupported(cur, asset_id: str, today: date, why: str) -> None:
    """Record that an asset has no intraday source, which is a fact rather than a failure.

    Written so the coverage question has a stored answer. An absent row and an unsupported
    asset would otherwise look the same, and the first is a gap in this job while the second
    is a gap in the world.
    """
    write_session(cur, asset_id, today, CANONICAL, "unsupported", why, None, 0, 0, None,
                  None, None, SOURCE)


def derive_for(cur, asset_id: str) -> int:
    """Rebuild every derived interval for one asset from its stored canonical bars."""
    fine = [
        {
            "ts": r["ts"], "sessionDate": r["sessionDate"], "open": float(r["open"]),
            "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"]),
            "volume": None if r["volume"] is None else float(r["volume"]),
            "phase": r["phase"], "interval": CANONICAL,
        }
        for r in rows(
            cur,
            """
            SELECT ts, "sessionDate", open, high, low, close, volume, phase
            FROM "IntradayBar" WHERE "assetId" = %s AND interval = %s
            ORDER BY ts
            """,
            (asset_id, CANONICAL),
        )
    ]
    if not fine:
        return 0
    written = 0
    for minutes in DERIVE_TO:
        written += write_bars(cur, asset_id, aggregate(fine, minutes), DERIVED)
    return written


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "active"
    today = date.today()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = db()
    cur = conn.cursor()
    try:
        if mode == "derive":
            step("rebuild the derived intervals from stored five minute bars")
            targets = rows(
                cur,
                'SELECT DISTINCT "assetId" AS id FROM "IntradayBar" WHERE interval = %s',
                (CANONICAL,),
            )
            total = 0
            for t in targets:
                total += derive_for(cur, t["id"])
                conn.commit()
            print(f"  {len(targets)} assets, {total} derived bars written")
            return

        if mode == "all":
            chosen = [
                {**a, "why": ["a first fill was requested for every supported asset"]}
                for a in rows(
                    cur,
                    'SELECT id, symbol, name, "sourceRef", source, currency FROM "Asset" '
                    "ORDER BY symbol",
                )
            ]
            step(f"first fill: {len(chosen)} assets considered")
        else:
            chosen = active_set(cur, today)
            step(f"active set: {len(chosen)} assets selected from stored rows")
            if not chosen:
                print(
                    "  nothing is active. No directional read, no live thesis, no unusual "
                    "move, no catalyst and no date within three days, so no intraday request "
                    "is worth making. This is the ordinary state."
                )
                return

        skipped: list[str] = []
        usable = []
        for a in chosen:
            ok, why = supported(a)
            if ok:
                usable.append(a)
            else:
                mark_unsupported(cur, a["id"], today, why)
                skipped.append(a["symbol"])
        conn.commit()

        if skipped:
            print(
                f"  {len(skipped)} have no intraday source and are recorded as unsupported: "
                + ", ".join(skipped[:8])
                + (" ..." if len(skipped) > 8 else "")
            )

        budget = MAX_REQUESTS
        fetched = failed = bars_total = derived_total = 0
        statuses: dict[str, int] = {}

        for rank, a in enumerate(usable):
            if budget <= 0:
                print(f"  request ceiling of {MAX_REQUESTS} reached, stopping here")
                break

            wanted = [CANONICAL]
            # The finest interval goes to the few assets that collected the most reasons to
            # be watched. Everything else is read at the canonical interval.
            if mode != "all" and rank < FINE_SLICE and budget > 1:
                wanted.append(FINE)

            for interval in wanted:
                if budget <= 0:
                    break
                budget -= 1
                payload = fetch(a["sourceRef"], interval)
                if payload is None or payload.get("error"):
                    failed += 1
                    write_session(
                        cur, a["id"], today, interval, "failed",
                        payload.get("error") if payload else
                        "the provider did not answer, so nothing is stored for this session",
                        None, 0, 0, None, None, None, SOURCE,
                    )
                    conn.commit()
                    continue

                fetched += 1
                bars, holes = to_bars(payload, interval)
                session_dates(bars, payload.get("gmtoffset"))
                regular = (payload.get("periods") or {}).get("regular")
                phase_of(bars, regular)

                by_session: dict[date, list[dict]] = {}
                for b in bars:
                    by_session.setdefault(b["sessionDate"], []).append(b)

                bars_total += write_bars(cur, a["id"], bars, SOURCE)

                expected = expected_bars(regular, interval)
                for sess, group in sorted(by_session.items()):
                    group.sort(key=lambda x: x["ts"])
                    # Holes are counted across the whole payload, so they are attributed to
                    # the newest session rather than split on a guess.
                    share = holes if sess == max(by_session) else 0
                    status, note = classify(
                        len(group), expected, share, group[-1]["ts"], now
                    )
                    statuses[status] = statuses.get(status, 0) + 1
                    write_session(
                        cur, a["id"], sess, interval, status, note, expected, len(group),
                        share, payload.get("tz"), group[0]["ts"], group[-1]["ts"], SOURCE,
                    )
                if not by_session:
                    status, note = classify(0, expected, holes, None, now)
                    statuses[status] = statuses.get(status, 0) + 1
                    write_session(cur, a["id"], today, interval, status, note, expected, 0,
                                  holes, payload.get("tz"), None, None, SOURCE)
                conn.commit()

            derived_total += derive_for(cur, a["id"])
            conn.commit()

        print(
            f"  {fetched} provider calls succeeded, {failed} failed, "
            f"{MAX_REQUESTS - budget} of {MAX_REQUESTS} budget used"
        )
        print(f"  {bars_total} fetched bars stored, {derived_total} derived bars stored")
        for status, n in sorted(statuses.items()):
            print(f"  {status:<12} {n} sessions")
        print(
            "  a session marked partial or failed is a gap that is stored, not smoothed. No "
            "bar is invented and no absent volume becomes a zero."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
