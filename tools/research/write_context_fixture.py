"""Write the fixture `tests/marketContextParity.test.ts` checks the TypeScript context block against.

    python tools/research/write_context_fixture.py

Same arrangement as `write_parity_fixture.py` and for the same reason: the market-factor block is
defined once in `tools/research/market_context.py`, fitted in Python over a million rows, and
recomputed on every request in `lib/marketContext.ts`. One definition, two implementations, and a
component that drifts between them is invisible in every metric the site shows.

Real bars from two coins against real Bitcoin bars, not synthetic series. The components that
diverge between two implementations are the ones with a degenerate branch -- a flat factor window,
a zero range, a beta at its clip -- and those appear in real data and not in a generator written to
look reasonable.

A second case is included deliberately: **Bitcoin against itself**, where the residuals are exactly
zero and the beta is exactly one. That is the degenerate case the trainer sees on every BTC row, so
it is the one a serving path is most likely to get subtly wrong.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from market_context import CONTEXT_FEATURES, VERSION, context_for  # noqa: E402
from intraday_features import WARMUP  # noqa: E402

CORPUS = ROOT / ".cache" / "foundation" / "intraday"
OUT = ROOT / "tests" / "fixtures" / "marketContextParity.json"

#: Enough bars for several decision rows past the warm-up.
BARS = WARMUP + 40


def read(symbol: str, start: int, count: int) -> list[dict]:
    path = CORPUS / f"{symbol}-5m.jsonl.gz"
    if not path.exists():
        raise SystemExit(f"no corpus at {path}")
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < start:
                continue
            out.append(json.loads(line))
            if len(out) >= count:
                break
    return out


def case(label: str, coin: str, start: int) -> dict:
    """One case: a coin's window, the factor's window over the same instants, and the answers."""
    coin_bars = read(coin, start, BARS)
    first_ts = coin_bars[0]["ts"]
    # The factor window has to cover the same instants. Read a generous slice of Bitcoin and keep
    # the bars whose timestamps fall inside the coin's span -- which is exactly what the serving
    # path has: two independently fetched windows that happen to overlap.
    btc_all = read("BTCUSDT", 0, 0) if coin == "BTCUSDT" else None
    if coin == "BTCUSDT":
        mkt_bars = list(coin_bars)
    else:
        span = {b["ts"] for b in coin_bars}
        mkt_bars = []
        with gzip.open(CORPUS / "BTCUSDT-5m.jsonl.gz", "rt", encoding="utf-8") as fh:
            for line in fh:
                b = json.loads(line)
                if b["ts"] > coin_bars[-1]["ts"]:
                    break
                if b["ts"] >= first_ts or b["ts"] in span:
                    mkt_bars.append(b)
    del btc_all

    ts = np.asarray([b["ts"] for b in coin_bars], dtype=np.int64)
    close = np.asarray([b["c"] for b in coin_bars], dtype=np.float64)
    mts = np.asarray([b["ts"] for b in mkt_bars], dtype=np.int64)
    mc = np.asarray([b["c"] for b in mkt_bars], dtype=np.float64)
    mh = np.asarray([b["h"] for b in mkt_bars], dtype=np.float64)
    ml = np.asarray([b["l"] for b in mkt_bars], dtype=np.float64)

    C, ok = context_for(ts, close, mts, mc, mh, ml, WARMUP)
    rows = [int(i) for i in np.flatnonzero(ok)][-3:]
    if not rows:
        raise SystemExit(f"{label}: no usable rows -- the factor window does not cover the coin's")
    return {
        "label": label,
        "symbol": coin,
        "bars": coin_bars,
        "marketBars": mkt_bars,
        "rows": rows,
        "expected": [[float(v) for v in C[i]] for i in rows],
    }


def main() -> int:
    cases = [
        case("an altcoin against Bitcoin", "ETHUSDT", 40_000),
        # The degenerate case the trainer sees on every Bitcoin row.
        case("Bitcoin against itself", "BTCUSDT", 60_000),
    ]
    doc = {
        "contextVersion": VERSION,
        "featureNames": list(CONTEXT_FEATURES),
        "warmup": WARMUP,
        "producedBy": "tools/research/write_context_fixture.py",
        "note": "Real bars. The expected vectors are what market_context.context_for -- the "
                "definition -- returned, and lib/marketContext.ts must reproduce them.",
        "cases": cases,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT}: {len(cases)} cases, "
          f"{sum(len(c['rows']) for c in cases)} rows, {OUT.stat().st_size // 1024} KB")
    for c in cases:
        print(f"  {c['label']}: {len(c['bars'])} coin bars, {len(c['marketBars'])} factor bars, "
              f"rows {c['rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
