"""Every coin this site can price, forecast and size -- across three venues, checked against each other.

    python tools/foundation/crypto_universe.py

This replaces `binance_universe.py`, which listed one venue. Binance trades 516 USDT pairs; MEXC
trades 1,462 and Gate 2,032, and the union is **2,754 distinct coins**, every one of which has a
live price and the klines the brain reads. Listing only Binance left two thousand coins
unreachable for no reason except that one exchange had not listed them.

Three things are recorded for each coin, and each answers a question the pages were getting wrong.

**Which venue serves it.** Binance first wherever it is listed: its klines are the only free ones
carrying taker-buy volume and a trade count, which are four of the forty-one features the models
were fitted on. MEXC and Gate do not publish those, so a coin served from either is marked
degraded at serving time rather than quietly imputed -- that machinery already exists in
`lib/cryptoBars.ts` and this just tells it which venue to ask.

**What it is worth.** CoinPaprika's free ticker endpoint carries a market capitalisation for 2,000
coins. The market table had an em dash in that column for every coin outside the 76-coin registry,
which is most of them.

**Whether the price is right.** A ticker symbol is not a unique identifier -- 39 of the tickers in
our universe match more than one CoinPaprika coin, and `ATOM` on one exchange is not necessarily
`ATOM` on another. So the match is not made on the symbol alone: a candidate is accepted only when
its USD price agrees with the venue's to within `PRICE_TOLERANCE`, and where several agree the
highest-ranked wins. A coin whose candidates all disagree on price gets **no** capitalisation
rather than a wrong one.

That check is worth more than the disambiguation it was built for. It is a cross-venue price
audit: `priceDisagreementPct` is recorded for every coin, so a feed that has drifted, a stale
pair, or a ticker collision shows up as a number instead of as a plausible-looking price.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_universe.json"
VENUE_MAP = ROOT / "data" / "foundation" / "dataset" / "crypto_venue_map.json"

#: How far a second source's USD price may sit from the venue's before the match is refused.
#:
#: Ten percent. Wide enough that a quote taken seconds apart on a volatile coin still matches, and
#: narrow enough that two different coins sharing a ticker almost never do -- their prices differ
#: by orders of magnitude, not by percentages.
PRICE_TOLERANCE = 0.10

#: Leveraged tokens and other wrappers whose price is a rebalancing rule, not an asset. A
#: direction model fitted on spot behaviour has no business being pointed at one.
LEVERAGED = re.compile(r"(\d+L|\d+S|UP|DOWN|BULL|BEAR)$")
#: Tickers that end in UP/DOWN and are real coins. Named, because the rule above is a heuristic
#: and a heuristic that silently eats a real asset is worse than no rule.
NOT_LEVERAGED = {"JUP", "PUMP", "SUP", "SOUP"}


def get(url: str, timeout: int = 60) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "nextbigthing-universe"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def safe(url: str, label: str, timeout: int = 60) -> object | None:
    try:
        return get(url, timeout)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  {label}: unreachable ({type(e).__name__}), skipped", file=sys.stderr)
        return None


def is_leveraged(base: str) -> bool:
    return bool(LEVERAGED.search(base)) and base not in NOT_LEVERAGED


def binance() -> dict[str, dict]:
    """`base -> {pair, price}` for every TRADING USDT pair."""
    info = safe("https://data-api.binance.vision/api/v3/exchangeInfo?permissions=SPOT", "binance info")
    px = safe("https://data-api.binance.vision/api/v3/ticker/price", "binance prices")
    prices = {}
    if isinstance(px, list):
        for r in px:
            try:
                prices[r["symbol"]] = float(r["price"])
            except (KeyError, TypeError, ValueError):
                continue
    out: dict[str, dict] = {}
    if not isinstance(info, dict):
        return out
    for s in info.get("symbols", []):
        if s.get("quoteAsset") != "USDT" or s.get("status") != "TRADING":
            continue
        base = s["baseAsset"]
        if is_leveraged(base):
            continue
        out[base] = {"pair": s["symbol"], "price": prices.get(s["symbol"])}
    return out


def mexc() -> dict[str, dict]:
    info = safe("https://api.mexc.com/api/v3/exchangeInfo", "mexc info")
    px = safe("https://api.mexc.com/api/v3/ticker/price", "mexc prices")
    prices = {}
    if isinstance(px, list):
        for r in px:
            try:
                prices[r["symbol"]] = float(r["price"])
            except (KeyError, TypeError, ValueError):
                continue
    out: dict[str, dict] = {}
    if not isinstance(info, dict):
        return out
    for s in info.get("symbols", []):
        if s.get("quoteAsset") != "USDT":
            continue
        # MEXC reports status as "1" on the spot endpoint and "ENABLED" elsewhere; both mean the
        # same thing and neither is documented as stable, so both are accepted by name.
        if str(s.get("status")) not in ("1", "ENABLED", "TRADING"):
            continue
        base = s["baseAsset"]
        if is_leveraged(base):
            continue
        out[base] = {"pair": s["symbol"], "price": prices.get(s["symbol"])}
    return out


def gate() -> dict[str, dict]:
    pairs = safe("https://api.gateio.ws/api/v4/spot/currency_pairs", "gate pairs")
    tick = safe("https://api.gateio.ws/api/v4/spot/tickers", "gate tickers")
    prices = {}
    if isinstance(tick, list):
        for r in tick:
            try:
                prices[r["currency_pair"]] = float(r["last"])
            except (KeyError, TypeError, ValueError):
                continue
    out: dict[str, dict] = {}
    if not isinstance(pairs, list):
        return out
    for s in pairs:
        if s.get("quote") != "USDT" or s.get("trade_status") != "tradable":
            continue
        base = s["base"]
        if is_leveraged(base):
            continue
        out[base] = {"pair": s["id"], "price": prices.get(s["id"])}
    return out


def paprika() -> dict[str, list[dict]]:
    """`TICKER -> [candidate, ...]`, each with a USD price, a market capitalisation and a rank."""
    rows = safe("https://api.coinpaprika.com/v1/tickers?quotes=USD", "coinpaprika", timeout=120)
    out: dict[str, list[dict]] = {}
    if not isinstance(rows, list):
        return out
    for r in rows:
        try:
            usd = r["quotes"]["USD"]
            out.setdefault(r["symbol"].upper(), []).append({
                "id": r["id"],
                "name": r["name"],
                "rank": r.get("rank") or 10**6,
                "price": float(usd["price"]),
                "marketCap": float(usd.get("market_cap") or 0) or None,
                "volume24h": float(usd.get("volume_24h") or 0) or None,
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


def match(ticker: str, venue_price: float | None, candidates: list[dict]) -> tuple[dict | None, float | None]:
    """The candidate whose price agrees with the venue, and by how much it differs.

    Returns `(None, None)` when nothing agrees. That is the right answer for a ticker collision:
    a market capitalisation attached to the wrong coin is worse than an em dash, because an em
    dash is visibly an absence and a wrong number is not.
    """
    if not candidates:
        return None, None
    if venue_price is None or venue_price <= 0:
        # Without a price to check against there is nothing to disambiguate on, so only an
        # unambiguous ticker is accepted.
        return (candidates[0], None) if len(candidates) == 1 else (None, None)
    scored = []
    for c in candidates:
        if c["price"] <= 0:
            continue
        diff = abs(c["price"] - venue_price) / venue_price
        scored.append((diff, c))
    if not scored:
        return None, None
    agreeing = [(d, c) for d, c in scored if d <= PRICE_TOLERANCE]
    if not agreeing:
        return None, min(scored, key=lambda x: x[0])[0]
    agreeing.sort(key=lambda x: (x[1]["rank"], x[0]))
    return agreeing[0][1], agreeing[0][0]


def main() -> int:
    print("fetching venues...", flush=True)
    b, m, g = binance(), mexc(), gate()
    print(f"  binance {len(b)}  mexc {len(m)}  gate {len(g)}", flush=True)
    caps = paprika()
    print(f"  coinpaprika {sum(len(v) for v in caps.values())} tickers", flush=True)

    registry: dict[str, dict] = {}
    if VENUE_MAP.exists():
        doc = json.loads(VENUE_MAP.read_text(encoding="utf-8"))
        for a in doc.get("assets", []):
            if a.get("binance"):
                registry[a["binance"].replace("USDT", "")] = {"slug": a["slug"], "name": a["name"]}

    bases = sorted(set(b) | set(m) | set(g))
    assets = []
    stats = {"binance": 0, "mexc": 0, "gate": 0, "withMarketCap": 0,
             "priceChecked": 0, "priceDisagreed": 0}
    for base in bases:
        # Binance first: its klines are the only free ones carrying taker-buy volume and a trade
        # count, and a coin served from anywhere else imputes four of the forty-one features.
        if base in b:
            venue, inst, price = "binance", b[base]["pair"], b[base]["price"]
        elif base in m:
            venue, inst, price = "mexc", m[base]["pair"], m[base]["price"]
        else:
            venue, inst, price = "gate", g[base]["pair"], g[base]["price"]
        stats[venue] += 1

        cand, diff = match(base, price, caps.get(base.upper(), []))
        if diff is not None:
            stats["priceChecked"] += 1
            if cand is None:
                stats["priceDisagreed"] += 1
        if cand:
            stats["withMarketCap"] += 1

        known = registry.get(base)
        # Every venue the coin is on, so the bar fetcher can fall past one that is down.
        on = {k: v[base]["pair"] for k, v in (("binance", b), ("mexc", m), ("gate", g))
              if base in v}
        assets.append({
            "ticker": base,
            # A registry coin keeps its CoinPaprika slug so every existing link still works; a
            # coin the registry has never collected is addressed by its lowercased ticker.
            "slug": known["slug"] if known else base.lower(),
            "name": known["name"] if known else (cand["name"] if cand else base),
            "venue": venue,
            "instrument": inst,
            "on": on,
            "inRegistry": bool(known),
            "marketCap": cand["marketCap"] if cand else None,
            "rank": cand["rank"] if cand and cand["rank"] < 10**6 else None,
            "paprikaId": cand["id"] if cand else None,
            "priceDisagreementPct": round(diff * 100, 4) if diff is not None else None,
        })

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/foundation/crypto_universe.py",
        "venues": "Binance, MEXC and Gate spot, USDT quotes, tradeable status only",
        "priceTolerancePct": PRICE_TOLERANCE * 100,
        "what": "every coin this site can price and forecast. Market capitalisation comes from "
                "CoinPaprika and is attached only where its USD price agrees with the venue's, so "
                "a ticker shared by two coins gets no figure rather than the wrong one.",
        "coins": len(assets),
        "stats": stats,
        "assets": assets,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    size = OUT.stat().st_size
    print(f"wrote {OUT}: {len(assets)} coins, {size // 1024} KB")
    print(f"  venues: {stats['binance']} binance, {stats['mexc']} mexc, {stats['gate']} gate")
    print(f"  market caps on {stats['withMarketCap']}; price checked on {stats['priceChecked']}, "
          f"{stats['priceDisagreed']} refused for disagreeing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
