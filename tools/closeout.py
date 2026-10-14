"""Read-only closeout of the historical replay: does the checkpoint match what was expected,
and do the persisted outputs match the checkpoint?

    python tools/closeout.py --checkpoint name=dir/checkpoint.json [--primary name] --outputs outputs/ --from 2019-01-02 --to 2026-09-01

`--outputs` holds one extracted directory per `nbt-worker-output-<run_id>` artifact. Nothing is
written to the database and nothing is replayed. Prints a report and writes `closeout.json`
(counts, dates and file hashes only -- no row contents, no credentials).

Verdict is PASS only when every expected session is in the checkpoint, no session is missing or
unexpected, the checkpoint has no duplicates, and every checkpointed session has a persisted
decisions file that is valid JSON for that date.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from worker import arg, eligible_sessions  # noqa: E402


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    # `--checkpoint name=path`, repeatable: one entry per checkpoint namespace. The union of the
    # persisted outputs is the evidence of completion; a namespace is only a claim about it.
    namespaces: dict[str, dict] = {}
    for i, a in enumerate(sys.argv):
        if a == "--checkpoint":
            name, _, path = sys.argv[i + 1].partition("=")
            namespaces[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    primary = arg("--primary") or next(iter(namespaces))
    cp = namespaces[primary]
    outputs = Path(arg("--outputs"))
    frm = date.fromisoformat(arg("--from") or "2019-01-02")
    to = date.fromisoformat(arg("--to") or "2026-09-01")

    expected = [d.isoformat() for d in eligible_sessions(frm, to)]
    raw_done = cp.get("done", [])
    done = set(raw_done)
    dupes = sorted({d for d in raw_done if raw_done.count(d) > 1}) if len(raw_done) != len(done) else []

    missing = sorted(set(expected) - done)
    unexpected = sorted(done - set(expected))

    # Persisted outputs: decisions-<date>.json across every output artifact.
    found: dict[str, list[dict]] = {}
    bad: list[str] = []
    for f in sorted(outputs.rglob("decisions-*.json")):
        day = f.stem.removeprefix("decisions-")
        try:
            body = json.loads(f.read_text(encoding="utf-8"))
            ok = body.get("asOf") == day
        except Exception:
            ok = False
        if not ok:
            bad.append(str(f.relative_to(outputs)))
            continue
        found.setdefault(day, []).append({
            "artifact": f.relative_to(outputs).parts[0], "sha256": sha256(f),
            "setups": body.get("setups"),
        })
    setups_found = {f.stem.removeprefix("setups-") for f in outputs.rglob("setups-*.jsonl")}

    no_output = sorted(done - set(found))
    no_setups = sorted(done - setups_found)
    # The same date written by two runs should hash identically (the replay is deterministic).
    divergent = sorted(d for d, v in found.items() if len({x["sha256"] for x in v}) > 1)

    # PASS needs the primary checkpoint AND the persisted outputs to both cover every expected
    # session; either alone is a claim, not proof.
    passed = (not missing and not unexpected and not dupes and not no_output
              and not bad and len(done) == len(expected) and bool(expected)
              and not (set(expected) - set(found)))
    report = {
        "verdict": "PASS" if passed else "NOT COMPLETE",
        "range": [frm.isoformat(), to.isoformat()],
        "eligibleSessions": len(expected),
        "completedUniqueSessions": len(done & set(expected)),
        "remainingSessions": len(missing),
        "failedSessions": len(missing),  # failures are not persisted; a failed date is a missing one
        "primaryNamespace": primary,
        "namespaces": {n: {"listLength": len(c.get("done", [])),
                           "unique": len(set(c.get("done", []))),
                           "last": c.get("lastSession"),
                           "recordedFailures": len(c.get("failed", {}))}
                       for n, c in namespaces.items()},
        "outputsMissingForExpected": sorted(set(expected) - set(found)),
        "checkpointListLength": len(raw_done),
        "checkpointSessionsDone": cp.get("sessionsDone"),
        "checkpointLastSession": cp.get("lastSession"),
        "firstCompletedDate": min(done) if done else None,
        "lastCompletedDate": max(done) if done else None,
        "duplicateDates": dupes,
        "missingDates": missing,
        "unexpectedDates": unexpected,
        "datesWithDecisionsFile": len(found),
        "checkpointedWithoutDecisionsFile": no_output,
        "checkpointedWithoutSetupsFile": no_setups,
        "corruptOrMismatchedDecisionsFiles": bad,
        "datesWhoseCopiesDiffer": divergent,
        "outputArtifacts": sorted({x["artifact"] for v in found.values() for x in v}),
        "decisionFiles": {d: v[0] for d, v in sorted(found.items())},
    }
    Path("closeout.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "decisionFiles"}, indent=1))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
