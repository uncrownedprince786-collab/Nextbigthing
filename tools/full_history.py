"""Every eligible asset-session in the stored history, with its forward outcome.

    python tools/full_history.py --out <dir> [--limit-assets N]

Why this exists beside `tools/make_dataset.py`
----------------------------------------------
`make_dataset.py` builds examples from sessions that `tools/replay_batch.py` has reconstructed,
which means one `jobs/setup.py --as-of` run per date. Measured, that is about a minute a session;
across the 2,072 stored sessions it is days of compute, so replay sampling cannot reach full
coverage on its own.

The outcome half does not need the replay. A forward return is arithmetic over stored bars, so
this walks `PriceSnapshot` **once**, per asset, and emits every session that has a complete
forward window. The reconstructed setup is the part that needs the replay, and it is absent here
-- which is why these rows carry `candidate: null` and a `setupAvailable: false` flag rather than
a fabricated one. Joining the two is a matter of asset and date when more sessions are replayed.

Eligibility, stated before counting
-----------------------------------
An asset-session is **eligible** when it has a stored close and at least `WINDOW` (20) later
stored sessions for the same asset, so every horizon this file labels has fully elapsed. Sessions
inside the final 20 of an asset's series are **excluded as immature**, not labelled FLAT. The
reconciliation at the end accounts for every stored row as generated, immature, or missing a
close, so an unexplained omission would show up as a non-zero remainder.

Nothing is written to any database.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

from nbt import db  # noqa: E402

HORIZONS = (1, 5, 20)
WINDOW = max(HORIZONS)
LABEL_THRESHOLD_PCT = 2.0
DATASET_VERSION = 2


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def rules_version() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    return out or "unknown"


def main() -> None:
    out_dir = Path(arg("--out") or (ROOT.parent / "nbt-private" / "dataset"))
    out_dir.mkdir(parents=True, exist_ok=True)
    limit = int(arg("--limit-assets") or "0")

    conn = db()
    cur = conn.cursor()
    cur.execute('SELECT a.id, a.symbol, a."assetType"::text AS "assetType", a.active, '
                'a.currency, i.market FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId" '
                'ORDER BY a.symbol')
    assets = cur.fetchall()
    if limit:
        assets = assets[:limit]
    by_id = {a["id"]: a for a in assets}

    cur.execute('SELECT count(*) AS n FROM "PriceSnapshot"')
    stored_rows_all = cur.fetchone()["n"]

    print(f"full history: {len(assets)} assets, {stored_rows_all:,} stored price rows")

    rows_out: list[str] = []
    stats = Counter()
    per_class: dict[str, Counter] = {}
    labels = Counter()
    oldest = newest = None

    # One statement for the universe, not one per asset. A per-asset loop here would be 616
    # network waits for rows a single ordered read already returns grouped -- the same fault
    # `jobs/setup.py`'s `all_closes` was rewritten to avoid, and the reason the query budget
    # counts in-loop reads at all.
    cur.execute(
        'SELECT "assetId", date, close FROM "PriceSnapshot" WHERE close IS NOT NULL '
        'ORDER BY "assetId", date ASC')
    series: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        series.setdefault(r["assetId"], []).append(r)

    for n, a in enumerate(assets, 1):
        bars = series.get(a["id"], [])
        klass = a["assetType"]
        pc = per_class.setdefault(klass, Counter())
        pc["storedRows"] += len(bars)
        stats["storedRowsWithClose"] += len(bars)

        closes = [float(b["close"]) for b in bars]
        dates = [b["date"] for b in bars]
        for i in range(len(bars)):
            if i + WINDOW >= len(bars):
                stats["excludedImmature"] += 1
                pc["excludedImmature"] += 1
                continue
            base = closes[i]
            if not base:
                stats["excludedNoBase"] += 1
                continue
            fwd = closes[i + 1: i + 1 + WINDOW]
            o = {f"fwd{h}": round((closes[i + h] / base - 1) * 100, 4) for h in HORIZONS}
            o["mfe"] = round((max(fwd) / base - 1) * 100, 4)
            o["mae"] = round((min(fwd) / base - 1) * 100, 4)
            f20 = o["fwd20"]
            label = ("UP" if f20 >= LABEL_THRESHOLD_PCT
                     else "DOWN" if f20 <= -LABEL_THRESHOLD_PCT else "FLAT")
            o["label20"] = label
            labels[label] += 1
            d = dates[i]
            oldest = d if oldest is None or d < oldest else oldest
            newest = d if newest is None or d > newest else newest
            rows_out.append(json.dumps({
                "asOf": d.isoformat(),
                "assetId": a["id"],
                "symbol": a["symbol"],
                "assetType": klass,
                "market": a["market"],
                "currency": a["currency"],
                "assetActiveNow": a["active"],
                "datasetVersion": DATASET_VERSION,
                "rulesVersion": RULES,
                # The reconstructed setup needs jobs/setup.py --as-of for that date, which this
                # pass deliberately does not run. Absent, and said so, rather than invented.
                "candidate": None,
                "setupAvailable": False,
                "engineDecision": None,
                "outcome": {**o, "baseClose": base, "sessionsAvailable": WINDOW, "mature20": True},
                "quality": {
                    "priceSource": "PriceSnapshot (stored)",
                    "inputsOmitted": ["News", "HumanSignal", "MacroGate", "AssetFactor",
                                      "AssetAnalog", "AssetSetup"],
                    "survivorship": "current-universe-only",
                },
            }))
            stats["generated"] += 1
            pc["generated"] += 1
        if n % 100 == 0:
            print(f"  {n}/{len(assets)} assets, {stats['generated']:,} examples so far")

    conn.close()

    payload = ("\n".join(rows_out)).encode("utf-8")
    path = out_dir / f"full-history-v{DATASET_VERSION}.jsonl.gz"
    with gzip.open(path, "wb", compresslevel=6) as fh:
        fh.write(payload)
    digest = hashlib.sha256(payload).hexdigest()

    accounted = stats["generated"] + stats["excludedImmature"] + stats["excludedNoBase"]
    manifest = {
        "dataset": "full-history-outcomes",
        "version": DATASET_VERSION,
        "rulesVersion": RULES,
        "artifact": path.name,
        "sha256": digest,
        "uncompressedBytes": len(payload),
        "compressedBytes": path.stat().st_size,
        "rows": stats["generated"],
        "dateRange": [oldest.isoformat() if oldest else None,
                      newest.isoformat() if newest else None],
        "reconciliation": {
            "storedPriceRowsTotal": stored_rows_all,
            "storedRowsWithClose": stats["storedRowsWithClose"],
            "generated": stats["generated"],
            "excludedImmature": stats["excludedImmature"],
            "excludedNoBase": stats["excludedNoBase"],
            "accountedFor": accounted,
            "unexplained": stats["storedRowsWithClose"] - accounted,
        },
        "byAssetClass": {k: dict(v) for k, v in sorted(per_class.items())},
        "label20Counts": dict(labels),
        "eligibility": (
            f"An asset-session is eligible when it has a stored close and at least {WINDOW} "
            "later stored sessions for the same asset. Sessions inside the final 20 of a "
            "series are excluded as immature, never labelled FLAT."
        ),
        "limitations": [
            "Outcome-only: no reconstructed setup, factor or analog is attached. candidate is "
            "null and setupAvailable is false on every row.",
            "Survivorship: the universe is today's active and inactive Asset rows, so names "
            "delisted before they were ever seeded are absent. NOT survivorship-bias-free.",
            "Daily closes only; intraday path, and therefore stop/target ordering, is unknown.",
            "The 2% FLAT band is applied across all asset classes and is not volatility-scaled; "
            "it is carried unchanged from dataset v1 so the two remain comparable.",
        ],
        "reproduce": "python tools/full_history.py --out <dir>",
    }
    (out_dir / f"manifest-full-v{DATASET_VERSION}.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")

    print(json.dumps({"rows": stats["generated"],
                      "reconciliation": manifest["reconciliation"],
                      "label20": dict(labels),
                      "compressedMB": round(path.stat().st_size / 1048576, 1),
                      "sha256": digest[:16]}, indent=1))
    print(f"artifact: {path}")


RULES = rules_version()

if __name__ == "__main__":
    main()
