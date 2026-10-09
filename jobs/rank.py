"""Rank each industry four ways.

  size         size at 2021-12-31, the pre-AI picture
  sizeNow      size at the latest stored close, the post-AI picture
  totalReturn  return between 2019-12-31 and 2021-12-31, and 2021-12-31 to today
  rising       24 month return minus the industry average, checked against volume

Size is market cap, or fund size for funds, or absent. An asset with no stored size
gets no size rank and the page says so. Nothing is backfilled.

Run: python jobs/rank.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import PRE_AI_END, RISING_MONTHS, SNAPSHOTS, db, mean, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

PRE_AI_START = SNAPSHOTS[0]
CAP_LABEL = {
    "marketCap": "market capitalisation",
    "fundAssets": "fund size",
    "none": None,
}


def closes_on(cur, asset_ids: list[str], target: date) -> dict[str, dict]:
    """{assetId: the newest stored row at or before `target`} for a whole industry at once.

    This was a query per asset, and the three callers below ran it twice each, so one industry
    cost six round trips per name and the job cost about 2,500 for the universe. On a host in
    the database's own region that is seconds; from anywhere else it was 17 minutes of a
    2h50m run, and it grows with every name added to the pool.

    The row is picked exactly as the per-asset version picked it: newest date at or before the
    target, whether or not it carries a close. The callers already test `close` themselves,
    and filtering here would silently substitute an older row where the old code skipped the
    asset.
    """
    if not asset_ids:
        return {}
    got = rows(
        cur,
        """
        SELECT DISTINCT ON ("assetId") "assetId" AS aid, date, close, volume, "marketCap"
        FROM "PriceSnapshot"
        WHERE "assetId" = ANY(%s) AND date <= %s
        ORDER BY "assetId", date DESC
        """,
        (asset_ids, target),
    )
    return {g["aid"]: g for g in got}


def upsert_many(cur, recs: list[dict]) -> int:
    """Every ranking row for one basis in one statement.

    `executemany` rather than a hand-built VALUES list: psycopg pipelines it into a single
    round trip and the conflict clause stays exactly as it was, which matters because this
    table is rewritten in full on every run and the clause is what makes a rerun idempotent.
    """
    if not recs:
        return 0
    cur.executemany(
        """
        INSERT INTO "Ranking"
          ("industryId", "assetId", basis, "periodStart", "periodEnd", rank,
           "sizeRank", value, source, note)
        VALUES (%(industryId)s, %(assetId)s, %(basis)s::"RankingBasis",
                %(periodStart)s, %(periodEnd)s, %(rank)s, %(sizeRank)s,
                %(value)s, %(source)s, %(note)s)
        ON CONFLICT ("industryId", basis, "periodEnd", "assetId") DO UPDATE
        SET rank = EXCLUDED.rank, "sizeRank" = EXCLUDED."sizeRank",
            value = EXCLUDED.value, source = EXCLUDED.source, note = EXCLUDED.note,
            "periodStart" = EXCLUDED."periodStart"
        """,
        recs,
    )
    return len(recs)


def latest_caps(cur, industry_id: str, target: date) -> dict[str, dict]:
    """{assetId: the newest stored market cap at or before `target`}, for a whole industry.

    This replaces two queries that asked the same question in two different shapes: a correlated
    `date = (SELECT max(date) ... WHERE assetId = ps."assetId")` in `size_ranks`, and a second
    read in `write_size` that pulled every non-null market cap row at or before the target so it
    could pick the newest per asset in Python -- the same answer, fetched again, because the
    first query selected the figure and not the day it was measured on. `DISTINCT ON` returns
    both at once, so the pair becomes one.

    **The cost here is round trips, not query plans, and it is worth being exact about that.**
    Measured against the live endpoint on 2026-10-09, three industries each: the old correlated
    form took 239-271ms, the old full read 239-253ms, and this one 328-336ms. Every one of those
    is dominated by the ~250ms it takes to reach the database at all; this query is genuinely a
    little more work than either of the two it replaces, and still halves the time because it
    replaces *both*. 335ms against 515ms.

    The larger half is how often they ran. The same two (industry, date) pairs were asked for
    seven times per industry -- five size reads and two full scans -- and are now asked for twice.
    Over 41 industries that is 287 round trips reduced to 82, around 50 seconds of a job whose
    per-query gain alone would have been nil. The ratchet in tests/test_brain.py records the
    in-loop count falling from 14 to 3 for the same reason.

    The row carries the date as well as the figure because the note printed beside a rank quotes
    the day the size was measured on, and that day is a property of the row rather than of the run.

    Absent where the asset has published no size at all -- which is the state the page describes
    in words. Nothing is backfilled here and nothing is ranked on a missing figure.
    """
    got = rows(
        cur,
        """
        SELECT DISTINCT ON (ps."assetId")
               ps."assetId" AS aid, ps.date, ps."marketCap" AS cap
        FROM "PriceSnapshot" ps
        JOIN "Asset" a ON a.id = ps."assetId"
        WHERE a."industryId" = %s AND ps.date <= %s AND ps."marketCap" IS NOT NULL
        ORDER BY ps."assetId", ps.date DESC
        """,
        (industry_id, target),
    )
    return {g["aid"]: g for g in got}


def size_ranks(caps: dict[str, dict]) -> dict[str, int]:
    """1 is largest. Assets with no stored size on that date are simply absent.

    Takes the rows rather than a cursor, because the same (industry, date) pair is asked for up
    to three times in one industry -- once by each of the two size bases and again by every
    return basis that prints a size rank beside its own -- and it is one ordering of one list.
    """
    ordered = sorted(caps.items(), key=lambda kv: kv[1]["cap"], reverse=True)
    return {aid: i + 1 for i, (aid, _) in enumerate(ordered)}


def write_size(cur, caps: dict[str, dict], industry, basis: str) -> int:
    sranks = size_ranks(caps)
    if not sranks:
        return 0
    assets = rows(
        cur,
        'SELECT id, name, "capBasis", source FROM "Asset" WHERE "industryId" = %s',
        (industry["id"],),
    )

    by_id = {a["id"]: a for a in assets}
    recs = []
    for aid, rank in sorted(sranks.items(), key=lambda kv: kv[1]):
        a = by_id[aid]
        label = CAP_LABEL.get(a["capBasis"])
        cap = caps[aid]
        recs.append({
            "industryId": industry["id"],
            "assetId": aid,
            "basis": basis,
            "periodStart": None,
            "periodEnd": cap["date"],
            "rank": rank,
            "sizeRank": rank,
            "value": float(cap["cap"]),
            "source": a["source"],
            "note": f"{label} on {cap['date']}, price times shares outstanding",
        })
    return upsert_many(cur, recs)


def write_returns(cur, sranks: dict[str, int], industry, start: date, end: date, basis: str) -> int:
    assets = rows(
        cur,
        'SELECT id, name, source FROM "Asset" WHERE "industryId" = %s',
        (industry["id"],),
    )
    ids = [a["id"] for a in assets]
    starts = closes_on(cur, ids, start)
    ends = closes_on(cur, ids, end)
    scored = []
    for a in assets:
        a_start, a_end = starts.get(a["id"]), ends.get(a["id"])
        if not a_start or not a_end or not a_start["close"]:
            continue
        ret = (a_end["close"] / a_start["close"] - 1.0) * 100.0
        scored.append((a, a_start, a_end, ret))

    scored.sort(key=lambda t: t[3], reverse=True)
    recs = []
    for i, (a, a_start, a_end, ret) in enumerate(scored, start=1):
        recs.append({
            "industryId": industry["id"],
            "assetId": a["id"],
            "basis": basis,
            "periodStart": a_start["date"],
            "periodEnd": a_end["date"],
            "rank": i,
            "sizeRank": sranks.get(a["id"]),
            "value": ret,
            "source": a["source"],
            "note": f"close {a_start['close']:.4g} on {a_start['date']} to {a_end['close']:.4g} on {a_end['date']}",
        })
    return upsert_many(cur, recs)


def write_rising(cur, sranks: dict[str, int], industry, today: date) -> int:
    start = today - timedelta(days=RISING_MONTHS * 30)
    assets = rows(
        cur,
        'SELECT id, name, source FROM "Asset" WHERE "industryId" = %s',
        (industry["id"],),
    )
    ids = [a["id"] for a in assets]
    starts = closes_on(cur, ids, start)
    ends = closes_on(cur, ids, today)
    now_vols = avg_volumes(cur, ids, today, 60)

    # The "then" window ends sixty days after each asset's own starting session, and those
    # sessions are nearly all the same day -- the newest close at or before one fixed date.
    # Grouping by that date turns a query per asset into a query per distinct starting day,
    # which in practice is one or two.
    by_start_day: dict[date, list[str]] = {}
    for a in assets:
        a_start = starts.get(a["id"])
        if a_start:
            by_start_day.setdefault(a_start["date"], []).append(a["id"])
    then_vols: dict[str, float] = {}
    for day, group in by_start_day.items():
        then_vols.update(avg_volumes(cur, group, day + timedelta(days=60), 60))

    scored = []
    for a in assets:
        a_start, a_end = starts.get(a["id"]), ends.get(a["id"])
        if not a_start or not a_end or not a_start["close"]:
            continue
        ret = (a_end["close"] / a_start["close"] - 1.0) * 100.0
        vol_now = now_vols.get(a["id"])
        vol_then = then_vols.get(a["id"])
        if vol_now is None or vol_then is None or vol_then == 0:
            vol_note = "volume trend unavailable, source did not publish volume for this asset"
            vol_up = None
        else:
            vol_up = vol_now / vol_then
            vol_note = f"60 day average volume {'up' if vol_up >= 1 else 'down'} {(vol_up - 1) * 100:.0f}%"
        scored.append((a, a_start, a_end, ret, vol_up, vol_note))

    if not scored:
        return 0
    industry_avg = mean([s[3] for s in scored])
    excess = [
        (a, a_start, a_end, ret - industry_avg, vol_up, vol_note)
        for a, a_start, a_end, ret, vol_up, vol_note in scored
    ]
    excess.sort(key=lambda t: t[3], reverse=True)
    recs = []
    for i, (a, a_start, a_end, ex, vol_up, vol_note) in enumerate(excess, start=1):
        recs.append(
            {
                "industryId": industry["id"],
                "assetId": a["id"],
                "basis": "rising",
                "periodStart": a_start["date"],
                "periodEnd": a_end["date"],
                "rank": i,
                "sizeRank": sranks.get(a["id"]),
                "value": ex,
                "source": a["source"],
                "note": f"{RISING_MONTHS} month return against industry average. {vol_note}",
            },
        )
    return upsert_many(cur, recs)


def avg_volumes(cur, asset_ids: list[str], end: date, days: int) -> dict[str, float]:
    """{assetId: mean stored volume over the `days` days ending at `end`}, one query.

    Absent where the asset published no volume in the window, which is what the caller tests:
    an asset with no volume gets the words "volume trend unavailable" rather than a zero.
    """
    if not asset_ids:
        return {}
    got = rows(
        cur,
        """
        SELECT "assetId" AS aid, avg(volume) AS v FROM "PriceSnapshot"
        WHERE "assetId" = ANY(%s) AND date <= %s AND date > %s AND volume IS NOT NULL
        GROUP BY "assetId"
        """,
        (asset_ids, end, end - timedelta(days=days)),
    )
    return {g["aid"]: g["v"] for g in got if g["v"] is not None}


def rank_industry(cur, ind, today: date) -> None:
    """Every basis for one industry, inside one short transaction the caller commits.

    The two size reads happen once each and are then passed down, rather than being asked for
    again by each basis that prints a size rank. Five reads of the same two (industry, date)
    pairs become two -- see `latest_caps` for why each one was expensive as well as repeated.
    """
    pre_caps = latest_caps(cur, ind["id"], PRE_AI_END)
    now_caps = latest_caps(cur, ind["id"], today)
    now_ranks = size_ranks(now_caps)

    # Scoped to this industry and run immediately before its rows are rewritten, instead of one
    # `DELETE FROM "Ranking"` across the whole table at the top of the run. Same effect -- a
    # `periodEnd` moves day to day, so the upsert alone would accumulate yesterday's rows -- and
    # three properties the global delete did not have:
    #
    #   * the table is never empty. The old shape deleted everything and then spent the rest of
    #     the run refilling it inside one uncommitted transaction, so a reader arriving mid-run
    #     saw either the old rows or, if the run failed late, no rankings at all.
    #   * a failed industry costs that industry. The others are already committed.
    #   * the transaction is seconds long rather than the whole run, which is what makes a
    #     pooled connection safe to hold -- the fault rule 33 and the news lane both name.
    cur.execute('DELETE FROM "Ranking" WHERE "industryId" = %s', (ind["id"],))

    n = write_size(cur, pre_caps, ind, "size")
    print(f"  size at {PRE_AI_END}: {n} assets with a stored size")
    n = write_size(cur, now_caps, ind, "sizeNow")
    print(f"  size now: {n} assets with a stored size")
    # Two windows under one basis, and both are read -- which is worth stating here
    # because it does not look that way from the website. /industry/[slug] shows only
    # the second one ("Return since 2021"), so the pre-AI rows appear to be written and
    # never used, and an audit of the web layer alone concludes exactly that.
    #
    # They are used by jobs/analysis.py, which separates the two with
    # `periodEnd <= PRE_AI_END` in industry_shift() and again in the per-asset writer,
    # and turns the pair into the stored prose the site then displays. Deleting this
    # call would not drop a dead row; it would quietly empty half of every industry's
    # analysis.
    #
    # The two windows are also why the read path cannot simply take the newest
    # periodEnd per asset -- see RANKING_WINDOW_LAG_DAYS in lib/rankingWindow.ts.
    #
    # The size rank printed beside the pre-AI window is the pre-AI one, which is the pairing the
    # old code had: it called `size_ranks(..., end)` with that window's own end date.
    n = write_returns(cur, size_ranks(pre_caps), ind, PRE_AI_START, PRE_AI_END, "totalReturn")
    print(f"  pre-AI return: {n} assets")
    n = write_returns(cur, now_ranks, ind, PRE_AI_END, today, "totalReturn")
    print(f"  post-AI return: {n} assets")
    n = write_rising(cur, now_ranks, ind, today)
    print(f"  rising: {n} assets")


def main() -> None:
    conn = db()
    today = date.today()
    cur = conn.cursor()
    industries = rows(cur, 'SELECT id, slug, name FROM "Industry" ORDER BY sort')

    failed: list[str] = []
    for ind in industries:
        step(ind["name"])
        try:
            rank_industry(cur, ind, today)
            conn.commit()
        except psycopg.OperationalError as e:
            # The drop the news lane was losing three hours to, handled where it can only cost
            # one industry. The transaction this industry was in is gone with the connection, so
            # the retry starts it again from its own `DELETE` -- which is why that delete is
            # inside `rank_industry` and not above the loop.
            print(f"  database connection lost ({type(e).__name__}), reconnecting and retrying")
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - it is already gone; this is tidiness
                pass
            conn = db()
            cur = conn.cursor()
            try:
                rank_industry(cur, ind, today)
                conn.commit()
            except Exception as e2:  # noqa: BLE001
                conn.rollback()
                failed.append(ind["name"])
                print(f"  {ind['name']} failed after a reconnect: {e2}")
        except Exception as e:  # noqa: BLE001
            # One industry's rows are not worth the other fourteen. Rolled back so the next
            # industry starts clean, recorded, and reported as a non-zero exit at the end.
            conn.rollback()
            failed.append(ind["name"])
            print(f"  {ind['name']} failed: {e}")

    cur.execute('SELECT basis, count(*) AS n FROM "Ranking" GROUP BY basis ORDER BY basis')
    for got in cur.fetchall():
        print(f"{got['basis']:12} {got['n']}")
    conn.commit()
    conn.close()

    if failed:
        print(f"\n{len(failed)} of {len(industries)} industries failed: {', '.join(failed)}")
        print("The rows the others committed are kept.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
