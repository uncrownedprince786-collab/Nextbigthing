"""Find, and on request remove, measurement rows dated after the session they measured.

A row in `AssetSetup`, `AssetAnalog`, `MoveAttribution` or `Investigation` carries a
`periodEnd`, and every reader of those tables takes the newest one per asset. So a row dated
to a day the asset has no close for does not merely read oddly -- it wins, and it wins over
the correct row underneath it.

Four jobs produced exactly that until 2026-10-08, each one stamping the calendar date of the
run instead of the session its numbers came from. The code is fixed and re-running those jobs
writes correctly dated rows beside the wrong ones; it does not remove the wrong ones, because
an upsert keyed on `(assetId, periodEnd, ...)` has no reason to.

The comparison is per asset and not against one site-wide maximum, which matters on any day
the two exchanges are out of step: Karachi publishes its closing file hours before New York
closes, so 2026-10-08 is a real session for a PSX name and a day that has not happened yet for
a US one. A single global cutoff would either spare every bad US row or delete every good PSX
one.

    python tools/future_rows.py              # report only
    python tools/future_rows.py --delete     # report, then remove them

Reads PriceSnapshot. Writes nothing without --delete.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

from nbt import db, rows  # noqa: E402

# Every table that dates a row to the session it measured. `DecisionLog` is deliberately
# absent: its `periodEnd` is the day the desk published a reading, which is a statement about
# the calendar and not about a session, and `tools/decide.mjs` anchors its base close to the
# newest session at or before that date rather than to the date itself.
TABLES = ("AssetSetup", "AssetAnalog", "MoveAttribution", "Investigation")

# The intraday horizon is measured from five minute bars, not from daily closes, so a read of
# this morning's session is correctly dated to today while the daily close for today does not
# exist yet -- three assets were in exactly that state when this was written. Comparing it
# against `PriceSnapshot` would call a correct row an error every time a market is open. It is
# left out here rather than given a second rule, because `jobs/horizons.py` dates it from the
# `sessionDate` of the very bars it read, which cannot run ahead of itself.
ONLY = {"AssetSetup": """ AND t.horizon IN ('swing', 'longer')"""}

AHEAD = """
    SELECT t."periodEnd" AS d, count(*) AS n, count(DISTINCT t."assetId") AS assets
      FROM "{table}" t
      JOIN (SELECT "assetId", max(date) AS newest FROM "PriceSnapshot"
             WHERE close IS NOT NULL GROUP BY "assetId") p
        ON p."assetId" = t."assetId"
     WHERE t."periodEnd" > p.newest{only}
     GROUP BY 1 ORDER BY 1 DESC
"""

REMOVE = """
    DELETE FROM "{table}" t
     USING (SELECT "assetId", max(date) AS newest FROM "PriceSnapshot"
             WHERE close IS NOT NULL GROUP BY "assetId") p
     WHERE p."assetId" = t."assetId" AND t."periodEnd" > p.newest{only}
"""


def main() -> int:
    delete = "--delete" in sys.argv
    conn = db()
    cur = conn.cursor()
    total = 0
    try:
        for table in TABLES:
            ahead = rows(cur, AHEAD.format(table=table, only=ONLY.get(table, "")))
            n = sum(int(r["n"]) for r in ahead)
            total += n
            if not n:
                print(f"  {table:<18} none dated past its own newest close")
                continue
            detail = ", ".join(f"{r['d']}: {r['n']} rows over {r['assets']} assets"
                               for r in ahead)
            print(f"  {table:<18} {n} ahead of the data  ({detail})")
            if delete:
                cur.execute(REMOVE.format(table=table, only=ONLY.get(table, "")))
                conn.commit()
                print(f"  {'':<18} removed {cur.rowcount}")
        print()
        if not total:
            print("  nothing is dated to a session that has not happened.")
        elif delete:
            print(f"  {total} rows removed. Re-run the jobs that write them if the correctly "
                  "dated replacements are not already stored.")
        else:
            print(f"  {total} rows would be removed by --delete. Nothing was written.")
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
