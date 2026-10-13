"""Replay a list of past sessions end to end and record what each one actually produced.

    python tools/replay_batch.py --dates 2019-06-14,2024-06-14 --out <dir>
    python tools/replay_batch.py --from 2019-01-02 --to 2026-10-01 --every 60 --out <dir>

For each date it runs `jobs/setup.py --as-of` to reconstruct that session's setups, feeds them to
`tools/decide.mjs --as-of --setups-file`, and writes the decisions as JSONL beside a manifest.

Why the counts are the point
----------------------------
A replay is only worth running if it produces examples that can be labelled, and "how many" is a
measurement rather than a projection. This writes the real distribution per date -- how many
setups were reconstructed, how many were directional, and which gate refused each decision -- so
the usable sample size is read off a completed run instead of multiplied out from one day.

Nothing is written to any database. `setup.py --as-of` prints rather than inserts and
`decide.mjs --as-of` forces its own dry run, so this is read-only by construction on both halves.

Resumable: a date whose output file already exists is skipped unless `--force` is given.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The rule version every row is stamped with, so a dataset can be tied to the code that made it.
RULES = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
).stdout.strip() or "unknown"


def arg(name: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def sessions(frm: date, to: date, every: int) -> list[date]:
    """Weekday sessions from `frm` to `to`, one every `every` days."""
    out, d = [], frm
    while d <= to:
        if d.isoweekday() < 6:
            out.append(d)
        d += timedelta(days=every)
    return out


def run_one(day: date, out_dir: Path, force: bool) -> dict:
    setups_path = out_dir / f"setups-{day}.jsonl"
    decisions_path = out_dir / f"decisions-{day}.json"
    if decisions_path.exists() and not force:
        return json.loads(decisions_path.read_text(encoding="utf-8"))

    setup = subprocess.run(
        [sys.executable, "jobs/setup.py", "--as-of", day.isoformat()],
        cwd=ROOT, capture_output=True, text=True, timeout=1800,
    )
    rows = [json.loads(l) for l in setup.stdout.splitlines() if l.strip().startswith("{")]
    setups_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    states: dict[str, int] = {}
    for r in rows:
        states[r["state"]] = states.get(r["state"], 0) + 1

    decide = subprocess.run(
        ["node", "tools/decide.mjs", "--as-of", day.isoformat(), "--setups-file", str(setups_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=1800,
    )
    actions, gates, section = {}, {}, None
    for line in decide.stdout.splitlines():
        s = line.strip()
        if s.startswith("by action:"):
            section = "a"; continue
        if s.startswith("by gate:"):
            section = "g"; continue
        if s.startswith("by ") or s.startswith("developing") or not s:
            if s.startswith("by "):
                section = None
            continue
        parts = s.split()
        if section and len(parts) >= 2 and parts[-1].isdigit():
            (actions if section == "a" else gates)[" ".join(parts[:-1])] = int(parts[-1])

    record = {
        "asOf": day.isoformat(),
        "rulesVersion": RULES,
        "setups": {"total": len(rows), "byState": states,
                   "directional": states.get("buy", 0) + states.get("short", 0)},
        "decisions": {"byAction": actions, "byGate": gates},
        # Inputs that exist for this date, named rather than assumed. News, HumanSignal, MacroGate
        # and the factor/analog tables hold only a few recent days, so a 2019 replay runs without
        # them and must say so: this is a reduced-input decision, not the one the live system
        # would have published that day.
        "inputsOmitted": ["News", "HumanSignal", "MacroGate", "AssetFactor", "AssetAnalog"],
        "setupStderr": setup.stderr.strip()[-300:] or None,
        "decideFailed": decide.returncode != 0,
    }
    decisions_path.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def main() -> None:
    out_dir = Path(arg("--out") or (ROOT.parent / "nbt-private" / "replay"))
    out_dir.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv

    if arg("--dates"):
        days = [date.fromisoformat(d) for d in arg("--dates").split(",")]
    else:
        days = sessions(
            date.fromisoformat(arg("--from") or "2019-01-02"),
            date.fromisoformat(arg("--to") or date.today().isoformat()),
            int(arg("--every") or "60"),
        )

    print(f"replay: {len(days)} sessions, rules {RULES}, out {out_dir}")
    records = []
    for day in days:
        rec = run_one(day, out_dir, force)
        d = rec["decisions"]["byAction"]
        print(f"  {rec['asOf']}  setups {rec['setups']['total']:4} "
              f"(directional {rec['setups']['directional']:3})  "
              f"decisions LONG {d.get('LONG', 0):3} SHORT {d.get('SHORT', 0):3} WAIT {d.get('WAIT', 0):4}")
        records.append(rec)

    manifest = {
        "dataset": "replay-decisions",
        "version": 1,
        "rulesVersion": RULES,
        "generatedSessions": len(records),
        "dateRange": [records[0]["asOf"], records[-1]["asOf"]] if records else None,
        "totals": {
            "setups": sum(r["setups"]["total"] for r in records),
            "directionalSetups": sum(r["setups"]["directional"] for r in records),
            "LONG": sum(r["decisions"]["byAction"].get("LONG", 0) for r in records),
            "SHORT": sum(r["decisions"]["byAction"].get("SHORT", 0) for r in records),
            "WAIT": sum(r["decisions"]["byAction"].get("WAIT", 0) for r in records),
        },
        "inputsOmitted": ["News", "HumanSignal", "MacroGate", "AssetFactor", "AssetAnalog"],
        "limitation": (
            "Reduced-input replay. The confirmation tables hold only recent days, so these are "
            "not the decisions the live system would have published on these dates."
        ),
        "reproduce": "python tools/replay_batch.py --dates <csv> --out <dir>",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest["totals"], indent=1))
    print(f"manifest: {out_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
