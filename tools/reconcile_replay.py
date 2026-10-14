"""Rebuild the replay's canonical state from the outputs themselves.

    python tools/reconcile_replay.py --outputs outputs --runs runs.json --from 2019-01-02 \
        --to 2026-09-01 --out canonical [--checkpoint name=path ...]

The checkpoint namespaces disagreed with each other (799 dates in one, 2,000 in another), so no
checkpoint is believed. A session counts as complete only when a persisted output proves it:

  * `decisions-<date>.json` parses, names that date, and carries a setup count and action table;
  * `setups-<date>.jsonl` from the SAME run exists, every line parses, and the line count equals
    the decisions file's setup count;
  * the run that wrote it executed code whose replay-relevant tree equals the current one
    (`--runs` maps run id -> {"trusted": bool}; the workflow computes it with `git diff`).

Where several runs wrote the same date, the copies are compared; a date whose verified copies
differ is reported, not silently resolved. Nothing is written to a database.

Writes `canonical/checkpoint.json` in the format `tools/worker.py` resumes from, and
`canonical/report.json`. Prints GitHub annotations (counts and dates only) so the result can be
read without opening the run's logs.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from worker import arg, eligible_sessions  # noqa: E402

RUN = re.compile(r"nbt-worker-output-(\d+)")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_pair(dec: Path, setups: Path | None, day: str) -> str | None:
    """None when the session's output is internally consistent, else the reason it is not."""
    try:
        body = json.loads(dec.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return f"decisions unreadable: {type(e).__name__}"
    if body.get("asOf") != day:
        return "decisions names another date"
    n = body.get("setups")
    if not isinstance(n, int) or n < 0 or not isinstance(body.get("byAction"), dict):
        return "decisions missing setup count or action table"
    if setups is None or not setups.exists():
        return "setups file missing"
    lines = [l for l in setups.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lines) != n:
        return f"setups has {len(lines)} rows, decisions says {n}"
    try:
        for l in lines:
            json.loads(l)
    except Exception:  # noqa: BLE001
        return "setups row is not JSON"
    return None


def main() -> int:
    outputs = Path(arg("--outputs"))
    runs = json.loads(Path(arg("--runs")).read_text(encoding="utf-8")) if arg("--runs") else {}
    frm = date.fromisoformat(arg("--from") or "2019-01-02")
    to = date.fromisoformat(arg("--to") or "2026-09-01")
    out = Path(arg("--out") or "canonical")
    out.mkdir(parents=True, exist_ok=True)

    expected = [d.isoformat() for d in eligible_sessions(frm, to)]
    expected_set = set(expected)

    occurrences: dict[str, list[dict]] = {}
    for art in sorted(p for p in outputs.iterdir() if p.is_dir()):
        m = RUN.fullmatch(art.name)
        run_id = m.group(1) if m else art.name
        trusted = bool(runs.get(run_id, {}).get("trusted"))
        for dec in sorted(art.rglob("decisions-*.json")):
            day = dec.stem.removeprefix("decisions-")
            reason = check_pair(dec, dec.parent / f"setups-{day}.jsonl", day)
            occurrences.setdefault(day, []).append({
                "run": run_id, "trusted": trusted, "reason": reason,
                "decisions": sha(dec),
                "setups": sha(dec.parent / f"setups-{day}.jsonl")
                if (dec.parent / f"setups-{day}.jsonl").exists() else None,
            })

    done: dict[str, dict] = {}
    invalid: dict[str, str] = {}
    divergent: list[str] = []
    untrusted_only: list[str] = []
    for day in sorted(expected_set):
        occ = occurrences.get(day, [])
        good = [o for o in occ if o["reason"] is None and o["trusted"]]
        if good:
            if len({(o["decisions"], o["setups"]) for o in good}) > 1:
                divergent.append(day)
            # Newest run id wins; the choice is recorded, not hidden.
            pick = max(good, key=lambda o: int(o["run"]) if o["run"].isdigit() else 0)
            done[day] = pick
        elif occ:
            if any(o["reason"] is None for o in occ):
                untrusted_only.append(day)
            invalid[day] = next((o["reason"] for o in occ if o["reason"]),
                                "run's code differs from the current replay code")
    missing = sorted(expected_set - set(done))
    outside = sorted(set(occurrences) - expected_set)

    ckpt = {
        "lastSession": max(done) if done else None,
        "sessionsDone": len(done),
        "done": sorted(done),
        "failed": {d: {"stage": "reconcile", "error": invalid.get(d, "no persisted output")}
                   for d in missing},
        "outputs": {d: done[d]["decisions"] for d in sorted(done)},
        "provenance": {d: done[d]["run"] for d in sorted(done)},
        "namespace": "nbt-canonical-checkpoint",
        "updatedAt": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
    }
    (out / "checkpoint.json").write_text(json.dumps(ckpt, indent=1), encoding="utf-8")

    named: dict[str, dict] = {}
    for i, a in enumerate(sys.argv):
        if a == "--checkpoint":
            n, _, path = sys.argv[i + 1].partition("=")
            c = json.loads(Path(path).read_text(encoding="utf-8"))
            ds = c.get("done", [])
            named[n] = {"list": len(ds), "unique": len(set(ds)),
                        "outsideRange": len(set(ds) - expected_set),
                        "notBackedByVerifiedOutput": len(set(ds) & expected_set - set(done)),
                        "last": c.get("lastSession")}

    report = {
        "verdict": "PASS" if expected and not missing and not divergent else "NOT COMPLETE",
        "range": [frm.isoformat(), to.isoformat()],
        "eligible": len(expected),
        "verifiedComplete": len(done),
        "missingOrInvalid": len(missing),
        "invalidReasons": {r: sum(1 for v in invalid.values() if v == r) for r in set(invalid.values())},
        "datesWithNoOutputAtAll": len([d for d in missing if d not in occurrences]),
        "divergentDates": divergent,
        "completeOnlyFromUntrustedRun": len(untrusted_only),
        "outputsOutsideRange": len(outside),
        "duplicateOutputDates": sum(1 for d in expected if len(occurrences.get(d, [])) > 1),
        "firstVerified": min(done) if done else None,
        "lastVerified": max(done) if done else None,
        "runsContributing": sorted({v["run"] for v in done.values()}),
        "namespaces": named,
        "missingDates": missing,
    }
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    # Annotations are public on this repository's check runs; they carry counts and dates only.
    head = {k: v for k, v in report.items() if k not in ("missingDates",)}
    print(f"::notice title=replay reconcile {report['verdict']}::{json.dumps(head)}")
    for i in range(0, len(missing), 60):
        print(f"::notice title=replay missing dates {i // 60 + 1}::{' '.join(missing[i:i + 60])}")
    if divergent:
        print(f"::warning title=replay divergent dates::{' '.join(divergent[:100])}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
