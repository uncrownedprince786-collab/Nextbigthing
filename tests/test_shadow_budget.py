"""Guards for the bounded-recording policy: the headroom floor and the schedule that respects it.

`data/foundation/dataset/shadow_storage_budget.json` records that the free tier is 500 MB and that a
full-universe daily stream would fill it in about two weeks. These are the tests that fail if a
writer stops checking the floor, if the check is bypassed by the writers that actually insert, or if
the scheduled lane is loosened past the two-rows-per-market bound the policy allows or loses its
scorer.
"""

import re
import sys
import types
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

import shadow_budget as sb  # noqa: E402
import shadow_predict as sp  # noqa: E402
import shadow_score as ss  # noqa: E402


def _nows(text: str) -> str:
    return re.sub(r"\s+", "", text)


class _Cur:
    def __init__(self, mb, tuple_rows=False, rowcount=1):
        self.mb, self.tuple_rows, self._rowcount = mb, tuple_rows, rowcount
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    @property
    def rowcount(self):
        return self._rowcount

    def fetchone(self):
        return (self.mb,) if self.tuple_rows else {"mb": self.mb}

    def close(self):
        self.closed = True


class _Conn:
    def __init__(self, mb, tuple_rows=False, fail=False):
        self._cur = _Cur(mb, tuple_rows)
        self.commits, self.rolled, self.fail = 0, 0, fail

    def cursor(self):
        return self._cur

    def commit(self):
        if self.fail:
            raise RuntimeError("boom")
        self.commits += 1

    def rollback(self):
        self.rolled += 1


class HeadroomIsMeasuredAgainstTheCap(unittest.TestCase):
    def test_a_largely_empty_store_has_almost_all_the_cap_free(self):
        headroom, size = sb.headroom_mb(_Conn(100.0))
        self.assertEqual(size, 100.0)
        self.assertEqual(headroom, sb.FREE_TIER_MB - 100.0)

    def test_tuple_rows_and_dict_rows_read_the_same(self):
        self.assertEqual(sb.headroom_mb(_Conn(120.0, tuple_rows=True)),
                         sb.headroom_mb(_Conn(120.0)))

    def test_a_custom_cap_is_honoured(self):
        headroom, _ = sb.headroom_mb(_Conn(100.0), limit_mb=200.0)
        self.assertEqual(headroom, 100.0)


class TheFloorRefusesOnlyWhenFull(unittest.TestCase):
    def test_a_store_with_room_is_not_refused(self):
        self.assertIsNone(sb.refuse_if_full(_Conn(100.0)))

    def test_a_store_below_the_floor_is_refused_and_says_how_full(self):
        refusal = sb.refuse_if_full(_Conn(sb.FREE_TIER_MB - 2.0))
        self.assertEqual(refusal["status"], "refused")
        self.assertEqual(refusal["written"], 0)
        self.assertIn("floor", refusal["reason"])
        self.assertEqual(refusal["headroomMB"], 2.0)

    def test_the_check_can_be_disabled(self):
        self.assertIsNone(sb.refuse_if_full(_Conn(sb.FREE_TIER_MB), min_mb=0))


class ThePredictionWriterRespectsTheFloor(unittest.TestCase):
    def _install(self, conn):
        fake = types.ModuleType("nbt")
        fake.db = lambda: conn
        prev = sys.modules.get("nbt")
        sys.modules["nbt"] = fake
        self.addCleanup(lambda: sys.modules.__setitem__("nbt", prev) if prev
                        else sys.modules.pop("nbt", None))

    def test_a_full_store_is_refused_and_nothing_is_inserted(self):
        conn = _Conn(sb.FREE_TIER_MB - 1.0)
        self._install(conn)
        res = sp.write_rows([{"asOf": "2026-10-16"}])
        self.assertEqual(res["status"], "refused")
        self.assertEqual(res["written"], 0)
        # Only the size probe ran; no INSERT statement was issued against the full store.
        self.assertEqual(len(conn._cur.calls), 1)

    def test_a_store_with_room_writes_normally(self):
        conn = _Conn(100.0)
        self._install(conn)
        res = sp.write_rows([])
        self.assertEqual(res, {"written": 0, "status": "ok"})
        self.assertEqual(conn.commits, 1)


class TheOutcomeWriterRespectsTheFloor(unittest.TestCase):
    def _final(self):
        return {"predictionId": "p1", "final": True, "label": "UP", "fwdPct": 1.0,
                "referencePrice": 100.0, "observedPrice": 101.0,
                "observedOn": date(2026, 11, 12), "fromSession": date(2026, 10, 15),
                "toSession": date(2026, 11, 12), "sessionsElapsed": 20, "horizonSessions": 20,
                "mfe": 1.0, "mae": -1.0, "source": None,
                "scoringRule": ss.SCORING_RULE, "scorerVersion": ss.SCORER_VERSION,
                "observedAt": None}

    def test_a_full_store_is_refused_and_reports_how_many_were_eligible(self):
        conn = _Conn(sb.FREE_TIER_MB - 1.0)
        res = ss.write_outcomes(conn.cursor(), conn, [self._final()])
        self.assertEqual(res["status"], "refused")
        self.assertEqual(res["eligible"], 1)
        # The refusal happens before any outcome INSERT.
        self.assertEqual(len(conn._cur.calls), 1)

    def test_a_store_with_room_writes_the_outcome(self):
        conn = _Conn(100.0)
        res = ss.write_outcomes(conn.cursor(), conn, [self._final()])
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["written"], 1)


class TheScheduleStaysBounded(unittest.TestCase):
    """The canary is the one thing that spends the free tier unattended; its limits are stated."""

    def setUp(self):
        self.wf = _nows(
            (ROOT / ".github" / "workflows" / "cron-shadow-canary.yml")
            .read_text(encoding="utf-8"))

    def test_it_runs_on_a_schedule_and_after_the_decision(self):
        self.assertIn("schedule:", self.wf)
        # 23:15 UTC: after the decision job whose factors it reads.
        self.assertIn('-cron:"1523***"', self.wf)
        self.assertIn('"crondecision"', self.wf)

    def test_it_is_bounded_to_two_rows_per_market_per_session(self):
        self.assertIn("--per-market2", self.wf)
        # The cap is DB-backed, so it holds across retries and not only within one invocation.
        self.assertIn("--max-per-market-session2", self.wf)

    def test_it_routes_to_the_per_market_candidates_and_cannot_fall_back(self):
        self.assertIn("--per-market-models", self.wf)
        self.assertNotIn("--modelbrain-v2", self.wf)

    def test_it_passes_the_headroom_floor_to_the_prediction_writer(self):
        self.assertIn("--min-headroom-mb8", self.wf)

    def test_it_records_and_scores_in_the_same_pass(self):
        self.assertIn("tools/research/shadow_predict.py", self.wf)
        self.assertIn("--live", self.wf)
        self.assertIn("shadow_score.py--write", self.wf)

    def test_the_capacity_gate_reads_the_primary_through_the_projects_routing(self):
        # It must not connect to DATABASE_URL directly: that is the Prisma tier the project cannot
        # reach, and an earlier version of this gate failed there before the lane ever wrote.
        self.assertNotIn("importpsycopg", self.wf)
        self.assertIn("fromnbtimportdb", self.wf)
        self.assertIn("shadow_budget.headroom_mb", self.wf)


if __name__ == "__main__":
    unittest.main()
