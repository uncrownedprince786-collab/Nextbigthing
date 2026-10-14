"""Compare stored closes with a second, different provider on a deterministic sample.

    python tools/foundation/verify_prices.py [--n-stock 400] [--seed 20261014]

Why this exists: the earlier "reconcile exactly" check compared stored Yahoo closes with a live
Yahoo fetch, which tests the pipeline and not the provider. Here every class is checked against a
provider that is not the one that supplied the stored value:

    US stocks, ETFs      stored Yahoo      vs  Nasdaq historical, compared as DAILY RETURNS (see below)
    Crypto               stored Coinbase   vs  Binance USDT (fallback Bitstamp USD)
    Crypto (Kraken)      stored Kraken     vs  same
    Forex                stored Yahoo      vs  ECB euro reference rates, crossed through EUR
    PSX shares           stored PSX file   vs  Yahoo's Karachi listing (SYMBOL.KA, quoted in PKR)

Why returns for stocks and ETFs: the stored `close` for these is Yahoo's dividend-ADJUSTED close
(measured: it equals Yahoo's `adjclose`, not its `close`), while Nasdaq's is adjusted for splits
only. Their levels differ by the cumulative dividends since the date, so a level comparison would
fail on correct data and was the first thing this tool did. Returns agree except on ex-dividend
days, where the adjusted return is higher by about the dividend yield; those are classed
`dividend-consistent` only when the gap is positive and below 6%, and anything else is a
mismatch. The level gap itself is reported as a finding, because it means stored stock closes are
not the prices that traded and are rewritten whenever a new dividend is paid.

PSX is compared as returns for the same reason as US stocks: the exchange file carries the raw
close and Yahoo's Karachi series is adjusted, so the levels differ by the cumulative adjustment
while the daily returns should not.

Not verifiable independently, and said so rather than skipped silently: commodity futures (Yahoo
`=F` contracts have no free keyless counterpart, and a spot series is a different instrument), and
anything Stooq would cover (its pages sit behind a JavaScript challenge this tool does not bypass).

A difference is classified, never just counted: `within` the class tolerance, `split` when the
ratio is a clean split factor, or `mismatch`. Tolerances are stated up front and are about what
two honest providers can differ by (different venue, fix time, quote currency), not tuned to pass.

Read-only against the database. Summary statistics go to the repository; the fetched prices stay
in memory.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
OUT = ROOT / "data" / "foundation" / "price_verification"
BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/120.0 Safari/537.36")

# Relative tolerance per class: what two honest providers can disagree by.
TOL = {"stock": 0.001, "etf": 0.001, "crypto-coinbase": 0.005, "crypto-kraken": 0.005,
       "forex": 0.01, "psx": 0.001}
SPLITS = [2, 3, 4, 5, 6, 8, 10, 15, 20, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 20]


def get(url: str, headers: dict | None = None, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": BROWSER})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 451):
                return None
            time.sleep(2 * (i + 1))
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(2 * (i + 1))
    return None


def nasdaq(symbol: str, klass: str) -> dict[date, float]:
    asset = "etf" if klass == "etf" else "stocks"
    sym = symbol.replace("-", ".") if asset == "stocks" else symbol
    j = get(f"https://api.nasdaq.com/api/quote/{sym}/historical?assetclass={asset}"
            f"&fromdate=2019-01-01&limit=9999&todate={date.today().isoformat()}",
            {"User-Agent": BROWSER, "Accept": "application/json"})
    try:
        rows = j["data"]["tradesTable"]["rows"] or []
    except (TypeError, KeyError):
        return {}
    out = {}
    for r in rows:
        try:
            m, d, y = r["date"].split("/")
            out[date(int(y), int(m), int(d))] = float(r["close"].replace("$", "").replace(",", ""))
        except (ValueError, KeyError):
            continue
    return out


def yahoo_karachi(symbol: str) -> dict[date, float]:
    """Yahoo's Karachi listing for a PSX symbol. A different provider from the exchange file."""
    p1 = int(datetime(2019, 1, 1, tzinfo=timezone.utc).timestamp())
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}.KA"
            f"?period1={p1}&period2={int(time.time())}&interval=1d")
    try:
        r = j["chart"]["result"][0]
        if r["meta"].get("currency") != "PKR":
            return {}
        return {datetime.fromtimestamp(t, timezone.utc).date(): float(c)
                for t, c in zip(r.get("timestamp") or [],
                                r["indicators"]["quote"][0].get("close") or []) if c is not None}
    except (TypeError, KeyError, IndexError):
        return {}


