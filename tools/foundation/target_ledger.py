"""One row per frozen target: what its history was required to be, and what it actually is.

    python tools/foundation/target_ledger.py

The trap this exists to avoid
-----------------------------
A coverage figure computed from the dates already in the database cannot find missing older
history: whatever is there defines the range, so the range is always full. Every row here carries
a **required floor that was decided before the data was looked at**, and the gap between that
floor and the first real observation is reported as a number, not implied by a percentage.

Two different floors are in play and they are not interchangeable:

  * **2018-01-01** -- the frozen brief's common cutoff for PSX instruments and the KSE-100.
  * **2019-01-02** -- the universe's own start for the registry's other price assets, a project
    decision recorded in brain.md, not a limit of the sources. Yahoo would serve earlier history
    for the US names; nobody has asked it to. That is a scope choice and it is labelled as one
    rather than counted as a gap.

Per-asset detail goes to the manifest; the console prints the rollup.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "foundation" / "acquisition"
F = ROOT / "data" / "foundation"

PSX_FLOOR = "2018-01-01"       # the frozen brief's cutoff for PSX instruments
REGISTRY_FLOOR = "2019-01-02"  # the universe's own start, a project decision


def load(p, d=None):
    p = Path(p)
    return json.loads(p.read_text("utf-8")) if p.exists() else d


def read_csv_any(path: Path):
    raw = path.read_bytes()
    text = gzip.decompress(raw).decode() if path.suffix == ".gz" else raw.decode("utf-8-sig")
    r = csv.reader(io.StringIO(text))
    header = next(r)
    return header, [row for row in r if row], hashlib.sha256(raw).hexdigest()


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT / "jobs"))
    from nbt import db, rows as q

    ledger = []
    conn = db()
    cur = conn.cursor()
    try:
        per_asset = q(cur, '''
            SELECT a.symbol, a."assetType"::text AS t, a.currency,
                   count(p.date) bars, count(DISTINCT p.date) distinct_dates,
                   min(p.date)::text lo, max(p.date)::text hi,
                   count(DISTINCT p.source) sources
            FROM "Asset" a LEFT JOIN "PriceSnapshot" p ON p."assetId" = a.id
            GROUP BY 1,2,3 ORDER BY 2,1''')
        size = q(cur, "SELECT pg_size_pretty(pg_database_size(current_database())) s")[0]["s"]
        total = q(cur, 'SELECT count(*) n FROM "PriceSnapshot"')[0]["n"]
        tables = q(cur, 'SELECT count(*) n FROM pg_stat_user_tables WHERE schemaname=%s',
                   ("public",))[0]["n"]
    finally:
        cur.close()
        conn.close()

    # ---- registry price assets, grouped, with the late-start test against the declared floor ----
    groups: dict[str, list] = defaultdict(list)
    for a in per_asset:
        k = a["t"] if a["t"] != "stock" else ("stock/PKR" if a["currency"] == "PKR" else "stock/USD")
        groups[k].append(a)
    for k, members in sorted(groups.items()):
        floor = PSX_FLOOR if k == "stock/PKR" else REGISTRY_FLOOR
        withdata = [m for m in members if m["bars"]]
        late = [m for m in withdata if m["lo"] > floor]
        dupes = sum(m["bars"] - m["distinct_dates"] for m in withdata)
        ledger.append({
            "target": f"registry: {k}", "identity": f"{len(members)} assets in the Asset registry",
            "requiredFloor": floor,
            "floorBasis": ("frozen brief cutoff for PSX instruments" if k == "stock/PKR"
                           else "universe start recorded in brain.md; the sources would serve "
                                "earlier history and have not been asked to - a scope choice"),
            "source": ("PSX closing file + Yahoo Karachi listing" if k == "stock/PKR"
                       else "Coinbase/Kraken" if k == "crypto" else "Yahoo Finance"),
            "assets": len(members), "assetsWithData": len(withdata),
            "assetsWithNoData": len(members) - len(withdata),
            "observations": sum(m["bars"] for m in withdata),
            "distinctDatesAcrossAssets": len({m["lo"] for m in withdata}) and None,
            "duplicateRows": dupes,
            "earliest": min((m["lo"] for m in withdata), default=None),
            "latest": max((m["hi"] for m in withdata), default=None),
            "assetsStartingAfterTheFloor": len(late),
            "assetsStartingAfterTheFloorExamples": sorted(
                ({"symbol": m["symbol"], "first": m["lo"]} for m in late),
                key=lambda x: x["first"], reverse=True)[:5],
            "lateStartMeaning": ("a listing that began after the floor, or a venue that listed it "
                                 "later; not a missing record unless the instrument traded then"),
            "priceBasis": ("raw as-traded for the exchange rows, split-adjusted for the Karachi "
                           "listing rows - kept apart by source" if k == "stock/PKR"
                           else "provider default"),
            "durableLocation": "primary store: PriceSnapshot",
            "consumerUsable": True,
            "rights": ("PSX redistribution unresolved (recovery-manifest psx-redistribution-"
                       "licence); collection and private use unaffected" if k == "stock/PKR"
                       else "provider terms permit this use"),
            "status": "complete against the declared floor" if not late else "complete at the "
                      "market level; some listings start later than the floor",
        })

    # ---- durable files ----
    for d, label in ((F / "benchmarks", "benchmark/macro file"), (F / "sbp", "SBP file"),
                     (F / "psx_index", "KSE-100 file"), (F / "psx_delisted", "PSX delisted file")):
        man = load(d / "manifest.json")
        if not man:
            continue
        series = man.get("series") if isinstance(man.get("series"), dict) else {
            man.get("series") or d.name: man}
        for key, claim in series.items():
            fn = claim.get("file")
            if not fn or not (d / fn).exists():
                continue
            header, rows_, sha = read_csv_any(d / fn)
            di = header.index("date") if "date" in header else 0
            dates = [r[di] for r in rows_]
            v = claim.get("validation") or {}
            ledger.append({
                "target": key, "identity": claim.get("name") or claim.get("title") or key,
                "kind": label,
                "requiredFloor": (PSX_FLOOR if d.name in ("psx_index", "psx_delisted")
                                  else "earliest reliable history the source serves"),
                "source": claim.get("source") or claim.get("sourceUrl") or man.get("source"),
                "observations": len(rows_), "distinctDates": len(set(dates)),
                "duplicateRows": len(dates) - len(set(dates)) if "symbol" not in header else None,
                "earliest": min(dates), "latest": max(dates),
                "fields": header,
                "fieldsNotProvided": claim.get("fieldsNotProvided") or [],
                "priceBasis": claim.get("basis"),
                "durableLocation": str((d / fn).relative_to(ROOT)),
                "sha256": sha, "sha256MatchesManifest": sha == claim.get("sha256"),
                "consumerUsable": True,
                "rights": claim.get("licensing") or man.get("licensing") or "see manifest",
                "status": claim.get("coverageAgainstFrozenTarget") or "complete",
                "missingAgainstFloor": claim.get("missingAgainstFrozenTarget"),
                "dataQuality": man.get("dataQuality") if d.name == "psx_delisted" else None,
            })

    # ---- quarantined candidate ----
    odp = load(F / "psx_index" / "kse100_opendata_candidate.json")
    if odp:
        ledger.append({
            "target": "KSE-100 pre-2021 candidate", "identity": "KSE-100 index, Open Data Pakistan",
            "kind": "quarantined candidate", "requiredFloor": PSX_FLOOR,
            "source": odp["sourceUrl"],
            "observations": odp["observations"], "distinctDates": odp["distinctDates"],
            "duplicateRows": odp["rejected"].get("duplicateDate", 0),
            "rejectedRows": odp["rejected"],
            "earliest": odp["first"], "latest": odp["last"],
            "fields": odp["fields"], "fieldsNotProvided": [],
            "priceBasis": "index level with real high and low",
            "durableLocation": ".cache/acquire/opendata/kse100_opendata.csv (private; also in the "
                               "PC backup). Deliberately not committed.",
            "sha256": odp["sha256Raw"],
            "consumerUsable": False,
            "rights": "No License Provided on the resource page - reuse rights unestablished",
            "status": "QUARANTINED - acquired, not cleared",
            "overlapWithExchangeEndpoint": odp["overlappingSessionsWithPsxEndpoint"],
        })

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "floors": {"psxInstrumentsAndIndex": PSX_FLOOR, "otherRegistryPriceAssets": REGISTRY_FLOOR,
                   "note": ("the second is the universe's own start, a project decision; the "
                            "sources would serve earlier history for those names")},
        "database": {"size": size, "priceSnapshotRows": total, "tables": tables},
        "targets": len(ledger),
        "ledger": ledger,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "target_ledger.json").write_text(json.dumps(report, indent=1, default=str),
                                            encoding="utf-8")
    print(f"database: {size}, {total} rows, {tables} tables")
    print(f"targets in ledger: {len(ledger)}\n")
    for r in ledger:
        print(f"  {str(r['target'])[:30]:30} floor={str(r['requiredFloor'])[:12]:12} "
              f"{str(r.get('earliest'))[:10]:10} .. {str(r.get('latest'))[:10]:10} "
              f"obs={str(r.get('observations')):>7} {str(r.get('status'))[:34]}")


if __name__ == "__main__":
    main()
