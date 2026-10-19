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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from context_features import ContextSource  # noqa: E402
import shadow_budget  # noqa: E402
import shadow_markets as mk  # noqa: E402

DEFAULT_MODEL = ROOT / "data" / "foundation" / "brain" / "brain-v2-context"
DEFAULT_MODELS_ROOT = ROOT / "data" / "foundation" / "brain"
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
    "the session must be one this market trades, because a call dated to a day the market is "
    "closed is dated to a session that never happened",
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
                require_reference_price: bool = False,
                require_trading_session: bool = False) -> dict:
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
    # A session a market does not trade is not a session. A weekday call dated to Saturday, or a
    # US call dated to a day only crypto was open, would mature on a date the market never printed
    # a close for -- an outcome measured against nothing. A caller that reads a live session asks
    # for this; the check is per market, because the same date is a trading day for crypto.
    if require_trading_session and not mk.trades_on_market(market, as_of):
        missing_critical.append(CRITICAL[3])

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


def load_market_models(root: Path, horizon: int = 20) -> dict[str, dict]:
    """One candidate per market **for this horizon**, loaded from under `root`.

    A market with no artifact is a hard stop for the whole run, not a fall back to the global
    model: predicting US under `brain-v2-context` while recording the row as a per-market call is
    the relabelling this project spent a session removing. Every artifact loads through
    `load_model`, so each still has to be `productionApproved: false` to be served at all.

    The horizon is part of which artifact is correct, not a label applied afterwards. A model
    trained on `label20` answers a different question from one trained on `label5`, and serving
    the 20-session candidate under a 5-session call would record a horizon the model was never
    fitted for -- the same relabelling fault one level up. `brain-v4-<market>` is the 20-session
    family; `brain-v5-h<N>-<market>` is the family for horizon N.
    """
    out: dict[str, dict] = {}
    for m in mk.MARKETS:
        name = (f"brain-v4-{m.lower()}" if horizon == 20
                else f"brain-v5-h{horizon}-{m.lower()}")
        d = root / name
        if not (d / "model.json").exists():
            raise SystemExit(f"refusing: no per-market artifact for a {horizon}-session "
                             f"horizon at {d}")
        loaded = load_model(d)
        # The artifact says which horizon it was fitted for; a mismatch here is a wiring fault and
        # must stop the run rather than be recorded as evidence.
        trained_for = ((loaded.get("manifest") or {}).get("task") or {}).get("horizonSessions")
        if trained_for is not None and int(trained_for) != int(horizon):
            raise SystemExit(f"refusing: {d.name} was trained for a {trained_for}-session "
                             f"horizon but this run records {horizon}-session calls")
        out[m] = loaded
    return out


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


def _as_date(v) -> date:
    return v.date() if isinstance(v, datetime) else v


def _market_sessions(conn, floor: date) -> dict[str, list[date]]:
    """{market: sessions, newest first}, from the factor table, since `floor`.

    The factor table carries a row per asset per date, and the newest date is global. Only dates
    this market actually trades are kept, so a Sunday factor row for US -- the row exists because
    crypto traded -- is not offered as a US session.
    """
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT f."periodEnd" d, a."assetType" t, a.source s '
                'FROM "AssetFactor" f JOIN "Asset" a ON a.id = f."assetId" '
                'WHERE f."periodEnd" >= %s', (floor,))
    by_market: dict[str, set] = {}
    for r in cur.fetchall():
        d = _as_date(r["d"])
        m = mk.market_of(r["t"], r["s"])
        if mk.trades_on_market(m, d):
            by_market.setdefault(m, set()).add(d)
    cur.close()
    return {m: sorted(ds, reverse=True) for m, ds in by_market.items()}


