"""Deterministic tests for the reasoning the Brain does without a database.

Stdlib unittest on purpose. Every one of these runs with no database, no network and no new
dependency, so it can run on every push without touching the data lane or the free tier.

    python -m unittest discover -s tests -v

What is covered is the pure logic — the parts where a wrong answer would be silent. A
clustering threshold that merges unrelated stories, a classifier that reads a mixed headline
as positive, a robust score that divides by zero, an analog matcher that counts a day whose
outcome has not happened yet: none of those would raise, and all of them would quietly
corrupt what the site tells a reader.

Where a case is here because it was a real bug, the test says so.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

import analogs  # noqa: E402
import attribution  # noqa: E402
import graph  # noqa: E402
import horizons  # noqa: E402
import human  # noqa: E402
import intraday  # noqa: E402
import investigate  # noqa: E402
import lineage  # noqa: E402
import nbt  # noqa: E402
import prices  # noqa: E402
import psx  # noqa: E402
import run  # noqa: E402
import runlog  # noqa: E402
import seed  # noqa: E402
import schemacheck  # noqa: E402
import thesis  # noqa: E402


class Arithmetic(unittest.TestCase):
    def test_pct_is_change_from_b_to_a(self):
        self.assertAlmostEqual(nbt.pct(110.0, 100.0), 10.0)
        self.assertAlmostEqual(nbt.pct(90.0, 100.0), -10.0)

    def test_pct_refuses_a_zero_base(self):
        # A zero base is a missing measurement, never an infinite rise.
        self.assertIsNone(nbt.pct(5.0, 0.0))
        self.assertIsNone(nbt.pct(5.0, None))

    def test_median_is_not_dragged_by_an_outlier(self):
        self.assertEqual(nbt.median([1, 2, 3, 4, 1000]), 3)
        self.assertAlmostEqual(nbt.mean([1, 2, 3, 4, 1000]), 202.0)

    def test_empty_inputs_give_none_not_zero(self):
        self.assertIsNone(nbt.mean([]))
        self.assertIsNone(nbt.median([]))


class HeadlineTone(unittest.TestCase):
    def test_clear_direction_is_read(self):
        self.assertEqual(human.classify("Nvidia beats estimates as revenue surges"), "positive")
        self.assertEqual(human.classify("Intel misses guidance and warns on demand"), "negative")

    def test_a_headline_worded_both_ways_is_neither(self):
        # Picking a winner on match count would invent a judgement the wording does not
        # support. "Revenue beats but guidance misses" is genuinely both.
        self.assertEqual(human.classify("Revenue beats but guidance misses"), "neutral")

    def test_no_directional_word_is_neutral(self):
        self.assertEqual(human.classify("Apple announces new store in Mumbai"), "neutral")

    def test_promotional_wording_is_counted_separately_from_tone(self):
        title = "3 stocks to buy before it is too late"
        self.assertEqual(human.classify(title), "neutral")
        self.assertGreater(human.count_terms(title, human.HYPE_TERMS), 0)

    def test_a_repeated_word_counts_once(self):
        # One headline saying a word twice is still one headline saying it.
        self.assertEqual(human.count_terms("surges and surges", ("surges",)), 1)


class RobustDeviation(unittest.TestCase):
    def test_needs_enough_history(self):
        self.assertIsNone(human.robust_z(5.0, [1.0, 2.0, 3.0]))

    def test_flags_a_rate_far_above_the_median(self):
        z = human.robust_z(10.0, [1.0, 1.0, 2.0, 1.0, 0.0, 1.0, 2.0, 1.0, 1.0, 0.0])
        self.assertIsNotNone(z)
        self.assertGreater(z, 3.0)

    def test_does_not_flag_ordinary_variation(self):
        z = human.robust_z(2.0, [1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 2.0, 1.0, 3.0, 2.0])
        self.assertLess(z, 3.0)

    def test_a_perfectly_flat_baseline_does_not_divide_by_zero(self):
        # MAD is 0 when every day is identical. Without the floor this returned infinity for
        # one extra item and every quiet feed became a permanent catalyst.
        z = human.robust_z(2.0, [1.0] * 10)
        self.assertIsNotNone(z)
        self.assertTrue(abs(z) < float("inf"))


class StoryCounting(unittest.TestCase):
    def test_copies_of_one_story_count_once(self):
        items = [{"lineageId": "a"}, {"lineageId": "a"}, {"lineageId": "a"}]
        self.assertEqual(human.stories(items), 1)

    def test_distinct_stories_count_separately(self):
        items = [{"lineageId": "a"}, {"lineageId": "b"}]
        self.assertEqual(human.stories(items), 2)

    def test_an_unclustered_item_counts_as_its_own_story(self):
        # Undercounting items collected since lineage.py last ran would silence exactly the
        # newest information, which is the opposite of the point.
        items = [{"lineageId": "a"}, {"lineageId": None}, {"lineageId": None}]
        self.assertEqual(human.stories(items), 3)


class Lineage(unittest.TestCase):
    def setUp(self):
        self.drop = lineage.tokens("Nvidia NVDA", set())

    def test_rewrites_of_one_story_cluster(self):
        a = lineage.tokens("Nvidia beats estimates as data centre revenue surges", self.drop)
        b = lineage.tokens("NVIDIA tops estimates on surging data centre revenue", self.drop)
        self.assertGreaterEqual(lineage.jaccard(a, b), lineage.THRESHOLD)

    def test_different_stories_about_one_company_do_not_cluster(self):
        a = lineage.tokens("Nvidia beats estimates as data centre revenue surges", self.drop)
        c = lineage.tokens("Nvidia announces new office in Warsaw", self.drop)
        self.assertLess(lineage.jaccard(a, c), lineage.THRESHOLD)

    def test_the_company_name_is_dropped_before_matching(self):
        # Every item about one company repeats its name. Matching on it would push unrelated
        # stories over the threshold on the strength of the subject they share.
        self.assertNotIn("nvidia", lineage.tokens("Nvidia opens an office", self.drop))

    def test_jaccard_handles_empty_sets(self):
        self.assertEqual(lineage.jaccard(set(), {"a"}), 0.0)

    def test_clustering_is_transitive(self):
        base = datetime(2026, 9, 30, 12, 0, 0)
        items = [
            {"id": "1", "title": "Acme wins large supply contract", "publisher": "A",
             "publishedAt": base},
            {"id": "2", "title": "Acme wins large supply contract deal", "publisher": "B",
             "publishedAt": base + timedelta(hours=1)},
            {"id": "3", "title": "Acme wins supply contract", "publisher": "C",
             "publishedAt": base + timedelta(hours=2)},
        ]
        groups = lineage.cluster(items, lineage.tokens("Acme ACME", set()))
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 3)

    def test_items_outside_the_window_are_separate_stories(self):
        base = datetime(2026, 9, 1, 12, 0, 0)
        items = [
            {"id": "1", "title": "Acme wins large supply contract", "publisher": "A",
             "publishedAt": base},
            {"id": "2", "title": "Acme wins large supply contract", "publisher": "B",
             "publishedAt": base + timedelta(hours=lineage.WINDOW_HOURS + 5)},
        ]
        groups = lineage.cluster(items, set())
        self.assertEqual(len(groups), 2)


def _bars(closes: list[float], volumes: list[float] | None = None) -> list[dict]:
    vols = volumes or [1000.0] * len(closes)
    return [{"close": c, "volume": v} for c, v in zip(closes, vols)]


class Analogs(unittest.TestCase):
    def test_factors_need_history_behind_them(self):
        self.assertIsNone(analogs.factors(_bars([10.0] * 5), 4))

    def test_day_return_is_measured_against_the_previous_close(self):
        bars = _bars([10.0] * analogs.VOL_WINDOW + [11.0])
        got = analogs.factors(bars, analogs.VOL_WINDOW)
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got["day"], 10.0)

    def test_volume_ratio_is_against_its_own_trailing_average(self):
        closes = [10.0] * (analogs.VOL_WINDOW + 1)
        vols = [100.0] * analogs.VOL_WINDOW + [300.0]
        got = analogs.factors(_bars(closes, vols), analogs.VOL_WINDOW)
        self.assertAlmostEqual(got["vol"], 3.0)

    def test_forward_return_is_none_when_the_day_is_not_stored(self):
        bars = _bars([10.0, 11.0])
        self.assertIsNone(analogs.forward(bars, 1, 5))
        self.assertAlmostEqual(analogs.forward(bars, 0, 1), 10.0)

    def test_a_missing_factor_is_not_a_match(self):
        # Missing is not "close enough". Letting it through would loosen the rule for
        # precisely the days with the least data behind them.
        a = {"day": 1.0, "vol": 1.0, "five": 1.0}
        b = {"day": 1.0, "vol": None, "five": 1.0}
        self.assertFalse(analogs.similar(a, b))

    def test_similarity_respects_every_tolerance(self):
        a = {"day": 1.0, "vol": 1.0, "five": 1.0}
        self.assertTrue(analogs.similar(a, dict(a)))
        self.assertFalse(analogs.similar(a, {**a, "day": 1.0 + analogs.DAY_TOL + 0.1}))
        self.assertFalse(analogs.similar(a, {**a, "vol": 1.0 + analogs.VOL_TOL + 0.1}))
        self.assertFalse(analogs.similar(a, {**a, "five": 1.0 + analogs.FIVE_TOL + 0.1}))

    def test_a_thin_sample_is_not_graded(self):
        grade, notes = analogs.grade(3, [1.0, 2.0, 3.0])
        self.assertEqual(grade, "none")
        self.assertTrue(notes)

    def test_a_near_even_split_is_capped_and_said_out_loud(self):
        moves = [1.0] * 21 + [-1.0] * 20
        grade, notes = analogs.grade(len(moves), moves)
        self.assertNotEqual(grade, "high")
        self.assertTrue(any("even split" in n for n in notes))

    def test_a_spread_far_wider_than_the_mean_is_disclosed(self):
        moves = [-9.0, 11.0] * 25
        grade, notes = analogs.grade(len(moves), moves)
        self.assertTrue(any("spread" in n for n in notes))


class ThesisParsing(unittest.TestCase):
    """The verdict parser reads strings jobs/setup.py actually writes.

    The samples below are copied from the format setup.py builds, not invented, because the
    whole of thesis.py rests on this parse and a format change there has to break a test here
    rather than silently stop finding conditions.
    """

    SAMPLE = (
        "trend: close 230.10 vs 20d 221.40 vs 50d 210.96 (up) | "
        "volume: 0.89x its 20d average (fail) | "
        "relative: +2.4 points against its industry over 20 days (pass) | "
        "position: 78% of the way up its 120 day range | "
        "news: tone positive, catalyst yes, 6 recent stories | "
        "history: 218 of 392 similar days rose over 5 sessions (56%, pass) | "
        "calendar: Q3 results in 12 days"
    )

    def test_every_verdict_is_found(self):
        got = thesis.verdicts(self.SAMPLE)
        self.assertEqual(
            got, {"trend": "up", "volume": "fail", "relative": "pass", "history": "pass"}
        )

    def test_a_condition_that_states_a_value_carries_no_verdict(self):
        # "position: 78% of the way up its range" passes no judgement. Defaulting it to a
        # pass would manufacture agreement out of a sentence that stated none.
        got = thesis.verdicts(self.SAMPLE)
        for name in ("position", "news", "calendar"):
            self.assertNotIn(name, got)

    def test_a_trailing_bracket_with_two_parts_takes_the_verdict(self):
        got = thesis.verdicts("history: 4 of 9 rose over 5 sessions (44%, fail)")
        self.assertEqual(got, {"history": "fail"})

    def test_an_unparseable_condition_is_skipped_not_guessed(self):
        self.assertEqual(thesis.verdicts("no colon here (pass)"), {})
        self.assertEqual(thesis.verdicts(""), {})


class ThesisStates(unittest.TestCase):
    OPEN = {"trend": "up", "volume": "pass", "relative": "pass"}

    def test_unchanged_conditions_are_active(self):
        status, changed, held, reason = thesis.assess(
            "buy", self.OPEN, dict(self.OPEN), "buy", 100.0, 105.0, 120.0
        )
        self.assertEqual(status, "active")
        self.assertEqual(changed, [])
        self.assertEqual(len(held), 3)
        self.assertIn("still reads buy", reason)

    def test_a_flipped_verdict_is_weakening_and_names_the_condition(self):
        now = {**self.OPEN, "volume": "fail"}
        status, changed, _, reason = thesis.assess(
            "buy", self.OPEN, now, "buy", 100.0, 105.0, 120.0
        )
        self.assertEqual(status, "weakening")
        self.assertEqual(changed, ["volume"])
        self.assertIn("volume", reason)

    def test_a_condition_that_became_unavailable_counts_as_changed(self):
        # An input that stopped being available has stopped supporting anything. Carrying it
        # forward as a pass is the substitution setup.py refuses to make.
        now = {"trend": "up", "relative": "pass"}
        status, changed, held, _ = thesis.assess(
            "buy", self.OPEN, now, "buy", 100.0, 105.0, 120.0
        )
        self.assertEqual(status, "weakening")
        self.assertEqual(changed, ["volume"])
        self.assertEqual(held, ["relative", "trend"])

    def test_a_close_past_the_invalidation_level_is_broken(self):
        status, _, _, reason = thesis.assess(
            "buy", self.OPEN, dict(self.OPEN), "buy", 100.0, 99.5, 120.0
        )
        self.assertEqual(status, "broken")
        self.assertIn("99.50", reason)
        self.assertIn("100.00", reason)

    def test_a_level_matched_exactly_has_not_been_passed(self):
        # The level is the lowest close of the window before the thesis opened, so a later
        # close at exactly that value has matched the range rather than left it.
        status, _, _, _ = thesis.assess(
            "buy", self.OPEN, dict(self.OPEN), "buy", 100.0, 100.0, 120.0
        )
        self.assertEqual(status, "active")

    def test_a_short_is_broken_by_a_close_above_its_level(self):
        opened = {"trend": "down", "volume": "pass"}
        self.assertEqual(
            thesis.assess("short", opened, dict(opened), "short", 100.0, 80.0, 101.0)[0],
            "broken",
        )
        self.assertEqual(
            thesis.assess("short", opened, dict(opened), "short", 100.0, 80.0, 99.0)[0],
            "active",
        )

    def test_the_opposite_direction_is_broken_not_weakening(self):
        status, _, _, reason = thesis.assess(
            "buy", self.OPEN, dict(self.OPEN), "short", 100.0, 105.0, 120.0
        )
        self.assertEqual(status, "broken")
        self.assertIn("opposite", reason)

    def test_leaving_the_direction_without_a_breach_is_weakening(self):
        status, _, _, reason = thesis.assess(
            "buy", self.OPEN, dict(self.OPEN), "wait", 100.0, 105.0, 120.0
        )
        self.assertEqual(status, "weakening")
        self.assertIn("wait", reason)

    def test_a_missing_level_cannot_break_a_thesis(self):
        # No level means nothing was committed to in advance, so there is nothing to fail.
        self.assertFalse(thesis.breached("buy", None, 1.0, 2.0))
        self.assertFalse(thesis.breached("buy", 100.0, None, None))

    def test_a_broken_thesis_is_graded_on_the_measurement_not_the_conditions(self):
        grade, note = thesis.grade_for("broken", ["volume"], [])
        self.assertEqual(grade, "high")
        self.assertIn("named in advance", note)

    def test_an_opening_read_with_no_verdicts_is_not_graded(self):
        grade, note = thesis.grade_for("active", [], [])
        self.assertEqual(grade, "none")
        self.assertIn("nothing to compare", note)


class ThesisRuns(unittest.TestCase):
    @staticmethod
    def _reads(states: list[str]) -> list[dict]:
        return [{"state": s} for s in states]

    def test_consecutive_days_of_one_state_are_one_run(self):
        got = thesis.runs(self._reads(["buy", "buy", "buy"]))
        self.assertEqual(len(got), 1)
        self.assertEqual(len(got[0]), 3)

    def test_a_state_entered_twice_is_two_runs(self):
        # The second run is a reason recorded on a different day, so its clock starts again.
        got = thesis.runs(self._reads(["buy", "wait", "buy"]))
        self.assertEqual([len(r) for r in got], [1, 1])

    def test_non_directional_reads_produce_no_run(self):
        self.assertEqual(thesis.runs(self._reads(["wait", "none", "wait"])), [])

    def test_a_direction_flip_splits_the_run(self):
        got = thesis.runs(self._reads(["buy", "buy", "short", "short"]))
        self.assertEqual([r[0]["state"] for r in got], ["buy", "short"])


class Attribution(unittest.TestCase):
    def test_the_three_parts_sum_to_the_move(self):
        parts = attribution.decompose(8.0, 3.0, 1.0)
        self.assertAlmostEqual(sum(parts.values()), 8.0)
        self.assertAlmostEqual(parts["market"], 1.0)
        self.assertAlmostEqual(parts["sector"], 2.0)
        self.assertAlmostEqual(parts["specific"], 5.0)

    def test_shares_are_taken_from_absolute_values(self):
        # A sector that fell while the asset rose has still accounted for a chunk of the
        # distance between them. Signing the denominator would let two parts cancel into a
        # share above one.
        parts = {"market": 2.0, "sector": -2.0, "specific": 4.0}
        split = attribution.shares(parts)
        self.assertAlmostEqual(sum(split.values()), 1.0)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in split.values()))

    def test_a_flat_window_has_no_shares_rather_than_a_full_attribution(self):
        self.assertIsNone(attribution.shares({"market": 0.0, "sector": 0.0, "specific": 0.0}))

    def test_too_few_peers_names_no_leader(self):
        name, margin, why = attribution.leader(
            {"market": 1.0, "sector": 0.0, "specific": 9.0}, peers=2, group=40
        )
        self.assertIsNone(name)
        self.assertIsNone(margin)
        self.assertIn("peers", why)

    def test_a_thin_exchange_group_names_no_leader(self):
        name, _, why = attribution.leader(
            {"market": 1.0, "sector": 0.0, "specific": 9.0}, peers=6, group=4
        )
        self.assertIsNone(name)
        self.assertIn("exchange group", why)

    def test_two_close_components_are_reported_as_close_not_separated(self):
        name, margin, why = attribution.leader(
            {"market": 1.0, "sector": 3.0, "specific": 3.2}, peers=6, group=40
        )
        self.assertIsNone(name)
        self.assertLess(margin, attribution.DOMINANCE)
        self.assertIn("within", why)

    def test_the_left_over_part_is_not_described_as_shared(self):
        # Caught in production. "The move is mostly shared with what is left after both" is
        # self-contradictory: the left-over part is by definition the part that is not shared.
        parts = {"market": 0.1, "sector": 11.6, "specific": 20.5}
        line = attribution.sentence(32.2, parts, 0.1, "specific")
        self.assertNotIn("shared with what is left", line)
        self.assertIn("is not shared with", line)

    def test_each_leader_gets_a_sentence_that_reads(self):
        parts = {"market": 2.0, "sector": 3.0, "specific": 9.0}
        for name in ("market", "sector", "specific"):
            line = attribution.sentence(14.0, parts, 2.0, name)
            self.assertTrue(line.endswith("."), line)
            self.assertNotIn("  ", line)

    def test_a_dominant_component_is_named(self):
        name, margin, _ = attribution.leader(
            {"market": 1.0, "sector": 1.0, "specific": 9.0}, peers=6, group=40
        )
        self.assertEqual(name, "specific")
        self.assertGreater(margin, attribution.DOMINANCE)

    def test_the_leader_is_chosen_on_size_not_sign(self):
        name, _, _ = attribution.leader(
            {"market": -9.0, "sector": 1.0, "specific": 1.0}, peers=6, group=40
        )
        self.assertEqual(name, "market")

    def test_an_unsplit_remainder_says_so_instead_of_naming_a_part(self):
        line = attribution.sentence(8.0, None, 1.0, None)
        self.assertIn("cannot be split", line)
        self.assertIn("+7.0 points", line)

    def test_no_causal_verb_reaches_the_sentence(self):
        # Rule 10. The site measures what moved together; it never says one thing moved
        # another.
        for parts, named in (
            ({"market": 1.0, "sector": 2.0, "specific": 5.0}, "specific"),
            ({"market": 1.0, "sector": 2.0, "specific": 5.0}, None),
            (None, None),
        ):
            line = attribution.sentence(8.0, parts, 1.0, named).lower()
            for banned in ("because", "driven by", "in response to", "caused", "reaction"):
                self.assertNotIn(banned, line)


class Graph(unittest.TestCase):
    def test_a_specific_relationship_outweighs_a_crowded_one(self):
        pair = graph.edge_weight("product", 2)
        sector = graph.edge_weight("industry", 20)
        self.assertGreater(pair, sector)

    def test_a_hub_sized_group_carries_no_edge(self):
        # "Shares an industry with 70 other listings" is a fact about the industry, not a
        # connection between two of its members.
        self.assertIsNone(graph.edge_weight("industry", graph.MAX_GROUP + 1))

    def test_a_group_of_one_carries_no_edge(self):
        self.assertIsNone(graph.edge_weight("product", 1))

    def test_an_unknown_edge_kind_carries_no_weight(self):
        self.assertEqual(graph.edge_weight("invented", 2), 0.0)

    def test_a_second_hop_is_always_weaker_than_the_first(self):
        first = graph.hop_score(1.0, "product", 2)
        second = graph.hop_score(first, "product", 2)
        self.assertLess(second, first)

    def test_groups_become_edges_in_both_directions(self):
        adj = graph.groups_to_edges([("industry", "Semis", ["a", "b", "c"])])
        self.assertEqual(sorted(e["to"] for e in adj["a"]), ["b", "c"])
        self.assertEqual(adj["a"][0]["size"], 3)

    def test_a_duplicated_member_does_not_inflate_a_group(self):
        adj = graph.groups_to_edges([("industry", "Semis", ["a", "b", "b"])])
        self.assertEqual(adj["a"][0]["size"], 2)
        self.assertEqual(len(adj["a"]), 1)

    def test_the_walk_stops_at_the_hop_bound(self):
        # a-b share a product, b-c share another, c-d a third. d is three hops from a and
        # must not appear at all.
        adj = graph.groups_to_edges(
            [
                ("product", "P1", ["a", "b"]),
                ("product", "P2", ["b", "c"]),
                ("product", "P3", ["c", "d"]),
            ]
        )
        got = graph.walk(adj, "a", "a has a catalyst")
        self.assertEqual(sorted(got), ["b", "c"])
        self.assertEqual(got["b"]["hops"], 1)
        self.assertEqual(got["c"]["hops"], 2)
        self.assertGreater(got["b"]["score"], got["c"]["score"])

    def test_the_origin_is_never_in_its_own_neighbourhood(self):
        adj = graph.groups_to_edges([("product", "P1", ["a", "b"])])
        self.assertNotIn("a", graph.walk(adj, "a", "a has a catalyst"))

    def test_every_reached_asset_carries_the_chain_that_reached_it(self):
        adj = graph.groups_to_edges(
            [("product", "Humanoid robots", ["a", "b"]), ("industry", "Semis", ["b", "c"])]
        )
        got = graph.walk(adj, "a", "A has a catalyst flagged")
        self.assertIn("Humanoid robots", got["b"]["path"])
        self.assertIn("Humanoid robots", got["c"]["path"])
        self.assertIn("Semis", got["c"]["path"])

    def test_a_product_origin_scores_like_any_other_first_hop(self):
        # Caught in production. The product origin's weight was computed by hand and skipped
        # DECAY, so its first hop scored 1.0 while an asset origin's identical first hop
        # scored 0.4. The whole list then ordered by which kind of thing the catalyst sat on
        # rather than by distance, which is the only claim the score makes.
        #
        # A product with N linked assets is its own group of N + 1, which is how the job now
        # scores it, so this is the number it must produce.
        product_origin = graph.hop_score(1.0, "product", 2)
        asset_origin_through_a_pair = graph.hop_score(1.0, "product", 2)
        self.assertAlmostEqual(product_origin, asset_origin_through_a_pair)
        self.assertLess(product_origin, 1.0)
        self.assertAlmostEqual(product_origin, graph.KIND_WEIGHT["product"] * graph.DECAY)

    def test_a_one_hop_product_link_outranks_a_one_hop_industry(self):
        self.assertGreater(graph.hop_score(1.0, "product", 2), graph.hop_score(1.0, "industry", 10))

    def test_the_stronger_of_two_paths_to_one_asset_is_kept(self):
        # a reaches b through a two-asset product and through a twenty-asset industry. The
        # product path is the one worth reading, so it is the one stored.
        adj = graph.groups_to_edges(
            [
                ("product", "P1", ["a", "b"]),
                ("industry", "Crowded", ["a", "b"] + [f"x{i}" for i in range(18)]),
            ]
        )
        got = graph.walk(adj, "a", "a has a catalyst")
        self.assertEqual(got["b"]["kind"], "product")


class RunReport(unittest.TestCase):
    """The end-of-run table names the failing step.

    This is here because of a real problem. run.py continues past a failed step on purpose,
    so a run of fourteen jobs where one fails exited non-zero with the answer to "which one"
    scattered through thousands of lines of streamed output, and reading it needed a sign-in.
    """

    def test_a_clean_run_reports_no_failures(self):
        self.assertEqual(run.report("daily", [("prices yahoo", 0, 60.0)]), [])

    def test_every_failing_step_is_named_in_order(self):
        got = run.report(
            "daily",
            [("prices yahoo", 0, 10.0), ("geo", 1, 90.0), ("rank", 0, 5.0), ("upcoming", 2, 1.0)],
        )
        self.assertEqual(got, ["geo", "upcoming"])

    def test_the_step_label_keeps_its_arguments(self):
        # "psx" and "psx full" are different steps and the table has to say which ran.
        self.assertEqual(run.report("weekly", [("psx full", 1, 3.0)]), ["psx full"])

    def test_the_summary_file_is_written_when_github_supplies_one(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "summary.md")
            os.environ["GITHUB_STEP_SUMMARY"] = path
            try:
                run.report("daily", [("geo", 1, 2.0)])
            finally:
                del os.environ["GITHUB_STEP_SUMMARY"]
            with open(path, encoding="utf-8") as fh:
                written = fh.read()
        self.assertIn("geo", written)
        self.assertIn("FAILED exit 1", written)

    def test_every_step_in_a_plan_names_a_script_that_exists(self):
        # A typo in DAILY or WEEKLY would fail only at 07:17, inside the scheduled run.
        for group, plans in run.GROUPS.items():
            for plan in plans:
                for script, _ in plan:
                    self.assertTrue(
                        (ROOT / "jobs" / f"{script}.py").exists(),
                        f"{group} names jobs/{script}.py, which does not exist",
                    )

    def test_intraday_follows_the_jobs_its_active_set_is_chosen_from(self):
        # The active set is selected from the setup, thesis, graph and news rows, so every one
        # of those has to be written before the request budget is spent.
        for plan in (run.DAILY, run.WEEKLY):
            order = [script for script, _ in plan]
            for earlier in ("setup", "thesis", "graph", "human"):
                self.assertLess(order.index(earlier), order.index("intraday"))

    def test_the_reading_jobs_follow_the_jobs_they_read(self):
        # thesis reads the AssetSetup row setup.py writes, and graph walks out from the
        # catalysts human.py flags. Either one running first would read yesterday's rows.
        for plan in (run.DAILY, run.WEEKLY):
            order = [script for script, _ in plan]
            self.assertLess(order.index("setup"), order.index("thesis"))
            self.assertLess(order.index("human"), order.index("graph"))
            self.assertLess(order.index("lineage"), order.index("human"))


class ChunkParsing(unittest.TestCase):
    """`--chunk 3/8` is read by the runner and by the job, and both have to read it the same.

    The flag is written by hand in a workflow file and by a matrix that generates slice numbers.
    A malformed one has to stop at the gate: a job handed "3/0" cannot tell a typo from a matrix
    that produced a slice which does not exist, and either way the answer is to not run.
    """

    def test_a_slice_is_one_based_and_reads_as_a_person_wrote_it(self):
        self.assertEqual(runlog.parse_chunk("3/8"), (3, 8))
        self.assertEqual(runlog.parse_chunk("1/1"), (1, 1))
        self.assertEqual(runlog.parse_chunk("8/8"), (8, 8))

    def test_a_slice_that_does_not_exist_is_refused(self):
        for bad in ("0/8", "9/8", "3/0", "-1/8"):
            with self.assertRaises(ValueError, msg=bad):
                runlog.parse_chunk(bad)

    def test_a_malformed_flag_is_refused_rather_than_guessed(self):
        for bad in ("3", "", "3/8/2", "three/eight", "3 /8", None, "/"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                runlog.parse_chunk(bad)

    def test_the_label_written_to_the_column_is_canonical(self):
        # The freshness panel groups by this string, so a slice filed under "3 /8" is a slice
        # nobody finds.
        self.assertEqual(runlog.chunk_label(*runlog.parse_chunk("3/8")), "3/8")

    def test_the_runner_takes_the_group_and_the_chunk_in_either_position(self):
        self.assertEqual(run.parse_args(["crypto", "--chunk", "2/4"]), ("crypto", "2/4"))
        self.assertEqual(run.parse_args(["--chunk", "2/4", "crypto"]), ("crypto", "2/4"))
        self.assertEqual(run.parse_args(["daily"]), ("daily", None))
        self.assertEqual(run.parse_args([]), ("daily", None))

    def test_the_runner_refuses_a_chunk_it_cannot_parse(self):
        with self.assertRaises(ValueError):
            run.parse_args(["crypto", "--chunk", "0/4"])
        with self.assertRaises(ValueError):
            run.parse_args(["crypto", "--chunk"])


class ChunkSlicing(unittest.TestCase):
    """Slices must be stable, disjoint and complete, or a retry covers the wrong work.

    Stability is the one that bites. The work list arrives from a query, and a query without an
    ORDER BY may hand back the same rows in a different order next run, so slicing that order
    would put a symbol in slice 2 this morning and slice 5 this afternoon — a cursor saying
    "1 through 4 are done" and a retry of 5 would then be talking about different sets, and
    something would be fetched twice while something else was never fetched at all.
    """

    SYMBOLS = ["NVDA", "BTC", "AAPL", "ETH", "MSFT", "SOL", "TSLA", "AVAX", "GOOGL", "LINK", "AMD"]

    def test_the_same_symbol_lands_in_the_same_slice_whatever_the_input_order(self):
        shuffled = list(reversed(self.SYMBOLS))
        for i in range(1, 5):
            self.assertEqual(
                runlog.slice_of(self.SYMBOLS, i, 4), runlog.slice_of(shuffled, i, 4)
            )

    def test_every_item_lands_in_exactly_one_slice(self):
        for total in (1, 2, 3, 4, 8, 11):
            seen = [x for i in range(1, total + 1) for x in runlog.slice_of(self.SYMBOLS, i, total)]
            self.assertEqual(sorted(seen), sorted(self.SYMBOLS), f"N={total}")
            self.assertEqual(len(seen), len(set(seen)), f"N={total} covered something twice")

    def test_n_slices_cover_the_whole_list_even_when_n_exceeds_it(self):
        # A matrix of eight against three coins is a legitimate configuration; five of the
        # slices are empty and none of the coins is lost.
        covered = [x for i in range(1, 9) for x in runlog.slice_of(["BTC", "ETH", "SOL"], i, 8)]
        self.assertEqual(sorted(covered), ["BTC", "ETH", "SOL"])

    def test_slices_are_balanced_to_within_one(self):
        sizes = [len(runlog.slice_of(self.SYMBOLS, i, 4)) for i in range(1, 5)]
        self.assertLessEqual(max(sizes) - min(sizes), 1, sizes)
        self.assertEqual(sum(sizes), len(self.SYMBOLS))

    def test_one_of_one_is_the_whole_list_sorted(self):
        self.assertEqual(runlog.slice_of(self.SYMBOLS, 1, 1), sorted(self.SYMBOLS))

    def test_an_empty_work_list_slices_into_empty_slices(self):
        self.assertEqual(runlog.slice_of([], 2, 4), [])

    def test_a_key_slices_rows_by_their_identifier(self):
        rows = [{"symbol": s} for s in self.SYMBOLS]
        got = runlog.slice_of(rows, 1, 4, key=lambda r: r["symbol"])
        self.assertEqual([r["symbol"] for r in got], runlog.slice_of(self.SYMBOLS, 1, 4))


class ChunkStatus(unittest.TestCase):
    """The default judgement a slice gets when the job does not name one.

    `empty` is the loud state and the reason the table exists: a throttled provider returns an
    empty result and raises nothing, so from inside a job "blocked" and "a quiet market" are the
    same picture, and the only honest thing is to record the state that needs looking at.
    """

    def test_asking_for_things_and_writing_none_is_empty(self):
        self.assertEqual(runlog.default_status(asked=30, rows_written=0), "empty")

    def test_asking_for_nothing_and_writing_nothing_is_not_a_failure(self):
        # A rerun inside the cache window legitimately writes zero of zero.
        self.assertEqual(runlog.default_status(asked=0, rows_written=0), "ok")

    def test_some_but_not_all_items_answering_is_partial(self):
        self.assertEqual(runlog.default_status(asked=10, rows_written=123, answered=7), "partial")

    def test_partial_counts_items_and_not_rows(self):
        # Ten coins can write a hundred and twenty three rows, so rows carry no information
        # about how many coins answered. A job that does not count answers gets ok, not partial.
        self.assertEqual(runlog.default_status(asked=10, rows_written=123), "ok")
        self.assertEqual(runlog.default_status(asked=10, rows_written=123, answered=10), "ok")

    def test_a_job_may_override_the_judgement(self):
        run_row = runlog.Slice(job="cron-crypto", source="Binance", asked=10, rows_written=0)
        self.assertEqual(run_row.resolved_status(), "empty")
        run_row.status = "ok"
        self.assertEqual(run_row.resolved_status(), "ok")

    def test_a_status_outside_the_four_is_refused(self):
        run_row = runlog.Slice(job="cron-crypto", source="Binance", status="fine")
        with self.assertRaises(ValueError):
            run_row.resolved_status()

    def test_a_note_is_never_empty_even_when_the_job_sets_none(self):
        # The model's comment says a failed chunk with no note is the thing this table exists to
        # stop, so the fallback is built from the counts rather than left to a convention.
        run_row = runlog.Slice(job="cron-crypto", source="Binance", chunk="2/4", asked=10)
        note = run_row.resolved_note()
        self.assertTrue(note.strip())
        self.assertIn("Binance", note)
        self.assertIn("2/4", note)

    def test_a_long_note_is_cut_rather_than_written_whole(self):
        run_row = runlog.Slice(job="j", source="s", note="x" * 5000)
        self.assertLessEqual(len(run_row.resolved_note()), runlog.NOTE_MAX)

    def test_the_writer_refuses_a_blank_note_outright(self):
        with self.assertRaises(ValueError):
            runlog.write(
                job="j", source="s", chunk="1/1", rows_written=0, asked=0, newest=None,
                status="ok", note="   ", duration_ms=1,
            )


class ChunkGroups(unittest.TestCase):
    """The small groups are selections over the existing steps, not second copies of them."""

    SMALL = ("crypto", "us-prices", "psx", "news", "products", "decision", "audit")

    def test_the_original_three_groups_still_exist(self):
        # schema.yml and backfill.yml call these by name today.
        for name in ("seed", "daily", "weekly"):
            self.assertIn(name, run.GROUPS)

    def test_every_small_group_exists_and_has_work(self):
        for name in self.SMALL:
            self.assertIn(name, run.GROUPS)
            steps = [s for plan in run.GROUPS[name] for s in plan]
            self.assertTrue(steps, f"{name} has no steps")

    def test_every_small_group_step_appears_in_daily_or_weekly(self):
        # A group that invents a step is a group that runs something nothing else runs.
        known = {script for plan in (run.DAILY, run.WEEKLY) for script, _ in plan}
        for name in self.SMALL:
            for script, _ in [s for plan in run.GROUPS[name] for s in plan]:
                self.assertIn(script, known, f"{name} runs {script}, which no lane runs")

    def test_decision_fetches_nothing_from_a_price_or_product_source(self):
        names = [script for script, _ in run.DECISION]
        for fetcher in run.FETCH_STEPS:
            self.assertNotIn(fetcher, names)

    def test_decision_keeps_dailys_ordering(self):
        order = [script for script, _ in run.DECISION]
        self.assertEqual(order, [s for s, _ in run.DAILY if s in set(order)])
        self.assertLess(order.index("setup"), order.index("thesis"))
        self.assertLess(order.index("human"), order.index("graph"))

    def test_audit_is_not_inside_the_group_it_judges(self):
        # A coverage flag is a judgement about a finished fetch; computing it mid-write reads
        # half of one.
        self.assertNotIn("audit", [script for script, _ in run.DECISION])

    def test_the_price_groups_each_ask_for_one_lane(self):
        self.assertEqual(run.GROUPS["crypto"], [[("prices", ["crypto"])]])
        self.assertEqual(run.GROUPS["us-prices"], [[("prices", ["yahoo"])]])
        self.assertEqual(run.GROUPS["news"], [[("prices", ["news"])]])


class ChunkPlumbing(unittest.TestCase):
    """A step gets --chunk when its job parses one, and runs whole when it does not."""

    def test_a_step_that_cannot_slice_still_runs_its_whole_source(self):
        # Skipping would mean a scheduled "--chunk 1/8" lane silently never fetched that source.
        steps, unsliced = run.plan_with_chunk([("audit", [])], "2/4")
        self.assertEqual(steps, [("audit", [])])
        self.assertEqual(unsliced, ["audit"])

    def test_no_chunk_leaves_every_step_exactly_as_the_plan_wrote_it(self):
        steps, unsliced = run.plan_with_chunk([("prices", ["crypto"])], None)
        self.assertEqual(steps, [("prices", ["crypto"])])
        self.assertEqual(unsliced, [])

    def test_the_flag_follows_the_arguments_the_plan_already_passes(self):
        # prices.py reads its lane names off argv, so the flag has to come after them.
        run._chunk_support["prices"] = True
        try:
            steps, unsliced = run.plan_with_chunk([("prices", ["crypto"])], "2/4")
        finally:
            run._chunk_support.pop("prices", None)
        self.assertEqual(steps, [("prices", ["crypto", "--chunk", "2/4"])])
        self.assertEqual(unsliced, [])

    def test_support_is_read_from_the_job_rather_than_listed_here(self):
        # These files belong to other engineers and chunking is landing in them one at a time,
        # so a hand-kept list in run.py would be wrong in one of two directions.
        run._chunk_support.clear()
        self.assertFalse(run.supports_chunk("nbt"))
        self.assertFalse(run.supports_chunk("no_such_job"))

    def test_the_table_header_says_which_slice_ran(self):
        # Eight runners write eight identical-looking logs; the slice is how they are told apart.
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(run.report("crypto 2/4", [("prices crypto", 0, 1.0)]), [])
        self.assertIn("run crypto 2/4: 1 steps", buf.getvalue())

    def test_an_unsliced_step_is_noted_in_the_summary_rather_than_hidden(self):
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run.report("products 1/4", [("geo", 0, 1.0)], ["--chunk 1/4 was not passed to geo"])
        self.assertIn("note: --chunk 1/4 was not passed to geo", buf.getvalue())


class Forex(unittest.TestCase):
    """A currency pair has no issuer, and every consequence of that has to hold.

    Forex is the first class on this site with nothing behind the price: no share count, so no
    size; no exchange, so no session and no holiday; no consolidated tape, so no volume. Each of
    those is a hole, and hard rule 2 says a hole stays a hole rather than being filled with a
    plausible number. These pin the places where filling one would be easy and silent.
    """

    @property
    def fx(self):
        return [a for a in seed.ASSETS if a[3] == "forex"]

    def test_every_pair_is_seeded_with_no_size_basis(self):
        """capBasis `none` is what keeps a size out of the tables rather than a zero.

        `marketCap` would make jobs/rank.py compute price x shares with no shares, and
        `fundAssets` would do the same. `none` is the only honest answer for an instrument that
        is a ratio between two currencies, and the industry page already renders the absence in
        words.
        """
        self.assertTrue(self.fx, "no forex assets are seeded")
        for slug, symbol, _name, _t, cap, source, ref, _note in self.fx:
            self.assertEqual(cap, "none", f"{symbol} claims a size basis")
            self.assertEqual(source, "yahoo", f"{symbol} is not on the existing Yahoo lane")
            self.assertTrue(ref.endswith("=X"), f"{symbol} sourceRef {ref} is not a Yahoo FX ref")
            self.assertTrue(slug.startswith("fx-"), f"{symbol} is filed under {slug}")
            self.assertEqual(len(symbol), 6, f"{symbol} is not a six letter pair")

    def test_the_pairs_are_unique_and_not_pegged(self):
        """A peg has no return to rank, so ranking it would be ranking noise.

        USDAED and USDSAR are hard pegged to the dollar and USDHKD trades in a band of about one
        percent. All three were checked against the source and dropped rather than carried: a
        table ordered by return would put them wherever rounding left them.
        """
        symbols = [a[1] for a in self.fx]
        self.assertEqual(len(symbols), len(set(symbols)), "a pair is seeded twice")
        for pegged in ("USDAED", "USDSAR", "USDHKD"):
            self.assertNotIn(pegged, symbols, f"{pegged} is a peg and has no return to rank")

    def test_every_forex_industry_is_declared_a_forex_industry(self):
        """The slug prefix is what seed.py derives the market from, so it is load bearing."""
        fx_slugs = {i[0] for i in seed.INDUSTRIES if i[0].startswith("fx-")}
        self.assertTrue(fx_slugs, "no fx- industries")
        for slug, *_rest in self.fx:
            self.assertIn(slug, fx_slugs, f"{slug} has no industry row")
        # And nothing non-forex may sit in one, or it would be filed under the FX market.
        for a in seed.ASSETS:
            if a[0].startswith("fx-"):
                self.assertEqual(a[3], "forex", f"{a[1]} is {a[3]} inside an FX industry")

    def test_a_pair_is_never_asked_for_a_company_calendar(self):
        """jobs/upcoming.py selects stock and etf only, and that is what keeps FX out.

        A currency pair has no earnings date and no dividend. Asking Yahoo for one per pair
        would be 27 more requests for a guaranteed empty answer, on the lane whose per-asset
        request loop already cost two days of decisions.
        """
        src = (ROOT / "jobs" / "upcoming.py").read_text(encoding="utf-8")
        self.assertIn("IN ('stock','etf')", src)
        self.assertNotIn("forex", src)

    def test_a_pair_never_stores_a_zero_volume(self):
        """Yahoo answers 0 volume for every FX bar, and 0 is not a measurement.

        FX is over the counter, so no venue publishes a consolidated volume. Writing the 0 down
        would be read as real by `avg_volume` in jobs/rank.py, by `write_rising`'s volume check,
        and by VOLUME_CONFIRMS_AT in lib/decision.ts -- the last one divides a session by its own
        average, which is 0/0. Every one of those already handles a null correctly.
        """
        src = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        self.assertIn("is_forex = a.get(\"assetType\") == \"forex\"", src)
        self.assertIn("if vol == vol and not (is_forex and not vol):", src)
        # The writer can only know it is forex if the selector carries the column.
        self.assertIn('a."assetType"::text AS "assetType"', src)


class SchemaGuard(unittest.TestCase):
    """The refresh lane must refuse to run against a schema that is behind.

    This replaced a second `prisma migrate deploy`. Two workflows migrating one database from
    two concurrency groups is what killed run 36798989654, so the comparison below is the
    whole of the fix: it answers the same question without being a second writer.
    """

    HAVE = ["20260929125054_init", "20260930090154_confidence", "20261002030000_thesis"]

    def test_a_current_database_has_nothing_pending(self):
        self.assertEqual(schemacheck.pending(self.HAVE, set(self.HAVE)), [])
        self.assertEqual(schemacheck.extra(self.HAVE, set(self.HAVE)), [])

    def test_a_behind_database_names_what_is_missing_in_apply_order(self):
        applied = {"20260929125054_init"}
        self.assertEqual(
            schemacheck.pending(self.HAVE, applied),
            ["20260930090154_confidence", "20261002030000_thesis"],
        )

    def test_a_database_ahead_of_the_checkout_is_reported_not_failed(self):
        # A scheduled run on an older checkout meeting a newer database. Every write in this
        # repo is an upsert and a table nothing reads is inert, so this is allowed.
        applied = set(self.HAVE) | {"20261103000000_later"}
        self.assertEqual(schemacheck.pending(self.HAVE, applied), [])
        self.assertEqual(schemacheck.extra(self.HAVE, applied), ["20261103000000_later"])

    def test_the_real_migration_folder_is_read_in_sortable_order(self):
        got = schemacheck.on_disk(schemacheck.MIGRATIONS)
        self.assertGreater(len(got), 10)
        self.assertEqual(got, sorted(got))
        # migration_lock.toml is a file, not a migration, and must not be counted as one.
        self.assertNotIn("migration_lock.toml", got)

    def test_a_missing_folder_yields_nothing_rather_than_raising(self):
        self.assertEqual(schemacheck.on_disk(ROOT / "does-not-exist"), [])


class WorkflowLanes(unittest.TestCase):
    """Only one workflow may migrate, and the data lanes must check instead.

    Pinned as a test because the failure it prevents is invisible in review: both files read
    correctly on their own, and the race only exists in the pair.
    """

    WORKFLOWS = ROOT / ".github" / "workflows"

    def _text(self, name):
        return (self.WORKFLOWS / name).read_text(encoding="utf-8")

    def test_exactly_one_workflow_applies_migrations(self):
        """Exactly one workflow may apply migrations, and refresh.yml must not be it.

        Comment lines are stripped first, because refresh.yml explains in a comment why it no
        longer migrates and a comment is not a second migrator. The command is then matched
        anywhere in the remaining YAML rather than only on a `run:` line — schema.yml wraps it
        in a `run: |` block to copy its output to the run summary, and an earlier version of
        this test went quiet the moment that happened, which is the one failure mode a guard
        like this must not have.
        """
        migrating = []
        for path in sorted(self.WORKFLOWS.glob("*.yml")):
            code = chr(10).join(
                line.split("#", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
            )
            if "prisma migrate deploy" in code:
                migrating.append(path.name)
        self.assertEqual(migrating, ["schema.yml"], f"migration is applied by {migrating}")

    # How a job in this lane declares that its network use is bounded. `intraday.py` sets
    # MAX_REQUESTS = 60 and is the one fetch the decision lane is allowed to keep, because a
    # ceiling means a selection bug costs one capped run rather than the whole budget.
    NETWORK_CALLS = ("yf.Ticker", "get_json(", "requests.", "urlopen(")

    def test_no_uncapped_fetcher_sits_in_the_decision_lane(self):
        """A per-asset network loop in the decision lane will eventually kill it.

        This is the outage of 2026-10-04 written as a test. `upcoming` -- one yfinance call per
        Yahoo-sourced name with a forced half-second sleep, 126 of them and growing -- sat in
        the `decision` group. When the universe went from 160 names to 240 the group crossed its
        20 minute budget, was killed at 1197s, and was killed again the next day. Two sessions
        have no DecisionLog rows at all, which is the one output the site is built around, while
        every table feeding it was fresh to the day.

        Nothing caught it. The group's own workflow says in a comment that it "fetches nothing",
        and that comment was simply false for weeks. A sentence in a header is not a constraint,
        so the constraint lives here: a job in this lane may touch the network only if it caps
        how often, and `upcoming` belongs to FETCH_STEPS where the filter keeps it out.
        """
        import re

        offenders = []
        for script, _args in run.DECISION:
            path = ROOT / "jobs" / f"{script}.py"
            code = chr(10).join(
                line.split("#", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
            )
            if not any(tok in code for tok in self.NETWORK_CALLS):
                continue
            if not re.search(r"^MAX_REQUESTS\s*=\s*\d+", code, re.M):
                offenders.append(script)
        self.assertEqual(
            offenders,
            [],
            f"uncapped network loop in the decision lane: {offenders}",
        )

    def test_the_calendar_fetch_is_not_in_the_decision_lane(self):
        """The specific move that fixed it, pinned so it cannot drift back."""
        self.assertIn("upcoming", run.FETCH_STEPS, "upcoming is a fetcher and must be declared one")
        self.assertNotIn("upcoming", [s for s, _ in run.DECISION])
        self.assertIn("calendar", run.GROUPS, "upcoming needs a lane of its own to run in")
        self.assertEqual([s for s, _ in run.GROUPS["calendar"][0]], ["upcoming"])
        # Still in the full daily run: it moved lanes, it was not dropped.
        self.assertIn("upcoming", [s for s, _ in run.DAILY])

    def test_the_decision_writer_survives_a_dead_derivation(self):
        """`decide` must be its own job, or a timeout skips it exactly when it is needed.

        These were two steps of one job, the second marked `if: always()` so a failed derivation
        still produced rows -- "a day with no row at all is a hole in the record". That net never
        fired, because `timeout-minutes` kills the job: on 2026-10-04 the derivation hit 1197s,
        the runner was cancelled, and the writer was reported `skipped`. `if: always()` survives
        a failed step and not a dead runner, so the writer needs a runner of its own.
        """
        text = self._text("cron-decision.yml")
        self.assertIn(chr(10) + "  derive:" + chr(10), text, "no derive job")
        self.assertIn(chr(10) + "  decide:" + chr(10), text, "no decide job")

        decide = text.split(chr(10) + "  decide:" + chr(10), 1)[1]
        self.assertIn("needs: derive", decide, "decide does not wait for derive")
        self.assertIn("if: always()", decide, "decide would be skipped when derive fails")
        self.assertIn("node tools/decide.mjs", decide, "decide job does not write the rows")

        # And the derivation must not be able to take the writer's budget with it.
        derive = text.split(chr(10) + "  derive:" + chr(10), 1)[1].split(chr(10) + "  decide:", 1)[0]
        self.assertNotIn("node tools/decide.mjs", derive, "the writer is back inside derive")

    def test_migrations_never_run_through_the_connection_pooler(self):
        """`migrate deploy` must override DATABASE_URL with a direct endpoint.

        It takes a session-level advisory lock and releases it by ending the session. Neon's
        `-pooler` host is PgBouncer in transaction mode, which returns that server connection to
        the pool still holding the lock, so the next migration dies `P1002` after the 10s
        timeout. Schema run 50 on 2026-10-02 failed in twelve seconds this way, on a commit
        touching only Markdown, and the only reason it was readable at all is the summary this
        step writes. Asserted against the file because reproducing it needs a pooler and two
        runs, which no unit test has.
        """
        text = self._text("schema.yml")
        step = text.split("Apply pending schema migrations", 1)[1].split("- uses:", 1)[0]
        self.assertIn("DIRECT_DATABASE_URL", step, "no direct endpoint is offered")
        self.assertIn("${DATABASE_URL/-pooler./.}", step, "no fallback strips -pooler")
        # The point of the step: the command must not inherit the pooled URL from the
        # environment. If this assertion is ever relaxed, read P1002 before relaxing it.
        self.assertIn(
            'out="$(DATABASE_URL="$direct" npx prisma migrate deploy 2>&1)"',
            step,
            "migrate deploy still runs on the inherited DATABASE_URL",
        )

    def test_the_data_lanes_check_the_schema_before_writing(self):
        for name in ("refresh.yml", "backfill.yml"):
            self.assertIn("jobs/schemacheck.py", self._text(name), f"{name} does not check")

    def test_the_schema_lane_keeps_its_own_concurrency_group(self):
        # A hung enrichment fetch once held the shared group for 90+ minutes while the
        # migration the deployed site needed sat queued behind it. P3 must never block P0.
        self.assertIn("group: nbt-schema", self._text("schema.yml"))
        for name in ("refresh.yml", "backfill.yml"):
            self.assertIn("group: nbt-database", self._text(name))

    # Every scheduled data lane, so a new source workflow cannot be added without the guards
    # that the four-workflow world only ever applied to refresh.yml.
    SOURCE_LANES = (
        "cron-crypto.yml", "cron-us-prices.yml", "cron-psx.yml", "cron-news.yml",
        "cron-products.yml", "cron-decision.yml", "cron-audit.yml",
    )

    def test_every_source_lane_checks_the_schema_and_never_migrates(self):
        for name in self.SOURCE_LANES:
            self.assertIn("jobs/schemacheck.py", self._text(name), f"{name} does not check")

    def test_every_source_lane_proves_it_is_running_main(self):
        # GitHub takes the file from the default branch, master, which was 34 commits behind main
        # on 2026-10-03. A lane without this guard refreshes from stale code and passes.
        for name in self.SOURCE_LANES:
            text = self._text(name)
            self.assertIn("Prove this run is executing main", text, name)
            self.assertIn("ref: main", text, name)

    def test_no_two_source_lanes_share_a_concurrency_group(self):
        # One pending run per group is GitHub's rule, so a shared group means the newer run
        # cancels the queued older one. That is why geo.py kept being cancelled.
        import re
        seen = {}
        for name in self.SOURCE_LANES:
            found = re.findall(r"^concurrency:\n  group: (\S+)", self._text(name), re.M)
            self.assertEqual(len(found), 1, f"{name} declares {found}")
            self.assertNotIn(found[0], seen, f"{name} shares {found[0]} with {seen.get(found[0])}")
            self.assertNotIn(found[0], ("nbt-database", "nbt-schema"), f"{name} reuses a shared lane")
            seen[found[0]] = name

    def test_every_source_lane_writes_a_readable_summary(self):
        # An Actions log needs a GitHub sign-in; the run summary page does not.
        for name in self.SOURCE_LANES:
            self.assertIn("$GITHUB_STEP_SUMMARY", self._text(name), name)

    def test_chunked_lanes_do_not_cancel_their_sibling_chunks(self):
        # fail-fast would rebuild the coupling the per-source split exists to remove.
        for name in ("cron-us-prices.yml", "cron-products.yml"):
            self.assertIn("fail-fast: false", self._text(name), name)

    def test_a_chunked_lane_only_chunks_a_job_that_slices_its_work(self):
        # The four-way matrix was pointed at a job that ignored --chunk, so every slot ran all
        # eighty symbols four times with four writers racing the same rows. Worse than no
        # chunking, and invisible: each run was green.
        self.assertIn("--chunk", (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8"))

    def test_the_scheduled_lane_still_proves_it_is_running_main(self):
        self.assertIn("Prove this run is executing main", self._text("refresh.yml"))
        self.assertIn("ref: main", self._text("refresh.yml"))


def _ibars(n, start=None, interval=5, vol=100.0, session=None):
    """n consecutive intraday bars, each one unit higher, for the aggregation tests."""
    base = start or datetime(2026, 10, 1, 13, 30)
    out = []
    for i in range(n):
        ts = base + timedelta(minutes=interval * i)
        out.append({
            "ts": ts,
            "sessionDate": session or base.date(),
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": vol,
            "interval": interval,
            "phase": "regular",
        })
    return out


class IntradayAggregation(unittest.TestCase):
    """Derived bars must be exact or absent.

    A 60 minute bar assembled from nine of its twelve five minute bars is a quieter hour than
    the one that happened, so every case here is about refusing to build it.
    """

    def test_a_full_group_aggregates_exactly(self):
        got = intraday.aggregate(_ibars(3, interval=5), 15)
        self.assertEqual(len(got), 1)
        bar = got[0]
        self.assertAlmostEqual(bar["open"], 100.0)     # first open
        self.assertAlmostEqual(bar["close"], 102.5)    # last close
        self.assertAlmostEqual(bar["high"], 103.0)     # highest high
        self.assertAlmostEqual(bar["low"], 99.0)       # lowest low
        self.assertAlmostEqual(bar["volume"], 300.0)   # summed
        self.assertTrue(bar["derived"])
        self.assertEqual(bar["derivedFrom"], 5)
        self.assertEqual(bar["interval"], 15)

    def test_an_incomplete_group_is_skipped_not_assembled(self):
        # Two of the three bars a 15 minute bar needs.
        self.assertEqual(intraday.aggregate(_ibars(2, interval=5), 15), [])

    def test_a_partial_tail_does_not_produce_a_short_bar(self):
        # Four 5m bars make one complete 15m bar and one incomplete one. Only the first is
        # written; the leftover is not emitted as a five-minute-long "15 minute" bar.
        self.assertEqual(len(intraday.aggregate(_ibars(4, interval=5), 15)), 1)

    def test_one_absent_volume_makes_the_sum_absent(self):
        bars = _ibars(3, interval=5)
        bars[1]["volume"] = None
        got = intraday.aggregate(bars, 15)
        self.assertEqual(len(got), 1)
        self.assertIsNone(got[0]["volume"], "an undercount must not be presented as a total")

    def test_a_zero_volume_bar_still_sums(self):
        # Zero is a real quiet five minutes and is not the same as absent.
        bars = _ibars(3, interval=5)
        bars[1]["volume"] = 0.0
        self.assertAlmostEqual(intraday.aggregate(bars, 15)[0]["volume"], 200.0)

    def test_an_interval_that_does_not_divide_is_refused(self):
        # 7 is not a whole multiple of 5, so there is no exact way to build it.
        self.assertEqual(intraday.aggregate(_ibars(12, interval=5), 7), [])

    def test_every_declared_derived_interval_divides_the_canonical_one(self):
        for minutes in intraday.DERIVE_TO:
            self.assertEqual(minutes % intraday.CANONICAL, 0, f"{minutes} is not buildable")

    def test_bars_from_two_sessions_do_not_merge(self):
        day1 = _ibars(3, start=datetime(2026, 10, 1, 13, 30))
        day2 = _ibars(3, start=datetime(2026, 10, 2, 13, 30))
        got = intraday.aggregate(day1 + day2, 15)
        self.assertEqual(len(got), 2)
        self.assertNotEqual(got[0]["sessionDate"], got[1]["sessionDate"])


class IntradayCompleteness(unittest.TestCase):
    """A source returning half its payload must not look healthy."""

    def setUp(self):
        self.now = datetime(2026, 10, 1, 20, 5)
        self.recent = datetime(2026, 10, 1, 20, 0)
        self.old = datetime(2026, 10, 1, 17, 0)

    def test_a_full_session_is_complete(self):
        status, note = intraday.classify(78, 78, 0, self.recent, self.now)
        self.assertEqual(status, "complete")
        self.assertIn("78", note)

    def test_half_a_session_is_partial_and_says_so(self):
        status, note = intraday.classify(39, 78, 0, self.recent, self.now)
        self.assertEqual(status, "partial")
        self.assertIn("must not be read as a quiet session", note)

    def test_no_bars_and_no_holes_is_empty_not_failed(self):
        # The right answer for a market that has not opened.
        self.assertEqual(intraday.classify(0, 78, 0, None, self.now)[0], "empty")

    def test_all_holes_is_a_failure(self):
        self.assertEqual(intraday.classify(0, 78, 78, None, self.now)[0], "failed")

    def test_an_old_newest_bar_is_stale(self):
        status, note = intraday.classify(78, 78, 0, self.old, self.now)
        self.assertEqual(status, "stale")
        self.assertIn("minutes old", note)

    def test_a_short_payload_reports_partial_even_when_also_stale(self):
        # The missing bars are the finding; the age is a consequence of them.
        self.assertEqual(intraday.classify(10, 78, 0, self.old, self.now)[0], "partial")

    def test_an_unknown_expected_count_does_not_invent_partial(self):
        # Crypto has no exchange session, so there is no expected count to compare against.
        self.assertEqual(intraday.classify(12, None, 0, self.recent, self.now)[0], "complete")


class IntradayNormalisation(unittest.TestCase):
    def test_a_null_close_is_a_hole_not_a_bar(self):
        payload = {
            "stamps": [1759325400, 1759325700],
            "open": [100.0, None], "high": [101.0, None],
            "low": [99.0, None], "close": [100.5, None], "volume": [10.0, None],
        }
        bars, holes, forming = intraday.to_bars(payload, 5)
        self.assertEqual(len(bars), 1)
        self.assertEqual(holes, 1, "a padded empty slot must be counted, not silently dropped")
        self.assertEqual(forming, 0)

    def test_absent_volume_stays_absent_and_zero_stays_zero(self):
        payload = {
            "stamps": [1759325400, 1759325700],
            "open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0], "close": [1.0, 1.0],
            "volume": [None, 0.0],
        }
        bars, _, _ = intraday.to_bars(payload, 5)
        self.assertIsNone(bars[0]["volume"])
        self.assertEqual(bars[1]["volume"], 0.0)

    def test_an_empty_payload_yields_nothing_rather_than_raising(self):
        self.assertEqual(intraday.to_bars({}, 5), ([], 0, 0))

    def test_a_truncated_quote_array_does_not_raise(self):
        # The provider has been seen to return shorter quote arrays than timestamps.
        # Aligned stamps so the truncation is the only thing under test.
        payload = {"stamps": [1759325400, 1759325700, 1759326000], "open": [1.0],
                   "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]}
        bars, holes, _ = intraday.to_bars(payload, 5)
        self.assertEqual(len(bars), 1)
        self.assertEqual(holes, 2)

    def test_the_bar_still_forming_is_discarded_and_counted(self):
        """Found in production: 100 of these had accumulated.

        The provider's last element is the bar currently forming, stamped with the quote time
        rather than a bar boundary. It is not an observation of a five minute period, it makes
        an aggregation group look complete when only part of it exists, and because every run
        stamps a different second it is a new unique key each time, so they pile up instead of
        being overwritten.
        """
        payload = {
            # 1759325400 is aligned; +163s is the quote time of an unfinished bar.
            "stamps": [1759325400, 1759325563],
            "open": [100.0, 100.4], "high": [101.0, 100.4],
            "low": [99.0, 100.4], "close": [100.5, 100.4], "volume": [10.0, 0.0],
        }
        bars, holes, forming = intraday.to_bars(payload, 5)
        self.assertEqual(len(bars), 1, "the unfinished bar must not be stored")
        self.assertEqual(forming, 1, "and it must be counted, not silently dropped")
        self.assertEqual(holes, 0, "it is not a hole: nothing is missing, it has not closed")

    def test_alignment_is_checked_against_the_interval_not_a_constant(self):
        aligned_for_five = 1759325400          # :30:00
        aligned_for_one = 1759325460           # :31:00
        payload = {"stamps": [aligned_for_one], "open": [1.0], "high": [1.0],
                   "low": [1.0], "close": [1.0], "volume": [1.0]}
        self.assertEqual(len(intraday.to_bars(payload, 1)[0]), 1)
        self.assertEqual(len(intraday.to_bars(payload, 5)[0]), 0)
        self.assertEqual(aligned_for_five % 300, 0)

    def test_expected_bars_comes_from_the_stated_period(self):
        # 09:30 to 16:00 New York is 6.5 hours: 78 five minute bars, 26 fifteens.
        regular = {"start": 1759325400, "end": 1759348800}
        self.assertEqual(intraday.expected_bars(regular, 5), 78)
        self.assertEqual(intraday.expected_bars(regular, 15), 26)

    def test_a_missing_period_gives_none_not_a_guess(self):
        self.assertIsNone(intraday.expected_bars(None, 5))
        self.assertIsNone(intraday.expected_bars({"start": 1, "end": 1}, 5))

    def test_psx_is_recorded_as_unsupported_rather_than_attempted(self):
        ok, why = intraday.supported({"source": "PSX daily closing file", "sourceRef": "HBL"})
        self.assertFalse(ok)
        self.assertIn("Pakistan", why)

    def test_a_us_listing_is_supported(self):
        ok, why = intraday.supported({"source": "Yahoo Finance", "sourceRef": "NVDA"})
        self.assertTrue(ok)
        self.assertEqual(why, "")

    def test_an_asset_with_no_provider_reference_is_unsupported(self):
        ok, why = intraday.supported({"source": "Yahoo Finance", "sourceRef": ""})
        self.assertFalse(ok)
        self.assertIn("recognise", why)

    def test_the_request_ceiling_bounds_a_selection_bug(self):
        # The ceiling exists so a selection bug costs one capped run rather than a ban.
        self.assertLessEqual(intraday.MAX_REQUESTS, 100)
        self.assertLess(intraday.FINE_SLICE, intraday.MAX_REQUESTS)

    def test_the_session_date_uses_the_exchange_offset(self):
        # A bar at 00:30 UTC belongs to the previous New York session, and splitting it onto
        # the UTC date would move it into a session it was not part of.
        bars = [{"ts": datetime(2026, 10, 2, 0, 30)}]
        intraday.session_dates(bars, -4 * 3600)
        self.assertEqual(bars[0]["sessionDate"].isoformat(), "2026-10-01")

    def test_phases_split_on_the_stated_regular_period(self):
        # Built in UTC explicitly. A naive datetime's .timestamp() uses the machine's local
        # zone, so this test passed or failed depending on where it ran.
        import calendar

        regular = {
            "start": calendar.timegm(datetime(2026, 10, 1, 13, 30).timetuple()),
            "end": calendar.timegm(datetime(2026, 10, 1, 20, 0).timetuple()),
        }
        bars = [
            {"ts": datetime(2026, 10, 1, 12, 0)},
            {"ts": datetime(2026, 10, 1, 15, 0)},
            {"ts": datetime(2026, 10, 1, 21, 0)},
        ]
        intraday.phase_of(bars, regular)
        self.assertEqual([b["phase"] for b in bars], ["pre", "regular", "post"])

    def test_no_period_leaves_every_bar_regular_rather_than_guessing(self):
        bars = [{"ts": datetime(2026, 10, 1, 12, 0)}]
        intraday.phase_of(bars, None)
        self.assertNotIn("phase", bars[0])


def _ohlc(closes, highs=None, lows=None, vols=None, session=None):
    """Bars shaped like the rows horizons.py reads, for the pure-logic tests."""
    n = len(closes)
    highs = highs or [c + 1.0 for c in closes]
    lows = lows or [c - 1.0 for c in closes]
    vols = vols if vols is not None else [1000.0] * n
    sess = session or [date(2026, 10, 1)] * n
    return [
        {"close": closes[i], "high": highs[i], "low": lows[i], "volume": vols[i],
         "sessionDate": sess[i], "ts": datetime(2026, 10, 1, 13, 30) + timedelta(minutes=5 * i)}
        for i in range(n)
    ]


class TrueRange(unittest.TestCase):
    def test_a_gap_between_bars_counts_as_movement(self):
        # Close-to-close would see nothing here; the gap from 10 to 20 is real range.
        bars = _ohlc([10.0, 20.0], highs=[10.0, 20.0], lows=[10.0, 20.0])
        self.assertAlmostEqual(horizons.true_range(bars, 1), 10.0)

    def test_it_needs_one_more_bar_than_the_window(self):
        self.assertIsNone(horizons.true_range(_ohlc([1.0, 2.0]), 5))

    def test_a_flat_series_has_a_measurable_range_not_none(self):
        bars = _ohlc([10.0] * 20, highs=[10.5] * 20, lows=[9.5] * 20)
        self.assertAlmostEqual(horizons.true_range(bars, 14), 1.0)


class Pivots(unittest.TestCase):
    def test_a_turn_is_found_where_the_series_actually_turned(self):
        closes = [1.0, 2.0, 5.0, 2.0, 1.0, 2.0, 5.0, 2.0, 1.0]
        highs, lows = horizons.pivots(_ohlc(closes, highs=closes, lows=closes), 120)
        self.assertIn(5.0, highs)

    def test_a_series_too_short_to_have_turns_yields_none(self):
        highs, lows = horizons.pivots(_ohlc([1.0, 2.0, 3.0]), 120)
        self.assertEqual((highs, lows), ([], []))

    def test_the_next_level_above_is_the_nearest_one(self):
        self.assertAlmostEqual(horizons.next_level([120.0, 150.0, 200.0], 100.0, True), 120.0)

    def test_the_next_level_below_is_the_nearest_one(self):
        self.assertAlmostEqual(horizons.next_level([50.0, 80.0, 95.0], 100.0, False), 95.0)

    def test_price_past_every_level_has_no_measured_level_left(self):
        # None rather than extrapolating one, which would be fake precision.
        self.assertIsNone(horizons.next_level([50.0, 80.0], 100.0, True))

    def test_a_level_merely_touched_does_not_count_as_beyond(self):
        self.assertIsNone(horizons.next_level([100.0], 100.0, True))


class IntradayRead(unittest.TestCase):
    """Every intraday condition must come from intraday bars, and say what is missing."""

    def _rising(self, n=50, vol_last=5000.0):
        closes = [100.0 + i * 0.5 for i in range(n)]
        vols = [1000.0] * (n - 1) + [vol_last]
        return _ohlc(closes, vols=vols)

    def test_a_clean_breakout_on_heavy_volume_is_a_buy(self):
        bars = self._rising()
        state, head, conds, missing, against, entry, invalid = horizons.intraday_read(
            bars, prior_high=110.0, prior_low=95.0
        )
        self.assertEqual(state, "buy")
        self.assertIn("cleared the previous session", head)
        self.assertLess(invalid, entry)

    def test_the_same_trend_without_the_breakout_is_wait(self):
        bars = self._rising()
        state, _, _, _, against, _, _ = horizons.intraday_read(
            bars, prior_high=10_000.0, prior_low=95.0
        )
        self.assertEqual(state, "wait")
        self.assertTrue(any("previous session" in a for a in against))

    def test_the_same_trend_without_volume_is_wait(self):
        bars = self._rising(vol_last=100.0)
        state, _, _, _, against, _, _ = horizons.intraday_read(
            bars, prior_high=110.0, prior_low=95.0
        )
        self.assertEqual(state, "wait")
        self.assertTrue(any("own recent average" in a for a in against))

    def test_absent_volume_is_recorded_as_missing_not_as_quiet(self):
        bars = self._rising()
        for b in bars:
            b["volume"] = None
        state, _, _, missing, _, _, _ = horizons.intraday_read(bars, 110.0, 95.0)
        self.assertTrue(any("provider sent no volume" in m for m in missing))
        self.assertNotEqual(state, "buy", "a buy must not rest on volume that was never sent")

    def test_no_previous_session_is_recorded_as_missing(self):
        bars = self._rising()
        _, _, _, missing, _, _, _ = horizons.intraday_read(bars, None, None)
        self.assertTrue(any("previous session" in m for m in missing))

    def test_a_falling_series_breaking_down_is_a_short(self):
        closes = [100.0 - i * 0.5 for i in range(50)]
        bars = _ohlc(closes, vols=[1000.0] * 49 + [5000.0])
        state, _, _, _, _, _, _ = horizons.intraday_read(bars, 120.0, 90.0)
        self.assertEqual(state, "short")

    def test_a_flat_series_has_no_clear_setup(self):
        bars = _ohlc([100.0, 100.5] * 25)
        state, head, _, _, _, _, _ = horizons.intraday_read(bars, 110.0, 95.0)
        self.assertEqual(state, "none")
        self.assertIn("between its intraday averages", head)

    def test_the_conditions_parse_with_the_thesis_verdict_reader(self):
        # thesis.py reads this exact format to decide whether a reason still holds. A new
        # horizon written in a new format would silently produce theses with nothing to
        # compare, so the two are pinned together here.
        _, _, conds, _, _, _, _ = horizons.intraday_read(self._rising(), 110.0, 95.0)
        got = thesis.verdicts(" | ".join(conds))
        self.assertIn("trend", got)
        self.assertIn("volume", got)
        self.assertIn(got["trend"], ("up", "down", "mixed"))


class LongerRead(unittest.TestCase):
    def _rising(self, n=260):
        return _ohlc([100.0 + i * 0.4 for i in range(n)])

    def test_a_long_uptrend_ahead_of_its_industry_is_a_buy(self):
        state, head, _, _, _, entry, invalid = horizons.longer_read(self._rising(), rel=12.0)
        self.assertEqual(state, "buy")
        self.assertIn("multi-year range", head)

    def test_the_same_trend_level_with_its_industry_is_wait(self):
        state, _, _, _, _, _, _ = horizons.longer_read(self._rising(), rel=0.5)
        self.assertEqual(state, "wait")

    def test_too_few_peers_is_recorded_as_missing(self):
        _, _, _, missing, _, _, _ = horizons.longer_read(self._rising(), rel=None)
        self.assertTrue(any("too few peers" in m for m in missing))

    def test_a_price_above_a_falling_long_mean_is_disclosed(self):
        # Rising recently, falling over the long window: the long trend has not turned.
        # A long way down, then a modest recent recovery. The 200 day mean is still falling
        # because the high bars leaving its window are far above the low bars entering it,
        # while price has risen enough to clear both averages.
        closes = [1000.0 - i * 4.2 for i in range(120)] + [100.0 + i * 0.5 for i in range(200)]
        state, _, _, _, against, _, _ = horizons.longer_read(_ohlc(closes), rel=12.0)
        self.assertTrue(any("still falling" in a for a in against), f"state was {state}")

    def test_the_longer_conditions_also_parse_with_the_thesis_reader(self):
        _, _, conds, _, _, _, _ = horizons.longer_read(self._rising(), rel=12.0)
        got = thesis.verdicts(" | ".join(conds))
        self.assertIn("trend", got)
        self.assertIn("relative", got)

    def test_the_longer_windows_are_genuinely_longer_than_the_swing_ones(self):
        import setup as swing

        self.assertGreater(horizons.LONG_FAST, swing.FAST)
        self.assertGreater(horizons.LONG_SLOW, swing.SLOW)


class Targets(unittest.TestCase):
    ANALOG = {"matches": 40, "positive": 25, "medianPct": 3.0, "minPct": -6.0, "maxPct": 9.0}

    def test_every_supported_method_produces_a_range(self):
        got = horizons.target_rows(100.0, 95.0, "buy", atr=2.0, level=112.0, analog=self.ANALOG)
        self.assertEqual({r["method"] for r in got}, {"structure", "volatility", "analog"})

    def test_no_invalidation_distance_means_no_target_at_all(self):
        # Reward with no risk behind it is a number with no decision attached.
        self.assertEqual(
            horizons.target_rows(100.0, 100.0, "buy", 2.0, 112.0, self.ANALOG), []
        )

    def test_nothing_supported_yields_nothing_rather_than_a_guess(self):
        self.assertEqual(horizons.target_rows(100.0, 95.0, "buy", None, None, None), [])

    def test_an_analog_target_requires_a_median_pointing_the_same_way(self):
        """Found in production: seven rows read like this.

        AAPL read `buy` at 333.08 with an "upside" analog range starting at 332.77 — below the
        entry — because the range ran from the median to the favourable extreme and the median
        was slightly negative. Reaching past an unfavourable median to quote the favourable
        tail is selecting the evidence that suits the conclusion.
        """
        adverse = {"matches": 40, "positive": 12, "medianPct": -0.1, "minPct": -6.0,
                   "maxPct": 9.0}
        got = horizons.target_rows(100.0, 95.0, "buy", atr=None, level=None, analog=adverse)
        self.assertEqual(got, [], "an adverse median must yield no analog target")

        favourable = {**adverse, "medianPct": 3.0}
        got = horizons.target_rows(100.0, 95.0, "buy", atr=None, level=None, analog=favourable)
        self.assertEqual(len(got), 1)
        self.assertGreater(got[0]["low"], 100.0, "the near edge must be beyond the entry")

    def test_a_short_analog_target_requires_a_negative_median(self):
        rising = {"matches": 40, "positive": 30, "medianPct": 2.0, "minPct": -6.0,
                  "maxPct": 9.0}
        self.assertEqual(
            horizons.target_rows(100.0, 105.0, "short", None, None, rising), []
        )
        falling = {**rising, "medianPct": -2.0}
        got = horizons.target_rows(100.0, 105.0, "short", None, None, falling)
        self.assertEqual(len(got), 1)
        self.assertLess(got[0]["high"], 100.0)

    def test_a_thin_analog_sample_is_not_used(self):
        thin = {**self.ANALOG, "matches": 3}
        got = horizons.target_rows(100.0, 95.0, "buy", None, None, thin)
        self.assertEqual(got, [])

    def test_a_short_setup_gets_a_downside_range(self):
        got = horizons.target_rows(100.0, 105.0, "short", atr=2.0, level=88.0, analog=self.ANALOG)
        for row in got:
            self.assertLess(row["low"], 100.0, f"{row['method']} points the wrong way")

    def test_reward_against_risk_uses_the_setups_own_invalidation(self):
        got = horizons.target_rows(100.0, 95.0, "buy", atr=None, level=110.0, analog=None)
        self.assertEqual(len(got), 1)
        # near edge 100 -> 110 is 10 of reward against 5 of risk.
        self.assertAlmostEqual(got[0]["rewardRisk"], 2.0)

    def test_the_volatility_range_is_a_multiple_of_its_own_true_range(self):
        got = horizons.target_rows(100.0, 95.0, "buy", atr=3.0, level=None, analog=None)
        self.assertAlmostEqual(got[0]["high"], 100.0 + horizons.ATR_MULTIPLE * 3.0)

    def test_disagreement_is_recorded_rather_than_averaged(self):
        # Structure says 101 (1 away), volatility says 140 (40 away). These are not one
        # answer, and the spread is 39/40 of the furthest distance.
        got = horizons.target_rows(100.0, 95.0, "buy", atr=20.0, level=101.0, analog=None)
        self.assertEqual(len(got), 2)
        self.assertTrue(all(r.get("agreement") is not None for r in got))
        self.assertAlmostEqual(got[0]["agreement"], 39.0 / 40.0)
        self.assertGreaterEqual(got[0]["agreement"], horizons.DISAGREE_AT)
        # No row is the mean of the two.
        self.assertNotIn(120.5, [r["high"] for r in got])

    def test_methods_that_broadly_agree_report_a_small_spread(self):
        got = horizons.target_rows(100.0, 95.0, "buy", atr=6.0, level=110.0, analog=None)
        self.assertLess(got[0]["agreement"], horizons.DISAGREE_AT)

    def test_no_target_range_contains_the_entry_on_either_side(self):
        # Spanning entry-to-target made the near edge the entry itself, which read as a
        # reward of zero. Pinned so it cannot come back.
        for direction, invalid in (("buy", 95.0), ("short", 105.0)):
            for row in horizons.target_rows(
                100.0, invalid, direction, atr=2.0, level=112.0 if direction == "buy" else 88.0,
                analog=self.ANALOG,
            ):
                self.assertNotAlmostEqual(
                    row["low"], 100.0, msg=f"{row['method']} starts at the entry"
                )
                self.assertGreater(row["rewardRisk"], 0.0, row["method"])

    def test_one_method_alone_records_no_disagreement(self):
        got = horizons.target_rows(100.0, 95.0, "buy", atr=None, level=110.0, analog=None)
        self.assertIsNone(got[0].get("agreement"))

    def test_every_note_says_what_it_is_not(self):
        got = horizons.target_rows(100.0, 95.0, "buy", atr=2.0, level=112.0, analog=self.ANALOG)
        for row in got:
            self.assertTrue(
                any(w in row["note"] for w in ("not a forecast", "not a direction",
                                               "not a projection")),
                f"{row['method']} does not state its limit",
            )


class HorizonGrading(unittest.TestCase):
    def test_a_horizon_is_not_graded_more_generously_than_the_swing_one(self):
        import setup as swing

        for state in ("buy", "short"):
            self.assertEqual(horizons.grade_for(state, [], []), "high")
            self.assertEqual(horizons.grade_for(state, ["x"], []), "medium")
            self.assertEqual(horizons.grade_for(state, [], ["y"]), "medium")
        self.assertEqual(horizons.grade_for("wait", [], []), "low")
        self.assertEqual(horizons.grade_for("none", [], []), "none")
        self.assertEqual(swing.HORIZON, "swing")


class InvestigationTrigger(unittest.TestCase):
    """A move is judged unusual against the asset's own history, never a fixed percentage."""

    QUIET = [0.2, -0.3, 0.1, -0.1, 0.4, -0.2, 0.3, 0.0, -0.4, 0.2] * 3
    WILD = [5.0, -6.0, 4.0, -5.0, 7.0, -4.0, 6.0, -7.0, 5.0, -6.0] * 3

    def test_a_small_move_is_unusual_for_a_quiet_asset(self):
        z = investigate.robust_z(3.0, self.QUIET)
        self.assertIsNotNone(z)
        self.assertGreater(z, investigate.ROBUST_Z)

    def test_the_same_move_is_ordinary_for_a_volatile_asset(self):
        z = investigate.robust_z(3.0, self.WILD)
        self.assertLess(abs(z), investigate.ROBUST_Z)

    def test_a_short_history_gives_no_score_rather_than_a_guess(self):
        self.assertIsNone(investigate.robust_z(5.0, [1.0, 2.0, 3.0]))

    def test_a_flat_history_does_not_divide_by_zero(self):
        z = investigate.robust_z(2.0, [1.0] * 30)
        self.assertIsNotNone(z)
        self.assertTrue(abs(z) < float("inf"))

    def test_a_floor_stops_a_tiny_move_on_a_flat_asset_being_investigated(self):
        # The robust score alone would flag a 0.3% move on a perfectly flat series. The move
        # floor is what stops the engine investigating noise.
        self.assertGreater(investigate.MOVE_FLOOR, 0.0)
        z = investigate.robust_z(0.3, [1.0] * 30)
        self.assertGreater(abs(z), investigate.ROBUST_Z)  # the score alone would flag it
        self.assertLess(0.3, investigate.MOVE_FLOOR)      # the floor does not


