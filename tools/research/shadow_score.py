"""Score matured shadow predictions against what the market actually did.

    python tools/research/shadow_score.py                       # dry run, prints the state
    python tools/research/shadow_score.py --write               # record final outcomes
    python tools/research/shadow_score.py --as-of 2026-11-20 --write

Read-only over `ShadowPrediction` and `PriceSnapshot` unless `--write` is given, in which case it
writes **`ShadowOutcome` rows and nothing else**. A prediction is the thing being judged; a scorer
that edited it would be grading the exam by editing the answers. The prediction row is never
touched -- not to make scoring easier, not to record the result.

The rule it grades against is the one the model was trained on, imported rather than re-stated
------------------------------------------------------------------------------------------------
`tools/make_dataset.py` fixes the label at `label20 = UP when fwd20 >= +2%, DOWN when <= -2%, else
FLAT`, over the close 20 sessions later. Copying that rule here would let the two drift, and a
shadow scorecard that graded on a threshold the model was not trained under would be measuring the
scorer, not the model. So this file calls `make_dataset.outcomes` and reads
`make_dataset.LABEL_THRESHOLD_PCT`. A horizon with no defined rule is reported `unscorable`, never
graded on an invented band.

Idempotency, so a rerun is not additive
---------------------------------------
A final outcome's `observedOn` is the session the horizon matured on, computed from the market's own
calendar and therefore the same on every run. `ShadowOutcome` is unique on
`(predictionId, observedOn, final)`, and this tool writes with `ON CONFLICT ... DO NOTHING`, so
rerunning it records no second result. An unelapsed horizon is `awaiting` and is never written.

What it refuses to do
----------------------
* **It does not score an unelapsed horizon.** `mature` comes from the stored closes, not the clock.
* **It does not score a horizon it has no rule for** (a 60-session position): reported unscorable.
* **It does not read a missing outcome as FLAT** or as a failed prediction -- `None` is "no move
  measured yet", which is a different fact.
* **It does not fabricate a price, maturity or outcome**, and it never modifies a prediction.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

import shadow_markets as mk  # noqa: E402
from make_dataset import LABEL_THRESHOLD_PCT, WINDOW, outcomes  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "shadow_scorecard.json"
LABEL_SESSIONS = 20
SCORER_VERSION = "shadow-scorer-v1"
SCORING_RULE = (f"label20 = UP when fwd20 >= +{LABEL_THRESHOLD_PCT}%, DOWN when <= "
                f"-{LABEL_THRESHOLD_PCT}%, else FLAT; step {WINDOW} sessions")


def forward_label(fwd20: float | None) -> str | None:
    """The trained label from a 20-session forward return. `None` when the window is not closed."""
    if fwd20 is None:
        return None
    if fwd20 >= LABEL_THRESHOLD_PCT:
        return "UP"
    if fwd20 <= -LABEL_THRESHOLD_PCT:
        return "DOWN"
    return "FLAT"


def score_one(predicted: str | None, base: float | None, bars: list[dict]) -> dict:
    """One prediction's realized outcome, using the shared forward-outcome rule.

    `bars` are the sessions strictly after the decision session, oldest first, as
    `forward_bars` returns them.
    """
    if base is None:
        return {"scorable": False, "reason": "no reference close stored for the decision session"}
    out = outcomes(float(base), bars)
    f20 = out.get("fwd20")
    label = forward_label(f20)
    return {
        "scorable": f20 is not None,
        "mature": bool(out.get("mature20")),
        "sessionsAvailable": out.get("sessionsAvailable"),
        "fwd20": f20, "mfe": out.get("mfe"), "mae": out.get("mae"),
        "outcomeLabel": label,
        "correct": (None if label is None or predicted is None else label == predicted),
    }


def _tally(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        if v is not None:
            out[v] = out.get(v, 0) + 1
    return out


def aggregate(rows: list[dict]) -> dict:
    """Counts by state, and an accuracy only over rows that actually matured and were graded."""
    waiting = [r for r in rows if not r["scorable"] or not r["mature"]]
    matured = [r for r in rows if r["scorable"] and r["mature"]]
    graded = [r for r in matured if r["outcomeLabel"] is not None and r["predicted"] is not None]
    correct = sum(1 for r in graded if r["correct"])
    return {
        "total": len(rows),
        "awaiting": len(waiting),
        "matured": len(matured),
        "graded": len(graded),
        "byPredicted": _tally(r["predicted"] for r in rows),
        "byOutcome": _tally(r["outcomeLabel"] for r in matured),
        "correct": correct,
        # Over graded rows only. `null` -- not 0 -- when nothing has matured.
        "accuracy": (round(correct / len(graded), 4) if graded else None),
        "note": ("descriptive only; this is not a promotion decision and no threshold is applied "
                 "here"),
    }


def by_market(rows: list[dict]) -> dict:
    """Per-market reconciliation: how many are waiting, how many matured, how many were graded."""
    out: dict[str, dict] = {}
    for r in rows:
        m = r.get("market") or "?"
        d = out.setdefault(m, {"total": 0, "awaiting": 0, "matured": 0, "graded": 0, "correct": 0})
        d["total"] += 1
        if not r["scorable"] or not r["mature"]:
            d["awaiting"] += 1
        else:
            d["matured"] += 1
            if r.get("outcomeLabel") is not None and r.get("predicted") is not None:
                d["graded"] += 1
                d["correct"] += int(bool(r.get("correct")))
    return out


def load_predictions(cur, limit: int) -> list[dict]:
    cur.execute(
        'SELECT id, "assetId", symbol, "market", "predicted", "modelVersion", "asOf", '
        '"horizonSessions", "referencePrice", "strategy", "timeframe" FROM "ShadowPrediction" '
        'ORDER BY "asOf" ASC, symbol ASC LIMIT %s',
        (limit,),
    )
    return cur.fetchall()


def forward_bars_with_source(cur, as_of: date) -> dict[str, list[dict]]:
    """Up to WINDOW sessions strictly after `as_of`, per asset, oldest first, with the price source.

    The same shape `make_dataset.forward_bars` returns, plus `source`, which the scorecard records
    as the provenance of the observed close. The label itself still comes from
    `make_dataset.outcomes`, so the rule has one definition.
    """
    cur.execute(
        '''
        SELECT "assetId", date, close, source
        FROM (
            SELECT s."assetId", s.date, s.close, s.source,
                   row_number() OVER (PARTITION BY s."assetId" ORDER BY s.date ASC) AS rn
            FROM "PriceSnapshot" s
            WHERE s.date > %s AND s.close IS NOT NULL
        ) t
        WHERE rn <= %s
        ORDER BY "assetId", date ASC
        ''',
        (as_of, WINDOW),
    )
    out: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        out.setdefault(r["assetId"], []).append(r)
    return out


def db():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from nbt import db as _db
    return _db()


def _unscorable(p, market, reason) -> dict:
    return {"id": p["id"], "symbol": p["symbol"], "market": market,
            "predicted": p["predicted"], "asOf": p["asOf"].isoformat(),
            "scorable": False, "mature": False, "reason": reason}


def build(cur, as_of: date, limit: int, write: bool = False, conn=None) -> dict:
    """Read predictions, compute each one's realized outcome, and (optionally) write finals."""
    from make_dataset import base_closes

    preds = load_predictions(cur, limit)
    by_as_of: dict[date, tuple] = {}
    rows: list[dict] = []
    finals: list[dict] = []
    for p in preds:
        a = p["asOf"]
        if a not in by_as_of:
            by_as_of[a] = (base_closes(cur, a), forward_bars_with_source(cur, a))
        closes, fwd = by_as_of[a]
        horizon = p.get("horizonSessions") or LABEL_SESSIONS
        market = p.get("market")
        if market not in mk.MARKETS:
            rows.append(_unscorable(p, market, f"unknown market {market!r}"))
            continue
        # A horizon with no fixed rule, or a market whose timeframe stored data cannot judge, is
        # reported unscorable rather than graded on a guess.
        if horizon != LABEL_SESSIONS:
            rows.append(_unscorable(p, market, f"only the {LABEL_SESSIONS}-session label is "
                                               f"defined; this is a {horizon}-session horizon"))
            continue
        if not mk.capability(market, "swing")["verifiable"]:
            rows.append(_unscorable(p, market, f"{market} swing is not verifiable from closes"))
            continue
        # A call dated to a session the market does not trade has no origin: the close it was read
        # from belongs to an earlier session, and the forward window starts from a day that printed
        # nothing. Eight rows recorded before the per-market session fix carry a Sunday `asOf`
        # (2026-10-18) for US/PK/FX/Commodity; scoring them would measure a move the market never
        # made. They are reported unscorable and kept, not deleted -- the defect stays visible next
        # to its fix.
        if not mk.trades_on_market(market, a):
            rows.append(_unscorable(p, market,
                                    f"{a.isoformat()} is not a session {market} trades"))
            continue
        bars = fwd.get(p["assetId"], [])
        base = closes.get(p["assetId"])
        s = score_one(p["predicted"], base, bars)
        s.update({"id": p["id"], "symbol": p["symbol"], "market": market,
                  "predicted": p["predicted"], "asOf": a.isoformat(),
                  "sessionsElapsed": mk.sessions_between(a, as_of, market)})
        rows.append(s)
        if s["mature"]:
            obs = bars[horizon - 1]
            to_session = obs["date"]
            to_session = date.fromisoformat(to_session) if isinstance(to_session, str) else to_session
            finals.append({
                "predictionId": p["id"], "final": True, "label": s["outcomeLabel"],
                "fwdPct": s["fwd20"], "referencePrice": float(base),
                "observedPrice": float(obs["close"]), "observedOn": to_session,
                "fromSession": a, "toSession": to_session,
                "sessionsElapsed": horizon, "horizonSessions": horizon,
                "mfe": s["mfe"], "mae": s["mae"], "source": obs.get("source"),
                "scoringRule": SCORING_RULE, "scorerVersion": SCORER_VERSION,
                "observedAt": datetime.now(timezone.utc)})

    result: dict = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "shadow-scorecard-v1",
        "status": "assessment only; no prediction is modified and no promotion is implied",
        "asOf": as_of.isoformat(),
        "labelRule": SCORING_RULE,
        "summary": aggregate(rows),
        "byMarket": by_market(rows),
        "rows": rows,
    }
    if write:
        result["write"] = write_outcomes(cur, conn, finals)
    return result


