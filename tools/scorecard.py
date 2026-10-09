"""Score matured decisions against the direction and the stop they stated.

The other half of the accuracy loop. `matureRows` in `tools/decide.mjs` already returns to each
logged decision and records what the price did after it -- `move1Pct`, `move5Pct`, `move20Pct` --
but nothing judged those moves against what the decision actually claimed. A move is a
measurement; a score is a measurement compared with a stated intention, and only the second
answers "were these readings any good".

What it will and will not do:

  * It scores only rows whose window has elapsed and whose move is stored. A row still open is
    counted as pending and never as a miss -- treating "not yet known" as "wrong" is the same
    conflation this site spent a session removing from WAIT.
  * It judges `stopped` from stored closes, not from an assumed intraday path. The schema keeps
    daily bars, so a stop is recorded as hit when a CLOSE in the window finished past it. An
    intraday wick that recovered is invisible here, and claiming otherwise would be inventing a
    path nothing measured.
  * **It refuses to print a rate below MIN_SAMPLE.** A hit rate over nine rows is noise with a
    percent sign, and publishing it would be exactly the false confidence the rest of the system
    is built to avoid. Below the floor it prints the counts and says the sample is too small.
  * **The rows are not independent trials, and it says so every time.** One decision per asset per
    session means the same name recurs daily while its setup holds, so a six-day log of 197 scored
    rows is closer to 60 names observed repeatedly than to 197 experiments. The distinct-name count
    is printed beside the row count for that reason: the smaller number is the one that bounds what
    can be concluded, and a rate computed over the larger one would overstate its own weight.

Writes nothing. The scores are derived from stored rows on demand, so there is no new column to
migrate and no second copy of the truth to drift.

Run: python tools/scorecard.py [--window 1|5|20]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

from nbt import db  # noqa: E402

# Below this many scored rows, no rate is published.
#
# 30 is the smallest sample where a share has a standard error under 10 points, which is the
# coarsest number anyone could act on. It is a floor on publication, not on measurement: the
# counts are printed at any size, because knowing the sample is small is itself useful.
MIN_SAMPLE = 30

WINDOWS = {1: ("move1Pct", "measured1On"), 5: ("move5Pct", "measured5On"),
           20: ("move20Pct", "measured20On")}


# --- the scoring, as plain functions ----------------------------------------------------------
#
# Pulled out of `main` so the judgement can be tested without a database. Everything below takes
# numbers and returns a word; nothing here holds a cursor. That matters more here than in most
# files: this is the module that decides whether the site's own readings were any good, and a
# scorer that quietly mislabels a stop is worse than no scorecard at all, because it publishes a
# number nobody can see is wrong.


def band_in(series, after, through):
    """Lowest and highest close strictly after `after` and up to `through`. `(None, None)` for none.

    `series` is `(date, close)` pairs for one asset in any order. The window is half open on
    purpose: the decision was taken on `after`'s close, so that close is the entry and cannot
    also be the thing that stopped it out.
    """
    if after is None or through is None:
        return None, None
    inside = [c for d, c in series if c is not None and after < d <= through]
    if not inside:
        return None, None
    return min(inside), max(inside)


def stop_was_hit(action, invalidation, lo, hi):
    """Did a close inside the window finish past the stated stop?

    From stored daily closes, never from an assumed intraday path -- the schema keeps daily bars,
    so an intraday wick that recovered is invisible here and claiming otherwise would be
    inventing a path nothing measured.

    False whenever the question cannot be asked: no stop stored, or no closes in the window. A
    missing measurement must not score as a survived stop, which is what any other default here
    would quietly do.
    """
    if invalidation is None or lo is None or hi is None:
        return False
    if action == "LONG":
        return lo <= invalidation
    if action == "SHORT":
        return hi >= invalidation
    return False


def wilson(successes, n, z=1.96):
    """A 95% interval for a share, by Wilson's method. `(None, None)` when n is 0.

    Wilson and not the textbook normal approximation, for the reason that approximation fails
    exactly where this scorer lives: at small n and at shares near 0 or 1 it produces intervals
    that run past 100% or below 0%, and an accuracy report that claims a hit rate "between 82%
    and 104%" has discredited itself in the one place it was trying to be careful. Wilson's
    interval stays inside the unit interval by construction and is the standard small-sample
    choice for exactly this.

    It is a frequentist interval and not a posterior, and the distinction is worth keeping
    rather than calling this Bayesian: it answers "which shares would not be rejected by this
    sample", which is the question a reader of a hit rate actually has. With a uniform prior the
    Beta posterior's central interval is close enough that the extra machinery would buy
    nothing but a word.
    """
    if n <= 0:
        return None, None
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def effective_n(rows, names):
    """How many observations the interval may be computed over. The smaller of the two.

    **This is the correction that makes the interval mean something here**, and it is the
    module's own stated caveat finally obeyed by the arithmetic rather than only by the prose.
    One decision per asset per session means the same name recurs daily while its setup holds,
    so a six-day log of 197 scored rows is closer to 60 names observed repeatedly than to 197
    experiments. An interval over 197 is about a third narrower than one over 60 and is the
    wrong width -- it would let a run of luck on one name read as evidence about the engine.

    Taking the distinct-name count is conservative rather than exact: the true effective sample
    is somewhere between the two and depends on how correlated a name's own sessions are, which
    nothing here measures. Erring to the smaller number errs towards refusing to publish, which
    is the right direction for a figure whose whole purpose is to say whether these readings can
    be believed yet.
    """
    return max(0, min(rows, names))


def spans_chance(lo, hi, null=0.5):
    """Does the interval contain the share a coin would produce? Then it is not yet evidence.

    This is the whole of the "no noise-chasing" rule and it is one line: a hit rate of 58% over
    an interval running from 44% to 71% is a sample that has not yet distinguished the engine
    from chance, and printing "58%" beside it invites exactly the reading the interval exists to
    forbid. Null is 0.5 because the scored population is directional calls judged against the
    sign of the move -- two outcomes, and `flat` and `stopped` are counted separately.
    """
    if lo is None or hi is None:
        return True
    return lo <= null <= hi


def verdict_of(action, move, was_stopped):
    """One of "stopped", "flat", "right", "wrong", or None when the row is not yet scorable.

    The order is the judgement. A stop is checked first and beats the move, because a position
    that was taken out at the stop did not get to find out where the price finished -- scoring it
    on the move would credit a trade the stated plan had already closed.

    None for an unmeasured move, and never "wrong". Treating "not yet known" as a miss is the
    same conflation this site spent a session removing from WAIT.
    """
    if was_stopped:
        return "stopped"
    if move is None:
        return None
    if move == 0:
        return "flat"
    return "right" if (action == "LONG") == (move > 0) else "wrong"


def main() -> int:
    window = 5
    if "--window" in sys.argv:
        window = int(sys.argv[sys.argv.index("--window") + 1])
    if window not in WINDOWS:
        print(f"--window must be one of {sorted(WINDOWS)}")
        return 2
    move_col, on_col = WINDOWS[window]

    conn = db()
    conn.rollback()
    conn.read_only = True
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT d.id, a.symbol, d.action, d.gate, d.confidence, d."periodEnd",
               d."baseClose", d.invalidation, d."{move_col}" AS move, d."{on_col}" AS measured_on,
               d.status, d."assetId"
          FROM "DecisionLog" d JOIN "Asset" a ON a.id = d."assetId"
         WHERE d.action <> 'WAIT'
         ORDER BY d."periodEnd", a.symbol
        """
    )
    rows = cur.fetchall()

    pending = [r for r in rows if r["move"] is None]
    scored = [r for r in rows if r["move"] is not None]

    print(f"directional decisions logged: {len(rows)}")
    print(f"  window {window} session(s): {len(scored)} matured, {len(pending)} still pending")
    if rows:
        print(f"  logged from {rows[0]['periodEnd']} to {rows[-1]['periodEnd']}")

    if not scored:
        print(
            f"\nNot enough matured rows to score at {window} sessions. "
            "No rate is published, because there is nothing to publish."
        )
        conn.close()
        return 0

    # Did a close inside the window finish past the stop? **One query for the whole set**, which
    # this comment claimed while the code underneath it issued one per scored row.
    #
    # It was a round trip per row against a free tier endpoint, so the cost grew with the length
    # of the log rather than with the size of the universe -- a scorecard that gets slower every
    # day it runs. The same fault, and the same fix, as the eleven jobs the ninth session
    # rewrote: read the series the windows are slices of, once, and take the slices in memory.
    #
    # Bounded on both sides rather than read whole. Every window lies between the oldest decision
    # and the newest measurement, so those two dates bound the read, and the assets are the ones
    # actually scored rather than the whole table.
    windowed = [r for r in scored if r["invalidation"] is not None and r["measured_on"] is not None]
    series: dict[str, list] = {}
    if windowed:
        cur.execute(
            """
            SELECT "assetId", date, close FROM "PriceSnapshot"
             WHERE "assetId" = ANY(%s) AND close IS NOT NULL
               AND date > %s AND date <= %s
            """,
            (
                sorted({r["assetId"] for r in windowed}),
                min(r["periodEnd"] for r in windowed),
                max(r["measured_on"] for r in windowed),
            ),
        )
        for p in cur.fetchall():
            series.setdefault(p["assetId"], []).append((p["date"], p["close"]))

    stopped: set[str] = set()
    for r in windowed:
        lo, hi = band_in(series.get(r["assetId"], []), r["periodEnd"], r["measured_on"])
        if stop_was_hit(r["action"], r["invalidation"], lo, hi):
            stopped.add(r["id"])

    tally: Counter[str] = Counter()
    by_conf: dict[str, Counter[str]] = {}
    for r in scored:
        verdict = verdict_of(r["action"], r["move"], r["id"] in stopped)
        if verdict is None:
            # `scored` is already filtered to rows with a move, so this is unreachable on the
            # live table. It is handled rather than asserted because the alternative is a
            # KeyError inside a Counter on a row shape nobody expected, and a scorecard that
            # falls over on one odd row publishes nothing about the several hundred good ones.
            continue
        tally[verdict] += 1
        by_conf.setdefault(r["confidence"], Counter())[verdict] += 1

    print(f"\n--- scored at {window} session(s), against the direction and the stop as stated")
    for k in ("right", "wrong", "stopped", "flat"):
        if tally[k]:
            print(f"    {k:8} {tally[k]:4}")

    n = sum(tally.values())
    decided = tally["right"] + tally["wrong"]
    names = len({r["symbol"] for r in scored})
    sessions = len({r["periodEnd"] for r in scored})
    print()
    print(
        f"    {n} rows span {names} distinct names over {sessions} sessions, so these are "
        f"repeated observations of {names} names rather than {n} independent trials."
    )
    if n < MIN_SAMPLE:
        print(
            f"\n{n} scored rows is under the {MIN_SAMPLE} needed before a rate is published. "
            "Counts only."
        )
    elif decided:
        print(f"\n    went the stated way: {tally['right']} of {decided} ({tally['right']/decided:.0%})")
        print(f"    stopped out first  : {tally['stopped']}")
        # The interval, over the effective sample rather than the row count, and the sentence
        # that says what it means. A rate printed without one is a number a reader has no way to
        # weigh, which is principle 3: sample size decides how much weight a parallel earns, and
        # it is never left unstated.
        eff = effective_n(decided, names)
        lo, hi = wilson(round(tally["right"] * eff / decided), eff)
        if lo is None:
            print("    no interval: nothing matured")
        else:
            print(
                f"    95% interval       : {lo:.0%} to {hi:.0%}, over {eff} effective "
                f"observations ({names} distinct names across {decided} decided rows)"
            )
            print(
                "    this does not yet separate the engine from chance: the interval spans 50%."
                if spans_chance(lo, hi)
                else "    the interval clears 50%, so the sample does say something."
            )
        for conf, c in sorted(by_conf.items()):
            d = c["right"] + c["wrong"]
            if d >= MIN_SAMPLE:
                g_names = len({r["symbol"] for r in scored if r["confidence"] == conf})
                g_eff = effective_n(d, g_names)
                g_lo, g_hi = wilson(round(c["right"] * g_eff / d), g_eff)
                band = "" if g_lo is None else f"  [{g_lo:.0%}-{g_hi:.0%}]"
                flag = "" if g_lo is None or not spans_chance(g_lo, g_hi) else "  spans 50%"
                print(f"      {conf:7} {c['right']}/{d} ({c['right']/d:.0%}){band}{flag}")
            else:
                print(f"      {conf:7} {c['right']}/{d} — under the floor, no rate")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
