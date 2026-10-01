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
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

import analogs  # noqa: E402
import attribution  # noqa: E402
import graph  # noqa: E402
import human  # noqa: E402
import lineage  # noqa: E402
import nbt  # noqa: E402
import run  # noqa: E402
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

    def test_the_reading_jobs_follow_the_jobs_they_read(self):
        # thesis reads the AssetSetup row setup.py writes, and graph walks out from the
        # catalysts human.py flags. Either one running first would read yesterday's rows.
        for plan in (run.DAILY, run.WEEKLY):
            order = [script for script, _ in plan]
            self.assertLess(order.index("setup"), order.index("thesis"))
            self.assertLess(order.index("human"), order.index("graph"))
            self.assertLess(order.index("lineage"), order.index("human"))


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
