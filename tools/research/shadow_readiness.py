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
                         "documented as disposable" if ignored else "outside .cache",
                         "a live lane must rebuild it on a schedule or move it somewhere durable; "
                         "a serving path that reads a disposable cache is one cleanup from "
                         "silently losing twenty of its forty-four features"))

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
    has_version = "modelVersion" in text
    out.append(check("predictionCarriesAModelVersion", OK if has_version else BLOCKED,
                     f"a `modelVersion` field is {'present' if has_version else 'absent'} "
                     "in the schema",
                     "without it two candidates' shadow predictions are indistinguishable once "
                     "recorded, and the comparison they exist for cannot be made"))
    out.append(check("imputationIsVisible", BLOCKED,
                     "no field records which features were imputed at prediction time",
                     "at training an absent feature takes the training mean, which is measured "
                     "and fine. At inference the same rule silently turns a failed macro refresh "
                     "into 'an average day', and the prediction looks as confident as one built "
                     "from observed evidence. A shadow record must carry the imputed set."))
    return out


def database_checks() -> list[dict]:
    """Live price factors come from the database. Reachability only; nothing is read or written."""
    if not os.environ.get("DATABASE_URL"):
        return [check("databaseReachable", UNKNOWN,
                      "DATABASE_URL is not set in this process; connectivity not attempted",
                      "the fifteen price features are read from AssetFactor by the live lane")]
    try:
        sys.path.insert(0, str(ROOT / "jobs"))
        from nbt import db                                   # noqa: F401
        return [check("databaseReachable", UNKNOWN,
                      "DATABASE_URL is set and jobs.nbt imports; no connection was opened "
                      "because this tool is read-only and a probe is a side effect")]
    except Exception as e:                                   # noqa: BLE001
        return [check("databaseReachable", UNKNOWN, f"jobs.nbt did not import: {type(e).__name__}")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    mdir = Path(a.model)

    checks = (model_checks(mdir) + feature_checks(mdir) + context_checks()
              + recording_checks() + database_checks())
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
