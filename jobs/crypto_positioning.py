"""The five-minute positioning series, accumulated forward because they cannot be backfilled.

    python jobs/crypto_positioning.py              # every coin with a perpetual
    python jobs/crypto_positioning.py BTCUSDT ETHUSDT

Why this is a job and not a collector
--------------------------------------
`tools/foundation/crypto_funding.py` fetches funding rates, and funding reaches back to 2020, so
one run gets the whole history. These three series do not:

  * **open interest** -- how much leverage is outstanding
  * **global long/short account ratio** -- how the crowd is positioned
  * **taker buy/sell ratio** -- which side is crossing the spread

They are the richest short-horizon inputs Binance publishes free, at five-minute granularity
matching our bar grid exactly, and Binance keeps **about thirty days of them**. A `startTime`
thirty days back is rejected outright with `parameter 'startTime' is invalid`. There is no
endpoint, no paid tier in reach and no archive that returns the missing years.

So the history can only be built going forward, which makes every day this does not run a day
that is gone permanently. That is the whole reason this file exists now rather than when the
features are ready to use it: the data has to be accumulating before it can be useful, and
nothing about waiting makes the gap smaller.

What it writes
--------------
One gzipped JSONL per coin under `.cache/foundation/positioning/`, appended on each run and
deduplicated on timestamp. Runs are idempotent: re-running within the window adds nothing, and a
run after an outage of under thirty days backfills the gap. Longer than that and the gap is
permanent, which the report counts rather than smooths over.

A note on what this data is
---------------------------
The long/short ratio is Binance's accounts, not the market's -- one venue's retail, not global
positioning. It is a real signal about a real population and it is not the whole market, and when
these eventually become features that distinction belongs in their documentation too.
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
ROOT = HERE.parent

CORPUS = ROOT / ".cache" / "foundation" / "intraday"
OUT = ROOT / ".cache" / "foundation" / "positioning"

FAPI = "https://fapi.binance.com"
PERIOD = "5m"
#: Binance caps these at 500 rows a call, which at five minutes is a touch under two days.
PAGE = 500

#: Meme coins trade as thousand-token contracts on futures. Ratios are unitless so the
#: denomination does not matter, but open interest is in contracts and is scaled accordingly --
#: recorded on the row so a later feature builder is not silently comparing different units.
DENOM = {"PEPEUSDT": "1000PEPEUSDT", "SHIBUSDT": "1000SHIBUSDT",
         "BONKUSDT": "1000BONKUSDT", "FLOKIUSDT": "1000FLOKIUSDT"}

SERIES = {
    "openInterest": ("futures/data/openInterestHist", "sumOpenInterest"),
    "longShortRatio": ("futures/data/globalLongShortAccountRatio", "longShortRatio"),
    "takerRatio": ("futures/data/takerlongshortRatio", "buySellRatio"),
}


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


def existing(path: Path) -> dict[int, dict]:
    if not path.exists():
        return {}
    rows: dict[int, dict] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                rows[int(r["ts"])] = r
    return rows


def fetch_series(wire: str, endpoint: str, field: str) -> dict[int, float]:
    """The whole retained window for one series, paged backwards from now.

    Paged on `endTime` rather than `startTime` because the retention boundary is the thing we do
    not know: asking for a start that is too old is an error, while walking back from now simply
    stops returning rows when the window runs out.
    """
    out: dict[int, float] = {}
    end = int(time.time() * 1000)
    for _ in range(20):                     # 20 x 500 x 5min is well past the ~30 day window
        try:
            page = _get(f"{FAPI}/{endpoint}?symbol={wire}&period={PERIOD}"
                        f"&endTime={end}&limit={PAGE}")
        except RuntimeError:
            # Walking back past the retention boundary is answered with HTTP 400, not an empty
            # page, so the error *is* the end-of-window signal. Only once rows are already in
            # hand, though: the same 400 on the first call is a real failure -- a delisted
            # symbol, a changed endpoint -- and swallowing it would write an empty file and call
            # it a successful collection.
            if out:
                break
            raise
        if not isinstance(page, list) or not page:
            break
        fresh = 0
        for r in page:
            t = int(r["timestamp"])
            if t not in out:
                out[t] = float(r[field])
                fresh += 1
        if fresh == 0:
            break
        end = min(out) - 1
        time.sleep(0.2)
    return out


def collect(symbol: str, perps: set[str]) -> dict:
    wire = DENOM.get(symbol, symbol)
    if wire not in perps:
        return {"symbol": symbol, "ok": False, "why": "no perpetual future listed"}

    series = {}
    for name, (endpoint, field) in SERIES.items():
        series[name] = fetch_series(wire, endpoint, field)

    stamps = sorted(set().union(*(set(s) for s in series.values())) if series else set())
    if not stamps:
        return {"symbol": symbol, "ok": False, "why": "no rows returned"}

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{symbol}-positioning.jsonl.gz"
    have = existing(path)
    added = 0
    for t in stamps:
        if t in have:
            continue
        have[t] = {"ts": t, "wire": wire,
                   **{k: series[k].get(t) for k in SERIES}}
        added += 1

    # Rewritten whole and sorted, so the file is always in timestamp order however many partial
    # runs produced it. Cheap at this size and it keeps every reader from having to sort.
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for t in sorted(have):
            fh.write(json.dumps(have[t], separators=(",", ":")) + "\n")

    ts = sorted(have)
    gaps = sum(1 for a, b in zip(ts, ts[1:]) if b - a > 300_000)
    return {
        "symbol": symbol, "wireSymbol": wire, "ok": True,
        "rowsAdded": added, "rowsTotal": len(have),
        "first": datetime.fromtimestamp(ts[0] / 1000, timezone.utc).isoformat(),
        "last": datetime.fromtimestamp(ts[-1] / 1000, timezone.utc).isoformat(),
        "spanDays": round((ts[-1] - ts[0]) / 86_400_000, 2),
        "gaps": gaps,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Accumulate the 30-day futures positioning series.")
    ap.add_argument("symbols", nargs="*")
    a = ap.parse_args()

    syms = a.symbols or sorted({p.name.split("-")[0] for p in CORPUS.glob("*-5m.jsonl.gz")})
    perps = perpetuals()
    print(f"positioning for {len(syms)} coins ({len(perps)} perpetuals listed)\n", flush=True)

    reports, ok, added_total = [], 0, 0
    for i, s in enumerate(syms, 1):
        try:
            r = collect(s, perps)
        except RuntimeError as e:
            r = {"symbol": s, "ok": False, "why": str(e)}
        reports.append(r)
        if r["ok"]:
            ok += 1
            added_total += r["rowsAdded"]
            print(f"  {i:>3}/{len(syms)}  {s:<14} +{r['rowsAdded']:>4} new, "
                  f"{r['rowsTotal']:>6} total, {r['spanDays']:>5.2f}d, {r['gaps']} gaps",
                  flush=True)
        else:
            print(f"  {i:>3}/{len(syms)}  {s:<14} -- {r['why']}", flush=True)

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "jobs/crypto_positioning.py",
        "period": PERIOD,
        "series": {k: v[0] for k, v in SERIES.items()},
        "retention": ("Binance keeps roughly 30 days of these; they cannot be backfilled, so "
                      "this job must run at least every ~25 days or the gap is permanent"),
        "caveat": ("longShortRatio is Binance accounts, not the whole market -- one venue's "
                   "retail positioning, which is a real population and not a global one"),
        "counts": {"asked": len(syms), "collected": ok, "rowsAdded": added_total},
        "coins": reports,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_report.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\n{ok} of {len(syms)} collected, {added_total:,} new rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
