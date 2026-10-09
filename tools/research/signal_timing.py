"""How late are the live directional signals? Read-only.

The directive asked for signals that are forward-looking rather than "lagging historical indicators
that merely describe price action that has already occurred". No rule built from stored prices can
be guaranteed to be the first kind, and this project's own first principle says the same: the site
reports a trend, never a forecast. What can be done is **measure** how much of each signal's move
was already behind it when it printed, and print that next to the signal.

For every current LONG and SHORT it reports, from stored closes only:

  * stack age    sessions the 20/50-day stack (close beyond the 20-day beyond the 50-day, in the
                 signal's direction) has held without a break. Zero means it formed today.
  * already made the 20-session return in the signal's direction, as a share of the move: a LONG
                 up 14% in 20 sessions has 14 points of its trend behind it.

and splits both by whether an entry trigger (the one confirmation that is an event on the latest
bar rather than a standing state) was among the legs that backed the call.

Nothing is written.

Run: python tools/research/signal_timing.py
"""

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
import nbt

FAST, SLOW = 20, 50


def stack_age(closes: list[float], direction: str) -> int | None:
    """Consecutive sessions, ending at the newest, on which the 20/50 stack held in `direction`.

    "up" is close > 20-day mean > 50-day mean; "down" is the mirror. 0 when it does not hold on the
    newest session at all, which is the answer for a signal carried by a bias rather than a stack.
    None when there are too few closes to form the 50-day mean even once.
    """
    n = len(closes)
    if n < SLOW + 1:
        return None
    age = 0
    for j in range(n - 1, SLOW - 2, -1):
        fast = sum(closes[j - FAST + 1 : j + 1]) / FAST
        slow = sum(closes[j - SLOW + 1 : j + 1]) / SLOW
        held = (closes[j] > fast > slow) if direction == "up" else (closes[j] < fast < slow)
        if not held:
            break
        age += 1
    return age


def made(closes: list[float], direction: str) -> float | None:
    """The 20-session return in the signal's direction, in percent. Positive is move already made."""
    if len(closes) < FAST + 1 or closes[-1 - FAST] <= 0:
        return None
    r = (closes[-1] / closes[-1 - FAST] - 1.0) * 100.0
    return r if direction == "up" else -r


def main() -> int:
    conn = nbt.db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d."assetId", a.symbol, d.action, d.gate, d.legs, d.intent
          FROM "DecisionLog" d JOIN "Asset" a ON a.id = d."assetId"
         WHERE d.action IN ('LONG', 'SHORT') OR d.gate = 'stop-crossed'
        """
    )
    decisions = cur.fetchall()
    if not decisions:
        print("No directional decisions are logged.")
        return 0

    ids = sorted({d["assetId"] for d in decisions})
    cur.execute(
        'SELECT "assetId", date, close FROM "PriceSnapshot" WHERE "assetId" = ANY(%s) AND close IS NOT NULL '
        'ORDER BY "assetId", date ASC',
        (ids,),
    )
    series: dict[str, list[float]] = {}
    for r in cur.fetchall():
        series.setdefault(r["assetId"], []).append(float(r["close"]))

    rows = []
    for d in decisions:
        closes = series.get(d["assetId"], [])
        # A refusal is read in the direction it refused, so the signals the stop gate removed can be
        # compared with the ones it kept: if they are mostly old trends in a pullback, the gate is
        # filtering out the late ones as well as the invalid ones.
        side = d["action"] if d["action"] in ("LONG", "SHORT") else ("LONG" if d["intent"] == "up" else "SHORT")
        direction = "up" if side == "LONG" else "down"
        age, mv = stack_age(closes, direction), made(closes, direction)
        legs = (d["legs"] or "").split(",")
        rows.append({"gate": d["gate"], "age": age, "made": mv, "trigger": "trigger" in legs})

    def line(label: str, group: list[dict]) -> None:
        ages = [r["age"] for r in group if r["age"] is not None]
        mades = [r["made"] for r in group if r["made"] is not None]
        if not ages:
            print(f"  {label:34} {len(group):>4}  (too little history to measure)")
            return
        late = sum(1 for a in ages if a > 20) / len(ages)
        print(
            f"  {label:34} {len(group):>4}  stack age median {statistics.median(ages):>4.0f}  "
            f"older than 20 sessions {late:>4.0%}  move already made median {statistics.median(mades):>+6.1f}%"
        )

    kept = [r for r in rows if r["gate"] != "stop-crossed"]
    print(f"{len(kept)} live directional signals, and {len(rows) - len(kept)} the stop gate refused\n")
    print(f"  {'':34} {'n':>4}")
    line("printed (all kept)", kept)
    for gate in sorted({r["gate"] for r in kept}):
        line(f"gate: {gate}", [r for r in kept if r["gate"] == gate])
    line("REFUSED: stop already crossed", [r for r in rows if r["gate"] == "stop-crossed"])
    print()
    line("an entry trigger backed it", [r for r in kept if r["trigger"]])
    line("no entry trigger", [r for r in kept if not r["trigger"]])
    print(
        "\nRead: a trigger-backed signal is the only kind that is an event on the latest bar. If its stack "
        "age is not\nmaterially lower than the rest, the trigger is confirming a trend that is already old "
        "and is not catching starts."
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
