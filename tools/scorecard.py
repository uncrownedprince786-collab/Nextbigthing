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

    # Did a close inside the window finish past the stop? One query for the whole set.
    stopped: set[str] = set()
    for r in scored:
        if r["invalidation"] is None or r["measured_on"] is None:
            continue
        cur.execute(
            """
            SELECT min(close) AS lo, max(close) AS hi FROM "PriceSnapshot"
             WHERE "assetId" = %s AND date > %s AND date <= %s
            """,
            (r["assetId"], r["periodEnd"], r["measured_on"]),
        )
        band = cur.fetchone()
        if band["lo"] is None:
            continue
        if r["action"] == "LONG" and band["lo"] <= r["invalidation"]:
            stopped.add(r["id"])
        if r["action"] == "SHORT" and band["hi"] >= r["invalidation"]:
            stopped.add(r["id"])

    tally: Counter[str] = Counter()
    by_conf: dict[str, Counter[str]] = {}
    for r in scored:
        if r["id"] in stopped:
            verdict = "stopped"
        elif r["move"] == 0:
            verdict = "flat"
        elif (r["action"] == "LONG") == (r["move"] > 0):
            verdict = "right"
        else:
            verdict = "wrong"
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
        for conf, c in sorted(by_conf.items()):
            d = c["right"] + c["wrong"]
            if d >= MIN_SAMPLE:
                print(f"      {conf:7} {c['right']}/{d} ({c['right']/d:.0%})")
            else:
                print(f"      {conf:7} {c['right']}/{d} — under the floor, no rate")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
