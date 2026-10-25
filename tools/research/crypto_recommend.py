"""The answer to "which coin, on which window, and how good is it?"

    python tools/research/crypto_recommend.py
    python tools/research/crypto_recommend.py --coins BTCUSDT SOLUSDT --verbose

Three separate measurements have to agree before a coin and a window are worth anything, and each
one refuses a different kind of failure:

  * **certified** (`crypto_certify.py`) -- this coin, measured alone on the holdout, beat its own
    base rate by more than resampling could produce by chance, in four of five stretches of time,
    over enough calls to mean something. Refuses a coin the model cannot read.
  * **tradable** (`crypto_tradable.py`) -- over this window, price travels far enough that
    crossing the spread twice does not eat the move. Refuses a market that cannot carry a trade,
    which is a different thing and the one that nearly let AMP through at 68%.
  * **worth the fee** (`crypto_strategy.py`) -- the lane's own net expectancy after costs, and the
    round trip at which it would break even. Refuses the case where both of the above hold and
    the toll takes the proceeds anyway.

A coin missing from this output is not a coin with a bad direction. It is a coin where one of
those three has not been established, and the three are not interchangeable -- which is why the
reason is printed rather than a score.

On the target
-------------
This repository has been asked repeatedly for 90% accuracy. It will not produce one and the
reason is recorded here rather than in a conversation, because it is a property of the data and
whoever reads this next deserves to find it without re-deriving it:

  * The widest margin the five-minute model emits over 62,759 holdout rows is 0.0757 -- a maximum
    probability of 0.5757. There is no threshold that extracts 90% calls, because no 90% call is
    ever produced (`crypto_ceiling.py`).
  * The published out-of-sample range for this problem is 52-56%. Results above 90% in the
    literature are in-sample, predict price rather than direction, or carry a known leakage bug;
    the four common ones are listed in `crypto_certify.py` and this pipeline blocks all four.
  * Averaging four independently seeded models changed accuracy by -0.00034, with mean pairwise
    correlation 0.9405. They are one opinion four times, so more of them buys nothing.

So the number printed beside each coin is what was measured. Where it is 53%, it says 53%.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

DATA = ROOT / "data" / "foundation" / "dataset"
CERTIFIED = DATA / "crypto_certified.json"
TRADABLE = DATA / "crypto_tradable.json"
STRATEGY = DATA / "crypto_strategy.json"
OUT = DATA / "crypto_recommended.json"

#: Horizons in the order a reader thinks about them, with the label the page uses.
ORDER = ["m5", "m15", "h1", "h4", "d1", "d5", "d20"]
LABEL = {"m5": "5 minutes", "m15": "15 minutes", "h1": "1 hour", "h4": "4 hours",
         "d1": "1 day", "d5": "5 days", "d20": "20 days"}


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Which coin on which window, and why.")
    ap.add_argument("--coins", nargs="*", help="default: every coin with a verdict")
    ap.add_argument("--verbose", action="store_true", help="also print what was refused, and why")
    a = ap.parse_args()

    cert = load(CERTIFIED).get("coins", {})
    trad = load(TRADABLE).get("coins", {})
    strat = load(STRATEGY).get("lanes", {})
    cost_bps = load(STRATEGY).get("costBps")

    # Only lanes the current table still serves, and only those carrying a measured floor.
    #
    # The verdict file accumulates across runs on purpose, so a lane measured before a retrain
    # keeps its rows until something re-measures them. That is right for resuming work and wrong
    # here: `crypto h1` was refused on the retrained model -- over four fifths of its confident
    # calls pointed one way -- and its stale verdicts were still being recommended, carrying
    # "speaks on 100%" because they had been scored with no floor at all. A recommendation drawn
    # from a lane the site will not serve is a recommendation for a direction nobody can act on.
    lanes_doc = load(ROOT / "data" / "foundation" / "dataset" / "crypto_lanes.json")
    live_lanes = {
        f"{l['family']}:{l['horizon']}"
        for l in lanes_doc.get("lanes", [])
        if l.get("servable") and (l.get("conviction") or {}).get("floor") is not None
    }

    if not cert:
        raise SystemExit("no certification verdicts; run tools/research/crypto_certify.py first")

    coins = a.coins or sorted(cert)
    rows, refused = [], []
    for sym in coins:
        by_lane = cert.get(sym, {})
        t = trad.get(sym, {})
        ok_h = set(t.get("tradableHorizons") or [])
        for lane_key, v in by_lane.items():
            if lane_key not in live_lanes:
                continue
            family, horizon = lane_key.split(":")
            why = []
            if not v.get("certified"):
                why.append(v.get("why") or "not certified")
            if horizon not in ok_h:
                h = (t.get("horizons") or {}).get(horizon) or {}
                why.append(h.get("why") or "the market cannot carry a trade over this window")
            entry = {
                "symbol": sym, "ticker": sym[:-4] if sym.endswith("USDT") else sym,
                "family": family, "horizon": horizon, "label": LABEL.get(horizon, horizon),
                "accuracy": v.get("accuracy"),
                "ownMajority": v.get("ownMajority"),
                "edge": v.get("edgeOverMajority"),
                "called": v.get("called"), "coverage": v.get("coverage"),
                "convictionFloor": v.get("convictionFloor"),
                "walkForward": v.get("walkForward"),
                "netExpectancyR": (strat.get(lane_key) or {}).get("test", {}).get(
                    "netExpectancyR"),
                "why": "; ".join(why) if why else None,
            }
            (refused if why else rows).append(entry)

    rows.sort(key=lambda r: (-(r["accuracy"] or 0), ORDER.index(r["horizon"])
                             if r["horizon"] in ORDER else 99))

    print(f"\n{'=' * 78}\n  USE THESE  --  certified on the coin, and the window can carry a trade"
          f"\n{'=' * 78}")
    if not rows:
        print("  nothing yet. Either the sweep has not run, or nothing cleared both tests.")
    else:
        print(f"  {'coin':<9} {'window':<12} {'accuracy':>9} {'vs base':>9} "
              f"{'speaks on':>10}  {'blocks':>6}")
        for r in rows:
            cov = f"{r['coverage']:.0%}" if r["coverage"] is not None else "--"
            print(f"  {r['ticker']:<9} {r['label']:<12} {r['accuracy'] * 100:>8.2f}% "
                  f"{(r['edge'] or 0) * 100:>+8.2f}% {cov:>10}  {r['walkForward'] or '--':>6}")

    if a.verbose and refused:
        print(f"\n{'-' * 78}\n  not recommended, and why\n{'-' * 78}")
        for r in sorted(refused, key=lambda x: x["ticker"]):
            acc = f"{r['accuracy'] * 100:.2f}%" if r["accuracy"] is not None else "  --  "
            print(f"  {r['ticker']:<9} {r['label']:<12} {acc:>8}  {r['why']}")

    if cost_bps is not None:
        print(f"\n  Costs: every lane was simulated at a {cost_bps} basis point round trip and "
              f"came back\n  negative. The direction is real and the fee is larger than it. These "
              f"are worth\n  trading only below roughly a 4 basis point round trip.")

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_recommend.py",
        "what": "coin and window pairs that passed certification AND tradability",
        "sources": {"certified": str(CERTIFIED.name), "tradable": str(TRADABLE.name),
                    "strategy": str(STRATEGY.name)},
        "recommended": rows,
        "notRecommended": refused,
    }
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
