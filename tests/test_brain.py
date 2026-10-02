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
import run  # noqa: E402
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

    def test_the_data_lanes_check_the_schema_before_writing(self):
        for name in ("refresh.yml", "backfill.yml"):
            self.assertIn("jobs/schemacheck.py", self._text(name), f"{name} does not check")

    def test_the_schema_lane_keeps_its_own_concurrency_group(self):
        # A hung enrichment fetch once held the shared group for 90+ minutes while the
        # migration the deployed site needed sat queued behind it. P3 must never block P0.
        self.assertIn("group: nbt-schema", self._text("schema.yml"))
        for name in ("refresh.yml", "backfill.yml"):
            self.assertIn("group: nbt-database", self._text(name))

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
    APPEND_ONLY: tuple[str, ...] = ("Coverage", "Calibration")

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
        # And the only SystemExit in the job is the one after the commit.
        self.assertEqual(text.count("raise SystemExit"), 1)

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
            body.index("if not closes:"),
            body.index("cap_by_day[closes[-1][0]]"),
            "the empty-series guard must come before anything that indexes the series",
        )

    def test_a_crypto_row_has_every_column_the_copy_writer_unpacks(self):
        # The real defect: a six-field row handed to a nine-name unpack, which only fails
        # when the COPY loop runs and so needs a database to surface.
        rows = prices.crypto_rows(
            "a1",
            [(date(2026, 9, 29), 65000.0)],
            {date(2026, 9, 29): 1234.5},
            {date(2026, 9, 29): (64000.0, 66000.0, 63500.0)},
            {date(2026, 9, 29): 1.29e12},
        )
        self.assertEqual(len(rows), 1)
        asset_id, day, op, hi, lo, close, vol, cap, source = rows[0]
        self.assertEqual((asset_id, day, op, hi, lo), ("a1", date(2026, 9, 29), 64000.0, 66000.0, 63500.0))
        self.assertEqual((close, vol, cap, source), (65000.0, 1234.5, 1.29e12, "Binance"))
        # A day the source sent no bar for keeps three Nones rather than a shifted row.
        (only,) = prices.crypto_rows("a1", [(date(2026, 9, 30), 1.0)], {}, {}, {})
        self.assertEqual(len(only), 9)
        self.assertEqual(only[2:5], (None, None, None))

    def test_a_whole_binance_batch_coming_back_empty_fails_the_step(self):
        with self.assertRaises(prices.SourceSilent):
            prices.require_answer(0, 10, source="Binance")
        self.assertIsNone(prices.require_answer(3, 10, source="Binance"))


    def test_the_news_lane_counts_feeds_that_answered_not_rows_it_wrote(self):
        # `written` is new rows, and ON CONFLICT DO NOTHING makes that legitimately 0 on a
        # rerun inside the cache hour. Guarding on it would fail a healthy run; guarding on
        # feeds parsed catches a blocked host and nothing else.
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_news"):text.index("def main")]
        self.assertIn("require_answer(parsed, asked, source=GNEWS)", body)
        self.assertNotIn("require_answer(written", body)
        # And the guard runs before the 120-day retention sweep, so a run that fetched
        # nothing cannot delete four months of articles.
        self.assertLess(body.index("require_answer(parsed"), body.index("120 days"))


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

    def test_nothing_is_exposed_to_the_browser(self):
        # No NEXT_PUBLIC_ variable and no client component means no server-only value can reach
        # the browser bundle at all, which is stronger than auditing each one.
        for p in self._web_files():
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("NEXT_PUBLIC_", text, f"{p.relative_to(ROOT)}")
            self.assertNotIn("use client", text, f"{p.relative_to(ROOT)}")

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
        "thesis.py", "attribution.py", "graph.py",
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


if __name__ == "__main__":
    unittest.main()
