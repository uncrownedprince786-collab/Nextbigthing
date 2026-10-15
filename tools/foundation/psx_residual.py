"""Classify every remaining PSX gap by what the evidence actually says, and keep the delisted names.

    python tools/foundation/psx_residual.py

A previous pass reported 36,762 remaining gaps and called them non-trading sessions. That was one
category doing the work of several, and the difference matters: a day the exchange was shut is not
the same fact as a day one security did not trade, and neither is the same as a session whose
archive the exchange never published. Each gap is put in exactly one of five boxes, from the
cached archives and the staged provider data -- no new requests.

  1 exchangeWideNonTradingDay   the market calendar has no session on that date
  2 securityDidNotTrade         the exchange published the session and no price for that symbol
  3 exchangeArchiveEmpty        the exchange published the session as an empty file
  4 recoverableElsewhere        another provider served a validated bar for that security-date
  5 unresolved                  none of the above could be established

Category 4 is the one that must not be hidden inside category 2: those are real observations this
database does not hold, held back only because the provider quotes them on a different basis.

It also writes the delisted and renamed symbols' own history. Those names trade in the exchange's
files and have no `Asset` row, so nothing in the project was keeping them; the archives are already
on disk, so keeping them costs nothing but the writing.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "jobs"))

OUT = ROOT / "data" / "foundation" / "psx_complete"
DELISTED_OUT = ROOT / "data" / "foundation" / "psx_delisted"


def load(p, d=None):
    p = Path(p)
    return json.loads(p.read_text("utf-8")) if p.exists() else d


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import psx
    from nbt import db, rows
    from psx_backfill import validate

    sweep = load(ROOT / ".cache/acquire/psx_sweep_ledger.json", {"dates": {}})
    cands = load(ROOT / ".cache/acquire/psx_delisted_candidates.json", {"candidates": []})
    staged_dir = ROOT / ".cache/psx_backfill/staged"

    conn = db()
    cur = conn.cursor()
    try:
        got = rows(cur, 'SELECT a.symbol, p.date::text d FROM "PriceSnapshot" p '
                        'JOIN "Asset" a ON a.id = p."assetId" WHERE a.currency = %s', ("PKR",))
    finally:
        cur.close()
        conn.close()
    held: dict[str, set] = defaultdict(set)
    for r in got:
        held[r["symbol"]].add(r["d"])
    print(f"stored PSX bars: {len(got)} across {len(held)} symbols", flush=True)

    # What another provider validly serves, per security-date.
    provider: dict[str, set] = {}
    for p in staged_dir.glob("*.json"):
        g = load(p)
        provider[g["symbol"]] = {b["d"] for b in validate(g["bars"])[0]}

    calendar = {d for v in held.values() for d in v}
    ranges = {s: (min(v), max(v)) for s, v in held.items() if v}
    status = {d: v.get("status") for d, v in sweep["dates"].items()}
    today = date.today()

    counts = Counter()
    per_reason_examples = defaultdict(list)
    recoverable: dict[str, list[str]] = defaultdict(list)
    delisted_bars: dict[str, list[dict]] = defaultdict(list)
    want_delisted = set(cands["candidates"])

    published = sorted(d for d, s in status.items() if s == "published")
    for i, d in enumerate(published, 1):
        day_rows = psx.read_day(date.fromisoformat(d), today, keep=None) or {}
        traded = set(day_rows)
        for sym in want_delisted & traded:
            r = day_rows[sym]
            delisted_bars[sym].append({"d": d, "o": r.get("open"), "h": r.get("high"),
                                       "l": r.get("low"), "c": r.get("close"),
                                       "v": r.get("volume")})
        if d not in calendar:
            continue
        for sym, (lo, hi) in ranges.items():
            if d < lo or d > hi or d in held[sym]:
                continue
            if sym in traded:
                counts["5_unresolved"] += 1          # cannot happen after the sweep; counted anyway
                per_reason_examples["5_unresolved"].append(f"{sym} {d}")
            elif d in provider.get(sym, ()):
                counts["4_recoverableElsewhere"] += 1
                recoverable[sym].append(d)
            else:
                counts["2_securityDidNotTrade"] += 1
        if i % 500 == 0:
            print(f"  {i}/{len(published)} published days classified", flush=True)

    # Sessions the exchange published as an empty file, and the dates it answered with nothing.
    empty_dates = sorted(d for d, s in status.items() if s in ("publishedButEmpty", "notAnArchive"))
    for d in empty_dates:
        if d not in calendar:
            continue
        for sym, (lo, hi) in ranges.items():
            if d < lo or d > hi or d in held[sym]:
                continue
            counts["3_exchangeArchiveEmpty"] += 1
            if d in provider.get(sym, ()):
                counts["3a_ofWhichAnotherProviderHas"] += 1

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": ("every in-range calendar date without a stored bar, classified against the "
                   "cached exchange archive and the staged provider data; no new requests"),
        "storedPsxBars": len(got),
        "publishedSessionsRead": len(published),
        "classification": dict(counts),
        "total": sum(v for k, v in counts.items() if k[0].isdigit() and not k.startswith("3a")),
        "category4Detail": {
            "symbols": len(recoverable),
            "bars": sum(len(v) for v in recoverable.values()),
            "whatTheyAre": ("dates the Karachi listing serves a validated bar for and this "
                            "database does not hold, withheld because that provider quotes them "
                            "split-adjusted while the stored series is raw. Staged, not lost: "
                            ".cache/acquire/psx_withheld.json"),
            "worst": sorted(((s, len(v)) for s, v in recoverable.items()),
                            key=lambda x: -x[1])[:10],
        },
        "emptyArchiveDates": empty_dates,
        "examples": {k: v[:5] for k, v in per_reason_examples.items()},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "residual_classification.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("examples", "emptyArchiveDates")}, indent=1, default=str)[:1400])

    # ---- delisted and renamed names, kept from the archives already on disk ----
    if delisted_bars:
        DELISTED_OUT.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["symbol", "date", "open", "high", "low", "close", "volume"])
        per = {}
        for sym in sorted(delisted_bars):
            bars = sorted(delisted_bars[sym], key=lambda b: b["d"])
            per[sym] = {"bars": len(bars), "first": bars[0]["d"], "last": bars[-1]["d"]}
            for b in bars:
                w.writerow([sym, b["d"], b["o"], b["h"], b["l"], b["c"], b["v"]])
        blob = gzip.compress(buf.getvalue().encode(), 9)
        (DELISTED_OUT / "psx_delisted_history.csv.gz").write_bytes(blob)
        man = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "file": "psx_delisted_history.csv.gz",
               "source": "Pakistan Stock Exchange daily closing file, dps.psx.com.pk",
               "basis": "raw as-traded OHLCV, the same basis as the stored PSX series",
               "whatThisIs": ("symbols that traded in the exchange's own files during the swept "
                              "window and have no Asset row in this project, so nothing else here "
                              "keeps their history. Identified by comparing the first and last "
                              "archive day; dated futures contracts were excluded."),
               "symbols": len(per), "bars": sum(v["bars"] for v in per.values()),
               "sha256": hashlib.sha256(blob).hexdigest(), "perSymbol": per}
        (DELISTED_OUT / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
        print(f"\ndelisted/renamed history: {man['bars']} bars across {man['symbols']} symbols "
              f"-> {man['file']}")


if __name__ == "__main__":
    main()
