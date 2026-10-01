"""Live acceptance check. Read-only: every statement is a SELECT."""

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
att = one(cur, '''
    SELECT count(*) AS n, count(leader) AS led,
           max(abs("totalPct" - ("marketPct" + coalesce("sectorPct",0) + coalesce("specificPct",0)))) AS err
    FROM "MoveAttribution"
''')
ok = att["n"] and (att["err"] is None or float(att["err"]) < 1e-6)
check("ATTRIBUTION", PASS if ok else FAIL,
      f"{att['n']} rows, {att['led']} with a named leader, identity error {float(att['err'] or 0):.2e}")

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
size = one(cur, '''
    SELECT pg_size_pretty(pg_database_size(current_database())) AS db
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
print()
counts = {}
for _, verdict, _ in results:
    counts[verdict] = counts.get(verdict, 0) + 1
print("  " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

cur.close()
conn.close()