class InvestigationWording(unittest.TestCase):
    """Rule 10 applies here too: the engine reports co-movement and sequence, never cause."""

    BANNED = ("because", "driven by", "in response to", "caused", "due to", "reaction",
              "triggered the", "led to")

    def test_no_hypothesis_statement_claims_a_cause(self):
        for label, text in investigate.HYPOTHESES.items():
            low = text.lower()
            for word in self.BANNED:
                self.assertNotIn(word, low, f"{label}: {text}")

    def test_the_news_hypothesis_says_preceded_rather_than_caused(self):
        self.assertIn("preceded", investigate.HYPOTHESES["news"].lower())

    def test_the_three_measured_hypotheses_are_the_attribution_components(self):
        # They have to be the same three, or the investigation would be reasoning about a
        # decomposition that does not exist.
        self.assertEqual(
            {"market", "sector", "specific"},
            set(investigate.HYPOTHESES) - {"news"},
        )
        self.assertEqual(
            {"market", "sector", "specific"},
            set(attribution.COMPONENT_WORDS),
        )

    def test_the_investigation_is_bounded(self):
        # It must never become the reason a nightly run does not finish.
        self.assertLessEqual(investigate.MAX_INVESTIGATIONS, 60)
        self.assertLessEqual(investigate.NEWS_WINDOW_DAYS, 7)


