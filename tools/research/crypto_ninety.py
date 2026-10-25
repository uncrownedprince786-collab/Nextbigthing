"""What does a 90% win rate actually cost?

    python tools/research/crypto_ninety.py --tag crypto --horizon m15

A 90% directional model does not exist in this data and nine attempts to build one have said
so. **A 90% win rate is a different thing, and it is reachable today.** Move the target close
and the stop far: price reaches a point half a tick away far more often than it reaches one two
ATR away, so the share of trades that end green rises as far as you like.

What that does to the money is the entire point of this file, and it is why "90% accurate" and
"profitable" are not the same request. A trade risking 15 ATR to make 0.5 ATR wins thirty times
for every loss it needs to break even. At 90% it loses ten times in a hundred, and those ten
losses are thirty times the size of the ninety wins.

So this sweeps the stop and target over a wide grid, on the same holdout and the same gated
calls the page serves, and prints three things for every pair:

  * **win rate** -- the number being asked for;
  * **break-even win rate** -- what that pair's reward-to-risk requires before it makes a penny;
  * **net expectancy in R** -- what following it actually did, fee included.

The pair that reaches 90% is reported whether or not it is worth taking, beside what it earned.
That is the honest form of the answer: not "90% is impossible", which is false, but "here is 90%,
here is the bill".

Nothing here is a new model. It is the same direction calls, sized differently.
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

from crypto_horizons import HORIZONS  # noqa: E402
from crypto_conviction import lane_rows, load_artifact, score  # noqa: E402
from crypto_backtest import lane_floor, simulate, ATR_COLUMN  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_ninety.json"

#: A grid that deliberately reaches the lopsided corners a hit-rate target drives you into.
#: Tight targets with wide stops are where 90% lives, and they are included precisely so the
#: price of getting there is visible rather than argued about.
STOPS = (0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 60.0)
TARGETS = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Find the win rate being asked for, and its cost.")
    ap.add_argument("--tag", default="crypto")
    ap.add_argument("--horizon", default="m15")
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--target-win", type=float, default=0.90)
    a = ap.parse_args()

    h = HORIZONS[a.horizon]
    artifact = load_artifact(f"brain-c1-{a.tag}-{a.horizon}")
    r = lane_rows(a.tag, a.horizon)
    X, ts = r["data"]["X"], r["ts"]
    te = r["te"]
    p = score(artifact, X[te])

    floor = lane_floor(a.tag, a.horizon)
    keep = np.abs(p - 0.5) >= floor
    print(f"\n== {a.tag} {a.horizon}: {int(keep.sum()):,} gated calls of {len(te):,} test rows "
          f"(floor {floor:.3f}, {a.cost_bps}bp round trip)\n", flush=True)

    # Per symbol, because a forward window must stay inside one coin's own series.
    prepared = []
    offset = 0
    import gzip
    for sym, meta in r["data"]["corpora"].items():
        full_ts, _c, kept = meta["_series"]
        n = len(kept)
        if n == 0:
            continue
        here = np.zeros(len(ts), dtype=bool)
        here[offset:offset + n] = True
        offset += n
        sel = here[te] & keep
        if not sel.any():
            continue
        local_rows = te[sel] - (offset - n)
        fwd = kept[local_rows] + h["bars"]
        ok = fwd < len(full_ts)
        aligned = np.zeros(len(local_rows), dtype=bool)
        aligned[ok] = (full_ts[fwd[ok]] - full_ts[kept[local_rows][ok]]) == h["bars"] * meta["stepMs"]
        if not aligned.any():
            continue
        path = ROOT / ".cache" / "foundation" / "intraday" / f"{sym}-{h['interval']}.jsonl.gz"
        c_l, h_l, l_l = [], [], []
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                b = json.loads(line)
                c_l.append(b["c"]); h_l.append(b["h"]); l_l.append(b["l"])
        prepared.append({
            "close": np.asarray(c_l, dtype=np.float64),
            "high": np.asarray(h_l, dtype=np.float64),
            "low": np.asarray(l_l, dtype=np.float64),
            "local": kept[local_rows][aligned],
            "direction": np.where(p[sel][aligned] >= 0.5, 1.0, -1.0),
            "atr": X[te[sel][aligned], ATR_COLUMN].astype(np.float64),
        })
    if not prepared:
        raise SystemExit("no usable rows")

    rows = []
    print(f"   {'stop':>6} {'target':>7} {'R:R':>7} {'win':>8} {'need':>8} "
          f"{'net R':>9} {'trades':>9}", flush=True)
    for stop in STOPS:
        for target in TARGETS:
            rr = target / stop
            rs, costs = [], []
            for s in prepared:
                entry = s["close"][s["local"]]
                sd = entry * s["atr"] * stop
                td = entry * s["atr"] * target
                good = sd > 0
                if not good.any():
                    continue
                res, _held = simulate(s["close"], s["high"], s["low"], s["local"][good],
                                      s["direction"][good], sd[good], td[good], h["bars"])
                rs.append(res)
                costs.append((a.cost_bps / 10_000.0) / (sd[good] / entry[good]))
            if not rs:
                continue
            res = np.concatenate(rs)
            cost = np.concatenate(costs)
            net = res - cost
            win = float((res > 0).mean())
            breakeven = 1.0 / (1.0 + rr)
            exp_r = float(net.mean())
            rows.append({"stopAtr": stop, "targetAtr": target, "rewardToRisk": round(rr, 4),
                         "winRate": round(win, 5), "breakEvenWinRate": round(breakeven, 5),
                         "netExpectancyR": round(exp_r, 5), "trades": int(len(res))})
            flag = "  <- reaches the target win rate" if win >= a.target_win else ""
            print(f"   {stop:>6.1f} {target:>7.2f} {rr:>7.3f} {win:>8.2%} {breakeven:>8.2%} "
                  f"{exp_r:>+9.4f} {len(res):>9,}{flag}", flush=True)

    hit = [x for x in rows if x["winRate"] >= a.target_win]
    best_money = max(rows, key=lambda x: x["netExpectancyR"]) if rows else None

    print("\n=== answer ===", flush=True)
    if hit:
        cheapest = max(hit, key=lambda x: x["netExpectancyR"])
        print(f"   {len(hit)} pair(s) reach a {a.target_win:.0%} win rate.", flush=True)
        print(f"   The best of them: stop {cheapest['stopAtr']} / target "
              f"{cheapest['targetAtr']} ATR -- wins {cheapest['winRate']:.2%} of the time "
              f"and makes {cheapest['netExpectancyR']:+.4f}R per trade.", flush=True)
    else:
        top = max(rows, key=lambda x: x["winRate"])
        print(f"   No pair on this grid reaches {a.target_win:.0%}. The highest is "
              f"{top['winRate']:.2%} at stop {top['stopAtr']} / target {top['targetAtr']}, "
              f"making {top['netExpectancyR']:+.4f}R.", flush=True)
    if best_money:
        print(f"   Most profitable pair: stop {best_money['stopAtr']} / target "
              f"{best_money['targetAtr']} -- wins {best_money['winRate']:.2%}, "
              f"makes {best_money['netExpectancyR']:+.4f}R.", flush=True)

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_ninety.py",
        "what": ("the win rate reachable by moving the stop and target, and what each one earns "
                 "-- a high hit rate and a profitable one are different requests"),
        "lane": f"{a.tag}:{a.horizon}", "costBps": a.cost_bps, "targetWin": a.target_win,
        "convictionFloor": floor,
        "pairs": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
