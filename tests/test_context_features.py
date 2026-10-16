"""The context producer: can anything dated after the session, or about another name, reach it?

    python -m unittest discover -s tests -p test_context_features.py -v

Stdlib unittest, no database, no network, and no repository artifact — every fixture is written
into a temporary directory, so these run anywhere in under a second.

Two properties carry this file, because the producer can be wrong in two independent ways.

**Time.** A feature computed at a session must not change when data dated after that session is
added or altered. `tools/foundation/pit_features.py` is tested the same way, by perturbing every
bar after a session and requiring the session's row to be unchanged. A leak that passes a
value-equality test still fails that one.

**Subject.** A feature computed for one instrument must not move when another instrument's records
change. This is the failure no date check catches, and the corpus contains a live example: `PSX` is
the Pakistan Stock Exchange in the events corpus and Phillips 66's ticker in the universe. Matching
on the string would attach Pakistani geopolitical events to a US refiner — correctly dated, utterly
wrong. That case has its own test.

The rest covers what the producer must refuse: an unverified event, a duplicated article, a
reaction whose window has not closed, a record whose subject cannot be placed, and an absent
reading that could be quietly rendered as a zero. A zero is a measurement. `None` is the absence of
one. Collapsing them is the failure this producer exists to avoid.
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


def source(tmp: Path, *, macro=None, events=None, press=None, reactions=None,
           universe=None) -> cf.ContextSource:
    d = Path(tmp)
    return cf.ContextSource.load(
        macro=write_macro(d, macro) if macro is not None else d / "none.gz",
        events=write_events(d, events) if events is not None else d / "none.json",
        press=write_press(d, press) if press is not None else d / "none.jsonl",
        reactions=write_reactions(d, reactions) if reactions is not None else d / "none2.gz",
        universe=universe,
    )


AS_OF = date(2024, 3, 1)


# --- time -----------------------------------------------------------------------------------

class TheFutureCannotReachThePast(unittest.TestCase):
    """Add or change data dated after a session; the session's features must not move."""

    def test_macro_dated_after_the_session_is_never_the_row_used(self):
        before = [macro_row("2024-02-28", chg=0.1), macro_row("2024-03-01", chg=0.2)]
        with tempfile.TemporaryDirectory() as t:
            a = source(t, macro=before).macro_at(AS_OF)
        with tempfile.TemporaryDirectory() as t:
            after = before + [macro_row("2024-03-04", chg=99.0), macro_row("2024-06-01", chg=99.0)]
            b = source(t, macro=after).macro_at(AS_OF)
        self.assertEqual(a, b)
        self.assertEqual(a["asOf"], "2024-03-01")
        self.assertEqual(a["f"]["macro_DGS10_chg"], 0.2)

    def test_an_event_on_the_session_itself_is_not_yet_evidence(self):
        """Strictly before. An announcement must not inform the bar it moved."""
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-20"), an_event("2024-03-01"),
                                  an_event("2024-03-02")])
            got = s.events_at(AS_OF, "AAPL", "US")
        self.assertEqual(got["f"]["ctx_ownEventsIn90d"], 1.0)
        self.assertEqual(got["f"]["ctx_ownDaysSinceEvent"], 10.0)

    def test_press_published_on_or_after_the_session_does_not_count(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, press=[a_press("2024-02-25"), a_press("2024-03-01"),
                                 a_press("2024-03-05")])
            self.assertEqual(s.press_at(AS_OF, "AAPL", "US")["f"]["ctx_ownPressIn90d"], 1.0)

    def test_a_reaction_window_that_has_not_closed_is_not_a_prior(self):
        """The artifact dates its own window, so maturity is read, not assumed."""
        with tempfile.TemporaryDirectory() as t:
            s = source(t, reactions=[
                a_reaction("2024-01-02", "2024-02-01", 5.0),    # closed: counts
                a_reaction("2024-02-01", "2024-03-01", 99.0),   # closes on the session: does not
                a_reaction("2024-02-20", "2024-03-20", 99.0),   # still open: does not
            ])
            got = s.prior_at(AS_OF, "AAPL")
        self.assertEqual(got["f"]["ctx_maturedPriors"], 1.0)
        self.assertEqual(got["f"]["ctx_priorMedianFwd20"], 5.0)

    def test_the_whole_block_is_unchanged_when_the_future_is_rewritten(self):
        base = dict(macro=[macro_row("2024-02-28"), macro_row("2024-03-01")],
                    events=[an_event("2024-02-01"), an_event("2024-02-05", instrument="MKT")],
                    press=[a_press("2024-02-10")],
                    reactions=[a_reaction("2024-01-02", "2024-02-01", 3.0)])
        future = dict(
            macro=base["macro"] + [macro_row("2024-03-02", chg=99.0)],
            events=base["events"] + [an_event("2024-03-01"), an_event("2024-05-05")],
            press=base["press"] + [a_press("2024-03-01"), a_press("2024-04-04")],
            reactions=base["reactions"] + [a_reaction("2024-02-25", "2024-03-25", 99.0)])
        with tempfile.TemporaryDirectory() as t:
            a = source(t, **base).at(AS_OF, "AAPL", "US")
        with tempfile.TemporaryDirectory() as t:
            b = source(t, **future).at(AS_OF, "AAPL", "US")
        self.assertEqual(cf.ContextSource.vector(a), cf.ContextSource.vector(b))


