"""The context producer: can anything dated after the session reach the session's features?

    python -m unittest discover -s tests -p test_context_features.py -v

Stdlib unittest, no database, no network, and no repository artifact — every fixture is written
into a temporary directory, so these run anywhere in under a second.

The centre of this file is one property, tested four ways because the four layers carry four
different availability rules: **a feature computed at a session must not change when data dated
after that session is added or altered.** `tools/foundation/pit_features.py` is tested the same
way, by perturbing every bar after a session and requiring the session's row to be unchanged. A
leak that passes a value-equality test still fails that one, which is why it is here.

The rest covers what the producer must refuse: an unverified event, a duplicated article, a
reaction whose window has not closed, and an absent reading that could be quietly rendered as a
zero. A zero is a measurement. `None` is the absence of one. Collapsing them is the failure this
producer exists to avoid.
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import context_features as cf  # noqa: E402


# --- fixtures ---------------------------------------------------------------------------------

def macro_row(d: str, chg: float = 0.1, age: int = 1) -> dict:
    return {"d": d, "m": {s: {"v": 1.0, "age": age, "chg": chg} for s in cf.SERIES}}


def write_macro(dirpath: Path, rows: list[dict]) -> Path:
    p = dirpath / "macro-sessions.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def write_events(dirpath: Path, events: list[dict]) -> Path:
    p = dirpath / "events.json"
    p.write_text(json.dumps({"summary": {}, "events": events}), encoding="utf-8")
    return p


def an_event(d: str, instrument: str = "AAPL", verified: bool = True, **over) -> dict:
    e = {"name": "a thing happened", "category": "corporate", "date": d, "instrument": instrument,
         "cluster": "c", "tier": "B", "verified": verified,
         # The future at the event's own date. It must never reach a feature.
         "market": {"peakDate": "2099-01-01", "z": 424242.0, "returnPct": 424242.0}}
    e.update(over)
    return e


def write_press(dirpath: Path, records: list[dict]) -> Path:
    p = dirpath / "press.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return p


def a_press(published: str, instrument: str = "AAPL", dedupe: str = None, **over) -> dict:
    r = {"instrument": instrument, "publishedAt": published,
         "retrievedAt": "2099-01-01T00:00:00+00:00",       # collection time is not availability
         "dedupeKey": dedupe or f"k-{published}-{instrument}", "url": f"http://x/{published}"}
    r.update(over)
    return r


def write_reactions(dirpath: Path, records: list[dict]) -> Path:
    p = dirpath / "reactions.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return p


def a_reaction(event_date: str, exit_session: str, ret: float, symbol: str = "AAPL") -> dict:
    return {"eventDate": event_date, "symbol": symbol, "instrument": symbol,
            "forward": {cf.PRIOR_HORIZON: {"entrySession": event_date,
                                           "exitSession": exit_session, "returnPct": ret}}}


def source(tmp: Path, *, macro=None, events=None, press=None, reactions=None) -> cf.ContextSource:
    d = Path(tmp)
    return cf.ContextSource.load(
        macro=write_macro(d, macro) if macro is not None else d / "none.gz",
        events=write_events(d, events) if events is not None else d / "none.json",
        press=write_press(d, press) if press is not None else d / "none.jsonl",
        reactions=write_reactions(d, reactions) if reactions is not None else d / "none2.gz",
    )


# --- the property that matters ------------------------------------------------------------------

class TheFutureCannotReachThePast(unittest.TestCase):
    """Add or change data dated after a session; the session's features must not move."""

    AS_OF = date(2024, 3, 1)

    def test_macro_dated_after_the_session_is_never_the_row_used(self):
        with tempfile.TemporaryDirectory() as t:
            before = [macro_row("2024-02-28", chg=0.1), macro_row("2024-03-01", chg=0.2)]
            a = source(t, macro=before).macro_at(self.AS_OF)
        with tempfile.TemporaryDirectory() as t:
            after = before + [macro_row("2024-03-04", chg=99.0), macro_row("2024-06-01", chg=99.0)]
            b = source(t, macro=after).macro_at(self.AS_OF)
        self.assertEqual(a, b)
        self.assertEqual(a["asOf"], "2024-03-01")
        self.assertEqual(a["f"]["macro_DGS10_chg"], 0.2)

    def test_an_event_on_the_session_itself_is_not_yet_evidence(self):
        """Strictly before. An announcement must not inform the bar it moved."""
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-20"), an_event("2024-03-01"),
                                  an_event("2024-03-02")])
            got = s.events_at(self.AS_OF, "AAPL")
        self.assertEqual(got["f"]["ctx_eventsIn90d"], 1.0)
        self.assertEqual(got["f"]["ctx_daysSinceEvent"], 10.0)

    def test_press_published_on_or_after_the_session_does_not_count(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, press=[a_press("2024-02-25"), a_press("2024-03-01"),
                                 a_press("2024-03-05")])
            self.assertEqual(s.press_at(self.AS_OF, "AAPL")["f"]["ctx_pressIn90d"], 1.0)

    def test_a_reaction_window_that_has_not_closed_is_not_a_prior(self):
        """The artifact dates its own window, so maturity is read, not assumed."""
        with tempfile.TemporaryDirectory() as t:
            s = source(t, reactions=[
                a_reaction("2024-01-02", "2024-02-01", 5.0),    # closed: counts
                a_reaction("2024-02-01", "2024-03-01", 99.0),   # closes on the session: does not
                a_reaction("2024-02-20", "2024-03-20", 99.0),   # still open: does not
            ])
            got = s.prior_at(self.AS_OF, "AAPL")
        self.assertEqual(got["f"]["ctx_maturedPriors"], 1.0)
        self.assertEqual(got["f"]["ctx_priorMedianFwd20"], 5.0)

    def test_the_whole_block_is_unchanged_when_the_future_is_rewritten(self):
        base = dict(macro=[macro_row("2024-02-28"), macro_row("2024-03-01")],
                    events=[an_event("2024-02-01")], press=[a_press("2024-02-10")],
                    reactions=[a_reaction("2024-01-02", "2024-02-01", 3.0)])
        future = dict(
            macro=base["macro"] + [macro_row("2024-03-02", chg=99.0)],
            events=base["events"] + [an_event("2024-03-01"), an_event("2024-05-05")],
            press=base["press"] + [a_press("2024-03-01"), a_press("2024-04-04")],
            reactions=base["reactions"] + [a_reaction("2024-02-25", "2024-03-25", 99.0)])
        with tempfile.TemporaryDirectory() as t:
            a = source(t, **base).at(self.AS_OF, "AAPL")
        with tempfile.TemporaryDirectory() as t:
            b = source(t, **future).at(self.AS_OF, "AAPL")
        self.assertEqual(cf.ContextSource.vector(a), cf.ContextSource.vector(b))


