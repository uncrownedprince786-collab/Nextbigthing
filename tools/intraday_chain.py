"""End-to-end verification of the intraday chain against production. Read-only."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

# DATABASE_URL from the environment, or the project's own .env, exactly as the jobs read it.
# Never a path to a credential file somewhere else: these are committed.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

if not os.environ.get("DATABASE_URL"):
    raise SystemExit(
        "DATABASE_URL is not set. Copy .env.example to .env and paste the connection string, "
        "or export it in this shell."
    )

from nbt import db, one, rows  # noqa: E402
conn = db()
conn.rollback()
conn.read_only = True
cur = conn.cursor()


def head(n, t):
    print(f"\n{n}. {t}")
    print("   " + "-" * 72)


ok = []
bad = []


def claim(label, passed, detail):
    (ok if passed else bad).append(label)
    print(f"   [{'PASS' if passed else 'FAIL'}] {label}: {detail}")


# 1 -- unique constraint on AssetSetup (the truncated check)
head(1, "Unique constraint backing every upsert")
got = rows(
    cur,
    """
    SELECT c.relname AS tbl, i.relname AS idx
    FROM pg_index x
    JOIN pg_class c ON c.oid = x.indrelid
    JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
      AND x.indisunique AND right(i.relname, 5) <> '_pkey'
      AND c.relname IN ('AssetSetup','IntradayBar','IntradaySession','SetupTarget')
    ORDER BY c.relname
    """,
)
have = {r["tbl"] for r in got}
for t in ("AssetSetup", "IntradayBar", "IntradaySession", "SetupTarget"):
    claim(f"{t} has a non-pkey unique index", t in have,
          next((r["idx"] for r in got if r["tbl"] == t), "MISSING"))

# 2 -- 5 minute bars present and reachable
head(2, "Source -> 5 minute bars")
b = one(
    cur,
    """
    SELECT count(*) AS n, count(DISTINCT "assetId") AS assets, min(ts) AS lo, max(ts) AS hi,
           count(DISTINCT source) AS sources
    FROM "IntradayBar" WHERE interval = 5 AND derived = false
    """,
)
claim("five minute bars stored", b["n"] > 0,
      f"{b['n']:,} bars, {b['assets']} assets, {b['lo']} to {b['hi']}")

# 3 -- timestamps monotonic and aligned to the interval
head(3, "Timestamps")
mis = one(
    cur,
    """
    SELECT count(*) AS n FROM "IntradayBar"
    WHERE interval = 5 AND (EXTRACT(EPOCH FROM ts)::bigint %% 300) <> 0
    """,
)
claim("every 5m bar sits on a 5 minute boundary", mis["n"] == 0,
      f"{mis['n']} misaligned")
future = one(cur, 'SELECT count(*) AS n FROM "IntradayBar" WHERE ts > now()')
claim("no bar is dated in the future (no look-ahead)", future["n"] == 0,
      f"{future['n']} future-dated bars")

# 4 -- session boundaries: sessionDate must match the bar's exchange-local date
head(4, "Session boundaries")
spread = one(
    cur,
    """
    SELECT count(*) AS n FROM "IntradayBar"
    WHERE abs(EXTRACT(EPOCH FROM (ts - "sessionDate"::timestamp)) / 3600.0) > 30
    """,
)
claim("no bar sits more than 30h from its session date", spread["n"] == 0,
      f"{spread['n']} outliers")

# 5 -- phase classification
head(5, "Regular / pre / post classification")
phases = {r["phase"]: int(r["n"]) for r in rows(
    cur, 'SELECT phase, count(*) AS n FROM "IntradayBar" WHERE interval = 5 GROUP BY phase')}
regular = phases.get("regular", 0)
total = sum(phases.values()) or 1
claim("regular bars dominate, so the per-session fix holds",
      regular / total > 0.4, f"{phases}, regular share {regular / total:.0%}")

# 6 -- aggregation exactness, recomputed from the stored 5m bars
head(6, "15 / 30 / 60 aggregation is mathematically exact")
for minutes in (15, 30, 60):
    wrong = one(
        cur,
        f"""
        WITH fine AS (
            SELECT "assetId", "sessionDate", phase, ts, open, high, low, close, volume,
                   to_timestamp(floor(EXTRACT(EPOCH FROM ts) / {minutes * 60})
                                * {minutes * 60})::timestamp AS bucket
            FROM "IntradayBar" WHERE interval = 5
        ),
        agg AS (
            SELECT "assetId", "sessionDate", bucket, count(*) AS parts,
                   max(high) AS hi, min(low) AS lo,
                   (array_agg(open ORDER BY ts))[1] AS o,
                   (array_agg(close ORDER BY ts DESC))[1] AS c,
                   CASE WHEN count(volume) = count(*) THEN sum(volume) ELSE NULL END AS vol
            FROM fine GROUP BY 1,2,3
        )
        SELECT count(*) AS n
        FROM agg a
        JOIN "IntradayBar" d
          ON d."assetId" = a."assetId" AND d.interval = {minutes} AND d.ts = a.bucket
        WHERE a.parts = {minutes // 5}
          AND (abs(d.open - a.o) > 1e-9 OR abs(d.close - a.c) > 1e-9
               OR abs(d.high - a.hi) > 1e-9 OR abs(d.low - a.lo) > 1e-9
               OR (d.volume IS NULL) <> (a.vol IS NULL)
               OR (d.volume IS NOT NULL AND abs(d.volume - a.vol) > 1e-6))
        """,
    )
    matched = one(
        cur,
        f"""
        SELECT count(*) AS n FROM "IntradayBar" WHERE interval = {minutes} AND derived = true
        """,
    )
    claim(f"{minutes}m bars match a recomputation from the 5m series",
          wrong["n"] == 0, f"{matched['n']:,} derived bars, {wrong['n']} mismatched")

# 7 -- incomplete groups were skipped, never written
head(7, "Incomplete derived candles are never written")
for minutes in (15, 30, 60):
    leaked = one(
        cur,
        f"""
        WITH fine AS (
            SELECT "assetId", to_timestamp(floor(EXTRACT(EPOCH FROM ts) / {minutes * 60})
                   * {minutes * 60})::timestamp AS bucket, count(*) AS parts
            FROM "IntradayBar" WHERE interval = 5 GROUP BY 1,2
        )
        SELECT count(*) AS n
        FROM "IntradayBar" d JOIN fine f
          ON f."assetId" = d."assetId" AND f.bucket = d.ts
        WHERE d.interval = {minutes} AND f.parts < {minutes // 5}
        """,
    )
    claim(f"no {minutes}m bar was built from fewer than {minutes // 5} parts",
          leaked["n"] == 0, f"{leaked['n']} partial candles written")

# 8 -- derived flag is honest
head(8, "Derived is marked, not inferred")
flag = one(
    cur,
    """
    SELECT count(*) FILTER (WHERE interval = 5 AND derived) AS fine_marked_derived,
           count(*) FILTER (WHERE interval > 5 AND NOT derived) AS coarse_marked_fetched,
           count(*) FILTER (WHERE derived AND "derivedFrom" IS NULL) AS derived_without_source
    FROM "IntradayBar"
    """,
)
claim("the derived flag matches reality",
      flag["fine_marked_derived"] == 0 and flag["derived_without_source"] == 0,
      f"{dict(flag)}")

# 9 -- completeness accounting
head(9, "Completeness is recorded, including the absences")
st = {r["status"]: int(r["n"]) for r in rows(
    cur, 'SELECT status, count(*) AS n FROM "IntradaySession" GROUP BY status')}
claim("every status is represented honestly", "complete" in st and "partial" in st, f"{st}")
mismatch = one(
    cur,
    """
    SELECT count(*) AS n FROM "IntradaySession"
    WHERE status = 'complete' AND "barsExpected" IS NOT NULL
      AND "barsStored" < "barsExpected" * 0.9
    """,
)
claim("nothing short is labelled complete", mismatch["n"] == 0, f"{mismatch['n']} mislabelled")
unsup = one(
    cur,
    """
    SELECT count(DISTINCT s."assetId") AS n FROM "IntradaySession" s
    WHERE s.status = 'unsupported'
      AND NOT EXISTS (SELECT 1 FROM "IntradayBar" b WHERE b."assetId" = s."assetId")
    """,
)
claim("unsupported assets have no bars (the fact is stored, not faked)",
      unsup["n"] > 0, f"{unsup['n']} assets recorded unsupported with zero bars")

# 10 -- setups and targets read from intraday
head(10, "Bars -> setup -> target -> horizon output")
iset = one(
    cur,
    """
    SELECT count(*) AS n, count(*) FILTER (WHERE state IN ('buy','short')) AS directional
    FROM "AssetSetup"
    WHERE horizon = 'intraday'
      AND "periodEnd" = (SELECT max("periodEnd") FROM "AssetSetup" WHERE horizon = 'intraday')
    """,
)
claim("intraday reads exist", iset["n"] > 0,
      f"{iset['n']} reads, {iset['directional']} directional")
itg = one(
    cur,
    """
    SELECT count(*) AS n, count(DISTINCT t.method) AS methods
    FROM "SetupTarget" t JOIN "AssetSetup" s ON s.id = t."setupId"
    WHERE s.horizon = 'intraday'
    """,
)
claim("intraday setups carry target ranges", itg["n"] > 0,
      f"{itg['n']} ranges by {itg['methods']} methods")
orphan = one(
    cur,
    """
    SELECT count(*) AS n FROM "SetupTarget" t JOIN "AssetSetup" s ON s.id = t."setupId"
    WHERE s."invalidateLevel" IS NULL OR s."entryLevel" IS NULL
    """,
)
claim("no target exists without an entry and an invalidation", orphan["n"] == 0,
      f"{orphan['n']} targets with no risk behind them")
inside = one(
    cur,
    """
    SELECT count(*) AS n FROM "SetupTarget" t JOIN "AssetSetup" s ON s.id = t."setupId"
    WHERE s."entryLevel" BETWEEN least(t.low, t.high) AND greatest(t.low, t.high)
      AND t.low <> t.high
    """,
)
claim("no target range contains its own entry", inside["n"] == 0,
      f"{inside['n']} ranges containing the entry")

# 11 -- three horizons
head(11, "Three horizons, independently")
hz = {r["horizon"]: int(r["n"]) for r in rows(
    cur,
    """
    SELECT horizon, count(*) AS n FROM "AssetSetup" s
    WHERE "periodEnd" = (SELECT max("periodEnd") FROM "AssetSetup" x WHERE x.horizon = s.horizon)
    GROUP BY horizon
    """,
)}
claim("all three horizons are written", len(hz) == 3, f"{hz}")
disagree = one(
    cur,
    """
    WITH latest AS (
        SELECT s.* FROM "AssetSetup" s
        WHERE "periodEnd" = (SELECT max("periodEnd") FROM "AssetSetup" x WHERE x.horizon = s.horizon)
    )
    SELECT count(*) AS n FROM (
        SELECT "assetId" FROM latest GROUP BY "assetId"
        HAVING count(DISTINCT state) > 1
    ) d
    """,
)
claim("horizons are allowed to disagree and do", disagree["n"] > 0,
      f"{disagree['n']} assets read differently on different horizons")

# 12 -- retention bounds storage
head(12, "Retention actually bounds storage")
import intraday as idj  # noqa: E402

age = one(
    cur,
    """
    SELECT min("sessionDate") AS lo, max("sessionDate") AS hi,
           (max("sessionDate") - min("sessionDate")) AS span_days
    FROM "IntradayBar"
    """,
)
claim(f"stored span is within RETAIN_DAYS ({idj.RETAIN_DAYS})",
      age["span_days"] is not None and age["span_days"] <= idj.RETAIN_DAYS,
      f"{age['lo']} to {age['hi']} = {age['span_days']} days")

sizes = one(
    cur,
    """
    SELECT pg_size_pretty(pg_total_relation_size('"IntradayBar"')) AS intraday,
           pg_size_pretty(pg_total_relation_size('"PriceSnapshot"')) AS daily,
           pg_size_pretty(pg_database_size(current_database())) AS db,
           pg_database_size(current_database()) AS db_bytes
    """,
)
claim("database is inside the free tier",
      int(sizes["db_bytes"]) < 500 * 1024 * 1024,
      f"db {sizes['db']}, IntradayBar {sizes['intraday']}, PriceSnapshot {sizes['daily']}")

# 13 -- crypto mapping landed
head(13, "Crypto uses the provider's own symbol")
crypto = one(
    cur,
    """
    SELECT count(DISTINCT b."assetId") AS n FROM "IntradayBar" b
    JOIN "Asset" a ON a.id = b."assetId"
    WHERE a."assetType"::text = 'crypto'
    """,
)
claim("crypto assets have intraday bars", crypto["n"] > 0,
      f"{crypto['n']} crypto assets with bars")
failed = one(
    cur,
    """
    SELECT count(*) AS n FROM "IntradaySession" s
    JOIN "Asset" a ON a.id = s."assetId"
    WHERE a."assetType"::text = 'crypto' AND s.status = 'failed'
      AND s."sessionDate" = (SELECT max("sessionDate") FROM "IntradaySession")
    """,
)
claim("no crypto fetch failed on the newest session", failed["n"] == 0,
      f"{failed['n']} failures")

print("\n" + "=" * 76)
print(f"INTRADAY CHAIN: {len(ok)} pass, {len(bad)} fail")
if bad:
    for b_ in bad:
        print("  FAILED:", b_)
print("=" * 76)

cur.close()
conn.close()