# --- subject --------------------------------------------------------------------------------

class OneNamesRecordsStayWithThatName(unittest.TestCase):
    """The failure no date check catches: correctly dated evidence about the wrong company."""

    def test_another_companys_event_does_not_reach_this_instrument(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-01", instrument="TSLA"),
                                  an_event("2024-02-02", instrument="TSLA")])
            aapl = s.events_at(AS_OF, "AAPL", "US")
            tsla = s.events_at(AS_OF, "TSLA", "US")
        self.assertIsNone(aapl["f"]["ctx_ownEventsIn90d"])       # unknown, not zero
        self.assertEqual(aapl["f"]["ctx_mktEventsIn90d"], 0.0)   # and not folded into the market
        self.assertEqual(tsla["f"]["ctx_ownEventsIn90d"], 2.0)

    def test_changing_another_name_leaves_this_vector_identical(self):
        mine = [an_event("2024-02-01", instrument="AAPL")]
        with tempfile.TemporaryDirectory() as t:
            a = source(t, events=mine).at(AS_OF, "AAPL", "US")
        with tempfile.TemporaryDirectory() as t:
            noisy = mine + [an_event(f"2024-02-{d:02d}", instrument="TSLA") for d in range(3, 28)]
            b = source(t, events=noisy).at(AS_OF, "AAPL", "US")
        self.assertEqual(cf.ContextSource.vector(a), cf.ContextSource.vector(b))

    def test_a_market_wide_event_reaches_every_instrument(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-01", instrument="MKT")])
            for sym in ("AAPL", "TSLA", "ZZZZ"):
                self.assertEqual(s.events_at(AS_OF, sym, "US")["f"]["ctx_mktEventsIn90d"], 1.0,
                                 sym)

    def test_the_pakistan_exchange_never_becomes_phillips_66(self):
        """`PSX` is a market in the events corpus and a US ticker in the universe.

        Matching on the string would hand Pakistani geopolitical events to a refiner — correctly
        dated and about the wrong subject entirely. This is the case `MARKET_SCOPED` exists for.
        """
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-01", instrument="PSX",
                                           category="geopolitical")])
            refiner = s.events_at(AS_OF, "PSX", "US")       # Phillips 66, a US stock
            karachi = s.events_at(AS_OF, "HASCOL", "PK")    # a Pakistani name
        self.assertEqual(refiner["f"]["ctx_mktEventsIn90d"], 0.0)
        self.assertIsNone(refiner["f"]["ctx_ownEventsIn90d"])
        self.assertEqual(karachi["f"]["ctx_mktEventsIn90d"], 1.0)

    def test_a_market_scoped_record_does_not_reach_another_market(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, press=[a_press("2024-02-10", instrument="PSX")])
            self.assertEqual(s.press_at(AS_OF, "AAPL", "US")["f"]["ctx_mktPressIn90d"], 0.0)
            self.assertEqual(s.press_at(AS_OF, "HASCOL", "PK")["f"]["ctx_mktPressIn90d"], 1.0)

    def test_a_reaction_prior_is_never_spread_over_a_market(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, reactions=[a_reaction("2024-01-02", "2024-02-01", 7.0, symbol="MKT")])
            self.assertIsNone(s.prior_at(AS_OF, "AAPL")["f"]["ctx_maturedPriors"])


