"""Run the data jobs in the order a refresh needs them.

    python jobs/run.py daily    prices and news, then rankings, then the written lines
    python jobs/run.py weekly   prices and news, then all five product signal sources,
                                then rankings and the written lines
    python jobs/run.py seed     the reference lists only, for a first run

Each step is a separate process on purpose. A rate limited source that fails should not
undo the rows an earlier step already committed, and the exit code should tell a scheduler
whether the whole run was healthy.

Daily is what the site depends on. Weekly adds the product signals, because Reddit and
Wikipedia rate limit and asking them every day gets the site nothing.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

DAILY = [
    ("prices", ["yahoo", "crypto", "news"]),
    ("rankings", []),
    ("analysis", []),
]

WEEKLY = [
    ("prices", ["yahoo", "crypto", "news"]),
    ("signals", ["trends", "wiki", "hn", "news", "reddit"]),
    ("rankings", []),
    ("analysis", []),
]

GROUPS = {"seed": [[("seed", [])]], "daily": [DAILY], "weekly": [WEEKLY]}


def run(script: str, args: list[str]) -> tuple[bool, float]:
    label = script if not args else f"{script} {' '.join(args)}"
    print(f"\n=== {label} ===", flush=True)
    started = time.monotonic()
    done = subprocess.run(
        [sys.executable, "-X", "utf8", str(HERE / f"{script}.py"), *args],
        cwd=HERE.parent,
    )
    took = time.monotonic() - started
    ok = done.returncode == 0
    print(f"=== {label}: {'ok' if ok else 'FAILED'} in {took / 60:.1f} min ===", flush=True)
    return ok, took


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if which not in GROUPS:
        print(f"unknown group {which}, choose from {', '.join(GROUPS)}")
        raise SystemExit(2)

    failures: list[str] = []
    for plan in GROUPS[which]:
        for script, args in plan:
            ok, _ = run(script, args)
            if not ok:
                failures.append(script)

    print()
    if failures:
        # A partial failure still leaves the site serving the last good rows, so this is
        # reported rather than retried blindly.
        print(f"run {which} finished with failures: {', '.join(sorted(set(failures)))}")
        raise SystemExit(1)
    print(f"run {which} finished, every step ok")


if __name__ == "__main__":
    main()
