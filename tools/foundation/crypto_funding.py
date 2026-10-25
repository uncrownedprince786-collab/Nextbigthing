"""Perpetual funding rates: what the leveraged crowd is paying to hold its position.

    python tools/foundation/crypto_funding.py --all
    python tools/foundation/crypto_funding.py BTCUSDT ETHUSDT

Why this exists
---------------
Every one of the 52 features the brain currently reads is derived from OHLCV candles. Candles are
the **output** of a market -- the record of what price did. The information that moves price over
the next fifteen minutes is the **input**: who is positioned which way, how leveraged they are,
and what it is costing them to stay there. A model reading only candles is reading the scoreboard
and trying to infer the game.

Funding is the cheapest honest window into that. On a perpetual future, longs pay shorts (or the
reverse) every eight hours to keep the contract pinned to spot. When funding is strongly positive,
longs are crowded and paying rent to stay long -- which is both a sentiment reading and, more
usefully, squeeze fuel: crowded leveraged positions are what turn an ordinary move into a
cascade. None of that is recoverable from a price series, which is exactly why it is worth having.

What is available, and what is not
----------------------------------
Binance publishes four futures series. Only one of them is usable for training a model on history,
and the difference matters enough to record here:

  * **fundingRate** -- `/fapi/v1/fundingRate`. Goes back to **2020**, which is deeper than our
    candle corpus (October 2022). Available for 132 of the 140 pool coins. This is trainable now.
  * **openInterestHist**, **globalLongShortAccountRatio**, **takerlongshortRatio** -- all under
    `/futures/data/`. Richer, and at five-minute granularity, but Binance keeps only about **30
    days**. A `startTime` 30 days back is rejected outright. They cannot train a model on three
    years of candles, and no amount of asking changes that.

So this file collects funding, which can be used immediately. The thirty-day series need a
collector that runs forward from today and accumulates -- `jobs/crypto_positioning.py` -- and
becomes trainable once it has built up a history of its own. Writing that down because the
temptation with a thirty-day window is to backfill what cannot be backfilled and quietly train on
a sample that only covers one market regime.

Eight-hourly, not five-minutely
--------------------------------
Funding settles every eight hours, so it is a slow feature beside a five-minute bar: three values
a day, forward-filled to the bar grid. That is the honest shape of it. It is a regime variable
like the market-context block, not a trigger -- it says what the crowd has been doing, not what
the next bar will do.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

CORPUS = ROOT / ".cache" / "foundation" / "intraday"
OUT = ROOT / ".cache" / "foundation" / "funding"

FAPI = "https://fapi.binance.com"
#: Binance caps a funding page at 1000 rows. At three a day that is a touch under a year.
PAGE = 1000

#: Meme coins are quoted on futures in thousand-token units. The funding rate itself is a rate, so
#: the denomination does not change it -- but the symbol has to be right to find it at all.
DENOM = {"PEPEUSDT": "1000PEPEUSDT", "SHIBUSDT": "1000SHIBUSDT",
         "BONKUSDT": "1000BONKUSDT", "FLOKIUSDT": "1000FLOKIUSDT"}


def _get(url: str, tries: int = 4) -> object:
    last: Exception | None = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def perpetuals() -> set[str]:
    info = _get(f"{FAPI}/fapi/v1/exchangeInfo")
    return {s["symbol"] for s in info["symbols"]                      # type: ignore[index]
            if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING"}


def funding_history(symbol: str, start_ms: int) -> list[dict]:
    """Every funding settlement from `start_ms` to now, paged forward.

    Paged on `startTime` rather than by offset: the endpoint returns oldest-first within a page,
    so the cursor is the last `fundingTime` seen plus one millisecond. Stops when a page comes
    back short, which is the only reliable end-of-data signal here.
    """
    rows: list[dict] = []
    cursor = start_ms
    seen: set[int] = set()
    while True:
        page = _get(f"{FAPI}/fapi/v1/fundingRate?symbol={symbol}"
                    f"&startTime={cursor}&limit={PAGE}")
        if not isinstance(page, list) or not page:
            break
        fresh = 0
        for r in page:
            t = int(r["fundingTime"])
            if t in seen:
                continue
            seen.add(t)
            rows.append({"ts": t, "rate": float(r["fundingRate"])})
            fresh += 1
        if fresh == 0 or len(page) < PAGE:
            break
        cursor = max(seen) + 1
        time.sleep(0.25)
    rows.sort(key=lambda r: r["ts"])
    return rows


def corpus_start(symbol: str) -> int:
    """The first bar we hold for this coin, so funding is not fetched deeper than it is useful."""
    p = CORPUS / f"{symbol}-5m.jsonl.gz"
    if not p.exists():
        return 1_600_000_000_000
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        first = json.loads(fh.readline())
    # One funding interval before the first bar, so the first bar has a value to carry forward
    # rather than a hole the feature builder has to impute.
    return int(first["ts"]) - 8 * 3_600_000


def collect(symbol: str, perps: set[str]) -> dict:
    wire = DENOM.get(symbol, symbol)
    if wire not in perps:
        return {"symbol": symbol, "ok": False, "why": "no perpetual future listed"}
    start = corpus_start(symbol)
    rows = funding_history(wire, start)
    if not rows:
        return {"symbol": symbol, "ok": False, "why": "no funding rows returned"}

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{symbol}-funding.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")

    gaps = sum(1 for a, b in zip(rows, rows[1:]) if b["ts"] - a["ts"] > 9 * 3_600_000)
    return {
        "symbol": symbol, "wireSymbol": wire, "ok": True, "rows": len(rows),
        "first": datetime.fromtimestamp(rows[0]["ts"] / 1000, timezone.utc).isoformat(),
        "last": datetime.fromtimestamp(rows[-1]["ts"] / 1000, timezone.utc).isoformat(),
        "gapsOverNineHours": gaps,
        "meanRate": round(sum(r["rate"] for r in rows) / len(rows), 8),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect perpetual funding rate history.")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--all", action="store_true", help="every coin in the bar corpus")
    a = ap.parse_args()

    syms = sorted({p.name.split("-")[0] for p in CORPUS.glob("*-5m.jsonl.gz")}) \
        if a.all else a.symbols
    if not syms:
        raise SystemExit("name symbols or pass --all")

    print(f"funding for {len(syms)} coins", flush=True)
    perps = perpetuals()
    print(f"   {len(perps)} perpetuals listed on Binance futures\n", flush=True)

    reports, ok, missing = [], 0, []
    for i, s in enumerate(syms, 1):
        try:
            r = collect(s, perps)
        except RuntimeError as e:
            r = {"symbol": s, "ok": False, "why": str(e)}
        reports.append(r)
        if r["ok"]:
            ok += 1
            print(f"  {i:>3}/{len(syms)}  {s:<14} {r['rows']:>5} settlements  "
                  f"{r['first'][:10]} -> {r['last'][:10]}  mean {r['meanRate']:+.6f}", flush=True)
        else:
            missing.append(s)
            print(f"  {i:>3}/{len(syms)}  {s:<14} -- {r['why']}", flush=True)

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/foundation/crypto_funding.py",
        "source": f"{FAPI}/fapi/v1/fundingRate",
        "note": ("funding settles every 8 hours; the five-minute positioning series "
                 "(open interest, long/short, taker ratio) retain only ~30 days and are "
                 "collected forward by jobs/crypto_positioning.py instead"),
        "counts": {"asked": len(syms), "collected": ok, "unavailable": len(missing)},
        "unavailable": missing,
        "coins": reports,
    }
    (OUT / "_report.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\n{ok} of {len(syms)} collected; {len(missing)} without a perpetual", flush=True)
    print(f"wrote {OUT / '_report.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
