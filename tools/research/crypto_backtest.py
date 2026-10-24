"""What the brain's calls would actually have done, with costs, on the holdout.

    python tools/research/crypto_backtest.py --tag crypto --horizon m5
    python tools/research/crypto_backtest.py --tag crypto --horizon m15 --cost-bps 10

Accuracy is not the question. "53.7% of directions were correct" and "this would have made money"
are different claims, and only the second one is about trading -- a 64% win rate on a target half
the distance of the stop loses, and a 52% win rate at 2:1 wins. The ten formulas every quant sheet
opens with exist because of that gap, so this computes them on the rows the model actually called.

What is simulated, bar by bar
------------------------------
For each test row the model gave a direction on:

  * **enter** at that bar's close -- the same close the features were read from and the same one
    `lib/cryptoLevels.ts` anchors the levels to;
  * **stop and target** at the measured ATR multiples for that lane, the exact numbers the page
    prints;
  * then walk forward one bar at a time to the horizon. A bar whose low crosses the stop is a
    loss; one whose high reaches the target is a win. **A bar that does both is scored as a
    loss**, because a 5-minute bar does not say which came first and assuming the good one is how
    a backtest flatters itself;
  * anything still open at the horizon is closed at that bar's close, for whatever it is worth.

Costs are charged and are not an afterthought
----------------------------------------------
`--cost-bps` is the round trip: taker fee in, taker fee out, plus spread. The default of 10 basis
points is deliberately close to what a retail taker actually pays on a major venue, and it is
charged on **every** trade, winner or loser. At five minutes the measured target is about half a
percent away, so a tenth of a percent is a fifth of the reward -- which is the whole reason this
file exists rather than a win-rate table.

Every figure is reported with and without costs, because the difference between the two is the
most important number here and burying it inside one net figure would hide it.

What this is and is not
-----------------------
It is the model's own calls, on rows it never saw, scored against what the market did next. It is
**not** a live track record: no forecast in it was made before its data existed, there is no
slippage model, no funding, no partial fills, and no liquidity check -- a target reached on a coin
with eleven dollars of depth is not a trade anyone could have taken. The prospective record on
`/predictions` is the only forward evidence and this does not replace it.
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
from crypto_conviction import load_artifact, score, training_config  # noqa: E402
from crypto_horizons import HORIZONS  # noqa: E402
from crypto_matrix import prepare_cached  # noqa: E402
from intraday_features import FEATURES  # noqa: E402
from train_crypto_short import labels_for, split  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_backtest.json"

#: The stop/target pairs offered, in ATR units. Mirrors `crypto_levels.CANDIDATES`.
CANDIDATES = [
    (0.5, 0.75), (0.5, 1.0), (0.75, 1.0), (0.75, 1.5),
    (1.0, 1.0), (1.0, 1.5), (1.0, 2.0), (1.5, 2.0),
    # Wider rungs, added after the first sweep came back monotone in the stop width: every
    # candidate was net-negative and the widest was least so, because the fee is a fixed
    # fraction of notional and shrinks in R as the stop grows. A ladder whose best entry is its
    # last entry has not been measured, it has been truncated.
    (2.0, 3.0), (2.0, 4.0), (3.0, 4.0), (3.0, 6.0), (4.0, 8.0), (6.0, 12.0),
    (8.0, 16.0), (10.0, 20.0), (15.0, 30.0),
]
LEVELS = ROOT / "data" / "foundation" / "dataset" / "crypto_levels.json"
LANES = ROOT / "data" / "foundation" / "dataset" / "crypto_lanes.json"

ATR_COLUMN = FEATURES.index("atr14")

#: A retail taker round trip on a major venue, in basis points of notional. Charged on every
#: trade. Overridable, never zero by default: a backtest whose default is free is a brochure.
DEFAULT_COST_BPS = 10.0


def served_levels(tag: str, horizon: str, cost_bps: float) -> tuple[float, float] | None:
    """The stop and target multiples the site actually serves for this lane.

    The same rule as `lib/cryptoLevels.bestPair`, written twice on purpose and kept identical:
    expected move per unit of risk, after costs. A backtest that scored a different pair from the
    one the page prints would be a backtest of a product nobody is offered.
    """
    doc = json.loads(LEVELS.read_text(encoding="utf-8"))
    h = (doc.get("families", {}).get(tag) or {}).get(horizon)
    if not h or not h.get("pairs"):
        return None
    atr_pct = h.get("medianAtrPctOfPrice") or 0.0
    cost_atr = (cost_bps / 100.0) / atr_pct if atr_pct > 0 else 0.0
    best = None
    for p in h["pairs"].values():
        gross = (p["reachedTargetWithoutTouchingStop"] * p["targetAtr"]
                 - p["stoppedWithoutReachingTarget"] * p["stopAtr"])
        ev = (gross - cost_atr) / p["stopAtr"]
        if best is None or ev > best[0]:
            best = (ev, p["stopAtr"], p["targetAtr"])
    return (best[1], best[2]) if best else None


def lane_floor(tag: str, horizon: str) -> float:
    doc = json.loads(LANES.read_text(encoding="utf-8"))
    for l in doc["lanes"]:
        if l["family"] == tag and l["horizon"] == horizon:
            c = l.get("conviction")
            return float(c["floor"]) if c else 0.0
    return 0.0


def simulate(close: np.ndarray, high: np.ndarray, low: np.ndarray, idx: np.ndarray,
             direction: np.ndarray, stop_d: np.ndarray, target_d: np.ndarray,
             bars_ahead: int) -> tuple[np.ndarray, np.ndarray]:
    """`(r_multiple, bars_held)` for each call, before costs.

    `r_multiple` is the return in units of the risk taken: +targetAtr/stopAtr for a target, -1 for
    a stop, and the realised move over the risk for a trade still open at the horizon.
    """
    n = len(idx)
    entry = close[idx]
    sign = direction.astype(np.float64)
    stop_px = entry - sign * stop_d
    target_px = entry + sign * target_d
    out = np.full(n, np.nan)
    held = np.full(n, bars_ahead, dtype=np.int64)
    done = np.zeros(n, dtype=bool)

    for off in range(1, bars_ahead + 1):
        j = idx + off
        live = ~done
        if not live.any():
            break
        hi = high[j]
        lo = low[j]
        # Long: stop below, target above. Short: the mirror.
        hit_stop = np.where(sign > 0, lo <= stop_px, hi >= stop_px) & live
        hit_target = np.where(sign > 0, hi >= target_px, lo <= target_px) & live
        # Both in one bar is scored as the loss. A bar does not record which came first, and
        # assuming the good one is how a backtest flatters itself.
        loss = hit_stop
        win = hit_target & ~hit_stop
        out[loss] = -1.0
        out[win] = (target_d[win] / stop_d[win])
        held[loss | win] = off
        done |= loss | win

    # Whatever is still open at the horizon closes at that bar's close, for what it is worth.
    open_at_end = ~done
    if open_at_end.any():
        j = idx[open_at_end] + bars_ahead
        move = (close[j] - entry[open_at_end]) * sign[open_at_end]
        out[open_at_end] = move / stop_d[open_at_end]
    return out, held


def metrics(r: np.ndarray, rr: float, label: str) -> dict:
    wins = r > 0
    n = len(r)
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    dd = peak - equity
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    gross_win = float(r[r > 0].sum())
    gross_loss = float(-r[r < 0].sum())
    return {
        "label": label,
        "trades": int(n),
        "winRate": round(float(wins.mean()), 5) if n else None,
        "breakEvenWinRate": round(1.0 / (1.0 + rr), 5),
        "expectancyR": round(float(r.mean()), 5) if n else None,
        "totalR": round(float(equity[-1]), 2) if n else None,
        "profitFactor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
        "maxDrawdownR": round(float(dd.max()), 2) if n else None,
        # Per-trade Sharpe, not annualised: annualising a 5-minute strategy's per-trade ratio
        # requires a trade frequency assumption this makes none of.
        "sharpePerTrade": round(float(r.mean() / sd), 4) if sd > 0 else None,
        "bestR": round(float(r.max()), 3) if n else None,
        "worstR": round(float(r.min()), 3) if n else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Score the brain's own calls as trades, with costs.")
    ap.add_argument("--tag", required=True, choices=["btc", "crypto"])
    ap.add_argument("--horizon", required=True, choices=list(HORIZONS))
    ap.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    ap.add_argument("--band", default="strong", choices=["strong", "all"],
                    help="strong: only calls clearing the lane's floor, which is what the page "
                         "marks STRONG; all: every call")
    ap.add_argument("--fold", default="test", choices=["validation", "test"],
                    help="validation to CHOOSE a pair, test to REPORT one. Choosing on test is "
                         "fitting the holdout and the whole point of having one is that it is not")
    ap.add_argument("--pair", default=None,
                    help="score exactly this stop/target, e.g. 8/16 -- the way a pair chosen on "
                         "validation is then reported on the holdout without the holdout having "
                         "had any say in choosing it")
    ap.add_argument("--sweep", action="store_true",
                    help="score every candidate pair on this fold instead of the served one")
    a = ap.parse_args()

    h = HORIZONS[a.horizon]
    cfg = training_config(a.tag, a.horizon)
    floor = lane_floor(a.tag, a.horizon) if a.band == "strong" else 0.0
    if a.pair:
        s, _, tg = a.pair.partition("/")
        pairs = [(float(s), float(tg))]
    elif a.sweep:
        pairs = CANDIDATES
    else:
        lv = served_levels(a.tag, a.horizon, a.cost_bps)
        if lv is None:
            raise SystemExit(f"no measured levels for {a.tag} {a.horizon}")
        pairs = [lv]
    print(f"== {a.tag} {a.horizon} on the {a.fold} fold: {len(pairs)} pair(s), "
          f"floor {floor:.3f}, cost {a.cost_bps}bp round trip", flush=True)

    data = prepare_cached(cfg["symbols"], h["interval"], cfg["stride"], context=cfg["context"])
    y, usable, _ = labels_for(data, h["bars"])
    ts = data["ts"]
    step_ms = next(iter(data["corpora"].values()))["stepMs"]
    _tr, va_m, te_m, split_meta = split(ts, h["bars"], step_ms)
    te = np.flatnonzero((va_m if a.fold == "validation" else te_m) & usable)

    artifact = load_artifact(f"brain-c1-{a.tag}-{a.horizon}")
    p = score(artifact, data["X"][te].astype(np.float64))
    keep = np.abs(p - 0.5) >= floor
    print(f"   {len(te):,} {a.fold} rows, {int(keep.sum()):,} called "
          f"({keep.mean():.1%} of the fold)", flush=True)
    if keep.sum() < 200:
        raise SystemExit("under 200 calls; nothing worth reporting")

    # Prepared once per symbol and reused for every candidate pair: the expensive parts are
    # reading each coin's bars off disk and aligning the forward windows, and neither depends on
    # where the stop is.
    prepared: list[dict] = []
    offset = 0
    for _s, meta in data["corpora"].items():
        full_ts, full_close, kept = meta["_series"]
        n = len(kept)
        if n == 0:
            continue
        here = np.zeros(len(ts), dtype=bool)
        here[offset:offset + n] = True
        offset += n
        sel = here[te] & keep
        if not sel.any():
            continue
        rows_local = te[sel] - (offset - n)
        # Only rows whose whole forward window is consecutive in this coin's series.
        fwd = kept[rows_local] + h["bars"]
        ok = fwd < len(full_close)
        aligned = np.zeros(len(rows_local), dtype=bool)
        aligned[ok] = (full_ts[fwd[ok]] - full_ts[kept[rows_local][ok]]) == h["bars"] * meta["stepMs"]
        if not aligned.any():
            continue
        local = kept[rows_local][aligned]
        bars = meta.get("_bars")
        # Highs and lows come from the stored series; the matrix keeps closes only, so they are
        # read back from the corpus once per symbol.
        import gzip
        path = ROOT / ".cache" / "foundation" / "intraday" / f"{_s}-{h['interval']}.jsonl.gz"
        if bars is None:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                raw = [json.loads(line) for line in fh]
            meta["_bars"] = raw
            bars = raw
        close = np.asarray([b["c"] for b in bars], dtype=np.float64)
        high = np.asarray([b["h"] for b in bars], dtype=np.float64)
        low = np.asarray([b["l"] for b in bars], dtype=np.float64)

        pr = p[sel][aligned]
        atr_frac = data["X"][te[sel][aligned], ATR_COLUMN].astype(np.float64)
        prepared.append({
            "close": close, "high": high, "low": low, "local": local,
            "direction": np.where(pr >= 0.5, 1.0, -1.0), "atr": atr_frac,
        })

    if not prepared:
        raise SystemExit("no usable rows")

    scored = []
    for stop_atr, target_atr in pairs:
        rr = target_atr / stop_atr
        rs, costs_r = [], []
        for s in prepared:
            entry = s["close"][s["local"]]
            stop_d = entry * s["atr"] * stop_atr
            target_d = entry * s["atr"] * target_atr
            good = stop_d > 0
            if not good.any():
                continue
            r_, _held = simulate(s["close"], s["high"], s["low"], s["local"][good],
                                 s["direction"][good], stop_d[good], target_d[good], h["bars"])
            rs.append(r_)
            # The round trip in units of the risk taken: a cost of `c` of notional against a stop
            # that is `stop_d / entry` of notional.
            costs_r.append((a.cost_bps / 10_000.0) / (stop_d[good] / entry[good]))
        r = np.concatenate(rs)
        c = np.concatenate(costs_r)
        g = metrics(r, rr, "before costs")
        n = metrics(r - c, rr, f"after {a.cost_bps}bp round trip")
        scored.append({"stopAtr": stop_atr, "targetAtr": target_atr,
                       "rewardToRisk": round(rr, 4),
                       "meanCostInR": round(float(c.mean()), 4),
                       "grossOfCosts": g, "netOfCosts": n})
        print(f"   {stop_atr}/{target_atr} ({rr:.2f}R)  win {n['winRate']:.4f}  "
              f"net {n['expectancyR']:+.4f}R  gross {g['expectancyR']:+.4f}R  "
              f"cost {c.mean():.3f}R  PF {n['profitFactor']}", flush=True)

    scored.sort(key=lambda x: -(x["netOfCosts"]["expectancyR"] or -9))
    best = scored[0]
    stop_atr, target_atr = best["stopAtr"], best["targetAtr"]
    rr = best["rewardToRisk"]
    gross = best["grossOfCosts"]
    net = best["netOfCosts"]

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_backtest.py",
        "tag": a.tag, "horizon": a.horizon, "band": a.band,
        "fold": a.fold,
        "stopAtr": stop_atr, "targetAtr": target_atr, "rewardToRisk": round(rr, 4),
        "convictionFloor": floor,
        "costBps": a.cost_bps,
        "meanCostInR": best["meanCostInR"],
        "allPairs": scored if a.sweep else None,
        "split": split_meta,
        "symbols": len(cfg["symbols"]),
        "grossOfCosts": gross,
        "netOfCosts": net,
        "whatThisIsNot": [
            "Not a live track record: no call in it was made before its data existed.",
            "No slippage, no funding, no partial fills and no liquidity check. A target reached "
            "on a coin with no depth is not a trade anyone could have taken.",
            "A bar that touches both the stop and the target is scored as a loss, because a bar "
            "does not record which came first.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")

    for m in (gross, net):
        print(f"\n   {m['label']}")
        print(f"     trades {m['trades']:,}   win {m['winRate']:.4f} "
              f"(break-even {m['breakEvenWinRate']:.4f})")
        print(f"     expectancy {m['expectancyR']:+.4f}R   total {m['totalR']:+.1f}R   "
              f"profit factor {m['profitFactor']}")
        print(f"     max drawdown {m['maxDrawdownR']:.1f}R   per-trade Sharpe {m['sharpePerTrade']}")
    print(f"\n   best pair on this fold: {stop_atr}/{target_atr} "
          f"({best['meanCostInR']:.3f}R of cost per trade)")
    print(f"   wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
