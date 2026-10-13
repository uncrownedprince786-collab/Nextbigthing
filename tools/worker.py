"""The replay worker: a bounded slice of sessions, checkpointed after every one.

    python tools/worker.py --from 2019-01-02 --to 2026-09-01 --batch 900 --state state --out out

Run by `.github/workflows/data-worker.yml`, and runnable locally with the same arguments. It
reconstructs one session at a time with `jobs/setup.py --as-of`, replays it through
`tools/decide.mjs --as-of --setups-file`, writes the result, and records what it did before
moving on.

Resumable by construction
-------------------------
The checkpoint holds the last session that completed, so a run that is cancelled, times out or
dies mid-slice resumes from the next one rather than from the beginning. It is written with a
temporary file and `os.replace`, which is atomic on both Windows and Linux: a reader never sees a
half-written checkpoint, and a kill between the two lines leaves the previous one intact.

A session is only recorded once its output file is closed, so an interrupted session is replayed
rather than skipped. Replaying one is harmless -- the reconstruction is deterministic, and the
same date produces a byte-identical result -- which is what makes the whole slice idempotent.

Bounded twice
-------------
By `--batch`, and by a wall-clock deadline that stops the slice early enough to write its
checkpoint and upload before the job's own timeout kills it. Stopping with a good checkpoint is
always better than being killed with a stale one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

from nbt import db  # noqa: E402

# Leave the job time to encrypt and upload after the last session. The workflow's timeout is 330
# minutes; stopping at 300 leaves half an hour, which is far more than the upload needs and is
# the margin that keeps a slice from being killed with work it never recorded.
DEADLINE_SECONDS = 300 * 60
PER_SESSION_TIMEOUT = 600


def arg(name: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def first_error(stderr: str) -> str:
    """The head of a traceback, not its tail.

    Taking the last 300 characters of a Node stack left `dules/esm/loader:747:20)` in the log of
    run 38487057088 -- the line numbers survived and the message that named the fault did not.
    The first line that looks like an error, plus a little context, is what a reader needs.
    """
    lines = [l for l in stderr.strip().splitlines() if l.strip()]
    for i, l in enumerate(lines):
        if any(k in l for k in ("Error", "error:", "Traceback", "raise ", "Exception")):
            return " | ".join(lines[i:i + 3])[:400]
    return " | ".join(lines[:3])[:400]


def write_atomic(path: Path, payload: str) -> None:
    """Write via a temporary file and rename, so a reader never sees a partial checkpoint."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def eligible_sessions(frm: date, to: date) -> list[date]:
    """Every stored session date in range, from the database rather than from a calendar.

    A weekday with no bar is not a session, and generating one would ask `setup.py` to describe a
    day nothing traded on.
    """
    conn = db()
    cur = conn.cursor()
    cur.execute(
        'SELECT DISTINCT date FROM "PriceSnapshot" WHERE date >= %s AND date <= %s '
        'AND EXTRACT(ISODOW FROM date) < 6 ORDER BY date ASC',
        (frm, to),
    )
    out = [r["date"] for r in cur.fetchall()]
    conn.close()
    return out


