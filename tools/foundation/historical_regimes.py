"""The regime library over the full benchmark history, back to 1927 where the data reaches.

    python tools/foundation/historical_regimes.py [--out DIR]

Writes `data/foundation/dataset/historical_regimes.json`. Reads only committed benchmark files;
no database, no network.

**What this adds to `regime_coverage.json`.** That file answers "are the crashes in the training
examples" and is therefore bounded to 2018, where the instrument history starts. This one answers
a different question -- "which historical regimes does this project hold any evidence for at all"
-- and runs over the benchmark series, which go back much further: `^GSPC` to 1927, `DFF` to 1954,
`DGS10` to 1962, `DX-Y.NYB` to 1971, `DCOILWTICO` to 1986, `^VIX` to 1990.

**The distinction that must not blur.** A regime found here is present in a *benchmark series*.
It is **not** present in `examples-v3`, which begins in 2018 and holds no instrument-level bar
before it. 1929, 1987, the dot-com bear and 2008 are measurable here and are **not trainable**
from this project's data. Each episode therefore carries `inTrainingData` explicitly, and for
everything before 2018 that value is false.

**Named episodes are checked, not assumed.** A list of famous crashes is a list of claims. Each
named window below is tested against the series: the tool reports the drawdown it actually finds
in that window, and says so when a series does not reach back far enough to see it.

Thresholds are reported as a sensitivity, as in `regime_coverage.py`, because one cutoff cannot
serve 1929 and 2018 equally.
"""

from __future__ import annotations

import gzip
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BENCH = ROOT / "data" / "foundation" / "benchmarks"
OUT_DIR = ROOT / "data" / "foundation" / "dataset"

THRESHOLDS = (0.10, 0.20, 0.30, 0.50)
PRIMARY = 0.20
TRAINING_DATA_STARTS = date(2018, 1, 1)

SERIES = {
    "^GSPC": ("GSPC.csv.gz", "US large-cap equity"),
    "^SP500TR": ("SP500TR.csv.gz", "US equity total return"),
    "^VIX": ("VIX.csv.gz", "US equity implied volatility"),
    "DX-Y.NYB": ("DX-Y.NYB.csv.gz", "US dollar index"),
    "GC=F": ("GC_F.csv.gz", "gold"),
    "BZ=F": ("BZ_F.csv.gz", "Brent crude"),
    "DCOILWTICO": ("DCOILWTICO.csv.gz", "WTI crude"),
    "DGS10": ("DGS10.csv.gz", "US 10-year Treasury yield"),
    "DFF": ("DFF.csv.gz", "effective fed funds rate"),
}

# The episodes the brief names. Windows are generous: the tool reports the worst fall it actually
# finds inside each, rather than asserting the textbook figure.
NAMED = [
    ("1929 crash and Great Depression", "1929-09-01", "1932-07-31"),
    ("1973-74 bear market and oil shock", "1973-01-01", "1974-12-31"),
    ("1987 crash", "1987-08-01", "1987-12-31"),
    ("1997-98 Asian / Russian / LTCM stress", "1997-07-01", "1998-12-31"),
    ("2000-02 dot-com bear market", "2000-03-01", "2002-12-31"),
    ("2007-09 Global Financial Crisis", "2007-10-01", "2009-06-30"),
    ("2010-12 European sovereign-debt stress", "2010-04-01", "2012-12-31"),
    ("2014-16 commodity and oil downturn", "2014-06-01", "2016-02-29"),
    ("2018 sell-off", "2018-09-01", "2018-12-31"),
    ("COVID crash 2020", "2020-02-01", "2020-04-30"),
    ("2022 inflation and rate-shock bear", "2022-01-01", "2022-12-31"),
    ("2023 banking stress", "2023-03-01", "2023-05-31"),
]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def read_series(path: Path) -> list[tuple[date, float]]:
    if not path.exists():
        return []
    opener = gzip.open if path.suffix == ".gz" else open
    out = []
    with opener(path, "rt", encoding="utf-8") as fh:
        head = fh.readline().strip().split(",")
        # Yahoo-derived files carry OHLCV and name the column `close`; FRED series are a single
        # observation per date and name it `value`. Both are price-like levels for this purpose.
        di = head.index("date") if "date" in head else 0
        ci = next((head.index(c) for c in ("close", "value") if c in head), None)
        if ci is None:
            return []
        for line in fh:
            f = line.rstrip("\n").split(",")
            try:
                d, v = date.fromisoformat(f[di]), float(f[ci])
            except (ValueError, IndexError):
                continue
            if v > 0:
                out.append((d, v))
    return sorted(out)


