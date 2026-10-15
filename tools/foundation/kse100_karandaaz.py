"""Validate the Karandaaz KSE-100 file the owner downloaded, against everything already held.

    python tools/foundation/kse100_karandaaz.py validate <path-to-csv>
    python tools/foundation/kse100_karandaaz.py verify

What this file is
-----------------
`Date,KSE 100 Index` with a `Daily,` marker row, newest first. **One value column: the index
level.** No open, no high, no low, no volume -- and none are invented here. A close-only series is
stored as a close-only series.

Why it matters: it is the first candidate that *overlaps* what this project already holds. The
exchange endpoint supplies 2021-10-15 onward, so every shared date is a direct test of whether
this file is the same series rather than something merely similar. The Open Data Pakistan file
covers 2008-2021 and overlaps it too, giving a second, independent comparison.

The acceptance rule is the frozen one: a shared date passes when the two closes differ by no more
than **0.05%**. Nothing is rounded, rebased or nudged to make that true -- a failure is reported
as a failure and investigated.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "foundation" / "psx_index"
PRIVATE = ROOT / ".cache" / "acquire" / "karandaaz"
BASELINE = OUT / "KSE100.csv"
OPENDATA = ROOT / ".cache" / "acquire" / "opendata" / "kse100_opendata.csv"

GAP_FROM, GAP_TO = "2021-02-24", "2021-10-14"
TOL = 0.0005          # 0.05%, the frozen acceptance rule
BIG_MOVE = 0.03       # 3% daily move, flagged for investigation and never silently dropped


def parse(blob: bytes) -> tuple[list[tuple[str, float]], dict]:
    text = blob.decode("utf-8-sig", "replace")
    r = csv.reader(io.StringIO(text))
    why = {"headerRows": 0, "unparseableDate": 0, "unparseableValue": 0,
           "nonPositive": 0, "duplicateDate": 0}
    seen: dict[str, float] = {}
    for row in r:
        if not row or not row[0].strip():
            continue
        raw = row[0].strip()
        if raw.lower() in ("date", "daily", "monthly", "weekly"):
            why["headerRows"] += 1
            continue
        try:
            d = datetime.strptime(raw, "%d-%b-%Y").date().isoformat()
        except ValueError:
            why["unparseableDate"] += 1
            continue
        if len(row) < 2 or not row[1].strip():
            why["unparseableValue"] += 1
            continue
        try:
            v = float(row[1].replace(",", "").strip())
        except ValueError:
            why["unparseableValue"] += 1
            continue
        if v <= 0:
            why["nonPositive"] += 1
            continue
        if d in seen:
            why["duplicateDate"] += 1
            continue
        seen[d] = v
    return sorted(seen.items()), why


def load_pairs(path: Path, date_i: int, val_i: int, skip_header=True) -> dict[str, float]:
    text = path.read_text("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    out = {}
    for row in rows[1:] if skip_header else rows:
        if len(row) <= max(date_i, val_i):
            continue
        try:
            out[row[date_i]] = float(row[val_i])
        except ValueError:
            continue
    return out


def opendata_pairs() -> dict[str, float]:
    if not OPENDATA.exists():
        return {}
    rows = list(csv.reader(io.StringIO(OPENDATA.read_text("utf-8-sig", errors="replace"))))[1:]
    out = {}
    for r in rows:
        if len(r) < 5:
            continue
        try:
            d = datetime.strptime(r[0].strip(), "%d-%b-%y").date()
            if d.year > 2030:
                d = d.replace(year=d.year - 100)
            out[d.isoformat()] = float(r[4].replace(",", "").strip().strip('"'))
        except ValueError:
            continue
    return out


def compare(a: dict[str, float], b: dict[str, float], label_a: str, label_b: str) -> dict:
    shared = sorted(set(a) & set(b))
    diffs = [(d, a[d], b[d], abs(a[d] - b[d]) / b[d]) for d in shared if b[d]]
    exact = sum(1 for _d, x, y, _p in diffs if abs(x - y) < 1e-9)
    fails = [(d, x, y, p) for d, x, y, p in diffs if p > TOL]
    return {
        "sourceA": label_a, "sourceB": label_b,
        "matchedDates": len(shared),
        "exactMatches": exact,
        "withinTolerance": len(diffs) - len(fails),
        "tolerance": f"{TOL:.4%}",
        "maxAbsPctDiff": round(max((p for *_x, p in diffs), default=0) * 100, 6),
        "medianAbsPctDiff": round(statistics.median([p for *_x, p in diffs]) * 100, 6) if diffs else None,
        "failures": [{"date": d, label_a: x, label_b: y, "pctDiff": round(p * 100, 4)}
                     for d, x, y, p in fails[:20]],
        "failureCount": len(fails),
        "datesOnlyInA": len(set(a) - set(b)), "datesOnlyInB": len(set(b) - set(a)),
    }


def cmd_validate() -> None:
    src = Path(sys.argv[2])
    blob = src.read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    rows, why = parse(blob)
    if not rows:
        print("no observations parsed")
        raise SystemExit(1)
    dates = [d for d, _v in rows]
    by = dict(rows)

    # the interval this was fetched for
    gap = [(d, v) for d, v in rows if GAP_FROM <= d <= GAP_TO]
    sweep = json.loads((ROOT / ".cache/acquire/psx_sweep_ledger.json").read_text("utf-8"))["dates"]
    expected_sessions = sorted(d for d, s in sweep.items()
                               if GAP_FROM <= d <= GAP_TO and s.get("status") == "published")
    covered = sorted(set(expected_sessions) & {d for d, _v in gap})
    missing = sorted(set(expected_sessions) - {d for d, _v in gap})
    extra = sorted({d for d, _v in gap} - set(expected_sessions))

    # big daily moves, kept and flagged
    moves = []
    for i in range(1, len(rows)):
        prev, cur = rows[i - 1][1], rows[i][1]
        if prev > 0 and abs(cur / prev - 1) > BIG_MOVE:
            moves.append({"date": rows[i][0], "prev": prev, "close": cur,
                          "pct": round((cur / prev - 1) * 100, 2)})

    baseline = load_pairs(BASELINE, 0, 2) if BASELINE.exists() else {}
    report = {
        "validatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sourceFile": src.name, "bytes": len(blob), "sha256": sha,
        "providedBy": "downloaded by the owner through the portal's own flow",
        "fields": ["date", "index level"], "fieldsNotProvided": ["open", "high", "low", "volume"],
        "granularityMarkerInFile": "Daily",
        "observations": len(rows), "distinctDates": len(set(dates)),
        "rejected": why,
        "first": dates[0], "last": dates[-1],
        "chronologicalAfterSort": dates == sorted(dates),
        "gapInterval": {
            "from": GAP_FROM, "to": GAP_TO,
            "expectedPublishedSessions": len(expected_sessions),
            "covered": len(covered), "missing": len(missing),
            "missingDates": missing,
            "datesNotAPublishedSession": len(extra),
            "datesNotAPublishedSessionExamples": extra[:10]},
        "largeDailyMoves": {"thresholdPct": BIG_MOVE * 100, "count": len(moves),
                            "kept": True, "examples": moves[:10]},
        "overlapVsExchangeBaseline": compare(by, baseline, "karandaaz", "psxEndpoint"),
        "overlapVsOpenDataCandidate": compare(by, opendata_pairs(), "karandaaz", "openData"),
    }
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "kse100_karandaaz_raw.csv").write_bytes(blob)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "close"])
    w.writerows(rows)
    norm = buf.getvalue().encode()
    (PRIVATE / "kse100_karandaaz_normalized.csv").write_bytes(norm)
    report["privateArtifacts"] = {
        "raw": str((PRIVATE / "kse100_karandaaz_raw.csv").relative_to(ROOT)),
        "normalized": str((PRIVATE / "kse100_karandaaz_normalized.csv").relative_to(ROOT)),
        "normalizedSha256": hashlib.sha256(norm).hexdigest(),
        "note": ("held privately: the portal's Terms of Use require the express written permission "
                 "of KRN & CS before this content may be used. Not committed, not in production.")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "kse100_karandaaz_candidate.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("largeDailyMoves",)}, indent=1, default=str))
    print(f"\nlarge daily moves (>{BIG_MOVE:.0%}): {len(moves)} - kept, not discarded")
    for m in moves[:6]:
        print("   ", m)


def cmd_verify() -> None:
    man = json.loads((OUT / "kse100_karandaaz_candidate.json").read_text("utf-8"))
    p = PRIVATE / "kse100_karandaaz_raw.csv"
    print(json.dumps({
        "rawPresent": p.exists(),
        "sha256Matches": hashlib.sha256(p.read_bytes()).hexdigest() == man["sha256"],
        "observations": man["observations"],
        "overlapMatched": man["overlapVsExchangeBaseline"]["matchedDates"],
        "overlapFailures": man["overlapVsExchangeBaseline"]["failureCount"]}, indent=1))


COMMANDS = {"validate": cmd_validate, "verify": cmd_verify}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    COMMANDS[sys.argv[1]]()