class AnUnplaceableRecordIsCountedNotAssumedMarketWide(unittest.TestCase):
    """The first version let every named record fall back to MKT. That is the bug this closes."""

    UNIVERSE = {"AAPL", "TSLA"}

    def test_a_name_outside_the_universe_is_unresolved_and_in_neither_scope(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-01", instrument="GME")],
                       universe=self.UNIVERSE)
            got = s.at(AS_OF, "AAPL", "US")
        self.assertEqual(got["events"]["f"]["ctx_mktEventsIn90d"], 0.0)
        self.assertIsNone(got["events"]["f"]["ctx_ownEventsIn90d"])
        self.assertEqual(got["quality"]["f"]["ctx_unresolvedScopeRecords"], 1.0)
        self.assertEqual(s.provenance["events"]["byScope"][cf.SCOPE_UNRESOLVED], 1)
        self.assertIn("GME", s.provenance["unresolvedInstruments"])

    def test_an_alias_resolves_rather_than_going_unplaced(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-01", instrument="BTC")],
                       universe={"btc-bitcoin"})
            self.assertEqual(
                s.events_at(AS_OF, "btc-bitcoin", None)["f"]["ctx_ownEventsIn90d"], 1.0)
            self.assertEqual(s.provenance["events"]["byScope"][cf.SCOPE_UNRESOLVED], 0)

    def test_the_unresolved_count_is_itself_point_in_time(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-01", instrument="GME"),
                                  an_event("2024-04-01", instrument="GME")],
                       universe=self.UNIVERSE)
            self.assertEqual(s.quality_at(AS_OF)["f"]["ctx_unresolvedScopeRecords"], 1.0)

    def test_resolve_scope_answers_the_three_cases_directly(self):
        self.assertEqual(cf.resolve_scope("MKT"), (cf.SCOPE_MARKET, None))
        self.assertEqual(cf.resolve_scope("PSX"), (cf.SCOPE_MARKET, "PK"))
        self.assertEqual(cf.resolve_scope("AAPL", {"AAPL"}), (cf.SCOPE_OWN, "AAPL"))
        self.assertEqual(cf.resolve_scope("BTC", {"btc-bitcoin"}), (cf.SCOPE_OWN, "btc-bitcoin"))
        self.assertEqual(cf.resolve_scope("GME", {"AAPL"}), (cf.SCOPE_UNRESOLVED, "GME"))
        self.assertEqual(cf.resolve_scope(None), (cf.SCOPE_UNRESOLVED, None))

    def test_no_market_scoped_name_is_also_an_alias(self):
        """A name cannot be both a whole market and one instrument; the tables must not overlap."""
        self.assertEqual(set(cf.MARKET_SCOPED) & set(cf.ALIASES), set())
        self.assertNotIn(cf.MARKET_WIDE, cf.ALIASES)


