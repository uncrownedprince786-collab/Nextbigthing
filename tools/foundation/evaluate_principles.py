"""Run the testable principles through the walk-forward evaluator, cost-aware and multiple-testing aware.

    python tools/foundation/evaluate_principles.py --dataset DIR --out DIR [--horizon 20] [--max-rows N]

This is the capstone of the evaluation infrastructure, and it is deliberately NOT model training:
every rule here is a fixed, pre-registered function of the point-in-time features in the dataset,
written from the principle's own `signal` field before any result was seen. Nothing is fitted,
nothing is tuned on the outcome, and no rule is promoted into the live engine.

What each evaluation reports, from tools/foundation/walkforward.py:

* purged, embargoed walk-forward folds, so no training window's outcome reaches its test period;
* the mean net return at the low, base and high cost assumptions from tools/costs.py;
* a 95% interval bootstrapped over whole sessions, because rows on one date share a market move;
* an effective sample size that divides by the horizon, since 20-session outcomes overlap;
* the deflated Sharpe probability against the running trial count (Bailey and Lopez de Prado).

Two controls run through the identical folds and costs: buy-and-hold, and a reproducible coin
flip. A rule that does not beat both has found nothing, and the report says so per rule rather
than leaving a reader to compare.

A rule is reported PASS only when it beats both controls, its base-cost mean is positive, the
lower bound of its interval is above zero, and its deflated Sharpe probability clears 0.95. That
is a high bar on purpose: most of these will fail, and a corpus of honest failures is the
deliverable. No result here changes a live rule.
"""

from __future__ import annotations

import gzip
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

import walkforward as wf  # noqa: E402


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


# ---------------------------------------------------------------- feature access


def f(rec, key):
    p = rec.get("pit")
    return None if not p else p["f"].get(key)


def analog(rec, horizon="5"):
    p = rec.get("pit")
    a = (p or {}).get("an") or {}
    return a.get(horizon)


def sign(x, flip=False):
    if x is None:
        return 0
    s = 1 if x > 0 else -1 if x < 0 else 0
    return -s if flip else s


# ---------------------------------------------------------------- the rules
#
# Each is keyed by the principle id it tests, and each comment names the mapping from that
# principle's stated signal to the features this dataset holds. Where the mapping is partial, it
# says so; a partial test of a principle is evidence about this implementation, not about the paper.

def r_trend_ma(rec):
    """TREND-MA / TREND-FABER: close above its long moving average. sma50 is the longest stored."""
    c, s50 = f(rec, "sma20"), f(rec, "sma50")
    if c is None or s50 is None:
        return 0
    return 1 if c > s50 else -1


def r_mom_ts(rec):
    """MOM-TS: the sign of the asset's own trailing return. r20 is the longest span stored."""
    return sign(f(rec, "r20"))


def r_mom_xs_proxy(rec):
    """MOM-XS-12-1 (partial): a time-series stand-in. The real test ranks across the universe on
    the same date; this takes the sign of the 20-session return, skipping nothing."""
    return sign(f(rec, "r20"))


def r_rev_st(rec):
    """REV-ST-1M / REV-WEEKLY: fade the recent move. r5 is the shortest multi-day span stored."""
    return sign(f(rec, "r5"), flip=True)


def r_rev_1d(rec):
    """REV-WEEKLY at one session: fade yesterday's move."""
    return sign(f(rec, "r1"), flip=True)


def r_rev_zscore(rec):
    """REV-LIQ / SHOCK-INFO: fade only moves that are large against the asset's own recent history."""
    z = f(rec, "returnZ")
    if z is None or abs(z) < 2:
        return 0
    return -1 if z > 0 else 1


def r_vol_high(rec):
    """VOL-HIGH: long after unusually heavy volume."""
    v = f(rec, "volumeRatio")
    return 1 if v is not None and v >= 2.0 else 0


def r_mom_volume(rec):
    """MOM-VOLMOM / VOL-MOMVOL: the trend, taken only when volume confirms it."""
    v = f(rec, "volumeRatio")
    if v is None or v < 1.2:
        return 0
    return sign(f(rec, "r20"))


def r_52w_high(rec):
    """MOM-52WH (partial): nearness to the stored range high. rangePct is the position in the
    120-session range, not the 252-session one the paper uses."""
    p = f(rec, "rangePct")
    if p is None:
        return 0
    return 1 if p >= 90 else -1 if p <= 10 else 0


def r_drawdown(rec):
    """REV-LTR (partial): buy depth of drawdown. The stored window is 120 sessions, not 3 years."""
    d = f(rec, "drawdownPct")
    if d is None:
        return 0
    return 1 if d <= -25 else 0


def r_rel_strength(rec):
    """MOM-INDUSTRY / LINK-INDUSTRY-LEAD: the asset's 20-session return against its industry's."""
    return sign(f(rec, "relStrength"))


def r_low_vol(rec):
    """RISK-IVOL / QUAL-PRICE (partial): prefer the quiet. ATR relative to price is the stored
    dispersion measure; idiosyncratic volatility would need a factor regression."""
    a, c = f(rec, "atr14"), f(rec, "sma20")
    if a is None or not c:
        return 0
    return 1 if (a / c) < 0.015 else 0


def r_squeeze(rec):
    """TECH-FOUND family: the stored entry trigger, taken in its own stated direction."""
    d = f(rec, "triggerDirection")
    return 1 if d == "up" else -1 if d == "down" else 0


