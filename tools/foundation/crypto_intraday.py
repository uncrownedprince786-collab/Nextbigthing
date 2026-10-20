"""Intraday crypto bars from the public venues, validated before they are kept.

    python tools/foundation/crypto_intraday.py BTCUSDT --days 1100
    python tools/foundation/crypto_intraday.py BTCUSDT --days 30 --verify

Why a separate collector from `jobs/intraday.py`
------------------------------------------------
That job fetches a handful of bars for an *active set* of equities from Yahoo, writes them to
`IntradayBar`, and is shaped around an exchange session. What a short-horizon crypto model needs
is the opposite: one coin, every bar, years deep, on disk, with the provider's own completeness
record kept beside it. Writing three hundred thousand bars into a 500 MB free-tier database to
train a model once would spend the whole budget on a corpus that is read by one process.

So the corpus lives in `.cache/foundation/intraday/` as gzipped JSONL and the database keeps only
the recent window the serving path reads. Same bars, two retention policies, because they answer
two different questions.

What "validated" means here, exactly
------------------------------------
Nothing below is a filter that quietly drops rows. Every check that fires is **counted and
reported**, and a bar that fails a structural check is recorded as a rejection with its reason
rather than silently skipped -- a corpus that drops 4% of its bars without saying so is a corpus
whose gaps are indistinguishable from quiet markets.

  * **Shape.** open/high/low/close positive and finite; `high >= max(open, close)`;
    `low <= min(open, close)`; `high >= low`; volume present and non-negative.
  * **Identity.** One bar per open timestamp. A duplicate timestamp from a page overlap is
    deduplicated on the first occurrence and counted; a *conflicting* duplicate -- same timestamp,
    different close -- is counted separately, because that is a provider fault and not a paging
    artefact.
  * **Continuity.** The expected bar count between the first and last timestamp at the stated
    interval, against what arrived. Missing opens are listed as runs, so a venue outage reads as
    one gap rather than two hundred absences.
  * **Maturity.** The bar in progress is never kept. Binance returns the open candle of the
    current interval, and a 5-minute bar that is 40 seconds old is a partial observation being
    reported as a whole one -- the same fault `fetch_crypto` documents for the UTC day. A bar is
    kept only when its close time is in the past.

Provenance
----------
Every bar carries the venue it came from and the window it arrived in. `--verify` fetches an
overlapping window from a second venue (Coinbase Exchange) and reports the median absolute close
difference, so "the series is self-consistent" is distinguished from "the series is right".

Free and permitted: Binance's public `/api/v3/klines` and Coinbase Exchange's public `/candles`
both serve market data without a key and without authentication.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / ".cache" / "foundation" / "intraday"

#: The venue chain, in the order history depth makes useful. Binance pages back years at five
#: minutes; Coinbase serves 300 candles a request and is used for the cross-check rather than the
#: corpus.
BINANCE = "https://api.binance.com/api/v3/klines"
BINANCE_MIRROR = "https://data-api.binance.vision/api/v3/klines"
COINBASE = "https://api.exchange.coinbase.com/products/{product}/candles"

UA = {"User-Agent": "nextbigthing-research/1.0 (market data collection)"}

INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}

#: Binance symbol for a CoinPaprika slug, for the coins whose intraday series is wanted. Kept as a
#: table rather than derived from the slug because the ticker segment is not always the pair base
#: (`fetch-ai` is FET, `pol-polygon-ecosystem-token` is POL) and a guessed symbol returns a 400
#: that looks exactly like an outage.
BINANCE_SYMBOL = {
    "btc-bitcoin": "BTCUSDT", "eth-ethereum": "ETHUSDT", "sol-solana": "SOLUSDT",
    "xrp-xrp": "XRPUSDT", "bnb-binance-coin": "BNBUSDT", "ada-cardano": "ADAUSDT",
    "doge-dogecoin": "DOGEUSDT", "ltc-litecoin": "LTCUSDT", "link-chainlink": "LINKUSDT",
    "avax-avalanche": "AVAXUSDT", "bch-bitcoin-cash": "BCHUSDT", "dot-polkadot": "DOTUSDT",
    "trx-tron": "TRXUSDT", "xlm-stellar": "XLMUSDT", "etc-ethereum-classic": "ETCUSDT",
    "atom-cosmos": "ATOMUSDT", "uni-uniswap": "UNIUSDT", "fil-filecoin": "FILUSDT",
    "near-near-protocol": "NEARUSDT", "aave-new": "AAVEUSDT", "algo-algorand": "ALGOUSDT",
    "shib-shiba-inu": "SHIBUSDT", "pepe-pepe": "PEPEUSDT", "sui-sui": "SUIUSDT",
    "apt-aptos": "APTUSDT", "arb-arbitrum": "ARBUSDT", "op-optimism": "OPUSDT",
    "inj-injective-protocol": "INJUSDT", "tia-celestia": "TIAUSDT", "sei-sei": "SEIUSDT",
    "hbar-hedera-hashgraph": "HBARUSDT", "vet-vechain": "VETUSDT", "icp-internet-computer": "ICPUSDT",
    "stx-stacks": "STXUSDT", "crv-curve-dao-token": "CRVUSDT", "cake-pancakeswap": "CAKEUSDT",
    "dash-dash": "DASHUSDT", "zec-zcash": "ZECUSDT", "xmr-monero": "XMRUSDT",
    "bat-basic-attention-token": "BATUSDT", "xtz-tezos": "XTZUSDT", "qnt-quant": "QNTUSDT",
    "rndr-render-token": "RENDERUSDT", "fetch-ai": "FETUSDT", "tao-bittensor": "TAOUSDT",
    "wld-worldcoin": "WLDUSDT", "ena-ethena": "ENAUSDT", "ondo-ondo": "ONDOUSDT",
    "pol-polygon-ecosystem-token": "POLUSDT", "pyth-pyth-network": "PYTHUSDT",
    "ray-raydium": "RAYUSDT", "strk-starknet": "STRKUSDT", "zro-layerzero": "ZROUSDT",
    "pengu-pudgy-penguins": "PENGUUSDT", "trump-official-trump": "TRUMPUSDT",
    "virtual-virtual-protocol": "VIRTUALUSDT", "morpho-morpho": "MORPHOUSDT",
    "pendle-pendle": "PENDLEUSDT", "s-sonic": "SUSDT", "aero-aerodrome-finance": "AEROUSDT",
    "cro-cryptocom-chain": "CROUSDT", "flr-flare-network": "FLRUSDT", "pump-pumpfun": "PUMPUSDT",
    "hype-hyperliquid": "HYPEUSDT", "grass-grass": "GRASSUSDT", "sky-sky": "SKYUSDT",
    "cfx-conflux-network": "CFXUSDT", "spx-spx6900": "SPXUSDT", "aster-aster": "ASTERUSDT",
    "wbt-whitebit": None, "usdg-global-dollar": None, "chip-usdai": None, "drv7-derive": None,
    "met-meteora": None, "vvv-venice-token": None,
    "wlfi-official-world-liberty-financial": "WLFIUSDT",
}


def _get(url: str, tries: int = 4) -> object:
    """One GET with a bounded backoff. A 429 is waited out, not retried immediately."""
    delay = 1.0
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            # 418/429 are Binance's rate limiters and carry a Retry-After worth honouring.
            wait = float(e.headers.get("Retry-After") or 0) or delay
            if e.code in (418, 429):
                time.sleep(min(wait, 60))
            elif e.code >= 500:
                time.sleep(delay)
            else:
                raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"{url.split('?')[0]} did not answer after {tries} tries ({last})")


def binance_klines(symbol: str, interval: str, start_ms: int, end_ms: int,
                   mirror: bool = False, progress: bool = False) -> list[list]:
    """Every kline between two instants, paged forward 1000 at a time.

    Paged **forward** from `start_ms` rather than backward from now, because the forward form is
    the one where a page boundary is a known timestamp: each page starts at the open time of the
    bar after the last one kept, so an overlap is impossible by construction and a gap is visible
    as a jump rather than hidden by a window that silently slid.
    """
    base = BINANCE_MIRROR if mirror else BINANCE
    step = INTERVAL_MS[interval]
    out: list[list] = []
    cursor = start_ms
    pages = 0
    while cursor < end_ms:
        url = (f"{base}?symbol={symbol}&interval={interval}"
               f"&startTime={cursor}&endTime={end_ms}&limit=1000")
        page = _get(url)
        pages += 1
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        nxt = int(page[-1][0]) + step
        if nxt <= cursor:
            break
        cursor = nxt
        if progress and pages % 25 == 0:
            print(f"    page {pages}: {len(out):,} klines, at "
                  f"{datetime.fromtimestamp(cursor / 1000, timezone.utc).date()}", flush=True)
        # Binance's documented weight budget is 6000/minute and a 1000-row klines call costs 2,
        # so this is far inside it; the sleep is politeness to a free endpoint, not a limit.
        time.sleep(0.12)
    return out


def _finite(*vals: float) -> bool:
    return all(isinstance(v, float) and math.isfinite(v) for v in vals)


def validate(klines: list[list], interval: str, now_ms: int) -> tuple[list[dict], dict]:
    """Turn raw klines into bars, with every rejection counted and named.

    Returns `(bars, report)`. `bars` is sorted by open time, one per timestamp, every one of which
    passed every structural check and has closed. `report` is the completeness record.
    """
    step = INTERVAL_MS[interval]
    rejects: Counter = Counter()
    seen: dict[int, dict] = {}
    conflicts = 0
    immature = 0

    for k in klines:
        try:
            ts = int(k[0])
            o, h, lo, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
            v = float(k[5])
            close_ms = int(k[6])
            trades = int(k[8])
            taker_base = float(k[9])
        except (TypeError, ValueError, IndexError):
            rejects["unparseable"] += 1
            continue
        # The bar in progress is a partial observation. Kept out by its own close time rather than
        # by "drop the last row", which is wrong whenever a page ends early.
        if close_ms >= now_ms:
            immature += 1
            continue
        if not _finite(o, h, lo, c, v) or min(o, h, lo, c) <= 0:
            rejects["non-positive or non-finite price"] += 1
            continue
        if v < 0:
            rejects["negative volume"] += 1
            continue
        if h < max(o, c) or lo > min(o, c) or h < lo:
            rejects["inconsistent OHLC"] += 1
            continue
        if ts % step != 0:
            rejects["off-grid open time"] += 1
            continue
        prev = seen.get(ts)
        if prev is not None:
            if abs(prev["c"] - c) > 1e-9 or abs(prev["v"] - v) > 1e-9:
                conflicts += 1
            rejects["duplicate timestamp"] += 1
            continue
        seen[ts] = {
            "ts": ts, "o": o, "h": h, "l": lo, "c": c, "v": v,
            "n": trades,
            # Taker buy base volume: the share of the bar's volume that lifted the offer. It is a
            # published field of the kline and the one piece of order-flow information available
            # without a paid feed, so it is kept rather than discarded with the rest of the row.
            "tb": taker_base,
        }

    bars = [seen[t] for t in sorted(seen)]
    gaps: list[dict] = []
    if len(bars) >= 2:
        for a, b in zip(bars, bars[1:]):
            missing = (b["ts"] - a["ts"]) // step - 1
            if missing > 0:
                gaps.append({
                    "afterTs": a["ts"], "beforeTs": b["ts"], "missingBars": int(missing),
                    "from": datetime.fromtimestamp(a["ts"] / 1000, timezone.utc).isoformat(),
                    "to": datetime.fromtimestamp(b["ts"] / 1000, timezone.utc).isoformat(),
                })
    expected = ((bars[-1]["ts"] - bars[0]["ts"]) // step + 1) if bars else 0
    report = {
        "interval": interval,
        "barsKept": len(bars),
        "barsExpectedBetweenEnds": int(expected),
        "completeness": round(len(bars) / expected, 6) if expected else None,
        "firstTs": bars[0]["ts"] if bars else None,
        "lastTs": bars[-1]["ts"] if bars else None,
        "first": datetime.fromtimestamp(bars[0]["ts"] / 1000, timezone.utc).isoformat() if bars else None,
        "last": datetime.fromtimestamp(bars[-1]["ts"] / 1000, timezone.utc).isoformat() if bars else None,
        "immatureDropped": immature,
        "rejected": dict(rejects),
        "conflictingDuplicates": conflicts,
        "gapRuns": len(gaps),
        "missingBars": int(sum(g["missingBars"] for g in gaps)),
        "largestGapBars": max((g["missingBars"] for g in gaps), default=0),
        "gaps": gaps[:50],
    }
    return bars, report


def coinbase_candles(product: str, granularity: int, start: datetime, end: datetime) -> list[list]:
    """Up to 300 candles from Coinbase Exchange, for the cross-venue check."""
    url = (COINBASE.format(product=product)
           + f"?granularity={granularity}&start={start.isoformat()}&end={end.isoformat()}")
    page = _get(url)
    return page if isinstance(page, list) else []


#: Coinbase product for a Binance pair, for the coins the cross-check covers. Absent means the
#: check is reported as not run, which is a different answer from "it agreed".
COINBASE_PRODUCT = {
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD", "XRPUSDT": "XRP-USD",
    "ADAUSDT": "ADA-USD", "DOGEUSDT": "DOGE-USD", "LTCUSDT": "LTC-USD", "LINKUSDT": "LINK-USD",
    "AVAXUSDT": "AVAX-USD", "BCHUSDT": "BCH-USD", "DOTUSDT": "DOT-USD", "ATOMUSDT": "ATOM-USD",
    "UNIUSDT": "UNI-USD", "FILUSDT": "FIL-USD", "NEARUSDT": "NEAR-USD", "AAVEUSDT": "AAVE-USD",
}


def cross_check(symbol: str, bars: list[dict], interval: str) -> dict:
    """What a second venue printed over the same recent window.

    A disagreement here is normal and small -- two exchanges are two order books -- and the point
    is the size of it. A median difference of a few basis points says the series is a fair record
    of the market; one of several percent says the corpus is describing a different instrument.
    """
    product = COINBASE_PRODUCT.get(symbol)
    if not product or not bars:
        return {"checked": False, "why": f"no Coinbase product mapped for {symbol}"}
    gran = INTERVAL_MS[interval] // 1000
    if gran not in (60, 300, 900, 3600, 21600, 86400):
        return {"checked": False, "why": f"Coinbase does not serve a {gran}s granularity"}
    last = bars[-1]["ts"]
    start = datetime.fromtimestamp((last - 290 * INTERVAL_MS[interval]) / 1000, timezone.utc)
    end = datetime.fromtimestamp(last / 1000, timezone.utc)
    try:
        rows = coinbase_candles(product, gran, start, end)
    except RuntimeError as e:
        return {"checked": False, "why": str(e)}
    theirs = {int(r[0]) * 1000: float(r[4]) for r in rows if isinstance(r, list) and len(r) >= 5}
    pairs = [(b["c"], theirs[b["ts"]]) for b in bars[-300:] if b["ts"] in theirs]
    if not pairs:
        return {"checked": False, "why": "no overlapping timestamps"}
    diffs = sorted(abs(a - b) / b * 100 for a, b in pairs)
    mid = diffs[len(diffs) // 2]
    return {
        "checked": True,
        "venue": "Coinbase Exchange",
        "product": product,
        "overlappingBars": len(pairs),
        "medianAbsCloseDiffPct": round(mid, 5),
        "maxAbsCloseDiffPct": round(diffs[-1], 5),
        "note": "two exchanges are two order books; this measures whether they are quoting the "
                "same instrument, not whether either is 'correct'",
    }


def write(symbol: str, interval: str, bars: list[dict], report: dict, venue: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{symbol}-{interval}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for b in bars:
            fh.write(json.dumps(b, separators=(",", ":")) + "\n")
    meta = OUT / f"{symbol}-{interval}.manifest.json"
    meta.write_text(json.dumps({
        "symbol": symbol,
        "venue": venue,
        "collectedAt": datetime.now(timezone.utc).isoformat(),
        "file": path.name,
        "fields": {"ts": "bar open, ms since epoch UTC", "o": "open", "h": "high", "l": "low",
                   "c": "close", "v": "base volume", "n": "trade count",
                   "tb": "taker buy base volume"},
        **report,
    }, indent=1), encoding="utf-8")
    return path


def collect(symbol: str, interval: str, days: int, verify: bool = False,
            mirror: bool = False, progress: bool = False) -> dict:
    """Fetch, validate and store one symbol's series. Returns the completeness report."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 86_400_000
    raw = binance_klines(symbol, interval, start_ms, now_ms, mirror=mirror, progress=progress)
    bars, report = validate(raw, interval, now_ms)
    if verify:
        report["crossVenue"] = cross_check(symbol, bars, interval)
    report["path"] = str(write(symbol, interval, bars, report, "Binance"))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect validated intraday crypto bars.")
    ap.add_argument("symbols", nargs="+", help="Binance symbols, e.g. BTCUSDT ETHUSDT")
    ap.add_argument("--interval", default="5m", choices=sorted(INTERVAL_MS))
    ap.add_argument("--days", type=int, default=1100)
    ap.add_argument("--verify", action="store_true", help="cross-check against a second venue")
    ap.add_argument("--mirror", action="store_true", help="use data-api.binance.vision")
    a = ap.parse_args()

    failed = 0
    for symbol in a.symbols:
        print(f"{symbol} {a.interval}: fetching {a.days} days", flush=True)
        t0 = time.time()
        try:
            r = collect(symbol, a.interval, a.days, verify=a.verify, mirror=a.mirror,
                        progress=len(a.symbols) == 1)
        except (RuntimeError, urllib.error.HTTPError) as e:
            print(f"  FAIL {e}")
            failed += 1
            continue
        print(f"  kept {r['barsKept']:,} bars in {time.time() - t0:.0f}s  "
              f"completeness {r['completeness']}  "
              f"gaps {r['gapRuns']} runs / {r['missingBars']} bars  "
              f"rejected {sum(r['rejected'].values())}  {r['first']} .. {r['last']}")
        if r["rejected"]:
            print(f"  rejections: {r['rejected']}")
        cv = r.get("crossVenue") or {}
        if cv.get("checked"):
            print(f"  cross-venue vs {cv['venue']}: median |diff| {cv['medianAbsCloseDiffPct']}% "
                  f"over {cv['overlappingBars']} bars")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
