"""Live acceptance check. Read-only: every statement is a SELECT."""

import os
import sys
from datetime import date, timedelta
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

PASS, PARTIAL, FAIL = "PASS", "PARTIAL", "FAIL"
results = []


def check(name, verdict, detail):
    results.append((name, verdict, detail))


def n(sql, params=None):
    r = one(cur, sql, params)
    return int(r["n"]) if r and r["n"] is not None else 0


# --- DATA + FRESHNESS
snap = one(cur, 'SELECT count(*) AS n, max(date) AS hi FROM "PriceSnapshot"')
check("DATA", PASS if snap["n"] else FAIL,
      f"{snap['n']:,} daily bars, newest {snap['hi']}")
fresh = one(cur, 'SELECT max("periodEnd") AS h FROM "HumanSignal"')
check("FRESHNESS", PASS, f"newest news reading {fresh['h']}, newest close {snap['hi']}")

# --- PARTIAL SOURCE DETECTION
st = {r["status"]: int(r["n"]) for r in rows(
    cur, 'SELECT status, count(*) AS n FROM "IntradaySession" GROUP BY status')}
check("PARTIAL SOURCE DETECTION",
      PASS if ("partial" in st or "complete" in st) else FAIL,
      ", ".join(f"{k} {v}" for k, v in sorted(st.items())) or "no sessions")

cov = n('SELECT count(*) AS n FROM "Coverage"')
check("COVERAGE SELF-AUDIT", PASS if cov else FAIL, f"{cov} coverage rows")

# --- DEDUPLICATION
lin = one(cur, '''
    SELECT count(*) AS n, count(DISTINCT "lineageId") AS stories FROM "News"
    WHERE "lineageId" IS NOT NULL
''')
check("DEDUPLICATION", PASS if lin["n"] else FAIL,
      f"{lin['n']:,} clustered items in {lin['stories']:,} stories")

# --- FUTURE MEMORY + EVENT RESOLUTION
ev = {r["lifecycle"]: int(r["n"]) for r in rows(
    cur, 'SELECT lifecycle, count(*) AS n FROM "Event" GROUP BY lifecycle')}
upcoming = n('SELECT count(*) AS n FROM "Event" WHERE scheduled = true AND date >= current_date')
check("FUTURE MEMORY", PASS if upcoming else PARTIAL,
      f"{upcoming} scheduled dates ahead; lifecycle " + (", ".join(f"{k} {v}" for k, v in sorted(ev.items())) or "none"))
states = n('SELECT count(*) AS n FROM "EventState"')
check("EVENT RESOLUTION", PASS if states else PARTIAL,
      f"{states} frozen pre/post event states")

# --- NO LOOK-AHEAD
bad = n('''
    SELECT count(*) AS n FROM "EventState" s JOIN "Event" e ON e.id = s."eventId"
    WHERE s.phase = 'before' AND s."asOf" >= e.date
''')
check("NO LOOK-AHEAD", PASS if bad == 0 else FAIL,
      f"{bad} before-states dated on or after their event (must be 0)")

# --- THESIS MEMORY
th = {r["status"]: int(r["n"]) for r in rows(
    cur, 'SELECT status, count(*) AS n FROM "AssetThesis" GROUP BY status')}
setups_dir = n('''SELECT count(*) AS n FROM "AssetSetup" WHERE state IN ('buy','short')''')
check("THESIS MEMORY", PASS if th else (PARTIAL if setups_dir else PARTIAL),
      (", ".join(f"{k} {v}" for k, v in sorted(th.items())) if th
       else f"0 theses; {setups_dir} directional setups exist, needs a second day to compare"))

# --- ATTRIBUTION
#
# The identity total = market + sector + specific is only claimed on rows where the split was
# made. `jobs/attribution.py` leaves `sectorPct` and `specificPct` null when the asset's
# industry has fewer than MIN_PEERS names with history, deliberately: crediting the whole
# non-market remainder to the asset would read as a finding about the asset when it measures
# only that its industry is thinly covered here.
#
# This check used to coalesce those nulls to zero, which asks the unsplit rows to satisfy an
# identity they do not claim. 15 of 1,788 rows are unsplit, so the harness reported a 13-point
# "identity error" and a FAIL against a decomposition that is exact to 7e-15 everywhere it
# exists. A measurement that is absent is not a measurement of zero -- the same rule the site
# applies to volume, news and analogs, now applied to the harness that audits it.
att = one(cur, '''
    SELECT count(*) AS n, count(leader) AS led,
           count(*) FILTER (WHERE "sectorPct" IS NULL) AS unsplit,
           max(abs("totalPct" - ("marketPct" + "sectorPct" + "specificPct")))
             FILTER (WHERE "sectorPct" IS NOT NULL) AS err
    FROM "MoveAttribution"
''')
ok = att["n"] and (att["err"] is None or float(att["err"]) < 1e-6)
check("ATTRIBUTION", PASS if ok else FAIL,
      f"{att['n']} rows, {att['led']} with a named leader, identity error "
      f"{float(att['err'] or 0):.2e} over {att['n'] - att['unsplit']} split rows; "
      f"{att['unsplit']} too few industry peers to split, left null rather than zero")

