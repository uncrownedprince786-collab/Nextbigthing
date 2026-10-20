"""Which venue pair each stored coin is, checked against the venues' own instrument lists.

    python tools/foundation/crypto_venue_map.py
    python tools/foundation/crypto_venue_map.py --offline   # re-emit from the stored table only

Writes `data/foundation/dataset/crypto_venue_map.json`: one row per crypto `Asset`, with the
Binance and Coinbase instruments that are **confirmed to exist** on those venues, or an explicit
statement that none does.

Why confirmed rather than derived
---------------------------------
The obvious rule -- take the segment before the first dash of a CoinPaprika slug, upper-case it,
add USDT -- is wrong often enough to matter and wrong *silently*: `fetch-ai` is FET, not FETCH;
`pol-polygon-ecosystem-token` is POL; `s-sonic` is S; `aave-new` is AAVE. A guessed pair returns
HTTP 400, which on a free endpoint is indistinguishable from the geo-block that took Binance off
GitHub runners on 2026-09-29. So each candidate is checked against `exchangeInfo` and the answer
is stored, which turns "this coin has no intraday series" from an outage into a fact with a date
on it.

A coin with no venue pair is **not dropped**. It is listed with `intraday: false` and the reason,
because the site lists every coin in the registry and owes each one a statement about what can and
cannot be read for it.
"""

from __future__ import annotations

import argparse
import json

import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from crypto_intraday import BINANCE_SYMBOL  # noqa: E402

# Same idiom as the jobs: CI supplies the variables, a laptop supplies a .env, and neither is
# required to know about the other.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

#: Kraken pairs, for the coins it is worth keeping as a third venue. Deliberately short and hand
#: checked: Kraken's naming is its own (`XBT` for Bitcoin, and `XXBTZUSD` in a response key), so a
#: guessed list would trade a rare fallback for a common wrong answer. It matters most for the
#: coins Binance has delisted -- Monero is served here and nowhere else in the chain.
KRAKEN_PAIR = {
    "btc-bitcoin": "XBTUSD", "eth-ethereum": "ETHUSD", "sol-solana": "SOLUSD",
    "xrp-xrp": "XRPUSD", "ada-cardano": "ADAUSD", "doge-dogecoin": "DOGEUSD",
    "ltc-litecoin": "LTCUSD", "link-chainlink": "LINKUSD", "dot-polkadot": "DOTUSD",
    "xmr-monero": "XMRUSD", "atom-cosmos": "ATOMUSD", "fil-filecoin": "FILUSD",
    "algo-algorand": "ALGOUSD", "xlm-stellar": "XLMUSD", "etc-ethereum-classic": "ETCUSD",
    "bch-bitcoin-cash": "BCHUSD", "aave-new": "AAVEUSD", "uni-uniswap": "UNIUSD",
    "near-near-protocol": "NEARUSD", "avax-avalanche": "AVAXUSD",
}

OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_venue_map.json"
UA = {"User-Agent": "nextbigthing-research/1.0 (instrument list)"}


def _get(url: str) -> object:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def binance_symbols() -> set[str]:
    info = _get("https://api.binance.com/api/v3/exchangeInfo")
    return {s["symbol"] for s in info.get("symbols", [])
            if s.get("status") == "TRADING"}


def coinbase_products() -> set[str]:
    rows = _get("https://api.exchange.coinbase.com/products")
    return {p["id"] for p in rows
            if not p.get("trading_disabled") and p.get("status") == "online"}


def crypto_assets() -> list[dict]:
    """Every crypto asset in the registry, pool flag included, from the primary database."""
    from nbt import db, rows  # noqa: PLC0415 - imported here so --offline needs no database

    conn = db()
    cur = conn.cursor()
    try:
        return rows(cur, '''
            SELECT a.id, a.symbol, a.name, a.active, a.currency,
                   (SELECT count(*) FROM "PriceSnapshot" p WHERE p."assetId" = a.id) AS snapshots,
                   (SELECT max(p.date)::text FROM "PriceSnapshot" p WHERE p."assetId" = a.id) AS newest
            FROM "Asset" a
            WHERE a."assetType" = 'crypto'
            ORDER BY a.symbol
        ''')
    finally:
        cur.close()
        conn.close()


def coinbase_fallback_possible(base: str | None, cb: set[str], checked: bool) -> bool:
    if not base:
        return False
    return any((not checked) or cand in cb for cand in (f"{base}-USD", f"{base}-USDT"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()

    assets = crypto_assets()
    bn: set[str] = set()
    cb: set[str] = set()
    checked = False
    if not a.offline:
        try:
            bn, cb = binance_symbols(), coinbase_products()
            checked = True
        except Exception as e:  # noqa: BLE001 - any network fault is the same answer here
            print(f"  venue lists unavailable ({type(e).__name__}: {e}); emitting unchecked")

    out = []
    for r in assets:
        slug = r["symbol"]
        want = BINANCE_SYMBOL.get(slug)
        base = want[:-4] if want and want.endswith("USDT") else None
        binance = want if (want and (not checked or want in bn)) else None
        why = None
        if want is None:
            why = "no Binance pair is mapped for this coin"
        elif checked and want not in bn:
            why = f"{want} is not a TRADING pair on Binance as of this check"
        if why and (KRAKEN_PAIR.get(slug) or coinbase_fallback_possible(base, cb, checked)):
            why += "; a fallback venue carries it"
        coinbase = None
        if base:
            for cand in (f"{base}-USD", f"{base}-USDT"):
                if not checked or cand in cb:
                    coinbase = cand
                    break
        out.append({
            "slug": slug,
            "name": r["name"],
            "inActivePool": bool(r["active"]),
            "dailySnapshots": int(r["snapshots"]),
            "newestClose": r["newest"],
            "binance": binance,
            "coinbase": coinbase,
            "kraken": KRAKEN_PAIR.get(slug),
            "intraday": bool(binance or coinbase or KRAKEN_PAIR.get(slug)),
            "why": why,
        })

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/foundation/crypto_venue_map.py",
        "venueListsChecked": checked,
        "binanceTradingPairs": len(bn) or None,
        "coinbaseOnlineProducts": len(cb) or None,
        "coins": len(out),
        "withIntradaySource": sum(1 for r in out if r["intraday"]),
        "inActivePool": sum(1 for r in out if r["inActivePool"]),
        "note": "every crypto Asset in the registry, pooled or not. A coin absent from a venue is "
                "listed with the reason rather than omitted: the site lists the whole registry.",
        "assets": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: {doc['coins']} coins, {doc['withIntradaySource']} with an intraday "
          f"source, {doc['inActivePool']} in the active pool")
    missing = [r["slug"] for r in out if not r["intraday"]]
    if missing:
        print(f"  no intraday source: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