class TheEventsOwnReactionIsNeverAFeature(unittest.TestCase):
    """`market` holds peakDate, z and returnPct -- what the market did *after* the event."""

    def test_no_forbidden_key_reaches_the_block_or_the_vector(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-01-05")])
            block = s.at(date(2024, 3, 1), "AAPL")
        text = json.dumps(block)
        for k in cf.FORBIDDEN_KEYS:
            self.assertNotIn(k, text, f"{k} reached the context block")
        self.assertNotIn("424242", text, "the event's own market reaction reached the block")
        self.assertNotIn(424242.0, cf.ContextSource.vector(block))


# --- refusals ------------------------------------------------------------------------------------

class MissingIsMissingAndNeverZero(unittest.TestCase):
    """"Could not look" is not "nothing there", and a model cannot tell them apart from a 0."""

    def test_with_no_artifacts_every_block_is_absent_and_every_feature_is_none(self):
        with tempfile.TemporaryDirectory() as t:
            block = cf.ContextSource.load(
                macro=Path(t) / "x.gz", events=Path(t) / "x.json",
                press=Path(t) / "x.jsonl", reactions=Path(t) / "x2.gz",
            ).at(date(2024, 3, 1), "AAPL")
        for part in ("macro", "events", "press", "reactionPrior"):
            self.assertEqual(block[part]["status"], "absent", part)
            self.assertIn("reason", block[part])
        self.assertTrue(all(v is None for v in cf.ContextSource.vector(block)))

    def test_a_session_before_the_artifact_starts_is_absent_not_an_error(self):
        with tempfile.TemporaryDirectory() as t:
            got = source(t, macro=[macro_row("2024-03-01")]).macro_at(date(2019, 1, 1))
        self.assertEqual(got["status"], "absent")
        self.assertTrue(all(v is None for v in got["f"].values()))

    def test_an_instrument_with_no_reaction_is_absent_and_a_dry_spell_is_a_measured_zero(self):
        """These two differ and the producer must not say the same thing about both."""
        with tempfile.TemporaryDirectory() as t:
            s = source(t, reactions=[a_reaction("2024-02-20", "2024-03-20", 1.0)])
            unknown = s.prior_at(date(2024, 3, 1), "ZZZZ")
            known_but_open = s.prior_at(date(2024, 3, 1), "AAPL")
        self.assertIsNone(unknown["f"]["ctx_maturedPriors"])
        self.assertEqual(known_but_open["f"]["ctx_maturedPriors"], 0.0)

    def test_a_stale_macro_row_is_still_reported_with_its_age(self):
        with tempfile.TemporaryDirectory() as t:
            got = source(t, macro=[macro_row("2024-01-02")]).macro_at(date(2024, 3, 1))
        self.assertEqual(got["status"], "observed")
        self.assertEqual(got["ageDays"], 59)


class BadRecordsAreRefusedRatherThanCounted(unittest.TestCase):

    def test_an_unverified_event_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-01", verified=False),
                                  an_event("2024-02-02", verified=True)])
            self.assertEqual(s.events_at(date(2024, 3, 1), "AAPL")["f"]["ctx_eventsIn90d"], 1.0)

    def test_the_same_article_under_two_routes_counts_once(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, press=[a_press("2024-02-10", dedupe="same"),
                                 a_press("2024-02-10", dedupe="same", route="other"),
                                 a_press("2024-02-11", dedupe="different")])
            self.assertEqual(s.press_at(date(2024, 3, 1), "AAPL")["f"]["ctx_pressIn90d"], 2.0)

    def test_a_record_with_no_publication_time_has_no_availability_and_is_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            rec = a_press("2024-02-10")
            rec["publishedAt"] = None
            s = source(t, press=[rec, a_press("2024-02-11")])
            self.assertEqual(s.press_at(date(2024, 3, 1), "AAPL")["f"]["ctx_pressIn90d"], 1.0)

    def test_a_reaction_with_an_unmeasured_window_is_not_a_prior(self):
        with tempfile.TemporaryDirectory() as t:
            bad = a_reaction("2024-01-02", "2024-02-01", 0.0)
            bad["forward"][cf.PRIOR_HORIZON]["returnPct"] = None
            s = source(t, reactions=[bad])
            self.assertIsNone(s.prior_at(date(2024, 3, 1), "AAPL")["f"]["ctx_maturedPriors"])