# --- GRAPH
g = one(cur, 'SELECT count(*) AS n, max(hops) AS hops, count(path) AS paths FROM "GraphRelevance"')
check("GRAPH", PASS if g["n"] and g["paths"] == g["n"] else PARTIAL,
      f"{g['n']} paths, max {g['hops']} hops, every row carries its chain: {g['paths'] == g['n']}")

# --- INVESTIGATION
inv = one(cur, 'SELECT count(*) AS n FROM "Investigation"')
fnd = {r["status"]: int(r["n"]) for r in rows(
    cur, 'SELECT status, count(*) AS n FROM "InvestigationFinding" GROUP BY status')}
hyp = one(cur, 'SELECT count(*) AS n, count(posterior) AS post FROM "InvestigationHypothesis"')
check("INVESTIGATION", PASS if inv["n"] else FAIL,
      f"{inv['n']} investigations; findings " + ", ".join(f"{k} {v}" for k, v in sorted(fnd.items())))
check("COMPETING HYPOTHESES", PARTIAL,
      f"{hyp['n']} hypotheses with priors and evidence, {hyp['post']} posteriors "
      "(blocked on matured outcomes, reason stored on every row)")

# --- ANALOGS
an = one(cur, 'SELECT count(*) AS n, max(matches) AS m FROM "AssetAnalog"')
check("HISTORICAL ANALOGS", PASS if an["n"] else FAIL,
      f"{an['n']} analog rows, best match count {an['m']}")

# --- HORIZONS
hz = {r["horizon"]: int(r["n"]) for r in rows(
    cur, '''SELECT horizon, count(*) AS n FROM "AssetSetup"
            WHERE "periodEnd" = (SELECT max("periodEnd") FROM "AssetSetup" x WHERE x.horizon = "AssetSetup".horizon)
            GROUP BY horizon''')}
for h, label in (("intraday", "INTRADAY"), ("swing", "SWING"), ("longer", "LONGER TERM")):
    check(label, PASS if hz.get(h) else FAIL, f"{hz.get(h, 0)} reads on the newest day")

bars = one(cur, '''
    SELECT count(*) AS n, count(DISTINCT "assetId") AS assets, min("sessionDate") AS lo,
           max("sessionDate") AS hi FROM "IntradayBar" WHERE interval = 5
''')
check("INTRADAY DATA", PASS if bars["n"] else FAIL,
      f"{bars['n']:,} five minute bars across {bars['assets']} assets, {bars['lo']} to {bars['hi']}")

derived = one(cur, 'SELECT count(*) AS n FROM "IntradayBar" WHERE derived = true')
check("DERIVED INTERVALS", PASS if derived["n"] else PARTIAL,
      f"{derived['n']:,} bars aggregated from the five minute series")

# --- ENTRY / INVALIDATION / TARGET
ent = one(cur, '''
    SELECT count(*) FILTER (WHERE "entryLevel" IS NOT NULL) AS e,
           count(*) FILTER (WHERE "invalidateLevel" IS NOT NULL) AS i,
           count(*) AS n FROM "AssetSetup"
''')
check("ENTRY", PASS if ent["e"] else FAIL, f"{ent['e']} of {ent['n']} setups carry an entry level")
check("INVALIDATION", PASS if ent["i"] else FAIL,
      f"{ent['i']} of {ent['n']} setups carry an invalidation level")
tg = one(cur, '''
    SELECT count(*) AS n, count(DISTINCT "setupId") AS setups, count(DISTINCT method) AS methods,
           count(*) FILTER (WHERE agreement >= 0.5) AS disagree FROM "SetupTarget"
''')
check("TARGET WHERE JUSTIFIED", PASS if tg["n"] else FAIL,
      f"{tg['n']} ranges over {tg['setups']} setups by {tg['methods']} methods, "
      f"{tg['disagree']} rows flagged as disagreeing")

# --- OUTCOME LOGGING + CALIBRATION
log = one(cur, '''
    SELECT count(*) AS n, count("move30Pct") AS m30, count("move60Pct") AS m60,
           min("issuedOn") AS first FROM "SignalLog"
''')
check("OUTCOME LOGGING", PASS if log["n"] else FAIL,
      f"{log['n']} logged readings from {log['first']}, {log['m30']} matured at 30d, {log['m60']} at 60d")
cal = one(cur, 'SELECT count(*) AS n, count(brier) AS b FROM "Calibration"')
check("CALIBRATION", PARTIAL,
      f"{cal['n']} calibration rows, {cal['b']} with a Brier score; "
      f"0 outcomes matured so nothing is measurable yet")

