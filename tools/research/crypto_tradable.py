"""Is a certified coin's edge a market, or is it the tick grid?

    python tools/research/crypto_tradable.py
    python tools/research/crypto_tradable.py --coins AMPUSDT BTCUSDT

A coin can pass every statistical gate and still be worthless to trade, and the way it happens is
always the same shape: the model learns something real about a price series that is not really
moving. The pegged stablecoins were the first instance -- RLUSD, FDUSD and USDC came out as the
strongest signals on the board at p=0.668, predicting oscillation in the fourth decimal of a
dollar. The `pegged` flag caught those by name.

This catches the unnamed version. A coin priced at $0.0025 with a $0.00001 tick has 250 price
levels, so its five-minute return is not a continuous quantity -- it is a small integer number of
ticks. Bid-ask bounce between a handful of levels is genuinely predictable and genuinely
untradeable: every round trip pays the spread, and the spread is one tick, which is 0.4% of
price. A 68% hit rate on moves of half a tick loses money on every single trade.

So this measures, per coin, the things that distinguish a market from a grid:

  * **the tick, inferred from the data** -- the smallest non-zero gap between distinct observed
    closes. Taken from the series rather than from an exchange filter, because it is the
    granularity the *model* saw.
  * **tick as a fraction of price**, which is the floor on any round trip. If one tick is 0.4% of
    price, a ten-basis-point fee is the least of the problem.
  * **the share of bars that did not move at all.** A series that is flat half the time is a
    series where "direction" mostly means "which way did it eventually tick".
  * **the typical move in ticks.** When the median absolute five-minute return is one or two
    ticks, the model is predicting the grid, not the market.
  * **median dollar volume per bar**, because a real edge on a coin that trades $400 a bar is an
    edge you cannot take without being the entire market.

Nothing here is a statistical test and nothing here overrules one. A coin that fails the gates is
refused on the evidence; this refuses a different thing -- a coin whose evidence is sound and
whose market cannot carry a trade.
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

CORPUS = ROOT / ".cache" / "foundation" / "intraday"
CERTIFIED = ROOT / "data" / "foundation" / "dataset" / "crypto_certified.json"
OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_tradable.json"

#: One tick wider than this much of price and a round trip costs more than two ticks of edge,
#: which is more than the model's whole measured margin on any lane here.
MAX_TICK_PCT = 0.05

#: A typical move smaller than this many ticks means the model is reading the grid.
MIN_MOVE_TICKS = 3.0

#: Bars that did not move at all. Above this share the series is mostly stationary.
MAX_FLAT_SHARE = 0.25

#: Dollars of volume in a median bar. Below this a position cannot be taken or left without
#: moving the price against yourself by more than the edge.
MIN_BAR_DOLLARS = 5_000.0


def load(symbol: str) -> tuple[np.ndarray, np.ndarray] | None:
    p = CORPUS / f"{symbol}-5m.jsonl.gz"
    if not p.exists():
        return None
    c, v = [], []
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            b = json.loads(line)
            c.append(b["c"])
            v.append(b.get("v", 0.0))
    return np.asarray(c, dtype=np.float64), np.asarray(v, dtype=np.float64)


def inferred_tick(close: np.ndarray) -> float:
    """The smallest non-zero gap between distinct observed closes.

    From the data, not from an exchange filter: the question is what granularity the model saw,
    and a filter the venue publishes today may not be the one that produced bars from last year.
    """
    u = np.unique(close)
    if len(u) < 2:
        return 0.0
    d = np.diff(u)
    d = d[d > 0]
    return float(d.min()) if len(d) else 0.0


def assess(symbol: str) -> dict:
    data = load(symbol)
    if data is None:
        return {"symbol": symbol, "tradable": False, "why": "no bars"}
    close, vol = data
    if len(close) < 1000:
        return {"symbol": symbol, "tradable": False, "why": "under 1000 bars"}

    tick = inferred_tick(close)
    price = float(np.median(close))
    tick_pct = (tick / price * 100) if price > 0 else float("inf")

    ret = np.diff(close) / close[:-1]
    flat_share = float((ret == 0).mean())
    move = np.abs(np.diff(close))
    median_move = float(np.median(move))
    move_ticks = (median_move / tick) if tick > 0 else float("inf")
    bar_dollars = float(np.median(vol * close))

    problems = []
    if tick_pct > MAX_TICK_PCT:
        problems.append(f"one tick is {tick_pct:.3f}% of price")
    if move_ticks < MIN_MOVE_TICKS:
        problems.append(f"the median bar moves {move_ticks:.1f} ticks")
    if flat_share > MAX_FLAT_SHARE:
        problems.append(f"{flat_share:.0%} of bars do not move at all")
    if bar_dollars < MIN_BAR_DOLLARS:
        problems.append(f"a median bar trades ${bar_dollars:,.0f}")

    return {
        "symbol": symbol,
        "medianPrice": price,
        "tick": tick,
        "tickPctOfPrice": round(tick_pct, 5),
        "flatBarShare": round(flat_share, 5),
        "medianMoveTicks": round(move_ticks, 3),
        "medianBarDollars": round(bar_dollars, 2),
        "tradable": not problems,
        "why": "; ".join(problems) if problems else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Can a certified coin's edge actually be traded?")
    ap.add_argument("--coins", nargs="*", help="default: every coin certified on any lane")
    a = ap.parse_args()

    if a.coins:
        coins = a.coins
    else:
        doc = json.loads(CERTIFIED.read_text(encoding="utf-8"))
        coins = sorted({c for v in doc.get("certifiedByLane", {}).values() for c in v})
    if not coins:
        raise SystemExit("no certified coins to assess; run crypto_certify.py first")

    print(f"assessing {len(coins)} coins\n", flush=True)
    rows = [assess(s) for s in coins]
    rows.sort(key=lambda r: -(r.get("tickPctOfPrice") or 0))

    bad = [r for r in rows if not r["tradable"]]
    for r in rows:
        mark = "ok " if r["tradable"] else "NO "
        if "medianPrice" not in r:
            print(f"   {mark}{r['symbol']:<14} {r['why']}", flush=True)
            continue
        print(f"   {mark}{r['symbol']:<14} price {r['medianPrice']:>12,.6f}  "
              f"tick {r['tickPctOfPrice']:>7.3f}% of price  "
              f"move {r['medianMoveTicks']:>7.1f} ticks  "
              f"flat {r['flatBarShare']:>5.1%}  "
              f"${r['medianBarDollars']:>12,.0f}/bar"
              + (f"   <- {r['why']}" if r["why"] else ""), flush=True)

    print(f"\n=== {len(rows) - len(bad)} of {len(rows)} tradable ===", flush=True)
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_tradable.py",
        "what": ("whether a certified coin's market can carry a trade at all, which is a "
                 "different question from whether its edge is real"),
        "thresholds": {
            "maxTickPctOfPrice": MAX_TICK_PCT,
            "minMedianMoveTicks": MIN_MOVE_TICKS,
            "maxFlatBarShare": MAX_FLAT_SHARE,
            "minMedianBarDollars": MIN_BAR_DOLLARS,
        },
        "counts": {"assessed": len(rows), "tradable": len(rows) - len(bad)},
        "notTradable": [r["symbol"] for r in bad],
        "coins": {r["symbol"]: r for r in rows},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
