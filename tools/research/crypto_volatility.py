"""What about this market IS predictable at high accuracy?

    python tools/research/crypto_volatility.py --tag crypto --horizon h1

Direction has been measured to death in this repository and lands at 53%. That is not a failure
of method: four seeded models average to -0.00034 of each other, six configurations land on the
same number, and the published out-of-sample range for the problem is 52-56%. The sign of a
forward return is close to the hardest thing a market offers.

**It is also not the only thing a market offers.** The same bars carry questions whose answers are
far more predictable, because volatility clusters and direction does not. A violent hour is
usually followed by another violent hour; an up hour is not usually followed by another up hour.
That asymmetry is one of the oldest findings in finance and it is sitting unused in a corpus that
has only ever been asked which way.

So this measures three questions on the identical rows, the identical folds and the identical
gates, so the numbers are comparable rather than merely adjacent:

  * **direction** -- will the forward return be positive? The thing already measured, included as
    the control.
  * **volatility** -- will the forward window's realised range exceed this coin's own recent
    median? Calm or violent, not up or down.
  * **containment** -- will price stay inside a band of k ATR over the window? The question a
    stop-loss actually asks.

What this is for
----------------
Not a replacement for direction and not a trading strategy. A volatility call does not say which
way to bet. What it does say is how much to bet, how wide a stop has to be, and whether to be in
the market at all this hour -- and those decide returns at least as much as the direction does.
A 53% direction sized correctly beats a 53% direction sized blindly, and the sizing input can be
far better than 53%.

Measured on the same holdout, with the same embargo, read once.
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
from crypto_conviction import training_config  # noqa: E402
from crypto_matrix import prepare_cached  # noqa: E402
from intraday_features import FEATURES  # noqa: E402
from train_crypto_short import day_blocked_bootstrap, split  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_volatility.json"
ATR_COLUMN = FEATURES.index("atr14")

#: Band half-width for the containment question, in ATR at the decision bar.
CONTAINMENT_ATR = 2.0


def targets(data: dict, bars_ahead: int,
            fit_mask: np.ndarray) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """`{name: (y, usable)}` for each question, over the same rows.

    `fit_mask` marks the training rows, and it is not optional. The volatility label is "wider
    than this coin's usual range", and *usual* has to be measured somewhere. The first version of
    this file took the median over every row the coin had, test fold included -- so the threshold
    that defines the label knew the future, and the 72.9% it produced was the full-sample
    normalisation leak that the critique literature names first and that this pipeline blocks
    everywhere else. Measured on the training rows only, the threshold is a number that was
    knowable at the time.
    """
    ts = data["ts"]
    n_all = len(ts)
    direction = np.zeros(n_all, dtype=np.int64)
    vol = np.zeros(n_all, dtype=np.int64)
    contained = np.zeros(n_all, dtype=np.int64)
    usable = np.zeros(n_all, dtype=bool)
    atr = data["X"][:, ATR_COLUMN].astype(np.float64)

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

        here = np.zeros(n, dtype=bool)
        here[aligned] = True
        idx = np.flatnonzero(aligned)
        if len(idx):
            k = keep[idx]
            entry = full_close[k]
            end = full_close[k + bars_ahead]
            direction[offset + idx] = (end > entry).astype(np.int64)

            # Realised range over the window, as a fraction of entry, read from closes for the
            # same reason the level tables are: the model is fitted on closes.
            hi = np.full(len(idx), -np.inf)
            lo = np.full(len(idx), np.inf)
            for off in range(1, bars_ahead + 1):
                c = full_close[k + off]
                hi = np.maximum(hi, c)
                lo = np.minimum(lo, c)
            rng = (hi - lo) / entry

            a = atr[offset + idx]
            good = a > 1e-9
            # "More volatile than usual" is defined against this coin's own median realised range
            # over the fit rows, not a global constant -- a violent hour for Bitcoin is a quiet
            # one for a small cap, and a shared threshold would just be a size proxy.
            # The threshold comes from the training rows of this coin alone. Falling back to
            # all rows when a coin has too few training ones would quietly reintroduce the leak
            # for exactly the coins least able to afford it, so those rows are dropped instead.
            fit_here = fit_mask[offset + idx] & good
            if int(fit_here.sum()) < 200:
                here[idx] = False
                offset += n
                continue
            med = float(np.median(rng[fit_here]))
            vol[offset + idx] = (rng > med).astype(np.int64)
            contained[offset + idx] = (rng <= CONTAINMENT_ATR * a).astype(np.int64)
            here &= True
        usable[offset:offset + n] = here
        offset += n

    return {"direction": (direction, usable),
            "volatility": (vol, usable),
            "containment": (contained, usable)}


def measure(name: str, X: np.ndarray, y: np.ndarray, ts: np.ndarray,
            tr: np.ndarray, va: np.ndarray, te: np.ndarray, rounds: int, depth: int) -> dict:
    model = gbm.fit(X[tr], y[tr].astype(np.float64), rounds=rounds, depth=depth, lr=0.05,
                    l2=2.0, X_val=X[va], y_val=y[va].astype(np.float64),
                    early_stop=30, verbose=0)
    p = gbm.predict_proba(model, X[te])
    yy = y[te]
    pred = (p >= 0.5).astype(int)
    acc = float((pred == yy).mean())
    base = float(yy.mean())
    majority = max(base, 1 - base)
    maj_class = 1 if base >= 0.5 else 0
    boot = day_blocked_bootstrap((pred == yy).astype(float),
                                 (yy == maj_class).astype(float),
                                 (ts[te] // 86_400_000).astype(np.int64))
    # Accuracy among the most confident tenth, which is what a gated lane would serve.
    margin = np.abs(p - 0.5)
    cut = float(np.quantile(margin, 0.90))
    sel = margin >= cut
    top = float((pred[sel] == yy[sel]).mean()) if sel.sum() > 200 else None

    print(f"   {name:<13} accuracy {acc * 100:>6.2f}%   base {majority * 100:>6.2f}%   "
          f"edge {(acc - majority) * 100:>+6.2f}%   "
          f"top decile {(top * 100 if top else float('nan')):>6.2f}%   "
          f"boot95 [{boot['ci95'][0]:+.4f},{boot['ci95'][1]:+.4f}]", flush=True)
    return {
        "question": name, "accuracy": round(acc, 5), "baseRate": round(base, 5),
        "majority": round(majority, 5), "edgeOverMajority": round(acc - majority, 5),
        "topDecileAccuracy": round(top, 5) if top is not None else None,
        "bootstrapCi95": boot["ci95"], "testRows": int(len(yy)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare how predictable different questions are.")
    ap.add_argument("--tag", default="crypto")
    ap.add_argument("--horizon", default="h1")
    ap.add_argument("--rounds", type=int, default=300)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--coins", nargs="*", help="default: the lane's own training pool")
    a = ap.parse_args()

    h = HORIZONS[a.horizon]
    cfg = training_config(a.tag, a.horizon)
    symbols = a.coins or cfg["symbols"]
    data = prepare_cached(symbols, h["interval"], cfg["stride"], context=cfg["context"])
    X = data["X"]
    ts = data["ts"]
    step_ms = next(iter(data["corpora"].values()))["stepMs"]
    tr_m, va_m, te_m, _meta = split(ts, h["bars"], step_ms)

    print(f"\n== {a.tag} {a.horizon}: {len(symbols)} coins, same rows, same folds, same gates\n",
          flush=True)

    out = []
    for name, (y, usable) in targets(data, h["bars"], tr_m).items():
        tr = np.flatnonzero(tr_m & usable)
        va = np.flatnonzero(va_m & usable)
        te = np.flatnonzero(te_m & usable)
        te = te[np.argsort(ts[te], kind="stable")]
        if len(tr) < 5000 or len(te) < 1000:
            print(f"   {name}: too few rows", flush=True)
            continue
        out.append(measure(name, X, y, ts, tr, va, te, a.rounds, a.depth))

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_volatility.py",
        "what": ("how predictable three different questions are on identical rows and folds: "
                 "direction, volatility, and containment within a band"),
        "containmentAtr": CONTAINMENT_ATR,
        "tag": a.tag, "horizon": a.horizon, "coins": len(symbols),
        "results": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