def write_outcomes(cur, conn, finals: list[dict]) -> dict:
    """Insert final outcomes, idempotently. Returns what happened; never raises on a missing table."""
    if not finals:
        return {"written": 0, "status": "nothing-matured"}
    n = 0
    try:
        for o in finals:
            cur.execute(
                'INSERT INTO "ShadowOutcome" ("predictionId","final","label","fwdPct",'
                '"referencePrice","observedPrice","observedOn","fromSession","toSession",'
                '"sessionsElapsed","horizonSessions","mfe","mae","source","scoringRule",'
                '"scorerVersion","observedAt") '
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                'ON CONFLICT ("predictionId","observedOn","final") DO NOTHING',
                (o["predictionId"], o["final"], o["label"], o["fwdPct"], o["referencePrice"],
                 o["observedPrice"], o["observedOn"], o["fromSession"], o["toSession"],
                 o["sessionsElapsed"], o["horizonSessions"], o["mfe"], o["mae"], o["source"],
                 o["scoringRule"], o["scorerVersion"], o["observedAt"]))
            n += cur.rowcount if cur.rowcount is not None else 0
        conn.commit()
        return {"written": n, "eligible": len(finals), "status": "ok"}
    except Exception as e:                                    # noqa: BLE001
        try:
            conn.rollback()
        except Exception:                                     # noqa: BLE001
            pass
        return {"written": 0, "eligible": len(finals), "status": "failed",
                "reason": f"{type(e).__name__}: {str(e)[:200]}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--write", action="store_true",
                    help="record final ShadowOutcome rows; without it this is a dry run")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    as_of = date.fromisoformat(a.as_of)

    conn = db()
    cur = conn.cursor()
    payload = build(cur, as_of, a.limit, write=a.write, conn=conn)
    cur.close()
    conn.close()

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    s = payload["summary"]
    mode = "write" if a.write else "dry run"
    print(f"[{mode}] rows {s['total']}  awaiting {s['awaiting']}  matured {s['matured']}  "
          f"graded {s['graded']}  accuracy {s['accuracy']}")
    for m, d in sorted(payload["byMarket"].items()):
        print(f"  {m:10} total {d['total']:>4}  awaiting {d['awaiting']:>4}  "
              f"matured {d['matured']:>4}  graded {d['graded']:>4}  correct {d['correct']:>4}")
    if a.write:
        print(f"write: {payload.get('write')}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
