"""Build a shadow prediction, and say exactly what it was built from.

    python tools/research/shadow_predict.py --as-of 2026-09-25 [--limit 20] [--out FILE]
    python tools/research/shadow_predict.py --as-of 2026-09-25 --write        (needs DATABASE_URL)

A shadow prediction is the output of a candidate that is **not approved for production**. It is
recorded so that its outcome can be measured after the horizon matures, and for no other purpose.
Nothing in `app/` reads the table this writes to, `approved` is false, and there is no code path
here that sets it true.

The problem this file exists to solve
--------------------------------------
At training, an absent feature takes the training fold's mean. That is measured, recorded and
fine. **At inference the same rule is a silent substitution.** A macro refresh that failed, or an
instrument with no event records, becomes "an average day" -- and the prediction comes out looking
exactly as confident as one built from observed evidence. Nothing downstream can tell them apart,
and the later outcome evaluation would then be averaging two different things.

So every prediction here carries the list of features that were imputed, and a `quality` that is
one of three:

  * **ok**       nothing the model usually had is missing. Features that are routinely absent in
                 training -- `entryTrigger` is null on about 90% of training rows, because a
                 trigger only exists when there is one -- are imputed and listed, but they are the
                 normal case and do not degrade anything.
  * **degraded** a feature the model usually HAD is missing now. Listed in `imputedUnexpected`.
  * **refused**  a critical input was missing. **No prediction is produced at all.**

What counts as critical, and why
---------------------------------
Two rules, both conservative, both stated before any prediction was made:

1. **Every price feature must be observed.** The dataset itself drops a row without them --
   `assemble.py` writes no `pit` and every loader skips it -- so predicting from imputed price
   features would be scoring a row the model was never trained on the like of.
2. **The macro block must be observed.** It is twenty of the model's forty-four inputs. A
   prediction with all twenty invented is not a context-aware prediction with a caveat; it is a
   price-only prediction wearing a context-aware model's name, and its errors would be filed
   under the wrong candidate.

Missing *optional* context -- an instrument with no press records, a reaction window not yet
closed -- is ordinary and expected: those columns are null on more than 93% of the training rows
too. Those degrade, they do not refuse.

Writing
-------
`--write` requires `DATABASE_URL` and inserts into `ShadowPrediction`. Without it nothing touches
any database and the records are printed or written to a file, which is the default because a
dry run is the thing you want when checking whether the path works at all.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from context_features import ContextSource  # noqa: E402

DEFAULT_MODEL = ROOT / "data" / "foundation" / "brain" / "brain-v2-context"
DEFAULT_DS = ROOT / ".cache" / "foundation" / "dataset_v4"
OUT = ROOT / "data" / "foundation" / "dataset" / "shadow_predictions.json"

OK, DEGRADED, REFUSED = "ok", "degraded", "refused"

#: A feature is critical when the model almost always saw it while training. Read from the
#: training manifest's own `nullShareByFeature` rather than hard-coded, because the first version
#: of this file hard-coded "every price feature" and refused 24 of 25 rows: `entryTrigger` and
#: `triggerDirection` are null on about 90% of TRAINING rows by design -- a trigger only exists
#: when there is one -- so refusing on them refuses exactly the rows the model was trained on.
#: The model's own experience of a column is the only honest definition of whether it needs it.
CRITICAL_NULL_SHARE = 0.10
#: Above this, a feature was absent for most of training too, so its absence now is the normal
#: case and not a degradation. `entryTrigger` is null on about 90% of training rows -- a trigger
#: only exists when there is one -- and calling every ordinary row degraded because of it would
#: make the word mean nothing. A degradation is a feature the model usually HAD and now lacks.
ROUTINELY_ABSENT_NULL_SHARE = 0.50
CRITICAL = (
    f"every feature the model saw on more than {1 - CRITICAL_NULL_SHARE:.0%} of training rows "
    "must be observed",
    "the macro block must be observed (20 of 44 inputs)",
)


def load_model(mdir: Path) -> dict:
    m = json.loads((mdir / "model.json").read_text(encoding="utf-8"))
    man_path = mdir / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    if m.get("productionApproved") is not False:
        raise SystemExit("refusing: this tool only serves a candidate marked not "
                         "production-approved")
    return {
        "meta": m, "manifest": man,
        "features": list(m["features"]), "classes": list(m["classes"]),
        "W": np.asarray(m["weights"], dtype=np.float64),
        "mu": np.asarray(m["standardisation"]["mean"], dtype=np.float64),
        "sd": np.asarray(m["standardisation"]["sd"], dtype=np.float64),
        "sha256": (man.get("artifact") or {}).get("sha256", ""),
        "version": m["modelVersion"],
        "featureSchema": m.get("contextFeatureVersion", "unknown"),
        "datasetVersion": (man.get("dataset") or {}).get("prefix"),
        "critical": sorted(k for k, v in (man.get("nullShareByFeature") or {}).items()
                           if v is not None and v < CRITICAL_NULL_SHARE),
        "trainingNullShare": man.get("nullShareByFeature") or {},
    }


def predict_one(model: dict, price: dict, ctx_block: dict | None, *,
                asset_id: str, symbol: str, market: str, as_of: date,
                horizon: int = 20) -> dict:
    """One record, whatever the inputs were worth. Never raises on missing data."""
    ctx_f = {}
    ctx_status = {}
    if ctx_block:
        ctx_f = dict(zip(ContextSource.feature_names(), ContextSource.vector(ctx_block)))
        ctx_status = {k: (ctx_block.get(k) or {}).get("status")
                      for k in ("macro", "events", "press", "reactionPrior", "quality", "news")}

    values, imputed = [], []
    for i, name in enumerate(model["features"]):
        v = price.get(name) if name in price else ctx_f.get(name)
        if isinstance(v, str):
            v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
        if v is None:
            imputed.append(name)
            values.append(float(model["mu"][i]))     # the training mean: zero after standardising
        else:
            values.append(float(v))

    critical = set(model.get("critical") or ())
    shares = model.get("trainingNullShare") or {}
    hit = sorted(n for n in imputed if n in critical)
    expected = sorted(n for n in imputed
                      if (shares.get(n) or 0.0) >= ROUTINELY_ABSENT_NULL_SHARE)
    unexpected = sorted(n for n in imputed if n not in critical and n not in expected)
    missing_critical = []
    if hit:
        missing_critical.append(f"{CRITICAL[0]}: {', '.join(hit)}")
    if ctx_status.get("macro") != "observed":
        missing_critical.append(CRITICAL[1])

    base = {
        "asOf": as_of.isoformat(), "assetId": asset_id, "symbol": symbol, "market": market,
        "modelVersion": model["version"], "modelSha256": model["sha256"],
        "featureSchema": model["featureSchema"], "datasetVersion": model["datasetVersion"],
        "approved": False,
        "imputed": imputed, "imputedCount": len(imputed),
        "imputedExpected": expected, "imputedUnexpected": unexpected,
        "missingCritical": missing_critical or None,
        "contextStatus": ctx_status or None,
        "macroAsOf": (ctx_block or {}).get("macro", {}).get("asOf"),
        "macroAgeDays": (ctx_block or {}).get("macro", {}).get("ageDays"),
        "horizonSessions": horizon,
        "maturesAfter": (as_of + timedelta(days=horizon * 7 // 5 + 4)).isoformat(),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if missing_critical:
        # No prediction at all. A refusal that still carried a class would be the failure this
        # whole file is about, only harder to notice.
        return {**base, "quality": REFUSED, "predicted": None, "scores": None}

    z = (np.asarray(values, dtype=np.float64) - model["mu"]) / model["sd"]
    logits = np.hstack([z, [1.0]]) @ model["W"]
    e = np.exp(logits - logits.max())
    p = e / e.sum()
    return {**base,
            "quality": DEGRADED if unexpected else OK,
            "predicted": model["classes"][int(logits.argmax())],
            "scores": {c: round(float(p[i]), 6) for i, c in enumerate(model["classes"])}}


def rows_at(ds: Path, as_of: str, prefix: str, limit: int):
    """Price features for one session, read from the built dataset.

    The dataset is used here as a stand-in for the live factor read: it holds exactly the fields
    `jobs/factors.py` writes, under the same names, so the vector this assembles is the one a live
    caller would assemble. What it does not prove is database reachability, which
    `shadow_readiness.py` reports separately and does not fold into this.
    """
    year = as_of[:4]
    f = ds / f"{prefix}-{year}.jsonl.gz"
    if not f.exists():
        return []
    out = []
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["asOf"] != as_of:
                continue
            pit = r.get("pit") or {}
            if not pit.get("f"):
                continue
            out.append(r)
            if len(out) >= limit:
                break
    return out


def write_rows(records: list[dict]) -> dict:
    """Insert into ShadowPrediction. Returns what happened; never raises on a missing table."""
    try:
        sys.path.insert(0, str(ROOT / "jobs"))
        from nbt import db
    except Exception as e:                                    # noqa: BLE001
        return {"written": 0, "status": "unavailable", "reason": f"{type(e).__name__}: {e}"}
    try:
        conn = db()
        cur = conn.cursor()
        n = 0
        for r in records:
            cur.execute(
                'INSERT INTO "ShadowPrediction" ("asOf","assetId","symbol","market","predicted",'
                '"scores","modelVersion","modelSha256","featureSchema","datasetVersion",'
                '"quality","imputed","imputedCount","missingCritical","contextStatus",'
                '"macroAsOf","macroAgeDays","horizonSessions","maturesAfter") '
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                'ON CONFLICT ("modelVersion","assetId","asOf") DO NOTHING',
                (r["asOf"], r["assetId"], r["symbol"], r["market"], r["predicted"],
                 json.dumps(r["scores"]) if r["scores"] else None,
                 r["modelVersion"], r["modelSha256"], r["featureSchema"], r["datasetVersion"],
                 r["quality"], json.dumps(r["imputed"]), r["imputedCount"],
                 json.dumps(r["missingCritical"]) if r["missingCritical"] else None,
                 json.dumps(r["contextStatus"]) if r["contextStatus"] else None,
                 r["macroAsOf"], r["macroAgeDays"], r["horizonSessions"], r["maturesAfter"]))
            n += 1
        conn.commit()
        return {"written": n, "status": "ok"}
    except Exception as e:                                    # noqa: BLE001
        return {"written": 0, "status": "failed", "reason": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--dataset", default=str(DEFAULT_DS))
    ap.add_argument("--prefix", default="examples-v4-context")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    model = load_model(Path(a.model))
    print(f"model {model['version']} sha {model['sha256'][:16]} "
          f"({len(model['features'])} features, approved=False)")
    src = ContextSource.load()
    as_of = date.fromisoformat(a.as_of)

    rows = rows_at(Path(a.dataset), a.as_of, a.prefix, a.limit)
    if not rows:
        raise SystemExit(f"no rows with price features for {a.as_of}")

    records = []
    for r in rows:
        block = src.at(as_of, r["symbol"], r.get("market"))
        records.append(predict_one(model, r["pit"]["f"], block,
                                   asset_id=r.get("assetId") or r["symbol"],
                                   symbol=r["symbol"], market=r.get("market") or "",
                                   as_of=as_of))

    by_q = {q: sum(1 for x in records if x["quality"] == q) for q in (OK, DEGRADED, REFUSED)}
    by_p = {}
    for x in records:
        by_p[x["predicted"]] = by_p.get(x["predicted"], 0) + 1
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "shadow-predict-v1",
        "status": "experimental; the model is NOT production-approved and nothing here is a "
                  "trading signal",
        "asOf": a.as_of, "model": model["version"], "modelSha256": model["sha256"],
        "criticalRules": list(CRITICAL),
        "byQuality": by_q, "byPredictedClass": by_p,
        "records": records,
    }
    if a.write:
        if not os.environ.get("DATABASE_URL"):
            payload["write"] = {"written": 0, "status": "unavailable",
                                "reason": "DATABASE_URL is not set"}
        else:
            payload["write"] = write_rows([r for r in records if r["quality"] != REFUSED])
        print(f"write: {payload['write']}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"  rows {len(records)}  quality {by_q}  predicted {by_p}")
    worst = max(records, key=lambda r: r["imputedCount"])
    print(f"  most-imputed row: {worst['symbol']} {worst['imputedCount']} of "
          f"{len(model['features'])} features imputed, quality {worst['quality']}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
