"""Does the brain read direction better when a big move is coming?

    python tools/research/crypto_gate.py --tag crypto --horizon m5

Conviction gating works by asking the direction model how sure it is. It is worth ten points, and
it is the only lever that has moved this problem. But it asks one question: *am I confident?* It
never asks the other one: *is there anything to be confident about?*

Those come apart. A five-minute window that travels a tenth of its usual range is mostly
microstructure -- the spread, a resting order, a tick of rounding -- and its sign is close to
unpredictable however sure the model sounds. A window that travels twice its usual range is being
driven by something, and whatever is driving it leaves traces in the bars before it. Volatility
clusters; direction does not. That asymmetry is one of the oldest findings in finance and this
repository has never used it.

So this fits a **second** model on the identical features, predicting not which way the next
window goes but whether it will be a **large** move -- forward absolute return above this coin's
own trailing median, measured on training rows only. Then it measures the direction model's
accuracy on the rows the gate is confident about, against its accuracy everywhere, with
everything else held fixed.

Three outcomes, and all three are worth knowing:

  * the gate lifts direction accuracy, and a two-model serve is worth building;
  * it does nothing, and magnitude and sign are independent here, which is itself a finding about
    this market;
  * it *lowers* it, meaning the big moves are the unpredictable ones -- news, liquidations -- and
    the edge lives in the quiet bars the fee cannot pay for.

The threshold comes from the training fold only
------------------------------------------------
"Larger than usual" needs a definition of usual, and taking that median over every row would let
the label know the future. That is the full-sample normalisation leak the critique literature
names first, and this file had it in an earlier form of the volatility probe -- caught, and the
reason this note exists. The median here is computed on training rows per coin and nowhere else.
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
from crypto_conviction import lane_rows, load_artifact, score  # noqa: E402
from train_crypto_short import day_blocked_bootstrap  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_gate.json"

#: Coverages of the gate to report: the share of rows it is most confident are large moves.
BANDS = (1.0, 0.50, 0.25, 0.10, 0.05)

MIN_ROWS = 500


def big_move_labels(data: dict, bars_ahead: int,
                    fit_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`(y, usable)` for "the forward move is larger than this coin's usual", training-fold median."""
    n_all = len(data["ts"])
    y = np.zeros(n_all, dtype=np.int64)
    usable = np.zeros(n_all, dtype=bool)
    offset = 0
    for _sym, meta in data["corpora"].items():
        full_ts, full_close, keep = meta["_series"]
        n = len(keep)
        if n == 0:
            continue
        step = meta["stepMs"]
        fwd = keep + bars_ahead
        ok = fwd < len(full_close)
        aligned = np.zeros(n, dtype=bool)
        aligned[ok] = (full_ts[fwd[ok]] - full_ts[keep[ok]]) == bars_ahead * step
        idx = np.flatnonzero(aligned)
        if len(idx) == 0:
            offset += n
            continue
        k = keep[idx]
        move = np.abs(full_close[k + bars_ahead] / full_close[k] - 1.0)
        fit_here = fit_mask[offset + idx]
        if int(fit_here.sum()) < 200:
            offset += n
            continue
        med = float(np.median(move[fit_here]))
        y[offset + idx] = (move > med).astype(np.int64)
        usable[offset + idx] = True
        offset += n
    return y, usable


def main() -> int:
    ap = argparse.ArgumentParser(description="Does gating on move size improve direction?")
    ap.add_argument("--tag", default="crypto")
    ap.add_argument("--horizon", default="m5")
    ap.add_argument("--rounds", type=int, default=400)
    ap.add_argument("--depth", type=int, default=3)
    a = ap.parse_args()

    h = HORIZONS[a.horizon]
    name = f"brain-c1-{a.tag}-{a.horizon}"
    artifact = load_artifact(name)
    r = lane_rows(a.tag, a.horizon)
    X, ts, y_dir = r["data"]["X"], r["ts"], r["y"]

    # Rebuild the fold masks the lane was measured on.
    tr_mask = np.zeros(len(ts), dtype=bool)
    tr_mask[r["va"]] = False
    all_idx = np.arange(len(ts))
    te_set = set(r["te"].tolist())
    va_set = set(r["va"].tolist())
    tr_idx = np.array([i for i in all_idx if i not in te_set and i not in va_set], dtype=np.int64)
    tr_mask[tr_idx] = True

    y_big, big_ok = big_move_labels(r["data"], h["bars"], tr_mask)

    tr = tr_idx[big_ok[tr_idx]]
    va = r["va"][big_ok[r["va"]]]
    te = r["te"][big_ok[r["te"]]]
    print(f"\n== {name}: gate fitted on {len(tr):,} rows, measured on {len(te):,}\n", flush=True)

    gate = gbm.fit(X[tr], y_big[tr].astype(np.float64), rounds=a.rounds, depth=a.depth,
                   lr=0.05, l2=2.0, X_val=X[va], y_val=y_big[va].astype(np.float64),
                   early_stop=30, verbose=0)
    p_gate = gbm.predict_proba(gate, X[te])
    gate_acc = float(((p_gate >= 0.5).astype(int) == y_big[te]).mean())
    gate_base = float(max(y_big[te].mean(), 1 - y_big[te].mean()))
    print(f"   gate itself: {gate_acc * 100:.2f}% at predicting a large move "
          f"(base {gate_base * 100:.2f}%)", flush=True)

    p_dir = score(artifact, X[te])
    yd = y_dir[te]
    pred = (p_dir >= 0.5).astype(int)

    print(f"\n   gate band      rows   direction acc   base    edge", flush=True)
    rows = []
    order = np.argsort(-p_gate)
    for band in BANDS:
        take = order[: max(1, int(round(len(order) * band)))]
        if len(take) < MIN_ROWS:
            continue
        acc = float((pred[take] == yd[take]).mean())
        up = float(yd[take].mean())
        base = max(up, 1 - up)
        boot = day_blocked_bootstrap((pred[take] == yd[take]).astype(float),
                                     (yd[take] == (1 if up >= 0.5 else 0)).astype(float),
                                     (ts[te][take] // 86_400_000).astype(np.int64))
        print(f"   top {band:>6.0%}  {len(take):>9,}   {acc * 100:>8.2f}%   "
              f"{base * 100:>6.2f}%  {(acc - base) * 100:>+6.2f}%  "
              f"boot95 [{boot['ci95'][0]:+.4f},{boot['ci95'][1]:+.4f}]", flush=True)
        rows.append({"band": band, "rows": int(len(take)), "directionAccuracy": round(acc, 5),
                     "baseRate": round(base, 5), "edge": round(acc - base, 5),
                     "bootstrapCi95": boot["ci95"]})

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_gate.py",
        "question": ("whether the direction model is more accurate on the rows a second model "
                     "expects to be large moves"),
        "lane": name,
        "gateAccuracy": round(gate_acc, 5),
        "gateBaseRate": round(gate_base, 5),
        "bands": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
