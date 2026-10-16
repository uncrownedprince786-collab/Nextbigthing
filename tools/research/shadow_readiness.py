"""Could this candidate run as a live shadow prediction today, and what exactly stops it?

    python tools/research/shadow_readiness.py [--model DIR] [--out FILE]

Read-only. Nothing is deployed, nothing is written to any database, and no prediction is recorded.
The question is narrower and more useful than "does the code run": **which preconditions of a live
shadow path hold right now, measured, and which do not.**

Why a checklist and not a pipeline
-----------------------------------
`brain-v2-context` is a NO-GO. Building its serving path before anything is approved would be the
speculative infrastructure the project's own rules warn against. But "we cannot deploy it" and "we
do not know what deploying it would need" are different states, and only the second is a gap. This
closes the second at the cost of one read-only run.

Each check reports `ok`, `blocked` or `unknown`, with the evidence that decided it. `unknown` is a
first-class answer: a check that could not run is not a check that passed, and the summary counts
the three separately so a reader cannot mistake one for another.

The check that matters most, and is easy to miss
-------------------------------------------------
At training, an absent context feature takes the training fold's mean. That is measured, recorded
and fine. **At inference the same rule is a silent substitution**: a macro artifact that failed to
refresh, or an instrument with no records, becomes "an average day" and the prediction looks exactly
as confident as one built from observed evidence. A shadow path must therefore record *which*
features were imputed on each prediction, not only the prediction. That is `imputationIsVisible`
below, and it is `blocked` until a prediction record has somewhere to put it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

OUT = ROOT / "data" / "foundation" / "dataset" / "shadow_readiness.json"
DEFAULT_MODEL = ROOT / "data" / "foundation" / "brain" / "brain-v2-context"

OK, BLOCKED, UNKNOWN = "ok", "blocked", "unknown"


def check(name: str, status: str, evidence: str, detail=None) -> dict:
    return {"check": name, "status": status, "evidence": evidence, "detail": detail}


def model_checks(mdir: Path) -> list[dict]:
    out = []
    mp, fp = mdir / "model.json", mdir / "manifest.json"
    if not mp.exists():
        return [check("artifactLoads", BLOCKED, f"no model.json in {mdir}")]
    m = json.loads(mp.read_text(encoding="utf-8"))
    out.append(check("artifactLoads", OK,
                     f"{m['modelVersion']}: {len(m['features'])} features, "
                     f"weights {m['weightShape']}, classes {m['classes']}"))
    out.append(check("notProductionApproved",
                     OK if m.get("productionApproved") is False else BLOCKED,
                     f"productionApproved={m.get('productionApproved')}, status={m.get('status')}",
                     "a shadow path must refuse to serve this as an approved brain"))
    if fp.exists():
        man = json.loads(fp.read_text(encoding="utf-8"))
        out.append(check("verdictIsRecorded", OK,
                         f"verdict={man.get('verdict')}, "
                         f"eligibleForPromotion={man.get('eligibleForPromotion')}"))
    return out


def feature_checks(mdir: Path) -> list[dict]:
    """Can every feature the model names be produced live, by the same names?"""
    out = []
    try:
        from context_features import ContextSource
    except Exception as e:                                   # noqa: BLE001
        return [check("contextProducerImports", BLOCKED, f"{type(e).__name__}: {e}")]
    out.append(check("contextProducerImports", OK, "tools/foundation/context_features"))

    m = json.loads((mdir / "model.json").read_text(encoding="utf-8"))
    wanted = list(m["features"])
    ctx_names = set(ContextSource.feature_names())
    try:
        sys.path.insert(0, str(ROOT / "tools" / "research"))
        from baseline_experiment import FEATURES as PRICE
        price_names = set(PRICE)
    except Exception:                                        # noqa: BLE001
        price_names = set()
    unknown = [f for f in wanted if f not in ctx_names and f not in price_names]
    out.append(check("everyFeatureHasAProducer", OK if not unknown else BLOCKED,
                     f"{len(wanted)} wanted; {len(ctx_names & set(wanted))} from the context "
                     f"producer, {len(price_names & set(wanted))} from the factor lane",
                     {"withoutAProducer": unknown}))
    return out


def context_checks() -> list[dict]:
    from context_features import DEFAULT_MACRO, ContextSource
    out = []
    today = date.today()

    from context_features import DURABLE_MACRO
    macro_path = Path(DEFAULT_MACRO)
    if not macro_path.exists():
        out.append(check("macroArtifactPresent", BLOCKED, f"missing: {macro_path}",
                         "rebuild: python tools/foundation/macro_pit.py --out "
                         ".cache/foundation/macro_rebuild"))
    else:
        # The dependency a live path would trip over: this file is under .cache, which
        # .gitignore excludes and the freeze record itself calls disposable.
        ignored = ".cache" in macro_path.as_posix()
        out.append(check("macroArtifactPresent", OK, str(macro_path)))
        out.append(check("macroArtifactIsDurable", BLOCKED if ignored else OK,
                         "the macro artifact lives under .cache/, which is gitignored and "
                         "documented as disposable" if ignored
                         else f"committed at {Path(DURABLE_MACRO).relative_to(ROOT).as_posix()}",
                         "a serving path that reads a disposable cache is one cleanup from "
                         "silently losing twenty of its forty-four features"))
        prov = ContextSource.load().provenance["macro"]
        v = prov.get("digestVerified")
        out.append(check("macroDigestVerifies",
                         OK if v else (UNKNOWN if v is None else BLOCKED),
                         f"sha256 {str(prov.get('sha256'))[:16]}, verified={v}",
                         "a mismatch raises rather than annotating: corrupt is worse than "
                         "absent, because absent shows as status 'absent' and corrupt reads "
                         "as evidence"))

    src = ContextSource.load()
    if src.macro_dates:
        newest = src.macro_dates[-1]
        age = (today - newest).days
        out.append(check("macroIsFresh", OK if age <= 5 else BLOCKED,
                         f"newest macro session {newest}, {age} days old (today {today})",
                         "staleness is visible per series in macro_*_age, so a model can see it; "
                         "an outright missing row cannot be seen and becomes an imputed mean"))
    else:
        out.append(check("macroIsFresh", UNKNOWN, "no macro rows loaded"))

    for name, path in (("events", ROOT / "data" / "foundation" / "events" / "events.json"),
                       ("press", ROOT / "data" / "foundation" / "events" / "press_evidence.jsonl"),
                       ("reactions", ROOT / "data" / "foundation" / "events" / "reactions.jsonl.gz")):
        out.append(check(f"{name}CorpusIsCommitted", OK if path.exists() else BLOCKED,
                         f"{path.relative_to(ROOT).as_posix()}: "
                         f"{'present' if path.exists() else 'missing'}",
                         "committed under data/, so unlike macro it survives a cache clean"))

    block = src.at(today, "AAPL", "US")
    observed = {k: (block[k] or {}).get("status")
                for k in ("macro", "events", "press", "reactionPrior", "quality")}
    out.append(check("producesABlockForToday",
                     OK if observed["macro"] == "observed" else BLOCKED,
                     f"block for {today} AAPL/US: {observed}"))
    vec = ContextSource.vector(block)
    nulls = [n for n, v in zip(ContextSource.feature_names(), vec) if v is None]
    out.append(check("todaysBlockIsNotMostlyNull", OK if len(nulls) <= len(vec) // 2 else BLOCKED,
                     f"{len(nulls)} of {len(vec)} context features null for this instrument today",
                     {"null": nulls}))
    return out


def recording_checks() -> list[dict]:
    """Is there somewhere to put a timestamped shadow prediction and its later outcome?"""
    out = []
    schema = ROOT / "prisma" / "schema.prisma"
    if not schema.exists():
        return [check("predictionRecordExists", UNKNOWN, "no prisma/schema.prisma")]
    text = schema.read_text(encoding="utf-8")
    for model, why in (("DecisionRun", "a dated run a prediction can belong to"),
                       ("DecisionCall", "one call, with its direction and evidence"),
                       ("CallOutcome", "what happened after the horizon matured")):
        out.append(check(f"model{model}Exists", OK if f"model {model} " in text else BLOCKED,
                         f"prisma/schema.prisma: {'present' if f'model {model} ' in text else 'absent'}",
                         why))
    shadow = "model ShadowPrediction " in text
    out.append(check("modelShadowPredictionExists", OK if shadow else BLOCKED,
                     f"prisma/schema.prisma: {'present' if shadow else 'absent'}",
                     "its own table, so an unapproved candidate's output cannot reach a "
                     "published path through a query someone forgot to filter"))
    for field, why in (
            ("modelVersion", "without it two candidates' shadow predictions are "
                             "indistinguishable once recorded"),
            ("modelSha256", "traces a prediction to the artifact bytes, not to a name someone "
                            "may have reused"),
            ("imputed", "at inference the training-mean rule silently turns a failed macro "
                        "refresh into 'an average day'; this column is what stops that looking "
                        "identical to a prediction built from evidence"),
            ("quality", "ok / degraded / refused, so a downgrade is a value and not a comment"),
            ("maturesAfter", "links a prediction to the outcome it can be judged by, later")):
        present = shadow and f"  {field} " in text
        out.append(check(f"shadowRecordHas_{field}", OK if present else BLOCKED,
                         f"ShadowPrediction.{field}: {'present' if present else 'absent'}", why))
    mig = ROOT / "prisma" / "migrations" / "20261017000000_shadow_prediction" / "migration.sql"
    out.append(check("shadowMigrationExists", OK if mig.exists() else BLOCKED,
                     f"{mig.relative_to(ROOT).as_posix()}: "
                     f"{'present' if mig.exists() else 'absent'}",
                     "CI applies migrations on a push touching prisma/**; applying from here "
                     "would risk the pooler advisory lock the handoff documents"))
    return out


def database_checks(probe: bool) -> list[dict]:
    """Reachability, by `SELECT 1` and nothing else, and only when asked.

    Opening a connection is a side effect, so the default run stays read-only and reports
    `unknown`. `--probe-db` runs one `SELECT 1`: no table is read, nothing is written, and a
    failure is reported rather than retried.
    """
    if not probe:
        return [check("databaseReachable", UNKNOWN,
                      "not probed; pass --probe-db to run a single SELECT 1",
                      "the fifteen price features are read from AssetFactor by the live lane")]
    try:
        sys.path.insert(0, str(ROOT / "jobs"))
        # The same way every job in jobs/ supplies its connection: load .env from the repository
        # root. Reading the variable from somewhere else would be a bypass, not a probe.
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        from nbt import db
    except Exception as e:                                   # noqa: BLE001
        return [check("databaseReachable", UNKNOWN,
                      f"jobs.nbt did not import: {type(e).__name__}: {e}")]
    if not os.environ.get("DATABASE_URL"):
        return [check("databaseReachable", UNKNOWN,
                      "DATABASE_URL is not set and .env did not supply one",
                      "no credential is read from anywhere else and none is printed")]
    try:
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT 1 AS ok")
        got = cur.fetchone()
        cur.close()
        conn.close()
        ok = (got or {}).get("ok") == 1 if isinstance(got, dict) else bool(got)
        out = [check("databaseReachable", OK if ok else BLOCKED,
                     f"SELECT 1 returned {got}", "read-only; no table touched, nothing written")]
        # The table a shadow run would write to. Its migration is committed, and `schema.yml`
        # applies migrations on a push touching prisma/** -- so until that run completes the
        # table is absent and recording is not yet possible. Reported, not assumed: a readiness
        # report that says "ready" while the destination table does not exist is the kind of
        # claim this whole file exists to avoid.
        conn2 = db()
        c = conn2.cursor()
        c.execute("SELECT to_regclass('public.\"ShadowPrediction\"') AS t")
        row = c.fetchone()
        c.close()
        conn2.close()
        exists = bool((row or {}).get("t")) if isinstance(row, dict) else bool(row and row[0])
        out.append(check("shadowTableExistsLive", OK if exists else BLOCKED,
                         f"to_regclass: {'present' if exists else 'absent'}",
                         "CI applies the migration on a push touching prisma/**; until then a "
                         "shadow run can compute predictions but cannot record them"))
        return out
    except Exception as e:                                   # noqa: BLE001
        return [check("databaseReachable", BLOCKED,
                      f"{type(e).__name__}: {str(e)[:160]}",
                      "shadow recording needs this; until it answers, recording is unverified")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--probe-db", action="store_true",
                    help="run one read-only SELECT 1 against DATABASE_URL")
    a = ap.parse_args()
    mdir = Path(a.model)

    checks = (model_checks(mdir) + feature_checks(mdir) + context_checks()
              + recording_checks() + database_checks(a.probe_db))
    counts = {s: sum(1 for c in checks if c["status"] == s) for s in (OK, BLOCKED, UNKNOWN)}
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "shadow-readiness-v1",
        "model": str(mdir.relative_to(ROOT)).replace("\\", "/"),
        "status": "assessment only; nothing deployed, no prediction recorded, no database written",
        "summary": counts,
        "ready": counts[BLOCKED] == 0 and counts[UNKNOWN] == 0,
        "checks": checks,
        "note": ("a NO-GO candidate may run in shadow once these hold, and may not be served as an "
                 "approved brain under any of them."),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    for c in checks:
        mark = {OK: "ok     ", BLOCKED: "BLOCKED", UNKNOWN: "unknown"}[c["status"]]
        print(f"  {mark} {c['check']:<34} {c['evidence'][:88]}")
    print(f"\nok {counts[OK]}  blocked {counts[BLOCKED]}  unknown {counts[UNKNOWN]}  "
          f"-> ready: {payload['ready']}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