def _rows_for_session(conn, session: date, market: str, limit: int) -> list[dict]:
    """Price features for one market's session, read from the live database."""
    cols = ", ".join(f'f."{c}"' for c in PRICE_COLUMNS)
    cur = conn.cursor()
    cur.execute(
        f'SELECT f."assetId", a.symbol, a."assetType", a.source, '
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
        'FROM "AssetFactor" f JOIN "Asset" a ON a.id = f."assetId" '
        'WHERE f."periodEnd" = %s ORDER BY a.symbol LIMIT %s', (session, limit))
    rows = cur.fetchall()
    cur.close()
    out = []
    for r in rows:
        m = mk.market_of(r["assetType"], r["source"])
        if m != market:
            continue
        out.append({"asOf": session.isoformat(),
                    "assetId": r["assetId"], "symbol": r["symbol"],
                    "assetType": r["assetType"],
                    "market": m,
                    "referencePrice": (float(r["ref_close"])
                                       if r["ref_close"] is not None else None),
                    "referenceDate": (r["ref_date"].isoformat()
                                      if r["ref_date"] is not None else None),
                    "pit": {"f": {c: r.get(c) for c in PRICE_COLUMNS}}})
    return out


def _choose_sessions(sessions: dict[str, list[date]], max_session_lag: int):
    """Pick each market's newest session, or name it stale. Pure.

    The reference date is the newest session *anywhere* (the most recent day any market traded),
    and a market is skipped when its own newest session is more than `max_session_lag` of its
    sessions behind it. On 2026-10-18 the newest anywhere is Sunday (crypto), US/PK/FX/Commodity
    are 0 US sessions behind (the Friday-to-Sunday span holds no US session), and crypto is 0 --
    so all five are served, each on its own date. A market whose ingest has stopped falls behind
    and is skipped rather than filled from an old date.
    """
    newest_anywhere = max((ds[0] for ds in sessions.values() if ds), default=None)
    chosen: dict[str, date] = {}
    skipped: dict[str, int] = {}
    for m in mk.MARKETS:
        ds = sessions.get(m)
        if not ds:
            continue
        lag = mk.sessions_between(ds[0], newest_anywhere, m) if newest_anywhere else 0
        if lag > max_session_lag:
            skipped[m] = lag
        else:
            chosen[m] = ds[0]
    return chosen, skipped


def live_rows(limit: int, *, max_session_lag: int = 2, lookback_days: int = 21):
    """Each market's newest stored factor session, read from the live database.

    This is what makes a shadow prediction *prospective*. The frozen dataset ends at the last
    session with a fully elapsed 20-session forward window, so predicting on its newest date
    would be scoring rows whose outcome already exists -- a backtest wearing a shadow run's
    name. The newest `AssetFactor` session has no matured outcome yet, which is the whole point.

    The session is chosen **per market**. Until now one global `max(periodEnd)` was used for all
    five markets, which on 2026-10-18 (a Sunday) was a session only crypto traded -- so a US, PK,
    FX or commodity call would have been dated to a day its market was closed, and its outcome
    would have been measured against a close that never printed. A market whose newest session is
    more than `max_session_lag` sessions behind the newest session anywhere is skipped and named,
    rather than filled from a stale date.

    `market` comes from `shadow_markets.market_of`, which reads `Asset.assetType` first and the
    source second. The reference close -- the base an outcome is measured from -- is read
    alongside, so a stored prediction can be scored later without re-deriving what it saw.

    Returns `(rows, sessions)` where `sessions` is `{market: session iso}`.
    """
    sys.path.insert(0, str(ROOT / "jobs"))
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from nbt import db

    conn = db()
    try:
        cur = conn.cursor()
        cur.execute('SELECT max("periodEnd") AS d FROM "AssetFactor"')
        newest = _as_date((cur.fetchone() or {}).get("d"))
        cur.close()
        if not newest:
            raise SystemExit("no AssetFactor rows: nothing to predict from")
        sessions = _market_sessions(conn, newest - timedelta(days=lookback_days))
        chosen, skipped = _choose_sessions(sessions, max_session_lag)
        rows = []
        for m in mk.MARKETS:
            if m in chosen:
                rows.extend(_rows_for_session(conn, chosen[m], m, limit))
    finally:
        conn.close()
    return rows, {m: d.isoformat() for m, d in chosen.items()}, skipped


