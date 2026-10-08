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


def size_ranks(cur, industry_id: str, target: date) -> dict[str, int]:
    """1 is largest. Assets with no stored size on that date are simply absent."""
    got = rows(
        cur,
        """
        SELECT ps."assetId" AS aid, ps."marketCap" AS cap
        FROM "PriceSnapshot" ps
        JOIN "Asset" a ON a.id = ps."assetId"
        WHERE a."industryId" = %s AND ps.date = (
            SELECT max(p2.date) FROM "PriceSnapshot" p2
            WHERE p2."assetId" = ps."assetId" AND p2.date <= %s
              AND p2."marketCap" IS NOT NULL
        ) AND ps."marketCap" IS NOT NULL
        ORDER BY ps."marketCap" DESC
        """,
        (industry_id, target),
    )
    return {g["aid"]: i + 1 for i, g in enumerate(got)}


def write_size(cur, industry, target: date, basis: str) -> int:
    sranks = size_ranks(cur, industry["id"], target)
    if not sranks:
        return 0
    assets = rows(
        cur,
        'SELECT id, name, "capBasis", source FROM "Asset" WHERE "industryId" = %s',
        (industry["id"],),
    )
    cap_day = rows(
        cur,
        """
        SELECT ps."assetId" AS aid, ps.date, ps."marketCap" AS cap
        FROM "PriceSnapshot" ps
        WHERE ps."assetId" = ANY(%s) AND ps."marketCap" IS NOT NULL
          AND ps.date <= %s
        """,
        ([a["id"] for a in assets], target),
    )
    latest_cap: dict[str, dict] = {}
    for row in cap_day:
        if row["aid"] not in latest_cap or row["date"] > latest_cap[row["aid"]]["date"]:
            latest_cap[row["aid"]] = row

    by_id = {a["id"]: a for a in assets}
    recs = []
    for aid, rank in sorted(sranks.items(), key=lambda kv: kv[1]):
        a = by_id[aid]
        label = CAP_LABEL.get(a["capBasis"])
        recs.append({
            "industryId": industry["id"],
            "assetId": aid,
            "basis": basis,
            "periodStart": None,
            "periodEnd": latest_cap[aid]["date"],
            "rank": rank,
            "sizeRank": rank,
            "value": float(latest_cap[aid]["cap"]),
            "source": a["source"],
            "note": f"{label} on {latest_cap[aid]['date']}, price times shares outstanding",
        })
    return upsert_many(cur, recs)


def write_returns(cur, industry, start: date, end: date, basis: str) -> int:
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

    sranks = size_ranks(cur, industry["id"], end)
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


def write_rising(cur, industry, today: date) -> int:
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
    sranks = size_ranks(cur, industry["id"], today)
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


def main() -> None:
    conn = db()
    today = date.today()
    with conn, conn.cursor() as cur:
        industries = rows(cur, 'SELECT id, slug, name FROM "Industry" ORDER BY sort')
        cur.execute('DELETE FROM "Ranking"')

        for ind in industries:
            step(ind["name"])
            n = write_size(cur, ind, PRE_AI_END, "size")
            print(f"  size at {PRE_AI_END}: {n} assets with a stored size")
            n = write_size(cur, ind, today, "sizeNow")
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
            n = write_returns(cur, ind, PRE_AI_START, PRE_AI_END, "totalReturn")
            print(f"  pre-AI return: {n} assets")
            n = write_returns(cur, ind, PRE_AI_END, today, "totalReturn")
            print(f"  post-AI return: {n} assets")
            n = write_rising(cur, ind, today)
            print(f"  rising: {n} assets")

        cur.execute(
            'SELECT basis, count(*) AS n FROM "Ranking" GROUP BY basis ORDER BY basis'
        )
        for got in cur.fetchall():
            print(f"{got['basis']:12} {got['n']}")
    conn.close()


if __name__ == "__main__":
    main()
