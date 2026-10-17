"""One command that answers "is the system healthy today", and exits non-zero when it is not.

    python tools/daily_audit.py [--json FILE] [--no-db]

What this is for
----------------
The operator's question every morning is not "what changed" but "is anything broken, and is
anything claiming to be current when it is not". The pieces that answer it already exist and are
scattered: `lib/health.ts` owns the staleness rules, `ChunkRun` holds per-slice run outcomes,
`Coverage` holds per-source gap ratios, `price_freshness.py` asks about one lane, the freeze
records hold dataset digests and the brain manifests hold model digests. **This composes them.
It deliberately re-derives nothing that already has an owner.**

Staleness thresholds are **read out of `lib/health.ts`**, not restated here. That file's own
docstring makes the point: a health page calling a close fresh while every decision on it reads
stale would be two answers to one question. A Python copy of those numbers would be a third.

One connection, by design
-------------------------
The Supabase pooler accepts **15 session-mode clients** and that ceiling has already broken runs
in this project. This opens exactly one connection, reuses it for every database check, and closes
it. `--no-db` skips the database entirely so the local checks still run when the pooler is full --
which is itself a condition worth reporting rather than crashing on.

Severity
--------
`fail` means something is wrong now and the exit code is 1: a lane that has not run, data passing
as current when it is stale, an artifact whose digest no longer matches. `warn` means something
needs attention but nothing is lying to a user. `ok` is measured, not assumed. A check that could
not run reports `unknown` and never silently counts as a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OK, WARN, FAIL, UNKNOWN = "ok", "warn", "fail", "unknown"


def check(name: str, status: str, detail: str, extra=None) -> dict:
    return {"check": name, "status": status, "detail": detail, "extra": extra}


def health_constants() -> dict:
    """The staleness rules, read from lib/health.ts so there is one definition of stale."""
    out, src = {}, (ROOT / "lib" / "health.ts")
    if not src.exists():
        return out
    text = src.read_text(encoding="utf-8")
    for key in ("DECISIONS_STALE_AFTER_DAYS", "NEWS_STALE_AFTER_HOURS",
                "QUOTES_STALE_AFTER_MINUTES"):
        m = re.search(rf"export const {key}\s*=\s*([0-9.]+)", text)
        if m:
            out[key] = float(m.group(1))
    m = re.search(r"STALE_AFTER_DAYS\s*[:=]\s*\{([^}]*)\}", (ROOT / "lib" / "decision.ts")
                  .read_text(encoding="utf-8") if (ROOT / "lib" / "decision.ts").exists() else "")
    if m:
        out["STALE_AFTER_DAYS"] = {k: float(v) for k, v in re.findall(r"(\w+)\s*:\s*([0-9.]+)",
                                                                      m.group(1))}
    return out


# --- local checks, no database -----------------------------------------------------------------

def artifact_checks() -> list[dict]:
    """Every committed model and dataset digest still matches its own manifest."""
    out = []
    brains = ROOT / "data" / "foundation" / "brain"
    for d in sorted(p for p in brains.glob("*") if p.is_dir()) if brains.exists() else []:
        mp, fp = d / "model.json", d / "manifest.json"
        if not (mp.exists() and fp.exists()):
            continue
        man = json.loads(fp.read_text(encoding="utf-8"))
        live = hashlib.sha256(mp.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        recorded = (man.get("artifact") or {}).get("sha256")
        same = live == recorded
        approved = json.loads(mp.read_text(encoding="utf-8")).get("productionApproved")
        out.append(check(f"artifact:{d.name}", OK if same else FAIL,
                         f"digest {'matches' if same else 'DOES NOT MATCH'} its manifest; "
                         f"verdict {man.get('verdict')}, productionApproved {approved}",
                         {"sha256": live[:16], "recorded": (recorded or "")[:16]}))
        if approved is not False:
            out.append(check(f"artifact:{d.name}:approval", FAIL,
                             "productionApproved is not false on an unvalidated candidate"))
    for name in ("dataset_freeze.json", "dataset_freeze_v4_context.json"):
        p = ROOT / "data" / "foundation" / "dataset" / name
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append(check(f"freeze:{d.get('version')}",
                         OK if d.get("blockingGatesGreen") else FAIL,
                         f"status {d.get('status')}, gates green {d.get('blockingGatesGreen')}, "
                         f"{len(d.get('files') or {})} files"))
    return out


def recovery_checks() -> list[dict]:
    """The two resilience concerns the last checkpoint raised, measured rather than repeated."""
    out = []
    reh = ROOT / "data" / "foundation" / "dataset" / "restore_rehearsal.json"
    migrations = sorted(p.name for p in (ROOT / "prisma" / "migrations").glob("2*")
                        if p.is_dir())
    if reh.exists():
        d = json.loads(reh.read_text(encoding="utf-8"))
        at = (d.get("source") or {}).get("schemaVersion")
        behind = [m for m in migrations if at and m > at]
        out.append(check("restoreRehearsalCurrent", WARN if behind else OK,
                         f"verified at schema {at}; {len(behind)} migration(s) applied since",
                         {"behind": behind,
                          "rows": (d.get("toolResult") or "")[:80]}))
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(d["generatedAt"])).days
            out.append(check("restoreRehearsalAge", WARN if age > 14 else OK,
                             f"last real restore rehearsal {age} days ago"))
        except Exception:                                      # noqa: BLE001
            pass
    else:
        out.append(check("restoreRehearsalCurrent", FAIL, "no restore rehearsal on record"))
    return out


# --- database checks, one connection -------------------------------------------------------------

def db_checks(conn, const: dict) -> list[dict]:
    out, cur = [], conn.cursor()
    today = date.today()

    cur.execute('SELECT max(date) d, count(*) n FROM "PriceSnapshot"')
    r = cur.fetchone()
    lag = (today - r["d"]).days if r["d"] else None
    out.append(check("priceFreshness", OK if (lag is not None and lag <= 4) else FAIL,
                     f"newest stored close {r['d']} ({lag} days back), {r['n']:,} rows",
                     {"lagDays": lag}))

    cur.execute('SELECT max("periodEnd") d FROM "AssetFactor"')
    d = cur.fetchone()["d"]
    flag = (today - d).days if d else None
    out.append(check("factorFreshness", OK if (flag is not None and flag <= 4) else WARN,
                     f"newest factor session {d} ({flag} days back)", {"lagDays": flag}))

    hours = const.get("NEWS_STALE_AFTER_HOURS", 6)
    cur.execute('SELECT max("publishedAt") t FROM "News"')
    t = cur.fetchone()["t"]
    if t:
        # Postgres hands back a naive datetime for a column without a zone. Comparing it with an
        # aware "now" raises, and the first version of this file reported that TypeError as
        # "database not reachable" -- a bug in a health check disguised as an outage.
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - t).total_seconds() / 3600
        out.append(check("newsFreshness", OK if age_h <= hours * 4 else WARN,
                         f"newest headline {age_h:.1f}h old (lib/health.ts calls the lane stale "
                         f"after {hours}h)"))

    cur.execute("""SELECT source, status, round(("gapRatio")::numeric, 2) g FROM "Coverage"
                   WHERE status <> 'ok' ORDER BY "gapRatio" DESC LIMIT 8""")
    bad = cur.fetchall()
    out.append(check("sourceCoverage", OK if not bad else WARN,
                     "every source within its expected interval" if not bad
                     else f"{len(bad)} source(s) outside: "
                          + ", ".join(f"{b['source']}({b['status']} x{b['g']})" for b in bad)))

    # ChunkRun records one row per slice with `status` and `startedAt`; there is no finish
    # timestamp, which is the point -- runlog.py writes the row whether the slice succeeded or
    # not, so a missing row means nothing ran rather than something is still running.
    cur.execute("""SELECT job, status, count(*) n, max("startedAt") last FROM "ChunkRun"
                   WHERE "startedAt" > now() - interval '36 hours'
                   GROUP BY job, status ORDER BY job""")
    runs = cur.fetchall()
    failed = [r for r in runs if r["status"] not in ("ok", "complete", "done")]
    out.append(check("jobRuns36h", OK if (runs and not failed) else (FAIL if failed else WARN),
                     f"{sum(r['n'] for r in runs)} slice(s) in 36h"
                     + ("" if not failed else "; failing: "
                        + ", ".join(f"{r['job']}:{r['status']}x{r['n']}" for r in failed))
                     if runs else "no job slices logged in 36 hours"))

    cur.execute("""SELECT count(*) n, count("outcomeLabel") done,
                   min("maturesAfter") soonest, count(DISTINCT "modelVersion") mv
                   FROM "ShadowPrediction" """)
    s = cur.fetchone()
    due = 0
    if s["n"]:
        cur.execute("""SELECT count(*) n FROM "ShadowPrediction"
                       WHERE "outcomeLabel" IS NULL AND "maturesAfter" <= current_date""")
        due = cur.fetchone()["n"]
    out.append(check("shadowOutcomes", WARN if due else OK,
                     f"{s['n']} prediction(s) from {s['mv']} model version(s); "
                     f"{s['done']} scored; {due} matured and awaiting an outcome; "
                     f"earliest maturity {s['soonest']}",
                     {"matureAndUnscored": due}))

    cur.execute("""SELECT count(*) n FROM "ShadowPrediction" WHERE approved IS TRUE""")
    approved = cur.fetchone()["n"]
    out.append(check("noApprovedShadowRecords", OK if approved == 0 else FAIL,
                     f"{approved} shadow record(s) marked approved"))

    applied = set()
    cur.execute("SELECT migration_name FROM _prisma_migrations WHERE finished_at IS NOT NULL")
    applied = {r["migration_name"] for r in cur.fetchall()}
    on_disk = {p.name for p in (ROOT / "prisma" / "migrations").glob("2*") if p.is_dir()}
    pending = sorted(on_disk - applied)
    out.append(check("migrationsApplied", OK if not pending else FAIL,
                     f"{len(applied)} applied; {len(pending)} pending"
                     + ("" if not pending else ": " + ", ".join(pending))))

    cur.execute("SELECT pg_database_size(current_database())/1048576.0 mb")
    mb = cur.fetchone()["mb"]
    out.append(check("databaseSize", OK if mb < 450 else (WARN if mb < 500 else FAIL),
                     f"{mb:,.1f} MB of a 500 MB free tier ({mb/500:.1%})", {"mb": round(mb, 1)}))
    cur.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", default=str(ROOT / "data" / "foundation" / "dataset"
                                          / "daily_audit.json"))
    ap.add_argument("--no-db", action="store_true")
    a = ap.parse_args()

    const = health_constants()
    checks = artifact_checks() + recovery_checks()

    if a.no_db:
        checks.append(check("database", UNKNOWN, "skipped with --no-db"))
    else:
        try:
            sys.path.insert(0, str(ROOT / "jobs"))
            try:
                from dotenv import load_dotenv
                load_dotenv(ROOT / ".env")
            except ImportError:
                pass
            from nbt import db
            conn = db()
        except Exception as e:                                 # noqa: BLE001
            # The pooler's 15-client ceiling lives here. Unreachable is a reportable condition,
            # not a crash, and it is `unknown` rather than `fail` because nothing is proven wrong.
            conn = None
            checks.append(check("database", UNKNOWN,
                                f"not reachable: {type(e).__name__}: {str(e)[:120]}",
                                {"note": "pooler ceiling is 15 session clients"}))
        if conn is not None:
            try:
                checks += db_checks(conn, const)
            except Exception as e:                             # noqa: BLE001
                # A fault INSIDE a check is this file's bug, not an outage, and saying
                # "not reachable" about it would send the operator to the database.
                checks.append(check("auditInternal", FAIL,
                                    f"a check raised: {type(e).__name__}: {str(e)[:120]}"))
            finally:
                conn.close()

    counts = {s: sum(1 for c in checks if c["status"] == s) for s in (OK, WARN, FAIL, UNKNOWN)}
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "daily-audit-v1",
        "staleRulesReadFrom": "lib/health.ts + lib/decision.ts", "staleRules": const,
        "summary": counts,
        "healthy": counts[FAIL] == 0,
        "checks": checks,
    }
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")

    mark = {OK: "ok     ", WARN: "WARN   ", FAIL: "FAIL   ", UNKNOWN: "unknown"}
    for c in checks:
        print(f"  {mark[c['status']]} {c['check']:<34} {c['detail'][:92]}")
    print(f"\nok {counts[OK]}  warn {counts[WARN]}  fail {counts[FAIL]}  "
          f"unknown {counts[UNKNOWN]}  ->  healthy: {payload['healthy']}")
    print(f"wrote {a.json}")
    return 0 if payload["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
