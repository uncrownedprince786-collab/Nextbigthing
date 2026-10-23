"""Every coin the site can actually price and forecast, recorded as a file the web layer reads.

    python tools/foundation/binance_universe.py

The registry holds 76 coins, which is what `jobs/prices.py` collects daily closes and market
capitalisations for. That is not the same question as "which coins can this site answer about",
and the second number is much larger: Binance lists 516 USDT spot pairs, every one of which has a
live price and the 5-minute klines the brain reads.

A coin outside the registry has no stored market capitalisation and no daily history, so it cannot
carry the rule table's reading -- but it can carry a price, a 24-hour change, a volume and a
direction, which is what the crypto pages are for. Listing only the 76 was leaving 440 coins
unreachable for no better reason than that a different job had never heard of them.

Why a generated file rather than an HTTP call at request time
--------------------------------------------------------------
The pair list changes when Binance lists or delists something, which is a few times a month; the
prices change every second. Fetching a 1.4 MB exchange-info document on every page load to learn a
fact that is a month old would be the slowest thing on the page. So the universe is a committed
artifact and only the prices are live.

What is kept, and what is dropped
----------------------------------
Only `TRADING` status and only USDT quotes. A halted pair still appears in the document with its
last price and would render as a live market that cannot be traded; a BTC-quoted pair prices a
coin in bitcoin, which is a different question from the one a dollar column is asking.

Leveraged tokens (`UP`/`DOWN`/`BULL`/`BEAR` suffixes) are dropped by name: they are derivatives
whose price is a function of a rebalancing rule rather than of the asset, and a direction model
fitted on spot behaviour has no business being pointed at one.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "foundation" / "dataset" / "binance_universe.json"
VENUE_MAP = ROOT / "data" / "foundation" / "dataset" / "crypto_venue_map.json"

HOST = "https://data-api.binance.vision"

#: Leveraged tokens and other wrappers whose price is a rule, not an asset.
LEVERAGED = re.compile(r"(UP|DOWN|BULL|BEAR)$")


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "nextbigthing-universe"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    info = fetch(f"{HOST}/api/v3/exchangeInfo?permissions=SPOT")
    rows = []
    dropped = {"notTrading": 0, "notUsdt": 0, "leveraged": 0}
    for s in info.get("symbols", []):
        if s.get("quoteAsset") != "USDT":
            dropped["notUsdt"] += 1
            continue
        if s.get("status") != "TRADING":
            dropped["notTrading"] += 1
            continue
        base = s["baseAsset"]
        if LEVERAGED.search(base) and base not in ("JUP", "PUMP"):
            dropped["leveraged"] += 1
            continue
        rows.append({"pair": s["symbol"], "base": base})

    # The registry's own slugs win wherever a coin is in both, so a coin does not appear twice
    # under two names and every existing link keeps working.
    registry = {}
    if VENUE_MAP.exists():
        doc = json.loads(VENUE_MAP.read_text(encoding="utf-8"))
        for a in doc.get("assets", []):
            if a.get("binance"):
                registry[a["binance"]] = {"slug": a["slug"], "name": a["name"]}

    out = []
    for r in sorted(rows, key=lambda x: x["pair"]):
        known = registry.get(r["pair"])
        out.append({
            "pair": r["pair"],
            "ticker": r["base"],
            # A coin outside the registry is addressed by its ticker, lowercased. It is the only
            # stable name the venue gives us, and it is what a reader would type.
            "slug": known["slug"] if known else r["base"].lower(),
            "name": known["name"] if known else r["base"],
            "inRegistry": bool(known),
        })

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/foundation/binance_universe.py",
        "venue": "Binance spot, USDT quotes, TRADING status only",
        "what": "every coin this site can price and forecast; a superset of the 76-coin registry, "
                "which is the set that also carries daily closes, market capitalisation and the "
                "rule table's reading",
        "dropped": dropped,
        "coins": len(out),
        "inRegistry": sum(1 for c in out if c["inRegistry"]),
        "assets": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: {len(out)} coins ({doc['inRegistry']} in the registry, "
          f"{len(out) - doc['inRegistry']} venue-only); dropped {dropped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
