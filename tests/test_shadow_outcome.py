"""End-to-end guards for the shadow outcome path: schema, writer SQL, and the scorer's writes.

These are the tests that fail if someone reverts the identity key, edits a prediction while scoring,
makes a scorer rerun additive, or grades a horizon the model was never trained on.
"""

import re
import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

import make_dataset  # noqa: E402
import shadow_predict as sp  # noqa: E402
import shadow_score as ss  # noqa: E402


def _nows(text: str) -> str:
    return re.sub(r"\s+", "", text)


class FakeCursor:
    def __init__(self, rowcount: int = 1):
        self.calls: list = []
        self._rowcount = rowcount
        self.closed = False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    @property
    def rowcount(self):
        return self._rowcount

    def fetchall(self):
        return []

    # The headroom guard (shadow_budget) reads pg_database_size through the same cursor. A store
    # that is largely empty leaves the writer free to proceed.
    def fetchone(self):
        return {"mb": 100.0}

    def close(self):
        self.closed = True


class _GuardCursor:
    """Just enough cursor for the headroom probe, which runs before any insert."""

    def execute(self, sql, params=None):
        return self

    def fetchone(self):
        return {"mb": 100.0}

    def close(self):
        pass


class FakeConn:
    def __init__(self, fail: bool = False):
        self.committed = 0
        self.rolled = 0
        self.fail = fail

    def cursor(self):
        return _GuardCursor()

    def commit(self):
        if self.fail:
            raise RuntimeError("boom")
        self.committed += 1

    def rollback(self):
        self.rolled += 1


def _bars(n: int, base: float, last: float) -> list[dict]:
    out = []
    for i in range(n):
        close = base if i < n - 1 else last
        out.append({"date": date(2026, 10, 20) + timedelta(days=i), "close": close,
                    "source": "test"})
    return out


def _pred(pid="p1", market="US", horizon=20, predicted="UP", as_of=None):
    return {"id": pid, "assetId": "a1", "symbol": "AAPL", "market": market,
            "predicted": predicted, "modelVersion": "brain-v2-context",
            "asOf": as_of or date(2026, 10, 15), "horizonSessions": horizon,
            "referencePrice": 100.0, "strategy": "swing", "timeframe": "swing"}


class SchemaAndMigrationTest(unittest.TestCase):
    def setUp(self):
        self.schema = (ROOT / "prisma" / "schema.prisma").read_text(encoding="utf-8")
        self.mig = (ROOT / "prisma" / "migrations" / "20261019120000_shadow_outcome"
                    / "migration.sql").read_text(encoding="utf-8")

    def test_migration_adds_outcome_table_and_identity_key(self):
        m = _nows(self.mig)
        self.assertIn('CREATETABLE"ShadowOutcome"', m)
        self.assertIn('CREATEUNIQUEINDEX"ShadowOutcome_predictionId_observedOn_final_key"', m)
        self.assertIn('DROPINDEX"ShadowPrediction_modelVersion_assetId_asOf_key"', m)
        self.assertIn('CREATEUNIQUEINDEX"ShadowPrediction_identity_key"', m)

    def test_schema_identity_key_matches_migration_map(self):
        s = _nows(self.schema)
        self.assertIn('map:"ShadowPrediction_identity_key"', s)
        self.assertIn(
            '@@unique([modelVersion,modelSha256,strategy,timeframe,assetId,asOf,horizonSessions]',
            s)
        self.assertIn('map:"ShadowOutcome_predictionId_observedOn_final_key"', s)

    def test_new_columns_are_added_and_typed(self):
        m = _nows(self.mig)
        for col in ('"strategy"TEXTNOTNULLDEFAULT\'swing\'',
                    '"timeframe"TEXTNOTNULLDEFAULT\'swing\'',
                    '"referencePrice"DOUBLEPRECISION',
                    '"features"JSONB', '"sources"JSONB', '"inputCutoff"TIMESTAMP(3)'):
            self.assertIn(col, m)

    def test_outcome_is_nullable_so_missing_is_not_flat(self):
        m = _nows(self.mig)
        self.assertIn('"label"TEXT,', m)
        self.assertIn('"fwdPct"DOUBLEPRECISION,', m)
        self.assertNotIn('"label"TEXTNOTNULL', m)


