"""Move the staged benchmark and macro series out of the cache and into the project's data layer.

    python tools/foundation/benchmarks_persist.py

The series were acquired into `.cache/acquire/`, which is gitignored and disposable -- a cache is
not a durable copy. `data/foundation/macro/` is how this project already keeps a published series
it did not generate: a file per series plus one manifest carrying the row count, the range and a
checksum. These follow that, gzipped where the plain text would be large enough to bloat the
repository.

No `Asset` row is created for any of them. An index level is not a tradable instrument and giving
it one would change what `PriceSnapshot` means -- every ranking, peer median and relative-strength
figure in the project is computed over the rows in that table. The series live beside the macro
files, where a consumer reads them as what they are.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STAGE = ROOT / ".cache" / "acquire"
OUT = ROOT / "data" / "foundation" / "benchmarks"
# Over this many rows the file is gzipped; below it, plain CSV stays readable in a diff.
GZIP_OVER = 3000


def write_series(name: str, header: list[str], rows: list[list], meta: dict) -> dict:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    text = buf.getvalue().encode()
    if len(rows) > GZIP_OVER:
        blob, fname = gzip.compress(text, 9), f"{name}.csv.gz"
    else:
        blob, fname = text, f"{name}.csv"
    (OUT / fname).write_bytes(blob)
    return {**meta, "file": fname, "observations": len(rows),
            "first": rows[0][0] if rows else None, "last": rows[-1][0] if rows else None,
            "bytesOnDisk": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": ("index levels and macro rates, kept out of PriceSnapshot on purpose: "
                         "they are not tradable instruments and an Asset row would change what "
                         "that table means"),
                "series": {}}

    report = json.loads((STAGE / "benchmarks" / "_report.json").read_text("utf-8"))
    for sym, r in report.items():
        if not r.get("acquired"):
            continue
        f = STAGE / "benchmarks" / f"{sym.replace('^', '').replace('=', '_')}.json"
        bars = json.loads(f.read_text("utf-8"))["bars"]
        rows = [[b["d"], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in bars]
        manifest["series"][sym] = write_series(
            sym.replace("^", "").replace("=", "_"),
            ["date", "open", "high", "low", "close", "volume"], rows,
            {"name": r["name"], "basis": r["basis"], "source": r["source"],
             "currency": r.get("currency"), "instrumentType": r.get("instrumentType"),
             "rejectedBySource": r.get("rejected", {})})
        print(f"  {sym:10} {len(rows):6} rows -> {manifest['series'][sym]['file']}")

    fred = json.loads((STAGE / "fred" / "_report.json").read_text("utf-8"))
    for sid, r in fred.items():
        if not r.get("acquired"):
            continue
        obs = json.loads((STAGE / "fred" / f"{sid}.json").read_text("utf-8"))["observations"]
        rows = [[o["d"], o["v"]] for o in obs]
        manifest["series"][sid] = write_series(
            sid, ["date", "value"], rows,
            {"name": r["title"], "basis": "published macro observation",
             "source": "FRED", "sourceUrl": r["source"]})
        print(f"  {sid:10} {len(rows):6} rows -> {manifest['series'][sid]['file']}")

    for label, fname, src in (("BTC-USD.coinbase", "btc_pre_2018.json", "Coinbase Exchange API"),
                              ("BTC-USD.bitstamp", "btc_pre_2015_bitstamp.json", "Bitstamp API v2")):
        p = STAGE / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text("utf-8"))
        rows = [[b["d"], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in d["bars"]]
        manifest["series"][label] = write_series(
            label.replace(".", "_"), ["date", "open", "high", "low", "close", "volume"], rows,
            {"name": "Bitcoin daily, venue history before the stored series",
             "basis": d["basis"], "source": src,
             "note": "kept per venue; two venues' prints of one day are two observations"})
        print(f"  {label:18} {len(rows):6} rows -> {manifest['series'][label]['file']}")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(v["observations"] for v in manifest["series"].values())
    size = sum(v["bytesOnDisk"] for v in manifest["series"].values())
    print(f"\npersisted {len(manifest['series'])} series, {total:,} observations, "
          f"{size/1e6:.1f} MB on disk")


if __name__ == "__main__":
    main()