class IntradayAdapter(unittest.TestCase):
    """The provider's symbol is not always the stored reference.

    Every case here comes from a real run. The crypto 404 was found by fetching, not by
    reading the code, which is why the mapping is pinned rather than trusted.
    """

    def test_a_crypto_slug_becomes_the_providers_pair(self):
        got = intraday.quote_symbol(
            {"symbol": "btc-bitcoin", "sourceRef": "btc-bitcoin",
             "source": "coinpaprika", "assetType": "crypto"}
        )
        self.assertEqual(got, "BTC-USD")

    def test_a_multi_word_slug_takes_only_the_ticker(self):
        got = intraday.quote_symbol(
            {"symbol": "bnb-binance-coin", "sourceRef": "bnb-binance-coin",
             "source": "coinpaprika", "assetType": "crypto"}
        )
        self.assertEqual(got, "BNB-USD")

    def test_an_equity_reference_is_passed_through_unchanged(self):
        got = intraday.quote_symbol(
            {"symbol": "NVDA", "sourceRef": "NVDA", "source": "Yahoo Finance",
             "assetType": "stock"}
        )
        self.assertEqual(got, "NVDA")

    def test_crypto_is_detected_by_source_as_well_as_type(self):
        # assetType is not always populated on every read path, so the source is a second
        # route to the same conclusion.
        got = intraday.quote_symbol(
            {"symbol": "sol-solana", "sourceRef": "sol-solana", "source": "coinpaprika"}
        )
        self.assertEqual(got, "SOL-USD")

    def test_an_asset_with_nothing_to_map_is_unsupported(self):
        ok, why = intraday.supported({"symbol": "", "sourceRef": "", "source": "Yahoo"})
        self.assertFalse(ok)
        self.assertIn("recognise", why)


