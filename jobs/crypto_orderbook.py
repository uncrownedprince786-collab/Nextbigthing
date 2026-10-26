"""Order book depth, accumulated forward, because none of it can be bought back later.

    python jobs/crypto_orderbook.py                 # one snapshot of each watched coin
    python jobs/crypto_orderbook.py --loop 60       # every 60s until stopped

Every feature this brain reads is derived from candles, and seventeen measured attempts to
improve it on that basis have moved it from 53% to 57% and no further. The candle is the market's
**output**: a summary of what traded. The order book is its **input** -- what is resting, at what
price, on which side, and how that changes as it is consumed. The firms that beat these numbers
at five-minute horizons read the second thing.

There is no historical substitute. Venues do not publish past depth for free, and the paid
archives that do are priced per month of history. What can be had for nothing is **now**: a
snapshot taken every minute is a row that exists forever afterwards, and a row not taken is gone.
So this runs forward from today and the corpus grows at the only rate available.

What is kept per snapshot
-------------------------
Not the raw book -- fifty tiers a minute across nine coins is gigabytes a month and almost all of
it is noise. What survives is the handful of quantities that microstructure research keeps coming
back to:

  * **spread**, absolute and in basis points: the floor under every round trip, and the number
    that decides whether a 55% edge is tradable at all;
  * **depth** on each side at 5, 10 and 25 basis points from mid: how much can actually be filled
    before the price moves away;
  * **imbalance** at each of those distances -- bid depth over total -- which is the single most
    studied short-horizon predictor in the literature;
  * **slope**: how fast depth thins as you walk away from mid, a read on how brittle the book is;
  * **mid and microprice**, the second weighted by the touch sizes, which is a better estimate of
    where the next trade prints than the mid is.

Each row is small, so a year of minute snapshots for nine coins is tens of megabytes rather than
gigabytes, and every field is computed from one instant of one book -- nothing here needs a
history to be correct, which keeps the collector restartable.

Why a REST snapshot rather than a websocket
--------------------------------------------
A websocket diff stream reconstructs the book exactly and needs a process that never misses a
message, resyncs after a gap, and is correct about sequence numbers. A depth snapshot is one HTTP
call that is either right or absent. For features measured at five-minute horizons the difference
between a continuous book and a once-a-minute photograph of it is small, and the difference
between a collector that runs unattended for three months and one that silently desynchronises is
not. The exact book can come later, on top of a corpus that already exists.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / ".cache" / "foundation" / "orderbook"

BINANCE = "https://data-api.binance.vision"
DEPTH_LIMIT = 100

#: The coins the board carries. Mirrors components/CoinTable.WATCHLIST, by venue instrument.
WATCHED = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
           "LINKUSDT", "AVAXUSDT", "DOTUSDT", "SUIUSDT"]

#: Distances from mid, in basis points, that depth and imbalance are measured at.
BANDS_BPS = (5, 10, 25)


def _get(url: str, tries: int = 3) -> object | None:
    last: Exception | None = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nextbigthing"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
            last = e
            time.sleep(1.0 * (i + 1))
    print(f"   ! {url.split('symbol=')[-1]}: {last}", flush=True)
    return None


def summarise(book: dict, ts_ms: int, symbol: str) -> dict | None:
    """One book into one row. Returns None when the book is unusable."""
    bids = [(float(p), float(q)) for p, q in book.get("bids", [])[:DEPTH_LIMIT]]
    asks = [(float(p), float(q)) for p, q in book.get("asks", [])[:DEPTH_LIMIT]]
    if not bids or not asks:
        return None
    best_bid, bid_sz = bids[0]
    best_ask, ask_sz = asks[0]
    if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
        return None

    mid = (best_bid + best_ask) / 2.0
    spread = best_ask - best_bid
    # Microprice: the touch weighted by the *opposite* side's size, which is the standard form --
    # a large bid and a thin ask means the next print is likelier near the ask.
    total_touch = bid_sz + ask_sz
    micro = ((best_bid * ask_sz + best_ask * bid_sz) / total_touch) if total_touch > 0 else mid

    row: dict = {
        "ts": ts_ms,
        "sym": symbol,
        "mid": mid,
        "micro": micro,
        "spreadBps": (spread / mid) * 10_000.0 if mid > 0 else None,
        "bidSz": bid_sz,
        "askSz": ask_sz,
    }

    for bps in BANDS_BPS:
        lo = mid * (1.0 - bps / 10_000.0)
        hi = mid * (1.0 + bps / 10_000.0)
        bid_depth = sum(p * q for p, q in bids if p >= lo)
        ask_depth = sum(p * q for p, q in asks if p <= hi)
        total = bid_depth + ask_depth
        row[f"bid{bps}"] = bid_depth
        row[f"ask{bps}"] = ask_depth
        # Imbalance in [0, 1]: above a half means more resting bid than ask within the band.
        row[f"imb{bps}"] = (bid_depth / total) if total > 0 else None

    # Slope: how much of the 25bp depth is already present inside 5bp. A book that is all at the
    # touch is brittle; one that thickens outward absorbs size.
    wide = (row["bid25"] or 0) + (row["ask25"] or 0)
    near = (row["bid5"] or 0) + (row["ask5"] or 0)
    row["slope"] = (near / wide) if wide > 0 else None
    return row


def snapshot(symbols: list[str]) -> tuple[int, int]:
    """One pass over the watched coins. Returns `(written, failed)`."""
    OUT.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    written = failed = 0
    for sym in symbols:
        book = _get(f"{BINANCE}/api/v3/depth?symbol={sym}&limit={DEPTH_LIMIT}")
        if not isinstance(book, dict):
            failed += 1
            continue
        row = summarise(book, int(time.time() * 1000), sym)
        if row is None:
            failed += 1
            continue
        # One file per coin per UTC day: appendable, restartable, and trivially prunable later
        # without rewriting a single large archive.
        path = OUT / f"{sym}-{day}.jsonl.gz"
        with gzip.open(path, "at", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":"), default=_clean) + "\n")
        written += 1
        time.sleep(0.25)
    return written, failed


def _clean(v: object) -> object:
    # NaN and infinity are not JSON, and a row that quietly carries them is a row that explodes
    # at read time rather than at write time.
    if isinstance(v, float) and not math.isfinite(v):
        return None
    raise TypeError(f"not serialisable: {type(v)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Accumulate order book depth for the watched coins.")
    ap.add_argument("symbols", nargs="*", default=None)
    ap.add_argument("--loop", type=float, default=0.0,
                    help="seconds between passes; 0 takes one snapshot and exits")
    a = ap.parse_args()
    symbols = a.symbols or WATCHED

    print(f"order book: {len(symbols)} coins, {DEPTH_LIMIT} tiers, bands {BANDS_BPS} bps",
          flush=True)
    if a.loop <= 0:
        w, f = snapshot(symbols)
        print(f"   {w} written, {f} failed", flush=True)
        return 0

    passes = total_w = total_f = 0
    try:
        while True:
            started = time.time()
            w, f = snapshot(symbols)
            passes += 1
            total_w += w
            total_f += f
            if passes % 10 == 0:
                print(f"   {passes} passes, {total_w:,} rows, {total_f} failures, "
                      f"{datetime.now(timezone.utc):%H:%M:%S}Z", flush=True)
            # Sleep the remainder, so the cadence is the interval rather than the interval plus
            # however long the venue took.
            time.sleep(max(0.0, a.loop - (time.time() - started)))
    except KeyboardInterrupt:
        print(f"\nstopped after {passes} passes, {total_w:,} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
