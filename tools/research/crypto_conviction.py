"""When should the brain speak, and when should it say it sees nothing?

    python tools/research/crypto_conviction.py
    python tools/research/crypto_conviction.py --lanes btc:m5 crypto:m5

Every served lane today answers on every bar. At five minutes the pooled model is right 53.1% of
the time doing that, which is a real edge and a thin one, and a reader handed a direction on a bar
the model is near-indifferent about is being told something the model did not mean.

The models' own probabilities say when that is happening. On the pooled five-minute holdout,
accuracy rises from 0.531 at full coverage to 0.603 on the 14.7% of rows furthest from 0.5. That
is not abstention dressed up as accuracy -- it is only honest if the coverage travels with it,
which is why every number here is a pair -- but it does mean the model knows something about which
of its own calls to trust, and a brain that stays quiet on the rest is a better instrument than
one that fills the silence.

The rule, fixed before the test fold was read
---------------------------------------------
For each lane, from the ladder of margin floors:

    the HIGHEST floor at which the model still speaks on at least one VALIDATION bar in ten.

Chosen on the validation fold alone. Accuracy on called rows rises monotonically with the floor in
every lane measured, so maximising it without a coverage floor would select "speak almost never";
the one-in-ten floor is the product decision, stated here rather than tuned, and it is what makes
this a choice between two defensible lanes rather than a search for the prettiest number.

Then, and only then, the test fold is read once and the gated lane is measured on it:

  * accuracy on the called rows, against **those rows' own** majority -- a floor selects rows and
    a selection can move the base rate, so the comparison has to be made inside the selection;
  * coverage on the test fold, which is the claim "it will speak this often" tested out of sample;
  * both directions still called, neither above 0.80 of what it says;
  * a day-blocked bootstrap of (accuracy - majority) over the called rows, excluding zero;
  * above its own block majority in at least four of five chronological blocks of called rows.

A lane whose gated form fails any of these keeps serving ungated, and the failure is recorded.
Nothing here can promote a lane that was refused: conviction is a filter on a lane that already
passed, never a second chance for one that did not.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import gbm  # noqa: E402
from crypto_horizons import HORIZONS  # noqa: E402
from crypto_matrix import prepare_cached, symbols_with  # noqa: E402
from train_crypto_short import (  # noqa: E402
    day_blocked_bootstrap,
    labels_for,
    logistic_proba,
    split,
)

BRAIN_ROOT = ROOT / "data" / "foundation" / "brain"
OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_conviction.json"

#: The ladder the floor is chosen from. Fixed; not searched over finer steps, because a floor
#: fitted to three decimal places on one validation fold is a floor fitted to that fold.
LADDER = (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.075, 0.10, 0.125, 0.15)

#: The product decision: a brain that answers fewer than one bar in ten is not answering.
MIN_VALIDATION_COVERAGE = 0.10

#: Out of sample the coverage may drift; below this the lane's promise about how often it speaks
#: is not one the holdout supports.
MIN_TEST_COVERAGE = 0.05

GATES = {
    "aboveCalledMajority": "accuracy on called rows strictly above those rows' own larger class",
    "bothDirectionsCalled": "neither direction above 0.80 of the calls made",
    "bootstrapExcludesZero": "95% day-blocked bootstrap for (accuracy - majority) over called "
                             "rows, strictly above zero",
    "walkForwardMajority": "above its own block majority in at least 4 of 5 chronological blocks "
                           "of called rows",
    "testCoverageHeld": f"speaks on at least {MIN_TEST_COVERAGE:.0%} of the test fold",
}


def load_artifact(name: str) -> dict:
    p = BRAIN_ROOT / name / "model.json"
    if not p.exists():
        raise SystemExit(f"no artifact at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def score(artifact: dict, X: np.ndarray) -> np.ndarray:
    m = artifact["model"]
    if m.get("kind") == "gbm-logistic":
        return gbm.predict_proba(m, X)
    return logistic_proba(m, X)


def blocks_above(p: np.ndarray, y: np.ndarray, blocks: int = 5) -> dict:
    pred = (p >= 0.5).astype(int)
    edges = np.linspace(0, len(y), blocks + 1).astype(int)
    rows, above = [], 0
    for i in range(blocks):
        a, b = edges[i], edges[i + 1]
        if b - a < 100:
            continue
        yy, pp = y[a:b], pred[a:b]
        acc = float((pp == yy).mean())
        maj = float(max(yy.mean(), 1 - yy.mean()))
        above += 1 if acc > maj else 0
        rows.append({"block": i, "rows": int(b - a), "accuracy": round(acc, 5),
                     "majority": round(maj, 5), "above": bool(acc > maj)})
    return {"blocks": rows, "blocksAboveMajority": above, "blocksScored": len(rows)}


def at_floor(p: np.ndarray, y: np.ndarray, floor: float) -> dict:
    """What the lane looks like when it only speaks above `floor`."""
    sel = np.abs(p - 0.5) >= floor
    n = int(sel.sum())
    out = {"minMargin": floor, "rows": n, "coverage": round(n / len(y), 5)}
    if n < 500:
        out.update({"accuracy": None, "note": "under 500 called rows, not reported"})
        return out
    yy, pp = y[sel], (p[sel] >= 0.5).astype(int)
    up = float(yy.mean())
    maj = max(up, 1 - up)
    acc = float((pp == yy).mean())
    out.update({
        "accuracy": round(acc, 5),
        "majorityHere": round(maj, 5),
        "marginOverMajority": round(acc - maj, 5),
        "upShareCalled": round(float(pp.mean()), 5),
        "upRate": round(up, 5),
    })
    return out


def choose_floor(p_val: np.ndarray, y_val: np.ndarray) -> tuple[float, list[dict]]:
    """The pre-registered choice: the highest floor still speaking on one validation bar in ten."""
    curve = [at_floor(p_val, y_val, f) for f in LADDER]
    eligible = [c for c in curve if c["coverage"] >= MIN_VALIDATION_COVERAGE
                and c["accuracy"] is not None]
    chosen = max((c["minMargin"] for c in eligible), default=0.0)
    return chosen, curve


def measure(p: np.ndarray, y: np.ndarray, ts: np.ndarray, floor: float) -> dict:
    sel = np.abs(p - 0.5) >= floor
    n = int(sel.sum())
    base = at_floor(p, y, floor)
    if n < 500:
        return {**base, "gates": None, "gatesMet": False,
                "why": "under 500 called rows on the test fold"}
    yy, pp = y[sel], p[sel]
    pred = (pp >= 0.5).astype(int)
    up = float(yy.mean())
    maj_class = 1 if up >= 0.5 else 0
    boot = day_blocked_bootstrap((pred == yy).astype(float),
                                 (yy == maj_class).astype(float),
                                 (ts[sel] // 86_400_000).astype(np.int64))
    wf = blocks_above(pp, yy)
    up_share = float(pred.mean())
    checks = {
        "aboveCalledMajority": base["accuracy"] > base["majorityHere"],
        "bothDirectionsCalled": bool(max(up_share, 1 - up_share) <= 0.80),
        "bootstrapExcludesZero": bool(boot["excludesZero"]),
        "walkForwardMajority": wf["blocksScored"] > 0
        and wf["blocksAboveMajority"] >= min(4, wf["blocksScored"]),
        "testCoverageHeld": base["coverage"] >= MIN_TEST_COVERAGE,
    }
    return {**base, "blockedBootstrap": boot, "walkForward": wf,
            "gates": checks, "gatesMet": all(checks.values()), "why": None}


def lane_rows(tag: str, horizon: str) -> dict:
    h = HORIZONS[horizon]
    interval = h["interval"]
    symbols = ["BTCUSDT"] if tag == "btc" else symbols_with(interval)
    stride = 1 if tag == "btc" else 5
    data = prepare_cached(symbols, interval, stride)
    y, usable, _ = labels_for(data, h["bars"])
    ts = data["ts"]
    step_ms = next(iter(data["corpora"].values()))["stepMs"]
    tr_m, va_m, te_m, split_meta = split(ts, h["bars"], step_ms)
    va = np.flatnonzero(va_m & usable)
    te = np.flatnonzero(te_m & usable)
    # The test rows are ordered by time so the walk-forward blocks are chronological, which is the
    # only ordering that makes "four of five blocks" a statement about consistency over time.
    te = te[np.argsort(ts[te], kind="stable")]
    va = va[np.argsort(ts[va], kind="stable")]
    return {"data": data, "y": y, "ts": ts, "va": va, "te": te, "split": split_meta,
            "symbols": symbols, "stride": stride, "interval": interval}


def run_lane(tag: str, horizon: str, verbose: bool = True) -> dict:
    name = f"brain-c1-{tag}-{horizon}"
    artifact = load_artifact(name)
    r = lane_rows(tag, horizon)
    X = r["data"]["X"]
    p_va = score(artifact, X[r["va"]].astype(np.float64))
    y_va = r["y"][r["va"]]
    floor, val_curve = choose_floor(p_va, y_va)

    p_te = score(artifact, X[r["te"]].astype(np.float64))
    y_te = r["y"][r["te"]]
    ungated = measure(p_te, y_te, r["ts"][r["te"]], 0.0)
    gated = measure(p_te, y_te, r["ts"][r["te"]], floor)
    test_curve = [at_floor(p_te, y_te, f) for f in LADDER]

    if verbose:
        g = gated
        print(f"   {name}: floor {floor:.3f} chosen on validation "
              f"(val coverage {next(c['coverage'] for c in val_curve if c['minMargin'] == floor):.1%})",
              flush=True)
        print(f"      ungated test {ungated['accuracy']:.4f} on {ungated['coverage']:.0%} "
              f"(majority {ungated['majorityHere']:.4f})", flush=True)
        if g["accuracy"] is None:
            print(f"      gated: {g['why']}", flush=True)
        else:
            print(f"      gated   test {g['accuracy']:.4f} on {g['coverage']:.1%} "
                  f"(majority {g['majorityHere']:.4f}, margin {g['marginOverMajority']:+.4f}, "
                  f"boot95 [{g['blockedBootstrap']['ci95'][0]:+.4f},"
                  f"{g['blockedBootstrap']['ci95'][1]:+.4f}], "
                  f"wf {g['walkForward']['blocksAboveMajority']}/"
                  f"{g['walkForward']['blocksScored']}) "
                  f"-> {'GO' if g['gatesMet'] else 'NO-GO'}", flush=True)
    return {
        "family": tag,
        "horizon": horizon,
        "modelVersion": name,
        "interval": r["interval"],
        "symbols": r["symbols"],
        "stride": r["stride"],
        "split": r["split"],
        "rows": {"validation": int(len(r["va"])), "test": int(len(r["te"]))},
        "chosenFloor": floor,
        "validationCurve": val_curve,
        "testCurve": test_curve,
        "ungatedOnTest": ungated,
        "gatedOnTest": gated,
        "serveGated": bool(gated["gatesMet"] and floor > 0.0),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Choose and measure a speak-or-stay-quiet floor.")
    ap.add_argument("--lanes", nargs="*", default=["btc:m5", "btc:m15", "btc:h1",
                                                   "crypto:m5", "crypto:m15"])
    a = ap.parse_args()

    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_conviction.py",
        "rule": ("the highest margin floor at which the model still speaks on at least one "
                 f"validation bar in {int(1 / MIN_VALIDATION_COVERAGE)}, chosen on the validation "
                 "fold alone and then measured once on the test fold"),
        "ladder": list(LADDER),
        "minValidationCoverage": MIN_VALIDATION_COVERAGE,
        "minTestCoverage": MIN_TEST_COVERAGE,
        "preRegisteredGates": GATES,
        "limitations": [
            "The floor is a selection rule on a historical holdout. Coverage out of sample is a "
            "measurement on that holdout, not a guarantee about how often the live brain speaks.",
            "Direction only. No transaction cost, spread, funding or slippage is in any number "
            "here, and nothing here is a profitability claim.",
        ],
        "lanes": [],
    }
    for spec in a.lanes:
        tag, _, horizon = spec.partition(":")
        if horizon not in HORIZONS:
            raise SystemExit(f"unknown horizon in {spec!r}")
        print(f"== {tag} {horizon}", flush=True)
        out["lanes"].append(run_lane(tag, horizon))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")
    gated = [l for l in out["lanes"] if l["serveGated"]]
    print(f"{len(gated)} of {len(out['lanes'])} lanes earn a conviction floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