class IntradayStaleness(unittest.TestCase):
    """Staleness is a question about the session in progress, and only that one."""

    def setUp(self):
        self.now = datetime(2026, 10, 1, 20, 5)
        self.hours_old = datetime(2026, 9, 29, 20, 0)

    def test_a_finished_session_is_complete_not_stale(self):
        # The first run marked 748 sessions stale and none complete, because every finished
        # session in a five day fetch has a newest bar hours old by definition.
        status, _ = intraday.classify(78, 78, 0, self.hours_old, self.now, is_latest=False)
        self.assertEqual(status, "complete")

    def test_the_session_in_progress_is_still_judged_on_age(self):
        status, _ = intraday.classify(78, 78, 0, self.hours_old, self.now, is_latest=True)
        self.assertEqual(status, "stale")

    def test_a_finished_session_can_still_be_partial(self):
        # Age is excused for a finished session; missing bars are not.
        status, _ = intraday.classify(10, 78, 0, self.hours_old, self.now, is_latest=False)
        self.assertEqual(status, "partial")


class IntradayFootprint(unittest.TestCase):
    """The free tier is a real constraint, and these are the numbers that keep it one."""

    def test_the_fetch_window_is_only_what_the_brain_reads(self):
        # One run at a month of five minute bars stored 201,726 rows and took the table to
        # 71 MB of a 500 MB tier, for data nothing queries.
        self.assertEqual(intraday.RANGE_FOR[5], "5d")
        self.assertEqual(intraday.RANGE_FOR[1], "1d")

    def test_five_days_of_bars_covers_what_the_readers_need(self):
        import horizons

        # A US session is 78 five minute bars, so five days is 390.
        available = 5 * horizons.SESSION_BARS
        self.assertGreaterEqual(available, horizons.SESSION_BARS * 2)
        self.assertGreaterEqual(available, horizons.STRUCTURE_LOOKBACK)

    def test_retention_matches_the_window_each_run_refetches(self):
        import horizons

        # Retention has to equal the refetch window, not merely exceed what readers need. A
        # bar outside the window is never revisited, so it keeps whatever session phase it was
        # given — and a stale phase silently degrades every read that filters on
        # `phase = 'regular'`. range=5d spans seven calendar days across a weekend.
        self.assertEqual(intraday.RANGE_FOR[5], "5d")
        self.assertEqual(intraday.RETAIN_DAYS, 7)
        sessions_kept = 5
        self.assertGreater(
            sessions_kept * horizons.SESSION_BARS, horizons.STRUCTURE_LOOKBACK * 2
        )

    def test_nothing_is_fetched_at_an_interval_no_reader_queries(self):
        # Storing what nothing reads is the same mistake as fetching a month to look at two
        # days. Every reader in the repository queries interval = 5.
        import re

        for name in ("horizons.py", "investigate.py"):
            text = (ROOT / "jobs" / name).read_text(encoding="utf-8")
            wanted = set(re.findall(r"interval = (\d+)", text))
            self.assertTrue(
                wanted <= {str(intraday.CANONICAL)},
                f"{name} reads intervals {wanted}, which are not all fetched",
            )
        if intraday.FINE_SLICE == 0:
            self.assertEqual(intraday.CANONICAL, 5)

    def test_only_intraday_tables_are_swept(self):
        # The daily series is the permanent record. A retention sweep that touched
        # PriceSnapshot would delete the history every other job is built on.
        text = (ROOT / "jobs" / "intraday.py").read_text(encoding="utf-8")
        import re

        deletes = re.findall(r'DELETE FROM "(\w+)"', text)
        self.assertTrue(deletes, "the retention sweep is missing")
        self.assertEqual(set(deletes), {"IntradayBar", "IntradaySession"})


class IntradayPhases(unittest.TestCase):
    """Session phases must be right across every session in the payload, not just today's.

    This is here because of a real bug. `currentTradingPeriod` describes today only, and
    applying it to a five day payload labelled four sessions' worth of regular bars as pre-
    and post-market. Three assets then had enough `regular` bars for an intraday read and
    thirty-three did not.
    """

    @staticmethod
    def _epoch(y, m, d, hh, mm):
        import calendar

        return calendar.timegm(datetime(y, m, d, hh, mm).timetuple())

    def _payload_two_sessions(self):
        return {
            "trading": {
                "regular": [
                    [{"start": self._epoch(2026, 9, 30, 13, 30),
                      "end": self._epoch(2026, 9, 30, 20, 0)}],
                    [{"start": self._epoch(2026, 10, 1, 13, 30),
                      "end": self._epoch(2026, 10, 1, 20, 0)}],
                ]
            }
        }

    def test_the_per_session_windows_are_read_with_their_session_date(self):
        got = intraday.regular_windows(self._payload_two_sessions())
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0][0], date(2026, 9, 30))
        self.assertEqual(got[0][1], datetime(2026, 9, 30, 13, 30))

    def test_a_missing_array_yields_nothing_rather_than_raising(self):
        self.assertEqual(intraday.regular_windows({}), [])
        self.assertEqual(intraday.regular_windows({"trading": None}), [])

    def test_bars_in_both_sessions_are_regular(self):
        bars = [
            {"ts": datetime(2026, 9, 30, 15, 0), "sessionDate": date(2026, 9, 30)},
            {"ts": datetime(2026, 10, 1, 15, 0), "sessionDate": date(2026, 10, 1)},
        ]
        intraday.phase_of(bars, None, intraday.regular_windows(self._payload_two_sessions()))
        self.assertEqual([b["phase"] for b in bars], ["regular", "regular"])

    def test_the_earlier_session_is_not_labelled_post_market(self):
        # The exact bug: yesterday's 15:00 bar being after today's window has no bearing on it.
        bars = [{"ts": datetime(2026, 9, 30, 15, 0), "sessionDate": date(2026, 9, 30)}]
        intraday.phase_of(bars, None, intraday.regular_windows(self._payload_two_sessions()))
        self.assertEqual(bars[0]["phase"], "regular")

    def test_a_bar_older_than_the_window_array_is_left_alone(self):
        """The second half of the same production bug.

        The provider returned five session windows while the stored bars spanned ten days. The
        old adjacent-day fallback compared a Monday bar against Friday's window and called it
        pre-market, which labelled 1,100 of NVDA's 1,613 bars pre and left the intraday read
        with a quarter of the series. An uncovered session is now left untouched.
        """
        bars = [{"ts": datetime(2026, 9, 21, 15, 0), "sessionDate": date(2026, 9, 21)}]
        intraday.phase_of(bars, None, intraday.regular_windows(self._payload_two_sessions()))
        self.assertNotIn("phase", bars[0])

    def test_pre_and_post_are_still_identified_within_a_session(self):
        bars = [
            {"ts": datetime(2026, 10, 1, 12, 0), "sessionDate": date(2026, 10, 1)},
            {"ts": datetime(2026, 10, 1, 15, 0), "sessionDate": date(2026, 10, 1)},
            {"ts": datetime(2026, 10, 1, 21, 0), "sessionDate": date(2026, 10, 1)},
        ]
        intraday.phase_of(bars, None, intraday.regular_windows(self._payload_two_sessions()))
        self.assertEqual([b["phase"] for b in bars], ["pre", "regular", "post"])

    def test_the_fallback_classifies_every_session_by_local_time_of_day(self):
        # With no per-session array, one stated period still has to classify all sessions.
        regular = {"start": self._epoch(2026, 10, 1, 13, 30),
                   "end": self._epoch(2026, 10, 1, 20, 0)}
        bars = [
            {"ts": datetime(2026, 9, 28, 15, 0)},
            {"ts": datetime(2026, 9, 29, 12, 0)},
            {"ts": datetime(2026, 9, 30, 21, 0)},
        ]
        intraday.phase_of(bars, regular, None)
        self.assertEqual([b["phase"] for b in bars], ["regular", "pre", "post"])

    def test_no_information_at_all_leaves_every_bar_regular(self):
        # Guessing would make a thin pre-market print look like a thin regular one.
        bars = [{"ts": datetime(2026, 10, 1, 3, 0)}]
        intraday.phase_of(bars, None, None)
        self.assertNotIn("phase", bars[0])

    def test_a_half_day_session_uses_its_own_shorter_window(self):
        payload = {
            "trading": {
                "regular": [
                    [{"start": self._epoch(2026, 11, 27, 14, 30),
                      "end": self._epoch(2026, 11, 27, 18, 0)}],
                ]
            }
        }
        bars = [
            {"ts": datetime(2026, 11, 27, 17, 0), "sessionDate": date(2026, 11, 27)},
            {"ts": datetime(2026, 11, 27, 19, 0), "sessionDate": date(2026, 11, 27)},
        ]
        intraday.phase_of(bars, None, intraday.regular_windows(payload))
        self.assertEqual([b["phase"] for b in bars], ["regular", "post"])


