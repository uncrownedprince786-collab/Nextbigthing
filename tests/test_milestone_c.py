"""Regression tests for the event corpus load and the event-to-reaction dataset.

The unit tests run on synthetic series where the right answer is known. The dataset gates read
the committed artifact and fail if a stated threshold is not met, so "no leakage" is enforced
rather than asserted in a report. A gate whose artifact is absent is skipped, never passed.
"""

from __future__ import annotations

import gzip
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "jobs"))

import event_reactions as er  # noqa: E402
import events_load as el  # noqa: E402

DATA = ROOT / "data" / "foundation" / "events"
REACTIONS = DATA / "reactions.jsonl.gz"


def load_rows() -> list[dict]:
    with gzip.open(REACTIONS, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class CorpusLoad(unittest.TestCase):
    def test_only_verified_events_are_loaded(self):
        doc = {"events": [{"name": "a", "date": "2020-01-01", "verified": True},
                          {"name": "b", "date": "2020-01-02", "verified": False},
                          {"name": "c", "date": "2020-01-03"}]}
        self.assertEqual([e["name"] for e in el.verified_events(doc)], ["a"])

    def test_the_slug_is_stable_and_carries_the_date(self):
        a = el.slugify("Russia invades Ukraine", "2022-02-24")
        self.assertEqual(a, el.slugify("Russia invades Ukraine", "2022-02-24"))
        self.assertTrue(a.endswith("2022-02-24"))
        # Two events with the same name on different dates must not collide on one row.
        self.assertNotEqual(a, el.slugify("Russia invades Ukraine", "2022-02-25"))

    def test_provenance_travels_onto_the_row(self):
        e = {"name": "X", "date": "2021-05-05", "category": "monetary", "tier": "A",
             "evidenceGroups": ["wikimedia", "market-move"],
             "wikipedia": {"url": "https://en.wikipedia.org/wiki/X"},
             "instrument": "NVDA", "market": {"checked": True, "moved": True}}
        r = el.row_for(e, 1, "2026-10-14T11:26:55+00:00")
        self.assertEqual(r["sourceUrl"], "https://en.wikipedia.org/wiki/X")
        self.assertIn("tier A", r["notes"])
        self.assertIn("wikimedia", r["notes"])
        self.assertEqual(r["discoveredAt"], "2026-10-14T11:26:55+00:00")

    def test_a_market_proxy_is_labelled_not_forced_onto_a_ticker(self):
        e = {"name": "Y", "date": "2020-03-16", "instrument": "MKT", "tier": "A",
             "evidenceGroups": ["wikimedia"]}
        self.assertIn("market proxy", el.row_for(e, 1, "2026-01-01T00:00:00+00:00")["notes"])


class ReactionArithmetic(unittest.TestCase):
    def test_percent_change_refuses_an_unusable_base(self):
        self.assertAlmostEqual(er.pct(100.0, 110.0), 10.0)
        self.assertIsNone(er.pct(0.0, 5.0))
        self.assertIsNone(er.pct(-3.0, 5.0))

    def test_the_before_state_never_reads_the_event_session(self):
        dates = [date(2020, 1, d) for d in range(1, 11)]
        closes = [float(c) for c in range(100, 110)]
        vols = [1000.0] * 10
        b = er.before_state(dates, closes, vols, 5)
        self.assertEqual(b["lastSession"], "2020-01-05")
        self.assertEqual(b["lastClose"], 104.0)
        self.assertEqual(b["sessionsAvailable"], 5)

    def test_the_before_state_is_empty_rather_than_guessed_at_the_first_bar(self):
        self.assertEqual(er.before_state([date(2020, 1, 1)], [100.0], [None], 0),
                         {"sessionsAvailable": 0})

    def test_an_unfinished_window_is_none_and_never_a_short_one(self):
        dates = [date(2020, 1, d) for d in range(1, 8)]
        closes = [100.0] * 7
        self.assertIsNone(er.forward_block(dates, closes, 2, 20))
        self.assertIsNotNone(er.forward_block(dates, closes, 2, 4))

    def test_excursions_and_drawdown_are_measured_from_the_entry(self):
        dates = [date(2020, 1, d) for d in range(1, 7)]
        closes = [100.0, 100.0, 110.0, 90.0, 95.0, 95.0]
        blk = er.forward_block(dates, closes, 1, 4)
        self.assertAlmostEqual(blk["returnPct"], -5.0, places=4)
        self.assertAlmostEqual(blk["maxFavourablePct"], 10.0, places=4)
        self.assertAlmostEqual(blk["maxAdversePct"], -10.0, places=4)
        # The worst fall from a running peak, not the worst level: 110 -> 90.
        self.assertAlmostEqual(blk["maxDrawdownPct"], -18.1818, places=3)

    def test_the_session_lookup_lands_on_or_after_the_target(self):
        dates = [date(2020, 1, 2), date(2020, 1, 6), date(2020, 1, 7)]
        self.assertEqual(er.index_on_or_after(dates, date(2020, 1, 6)), 1)
        self.assertEqual(er.index_on_or_after(dates, date(2020, 1, 4)), 1)
        self.assertIsNone(er.index_on_or_after(dates, date(2020, 2, 1)))

    def test_an_instrument_is_never_its_own_benchmark(self):
        src = (ROOT / "tools" / "foundation" / "event_reactions.py").read_text(encoding="utf-8")
        self.assertIn('key != "MKT"', src)


class ReactionDatasetGates(unittest.TestCase):
    """Read the committed artifact and enforce what the closeout claims about it."""

    def setUp(self):
        if not REACTIONS.exists():
            self.skipTest("reactions.jsonl.gz not generated")
        self.rows = load_rows()

    def test_no_before_state_is_dated_on_or_after_its_event(self):
        for r in self.rows:
            last = r["before"].get("lastSession")
            if last:
                self.assertLess(date.fromisoformat(last), date.fromisoformat(r["eventDate"]),
                                r["name"])

    def test_every_forward_window_starts_after_the_event_session(self):
        for r in self.rows:
            d0 = date.fromisoformat(r["day0"]["session"])
            for h, blk in r["forward"].items():
                if blk:
                    self.assertGreater(date.fromisoformat(blk["entrySession"]), d0,
                                       f"{r['name']} {h}d")

    def test_every_window_ends_after_it_starts(self):
        for r in self.rows:
            for h, blk in r["forward"].items():
                if blk:
                    self.assertGreater(date.fromisoformat(blk["exitSession"]),
                                       date.fromisoformat(blk["entrySession"]),
                                       f"{r['name']} {h}d")

    def test_the_corpus_holds_both_outcomes_and_is_not_a_success_reel(self):
        # A dataset of only winners is selection bias wearing a label. Each horizon must carry
        # losses at a share no honest market study could fall below.
        for h in ("1", "5", "20"):
            blocks = [r["forward"][h] for r in self.rows if r["forward"].get(h)]
            downs = sum(1 for b in blocks if b["direction"] == "down")
            self.assertGreater(downs / len(blocks), 0.30, f"{h}d has too few losses")
            self.assertLess(downs / len(blocks), 0.70, f"{h}d has too few gains")

    def test_the_day_zero_move_does_not_predict_the_window(self):
        # If continuation ran near 1.0 the forward block would be re-reporting day 0 rather than
        # measuring what followed it.
        cont = [r["forward"]["20"]["continuation"] for r in self.rows
                if r["forward"].get("20") and r["forward"]["20"]["continuation"] is not None]
        share = sum(cont) / len(cont)
        self.assertGreater(share, 0.25)
        self.assertLess(share, 0.75)

    def test_coverage_matches_the_manifest(self):
        man = json.loads((DATA / "reactions_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(man["rowsWritten"], len(self.rows))
        for h, n in man["horizonCoverage"].items():
            got = sum(1 for r in self.rows if r["forward"].get(h))
            self.assertEqual(got, n, f"horizon {h}")

    def test_the_private_index_segment_was_not_used(self):
        man = json.loads((DATA / "reactions_manifest.json").read_text(encoding="utf-8"))
        self.assertIn("not read", man["privateData"])
        # The docstring names the file to explain why it is not used, so the test is about the
        # path, not the word: no code path may open the private cache.
        src = (ROOT / "tools" / "foundation" / "event_reactions.py").read_text(encoding="utf-8")
        for forbidden in ("acquire/karandaaz", "acquire\\karandaaz", "kse100_karandaaz"):
            self.assertNotIn(forbidden, src)

    def test_every_row_carries_its_evidence(self):
        for r in self.rows:
            self.assertIn(r["tier"], ("A", "B", "C"), r["name"])
            self.assertTrue(r["evidenceGroups"], r["name"])


class PsxSeriesFix(unittest.TestCase):
    def test_the_reaction_series_reads_the_whole_pkr_market(self):
        # `source ILIKE 'Pakistan%'` read the exchange file only and skipped the 183,267
        # recovered Karachi bars (brain.md rule 130 named this line).
        # The old predicate is still named in the comment that explains the change, so the test
        # reads the executable lines only.
        src = (ROOT / "tools" / "foundation" / "events.py").read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
        self.assertNotIn("source ILIKE 'Pakistan%'", code)
        self.assertIn("a.currency = 'PKR'", code)

    def test_the_reaction_builder_uses_the_same_rule(self):
        src = (ROOT / "tools" / "foundation" / "event_reactions.py").read_text(encoding="utf-8")
        self.assertIn("a.currency = 'PKR'", src)


if __name__ == "__main__":
    unittest.main()
