"""Check every durable acquisition file against its manifest, and say what is actually in it.

    python tools/foundation/verify_durable.py

A manifest is a claim. This opens each file the manifest names, re-computes its sha256, parses it,
and reports the row count, the distinct-date count, duplicates, the date range and whatever looks
wrong in the values -- so "verified" means the file was read, not that a checksum was copied twice.

Instrument identity is checked too, because the frozen target keeps pairs apart that are easy to
conflate: the S&P 500 price index against its total-return series, ICE's six-currency dollar index
against the Federal Reserve's broad one, a continuous future against spot, and KIBOR against the
policy rate. A file whose numbers equal another file's is reported, since that is what conflation
would look like.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DIRS = [ROOT / "data" / "foundation" / "benchmarks", ROOT / "data" / "foundation" / "sbp"]


def read_csv_any(path: Path) -> tuple[list[str], list[list[str]]]:
    raw = path.read_bytes()
    text = gzip.decompress(raw).decode() if path.suffix == ".gz" else raw.decode("utf-8-sig")
    r = csv.reader(io.StringIO(text))
    header = next(r)
    return header, [row for row in r if row]


def check(path: Path, claim: dict) -> dict:
    raw = path.read_bytes()
    got = {"file": path.name, "exists": True, "bytes": len(raw),
           "sha256Matches": hashlib.sha256(raw).hexdigest() == claim.get("sha256")}
    header, rows = read_csv_any(path)
    got["header"] = header
    got["rows"] = len(rows)
    got["rowsMatchManifest"] = len(rows) == claim.get("observations")
    dates = [r[0] for r in rows]
    got["distinctDates"] = len(set(dates))
    # A multi-series file repeats a date once per series; a single-series file must not.
    series_col = 1 if "series_key" in header else None
    if series_col is not None:
        pairs = Counter((r[0], r[series_col]) for r in rows)
        got["duplicateDateSeriesPairs"] = sum(1 for v in pairs.values() if v > 1)
        got["seriesInFile"] = len({r[series_col] for r in rows})
    else:
        got["duplicateDates"] = len(dates) - len(set(dates))
    got["first"], got["last"] = (min(dates), max(dates)) if dates else (None, None)
    got["rangeMatchesManifest"] = (got["first"] == claim.get("first")
                                   and got["last"] == claim.get("last"))
    got["datesSorted"] = dates == sorted(dates)
    # value sanity on the numeric columns
    bad, nonpos = 0, 0
    close_i = header.index("close") if "close" in header else (
        header.index("value") if "value" in header else (
            header.index("rate_percent") if "rate_percent" in header else (
                header.index("policy_rate_percent") if "policy_rate_percent" in header else None)))
    vals = []
    for r in rows:
        if close_i is None or close_i >= len(r):
            continue
        try:
            v = float(r[close_i])
        except ValueError:
            bad += 1
            continue
        vals.append(v)
        if v <= 0:
            nonpos += 1
    got["unparseableValues"] = bad
    got["nonPositiveValues"] = nonpos
    if vals:
        got["valueRange"] = [min(vals), max(vals)]
    if "high" in header and "low" in header:
        hi, lo, cl = header.index("high"), header.index("low"), header.index("close")
        viol = 0
        for r in rows:
            try:
                h, l, c = float(r[hi]), float(r[lo]), float(r[cl])
            except (ValueError, IndexError):
                continue
            if h < l or c > h + 1e-6 or c < l - 1e-6:
                viol += 1
        got["ohlcViolations"] = viol
    return got


def main() -> None:
    report = {"verifiedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": {},
              "manifests": {}, "problems": []}
    fingerprints = {}
    for d in DIRS:
        mpath = d / "manifest.json"
        if not mpath.exists():
            report["problems"].append(f"{d.name}: no manifest")
            continue
        man = json.loads(mpath.read_text("utf-8"))
        report["manifests"][d.name] = {"series": len(man["series"]),
                                       "generatedAt": man.get("generatedAt")}
        for key, claim in man["series"].items():
            p = d / claim["file"]
            if not p.exists():
                report["problems"].append(f"{key}: {claim['file']} missing")
                report["files"][key] = {"file": claim["file"], "exists": False}
                continue
            got = check(p, claim)
            got["claimedName"] = claim.get("name") or claim.get("title")
            got["basis"] = claim.get("basis")
            report["files"][key] = got
            for flag, msg in (("sha256Matches", "checksum mismatch"),
                              ("rowsMatchManifest", "row count differs from the manifest"),
                              ("rangeMatchesManifest", "date range differs from the manifest")):
                if not got.get(flag, True):
                    report["problems"].append(f"{key}: {msg}")
            if got.get("duplicateDates"):
                report["problems"].append(f"{key}: {got['duplicateDates']} duplicate dates")
            if got.get("duplicateDateSeriesPairs"):
                report["problems"].append(
                    f"{key}: {got['duplicateDateSeriesPairs']} duplicate date/series pairs")
            if got.get("ohlcViolations"):
                report["problems"].append(f"{key}: {got['ohlcViolations']} OHLC violations")
            if got.get("nonPositiveValues"):
                report["problems"].append(
                    f"{key}: {got['nonPositiveValues']} non-positive values")
            # identity: a file that is numerically identical to another would be a conflation
            _h, rows = read_csv_any(p)
            fingerprints.setdefault(
                hashlib.sha256(json.dumps([r[:2] for r in rows[:400]]).encode()).hexdigest(),
                []).append(key)
    dupes = {k: v for k, v in fingerprints.items() if len(v) > 1}
    report["distinctInstrumentCheck"] = {
        "method": "sha256 of the first 400 (date, first value) pairs of each file",
        "filesSharingAFingerprint": list(dupes.values()),
        "allDistinct": not dupes}
    if dupes:
        report["problems"].append(f"files that are numerically identical: {list(dupes.values())}")

    out = ROOT / "data" / "foundation" / "acquisition" / "durable_verification.json"
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    ok = sum(1 for v in report["files"].values() if v.get("sha256Matches"))
    print(f"files checked: {len(report['files'])}   checksum matches: {ok}")
    for k, v in report["files"].items():
        print(f"  {k:20} rows={v.get('rows', 0):7} distinctDates={v.get('distinctDates', 0):7} "
              f"{v.get('first')} .. {v.get('last')}  sha={'ok' if v.get('sha256Matches') else 'MISMATCH'}")
    print()
    print("problems:", report["problems"] or "none")
    print("all instruments numerically distinct:", report["distinctInstrumentCheck"]["allDistinct"])


if __name__ == "__main__":
    main()
