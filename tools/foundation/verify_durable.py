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

import sys

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

from ohlc import OK, UNTRUSTWORTHY, classify  # noqa: E402

# A price below zero is normally a parse error. On 2020-04-20 WTI settled at -37.63 because
# holders paid to avoid delivery, and FRED's DCOILWTICO carries it. The event is named here with
# its count so that this one row passes and any other non-positive value in the same file still
# fails: a blanket "non-positive is fine for oil" rule would hide a real parse error.
REAL_NON_POSITIVE = {"DCOILWTICO": 1}

# The PSX daily file publishes two shapes of range its own close contradicts -- a range collapsed
# to one value, and a close outside a real range -- and the delisted history inherits both from
# the same archive. They are classified and quarantined in
# data/foundation/price_verification/ohlc_quarantine.json; the close in each row is the exchange's
# own and is kept. Pinned to the exact counts rather than waved through by class, so one more of
# either still fails here. This file is checksummed and must not be rewritten to satisfy a rule.
KNOWN_RANGE_DEFECTS = {"psx_delisted": {"collapsed-range": 232, "incoherent-range": 138}}

DIRS = [ROOT / "data" / "foundation" / "benchmarks",
        ROOT / "data" / "foundation" / "sbp",
        ROOT / "data" / "foundation" / "psx_index",
        ROOT / "data" / "foundation" / "psx_delisted"]


def read_csv_any(path: Path) -> tuple[list[str], list[list[str]]]:
    raw = path.read_bytes()
    text = gzip.decompress(raw).decode() if path.suffix == ".gz" else raw.decode("utf-8-sig")
    r = csv.reader(io.StringIO(text))
    header = next(r)
    return header, [row for row in r if row]


def check(path: Path, claim: dict) -> dict:
    # A single-series manifest keeps its counts under "validation"; a multi-series one keeps them
    # at the top level. Read whichever this file uses before comparing anything.
    v = claim.get("validation")
    if isinstance(v, dict):
        claim = {**claim, "observations": v.get("distinctDates", claim.get("observations")),
                 "first": v.get("first"), "last": v.get("last")}
    raw = path.read_bytes()
    got = {"file": path.name, "exists": True, "bytes": len(raw),
           "sha256Matches": hashlib.sha256(raw).hexdigest() == claim.get("sha256")}
    header, rows = read_csv_any(path)
    got["header"] = header
    got["rows"] = len(rows)
    got["rowsMatchManifest"] = len(rows) == claim.get("observations")
    # The date is not always the first column: the delisted file is keyed (symbol, date), so
    # reading column 0 as a date turns 24,613 bars into "24,592 duplicate dates" and a range of
    # "BHAT .. WHALE". Find the column by name.
    di = header.index("date") if "date" in header else 0
    dates = [r[di] for r in rows]
    got["distinctDates"] = len(set(dates))
    # A multi-series file repeats a date once per series; a single-series file must not.
    series_col = (header.index("series_key") if "series_key" in header else
                  (header.index("symbol") if "symbol" in header else None))
    if series_col is not None:
        pairs = Counter((r[di], r[series_col]) for r in rows)
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
        # One definition of a range defect for the whole project: jobs/ohlc.py. The ad-hoc
        # 1e-6 absolute tolerance this used before was both too tight for a cheap scrip and too
        # loose for a Rs 500 one, and it could not tell a float artefact from a collapsed range.
        classes: Counter = Counter()
        for r in rows:
            try:
                h, l, c = float(r[hi]), float(r[lo]), float(r[cl])
            except (ValueError, IndexError):
                continue
            classes[classify(h, l, c)] += 1
        got["ohlcClasses"] = {k: v for k, v in sorted(classes.items()) if k != OK}
        got["ohlcViolations"] = sum(v for k, v in classes.items() if k in UNTRUSTWORTHY)
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
        # Two shapes in use: a manifest of many series, and a manifest that *is* one series.
        series = man.get("series") if isinstance(man.get("series"), dict) else None
        if series is None:
            series = {man.get("series") or d.name: man}
        report["manifests"][d.name] = {"series": len(series),
                                       "generatedAt": man.get("generatedAt")}
        for key, claim in series.items():
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
            classes = got.get("ohlcClasses") or {}
            known = KNOWN_RANGE_DEFECTS.get(key, {})
            unexpected = {k: n - known.get(k, 0) for k, n in classes.items()
                          if n > known.get(k, 0)}
            if unexpected:
                report["problems"].append(f"{key}: OHLC ranges beyond the recorded set {unexpected}")
            if got.get("nonPositiveValues", 0) > REAL_NON_POSITIVE.get(key, 0):
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