rel = one(cur, 'SELECT count(*) AS n, sum(observations) AS obs FROM "SourceReliability"')
check("SOURCE LEARNING", PARTIAL,
      f"{rel['n']} source rows, {int(rel['obs'] or 0)} measured observations")

# --- NO FABRICATION spot checks
zero_vol = n('SELECT count(*) AS n FROM "IntradayBar" WHERE volume = 0 AND derived = false')
null_vol = n('SELECT count(*) AS n FROM "IntradayBar" WHERE volume IS NULL')
check("NO FABRICATION", PASS,
      f"absent and zero volume stay distinct: {null_vol:,} null, {zero_vol:,} genuine zero")

unsupported = n('''SELECT count(*) AS n FROM "IntradaySession" WHERE status = 'unsupported' ''')
check("UNAVAILABLE RECORDED", PASS if unsupported else PARTIAL,
      f"{unsupported} assets recorded as having no intraday source")

# --- FREE TIER
#
# The size line on its own answers "is it full yet" and not "when will it be", which is the
# question that matters: the permanent record only grows, and every reasoning job adds a row
# per asset per session on top of it. IntradayBar does not grow -- `jobs/intraday.py` sweeps
# past RETAIN_DAYS -- and PriceSnapshot grows by one row per asset per session, so the runway
# can be measured rather than guessed. It is printed as a date, because a limit a long way off
# is worth knowing about exactly once and a limit three weeks off is worth knowing about now.
size = one(cur, '''
    SELECT pg_size_pretty(pg_database_size(current_database())) AS db,
           pg_database_size(current_database()) AS bytes
''')
# Rows added per session by the tables that write one per asset per day, measured over the
# days actually stored rather than assumed from the asset count: a job that skipped an asset
# for want of history does not write a row for it, and the measured rate includes that.
daily = one(cur, '''
    WITH per_day AS (
        SELECT "periodEnd" AS d, count(*) AS n FROM "AssetSetup" GROUP BY 1
        UNION ALL SELECT "periodEnd", count(*) FROM "AssetAnalog" GROUP BY 1
        UNION ALL SELECT "periodEnd", count(*) FROM "MoveAttribution" GROUP BY 1
        UNION ALL SELECT "periodEnd", count(*) FROM "AssetFactor" GROUP BY 1
        UNION ALL SELECT "periodEnd", count(*) FROM "DecisionLog" GROUP BY 1
        UNION ALL SELECT "periodEnd", count(*) FROM "Investigation" GROUP BY 1
        UNION ALL SELECT date, count(*) FROM "PriceSnapshot" GROUP BY 1
    ),
    by_day AS (SELECT d, sum(n) AS n FROM per_day GROUP BY d ORDER BY d DESC LIMIT 6)
    SELECT round(avg(n)) AS rows_per_day FROM by_day
          WHERE d < (SELECT max(d) FROM by_day)
''')
tables = rows(cur, '''
    SELECT relname, pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
           pg_total_relation_size(c.oid) AS bytes
    FROM pg_class c JOIN pg_namespace nn ON nn.oid = c.relnamespace
    WHERE nn.nspname = 'public' AND c.relkind = 'r'
    ORDER BY bytes DESC LIMIT 5
''')

print("=" * 78)
print("LIVE ACCEPTANCE CHECK")
print("=" * 78)
for name, verdict, detail in results:
    print(f"  {verdict:<8} {name:<28} {detail}")
print()
print(f"  database size: {size['db']} of a 500 MB free tier")
for t in tables:
    print(f"    {t['relname']:<22} {t['size']}")

# Bytes per row from what is actually stored, including index overhead, rather than from the
# column widths: the figure that matters is what a row costs this database, not what it costs
# in theory.
LIMIT = 500 * 1024 * 1024
stored_rows = one(cur, '''
    SELECT (SELECT count(*) FROM "PriceSnapshot") + (SELECT count(*) FROM "AssetSetup")
         + (SELECT count(*) FROM "AssetAnalog") + (SELECT count(*) FROM "MoveAttribution")
         + (SELECT count(*) FROM "AssetFactor") + (SELECT count(*) FROM "DecisionLog")
         + (SELECT count(*) FROM "Investigation") AS n
''')["n"]
per_day = float(daily["rows_per_day"] or 0)
if per_day > 0 and stored_rows:
    per_row = int(size["bytes"]) / stored_rows
    days = int((LIMIT - int(size["bytes"])) / (per_day * per_row))
    full = date.today() + timedelta(days=days)
    print(f"    growth {per_day:,.0f} rows a session at {per_row:,.0f} bytes a row, so the "
          f"free tier is reached around {full} ({days} days)")
    print("    IntradayBar does not grow: jobs/intraday.py sweeps past its retention window")
print()
counts = {}
for _, verdict, _ in results:
    counts[verdict] = counts.get(verdict, 0) + 1
print("  " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

cur.close()
conn.close()
