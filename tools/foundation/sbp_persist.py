"""Turn the EasyData downloads into durable project files, with a manifest that can be checked.

    python tools/foundation/sbp_persist.py

`data/foundation/macro/` is where this project keeps a published series it did not generate: a
plain CSV per series and one manifest carrying the row count, the range and a checksum. These two
follow that convention rather than inventing a second one.

The policy rate is 39 effective-dated observations and goes in as plain CSV. KIBOR is 93,300
observations across 18 series and would be about 10 MB of text, so it is written gzipped -- the
same choice `tools/foundation/pit_features.py` makes for its own output, and small enough that the
repository stays the durable copy rather than the cache.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / ".cache" / "acquire" / "sbp"
OUT = ROOT / "data" / "foundation" / "sbp"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def iso(d: str) -> str | None:
    """`28-Apr-2026` to `2026-04-28`, or None when the portal wrote something else."""
    m = re.match(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})$", (d or "").strip())
    if not m:
        return None
    mon = MONTHS.get(m.group(2).title())
    return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}" if mon else None


def read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        return header, [row for row in r if len(row) >= 5]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": "State Bank of Pakistan EasyData portal (easydata.sbp.org.pk)",
                "retrievedBy": "tools/foundation/sbp_easydata.py",
                "series": {}}

    # ---- policy rate: Dataset, Series Key, Series, Observation Date, Value, Unit, Status, Comment
    p = RAW / "TS_GP_IR_SIRPR_AH_SBPOL0030.raw"
    if p.exists():
        _, rows = read_rows(p)
        out, bad = [], 0
        for r in rows:
            d = iso(r[3])
            if d is None:
                bad += 1
                continue
            out.append({"date": d, "value": float(r[4]), "unit": r[5], "status": r[6]})
        out.sort(key=lambda x: x["date"])
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["date", "policy_rate_percent", "unit", "status"])
        for o in out:
            w.writerow([o["date"], o["value"], o["unit"], o["status"]])
        blob = buf.getvalue().encode()
        (OUT / "sbp_policy_rate.csv").write_bytes(blob)
        manifest["series"]["SBP_POLICY_RATE"] = {
            "file": "sbp_policy_rate.csv", "title": "SBP Policy (Target) Rate",
            "seriesKey": "TS_GP_IR_SIRPR_AH.SBPOL0030",
            "basis": "policy rate per annum, effective-dated; not an interbank rate",
            "frequency": "irregular - one observation per policy decision that changed the rate",
            "observations": len(out), "unparseableDates": bad,
            "first": out[0]["date"], "last": out[-1]["date"],
            "sha256": sha256_bytes(blob)}
        print(f"  policy rate: {len(out)} observations {out[0]['date']} .. {out[-1]['date']}")

    # ---- KIBOR: Dataset Name, Observation Date, Series Key, Series Display Name, Value, Unit, ...
    k = RAW / "TS_GP_BAM_SIRKIBOR_D.raw"
    if k.exists():
        _, rows = read_rows(k)
        out, bad = [], 0
        names: dict[str, str] = {}
        for r in rows:
            d = iso(r[1])
            if d is None:
                bad += 1
                continue
            key = r[2]
            names.setdefault(key, r[3])
            try:
                v = float(r[4])
            except ValueError:
                bad += 1
                continue
            out.append((d, key, v, r[5]))
        out.sort()
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["date", "series_key", "rate_percent", "unit"])
        for d, key, v, u in out:
            w.writerow([d, key, v, u])
        blob = gzip.compress(buf.getvalue().encode(), 9)
        (OUT / "sbp_kibor.csv.gz").write_bytes(blob)
        per = {}
        for d, key, _v, _u in out:
            e = per.setdefault(key, {"n": 0, "first": d, "last": d})
            e["n"] += 1
            e["first"] = min(e["first"], d)
            e["last"] = max(e["last"], d)
        manifest["series"]["KIBOR"] = {
            "file": "sbp_kibor.csv.gz", "title": "Structure of Interest Rates: KIBORs and KIBIDs",
            "datasetKey": "TS_GP_BAM_SIRKIBOR_D",
            "basis": "interbank bid and offer rates by tenor; not the policy rate",
            "frequency": "daily, business days",
            "observations": len(out), "unparseableRows": bad,
            "seriesCount": len(per),
            "first": out[0][0], "last": out[-1][0],
            "sha256": sha256_bytes(blob),
            "perSeries": {key: {**v, "name": names.get(key, "")} for key, v in sorted(per.items())}}
        print(f"  kibor: {len(out)} observations across {len(per)} series "
              f"{out[0][0]} .. {out[-1][0]}  ({len(blob)/1e6:.1f} MB gzipped)")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "perSeries"}
                      for k, v in manifest["series"].items()}, indent=1))


if __name__ == "__main__":
    main()