class PredictWriterTest(unittest.TestCase):
    def setUp(self):
        self.src = _nows(
            (ROOT / "tools" / "research" / "shadow_predict.py").read_text(encoding="utf-8"))

    def test_conflict_target_is_the_new_identity_key(self):
        # The key is split across two adjacent string literals in the source, so match each side.
        self.assertIn('ONCONFLICT("modelVersion","modelSha256","strategy","timeframe","assetId",',
                      self.src)
        self.assertIn('"asOf","horizonSessions")DONOTHING', self.src)

    def test_writer_supplies_the_new_columns(self):
        for col in ('"strategy"', '"timeframe"', '"referencePrice"', '"features"',
                    '"sources"', '"inputCutoff"'):
            self.assertIn(col, self.src)


class PredictWriteAccountTest(unittest.TestCase):
    """An insert conflict must not be reported as a write, or a rerun looks additive."""

    def _record(self):
        return {"asOf": "2026-10-16", "assetId": "a1", "symbol": "AAPL", "market": "US",
                "predicted": "UP", "scores": {"UP": 0.6}, "modelVersion": "brain-v2-context",
                "modelSha256": "sha", "featureSchema": "ctx", "datasetVersion": "v4",
                "quality": "ok", "imputed": [], "imputedCount": 0, "missingCritical": None,
                "contextStatus": None, "macroAsOf": None, "macroAgeDays": None,
                "horizonSessions": 20, "maturesAfter": "2026-11-13", "strategy": "swing",
                "timeframe": "swing", "referencePrice": 100.0, "features": {"r1": 0.1},
                "sources": None, "inputCutoff": "2026-10-16", "runId": "r", "commit": "c"}

    def _install(self, rowcount):
        fake = types.ModuleType("nbt")
        cursor = FakeCursor(rowcount=rowcount)
        conn = FakeConn()
        conn.cursor = lambda: cursor
        # `primary_db`, because the shadow writer must reach the authoritative primary or fail --
        # a prediction stranded on a standby is one the scorer, which reads the primary, never sees.
        # `db` stays on the stub so a caller that still wants failover is not silently broken here.
        fake.primary_db = lambda: conn
        fake.db = lambda: conn
        prev = sys.modules.get("nbt")
        sys.modules["nbt"] = fake
        self.addCleanup(lambda: sys.modules.__setitem__("nbt", prev) if prev
                        else sys.modules.pop("nbt", None))
        return cursor

    def test_inserted_row_is_counted(self):
        cur = self._install(1)
        res = sp.write_rows([self._record()])
        self.assertEqual(res, {"written": 1, "status": "ok"})
        self.assertTrue(cur.calls)

    def test_conflicting_row_is_not_counted_as_written(self):
        self._install(0)
        res = sp.write_rows([self._record()])
        self.assertEqual(res, {"written": 0, "status": "ok"})


class ScorerWriteTest(unittest.TestCase):
    def test_write_outcomes_upserts_on_the_final_key(self):
        cur = FakeCursor(rowcount=1)
        conn = FakeConn()
        finals = [{"predictionId": "p1", "final": True, "label": "UP", "fwdPct": 10.0,
                   "referencePrice": 100.0, "observedPrice": 110.0,
                   "observedOn": date(2026, 11, 12), "fromSession": date(2026, 10, 15),
                   "toSession": date(2026, 11, 12), "sessionsElapsed": 20, "horizonSessions": 20,
                   "mfe": 12.0, "mae": -3.0, "source": "psx",
                   "scoringRule": ss.SCORING_RULE, "scorerVersion": ss.SCORER_VERSION,
                   "observedAt": None}]
        res = ss.write_outcomes(cur, conn, finals)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["written"], 1)
        self.assertEqual(conn.committed, 1)
        sql = _nows(cur.calls[0][0])
        self.assertIn('INSERTINTO"ShadowOutcome"', sql)
        self.assertIn('ONCONFLICT("predictionId","observedOn","final")DONOTHING', sql)
        # The prediction itself is never the target of an UPDATE.
        self.assertNotIn("UPDATE", sql.upper())

    def test_write_outcomes_is_a_noop_when_nothing_matured(self):
        cur = FakeCursor()
        res = ss.write_outcomes(cur, FakeConn(), [])
        self.assertEqual(res["status"], "nothing-matured")
        self.assertEqual(cur.calls, [])

    def test_write_outcomes_rolls_back_and_reports_failure(self):
        cur = FakeCursor()
        conn = FakeConn(fail=True)
        finals = [{"predictionId": "p1", "final": True, "label": "UP", "fwdPct": 1.0,
                   "referencePrice": 100.0, "observedPrice": 101.0,
                   "observedOn": date(2026, 11, 12), "fromSession": date(2026, 10, 15),
                   "toSession": date(2026, 11, 12), "sessionsElapsed": 20, "horizonSessions": 20,
                   "mfe": 1.0, "mae": -1.0, "source": None,
                   "scoringRule": ss.SCORING_RULE, "scorerVersion": ss.SCORER_VERSION,
                   "observedAt": None}]
        res = ss.write_outcomes(cur, conn, finals)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(conn.rolled, 1)


