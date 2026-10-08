"""Run the data jobs in the order a refresh needs them.

    python jobs/run.py <group> [--chunk i/N]

    Groups, one source or one concern each:
      crypto      the crypto closes
      us-prices   the US closes
      psx         the Karachi closes, recent window
      news        the news fetch and clustering
      products    the five product signal sources, the marketplace ranks and the geo read
      decision    everything that reasons over rows already stored, ending in the written lines
      audit       the coverage flags

    And the three original lanes, unchanged:
      daily       prices and news for both exchanges, then rankings, then the confidence
                  grades, the condition reads and what has happened to the reasons behind
                  them, the move attribution, the bounded graph walk, the written lines and
                  the event windows
      weekly      the daily run plus the full PSX history backfill, all five product signal
                  sources and the marketplace rankings
      seed        the reference lists only, for a first run

Each step is a separate process on purpose. A rate limited source that fails should not
undo the rows an earlier step already committed, and the exit code should tell a scheduler
whether the whole run was healthy.

The small groups exist because one giant job is one transaction's worth of risk: a blocked
source at minute fifty costs the hour. A group per source commits per source, so a retry asks
again for the one slice that failed instead of the whole afternoon. `--chunk 3/8` cuts a group
again, into eight slices of its work list, so a lane that cannot finish inside a runner's
timeout is eight lanes that can — and because the slicing is a property of the symbol rather
than of the order a query returned (see runlog.slice_of), a retry of slice 3 covers exactly
what the first attempt of slice 3 would have.

Daily is what the site depends on. Weekly adds the product signals, because Reddit and
Wikipedia rate limit and asking them every day gets the site nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import runlog

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
    # factors reads the closes the two price jobs have just written and nothing else, so it is
    # the first of the reasoning jobs. Everything downstream that wants a measured number about
    # a session -- the volume ratio that confirms a direction, the peer-relative strength that
    # can contradict one -- reads its row rather than deriving its own, which is the only way
    # the panel, the lists and the audit can be made to agree about what a day looked like.
    ("factors", []),
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
    # retention is last of everything, and deliberately after analysis rather than before it:
    # it caps the per-session working set, and a sweep that ran first would prune rows the
    # same run was about to read. It touches nothing the accuracy loop measures -- the list of
    # what it will and will not delete is written out in the job itself.
    ("retention", []),
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
    # factors reads the closes the two price jobs have just written and nothing else, so it is
    # the first of the reasoning jobs. Everything downstream that wants a measured number about
    # a session -- the volume ratio that confirms a direction, the peer-relative strength that
    # can contradict one -- reads its row rather than deriving its own, which is the only way
    # the panel, the lists and the audit can be made to agree about what a day looked like.
    ("factors", []),
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

# The small groups. Every one of them is a selection over the steps DAILY and WEEKLY already
# define, never a second copy of a step: the jobs themselves are not touched here, and the
# argument lists below are the same argument lists those lanes pass.
#
# The fetchers are named explicitly because DAILY asks prices.py for all three lanes in one
# process and the point of the split is that it should not have to. The reasoning chain is
# filtered out of DAILY instead of being retyped, so the ordering comments above — intraday
# after the jobs its active set comes from, thesis after setup, graph after human — keep
# holding for `decision` without anyone having to remember them twice.
# `upcoming` is in this set because it is a fetcher, even though its name reads like a
# derivation. It calls yfinance once per Yahoo-sourced stock and ETF with a forced 0.5s sleep
# between calls, which is 126 requests today and grows with every name added to the universe.
#
# That is what broke the decision lane. On 2026-10-04 the universe went from 160 names to 240;
# the `decision` group crossed its 20 minute budget on the next run and was killed at 1197s, and
# again the run after that. Two sessions have no DecisionLog rows at all as a result -- the one
# output the whole site is built around, absent, while every input table was fresh.
#
# A per-asset network loop does not belong in the group whose entire design claim is that it
# cannot be blocked by a venue. Moving it here restores that claim and takes the unbounded part
# of the runtime out of the critical path. A company calendar changes a few times a year, so it
# rides its own schedule and the decision reads whatever was stored last.
FETCH_STEPS = {"prices", "psx", "signals", "marketplace", "geo", "upcoming"}

# decision is DAILY minus the fetchers and minus audit: the arithmetic over rows already
# stored, in DAILY's order. audit is its own group because a coverage flag is a judgement about
# a finished fetch, and running it inside the lane it judges reads the data mid-write.
DECISION = [(script, args) for script, args in DAILY if script not in FETCH_STEPS | {"audit"}]

PRODUCTS = [
    ("signals", ["trends", "wiki", "hn", "news", "reddit"]),
    ("marketplace", []),
    # geo asks Trends too, so it keeps the Amazon fetch between itself and signals for the same
    # reason WEEKLY does: several minutes of asking a different host is the cheapest separation
    # available between two runs at the same rate limited source.
    ("geo", []),
]

GROUPS ={
    "seed": [[("seed", [])]], "daily": [DAILY], "weekly": [WEEKLY],
    "crypto": [[("prices", ["crypto"])]],
    "us-prices": [[("prices", ["yahoo"])]],
    "psx": [[("psx", ["recent"])]],
    "news": [[("prices", ["news"])]],
    "products": [PRODUCTS],
    "decision": [DECISION],
    "calendar": [[("upcoming", [])]],
    "audit": [[("audit", [])]],
}


# Which jobs understand `--chunk`. Read out of the job's own source rather than listed here on
# purpose: these files belong to other engineers, chunking is landing in them one at a time, and
# a hand-maintained list in this file would be wrong in one of two directions — passing a flag
# to a job that does not parse it yet, or silently running a whole source when the job grew the
# ability to slice it. Reading the source means the runner starts passing the flag the day the
# job starts accepting it, with no edit here.
#
# The cost is that a job which only *mentions* the flag in a comment would be treated as
# supporting it. That is the harmless direction: it is visible in the summary table and in the
# job's own usage error, where the other direction is a run that quietly fetched everything.
CHUNK_FLAG = "--chunk"
_chunk_support: dict[str, bool] = {}


def supports_chunk(script: str) -> bool:
    """Whether jobs/<script>.py parses --chunk. Cached: a group asks about the same step once."""
    if script not in _chunk_support:
        path = HERE / f"{script}.py"
        try:
            _chunk_support[script] = CHUNK_FLAG in path.read_text(encoding="utf-8")
        except OSError:
            # A missing script is a plan typo, caught by the test that walks every group. Here it
            # is only "cannot slice", and run() will report the real failure a moment later.
            _chunk_support[script] = False
    return _chunk_support[script]


def plan_with_chunk(plan: list[tuple[str, list[str]]], chunk: str | None):
    """The plan with `--chunk i/N` appended to the steps that take it.

    Returns (steps, skipped) so the summary can say which steps ran whole. A step that does not
    slice is run unsliced rather than skipped: running the whole source is the behaviour that
    existed before chunking and it is the safe one, where skipping would mean a scheduled
    `--chunk 1/8` lane silently never fetched that source at all.
    """
    if not chunk:
        return list(plan), []
    steps, skipped = [], []
    for script, args in plan:
        if supports_chunk(script):
            steps.append((script, [*args, CHUNK_FLAG, chunk]))
        else:
            steps.append((script, list(args)))
            skipped.append(script)
    return steps, skipped


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


def report(
    which: str,
    results: list[tuple[str, int, float]],
    notes: list[str] | None = None,
) -> list[str]:
    """Print every step with its exit code, and return the names that failed.

    This exists because of a real problem rather than for tidiness. `run.py` continues past a
    failed step on purpose, so a run of fourteen jobs where one fails exits non-zero with the
    answer to "which one" scattered through several thousand lines of streamed output. The
    table below is the last thing in the log, so the question is answerable from the tail of
    it without reading the rest.

    When GitHub supplies a step summary file the same table is written there, which puts it
    on the run's own page instead of inside the log.

    `notes` are lines about the run rather than about a step — which steps ignored a --chunk,
    for instance. They go in the same table because the table is the thing a maintainer reads.
    """
    width = max(len(name) for name, _, _ in results)
    lines = [f"run {which}: {len(results)} steps"]
    for name, code, took in results:
        state = "ok" if code == 0 else f"FAILED exit {code}"
        lines.append(f"  {name:<{width}}  {took / 60:>5.1f} min  {state}")
    for note in notes or []:
        lines.append(f"  note: {note}")

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


def parse_args(argv: list[str]) -> tuple[str, str | None]:
    """(group, chunk) from the command line. The group defaults to daily, the chunk to none.

    A bad --chunk is refused here rather than being handed to a job, because "3/0" reaching a
    job means one of two things and there is no way to tell which: a workflow with a typo, or a
    matrix that generated a slice that does not exist. Both want the run to stop at the gate.
    """
    args = list(argv)
    chunk = None
    if CHUNK_FLAG in args:
        at = args.index(CHUNK_FLAG)
        if at + 1 >= len(args):
            # ValueError rather than SystemExit so main reports it the same way it reports a
            # bad slice number, and both leave with 2: a usage error, not a failed fetch.
            raise ValueError(f"{CHUNK_FLAG} needs a value like 3/8")
        chunk = args[at + 1]
        del args[at : at + 2]
        runlog.parse_chunk(chunk)  # raises ValueError on anything that is not i/N
    which = args[0] if args else "daily"
    return which, chunk


def main() -> None:
    try:
        which, chunk = parse_args(sys.argv[1:])
    except ValueError as e:
        print(e)
        raise SystemExit(2)
    if which not in GROUPS:
        print(f"unknown group {which}, choose from {', '.join(GROUPS)}")
        raise SystemExit(2)

    label_which = which if not chunk else f"{which} {chunk}"
    results: list[tuple[str, int, float]] = []
    notes: list[str] = []
    for plan in GROUPS[which]:
        steps, unsliced = plan_with_chunk(plan, chunk)
        if unsliced:
            notes.append(
                f"{CHUNK_FLAG} {chunk} was not passed to {', '.join(sorted(set(unsliced)))}: "
                "those jobs do not parse it yet, so each ran its whole source once. Nothing was "
                "skipped, but N slices of this group will fetch them N times."
            )
        for script, args in steps:
            # The loop does not break on a failure, and that is the behaviour the whole design
            # rests on: every later step still runs, every step that worked keeps its committed
            # rows, and the non-zero exit is raised once at the end from `report`'s answer below.
            # Aborting here would throw away the eleven jobs that would have worked.
            code, took = run(script, args)
            step_label = script if not args else f"{script} {' '.join(args)}"
            results.append((step_label, code, took))

    # A partial failure still leaves the site serving the last good rows, so this is reported
    # rather than retried blindly. The exit code is non-zero so the workflow goes red even
    # though the run was allowed to finish.
    if report(label_which, results, notes):
        raise SystemExit(1)
    print(f"run {label_which} finished, every step ok")


if __name__ == "__main__":
    main()
