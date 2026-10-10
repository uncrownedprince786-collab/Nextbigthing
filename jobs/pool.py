"""The active scanning pool: who is in it, and who joins it.

    python jobs/pool.py              gate and discover, and write
    python jobs/pool.py --dry-run    print what would change, write nothing

Runs nightly in the decision lane before `factors`, so a name that joins tonight is measured and
called tonight. Two halves (brain.md rule 87):

1. **The liquidity gate.** Each asset's median daily traded value over its last 20 sessions is held
   against its market's floor (`FLOORS`). Below it, the asset is set inactive: it leaves the lists,
   the pool count and the nightly calls. Nothing is deleted -- its prices keep updating and its
   history stays -- and it returns once its value clears the floor by `REENTRY`, so a name sitting
   on the line does not flip in and out every night. Crypto is judged on the larger of its global
   24-hour volume (CoinPaprika) and its exchange volume, because either source alone has listed a
   liquid coin at zero. FX pairs and futures are exempt: their "volume" is not money traded.

2. **Discovery.** The highest-volume coins on CoinPaprika and Yahoo's most-active and top-gaining US
   stocks that are not in the pool are added -- at most `DISCOVER_PER_RUN` of each a night and
   `DISCOVER_CAP` in all -- when they clear a much higher bar than the floor (`DISCOVER_*`) and a
   venue returns at least `MIN_BARS` daily closes. Those closes are written in the same step, so a
   new name is never listed without a price.

Never fails the lane for a source that does not answer: a gate or a discovery that cannot read its
source changes nothing and says so.
"""

from __future__ import annotations

import sys
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, get_json, median, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

# Median daily traded value, in the asset's own currency, below which an asset leaves the pool.
# Measured on 2026-10-10: no US stock or fund in the pool trades under $15M a day, six coins
# trade under $10M worldwide, and 50 of 226 PSX names under PKR 2M (about $7,000).
FLOORS = {"crypto": 10e6, "us": 5e6, "psx": 2e6}
# An asset out of the pool returns only above floor x REENTRY.
REENTRY = 1.5
# Sessions the median is taken over, and the fewest with a volume before the gate will judge.
WINDOW = 20
MIN_SESSIONS = 10
# An asset whose newest close is older than this is out of the pool whatever its market: a call on a
# price that stopped is a call on nothing (Binance stopped quoting Monero in February 2024 and kept
# answering with the old series). It returns when a current close arrives.
STALE_DAYS = 10
# Discovery wants a close at most this old.
DISCOVER_FRESH_DAYS = 3
# A gate that would remove more than this share of one market in one night is reading a data
# fault (a venue that published zero volume), not a market, and is refused for that market.
MAX_SHARE_OUT = 0.3

# Discovery bars, far above the floors: a new name has to be among the most traded, not merely liquid.
DISCOVER_CRYPTO_VOLUME = 100e6  # USD traded in 24 hours, worldwide
DISCOVER_CRYPTO_RANK = 300  # by market cap
DISCOVER_US_DOLLAR_VOLUME = 200e6  # USD, average daily over three months
DISCOVER_US_MIN_PRICE = 5.0  # no penny stocks
DISCOVER_US_MIN_CAP = 2e9
DISCOVER_PER_RUN = 5
# Candidates tried per market a night, added or not. With up to four crypto venues per try, one tickers
# read and two screens, MAX_REQUESTS is the most this job can send in a night; the decision lane
# admits a network job only with that ceiling stated (tests: WorkflowLanes).
MAX_TRIES = 2 * DISCOVER_PER_RUN
MAX_REQUESTS = 3 + MAX_TRIES * 4 + MAX_TRIES
DISCOVER_CAP = 40  # discovered names in the pool at once, so the pool cannot grow without bound
MIN_BARS = 60

STABLE = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD", "USDS", "USDD", "FRAX", "BUSD", "USD1", "RLUSD", "GHO", "USDX", "EURC", "XAUT", "PAXG"}
NOT_A_COIN = ("tokenized", "wrapped", "staked", "bridged", "wormhole", "liquid staking", "restaked")
US_EXCHANGES = {"NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BTS"}
DISCOVERED = "Added by discovery"
US_MOVERS = ("us-movers", "High-volume US movers", "US stocks added automatically when they are among the most traded names of the day, and kept while they stay liquid.", 98)


