"""Load the frozen dataset once into arrays, so an experiment costs seconds instead of a quarter hour.

    python tools/research/sweep_cache.py [--dataset DIR] [--out FILE]

Why this exists
---------------
Every experiment in this directory begins by walking nine gzipped JSONL files -- 299 MB, about a
million rows -- parsing each line and assembling a feature matrix. That is twelve to fifteen
minutes before the first number appears, and it is paid again by every run. It is also the reason
the model work has proceeded one pre-registered experiment at a time: a sweep over families,
horizons and label bands at fifteen minutes an arm is a sweep nobody runs.

This writes the parse out once, per market, as float32 arrays: the 44 features, the three forward
returns (`fwd1`, `fwd5`, `fwd20`) the labels are derived from, the decision date, and the symbol.
Loading it back is about a second, so the question stops being "which single experiment can we
afford" and becomes "what does the whole grid say".

**It caches observations, never labels.** The forward returns are stored raw and every label is
derived at experiment time through `make_dataset.label_for`, because the band is one of the things
being swept and a cached label would quietly fix it. The same reason the split is not cached: a
chronological boundary is part of an experiment's design, not of its data.

What is deliberately not here
-----------------------------
No filtering by quality, no imputation, no standardisation, no de-duplication beyond what the
dataset already did. Those are training-fold decisions and they belong on the far side of a split.
NaN stays NaN.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from array import array
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

from shadow_markets import MARKETS  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402
from train_v4_markets import market_of_row  # noqa: E402

DEFAULT_DS = ROOT / ".cache" / "foundation" / "dataset_v4"
DEFAULT_OUT = ROOT / ".cache" / "foundation" / "sweep_cache.npz"
PREFIX = "examples-v4-context"

#: The forward returns kept per row. Labels are derived from these at experiment time.
FORWARDS = ("fwd1", "fwd5", "fwd20")


def build(ds: Path, prefix: str = PREFIX) -> dict:
    """One pass over the dataset, grouped by market."""
    files = sorted(ds.glob(f"{prefix}-*.jsonl.gz"))
    if not files:
        raise SystemExit(f"no {prefix}-*.jsonl.gz in {ds}")
    per = {m: {"x": array("f"), "f": {k: array("f") for k in FORWARDS},
               "dates": [], "symbols": []} for m in MARKETS}
    seen = kept = 0
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                seen += 1
                r = json.loads(line)
                pit = r.get("pit") or {}
                p = pit.get("f")
                if not p:
                    continue
                o = r.get("outcome") or {}
                c = (pit.get("ctx") or {}).get("f") or {}
                row = []
                ok = True
                for k in ALL_FEATURES:
                    v = p.get(k) if k in p else c.get(k)
                    if isinstance(v, str):
                        v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
                    if v is None:
                        row.append(float("nan"))
                        continue
                    try:
                        row.append(float(v))
                    except (TypeError, ValueError):
                        ok = False
                        break
                if not ok:
                    continue
                b = per[market_of_row(r.get("assetType"), r.get("market"))]
                b["x"].extend(row)
                for k in FORWARDS:
                    v = o.get(k)
                    b["f"][k].append(float("nan") if v is None else float(v))
                b["dates"].append(r["asOf"])
                b["symbols"].append(r.get("symbol") or "")
                kept += 1
        print(f"  {f.name}: {kept:,} rows kept of {seen:,} seen")
    out = {}
    for m, b in per.items():
        n = len(b["dates"])
        out[f"{m}/X"] = np.frombuffer(b["x"], dtype=np.float32).reshape(n, len(ALL_FEATURES))
        for k in FORWARDS:
            out[f"{m}/{k}"] = np.frombuffer(b["f"][k], dtype=np.float32)
        out[f"{m}/dates"] = np.asarray(b["dates"])
        out[f"{m}/symbols"] = np.asarray(b["symbols"])
        print(f"  {m:<10} {n:>8,} rows")
    out["features"] = np.asarray(ALL_FEATURES)
    return out


def load(path: Path = DEFAULT_OUT) -> dict:
    """The cache as `{market: {"X","fwd1","fwd5","fwd20","dates","symbols"}}` plus `features`."""
    if not path.exists():
        raise SystemExit(f"no cache at {path}; run tools/research/sweep_cache.py first")
    z = np.load(path, allow_pickle=False)
    per: dict = {"features": list(z["features"])}
    for m in MARKETS:
        if f"{m}/X" not in z:
            continue
        per[m] = {"X": z[f"{m}/X"], "dates": z[f"{m}/dates"], "symbols": z[f"{m}/symbols"],
                  **{k: z[f"{m}/{k}"] for k in FORWARDS}}
    return per


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(DEFAULT_DS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    out = build(Path(a.dataset))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez(a.out, **out)
    size = Path(a.out).stat().st_size / 1048576
    print(f"\nwrote {a.out} ({size:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