class TheEventsOwnReactionIsNeverAFeature(unittest.TestCase):
    """`market` holds peakDate, z and returnPct — what the market did *after* the event."""

    @staticmethod
    def _keys(obj) -> set:
        """Every key anywhere in the structure. A substring check would trip over `marketCode`."""
        out = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                out.add(k)
                out |= TheEventsOwnReactionIsNeverAFeature._keys(v)
        elif isinstance(obj, list):
            for v in obj:
                out |= TheEventsOwnReactionIsNeverAFeature._keys(v)
        return out

    def test_no_forbidden_key_reaches_the_block_or_the_vector(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-01-05")])
            block = s.at(AS_OF, "AAPL", "US")
        self.assertEqual(self._keys(block) & set(cf.FORBIDDEN_KEYS), set())
        self.assertNotIn("424242", json.dumps(block),
                         "the event's own market reaction reached the block")
        self.assertNotIn(424242.0, cf.ContextSource.vector(block))


# --- refusals ------------------------------------------------------------------------------------

class MissingIsMissingAndNeverZero(unittest.TestCase):
    """"Could not look" is not "nothing there", and a model cannot tell them apart from a 0."""

    def test_with_no_artifacts_every_block_is_absent_and_every_feature_is_none(self):
        with tempfile.TemporaryDirectory() as t:
            block = cf.ContextSource.load(
                macro=Path(t) / "x.gz", events=Path(t) / "x.json",
                press=Path(t) / "x.jsonl", reactions=Path(t) / "x2.gz",
            ).at(AS_OF, "AAPL", "US")
        for part in ("macro", "events", "press", "reactionPrior"):
            self.assertEqual(block[part]["status"], "absent", part)
            self.assertIn("reason", block[part])
        vec = cf.ContextSource.vector(block)
        names = cf.ContextSource.feature_names()
        for n, v in zip(names, vec):
            if n != "ctx_unresolvedScopeRecords":
                self.assertIsNone(v, n)

    def test_a_session_before_the_artifact_starts_is_absent_not_an_error(self):
        with tempfile.TemporaryDirectory() as t:
            got = source(t, macro=[macro_row("2024-03-01")]).macro_at(date(2019, 1, 1))
        self.assertEqual(got["status"], "absent")
        self.assertTrue(all(v is None for v in got["f"].values()))

    def test_an_instrument_with_no_reaction_is_absent_and_a_dry_spell_is_a_measured_zero(self):
        """These two differ and the producer must not say the same thing about both."""
        with tempfile.TemporaryDirectory() as t:
            s = source(t, reactions=[a_reaction("2024-02-20", "2024-03-20", 1.0)])
            unknown = s.prior_at(AS_OF, "ZZZZ")
            known_but_open = s.prior_at(AS_OF, "AAPL")
        self.assertIsNone(unknown["f"]["ctx_maturedPriors"])
        self.assertEqual(known_but_open["f"]["ctx_maturedPriors"], 0.0)

    def test_a_stale_macro_row_is_still_reported_with_its_age(self):
        with tempfile.TemporaryDirectory() as t:
            got = source(t, macro=[macro_row("2024-01-02")]).macro_at(AS_OF)
        self.assertEqual(got["status"], "observed")
        self.assertEqual(got["ageDays"], 59)


class BadRecordsAreRefusedRatherThanCounted(unittest.TestCase):

    def test_an_unverified_event_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, events=[an_event("2024-02-01", verified=False),
                                  an_event("2024-02-02", verified=True)])
            self.assertEqual(s.events_at(AS_OF, "AAPL", "US")["f"]["ctx_ownEventsIn90d"], 1.0)

    def test_the_same_article_under_two_routes_counts_once(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, press=[a_press("2024-02-10", dedupe="same"),
                                 a_press("2024-02-10", dedupe="same", route="other"),
                                 a_press("2024-02-11", dedupe="different")])
            self.assertEqual(s.press_at(AS_OF, "AAPL", "US")["f"]["ctx_ownPressIn90d"], 2.0)

    def test_a_record_with_no_publication_time_has_no_availability_and_is_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            rec = a_press("2024-02-10")
            rec["publishedAt"] = None
            s = source(t, press=[rec, a_press("2024-02-11")])
            self.assertEqual(s.press_at(AS_OF, "AAPL", "US")["f"]["ctx_ownPressIn90d"], 1.0)

    def test_a_reaction_with_an_unmeasured_window_is_not_a_prior(self):
        with tempfile.TemporaryDirectory() as t:
            bad = a_reaction("2024-01-02", "2024-02-01", 0.0)
            bad["forward"][cf.PRIOR_HORIZON]["returnPct"] = None
            s = source(t, reactions=[bad])
            self.assertIsNone(s.prior_at(AS_OF, "AAPL")["f"]["ctx_maturedPriors"])


# --- the schema is a contract -------------------------------------------------------------------

class TheFeatureVectorIsPositional(unittest.TestCase):

    def test_names_are_unique_stable_and_match_the_vector_length(self):
        names = cf.ContextSource.feature_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names, cf.ContextSource.feature_names())
        with tempfile.TemporaryDirectory() as t:
            block = source(t, macro=[macro_row("2024-03-01")]).at(AS_OF, "AAPL", "US")
        self.assertEqual(len(cf.ContextSource.vector(block)), len(names))

    def test_both_scopes_are_present_in_the_schema(self):
        names = set(cf.ContextSource.feature_names())
        for n in ("ctx_mktEventsIn90d", "ctx_ownEventsIn90d",
                  "ctx_mktPressIn90d", "ctx_ownPressIn90d", "ctx_unresolvedScopeRecords"):
            self.assertIn(n, names)

    def test_no_level_is_carried_only_changes_and_ages(self):
        """A trending level is a proxy for the date; the recorded context experiment fixed this."""
        for n in cf.ContextSource.feature_names():
            if n.startswith("macro_"):
                self.assertTrue(n.endswith("_chg") or n.endswith("_age"), n)

    def test_the_excluded_news_layer_contributes_no_feature_and_says_why(self):
        with tempfile.TemporaryDirectory() as t:
            block = source(t).at(AS_OF, "AAPL", "US")
        self.assertEqual(block["news"]["status"], "excluded")
        self.assertIn("70 days", block["news"]["reason"])
        self.assertEqual(block["news"]["f"], {})
        self.assertFalse([n for n in cf.ContextSource.feature_names() if "news" in n.lower()])

    def test_a_string_date_and_a_date_object_give_the_same_block(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, macro=[macro_row("2024-03-01")])
            self.assertEqual(s.at("2024-03-01", "AAPL", "US"), s.at(AS_OF, "AAPL", "US"))