def market_of(asset: dict) -> str | None:
    """The gate a market answers to, or None for one it does not judge."""
    if asset["source"] == "coinpaprika":
        return "crypto"
    if asset["source"] == "psx":
        return "psx"
    if asset["source"] == "yahoo" and asset["assetType"] in ("stock", "etf"):
        return "us"
    return None  # FX pairs and futures


def traded_value(bars: list[dict]) -> float | None:
    """Median close x volume over the last WINDOW sessions with a volume, or None below MIN_SESSIONS."""
    values = [float(b["close"]) * float(b["volume"]) for b in bars[-WINDOW:] if b.get("volume") is not None and b.get("close") is not None]
    return median(values) if len(values) >= MIN_SESSIONS else None


def gate(asset: dict, value: float | None, today: date, newest: date | None = None) -> tuple[bool, str | None] | None:
    """The asset's new (active, note), or None when nothing changes. `newest` is its newest close."""
    active, note = asset["active"], asset["poolNote"] or ""
    if newest is None or (today - newest).days > STALE_DAYS:
        since = newest.isoformat() if newest else "more than 45 days"
        return (False, f"Out of the pool since {today.isoformat()}: no close since {since}.") if active else None
    was_stale = not active and "no close since" in note
    back = f"Back in the pool {today.isoformat()}: current closes again."
    market = market_of(asset)
    if market is None:  # FX pairs and futures: no volume gate, only the stale one
        return (True, back) if not active else None
    if value is None:  # nothing measured: no judgement on liquidity
        return (True, back) if was_stale else None
    floor = FLOORS[market]
    money = f"{value / 1e6:,.1f}M" + (" PKR" if market == "psx" else " USD")
    under = f"Out of the pool since {today.isoformat()}: {money} traded a day, under the {floor / 1e6:g}M floor."
    if active:
        return (False, under) if value < floor else None
    # Out for a stale price and current again: back at the floor itself. Out for thin trading: back
    # only above floor x REENTRY, so a name on the line does not flip every night.
    if value >= floor * (1 if was_stale else REENTRY):
        return True, f"Back in the pool {today.isoformat()}: {money} traded a day."
    return (False, under) if was_stale else None


def stable_or_wrapped(t: dict) -> bool:
    name = (t.get("name") or "").lower()
    sym = (t.get("symbol") or "").upper()
    price = ((t.get("quotes") or {}).get("USD") or {}).get("price") or 0
    if sym in STABLE or any(w in name for w in NOT_A_COIN):
        return True
    return abs(price - 1) < 0.03 and "usd" in name


def crypto_candidates(tickers: list[dict], known: set[str]) -> list[dict]:
    out = []
    for t in tickers:
        usd = (t.get("quotes") or {}).get("USD") or {}
        if t.get("id") in known or stable_or_wrapped(t):
            continue
        if (t.get("rank") or 10**9) > DISCOVER_CRYPTO_RANK or (usd.get("volume_24h") or 0) < DISCOVER_CRYPTO_VOLUME:
            continue
        out.append(t)
    return sorted(out, key=lambda t: -t["quotes"]["USD"]["volume_24h"])


def us_candidates(quotes: list[dict], known: set[str]) -> list[dict]:
    out, seen = [], set()
    for q in quotes:
        sym = q.get("symbol")
        if not sym or sym in known or sym in seen or q.get("quoteType") != "EQUITY" or q.get("exchange") not in US_EXCHANGES:
            continue
        price = q.get("regularMarketPrice") or 0
        avg = (q.get("averageDailyVolume3Month") or 0) * price
        if price < DISCOVER_US_MIN_PRICE or (q.get("marketCap") or 0) < DISCOVER_US_MIN_CAP or avg < DISCOVER_US_DOLLAR_VOLUME:
            continue
        seen.add(sym)
        out.append(q)
    return sorted(out, key=lambda q: -((q.get("averageDailyVolume3Month") or 0) * (q.get("regularMarketPrice") or 0)))