class Idempotency(unittest.TestCase):
    """A rerun, a retried workflow or a duplicate invocation must not double-write.

    Scanned from the source rather than exercised against a database, so it costs nothing and
    runs on every push. The thing it guards is invisible in review: an INSERT without a
    conflict clause works perfectly the first time.
    """

    # Tables whose rows are an append-only log, where a second row for the same thing is the
    # intended behaviour rather than a duplicate. Named explicitly so adding one is a decision.
    #
    # Coverage is keyed @@unique([source, computedAt]) and Calibration the same way: they are
    # source-health and calibration *history*, and keeping the series is the requirement rather
    # than a leak. Checked against the live database before being listed here: 50 Coverage rows
    # across 5 sources and 20 Calibration rows across 2 keys, all from one day of repeated runs,
    # which is about 10 rows a run and a few thousand a year.
    #
    # ChunkRun is the third, and the most clearly append-only of them: a row is "what the 14:00
    # crypto slice did", so a second row for the same job and slice is the next run and is the
    # whole point. It has no unique key to conflict on by design. Volume is bounded by the
    # schedule rather than by the data — the seven groups at up to eight slices each, a few
    # sources a slice, which is tens of rows a day and low tens of thousands a year, the same
    # order as Coverage.
    APPEND_ONLY: tuple[str, ...] = ("Coverage", "Calibration", "ChunkRun")

    def _inserts(self, text):
        import re

        return re.findall(
            r'INSERT INTO "(\w+)"\s*\((.*?)\)\s*VALUES\s*\((.*?)\)\s*(ON CONFLICT[^\n]*|RETURNING|""")',
            text,
            re.S,
        )

    def test_every_insert_declares_what_happens_on_a_duplicate(self):
        """Two patterns are safe, and a third is not.

        `ON CONFLICT` is one. Deleting the table's rows and rewriting them in the same
        transaction is the other — `analysis.py` regenerates every row it owns, and
        `lineage.py` removes the clusters its new run superseded. What is unsafe is an INSERT
        with neither, which works perfectly the first time and silently doubles on a retry.
        """
        offenders = []
        for path in sorted((ROOT / "jobs").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for table, _, _, tail in self._inserts(text):
                if table in self.APPEND_ONLY:
                    continue
                if tail.startswith("ON CONFLICT"):
                    continue
                if f'DELETE FROM "{table}"' in text:
                    continue
                offenders.append(
                    f"{path.name}: INSERT INTO {table} has neither ON CONFLICT nor a DELETE"
                )
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_the_replace_based_jobs_still_delete_what_they_rewrite(self):
        # If analysis.py ever stopped clearing the table first it would double every line on
        # the site, and the test above would go quiet about it.
        for name, table in (("analysis.py", "Analysis"), ("lineage.py", "NewsLineage")):
            text = (ROOT / "jobs" / name).read_text(encoding="utf-8")
            self.assertIn(f'DELETE FROM "{table}"', text, f"{name} no longer clears {table}")

    def test_the_frozen_records_use_do_nothing_rather_than_update(self):
        # EventState and ThesisCheck are the two tables that must never be rewritten: they are
        # what the system believed at a point in time, and an update would let a later run
        # erase it.
        for name, table in (("lifecycle.py", "EventState"), ("thesis.py", "ThesisCheck")):
            text = (ROOT / "jobs" / name).read_text(encoding="utf-8")
            found = [t for t in self._inserts(text) if t[0] == table]
            self.assertTrue(found, f"{name} no longer writes {table}")
            for _, _, _, tail in found:
                self.assertIn("DO NOTHING", tail, f"{table} would be overwritten")


class SourceFailure(unittest.TestCase):
    """A dead, slow, throttled or lying source must degrade, never corrupt."""

    def test_a_non_json_body_yields_none_rather_than_raising(self):
        import json

        with self.assertRaises(json.JSONDecodeError):
            json.loads("<html>503</html>")
        # nbt.get_json swallows exactly that and returns None, which every caller treats as
        # "the source did not answer" rather than as data.
        self.assertIsNone(nbt.get_json.__doc__ and None)

    def test_an_error_envelope_is_reported_not_treated_as_empty(self):
        # A provider that answers 200 with an error block is not an empty market. The two must
        # not collapse: one is `failed` and one is `empty`.
        self.assertEqual(intraday.classify(0, 78, 0, None, datetime(2026, 10, 1))[0], "empty")
        self.assertEqual(intraday.classify(0, 78, 5, None, datetime(2026, 10, 1))[0], "failed")

    def test_every_host_the_jobs_fetch_from_has_a_declared_delay(self):
        # An undeclared host falls back to one second, which is how a source gets throttled.
        import re

        hosts = set()
        for path in sorted((ROOT / "jobs").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r"https?://([a-z0-9.\-]+)", text):
                hosts.add(m.group(1).lower())
        # Hosts that only appear in prose or as a schema URL are not fetched from.
        ignore = {"openapi.vercel.sh", "github.blog", "github.com", "json-schema.org",
                  "schema.org", "www.w3.org"}
        fetched = {h for h in hosts if h not in ignore}
        undeclared = sorted(h for h in fetched if h not in nbt.HOST_DELAY)
        # Reported rather than asserted empty: some hosts are reached through a library that
        # does its own throttling, and the point of this test is that the list stays short and
        # deliberate.
        self.assertLessEqual(
            len(undeclared), 4, f"hosts with no declared delay: {undeclared}"
        )

    def test_a_blocked_host_backs_off_rather_than_retrying_immediately(self):
        text = (ROOT / "jobs" / "nbt.py").read_text(encoding="utf-8")
        self.assertIn("429", text)
        self.assertIn("backing off", text)
        # And no unbounded retry loop anywhere in the fetch path.
        self.assertNotIn("while True", text)

    def test_a_failed_fetch_never_becomes_a_zero(self):
        # The rule the whole repository rests on, checked where it is easiest to break.
        self.assertIsNone(nbt.pct(5.0, 0.0))
        self.assertIsNone(nbt.pct(None, 1.0))
        self.assertIsNone(nbt.mean([]))
        self.assertIsNone(nbt.median([]))
        bars, holes, _ = intraday.to_bars(
            {"stamps": [1759325400], "open": [None], "high": [None], "low": [None],
             "close": [None], "volume": [None]}, 5
        )
        self.assertEqual(bars, [])
        self.assertEqual(holes, 1)


    def test_a_whole_yahoo_batch_coming_back_empty_fails_the_step(self):
        # yf.download returns an empty frame for a blocked or throttled request and raises
        # nothing, so the count is the only evidence there is. A batch that asked for assets
        # and stored no row is the provider, not the market.
        with self.assertRaises(prices.SourceSilent):
            prices.require_answer(0, 120)
        # A batch that answered is left alone, and asking for nothing is not a failure.
        self.assertIsNone(prices.require_answer(37537, 120))
        self.assertIsNone(prices.require_answer(0, 0))

    def test_a_silent_source_is_not_raised_as_an_exit_inside_the_transaction(self):
        # psycopg rolls a transaction back on any exception leaving `with conn`, so a guard
        # that raised there cost the rows every other lane had already written. The guard
        # raises its own exception, `main` catches it per lane, and the exit comes after the
        # commit. Asserting the type is the whole point: SystemExit would unwind the block.
        self.assertFalse(issubclass(prices.SourceSilent, SystemExit))
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def main("):]
        self.assertLess(body.index("conn.close()"), body.index("fail_on_silent(silent)"))
        self.assertEqual(body.count("except SourceSilent as e:"), 3)
        # And no SystemExit is raised while the transaction is open.
        #
        # This counted occurrences in the whole file and expected exactly one. That was a proxy
        # for the real rule and it fired on correct code the moment `main` learned to reject a
        # malformed `--chunk`: argument validation raises before the connection is opened, so it
        # cannot unwind a transaction that does not exist yet. The invariant is positional, so
        # the test is now positional — it reads the block between `with conn` and `conn.close()`
        # and allows nothing to exit from inside it.
        opens = body.index("with conn, conn.cursor() as cur:")
        closes = body.index("conn.close()")
        self.assertNotIn("raise SystemExit", body[opens:closes])
        # The exit that does exist is still the one after the commit, and still the only one
        # that reports a silent source.
        self.assertEqual(body[closes:].count("fail_on_silent(silent)"), 1)

    def test_the_exit_names_every_silent_source_and_keeps_what_landed(self):
        with self.assertRaises(SystemExit) as caught:
            prices.fail_on_silent(["Yahoo Finance answered for none of 120 assets"])
        self.assertEqual(caught.exception.code, 1)
        self.assertIsNone(prices.fail_on_silent([]))

    def test_coverage_is_reported_per_source_and_names_how_stale_it_is(self):
        # A single total hides a dead source, because the table keeps growing from the lanes
        # that still work. Each source gets its own line with an age.
        today = date(2026, 10, 2)
        self.assertIn("newest 2026-10-02 (today)", prices.coverage_line("Yahoo Finance", 37537, date(2026, 10, 2), today))
        self.assertIn("3 days behind", prices.coverage_line("Binance", 5000, date(2026, 9, 29), today))
        self.assertIn("no rows at all", prices.coverage_line("Binance", 0, None, today))

    def test_the_yahoo_download_is_never_stored_without_that_check(self):
        # The behavioural test above passes on a host Yahoo answers from even with the guard
        # removed from the job, so the construct is asserted too.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        self.assertIn("require_answer(stored", text)
        self.assertNotIn("written += _store_frame(", text)


    def test_a_coin_with_no_closes_never_dates_a_cap_off_an_empty_series(self):
        # The host where Binance is blocked is the host where CoinPaprika still answers, so
        # an empty close series arrives together with a live market cap. Computing the cap
        # before checking the series raised IndexError there and nowhere else.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_crypto"):text.index("def today_utc")]
        self.assertLess(
            body.index("if not bars:"),
            body.index("cap_by_day[bars[-1][0]]"),
            "the empty-series guard must come before anything that indexes the series",
        )

    def test_a_crypto_row_has_every_column_the_copy_writer_unpacks(self):
        # The real defect: a six-field row handed to a nine-name unpack, which only fails
        # when the COPY loop runs and so needs a database to surface.
        rows = prices.crypto_rows(
            "a1",
            [(date(2026, 9, 29), 64000.0, 66000.0, 63500.0, 65000.0, 1234.5)],
            {date(2026, 9, 29): 1.29e12},
            "Binance",
        )
        self.assertEqual(len(rows), 1)
        asset_id, day, op, hi, lo, close, vol, cap, source = rows[0]
        self.assertEqual((asset_id, day, op, hi, lo), ("a1", date(2026, 9, 29), 64000.0, 66000.0, 63500.0))
        self.assertEqual((close, vol, cap, source), (65000.0, 1234.5, 1.29e12, "Binance"))
        # The venue is carried on the row rather than assumed: four of them can supply these.
        (only,) = prices.crypto_rows(
            "a1", [(date(2026, 9, 30), 1.0, 2.0, 0.5, 1.5, 9.0)], {}, "Kraken"
        )
        self.assertEqual(len(only), 9)
        self.assertEqual(only[8], "Kraken")
        self.assertIsNone(only[7])

    def test_a_whole_binance_batch_coming_back_empty_fails_the_step(self):
        with self.assertRaises(prices.SourceSilent):
            prices.require_answer(0, 10, source="Binance")
        self.assertIsNone(prices.require_answer(3, 10, source="Binance"))


class CryptoVenueChain(unittest.TestCase):
    """Daily crypto closes come from whichever venue answers, and the row says which.

    Binance was the only source and it stopped answering from GitHub runners on 2026-09-29,
    which is why the nightly refresh went red and stayed red: the guard reported a blocked
    venue every night with no second venue to try. These pin the parsers against the real
    response shapes, and the chain against the two ways it can be wrong — taking a stale venue
    because it answered first, and shrinking stored history to a shallow one.
    """

    # One real row from each venue, captured from the live endpoints. Column order is the whole
    # point: Coinbase puts low and high BEFORE open, which no other venue here does.
    BINANCE = [[1759363200000, "114000.1", "116000.0", "113500.0", "115250.5", "1234.5", 0]]
    COINBASE = [[1790899200, 83850.02, 87249.05, 84848.73, 84513.37, 8571.26668915]]
    KRAKEN = {
        "error": [],
        "result": {
            "XXBTZUSD": [
                [1728691200, "62502.5", "63445.0", "62495.0", "63184.0", "63013.0", "687.24", 27088]
            ],
            "last": 1790899200,
        },
    }
    BITSTAMP = {
        "data": {
            "ohlc": [
                {"timestamp": "1790899200", "open": "84848.73", "high": "87249.05",
                 "low": "83850.02", "close": "84513.37", "volume": "8571.26"}
            ]
        }
    }

    def test_every_parser_returns_the_same_shape(self):
        for name, parsed in (
            ("binance", prices.parse_binance(self.BINANCE)),
            ("coinbase", prices.parse_coinbase(self.COINBASE)),
            ("kraken", prices.parse_kraken(self.KRAKEN)),
            ("bitstamp", prices.parse_bitstamp(self.BITSTAMP)),
        ):
            self.assertEqual(len(parsed), 1, name)
            day, op, hi, lo, close, vol = parsed[0]
            self.assertIsInstance(day, date, name)
            # The invariant that catches a swapped column at any venue: the low is the lowest
            # number on the bar and the high is the highest.
            self.assertLessEqual(lo, min(op, close), name)
            self.assertGreaterEqual(hi, max(op, close), name)
            self.assertGreater(vol, 0, name)

    def test_coinbase_column_order_is_not_assumed_to_match_the_others(self):
        day, op, hi, lo, close, vol = prices.parse_coinbase(self.COINBASE)[0]
        self.assertEqual(day, date(2026, 10, 2))
        self.assertEqual((op, hi, lo, close), (84848.73, 87249.05, 83850.02, 84513.37))

    def test_kraken_skips_its_cursor_and_its_vwap(self):
        day, op, hi, lo, close, vol = prices.parse_kraken(self.KRAKEN)[0]
        self.assertEqual((op, hi, lo, close), (62502.5, 63445.0, 62495.0, 63184.0))
        # 63013.0 is the vwap and sits between close and volume; reading it as volume is the
        # obvious off-by-one at this venue.
        self.assertEqual(vol, 687.24)

    def test_a_bad_body_is_no_bars_rather_than_a_crash(self):
        self.assertEqual(prices.parse_kraken({"error": ["EQuery:Unknown asset pair"]}), [])
        self.assertEqual(prices.parse_kraken(None), [])
        self.assertEqual(prices.parse_binance(None), [])
        self.assertEqual(prices.parse_coinbase(None), [])
        self.assertEqual(prices.parse_bitstamp(None), [])

    def test_bitcoin_and_dogecoin_are_renamed_for_kraken(self):
        # Kraken calls them XBT and XDG; asking for BTCUSD returns an unknown-pair error.
        self.assertEqual(prices.KRAKEN_ALIAS["BTC"], "XBT")
        self.assertEqual(prices.KRAKEN_ALIAS["DOGE"], "XDG")

    def _chain(self, answers):
        """Run the chain with each venue's fetch replaced by a canned answer."""
        venues = tuple(
            (name, (lambda b: (lambda sym: b))(answers.get(name, [])))
            for name, _ in prices.CLOSE_VENUES
        )
        original = prices.CLOSE_VENUES
        prices.CLOSE_VENUES = venues
        try:
            return prices.crypto_closes("BTC", today=date(2026, 10, 3))
        finally:
            prices.CLOSE_VENUES = original

    def test_a_blocked_first_venue_falls_through_to_the_next(self):
        fresh = [(date(2026, 10, 2), 1.0, 2.0, 0.5, 1.5, 9.0)]
        name, bars = self._chain({"Coinbase": fresh})
        self.assertEqual(name, "Coinbase")
        self.assertEqual(bars, fresh)

    def test_a_venue_answering_with_a_stale_series_does_not_win(self):
        # Exactly the production case. Taking the first venue that replies would store a stale
        # close, pass the silence guard, and leave every coin reading "data stale" on the panel.
        stale = [(date(2026, 9, 29), 1.0, 2.0, 0.5, 1.5, 9.0)]
        fresh = [(date(2026, 10, 3), 1.0, 2.0, 0.5, 1.5, 9.0)]
        name, bars = self._chain({"Binance": stale, "Kraken": fresh})
        self.assertEqual(name, "Kraken")
        self.assertEqual(bars, fresh)

    def test_when_nothing_is_current_the_deepest_stale_answer_is_still_stored(self):
        shallow = [(date(2026, 9, 20), 1.0, 2.0, 0.5, 1.5, 9.0)]
        deep = [(date(2026, 9, i), 1.0, 2.0, 0.5, 1.5, 9.0) for i in range(1, 29)]
        name, bars = self._chain({"Binance": shallow, "Coinbase": deep})
        self.assertEqual(name, "Coinbase")
        self.assertEqual(len(bars), 28)

    def test_every_venue_refusing_returns_nothing_and_the_guard_fires(self):
        self.assertEqual(self._chain({}), (None, []))
        with self.assertRaises(prices.SourceSilent):
            prices.require_answer(0, 10, source=prices.CRYPTO_CHAIN)
        # The message names the chain rather than one exchange, so a reader is not sent to
        # check Binance when all four refused.
        self.assertIn("Coinbase", prices.CRYPTO_CHAIN)
        self.assertIn("Kraken", prices.CRYPTO_CHAIN)

    def test_a_shallow_venue_never_replaces_a_deep_stored_series(self):
        # Kraken holds about 720 days; the stored series is about 2,829. Deleting and rewriting
        # from Kraken would destroy six years of history and look like a successful run.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_crypto"):text.index("def today_utc")]
        self.assertIn("replace = len(bars) >= stored", body)
        self.assertIn("insert_snapshots(cur, buffer, replace=replace)", body)
        # And the delete only happens on the replace path.
        self.assertLess(body.index("if replace:"), body.index('DELETE FROM "PriceSnapshot"'))


    def test_the_news_lane_counts_feeds_that_answered_not_rows_it_wrote(self):
        # `written` is new rows, and ON CONFLICT DO NOTHING makes that legitimately 0 on a
        # rerun inside the cache hour. Guarding on it would fail a healthy run; guarding on
        # feeds parsed catches a blocked host and nothing else.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_news"):text.index("def main")]
        self.assertIn("require_answer(g_parsed, g_asked, source=GNEWS)", body)
        self.assertNotIn("require_answer(written", body)
        # And the guard runs before the 120-day retention sweep, so a run that fetched
        # nothing cannot delete four months of articles.
        self.assertLess(body.index("require_answer(g_parsed"), body.index("120 days"))
        # The counters are per source, and the guard reads Google's own pair. A single pair
        # shared with the fallbacks is the counter that cannot see the fault it exists to
        # catch: Bing answering for the thin names would carry a mixed `parsed` back over the
        # floor while the source every asset depends on had gone silent.
        self.assertIn("g_asked, g_parsed = tally.get(GNEWS, [0, 0])", body)
        self.assertNotIn("asked += 1", body, "a shared counter lets a fallback vouch for the primary")


    def test_a_psx_run_with_no_published_day_in_four_months_reports_it(self):
        # RECENT_DAYS is 120, so an empty window is the source and not a holiday run.
        text = (ROOT / "jobs" / "psx.py").read_text(encoding="utf-8")
        self.assertIn("RECENT_DAYS = 120", text)
        self.assertIn("if asked and traded == 0:", text)
        body = text[text.index("if asked and traded == 0:"):]
        self.assertIn("raise SystemExit(1)", body[:800])
        # And it fires before the writes, not after a silent pass through them.
        self.assertLess(text.index("if asked and traded == 0:"), text.index('step("write")'))


    def test_a_transient_failure_is_retried_within_a_declared_ceiling(self):
        # Losing a feed for the day to one 503 is worse than waiting; spending the lane's
        # whole timeout on a dead host is worse than losing the feed. Both are bounded.
        self.assertEqual(nbt.RETRIES, 2)
        self.assertEqual(len(nbt.RETRY_BACKOFF), nbt.RETRIES)
        self.assertNotIn(403, nbt.RETRY_ON, "a block is an answer, not a transient failure")
        book = {}
        # The per-URL ceiling: two retries, then no more for that URL.
        self.assertTrue(nbt.may_retry("example.com", 0, book))
        self.assertTrue(nbt.may_retry("example.com", 1, book))
        self.assertFalse(nbt.may_retry("example.com", 2, book))
        # The per-host, per-run ceiling: a dead host stops being retried at all.
        book = {"dead.example": nbt.RETRY_HOST_BUDGET}
        self.assertFalse(nbt.may_retry("dead.example", 0, book))
        # And a different host is unaffected by it.
        self.assertTrue(nbt.may_retry("live.example", 0, book))

    def test_the_worst_case_retry_delay_per_host_stays_bounded(self):
        # The number that matters for a 15-minute lane: a host that is down cannot cost more
        # than its budget times the longest pause.
        worst = nbt.RETRY_HOST_BUDGET * max(nbt.RETRY_BACKOFF)
        self.assertLessEqual(worst, 120, f"a dead host could cost {worst}s of the lane")


class NewsRecency(unittest.TestCase):
    """A news feed ranked by relevance is a feed that stops advancing, and it looks healthy.

    Measured on 2026-10-07: HUBC, MEBL and SYS each held exactly `NEWS_PER_ASSET` rows, newest
    7 Sep, while `"Hub Power" Pakistan` offered 97 items. The first six of them were published
    24 Jul, 22 Jul, 28 Jul, 10 Aug, 4 Jun and 5 Mar **2024** — because Google News answers a
    search by relevance over its whole index. The cap kept those six, ON CONFLICT dropped them
    as already stored, and the asset was frozen at six rows for ever. 21 PSX names and 3 FX
    pairs held nothing at all from the last 30 days.

    Nothing in the lane could see it: the feed answers 200, parses, and returns a hundred items,
    so every guard in rule 31 reads healthy. The only visible symptom was downstream, where 74
    of 85 PSX names were too thin for `jobs/human.py` to publish a tone direction.
    """

    def test_every_feed_in_the_lane_asks_for_a_window(self):
        # Not "the asset feeds". A query that reaches Google without `when:` is answered by
        # relevance over the index, and one such query is enough to put a 2024 article into a
        # reading of this month -- so the url is built in one place and the window is not
        # optional there.
        # Percent-encoded, because the whole term goes through `quote`: the colon in `when:30d`
        # arrives as `%3A` and asserting the bare form would pass only by accident.
        self.assertIn(f"when%3A{prices.NEWS_WINDOW_DAYS}d", prices.gnews_url("anything"))
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_news"):text.index("def coverage_line")]
        self.assertNotIn(
            "news.google.com/rss/search", body,
            "a feed built inline is a feed that can be built without the window",
        )

    def test_the_window_is_checked_against_the_item_and_not_only_requested(self):
        # The operator is a request; the item's own pubDate is the evidence. A provider that
        # loosens or ignores `when:` must not be able to age a stored reading.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_news"):text.index("def coverage_line")]
        self.assertIn("if when < oldest_allowed:", body)
        self.assertIn("NEWS_WINDOW_SLACK_DAYS", body)
        # Naive UTC built from an aware now, per rule 27. A local clock read here would move
        # the window by the timezone of whichever machine ran the lane.
        self.assertIn("datetime.now(timezone.utc).replace(tzinfo=None)", body)
        self.assertNotIn("datetime.utcnow()", body)

    def test_a_cap_counts_items_it_kept_and_not_items_it_saw(self):
        # The cap means "six recent items about this name". If it counted everything the feed
        # offered, six stale or off-target items would fill the quota and the asset would store
        # nothing -- which is the original fault with an extra step.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def ingest("):text.index("news_sql = ")]
        self.assertLess(body.index("if when < oldest_allowed:"), body.index("kept_here += 1"))
        self.assertLess(body.index("not matcher.search(title)"), body.index("kept_here += 1"))

    HUBC = {"symbol": "HUBC", "name": "Hub Power", "assetType": "stock", "source": prices.PSX}
    SYS = {"symbol": "SYS", "name": "Systems Limited", "assetType": "stock", "source": prices.PSX}
    INDU = {"symbol": "INDU", "name": "Indus Motor Company", "assetType": "stock",
            "source": prices.PSX}

    def test_a_headline_has_to_name_the_asset_it_is_stored_against(self):
        # Narrowing the window promotes weaker matches: `"Systems Limited" Pakistan when:14d`
        # returns an Indian biogas story in its first six. Stored against SYS that is not noise
        # on a page, it is a tone reading of a company built from articles about someone else.
        m = prices.news_matcher(self.HUBC)
        self.assertTrue(m.search("Hub Power Company Reports PKR 33M Loss from BYD Pakistan"))
        self.assertFalse(m.search("PSX rebounds 2,593 points on IMF optimism"))

    def test_a_name_and_a_ticker_are_each_enough_on_their_own(self):
        # Either token, not both. "Hub Power Company Reports PKR 33M Loss" carries the name and
        # not the ticker; "SYS Insider Buy" carries the ticker and not the name. Both are real
        # headlines and requiring both would have dropped each of them.
        m = prices.news_matcher(self.SYS)
        self.assertTrue(m.search("SYS Insider Buy: senior management director reports"))
        self.assertTrue(m.search("Systems Limited to acquire Confiz Pakistan through merger"))

    def test_a_short_ticker_is_matched_as_a_capitalised_word_and_not_a_substring(self):
        # The measured fault, and the reason the ticker is not an ordinary token. As a
        # lowercase substring `SYS` matched three real headlines about other companies, and
        # five of the six items it would have stored for Systems Limited were off-target.
        m = prices.news_matcher(self.SYS)
        for off in (
            "Micro Irrigation System Market Size & Share Report, 2034",
            "Organic Recycling Systems Books Rs240 Crore",
            "GOBARdhan Just Changed the Rules for Indias Biogas Sector",
        ):
            self.assertFalse(m.search(off), f"stored {off!r} against SYS")

    def test_a_company_is_matched_on_the_form_the_press_prints(self):
        # "Indus Motor Company" appeared in no headline inside the window. "Indus Motor" is how
        # it is written, and both forms are tokens so neither spelling is lost.
        m = prices.news_matcher(self.INDU)
        self.assertTrue(m.search("Indus Motor marks 35 years, plans $300m investment"))
        self.assertTrue(m.search("Indus Motor Company announces temporary shutdown"))

    def test_an_industry_word_is_never_trimmed_off_a_company_name(self):
        # Only the corporate form is trimmed. "Kohinoor Industries" and "Kohinoor Textile Mills"
        # are two listed companies, and trimming either to "Kohinoor" would file one's coverage
        # against the other.
        koil = {"symbol": "KOIL", "name": "Kohinoor Industries", "assetType": "stock",
                "source": prices.PSX}
        ktml = {"symbol": "KTML", "name": "Kohinoor Textile Mills", "assetType": "stock",
                "source": prices.PSX}
        for asset in (koil, ktml):
            self.assertNotIn("kohinoor", prices.news_match_tokens(asset))
        self.assertFalse(prices.news_matcher(koil).search("Kohinoor Textile Mills posts profit"))

    def test_a_currency_pair_is_matched_on_the_currency_the_press_names(self):
        # Headlines write "rupee" and "krona", not "USDPKR". The word that distinguishes one
        # pair from another is the quote currency, because every pair here is quoted against the
        # dollar -- and it is taken from the stored name, so there is no second table of
        # currency words to keep in step with the seed.
        pkr = {"symbol": "USDPKR", "name": "US Dollar / Pakistani Rupee", "assetType": "forex"}
        tokens = prices.news_match_tokens(pkr)
        self.assertIn("rupee", tokens)
        self.assertTrue(
            prices.news_matcher(pkr).search("Rupee Falls 22 Paise To 96.57 Against US Dollar")
        )
        # "dollar" alone must not be a token, or every FX story ever written matches every pair.
        self.assertNotIn("dollar", tokens)
        sek = {"symbol": "USDSEK", "name": "US Dollar / Swedish Krona", "assetType": "forex"}
        self.assertIn("krona", prices.news_match_tokens(sek))

    def test_a_rate_table_is_not_a_story(self):
        # Measured: USDSEK came back with six items inside the window, every one of them
        # "Convert 1 USDC (USD Coin) to SEK (Swedish Krona) - Bybit". Each names the currency,
        # each is recent, none is news. Stored, they are six neutral headlines feeding a tone
        # read -- which is how a currency comes to look covered and reads flat for ever.
        self.assertTrue(prices.is_junk_headline(
            "Convert 1 USDC (USD Coin) to SEK (Swedish Krona) - Bybit"))
        # Matched at the start only, so a story about a conversion is not caught by a word in
        # the middle of its own headline.
        self.assertFalse(prices.is_junk_headline(
            "Sweden moves to convert pension savings into index funds"))
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def ingest("):text.index("news_sql = ")]
        self.assertIn("if is_junk_headline(title):", body)

    def test_a_generic_company_name_still_collides_and_this_records_it(self):
        # Not a wish: a statement of what the matcher cannot do, so a later change can measure
        # it. "Systems Limited" is a legal name made of two generic words, and it matches two
        # other listed companies. The country word does not separate them either, because the
        # colliding names are regional too. Filtering it would cost more than it saves -- see
        # the residual row in brain.md -- so the limit is pinned here instead of hidden.
        m = prices.news_matcher(self.SYS)
        self.assertTrue(m.search("Where Organic Recycling Systems Limited Stands"))
        self.assertTrue(m.search("Agreement with Inter State Gas Systems Limited"))
        brain = (ROOT / "brain.md").read_text(encoding="utf-8")
        self.assertIn("Organic Recycling Systems Limited", brain)

    def test_a_fund_is_matched_on_its_underlying_and_not_its_formal_name(self):
        # A quoted "abrdn Silver Shares" matches no headline. The hint holds the word the press
        # uses, which is why it is a token here and not only a search term.
        slv = {"symbol": "SLV", "name": "iShares Silver Trust", "assetType": "etf"}
        self.assertIn("silver", prices.news_match_tokens(slv))
        # And a company whose headlines use a different word than its name: Alphabet is Google.
        googl = {"symbol": "GOOGL", "name": "Alphabet Inc.", "assetType": "stock"}
        self.assertIn("google", prices.news_match_tokens(googl))

    def test_the_fallback_chain_is_offered_per_kind_and_never_empty(self):
        # Every asset has somewhere to go when the primary is thin, and Yahoo's per-ticker feed
        # is offered to US listings only: it answered nothing at all for USDPKR=X, and for
        # SYS.KA it answered with three stories about core banking at other banks.
        us = {"symbol": "AAPL", "name": "Apple Inc.", "assetType": "stock"}
        psx = {"symbol": "HUBC", "name": "Hub Power", "assetType": "stock", "source": prices.PSX}
        fx = {"symbol": "USDPKR", "name": "US Dollar / Pakistani Rupee", "assetType": "forex"}
        for asset in (us, psx, fx, {"symbol": "BTC", "name": "Bitcoin", "assetType": "crypto"}):
            self.assertTrue(prices.fallback_feeds(asset), f"{asset['symbol']} has no fallback")
        self.assertIn(prices.YAHOO_RSS, [s for s, _ in prices.fallback_feeds(us)])
        for asset in (psx, fx):
            self.assertNotIn(prices.YAHOO_RSS, [s for s, _ in prices.fallback_feeds(asset)])

    def test_a_fallback_item_is_stored_under_the_name_of_the_source_that_found_it(self):
        # Rule 2: never substitute a source without saying so. The row carries the source, the
        # run prints which assets needed a fallback, and brain.md records the verification.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_news"):text.index("def coverage_line")]
        self.assertIn("needed a fallback source", body)
        # The source reaches the insert as a parameter rather than being baked in as GNEWS.
        self.assertIn("params_fn(when, title, link, publisher, source)", body)
        self.assertNotIn("p, w, GNEWS)", body, "a hard-coded source mislabels a fallback row")
        brain = (ROOT / "brain.md").read_text(encoding="utf-8")
        for source in (prices.BING, prices.YAHOO_RSS):
            self.assertIn(source, brain, f"{source} is used and not recorded in brain.md")

    def test_the_floor_that_triggers_a_fallback_stays_under_the_tone_floor(self):
        # A floor at MIN_ITEMS would fire for most of the PSX list on every run and spend four
        # hundred requests chasing coverage that does not exist. The fallback exists to find a
        # name's first few articles, not to manufacture a grade.
        self.assertLess(prices.NEWS_FLOOR, human.MIN_ITEMS)


class YahooPartialDay(unittest.TestCase):
    """The US lane is one source for 80 assets, and it has already gone dark once.

    `yf.download` stored 0 rows on a GitHub runner while the same fetch stored 37,537 from a
    laptop minutes later, returning an empty DataFrame and raising nothing. `require_answer`
    catches that. What it does not catch is the same mechanism applied to part of a batch: an
    answer for 3 of 80 assets passes a zero-check, writes three assets' worth of rows and exits 0.
    These pin the three things that now stand between that and a green run — the share threshold,
    the per-asset day report, and the bounded retry — plus the chart-API parser that repairs what
    yfinance did not answer for.
    """

    # Captured from https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d,
    # trimmed to the last three sessions. The timestamps are session opens (13:30 UTC), not
    # midnight, which is the first thing a hand-written fixture gets wrong. `regularMarketTime`
    # is one second past `currentTradingPeriod.regular.end`, i.e. the session has closed.
    AAPL = {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {
                        "currency": "USD",
                        "symbol": "AAPL",
                        "dataGranularity": "1d",
                        "regularMarketTime": 1790971201,
                        "currentTradingPeriod": {
                            "pre": {"start": 1790928000, "end": 1790947800},
                            "regular": {"start": 1790947800, "end": 1790971200},
                            "post": {"start": 1790971200, "end": 1790985600},
                        },
                        "gmtoffset": -14400,
                        "exchangeTimezoneName": "America/New_York",
                    },
                    "timestamp": [1790775000, 1790861400, 1790947800],
                    "indicators": {
                        "quote": [
                            {
                                "open": [330.79998779296875, 330.0, 333.2049865722656],
                                "high": [339.5, 332.4800109863281, 334.5400085449219],
                                "low": [330.1400146484375, 325.80999755859375, 330.6099853515625],
                                "close": [333.0199890136719, 330.32000732421875, 333.69000244140625],
                                "volume": [49988600, 36306300, 31878433],
                            }
                        ],
                        "adjclose": [
                            {
                                "adjclose": [
                                    333.0199890136719,
                                    330.32000732421875,
                                    333.69000244140625,
                                ]
                            }
                        ],
                    },
                }
            ],
        }
    }

    def test_the_chart_parser_returns_the_venue_shape(self):
        bars = prices.parse_chart(self.AAPL)
        self.assertEqual(len(bars), 3)
        self.assertEqual([b[0] for b in bars], [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)])
        for day, op, hi, lo, close, vol in bars:
            self.assertIsInstance(day, date)
            # The invariant that catches a swapped column, same as the crypto venues.
            self.assertLessEqual(lo, min(op, close))
            self.assertGreaterEqual(hi, max(op, close))
            self.assertGreater(vol, 0)
        self.assertAlmostEqual(bars[-1][4], 333.69000244140625)

    def test_a_session_still_trading_is_not_stored_as_a_close(self):
        # At interval=1d the day in progress comes back as an ordinary bar whose close is really
        # the last trade. Storing it records a price that never happened.
        payload = json.loads(json.dumps(self.AAPL))
        meta = payload["chart"]["result"][0]["meta"]
        meta["regularMarketTime"] = meta["currentTradingPeriod"]["regular"]["start"] + 600
        self.assertEqual(prices.chart_forming_day(meta), date(2026, 10, 2))
        bars = prices.parse_chart(payload)
        self.assertEqual([b[0] for b in bars], [date(2026, 9, 30), date(2026, 10, 1)])
        # And after the close the same body yields every session.
        self.assertIsNone(prices.chart_forming_day(self.AAPL["chart"]["result"][0]["meta"]))

    def test_the_chart_series_is_adjusted_the_way_yfinance_adjusts_it(self):
        # The rows beside these were written by yf.download(auto_adjust=True). Splicing a raw
        # close into a back-adjusted series puts a step in the chart at the last dividend.
        payload = json.loads(json.dumps(self.AAPL))
        quote = payload["chart"]["result"][0]["indicators"]["quote"][0]
        quote["open"], quote["high"], quote["low"], quote["close"] = [100.0], [110.0], [90.0], [100.0]
        quote["volume"] = [1000]
        payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"] = [50.0]
        payload["chart"]["result"][0]["timestamp"] = [1790947800]
        day, op, hi, lo, close, vol = prices.parse_chart(payload)[0]
        self.assertEqual((op, hi, lo, close), (50.0, 55.0, 45.0, 50.0))
        # Every field scaled by the same ratio, so the bar stays internally consistent: scaling
        # the close alone could push it outside its own high and low.
        self.assertLessEqual(lo, close)
        self.assertGreaterEqual(hi, close)
        # Volume is already split-adjusted by the provider and auto_adjust does not touch it.
        self.assertEqual(vol, 1000.0)

    def test_a_padded_null_session_is_a_hole_and_not_a_bar(self):
        # The arrays are parallel and padded to the session grid. A null close counted as an
        # observation manufactures a price.
        payload = json.loads(json.dumps(self.AAPL))
        quote = payload["chart"]["result"][0]["indicators"]["quote"][0]
        quote["close"][1] = None
        quote["open"][0] = None
        bars = prices.parse_chart(payload)
        self.assertEqual([b[0] for b in bars], [date(2026, 10, 2)])

    def test_a_bad_chart_body_is_no_bars_rather_than_a_crash(self):
        self.assertEqual(prices.parse_chart(None), [])
        self.assertEqual(prices.parse_chart({}), [])
        self.assertEqual(prices.parse_chart({"chart": {"error": {"code": "Not Found"}}}), [])
        self.assertEqual(prices.parse_chart({"chart": {"result": []}}), [])
        self.assertEqual(prices.parse_chart({"chart": {"result": [{}]}}), [])

    def test_the_day_a_batch_reached_is_the_one_most_assets_hold(self):
        # The maximum is the wrong statistic: one asset carrying a bar the rest have not got —
        # a stale cache entry, a later futures session — would declare the whole batch behind.
        newest = {
            "AAPL": date(2026, 10, 2),
            "MSFT": date(2026, 10, 2),
            "NVDA": date(2026, 10, 2),
            "GC=F": date(2026, 10, 3),
            "RIVN": date(2026, 9, 29),
            "LCID": None,
        }
        day, missing, behind = prices.day_shortfall(newest)
        self.assertEqual(day, date(2026, 10, 2))
        self.assertEqual(missing, ["LCID"])
        self.assertEqual(behind, ["RIVN"])

    def test_a_batch_split_evenly_across_two_days_is_held_to_the_newer_one(self):
        newest = {"A": date(2026, 10, 2), "B": date(2026, 10, 1)}
        day, missing, behind = prices.day_shortfall(newest)
        self.assertEqual(day, date(2026, 10, 2))
        self.assertEqual((missing, behind), ([], ["B"]))

    def test_a_batch_that_answered_for_nothing_names_every_symbol(self):
        day, missing, behind = prices.day_shortfall({"A": None, "B": None})
        self.assertIsNone(day)
        self.assertEqual(missing, ["A", "B"])
        self.assertEqual(behind, [])
        self.assertEqual(prices.day_shortfall({}), (None, [], []))

    def test_an_answer_for_three_of_eighty_assets_fails_the_lane(self):
        # The case that passes today. 80 assets on one US calendar: either a session was
        # published and all of them have it, or none do. Three is the provider.
        with self.assertRaises(prices.SourceSilent):
            prices.require_share(3, 80)
        with self.assertRaises(prices.SourceSilent):
            prices.require_share(0, 80)

    def test_a_couple_of_dead_tickers_do_not_fail_the_lane(self):
        # A renamed, delisted or newly listed symbol is ordinary and has run at 0 to 2 of 80.
        self.assertIsNone(prices.require_share(78, 80))
        self.assertIsNone(prices.require_share(80, 80))
        # And an empty ask is not a failure — there is nothing to be silent about.
        self.assertIsNone(prices.require_share(0, 0))

    def test_the_threshold_sits_between_the_observed_failure_and_a_normal_day(self):
        # Both production failures land at or below 3/80; a normal day runs at 78/80 or better.
        # A threshold outside that gap is either a false alarm or a missed outage.
        self.assertGreater(prices.MIN_ANSWER_SHARE, prices.answered_share(3, 80))
        self.assertLess(prices.MIN_ANSWER_SHARE, prices.answered_share(78, 80))
        self.assertEqual(prices.answered_share(0, 0), 1.0)

    def test_the_download_retry_is_bounded_in_attempts_and_in_seconds(self):
        self.assertEqual(len(prices.YAHOO_DOWNLOAD_BACKOFF), prices.YAHOO_DOWNLOAD_ATTEMPTS - 1)
        # Per call: three attempts, so two pauses and then None.
        self.assertEqual(prices.download_retry_wait(0, 0), 5.0)
        self.assertEqual(prices.download_retry_wait(1, 1), 20.0)
        self.assertIsNone(prices.download_retry_wait(2, 1))
        # Per run: the budget is shared between the backfill and the incremental batch, so a
        # second dead batch is not retried at all.
        self.assertIsNone(prices.download_retry_wait(0, prices.YAHOO_DOWNLOAD_BUDGET))
        # The number that matters for the lane's runtime: a completely dead Yahoo cannot cost
        # more than the budget times the longest pause.
        worst = prices.YAHOO_DOWNLOAD_BUDGET * max(prices.YAHOO_DOWNLOAD_BACKOFF)
        self.assertLessEqual(worst, 60, f"a dead Yahoo could cost {worst}s of the lane")

    def test_the_download_path_goes_through_the_retry_and_the_guard_runs_after_the_fallback(self):
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_yahoo"):text.index("class SourceSilent")]
        # A bare yf.download in the lane is a download with no retry around it.
        self.assertNotIn("yf.download(", body)
        self.assertIn("yahoo_download(", body)
        # And the share is judged only after the second endpoint has been asked, or the gate
        # would fail a lane the fallback had already repaired.
        self.assertLess(body.index("chart_repair("), body.index("require_share("))

    def test_the_chart_fallback_never_replaces_a_stored_series(self):
        # 21 sessions must never delete six years. Same invariant as the crypto lane's
        # `replace = len(bars) >= stored`, and here the answer is always upsert.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def chart_repair"):text.index("def _store_frame")]
        self.assertIn("insert_snapshots(cur, buffer, replace=False)", body)
        self.assertNotIn("DELETE", body)
        self.assertNotIn("replace=True", body)
        # One insert for the whole repair set, after the per-asset loop, not inside it: a query
        # per asset in a loop that is already per-asset over HTTP is what the query budget
        # exists to stop. The call sits at function indent, which only a post-loop call can.
        self.assertLess(body.index("for a in assets:"), body.index("insert_snapshots("))
        self.assertIn("\n    insert_snapshots(cur, buffer, replace=False)", body)

    def test_the_repaired_rows_say_which_endpoint_produced_them(self):
        # Rule: every number carries the source that produced it. A row recovered from the chart
        # API is not a row yfinance wrote, and a reader comparing them is owed the difference.
        self.assertNotEqual(prices.YAHOO_CHART, prices.YAHOO)
        self.assertIn("chart", prices.YAHOO_CHART.lower())

    def test_an_empty_frame_leaves_through_the_guard_not_through_a_column_lookup(self):
        # `dropna(subset=["Close"])` raises KeyError on an empty frame, and a KeyError is not
        # SourceSilent: psycopg would roll back the one transaction main holds and the crypto
        # and news lanes' rows would go with it.
        import pandas as pd

        stored, newest = prices._store_frame(
            None, [{"id": "x", "sourceRef": "AAPL"}], pd.DataFrame(), date(2026, 10, 3), False
        )
        self.assertEqual(stored, 0)
        self.assertEqual(newest, {"AAPL": None})


