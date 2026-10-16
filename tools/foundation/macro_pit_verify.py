"""Does the macro artifact hold, on each session, the value that was public on that session?

    python tools/foundation/macro_pit_verify.py --artifact DIR [--against DIR] [--out FILE]

`macro_pit.py` prints `observationsDatedAfterTheirSession`, which catches a row describing a period
that had not ended. It cannot catch the fault that invalidated the previous artifact, because that
one is not about dates at all: the stored CSVs pair the **latest revised value** with the **first
publication date**, so a join on `availableAt` returns a number nobody could see on that day --
`CPIAUCSL` observation 2010-01-01 carried 217.488, which is the 2015-02-28 revision, against an
`availableAt` of 2010-02-16 when February 2010 had printed 217.587 (brain.md rule 156).

So this reads the artifact back against the vintage histories themselves, which are the only record
of what was public when, and checks the three things that fault would break:

1. **Every value was published.** For each session and each revision-tracked series, the stored `v`
   equals the latest revision whose publication date is on or before that session -- recomputed here
   from `vintages/<id>.jsonl` rather than from anything `macro_pit.py` produced.
2. **No later revision arrived early.** The same check from the other side: the stored value is never
   one that a *later* publication introduced. This is the one the old artifact failed, and it fails
   loudly here rather than as a slightly better backtest.
3. **A series with no vintage yet is absent, not guessed.** Before its first publication a series
   must not appear in a session's state at all.

`chg` is checked too: it must be the step from the previous *distinct observation*, never the size
of a revision to the same observation, which is not a thing a market reacts to.

With `--against DIR` it also reports how the two artifacts differ per series, which is what shows
the rebuild actually changed the contaminated series and left the others alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MACRO = ROOT / "data" / "foundation" / "macro"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def vintages(sid: str) -> list[tuple[str, str, float]]:
    """(published, observation, value), sorted -- the publication events, straight from the record."""
    path = MACRO / "vintages" / f"{sid}.jsonl"
    rows: list[tuple[str, str, float]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            for published, value in rec.get("history") or []:
                if published and value not in (None, "", "."):
                    rows.append((published, rec["obs"], float(value)))
    rows.sort()
    return rows


def csv_final(sid: str) -> dict[str, float]:
    """{observation: value} as the CSV holds it -- the latest revision, which is the wrong answer."""
    import csv

    out: dict[str, float] = {}
    path = MACRO / f"{sid}.csv"
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("value") not in (None, "", "."):
                out[r["observation_date"]] = float(r["value"])
    return out


def read(artifact: Path) -> list[dict]:
    with gzip.open(artifact / "macro-sessions.jsonl.gz", "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> int:
    artifact = Path(arg("--artifact") or (ROOT / ".cache" / "foundation" / "macro_rebuild"))
    against = arg("--against")
    sessions = read(artifact)
    tracked = sorted(p.stem for p in (MACRO / "vintages").glob("*.jsonl"))

    report: dict = {"artifact": str(artifact), "sessions": len(sessions), "seriesTracked": len(tracked),
                    "perSeries": {}, "failures": []}

    for sid in tracked:
        rows = vintages(sid)
        pub = [r[0] for r in rows]
        obs = [r[1] for r in rows]
        val = [r[2] for r in rows]
        final = csv_final(sid)
        checked = present = absent_before_first = 0
        equals_final_when_differs = 0
        wrong_value = wrong_chg = early_revision = appeared_too_early = 0
        first_pub = pub[0] if pub else None

        for rec in sessions:
            day = rec["d"]
            row = rec["m"].get(sid)
            i = bisect_right(pub, day) - 1

            if i < 0:
                # Nothing had been published by this session, so the series must be absent.
                if row is None:
                    absent_before_first += 1
                else:
                    appeared_too_early += 1
                    if len(report["failures"]) < 40:
                        report["failures"].append(
                            {"series": sid, "session": day, "fault": "present before its first publication",
                             "firstPublication": first_pub, "stored": row.get("v")})
                continue

            if row is None:
                # A published series that is missing is a coverage hole, not a correctness fault, and
                # `coveragePerSeries` in the producer's own manifest is where that is reported.
                continue

            present += 1
            checked += 1
            expected = val[i]
            if row.get("v") != expected:
                wrong_value += 1
                # Was the stored value introduced by a publication *after* this session? That is the
                # exact shape of the fault the rebuild exists to remove.
                later = any(abs(v - row["v"]) < 1e-9 and p > day for p, o, v in rows if o == obs[i])
                if later:
                    early_revision += 1
                if len(report["failures"]) < 40:
                    report["failures"].append(
                        {"series": sid, "session": day, "fault": "value was not the one public that day",
                         "stored": row.get("v"), "publicThatDay": expected,
                         "introducedByALaterPublication": later})

            # The CSV's final value, where it differs from what was public, is the number the old
            # artifact carried. Counting it says whether this one still does.
            csv_value = final.get(obs[i])
            if csv_value is not None and abs(csv_value - expected) > 1e-9 and row.get("v") == csv_value:
                equals_final_when_differs += 1

            # `chg` steps back to the newest row describing a different observation.
            j = i - 1
            while j >= 0 and obs[j] == obs[i]:
                j -= 1
            expected_chg = round(val[i] - val[j], 6) if j >= 0 else None
            if expected_chg is None:
                if "chg" in row:
                    wrong_chg += 1
            elif abs(row.get("chg", expected_chg) - expected_chg) > 1e-6:
                wrong_chg += 1
                if len(report["failures"]) < 40:
                    report["failures"].append(
                        {"series": sid, "session": day, "fault": "chg is not the step between distinct observations",
                         "stored": row.get("chg"), "expected": expected_chg})

        report["perSeries"][sid] = {
            "publications": len(rows), "sessionsChecked": checked, "sessionsPresent": present,
            "absentBeforeFirstPublication": absent_before_first,
            "wrongValue": wrong_value, "introducedByALaterPublication": early_revision,
            "stillEqualsTheCsvFinalValue": equals_final_when_differs,
            "wrongChg": wrong_chg, "presentBeforeFirstPublication": appeared_too_early,
        }

    totals = {k: sum(s[k] for s in report["perSeries"].values())
              for k in ("sessionsChecked", "wrongValue", "introducedByALaterPublication",
                        "stillEqualsTheCsvFinalValue", "wrongChg", "presentBeforeFirstPublication",
                        "absentBeforeFirstPublication")}
    report["totals"] = totals

    if against:
        other = {r["d"]: r["m"] for r in read(Path(against))}
        changed: dict[str, int] = {}
        for rec in sessions:
            prev = other.get(rec["d"])
            if prev is None:
                continue
            for sid in tracked:
                a, b = rec["m"].get(sid), prev.get(sid)
                if a != b:
                    changed[sid] = changed.get(sid, 0) + 1
        report["differsFromPrevious"] = {"artifact": against, "sessionsChangedPerSeries": dict(sorted(changed.items()))}

    ok = all(totals[k] == 0 for k in ("wrongValue", "introducedByALaterPublication",
                                      "stillEqualsTheCsvFinalValue", "wrongChg",
                                      "presentBeforeFirstPublication"))
    report["ok"] = ok
    out = arg("--out")
    if out:
        Path(out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "perSeries"}, indent=1))
    print(json.dumps(report["perSeries"], indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