# --- the schema is a contract -------------------------------------------------------------------

class TheFeatureVectorIsPositional(unittest.TestCase):

    def test_names_are_unique_stable_and_match_the_vector_length(self):
        names = cf.ContextSource.feature_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names, cf.ContextSource.feature_names())
        with tempfile.TemporaryDirectory() as t:
            block = source(t, macro=[macro_row("2024-03-01")]).at(date(2024, 3, 1), "AAPL")
        self.assertEqual(len(cf.ContextSource.vector(block)), len(names))

    def test_no_level_is_carried_only_changes_and_ages(self):
        """A trending level is a proxy for the date; the recorded context experiment fixed this."""
        for n in cf.ContextSource.feature_names():
            if n.startswith("macro_"):
                self.assertTrue(n.endswith("_chg") or n.endswith("_age"), n)

    def test_the_excluded_news_layer_contributes_no_feature_and_says_why(self):
        with tempfile.TemporaryDirectory() as t:
            block = source(t).at(date(2024, 3, 1), "AAPL")
        self.assertEqual(block["news"]["status"], "excluded")
        self.assertIn("70 days", block["news"]["reason"])
        self.assertEqual(block["news"]["f"], {})
        self.assertFalse([n for n in cf.ContextSource.feature_names() if "news" in n.lower()])

    def test_a_string_date_and_a_date_object_give_the_same_block(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, macro=[macro_row("2024-03-01")])
            self.assertEqual(s.at("2024-03-01", "AAPL"), s.at(date(2024, 3, 1), "AAPL"))


class CoverageIsMeasuredNotAssumed(unittest.TestCase):

    def test_coverage_reports_a_share_per_block_and_per_feature(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, macro=[macro_row("2024-02-01"), macro_row("2024-03-01")],
                       events=[an_event("2024-01-15")])
            rep = cf.coverage(s, [date(2024, 3, 1)], ["AAPL"])
        self.assertEqual(rep["rowsMeasured"], 1)
        self.assertEqual(rep["observedShareByBlock"]["macro"], 1.0)
        self.assertEqual(rep["observedShareByBlock"]["press"], 0.0)
        self.assertEqual(rep["nullShareByFeature"]["ctx_pressIn90d"], 1.0)
        self.assertIn("operational news feed", rep["excluded"])


if __name__ == "__main__":
    unittest.main()
