"""Did the prices job store new daily rows today? Read-only."""

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

from nbt import db, one, rows  # noqa: E402
conn = db()
conn.rollback()
conn.read_only = True
cur = conn.cursor()

print("PriceSnapshot columns that could carry a write time:")
for r in rows(
    cur,
    """
    SELECT column_name, data_type FROM information_schema.columns
    WHERE table_name = 'PriceSnapshot'
    ORDER BY ordinal_position
    """,
):
    print(f"   {r['column_name']:<16} {r['data_type']}")

print()
print("newest stored date per source:")
for r in rows(
    cur,
    """
    SELECT source, max(date) AS newest, count(*) AS total
    FROM "PriceSnapshot" GROUP BY source ORDER BY source
    """,
):
    print(f"   {r['source'][:50]:<52} newest {r['newest']}  total {r['total']}")

print()
print("rows per source on the two most recent dates:")
for r in rows(
    cur,
    """
    SELECT date, source, count(*) AS n
    FROM "PriceSnapshot"
    WHERE date >= current_date - 2
    GROUP BY date, source ORDER BY date DESC, source
    """,
):
    print(f"   {r['date']}  {r['source'][:46]:<48} {r['n']} rows")

print()
got = one(
    cur,
    """
    SELECT count(*) AS n FROM "PriceSnapshot"
    WHERE date = current_date
    """,
)
print(f"rows dated today ({'2026-10-02 UTC' if False else 'current_date'}): {got['n']}")
print("today is", one(cur, "SELECT current_date AS d")["d"])

cur.close()
conn.close()
