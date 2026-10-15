"""Null the fabricated zero volumes on currency pairs. The one database write of Milestone B.

    python tools/foundation/fix_forex_volume.py            # report only, writes nothing
    python tools/foundation/fix_forex_volume.py --apply    # perform the update

**What is wrong.** A currency pair has no consolidated tape, so there is no volume to publish and
Yahoo answers `0` for every FX bar. `jobs/prices.py _store_frame` has always turned that into a
null for exactly this reason, and its comment names the three readers that would otherwise take
the 0 as real: `avg_volume` in `jobs/rank.py`, which averages non-null volumes; `write_rising`,
which uses the volume trend as its second check; and `VOLUME_CONFIRMS_AT` in `lib/decision.ts`,
which compares a session against its own average. `chart_repair` wrote the same rows without that
rule, so 216 bars carry a 0 that was never a measurement.

**Scope, measured before writing.** 216 rows: 27 currency pairs across the 8 sessions from
2026-09-14 to 2026-09-24, every one of them `source = 'Yahoo Finance chart API'`. Zero-volume bars
on other asset types are left exactly as they are -- 1,966 commodity and 1,136 equity rows where a
contract or share genuinely did not trade, which is a real measurement and not a placeholder.

**Rollback.** The affected keys and their prior values are written to
`data/foundation/price_verification/forex_volume_rollback.json` before the update. Restoring is an
UPDATE back to 0 over that key list, and the row-level backup in the pre-change dump is the
fallback. Nothing else on these rows is touched: not the close, not the range, not the source.

`jobs/prices.py chart_repair` now applies the same rule the other path always did, so this cannot
recur and this script should find nothing on a second run.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

CHART = "Yahoo Finance chart API"
OUT = ROOT / "data" / "foundation" / "price_verification" / "forex_volume_rollback.json"

SELECT = '''
SELECT p."assetId", a.symbol, p.date::text AS d, p.volume, p.source
FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId"
WHERE a."assetType" = 'forex' AND p.volume = 0
ORDER BY a.symbol, p.date'''

UPDATE = '''
UPDATE "PriceSnapshot" p SET volume = NULL
FROM "Asset" a
WHERE a.id = p."assetId" AND a."assetType" = 'forex' AND p.volume = 0'''


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from nbt import db, rows

    apply = "--apply" in sys.argv
    conn = db()
    cur = conn.cursor()
    try:
        found = rows(cur, SELECT)
        print(f"currency-pair bars carrying a fabricated zero volume: {len(found):,}")
        if not found:
            print("nothing to do")
            return 0
        sources = sorted({r["source"] for r in found})
        dates = sorted({r["d"] for r in found})
        symbols = sorted({r["symbol"] for r in found})
        print(f"  sources : {sources}")
        print(f"  dates   : {dates[0]} .. {dates[-1]} ({len(dates)} sessions)")
        print(f"  symbols : {len(symbols)}")
        if sources != [CHART]:
            # The measured population is one source. If that ever changes, stop and look rather
            # than widening a write on the strength of a rule that was checked against one path.
            print(f"REFUSING: expected only {CHART!r}, found {sources}")
            return 1

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "version": "forex-volume-rollback-v1",
            "what": "volume set from 0 to NULL on currency-pair bars; nothing else changed",
            "why": ("FX has no consolidated tape, so Yahoo's 0 is a placeholder and not a "
                    "measurement; jobs/prices.py _store_frame has always nulled it and "
                    "chart_repair did not"),
            "rollback": ('UPDATE "PriceSnapshot" SET volume = 0 WHERE ("assetId", date) IN the '
                         "keys below"),
            "rows": len(found),
            "keys": [{"assetId": r["assetId"], "symbol": r["symbol"], "date": r["d"],
                      "priorVolume": r["volume"]} for r in found],
        }, indent=1), encoding="utf-8")
        print(f"  rollback written: {OUT}")

        if not apply:
            print("\nreport only. Re-run with --apply to perform the update.")
            return 0

        cur.execute(UPDATE)
        changed = cur.rowcount
        conn.commit()
        print(f"  updated {changed:,} rows")
        left = rows(cur, SELECT)
        print(f"  remaining fabricated zeros: {len(left)}")
        return 0 if changed == len(found) and not left else 1
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
