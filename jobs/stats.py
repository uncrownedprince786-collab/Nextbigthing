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
    ('Event', 'date'),
    ('EventImpact', None),
    ('MarketplaceItem', '"periodEnd"'),
    ('HumanSignal', '"periodEnd"'),
    ('SignalLog', '"issuedOn"'),
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

        # Coverage per exchange, because a PSX job that quietly fetched nothing looks the
        # same as a healthy run in the totals above.
        print()
        for got in rows(
            cur,
            """
            -- One index probe per asset for its newest stored day, not a join across every
            -- priced row to count the distinct names in it: measured 2026-10-12 at 19.1
            -- seconds against 1.1, the same three rows. `count(l.date)` counts the assets
            -- that matched, which is what `count(DISTINCT p."assetId")` counted.
            SELECT i.market, count(*) AS assets,
                   count(l.date) AS priced,
                   max(l.date) AS newest
            FROM "Industry" i
            JOIN "Asset" a ON a."industryId" = i.id
            LEFT JOIN LATERAL (
                SELECT s.date FROM "PriceSnapshot" s
                WHERE s."assetId" = a.id ORDER BY s.date DESC LIMIT 1
            ) l ON true
            GROUP BY i.market ORDER BY i.market
            """,
        ):
            newest = f" newest {got['newest']:%Y-%m-%d}" if got["newest"] else " no prices"
            print(
                f"market {got['market']:6} {got['assets']:>4} assets, "
                f"{got['priced']:>4} with a stored price{newest}"
            )

        # The accuracy log is only worth anything if rows actually mature, so the split
        # between what is waiting and what has been measured is the line to watch.
        print()
        for got in rows(
            cur,
            'SELECT status, count(*) AS n FROM "SignalLog" GROUP BY status ORDER BY status',
        ):
            print(f"signal log {got['status']:14} {got['n']:>6} rows")
        for got in rows(
            cur,
            """
            SELECT attention, count(*) AS n, count(tone) AS graded
            FROM "HumanSignal" GROUP BY attention ORDER BY attention
            """,
        ):
            print(
                f"attention {got['attention']:10} {got['n']:>5} targets, "
                f"{got['graded']:>5} with a published tone"
            )
    conn.close()


if __name__ == "__main__":
    main()
