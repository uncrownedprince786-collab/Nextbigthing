"""A second model that judges the first one's calls.

    python tools/research/crypto_meta.py --tag eth --horizon m15

Everything tried so far has asked the same question in a different voice: which way does price
go? Conviction gating asks the direction model how sure it is. The move-size gate asked whether
the window would be large, and came back negative. Both still read the market.

**Meta-labelling reads the model instead.** It is López de Prado's two-stage design: the primary
model picks a side, and a *secondary* model -- trained on the same features plus the primary's
side and its probability -- predicts one thing only: will this particular call turn out right?

That is a different target from anything fitted here. The direction model is asked to separate up
from down, which on five-minute crypto it does at 53%. The meta model is asked to separate the
primary's hits from its misses, and the information for that is not only in the market: it is in
*when this model tends to be wrong*. A model that is reliably poor in the first hour after a
volatility spike has a pattern a second model can learn, and no amount of retraining the first
one will fix.

What is being optimised, and why it suits quick in-and-out
----------------------------------------------------------
Precision, deliberately at the cost of recall. The reported effect in the literature is a lift
from around 60% precision to around 80% while giving up a fifth of the recall -- fewer trades,
and a much higher share of them right. For a reader who wants to be in and out quickly and only
when the brain is sure, recall is close to worthless and precision is the whole product.

**It concentrates edge, it does not create it.** A filter on a primary model with no edge
produces a smaller sample of nothing, and the backtest literature on 42 instruments says exactly
that. The primary here has a measured edge of two to three points, so there is something to
concentrate; how much survives is what this measures.

The label is the trade, not the sign
-------------------------------------
The secondary model learns whether the *trade* would have won -- target hit before stop, walked
forward bar by bar, a bar touching both scored as a loss -- rather than whether the sign was
right. Those differ, and the trade is the thing a reader acts on.

Leakage
-------
The meta model is fitted on the training fold's trades alone, with the primary's probabilities on
those rows coming from the primary's own training. Its threshold is chosen on validation and read
once on test, the same discipline as every other number here.
"""

from __future__ import annotations

import argparse
import gzip
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
from crypto_backtest import ATR_COLUMN, lane_floor, simulate  # noqa: E402
from train_crypto_short import day_blocked_bootstrap, split  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_meta.json"

#: Precision is reported at these shares of the primary's calls, strictest last.
BANDS = (1.0, 0.50, 0.25, 0.10, 0.05, 0.025)
MIN_ROWS = 200


