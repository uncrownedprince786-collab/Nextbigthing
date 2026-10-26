"""Does every number the site shows agree with the measurement behind it?

    python tools/research/crypto_audit.py
    python tools/research/crypto_audit.py --fail      # non-zero exit on any finding

The unit tests check the rules. This checks the *data those rules run on*, end to end, for every
coin and window the site will actually serve. Both have caught real faults this week and they
caught different kinds:

  * a served stop and target that no window ever reaches -- 15 ATR against a 0.97 ATR typical
    move, neither level touched on 100% of trades, and a page printing a 4.26% stop on a
    fifteen-minute scalp;
  * a slug-to-symbol lookup that matched nothing, so every coin read as unmeasured and the gate
    refused the entire site while the models were fine;
  * experiment artifacts leaking into the lane table as servable lanes;
  * a conviction floor on a lane the table refuses.

None of those broke a test, because each was a disagreement *between* files rather than a rule
violation inside one. So this walks the chain a reader's page walks -- lane, floor, levels,
certification, tradability -- and reports every place two of them say different things.

Findings are printed, not raised. A run that reports nothing is the claim; a run that reports
something names the file to fix.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data" / "foundation" / "dataset"

#: Coins the recommend board carries, by slug, mirroring components/CoinTable.WATCHLIST.
WATCHLIST = {
    "btc-bitcoin": "btc", "eth-ethereum": "eth", "sol-solana": "sol", "xrp-xrp": "xrp",
    "ada-cardano": "ada", "link-chainlink": "link", "avax-avalanche": "avax",
    "dot-polkadot": "dot", "sui-sui": "sui",
}
SCALP = ("m5", "m15")

#: A served target beyond this many times the horizon's typical favourable move is not a target.
MAX_TARGET_OVER_TYPICAL = 4.0


def load(name: str) -> dict:
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-check every served number.")
    ap.add_argument("--fail", action="store_true")
    a = ap.parse_args()

    lanes_doc = load("crypto_lanes.json")
    levels = load("crypto_levels.json").get("families", {})
    cert = load("crypto_certified.json").get("coins", {})
    trad = load("crypto_tradable.json").get("coins", {})
    universe = {x["slug"]: x for x in load("crypto_universe.json").get("assets", [])}
    lanes = {f"{l['family']}:{l['horizon']}": l for l in lanes_doc.get("lanes", [])}

    findings: list[str] = []
    def bad(msg: str) -> None:
        findings.append(msg)
        print(f"   FINDING  {msg}", flush=True)

    print("\n=== 1. experiment artifacts must not be servable ===", flush=True)
    for key, l in lanes.items():
        if l["family"] in {"fund", "nofund", "yours"} and l.get("servable"):
            bad(f"{key} is an experiment lane marked servable")
    print("   checked", flush=True)

    print("\n=== 2. a floor exists only on a lane the table serves ===", flush=True)
    for key, l in lanes.items():
        if l.get("conviction") and not l.get("servable"):
            bad(f"{key} carries a conviction floor but is not servable")
    print("   checked", flush=True)

    print("\n=== 3. served levels are reachable inside the window ===", flush=True)
    for fam, hz in levels.items():
        for h, v in hz.items():
            sp = v.get("servedPair")
            if not sp:
                continue
            typical = ((levels.get(fam, {}).get(h) or {}).get("favourableExcursionAtr") or {}
                       ).get("median")
            if typical is None:
                typical = ((levels.get("crypto", {}).get(h) or {}).get(
                    "favourableExcursionAtr") or {}).get("median")
            if not typical:
                continue
            if sp["targetAtr"] > typical * MAX_TARGET_OVER_TYPICAL:
                bad(f"{fam}:{h} serves a {sp['targetAtr']} ATR target against a typical move of "
                    f"{typical} ATR -- {sp['targetAtr'] / typical:.0f}x, it will not be reached")
            pair = (v.get("pairs") or {}).get(f"{sp['stopAtr']}/{sp['targetAtr']}")
            if pair and pair.get("neither", 0) > 0.95:
                bad(f"{fam}:{h} serves a pair neither level is reached on "
                    f"{pair['neither']:.1%} of windows")
    print("   checked", flush=True)

    print("\n=== 4. every watchlist coin resolves to a lane, and it is its own or the pool ===",
          flush=True)
    for slug, fam in WATCHLIST.items():
        if slug not in universe:
            bad(f"{slug} is on the watchlist but not in the universe")
            continue
        for h in SCALP:
            own = lanes.get(f"{fam}:{h}")
            pooled = lanes.get(f"crypto:{h}")
            served = own if (own and own.get("servable")) else (
                pooled if (pooled and pooled.get("servable")) else own or pooled)
            if served is None:
                bad(f"{slug} at {h} resolves to no lane at all")
                continue
            if served["family"] not in (fam, "crypto"):
                bad(f"{slug} at {h} is served by {served['family']}, "
                    f"which is neither its own nor the pool")
            pool = served.get("trainedOn") or []
            if len(pool) == 1:
                ticker = universe[slug]["ticker"].upper()
                if pool[0].upper() not in (f"{ticker}USDT", ticker):
                    bad(f"{slug} at {h} is served {served['modelVersion']}, fitted only on "
                        f"{pool[0]}")
    print("   checked", flush=True)

    print("\n=== 5. a certified verdict is reachable from the coin's slug ===", flush=True)
    for slug in WATCHLIST:
        u = universe.get(slug)
        if not u:
            continue
        inst = (u.get("on") or {}).get("binance") or (u.get("on") or {}).get("mexc")
        sym = (inst or f"{u['ticker']}USDT").upper()
        if sym not in cert:
            bad(f"{slug} resolves to {sym}, which has no certification verdict")
    print("   checked", flush=True)

    print("\n=== 6. a lane the board serves has levels to go with it ===", flush=True)
    for slug, fam in WATCHLIST.items():
        for h in SCALP:
            own = lanes.get(f"{fam}:{h}")
            if not (own and own.get("servable") and own.get("conviction")):
                continue
            if not (levels.get(fam, {}).get(h) or {}).get("servedPair"):
                bad(f"{fam}:{h} is served with a floor but has no entry, stop or target")
    print("   checked", flush=True)

    print("\n=== 7. accuracy claims are inside their own measured interval ===", flush=True)
    for key, l in lanes.items():
        c = l.get("conviction")
        if not (l.get("servable") and c):
            continue
        called = c.get("called") or {}
        acc, maj = called.get("accuracy"), called.get("majorityHere")
        if acc is None or maj is None:
            bad(f"{key} is served with a floor but no measured accuracy")
            continue
        if acc <= maj:
            bad(f"{key} serves {acc:.4f} against its own majority of {maj:.4f}")
        ci = called.get("bootstrapCi95")
        if ci and ci[0] <= 0:
            bad(f"{key} is served although its bootstrap interval includes zero: {ci}")
    print("   checked", flush=True)

    print(f"\n=== {len(findings)} finding(s) ===", flush=True)
    for f in findings:
        print(f"   {f}", flush=True)
    if not findings:
        print("   every served number agrees with the measurement behind it.", flush=True)
    return 1 if (a.fail and findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