def r_analog_majority(rec):
    """The repository's own analog leg: trade with the measured majority of similar past days,
    only where the sample is graded well enough to describe anything."""
    a = analog(rec)
    if not a or a.get("grade") in (None, "none", "low") or not a.get("matches"):
        return 0
    share = a["positive"] / a["matches"]
    med = a.get("median")
    if med is None:
        return 0
    if share >= 0.6 and med > 0:
        return 1
    if share <= 0.4 and med < 0:
        return -1
    return 0


def r_setup_state(rec):
    """The reconstructed setup's own direction, where a replayed setup joined this row."""
    c = rec.get("candidate")
    if not c:
        return 0
    return 1 if c.get("state") == "buy" else -1 if c.get("state") == "short" else 0


RULES = [
    ("TREND-MA", "close above its 50-session mean", r_trend_ma),
    ("MOM-TS", "sign of the 20-session return", r_mom_ts),
    ("MOM-XS-12-1", "20-session return, time-series stand-in", r_mom_xs_proxy),
    ("REV-ST-1M", "fade the 5-session return", r_rev_st),
    ("REV-WEEKLY", "fade the 1-session return", r_rev_1d),
    ("REV-LIQ", "fade a 2-sigma one-day move", r_rev_zscore),
    ("VOL-HIGH", "long after volume twice its average", r_vol_high),
    ("VOL-MOMVOL", "trend confirmed by volume", r_mom_volume),
    ("MOM-52WH", "top or bottom decile of the stored range", r_52w_high),
    ("REV-LTR", "buy a 25 percent drawdown", r_drawdown),
    ("MOM-INDUSTRY", "return against the industry's", r_rel_strength),
    ("RISK-IVOL", "prefer low ATR relative to price", r_low_vol),
    ("TECH-FOUND", "the stored entry trigger", r_squeeze),
    ("NBT-ANALOG", "the repository's own analog majority", r_analog_majority),
    ("NBT-SETUP", "the replayed setup's own direction", r_setup_state),
]


# ---------------------------------------------------------------- running


def load(dataset: Path, max_rows: int | None, horizon: int):
    rows = []
    for p in sorted(dataset.glob("examples-v3-*.jsonl.gz")):
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r["outcome"].get(f"fwd{horizon}") is None:
                    continue
                rows.append(r)
                if max_rows and len(rows) >= max_rows:
                    return rows
    return rows


def verdict(res, controls) -> dict:
    """PASS only when it beats both controls on every count that matters."""
    if res.get("trades", 0) < 100:
        return {"verdict": "INSUFFICIENT", "why": "fewer than 100 trades"}
    reasons = []
    if res["meanNetPct"]["base"] <= 0:
        reasons.append("loses money at the base cost")
    if res["meanNetBaseCI95"][0] <= 0:
        reasons.append("the interval includes zero")
    for name, c in controls.items():
        if c and res["meanNetPct"]["base"] <= c["meanNetPct"]["base"]:
            reasons.append(f"does not beat {name}")
    p = res.get("deflatedSharpeProbability")
    if p is None or p < 0.95:
        reasons.append(f"deflated Sharpe probability {p}")
    return {"verdict": "PASS" if not reasons else "FAIL", "why": "; ".join(reasons) or "beats both controls, net of base costs, after the multiple-testing discount"}


def main() -> int:
    dataset, out = Path(arg("--dataset")), Path(arg("--out"))
    horizon = int(arg("--horizon") or 20)
    max_rows = int(arg("--max-rows") or 0) or None
    out.mkdir(parents=True, exist_ok=True)

    rows = load(dataset, max_rows, horizon)
    if not rows:
        print("::error title=evaluate::no mature rows in the dataset")
        return 2
    dates = sorted({r["asOf"] for r in rows})
    print(f"{len(rows):,} rows, {len(dates):,} sessions, {dates[0]} to {dates[-1]}", flush=True)

    log = wf.TrialLog(out / "trials.jsonl")
    results = {}
    # Controls first, so every rule is discounted against a trial count that already includes them.
    for name, rule in (("buy-and-hold", wf.buy_and_hold), ("coin-flip", wf.random_sign(20261014))):
        try:
            results[name] = wf.evaluate(rows, rule, name=name, horizon=horizon, log=log)
        except ValueError as e:
            results[name] = {"name": name, "error": str(e)}
        print(f"  control {name}: net base {results[name].get('meanNetPct', {}).get('base')}", flush=True)
    controls = {k: v for k, v in results.items() if "meanNetPct" in v}

    for pid, desc, rule in RULES:
        try:
            res = wf.evaluate(rows, rule, name=pid, horizon=horizon, log=log)
        except ValueError as e:
            results[pid] = {"name": pid, "error": str(e)}
            continue
        res["signalTested"] = desc
        res.update(verdict(res, controls))
        results[pid] = res
        print(f"  {pid:14} trades {res.get('trades', 0):7,} net {res.get('meanNetPct', {}).get('base')} "
              f"{res.get('verdict')}", flush=True)

    passed = [k for k, v in results.items() if v.get("verdict") == "PASS"]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": len(rows), "sessions": len(dates), "range": [dates[0], dates[-1]],
        "horizonSessions": horizon, "trialsLogged": log.count,
        "rulesEvaluated": len(RULES), "passed": passed,
        "controls": {k: {"meanNetPct": v["meanNetPct"], "trades": v["trades"]} for k, v in controls.items()},
        "results": results,
        "whatThisIsNot": [
            "Not model training: every rule is a fixed function written before any result was seen.",
            "Not a promotion path: no result here changes a live decision rule.",
            "A partial mapping of a principle to the stored features tests this implementation, "
            "not the published finding.",
        ],
    }
    (out / "principles_evaluation.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"::notice title=principles evaluation::{json.dumps({'rows': len(rows), 'rules': len(RULES), 'passed': passed, 'trials': log.count})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