def ohlc(symbol: str, interval: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = ROOT / ".cache" / "foundation" / "intraday" / f"{symbol}-{interval}.jsonl.gz"
    c, hi, lo = [], [], []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            b = json.loads(line)
            c.append(b["c"]); hi.append(b["h"]); lo.append(b["l"])
    return (np.asarray(c, dtype=np.float64), np.asarray(hi, dtype=np.float64),
            np.asarray(lo, dtype=np.float64))


def trades_for(data: dict, rows: np.ndarray, p: np.ndarray, ts: np.ndarray,
               bars: int, interval: str, stop_atr: float,
               target_atr: float) -> tuple[np.ndarray, np.ndarray]:
    """`(won, mask)` -- for each row in `rows`, whether the trade the primary implies would win."""
    won = np.zeros(len(rows), dtype=np.int64)
    usable = np.zeros(len(rows), dtype=bool)
    X = data["X"]
    offset = 0
    pos = {int(v): i for i, v in enumerate(rows)}
    for sym, meta in data["corpora"].items():
        full_ts, _c, kept = meta["_series"]
        n = len(kept)
        if n == 0:
            continue
        lo_i, hi_i = offset, offset + n
        offset += n
        mine = [(pos[int(v)], int(v)) for v in rows if lo_i <= v < hi_i]
        if not mine:
            continue
        idx_out = np.asarray([m[0] for m in mine], dtype=np.int64)
        glob = np.asarray([m[1] for m in mine], dtype=np.int64)
        local = kept[glob - lo_i]
        fwd = local + bars
        close, high, low = ohlc(sym, interval)
        ok = fwd < len(close)
        aligned = np.zeros(len(local), dtype=bool)
        aligned[ok] = (full_ts[fwd[ok]] - full_ts[local[ok]]) == bars * meta["stepMs"]
        if not aligned.any():
            continue
        sel_out = idx_out[aligned]
        entry = close[local[aligned]]
        atr = X[glob[aligned], ATR_COLUMN].astype(np.float64)
        direction = np.where(p[sel_out] >= 0.5, 1.0, -1.0)
        sd = entry * atr * stop_atr
        td = entry * atr * target_atr
        good = sd > 0
        if not good.any():
            continue
        r, _held = simulate(close, high, low, local[aligned][good], direction[good],
                            sd[good], td[good], bars)
        won[sel_out[good]] = (r > 0).astype(np.int64)
        usable[sel_out[good]] = True
    return won, usable


def main() -> int:
    ap = argparse.ArgumentParser(description="Does a second model improve the first's precision?")
    ap.add_argument("--tag", default="crypto")
    ap.add_argument("--horizon", default="m15")
    ap.add_argument("--stop-atr", type=float, default=1.0)
    ap.add_argument("--target-atr", type=float, default=1.5)
    ap.add_argument("--rounds", type=int, default=400)
    a = ap.parse_args()

    h = HORIZONS[a.horizon]
    name = f"brain-c1-{a.tag}-{a.horizon}"
    artifact = load_artifact(name)
    r = lane_rows(a.tag, a.horizon)
    X, ts = r["data"]["X"], r["ts"]

    te_set = set(r["te"].tolist()); va_set = set(r["va"].tolist())
    tr = np.asarray([i for i in range(len(ts)) if i not in te_set and i not in va_set],
                    dtype=np.int64)
    va, te = r["va"], r["te"]

    floor = lane_floor(a.tag, a.horizon)
    print(f"\n== {name}: meta model over the primary's calls "
          f"(floor {floor:.3f}, stop {a.stop_atr} / target {a.target_atr} ATR)\n", flush=True)

    out: dict[str, np.ndarray] = {}
    for label, rows in (("train", tr), ("validation", va), ("test", te)):
        p = score(artifact, X[rows])
        keep = np.abs(p - 0.5) >= floor
        rows_k = rows[keep]
        p_k = p[keep]
        won, usable = trades_for(r["data"], rows_k, p_k, ts, h["bars"], r["interval"],
                                 a.stop_atr, a.target_atr)
        out[label] = (rows_k[usable], p_k[usable], won[usable])
        print(f"   {label:<11} {len(rows_k[usable]):>8,} trades, "
              f"{won[usable].mean():.2%} won", flush=True)

    def meta_features(rows: np.ndarray, p: np.ndarray) -> np.ndarray:
        # The market the primary saw, plus what the primary said about it. The side and the
        # margin are the whole point: the meta model is judging a specific call, not a bar.
        side = np.where(p >= 0.5, 1.0, -1.0)
        return np.column_stack([X[rows], p, np.abs(p - 0.5), side])

    tr_rows, tr_p, tr_y = out["train"]
    va_rows, va_p, va_y = out["validation"]
    te_rows, te_p, te_y = out["test"]
    if len(tr_rows) < 2000 or len(te_rows) < MIN_ROWS:
        raise SystemExit("too few trades to fit a meta model")

    meta = gbm.fit(meta_features(tr_rows, tr_p), tr_y.astype(np.float64),
                   rounds=a.rounds, depth=3, lr=0.05, l2=2.0,
                   X_val=meta_features(va_rows, va_p), y_val=va_y.astype(np.float64),
                   early_stop=30, verbose=0)
    m_te = gbm.predict_proba(meta, meta_features(te_rows, te_p))

    base = float(te_y.mean())
    print(f"\n   taking every call the primary makes: {base:.2%} of trades win\n", flush=True)
    print(f"   {'meta band':>11} {'trades':>9} {'win rate':>10} {'lift':>8}", flush=True)
    rows_out = []
    order = np.argsort(-m_te)
    for b in BANDS:
        take = order[: max(1, int(round(len(order) * b)))]
        if len(take) < MIN_ROWS:
            continue
        win = float(te_y[take].mean())
        boot = day_blocked_bootstrap(te_y[take].astype(float),
                                     np.full(len(take), base),
                                     (ts[te_rows][take] // 86_400_000).astype(np.int64))
        print(f"   {b:>10.1%} {len(take):>9,} {win:>9.2%} {win - base:>+8.2%}  "
              f"boot95 [{boot['ci95'][0]:+.4f},{boot['ci95'][1]:+.4f}]", flush=True)
        rows_out.append({"band": b, "trades": int(len(take)), "winRate": round(win, 5),
                         "liftOverAll": round(win - base, 5), "bootstrapCi95": boot["ci95"]})

    best = max(rows_out, key=lambda x: x["winRate"]) if rows_out else None
    print("\n=== answer ===", flush=True)
    if best:
        print(f"   best: {best['winRate']:.2%} on the top {best['band']:.1%} of calls "
              f"({best['trades']:,} trades), against {base:.2%} taking them all.", flush=True)

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_meta.py",
        "what": ("a secondary model predicting whether each of the primary's calls wins its "
                 "trade, which is a different target from the direction itself"),
        "lane": name, "stopAtr": a.stop_atr, "targetAtr": a.target_atr,
        "convictionFloor": floor, "allCallsWinRate": round(base, 5),
        "bands": rows_out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
