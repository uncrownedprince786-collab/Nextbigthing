"""Which stored dates carry a corporate action nobody adjusted for, and what that spoils.

`data/foundation/price_verification/unadjusted_actions.json` holds the scan's candidates: a one-day
move beyond 30% whose ratio is within 4% of a simple split factor. A stored series that was never
adjusted for that split carries a one-day "return" that no holder experienced, and every factor
measured across the date is wrong.

Two consumers read it and they must agree about what it says, which is why the reading lives here
rather than in each of them: `assemble.py` flags the rows, and `pit_features.py` keeps the
fabricated days out of the analog match pool.

The one candidate class that is not an action
---------------------------------------------
The scan asked a second provider what it saw on the same date. Where both independent providers
report the same large move, the move is a real one and the date is not an unadjusted action --
Yahoo adjusts its history for splits, so a split cannot still be a 32% one-day fall there. Two of
the 239 candidates are that shape (`DG` 2024-08-29, `ALTN` 2025-02-27) and they are excluded here.
Treating a real move as an action would not be conservative: it would throw away a genuine day's
history on evidence that says the opposite.
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path

# A verdict from the scan's second-provider check that means the date is a genuine move.
CONFIRMED_REAL = "both saw the move"


def unadjusted_windows(path: Path | None) -> dict[str, list[str]]:
    """{symbol: [action dates]} from the split scan, or {} when it has not been run.

    Flagging and not dropping is deliberate for the rows: they are still correct about everything
    that does not cross the action, and a consumer should decide.
    """
    if not path or not Path(path).exists():
        return {}
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for c in doc.get("candidatesList", []):
        second = c.get("secondProvider")
        if isinstance(second, dict) and second.get("verdict") == CONFIRMED_REAL:
            continue
        out.setdefault(c["symbol"], []).append(c["date"])
    return {k: sorted(v) for k, v in out.items()}


def crossed(dates, actions: list[str]) -> list[int]:
    """How many actions fall on or before each bar date, as a running count.

    With this, "an action falls in the span (dates[j], dates[i]]" is `counts[i] > counts[j]` --
    one comparison per candidate rather than a search per candidate, which is what lets the
    vectorised analog matcher apply the rule without losing the speed it exists for.
    """
    if not actions:
        return [0] * len(dates)
    acts = sorted(actions)
    return [bisect.bisect_right(acts, d.isoformat() if hasattr(d, "isoformat") else str(d))
            for d in dates]
