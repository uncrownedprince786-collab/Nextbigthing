"""Print one line per table with its row count and newest stored date.

Used by the scheduled job so a run leaves a record of what is in the database, and useful
by hand after any migration.

    python jobs/stats.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, one, rows  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

TABLES = [
    ('Industry', None),
    ('Asset', None),
    ('Product', '"computedAt"'),
    ('ProductSignal', '"periodEnd"'),
    ('ProductAssetLink', None),
    ('PriceSnapshot', 'date'),
    ('Ranking', '"periodEnd"'),
    ('Analysis', '"createdAt"'),
    ('News', '"publishedAt"'),
]


def main() -> None:
    conn = db()
    with conn, conn.cursor() as cur:
        for table, datecol in TABLES:
            if datecol:
                got = one(
                    cur,
                    f'SELECT count(*) AS n, max({datecol}) AS newest FROM "{table}"',
                )
                newest = got["newest"]
            else:
                got = one(cur, f'SELECT count(*) AS n FROM "{table}"')
                newest = None
            tail = f" newest {newest:%Y-%m-%d}" if newest else ""
            print(f"{table:20} {got['n']:>10,}{tail}")

        print()
        for got in rows(
            cur,
            'SELECT source, count(*) AS n, count(DISTINCT "productId") AS products FROM "ProductSignal" GROUP BY source ORDER BY source',
        ):
            print(f"signal {got['source']:14} {got['n']:>6} rows over {got['products']:>3} products")
        for got in rows(
            cur,
            'SELECT basis, count(*) AS n FROM "Ranking" GROUP BY basis ORDER BY basis',
        ):
            print(f"ranking {got['basis']:14} {got['n']:>6} rows")
    conn.close()


if __name__ == "__main__":
    main()
