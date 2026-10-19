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
3. **A stored close at or before the session must exist.** The outcome is a move from the close the
   call was read from; with no close there is no base, and the row would mature into a record that
   is neither right nor wrong. A live caller refuses it rather than storing it.

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
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from context_features import ContextSource  # noqa: E402
import shadow_markets as mk  # noqa: E402

DEFAULT_MODEL = ROOT / "data" / "foundation" / "brain" / "brain-v2-context"
DEFAULT_DS = ROOT / ".cache" / "foundation" / "dataset_v4"
OUT = ROOT / "data" / "foundation" / "dataset" / "shadow_predictions.json"

OK, DEGRADED, REFUSED = "ok", "degraded", "refused"


def _git_short() -> str | None:
    """This checkout's short HEAD, recorded with every written row so a prediction is traceable to
    the code that produced it. Best effort: an absent git or a non-repo tree returns None."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True)
        return out.stdout.strip() or None
    except Exception:                                         # noqa: BLE001
        return None

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
    "a stored close at or before the session must exist, because a call with no base price cannot "
    "be scored later",
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
                horizon: int | None = None, strategy: str = "swing",
                timeframe: str | None = None,
                reference_price: float | None = None,
                reference_date: str | None = None,
                require_reference_price: bool = False) -> dict:
    """One record, whatever the inputs were worth. Never raises on missing data.

    `horizon` defaults to the session count the named `strategy` implies (`shadow_markets`), so a
    caller cannot record a call as "swing" and then measure it over an unrelated number of
    sessions. `reference_price` is the close the call was read from -- the base an outcome is
    measured against -- and is recorded, because without it a stored prediction cannot be scored
    without re-deriving what it saw.
    """
    if horizon is None:
        horizon = mk.STRATEGY_SESSIONS.get(strategy, 20)
    ctx_f = {}
    ctx_status = {}
    if ctx_block:
        ctx_f = dict(zip(ContextSource.feature_names(), ContextSource.vector(ctx_block)))
        ctx_status = {k: (ctx_block.get(k) or {}).get("status")
                      for k in ("macro", "events", "press", "reactionPrior", "quality", "news")}

    values, imputed, observed = [], [], {}
    for i, name in enumerate(model["features"]):
        v = price.get(name) if name in price else ctx_f.get(name)
        if isinstance(v, str):
            v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
        if v is None:
            imputed.append(name)
            observed[name] = None
            values.append(float(model["mu"][i]))     # the training mean: zero after standardising
        else:
            observed[name] = float(v)
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
    # A recorded call with no base price is a claim that can never be scored: the outcome is a
    # move from the close it was read from, and there is no close. A live caller refuses it rather
    # than storing a row that will sit as neither right nor wrong forever.
    if require_reference_price and reference_price is None:
        missing_critical.append(CRITICAL[2])

    base = {
        "asOf": as_of.isoformat(), "assetId": asset_id, "symbol": symbol, "market": market,
        "modelVersion": model["version"], "modelSha256": model["sha256"],
        "featureSchema": model["featureSchema"], "datasetVersion": model["datasetVersion"],
        "approved": False,
        "strategy": strategy, "timeframe": timeframe or strategy,
        "referencePrice": reference_price, "referenceDate": reference_date or as_of.isoformat(),
        "inputCutoff": as_of.isoformat(),
        "features": observed, "sources": ctx_status or None,
        "imputed": imputed, "imputedCount": len(imputed),
        "imputedExpected": expected, "imputedUnexpected": unexpected,
        "missingCritical": missing_critical or None,
        "contextStatus": ctx_status or None,
        "macroAsOf": (ctx_block or {}).get("macro", {}).get("asOf"),
        "macroAgeDays": (ctx_block or {}).get("macro", {}).get("ageDays"),
        "horizonSessions": horizon,
        # The n-th session of *this asset's market*, not n calendar weeks. A weekday market lands
        # on a weekday and crypto may land on a weekend, because that is when each trades.
        "maturesAfter": mk.matures_after(as_of, horizon, market).isoformat(),
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


def market_for_row(r: dict) -> str:
    """The market of a prediction row, from the same rule as everywhere else.

    Live rows already carry the market from `shadow_markets.market_of`. Dataset rows carry the
    stored `market` column (US/PK/FX only) and no `source`, so a `stock` there is `PK` only when
    that column says so; crypto, forex and commodity are still read off the asset type, which is
    why those no longer fall under US. One rule, reused by both paths.
    """
    m = mk.market_of(r.get("assetType"), r.get("source"))
    if m == "US" and (r.get("market") or "").strip().upper() == "PK":
        return "PK"
    return m


def select_rows(rows: list[dict], market: str | None, per_market: int) -> list[dict]:
    """Normalise each row's market, then apply `--market` and `--per-market`.

    Normalising first means the selectors work on the derived market, not the stored one, so a
    coin is selectable as `Crypto` even though its stored row says `US`. `--per-market` keeps at
    most N per market in the rows' own order, which is what makes a canary balanced instead of the
    alphabet's first names.
    """
    for r in rows:
        r["market"] = market_for_row(r)
    if market:
        rows = [r for r in rows if r["market"] == market]
    if per_market:
        kept, seen = [], {}
        for r in rows:
            m = r["market"]
            if seen.get(m, 0) < per_market:
                kept.append(r)
                seen[m] = seen.get(m, 0) + 1
        rows = kept
    return rows


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


PRICE_COLUMNS = ("r1", "r5", "r20", "returnZ", "volumeRatio", "peerMedianR20", "relStrength",
                 "peers", "sma20", "sma50", "rangePct", "drawdownPct", "entryTrigger",
                 "triggerDirection", "atr14")


def live_rows(limit: int):
    """The newest stored factor session per market, read from the live database.

    This is what makes a shadow prediction *prospective*. The frozen dataset ends at the last
    session with a fully elapsed 20-session forward window, so predicting on its newest date
    would be scoring rows whose outcome already exists -- a backtest wearing a shadow run's
    name. The newest `AssetFactor` session has no matured outcome yet, which is the whole point.

    `market` comes from `shadow_markets.market_of`, which reads `Asset.assetType` first and the
    source second. The older derivation here (`source == 'psx'` -> PK else US) filed FX,
    commodities and crypto under `US`; that is the defect this and the readiness report exist to
    stop repeating. The reference close -- the base an outcome is measured from -- is read
    alongside, so a stored prediction can be scored later without re-deriving what it saw.
    """
    sys.path.insert(0, str(ROOT / "jobs"))
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from nbt import db

    conn = db()
    cur = conn.cursor()
    market_sql = """CASE
        WHEN lower(a."assetType") = 'crypto' OR lower(coalesce(a.source, '')) LIKE '%paprika%'
          OR lower(coalesce(a.source, '')) LIKE '%coingecko%' THEN 'Crypto'
        WHEN lower(a."assetType") = 'forex' THEN 'FX'
        WHEN lower(a."assetType") = 'commodity' THEN 'Commodity'
        WHEN lower(coalesce(a.source, '')) = 'psx' THEN 'PK'
        ELSE 'US' END"""
    market_sql2 = market_sql.replace("a.", "a2.")
    cur.execute(
        f'SELECT max(f."periodEnd") AS d FROM "AssetFactor" f JOIN "Asset" a ON a.id = f."assetId" '
        f'GROUP BY {market_sql}'
    )
    dates = [r["d"] for r in cur.fetchall() if r.get("d")]
    if not dates:
        cur.close()
        conn.close()
        raise SystemExit("no AssetFactor rows: nothing to predict from")
    newest = max(dates)
    cols = ", ".join(f'f."{c}"' for c in PRICE_COLUMNS)
    cur.execute(
        f'SELECT f."assetId", f."periodEnd" AS factor_session, a.symbol, a."assetType", a.source, '
        # The base an outcome is measured from: the most recent stored close at or before the
        # session. `=` made this NULL whenever the factor session had no close of its own -- a
        # weekend session, or an ingest that lags -- and a NULL base is a prediction that can never
        # be scored. The close the call was read from is the last one on or before its session.
        '(SELECT s.close FROM "PriceSnapshot" s '
        'WHERE s."assetId" = f."assetId" AND s.date <= f."periodEnd" '
        'ORDER BY s.date DESC LIMIT 1) AS ref_close, '
        '(SELECT s.date FROM "PriceSnapshot" s '
        'WHERE s."assetId" = f."assetId" AND s.date <= f."periodEnd" '
        'ORDER BY s.date DESC LIMIT 1) AS ref_date, '
        + cols + " "
        f'FROM "AssetFactor" f JOIN "Asset" a ON a.id = f."assetId" '
        f'JOIN (SELECT {market_sql2} AS market, max(f2."periodEnd") AS d '
        f'FROM "AssetFactor" f2 JOIN "Asset" a2 ON a2.id = f2."assetId" '
        f'GROUP BY market) latest ON latest.market = {market_sql} AND latest.d = f."periodEnd" '
        'ORDER BY a.symbol LIMIT %s', (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = []
    for r in rows:
        session = r["factor_session"]
        out.append({"asOf": session.isoformat() if hasattr(session, "isoformat") else str(session),
                    "assetId": r["assetId"], "symbol": r["symbol"],
                    "assetType": r["assetType"],
                    "market": mk.market_of(r["assetType"], r["source"]),
                    "referencePrice": (float(r["ref_close"])
                                       if r["ref_close"] is not None else None),
                    "referenceDate": (r["ref_date"].isoformat()
                                      if r["ref_date"] is not None else None),
                    "pit": {"f": {c: r.get(c) for c in PRICE_COLUMNS}}})
    return out, (newest.isoformat() if hasattr(newest, "isoformat") else str(newest))


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
                '"macroAsOf","macroAgeDays","horizonSessions","maturesAfter",'
                '"strategy","timeframe","referencePrice","features","sources","inputCutoff",'
                '"runId","commit") '
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                "%s,%s,%s,%s,%s,%s,%s,%s) "
                # The identity key, not the old (modelVersion, assetId, asOf): two strategies may
                # both call the same asset on the same session, and a retry of the same event must
                # still be a no-op rather than a second row.
                'ON CONFLICT ("modelVersion","modelSha256","strategy","timeframe","assetId",'
                '"asOf","horizonSessions") DO NOTHING',
                (r["asOf"], r["assetId"], r["symbol"], r["market"], r["predicted"],
                 json.dumps(r["scores"]) if r["scores"] else None,
                 r["modelVersion"], r["modelSha256"], r["featureSchema"], r["datasetVersion"],
                 r["quality"], json.dumps(r["imputed"]), r["imputedCount"],
                 json.dumps(r["missingCritical"]) if r["missingCritical"] else None,
                 json.dumps(r["contextStatus"]) if r["contextStatus"] else None,
                 r["macroAsOf"], r["macroAgeDays"], r["horizonSessions"], r["maturesAfter"],
                 r.get("strategy"), r.get("timeframe"),
                 r.get("referencePrice"),
                 json.dumps(r["features"]) if r.get("features") else None,
                 json.dumps(r["sources"]) if r.get("sources") else None,
                 r.get("inputCutoff"), r.get("runId"), r.get("commit")))
            # Count rows the database actually inserted. A conflict means the event was already
            # recorded, and reporting that as "written" would make a rerun look additive when the
            # whole point of the identity key is that it is not.
            n += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        conn.commit()
        return {"written": n, "status": "ok"}
    except Exception as e:                                    # noqa: BLE001
        return {"written": 0, "status": "failed", "reason": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of")
    ap.add_argument("--live", action="store_true",
                    help="read the newest AssetFactor session from the database "
                         "instead of the frozen dataset; this is what makes a "
                         "shadow prediction prospective")
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--dataset", default=str(DEFAULT_DS))
    ap.add_argument("--prefix", default="examples-v4-context")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--market", default=None, choices=sorted(mk.MARKETS),
                    help="restrict to one market; pair with a per-market model artifact so a call "
                         "is recorded under the model built for its own market")
    ap.add_argument("--per-market", type=int, default=0,
                    help="keep at most N rows per market, so a canary is balanced across markets "
                         "instead of ordering the alphabet's first names")
    ap.add_argument("--strategy", default="swing", choices=sorted(mk.TIMEFRAMES),
                    help="the horizon profile this call is made under; the session count is "
                         "taken from shadow_markets, not guessed")
    ap.add_argument("--timeframe", default=None,
                    help="an optional finer timeframe label; defaults to the strategy name")
    ap.add_argument("--run-id", default=None,
                    help="an identifier for this run, recorded with every row it writes")
    ap.add_argument("--commit", default=None,
                    help="the commit to record with the rows; defaults to this checkout's HEAD")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    model = load_model(Path(a.model))
    print(f"model {model['version']} sha {model['sha256'][:16]} "
          f"({len(model['features'])} features, approved=False)")
    src = ContextSource.load()
    # A market filter has to see every market before it can keep one, so it ignores `--limit` and
    # pulls the whole session; the cap that matters is `--per-market`.
    pull = a.limit if not (a.market or a.per_market) else 200000
    if a.live:
        rows, as_of_str = live_rows(pull)
        print(f"live: newest AssetFactor session {as_of_str}, {len(rows)} assets")
    else:
        if not a.as_of:
            raise SystemExit("pass --as-of or --live")
        as_of_str = a.as_of
        rows = rows_at(Path(a.dataset), a.as_of, a.prefix, pull)
    if not rows:
        raise SystemExit(f"no rows with price features for {as_of_str}")
    as_of = date.fromisoformat(as_of_str)

    # Normalise each row's market once, then apply the selectors.
    rows = select_rows(rows, a.market, a.per_market)
    if not rows:
        raise SystemExit(f"no rows left after --market/--per-market for {as_of_str}")

    records = []
    for r in rows:
        row_as_of = date.fromisoformat(r.get("asOf", as_of_str))
        block = src.at(row_as_of, r["symbol"], r["market"])
        records.append(predict_one(model, r["pit"]["f"], block,
                                   asset_id=r.get("assetId") or r["symbol"],
                                   symbol=r["symbol"], market=r["market"],
                                   as_of=row_as_of, strategy=a.strategy, timeframe=a.timeframe,
                                   reference_price=r.get("referencePrice"),
                                   reference_date=r.get("referenceDate"),
                                   require_reference_price=bool(a.live)))

    by_q = {q: sum(1 for x in records if x["quality"] == q) for q in (OK, DEGRADED, REFUSED)}
    by_p = {}
    by_m = {}
    for x in records:
        by_p[x["predicted"]] = by_p.get(x["predicted"], 0) + 1
        by_m[x["market"]] = by_m.get(x["market"], 0) + 1
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "shadow-predict-v2",
        "status": "experimental; the model is NOT production-approved and nothing here is a "
                  "trading signal",
        "asOf": as_of_str, "source": "live AssetFactor" if a.live else "dataset",
        "model": model["version"], "modelSha256": model["sha256"],
        "strategy": a.strategy, "timeframe": a.timeframe or a.strategy,
        "criticalRules": list(CRITICAL),
        "byQuality": by_q, "byPredictedClass": by_p, "byMarket": by_m,
        "records": records,
    }
    if a.write:
        if not os.environ.get("DATABASE_URL"):
            payload["write"] = {"written": 0, "status": "unavailable",
                                "reason": "DATABASE_URL is not set"}
        else:
            run_id = a.run_id or f"shadow-{as_of_str}-{a.strategy}"
            commit = a.commit or _git_short()
            writable = [r for r in records if r["quality"] != REFUSED]
            for r in writable:
                r["runId"] = run_id
                r["commit"] = commit
            payload["write"] = write_rows(writable)
            payload["runId"] = run_id
            payload["commit"] = commit
        print(f"write: {payload['write']}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"  rows {len(records)}  quality {by_q}  predicted {by_p}")
    print(f"  by market {by_m}")
    worst = max(records, key=lambda r: r["imputedCount"])
    print(f"  most-imputed row: {worst['symbol']} {worst['imputedCount']} of "
          f"{len(model['features'])} features imputed, quality {worst['quality']}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
