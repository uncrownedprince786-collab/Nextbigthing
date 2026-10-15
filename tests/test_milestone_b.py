"""Regression tests for the Milestone B findings: ranges, bases, misdated sessions, nulls.

Each test pins one thing that was wrong and is now not, so the fix cannot be undone quietly.
Nothing here touches the database or the network; the dataset gates read committed sidecars and
skip when one is absent rather than passing.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "jobs"))

import ohlc  # noqa: E402

DATA = ROOT / "data" / "foundation"


class RangeValidation(unittest.TestCase):
    """jobs/ohlc.py: a range that cannot hold its close is not stored, and the close is kept."""

    def test_a_contained_close_is_ok(self):
        self.assertEqual(ohlc.classify(10.0, 8.0, 9.0), ohlc.OK)
        self.assertEqual(ohlc.classify(10.0, 8.0, 10.0), ohlc.OK)
        self.assertEqual(ohlc.classify(10.0, 8.0, 8.0), ohlc.OK)

    def test_a_collapsed_range_is_named_separately(self):
        # The exchange's thin-session shape: one value in both columns, a close that is neither.
        self.assertEqual(ohlc.classify(2.10, 2.10, 2.99), ohlc.COLLAPSED)

    def test_a_close_outside_a_real_range_is_incoherent(self):
        self.assertEqual(ohlc.classify(11.68, 9.89, 7.74), ohlc.INCOHERENT)

    def test_an_inverted_range_is_caught_before_anything_else(self):
        self.assertEqual(ohlc.classify(8.0, 10.0, 9.0), ohlc.INVERTED)

    def test_float_noise_is_not_a_defect(self):
        high = 7.58588886260986
        self.assertEqual(ohlc.classify(high, 7.08, high * (1 + 1e-13)), ohlc.FLOAT)

    def test_a_missing_range_is_not_a_breach(self):
        self.assertEqual(ohlc.classify(None, None, 9.0), ohlc.NO_RANGE)
        self.assertEqual(ohlc.classify(10.0, None, 9.0), ohlc.NO_RANGE)

    def test_the_guard_drops_an_untrustworthy_range_and_never_the_close(self):
        # The close is not a return value: nothing in the guard may change it.
        o, h, lo, verdict = ohlc.guard(2.10, 2.10, 2.10, 2.99)
        self.assertEqual(verdict, ohlc.COLLAPSED)
        self.assertEqual((o, h, lo), (None, None, None))

    def test_the_guard_keeps_a_good_bar_exactly(self):
        self.assertEqual(ohlc.guard(9.0, 10.0, 8.0, 9.5), (9.0, 10.0, 8.0, ohlc.OK))

    def test_a_negative_price_is_real_and_not_a_breach(self):
        # CL=F on 2020-04-20 settled at -37.63 inside a range of -40.32 to 17.85. A rule that
        # treats a non-positive price as invalid would delete the day oil went negative.
        self.assertEqual(ohlc.classify(17.85, -40.32, -37.63), ohlc.OK)
        self.assertEqual(ohlc.breach(17.85, -40.32, -37.63), 0.0)

    def test_expectation_separates_a_known_feed_property_from_something_new(self):
        psx = "Pakistan Stock Exchange daily closing file"
        self.assertTrue(ohlc.is_expected(ohlc.COLLAPSED, psx, "stock"))
        self.assertTrue(ohlc.is_expected(ohlc.INCOHERENT, "Yahoo Finance", "forex"))
        # Yahoo's equity bars have never breached beyond float noise; if they start, say so.
        self.assertFalse(ohlc.is_expected(ohlc.INCOHERENT, "Yahoo Finance", "stock"))


class LiveLanesValidate(unittest.TestCase):
    """Both write paths run the guard, so a bad range cannot be reintroduced quietly."""

    def test_both_price_lanes_call_the_guard(self):
        for job in ("psx.py", "prices.py"):
            src = (ROOT / "jobs" / job).read_text(encoding="utf-8")
            self.assertIn("ohlc_guard(", src, job)
            self.assertIn("range_dropped", src, job)

    def test_neither_lane_writes_a_raw_range_beside_the_guard(self):
        # The PSX buffer must carry the guarded values, not row["high"] straight through.
        src = (ROOT / "jobs" / "psx.py").read_text(encoding="utf-8")
        self.assertNotIn('a["id"], day, row["open"], row["high"], row["low"]', src)


class MisdatedSessions(unittest.TestCase):
    """2022-10-01 was Friday's file stored under Saturday's date."""

    def test_the_session_date_is_read_from_the_file(self):
        import psx

        row = "31DEC2021|OGDC|0820|Oil & Gas Dev.|84.20|87.30|84.15|86.20|3368560|84.94|||"
        self.assertEqual(psx.file_session_date(row), date(2021, 12, 31))
        self.assertEqual(
            psx.file_session_date("30SEP2022|ABL|0801|Allied|64.5|64.9|64.5|64.9|1000|64.5|||"),
            date(2022, 9, 30))

    def test_an_unreadable_stamp_does_not_silence_a_real_session(self):
        import psx

        # None, not an exception and not a date: the check must never turn a session it cannot
        # read into a closed market.
        self.assertIsNone(psx.file_session_date("nothing parseable here"))
        self.assertIsNone(psx.file_session_date("30XXX2022|A|1|n|1|1|1|1|1|1|||"))

    def test_read_day_refuses_a_file_stamped_with_another_date(self):
        src = (ROOT / "jobs" / "psx.py").read_text(encoding="utf-8")
        self.assertIn("stamped = file_session_date(text)", src)
        self.assertIn("if stamped is not None and stamped != day:", src)

    def test_the_finding_is_recorded_with_its_rollback(self):
        path = DATA / "psx_complete" / "misdated_sessions.json"
        if not path.exists():
            self.skipTest("misdated_sessions.json not generated")
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["evidence"]["exchangeArchive"]["rowsStampedWith"], "30SEP2022")
        self.assertEqual(doc["evidence"]["storedRows"]["identicalShare"], 1.0)
        self.assertEqual(doc["exposure"]["barsPassingTheCanonicalSessionFilter"], 0)
        self.assertIn("rollback", doc)


class MissingFieldsStayMissing(unittest.TestCase):
    """A field the source never published is not invented from a field it did."""

    def test_a_bar_without_a_range_is_not_filled_with_its_close(self):
        src = (ROOT / "jobs" / "horizons.py").read_text(encoding="utf-8")
        self.assertNotIn('b["high"] = b["close"]', src)
        self.assertNotIn('b["low"] = b["close"]', src)

    def test_true_range_skips_bars_with_no_range_rather_than_counting_them_flat(self):
        import horizons

        bars = [{"high": 11.0, "low": 9.0, "close": 10.0} for _ in range(20)]
        full = horizons.true_range(bars, 14)
        with_gap = list(bars)
        with_gap[5] = {"high": None, "low": None, "close": 10.0}
        self.assertEqual(horizons.true_range(bars[:19] + [with_gap[5]] + bars[19:], 14), full)

    def test_true_range_returns_none_rather_than_a_default_when_too_few_bars_have_a_range(self):
        import horizons

        bars = [{"high": None, "low": None, "close": 10.0} for _ in range(40)]
        self.assertIsNone(horizons.true_range(bars, 14))

    def test_pivots_ignore_a_bar_that_has_no_high_or_low(self):
        import horizons

        shaped = [{"high": h, "low": h - 1.0, "close": h - 0.5}
                  for h in (1.0, 2.0, 5.0, 2.0, 1.0, 2.0, 1.5)]
        highs, _ = horizons.pivots(shaped, 50)
        self.assertIn(5.0, highs)
        blank = {"high": None, "low": None, "close": 99.0}
        highs_with_blank, _ = horizons.pivots(shaped[:3] + [blank] + shaped[3:], 50)
        self.assertNotIn(99.0, highs_with_blank)

    def test_has_range_is_the_single_question_both_ask(self):
        import horizons

        self.assertTrue(horizons.has_range({"high": 1.0, "low": 0.5}))
        self.assertFalse(horizons.has_range({"high": None, "low": 0.5}))
        self.assertFalse(horizons.has_range({"close": 1.0}))


class BasisPolicy(unittest.TestCase):
    """The two PSX bases may not be mixed inside one window without it being visible."""

    def test_the_reader_returns_only_the_steps_no_session_could_make(self):
        from actions import basis_breaks

        path = DATA / "price_verification" / "basis_transitions.json"
        if not path.exists():
            self.skipTest("basis_transitions.json not generated")
        breaks = basis_breaks(path)
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(sum(len(v) for v in breaks.values()), len(doc["exceptions"]))

    def test_an_absent_ledger_is_empty_and_not_an_error(self):
        from actions import basis_breaks

        self.assertEqual(basis_breaks(None), {})
        self.assertEqual(basis_breaks(ROOT / "no" / "such" / "file.json"), {})

    def test_the_assembly_carries_the_flag(self):
        src = (ROOT / "tools" / "foundation" / "assemble.py").read_text(encoding="utf-8")
        self.assertIn("basisBreakInWindow", src)
        self.assertIn("from actions import basis_breaks", src)

    def test_the_measurement_is_what_justifies_not_excluding_half_the_windows(self):
        path = DATA / "price_verification" / "basis_transitions.json"
        if not path.exists():
            self.skipTest("basis_transitions.json not generated")
        doc = json.loads(path.read_text(encoding="utf-8"))
        # The claim the policy rests on: joining two bases is not worse than an ordinary
        # session. If that ever stops being true, this test is the thing that notices.
        self.assertLessEqual(doc["crossBasis"]["rate"], doc["sameBasis"]["rate"])
        self.assertGreater(doc["windows"]["shareSpanning"], 0.4)
        self.assertLess(doc["windows"]["shareExcluded"], 0.01)


class QuarantineLedger(unittest.TestCase):
    """The stored contradictions are accounted for exactly, not approximately."""

    def test_the_counts_reconcile(self):
        path = DATA / "price_verification" / "ohlc_quarantine.json"
        if not path.exists():
            self.skipTest("ohlc_quarantine.json not generated")
        doc = json.loads(path.read_text(encoding="utf-8"))
        r = doc["reconciliation"]
        self.assertEqual(r["quarantined"] + r["floatRepresentation"], r["databaseComparisonFinds"])

    def test_every_quarantined_group_states_a_reason(self):
        path = DATA / "price_verification" / "ohlc_quarantine.json"
        if not path.exists():
            self.skipTest("ohlc_quarantine.json not generated")
        doc = json.loads(path.read_text(encoding="utf-8"))
        for g in doc["ledger"]:
            if g["quarantined"]:
                self.assertTrue(g["reason"], f"{g['source']} {g['class']} has no reason")


if __name__ == "__main__":
    unittest.main()
