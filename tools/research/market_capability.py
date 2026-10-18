"""What each market can be modelled and judged on, as a table rather than as an assumption.

    python tools/research/market_capability.py [--probe-db] [--out FILE]

Read-only. Writes `data/foundation/dataset/market_capability.json`: for every market the project
carries (US, PK, FX, Commodity, Crypto) and every timeframe (scalp, intraday, swing, position),
whether a prediction on it can be judged from stored data, and -- when `--probe-db` is passed --
how many assets and how fresh each market's factor lane actually is.

Why a capability matrix and not one model per market
----------------------------------------------------
A model per market is a lot of infrastructure to stand up before knowing which markets can even be
*measured*. Two facts decide that, and both are cheap to state:

* **The horizon.** A scalp call is a claim about minutes. The database stores daily closes and
  cannot order what happened inside a session, so a scalp prediction can never be scored here --
  not "will be hard to score", but *cannot*. Recording one would create a row that matures into
  nothing, which reads later as an unscored success.
* **The calendar.** Twenty sessions is about four weeks for a US equity and twenty *days* for a
  coin, because crypto trades weekends. Counting calendar days instead made every horizon land on
  the wrong date for at least one market.

Both live in `shadow_markets`; this file only renders them, plus the live counts that say whether a
market has anything to predict on at all.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.insert(0, str(ROOT / "jobs"))

import shadow_markets as mk  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "market_capability.json"


def live_counts() -> dict:
    """Assets per market and the newest factor session per market. Empty when the DB is absent."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    if not os.environ.get("DATABASE_URL"):
        return {"status": "unavailable", "reason": "DATABASE_URL is not set"}
    try:
        from nbt import db
        conn = db()
        cur = conn.cursor()
        cur.execute('SELECT id, "assetType", source FROM "Asset"')
        assets = cur.fetchall()
        cur.execute('SELECT f."assetId", max(f."periodEnd") AS d FROM "AssetFactor" f '
                    'GROUP BY f."assetId"')
        newest = {r["assetId"]: r["d"] for r in cur.fetchall()}
        cur.close()
        conn.close()
    except Exception as e:                                    # noqa: BLE001
        return {"status": "failed", "reason": f"{type(e).__name__}: {str(e)[:160]}"}
    counts: dict[str, dict] = {m: {"assets": 0, "newestSession": None} for m in mk.MARKETS}
    for a in assets:
        m = mk.market_of(a["assetType"], a["source"])
        counts[m]["assets"] += 1
        d = newest.get(a["id"])
        if d is not None and (counts[m]["newestSession"] is None
                              or str(d) > counts[m]["newestSession"]):
            counts[m]["newestSession"] = str(d)
    return {"status": "ok", "byMarket": counts}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probe-db", action="store_true",
                    help="also read per-market asset counts and factor freshness")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "market-capability-v1",
        "status": "reference table; it says what can be judged, not what is deployed",
        "markets": list(mk.MARKETS),
        "timeframes": {name: spec["sessions"] for name, spec in mk.TIMEFRAMES.items()},
        "profiles": [mk.market_profile(m) for m in mk.MARKETS],
        "matrix": mk.market_capability_matrix(),
        "live": live_counts() if a.probe_db else {"status": "not probed"},
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    for row in payload["matrix"]:
        mark = "verifiable  " if row["verifiable"] else "UNVERIFIABLE"
        print(f"  {mark} {row['market']:10} {row['timeframe']:9} "
              f"{row['horizonSessions']:>2}s  {row['judgedOn'][:60]}")
    if payload["live"].get("status") == "ok":
        for m, c in payload["live"]["byMarket"].items():
            print(f"  live {m:10} {c['assets']:>4} assets, newest {c['newestSession']}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
