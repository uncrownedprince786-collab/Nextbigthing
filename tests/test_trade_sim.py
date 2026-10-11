"""The trade simulation and the directional verdict, kept apart (brain.md rule 95), on synthetic bars.

Every case the owner named: stop first, target first, both touched, no fill, gap through the stop, expiry,
withdrawal, missing bars, repeated grading -- and the conservative choices the daily bars force.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "jobs"))

import trade_sim as ts  # noqa: E402

D0 = date(2026, 10, 12)  # Monday: the session the call was read from


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def long_call(**over):
    # Zone 98-100, stop 95 (risk 5 from the 100 entry), measured exit 110 (2R).
    c = {"id": "c1", "assetId": "A", "action": "LONG", "entryLow": 98.0, "entryHigh": 100.0, "stop": 95.0,
         "target": 110.0, "baseSession": D0, "baseClose": 101.0, "validUntil": day(7), "published": True,
         "periodEnd": D0, "startedAt": "2026-10-12T22:10:00", "validFrom": D0, "market": "US",
         "confidence": "High", "horizon": "swing"}
    c.update(over)
    return c


def short_call(**over):
    c = long_call(action="SHORT", entryLow=100.0, entryHigh=102.0, stop=105.0, target=90.0, baseClose=99.0)
    c.update(over)
    return c


AFTER = day(30)  # the window has long closed


class TradeOutcomes(unittest.TestCase):
    def test_target_first(self):
        bars = [(day(1), 101, 102, 99.5, 101), (day(2), 101, 111, 100.5, 109)]
        t = ts.simulate(long_call(), bars, AFTER)
        self.assertEqual((t["trade"], t["fillOn"], t["fillPrice"], t["exitPrice"]), ("TARGET_FIRST", day(1), 100.0, 110.0))
        self.assertEqual(t["grossR"], 2.0)
        self.assertTrue(t["final"])

    def test_stop_first(self):
        bars = [(day(1), 101, 102, 99.5, 100), (day(2), 99, 99.5, 94, 95.5)]
        t = ts.simulate(long_call(), bars, AFTER)
        self.assertEqual((t["trade"], t["exitPrice"], t["grossR"]), ("STOP_FIRST", 95.0, -1.0))

    def test_both_touched_on_one_bar_is_ambiguous_never_the_favourable_one(self):
        bars = [(day(1), 101, 102, 99.5, 100), (day(2), 100, 111, 94, 100)]
        t = ts.simulate(long_call(), bars, AFTER)
        self.assertEqual(t["trade"], "AMBIGUOUS")
        self.assertIsNone(t["grossR"])
        # ... and the expectancy books it at the stop.
        b = ts.bucket([{**long_call(), **t, "direction": "stopped"}])
        self.assertEqual(b["grossRExpectancy"]["mean"], -1.0)

    def test_never_reaching_the_entry_is_not_filled_not_a_win_or_a_loss(self):
        bars = [(day(i), 103, 106, 101, 105) for i in range(1, 6)]
        t = ts.simulate(long_call(), bars, AFTER)
        self.assertEqual(t["trade"], "NOT_FILLED")
        self.assertIsNone(t["grossR"])
        b = ts.bucket([{**long_call(), **t, "direction": "right"}])
        self.assertEqual(b["fillRate"], {"k": 0, "n": 1, "rate": 0.0})
        self.assertEqual(b["grossRExpectancy"]["n"], 0)

    def test_a_gap_through_the_stop_exits_at_the_open_and_costs_more_than_one_r(self):
        bars = [(day(1), 101, 102, 99.5, 100), (day(2), 92, 93, 90, 91)]
        t = ts.simulate(long_call(), bars, AFTER)
        self.assertEqual((t["trade"], t["exitPrice"], t["gapThrough"]), ("STOP_FIRST", 92, True))
        self.assertAlmostEqual(t["grossR"], -1.6)

    def test_a_gap_through_the_exit_fills_at_the_open(self):
        bars = [(day(1), 101, 102, 99.5, 100), (day(2), 112, 113, 111, 112)]
        t = ts.simulate(long_call(), bars, AFTER)
        self.assertEqual((t["trade"], t["exitPrice"]), ("TARGET_FIRST", 112))
        self.assertAlmostEqual(t["grossR"], 2.4)

    def test_an_open_trade_at_the_end_of_its_window_expires_at_the_last_close(self):
        bars = [(day(1), 101, 102, 99.5, 100)] + [(day(i), 102, 104, 101, 103) for i in range(2, 8)] + [(day(9), 120, 121, 119, 120)]
        t = ts.simulate(long_call(), bars, AFTER)
        self.assertEqual((t["trade"], t["exitOn"], t["exitPrice"]), ("EXPIRED", day(7), 103))
        self.assertAlmostEqual(t["grossR"], 0.6)

    def test_a_call_withdrawn_before_it_filled(self):
        bars = [(day(1), 103, 104, 101, 103), (day(2), 101, 102, 99, 100)]
        t = ts.simulate(long_call(), bars, AFTER, verdicts=[(day(1), "WAIT")])
        self.assertEqual(t["trade"], "WITHDRAWN")
        # Withdrawn on the evening of day 1, so the day-2 fill never happens. A verdict of the same side
        # does not withdraw it.
        t = ts.simulate(long_call(), bars, AFTER, verdicts=[(day(1), "LONG")])
        self.assertEqual((t["trade"], t["fillOn"]), ("EXPIRED", day(2)))

    def test_opening_beyond_the_stop_before_the_fill_invalidates_the_plan(self):
        bars = [(day(1), 94, 96, 93, 95)]
        self.assertEqual(ts.simulate(long_call(), bars, AFTER)["trade"], "INVALIDATED_BEFORE_FILL")

    def test_missing_or_contradictory_bars_are_unavailable_and_stay_in_the_count(self):
        self.assertEqual(ts.simulate(long_call(), [], AFTER)["trade"], "UNAVAILABLE")
        # The live case: USDPKR closed at 276.7 above a high of 268.2.
        bad = [(day(1), 101, 102, 99.5, 120)]
        self.assertEqual(ts.simulate(long_call(), bad, AFTER)["trade"], "UNAVAILABLE")
        self.assertEqual(ts.simulate(long_call(), [(day(1), None, 102, 99, 100)], AFTER)["trade"], "UNAVAILABLE")
        self.assertEqual(ts.simulate(long_call(stop=None), [], AFTER)["trade"], "UNAVAILABLE")

    def test_a_window_still_open_is_pending_and_not_final(self):
        bars = [(day(1), 103, 104, 101, 103)]
        t = ts.simulate(long_call(), bars, day(3))
        self.assertEqual((t["trade"], t["final"]), ("PENDING", False))
        self.assertEqual(ts.simulate(long_call(), [], day(3))["trade"], "PENDING")

    def test_on_the_fill_session_a_stop_touch_counts_and_an_exit_touch_does_not(self):
        # Opened above the zone, came down through 100 (filled inside the bar), and also traded at 110: the
        # 110 may have come before the fill, so it is not counted.
        bars = [(day(1), 108, 110.5, 99.5, 101), (day(2), 101, 103, 100.5, 102)]
        t = ts.simulate(long_call(validUntil=day(2)), bars, AFTER)
        self.assertEqual(t["trade"], "EXPIRED")
        # Filled at the open inside the zone, then 110 the same day: that exit came after the fill.
        bars = [(day(1), 99, 110.5, 98.5, 109)]
        self.assertEqual(ts.simulate(long_call(), bars, AFTER)["trade"], "TARGET_FIRST")
        # Filled inside the bar and the same bar reached the stop: booked at the stop.
        bars = [(day(1), 103, 104, 94, 96)]
        self.assertEqual(ts.simulate(long_call(), bars, AFTER)["trade"], "STOP_FIRST")

    def test_nothing_fills_on_the_session_the_call_was_read_from(self):
        bars = [(D0, 99, 112, 98, 101), (day(1), 104, 106, 103, 105)]
        self.assertEqual(ts.simulate(long_call(validUntil=day(1)), bars, AFTER)["trade"], "NOT_FILLED")

    def test_the_short_side_mirrors_it(self):
        bars = [(day(1), 99, 100.5, 98, 99), (day(2), 98, 99, 89, 90)]
        t = ts.simulate(short_call(), bars, AFTER)
        self.assertEqual((t["trade"], t["fillPrice"], t["exitPrice"]), ("TARGET_FIRST", 100.0, 90.0))
        self.assertEqual(t["grossR"], 2.0)
        t = ts.simulate(short_call(), [(day(1), 101, 106, 100, 104)], AFTER)
        self.assertEqual(t["trade"], "STOP_FIRST")


class TheTwoOutcomesStayApart(unittest.TestCase):
    def test_right_direction_and_a_stopped_trade_are_both_recorded(self):
        # The stop trades on day 2, and five sessions later the price is above the call's close: the
        # scorecard says "stopped" (its stop beats the move), the trade says STOP_FIRST.
        bars = [(day(1), 101, 102, 99.5, 100), (day(2), 99, 99.5, 94, 96)] + [(day(i), 100, 104, 99, 103) for i in range(3, 8)]
        g = ts.grade([long_call()], {"A": bars}, AFTER)[0]
        self.assertEqual((g["direction"], g["trade"]), ("stopped", "STOP_FIRST"))
        # A direction that came true from a call that never filled.
        bars = [(day(i), 103, 106, 101, 105) for i in range(1, 8)]
        g = ts.grade([long_call()], {"A": bars}, AFTER)[0]
        self.assertEqual((g["direction"], g["trade"]), ("right", "NOT_FILLED"))


class OneTradePerPosition(unittest.TestCase):
    def test_reruns_and_the_next_days_reissue_are_one_position(self):
        calls = [
            long_call(id="a", startedAt="2026-10-12T22:10:00"),
            long_call(id="b", startedAt="2026-10-12T23:14:00"),  # a second pass the same day
            long_call(id="c", startedAt="2026-10-13T22:10:00", periodEnd=day(1)),  # re-issued, still open
            long_call(id="d", startedAt="2026-10-12T21:00:00", published=False),  # withheld: never graded
            long_call(id="e", action="SHORT", startedAt="2026-10-14T22:10:00", periodEnd=day(2), validFrom=day(2)),
        ]
        got = sorted(c["id"] for c in ts.units(calls))
        self.assertEqual(got, ["a", "e"])

    def test_grading_twice_gives_the_same_answer(self):
        bars = [(day(1), 101, 102, 99.5, 100), (day(2), 101, 111, 100.5, 109)] + [(day(i), 105, 106, 104, 105) for i in range(3, 8)]
        once = ts.grade([long_call()], {"A": bars}, AFTER)
        twice = ts.grade([long_call()], {"A": list(reversed(bars))}, AFTER)
        self.assertEqual(once, twice)
        self.assertTrue(once[0]["final"])


class TheSummaryClaimsNothingItHasNotMeasured(unittest.TestCase):
    def test_every_rate_carries_its_count_and_no_expectancy_is_claimed_below_the_sample(self):
        rows = [{**long_call(), **ts.simulate(long_call(), [(day(1), 101, 111, 99.5, 109)], AFTER), "direction": "right"}]
        s = ts.summarise(rows, AFTER)
        self.assertEqual(s["minSample"], 30)
        for key in ("fillRate", "targetFirst", "stopFirst", "expired", "ambiguous"):
            self.assertIn("n", s["all"][key])
        self.assertFalse(s["all"]["grossRExpectancy"]["measured"])
        self.assertEqual(set(s), {"asOf", "since", "minSample", "all", "byMarket", "bySide", "byHorizon", "byConfidence", "assumptions"})
        self.assertIn("US", s["byMarket"])
        self.assertIn("LONG", s["bySide"])
        self.assertTrue(any("gross" in a for a in s["assumptions"]))

    def test_an_empty_history_says_so(self):
        s = ts.summarise([], AFTER)
        self.assertEqual(s["all"]["calls"], 0)
        self.assertIsNone(s["all"]["fillRate"]["rate"])
        self.assertIsNone(s["since"])


class TheHistoryIsAppendOnly(unittest.TestCase):
    MIGRATION = ROOT / "prisma" / "migrations" / "20261011130000_decision_history" / "migration.sql"

    def test_the_database_refuses_to_rewrite_a_call_a_finished_run_or_a_final_outcome(self):
        sql = self.MIGRATION.read_text(encoding="utf-8")
        self.assertIn('BEFORE UPDATE OR DELETE ON "DecisionCall"', sql)
        self.assertIn('BEFORE UPDATE ON "DecisionRun"', sql)
        self.assertIn("IF OLD.\"status\" <> 'running' THEN", sql)
        self.assertIn('BEFORE DELETE ON "DecisionRun"', sql)
        self.assertIn('BEFORE UPDATE ON "CallOutcome"', sql)
        self.assertIn('IF OLD."final" THEN', sql)
        self.assertIn('CREATE UNIQUE INDEX "DecisionCall_runId_assetId_key"', sql)
        # It adds history and removes nothing.
        for verb in ("DELETE FROM", "DROP TABLE", "TRUNCATE", "ALTER TABLE \"DecisionLog\""):
            self.assertNotIn(verb, sql)

    def test_the_grader_writes_only_outcomes_that_are_not_yet_final(self):
        self.assertIn('WHERE NOT "CallOutcome".final', ts.UPSERT_OUTCOME)
        self.assertIn("r.status IN ('complete', 'partial')", ts.CALLS_SQL)


class SessionsOnly(unittest.TestCase):
    """Weekend stubs (rule 95): the same rule in the jobs, the decision job and the site."""

    def test_the_rule(self):
        from sessions import session_bar, trades_on

        self.assertFalse(trades_on("forex", date(2026, 10, 10)))
        self.assertFalse(trades_on("stock", date(2026, 10, 11)))
        self.assertTrue(trades_on("crypto", date(2026, 10, 10)))
        self.assertTrue(trades_on("forex", date(2026, 10, 9)))
        self.assertEqual(
            session_bar("s"),
            '(EXTRACT(ISODOW FROM s."date") < 6 OR s."assetId" IN (SELECT id FROM "Asset" WHERE "assetType" = \'crypto\'))',
        )

    def test_every_close_reader_on_the_decision_path_skips_weekend_stubs(self):
        inline = "(a.\"assetType\" = 'crypto' OR EXTRACT(ISODOW FROM s.date) < 6)"
        queries = (ROOT / "lib" / "queries.ts").read_text(encoding="utf-8")
        self.assertEqual(queries.count(inline), 3, "decision rows, health and the data stamp")
        decide = (ROOT / "tools" / "decide.mjs").read_text(encoding="utf-8")
        self.assertIn("WHERE a.\"assetType\" = 'crypto' OR EXTRACT(ISODOW FROM s.date) < 6", decide)
        self.assertIn("AND (EXTRACT(ISODOW FROM date) < 6 OR \"assetId\" IN (SELECT id FROM \"Asset\" WHERE \"assetType\" = 'crypto'))", decide)
        for job in ("factors.py", "setup.py", "horizons.py"):
            self.assertIn("{session_bar()}", (ROOT / "jobs" / job).read_text(encoding="utf-8"), job)
        for tool in ("scorecard.py", "audit_log.py", "trade_sim.py"):
            self.assertIn("session_bar()", (ROOT / "tools" / tool).read_text(encoding="utf-8"), tool)

    def test_the_yahoo_writer_drops_weekend_bars(self):
        import prices

        sat = 1_791_590_400  # 2026-10-10 00:00 UTC
        fri = sat - 86_400
        payload = {"chart": {"result": [{
            "meta": {},
            "timestamp": [fri, sat],
            "indicators": {"quote": [{"open": [1.0, 1.1], "high": [1.2, 1.1], "low": [0.9, 1.1], "close": [1.1, 1.1], "volume": [None, None]}],
                           "adjclose": [{"adjclose": [1.1, 1.1]}]},
        }]}}
        got = prices.parse_chart(payload)
        self.assertEqual([b[0] for b in got], [date(2026, 10, 9)])


if __name__ == "__main__":
    unittest.main()
