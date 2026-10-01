"""Run the data jobs in the order a refresh needs them.

    python jobs/run.py daily    prices and news for both exchanges, then rankings, then
                                the confidence grades, the condition reads and what has
                                happened to the reasons behind them, the move attribution,
                                the bounded graph walk, the written lines and the event
                                windows
    python jobs/run.py weekly   the daily run plus the full PSX history backfill, all five
                                product signal sources and the marketplace rankings
    python jobs/run.py seed     the reference lists only, for a first run

Each step is a separate process on purpose. A rate limited source that fails should not
undo the rows an earlier step already committed, and the exit code should tell a scheduler
whether the whole run was healthy.

Daily is what the site depends on. Weekly adds the product signals, because Reddit and
Wikipedia rate limit and asking them every day gets the site nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# psx runs before rank for the same reason prices does: the ranking job reads closes out
# of PriceSnapshot and cannot rank a Karachi sector whose prices arrive after it.
# events runs before analysis and not after it, because analysis writes the sentence that
# sits under each event's table and has to read the rows that table is built from. Running
# it the other way round would print last week's event lines over this week's numbers.
# human reads the News rows prices has just written, so it follows prices rather than
# leading it, and accuracy follows human so a reading is in the log before the job that
# measures logged readings runs. Neither touches the network: both are arithmetic over rows
# already stored, which is why they sit in the daily group without adding a request to it.
DAILY = [
    ("prices", ["yahoo", "crypto", "news"]),
    ("psx", ["recent"]),
    # analogs reads the closes the two price jobs have just written, so it follows them.
    # Arithmetic over stored rows, no network.
    ("analogs", []),
    # upcoming asks the provider's company calendar, which is the one forward looking source
    # here. Daily rather than weekly because a date that moves is worth catching the day it
    # moves, and a reminder set for a date that has changed is worse than none.
    ("upcoming", []),
    # lifecycle follows upcoming, because a date has to be discovered before it can be
    # advanced, and it precedes rank so an event that resolves is frozen and measured in the
    # same run that resolved it rather than a day later.
    ("lifecycle", []),
    ("rank", []),
    ("confidence", ["rankings"]),
    ("events", []),
    # lineage runs before human, because the catalyst decision counts stories and stories do
    # not exist until the clustering has run. Running it the other way round would count
    # today's syndication as today's news.
    ("lineage", []),
    ("human", []),
    # setup reads prices, the news reading and the analogs, so it is last of the readers and
    # runs after all three. Rules over stored rows, no network.
    ("setup", []),
    # thesis reads the run of setup rows including the one just written, so it follows setup
    # directly. Running it before would compare today against a run that ends yesterday and
    # miss the day a reason broke.
    ("thesis", []),
    # attribution needs every asset's closes, which both price jobs have written by now. It
    # does not read setup, but it sits here so the three reading jobs are one block.
    ("attribution", []),
    # graph walks out from the catalysts human flagged, so it follows human. Arithmetic over
    # stored relationship rows, no network.
    ("graph", []),
    # intraday is last of the fetchers, not first, because its active set is chosen from what
    # everything above just found: a directional read, a live thesis, an unusual move, a
    # flagged catalyst, a graph neighbour, a date within three days. Running it earlier would
    # select on yesterday's findings and spend the request budget on the wrong assets.
    ("intraday", []),
    # horizons reads the bars intraday has just written, so it follows it. It also writes the
    # target ranges for every horizon including the swing read setup.py produced earlier, which
    # is why it is the last of the reasoning jobs rather than sitting beside setup.
    ("horizons", []),
    # investigate runs after everything it reads: the attribution it reasons over, the graph
    # neighbourhood, the clustered stories, the analogs and the intraday bars. It is the last
    # reasoning step for that reason, and it makes no network request of its own.
    ("investigate", []),
    ("accuracy", []),
    ("audit", []),
    ("analysis", []),
]

WEEKLY = [
    ("prices", ["yahoo", "crypto", "news"]),
    ("psx", ["full"]),
    ("signals", ["trends", "wiki", "hn", "news", "reddit"]),
    ("marketplace", []),
    # geo asks Trends too, so it sits behind marketplace rather than next to signals: the
    # Amazon fetch in between is several minutes of asking a different host, which is the
    # cheapest separation available between two runs at the same rate limited source.
    ("geo", []),
    ("analogs", []),
    ("upcoming", []),
    ("lifecycle", []),
    ("rank", []),
    ("confidence", ["rankings"]),
    ("events", []),
    ("lineage", []),
    ("human", []),
    ("setup", []),
    ("thesis", []),
    ("attribution", []),
    ("graph", []),
    ("intraday", []),
    # horizons reads the bars intraday has just written, so it follows it. It also writes the
    # target ranges for every horizon including the swing read setup.py produced earlier, which
    # is why it is the last of the reasoning jobs rather than sitting beside setup.
    ("horizons", []),
    # investigate runs after everything it reads: the attribution it reasons over, the graph
    # neighbourhood, the clustered stories, the analogs and the intraday bars. It is the last
    # reasoning step for that reason, and it makes no network request of its own.
    ("investigate", []),
    ("accuracy", []),
    ("audit", []),
    ("analysis", []),
]

GROUPS ={"seed": [[("seed", [])]], "daily": [DAILY], "weekly": [WEEKLY]}


def run(script: str, args: list[str]) -> tuple[int, float]:
    """Run one step, streaming its output, and return (exit code, seconds).

    Streaming rather than capturing: a job that sits on the network for twenty minutes has
    to be visible while it does it, and a captured run looks identical to a hung one until
    it ends. The cost is that the failing step's own error is buried wherever it happened,
    which `report` exists to undo.
    """
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
    return done.returncode, took


def report(which: str, results: list[tuple[str, int, float]]) -> list[str]:
    """Print every step with its exit code, and return the names that failed.

    This exists because of a real problem rather than for tidiness. `run.py` continues past a
    failed step on purpose, so a run of fourteen jobs where one fails exits non-zero with the
    answer to "which one" scattered through several thousand lines of streamed output. The
    table below is the last thing in the log, so the question is answerable from the tail of
    it without reading the rest.

    When GitHub supplies a step summary file the same table is written there, which puts it
    on the run's own page instead of inside the log.
    """
    width = max(len(name) for name, _, _ in results)
    lines = [f"run {which}: {len(results)} steps"]
    for name, code, took in results:
        state = "ok" if code == 0 else f"FAILED exit {code}"
        lines.append(f"  {name:<{width}}  {took / 60:>5.1f} min  {state}")

    failed = [name for name, code, _ in results if code != 0]
    if failed:
        lines.append("")
        lines.append(
            f"{len(failed)} of {len(results)} steps failed: {', '.join(failed)}. The rows the "
            "other steps committed are kept, so the site is serving its last good data rather "
            "than nothing."
        )
        lines.append(
            "Search this log for '=== " + failed[0] + "' to reach the first failure's own "
            "output."
        )

    print()
    for line in lines:
        print(line)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write("## Data jobs\n\n```\n" + "\n".join(lines) + "\n```\n")
        except OSError as e:  # noqa: BLE001 - a summary that cannot be written is not a failure
            print(f"  could not write the step summary: {e}")
    return failed


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if which not in GROUPS:
        print(f"unknown group {which}, choose from {', '.join(GROUPS)}")
        raise SystemExit(2)

    results: list[tuple[str, int, float]] = []
    for plan in GROUPS[which]:
        for script, args in plan:
            code, took = run(script, args)
            label = script if not args else f"{script} {' '.join(args)}"
            results.append((label, code, took))

    # A partial failure still leaves the site serving the last good rows, so this is reported
    # rather than retried blindly.
    if report(which, results):
        raise SystemExit(1)
    print(f"run {which} finished, every step ok")


if __name__ == "__main__":
    main()