def write_rows(records: list[dict], max_per_market_session: int = 0, *,
               min_headroom_mb: float = shadow_budget.MIN_HEADROOM_MB) -> dict:
    """Insert predictions idempotently, optionally enforcing a DB-backed market/session cap.

    Before any insert this checks the store's headroom against the free-tier cap (shadow_budget) and
    refuses when it is below `min_headroom_mb`, so the budget is enforced by the writer that spends
    it and not only by the workflow that happens to call it. The per-market/session cap counts the
    rows already stored and this run's inserts together, so it holds across retries.

    **The cap is per market, session and horizon, not per market and session.** It budgets rows
    against the free tier, and the unit it has to budget is the unit the identity key records: a
    5-session call and a 20-session call on the same asset and session are two different
    predictions and are stored as two rows. Counted without the horizon, the two rows an earlier
    20-session canary left for 2026-10-16 filled the quota for that market and session outright,
    and the first ten 5-session rows were refused with `skippedByCap: 10` -- a new horizon could
    never be started while an old one held the session. Measured on 2026-10-19; the cap is still
    two rows per market per session *per horizon*, so what it spends per horizon is unchanged.
    """
    try:
        sys.path.insert(0, str(ROOT / "jobs"))
        from nbt import db
    except Exception as e:                                    # noqa: BLE001
        return {"written": 0, "status": "unavailable", "reason": f"{type(e).__name__}: {e}"}
    try:
        conn = db()
        refusal = shadow_budget.refuse_if_full(conn, min_headroom_mb)
        if refusal:
            return refusal
        cur = conn.cursor()
        n = 0
        skipped_by_cap = 0
        skipped_already_matured = 0
        today = date.today()
        session_counts: dict[tuple[str, str, int], int] = {}
        for r in records:
            # A prospective prediction is one whose answer is not yet knowable. If this row's
            # horizon has already elapsed, the closes that decide it are either stored already or
            # will be before anyone looks, and writing it would be recording a forecast of the
            # past -- the one thing that would make every number on the scorecard worthless.
            #
            # This is not hypothetical. The features come from `AssetFactor`, whose newest session
            # lags the calendar whenever an ingest is behind: on 2026-10-19 the newest US factor
            # session was 2026-10-16, so a 1-session call would have been dated 2026-10-16 and
            # matured on 2026-10-19 -- a session already stored. Over a 5-session horizon the same
            # lag is harmless and the row is genuinely forward; over a short one it is not, and
            # the difference is a date comparison rather than a judgement call.
            #
            # Strictly after today, not on or after: a maturity date of today is a session that
            # may already have closed, and there is no cheap way to be sure from here. One day of
            # caution costs a row and buys the whole claim.
            matures = r.get("maturesAfter")
            matures = date.fromisoformat(matures) if isinstance(matures, str) else matures
            if matures is not None and matures <= today:
                skipped_already_matured += 1
                continue
            key = (r["market"], r["asOf"], int(r["horizonSessions"]))
            if max_per_market_session > 0:
                if key not in session_counts:
                    cur.execute(
                        'SELECT COUNT(*) AS n FROM "ShadowPrediction" '
                        'WHERE "market" = %s AND "asOf" = %s AND "horizonSessions" = %s', key)
                    existing = cur.fetchone() or {"n": 0}
                    session_counts[key] = int(existing["n"] if isinstance(existing, dict) else existing[0])
                if session_counts[key] >= max_per_market_session:
                    skipped_by_cap += 1
                    continue
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
            inserted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            n += inserted
            if max_per_market_session > 0:
                session_counts[key] += inserted
        conn.commit()
        result = {"written": n, "status": "ok"}
        if max_per_market_session > 0:
            result["skippedByCap"] = skipped_by_cap
        if skipped_already_matured:
            # Named, not silent. A run that drops every row because the inputs are stale must not
            # look like a run that had nothing to say.
            result["skippedAlreadyMatured"] = skipped_already_matured
        return result
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
    ap.add_argument("--per-market-models", action="store_true",
                    help="route each market to its own candidate artifact "
                         "brain-v4-<market> under --models-root; a market with no artifact "
                         "refuses the run rather than falling back to the global model")
    ap.add_argument("--models-root", default=str(DEFAULT_MODELS_ROOT))
    ap.add_argument("--max-session-lag", type=int, default=2,
                    help="in --live, skip a market whose newest factor session is more than this "
                         "many of its own sessions behind the newest session anywhere (default 2)")
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
    ap.add_argument("--max-per-market-session", type=int, default=0,
                    help="when writing, never exceed this many rows per market/session across retries; "
                         "0 leaves the writer uncapped (scheduled canary uses 2)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--min-headroom-mb", type=float, default=shadow_budget.MIN_HEADROOM_MB,
                    help="refuse to write when the database has less than this much room against "
                         "the free-tier cap; 0 disables the check (see shadow_budget)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    model = load_model(Path(a.model))
    print(f"model {model['version']} sha {model['sha256'][:16]} "
          f"({len(model['features'])} features, approved=False)")
    horizon = mk.STRATEGY_SESSIONS.get(a.strategy, 20)
    market_models = (load_market_models(Path(a.models_root), horizon)
                     if a.per_market_models else None)
    if market_models:
        print("per-market candidates: " + ", ".join(
            f"{m}={market_models[m]['version']}" for m in mk.MARKETS))
    src = ContextSource.load()
    # A market filter has to see every market before it can keep one, so it ignores `--limit` and
    # pulls the whole session; the cap that matters is `--per-market`.
    pull = a.limit if not (a.market or a.per_market) else 200000
    sessions: dict[str, str] = {}
    skipped: dict[str, int] = {}
    if a.live:
        rows, sessions, skipped = live_rows(pull, max_session_lag=a.max_session_lag)
        for m, s in sessions.items():
            print(f"live: {m} session {s}")
        for m, lag in skipped.items():
            print(f"live: skipping {m}: newest session {lag} sessions behind the newest anywhere "
                  f"(stale input; a fill from an older date would be dated to the wrong session)")
        if not rows:
            raise SystemExit("no market had a fresh session: nothing to predict from")
        as_of_str = max(sessions.values())
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
        row_as_of = date.fromisoformat(r["asOf"]) if r.get("asOf") else as_of
        row_model = market_models[r["market"]] if market_models else model
        block = src.at(row_as_of, r["symbol"], r["market"])
        records.append(predict_one(row_model, r["pit"]["f"], block,
                                   asset_id=r.get("assetId") or r["symbol"],
                                   symbol=r["symbol"], market=r["market"],
                                   as_of=row_as_of, strategy=a.strategy, timeframe=a.timeframe,
                                   reference_price=r.get("referencePrice"),
                                   reference_date=r.get("referenceDate"),
                                   require_reference_price=bool(a.live),
                                   require_trading_session=bool(a.live)))

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
        "sessions": sessions or None,
        "staleMarkets": (skipped or None),
        "model": ("per-market candidates" if market_models else model["version"]),
        "modelSha256": (None if market_models else model["sha256"]),
        "models": ({m: {"version": market_models[m]["version"],
                        "sha256": market_models[m]["sha256"]} for m in mk.MARKETS}
                   if market_models else None),
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
            if not writable:
                payload["write"] = {
                    "written": 0, "status": "refused",
                    "reason": "all candidate rows were refused by critical-input/session gates",
                }
            else:
                payload["write"] = write_rows(
                    writable, max_per_market_session=a.max_per_market_session,
                    min_headroom_mb=a.min_headroom_mb)
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
    if a.write and payload.get("write", {}).get("status") != "ok":
        print("shadow write did not complete successfully; see write status above", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
