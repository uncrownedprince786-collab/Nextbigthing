"""Does a bigger tree, a longer fit or a different feature set read crypto direction any better?

    python tools/research/crypto_capacity.py --tag crypto --horizon m5
    python tools/research/crypto_capacity.py --tag btc --horizon m15 --grid wide

Every number this prints is measured on the **validation** fold. The test fold is not loaded, not
scored and not mentioned: the whole point of a sweep is that it tries many things, and a sweep
that reads the holdout has spent it. `train_crypto_short.py` remains the only file that reads the
test fold, and it reads it once, for whichever configuration this one recommends.

What is swept
-------------
  * **depth** -- the current artifacts are depth 3. A depth-3 tree can express a three-way
    interaction and no more; whether direction needs a fourth is a measurement, not a preference.
  * **learning rate and rounds** -- a smaller step with more rounds is the standard way to buy
    accuracy from a boosted tree, and early stopping on the validation fold decides where it
    stops rather than the argument doing it.
  * **feature set** -- the full forty-one, and the thirty-seven that survive a venue which
    publishes no taker-side volume. The second exists because the serving chain can fall past
    Binance, and a model fitted without those inputs reads a Coinbase window as the window it was
    fitted on rather than as four imputed neutrals.

What is reported for each configuration
---------------------------------------
Headline validation accuracy against the validation fold's own majority, and the **conviction
curve**: accuracy and coverage as the probability margin floor rises. The second is what the
serving decision actually turns on -- a brain that speaks on every bar at 53% and one that speaks
on a fifth of them at 58% are different products, and the curve is where that choice is read.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import gbm  # noqa: E402
from crypto_horizons import HORIZONS  # noqa: E402
from crypto_matrix import prepare_cached, symbols_with  # noqa: E402
from intraday_features import FEATURES  # noqa: E402
from market_context import CONTEXT_FEATURES  # noqa: E402
from train_crypto_short import fit_logistic, labels_for, logistic_proba, split  # noqa: E402

OUT_DIR = ROOT / "data" / "foundation" / "dataset"

#: The inputs a venue without taker-side volume or a trade count cannot supply. Kept by name so
#: the list is checked against the feature order rather than assumed to be a contiguous block.
FLOW_FEATURES = ["tbi1", "tbi12", "tbi48", "tsz48"]

BTC = ["BTCUSDT"]

#: The margin floors the conviction curve is read at. `0.0` is "speak on every bar", which is what
#: the lanes do today.
FLOORS = (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.075, 0.10, 0.125, 0.15)

GRIDS: dict[str, list[dict]] = {
    # The fitted artifacts' own configuration first, so every row is read against the thing it
    # would replace rather than against an abstract baseline.
    "narrow": [
        {"depth": 3, "rounds": 300, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 4, "rounds": 600, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 5, "rounds": 600, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 6, "rounds": 800, "lr": 0.03, "l2": 4.0, "features": "all"},
    ],
    "wide": [
        {"depth": 3, "rounds": 300, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 3, "rounds": 900, "lr": 0.02, "l2": 2.0, "features": "all"},
        {"depth": 4, "rounds": 600, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 5, "rounds": 600, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 5, "rounds": 900, "lr": 0.03, "l2": 4.0, "features": "all"},
        {"depth": 6, "rounds": 800, "lr": 0.03, "l2": 4.0, "features": "all"},
        {"depth": 7, "rounds": 800, "lr": 0.03, "l2": 8.0, "features": "all"},
        {"depth": 5, "rounds": 600, "lr": 0.05, "l2": 2.0, "features": "noflow"},
    ],
    "flow": [
        {"depth": 3, "rounds": 300, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 3, "rounds": 300, "lr": 0.05, "l2": 2.0, "features": "noflow"},
        {"depth": 5, "rounds": 600, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 5, "rounds": 600, "lr": 0.05, "l2": 2.0, "features": "noflow"},
    ],
    # Does showing the model what the rest of the market was doing help? Run on a matrix built
    # with --context, so every configuration here is fitted and scored on the same rows.
    "context": [
        {"depth": 3, "rounds": 400, "lr": 0.05, "l2": 2.0, "features": "all"},
        {"depth": 3, "rounds": 400, "lr": 0.05, "l2": 2.0, "features": "context"},
        {"depth": 3, "rounds": 400, "lr": 0.05, "l2": 2.0, "features": "contextonly"},
        {"depth": 5, "rounds": 600, "lr": 0.05, "l2": 2.0, "features": "context"},
    ],
}


#: The full column order a context matrix carries: f1, then the market-factor block.
ALL_WITH_CONTEXT = list(FEATURES) + list(CONTEXT_FEATURES)


def feature_columns(which: str) -> tuple[list[int], list[str]]:
    """Which columns a named feature set uses, out of a matrix that may carry the context block.

    `all` is the forty-one of f1 and nothing else, whether or not the matrix has context columns
    appended -- so "f1 against f1 plus context" is one matrix read two ways, on identical rows.
    That matters more than it looks: context drops the rows the factor has no bar for, and
    comparing a 41-feature fit on all rows against a 52-feature fit on fewer would be comparing
    two different test sets and calling the difference a feature.
    """
    if which == "all":
        return list(range(len(FEATURES))), list(FEATURES)
    if which == "noflow":
        keep = [i for i, f in enumerate(FEATURES) if f not in FLOW_FEATURES]
        return keep, [FEATURES[i] for i in keep]
    if which == "context":
        return list(range(len(ALL_WITH_CONTEXT))), list(ALL_WITH_CONTEXT)
    if which == "contextonly":
        # The factor block alone, as the control: if this scores like the full set, the coin's own
        # bars are carrying nothing and the pooled model is a market-direction model wearing a
        # coin's name.
        base = len(FEATURES)
        return list(range(base, base + len(CONTEXT_FEATURES))), list(CONTEXT_FEATURES)
    raise SystemExit(f"unknown feature set {which!r}")


def conviction_curve(p: np.ndarray, y: np.ndarray) -> list[dict]:
    """Accuracy and coverage as the probability margin floor rises.

    `majorityHere` travels with every row because a floor selects rows, and a selection can move
    the base rate it should be judged against. Accuracy of 0.58 on rows that are 0.56 UP is a much
    smaller claim than 0.58 on rows that are even, and the pair is the only honest way to read it.
    """
    conf = np.abs(p - 0.5)
    pred = (p >= 0.5).astype(int)
    out = []
    for floor in FLOORS:
        sel = conf >= floor
        n = int(sel.sum())
        if n < 500:
            out.append({"minMargin": floor, "rows": n, "coverage": round(n / len(y), 5),
                        "accuracy": None, "note": "under 500 rows, not reported"})
            continue
        yy = y[sel]
        up = float(yy.mean())
        out.append({
            "minMargin": floor,
            "rows": n,
            "coverage": round(n / len(y), 5),
            "accuracy": round(float((pred[sel] == yy).mean()), 5),
            "majorityHere": round(max(up, 1 - up), 5),
            "upShareCalled": round(float(pred[sel].mean()), 5),
        })
    return out


def run_one(Xtr: np.ndarray, ytr: np.ndarray, Xva: np.ndarray, yva: np.ndarray,
            cfg: dict, verbose: int = 0) -> dict:
    t0 = time.time()
    tree = gbm.fit(Xtr, ytr, rounds=cfg["rounds"], depth=cfg["depth"], lr=cfg["lr"],
                   l2=cfg["l2"], X_val=Xva, y_val=yva, early_stop=40, verbose=verbose)
    p = gbm.predict_proba(tree, Xva)
    acc = float(((p >= 0.5).astype(int) == yva).mean())
    up = float(yva.mean())
    return {
        **cfg,
        "fitSeconds": round(time.time() - t0, 1),
        "roundsKept": tree["roundsKept"],
        "roundsFitted": tree["roundsFitted"],
        "validationAccuracy": round(acc, 5),
        "validationMajority": round(max(up, 1 - up), 5),
        "marginOverMajority": round(acc - max(up, 1 - up), 5),
        "convictionCurve": conviction_curve(p, yva),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validation-fold capacity sweep for a crypto lane.")
    ap.add_argument("--tag", required=True, choices=["btc", "crypto"])
    ap.add_argument("--horizon", required=True, choices=list(HORIZONS))
    ap.add_argument("--grid", default="narrow", choices=list(GRIDS))
    ap.add_argument("--stride", type=int, default=None,
                    help="default: 1 for btc, 5 for the pooled fit (what the artifacts used)")
    ap.add_argument("--context", action="store_true",
                    help="build the matrix with the market-factor block appended")
    ap.add_argument("--verbose", type=int, default=0)
    a = ap.parse_args()

    h = HORIZONS[a.horizon]
    interval = h["interval"]
    symbols = BTC if a.tag == "btc" else symbols_with(interval)
    stride = a.stride if a.stride is not None else (1 if a.tag == "btc" else 5)

    print(f"== {a.tag} {a.horizon} ({h['label']}) on {len(symbols)} symbols at {interval}, "
          f"stride {stride}", flush=True)
    data = prepare_cached(symbols, interval, stride, context=a.context)
    y, usable, _ = labels_for(data, h["bars"])
    ts = data["ts"]
    step_ms = next(iter(data["corpora"].values()))["stepMs"]
    tr_m, va_m, _te_m, split_meta = split(ts, h["bars"], step_ms)
    tr = np.flatnonzero(tr_m & usable)
    va = np.flatnonzero(va_m & usable)
    print(f"   train {len(tr):,}  validation {len(va):,}  "
          f"(test fold not loaded)", flush=True)

    results = []
    for cfg in GRIDS[a.grid]:
        cols, names = feature_columns(cfg["features"])
        Xtr = data["X"][tr][:, cols].astype(np.float64)
        Xva = data["X"][va][:, cols].astype(np.float64)
        ytr = y[tr].astype(np.float64)
        yva = y[va].astype(np.int64)
        label = (f"depth {cfg['depth']} rounds {cfg['rounds']} lr {cfg['lr']} "
                 f"l2 {cfg['l2']} {cfg['features']}({len(names)})")
        print(f"   -- {label}", flush=True)
        r = run_one(Xtr, ytr, Xva, yva.astype(np.float64).astype(np.int64), cfg, a.verbose)
        r["featureCount"] = len(names)
        at5 = next((c for c in r["convictionCurve"] if c["minMargin"] == 0.05), None)
        print(f"      val acc {r['validationAccuracy']:.4f} "
              f"(majority {r['validationMajority']:.4f}, margin {r['marginOverMajority']:+.4f})  "
              f"kept {r['roundsKept']}/{r['roundsFitted']}  {r['fitSeconds']:.0f}s"
              + (f"   @0.05: {at5['accuracy']:.4f} on {at5['coverage']:.1%}"
                 if at5 and at5["accuracy"] is not None else ""), flush=True)
        results.append(r)

    results.sort(key=lambda r: -r["validationAccuracy"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"crypto_capacity_{a.tag}_{a.horizon}.json"
    out.write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_capacity.py",
        "measuredOn": "the validation fold only; the test fold is not read by this file",
        "tag": a.tag,
        "horizon": a.horizon,
        "interval": interval,
        "symbols": symbols,
        "stride": stride,
        "marketContext": bool(a.context),
        "rows": {"train": int(len(tr)), "validation": int(len(va))},
        "split": split_meta,
        "grid": a.grid,
        "results": results,
    }, indent=1), encoding="utf-8")
    print(f"\n   best on validation: depth {results[0]['depth']} "
          f"rounds {results[0]['roundsKept']} lr {results[0]['lr']} "
          f"{results[0]['features']} -> {results[0]['validationAccuracy']:.4f}")
    print(f"   wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
