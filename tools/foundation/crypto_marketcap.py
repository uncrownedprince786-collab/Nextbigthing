"""Market capitalisations for the coins CoinPaprika does not index.

    python tools/foundation/crypto_marketcap.py
    python tools/foundation/crypto_marketcap.py --dry-run

Of the 490 coins trading over $250k a day, 84 reach the site with no market capitalisation,
because the only source for it is CoinPaprika and Paprika does not carry them. The first fix was
to drop those rows from the curated boards, which hides a number rather than finding it.

CoinGecko carries many of them. What it does not carry is a safe way to match them: our universe
keys on a venue ticker, CoinGecko keys on its own id, and the only thing the two share is a
symbol. **Matching on a bare symbol is exactly the bug this repository has already shipped once**
-- ELON meant two different assets on two venues, 2.84e-08 on one and 0.04873 on the other, and
the bar chain happily filled one token's gaps with the other's prices until an identity test
caught it.

So every candidate match here has to agree on price. CoinGecko publishes `current_price` beside
the capitalisation; the venue publishes a last trade. Two different assets wearing one ticker do
not agree to within a few percent, and two listings of the same asset nearly always do. A symbol
that matches several CoinGecko ids is resolved by that agreement or dropped -- never by picking
the larger, which is how a microcap inherits a major's capitalisation.

What is deliberately NOT matched
---------------------------------
Tokenised real-world assets: SNDKB, SOXLB, MSTRB, CRCLB, SKHYB, KORUB are SanDisk, SOXL,
MicroStrategy, Circle, SK Hynix and a Korean equity; GOLD(XAUT) is gold and EUR is a currency.
SanDisk has a market capitalisation and it is a *stock* capitalisation -- the value of a company,
not of a token float. Writing it into this column would put a $20bn number beside a token with a
few million dollars of supply, which is worse than the blank it replaces. They are marked
`assetClass: "tokenised"` instead, so the page can say what they are rather than imply a number
it does not have.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
UNIVERSE = ROOT / "data" / "foundation" / "dataset" / "crypto_universe.json"

CG = "https://api.coingecko.com/api/v3"
PAGES = 12                      # 250 a page: the top 3,000 by capitalisation
PRICE_TOLERANCE = 0.05          # the universe builder's own identity test

#: Suffixes and names that mark a tokenised real-world asset rather than a cryptocurrency.
#: Matched case-insensitively against the ticker.
TOKENISED_HINTS = ("XAUT", "XAUP", "PAXG")


def get(url: str, tries: int = 4) -> object:
    last: Exception | None = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nextbigthing"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
            last = e
            time.sleep(4 * (i + 1))       # the free tier rate-limits hard
    raise RuntimeError(f"{url}: {last}")


def venue_prices() -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for venue, url, sym, px in (
        ("binance", "https://data-api.binance.vision/api/v3/ticker/price", "symbol", "price"),
        ("mexc", "https://api.mexc.com/api/v3/ticker/price", "symbol", "price"),
        ("gate", "https://api.gateio.ws/api/v4/spot/tickers", "currency_pair", "last"),
    ):
        try:
            for x in get(url):            # type: ignore[union-attr]
                try:
                    out[(venue, x[sym])] = float(x[px])
                except (KeyError, TypeError, ValueError):
                    continue
        except RuntimeError as e:
            print(f"   ! {venue} prices unavailable ({e})", flush=True)
    return out


def looks_tokenised(ticker: str) -> bool:
    t = ticker.upper()
    # Binance denotes its tokenised equities with a trailing B on a recognisable ticker, but a
    # trailing B alone is far too loose a rule -- it would catch any coin whose symbol ends in B.
    # Only the explicit hints and an exact fiat code are treated as tokenised here; the rest are
    # left unmatched rather than guessed at.
    return t in {"EUR", "USD", "GBP", "JPY", "TRY", "BRL"} or any(h in t for h in TOKENISED_HINTS)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill missing market caps from CoinGecko, safely.")
    ap.add_argument("--dry-run", action="store_true", help="report without writing the universe")
    ap.add_argument("--sleep", type=float, default=2.5,
                    help="seconds between pages; the free tier returns 429 below about 8")
    ap.add_argument("--start-page", type=int, default=1,
                    help="resume from a page, so a rate-limited run need not refetch what it has")
    a = ap.parse_args()

    doc = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    assets = doc["assets"]
    missing = [x for x in assets if not x.get("marketCap")]
    print(f"{len(missing)} of {len(assets)} assets have no market cap", flush=True)

    print("reading venue prices…", flush=True)
    px = venue_prices()

    print(f"reading {PAGES} pages of CoinGecko…", flush=True)
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for page in range(a.start_page, PAGES + 1):
        try:
            rows = get(f"{CG}/coins/markets?vs_currency=usd&per_page=250&page={page}")
        except RuntimeError as e:
            print(f"   ! page {page} failed ({e}); stopping early", flush=True)
            break
        if not isinstance(rows, list) or not rows:
            break
        for r in rows:
            sym = str(r.get("symbol", "")).upper()
            if sym and r.get("market_cap") and r.get("current_price"):
                by_symbol[sym].append(r)
        print(f"   page {page}: {len(rows)} coins", flush=True)
        time.sleep(a.sleep)

    filled, tokenised, ambiguous, absent, disagreed = 0, 0, 0, 0, 0
    for u in missing:
        ticker = str(u.get("ticker", "")).upper()
        if looks_tokenised(ticker):
            u["assetClass"] = "tokenised"
            tokenised += 1
            continue
        cands = by_symbol.get(ticker)
        if not cands:
            absent += 1
            continue
        on = u.get("on") or {}
        ours = next((px[(v, i)] for v, i in on.items() if i and (v, i) in px), None)
        if ours is None or ours <= 0:
            ambiguous += 1
            continue
        # Price agreement decides, never size. Two assets sharing a ticker disagree wildly; two
        # listings of one asset agree closely.
        ok = [c for c in cands
              if abs(float(c["current_price"]) - ours) / ours <= PRICE_TOLERANCE]
        if len(ok) != 1:
            if ok:
                ambiguous += 1
            else:
                disagreed += 1
            continue
        u["marketCap"] = float(ok[0]["market_cap"])
        u["marketCapSource"] = "coingecko"
        u["coingeckoId"] = ok[0]["id"]
        filled += 1

    print(f"\n   filled from CoinGecko : {filled}")
    print(f"   marked tokenised      : {tokenised}")
    print(f"   ticker not on CoinGecko: {absent}")
    print(f"   price disagreed       : {disagreed}   (different asset wearing the same ticker)")
    print(f"   ambiguous             : {ambiguous}")

    if a.dry_run:
        print("\ndry run; universe not written")
        return 0
    doc["marketCapEnrichedAt"] = datetime.now(timezone.utc).isoformat()
    UNIVERSE.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {UNIVERSE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