def closed(bars: list[tuple], today: date) -> list[tuple]:
    return [b for b in bars if b[0] < today]


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    today = datetime.now(timezone.utc).date()
    conn = db()
    cur = conn.cursor()
    try:
        assets = rows(cur, 'SELECT id, symbol, name, source, "sourceRef", "assetType", active, "poolNote" FROM "Asset"')
        history = rows(
            cur,
            """SELECT "assetId", date, close, volume FROM "PriceSnapshot"
                WHERE date >= current_date - 45 ORDER BY "assetId", date""",
        )
        series: dict[str, list[dict]] = {}
        for r in history:
            series.setdefault(r["assetId"], []).append(r)

        # CoinPaprika's tickers, already cached by the crypto lane: global volume and discovery.
        tickers = get_json("https://api.coinpaprika.com/v1/tickers?quotes=USD", cache_key="paprika-tickers", ttl=12 * 3600) or []
        global_volume = {t["id"]: ((t.get("quotes") or {}).get("USD") or {}).get("volume_24h") for t in tickers}

        # --- 1. the gate ---
        step(f"liquidity gate over {len(assets)} assets")
        changes: list[tuple[dict, bool, str | None]] = []
        for a in assets:
            bars = series.get(a["id"], [])
            value = traded_value(bars)
            if a["source"] == "coinpaprika":
                # Judged on the worldwide figure. One exchange's volume understates a coin -- Polkadot
                # read $4M on Coinbase the night CoinPaprika listed it at zero -- so with no positive
                # worldwide figure there is no judgement at all.
                paprika = global_volume.get(a["sourceRef"])
                value = max(value or 0.0, paprika) if paprika else None
            newest = bars[-1]["date"] if bars else None
            change = gate(a, value, today, newest)
            if change:
                changes.append((a, *change))
        refused: set[str] = set()
        for market in (*FLOORS, None):
            members = [a for a in assets if market_of(a) == market and a["active"]]
            out = [a for a, active, _ in changes if market_of(a) == market and not active and a["active"]]
            if members and len(out) / len(members) > MAX_SHARE_OUT:
                refused.add(market)
                print(f"  {market or 'fx and futures'}: {len(out)} of {len(members)} would leave tonight -- read as a data fault, gate refused")
        changes = [c for c in changes if market_of(c[0]) not in refused]
        for a, active, note in changes:
            print(f"  {'IN ' if active else 'OUT'} {a['symbol']}: {note}")
        if changes and not dry:
            cur.executemany('UPDATE "Asset" SET active = %s, "poolNote" = %s WHERE id = %s', [(active, note, a["id"]) for a, active, note in changes])
            conn.commit()
        print(f"  {sum(1 for c in changes if not c[1])} out, {sum(1 for c in changes if c[1])} back in")

        # --- 2. discovery ---
        discovered_now = sum(1 for a in assets if (a["poolNote"] or "").startswith(DISCOVERED) and a["active"])
        room = max(0, DISCOVER_CAP - discovered_now)
        step(f"discovery: {discovered_now} discovered names in the pool, room for {room}")
        if room == 0:
            return 0
        found = discover_crypto(assets, tickers, min(room, DISCOVER_PER_RUN), today)
        room -= len(found)
        if room > 0:
            found += discover_us(assets, min(room, DISCOVER_PER_RUN), today)
        for f in found:
            print(f"  ADD {f['symbol']} ({f['name']}): {f['note']} {len(f['bars'])} closes from {f['venue']}")
        if found and not dry:
            write_found(cur, found)
            conn.commit()
        print(f"  {len(found)} added")
        return 0
    finally:
        cur.close()
        conn.close()