def replay_one(day: date, out_dir: Path) -> dict:
    """Reconstruct and replay one session. Returns what it produced, or why it did not."""
    setups_path = out_dir / f"setups-{day}.jsonl"
    result_path = out_dir / f"decisions-{day}.json"

    setup = subprocess.run(
        [sys.executable, "jobs/setup.py", "--as-of", day.isoformat()],
        cwd=ROOT, capture_output=True, text=True, timeout=PER_SESSION_TIMEOUT,
    )
    if setup.returncode != 0:
        return {"ok": False, "stage": "setup", "error": first_error(setup.stderr)}
    rows = [l for l in setup.stdout.splitlines() if l.strip().startswith("{")]
    # Written before the replay reads it, and the session is not recorded until the result file
    # below is closed, so a crash here leaves the date to be replayed rather than skipped.
    setups_path.write_text("\n".join(rows), encoding="utf-8")

    decide = subprocess.run(
        ["node", "tools/decide.mjs", "--as-of", day.isoformat(),
         "--setups-file", str(setups_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=PER_SESSION_TIMEOUT,
    )
    if decide.returncode != 0:
        return {"ok": False, "stage": "decide", "setups": len(rows),
                "error": first_error(decide.stderr)}

    actions: dict[str, int] = {}
    section = None
    for line in decide.stdout.splitlines():
        s = line.strip()
        if s.startswith("by action:"):
            section = "a"
            continue
        if s.startswith("by ") or s.startswith("developing") or not s:
            section = None
            continue
        parts = s.split()
        if section == "a" and len(parts) >= 2 and parts[-1].isdigit():
            actions[" ".join(parts[:-1])] = int(parts[-1])

    write_atomic(result_path, json.dumps(
        {"asOf": day.isoformat(), "setups": len(rows), "byAction": actions}, indent=1))
    return {"ok": True, "setups": len(rows), "byAction": actions}


def main() -> None:
    state_dir = Path(arg("--state") or "state")
    out_dir = Path(arg("--out") or "out")
    state_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    frm = date.fromisoformat(arg("--from") or "2019-01-02")
    to = date.fromisoformat(arg("--to") or date.today().isoformat())
    batch = int(arg("--batch") or "900")

    cp_path = state_dir / "checkpoint.json"
    checkpoint = json.loads(cp_path.read_text(encoding="utf-8")) if cp_path.exists() else {}
    done = set(checkpoint.get("done", []))
    last = checkpoint.get("lastSession")

    sessions = eligible_sessions(frm, to)
    todo = [d for d in sessions if d.isoformat() not in done]
    print(f"worker: {len(sessions)} eligible sessions in range, {len(done)} already done, "
          f"{len(todo)} remaining; this slice takes up to {batch}")
    if last:
        print(f"  resuming after {last}")

    started = time.time()
    processed = failed = 0
    failures: list[dict] = []

    for day in todo[:batch]:
        if time.time() - started > DEADLINE_SECONDS:
            print("  deadline reached; stopping this slice with a good checkpoint")
            break
        r = replay_one(day, out_dir)
        if r["ok"]:
            processed += 1
            done.add(day.isoformat())
            last = day.isoformat()
        else:
            failed += 1
            failures.append({"asOf": day.isoformat(), **r})
            print(f"  {day}: FAILED at {r['stage']}: {r.get('error', '')[:160]}")
        # After every session, not at the end: a slice killed between two sessions resumes from
        # the one it actually finished.
        write_atomic(cp_path, json.dumps({
            "lastSession": last,
            "sessionsDone": len(done),
            "done": sorted(done),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, indent=1))
        if processed and processed % 25 == 0:
            rate = (time.time() - started) / processed
            print(f"  {processed} done this slice, {rate:.1f}s a session")

    elapsed = time.time() - started
    remaining = len(sessions) - len(done)
    progress = {
        "lastSession": last,
        "sessionsDoneTotal": len(done),
        "eligibleTotal": len(sessions),
        "remaining": remaining,
        "processedThisSlice": processed,
        "failedThisSlice": failed,
        "secondsThisSlice": round(elapsed, 1),
        "secondsPerSession": round(elapsed / processed, 1) if processed else None,
        "coveragePct": round(100 * len(done) / len(sessions), 2) if sessions else None,
        "failures": failures[:20],
        "heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_atomic(state_dir / "progress.json", json.dumps(progress, indent=1))
    print(json.dumps({k: v for k, v in progress.items() if k != "failures"}, indent=1))
    # A slice that failed every session it tried is a problem worth a red run; one that failed a
    # few names is data about those names and the next slice still has work to do.
    if processed == 0 and failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
