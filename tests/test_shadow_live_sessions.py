"""Live shadow inference must use each market's own newest *trading* session.

One global `max(AssetFactor.periodEnd)` was a Sunday (2026-10-18) only crypto traded, so a US, PK,
FX or commodity call would be dated to a day its market was closed. Grouping the maximum by market
is not enough either: the factor table carries a row for every asset on a day *some* market was
open, so the date also has to be one the market actually trades.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "jobs"))

import shadow_predict  # noqa: E402
import nbt  # noqa: E402


class _Cursor:
    """Answers the three reads `live_rows` makes, by marker, from a fixed fixture."""

    def __init__(self, newest, session_rows, asset_rows):
        self._newest, self._sessions, self._assets = newest, session_rows, asset_rows
        self._rows = []
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if 'max("periodEnd")' in query and "ASSETID" not in query.upper():
            self._rows = [{"d": self._newest}]
        elif "DISTINCT" in query:
            self._rows = self._sessions
        else:
            self._rows = self._assets

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _Conn:
    def __init__(self, cursor):
        self._cursor, self.closed = cursor, False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _asset(asset_id, symbol, asset_type, source, session, days=(0,)):
    cols = shadow_predict.PRICE_COLUMNS
    row = {"assetId": asset_id, "symbol": symbol, "assetType": asset_type, "source": source,
           "ref_close": 10.0, "ref_date": session, **{c: 1.0 for c in cols}}
    return row


class LiveRowsUsePerMarketTradingSession(unittest.TestCase):

    def _run(self, sessions, session_rows, asset_rows, **kw):
        cur = _Cursor(max(sessions), session_rows, asset_rows)
        conn = _Conn(cur)
        with patch.object(nbt, "db", return_value=conn):
            rows, chosen, skipped = shadow_predict.live_rows(200000, **kw)
        return rows, chosen, skipped, conn

    def test_us_and_crypto_keep_different_latest_sessions(self):
        rows, chosen, skipped, conn = self._run(
            [date(2026, 10, 16), date(2026, 10, 18)],
            [{"d": date(2026, 10, 16), "t": "stock", "s": "yahoo"},
             {"d": date(2026, 10, 18), "t": "crypto", "s": "coinpaprika"}],
            [_asset("us", "AAPL", "stock", "yahoo", date(2026, 10, 16)),
             _asset("coin", "btc-bitcoin", "crypto", "coinpaprika", date(2026, 10, 18))],
        )
        self.assertEqual(chosen, {"US": "2026-10-16", "Crypto": "2026-10-18"})
        self.assertEqual(skipped, {})
        self.assertEqual({r["symbol"]: r["asOf"] for r in rows},
                         {"AAPL": "2026-10-16", "btc-bitcoin": "2026-10-18"})
        self.assertEqual({r["symbol"]: r["market"] for r in rows},
                         {"AAPL": "US", "btc-bitcoin": "Crypto"})
        self.assertTrue(conn.closed)

    def test_a_sunday_factor_row_is_not_a_us_session(self):
        # The newest factor date anywhere is Sunday and crypto traded, but US did not: even though
        # a US factor row exists for that date, the US session chosen is the Friday.
        rows, chosen, _, _ = self._run(
            [date(2026, 10, 18)],
            [{"d": date(2026, 10, 17), "t": "crypto", "s": "coinpaprika"},
             {"d": date(2026, 10, 16), "t": "stock", "s": "yahoo"},
             {"d": date(2026, 10, 18), "t": "crypto", "s": "coinpaprika"}],
            [_asset("us", "AAPL", "stock", "yahoo", date(2026, 10, 16)),
             _asset("coin", "btc-bitcoin", "crypto", "coinpaprika", date(2026, 10, 18))],
        )
        self.assertEqual(chosen["US"], "2026-10-16")
        self.assertNotIn("2026-10-18", {r["asOf"] for r in rows if r["market"] == "US"})

    def test_a_market_that_has_fallen_behind_is_named_not_filled(self):
        # Crypto traded to Wednesday 2026-10-21; US stopped at Friday 2026-10-16 (three US sessions
        # behind). The stale market is skipped rather than dated to an old session.
        rows, chosen, skipped, _ = self._run(
            [date(2026, 10, 21)],
            [{"d": date(2026, 10, 21), "t": "crypto", "s": "coinpaprika"},
             {"d": date(2026, 10, 16), "t": "stock", "s": "yahoo"}],
            [_asset("us", "AAPL", "stock", "yahoo", date(2026, 10, 16)),
             _asset("coin", "btc-bitcoin", "crypto", "coinpaprika", date(2026, 10, 21))],
        )
        self.assertNotIn("US", chosen)
        self.assertEqual(skipped.get("US"), 3)
        self.assertEqual({r["market"] for r in rows}, {"Crypto"})


if __name__ == "__main__":
    unittest.main()
