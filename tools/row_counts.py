"""Snapshot row counts for the idempotency proof. Read-only."""

import json

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

# DATABASE_URL from the environment, or the project's own .env, exactly as the jobs read it.
# Never a path to a credential file somewhere else: these are committed.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

if not os.environ.get("DATABASE_URL"):
    raise SystemExit(
        "DATABASE_URL is not set. Copy .env.example to .env and paste the connection string, "
        "or export it in this shell."
    )

from nbt import db, one  # noqa: E402
TABLES = [
    "PriceSnapshot", "IntradayBar", "IntradaySession", "AssetSetup", "SetupTarget",
    "AssetThesis", "ThesisCheck", "MoveAttribution", "GraphRelevance", "Investigation",
    "InvestigationFinding", "InvestigationHypothesis", "News", "NewsLineage", "HumanSignal",
    "SignalLog", "Ranking", "Analysis", "Event", "EventState", "EventImpact", "AssetAnalog",
    "Coverage", "Calibration", "SourceReliability", "ProductSignal", "ProductRegion",
    "MarketplaceItem",
]

out = {}
conn = db()
conn.rollback()
conn.read_only = True
cur = conn.cursor()
for t in TABLES:
    try:
        out[t] = one(cur, f'SELECT count(*) AS n FROM "{t}"')["n"]
    except Exception as e:  # noqa: BLE001
        out[t] = f"ERR {type(e).__name__}"
        conn.rollback()
cur.close()
conn.close()

where = sys.argv[1] if len(sys.argv) > 1 else "snap.json"
Path(where).write_text(json.dumps(out, indent=1), encoding="utf-8")
for k, n in out.items():
    print(f"  {k:<26} {n}")