def binance(ticker: str) -> dict[date, float]:
    out, start = {}, int(datetime(2018, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)
    for _ in range(4):
        j = get(f"https://api.binance.com/api/v3/klines?symbol={ticker.upper()}USDT&interval=1d"
                f"&startTime={start}&limit=1000")
        if not j:
            break
        for k in j:
            out[datetime.fromtimestamp(k[0] / 1000, timezone.utc).date()] = float(k[4])
        if len(j) < 1000:
            break
        start = j[-1][0] + 86400000
    return out


def bitstamp(ticker: str) -> dict[date, float]:
    out, start = {}, int(datetime(2018, 11, 1, tzinfo=timezone.utc).timestamp())
    for _ in range(4):
        j = get(f"https://www.bitstamp.net/api/v2/ohlc/{ticker.lower()}usd/?step=86400&limit=1000&start={start}")
        try:
            bars = j["data"]["ohlc"]
        except (TypeError, KeyError):
            break
        if not bars:
            break
        for b in bars:
            out[datetime.fromtimestamp(int(b["timestamp"]), timezone.utc).date()] = float(b["close"])
        if len(bars) < 1000:
            break
        start = int(bars[-1]["timestamp"]) + 86400
    return out


_ecb: dict[str, dict[date, float]] = {}


def ecb(cur: str) -> dict[date, float]:
    """Units of `cur` per EUR by date."""
    if cur == "EUR":
        return defaultdict(lambda: 1.0)
    if cur not in _ecb:
        url = (f"https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A"
               f"?startPeriod=2019-01-01&format=jsondata")
        j = get(url, {"User-Agent": BROWSER, "Accept": "application/json"})
        out = {}
        try:
            times = j["structure"]["dimensions"]["observation"][0]["values"]
            obs = next(iter(j["dataSets"][0]["series"].values()))["observations"]
            for idx, v in obs.items():
                out[date.fromisoformat(times[int(idx)]["id"])] = float(v[0])
        except (TypeError, KeyError, StopIteration, ValueError):
            pass
        _ecb[cur] = out
    return _ecb[cur]


def fx(symbol: str) -> dict[date, float]:
    base, quote = symbol[:3], symbol[3:6]
    b, q = ecb(base), ecb(quote)
    return {d: q[d] / b[d] for d in set(b) & set(q) if b[d] and q.get(d)} if base != "EUR" or quote != "EUR" else {}


def classify(stored: float, other: float, tol: float) -> tuple[str, float]:
    rel = abs(stored / other - 1)
    if rel <= tol:
        return "within", rel
    ratio = stored / other
    if any(abs(ratio / s - 1) < 0.02 for s in SPLITS):
        return "split", rel
    return "mismatch", rel


def sample(cur, klass: str, where: str, n: int, seed: int) -> list[dict]:
    cur.execute(f'''SELECT a.id, a.symbol, a."sourceRef", p.date, p.close FROM "PriceSnapshot" p
                    JOIN "Asset" a ON a.id = p."assetId" WHERE {where}
                    ORDER BY md5(a.symbol || p.date::text || '{seed}') LIMIT {int(n)}''')
    rows = [dict(r, klass=klass) for r in cur.fetchall()]
    if klass in ("stock", "etf", "psx"):
        for r in rows:
            cur.execute('SELECT date, close FROM "PriceSnapshot" WHERE "assetId" = %s AND date < %s '
                        'ORDER BY date DESC LIMIT 1', (r["id"], r["date"]))
            prev = cur.fetchone()
            r["prevDate"], r["prevClose"] = (prev["date"], float(prev["close"])) if prev else (None, None)
    return rows


def main() -> None:
    from nbt import db
    arg = lambda k, d: int(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
    seed, n_stock = arg("--seed", 20261014), arg("--n-stock", 400)
    cur = db().cursor()
    picks = (
        sample(cur, "stock", "a.\"assetType\"::text='stock' AND p.source='Yahoo Finance'", n_stock, seed)
        + sample(cur, "etf", "a.\"assetType\"::text='etf'", 80, seed)
        + sample(cur, "crypto-coinbase", "p.source='Coinbase'", 300, seed)
        + sample(cur, "crypto-kraken", "p.source='Kraken'", 60, seed)
        + sample(cur, "forex", "a.\"assetType\"::text='forex' AND p.source='Yahoo Finance'", 200, seed)
        + sample(cur, "psx", "p.source ILIKE 'Pakistan%'", 300, seed)
    )
    by_sym: dict[tuple, list[dict]] = defaultdict(list)
    for r in picks:
        by_sym[(r["klass"], r["symbol"])].append(r)
    results = defaultdict(lambda: {"sampled": 0, "compared": 0, "within": 0, "split": 0,
                                   "mismatch": 0, "dividend": 0, "noIndependentData": 0, "rel": [], "outliers": []})
    cache: dict[tuple, dict] = {}
    for (klass, sym), rows in sorted(by_sym.items()):
        res = results[klass]
        res["sampled"] += len(rows)
        if klass in ("stock", "etf"):
            key = ("n", sym)
            cache[key] = cache.get(key) or nasdaq(sym, klass)
            other, src = cache[key], "nasdaq"
            time.sleep(0.25)
        elif klass == "psx":
            key = ("k", sym)
            cache[key] = cache.get(key) or yahoo_karachi(sym)
            other, src = cache[key], "yahoo .KA"
            time.sleep(0.25)
        elif klass.startswith("crypto"):
            tick = sym.split("-")[0]
            key = ("c", tick)
            if key not in cache:
                cache[key] = binance(tick)
                if not cache[key]:
                    cache[key] = bitstamp(tick)
            other, src = cache[key], "binance/bitstamp"
        else:
            other, src = fx(sym), "ecb"
        for r in rows:
            o = other.get(r["date"]) if other else None
            if klass in ("stock", "etf", "psx"):
                po = other.get(r["prevDate"]) if other and r.get("prevDate") else None
                if not o or not po or not r.get("prevClose"):
                    res["noIndependentData"] += 1
                    continue
                res["compared"] += 1
                res.setdefault("levelDiffs", []).append(abs(float(r["close"]) / o - 1))
                rs, rn = float(r["close"]) / r["prevClose"] - 1, o / po - 1
                gap = rs - rn
                if abs(gap) <= 0.0005:
                    kind = "within"
                elif 0 < gap <= 0.06:
                    kind = "dividend"
                else:
                    kind = "mismatch"
                res[kind] = res.get(kind, 0) + 1
                res["rel"].append(abs(gap))
                if kind == "mismatch" and len(res["outliers"]) < 15:
                    res["outliers"].append({"symbol": sym, "date": r["date"].isoformat(), "kind": kind,
                                            "returnGapPct": round(gap * 100, 3), "versus": src})
                continue
            if not o:
                res["noIndependentData"] += 1
                continue
            res["compared"] += 1
            kind, rel = classify(float(r["close"]), o, TOL[klass])
            res[kind] += 1
            res["rel"].append(rel)
            if kind != "within" and len(res["outliers"]) < 15:
                res["outliers"].append({"symbol": sym, "date": r["date"].isoformat(), "kind": kind,
                                        "relDiffPct": round(rel * 100, 3), "versus": src})
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seed": seed,
              "tolerances": TOL, "classes": {}, "notIndependentlyVerifiable": {
                  "commodity futures (=F)": "no free keyless counterpart for the same contract",
                  "Stooq": "behind a JavaScript challenge; not bypassed"}}
    for k, v in results.items():
        lv = sorted(v.pop("levelDiffs", []))
        if lv:
            v["levelDiff"] = {"medianPct": round(statistics.median(lv) * 100, 3),
                              "shareAbove0.1pct": round(sum(x > 0.001 for x in lv) / len(lv), 3),
                              "note": "compared as returns: the two providers use different adjustment bases"}
        rel = sorted(v.pop("rel"))
        q = lambda p: round(rel[min(len(rel) - 1, int(len(rel) * p))] * 100, 4) if rel else None  # noqa: E731
        v.update({"medianAbsDiffPct": round(statistics.median(rel) * 100, 4) if rel else None,
                  "p95AbsDiffPct": q(0.95), "p99AbsDiffPct": q(0.99),
                  "withinShare": round(v["within"] / v["compared"], 4) if v["compared"] else None})
        report["classes"][k] = v
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for k, v in report["classes"].items():
        print(f"{k:16} sampled {v['sampled']:4} compared {v['compared']:4} within {v['within']:4} "
              f"div {v['dividend']:3} split {v['split']:3} mismatch {v['mismatch']:3} no-data {v['noIndependentData']:3} "
              f"median {v['medianAbsDiffPct']}% p99 {v['p99AbsDiffPct']}%")


if __name__ == "__main__":
    main()
