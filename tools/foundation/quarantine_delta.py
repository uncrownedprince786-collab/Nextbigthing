"""What the narrowed corporate-action rule excludes, restores and still affects, row by row.

    python tools/foundation/quarantine_delta.py [--out DIR]

The first answer to unadjusted corporate actions flagged every session at or after an asset's first
action, because the analog match pool is the asset's whole history and a 2026 session really could
match a 2019 candidate carrying a fabricated move. It was correct and it was expensive: 88 of the
152 affected assets have their first action in 2021 or earlier, so nearly all of their stored
history was quarantined.

`pit_features.AnalogSeries` now excludes the contaminated candidates themselves -- the candidate
whose own factors are measured across an action, the forward window that crosses one, and the
session whose own factors do -- so the pool is clean and the broad flag is no longer the only thing
standing between a fabricated move and a rule's statistics.

This counts what changed, over the same eligible sessions the assembly uses, so the claim "history
was restored" carries a number rather than a direction. It reads the database and writes nothing.

  excluded   sessions the windowed rule still flags: an action inside the feature lookback or the
             outcome lookforward. Unchanged by the fix, and correctly flagged.
  suppressed sessions that now get no analog block at all, because their own factors cross an
             action. These are newly precise, not newly lost: they were flagged before too.
  restored   sessions the broad rule flagged and no rule flags now.
  affected   assets and sessions still touching an action under either rule.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "jobs"))

from actions import unadjusted_windows  # noqa: E402

# The same reaches assemble.py uses: 260 sessions of lookback is about 378 calendar days, 20
# sessions of lookforward about 29.
LOOKBACK_DAYS = 378
LOOKFORWARD_DAYS = 29
# tools/foundation/pit_features.ACTION_REACH, and the volume window behind it.
PRICE_REACH = 5
VOLUME_REACH = 20


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from nbt import db, rows
    from sessions import session_bar

    actions = unadjusted_windows(ROOT / "data" / "foundation" / "price_verification" /
                                 "unadjusted_actions.json")
    conn = db()
    cur = conn.cursor()
    try:
        got = rows(cur, 'SELECT a.symbol, a."assetType"::text AS "assetType", p.date::text AS d, '
                        '(p.volume IS NOT NULL AND p.volume > 0) AS has_volume '
                        f'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                        f'WHERE p.close IS NOT NULL AND {session_bar()} ORDER BY a.symbol, p.date')
    finally:
        cur.close()
        conn.close()

    by_symbol: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    kind: dict[str, str] = {}
    for r in got:
        by_symbol[r["symbol"]].append((r["d"], bool(r["has_volume"])))
        kind[r["symbol"]] = r["assetType"]

    totals: dict[str, int] = defaultdict(int)
    per_class: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    restored_assets: set[str] = set()
    for symbol, bars in by_symbol.items():
        acts = actions.get(symbol, [])
        cls = kind[symbol]
        dates = [d for d, _ in bars]
        for i, (d, has_vol) in enumerate(bars):
            totals["eligible"] += 1
            per_class[cls]["eligible"] += 1
            if not acts:
                continue
            windowed = any((date.fromisoformat(d) - timedelta(days=LOOKBACK_DAYS)).isoformat()
                           <= a <= (date.fromisoformat(d) + timedelta(days=LOOKFORWARD_DAYS)).isoformat()
                           for a in acts)
            broad = d >= acts[0]
            reach = VOLUME_REACH if has_vol else PRICE_REACH
            back = dates[max(0, i - reach)]
            crosses = any(back < a <= d for a in acts)
            if windowed:
                totals["excludedByTheWindowRule"] += 1
                per_class[cls]["excludedByTheWindowRule"] += 1
            if crosses:
                totals["analogBlockSuppressed"] += 1
                per_class[cls]["analogBlockSuppressed"] += 1
            if broad and not windowed:
                totals["restored"] += 1
                per_class[cls]["restored"] += 1
                restored_assets.add(symbol)
            if broad:
                totals["flaggedByTheOldBroadRule"] += 1
                per_class[cls]["flaggedByTheOldBroadRule"] += 1

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eligibleSessions": totals["eligible"],
        "assetsWithAnUnadjustedAction": len(actions),
        "actionDates": sum(len(v) for v in actions.values()),
        "flaggedByTheOldBroadRule": totals["flaggedByTheOldBroadRule"],
        "excludedByTheWindowRule": totals["excludedByTheWindowRule"],
        "analogBlockSuppressed": totals["analogBlockSuppressed"],
        "restored": totals["restored"],
        "assetsWithRestoredSessions": len(restored_assets),
        "byAssetClass": {c: dict(v) for c, v in sorted(per_class.items())},
        "note": ("restored = flagged by the old rule and by no rule now. A suppressed session is "
                 "not a loss against the old rule, which flagged it as well; it is the same "
                 "session with the reason stated precisely."),
    }
    out = Path(arg("--out") or ROOT / "data" / "foundation" / "price_verification")
    out.mkdir(parents=True, exist_ok=True)
    (out / "quarantine_delta.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "byAssetClass"}, indent=1))


if __name__ == "__main__":
    main()
