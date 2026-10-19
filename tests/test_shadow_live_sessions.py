"""Live shadow inference must retain each market's actual latest factor session."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "jobs"))

import shadow_predict  # noqa: E402
import nbt  # noqa: E402


class FakeCursor:
    def __init__(self, rows_by_query):
        self.rows_by_query = rows_by_query
        self.rows = []
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))
        self.rows = next(rows for marker, rows in self.rows_by_query if marker in query)

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


class LiveRowsUsePerMarketSession(unittest.TestCase):
    def test_us_and_crypto_keep_different_latest_sessions(self):
        us_day = date(2026, 10, 16)
        crypto_day = date(2026, 10, 18)
        cols = shadow_predict.PRICE_COLUMNS
        rows = [
            {
                "assetId": "us-id", "factor_session": us_day, "symbol": "AAPL",
                "assetType": "stock", "source": "yahoo", "ref_close": 250.0,
                "ref_date": us_day, **{c: 1.0 for c in cols},
            },
            {
                "assetId": "coin-id", "factor_session": crypto_day, "symbol": "btc-bitcoin",
                "assetType": "crypto", "source": "coinpaprika", "ref_close": 68000.0,
                "ref_date": crypto_day, **{c: 2.0 for c in cols},
            },
        ]
        cursor = FakeCursor([
            ('SELECT max(f."periodEnd") AS d', [{"d": us_day}, {"d": crypto_day}]),
            ('SELECT f."assetId"', rows),
        ])
        conn = FakeConnection(cursor)
        with patch.object(nbt, "db", return_value=conn):
            got, newest = shadow_predict.live_rows(200000)

        self.assertEqual(newest, "2026-10-18")
        self.assertEqual({r["symbol"]: r["asOf"] for r in got}, {
            "AAPL": "2026-10-16", "btc-bitcoin": "2026-10-18",
        })
        self.assertEqual({r["symbol"]: r["market"] for r in got}, {
            "AAPL": "US", "btc-bitcoin": "Crypto",
        })
        query = cursor.queries[1][0]
        self.assertIn('latest.d = f."periodEnd"', query)
        self.assertNotIn('WHERE f."periodEnd" = %s', query)
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
