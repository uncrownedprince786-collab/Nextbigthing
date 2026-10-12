"""Recover one asset's missing daily history from its own provider, and prove nothing else moved.

    python tools/recover_asset.py COF                 report only: what is stored, what is available
    python tools/recover_asset.py COF --since 2019-01-02 --write    fetch and upsert that range

Why one asset at a time
-----------------------
`jobs/prices.py` fetches a whole lane. That is right for a lane and wrong for a repair: re-fetching
288 US names to fix one of them spends the provider's patience and rewrites rows that were already
correct. The audit of 2026-10-12 found exactly one long-listed name with a short history -- `COF`,
Capital One, holding 22 bars from 2026-09-10 while the universe starts at 2019-01-02 -- and this is
the bounded operation that fixes that shape of gap without touching anything else.

What it will not do
-------------------
  * **It never deletes.** The write goes through `_store_frame(..., is_full=False)`, which is the
    upsert path: `ON CONFLICT ("assetId", date) DO UPDATE`. A row that is already correct is
    rewritten with the same values; a row the provider no longer serves is left exactly where it is.
    `is_full=True` would replace the asset's series, and a repair must never be able to shorten a
    history it was called to lengthen.
  * **It never invents a bar.** Whatever the provider did not answer for stays missing, and the
    report says so rather than filling it.
  * **It checks its own work.** The rows that existed before are re-read afterwards and compared
    value for value; a single changed close that was not supposed to change fails the run.
"""

from __future__ import annotations

import sys
import warnings
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
warnings.filterwarnings("ignore")

from nbt import db, rows  # noqa: E402
import prices  # noqa: E402


def stored(cur, asset_id: str) -> list[dict]:
    return rows(
        cur,
        'SELECT date, open, high, low, close, volume, source FROM "PriceSnapshot" '
        'WHERE "assetId" = %s ORDER BY date',
        (asset_id,),
    )


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    symbol = argv[0]
    write = "--write" in argv
    since = date(2019, 1, 2)
    if "--since" in argv:
        since = datetime.strptime(argv[argv.index("--since") + 1], "%Y-%m-%d").date()

    conn = db()
    cur = conn.cursor()
    try:
        got = rows(
            cur,
            'SELECT a.id, a.symbol, a."sourceRef", a.source, a."assetType"::text AS "assetType", '
            'i.market FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId" WHERE a.symbol = %s',
            (symbol,),
        )
        if not got:
            print(f"no asset with symbol {symbol}")
            return 2
        a = got[0]
        before = stored(cur, a["id"])
        print(f"{symbol} ({a['market']}, {a['assetType']}, ref={a['sourceRef']}, source={a['source']})")
        print(f"  stored now: {len(before)} bars"
              + (f", {before[0]['date']} .. {before[-1]['date']}" if before else ""))

        if a["source"] != "yahoo":
            print(f"  this tool only speaks to Yahoo; {symbol} comes from {a['source']}")
            return 2

        import yfinance as yf

        frame = yf.download(
                a["sourceRef"], start=since.isoformat(), interval="1d",
                progress=False, auto_adjust=False, group_by="ticker", threads=False, timeout=30,
            )
        if frame is None or getattr(frame, "empty", True):
            print("  the provider answered nothing for that range; nothing written")
            return 1
        print(f"  provider holds {len(frame)} rows from {since}")

        if not write:
            missing = len(frame) - len(before)
            print(f"  would add about {max(missing, 0)} bars. Re-run with --write to do it.")
            return 0

        # The lane's own writer, in upsert mode. `forming_sessions` drops a bar for a session still
        # being traded, exactly as the daily lane does, so a repair cannot store a live price as a
        # close.
        written, newest = prices._store_frame(
            cur, [a], frame, date.today(), is_full=False,
            forming=prices.forming_sessions([a]),
        )
        conn.commit()

        after = stored(cur, a["id"])
        kept = {r["date"]: r for r in after}
        changed = [
            r["date"] for r in before
            if r["date"] in kept and (
                (r["close"] is None) != (kept[r["date"]]["close"] is None)
                or (r["close"] is not None and abs(float(r["close"]) - float(kept[r["date"]]["close"])) > 1e-9)
            )
        ]
        lost = [r["date"] for r in before if r["date"] not in kept]
        print(f"  wrote {written} rows; stored now {len(after)} bars"
              + (f", {after[0]['date']} .. {after[-1]['date']}" if after else ""))
        print(f"  pre-existing bars preserved: {len(before) - len(lost)} of {len(before)}"
              f"   lost: {len(lost)}   closes changed: {len(changed)}")
        if lost or changed:
            print(f"  FAILED the integrity check: lost={lost[:5]} changed={changed[:5]}")
            return 1
        print("  integrity check passed: no existing bar was lost or altered")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