class BuildTest(unittest.TestCase):
    def setUp(self):
        self._orig = (ss.load_predictions, make_dataset.base_closes,
                      ss.forward_bars_with_source)

        def restore():
            (ss.load_predictions, make_dataset.base_closes,
             ss.forward_bars_with_source) = self._orig
        self.addCleanup(restore)

    def _patch(self, preds, closes, bars):
        ss.load_predictions = lambda cur, limit: preds
        make_dataset.base_closes = lambda cur, a: closes
        ss.forward_bars_with_source = lambda cur, a: bars

    def test_matured_row_produces_a_final_outcome(self):
        self._patch([_pred()], {"a1": 100.0}, {"a1": _bars(20, 100.0, 110.0)})
        payload = ss.build(FakeCursor(), date(2026, 11, 20), 10, write=False)
        self.assertEqual(payload["summary"]["matured"], 1)
        self.assertEqual(payload["summary"]["graded"], 1)
        self.assertEqual(payload["summary"]["accuracy"], 1.0)
        self.assertEqual(payload["rows"][0]["outcomeLabel"], "UP")

    def test_unelapsed_horizon_is_awaiting_and_writes_nothing(self):
        self._patch([_pred()], {"a1": 100.0}, {"a1": _bars(5, 100.0, 103.0)})
        cur, conn = FakeCursor(), FakeConn()
        payload = ss.build(cur, date(2026, 10, 30), 10, write=True, conn=conn)
        self.assertEqual(payload["summary"]["awaiting"], 1)
        self.assertEqual(payload["summary"]["accuracy"], None)
        self.assertEqual(payload["write"]["status"], "nothing-matured")
        self.assertEqual(cur.calls, [])

    def test_horizon_without_a_defined_rule_is_unscorable(self):
        self._patch([_pred(horizon=60)], {"a1": 100.0}, {"a1": _bars(20, 100.0, 130.0)})
        payload = ss.build(FakeCursor(), date(2026, 11, 20), 10)
        self.assertEqual(payload["summary"]["matured"], 0)
        self.assertFalse(payload["rows"][0]["scorable"])
        self.assertIn("60-session", payload["rows"][0]["reason"])

    def test_unknown_market_is_unscorable(self):
        self._patch([_pred(market="XX")], {"a1": 100.0}, {"a1": _bars(20, 100.0, 130.0)})
        payload = ss.build(FakeCursor(), date(2026, 11, 20), 10)
        self.assertFalse(payload["rows"][0]["scorable"])
        self.assertIn("unknown market", payload["rows"][0]["reason"])

    def test_a_call_dated_to_a_day_its_market_was_closed_is_unscorable(self):
        # The eight rows recorded before the per-market session fix carry a Sunday (2026-10-18)
        # asOf for US/PK/FX/Commodity. Scoring one would measure a move against a session the
        # market never had, so it is refused and reported rather than graded.
        self._patch([_pred(as_of=date(2026, 10, 18))], {"a1": 100.0},
                    {"a1": _bars(20, 100.0, 130.0)})
        payload = ss.build(FakeCursor(), date(2026, 11, 20), 10)
        self.assertFalse(payload["rows"][0]["scorable"])
        self.assertIn("not a session US trades", payload["rows"][0]["reason"])
        # Crypto does trade that day, so the same date is fine for it.
        self._patch([_pred(as_of=date(2026, 10, 18), market="Crypto")], {"a1": 100.0},
                    {"a1": _bars(20, 100.0, 130.0)})
        payload = ss.build(FakeCursor(), date(2026, 11, 20), 10)
        self.assertTrue(payload["rows"][0]["scorable"])

    def test_build_never_mutates_the_prediction(self):
        pred = _pred()
        snapshot = dict(pred)
        self._patch([pred], {"a1": 100.0}, {"a1": _bars(20, 100.0, 90.0)})
        ss.build(FakeCursor(), date(2026, 11, 20), 10)
        self.assertEqual(pred, snapshot)
        self.assertIsNone(pred.get("outcomeLabel"))

    def test_by_market_splits_grades_per_market(self):
        rows = [{"market": "US", "scorable": True, "mature": True, "outcomeLabel": "UP",
                 "predicted": "UP", "correct": True},
                {"market": "PK", "scorable": True, "mature": True, "outcomeLabel": "DOWN",
                 "predicted": "UP", "correct": False},
                {"market": "PK", "scorable": False, "mature": False, "outcomeLabel": None,
                 "predicted": "UP", "correct": None}]
        m = ss.by_market(rows)
        self.assertEqual(m["US"], {"total": 1, "awaiting": 0, "pending": 0, "unscorable": 0,
                                   "matured": 1, "graded": 1, "correct": 1})
        self.assertEqual(m["PK"]["graded"], 1)
        self.assertEqual(m["PK"]["correct"], 0)
        self.assertEqual(m["PK"]["awaiting"], 1)
        # No `reason`, so the third row is waiting for its horizon rather than refused.
        self.assertEqual(m["PK"]["pending"], 1)
        self.assertEqual(m["PK"]["unscorable"], 0)

    def test_state_of_separates_a_refusal_from_an_unclosed_window(self):
        """`scorable: False` is two different facts and only one of them is permanent."""
        # Waiting for the horizon: no reason, so it will score the day the window closes.
        self.assertEqual(ss.state_of({"scorable": False, "mature": False}), "pending")
        # Refused: `_unscorable` and the missing-base branch of `score_one` both set a reason,
        # and no later session supplies a close that was never stored.
        self.assertEqual(
            ss.state_of({"scorable": False, "mature": False,
                         "reason": "no reference close stored for the decision session"}),
            "unscorable")
        self.assertEqual(ss.state_of({"scorable": True, "mature": True}), "matured")
        # A matured row is never re-read as pending just because it has not been graded.
        self.assertEqual(ss.state_of({"scorable": True, "mature": False}), "pending")

    def test_aggregate_counts_unscorable_apart_and_keeps_awaiting_whole(self):
        """`awaiting` keeps its old value; the split beneath it is what a reader should use."""
        rows = [
            {"market": "US", "scorable": True, "mature": True, "outcomeLabel": "UP",
             "predicted": "UP", "correct": True},
            {"market": "US", "scorable": False, "mature": False, "outcomeLabel": None,
             "predicted": "UP", "correct": None},
            {"market": "US", "scorable": False, "mature": False, "outcomeLabel": None,
             "predicted": "UP", "correct": None,
             "reason": "2026-10-18 is not a session US trades"},
        ]
        a = ss.aggregate(rows)
        self.assertEqual(a["total"], 3)
        self.assertEqual(a["matured"], 1)
        self.assertEqual(a["pending"], 1)
        self.assertEqual(a["unscorable"], 1)
        # Unchanged for every existing reader: still "everything that has not matured".
        self.assertEqual(a["awaiting"], a["pending"] + a["unscorable"])
        self.assertEqual(a["awaiting"], 2)
        self.assertEqual(a["unscorableReasons"],
                         {"2026-10-18 is not a session US trades": 1})
        # The three states partition the rows: nothing is counted twice or dropped.
        self.assertEqual(a["matured"] + a["pending"] + a["unscorable"], a["total"])


if __name__ == "__main__":
    unittest.main()
