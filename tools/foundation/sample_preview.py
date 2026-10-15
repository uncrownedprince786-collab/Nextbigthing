"""A small, traceable, deliberately unflattering sample of the training corpus.

    python tools/foundation/sample_preview.py [--per-bucket N] [--dataset DIR]

Writes `data/foundation/dataset/sample_preview.jsonl` and a manifest. Reads the durable dataset
copy; touches no database.

**What a preview is for.** Someone has to be able to open a handful of rows and see what the model
will actually be trained on -- including the rows nobody would choose. So the sample is drawn by
rule, from named buckets, and the buckets are picked to include the failures:

  * every asset class and every market
  * every label: UP, FLAT and DOWN
  * the early years and the late ones
  * **adverse outcomes**: rows whose maximum adverse excursion is worse than -15%
  * **failed-looking rows**: labelled UP yet with a deep drawdown on the way, and the reverse
  * **inconclusive rows**: FLAT, where twenty sessions resolved nothing
  * **quality-flagged rows**: an unadjusted action, a non-daily window or a basis break in range

Deterministic: buckets are filled in file order with a fixed cap, so the same dataset yields the
same preview. Nothing is generated; every row is a real stored example, carried with its
instrument, date, feature block, outcome and the data-quality flags that apply to it.
"""

from __future__ import annotations

import glob
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_DS = Path(r"C:\Users\NEW TECH\nbt-private\dataset"
                  r"\examples-v3-2026-10-15-run38735767762\dataset")
OUT_DIR = ROOT / "data" / "foundation" / "dataset"

PER_BUCKET = 3
ADVERSE_MAE = -15.0
DEEP_DRAWDOWN = -10.0


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def buckets_for(r: dict) -> list[str]:
    """Every bucket this row belongs to. A row can serve more than one."""
    o = r.get("outcome") or {}
    q = r.get("dataQuality") or {}
    out = [f"class:{r['assetType']}", f"market:{r.get('market')}",
           f"label:{o.get('label20')}", f"year:{r['asOf'][:4]}"]
    mae, fwd = o.get("mae"), o.get("fwd20")
    if mae is not None and mae <= ADVERSE_MAE:
        out.append("adverse:mae-worse-than-15pct")
    if o.get("label20") == "UP" and mae is not None and mae <= DEEP_DRAWDOWN:
        out.append("failed-looking:up-after-a-deep-drawdown")
    if o.get("label20") == "DOWN" and o.get("mfe") is not None and o["mfe"] >= -DEEP_DRAWDOWN:
        out.append("failed-looking:down-after-a-strong-rally")
    if o.get("label20") == "FLAT":
        out.append("inconclusive:twenty-sessions-resolved-nothing")
    for k, v in q.items():
        if v:
            out.append(f"quality-flag:{k}")
    if not (r.get("coverage") or {}).get("setup"):
        out.append("no-replayed-setup")
    return out


def main() -> int:
    ds = Path(arg("--dataset", DEFAULT_DS))
    cap = int(arg("--per-bucket", PER_BUCKET))
    files = sorted(glob.glob(str(ds / "examples-v3-*.jsonl.gz")))
    if not files:
        print(f"no dataset at {ds}")
        return 1

    chosen: dict[str, list[dict]] = {}
    seen: set[tuple] = set()
    scanned = 0
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                scanned += 1
                for b in buckets_for(r):
                    if b.endswith("None"):
                        continue
                    slot = chosen.setdefault(b, [])
                    if len(slot) >= cap:
                        continue
                    key = (r["symbol"], r["asOf"])
                    if key in seen and len(slot) > 0:
                        continue
                    slot.append(r)
                    seen.add(key)

    rows = []
    for bucket, items in sorted(chosen.items()):
        for r in items:
            o = r.get("outcome") or {}
            p = r.get("pit") or {}
            rows.append({
                "bucket": bucket,
                "symbol": r["symbol"], "asOf": r["asOf"],
                "assetType": r["assetType"], "market": r.get("market"),
                "label20": o.get("label20"),
                "outcome": {k: o.get(k) for k in
                            ("fwd1", "fwd5", "fwd20", "mfe", "mae", "mature20", "baseClose")},
                "features": {"sessionsAvailable": p.get("n"), "spanDays": p.get("spanDays"),
                             "f": p.get("f")},
                "dataQuality": r.get("dataQuality"),
                "coverage": r.get("coverage"),
                "labelRule": ("label20 = UP when fwd20 >= +2.0%, DOWN when <= -2.0%, else FLAT; "
                              "fwd20 = close[t+20]/close[t] - 1 over stored sessions"),
                "provenance": {"dataset": "examples-v3", "assembledBy": "data-assemble.yml "
                               "run 38735767762", "featuresFrom": "data-pit-features.yml "
                               "run 38733216507",
                               "inputsAreStrictlyBefore": "the session being described"},
            })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "sample_preview.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "sample-preview-v1",
        "dataset": "examples-v3",
        "rowsScanned": scanned,
        "buckets": len(chosen),
        "previewRows": len(rows),
        "perBucketCap": cap,
        "bucketCounts": {k: len(v) for k, v in sorted(chosen.items())},
        "selection": ("deterministic: buckets filled in file order to a fixed cap, so the same "
                      "dataset yields the same preview"),
        "deliberatelyIncludes": ["adverse outcomes", "failed-looking rows", "inconclusive FLAT "
                                 "rows", "quality-flagged rows", "rows with no replayed setup"],
        "notGenerated": "every row is a stored example; nothing here is synthetic",
        "file": out.name, "bytes": out.stat().st_size, "sha256": digest,
    }
    (OUT_DIR / "sample_preview_manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"scanned {scanned:,} rows")
    print(f"buckets {len(chosen)}  preview rows {len(rows)}")
    print(f"wrote {out} ({out.stat().st_size:,} bytes, sha256 {digest[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