class CoverageIsMeasuredNotAssumed(unittest.TestCase):

    def test_coverage_reports_a_share_per_block_and_per_feature(self):
        with tempfile.TemporaryDirectory() as t:
            s = source(t, macro=[macro_row("2024-02-01"), macro_row("2024-03-01")],
                       events=[an_event("2024-01-15")])
            rep = cf.coverage(s, [AS_OF], [("AAPL", "US")])
        self.assertEqual(rep["rowsMeasured"], 1)
        self.assertEqual(rep["observedShareByBlock"]["macro"], 1.0)
        self.assertEqual(rep["observedShareByBlock"]["press"], 0.0)
        self.assertEqual(rep["nullShareByFeature"]["ctx_ownPressIn90d"], 1.0)
        self.assertIn("operational news feed", rep["excluded"])
        self.assertIn("unresolved", rep["scopeRule"])


class TheJoinPutsContextWhereATrainerWillReadIt(unittest.TestCase):
    """The claim a producer cannot make for itself: the feature arrives in a dataset row.

    `assemble_year` is driven directly with fixtures rather than through a full build, because the
    question here is the shape of the row, not the size of the corpus. `pit.ctx` rides inside
    `pit` on purpose: a row without `pit.f` is skipped by every loader in this repository, so
    context hung outside it would be context attached to rows nobody trains on.
    """

    @staticmethod
    def _assemble(ctx, as_of="2024-03-01", symbol="AAPL", market="US"):
        import assemble as asm
        from collections import Counter
        full = [{"asOf": as_of, "assetId": "1", "symbol": symbol, "assetType": "stock",
                 "market": market,
                 "outcome": {"label20": "UP", "mature20": True, "fwd20": 3.0}}]
        stats = Counter()
        with tempfile.TemporaryDirectory() as d:
            pit = Path(d) / "pit-2024.jsonl.gz"
            with gzip.open(pit, "wt", encoding="utf-8") as fh:
                fh.write(json.dumps({"a": symbol, "d": as_of, "n": 400, "spanDays": 560,
                                     "f": {"r20": 1.0}, "an": None}) + chr(10))
            rows = list(asm.assemble_year(2024, full, pit, {}, stats, ctx=ctx))
        return rows, stats

    def test_the_row_carries_the_context_vector_in_feature_order(self):
        with tempfile.TemporaryDirectory() as t:
            ctx = source(t, macro=[macro_row("2024-03-01", chg=0.5)],
                         events=[an_event("2024-02-01", instrument="AAPL")],
                         universe={"AAPL"})
            rows, stats = self._assemble(ctx)
        self.assertEqual(len(rows), 1)
        got = rows[0]["pit"]["ctx"]
        self.assertEqual(got["v"], cf.VERSION)
        self.assertEqual(list(got["f"]), cf.ContextSource.feature_names())
        self.assertEqual(got["f"]["macro_DGS10_chg"], 0.5)
        self.assertEqual(got["f"]["ctx_ownEventsIn90d"], 1.0)
        self.assertEqual(got["s"]["macro"], "observed")
        self.assertEqual(stats["withCtx"], 1)
        self.assertEqual(stats["leakCtxAfterSession"], 0)

    def test_without_the_source_the_row_is_exactly_the_old_shape(self):
        """A build without --context must reproduce examples-v3, so the key may not appear."""
        rows, stats = self._assemble(None)
        self.assertNotIn("ctx", rows[0]["pit"])
        self.assertEqual(stats["withCtx"], 0)

    def test_a_row_with_no_price_features_carries_no_context(self):
        import assemble as asm
        from collections import Counter
        with tempfile.TemporaryDirectory() as t:
            ctx = source(t, macro=[macro_row("2024-03-01")], universe={"AAPL"})
            full = [{"asOf": "2024-03-01", "assetId": "1", "symbol": "AAPL",
                     "assetType": "stock", "market": "US",
                     "outcome": {"label20": "UP", "mature20": True}}]
            rows = list(asm.assemble_year(2024, full, None, {}, Counter(), ctx=ctx))
        self.assertIsNone(rows[0]["pit"])

    def test_the_macro_row_used_is_never_dated_after_the_session(self):
        with tempfile.TemporaryDirectory() as t:
            ctx = source(t, macro=[macro_row("2024-02-28"), macro_row("2024-03-05", chg=99.0)],
                         universe={"AAPL"})
            rows, stats = self._assemble(ctx)
        self.assertEqual(rows[0]["pit"]["ctx"]["f"]["macro_DGS10_chg"], 0.1)
        self.assertEqual(stats["leakCtxAfterSession"], 0)

if __name__ == "__main__":
    unittest.main()