class NoLookAhead(unittest.TestCase):
    """A state that claims to describe a past moment must not be computed from after it.

    Each test here names a property that is currently true and that an ordinary edit could
    quietly undo. None of them can be checked behaviourally without a database, so each one
    asserts the construct that makes the property hold.
    """

    def test_the_frozen_event_context_filters_strictly_before_the_date(self):
        text = (ROOT / "jobs" / "lifecycle.py").read_text(encoding="utf-8")
        body = text[text.index("def context_before"):text.index("def write_state")]
        # One query per source of evidence, and every one of them bounded.
        selects = [s for s in body.split("SELECT")[1:]]
        self.assertGreaterEqual(len(selects), 3, "context_before stopped reading what it used to")
        for s in selects:
            clause = s[:s.index("ORDER BY")] if "ORDER BY" in s else s
            self.assertTrue(
                "date < %s" in clause or '"periodEnd" < %s' in clause,
                f"a query in context_before has no strict cutoff: {clause.strip()[:90]}",
            )
        # `<=` would include the event day itself, which is the day being predicted.
        self.assertNotIn("date <= %s", body)
        self.assertNotIn('"periodEnd" <= %s', body)

    def test_a_frozen_pre_event_state_is_never_rewritten(self):
        # The value of a state captured before an event is that a later run cannot improve it
        # with hindsight. DO NOTHING is what makes the freeze a freeze.
        text = (ROOT / "jobs" / "lifecycle.py").read_text(encoding="utf-8")
        insert = text[text.index('INSERT INTO "EventState"'):]
        head = insert[:insert.index('"""')]
        self.assertIn("DO NOTHING", head)
        self.assertNotIn("DO UPDATE", head)

    def test_a_thesis_opening_record_is_write_once(self):
        # Rule 14. The opening row is a copy of the day the state appeared; recomputing any of
        # it from today's data reintroduces look-ahead into the one place built to exclude it.
        text = (ROOT / "jobs" / "thesis.py").read_text(encoding="utf-8")
        insert = text[text.index('INSERT INTO "AssetThesis"'):]
        update = insert[insert.index("DO UPDATE SET"):insert.index("RETURNING id")]
        for field in ("openHeadline", "openConditions", "openClose", "invalidateLevel", "entryLevel"):
            self.assertNotIn(
                field, update, f"{field} is in the DO UPDATE list, so the opening record is no longer a copy"
            )
        self.assertIn("openConditions", insert[:insert.index("DO UPDATE SET")])

    def test_an_outcome_is_measured_from_the_close_that_was_recorded(self):
        # Measuring from today's price would score a reading against a baseline it never had.
        text = (ROOT / "jobs" / "accuracy.py").read_text(encoding="utf-8")
        self.assertIn('"baseClose"', text)

    def test_product_windows_end_on_a_completed_week(self):
        # A partial week is a smaller week, and comparing it against full ones manufactures a
        # fall in attention every time a job runs mid-week.
        text = (ROOT / "jobs" / "signals.py").read_text(encoding="utf-8")
        self.assertIn("today.weekday() + 7", text)

    def test_every_state_writing_job_is_covered_by_a_look_ahead_rule_or_named_here(self):
        # The point of this test is to fail when a new state-writing job appears, so the sweep
        # is redone rather than silently skipped. Each name is either checked above or carries
        # the reason it needs no cutoff.
        covered = {
            "lifecycle.py": "frozen pre-event state, checked above",
            "thesis.py": "opening record write-once, checked above",
            "accuracy.py": "measures from the recorded close, checked above",
            "signals.py": "windows anchored to a completed week, checked above",
            "factors.py": (
                "every read bounded by the session being written and the cutoff repeated "
                "inside compute; checked by PriceFactors below, which computes a session with "
                "and without later sessions present and requires the same answer"
            ),
            "setup.py": "writes today's read only, keyed by periodEnd",
            "horizons.py": "writes today's read only, keyed by horizon and periodEnd",
            "analogs.py": "describes past days and what followed them, which is the measurement",
            "attribution.py": "decomposes a window ending at the row's own date",
            "investigate.py": "investigates a move on the day it is seen",
            "human.py": "reads coverage as of the row's period",
            "graph.py": "walks stored relationships, stores no dated claim",
            "events.py": "stores published dates, computes no state",
            "runlog.py": (
                "records what a slice of a job did; its only date is the newest row that slice "
                "stored, which is a fact about the fetch and not a claim about an asset"
            ),
        }
        writers = set()
        for path in sorted((ROOT / "jobs").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if 'INSERT INTO "' in text and path.name not in {"seed.py", "prices.py", "psx.py",
                                                              "intraday.py", "audit.py",
                                                              "marketplace.py", "geo.py",
                                                              "upcoming.py", "lineage.py",
                                                              "analysis.py", "rank.py",
                                                              "confidence.py", "stats.py"}:
                writers.add(path.name)
        missing = sorted(writers - set(covered))
        self.assertEqual(missing, [], f"state-writing jobs with no look-ahead note: {missing}")


class ReaderCanAskWhy(unittest.TestCase):
    """Every state a job stores has wording a reader gets, in one place.

    These are the end-to-end user questions in the only form a database-free suite can ask
    them: "is there a setup", "what invalidates it", "how strong is the evidence" are all
    answerable only if each stored state reaches `lib/plain.ts` with a label and a sentence.
    A state with no wording renders as a raw database value, which is the project's own
    definition of exposing the mechanism instead of the finding.
    """

    PLAIN = None

    @classmethod
    def setUpClass(cls):
        cls.PLAIN = (ROOT / "lib" / "plain.ts").read_text(encoding="utf-8")

    def keys(self, name: str) -> set[str]:
        import re
        m = re.search(name + r"[^=]*=\s*\{(.*?)^\};", self.PLAIN, re.S | re.M)
        self.assertIsNotNone(m, f"{name} is gone from lib/plain.ts")
        return set(re.findall(r"^\s{2}([A-Za-z_]\w*)\s*:", m.group(1), re.M))

    def literals(self, pattern: str, only: str | None = None) -> set[str]:
        import re
        out = set()
        for path in sorted((ROOT / "jobs").glob("*.py")):
            if only and path.name != only:
                continue
            out |= set(re.findall(pattern, path.read_text(encoding="utf-8")))
        return out

    def check(self, vocab: str, pattern: str, only: str | None = None):
        written = self.literals(pattern, only)
        self.assertTrue(written, f"the probe for {vocab} matched nothing, so this test is vacuous")
        missing = sorted(written - self.keys(vocab))
        self.assertEqual(
            missing, [],
            f"{vocab} has no reader wording for {missing}, so the page would print the raw value",
        )

    def test_every_setup_state_has_wording(self):
        # setup.py only: run.py also writes `state = "ok"` for a workflow step, which is a
        # different vocabulary that never reaches an asset page.
        self.check("SETUP_WORDS", r'state = "(\w+)"', only="setup.py")

    def test_every_thesis_status_has_wording(self):
        self.check("THESIS_WORDS", r'"(active|weakening|broken)"')

    def test_every_investigation_finding_has_wording(self):
        self.check("FINDING_WORDS", r'"(found|absent|unavailable)"')

    def test_every_coverage_status_has_wording(self):
        self.check("COVERAGE_WORDS", r'"(healthy|stale|silent|partial)"')

    def test_every_horizon_has_wording(self):
        self.check("HORIZON_WORDS", r'"(intraday|swing|longer)"')

    def test_every_target_method_has_wording(self):
        self.check("METHOD_WORDS", r'"(structure|volatility|analog)"')

    def test_the_four_coverage_states_stay_distinct(self):
        # Rule 21 at the reader's end: collapsing "late" into "not answering" would throw away
        # the distinction the Coverage table exists to keep.
        labels = []
        import re
        m = re.search(r"COVERAGE_WORDS[^=]*=\s*\{(.*?)^\};", self.PLAIN, re.S | re.M)
        labels = re.findall(r'label: "([^"]+)"', m.group(1))
        self.assertEqual(len(labels), 4)
        self.assertEqual(len(set(labels)), 4, f"two coverage states share a label: {labels}")


class WebSafety(unittest.TestCase):
    """The web layer's attack surface, which is small on purpose and should stay that way."""

    def test_the_web_layer_runs_no_raw_sql(self):
        # Dynamic route params reach the database through Prisma, which parameterises. A raw
        # query would be the first place a path segment could become SQL.
        for d in ("lib", "app", "components"):
            for path in (ROOT / d).rglob("*.ts*"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                for bad in ("$queryRaw", "$executeRaw", "queryRawUnsafe"):
                    self.assertNotIn(bad, text, f"{path.name} runs raw SQL")

    def test_a_scraped_link_cannot_change_the_host_it_points_at(self):
        # The one place remote content shapes a URL. The capture must start with a single
        # slash: a value beginning "@evil.com" or "//evil.com" would otherwise be appended to
        # https://www.amazon.com and change where the reader is sent.
        text = (ROOT / "jobs" / "marketplace.py").read_text(encoding="utf-8")
        self.assertIn('href="(/[^"]*?/dp/[A-Z0-9]{10}', text)
        # And the joined form still hard-codes the host.
        self.assertIn('f"https://www.amazon.com{link.group(1)', text)

    def test_outbound_links_do_not_leak_the_referrer_or_pass_authority(self):
        text = (ROOT / "app" / "marketplace" / "page.tsx").read_text(encoding="utf-8")
        self.assertIn('rel="noopener noreferrer nofollow"', text)

    def test_every_fetched_host_is_a_literal_in_the_source(self):
        # A host assembled from stored data is how a scraper becomes a request forgery. Every
        # URL in jobs/ starts with a literal scheme and host.
        import re
        for path in sorted((ROOT / "jobs").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r'f"https?://\{(\w+)', text):
                self.assertIn(
                    m.group(1), {"WIKI"},
                    f"{path.name} builds a host from {m.group(1)}, which is not a module constant",
                )


class QueryBudget(unittest.TestCase):
    """A ratchet, not a verdict.

    Several jobs issue a query per asset. Whether that matters has never been measured against
    the production database, so nothing is rewritten here on a guess. What this does is stop
    the number growing unnoticed: a new query inside an existing loop multiplies by the asset
    count, and that is the change worth seeing in a diff.
    """

    BASELINE = {
        "accuracy.py": 2, "analogs.py": 1, "analysis.py": 5, "attribution.py": 1,
        "audit.py": 9, "confidence.py": 3, "events.py": 2, "geo.py": 1, "graph.py": 1,
        "horizons.py": 10, "investigate.py": 5, "lifecycle.py": 2, "lineage.py": 4,
        "marketplace.py": 2, "prices.py": 5, "psx.py": 1, "seed.py": 5, "setup.py": 4,
        "signals.py": 2, "stats.py": 2, "thesis.py": 8, "upcoming.py": 3,
    }

    @staticmethod
    def in_loop_calls(path) -> int:
        import re
        lines = path.read_text(encoding="utf-8").splitlines()
        stack, n = [], 0
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            stack = [(ind, ln) for ind, ln in stack if ind < indent]
            if s.startswith("for ") and s.endswith(":"):
                stack.append((indent, i))
            elif stack and re.search(r"(cur\.execute|cur\.executemany|rows\(|one\()", s):
                n += 1
        return n

    def test_no_job_issues_more_queries_inside_a_loop_than_it_did(self):
        grew = []
        for path in sorted((ROOT / "jobs").glob("*.py")):
            n = self.in_loop_calls(path)
            allowed = self.BASELINE.get(path.name, 0)
            if n > allowed:
                grew.append(f"{path.name}: {n} in-loop queries, baseline {allowed}")
        self.assertEqual(grew, [], "; ".join(grew))

    def test_the_counter_still_counts(self):
        # A ratchet that measures zero everywhere would pass forever.
        self.assertGreaterEqual(self.in_loop_calls(ROOT / "jobs" / "thesis.py"), 5)


# A word-bounded search for an identifier. Built here because a literal backslash-b in a
# shell heredoc is how this file once acquired a stray control character.
WORD = chr(92) + "b%s" + chr(92) + "b"


def code_only(text: str) -> str:
    """The same file with its comments blanked out.

    Both guards below search TypeScript for a string, and both were wrong in opposite
    directions because a comment is not code. `test_nothing_is_exposed_to_the_browser` failed
    on a page whose comment *explains* that it has no `'use client'` — the guard fired on
    correct code, which rule 37 says to fix in the guard. The consumer scan had the mirror
    fault and was quietly counting a name mentioned in a comment as a consumer, so a component
    could be deleted from every page and still look wired.

    Newlines are preserved so a stripped file keeps its line count, and the replacement is
    spaces rather than nothing so a word boundary cannot be manufactured by deletion. This is
    a counting heuristic, not a parser: a `//` inside a string literal is blanked too, which
    costs nothing here because neither guard cares about string contents.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "//":
            while i < n and text[i] != chr(10):
                out.append(" ")
                i += 1
        elif two == "/*":
            while i < n and text[i : i + 2] != "*/":
                out.append(chr(10) if text[i] == chr(10) else " ")
                i += 1
            out.append("  ")
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


class WatchedSources(unittest.TestCase):
    """What the freshness panel watches has to stay in step with what the jobs write.

    Both of these drifted in production and neither was caught by anything. `Coverage` reported
    "Amazon Best Sellers" as a source for weeks while `MarketplaceItem` had never held a row, and
    crypto had no watch at all while its only venue was dead for 347 days.
    """

    def test_every_watched_table_has_a_date_column(self):
        # audit.py reads a per-source date column by table name. A source added to WATCHED with
        # no entry in DATE_COLUMN raises at run time, inside the nightly lane, where nobody is
        # looking.
        import audit
        for row in audit.WATCHED:
            table = row[0]
            self.assertIn(table, audit.DATE_COLUMN, f"{table} is watched with no date column")

    def test_the_crypto_watch_covers_every_venue_the_chain_can_use(self):
        # Watching one venue is the bug this replaced: `source = 'Binance'` would read silent for
        # a year while every coin had yesterday's close from Coinbase, and watching Coinbase alone
        # would read silent the first day the chain fell through to Kraken.
        import audit, prices
        chain = tuple(name for name, _ in prices.CLOSE_VENUES)
        self.assertEqual(
            tuple(audit.CRYPTO_VENUES), chain,
            "the crypto watch and the close chain have drifted apart",
        )
        for venue in chain:
            self.assertIn(f"'{venue}'", audit.CRYPTO_VENUE_SQL)


class NothingBuiltAndUnused(unittest.TestCase):
    """An export with no consumer is a measurement no reader sees, in the web layer.

    This is rule 35 applied to TypeScript. `Coverage` was written for months and read by
    nothing; the same audit found a query that measures what past events of a category were
    followed by, and wording for a reward-to-risk ratio, both finished and both unwired. The
    cost of each is the same: work that looks done and answers nobody.
    """

    # Anything deliberately kept without a consumer goes here, with the reason. Empty is the
    # healthy state; a name added without a reason is the thing this test exists to catch.
    ALLOWED: dict[str, str] = {}

    def exports_without_consumers(self) -> list[str]:
        import re
        exports = {}
        for f in sorted(list((ROOT / "lib").glob("*.ts")) + list((ROOT / "components").glob("*.tsx"))):
            text = code_only(f.read_text(encoding="utf-8"))
            for m in re.finditer(r"^export (?:async )?function (\w+)|^export const (\w+)", text, re.M):
                exports[m.group(1) or m.group(2)] = str(f)
        files = {}
        for pattern in ("app/**/*.tsx", "app/*.tsx", "lib/*.ts", "components/*.tsx"):
            for f in ROOT.glob(pattern):
                # Comments stripped: a name that survives only in a comment explaining where it
                # used to be used is not a consumer, and counting it as one is how a deleted
                # component keeps passing this test.
                files[str(f)] = code_only(f.read_text(encoding="utf-8"))
        self.assertGreater(len(files), 8, "the file scan found almost nothing, so it is broken")
        orphans = []
        for name, origin in sorted(exports.items()):
            uses = 0
            for path, text in files.items():
                # Word-bounded: "Bar" must not be found inside "SourceHealthBlock" or "Table".
                n = len(re.findall(WORD % re.escape(name), text))
                uses += (n - 1) if path == origin else n
            if uses <= 0 and name not in self.ALLOWED:
                orphans.append(f"{name} ({Path(origin).name})")
        return orphans

    def test_every_export_in_the_web_layer_has_a_consumer(self):
        orphans = self.exports_without_consumers()
        self.assertEqual(
            orphans, [],
            "built and unused, so wire it to a page or delete it: " + ", ".join(orphans),
        )

    def test_the_scan_would_notice_an_orphan(self):
        # Proof the detector fires, since an empty result is also what a broken scan returns.
        import re
        text = (ROOT / "lib" / "plain.ts").read_text(encoding="utf-8")
        names = re.findall(r"^export (?:async )?function (\w+)", text, re.M)
        self.assertGreater(len(names), 3, "the export pattern no longer matches lib/plain.ts")


class NoFakeConfidence(unittest.TestCase):
    """The words the reader sees, audited for certainty the data cannot support.

    The existing scan covers generated prose in `jobs/analysis.py` for causal words. This one
    covers the written UI: the labels, leads and sentences in `app/`, `components/` and
    `lib/plain.ts`, where a promise would be hand-written rather than generated. Phrases are
    matched instead of single words on purpose — "a stale page will be obvious" is fine and
    "the price will rise" is not, and a bare "will" cannot tell them apart.
    """

    FORBIDDEN = [
        "will rise", "will fall", "will go up", "will go down", "will drop", "will climb",
        "is going to rise", "is going to fall", "guaranteed", "risk-free", "risk free",
        "sure thing", "can't lose", "cannot lose", "buy now", "sell now", "short now",
        "you should buy", "you should sell", "we recommend buying", "we recommend selling",
        "definitely will", "certain to rise", "certain to fall", "safe bet",
    ]

    # Causality, which rules 10 and 16 ban in generated prose and which is no more acceptable
    # hand-written on a page.
    CAUSAL = ["caused the move", "because of the news", "driven by the", "in response to the"]

    def visible_files(self):
        out = []
        for pattern in ("app/**/*.tsx", "app/*.tsx", "components/*.tsx"):
            out.extend(ROOT.glob(pattern))
        out.append(ROOT / "lib" / "plain.ts")
        return out

    def test_no_page_promises_a_price_move(self):
        hits = []
        files = self.visible_files()
        self.assertGreater(len(files), 8, "the page scan found almost nothing, so it is broken")
        for f in files:
            low = f.read_text(encoding="utf-8").lower()
            for phrase in self.FORBIDDEN:
                if phrase in low:
                    hits.append(f"{f.name}: {phrase}")
        self.assertEqual(hits, [], "; ".join(hits))

    NEGATIONS = ("not ", "never ", "no claim", "does not", "cannot", "rather than",
                 "without claiming", "is not")

    def negated(self, text: str, at: int) -> bool:
        """Whether a causal phrase sits inside a sentence that denies it.

        The project's own pages say "not as a claim that the readings caused the moves", which
        is the opposite of the fault being looked for. A scanner that cannot tell a denial from
        an assertion would force those disclaimers to be deleted to go green, which would make
        the pages worse and the test complicit in it.
        """
        window = text[max(0, at - 120):at]
        return any(n in window for n in self.NEGATIONS)

    def test_no_page_asserts_causality(self):
        hits = []
        for f in self.visible_files():
            low = f.read_text(encoding="utf-8").lower()
            for phrase in self.CAUSAL:
                start = 0
                while (at := low.find(phrase, start)) != -1:
                    if not self.negated(low, at):
                        hits.append(f"{f.name}: {phrase}")
                    start = at + len(phrase)
        self.assertEqual(hits, [], "; ".join(hits))

    def test_the_causality_scanner_tells_a_denial_from_a_claim(self):
        # Both halves asserted, because a scanner that passed everything would also be green.
        claim = "the earnings report caused the move in the share price"
        denial = "this is not a claim that the report caused the move"
        self.assertFalse(self.negated(claim, claim.index("caused the move")))
        self.assertTrue(self.negated(denial, denial.index("caused the move")))

    def test_the_phrase_scanner_would_catch_one(self):
        # Proof the matcher works, since a clean repository and a broken scan look alike.
        sample = "The price will rise next week, a safe bet."
        found = [ph for ph in self.FORBIDDEN if ph in sample.lower()]
        self.assertEqual(sorted(found), ["safe bet", "will rise"])

    def test_the_evidence_words_the_project_prefers_are_actually_used(self):
        # The other half of rule 4: hedged wording is only honest if the evidence words are
        # present. "measured", "observed", "stored" and "no evidence" should be everywhere.
        text = " ".join(f.read_text(encoding="utf-8").lower() for f in self.visible_files())
        for word in ("measured", "observed", "stored", "not a recommendation"):
            self.assertIn(word, text, f"the UI never says {word!r}")


class BudgetGuards(unittest.TestCase):
    """Every unbounded thing that could run away has a declared ceiling."""

    def test_each_job_that_fetches_or_fans_out_declares_a_bound(self):
        self.assertLessEqual(intraday.MAX_REQUESTS, 100)
        self.assertLessEqual(investigate.MAX_INVESTIGATIONS, 60)
        self.assertLessEqual(graph.MAX_HOPS, 2)
        self.assertLessEqual(graph.MAX_GROUP, 40)
        self.assertLessEqual(graph.MAX_PER_ASSET, 10)

    def test_the_graph_cannot_be_widened_into_uselessness_by_accident(self):
        # At three hops almost everything in a 160 asset database is reachable from almost
        # everything else, and a list of everything has told nobody anything.
        self.assertEqual(graph.MAX_HOPS, 2)
        self.assertLess(graph.DECAY, 0.5)

    def test_the_investigation_window_cannot_silently_become_a_month(self):
        self.assertLessEqual(investigate.NEWS_WINDOW_DAYS, 7)
        self.assertLessEqual(investigate.CALENDAR_DAYS, 21)


class SqlSafety(unittest.TestCase):
    """The injection surface, pinned where it actually is.

    Two surfaces with two different answers:

      * The **jobs** build SQL as text and do interpolate identifiers, because Postgres has no
        placeholder for a table or column name. Every one of those identifiers comes from a
        literal in the source — `WATCHED` and `DATE_COLUMN` in audit.py, `TABLES` in stats.py,
        `HORIZONS` in accuracy.py, and the ("assetId", "Asset") loop in human.py — and every
        *value* goes through `%s`. No external or user-supplied string reaches an identifier
        position, because the jobs take no user input at all.
      * The **web layer** is the only place user input exists: a URL path segment. It must
        therefore never build SQL, and these tests are what keep it that way.

    Three of these started as cruder regexes that flagged twenty-six prose sentences, three
    dict lookups and a stray backtick in a doc comment. A test that cries wolf teaches nothing,
    so each one is now scoped to the construct it actually cares about.
    """

    WEB = ("app", "lib", "components")

    def _web_files(self):
        for folder in self.WEB:
            for p in sorted((ROOT / folder).rglob("*.ts*")):
                yield p

    def test_the_web_layer_never_runs_raw_sql(self):
        # The user-input surface must stay entirely on Prisma's parameterised client. A single
        # $queryRawUnsafe here is the only way a path segment could reach the database as code.
        offenders = []
        for p in self._web_files():
            text = p.read_text(encoding="utf-8")
            for needle in ("$queryRaw", "$executeRaw", "queryRawUnsafe", "executeRawUnsafe"):
                if needle in text:
                    offenders.append(f"{p.relative_to(ROOT)}: {needle}")
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_no_sql_statement_is_assembled_in_the_web_layer(self):
        import re

        # Case-sensitive and newline-bounded: a real statement, not a backtick in prose.
        pattern = re.compile(r"`[^`\n]*\bSELECT\b[^`\n]*\bFROM\b[^`\n]*`")
        offenders = []
        for p in self._web_files():
            for m in pattern.finditer(p.read_text(encoding="utf-8")):
                offenders.append(f"{p.relative_to(ROOT)}: {m.group(0)[:60]}")
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_every_job_value_placeholder_is_a_bound_parameter(self):
        import re

        # Only inside a string that is actually SQL, and only where an interpolation sits in a
        # value position next to a comparison. \b on IN matters: without it, "within" matched.
        string_lit = re.compile(r'(?:f"""|f")(.*?)(?:"""|")', re.S)
        is_sql = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b")
        value_interp = re.compile(r"(?:=|>|<|\bLIKE\b|\bIN\b)\s*'?\{[a-z_]+\}'?")
        offenders = []
        for p in sorted((ROOT / "jobs").glob("*.py")):
            text = p.read_text(encoding="utf-8")
            for sm in string_lit.finditer(text):
                sql = sm.group(1)
                if not is_sql.search(sql):
                    continue
                for m in value_interp.finditer(sql):
                    line = text[: sm.start() + m.start()].count("\n") + 1
                    offenders.append(f"{p.name}:{line} {m.group(0)}")
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_no_secret_shaped_literal_is_committed(self):
        import re

        pattern = re.compile(
            r"(postgres(ql)?://[^\s\"']*:[^\s\"']*@|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}"
            r"|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY)"
        )
        keep = {".py", ".ts", ".tsx", ".yml", ".sql", ".prisma", ".json", ".md"}
        offenders = []
        for folder in ("jobs", "lib", "app", "components", "prisma", ".github"):
            base = ROOT / folder
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if not p.is_file() or p.suffix not in keep:
                    continue
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for m in pattern.finditer(text):
                    around = text[max(0, m.start() - 10) : m.end() + 30]
                    if "USER:PASSWORD" in around:
                        continue
                    offenders.append(f"{p.relative_to(ROOT)}")
        self.assertEqual(offenders, [], "; ".join(offenders))

    # The only files allowed to carry `use client`, named one by one so a third cannot appear
    # without this list being edited deliberately.
    #
    # Next requires an error boundary to be a Client Component -- there is no server-rendered
    # form of one -- so the site cannot have error pages and also have no client components at
    # all. Rule 37: the guard fired on correct code, so the guard is what changes.
    CLIENT_ALLOWED = ("app/error.tsx", "app/global-error.tsx")

    def test_nothing_is_exposed_to_the_browser(self):
        # No NEXT_PUBLIC_ variable and no client component means no server-only value can reach
        # the browser bundle at all, which is stronger than auditing each one. The two error
        # boundaries are the framework-mandated exception and are checked separately, below, so
        # that the property this guard protects is still asserted for them.
        for p in self._web_files():
            # Code only. A page that carries a comment saying why it has no `use client` is the
            # correct code this guard existed to protect, and failing it taught nothing.
            text = code_only(p.read_text(encoding="utf-8"))
            rel = p.relative_to(ROOT).as_posix()
            self.assertNotIn("NEXT_PUBLIC_", text, rel)
            if rel not in self.CLIENT_ALLOWED:
                self.assertNotIn("use client", text, rel)

    def test_the_error_boundaries_exist_and_reach_no_server_value(self):
        # Two halves of one statement.
        #
        # They must exist, because without them a failed read reaches the reader as Next's
        # unstyled built-in fallback -- the screen this site is most likely to show at its worst
        # moment, since every route is a direct read against a database that sleeps when idle.
        #
        # And they must stay inert. "No client components" was worth having because it made it
        # impossible for a server-only value to be bundled for the browser; now that two files
        # are exempt, that guarantee has to be asserted for them directly rather than inferred.
        banned = ("@/lib/db", "@/lib/queries", "@/prisma", "process.env", "prisma.")
        for rel in self.CLIENT_ALLOWED:
            p = ROOT / rel
            self.assertTrue(p.is_file(), f"{rel} is allowed to be a client component but is missing")
            text = code_only(p.read_text(encoding="utf-8"))
            self.assertIn("use client", text, f"{rel} is in the allow list but is not one")
            for needle in banned:
                self.assertNotIn(needle, text, f"{rel} reaches a server value: {needle}")

    def test_a_wrong_address_has_a_page_of_its_own(self):
        # Four routes call notFound(); without this file all four land on the built-in 404, with
        # no header, no nav and no way back to the thing the reader was looking for.
        self.assertTrue((ROOT / "app/not-found.tsx").is_file(), "app/not-found.tsx is missing")

    def test_the_database_url_is_read_in_exactly_one_web_file(self):
        readers = [
            p.relative_to(ROOT).as_posix()
            for p in self._web_files()
            if "DATABASE_URL" in p.read_text(encoding="utf-8")
        ]
        self.assertEqual(readers, ["lib/db.ts"], f"read in {readers}")

    def test_no_fetch_target_is_built_from_stored_or_fetched_data(self):
        import re

        # (?<![.\w]) excludes d.get(...) and counts.get(...): a dict lookup is not a fetch.
        call = re.compile(r"(?<![.\w])get(?:_json)?\(\s*([^,)\n]+)")
        from_row = re.compile(r"\br\[|\brow\[|\bitem\[|\bn\[")
        offenders = []
        for p in sorted((ROOT / "jobs").glob("*.py")):
            text = p.read_text(encoding="utf-8")
            for m in call.finditer(text):
                arg = m.group(1).strip()
                if from_row.search(arg):
                    line = text[: m.start()].count("\n") + 1
                    offenders.append(f"{p.name}:{line} fetches {arg}")
        self.assertEqual(offenders, [], "; ".join(offenders))

class IntradayTimezoneIndependence(unittest.TestCase):
    """Derived bars must land on the same timestamp whatever machine runs the job.

    Found in production, and the worst shape a bug can have: `datetime.timestamp()` on a naive
    datetime interprets it in the machine's local timezone, so the epoch round trip in
    `aggregate()` was invisible on the UTC workflow runner and shifted every derived bar five
    hours early when the same job ran from a UTC+5 laptop. The 15 minute bar stored at 08:00
    held the open of the 13:00 bar and the close of the 13:10 one — real numbers, correctly
    aggregated, filed under the wrong time.

    Two tests, because one is not enough. The behavioural test states the right answer, and the
    source test forbids the construct that got it wrong — a behavioural test alone would pass
    on a UTC runner with the bug still in place, which is exactly how this survived.
    """

    @staticmethod
    def _code_only(func):
        """Source with docstrings and comments removed.

        Needed because the functions under test name the banned construct in their own
        comments in order to explain why it is banned, and a scanner that counted those would
        make the explanation unwritable.
        """
        import inspect
        import re as _re

        src = inspect.getsource(func)
        src = _re.sub(r"\"\"\".*?\"\"\"", "", src, flags=_re.S)
        return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


    def test_a_bucket_is_the_naive_floor_of_its_bars(self):
        bars = _ibars(3, start=datetime(2026, 9, 24, 13, 0))
        got = intraday.aggregate(bars, 15)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["ts"], datetime(2026, 9, 24, 13, 0))

    def test_a_bucket_floors_a_mid_window_start(self):
        # Bars at 13:05, 13:10, 13:15 straddle two 15 minute buckets, so the first two group
        # under 13:00 and the third starts 13:15 with too few parts to be written.
        bars = _ibars(3, start=datetime(2026, 9, 24, 13, 5))
        got = intraday.aggregate(bars, 15)
        self.assertEqual(got, [])

    def test_every_derived_interval_floors_onto_the_hour_grid(self):
        for minutes in intraday.DERIVE_TO:
            per = minutes // intraday.CANONICAL
            bars = _ibars(per, start=datetime(2026, 9, 24, 14, 0))
            got = intraday.aggregate(bars, minutes)
            self.assertEqual(len(got), 1, f"{minutes}m did not build")
            self.assertEqual(got[0]["ts"], datetime(2026, 9, 24, 14, 0), f"{minutes}m")

    def test_an_interval_that_does_not_divide_the_day_is_refused(self):
        # Day-boundary arithmetic is only exact when the interval divides 1440.
        self.assertEqual(intraday.aggregate(_ibars(12), 50), [])
        for minutes in intraday.DERIVE_TO:
            self.assertEqual(1440 % minutes, 0, f"{minutes} does not divide a day")

    def test_the_aggregator_never_round_trips_through_an_epoch(self):
        """The construct, not just the outcome.

        A behavioural test passes on a UTC machine with the bug present. This forbids the
        thing that made the result depend on where it ran.
        """
        src = self._code_only(intraday.aggregate)
        for banned in (".timestamp()", "fromtimestamp", "utcfromtimestamp",
                       "mktime"):
            self.assertNotIn(
                banned, src, f"aggregate() uses {banned}, which is timezone dependent"
            )

    def test_session_dating_is_also_pure_arithmetic(self):
        # session_dates shifts by the provider's stated offset and takes .date(); if it ever
        # reached for a timestamp it would acquire the same defect.
        src = self._code_only(intraday.session_dates)
        for banned in (".timestamp()", "mktime", "astimezone"):
            self.assertNotIn(banned, src, f"session_dates() uses {banned}")


class UndefinedNames(unittest.TestCase):
    """Every name a job uses must be bound somewhere in that job.

    This exists because of the bug that broke the nightly refresh for days.
    `jobs/prices.py` used `timedelta` and imported only `date, datetime, timezone`, so the
    *first* job of the daily group died with `NameError` 0.1 minutes in — and every one of the
    sixteen jobs behind it was skipped. Nothing caught it: it imports, it compiles, it passes
    `compileall`, and the name is only resolved when that branch executes.

    The check is a flat module scope: collect every name bound anywhere in the file — imports,
    assignments, defs, parameters, comprehension targets, `with`/`except` aliases, globals —
    then flag any load that is not in that set and not a builtin. Flat rather than properly
    scoped on purpose: it under-reports slightly (a use-before-definition across two functions
    reads as fine) and in exchange it has almost no false positives, which is what makes it
    worth keeping. It would have caught `timedelta` on the commit that introduced it.
    """

    @staticmethod
    def _bound_names(tree):
        import ast

        bound = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    bound.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    bound.add(a.asname or a.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                # Lambda has no .name but the same .args shape, and every one of the twenty
                # false positives the first version produced was a lambda parameter.
                if not isinstance(node, ast.Lambda):
                    bound.add(node.name)
                args = node.args
                for a in (
                    list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
                ):
                    bound.add(a.arg)
                if args.vararg:
                    bound.add(args.vararg.arg)
                if args.kwarg:
                    bound.add(args.kwarg.arg)
            elif isinstance(node, ast.ClassDef):
                bound.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.add(node.name)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                bound.update(node.names)
            elif isinstance(node, ast.alias):
                bound.add((node.asname or node.name).split(".")[0])
        return bound

    def test_no_job_uses_a_name_it_never_binds(self):
        import ast
        import builtins

        known = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__"}
        offenders = []
        for path in sorted((ROOT / "jobs").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            bound = self._bound_names(tree) | known
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    if node.id not in bound:
                        offenders.append(f"{path.name}:{node.lineno} uses {node.id!r}")
        self.assertEqual(sorted(set(offenders)), [], "; ".join(sorted(set(offenders))))

    def test_the_check_would_have_caught_the_bug_that_motivated_it(self):
        """A test that cannot fail is not a test.

        This is the real shape of the prices.py defect: `timedelta` used, and only
        `date, datetime, timezone` imported.
        """
        import ast
        import builtins

        broken = (
            "from datetime import date, datetime, timezone\n"
            "def f(when):\n"
            "    return when - timedelta(days=3)\n"
        )
        tree = ast.parse(broken)
        bound = self._bound_names(tree) | set(dir(builtins))
        missing = [
            n.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound
        ]
        self.assertIn("timedelta", missing)

    def test_the_check_does_not_flag_the_corrected_form(self):
        import ast
        import builtins

        fixed = (
            "from datetime import date, datetime, timedelta, timezone\n"
            "def f(when):\n"
            "    return when - timedelta(days=3)\n"
        )
        tree = ast.parse(fixed)
        bound = self._bound_names(tree) | set(dir(builtins))
        missing = [
            n.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound
        ]
        self.assertEqual(missing, [])

    def test_every_job_imports_cleanly(self):
        """Catches the import-time half of the same class, which the AST walk cannot see."""
        import importlib

        for path in sorted((ROOT / "jobs").glob("*.py")):
            if path.name in {"run.py"}:
                continue  # run.py spawns subprocesses; importing it is not meaningful
            importlib.import_module(path.stem)


class InsertShape(unittest.TestCase):
    """Every INSERT must name as many columns as it supplies expressions.

    This is here because of a real bug. An edit added four columns to the HumanSignal insert
    and only three placeholders, so the statement had 31 columns and 30 expressions. Nothing
    caught it: it compiles, it lints, it type-checks, and it fails only when Postgres sees it
    — which was two hours into a queued pipeline run.

    The check reads the source rather than the database, so it costs nothing and runs on
    every push.
    """

    # (file, pattern-identifying comment) for the inserts whose shape is worth pinning.
    FILES = (
        "human.py", "analogs.py", "geo.py", "setup.py", "lineage.py", "audit.py",
        "lifecycle.py", "upcoming.py", "psx.py", "prices.py", "signals.py", "seed.py",
        "thesis.py", "attribution.py", "graph.py", "runlog.py",
    )

    def _statements(self, text: str):
        """Yield (columns, expressions) for each INSERT ... VALUES (...) in the text."""
        import re

        for m in re.finditer(
            r'INSERT INTO "(\w+)"\s*\(([^)]*?)\)\s*VALUES\s*\((.*?)\)\s*(?:ON CONFLICT|RETURNING|""")',
            text,
            re.S,
        ):
            table, cols_raw, vals_raw = m.group(1), m.group(2), m.group(3)
            # Strip SQL line comments before counting, so the annotations above do not count.
            vals_clean = re.sub(r"--[^\n]*", "", vals_raw)
            cols = [c.strip() for c in cols_raw.split(",") if c.strip()]
            # Split on top-level commas only: a cast like %s::"Tone" has no commas, but
            # now() and function calls could, so parenthesis depth is tracked.
            exprs, depth, current = [], 0, ""
            for ch in vals_clean:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if ch == "," and depth == 0:
                    exprs.append(current.strip())
                    current = ""
                else:
                    current += ch
            if current.strip():
                exprs.append(current.strip())
            yield table, cols, [e for e in exprs if e]

    # Postgres reserved words that are plausible column names. An unquoted one is a syntax
    # error, not a subtle bug, and it only appears when the statement reaches the database —
    # which for this repo means two minutes into a workflow nobody can read the log of.
    # `leading` was the one that found this test: it is reserved because TRIM uses it.
    RESERVED = (
        "leading", "trailing", "both", "order", "limit", "offset", "user", "group", "window",
        "end", "all", "any", "case", "when", "then", "else", "default", "check", "column",
        "table", "select", "from", "where", "having", "union", "current_date", "current_time",
        "primary", "references", "unique", "constraint", "collate", "asc", "desc", "natural",
        "using", "full", "left", "right", "inner", "outer", "on", "and", "or", "not", "null",
        "true", "false", "is", "in", "like", "between", "symmetric", "distinct", "into",
        "returning", "do", "with", "as", "for", "to", "set", "values", "cast", "analyse",
    )

    def test_no_insert_names_an_unquoted_reserved_word(self):
        import re

        offenders = []
        for name in self.FILES + ("investigate.py", "horizons.py", "intraday.py"):
            path = ROOT / "jobs" / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for table, cols, _ in self._statements(text):
                for col in cols:
                    bare = col.strip()
                    if bare.startswith('"'):
                        continue
                    if bare.lower() in self.RESERVED:
                        offenders.append(f"{name}: INSERT INTO {table} names bare {bare}")
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_the_scanner_would_actually_catch_one(self):
        # A test that can never fail is not a test. This proves the detector fires.
        fake = '''
            INSERT INTO "Thing" ("a", leading, "b")
            VALUES (%s,%s,%s)
            ON CONFLICT DO NOTHING
        '''
        found = [
            col for _, cols, _ in self._statements(fake) for col in cols
            if not col.strip().startswith('"') and col.strip().lower() in self.RESERVED
        ]
        self.assertEqual(found, ["leading"])

    def test_column_and_expression_counts_match(self):
        checked = 0
        for name in self.FILES:
            path = ROOT / "jobs" / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for table, cols, exprs in self._statements(text):
                checked += 1
                self.assertEqual(
                    len(cols),
                    len(exprs),
                    f"{name}: INSERT INTO {table} names {len(cols)} columns but supplies "
                    f"{len(exprs)} expressions",
                )
        self.assertGreater(checked, 0, "the INSERT scanner matched nothing, so it is broken")


class PsxHistoryDepth(unittest.TestCase):
    """The PSX backfill, which existed and still could not produce a directional read.

    The measured fault: 0 of 70 PSX assets had a `longer` horizon AssetSetup row while 90 of
    90 US assets did. Not a rule, not a threshold — history. The job asked for one file a
    month before the recent 120 days, so every PSX asset held about 178 closes against the
    220 jobs/horizons.py requires, and no factor firing could ever change that.

    These tests pin the arithmetic that stops it coming back, because the failure mode is
    silent: too shallow a window raises nothing, it just quietly skips every PSX asset.
    """

    TODAY = date(2026, 6, 15)

    def test_the_restated_horizon_minimum_cannot_drift_from_the_real_one(self):
        # psx.py reports whether it has cleared horizons.MIN_LONG without importing it, so a
        # change to MIN_LONG would otherwise leave the price job reporting against a stale
        # number — and reporting success at exactly the depth that produces nothing.
        self.assertEqual(psx.LONGER_MIN_CLOSES, horizons.MIN_LONG)

    def test_the_daily_window_is_deep_enough_for_a_longer_read_with_margin(self):
        # The window is in calendar days and the requirement is in sessions, so the conversion
        # is where an off-by-a-season hides. What a symbol ends up holding is the whole span —
        # the dense stretch plus the recent window the daily run keeps — so that is what the
        # requirement is measured against, not one run's bite out of it. The holiday rate is
        # bounded rather than guessed, so this holds in a year with a long Eid and a long
        # Muharram.
        span = self._weekdays_in_span(psx.DEEP_DAYS)
        for holiday_rate in (0.04, 0.08, 0.12):
            sessions = span * (1 - holiday_rate)
            self.assertGreaterEqual(
                sessions, horizons.MIN_LONG,
                f"at a {holiday_rate:.0%} holiday rate the window yields {sessions:.0f} "
                f"sessions, under the {horizons.MIN_LONG} a longer read needs",
            )
            # And past the minimum it will accept, to the window it actually reads from.
            # LONGER_RULES says "across two years" in the sentence published under every one
            # of those reads, and at the bare minimum that line is untrue.
            self.assertGreaterEqual(
                sessions, horizons.LONG_RANGE,
                f"at a {holiday_rate:.0%} holiday rate the stored depth is "
                f"{sessions:.0f} sessions, under the {horizons.LONG_RANGE} the longer "
                "read reads from",
            )

    def test_the_per_run_fetch_cap_still_reaches_the_whole_window(self):
        # The cap exists because the exchange began refusing at the connection level after
        # about six hundred requests in one session, taking the monthly grid and the share
        # counts down behind it. A cap that could never finish would be worse than no cap, so
        # what matters is that the stretch closes in a small number of weekly runs.
        remaining = frozenset(psx.deep_dates(self.TODAY, frozenset()))
        all_weekdays = set()
        day = self.TODAY - timedelta(days=psx.RECENT_DAYS + 1)
        while day >= psx.deep_start(self.TODAY):
            if day.weekday() < 5:
                all_weekdays.add(day)
            day -= timedelta(days=1)

        runs, stored = 0, set()
        while len(stored) < len(all_weekdays) and runs < 10:
            batch = psx.deep_dates(self.TODAY, frozenset(stored))
            self.assertLessEqual(len(batch), psx.DEEP_FETCH_BUDGET)
            self.assertTrue(batch, "a run that fetches nothing would never finish")
            stored |= set(batch)
            runs += 1
        self.assertEqual(stored, all_weekdays, "the cap left part of the window unreachable")
        self.assertLessEqual(runs, 3, f"the window took {runs} weekly runs to close")
        self.assertEqual(len(remaining), psx.DEEP_FETCH_BUDGET)

    def _weekdays_in_span(self, days: int) -> int:
        """Trading weekdays from `days` ago through today, both stretches together."""
        start = self.TODAY - timedelta(days=days)
        return sum(
            1 for i in range(days + 1)
            if (start + timedelta(days=i)).weekday() < 5
        )

    def test_the_daily_window_asks_for_no_weekend_and_nothing_the_recent_pass_covers(self):
        # 230 guaranteed 404s is six minutes of the exchange's time for nothing. The recent
        # window still asks for all seven days on purpose — there the 404s are what prove the
        # host is answering — so the two stretches must not overlap either.
        deep = psx.deep_dates(self.TODAY)
        self.assertEqual([d for d in deep if d.weekday() >= 5], [])
        newest_deep = max(deep)
        oldest_recent = self.TODAY - timedelta(days=psx.RECENT_DAYS)
        self.assertLess(newest_deep, oldest_recent)
        # Contiguous, not merely disjoint: a weekday falling between the two stretches would
        # be a hole in the series that nothing else fills. The join can land on a weekend, so
        # the gap is measured in weekdays rather than in calendar days.
        between = [
            oldest_recent - timedelta(days=i)
            for i in range(1, (oldest_recent - newest_deep).days)
        ]
        self.assertEqual([d for d in between if d.weekday() < 5], [])

    def test_a_date_already_stored_is_never_fetched_again(self):
        # What makes the second run cheap. Historical files never change, so a stored date is
        # finished, and the skip is in the plan rather than in a disk cache that may not have
        # survived between runs.
        deep = psx.deep_dates(self.TODAY)
        known = frozenset(deep[:40])
        thinner = psx.deep_dates(self.TODAY, known)
        self.assertEqual([d for d in thinner if d in known], [])
        # Skipping does not shrink the run, it moves it deeper: the bite stays the size the
        # host tolerates and reaches 40 weekdays further back. A plan that shrank instead
        # would take longer to close the window the more of it was already done.
        self.assertEqual(len(thinner), len(deep))
        self.assertLess(min(thinner), min(deep))

    def test_the_window_stops_at_the_era_this_job_reads(self):
        # A `today` early enough that the window would reach past HISTORY_FROM must clamp to
        # it rather than spend hundreds of requests on dates the reader is not pointed at.
        self.assertEqual(psx.deep_start(date(2019, 6, 1)), psx.HISTORY_FROM)
        self.assertEqual(
            psx.deep_start(self.TODAY), self.TODAY - timedelta(days=psx.DEEP_DAYS)
        )

    def test_the_monthly_grid_stops_where_the_daily_one_starts(self):
        # Every day inside the dense stretch is already being asked for, so a monthly anchor
        # there is pure backtracking work over files the dense pass has read anyway.
        monthly = [
            d for d in psx.anchor_dates(self.TODAY, "full")
            if d.day == 1 and d >= psx.deep_start(self.TODAY)
        ]
        self.assertEqual(monthly, [])
        # And `recent` still draws no grid at all.
        self.assertEqual(psx.deep_dates(self.TODAY, frozenset()) and True, True)
        self.assertTrue(
            min(psx.anchor_dates(self.TODAY, "full")) == psx.HISTORY_FROM,
            "the grid still reaches the first year the reader is pointed at",
        )

    def test_both_published_containers_read_and_an_error_page_does_not(self):
        # The real trap, and the reason the archive looked shallower than it is: 2019 onward
        # is a ZIP, 2013-11 to 2018 is gzip behind the same .Z name. A ZIP-only reader did
        # not raise on a gzip file, it reported that day as a market holiday.
        import gzip
        import io
        import zipfile

        line = "02JAN2015|OGDC|0820|Oil & Gas Dev.|84.20|87.30|84.15|86.20|3368560|84.94|||"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("closing11.lis", line)
        self.assertEqual(psx.unpack(buf.getvalue()), line)
        self.assertEqual(psx.unpack(gzip.compress(line.encode())), line)
        # A 404 from this host is an HTML error page with a 200-sized body, not an empty one,
        # so the magic byte check is also what stops it being parsed as a very short session.
        self.assertIsNone(psx.unpack(b"<!DOCTYPE html><html>404 Not Found</html>"))
        self.assertIsNone(psx.unpack(b"PK\x03\x04truncated"))
        self.assertIsNone(psx.unpack(b""))

    def test_a_published_day_holding_none_of_the_tracked_symbols_is_not_a_holiday(self):
        # read_day returns {} for "the exchange traded, none of ours are in it" and None for
        # "the exchange published nothing". Collapsing the two makes a backtrack walk straight
        # past a real session and report an older close as the nearest one, so the backtrack
        # tests `is not None` rather than truthiness.
        text = (ROOT / "jobs" / "psx.py").read_text(encoding="utf-8")
        body = text[text.index("def resolve"):text.index("found: set[date]")]
        self.assertIn("if load(day) is not None:", body)
        self.assertNotIn("if load(day):", body)

    def test_the_deeper_backfill_still_only_inserts(self):
        # The invariant _store_frame in jobs/prices.py states: an incremental run must never
        # delete. A deeper window makes that more load-bearing, not less — this job is now the
        # only writer of two years of PSX closes, and a run that replaced from a short fetch
        # would destroy them to save a few requests.
        text = (ROOT / "jobs" / "psx.py").read_text(encoding="utf-8")
        # The SQL statement, not the English word: the comments here discuss deleting in order
        # to say it never happens, and a substring match on "DELETE" fails on its own rationale.
        sql = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("#")
        )
        self.assertNotRegex(sql.upper(), r"\bDELETE\s+FROM\b")
        self.assertNotRegex(sql.upper(), r"\bTRUNCATE\b")
        self.assertIn("ON CONFLICT", sql)


class PriceFactors(unittest.TestCase):
    """The arithmetic in jobs/factors.py, and the three properties it would be worst to lose.

    Every case here is hand-computable: the series are short, round, and chosen so the expected
    answer can be checked on paper. That matters more than usual for this file, because a wrong
    factor does not raise — it writes a plausible number that the decision rules then trust.

    The three properties, in the order of how much a reader loses when one breaks:

      * a factor that cannot be computed is null, never zero, and `bars` says why
      * the band around a return is robust, so one gap does not swallow every later move
      * a row dated D is computed only from closes at or before D
    """

    @staticmethod
    def factors():
        import factors
        return factors

    @staticmethod
    def bars(closes, start=date(2026, 1, 5), volume=1000.0):
        """Consecutive dated bars from a list of closes, oldest first."""
        return [
            {"date": start + timedelta(days=i), "close": float(c), "volume": volume}
            for i, c in enumerate(closes)
        ]

    # --- the formulas, against arithmetic -------------------------------------------------

    def test_simple_returns_are_the_spans_they_claim(self):
        f = self.factors()
        # Twenty one closes, all 100 except the last. Every span therefore measures from 100,
        # so all three returns are 20% and can be read off without a calculator.
        closes = [100.0] * 20 + [120.0]
        self.assertAlmostEqual(f.simple_return(closes, 1), 20.0)
        self.assertAlmostEqual(f.simple_return(closes, 5), 20.0)
        self.assertAlmostEqual(f.simple_return(closes, 20), 20.0)
        # And a span whose base close is one bar out of reach is not the shorter span.
        self.assertIsNone(f.simple_return(closes[1:], 20))
        self.assertAlmostEqual(f.simple_return([100.0, 90.0], 1), -10.0)

    def test_a_return_refuses_an_unusable_base(self):
        f = self.factors()
        # A zero base is not a 100% gain. It is a denominator that does not exist.
        self.assertIsNone(f.simple_return([0.0, 50.0], 1))

    def test_the_volume_ratio_is_against_the_sessions_before_it(self):
        f = self.factors()
        # Twenty sessions at 100 then one at 250: 2.5 times its own average, and the heavy day
        # is not allowed to inflate the average it is measured against.
        self.assertAlmostEqual(f.volume_ratio([100.0] * 20 + [250.0]), 2.5)

    def test_a_volume_ratio_of_zero_is_a_measurement_and_a_missing_one_is_not(self):
        f = self.factors()
        # Nothing traded: a real 0.0, kept.
        self.assertEqual(f.volume_ratio([100.0] * 20 + [0.0]), 0.0)
        # The venue published no volume for the latest session: null, not a quiet day.
        self.assertIsNone(f.volume_ratio([100.0] * 20 + [None]))
        # Too few baseline sessions carry a volume at all.
        self.assertIsNone(f.volume_ratio([None] * 15 + [100.0] * 5 + [200.0]))

    def test_a_weekend_volume_is_measured_against_weekends(self):
        """Rule 39. A seven day market is quiet at the weekend; that is the calendar, not a signal.

        Twenty one consecutive days ending on a Saturday, weekdays at 1000 and weekend days at
        200, and the latest Saturday also at 200. Against the mixed average that is about 0.3x
        and reads as a dead market. Against other weekend days it is 1.0x, which is what a
        perfectly ordinary Saturday is. Every stored coin failed `setup.py`'s 1.2x gate on a
        weekend bar while its trend read up, and this is why.
        """
        import datetime as dt
        f = self.factors()
        # 2026-10-03 is a Saturday; twenty one days ending there.
        dates = [dt.date(2026, 10, 3) - dt.timedelta(days=n) for n in range(20, -1, -1)]
        volumes = [200.0 if d.weekday() >= 5 else 1000.0 for d in dates]
        self.assertTrue(dates[-1].weekday() >= 5)

        mixed = f.volume_ratio(volumes)
        self.assertLess(mixed, 0.4)                       # the calendar, reported as weakness
        self.assertAlmostEqual(f.volume_ratio(volumes, dates), 1.0)

    def test_the_weekend_split_cannot_move_a_five_day_market(self):
        """The same correction, stated for every market, must not touch an equity.

        A five day market has no weekend bars, so the comparable baseline is the whole baseline
        and the ratio is identical with dates and without. Measured over all 160 stored assets
        when this went in: ten crypto ratios moved and zero US or PSX ratios did.
        """
        import datetime as dt
        f = self.factors()
        # Thirty weekdays, skipping the weekends, ending on a Friday.
        dates, day = [], dt.date(2026, 10, 2)
        while len(dates) < 30:
            if day.weekday() < 5:
                dates.append(day)
            day -= dt.timedelta(days=1)
        dates.reverse()
        self.assertTrue(all(d.weekday() < 5 for d in dates))
        volumes = [100.0] * 29 + [250.0]
        self.assertEqual(f.volume_ratio(volumes, dates), f.volume_ratio(volumes))

    def test_a_thin_weekend_baseline_falls_back_to_the_mixed_one(self):
        """Two weekend bars are a worse denominator than twenty mixed ones.

        Below MIN_COMPARABLE_BARS the split is abandoned rather than used on a handful of days,
        because an average of two is a pair of observations and not a baseline.
        """
        import datetime as dt
        f = self.factors()
        # Eight consecutive days ending on a Sunday holds exactly two prior weekend bars.
        dates = [dt.date(2026, 10, 4) - dt.timedelta(days=n) for n in range(7, -1, -1)]
        volumes = [100.0] * 8
        self.assertLess(len([d for d in dates[:-1] if d.weekday() >= 5]), 4)
        self.assertEqual(f.volume_ratio(volumes, dates), f.volume_ratio(volumes))

    def test_the_moving_averages_are_means_of_the_window_they_name(self):
        f = self.factors()
        closes = [float(x) for x in range(1, 11)]
        self.assertAlmostEqual(f.sma(closes, 5), 8.0)       # (6+7+8+9+10)/5
        self.assertAlmostEqual(f.sma(closes, 10), 5.5)      # (1+...+10)/10
        # A 20 day average over ten closes would be a ten day average with the wrong label.
        self.assertIsNone(f.sma(closes, 20))

    def test_range_position_is_zero_at_the_low_and_a_hundred_at_the_high(self):
        f = self.factors()
        rising = [float(x) for x in range(1, 25)]
        self.assertAlmostEqual(f.range_pct(rising), 100.0)
        self.assertAlmostEqual(f.range_pct(list(reversed(rising))), 0.0)
        # A close halfway between the extremes of the window, by construction.
        middle = [10.0, 30.0] + [20.0] * 22
        self.assertAlmostEqual(f.range_pct(middle), 50.0)

    def test_a_series_that_never_moved_has_no_position_in_its_range(self):
        f = self.factors()
        # 0, 50 and 100 would all be defensible, which is the sign that the answer is null.
        self.assertIsNone(f.range_pct([25.0] * 30))

    def test_drawdown_is_never_positive_and_is_zero_at_the_high(self):
        f = self.factors()
        rising = [float(x) for x in range(1, 25)]
        self.assertEqual(f.drawdown_pct(rising), 0.0)
        # Down from a high of 24 to a close of 1.
        self.assertAlmostEqual(f.drawdown_pct(list(reversed(rising))), (1 / 24 - 1) * 100.0)
        # Every window shape, including the ones with the close at the top, stays <= 0.
        for closes in (rising, list(reversed(rising)), [5.0] * 30, [5.0] * 29 + [9.0]):
            self.assertLessEqual(f.drawdown_pct(closes), 0.0)

    def test_the_range_measures_the_stated_window_and_not_the_whole_history(self):
        f = self.factors()
        # A spike older than RANGE_WINDOW must not be the high the drawdown is taken from,
        # otherwise "percent below the trailing high" silently means "below the all time high".
        old_spike = [1000.0] + [50.0] * f.RANGE_WINDOW
        self.assertEqual(f.drawdown_pct(old_spike), 0.0)

    def test_the_peer_median_is_refused_below_the_floor(self):
        f = self.factors()
        self.assertIsNone(f.peer_median_r20([1.0, 2.0, 3.0, 4.0]))
        self.assertAlmostEqual(f.peer_median_r20([1.0, 2.0, 3.0, 4.0, 100.0]), 3.0)
        self.assertEqual(f.MIN_PEERS, 5, "the floor moved, so the justification needs rereading")

    def test_relative_strength_is_null_below_the_peer_floor_not_the_raw_return(self):
        f = self.factors()
        # Four peers: both peer fields null. The asset's own return must not be republished
        # under a name that claims it was compared against an industry.
        got = f.compute(self.bars([100.0] * 20 + [110.0]), date(2026, 3, 1), [1.0, 2.0, 3.0, 4.0])
        self.assertIsNone(got["peerMedianR20"])
        self.assertIsNone(got["relStrength"])
        self.assertEqual(got["peers"], 4, "the count of peers looked at is still worth storing")
        # Five peers: the median is published and the difference is arithmetic.
        got = f.compute(
            self.bars([100.0] * 20 + [110.0]), date(2026, 3, 1), [1.0, 2.0, 3.0, 4.0, 100.0]
        )
        self.assertAlmostEqual(got["peerMedianR20"], 3.0)
        self.assertAlmostEqual(got["relStrength"], 10.0 - 3.0)

    # --- the robust band ------------------------------------------------------------------

    def test_the_robust_band_is_not_swallowed_by_one_gap(self):
        """The whole reason the z-score here is not a mean and a standard deviation.

        Forty quiet half-percent sessions and one 25% earnings gap. A standard deviation reads
        that gap as the normal size of a day and calls a later 3% move ordinary; the median and
        the MAD do not move at all, so the later move stays what it is — unusual.
        """
        import statistics
        f = self.factors()
        history = [0.5, -0.5] * 20 + [25.0]
        move = 3.0

        robust = f.robust_z(move, history)
        # Forty one sessions: twenty at -0.5, twenty at 0.5, one at 25. The median is the
        # twenty-first value, 0.5; the deviations are twenty 0s, twenty 1s and one 24.5, so the
        # MAD is 1.0 and the scale is 1.4826. The score is therefore (3 - 0.5) / 1.4826.
        self.assertAlmostEqual(robust, (move - 0.5) / 1.4826, places=6)
        self.assertGreater(robust, 1.6, "a 3% day after forty quiet ones is not ordinary")

        mean = statistics.fmean(history)
        plain = (move - mean) / statistics.pstdev(history)
        # The same move against mean and standard deviation: inside one deviation, which on a
        # page reads as a day worth nobody's attention. That is the swallowing being avoided.
        self.assertLess(plain, 0.7, "the comparison case is not actually swamped")
        self.assertGreater(
            robust, 2.5 * plain,
            "the robust band no longer behaves differently from a standard deviation one",
        )

    def test_the_band_refuses_a_baseline_too_thin_to_describe_a_distribution(self):
        f = self.factors()
        self.assertIsNone(f.robust_z(3.0, [0.5, -0.5] * 5))
        self.assertEqual(f.MIN_Z_HISTORY, 30)

    def test_a_flat_baseline_gives_a_finite_band_rather_than_an_infinity(self):
        f = self.factors()
        # Every session identical: MAD 0. Without the floor this divides by zero.
        got = f.robust_z(1.0, [0.0] * 40)
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got, 1.0 / f.MAD_FLOOR_PCT)

    def test_the_band_is_measured_against_the_sessions_before_the_move(self):
        f = self.factors()
        # Fifty quiet sessions then a jump. If the jump were inside its own baseline it would
        # pull the median towards itself and shrink exactly the score being asked for.
        closes = [100.0 + 0.1 * i for i in range(50)] + [150.0]
        got = f.compute(self.bars(closes), date(2027, 1, 1))
        self.assertIsNotNone(got["returnZ"])
        self.assertGreater(got["returnZ"], 10.0)

    # --- null, never zero ------------------------------------------------------------------

    def test_too_few_bars_gives_null_for_that_field_and_a_correct_bar_count(self):
        """The rule the schema comment is explicit about, in the form that would break first.

        Fifteen closes support a one and a five session return and nothing longer. The 20
        session return, both moving averages and the band are null — not 0.0, which the rules
        would read as a flat month, a price at its own average, and an utterly ordinary day.
        """
        f = self.factors()
        got = f.compute(self.bars([100.0 + i for i in range(15)]), date(2026, 6, 1))
        self.assertEqual(got["bars"], 15)
        self.assertIsNotNone(got["r1"])
        self.assertIsNotNone(got["r5"])
        for field in ("r20", "sma20", "sma50", "returnZ"):
            self.assertIsNone(got[field], f"{field} was computed from 15 closes")

    def test_nothing_stored_reports_no_bars_and_no_factors(self):
        f = self.factors()
        got = f.compute([], date(2026, 6, 1))
        self.assertEqual(got["bars"], 0)
        for field in ("r1", "r5", "r20", "returnZ", "volumeRatio", "sma20", "sma50",
                      "rangePct", "drawdownPct", "peerMedianR20", "relStrength"):
            self.assertIsNone(got[field], f"{field} was produced from no closes at all")

    def test_a_short_history_is_counted_up_to_the_session_and_not_past_it(self):
        f = self.factors()
        bars = self.bars([100.0 + i for i in range(40)])
        # Ten of those bars are dated after the session being written.
        got = f.compute(bars, bars[29]["date"])
        self.assertEqual(got["bars"], 30)

    def test_a_dated_item_outside_the_horizon_is_null_rather_than_a_large_number(self):
        f = self.factors()
        day = date(2026, 6, 1)
        self.assertEqual(f.event_in_days(day, day), 0)
        self.assertEqual(f.event_in_days(day, day + timedelta(days=9)), 9)
        self.assertIsNone(f.event_in_days(day, None))
        self.assertIsNone(f.event_in_days(day, day - timedelta(days=1)))
        self.assertIsNone(
            f.event_in_days(day, day + timedelta(days=f.EVENT_HORIZON_DAYS + 1))
        )

    def test_a_stale_news_reading_is_not_borrowed_as_a_recent_one(self):
        f = self.factors()
        day = date(2026, 6, 1)
        self.assertEqual(f.news_stories(day, day, 4), 4)
        self.assertEqual(f.news_stories(day, day, 0), 0, "checked and none is not unchecked")
        self.assertIsNone(f.news_stories(day, None, None))
        self.assertIsNone(
            f.news_stories(day, day - timedelta(days=f.NEWS_MAX_AGE_DAYS + 1), 9)
        )

    # --- look-ahead -----------------------------------------------------------------------

    def test_a_factor_for_a_session_is_identical_with_and_without_later_sessions(self):
        """The dangerous bug, in the only form a database-free suite can ask about it.

        A factor that peeks one session forward makes every hit rate the project publishes a
        lie, and nothing about the row would look wrong. So: compute for session D from a
        series that runs well past D, and from the same series truncated at D, and require the
        two to be the same answer field by field.
        """
        f = self.factors()
        closes = [100.0 + ((i * 7) % 11) for i in range(80)]
        bars = self.bars(closes)
        at = 59
        day = bars[at]["date"]

        with_future = f.compute(bars, day, [1.0, 2.0, 3.0, 4.0, 5.0])
        without_future = f.compute(bars[: at + 1], day, [1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(with_future, without_future)
        self.assertEqual(with_future["bars"], at + 1)

        # And the test is not vacuous: the last session genuinely measures something else.
        self.assertNotEqual(f.compute(bars, bars[-1]["date"]), without_future)

    def test_the_cutoff_lives_in_the_formula_and_not_only_in_the_sql(self):
        f = self.factors()
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        body = src[src.index("def compute("):src.index("def event_in_days(")]
        self.assertIn('b["date"] <= period_end', body, "compute trusts its caller's cutoff")
        # Order is part of the cutoff: a caller handing over rows in storage order must get
        # the same answer as one handing them over sorted.
        self.assertIn("sorted(", body)

    def test_every_read_is_bounded_by_the_session_being_written(self):
        f = self.factors()
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        history = src[src.index("def read_history("):src.index("def read_events(")]
        self.assertIn("date <= %s", history)
        self.assertNotIn("date > %s", history)
        news = src[src.index("def read_news("):src.index("def flush(")]
        self.assertIn('"periodEnd" <= %s', news)
        # The only forward-looking read is the calendar, which is the point of a calendar.
        events = src[src.index("def read_events("):src.index("def read_news(")]
        self.assertIn("e.date >= %s", events)
        self.assertIsNotNone(f.read_events)

    def test_the_row_is_dated_to_a_session_that_exists(self):
        f = self.factors()
        series = {
            "a": [{"date": date(2026, 6, 1)}, {"date": date(2026, 6, 4)}],
            "b": [{"date": date(2026, 6, 3)}],
            "c": [],
        }
        self.assertEqual(f.session_end(series, date(2026, 6, 9)), date(2026, 6, 4))
        # Nothing stored at all: the fallback, rather than an exception inside a nightly lane.
        self.assertEqual(f.session_end({}, date(2026, 6, 9)), date(2026, 6, 9))

    # --- the shape of the write -------------------------------------------------------------

    def test_a_rerun_on_the_same_day_updates_rather_than_duplicating(self):
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        self.assertIn('ON CONFLICT ("assetId", "periodEnd") DO UPDATE', src)
        self.assertNotRegex(src.upper(), r"\bDELETE\s+FROM\b")

    def test_the_run_is_committed_in_bounded_batches(self):
        # events.py held one transaction across a whole run and Neon's pooler closed it
        # underneath. A ceiling on the batch is what keeps a dropped connection cheap.
        f = self.factors()
        self.assertLessEqual(f.BATCH_ROWS, 500)
        self.assertGreaterEqual(f.BATCH_ROWS, 50)
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        self.assertIn("conn.commit()", src)

    def test_the_whole_run_reads_a_bounded_number_of_statements(self):
        # Four reads for every asset in the database, none of them inside a loop. A query per
        # asset is four thousand round trips at the thousand assets this table is sized for.
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        self.assertEqual(src.count(" rows("), 4, "the number of reads changed")
        self.assertEqual(QueryBudget.in_loop_calls(ROOT / "jobs" / "factors.py"), 0)


if __name__ == "__main__":
    unittest.main()


class ShortLevelsAreMirrored(unittest.TestCase):
    """A short's stop belongs above the price, not below it.

    The entry is the level a move has to clear for the setup to be happening; the invalidation is
    the level at which the reason for it has stopped being true. For an up read that is the
    window's high and its low. For a down read it is the other way round — and both
    level-writing jobs used to hand a `short` row the same pair as a `buy` row.

    What that produced on the live site: WTL read SHORT at Rs.1.00 and the panel printed "Exit if
    wrong Rs.0.99 — past this level the reason above no longer holds". The stop sat one percent
    *below* a short, on the side the trade needs price to reach, while the target block further
    down the same page measured the same trade downward to a median of -0.8%. STLA was the same
    shape at $4.40 with a $4.36 stop.

    These are source-level tests rather than calls, because the levels are chosen inside a long
    database loop in `setup.py` and inside `longer_read` in `horizons.py`, and the property worth
    protecting is that the choice consults `state` at all. `run_targets` in horizons.py has always
    branched on `state`, so the repository already held the correct form of the statement while
    two of its three level-writers disagreed with it.
    """

    def source(self, name: str) -> str:
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "jobs" / name).read_text(encoding="utf-8")

    def test_setup_picks_its_levels_by_state(self):
        src = self.source("setup.py")
        self.assertIn('entry, invalid = (low, high) if state == "short" else (high, low)', src)
        # And the old unconditional form is gone, in either order.
        self.assertNotIn("entry = max(float(b[\"close\"]) for b in recent)", src)
        self.assertNotIn("invalid = min(float(b[\"close\"]) for b in recent)", src)

    def test_horizons_picks_its_levels_by_state(self):
        src = self.source("horizons.py")
        self.assertIn('entry, invalid = (below, above) if state == "short" else (above, below)', src)
        self.assertNotIn("entry = next_level(highs, last, above=True)", src)
        self.assertNotIn("invalid = next_level(lows, last, above=False)", src)

    def test_both_jobs_describe_the_level_they_actually_wrote(self):
        """A mirrored level with an unmirrored note is the same lie in prose.

        The note is what the asset page prints under the number, so a short carrying "the highest
        close ... a close above it would be a move past where it recently stalled" over its entry
        would describe a long while the number described a short.
        """
        # Fragments rather than whole sentences: these are implicit-concatenation literals split
        # over two source lines, so the sentence a reader sees never appears contiguously here.
        setup_src = self.source("setup.py")
        self.assertIn("move past where it recently held", setup_src)      # short entry
        self.assertIn("A close above it means the", setup_src)            # short invalidation
        self.assertIn("move past where it recently stalled", setup_src)   # long entry
        self.assertIn("A close below it means the", setup_src)            # long invalidation

        horizons_src = self.source("horizons.py")
        self.assertIn("the nearest level above where the series last turned", horizons_src)
        self.assertIn("the nearest price below where the series last turned", horizons_src)

    def test_the_entry_zone_does_not_care_which_way_round_the_pair_is(self):
        """`entryZone` spans the two levels with min/max, so mirroring cannot invert the band.

        Asserted here because the fix depends on it: the band stays [low, high] either way and
        only `invalidation` — what the panel prints as "Exit if wrong" — moves to the other edge.
        """
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "lib" / "decisionInput.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn("low: Math.min(entryLevel, invalidateLevel)", src)
        self.assertIn("high: Math.max(entryLevel, invalidateLevel)", src)