def worst_in_window(series, a: date, b: date) -> dict | None:
    """The deepest peak-to-trough fall whose peak and trough both sit inside [a, b]."""
    seg = [(d, v) for d, v in series if a <= d <= b]
    if len(seg) < 3:
        return None
    peak_d, peak_v = seg[0]
    best = None
    for d, v in seg:
        if v > peak_v:
            peak_d, peak_v = d, v
        dd = v / peak_v - 1
        if best is None or dd < best["drawdownPct"] / 100:
            best = {"peakDate": peak_d.isoformat(), "peakClose": round(peak_v, 4),
                    "troughDate": d.isoformat(), "troughClose": round(v, 4),
                    "drawdownPct": round(dd * 100, 2)}
    return best


def all_episodes(series, threshold: float) -> int:
    if not series:
        return 0
    n, peak, trough, inep = 0, series[0][1], series[0][1], False
    for _, v in series:
        if v >= peak:
            if inep:
                n += 1
                inep = False
            peak = trough = v
            continue
        trough = min(trough, v)
        if not inep and trough / peak - 1 <= -threshold:
            inep = True
    return n + (1 if inep else 0)


def main() -> int:
    out_dir = Path(arg("--out", OUT_DIR))
    out_dir.mkdir(parents=True, exist_ok=True)

    loaded = {}
    for sym, (fname, what) in SERIES.items():
        s = read_series(BENCH / fname)
        loaded[sym] = s
        print(f"  {sym:<12} {what[:30]:<32} {len(s):>7,} obs  "
              f"{s[0][0] if s else '-'} .. {s[-1][0] if s else '-'}")

    inventory = []
    for name, a, b in NAMED:
        A, B = date.fromisoformat(a), date.fromisoformat(b)
        per = {}
        for sym, s in loaded.items():
            if not s:
                continue
            if s[0][0] > B:
                per[sym] = {"status": "SERIES_STARTS_AFTER_EPISODE",
                            "seriesFrom": s[0][0].isoformat()}
                continue
            w = worst_in_window(s, A, B)
            per[sym] = ({"status": "MEASURED", **w} if w
                        else {"status": "NO_OBSERVATIONS_IN_WINDOW"})
        measured = [v for v in per.values() if v.get("status") == "MEASURED"]
        inventory.append({
            "episode": name, "window": [a, b],
            "inTrainingData": B >= TRAINING_DATA_STARTS,
            "trainingDataNote": ("examples-v3 begins 2018-01-01; anything earlier is evidence in "
                                 "a benchmark series only and cannot be trained on"),
            "seriesMeasured": len(measured),
            "seriesTooYoung": sum(1 for v in per.values()
                                  if v.get("status") == "SERIES_STARTS_AFTER_EPISODE"),
            "deepestEquityDrawdownPct": min(
                (v["drawdownPct"] for k, v in per.items()
                 if k in ("^GSPC", "^SP500TR") and v.get("status") == "MEASURED"), default=None),
            "perSeries": per,
        })

    sens = {sym: {f"{int(t*100)}%": all_episodes(s, t) for t in THRESHOLDS}
            for sym, s in loaded.items() if s}

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "historical-regimes-v1",
        "purpose": ("which historical regimes this project holds any evidence for, over the full "
                    "benchmark history. Representation inside examples-v3 is a different "
                    "question and lives in regime_coverage.json"),
        "trainingDataStarts": TRAINING_DATA_STARTS.isoformat(),
        "seriesCoverage": {sym: {"observations": len(s),
                                 "from": s[0][0].isoformat() if s else None,
                                 "to": s[-1][0].isoformat() if s else None,
                                 "describes": SERIES[sym][1]}
                           for sym, s in loaded.items()},
        "episodeCountByThreshold": sens,
        "thresholds": [f"{int(t*100)}%" for t in THRESHOLDS],
        "namedEpisodes": inventory,
    }
    out = out_dir / "historical_regimes.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("\nnamed episodes, deepest equity drawdown measured in the window:")
    for e in inventory:
        dd = e["deepestEquityDrawdownPct"]
        tag = "in training data" if e["inTrainingData"] else "benchmark evidence only"
        print(f"  {e['episode'][:44]:<46} {('%.2f%%' % dd) if dd is not None else '    n/a':>9}"
              f"  series {e['seriesMeasured']:>2}  {tag}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
