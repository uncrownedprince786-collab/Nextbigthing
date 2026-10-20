"""Write the fixture `tests/intradayParity.test.ts` checks the TypeScript features against.

    python tools/research/write_parity_fixture.py

Real bars, not synthetic ones. A hand-made series with round numbers and even volume would pass a
parity test that a real one fails: the components that diverge between two implementations are the
ones with a degenerate branch -- a zero range, a bar with no trades, a flat window -- and those
appear in real data and not in a generator someone wrote to look reasonable.

The fixture holds the bars, the row indices checked, and the expected vector per row from
`intraday_features.features_at`, which is the definition. It is committed, so the test needs
neither a corpus nor a network.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from intraday_features import FEATURES, VERSION, WARMUP, features_at  # noqa: E402

CORPUS = ROOT / ".cache" / "foundation" / "intraday"
OUT = ROOT / "tests" / "fixtures" / "intradayParity.json"
#: Enough bars for two decision rows past the warm-up, plus a margin.
BARS = WARMUP + 24


def slice_from(symbol: str, interval: str, start: int) -> list[dict]:
    path = CORPUS / f"{symbol}-{interval}.jsonl.gz"
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < start:
                continue
            out.append(json.loads(line))
            if len(out) >= BARS:
                break
    return out


def main() -> int:
    cases = []
    # Three windows from different years and two intervals, so the fixture covers a quiet stretch,
    # a volatile one and the coarser corpus the session horizons read.
    for symbol, interval, start in (("BTCUSDT", "5m", 50_000), ("BTCUSDT", "5m", 300_000),
                                    ("BTCUSDT", "4h", 8_000)):
        bars = slice_from(symbol, interval, start)
        if len(bars) < BARS:
            raise SystemExit(f"{symbol} {interval}: only {len(bars)} bars from offset {start}")
        rows = [WARMUP, WARMUP + 7, len(bars) - 1]
        cases.append({
            "symbol": symbol,
            "interval": interval,
            "bars": bars,
            "expect": [{"i": i, "features": features_at(bars, i)} for i in rows],
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "featureSchema": VERSION,
        "featureNames": FEATURES,
        "warmup": WARMUP,
        "producedBy": "tools/research/write_parity_fixture.py",
        "cases": cases,
    }, separators=(",", ":")), encoding="utf-8")
    n = sum(len(c["expect"]) for c in cases)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(cases)} cases, {n} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
