"""Score matured shadow predictions against what the market actually did.

    python tools/research/shadow_score.py [--as-of 2026-11-20] [--out FILE]

Read-only over `ShadowPrediction` and `PriceSnapshot`: it writes a scorecard file and **never
changes a prediction**. A prediction is the thing being judged; a scorer that edited it would be
grading the exam by editing the answers.

The rule it grades against is the one the model was trained on, imported rather than re-stated
------------------------------------------------------------------------------------------------
`tools/make_dataset.py` fixes the label at `label20 = UP when fwd20 >= +2%, DOWN when <= -2%, else
FLAT`, over the close 20 sessions later. Copying that rule here would let the two drift, and a
shadow scorecard that graded on a threshold the model was not trained under would be measuring the
scorer, not the model. So this file calls `make_dataset.outcomes` and reads
`make_dataset.LABEL_THRESHOLD_PCT`.

What it refuses to do
----------------------
* **It does not score an unelapsed horizon.** `mature` is computed from this market's own session
  count after the decision session, not from the wall clock, and an immature row is counted as
  `awaiting` -- never as a wrong direction.
* **It does not score a horizon it has no rule for.** The label is defined at 20 sessions. A
  `position` prediction at 60 has no fixed rule yet, so it is reported as `unscorable` with the
  reason, rather than graded on an invented band.
* **It does not fabricate an accuracy over nothing.** When no row has matured, `accuracy` is
  `null`, because a percentage over zero scored records is not a number.
"""

from __future__ import annotations

import argparse
import json
import os
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
    `make_dataset.forward_bars` returns them.
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


def load_predictions(cur, as_of: date, limit: int) -> list[dict]:
    cur.execute(
        'SELECT id, "assetId", symbol, "market", "predicted", "modelVersion", "asOf", '
        '"horizonSessions" FROM "ShadowPrediction" ORDER BY "asOf" ASC, symbol ASC LIMIT %s',
        (limit,),
    )
    return cur.fetchall()


def db():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from nbt import db as _db
    return _db()


def build(cur, as_of: date, limit: int) -> dict:
    """Read predictions, compute each one's realized outcome, and aggregate."""
    from make_dataset import base_closes, forward_bars

    preds = load_predictions(cur, as_of, limit)
    by_as_of: dict[date, "tuple[dict, dict]"] = {}
    rows: list[dict] = []
    for p in preds:
        a = p["asOf"]
        if a not in by_as_of:
            by_as_of[a] = (base_closes(cur, a), forward_bars(cur, a))
        closes, fwd = by_as_of[a]
        horizon = p.get("horizonSessions") or LABEL_SESSIONS
        market = p.get("market")
        # A horizon with no fixed rule, or a market whose timeframe the stored data cannot judge,
        # is reported unscorable rather than graded on a guess.
        if horizon != LABEL_SESSIONS:
            rows.append({"id": p["id"], "symbol": p["symbol"], "market": market,
                         "predicted": p["predicted"], "asOf": a.isoformat(),
                         "scorable": False, "mature": False,
                         "reason": f"only the {LABEL_SESSIONS}-session label is defined; this is "
                                   f"a {horizon}-session horizon"})
            continue
        if not mk.capability(market, "swing")["verifiable"]:
            rows.append({"id": p["id"], "symbol": p["symbol"], "market": market,
                         "predicted": p["predicted"], "asOf": a.isoformat(),
                         "scorable": False, "mature": False,
                         "reason": f"{market} swing is not verifiable from stored closes"})
            continue
        s = score_one(p["predicted"], closes.get(p["assetId"]), fwd.get(p["assetId"], []))
        sessions_elapsed = mk.sessions_between(a, as_of, market)
        s.update({"id": p["id"], "symbol": p["symbol"], "market": market,
                  "predicted": p["predicted"], "asOf": a.isoformat(),
                  "sessionsElapsed": sessions_elapsed})
        rows.append(s)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "shadow-scorecard-v1",
        "status": "assessment only; no prediction is modified and no promotion is implied",
        "asOf": as_of.isoformat(),
        "labelRule": (f"label20 = UP when fwd20 >= +{LABEL_THRESHOLD_PCT}%, DOWN when <= "
                      f"-{LABEL_THRESHOLD_PCT}%, else FLAT; step {WINDOW} sessions"),
        "summary": aggregate(rows),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    as_of = date.fromisoformat(a.as_of)

    conn = db()
    cur = conn.cursor()
    payload = build(cur, as_of, a.limit)
    cur.close()
    conn.close()

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    s = payload["summary"]
    print(f"rows {s['total']}  awaiting {s['awaiting']}  matured {s['matured']}  "
          f"graded {s['graded']}  accuracy {s['accuracy']}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