def write_found(cur, found: list[dict]) -> None:
    """Every discovered asset in one statement, then every one of their closes in one more."""
    from prices import insert_snapshots

    slug, name, summary, sort = US_MOVERS
    if any(f["industry"] == slug for f in found):
        cur.execute(
            """INSERT INTO "Industry" (slug, name, summary, sort, market, currency) VALUES (%s, %s, %s, %s, 'US', 'USD')
               ON CONFLICT (slug) DO NOTHING""",
            (slug, name, summary, sort),
        )
    cols = ("industry", "symbol", "name", "assetType", "source", "ref", "note")
    made = rows(
        cur,
        """INSERT INTO "Asset" ("industryId", symbol, name, "assetType", "capBasis", source, "sourceRef", currency, active, "poolNote")
           SELECT i.id, v.symbol, v.name, v.atype::"AssetType", 'marketCap'::"CapBasis", v.source, v.ref, 'USD', true, v.note
             FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[], %s::text[], %s::text[], %s::text[])
                  AS v(slug, symbol, name, atype, source, ref, note)
             JOIN "Industry" i ON i.slug = v.slug
           ON CONFLICT ("industryId", symbol) DO NOTHING
           RETURNING id, symbol""",
        tuple([f[c] for f in found] for c in cols),
    )
    ids = {r["symbol"]: r["id"] for r in made}
    insert_snapshots(
        cur,
        [(ids[f["symbol"]], d, op, hi, lo, c, v, None, f["venue"]) for f in found if f["symbol"] in ids for d, op, hi, lo, c, v in f["bars"]],
        replace=False,
    )


def discover_crypto(assets, tickers, limit: int, today: date) -> list[dict]:
    from prices import crypto_closes

    known = {a["sourceRef"] for a in assets if a["source"] == "coinpaprika"}
    found: list[dict] = []
    for t in crypto_candidates(tickers, known)[:MAX_TRIES]:
        if len(found) >= limit:
            break
        venue, bars = crypto_closes(t["symbol"].upper(), today)
        bars = closed(bars, today)
        if bars and (today - bars[-1][0]).days > DISCOVER_FRESH_DAYS:
            print(f"  skip {t['id']}: newest close {bars[-1][0]} from {venue}, not current")
            continue
        if not venue or len(bars) < MIN_BARS:
            print(f"  skip {t['id']}: {len(bars)} closes from {venue or 'no venue'}")
            continue
        vol = t["quotes"]["USD"]["volume_24h"]
        found.append({
            "industry": "crypto", "symbol": t["id"], "name": t["name"], "assetType": "crypto",
            "source": "coinpaprika", "ref": t["id"], "venue": venue, "bars": bars,
            "note": f"{DISCOVERED} {today.isoformat()}: {vol / 1e6:,.0f}M USD traded in 24 hours.",
        })
    return found


def discover_us(assets, limit: int, today: date) -> list[dict]:
    from prices import CHART, YAHOO_CHART, parse_chart

    quotes: list[dict] = []
    for screen in ("most_actives", "day_gainers"):
        got = get_json(
            f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds={screen}&count=50",
            cache_key=f"yahoo-screen-{screen}-{today.isoformat()}",
            ttl=6 * 3600,
        )
        for result in (((got or {}).get("finance") or {}).get("result") or []):
            quotes.extend(result.get("quotes") or [])
    if not quotes:
        print("  the US screens answered nothing tonight; no US discovery")
        return []
    known = {a["sourceRef"] for a in assets if a["source"] == "yahoo"}
    found: list[dict] = []
    for q in us_candidates(quotes, known)[:MAX_TRIES]:
        if len(found) >= limit:
            break
        sym = q["symbol"]
        payload = get_json(f"{CHART}{urllib.parse.quote(sym)}?range=1y&interval=1d", cache_key=f"yahoo-chart-1y-{sym}", ttl=6 * 3600)
        bars = closed(parse_chart(payload), today)
        if bars and (today - bars[-1][0]).days > DISCOVER_FRESH_DAYS + 3:  # a weekend and a holiday
            print(f"  skip {sym}: newest close {bars[-1][0]}, not current")
            continue
        if len(bars) < MIN_BARS:
            print(f"  skip {sym}: {len(bars)} closes")
            continue
        dollars = (q.get("averageDailyVolume3Month") or 0) * (q.get("regularMarketPrice") or 0)
        found.append({
            "industry": US_MOVERS[0], "symbol": sym, "name": q.get("longName") or q.get("shortName") or sym,
            "assetType": "stock", "source": "yahoo", "ref": sym, "venue": YAHOO_CHART, "bars": bars,
            "note": f"{DISCOVERED} {today.isoformat()}: {dollars / 1e6:,.0f}M USD traded a day over three months.",
        })
    return found


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
