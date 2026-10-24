"""Is the price we print for each coin the price the market is actually trading it at?

    python tools/foundation/price_audit.py
    python tools/foundation/price_audit.py --max-disagreement 2.0 --fail

Every coin on the site is priced from one venue -- Binance where it is listed, then MEXC, then
Gate. That is a single point of failure for the most basic number on the page, and the ways it
goes wrong are quiet ones: a ticker that means two different assets on two exchanges, a pair left
listed after it stopped trading, a thin book whose last print is hours old, a mapping that was
right when it was written.

None of those produces an error. They produce a *number*, which is why this exists.

What it does
------------
For every coin listed on more than one venue it compares the last trade across them. Agreement is
the normal case and is reported as a distribution, not a pass: the interesting output is the tail.
Where a second source (CoinPaprika, which is also where the market capitalisations come from) has
the coin, that is compared too -- a third opinion settles which of two disagreeing venues is the
odd one.

Why a percentage and not an absolute
------------------------------------
Exchanges genuinely differ. Fees, depth and the exact instant of the last print put two honest
quotes a few basis points apart, and a thin coin can sit a percent apart all day without either
venue being wrong. So this reports where each coin sits and flags the tail, rather than pretending
there is one true price.

What a flag means
-----------------
Not "this price is wrong" -- "these two venues disagree by more than coins normally do, and one of
them is what the site is printing". Each flagged coin is listed with every venue's quote so the
reader can see which one is the outlier, and `--fail` turns the tail into a non-zero exit for CI.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
UNIVERSE = ROOT / "data" / "foundation" / "dataset" / "crypto_universe.json"
OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_price_audit.json"

#: Above this, two venues are further apart than coins normally sit and the pair is listed.
DEFAULT_MAX = 2.0


def get(url: str, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "nextbigthing-price-audit"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def safe(url: str, label: str):
    try:
        return get(url)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  {label}: unreachable ({type(e).__name__})", file=sys.stderr)
        return None


def binance_prices() -> dict[str, float]:
    rows = safe("https://data-api.binance.vision/api/v3/ticker/price", "binance")
    out = {}
    for r in rows or []:
        try:
            v = float(r["price"])
            if v > 0:
                out[r["symbol"]] = v
        except (KeyError, TypeError, ValueError):
            continue
    return out


def mexc_prices() -> dict[str, float]:
    rows = safe("https://api.mexc.com/api/v3/ticker/price", "mexc")
    out = {}
    for r in rows or []:
        try:
            v = float(r["price"])
            if v > 0:
                out[r["symbol"]] = v
        except (KeyError, TypeError, ValueError):
            continue
    return out


def gate_prices() -> dict[str, float]:
    rows = safe("https://api.gateio.ws/api/v4/spot/tickers", "gate")
    out = {}
    for r in rows or []:
        try:
            v = float(r["last"])
            if v > 0:
                out[r["currency_pair"]] = v
        except (KeyError, TypeError, ValueError):
            continue
    return out


def paprika_prices() -> dict[str, list[float]]:
    rows = safe("https://api.coinpaprika.com/v1/tickers?quotes=USD", "coinpaprika")
    out: dict[str, list[float]] = {}
    for r in rows or []:
        try:
            out.setdefault(r["symbol"].upper(), []).append(float(r["quotes"]["USD"]["price"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare every coin's price across its venues.")
    ap.add_argument("--max-disagreement", type=float, default=DEFAULT_MAX,
                    help="percent; above this a coin is listed in the tail")
    ap.add_argument("--fail", action="store_true",
                    help="exit non-zero when anything is in the tail")
    ap.add_argument("--show", type=int, default=25)
    a = ap.parse_args()

    uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))["assets"]
    print(f"checking {len(uni)} coins across three venues...", flush=True)
    b, m, g = binance_prices(), mexc_prices(), gate_prices()
    pap = paprika_prices()
    print(f"  binance {len(b)}  mexc {len(m)}  gate {len(g)}  coinpaprika {len(pap)}", flush=True)

    rows = []
    spreads = []
    no_quote = []
    for c in uni:
        on = c.get("on") or {}
        quotes: dict[str, float] = {}
        if on.get("binance") and on["binance"] in b:
            quotes["binance"] = b[on["binance"]]
        if on.get("mexc") and on["mexc"] in m:
            quotes["mexc"] = m[on["mexc"]]
        if on.get("gate") and on["gate"] in g:
            quotes["gate"] = g[on["gate"]]

        served = quotes.get(c["venue"])
        if served is None:
            # The venue the site would price this coin from did not quote it at all. Worth
            # knowing: the page falls back to a stored close, or to an em dash.
            no_quote.append(c["slug"])
            continue

        # The second source only counts when it is unambiguous for this ticker. A ticker shared by
        # two coins there cannot adjudicate between two venues; it would just add a third number.
        cands = pap.get(c["ticker"].upper(), [])
        third = cands[0] if len(cands) == 1 else None

        values = dict(quotes)
        if third:
            values["coinpaprika"] = third
        if len(values) < 2:
            continue

        lo, hi = min(values.values()), max(values.values())
        spread = (hi - lo) / lo * 100 if lo > 0 else 0.0
        spreads.append(spread)
        rows.append({
            "slug": c["slug"],
            "ticker": c["ticker"],
            "servedBy": c["venue"],
            "servedPrice": served,
            "quotes": {k: round(v, 10) for k, v in values.items()},
            "spreadPct": round(spread, 4),
        })

    rows.sort(key=lambda r: -r["spreadPct"])
    tail = [r for r in rows if r["spreadPct"] > a.max_disagreement]

    q = sorted(spreads)

    def pct(p: float) -> float:
        return round(q[min(len(q) - 1, int(len(q) * p))], 4) if q else 0.0

    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/foundation/price_audit.py",
        "coinsChecked": len(rows),
        "comparedAcross": "the venues that list each coin, plus CoinPaprika where its ticker is "
                          "unambiguous there",
        "noQuoteFromServingVenue": no_quote,
        "spreadPct": {
            "median": round(statistics.median(spreads), 4) if spreads else None,
            "p90": pct(0.90), "p99": pct(0.99),
            "max": round(max(spreads), 4) if spreads else None,
        },
        "threshold": a.max_disagreement,
        "beyondThreshold": len(tail),
        "worst": rows[: max(a.show, 0)],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=1), encoding="utf-8")

    s = summary["spreadPct"]
    print(f"\n{len(rows)} coins quoted by more than one source")
    print(f"  spread: median {s['median']}%  p90 {s['p90']}%  p99 {s['p99']}%  max {s['max']}%")
    print(f"  {len(tail)} beyond {a.max_disagreement}%")
    if no_quote:
        print(f"  {len(no_quote)} got no quote from the venue that serves them: "
              f"{', '.join(no_quote[:8])}{' ...' if len(no_quote) > 8 else ''}")
    for r in tail[: a.show]:
        qs = "  ".join(f"{k} {v:.8g}" for k, v in r["quotes"].items())
        print(f"    {r['ticker']:<12} {r['spreadPct']:>8.2f}%  served by {r['servedBy']:<8} {qs}")
    print(f"\nwrote {OUT}")
    return 1 if (a.fail and tail) else 0


if __name__ == "__main__":
    raise SystemExit(main())
