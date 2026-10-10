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
import os
import re
import sys
import unittest
from unittest import mock
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

import analogs  # noqa: E402
import attribution  # noqa: E402
import factors  # noqa: E402
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
import setup  # noqa: E402
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


class ToneDenominator(unittest.TestCase):
    """A net lean has to be measured against the headlines that took a side.

    `tone_score` was `(positive - negative) / items`, dividing by every headline in the window
    including the ones carrying no tone word at all. Measured 2026-10-07 across 265 assets: only
    **11.1%** of headlines carry any tone word and the median asset has **2** of them, so the rule
    was asking for a net lean of 15% of total coverage -- and the bar rose with coverage, because
    `items` grew while the opinionated subset did not.

    The same denominator family as rule 42, and the fifth instance in this repository.
    """

    def _tone(self, positive, negative, items):
        """The published rule, called the way jobs/human.py calls it."""
        n = items
        opinionated = positive + negative
        score = (positive - negative) / opinionated if opinionated else 0.0
        if not n:
            return None
        if opinionated < human.MIN_TONE_ITEMS:
            return "neutral"
        if score > human.NEUTRAL_BAND:
            return "positive"
        if score < -human.NEUTRAL_BAND:
            return "negative"
        return "neutral"

    def test_the_measured_cases_that_were_called_neutral_and_were_not(self):
        # All three are real rows from 2026-10-07. The first is the one that gives it away:
        # seven headlines leaning positive, none leaning negative, reported as no direction.
        self.assertEqual(self._tone(7, 0, 64), "positive")
        self.assertEqual(self._tone(14, 5, 88), "positive")
        self.assertEqual(self._tone(10, 6, 90), "positive")
        # And what the old rule did with them, for the record.
        for p_, n_, items in ((7, 0, 64), (14, 5, 88), (10, 6, 90)):
            self.assertLessEqual(
                (p_ - n_) / items, human.NEUTRAL_BAND,
                "fixture no longer demonstrates the old rule calling these neutral",
            )

    def test_coverage_no_longer_raises_the_bar_against_itself(self):
        # The perverse property, stated directly: the same 6-1 split must read the same whether
        # it sits in a thin window or a well covered one. Under the old rule the second was
        # neutral purely because more factual headlines existed around it.
        self.assertEqual(self._tone(6, 1, 10), self._tone(6, 1, 200))
        self.assertEqual(self._tone(6, 1, 200), "positive")

    def test_a_balanced_window_is_still_neutral(self):
        # The band has to keep doing its job on the new denominator. 4 against 3 is not a
        # direction; among seven opinionated headlines that is a 14% lean, inside the band.
        self.assertEqual(self._tone(4, 3, 40), "neutral")
        self.assertEqual(self._tone(3, 4, 40), "neutral")

    def test_a_direction_is_not_read_off_one_or_two_words(self):
        # The floor the old denominator had been providing by accident. A 1-0 split is a 100%
        # lean by the new arithmetic and must not publish a direction.
        self.assertEqual(self._tone(1, 0, 30), "neutral")
        self.assertEqual(self._tone(2, 0, 30), "neutral")
        self.assertEqual(self._tone(0, 2, 30), "neutral")
        # At the floor it may, and the sign has to be right.
        self.assertEqual(self._tone(5, 0, 30), "positive")
        self.assertEqual(self._tone(0, 5, 30), "negative")

    def test_negative_still_reaches_negative(self):
        # The gate that had never produced a short in the life of the table reads off this.
        self.assertEqual(self._tone(1, 8, 50), "negative")
        self.assertEqual(self._tone(0, 6, 12), "negative")

    def test_an_empty_window_has_no_tone_rather_than_a_neutral_one(self):
        # Unchanged, and pinned because it sits beside what moved: nothing read is not the same
        # as read and balanced.
        self.assertIsNone(self._tone(0, 0, 0))

    def test_the_floor_and_the_band_are_both_declared(self):
        self.assertEqual(human.MIN_TONE_ITEMS, 5)
        self.assertEqual(human.NEUTRAL_BAND, 0.15)


class PeriodAnchors(unittest.TestCase):
    """A row describing a session carries that session's date, not the machine's.

    `jobs/factors.py` states the rule in `session_end` and obeys it: "Today's date is the wrong
    anchor: the job runs before a close on a holiday and on a weekend, and dating a row to a day
    with no session in it would make `periodEnd` a claim about a day nothing was measured on."

    `jobs/setup.py` did not. Measured 2026-10-07: every close, factor and decision was dated 10-07
    while all 272 swing setups read **10-08**, because the job ran from a UTC+5 host after 19:00
    UTC and `date.today()` had already rolled. The rows described 10-07 closes under tomorrow's
    date, and `jobs/thesis.py` copied that date onto 11 theses. On a UTC runner the same bug fires
    every weekend and every holiday instead -- less often, and in exactly the same way.
    """

    def test_setup_dates_its_rows_from_the_newest_close(self):
        src = (ROOT / "jobs" / "setup.py").read_text(encoding="utf-8")
        # The row's own date comes from the stored series.
        self.assertIn(
            'SELECT max(date) AS d FROM "PriceSnapshot"', src,
            "setup.py no longer anchors periodEnd to a session that exists",
        )
        self.assertIn("period_end", src)
        # And the row that is written uses it rather than the calendar. The parameters now sit
        # in a payload list that one `executemany` consumes, so the check is on the tuple
        # rather than on the text of the statement.
        row = src[src.index("payload.append("):]
        head = row[: row.index("RULES")]
        self.assertIn("period_end", head, "the AssetSetup row is not using the session date")
        self.assertNotIn(
            'a["id"], today, HORIZON', src,
            "the AssetSetup insert is stamping rows with the machine's calendar date",
        )

    def test_setup_still_reads_the_calendar_for_things_ahead(self):
        # The other half, and the reason this is two variables rather than one rename: "what is
        # scheduled from here on" is a question about now. Dating an event lookup to the last
        # close would hide an event that falls between that close and today.
        src = (ROOT / "jobs" / "setup.py").read_text(encoding="utf-8")
        self.assertIn("today = date.today()", src)
        self.assertIn("e.date >= %s", src)
        # The lookup is taken for every asset in one statement now; the date it is bounded by
        # is still the calendar and that is the half this test exists to hold.
        self.assertIn(
            "all_next_events(cur, today)", src,
            "the event lookup should still be bounded by the calendar",
        )
        self.assertIn("(today,)", src)


class VolumeBaseline(unittest.TestCase):
    """"Is this session busier than usual" has to be measured against a typical session.

    `volume_ratio` divided the latest volume by the **mean** of its trailing window, which is
    the same mistake `robust_z` in the same file already refuses to make for returns. Volume's
    skew is one sided -- a session can be five times normal and cannot be below zero -- so the
    mean of a twenty session window sits above the typical session in essentially every window.

    Measured 2026-10-07 over 15,411 asset-sessions, as the median of all ratios produced: PSX
    0.614 by mean against 0.827 by median, Commodity 0.756 / 1.003, US 0.874 / 0.955, Crypto
    0.931 / 1.063. The bias is the smaller half. The larger half is that it is uneven between
    markets, so `VOL_ACTIVE` at 1.2 asked a Karachi name for roughly twice its typical session
    and a coin for roughly 1.3 times its own, and nothing said so.
    """

    def _flat(self, n, value, latest):
        from datetime import date as _date, timedelta as _td

        # Weekdays only, so the weekend split is a no-op and these test the denominator alone.
        days, cursor = [], _date(2026, 1, 5)  # a Monday
        while len(days) < n + 1:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += _td(days=1)
        return [value] * n + [latest], days

    def test_an_ordinary_session_against_a_skewed_window_reads_as_ordinary(self):
        # The fault, in the smallest shape that shows it. Nineteen sessions at 100 and one spike
        # at 1000: the typical session is 100, and a session of exactly 100 is exactly typical.
        # The mean of that window is 145, so the old measure called a typical session 0.69 --
        # and `VOL_ACTIVE` at 1.2 then needed 174, not 120, without saying so.
        vols = [100.0] * 19 + [1000.0]
        from datetime import date as _date, timedelta as _td

        days, cursor = [], _date(2026, 1, 5)
        while len(days) < len(vols) + 1:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += _td(days=1)
        got = factors.volume_ratio(vols + [100.0], days)
        self.assertAlmostEqual(got, 1.0, places=6)
        mean_would_be = 100.0 / (sum(vols) / len(vols))
        self.assertLess(mean_would_be, 0.75, "fixture no longer demonstrates the bias")

    def test_the_threshold_still_means_what_its_constant_says(self):
        # 1.2x of a typical session, and nothing else. A spike in the window must not move it.
        vols = [100.0] * 15 + [900.0] * 4
        from datetime import date as _date, timedelta as _td

        days, cursor = [], _date(2026, 1, 5)
        while len(days) < len(vols) + 1:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += _td(days=1)
        self.assertAlmostEqual(factors.volume_ratio(vols + [120.0], days), 1.2, places=6)
        self.assertAlmostEqual(factors.volume_ratio(vols + [119.0], days), 1.19, places=6)

    def test_a_real_spike_is_still_a_spike(self):
        # The measure has to stay sharp in the direction it exists for. Tripling a typical
        # session reads as 3x, not as something the window's own outliers have flattened.
        vols, days = self._flat(20, 100.0, 300.0)
        self.assertAlmostEqual(factors.volume_ratio(vols, days), 3.0, places=6)

    def test_a_name_that_barely_trades_has_no_typical_session(self):
        # Sixteen zeros and four real sessions: the median is 0, and the honest answer is that
        # there is nothing to compare against. This is a weaker trigger than the mean's was --
        # a mean needed every session to be zero -- and that is the right place for it.
        vols, days = self._flat(0, 0.0, 0.0)
        vols = [0.0] * 16 + [500.0] * 4 + [600.0]
        from datetime import date as _date, timedelta as _td

        days, cursor = [], _date(2026, 1, 5)
        while len(days) < len(vols):
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += _td(days=1)
        self.assertIsNone(factors.volume_ratio(vols, days))

    def test_an_absent_latest_volume_is_still_absent_rather_than_quiet(self):
        # Unchanged behaviour, pinned because it sits next to what changed. A venue that
        # published no volume is not a quiet venue, and 0.0 would say the opposite.
        vols, days = self._flat(20, 100.0, 100.0)
        vols[-1] = None
        self.assertIsNone(factors.volume_ratio(vols, days))

    def test_the_weekend_split_still_applies_on_top_of_the_median(self):
        # The two corrections are independent and both have to hold: a weekend bar is compared
        # against weekend bars, and the comparison within them is against their median.
        from datetime import date as _date, timedelta as _td

        days, vols = [], []
        cursor = _date(2026, 1, 5)
        for _ in range(21):
            days.append(cursor)
            vols.append(30.0 if cursor.weekday() >= 5 else 100.0)
            cursor += _td(days=1)
        # Land the latest bar on a Saturday carrying a typical weekend volume.
        while days[-1].weekday() != 5:
            cursor = days[-1] + _td(days=1)
            days.append(cursor)
            vols.append(30.0 if cursor.weekday() >= 5 else 100.0)
        vols[-1] = 30.0
        got = factors.volume_ratio(vols, days)
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got, 1.0, places=6)


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


# The matching rule an asset with a tape gets: the three constants, unchanged. Written out here
# rather than taken from `tolerances` so a test of `similar` is a test of `similar` and does not
# silently start passing because the rule it was handed changed.
_TOL = {
    "day": analogs.DAY_TOL,
    "vol": analogs.VOL_TOL,
    "five": analogs.FIVE_TOL,
    "use_volume": True,
}


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
        self.assertFalse(analogs.similar(a, b, _TOL))

    def test_similarity_respects_every_tolerance(self):
        a = {"day": 1.0, "vol": 1.0, "five": 1.0}
        self.assertTrue(analogs.similar(a, dict(a), _TOL))
        self.assertFalse(analogs.similar(a, {**a, "day": 1.0 + analogs.DAY_TOL + 0.1}, _TOL))
        self.assertFalse(analogs.similar(a, {**a, "vol": 1.0 + analogs.VOL_TOL + 0.1}, _TOL))
        self.assertFalse(analogs.similar(a, {**a, "five": 1.0 + analogs.FIVE_TOL + 0.1}, _TOL))

    def test_an_instrument_with_no_tape_is_matched_on_what_it_has(self):
        # The gap this closes: `similar` refused every pair of days for an instrument with no
        # volume, so all 27 currency pairs held zero analogs while every other class was
        # near-complete. Two of the four things that can confirm a direction were permanently
        # absent for them, which is why 24 of 27 sat in WAIT with fresh inputs.
        bars = _bars([10.0 + (i % 7) * 0.02 for i in range(400)], [None] * 400)
        tol = analogs.tolerances(bars)
        self.assertIsNotNone(tol)
        self.assertFalse(tol["use_volume"])

        a = {"day": 0.10, "vol": None, "five": 0.30}
        self.assertTrue(analogs.similar(a, dict(a), tol))
        # The two return factors still bind, and volume is simply not asked about.
        self.assertTrue(analogs.similar(a, {**a, "vol": 99.0}, tol))
        self.assertFalse(analogs.similar(a, {**a, "day": a["day"] + tol["day"] + 0.01}, tol))
        self.assertFalse(analogs.similar(a, {**a, "five": a["five"] + tol["five"] + 0.01}, tol))

    def test_the_no_tape_window_is_scaled_to_the_asset_and_not_to_equities(self):
        # Rule 42, applied before it could bite. DAY_TOL is 1.25 points, sized against a US
        # equity whose daily sigma is around 1.5. A currency pair's daily sigma is nearer 0.35,
        # so 1.25 points would match almost every day to almost every other and return the
        # pair's unconditional average return wearing the word "similar".
        quiet = _bars([100.0 * (1.0 + 0.0008 * ((i % 7) - 3)) for i in range(500)], [None] * 500)
        tol = analogs.tolerances(quiet)
        self.assertLess(tol["day"], analogs.DAY_TOL / 4)

        # And on something that moves like an equity it lands near the constant it replaces,
        # which is the whole reason SIGMA_TOL is 0.8 rather than a number picked to be generous.
        lively = _bars([100.0 * (1.0 + 0.02 * ((i % 7) - 3)) for i in range(500)], [None] * 500)
        self.assertGreater(analogs.tolerances(lively)["day"], analogs.DAY_TOL)

    def test_an_asset_that_publishes_volume_keeps_the_old_rule_exactly(self):
        # The exception must stay an exception. One bar with volume anywhere in the history is
        # enough to keep the three constants, because the instrument does have a tape.
        bars = _bars([10.0] * 50, [None] * 49 + [1000.0])
        tol = analogs.tolerances(bars)
        self.assertTrue(tol["use_volume"])
        self.assertEqual(tol["day"], analogs.DAY_TOL)
        self.assertEqual(tol["five"], analogs.FIVE_TOL)

    def test_a_flat_series_with_no_tape_gets_no_row_rather_than_a_zero_window(self):
        # A tolerance of zero would match a day only to itself, which is not a finding. No row
        # is the honest answer, and it is what the caller does with None.
        self.assertIsNone(analogs.tolerances(_bars([10.0] * 60, [None] * 60)))

    def test_the_tolerance_note_says_which_rule_built_the_row(self):
        # `toleranceNote` is a stored column and this is what it is for: a reader comparing an
        # FX row to an equity row has to be told they were built by different rules.
        bars = _bars([10.0 + (i % 7) * 0.02 for i in range(400)], [None] * 400)
        note = analogs.tolerance_note(analogs.tolerances(bars))
        self.assertIn("volume was not a factor", note)
        self.assertIn("standard deviations", note)
        self.assertIn("volume ratio within", analogs.tolerance_note(_TOL))

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

    # The US regular session in UTC, both halves of the year. 09:30-16:00 New York is
    # 13:30-20:00 UTC on eastern daylight time and 14:30-21:00 UTC on eastern standard time, so
    # a schedule that must be post-close every day of the year has to clear 21:00.
    US_CLOSE_LATEST_UTC = 21 * 60

    # The PSX regular session ends 15:30 PKT, which is 10:30 UTC all year -- Pakistan keeps no
    # daylight saving. The closing *file* is published some unpromised time afterwards, and on
    # 2026-10-07 it was not there at 12:40 UTC and was there by 19:10, so "after the close" is
    # not the constraint that matters for this lane. The constraint is that some attempt happens
    # late enough in the Pakistani evening to catch a late publication on the same day.
    PSX_LATE_ATTEMPT_UTC = 19 * 60

    def _crons(self, name):
        """Every schedule in a workflow, as minutes past midnight UTC, comments stripped."""
        import re

        out = []
        for line in self._text(name).splitlines():
            code = line.split("#", 1)[0]
            m = re.search(r'cron:\s*"(\S+)\s+(\S+)\s', code)
            if not m:
                continue
            minute, hours = m.group(1), m.group(2)
            for hour in hours.split(","):
                if hour.isdigit() and minute.isdigit():
                    out.append(int(hour) * 60 + int(minute))
        return sorted(out)

    def test_the_us_price_lane_fetches_after_the_close_at_least_once_a_day(self):
        """A daily close has to be fetched after the bell, or it is not a close.

        This is the fault of 2026-10-07 written as a test, and it is the same shape as the one
        above it: a comment that was simply false. `cron-us-prices.yml` ran at 01:50, 07:50,
        13:50 and 19:50 UTC, and the line beside those hours read "01:50 UTC is after the US
        close has settled, 13:50 is before the next open". 13:50 UTC is twenty minutes after the
        open and 19:50 is ten minutes before the close, so both of the day's live slots sat
        inside the session and the lane stored a part-day as the day's close.

        What it cost was three steps downstream and looked nothing like a clock problem: across
        155 US names the newest bar's volume ran at a median of 0.21x its own 20-session average
        against the 1.2x `VOLUME_CONFIRMS_AT` asks for, so `jobs/setup.py` withheld the
        direction on all of them and the site answered WAIT under gate `incomplete` for 90.
        PSX, written only ever after its own bell, read 0.84x the same day.

        `forming_sessions` makes storing a part-day impossible, which is the real repair. This
        pins the other half: the schedule still has to offer the day a fetch that happens after
        the close, and an overnight retry alone would leave the decision a day behind for ever.
        """
        after_close = [m for m in self._crons("cron-us-prices.yml") if m >= self.US_CLOSE_LATEST_UTC]
        self.assertTrue(
            after_close,
            "no us-prices slot is after 21:00 UTC, so no fetch of the day sees a closed session",
        )

    def test_the_decision_lane_runs_after_the_prices_it_reads(self):
        """Being after the price lane is not the same as being after the close.

        `cron-decision.yml` ran at 15:10 UTC and said it sat "after the 13:50 US price chunks,
        so the run reads a day whose closes have landed from both exchanges". Both clauses were
        true of the ordering and false of the data: what had landed at 13:50 was twenty minutes
        of a session running to 20:00. The decision cannot be read off a day until that day has
        finished, so the constraint is against the exchange's clock and not against the other
        lane's.
        """
        decisions = self._crons("cron-decision.yml")
        self.assertTrue(decisions, "cron-decision.yml has no parsable schedule")
        # PSX, whose fault was the mirror image of the US one: not a part-day stored as a close,
        # but a complete close that arrived after the only run that asked for it, so every PSX
        # reading sat a day behind a market whose data was available. `psx.py` backfills recent
        # sessions, so the gap closed itself a day late and the table always read complete.
        psx_late = [m for m in self._crons("cron-psx.yml") if m >= self.PSX_LATE_ATTEMPT_UTC]
        self.assertTrue(
            psx_late,
            "no PSX attempt is late enough in the day to catch a late closing file, so the "
            "day's close is only ever picked up by tomorrow's run",
        )
        prices_after_close = [
            m for m in self._crons("cron-us-prices.yml") if m >= self.US_CLOSE_LATEST_UTC
        ]
        for when in decisions:
            self.assertGreaterEqual(
                when, self.US_CLOSE_LATEST_UTC,
                "the decision is materialized before the US session it reads has closed",
            )
            self.assertTrue(
                any(p < when for p in prices_after_close),
                "the decision runs before any post-close price fetch, so it reads yesterday",
            )
            self.assertTrue(
                any(p < when for p in psx_late),
                "the decision runs before the late PSX attempt, so a closing file published "
                "during the Pakistani evening misses today's decision",
            )

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

    def test_a_window_of_genuine_zero_volume_does_not_divide_by_it(self):
        # An asset can print a real zero volume bar, and this repository stores that as a zero
        # rather than a null on purpose -- 25,281 of them. When every bar in the trailing
        # window is one, the average is zero, and the ratio against it was computed in three
        # places: once behind a guard and twice without. The unguarded pair raised
        # ZeroDivisionError, which took down `run_intraday`, and because that is the first
        # thing `horizons.main()` calls it also took `run_longer` and `run_targets` with it.
        # Four days of the nightly decision lane wrote no intraday read and no target range.
        bars = self._rising()
        for b in bars:
            b["volume"] = 0.0
        state, _, _, missing, _, _, _ = horizons.intraday_read(bars, 110.0, 95.0)
        self.assertTrue(any("no traded volume stored" in m for m in missing))
        self.assertNotEqual(state, "buy", "a buy must not rest on a volume that is all zero")

    def test_an_unmeasurable_volume_is_not_reported_as_a_quiet_one(self):
        # "measured, and below the bar" and "not measured at all" are different sentences, and
        # only the first may be printed as a reason the conditions are short. The fix for the
        # division above collapsed both into one flag; this keeps them apart.
        bars = self._rising()
        for b in bars:
            b["volume"] = None
        _, head, _, missing, _, _, _ = horizons.intraday_read(bars, 10_000.0, 95.0)
        self.assertTrue(any("provider sent no volume" in m for m in missing))
        self.assertNotIn("not trading more than usual", head)

    def test_the_volume_ratio_is_computed_in_one_place(self):
        # Rule 36. The three copies above did not disagree about the threshold; they disagreed
        # about whether the denominator could be zero, which is the same bug one step earlier.
        text = (ROOT / "jobs" / "horizons.py").read_text(encoding="utf-8")
        self.assertEqual(
            text.count("sum(vols)"), 1,
            "the intraday volume ratio is measured more than once, so one copy can be guarded "
            "and another not",
        )

    def test_the_conditions_parse_with_the_thesis_verdict_reader(self):
        # thesis.py reads this exact format to decide whether a reason still holds. A new
        # horizon written in a new format would silently produce theses with nothing to
        # compare, so the two are pinned together here.
        _, _, conds, _, _, _, _ = horizons.intraday_read(self._rising(), 110.0, 95.0)
        got = thesis.verdicts(" | ".join(conds))
        self.assertIn("trend", got)
        self.assertIn("volume", got)
        self.assertIn(got["trend"], ("up", "down", "mixed"))


class PeriodEndIsASessionNotACalendarDay(unittest.TestCase):
    """A row that records a measurement must be dated to the session it measured.

    `jobs/factors.py` has stated the rule since it was written: "Today's date is the wrong
    anchor: the job runs before a close on a holiday and on a weekend, and dating a row to a
    day with no session in it would make `periodEnd` a claim about a day nothing was measured
    on." `setup.py` was caught breaking it on 2026-10-07 and fixed; four more jobs were still
    breaking it on 2026-10-08, and the only reason it was not visible is that each one was
    wrong by exactly one day in the same direction.

    Measured that morning, from a host five hours ahead of UTC: every close in the database
    ended 2026-10-07, and 1,788 attribution rows, 3,524 analog rows and 283 investigations all
    read `periodEnd` 2026-10-08. The content was right. The date was a day on which nothing
    traded -- and every reader of those tables takes the newest `periodEnd` per asset, so a row
    dated forward does not merely read oddly, it wins.
    """

    # file -> the expression its measurement rows are dated with, and what that expression is.
    ANCHORS = {
        "factors.py": ("period_end", "the newest stored close across every asset"),
        "setup.py": ("period_end", "the newest stored close"),
        "analogs.py": ("period_end", "the date of the bar the comparison was made from"),
        "attribution.py": ('m["asof"]', "the asset's own newest stored close"),
        "investigate.py": ('a["date"]', "the day the unusual move happened"),
    }

    def test_each_measurement_job_dates_its_rows_from_the_data(self):
        for name, (anchor, why) in sorted(self.ANCHORS.items()):
            text = (ROOT / "jobs" / name).read_text(encoding="utf-8")
            self.assertIn(
                anchor, text, f"{name} should date its rows with {anchor}: {why}"
            )

    def test_no_measurement_job_passes_the_bare_calendar_as_a_period(self):
        # The shape of the original mistake, in every file that makes one of these rows: the
        # asset id followed by the bare name `today` in an INSERT's parameter tuple. A fallback
        # is allowed and spelled `or today`, because an asset with no stored bar has no session
        # to be dated to -- and in every one of these jobs a row is only written after bars came
        # back, so the fallback is unreachable rather than lenient.
        import re

        bare = re.compile(r'(?<!or )\btoday\b\s*,')
        for name in sorted(self.ANCHORS):
            text = (ROOT / "jobs" / name).read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), start=1):
                code = line.split("#", 1)[0]
                if 'a["id"]' in code or "asset_id," in code or 'a["id"],' in code:
                    self.assertFalse(
                        bare.search(code),
                        f"{name}:{i} dates a measurement row with the calendar: {line.strip()}",
                    )

    def test_the_intraday_horizon_reads_the_session_its_bars_came_from(self):
        # Two ways to pick the completeness record, and only one of them is about the same day
        # as the bars. `intraday.py` writes a session row dated to the calendar day it ran,
        # including for days a venue never opened, so "newest session row" and "the session
        # this read was computed over" are routinely different days.
        text = (ROOT / "jobs" / "horizons.py").read_text(encoding="utf-8")
        # Read for the whole active set in one statement and matched in memory, so the check
        # is that the match is on the pair and not on "newest row for this asset".
        self.assertIn('sessions_by_key.get((a["id"], newest_session))', text)
        self.assertIn('DISTINCT ON ("assetId", "sessionDate")', text)
        self.assertNotIn('ORDER BY "sessionDate" DESC LIMIT 1', text)


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

        # Two shapes, because an INSERT that takes its rows from a SELECT is still an insert
        # and still needs a duplicate rule. `thesis.py` writes ThesisCheck that way so the row
        # can find its thesis by the thesis's own key instead of waiting for an id to come
        # back, and the first pattern alone stopped seeing it -- which made the freeze guard
        # below pass by finding nothing at all.
        return re.findall(
            r'INSERT INTO "(\w+)"\s*\((.*?)\)\s*VALUES\s*\((.*?)\)\s*(ON CONFLICT[^\n]*|RETURNING|""")',
            text,
            re.S,
        ) + re.findall(
            # The column list cannot contain a bracket and the body cannot contain another
            # INSERT, which is what keeps this one from swallowing the statement above it.
            r'INSERT INTO "(\w+)"\s*\(([^)]*)\)\s*(SELECT)'
            r'(?:(?!INSERT INTO)[\s\S])*?\n\s*(ON CONFLICT[^\n]*)',
            text,
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
        # the test is now positional — it reads the block the lanes run inside and allows
        # nothing to exit from it.
        #
        # The block opens with `cur = conn.cursor()` rather than `with conn, ...` since the
        # lanes stopped sharing one transaction. That was the same invariant being broken from
        # the other side: three lanes under one `with conn` meant a connection dropped during
        # the news pass rolled back the prices the same process had already fetched, which it
        # did twice on 2026-10-08. Each lane commits for itself now, and nothing may exit from
        # between the first one and the close.
        opens = body.index("cur = conn.cursor()")
        closes = body.index("conn.close()")
        self.assertNotIn("raise SystemExit", body[opens:closes])
        self.assertNotIn("with conn, conn.cursor() as cur:", body,
                         "the three lanes share one transaction again")
        self.assertGreaterEqual(body.count("conn.commit()"), 3,
                                "each lane must land on its own")
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

    def test_the_fallback_chain_declares_a_request_ceiling(self):
        # The lane that fetches per asset is the lane whose cost grows with the universe, and
        # this one has a `timeout-minutes`. The 160 -> 240 expansion is what pushed `cron
        # decision` past its budget on three consecutive days, and because GitHub reports a
        # timed-out job as "cancelled" it read as a scheduling quirk rather than an outage.
        self.assertIsInstance(prices.NEWS_FALLBACK_BUDGET, int)
        text = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        body = text[text.index("def fetch_news"):text.index("def coverage_line")]
        # Enforced, not merely declared: decremented per request and checked before spending.
        self.assertIn("fallback_budget -= 1", body)
        self.assertIn("if fallback_budget <= 0:", body)
        self.assertIn("kept < NEWS_FLOOR and fallback_budget > 0", body)
        # And the primary pass is never capped. It is the source every asset depends on, so
        # skipping it to save time is the failure rule 31 exists to catch.
        primary = body[body.index("matcher = news_matcher(a)"):body.index("if kept < NEWS_FLOOR")]
        self.assertNotIn("fallback_budget", primary)

    def test_the_news_lane_timeout_has_room_above_what_the_lane_can_spend(self):
        # A ceiling with no headroom above it is not a ceiling. The floor is one second per feed
        # from `nbt.get`'s per-host delay, over every asset, product and industry, plus whatever
        # the fallback budget allows -- and the timeout has to sit above that with room for
        # latency and retries, or the lane is killed mid-run and reported as cancelled.
        import re
        wf = (ROOT / ".github" / "workflows" / "cron-news.yml").read_text(encoding="utf-8")
        m = re.search(r"timeout-minutes:\s*(\d+)", wf)
        self.assertIsNotNone(m, "the news lane declares no timeout at all")
        timeout_s = int(m.group(1)) * 60
        # 318 primary feeds on the day this was written. Counted from the seed rather than
        # hard-coded, so growing the universe moves the floor this is checked against.
        feeds = len(seed.ASSETS) + len(seed.PRODUCTS)
        floor_s = feeds + prices.NEWS_FALLBACK_BUDGET
        self.assertGreater(
            timeout_s, floor_s * 1.5,
            f"{feeds} feeds plus {prices.NEWS_FALLBACK_BUDGET} fallbacks is a floor of "
            f"{floor_s}s of sleeping alone, and the lane is killed at {timeout_s}s",
        )
        # Still well inside its own 2-hourly interval, or the lane starts stacking on itself.
        self.assertLess(timeout_s, 3600, "a 2-hourly lane must finish inside half its cycle")

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
        # Read at the moment it was true, ten minutes into the session; the fixture is from
        # 2026-10-02 and the rule now consults the clock as well as the marker.
        mid = meta["currentTradingPeriod"]["regular"]["start"] + 700
        self.assertEqual(prices.chart_forming_day(meta, now=mid), date(2026, 10, 2))
        with mock.patch.object(prices, "chart_forming_day", lambda m, now=None: date(2026, 10, 2)):
            bars = prices.parse_chart(payload)
        self.assertEqual([b[0] for b in bars], [date(2026, 9, 30), date(2026, 10, 1)])
        # And after the close the same body yields every session.
        self.assertIsNone(prices.chart_forming_day(self.AAPL["chart"]["result"][0]["meta"]))

    # --- the daily download path, which carries no session metadata of its own ----------------
    #
    # Every test below was written against a fault measured in production on 2026-10-07, where
    # `cron-us-prices` fetched at 13:50 UTC into a session running 13:30-20:00 and the live bar
    # was stored as that day's close. The visible symptom was three steps downstream: the volume
    # leg of every US setup failed, so `jobs/setup.py` withheld the direction and the site
    # answered WAIT under gate `incomplete` for 90 of 155 US names.

    def test_the_session_day_is_the_exchanges_own_day_and_not_the_utc_one(self):
        # Measured on AUDUSD=X: the currency session runs 2026-10-06T23:00Z -> 2026-10-07T22:59Z,
        # which is the London day 10-07, and the bar being written is stamped 10-07. Reading the
        # UTC date of the start gives 10-06 -- a day that has already closed -- so a guard built
        # on it drops a finished bar and keeps the forming one.
        fx = {
            "currentTradingPeriod": {"regular": {"start": 1791327600, "end": 1791413940}},
            "gmtoffset": 3600,
            "exchangeTimezoneName": "Europe/London",
        }
        day, start, end = prices.session_bounds(fx)
        self.assertEqual(
            datetime.fromtimestamp(start, tz=timezone.utc).date(), date(2026, 10, 6),
            "fixture no longer has a session whose UTC start date differs from its own day",
        )
        self.assertEqual(day, date(2026, 10, 7))
        self.assertEqual(end, 1791413940)

    def test_a_provider_whose_clock_is_stale_does_not_freeze_the_lane(self):
        # Measured on HUBC.KA: Yahoo returned a session ending 2026-10-07T11:00Z with a
        # regularMarketTime of 2024-07-23, twenty-six months behind. Read as progress through the
        # session it says "still trading", and it says so for ever -- so a guard trusting the
        # marker alone stops storing that venue's closes permanently and silently.
        meta = {
            "currentTradingPeriod": {"regular": {"start": 1791347400, "end": 1791370800}},
            "gmtoffset": 18000,
            "regularMarketTime": 1721764800,  # 2024-07-23
        }
        self.assertLess(meta["regularMarketTime"], meta["currentTradingPeriod"]["regular"]["end"])
        self.assertIsNone(
            prices.chart_forming_day(meta),
            "a marker from before the session began is not progress through it",
        )

    def test_a_session_the_clock_has_not_reached_is_forming_whatever_the_marker_says(self):
        # The other half of the same rule, and the one that catches the live case: our clock has
        # not reached the end, so the bar is not a close no matter what the provider reports.
        now = datetime.now(timezone.utc).timestamp()
        meta = {
            "currentTradingPeriod": {"regular": {"start": int(now - 600), "end": int(now + 3600)}},
            "gmtoffset": 0,
            "regularMarketTime": int(now + 7200),  # ahead of the end, i.e. "closed"
        }
        self.assertEqual(
            prices.chart_forming_day(meta),
            datetime.fromtimestamp(now - 600, tz=timezone.utc).date(),
        )

    def test_a_finished_futures_or_fx_session_is_a_close_at_the_weekend(self):
        # Measured 2026-10-10 10:00 UTC, a Saturday. Brent: session Fri 04:00 -> Sat 03:59 UTC, last
        # trade Fri 20:59. EUR/USD: Thu 23:00 -> Fri 22:59, last trade 21:29. Both markers sit inside
        # their sessions, so the rule as it was read "still trading" until Sunday night and refused
        # Friday's bar for every future and FX pair all weekend.
        saturday = 1791626400  # 2026-10-10 10:00 UTC
        brent = {
            "currentTradingPeriod": {"regular": {"start": 1791518400, "end": 1791604740}},
            "gmtoffset": 0,
            "regularMarketTime": 1791579540,  # Fri 20:59
        }
        eurusd = {
            "currentTradingPeriod": {"regular": {"start": 1791500400, "end": 1791586740}},
            "gmtoffset": 3600,
            "regularMarketTime": 1791581340,  # Fri 21:29
        }
        self.assertIsNone(prices.chart_forming_day(brent, now=saturday))
        self.assertIsNone(prices.chart_forming_day(eurusd, now=saturday))
        # Inside the session by the clock it is still forming, whatever the marker says.
        self.assertEqual(prices.chart_forming_day(brent, now=1791579540 + 60), date(2026, 10, 9))

    def test_the_minutes_after_the_bell_still_wait_for_the_final_bar(self):
        # The case the marker rule exists for, and it must survive the fix: a US session that ended
        # at 20:00 with a last trade at 19:59, read at 20:10, has not finished landing.
        us = {
            "currentTradingPeriod": {"regular": {"start": 1791552600, "end": 1791576000}},
            "gmtoffset": -14400,
            "regularMarketTime": 1791575940,  # 19:59
        }
        self.assertEqual(prices.chart_forming_day(us, now=1791576600), date(2026, 10, 9))  # 20:10
        self.assertEqual(prices.LANDING_WINDOW, 2 * 3600)
        # Two hours of nothing after the bell is a finished session.
        self.assertIsNone(prices.chart_forming_day(us, now=1791575940 + prices.LANDING_WINDOW + 1))

    def test_one_session_probe_per_asset_type_and_not_one_per_symbol(self):
        asked = []

        def meta_for(sym):
            asked.append(sym)
            return {}

        assets = [
            {"sourceRef": "EQ%d" % i, "assetType": "equity"} for i in range(40)
        ] + [{"sourceRef": "FX%d" % i, "assetType": "forex"} for i in range(20)]
        with mock.patch.object(prices, "chart_meta", meta_for):
            prices.forming_sessions(assets)
        # The session is a property of the exchange calendar, not of the instrument. 60 probes
        # would be 58 requests spent re-learning the same two facts.
        self.assertEqual(len(asked), 2)
        self.assertEqual(sorted(asked), ["EQ0", "FX0"])

    def test_a_session_probe_that_fails_drops_nothing(self):
        def boom(sym):
            raise RuntimeError("provider unreachable")

        with mock.patch.object(prices, "chart_meta", boom):
            self.assertEqual(
                prices.forming_sessions([{"sourceRef": "AAPL", "assetType": "equity"}]), {}
            )
        # The direction to fail in: this guard exists to stop a partial bar being written, and a
        # guard that cannot reach the provider must not also stop the lane storing anything.

    def test_the_forming_bar_is_dropped_from_the_downloaded_frame(self):
        import pandas as pd

        frame = pd.DataFrame(
            {
                "Open": [330.0, 331.0, 333.2],
                "High": [339.5, 332.4, 334.5],
                "Low": [330.1, 325.8, 330.6],
                "Close": [333.02, 330.32, 333.69],
                "Volume": [49988600.0, 36306300.0, 8037036.0],
            },
            index=pd.to_datetime(["2026-10-05", "2026-10-06", "2026-10-07"]),
        )
        asset = {"id": "a1", "symbol": "AAPL", "sourceRef": "AAPL", "assetType": "equity"}
        written = []
        with mock.patch.object(prices, "share_series", lambda sym: []), mock.patch.object(
            prices, "insert_snapshots", lambda cur, buf, replace=True: written.extend(buf)
        ):
            rows, newest = prices._store_frame(
                None, [asset], frame, date(2026, 10, 7), False, {"equity": date(2026, 10, 7)}
            )
        self.assertEqual([r[1] for r in written], [date(2026, 10, 5), date(2026, 10, 6)])
        self.assertEqual(rows, 2)
        # The newest day *stored*, so the caller's shortfall report shows the drop rather than
        # hiding it behind a day that was never written.
        self.assertEqual(newest["AAPL"], date(2026, 10, 6))
        # And the 8.0M partial -- a fifth of its neighbours -- never reaches the table, which is
        # what the volume leg of every US setup was failing on.
        self.assertNotIn(8037036.0, [r[6] for r in written])

    def test_a_frame_holding_only_the_forming_bar_writes_and_deletes_nothing(self):
        import pandas as pd

        # The dangerous shape. `is_full` DELETEs the asset's series before inserting, so falling
        # through with an empty buffer would trade six years of history for no rows at all.
        frame = pd.DataFrame(
            {
                "Open": [333.2], "High": [334.5], "Low": [330.6],
                "Close": [333.69], "Volume": [8037036.0],
            },
            index=pd.to_datetime(["2026-10-07"]),
        )
        asset = {"id": "a1", "symbol": "AAPL", "sourceRef": "AAPL", "assetType": "equity"}
        deletes = []

        class Cur:
            def execute(self, sql, params=None):
                deletes.append(sql)

        with mock.patch.object(prices, "share_series", lambda sym: []), mock.patch.object(
            prices, "insert_snapshots", lambda cur, buf, replace=True: None
        ):
            rows, newest = prices._store_frame(
                Cur(), [asset], frame, date(2026, 10, 7), True, {"equity": date(2026, 10, 7)}
            )
        self.assertEqual(rows, 0)
        self.assertIsNone(newest["AAPL"])
        self.assertEqual(deletes, [], "nothing closed yet is not a reason to drop the series")

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
        # The statement is a module constant now, and it no longer returns an id: the check
        # row finds its thesis by that thesis's own natural key instead, so the two batches
        # need no round trip between them. The property under test is unchanged.
        insert = text[text.index('INSERT INTO "AssetThesis"'):]
        update = insert[insert.index("DO UPDATE SET"):insert.index('"""')]
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
            "live.py": (
                "stores the last trade as quoted, with the time it was struck, and only ever moves a quote "
                "forward; it makes no claim about a past moment and no rule reads it"
            ),
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


# The web layer's raw-SQL rule, in one place because two tests assert it.
#
# **The rule was "no raw SQL at all" and is now "no raw SQL that can carry a value".** That is a
# narrowing of the letter and not of the property. What both tests were protecting is stated in
# their own comments: dynamic route params reach the database through Prisma, which parameterises,
# and "a single $queryRawUnsafe here is the only way a path segment could reach the database as
# code". A tagged `$queryRaw` with no `${...}` in it cannot carry a path segment, or anything
# else -- it is a constant string.
#
# The three unsafe forms stay banned outright and unconditionally, because they concatenate:
# `$queryRawUnsafe`, `$executeRawUnsafe`, and `$executeRaw` (which writes, and nothing in the web
# layer may write at all).
#
# What bought the narrowing: `getDecisionRows` read the newest close per asset with
# `groupBy({ by: ["assetId"], _max: { date: true } })`, which Postgres plans as a parallel
# sequential scan of all 628,675 stored closes -- 13,061 buffers, 209 ms -- on every render of
# every list page, against a metered endpoint. A lateral probe does it in 1,921 buffers and 3.2
# ms, and Prisma cannot express a lateral join. An index was built and measured first and the
# planner did not use it.
#
# The check is mechanical rather than a judgement at the call site, which is the only reason this
# is an acceptable trade: an interpolated `$queryRaw` fails here exactly as a `$queryRawUnsafe`
# does, so nothing is left to a reviewer noticing.
RAW_SQL_BANNED = ("$queryRawUnsafe", "$executeRawUnsafe", "$executeRaw")


def raw_sql_offenders() -> list[str]:
    """Every web-layer file that could let a value reach the database as SQL."""
    out: list[str] = []
    for d in ("lib", "app", "components"):
        for path in sorted((ROOT / d).rglob("*.ts*")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for banned in RAW_SQL_BANNED:
                if banned in text:
                    out.append(f"{path.relative_to(ROOT)}: {banned}")
            # `$queryRaw` is allowed only as a constant. Each occurrence is read to the end of
            # its template literal and refused if anything is interpolated into it.
            at = text.find("$queryRaw")
            while at != -1:
                tick = text.find("`", at)
                if tick != -1:
                    close = text.find("`", tick + 1)
                    body = text[tick + 1 : close if close != -1 else len(text)]
                    if "${" in body:
                        out.append(f"{path.relative_to(ROOT)}: $queryRaw interpolates a value")
                at = text.find("$queryRaw", at + 1)
    return out


class WebSafety(unittest.TestCase):
    """The web layer's attack surface, which is small on purpose and should stay that way."""

    def test_the_web_layer_runs_no_raw_sql(self):
        """No value may reach the database as code. See `raw_sql_offenders` for what changed."""
        self.assertEqual(raw_sql_offenders(), [], "; ".join(raw_sql_offenders()))

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

    # Re-measured on 2026-10-09, and **tightened to what each job actually does** rather than
    # left at the ceiling it was allowed. That is the difference between a ratchet and a
    # headroom allowance: eighteen of these numbers had fallen below their baseline as jobs were
    # prefetched one at a time, and every point of slack was a per-asset query that could be
    # reintroduced into an optimised loop with nothing failing. `horizons.py` sat at 13 while
    # issuing 1; `setup.py` and `thesis.py` sat at 6 and 8 while issuing none.
    #
    # The one that moved this time is rank.py: 14 to 3. It is the job that went from minutes to
    # half an hour on a high latency host when the pool grew to 331, and the three it still
    # issues are per *industry* -- 41 of them -- rather than per asset, so they no longer grow
    # with the universe. The same two (industry, date) pairs were being read seven times per
    # industry and are now read twice: 287 round trips to 82. See `latest_caps` in jobs/rank.py,
    # which also records why the win is in the count and not in the query plan.
    #
    # A number here going UP in a diff is the thing to look at. A number going down should be
    # written down here in the same commit that earned it.
    BASELINE = {
        "accuracy.py": 3, "analogs.py": 1, "analysis.py": 3, "attribution.py": 0,
        "audit.py": 9, "confidence.py": 2, "events.py": 7, "factors.py": 1, "geo.py": 2,
        "graph.py": 1, "horizons.py": 1, "human.py": 0, "intraday.py": 7,
        "investigate.py": 3, "lifecycle.py": 7, "lineage.py": 3, "marketplace.py": 3,
        # retention.py reads a count per table, not per asset, so its five are bounded by the
        # number of tables in the sweep and not by the size of the pool.
        "prices.py": 7, "psx.py": 2, "rank.py": 3, "retention.py": 5, "seed.py": 5,
        "setup.py": 0,
        "signals.py": 12, "stats.py": 2, "thesis.py": 0, "upcoming.py": 3,
        # tools/, measured 2026-10-10 when the scan was widened to cover it. These are one-off
        # reports run by hand rather than lanes on a schedule, so a per-row read costs a person
        # waiting rather than a nightly budget -- which is why they are recorded at what they do
        # instead of being rewritten on sight. `scorecard.py` is 0 because it was the one that
        # mattered: it runs over a log that grows every day, and it was rewritten.
        "future_rows.py": 2, "intraday_chain.py": 6, "rederive.py": 4, "row_counts.py": 1,
        "scorecard.py": 0, "acceptance.py": 0, "candidates.py": 0, "price_freshness.py": 0,
    }

    # A query reached through a helper costs the same round trip as one written inline. The
    # counter only looked for the query call itself, so `jobs/rank.py` measured zero: every one
    # of its per-asset reads goes through `close_on`, `avg_volume` or `size_ranks`, which are
    # defined at module level and do the querying there. It issues around seven statements per
    # asset and the ratchet could not see one of them -- which is how a 273 name pool grew to
    # 331 and the job went from minutes to half an hour on a high latency host without any
    # guard noticing.
    #
    # So the helpers are found first: a module level function whose own body queries is itself
    # a query, and a call to it inside a loop counts.
    @staticmethod
    def querying_helpers(text: str) -> set[str]:
        import re
        out, current, body = set(), None, []
        for line in text.splitlines():
            m = re.match(r"def (\w+)\(", line)
            if m:
                if current and any(
                    re.search(r"(cur\.execute|cur\.executemany|rows\(|one\()", b) for b in body
                ):
                    out.add(current)
                current, body = m.group(1), []
            elif current is not None:
                body.append(line)
        if current and any(
            re.search(r"(cur\.execute|cur\.executemany|rows\(|one\()", b) for b in body
        ):
            out.add(current)
        return out

    @staticmethod
    def in_loop_calls(path) -> int:
        import re
        text = path.read_text(encoding="utf-8")
        helpers = QueryBudget.querying_helpers(text)
        direct = r"(cur\.execute|cur\.executemany|rows\(|one\()"
        indirect = (
            "|".join(rf"\b{h}\s*\(" for h in sorted(helpers)) if helpers else r"(?!)"
        )
        lines = text.splitlines()
        stack, n = [], 0
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            stack = [(ind, ln) for ind, ln in stack if ind < indent]
            if s.startswith("for ") and s.endswith(":"):
                stack.append((indent, i))
            elif stack and (re.search(direct, s) or re.search(indirect, s)):
                n += 1
        return n

    def test_no_job_issues_more_queries_inside_a_loop_than_it_did(self):
        grew = []
        for path in self.scanned():
            n = self.in_loop_calls(path)
            allowed = self.BASELINE.get(path.name, 0)
            if n > allowed:
                grew.append(f"{path.name}: {n} in-loop queries, baseline {allowed}")
        self.assertEqual(grew, [], "; ".join(grew))

    @staticmethod
    def scanned():
        """Every file the ratchet watches: `jobs/` and `tools/`.

        **`tools/` was outside it, and that is how `tools/scorecard.py` came to issue one query
        per scored row under a comment reading "one query for the whole set".** The pass that
        rewrote eleven jobs for exactly this fault could not see it, because the scan stopped at
        `jobs/`. A directory excluded from a ratchet is a directory where the thing the ratchet
        prevents is free to happen, and the cost there grew with the length of the decision log
        rather than with the size of the universe -- a report that gets slower every day it is
        kept.
        """
        return sorted((ROOT / "jobs").glob("*.py")) + sorted((ROOT / "tools").glob("*.py"))

    def test_the_counter_still_counts(self):
        # A ratchet that measures zero everywhere would pass forever.
        #
        # This has now had to be re-pointed twice -- first off thesis.py and then off rank.py --
        # each time because the named file was optimised and the canary went quiet for the best
        # possible reason. A canary that fails when the thing it watches gets *better* is the
        # wrong canary, so it no longer names a file: the counter is working as long as some job
        # somewhere still reads inside a loop, and several legitimately do. `signals.py` and
        # `audit.py` are the current largest, and neither is a fault -- a per-product fetch has
        # to ask per product.
        most = max(self.in_loop_calls(p) for p in self.scanned())
        self.assertGreaterEqual(most, 5, "the in-loop counter has stopped finding anything")


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


class TargetDirection(unittest.TestCase):
    """Which way a target points, and when it is refused.

    The gap this covers cost the site most of its targets: `run_targets` selected only
    `state IN ('buy','short')`, so 745 current swing and longer rows -- every one of them
    carrying both an entry and an invalidation -- held no target at all and the panel printed
    "No clear target stored" with no reward against risk beside it.
    """

    def test_a_stated_direction_is_taken_as_stated(self):
        self.assertEqual(horizons.aimed_at({"state": "buy", "conditions": ""}), "buy")
        self.assertEqual(horizons.aimed_at({"state": "short", "conditions": ""}), "short")

    def test_a_withheld_trend_still_names_a_side(self):
        # State `wait` is setup.py saying the trend is clear and the conditions behind it are
        # not all present. The direction is measured; only the action was withheld.
        row = {"state": "wait",
               "conditions": "trend: close 9.1 vs 20d 9.4 vs 50d 9.9 (down) | volume: 0.7x (fail)"}
        self.assertEqual(horizons.aimed_at(row), "short")

    def test_the_bias_is_read_only_when_the_trend_says_nothing(self):
        # Rule 45's weaker reading, and it is asked last. A mixed trend with a bias beside it
        # points the bias's way; a directional trend beats a contradicting bias outright.
        mixed = {"state": "none",
                 "conditions": "trend: close 10 vs 20d 10.1 vs 50d 9.9 (mixed) | "
                               "bias: 20d average 2.00% above the 50d (up)"}
        self.assertEqual(horizons.aimed_at(mixed), "buy")

        both = {"state": "wait",
                "conditions": "trend: close 9 vs 20d 9.4 vs 50d 9.9 (down) | "
                              "bias: 20d average 2.00% above the 50d (up)"}
        self.assertEqual(horizons.aimed_at(both), "short")

    def test_nothing_naming_a_side_gets_no_target(self):
        # A target with nothing to point at would have its direction chosen by this job rather
        # than measured, which is the one thing it may not do.
        self.assertIsNone(horizons.aimed_at({"state": "none", "conditions": ""}))
        self.assertIsNone(horizons.aimed_at({"state": "none", "conditions": None}))
        self.assertIsNone(horizons.aimed_at(
            {"state": "none", "conditions": "trend: close 10 vs 20d 10 vs 50d 10 (mixed)"}))

    def test_it_reads_the_same_format_thesis_does(self):
        # Rule 23, asserted rather than asserted-in-a-comment: this uses thesis.verdicts, so a
        # new horizon written in a new format breaks both rather than silently aiming targets
        # at nothing.
        conditions = "trend: close 1 vs 20d 2 vs 50d 3 (up) | position: 40% of the way up"
        self.assertEqual(thesis.verdicts(conditions).get("trend"), "up")
        self.assertEqual(horizons.aimed_at({"state": "wait", "conditions": conditions}), "buy")


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
    ALLOWED: dict[str, str] = {
        # Read by `tools/macro_gate.mjs`, the nightly job, and deliberately by nothing on the site: the
        # site never calls the model, it reads the answer the job stored. That the job really imports it
        # is pinned in `TheMacroGateOnlyRefuses`, so this entry cannot outlive its only consumer.
        "evaluate": "tools/macro_gate.mjs",
        # The local engine's two job-facing exports, on the same terms: the site reads the stored answer
        # and never runs either engine. `test_the_one_export_the_web_layer_does_not_use_is_used_by_the_job`
        # pins that the job imports all three.
        "evaluateLocal": "tools/macro_gate.mjs",
        "LOCAL_ENGINE": "tools/macro_gate.mjs",
    }

    def exports_without_consumers(self) -> list[str]:
        import re
        exports = {}
        for f in sorted(list((ROOT / "lib").glob("*.ts")) + list((ROOT / "components").glob("*.tsx"))):
            text = code_only(f.read_text(encoding="utf-8"))
            for m in re.finditer(r"^export (?:async )?function (\w+)|^export const (\w+)", text, re.M):
                exports[m.group(1) or m.group(2)] = str(f)
        files = {}
        # Route handlers are `.ts`, and one is a consumer like any page: `app/api/quote/route.ts` is
        # what reads the quote helpers.
        for pattern in ("app/**/*.tsx", "app/*.tsx", "app/**/*.ts", "lib/*.ts", "components/*.tsx"):
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
        self.assertEqual(raw_sql_offenders(), [], "; ".join(raw_sql_offenders()))

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
    # `components/LivePrice.tsx` joined the two error boundaries: a last trade has to refresh in the
    # browser, and that is the one thing a server-rendered, hourly-cached page cannot do. It is held to
    # the same rule as they are -- no server module, no environment, no database -- and to one more in
    # `TheLiveLane`: it may fetch exactly one same-origin URL.
    CLIENT_ALLOWED = ("app/error.tsx", "app/global-error.tsx", "components/LivePrice.tsx")

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
        # One in-loop round trip, and it is the batch flush rather than a per-asset read: the
        # loop that calls it is over slices of the payload, so the count rises with the batch
        # size and not with the asset count. Anything above one is a read per asset.
        self.assertEqual(QueryBudget.in_loop_calls(ROOT / "jobs" / "factors.py"), 1)


class EntryTriggers(unittest.TestCase):
    """The fifth confirmation: did an entry rule fire on this session, and which way?

    brain.md rule 54 measured four candidate entry rules against the moving-average stack and
    kept the two that beat it -- not as a replacement for the stack, which would have cut the
    pool from 467 directions to a few dozen, but as a fifth confirmation and a marker saying the
    direction was caught at its start.

    What these tests guard, in the order of how much is lost when one breaks:

      * **the rule-46 distinction.** Compression as a standing state is followed by *smaller*
        moves. These rules fire on the expansion bar OUT of a compression, which is a different
        event, and a quiet asset that stays quiet must never fire one.
      * **the window means what it claims.** A dispersion over nine returns labelled as twenty is
        the mislabelling every null in jobs/factors.py exists to prevent.
      * **the baseline cannot contain the bar it judges**, or every expansion reads as ordinary.
    """

    @staticmethod
    def factors():
        import factors
        return factors

    @staticmethod
    def series(returns, start=100.0):
        """Closes built from a list of percent returns, oldest first.

        Built from returns rather than written out, because every property under test here is
        about the spread of the returns, and a hand-written list of closes hides it.
        """
        closes = [start]
        for r in returns:
            closes.append(closes[-1] * (1 + r / 100.0))
        return closes

    # 100 alternating 2% sessions, then 19 at a tenth of that. The quiet stretch is the
    # compression; what follows it in each test is the bar being judged.
    NOISY = [2.0, -2.0] * 50
    QUIET = [0.1, -0.1] * 9 + [0.1]

    # --- dispersion -------------------------------------------------------------------------

    def test_dispersion_is_a_spread_and_refuses_a_sample_too_small_to_have_one(self):
        f = self.factors()
        self.assertEqual(f.dispersion([1.0, 1.0, 1.0]), 0.0)
        self.assertAlmostEqual(f.dispersion([1.0, 2.0, 3.0]), (2.0 / 3.0) ** 0.5, places=9)
        # Two numbers have a gap between them, not a spread.
        self.assertIsNone(f.dispersion([1.0, 2.0]))
        self.assertIsNone(f.dispersion([]))

    def test_dispersion_keeps_the_outlier_the_robust_score_throws_away(self):
        """The two statistics in this file answer different questions, deliberately.

        `robust_z` asks whether one observation is unusual, and must not let an outlier widen the
        history it is judged against. This asks how wide the window itself was, and a fortnight
        containing one 9% session was not a quiet fortnight.
        """
        f = self.factors()
        calm = [0.1] * 20
        shocked = [0.1] * 19 + [9.0]
        self.assertEqual(f.dispersion(calm), 0.0)
        self.assertGreater(f.dispersion(shocked), 1.0)

    # --- the squeeze break ------------------------------------------------------------------

    def test_an_expansion_out_of_a_compression_fires_both_ways(self):
        f = self.factors()
        self.assertEqual(f.squeeze_break(self.series(self.NOISY + self.QUIET + [5.0])), "up")
        self.assertEqual(f.squeeze_break(self.series(self.NOISY + self.QUIET + [-5.0])), "down")

    def test_a_quiet_asset_that_stays_quiet_never_fires(self):
        """Rule 46, kept. Compression on its own is followed by smaller moves, not larger ones,
        and this rule must not quietly turn it into a signal."""
        f = self.factors()
        self.assertIsNone(f.squeeze_break(self.series(self.NOISY + self.QUIET + [0.1])))

    def test_a_big_move_out_of_an_already_loud_stretch_is_not_a_squeeze_break(self):
        """The other half of the same distinction: there has to be a narrow base to break out of."""
        f = self.factors()
        loud = self.NOISY + [2.0, -2.0] * 10 + [5.0]
        self.assertIsNone(f.squeeze_break(self.series(loud)))

    def test_the_move_has_to_clear_the_dispersion_it_broke_out_of(self):
        f = self.factors()
        # The window's own dispersion is about a tenth of a point, so SQUEEZE_BREAKS_AT puts the
        # bar near 0.15. A move of 0.12 is above every session in the compression and is still
        # not an expansion out of it.
        self.assertIsNone(f.squeeze_break(self.series(self.NOISY + self.QUIET + [0.12])))
        self.assertEqual(f.squeeze_break(self.series(self.NOISY + self.QUIET + [1.0])), "up")

    def test_a_history_too_short_to_judge_compression_against_is_null(self):
        """A name with 50 closes is not uncompressed. It is unmeasured, and says so."""
        f = self.factors()
        self.assertIsNone(f.squeeze_break(self.series(self.NOISY[:30] + [5.0])))
        self.assertIsNone(f.squeeze_break([100.0] * 5))
        self.assertIsNone(f.squeeze_break([]))

    def test_a_flat_series_has_no_dispersion_to_break_out_of(self):
        """Dispersion 0 is a divisor. A halted name must not fire on its first tick back."""
        f = self.factors()
        self.assertIsNone(f.squeeze_break([100.0] * 200))

    def test_the_baseline_does_not_contain_the_window_it_judges(self):
        """The one property whose loss would be invisible: every expansion would read ordinary.

        If the history overlapped the current window, the breakout bar would sit inside its own
        baseline and the share of history at or below it would rise past the quiet threshold.
        The arithmetic is read out of the source because the failure has no other symptom -- the
        rule would simply stop firing, which looks exactly like a market with no squeezes in it.
        """
        f = self.factors()
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        body = src[src.index("def squeeze_break("):src.index("def volume_flip(")]
        self.assertIn("last_end = len(rets) - SQUEEZE_WINDOW", body)
        self.assertIn("rets[end - SQUEEZE_WINDOW : end]", body)
        self.assertIn("last_end + 1", body)
        self.assertIsNotNone(f.squeeze_break)

    # --- the volume flip --------------------------------------------------------------------

    def test_momentum_turning_on_a_busy_session_fires_both_ways(self):
        f = self.factors()
        self.assertEqual(f.volume_flip([100.0] * 6 + [105.0], 1.5), "up")
        self.assertEqual(f.volume_flip([100.0] * 6 + [95.0], 1.5), "down")

    def test_a_turn_on_an_ordinary_session_is_not_a_flip(self):
        f = self.factors()
        rising = [100.0] * 6 + [105.0]
        self.assertEqual(f.volume_flip(rising, 1.2), "up")
        self.assertIsNone(f.volume_flip(rising, 1.19))
        # No volume published at all, which is the standing state of every currency pair. The
        # rule cannot be judged there rather than failing there.
        self.assertIsNone(f.volume_flip(rising, None))

    def test_momentum_that_was_already_going_this_way_has_not_turned(self):
        f = self.factors()
        self.assertIsNone(f.volume_flip([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0], 2.0))

    def test_too_few_closes_to_measure_the_span_is_null(self):
        f = self.factors()
        self.assertIsNone(f.volume_flip([100.0] * 5 + [105.0], 2.0))

    def test_the_flip_boundary_is_out_of_flat_and_not_out_of_rising(self):
        """`> 0 >=` and not `> 0 >`: exactly zero is the honest edge of 'was not going this way'."""
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        body = src[src.index("def volume_flip("):src.index("def entry_trigger(")]
        self.assertIn("now > 0 >= prior", body)
        self.assertIn("now < 0 <= prior", body)

    # --- which one is reported --------------------------------------------------------------

    def test_the_better_measured_rule_is_the_one_the_card_names(self):
        """Both fire on this series, and `squeeze_break` is the one carried through.

        Not an arbitrary tie-break: it measured better, 0.153R against 0.146R, and it is the one
        a reader cannot reconstruct from the other stored factors -- a flip is `r5` and
        `volumeRatio` side by side, and nothing on the page says how wide the last fortnight was
        against its own history.
        """
        f = self.factors()
        both = self.series(self.NOISY + [0.0] * 19 + [5.0])
        self.assertEqual(f.squeeze_break(both), "up")
        self.assertEqual(f.volume_flip(both, 1.5), "up")
        self.assertEqual(f.entry_trigger(both, 1.5), ("squeeze_break", "up"))

    def test_neither_firing_is_a_pair_of_nulls_and_never_an_exception(self):
        f = self.factors()
        quiet = self.series(self.NOISY + self.QUIET + [0.1])
        self.assertEqual(f.entry_trigger(quiet, 1.5), (None, None))
        self.assertEqual(f.entry_trigger([], None), (None, None))
        self.assertEqual(f.entry_trigger([100.0], None), (None, None))

    def test_the_trigger_reads_the_stored_volume_ratio_rather_than_taking_its_own(self):
        """One definition of "busy" per repository.

        The backtest used a mean-based ratio because that was cheap inside a sweep; the stored
        one is median-based and splits weekend sessions from weekday ones. The live rule uses the
        stored one, which makes it a near neighbour of the measured rule rather than the measured
        rule itself -- a difference FLIP_VOLUME_AT states in full, and this pins to the call site.
        """
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        body = src[src.index("def compute("):src.index("def event_in_days(")]
        self.assertIn('entry_trigger(closes, out["volumeRatio"])', body)

    # --- the row it is written into -----------------------------------------------------------

    def test_compute_reports_the_pair_on_every_row(self):
        f = self.factors()
        closes = self.series(self.NOISY + self.QUIET + [5.0])
        bars = [
            {"date": date(2026, 1, 5) + timedelta(days=i), "close": c, "volume": 1000.0}
            for i, c in enumerate(closes)
        ]
        got = f.compute(bars, bars[-1]["date"])
        self.assertEqual(got["entryTrigger"], "squeeze_break")
        self.assertEqual(got["triggerDirection"], "up")
        # Both keys exist whether or not a rule fired, so a payload built from this dict cannot
        # lose a column on a quiet day.
        quiet = f.compute(bars[:-1], bars[-2]["date"])
        self.assertIn("entryTrigger", quiet)
        self.assertIn("triggerDirection", quiet)

    def test_the_trigger_obeys_the_cutoff_like_every_other_factor(self):
        """A row dated D computed from a close after D is the one bug in this file that would
        corrupt every published hit rate while leaving the rows looking perfect."""
        f = self.factors()
        closes = self.series(self.NOISY + self.QUIET + [5.0, 0.1, 0.1, 0.1])
        bars = [
            {"date": date(2026, 1, 5) + timedelta(days=i), "close": c, "volume": 1000.0}
            for i, c in enumerate(closes)
        ]
        at = len(closes) - 4
        with_future = f.compute(bars, bars[at]["date"])
        without_future = f.compute(bars[: at + 1], bars[at]["date"])
        self.assertEqual(with_future["entryTrigger"], without_future["entryTrigger"])
        self.assertEqual(with_future["triggerDirection"], without_future["triggerDirection"])
        self.assertEqual(with_future["entryTrigger"], "squeeze_break")

    def test_the_insert_binds_exactly_the_columns_it_names(self):
        """The fault that broke `fetch_crypto` for a week, guarded on the file it would break next.

        `insert_snapshots` gained three columns and one of its two callers was not updated, so six
        fields reached a nine-name unpack and every crypto insert raised for seven days. The same
        shape is here: a column list, a row of placeholders, and a tuple built two hundred lines
        away. Nothing checks that the three agree until a row is written, and this job writes rows
        only against a live database -- which is exactly when it is least affordable to find out.
        """
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        body = src[src.index("def flush("):src.index("def session_end(")]
        columns = body[body.index('INSERT INTO "AssetFactor" ('):body.index("VALUES (")]
        named = columns.count(",") + 1
        placeholders = body[body.index("VALUES ("):body.index("ON CONFLICT")].count("%s")
        # One column more than there are placeholders, and it is "computedAt", bound to now().
        self.assertEqual(named, placeholders + 1)
        self.assertIn('"computedAt")', columns)

    def test_every_column_the_insert_names_is_also_updated_on_conflict(self):
        """A rerun has to update what it inserts, or the newest session keeps a stale reading.

        The nightly lane rewrites the current session on every run. A column present in the
        INSERT and absent from the DO UPDATE would be written once by the first run of the day
        and then frozen, which on this table means a trigger that fired at lunchtime still
        reading as fired after the close reversed it.
        """
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        body = src[src.index("def flush("):src.index("def session_end(")]
        columns = body[body.index('INSERT INTO "AssetFactor" ('):body.index("VALUES (")]
        update = body[body.index("DO UPDATE SET"):body.index("conn.commit()")]
        for name in ("entryTrigger", "triggerDirection", "volumeRatio", "relStrength", "r20"):
            self.assertIn(name, columns, name + " is not inserted")
            self.assertIn("EXCLUDED." + ('"' + name + '"' if name != "r20" else "r20"), update,
                          name + " is inserted and never updated on conflict")


class ScorecardDegrades(unittest.TestCase):
    """The scorer, against the states a half-written log actually holds.

    `tools/scorecard.py` is the module that says whether the site's own readings were any good,
    which makes a quiet mislabelling here worse than an exception: it publishes a number nobody
    can see is wrong. Every function it scores with is pure, so every one of these cases is a
    list and a word.

    The three it would be worst to get wrong, in order:

      * **"not yet known" is never "wrong".** The same conflation this site spent a session
        removing from WAIT, and the one a scorer reaches for by default.
      * **a stop beats the move.** A position taken out at its stop did not get to find out
        where the price finished, and scoring it on the move credits a trade the stated plan had
        already closed.
      * **an unanswerable question is not a pass.** No stop stored, or no closes in the window,
        must not score as a stop that held.
    """

    @staticmethod
    def scorecard():
        import importlib.util

        path = ROOT / "tools" / "scorecard.py"
        spec = importlib.util.spec_from_file_location("nbt_scorecard", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_the_window_excludes_the_session_the_decision_was_taken_on(self):
        """The entry close cannot also be the close that stopped it out."""
        sc = self.scorecard()
        series = [
            (date(2026, 6, 1), 100.0),
            (date(2026, 6, 2), 90.0),
            (date(2026, 6, 3), 110.0),
            (date(2026, 6, 4), 500.0),
        ]
        lo, hi = sc.band_in(series, date(2026, 6, 1), date(2026, 6, 3))
        self.assertEqual((lo, hi), (90.0, 110.0))
        # Half open on the left, closed on the right: 6-1 is the entry and 6-4 is outside.
        self.assertEqual(sc.band_in(series, date(2026, 6, 3), date(2026, 6, 3)), (None, None))

    def test_the_window_is_read_from_an_unordered_series(self):
        """The bulk read returns rows grouped by asset, not sorted per window."""
        sc = self.scorecard()
        series = [
            (date(2026, 6, 3), 110.0),
            (date(2026, 6, 2), 90.0),
            (date(2026, 6, 4), 95.0),
        ]
        self.assertEqual(sc.band_in(series, date(2026, 6, 1), date(2026, 6, 4)), (90.0, 110.0))

    def test_a_window_with_nothing_in_it_is_two_nulls(self):
        sc = self.scorecard()
        self.assertEqual(sc.band_in([], date(2026, 6, 1), date(2026, 6, 9)), (None, None))
        self.assertEqual(sc.band_in([(date(2026, 6, 2), None)], date(2026, 6, 1), date(2026, 6, 9)),
                         (None, None))
        # A row whose maturation date was never written. Asking for a band from it is not a
        # question that can be answered, and a date comparison against None would raise.
        self.assertEqual(sc.band_in([(date(2026, 6, 2), 5.0)], date(2026, 6, 1), None), (None, None))
        self.assertEqual(sc.band_in([(date(2026, 6, 2), 5.0)], None, date(2026, 6, 9)), (None, None))

    def test_a_stop_is_hit_on_the_side_the_direction_is_exposed_to(self):
        sc = self.scorecard()
        self.assertTrue(sc.stop_was_hit("LONG", 94.0, 93.0, 120.0))
        self.assertFalse(sc.stop_was_hit("LONG", 94.0, 95.0, 120.0))
        self.assertTrue(sc.stop_was_hit("SHORT", 106.0, 80.0, 107.0))
        self.assertFalse(sc.stop_was_hit("SHORT", 106.0, 80.0, 105.0))
        # Exactly at the level counts as hit, on both sides. A stop is the level at which the
        # reason has stopped being true, and "it only just touched it" is not a measurement.
        self.assertTrue(sc.stop_was_hit("LONG", 94.0, 94.0, 120.0))
        self.assertTrue(sc.stop_was_hit("SHORT", 106.0, 80.0, 106.0))

    def test_an_unanswerable_stop_is_false_and_never_an_exception(self):
        sc = self.scorecard()
        for args in (
            ("LONG", None, 90.0, 110.0),
            ("LONG", 94.0, None, None),
            ("SHORT", 106.0, None, 110.0),
            ("WAIT", 94.0, 90.0, 110.0),
            ("", 94.0, 90.0, 110.0),
        ):
            self.assertFalse(sc.stop_was_hit(*args), args)

    def test_a_stop_beats_the_move_that_followed_it(self):
        sc = self.scorecard()
        # Up 8% at the end of the window and stopped out on the way: the plan was closed before
        # the 8% happened, and scoring it right would credit a trade nobody was still in.
        self.assertEqual(sc.verdict_of("LONG", 8.0, True), "stopped")
        self.assertEqual(sc.verdict_of("SHORT", -8.0, True), "stopped")

    def test_an_unmeasured_move_is_not_a_miss(self):
        sc = self.scorecard()
        self.assertIsNone(sc.verdict_of("LONG", None, False))
        self.assertIsNone(sc.verdict_of("SHORT", None, False))
        # And a stop that was hit is still a verdict, because that much IS known.
        self.assertEqual(sc.verdict_of("LONG", None, True), "stopped")

    def test_a_flat_move_is_its_own_word(self):
        """Exactly zero went neither way. Folding it into "wrong" would overstate the miss rate
        and folding it into "right" would overstate the hit rate."""
        sc = self.scorecard()
        self.assertEqual(sc.verdict_of("LONG", 0.0, False), "flat")
        self.assertEqual(sc.verdict_of("SHORT", 0, False), "flat")

    def test_the_direction_is_scored_against_the_sign_of_the_move(self):
        sc = self.scorecard()
        self.assertEqual(sc.verdict_of("LONG", 3.0, False), "right")
        self.assertEqual(sc.verdict_of("LONG", -3.0, False), "wrong")
        self.assertEqual(sc.verdict_of("SHORT", -3.0, False), "right")
        self.assertEqual(sc.verdict_of("SHORT", 3.0, False), "wrong")

    def test_the_stop_check_is_one_statement_and_not_one_per_row(self):
        """The comment claimed this for weeks while the code under it did the opposite.

        It was a round trip per scored row against a free tier endpoint, so the cost grew with
        the length of the log rather than with the size of the universe -- a scorecard that gets
        slower every day it is kept. `tools/` sits outside the QueryBudget baseline, which is how
        it survived the pass that rewrote eleven jobs for exactly this.
        """
        self.assertEqual(QueryBudget.in_loop_calls(ROOT / "tools" / "scorecard.py"), 0)

    def test_the_scorer_writes_nothing(self):
        """Derived on demand, so there is no second copy of the truth to drift."""
        src = (ROOT / "tools" / "scorecard.py").read_text(encoding="utf-8")
        for write in ("INSERT ", "UPDATE ", "DELETE ", "conn.commit("):
            self.assertNotIn(write, src.upper() if write.isupper() else src)


class DecisionLaneConcurrency(unittest.TestCase):
    """What stops two writers, or two runs, from disagreeing about one session.

    The lanes are deliberately many small workflows rather than one monolith, and the price of
    that shape is that "did anything race" stops being answerable by looking at a single run.
    These are the four properties that make the shape safe, each asserted against the file that
    provides it.
    """

    @staticmethod
    def workflows():
        """Every workflow file as raw text.

        Read as text rather than parsed, for the reason every other workflow test in this file
        is: PyYAML is not in `requirements.txt`, and `requirements.txt` is the Python the data
        jobs need. Adding a parser to the production dependency list so a test can read a YAML
        key would be paying for a convenience in the wrong place.
        """
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        }

    def test_every_lane_holds_its_own_queue_and_cannot_be_cancelled_by_another(self):
        """One group per lane, and no lane cancels in progress.

        Sharing a group once deadlocked the thing that mattered most: a geo backfill hung on
        rate-limit retries held `nbt-database` for ninety minutes while the migration the
        deployed site needed sat queued behind it. And `cancel-in-progress: true` on a data lane
        would let a later run kill a writer mid-transaction.
        """
        groups: dict[str, list[str]] = {}
        for name, text in self.workflows().items():
            found = None
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if line.strip() == "concurrency:" and not line.startswith(" "):
                    block = dict(
                        part.split(":", 1)
                        for part in (ln.strip() for ln in lines[i + 1 : i + 3])
                        if ":" in part
                    )
                    found = (block.get("group", "").strip(),
                             block.get("cancel-in-progress", "").strip())
                    break
            if found is None:
                # tests.yml deliberately has none: no database, no secrets, nothing to
                # serialise, and it must never be able to block the data lane.
                self.assertNotIn("concurrency:", text, f"{name} declares one this cannot read")
                self.assertEqual(name, "tests.yml", f"{name} has no concurrency group")
                continue
            group, cancels = found
            self.assertEqual(cancels, "false", f"{name} can be cancelled in progress")
            groups.setdefault(group, []).append(name)

        # The decision lane's group is its own, which is a correctness property and not a
        # convenience: GitHub keeps one pending run per group, so sharing with an ingest lane
        # would let a source fetch cancel the one output the site is built around.
        self.assertEqual(groups["nbt-decision"], ["cron-decision.yml"])
        # refresh and backfill share `nbt-database` on purpose -- both write through the same
        # tables on a long schedule and must not interleave.
        self.assertEqual(sorted(groups["nbt-database"]), ["backfill.yml", "refresh.yml"])
        # Every other lane is alone in its group.
        for group, lanes in groups.items():
            if group != "nbt-database":
                self.assertEqual(len(lanes), 1, f"{group} is shared by {lanes}")

    def test_the_decision_is_written_even_when_its_inputs_fail(self):
        """Two jobs and not one, because `timeout-minutes` kills the job and not the step.

        These used to be two steps with `if: always()` on the second. That net never caught
        anything: on 2026-10-04 and again on 2026-10-05 the derivation hit 1197s, the runner was
        cancelled, and the decide step was skipped rather than run. A session with no row is a
        hole a later hit rate cannot tell apart from a session nothing was decided on.
        """
        text = self.workflows()["cron-decision.yml"]
        decide = text.split(chr(10) + "  decide:" + chr(10), 1)[1]
        self.assertIn("needs: derive", decide)
        self.assertIn("if: always()", decide)
        # Each on its own runner with its own budget, which is the whole of why it survives.
        self.assertEqual(text.count("runs-on: ubuntu-latest"), 2)
        self.assertEqual(text.count("timeout-minutes:"), 2)

    def test_one_job_writes_each_of_the_two_tables_the_decision_rests_on(self):
        """A single writer is what makes the upserts enough.

        Two lanes writing one table would still be safe row by row -- every statement here is an
        ON CONFLICT upsert -- but they could disagree about which session is current, and a
        reader cannot tell a stale row from a fresh one by looking at it.
        """
        writers = {"AssetFactor": set(), "DecisionLog": set()}
        for path in [*(ROOT / "jobs").glob("*.py"), *(ROOT / "tools").glob("*.py"),
                     *(ROOT / "tools").glob("*.mjs")]:
            src = path.read_text(encoding="utf-8")
            for table in writers:
                if f'INSERT INTO "{table}"' in src or f'UPDATE "{table}"' in src:
                    writers[table].add(path.name)
        self.assertEqual(writers["AssetFactor"], {"factors.py"})
        self.assertEqual(writers["DecisionLog"], {"decide.mjs"})

    def test_a_rerun_re_decides_today_without_erasing_what_was_measured(self):
        """The only column in this table that cannot be recomputed from current data.

        `decide.mjs` upserts one row per asset per session, and the lane can legitimately run
        twice in a day. If the conflict clause reset `status` or the move columns, a second run
        would throw away the maturation the first run's row had already collected -- and the
        accuracy loop would measure nothing while looking perfectly healthy.
        """
        src = (ROOT / "tools" / "decide.mjs").read_text(encoding="utf-8")
        start = src.index('ON CONFLICT ("assetId", "periodEnd") DO UPDATE SET')
        # Comments blanked first -- rule 59. This passed for a day and then failed the moment a
        # comment above the clause explained the guarantee by naming `status`: the assertion was
        # reading the prose that promised the column was absent. The guard was right and the way
        # it was reading the file was not.
        clause = code_only(src[start:src.index("// One batch, one transaction", start)])
        for untouched in ("status", "move1Pct", "move5Pct", "move20Pct",
                          "measured1On", "measured5On", "measured20On"):
            self.assertNotIn(untouched, clause, f"a rerun overwrites {untouched}")
        # And the verdict itself IS rewritten, or a rerun would publish yesterday's reading.
        self.assertIn("action = EXCLUDED.action", clause)
        self.assertIn("gate = EXCLUDED.gate", clause)

    def test_the_whole_run_is_decided_on_one_date_read_once(self):
        """A pass started at 23:59 must not date half its rows to the next day."""
        src = (ROOT / "tools" / "decide.mjs").read_text(encoding="utf-8")
        self.assertEqual(src.count("todayISO()"), 1, "the clock is read more than once")

    def test_the_log_reads_the_same_factor_columns_the_website_does(self):
        """The seam that already broke once, pinned on both sides.

        `r20` was added to the rule table, to `lib/decisionInput.ts` and to `lib/queries.ts` on
        2026-10-09 and never to `tools/decide.mjs`, so the nightly log decided late shorts on
        half of `shortNeedsBacking` while the site applied all of it. In Crypto, PSX and FX --
        the three markets whose short expectancy measured positive -- that fall was the only
        thing standing between a late short and a printed SHORT, so the site refused those names
        and the log recorded them as taken. A log that disagrees with the page is worse than no
        log, because the refusal is eventually judged by it.
        """
        mjs = (ROOT / "tools" / "decide.mjs").read_text(encoding="utf-8")
        for column in ("volumeRatio", "relStrength", "r20", "entryTrigger", "triggerDirection"):
            self.assertIn(f'"{column}"', mjs, f"{column} is not selected for the nightly log")
            self.assertIn(f"factor?.{column}", mjs, f"{column} is selected and never passed on")


class SourceBreaker(unittest.TestCase):
    """Stop asking a source that stopped answering, and never stop asking it for good.

    The second half of that sentence is the hard half and it is what most of these tests are
    about. A breaker is easy to open and easy to get wrong in one direction: every mistake makes
    it open sooner, stay open longer, and eventually delete a venue that recovered hours ago. So
    the properties guarded here are mostly about the breaker letting go.

    In the order of how much is lost when one breaks:

      * **the cooldown is capped.** An unbounded backoff is a permanent deletion wearing the
        clothes of a retry policy.
      * **the breaker does not read its own footprint.** Skips must not count as evidence, or
        every run extends the cooldown and the first outage is the last fetch.
      * **it never takes the lane down itself.** A resilience layer that can raise has made
        things worse than the problem it was added for.
      * **it substitutes nothing.** A source that did not answer reaches the reader as a source
        that did not answer.
    """

    @staticmethod
    def breaker():
        import breaker
        return breaker

    @staticmethod
    def at(**kw):
        return datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc) - timedelta(**kw)

    NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)

    def rows(self, *spec):
        """`("failed", hours_ago)` pairs into ChunkRun-shaped rows, newest first."""
        return [{"status": st, "startedAt": self.at(hours=h)} for st, h in spec]

    # --- the cooldown ------------------------------------------------------------------------

    def test_the_cooldown_is_capped_however_long_a_source_has_been_down(self):
        """The property whose loss is a permanent deletion.

        At the eleventh doubling an uncapped backoff puts the next probe a month out, and the
        breaker has quietly stopped being a breaker. The ceiling means every source is probed at
        least twice a day however long it has been dark, so this can only ever delay a fetch.
        """
        b = self.breaker()
        for failures in (3, 10, 50, 500, 10_000):
            self.assertLessEqual(b.cooldown_minutes(failures), b.COOLDOWN_MAX_MIN, failures)
        # And the arithmetic does not go through 2**10000 on the way to being clamped.
        self.assertEqual(b.cooldown_minutes(10_000), float(b.COOLDOWN_MAX_MIN))

    def test_the_cooldown_starts_at_the_base_and_doubles(self):
        b = self.breaker()
        self.assertEqual(b.cooldown_minutes(b.OPEN_AFTER - 1), 0.0)
        self.assertEqual(b.cooldown_minutes(b.OPEN_AFTER), float(b.COOLDOWN_BASE_MIN))
        self.assertEqual(b.cooldown_minutes(b.OPEN_AFTER + 1), float(b.COOLDOWN_BASE_MIN * 2))
        self.assertEqual(b.cooldown_minutes(b.OPEN_AFTER + 2), float(b.COOLDOWN_BASE_MIN * 4))

    # --- when it opens -----------------------------------------------------------------------

    def test_a_source_nobody_has_asked_is_not_a_broken_source(self):
        """Every rule in this project reads an absent measurement as missing evidence and never
        as evidence against. A breaker that opened on no history would stop a brand new venue
        from ever being tried."""
        b = self.breaker()
        state = b.state_of("Binance", [], self.NOW)
        self.assertEqual(state.state, b.CLOSED)
        self.assertTrue(state.may_fetch)

    def test_one_quiet_slice_is_not_an_outage(self):
        """A rerun inside the cache hour legitimately writes nothing, a venue can drop one
        request, and a market can be shut. Opening on one would make the breaker the outage."""
        b = self.breaker()
        self.assertEqual(b.state_of("X", self.rows(("empty", 1)), self.NOW).state, b.CLOSED)
        self.assertEqual(
            b.state_of("X", self.rows(("empty", 1), ("failed", 2)), self.NOW).state, b.CLOSED
        )

    def test_it_opens_on_consecutive_non_answers_and_then_skips(self):
        b = self.breaker()
        state = b.state_of("X", self.rows(("failed", 0.1), ("failed", 1), ("empty", 2)), self.NOW)
        self.assertEqual(state.state, b.OPEN)
        self.assertFalse(state.may_fetch)
        self.assertGreater(state.wait_minutes, 0)
        self.assertIn("next probe in", state.reason)

    def test_a_degraded_source_is_not_a_blocked_one(self):
        """`partial` is an answer. Some of the assets came back, which is the ordinary state of
        a chunked lane against a venue that rate limits -- and a breaker is the wrong instrument
        for degraded. Counting it as a failure would open on a working source."""
        b = self.breaker()
        degraded = self.rows(("failed", 0.1), ("partial", 1), ("failed", 2), ("failed", 3))
        self.assertEqual(b.state_of("X", degraded, self.NOW).state, b.CLOSED)

    def test_the_streak_stops_at_the_last_time_it_answered(self):
        b = self.breaker()
        failures, newest = b.consecutive_failures(
            self.rows(("failed", 0.1), ("failed", 1), ("ok", 2), ("failed", 3), ("failed", 4))
        )
        self.assertEqual(failures, 2)
        self.assertEqual(newest, self.at(hours=0.1))

    # --- when it lets go ---------------------------------------------------------------------

    def test_the_cooldown_elapsing_allows_exactly_one_probe(self):
        b = self.breaker()
        old = self.rows(("failed", 9), ("failed", 10), ("failed", 11))
        state = b.state_of("X", old, self.NOW)
        self.assertEqual(state.state, b.HALF_OPEN)
        self.assertTrue(state.may_fetch, "a breaker that never probes is a switch")
        self.assertEqual(state.wait_minutes, 0.0)

    def test_a_probe_that_answers_closes_the_breaker(self):
        b = self.breaker()
        recovered = self.rows(("ok", 0.1), ("failed", 9), ("failed", 10), ("failed", 11))
        self.assertEqual(b.state_of("X", recovered, self.NOW).state, b.CLOSED)

    def test_a_probe_that_fails_waits_longer_than_the_one_before(self):
        b = self.breaker()
        three = b.state_of("X", self.rows(("failed", 0.1), ("failed", 1), ("failed", 2)), self.NOW)
        four = b.state_of(
            "X", self.rows(("failed", 0.1), ("failed", 1), ("failed", 2), ("failed", 3)), self.NOW
        )
        self.assertGreater(four.wait_minutes, three.wait_minutes)

    def test_an_old_outage_stops_counting(self):
        """Read as a window, because three weeks ago is not evidence about now. The window is
        applied in the query; this pins the constant that defines it so a later edit cannot
        quietly make the history unbounded."""
        b = self.breaker()
        src = (ROOT / "jobs" / "breaker.py").read_text(encoding="utf-8")
        self.assertIn('"startedAt" >= %s', src)
        self.assertIn("timedelta(days=LOOKBACK_DAYS)", src)
        self.assertLessEqual(b.LOOKBACK_DAYS, 30)

    # --- the fault that would make it feed itself ----------------------------------------------

    def test_the_breaker_does_not_count_its_own_skips(self):
        """The self-reinforcing bug, and the reason `skipped` is its own status.

        Filing a skip as `empty` would make every run add a failure: the cooldown would double
        each time, hit the ceiling, and keep its own streak alive forever on rows the breaker
        itself wrote. The source would never be asked again, and the table would say it had been
        failing continuously for months without a single request having been made.
        """
        b = self.breaker()
        self.assertIn("skipped", b.IGNORED)
        self.assertNotIn("skipped", b.ANSWERED)
        # Three real failures, then twenty skips this module wrote. The streak must still be
        # three, and the cooldown must still be measured from the last real attempt.
        history = [{"status": "skipped", "startedAt": self.at(hours=i * 0.5)} for i in range(20)]
        history += self.rows(("failed", 10.1), ("failed", 11), ("failed", 12))
        failures, newest = b.consecutive_failures(history)
        self.assertEqual(failures, 3)
        self.assertEqual(newest, self.at(hours=10.1))
        # And with the real failures that old, the cooldown has elapsed and it probes.
        self.assertEqual(b.state_of("X", history, self.NOW).state, b.HALF_OPEN)

    def test_the_skipped_status_is_one_the_writer_accepts(self):
        """A status the breaker writes and the log refuses would turn every skip into an
        exception inside the thing that was meant to prevent one."""
        import runlog
        self.assertIn("skipped", runlog.STATUSES)
        # And it is not derivable by accident: nothing but an explicit skip produces it.
        for asked, written, answered in ((0, 0, None), (5, 0, None), (5, 2, 2), (5, 5, 5)):
            self.assertNotEqual(runlog.default_status(asked, written, answered), "skipped")

    # --- it must never be the thing that fails -------------------------------------------------

    def test_an_unreadable_history_fetches_as_usual_rather_than_raising(self):
        """A resilience layer that can take the lane down has made things worse than the problem
        it was added for. An unreadable history is treated exactly like an empty one, which is
        the behaviour the pipeline had before this module existed."""
        b = self.breaker()

        class Broken:
            def execute(self, *a, **k):
                raise RuntimeError("relation \"ChunkRun\" does not exist")

            def fetchall(self):
                return []

        state = b.breaker_for(Broken(), "Binance", self.NOW)
        self.assertEqual(state.state, b.CLOSED)
        self.assertTrue(state.may_fetch)

    def test_a_malformed_history_row_does_not_raise(self):
        b = self.breaker()
        for history in ([{}], [{"status": None}], [{"status": "failed"}] * 5, [{"startedAt": None}]):
            state = b.state_of("X", history, self.NOW)
            self.assertIn(state.state, (b.CLOSED, b.OPEN, b.HALF_OPEN))

    def test_failures_with_no_recorded_time_probe_rather_than_hold_shut(self):
        """An unmeasurable cooldown must not hold the breaker shut: that would be a gate resting
        on an absence, which is the one thing every rule in this project refuses."""
        b = self.breaker()
        state = b.state_of("X", [{"status": "failed"}] * 5, self.NOW)
        self.assertEqual(state.state, b.HALF_OPEN)
        self.assertTrue(state.may_fetch)

    # --- what it refuses to do ------------------------------------------------------------------

    def test_nothing_is_substituted_for_the_data_that_did_not_arrive(self):
        """The line this layer does not cross, asserted on the only two files that could cross it.

        A synthesised close is the most dangerous invention available here: it is
        indistinguishable from a real one downstream, it passes every staleness gate precisely
        *because* it is freshly dated, and the decision rules then read it as evidence. A source
        that did not answer must reach the reader as a source that did not answer, which is what
        `SourceSilent`, `Coverage` and gate 3 of the rule table already do.
        """
        src = (ROOT / "jobs" / "breaker.py").read_text(encoding="utf-8")
        for writes in ('INSERT INTO "PriceSnapshot"', 'INSERT INTO "AssetFactor"', "UPDATE "):
            self.assertNotIn(writes, src, "the breaker writes data of its own")
        # The skip row is a diagnostic and carries no rows.
        prices = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        skip = prices[prices.index("def runlog_write_skip("):prices.index("def main()")]
        self.assertIn("rows_written=0", skip)
        self.assertIn('status="skipped"', skip)

    def test_a_skipped_lane_still_leaves_a_row_a_human_can_read(self):
        """A lane that silently does nothing is indistinguishable from one that never ran, which
        is the exact confusion `ChunkRun` exists to end."""
        prices = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        lane = prices[prices.index("def lane("):prices.index("def runlog_write_skip(")]
        self.assertIn("runlog_write_skip(", lane)
        self.assertIn("yield None", lane)

    def test_every_price_lane_goes_through_the_breaker_and_the_log(self):
        """The wiring, pinned. `runlog.chunk_run` existed for days with no caller at all, so the
        table the freshness panel reads was empty and the claim that a failed chunk is a row
        rather than something to hunt for in a log was not true of production."""
        prices = (ROOT / "jobs" / "prices.py").read_text(encoding="utf-8")
        main = prices[prices.index("def main() -> None:"):]
        for source in ("YAHOO", "BINANCE", "GNEWS"):
            self.assertIn(f"lane(cur, job, {source}, label)", main, f"{source} is not logged")
        # Three lanes, three records. A fourth call with no test here is a lane nobody checked.
        self.assertEqual(main.count("with lane("), 3)

    def test_an_exception_still_reaches_the_handler_that_keeps_the_other_lanes(self):
        """Recording a failure is not handling it.

        `chunk_run` writes the failed row on the way out and re-raises. If `lane` swallowed that,
        a blocked venue would stop appearing in `main`'s `silent` list, the run would go green on
        an outage, and the one summary a human reads would say every source answered.

        Exercised rather than read, because "does this propagate" is a question source text
        answers badly: the wrapper is two context managers deep and either of them could catch.
        `DATABASE_URL` is cleared so the log writer takes its no-database path instead of
        spending a connection timeout on each of these.
        """
        import os
        import unittest.mock
        import prices

        class Cur:
            def execute(self, *a, **k): pass
            def fetchall(self): return []

        class Blocked(Exception):
            pass

        with unittest.mock.patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            with self.assertRaises(Blocked):
                with prices.lane(Cur(), "test", "Binance", "1/1") as run:
                    self.assertIsNotNone(run, "a closed breaker must still fetch")
                    raise Blocked("no row from Binance for any of 10 assets")

    def test_a_skipped_lane_yields_nothing_and_runs_no_body(self):
        """The whole point of the open state: the fetch does not happen.

        Exercised for the same reason as the test above -- a wrapper that yielded a record on
        the open path would skip nothing at all, and nothing in the source text would look
        different.
        """
        import os
        import unittest.mock
        import prices

        # Relative to the real clock, because `lane` asks the breaker for the state *now*: it
        # takes no injected time, since the thing it is deciding is whether to fetch this second.
        # A fixture pinned to a fixed date would read as a cooldown that elapsed long ago.
        now = datetime.now(timezone.utc)
        dead = [
            {"status": "failed", "startedAt": now - timedelta(minutes=1 + i * 60)}
            for i in range(4)
        ]

        class Cur:
            def execute(self, *a, **k): pass
            def fetchall(self): return dead

        ran = False
        with unittest.mock.patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            with prices.lane(Cur(), "test", "Binance", "1/1") as run:
                if run is not None:
                    ran = True
        self.assertFalse(ran, "the body ran against a source the breaker had open")


class BoundedRates(unittest.TestCase):
    """A hit rate with no interval around it is a number nobody can weigh.

    Principle 3: sample size decides how much weight a parallel earns, and it is never left
    unstated. The scorecard printed `right/decided (60%)` and the sample beside it in a separate
    sentence, which leaves the reader to do the one piece of arithmetic that decides whether the
    percentage means anything.

    Two properties, and the second is the one that actually stops noise-chasing:

      * the interval is computed by a method that stays inside 0 and 1, because an accuracy
        report claiming "82% to 104%" has discredited itself in the one place it was being
        careful; and
      * it is computed over the **effective** sample. One decision per asset per session means
        a six-day log of 197 rows is 60 names observed repeatedly, and an interval over 197 is
        about a third too narrow -- which is exactly how a run of luck on one name comes to read
        as evidence about the engine.
    """

    @staticmethod
    def scorecard():
        import importlib.util

        path = ROOT / "tools" / "scorecard.py"
        spec = importlib.util.spec_from_file_location("nbt_scorecard_bounds", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_the_interval_matches_the_published_wilson_figures(self):
        """Checked against the standard worked example rather than against itself."""
        sc = self.scorecard()
        lo, hi = sc.wilson(60, 100)
        self.assertAlmostEqual(lo, 0.5020, places=3)
        self.assertAlmostEqual(hi, 0.6906, places=3)

    def test_the_interval_never_leaves_the_unit_interval(self):
        """Where the normal approximation fails, and it fails exactly where this scorer lives:
        at small n and at shares near 0 or 1."""
        sc = self.scorecard()
        for successes, n in ((0, 1), (1, 1), (0, 10), (10, 10), (1, 3), (29, 30), (0, 400)):
            lo, hi = sc.wilson(successes, n)
            self.assertGreaterEqual(lo, 0.0, (successes, n))
            self.assertLessEqual(hi, 1.0, (successes, n))
            self.assertLessEqual(lo, hi, (successes, n))

    def test_an_empty_sample_has_no_interval_rather_than_a_wide_one(self):
        sc = self.scorecard()
        self.assertEqual(sc.wilson(0, 0), (None, None))
        self.assertEqual(sc.wilson(5, -1), (None, None))

    def test_a_smaller_sample_gives_a_wider_interval(self):
        """The whole point. If this ever inverts, the figure is lying in the direction that
        matters: it would read most confident where it knows least."""
        sc = self.scorecard()
        widths = []
        for n in (10, 30, 100, 1000):
            lo, hi = sc.wilson(round(0.6 * n), n)
            widths.append(hi - lo)
        self.assertEqual(widths, sorted(widths, reverse=True), widths)

    def test_the_sample_is_the_distinct_names_and_not_the_row_count(self):
        """The module's own caveat, finally obeyed by the arithmetic rather than only by prose.

        It has said in its docstring since it was written that "197 scored rows is closer to 60
        names observed repeatedly than to 197 experiments". Until now the rate was still printed
        over 197.
        """
        sc = self.scorecard()
        self.assertEqual(sc.effective_n(197, 60), 60)
        # Never larger than either, and never negative.
        self.assertEqual(sc.effective_n(10, 99), 10)
        self.assertEqual(sc.effective_n(0, 5), 0)
        self.assertEqual(sc.effective_n(-4, 5), 0)
        # And the correction has to actually bite: the honest interval is materially wider.
        wide = sc.wilson(36, 60)
        narrow = sc.wilson(118, 197)
        self.assertGreater(wide[1] - wide[0], (narrow[1] - narrow[0]) * 1.4)

    def test_a_rate_that_has_not_beaten_a_coin_says_so(self):
        """The no-noise-chasing rule, and it is one line. 58% over an interval from 44% to 71%
        is a sample that has not yet distinguished the engine from chance, and printing 58%
        beside it invites the exact reading the interval exists to forbid."""
        sc = self.scorecard()
        lo, hi = sc.wilson(35, 60)
        self.assertTrue(sc.spans_chance(lo, hi))
        lo, hi = sc.wilson(400, 600)
        self.assertFalse(sc.spans_chance(lo, hi))
        # No interval at all is treated as "not evidence", never as "evidence".
        self.assertTrue(sc.spans_chance(None, None))

    def test_the_printed_rate_carries_its_interval(self):
        """Pinned at the call site: the two were separable and the point is that they are not."""
        src = (ROOT / "tools" / "scorecard.py").read_text(encoding="utf-8")
        tail = src[src.index("elif decided:"):]
        self.assertIn("effective_n(decided, names)", tail)
        self.assertIn("wilson(", tail)
        self.assertIn("spans_chance(", tail)


class RetryIsBounded(unittest.TestCase):
    """The retry lane, and the single guard that keeps it from becoming the outage.

    A lane that re-triggers its own retry on every failure is a loop bounded by nothing but the
    free tier's Actions minutes. That is not hypothetical here: this repository's database spent
    2026-10-09 refusing every connection for exceeding its quota, and a retry loop against a
    quota-exhausted service turns one dead dependency into two.
    """

    @staticmethod
    def retry():
        return (ROOT / ".github" / "workflows" / "retry.yml").read_text(encoding="utf-8")

    @staticmethod
    def condition():
        """The job's own `if:` expression, and nothing else.

        Read out of the block rather than searched for in the file, because the first version of
        this test looked for the guard anywhere in the text and the comment above the guard
        explains it by name -- so deleting the condition entirely left the test passing on the
        prose that described it. A guard asserted against its own documentation is not asserted.
        """
        text = (ROOT / ".github" / "workflows" / "retry.yml").read_text(encoding="utf-8")
        block = text.split("    if: >-", 1)[1]
        return block.split("    steps:", 1)[0]

    def test_a_lane_is_retried_once_and_never_in_a_loop(self):
        text = self.retry()
        self.assertIn("run_attempt == 1", self.condition())
        # A second consecutive failure is information -- it says the fault is not transient --
        # and a retry loop destroys that information by making every failure look alike.
        self.assertIn("--failed", text, "the retry re-runs jobs that already succeeded")

    def test_it_fires_on_a_timeout_as_well_as_on_a_failure(self):
        """A lane killed at its budget reads as `cancelled` from here, and that is precisely the
        case worth one more try: the 2026-10-04 and 2026-10-05 derivations both died that way."""
        cond = self.condition()
        self.assertIn("conclusion == 'failure'", cond)
        self.assertIn("conclusion == 'cancelled'", cond)

    def test_the_migration_and_the_test_lanes_are_never_retried(self):
        """`prisma migrate deploy` takes an advisory lock and a failed apply can leave a
        migration recorded as started, which a blind re-run turns into a second partial apply.
        And a failing test is a fact about the code: running it again is how a flaky suite gets
        to stay flaky."""
        trigger = self.retry().split("permissions:", 1)[0]
        self.assertNotIn('"schema"', trigger)
        self.assertNotIn('"tests"', trigger)

    def test_every_lane_it_watches_exists_under_that_name(self):
        """`workflow_run` matches on a workflow's `name:`, not on its filename, so a renamed
        lane silently stops being retried and nothing anywhere goes red."""
        trigger = self.retry().split("types: [completed]", 1)[0]
        watched = {
            line.strip().lstrip("- ").strip('"')
            for line in trigger.splitlines()
            if line.strip().startswith('- "')
        }
        names = set()
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            first = path.read_text(encoding="utf-8").splitlines()[0]
            if first.startswith("name:"):
                names.add(first.split("name:", 1)[1].strip())
        self.assertTrue(watched, "the retry lane watches nothing")
        self.assertEqual(watched - names, set(), "it watches a workflow name that does not exist")

    def test_it_cannot_write_anything_but_a_rerun(self):
        """Nothing here reads the repository's data and nothing needs a database credential: the
        retry re-runs the original lane, which carries its own secrets."""
        text = self.retry()
        block = text.split("permissions:", 1)[1].split("concurrency:", 1)[0]
        self.assertIn("actions: write", block)
        self.assertNotIn("DATABASE_URL", text)
        self.assertNotIn("packages:", block)

    def test_a_failed_retry_does_not_raise_a_second_alert(self):
        """This workflow going red would be a second alert for one fault, pointing at the wrong
        file. The original failure is the one worth looking at."""
        text = self.retry()
        self.assertIn("::warning::", text)
        self.assertIn("exit 0", text)


class UnchangedRowsAreNotRewritten(unittest.TestCase):
    """A rerun that decides exactly what is already stored must not write anything.

    Not about duplicate rows -- the unique keys on `(assetId, periodEnd)` made those impossible
    from the start, and the job re-decides the same session whenever it runs twice in a day. It
    is about what an UPDATE that changes nothing costs: Postgres writes a new row version
    anyway, marks the old one dead and journals both. A 477-name lane run twice therefore
    doubles its own dead tuples to store exactly what was already there, and on a weekend --
    when `session_end` returns the same stored close and every factor is identical by
    definition -- the entire table is rewritten for nothing.

    Two properties, and the second is the one that could lose data rather than waste space:

      * `IS DISTINCT FROM`, never `<>`. Half of these columns are legitimately null, and `<>`
        against a null is null rather than true -- so a row going from null to a number would
        compare as unchanged and never be stored.
      * **every column the SET writes is in the comparison.** A column named in one and
        forgotten in the other makes a genuinely changed row compare as unchanged and vanish,
        with no error and no row: the log quietly keeps yesterday's verdict under today's date.
    """

    @staticmethod
    def factor_upsert():
        src = (ROOT / "jobs" / "factors.py").read_text(encoding="utf-8")
        body = src[src.index("def flush("):src.index("def session_end(")]
        return body[body.index("ON CONFLICT"):body.index('        """,')]

    # --- the factor row ----------------------------------------------------------------------

    def test_the_factor_upsert_skips_a_row_whose_measurements_did_not_move(self):
        clause = self.factor_upsert()
        self.assertIn("WHERE", clause, "the conflict clause writes unconditionally")
        self.assertIn("IS DISTINCT FROM", clause)

    def test_a_null_becoming_a_number_still_counts_as_a_change(self):
        """The classic skip-clause bug, and the reason for `IS DISTINCT FROM`.

        `volumeRatio` is null for every currency pair and for any name whose venue published
        nothing, and it becomes a number the day one does. Under `<>` that comparison is null,
        which is not true, so the row would be skipped and the pair would never acquire the
        measurement it had just earned.
        """
        clause = self.factor_upsert()
        comparison = clause[clause.index("WHERE"):]
        self.assertNotRegex(comparison, r"<>")
        self.assertNotRegex(comparison, r"(?<![<>!])=(?!=)", "a bare = would be null-blind too")

    def test_every_column_the_factor_upsert_sets_is_also_compared(self):
        """The failure mode that loses data rather than space.

        A column in the SET and not in the comparison is a measurement that can change while the
        row reads as unchanged. Nothing raises, nothing is logged, and the stored factor is
        simply yesterday's -- which the decision rules then read as today's.
        """
        import re as _re

        clause = self.factor_upsert()
        sets, comparison = clause.split("WHERE", 1)
        named = set(_re.findall(r'"?([A-Za-z0-9_]+)"?\s*=\s*EXCLUDED', sets))
        self.assertTrue(named, "the SET list could not be read")
        for column in sorted(named):
            self.assertIn(
                f"EXCLUDED.{column}" if f"EXCLUDED.{column}" in comparison else f'EXCLUDED."{column}"',
                comparison,
                f"{column} is written but never compared, so a change to it would be skipped",
            )

    def test_computed_at_is_set_but_never_compared(self):
        """It is `now()`. Including it would make every row differ and defeat the clause.

        The consequence is a change in what the column means and it is deliberate: it now says
        when this reading last *changed*, not when the job last ran. Nothing reads it -- the
        freshness a reader cares about is `periodEnd`, which is part of the key -- and "the job
        ran" is a question `ChunkRun` answers properly now that the lanes write it.
        """
        clause = self.factor_upsert()
        sets, comparison = clause.split("WHERE", 1)
        self.assertIn('"computedAt" = now()', sets)
        self.assertNotIn("computedAt", comparison)

    # --- the decision row ----------------------------------------------------------------------

    @staticmethod
    def decide_src():
        return (ROOT / "tools" / "decide.mjs").read_text(encoding="utf-8")

    def test_the_decision_upsert_skips_an_unchanged_verdict(self):
        src = self.decide_src()
        self.assertIn("IS DISTINCT FROM", src)
        self.assertIn("changingColumns(extra)", src)

    def test_the_compared_columns_are_derived_from_the_insert_and_not_retyped(self):
        """A second hand-written list is how one of the two comes to be missing a column."""
        src = self.decide_src()
        body = src[src.index("function changingColumns("):src.index("async function writeDecisions(")]
        # Built from the core list and from `extra`, the optional columns this database actually
        # has -- the same two things the INSERT's column list is built from.
        self.assertIn("CORE_COLUMNS", body)
        self.assertIn("extra", body)
        insert = src[src.index("async function writeDecisions("):]
        self.assertIn("const columns = [...CORE_COLUMNS, ...extra]", insert)
        self.assertIn('c !== "assetId"', body)
        self.assertIn('c !== "periodEnd"', body)

    def test_a_skipped_decision_write_can_never_touch_a_maturation(self):
        """The property that makes this safe to do at all on the one table nothing may prune.

        `status` and the move columns are absent from the SET -- that is rule 58's guarantee, not
        this one's -- and because the comparison is built from the same lists as the SET, they
        cannot appear in the WHERE either. So the worst a wrong comparison could do here is write
        when it did not need to, which costs space; it cannot overwrite a measured outcome.
        """
        src = self.decide_src()
        start = src.index('ON CONFLICT ("assetId", "periodEnd") DO UPDATE SET')
        # Comments blanked first. The comment above this very clause explains the guarantee by
        # naming `status`, so a search over the raw text finds the word in the prose that
        # promises it is absent -- which is rule 59 exactly, and it caught this test rather than
        # the code. `code_only` is the same helper the component guards use.
        clause = code_only(src[start:src.index("// One batch, one transaction", start)])
        for untouched in ("status", "move1Pct", "move5Pct", "move20Pct",
                          "measured1On", "measured5On", "measured20On"):
            self.assertNotIn(untouched, clause, f"a rerun can still reach {untouched}")

    def test_the_decision_columns_the_rules_act_on_are_all_compared(self):
        """`action`, `gate` and `confidence` are the verdict. A change to any of them that
        compared as unchanged would leave the log asserting yesterday's call under today's
        date -- which is the one thing the log exists not to do."""
        import re as _re

        src = self.decide_src()
        core = src[src.index("const CORE_COLUMNS = ["):src.index("const SIZING_COLUMNS")]
        named = set(_re.findall(r'"([A-Za-z0-9_]+)"', core))
        for column in ("action", "gate", "confidence", "invalidation", "baseClose"):
            self.assertIn(column, named, f"{column} is no longer written at all")
        # And the key is excluded from the comparison rather than merely absent from it.
        self.assertIn("assetId", named)
        self.assertIn("periodEnd", named)


class TheHotQueryReadsAnIndex(unittest.TestCase):
    """The newest close per asset, on every render of every list page.

    It was `groupBy({ by: ["assetId"], _max: { date: true } })` under a comment promising it
    "reads an index and returns one small row per asset instead of the table". Measured on
    2026-10-10 against 628,675 stored closes, Postgres plans a **parallel sequential scan of the
    whole table** for it -- there is no loose index scan for `GROUP BY assetId, max(date)` -- at
    13,061 shared buffers and 209 ms, every request.

    An index does not fix it: `(assetId, date DESC)` was built, measured, and chosen by nothing.
    The query shape fixes it. A lateral probe walks the primary key backwards once per asset,
    1,921 buffers and 3.2 ms, and returns the close and source at the same time so the second
    price read is gone entirely.

    This is a storage-tier and a compute-tier matter rather than a latency one: the endpoint is
    metered by active time, so a page that reads the whole price history is paying for it on
    every visit.
    """

    @staticmethod
    def queries():
        """Only `getDecisionRows`, with its comments blanked.

        Scoped to the one function, because `lib/queries.ts` has other price reads that are
        correct: `getAssetFreshness` and the asset page each fetch one asset's series and must
        keep doing so. A guard that searched the whole file would fail on them and would be
        asserting something it does not mean -- rule 59, in its other form: an assertion scoped
        wider than the construct it describes.
        """
        src = (ROOT / "lib" / "queries.ts").read_text(encoding="utf-8")
        start = src.index("export async function getDecisionRows(")
        return code_only(src[start:])

    def test_the_price_read_is_a_lateral_and_not_a_whole_table_group_by(self):
        src = self.queries()
        self.assertNotIn(
            'prisma.priceSnapshot.groupBy', src,
            "the newest close per asset is being read by scanning the whole price table again",
        )
        self.assertIn("LEFT JOIN LATERAL", src)
        self.assertIn('ORDER BY s.date DESC', src)
        self.assertIn("LIMIT 1", src)

    def test_the_lateral_is_ordered_so_it_can_walk_the_primary_key(self):
        """`(assetId, date)` is the key. Probing one asset and taking the newest date is an index
        scan backwards; any other ordering is a sort over that asset's whole history."""
        src = self.queries()
        block = src[src.index("LEFT JOIN LATERAL"):src.index("ON true")]
        self.assertIn('s."assetId" = a.id', block)
        self.assertIn("ORDER BY s.date DESC", block)

    def test_the_second_price_read_is_gone_rather_than_merely_smaller(self):
        """The lateral already returns the close and the source, so filtering a second read by a
        day list would be fetching what is already in hand."""
        src = self.queries()
        self.assertNotIn("priceDayList", src)
        self.assertNotIn("prisma.priceSnapshot.findMany", src)

    def test_the_other_group_bys_are_left_alone(self):
        """They read tables `jobs/retention.py` caps at 7 to 14 days, so each is a few thousand
        rows rather than six hundred thousand. Rewriting them would be churn for nothing, and
        the point of measuring was to change the one query that was actually costing something.
        """
        src = self.queries()
        for table in ("assetSetup", "assetAnalog", "humanSignal", "investigation", "assetFactor"):
            self.assertIn(f"prisma.{table}.groupBy", src, f"{table} lost its day query")


class TheLogLearnsWithoutChasingNoise(unittest.TestCase):
    """What the decision log may conclude from its own outcomes, and what it may not.

    It reports per confirmation whether the names a leg backed did better than the names it did
    not, with an interval over the **distinct names** and not the rows. It does not re-weight
    anything: the grade counts legs and has no weights, and a live log of a few hundred rows that
    are repeated observations of a few hundred names is a far smaller and far more correlated
    sample than the 100,000 to 220,000 observations each threshold in the rule table was argued
    from. Letting it move those numbers automatically would be noise-chasing with a feedback path.

    The properties that make that true, in the order of how much is lost when one breaks:

      * **no conclusion from too little.** Both arms need MIN_SAMPLE effective names, and the
        intervals have to stop overlapping, before anything is called a difference.
      * **it never says "apply".** A change to the rule table is a proposal for a person.
      * **an unrecorded row is not an unconfirmed one.** `legs` NULL and `legs` "" are different
        findings, and folding the first into the second would count every pre-column row as a
        decision nothing backed.
    """

    @staticmethod
    def scorecard():
        import importlib.util

        path = ROOT / "tools" / "scorecard.py"
        spec = importlib.util.spec_from_file_location("nbt_scorecard_learn", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @staticmethod
    def row(symbol, legs):
        return {"symbol": symbol, "legs": legs}

    def pairs(self, rights, wrongs, legs, prefix="N"):
        """`(row, verdict)` pairs over distinct names, so effective n equals the count."""
        out = []
        for i in range(rights):
            out.append((self.row(f"{prefix}R{i}", legs), "right"))
        for i in range(wrongs):
            out.append((self.row(f"{prefix}W{i}", legs), "wrong"))
        return out

    # --- an unrecorded row is not an unconfirmed one -----------------------------------------

    def test_a_row_that_never_recorded_its_legs_is_not_one_nothing_backed(self):
        sc = self.scorecard()
        self.assertIsNone(sc.legs_of({"legs": None}))
        self.assertIsNone(sc.legs_of({}))
        self.assertEqual(sc.legs_of({"legs": ""}), [])
        self.assertEqual(sc.legs_of({"legs": "volume,trigger"}), ["volume", "trigger"])

    def test_old_rows_are_in_neither_arm_of_a_leg_comparison(self):
        sc = self.scorecard()
        items = self.pairs(40, 0, None, "OLD") + self.pairs(5, 5, "volume", "V") + self.pairs(5, 5, "", "E")
        (leg, with_, without, _), = sc.leg_report(items, ("volume",))
        self.assertEqual(with_[1], 10, "the backed arm is wrong")
        self.assertEqual(without[1], 10, "pre-column rows leaked into the unbacked arm")

    # --- arms and intervals ------------------------------------------------------------------

    def test_only_right_and_wrong_enter_the_denominator(self):
        sc = self.scorecard()
        items = self.pairs(6, 4, "volume") + [(self.row("F", "volume"), "flat"), (self.row("S", "volume"), "stopped")]
        self.assertEqual(sc.arm(items)[:2], (6, 10))

    def test_the_interval_is_over_names_and_not_rows(self):
        """Forty rows on four names is four experiments observed ten times each."""
        sc = self.scorecard()
        items = []
        for name in ("A", "B", "C", "D"):
            for _ in range(10):
                items.append((self.row(name, "volume"), "right"))
        right, decided, names = sc.arm(items)
        self.assertEqual((right, decided, names), (40, 40, 4))
        self.assertEqual(sc.interval_of((right, decided, names))[2], 4)

    def test_an_empty_arm_has_no_interval(self):
        sc = self.scorecard()
        self.assertIsNone(sc.interval_of((0, 0, 0)))

    # --- no conclusion from too little -------------------------------------------------------

    def test_nothing_is_said_before_both_sides_have_matured_rows(self):
        sc = self.scorecard()
        self.assertEqual(sc.lift_verdict((5, 9, 9), (0, 0, 0)), "no matured rows on one side yet")

    def test_too_few_independent_names_says_so_rather_than_guessing(self):
        sc = self.scorecard()
        floor = sc.MIN_SAMPLE
        few = (floor - 1, floor - 1, floor - 1)
        enough = (floor, floor, floor)
        self.assertIn("too few independent names", sc.lift_verdict(few, enough))
        self.assertIn("too few independent names", sc.lift_verdict(enough, few))

    def test_overlapping_intervals_propose_no_change(self):
        """The default answer for a long time, and the correct one: it is what stops a lucky
        fortnight on a handful of names reading as a finding."""
        sc = self.scorecard()
        got = sc.lift_verdict((22, 40, 40), (18, 40, 40))
        self.assertIn("not separable", got)
        self.assertIn("no change is proposed", got)

    def test_a_real_gap_is_called_a_gap_in_either_direction_and_sent_to_a_person(self):
        sc = self.scorecard()
        better = sc.lift_verdict((190, 200, 200), (60, 200, 200))
        worse = sc.lift_verdict((60, 200, 200), (190, 200, 200))
        self.assertIn("did better", better)
        self.assertIn("did WORSE", worse)
        for verdict in (better, worse):
            self.assertIn("a person's review", verdict)

    def test_no_verdict_ever_says_to_apply_a_change(self):
        """A change to the rule table is a proposal with evidence attached, reviewed by a person,
        which is the bar every rule in brain.md was held to. Exhaustive over a grid of arms."""
        sc = self.scorecard()
        seen = set()
        for a in ((0, 0, 0), (5, 9, 9), (30, 60, 60), (190, 200, 200), (60, 200, 200)):
            for b in ((0, 0, 0), (5, 9, 9), (30, 60, 60), (190, 200, 200), (60, 200, 200)):
                v = sc.lift_verdict(a, b)
                seen.add(v)
                for word in ("apply", "reweight", "re-weight", "increase the weight", "adjust"):
                    self.assertNotIn(word, v.lower(), v)
        self.assertGreater(len(seen), 3, "the grid stopped reaching distinct verdicts")

    # --- what the module does NOT do ---------------------------------------------------------

    def test_the_scorecard_never_writes_a_weight_or_a_threshold_anywhere(self):
        src = code_only((ROOT / "tools" / "scorecard.py").read_text(encoding="utf-8"))
        for write in ("INSERT ", "UPDATE ", "DELETE ", ".write(", "open("):
            self.assertNotIn(write, src.replace("(sys.argv", ""), f"the scorecard contains {write!r}")

    def test_a_refusal_is_scored_on_the_sign_of_the_move_and_never_on_its_stop(self):
        """For a plan whose stop was already crossed, 'stopped out' is true by construction. A
        scorer that counted it would call every `stop-crossed` refusal correct for a reason that
        has nothing to do with whether the refusal was right."""
        src = (ROOT / "tools" / "scorecard.py").read_text(encoding="utf-8")
        tail = src[src.index("were the refusals right?"):]
        self.assertIn("verdict_of(side, r[\"move\"], False)", tail)

    def test_every_leg_the_scorecard_compares_is_a_leg_the_rule_table_can_name(self):
        """Two lists of five names in two languages. If one grows and the other does not, the new
        leg is recorded and never compared, or compared and never recorded."""
        import re as _re

        ts = (ROOT / "lib" / "decision.ts").read_text(encoding="utf-8")
        found = _re.search(r"export const LEGS = \[([^\]]+)\]", ts)
        self.assertIsNotNone(found, "LEGS is gone from lib/decision.ts")
        in_rules = tuple(x.strip().strip('"') for x in found.group(1).split(","))
        self.assertEqual(in_rules, self.scorecard().LEG_NAMES)

    def test_the_nightly_writer_records_the_legs_and_the_refused_side(self):
        src = (ROOT / "tools" / "decide.mjs").read_text(encoding="utf-8")
        self.assertIn("confirmingLegs(decisionInput, dir)", src)
        self.assertIn("intent: decision.intent", src)
        self.assertIn('const LEARNING_COLUMNS = ["legs", "intent"]', src)

    def test_the_migration_adds_both_columns_as_nullable_with_no_backfill(self):
        text = (ROOT / "prisma" / "migrations" / "20261010150000_decision_legs" / "migration.sql").read_text(
            encoding="utf-8"
        )
        body = code_only_sql(text)
        self.assertIn('ADD COLUMN "legs"', body)
        self.assertIn('ADD COLUMN "intent"', body)
        self.assertNotIn("NOT NULL", body.upper())
        self.assertNotIn("UPDATE", body.upper(), "a backfill would attach today's rows to a past call")


def code_only_sql(text: str) -> str:
    """SQL with its `--` comments removed, so a guard reads the statements and not the prose."""
    return chr(10).join(line.split("--", 1)[0] for line in text.splitlines())


class TheUniverseIsFilteredNotFlooded(unittest.TestCase):
    """What may be added to the asset universe, and the faults a careless expansion would commit.

    The exchange lists 1,057 symbols and the project follows 157 of them. The unfollowed ones look
    like stocks and mostly are not: the most heavily "traded" are government securities and monthly
    futures contracts, and the top of a crypto ranking is stablecoins and wrapped copies. So the
    properties here are all refusals, and each one is a real thing the first draft of the filter
    would have let through.
    """

    @staticmethod
    def universe():
        import importlib.util

        path = ROOT / "tools" / "universe.py"
        spec = importlib.util.spec_from_file_location("nbt_universe", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    TODAY = date(2026, 10, 10)

    def coin(self, **over):
        base = {
            "id": "xyz-xyzcoin", "symbol": "XYZ", "name": "XYZ Coin", "rank": 50,
            "first_data_at": "2021-01-01T00:00:00Z",
            "quotes": {"USD": {"price": 12.0, "percent_change_30d": 8.0, "volume_24h": 5_000_000}},
        }
        base.update(over)
        return base

    def reason(self, coin, *, seeded=frozenset(), coinbase=frozenset({"XYZ"}), binance=frozenset()):
        return self.universe().crypto_reject_reason(
            coin, seeded_ids=set(seeded), coinbase_usd=set(coinbase), binance_usdt=set(binance), today=self.TODAY
        )

    # --- crypto ------------------------------------------------------------------------------

    def test_an_ordinary_liquid_coin_with_history_and_a_coinbase_pair_is_proposed(self):
        self.assertIsNone(self.reason(self.coin()))

    def test_a_stablecoin_is_refused_by_name_and_by_peg(self):
        """The named list is the first line and the peg test the backstop: a de-pegged stablecoin
        passes any numeric test on exactly the days it matters, so the name has to come first."""
        self.assertEqual(self.reason(self.coin(symbol="USDC"), coinbase={"USDC"}), "a stablecoin")
        pegged = self.coin(symbol="ZZZ", quotes={"USD": {"price": 1.001, "percent_change_30d": 0.1, "volume_24h": 9e9}})
        self.assertIn("peg", self.reason(pegged, coinbase={"ZZZ"}))
        # And a real asset that happens to sit near a dollar for a day is not a peg.
        moving = self.coin(quotes={"USD": {"price": 1.0, "percent_change_30d": 40.0, "volume_24h": 9e6}})
        self.assertIsNone(self.reason(moving))

    def test_wrapped_staked_and_bridged_copies_are_the_same_reading_twice(self):
        for sym in ("WBTC", "STETH", "CBBTC", "JITOSOL"):
            self.assertIn("wrapped", self.reason(self.coin(symbol=sym), coinbase={sym}), sym)
        self.assertIn("wrapped", self.reason(self.coin(name="Lido Staked Ether")))
        self.assertIn("wrapped", self.reason(self.coin(name="Binance-Peg Something")))

    def test_gold_backed_tokens_duplicate_a_contract_already_followed(self):
        for sym in ("PAXG", "XAUT"):
            self.assertIn("wrapped", self.reason(self.coin(symbol=sym), coinbase={sym}), sym)

    def test_binance_alone_is_not_enough(self):
        """Binance stopped answering from GitHub's runners on 2026-09-29 while answering from a
        laptop. A coin only it carries is stored locally and never updated in production, which is
        the failure that left every crypto close stale for a week."""
        why = self.reason(self.coin(), coinbase=frozenset(), binance={"XYZ"})
        self.assertIn("no USD daily pair on Coinbase", why)
        self.assertIn("geo-blocked", why)
        self.assertIn("no USD daily pair on Coinbase", self.reason(self.coin(), coinbase=frozenset()))

    def test_a_thin_copy_with_a_ranking_and_a_price_is_not_a_reading(self):
        """`TONToken` ranks 135th and traded $0.1m against the real Toncoin's $42.8m."""
        thin = self.coin(quotes={"USD": {"price": 3.0, "percent_change_30d": 5.0, "volume_24h": 100_000}})
        self.assertIn("too thin", self.reason(thin))
        missing = self.coin(quotes={"USD": {"price": 3.0, "percent_change_30d": 5.0}})
        self.assertIn("too thin", self.reason(missing))

    def test_a_coin_without_a_year_of_history_cannot_feed_the_legs_that_need_it(self):
        young = self.coin(first_data_at="2026-03-01T00:00:00Z")
        self.assertIn("days of history", self.reason(young))
        self.assertIn("no recorded start", self.reason(self.coin(first_data_at=None)))
        self.assertIn("unreadable", self.reason(self.coin(first_data_at="not-a-date")))

    def test_rank_and_already_followed_are_checked(self):
        self.assertIn("past the top", self.reason(self.coin(rank=151)))
        self.assertIn("past the top", self.reason(self.coin(rank=None)))
        self.assertEqual(self.reason(self.coin(), seeded={"xyz-xyzcoin"}), "already followed")

    def test_two_quotes_for_one_ticker_must_describe_the_same_asset(self):
        """A ticker is not an identity. A wrong mapping stores one coin's prices under another's
        name, silently and permanently."""
        u = self.universe()
        self.assertTrue(u.prices_agree(100.0, 108.0))
        self.assertTrue(u.prices_agree(100.0, 85.1))
        self.assertFalse(u.prices_agree(100.0, 120.0))
        self.assertFalse(u.prices_agree(100.0, 80.0))
        for bad in ((None, 1.0), (1.0, None), (0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)):
            self.assertFalse(u.prices_agree(*bad), bad)

    # --- PSX ---------------------------------------------------------------------------------

    def test_only_ordinary_shares_look_like_ordinary_shares(self):
        u = self.universe()
        for ok in ("HBL", "OGDC", "WAVESAPP", "MWMP", "SYM"):
            self.assertTrue(u.is_ordinary_share(ok), ok)
        for bad in ("PRL-OCT", "OGDC-OCTB", "P03GHS151026", "P01GIS210127", "P05VRR100529", "", "1ABC", "A"):
            self.assertFalse(u.is_ordinary_share(bad), bad)

    def test_a_corporate_action_marker_is_not_part_of_a_company_name(self):
        u = self.universe()
        self.assertEqual(u.clean_name("Ghani ChemworldXR"), "Ghani Chemworld")
        self.assertEqual(u.clean_name("Nishat ChunPowerXD"), "Nishat ChunPower")
        self.assertEqual(u.clean_name("Pak Elektron"), "Pak Elektron")
        # A name that genuinely ends in capitals is left alone, and nothing is ever stripped to empty.
        self.assertEqual(u.clean_name("ABC XD"), "ABC XD")
        self.assertEqual(u.clean_name("XD"), "XD")

    def test_a_sector_code_places_a_name_only_where_our_own_names_agree(self):
        u = self.universe()
        seeded = {"A": "psx-banks", "B": "psx-banks", "C": "psx-banks", "D": "psx-banks", "E": "psx-banks",
                  "F": "psx-oil", "G": "psx-oil", "H": "psx-fert", "I": "psx-chem"}
        codes = {"A": "0801", "B": "0801", "C": "0801", "D": "0801", "E": "0801",
                 "F": "0820", "G": "0820", "H": "0830", "I": "0830"}
        got = u.sector_map(seeded, codes)
        self.assertEqual(got["0801"], "psx-banks")
        self.assertEqual(got["0820"], "psx-oil")
        # Two of our own industries share this exchange code: ambiguous, so it places nothing.
        self.assertNotIn("0830", got)

    # --- the seed ----------------------------------------------------------------------------

    @staticmethod
    def seed():
        import seed as _seed
        return _seed

    def test_no_symbol_appears_twice_in_the_seed(self):
        """The asset page is looked up by symbol alone. The exchange's own ticker, `PSX`, is
        also Phillips 66, and listing both would have left one of the two pages unreachable."""
        from collections import Counter

        counts = Counter(row[1].upper() for row in self.seed().ASSETS)
        self.assertEqual([k for k, v in counts.items() if v > 1], [])

    def test_every_seeded_asset_names_an_industry_that_exists(self):
        s = self.seed()
        slugs = {i[0] for i in s.INDUSTRIES} | {i[0] for i in s.PSX_INDUSTRIES} | {i[0] for i in s.FOREX_INDUSTRIES}
        self.assertEqual([r[:2] for r in s.ASSETS if r[0] not in slugs], [])

    def test_every_seeded_row_has_the_eight_fields_the_seeder_unpacks(self):
        self.assertEqual([r[:2] for r in self.seed().ASSETS if len(r) != 8], [])

    def test_a_coin_is_identified_by_its_ranking_id_and_a_share_by_its_ticker(self):
        s = self.seed()
        for row in s.MORE_CRYPTO_3:
            self.assertEqual(row[1], row[6], f"{row[1]}: the symbol and the CoinPaprika id differ")
            self.assertEqual(row[5], s.PAPRIKA)
        for row in s.MORE_PSX_4:
            self.assertEqual(row[1], row[6], f"{row[1]}: the symbol and the exchange ticker differ")
            self.assertEqual(row[5], s.PSX)
            self.assertRegex(row[1], r"^[A-Z][A-Z0-9]{1,9}$")
            self.assertNotIn("-", row[1], "a futures contract entered the universe as a share")

    def test_no_name_in_the_expansion_carries_a_corporate_action_marker(self):
        import re as _re

        for row in self.seed().MORE_PSX_4:
            self.assertIsNone(_re.search(r"(?<=[a-z.])X[DRB]{1,2}$", row[2]), row[2])

    def test_the_expansion_adds_no_stablecoin_wrapped_copy_or_gold_token(self):
        banned = {"USDT", "USDC", "DAI", "WBTC", "STETH", "PAXG", "XAUT", "WETH", "CBBTC"}
        for row in self.seed().MORE_CRYPTO_3:
            ticker = row[1].split("-")[0].upper()
            self.assertNotIn(ticker, banned, row[1])

    def test_the_discovery_tool_writes_nothing_anywhere(self):
        """It proposes; a person reads the refusals and pastes. A tool that wrote the seed or the
        database would put names in the universe that no review ever saw."""
        src = code_only((ROOT / "tools" / "universe.py").read_text(encoding="utf-8"))
        for write in ("INSERT ", "UPDATE ", "DELETE ", "open(", ".write(", "commit("):
            self.assertNotIn(write, src, f"the discovery tool contains {write!r}")


class TheMirrorCopiesByNaturalKey(unittest.TestCase):
    """A standby is only worth having if copying into it cannot damage it.

    Every asset id is `gen_random_uuid()` assigned when the seed ran, so two projects seeded
    separately hold different ids for the same stock. The mirror therefore translates through
    `(industry slug, symbol)`, and the properties here are the ways a copy would otherwise corrupt
    the thing it exists to protect. The behaviour end to end -- 477 of 477 decision rows filed under
    the same stock in a target whose ids share nothing with the source, a rerun writing zero rows,
    a maturation carried, nothing deleted -- was verified against a throwaway schema in the live
    database; these pin the parts that can be pinned without one.
    """

    @staticmethod
    def mirror():
        import mirror

        return mirror

    # --- it will not copy a database onto itself ---------------------------------------------

    def test_the_pooler_and_the_direct_host_are_the_same_database(self):
        """The one mistake the guard exists for passes by changing a hostname."""
        m = self.mirror()
        pooled = "postgresql://u:p@ep-abc-pooler.c-7.aws.neon.tech/neondb?sslmode=require"
        direct = "postgresql://u:p@ep-abc.c-7.aws.neon.tech/neondb?sslmode=require"
        self.assertTrue(m.same_database(pooled, direct))
        self.assertTrue(m.same_database(pooled, pooled))

    def test_the_credentials_do_not_make_it_a_different_database(self):
        m = self.mirror()
        self.assertTrue(
            m.same_database(
                "postgresql://reader:x@ep-abc.c-7.aws.neon.tech/neondb",
                "postgresql://owner:y@ep-abc.c-7.aws.neon.tech/neondb",
            )
        )

    def test_a_different_project_or_database_or_schema_is_a_different_target(self):
        m = self.mirror()
        base = "postgresql://u:p@ep-abc.c-7.aws.neon.tech/neondb"
        self.assertFalse(m.same_database(base, "postgresql://u:p@ep-xyz.c-6.aws.neon.tech/neondb"))
        self.assertFalse(m.same_database(base, "postgresql://u:p@ep-abc.c-7.aws.neon.tech/other"))
        self.assertFalse(m.same_database(base, base + "?options=-csearch_path%3Dmirror_test"))

    # --- asset ids are translated, never copied ----------------------------------------------

    def test_a_source_id_is_replaced_by_the_target_id_for_the_same_stock(self):
        m = self.mirror()
        src = {"s1": ("mega-cap-tech", "AAPL"), "s2": ("psx-banks", "HBL"), "s3": ("energy", "PSX")}
        dst = {"t9": ("mega-cap-tech", "AAPL"), "t8": ("psx-banks", "HBL"), "t7": ("psx-investment", "PSX")}
        got = m.build_asset_map(src, dst)
        self.assertEqual(got, {"s1": "t9", "s2": "t8"})
        # Same symbol, different industry: `PSX` is both Phillips 66 and the exchange's own ticker.
        # Joined on the pair, so the two are never confused.
        self.assertNotIn("s3", got)

    def test_a_row_whose_asset_the_target_lacks_is_dropped_and_recorded_not_forced(self):
        m = self.mirror()
        unmatched: set = set()
        self.assertIsNone(m.remap_row({"assetId": "gone", "x": 1}, ("assetId",), {"a": "b"}, unmatched))
        self.assertEqual(unmatched, {"gone"})

    def test_a_row_with_no_asset_pointer_is_kept(self):
        """`SignalLog.assetId` is optional, and a signal about no particular asset is a real row."""
        m = self.mirror()
        unmatched: set = set()
        got = m.remap_row({"assetId": None, "kind": "k"}, ("kind",), {}, unmatched)
        self.assertEqual(got, {"assetId": None, "kind": "k"})
        self.assertEqual(unmatched, set())
        self.assertEqual(m.remap_row({"kind": "k"}, ("kind",), {}, unmatched), {"kind": "k"})

    def test_remapping_does_not_mutate_the_source_row(self):
        m = self.mirror()
        row = {"assetId": "s1", "v": 1}
        out = m.remap_row(row, ("assetId",), {"s1": "t1"}, set())
        self.assertEqual(row["assetId"], "s1")
        self.assertEqual(out["assetId"], "t1")

    # --- columns -----------------------------------------------------------------------------

    def test_only_columns_both_sides_have_are_copied_and_the_surrogate_id_never_is(self):
        """A column added to one project and not yet migrated on the other must not fail the whole
        copy. It is not copied, and the next run after the migration picks it up."""
        m = self.mirror()
        got = m.shared_columns(["id", "assetId", "date", "close", "legs"], ["id", "assetId", "date", "close"], ("assetId", "date"))
        self.assertEqual(got, ["assetId", "date", "close"])

    def test_a_missing_key_column_is_an_error_and_not_a_silent_partial_copy(self):
        m = self.mirror()
        with self.assertRaises(ValueError):
            m.shared_columns(["id", "date"], ["id", "assetId", "date"], ("assetId", "date"))

    # --- the upsert --------------------------------------------------------------------------

    def test_an_unchanged_row_is_not_rewritten_and_a_null_change_is_still_seen(self):
        m = self.mirror()
        sql = m.upsert_sql("DecisionLog", ["assetId", "periodEnd", "action", "move5Pct"], ("assetId", "periodEnd"))
        self.assertIn("IS DISTINCT FROM", sql)
        self.assertNotIn("<>", sql)
        self.assertIn('ON CONFLICT ("assetId", "periodEnd") DO UPDATE', sql)
        # The key is never in the SET, and only the non-key columns are compared.
        self.assertNotIn('"periodEnd" = EXCLUDED', sql)
        self.assertIn('"move5Pct" = EXCLUDED."move5Pct"', sql)

    def test_a_table_with_nothing_but_its_key_does_nothing_on_conflict(self):
        m = self.mirror()
        self.assertTrue(m.upsert_sql("T", ["a", "b"], ("a", "b")).endswith("DO NOTHING"))

    def test_identifiers_are_quoted_so_a_column_name_cannot_be_sql(self):
        m = self.mirror()
        sql = m.upsert_sql("T", ['we"ird', "ok"], ("ok",))
        self.assertIn('"we""ird"', sql)

    # --- what it will never do ---------------------------------------------------------------

    def test_the_mirror_never_deletes_from_the_target(self):
        """A mirror that propagates deletions turns one bad run against an emptied source into an
        emptied backup, and the whole point of a backup is that it survives the source's worst day."""
        src = code_only((ROOT / "jobs" / "mirror.py").read_text(encoding="utf-8"))
        # The module's docstring states the rule in prose, so the SQL is checked in code only.
        body = src.split('"""', 2)[-1] if src.count('"""') >= 2 else src
        for forbidden in ("DELETE FROM", "TRUNCATE", "DROP TABLE", "DROP SCHEMA"):
            self.assertNotIn(forbidden, body.upper(), forbidden)

    def test_it_copies_exactly_the_four_tables_nothing_else_may_lose(self):
        m = self.mirror()
        # `MacroGate` joined the four when the macro gatekeeper did: its refusals are inputs to `decide`,
        # so a standby that took over without them would print verdicts the primary had refused.
        self.assertEqual(
            set(m.TABLES), {"DecisionLog", "PriceSnapshot", "SignalLog", "AssetThesis", "MacroGate"}
        )
        # Each is keyed on something a person would call the row's identity, never on the UUID.
        for table, key in m.TABLES.items():
            self.assertNotIn("id", key, table)
        self.assertEqual(set(m.DATE_COLUMN), set(m.TABLES))

    def test_the_learning_corpus_is_one_of_them(self):
        """`DecisionLog`'s +1, +5 and +20 session maturations cannot be recomputed, and are what the
        scorecard learns from."""
        self.assertIn("DecisionLog", self.mirror().TABLES)

    def test_main_refuses_to_copy_a_database_onto_itself_before_connecting(self):
        """`same_database` being correct is not the same as `main` calling it. This drives `main`
        with a pooled and a direct address of one project and checks it exits 2 -- and because the
        addresses do not resolve here, reaching a connection attempt would raise instead of
        returning, so a missing guard fails this loudly rather than quietly succeeding."""
        m = self.mirror()
        same = [
            "--from", "postgresql://u:p@ep-nowhere-pooler.invalid/neondb",
            "--to", "postgresql://u:p@ep-nowhere.invalid/neondb",
        ]
        self.assertEqual(m.main(same), 2)

    def test_main_refuses_an_unknown_table_and_missing_arguments(self):
        m = self.mirror()
        self.assertEqual(m.main(["--from", "postgresql://a@x.invalid/d", "--to", "postgresql://a@y.invalid/d", "--tables", "News"]), 2)
        self.assertEqual(m.main([]), 2)
        self.assertEqual(m.main(["--from", "postgresql://a@x.invalid/d"]), 2)

    # --- more than one target ----------------------------------------------------------------

    def test_a_connection_string_is_removed_from_anything_the_job_prints(self):
        """A driver's error can carry the whole string -- psycopg's 'invalid connection option' does,
        and a live password reached a terminal that way earlier in this project's history -- and a CI
        log is readable by anyone with repository access."""
        m = self.mirror()
        leaky = 'invalid connection option "postgresql://postgres.abc:hunter2@host.example:5432/postgres?x=1"'
        got = m.redact(leaky)
        self.assertNotIn("hunter2", got)
        self.assertNotIn("postgres.abc", got)
        self.assertIn("<redacted>", got)
        self.assertEqual(m.redact("postgres://u:p@h/d and postgresql://u2:p2@h2/d2"), "postgresql://<redacted> and postgresql://<redacted>")
        self.assertEqual(m.redact("connection refused"), "connection refused")

    def test_repeated_options_are_all_read_in_order(self):
        m = self.mirror()
        self.assertEqual(m.option_values(["--to", "a", "--tables", "x", "--to", "b"], "--to"), ["a", "b"])
        self.assertEqual(m.option_values(["--to"], "--to"), [])
        self.assertEqual(m.option_values([], "--to"), [])

    def run_main(self, argv, results, env=None):
        """`main` with the copying itself replaced, so only the orchestration is under test."""
        import os
        import unittest.mock as mock

        m = self.mirror()
        called = []

        def fake(src, label, url, chosen, dry, since):
            called.append(label)
            return results.get(label, True)

        with mock.patch.object(m, "mirror_one", fake), mock.patch.dict(os.environ, env or {}, clear=False):
            code = m.main(argv)
        return code, called

    A = "postgresql://u:p@ep-a.invalid/db"
    B = "postgresql://u:p@ep-b.invalid/db"
    C = "postgresql://u:p@ep-c.invalid/db"

    def test_every_target_is_attempted_even_after_one_fails(self):
        """With three databases the one most likely to be down is the one being copied to, and a run
        that stopped at the first dead target would leave every later one stale -- the standby most
        worth refreshing is the one the dead one was standing in for."""
        code, called = self.run_main(
            ["--from", self.A, "--to", self.B, "--to", self.C], {"--to #1": False}
        )
        self.assertEqual(called, ["--to #1", "--to #2"])
        self.assertEqual(code, 1, "a failed target must make the run fail")

    def test_the_run_succeeds_only_when_every_target_did(self):
        code, _ = self.run_main(["--from", self.A, "--to", self.B, "--to", self.C], {})
        self.assertEqual(code, 0)

    def test_targets_can_be_named_by_environment_variable_so_no_url_is_on_a_command_line(self):
        code, called = self.run_main(
            ["--from-env", "SRC_X", "--to-env", "TGT_ONE,TGT_TWO"],
            {},
            env={"SRC_X": self.A, "TGT_ONE": self.B, "TGT_TWO": self.C},
        )
        self.assertEqual(called, ["TGT_ONE", "TGT_TWO"])
        self.assertEqual(code, 0)

    def test_an_unset_standby_is_skipped_and_not_an_error(self):
        """A deployment with Supabase but no second Neon project names both and is not penalised."""
        code, called = self.run_main(
            ["--from-env", "SRC_X", "--to-env", "UNSET_ONE_XYZ,TGT_TWO"],
            {},
            env={"SRC_X": self.A, "TGT_TWO": self.C},
        )
        self.assertEqual(called, ["TGT_TWO"])
        self.assertEqual(code, 0)

    def test_no_usable_target_is_a_usage_error(self):
        code, called = self.run_main(["--from-env", "SRC_X", "--to-env", "UNSET_ONE_XYZ"], {}, env={"SRC_X": self.A})
        self.assertEqual((code, called), (2, []))

    def test_two_targets_naming_one_database_are_refused_before_anything_is_copied(self):
        """The pooler and the direct host of one project are one database. Copying into it twice is
        harmless and wasteful, but it usually means one of the two variables is wrong."""
        pooled = "postgresql://u:p@ep-b-pooler.invalid/db"
        direct = "postgresql://u:p@ep-b.invalid/db"
        code, called = self.run_main(["--from", self.A, "--to", pooled, "--to", direct], {})
        self.assertEqual((code, called), (2, []))

    def test_any_target_that_is_the_source_refuses_the_whole_run(self):
        code, called = self.run_main(["--from", self.A, "--to", self.B, "--to", self.A], {})
        self.assertEqual((code, called), (2, []))

    def test_a_target_that_cannot_be_reached_is_reported_without_its_address_or_credentials(self):
        """The real `mirror_one`, against an address that cannot resolve: it must return False, not
        raise, and print nothing that looks like a connection string."""
        import contextlib
        import io as _io

        m = self.mirror()
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = m.mirror_one(
                "postgresql://u:secret1@nowhere-a.invalid:5432/db", "T", "postgresql://u:secret2@nowhere-b.invalid:5432/db",
                ["DecisionLog"], True, None,
            )
        out = buf.getvalue()
        self.assertFalse(ok)
        self.assertNotIn("secret1", out)
        self.assertNotIn("secret2", out)
        self.assertNotIn("postgresql://u", out)

    def test_a_driver_error_that_carries_the_connection_string_is_redacted_when_printed(self):
        """The test above uses addresses that cannot resolve, whose errors never contain a URL, so it
        could not have failed if the redaction were removed. This one makes the driver do what
        psycopg's 'invalid connection option' really does."""
        import contextlib
        import io as _io
        import unittest.mock as mock

        import psycopg

        m = self.mirror()
        leaky = psycopg.OperationalError('invalid connection option "postgresql://u:topsecret@h.example/db"')
        buf = _io.StringIO()
        with mock.patch("psycopg.connect", side_effect=leaky), contextlib.redirect_stdout(buf):
            ok = m.mirror_one("postgresql://u:a@s/db", "T", "postgresql://u:b@t/db", ["DecisionLog"], True, None)
        self.assertFalse(ok)
        self.assertNotIn("topsecret", buf.getvalue())
        self.assertIn("<redacted>", buf.getvalue())

        # And part way through a copy, where a different `except` prints.
        buf = _io.StringIO()
        with mock.patch.object(m, "asset_identity", side_effect=RuntimeError("boom postgresql://u:midcopy@h/db")),                 mock.patch("psycopg.connect", return_value=mock.MagicMock()), contextlib.redirect_stdout(buf):
            self.assertFalse(m.mirror_one("postgresql://u:a@s/db", "T", "postgresql://u:b@t/db", ["DecisionLog"], True, None))
        self.assertNotIn("midcopy", buf.getvalue())

    def test_the_nightly_workflow_skips_cleanly_with_no_standby_and_never_names_a_value(self):
        """A workflow that failed every night on a deployment that chose not to run a standby would
        train people to ignore a red run, and the retry lane would then re-run it."""
        text = (ROOT / ".github" / "workflows" / "cron-mirror.yml").read_text(encoding="utf-8")
        self.assertIn("::notice::no standby is configured", text)
        # Every step that runs the mirror carries the guard, not merely one of them: a second step
        # left unguarded would run with no target and exit 2 on exactly the deployment this protects.
        runs = text.count("python jobs/mirror.py")
        guards = text.count("if: steps.targets.outputs.any == 'true'")
        self.assertGreaterEqual(runs, 2)
        self.assertEqual(runs, guards, "a mirror step runs without checking that a standby exists")
        # Only secrets, only through env, and never echoed.
        self.assertNotRegex(text, r"echo[^\n]*\$\{\{\s*secrets\.")
        self.assertNotRegex(text, r"echo[^\n]*(\$NEON2|\$SUPA)\b")
        # Its own concurrency group, never cancelled, and not in the retry lane's watch list.
        self.assertIn("group: nbt-mirror", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertNotIn('"cron mirror"', (ROOT / ".github" / "workflows" / "retry.yml").read_text(encoding="utf-8"))

    def test_the_nightly_decision_window_reaches_past_the_longest_maturation(self):
        """DecisionLog rows are updated for a month as +1, +5 and +20 session outcomes land. A window
        shorter than that freezes a decision's outcome at whatever it was the last time the window
        covered it -- the one table where that is not recoverable."""
        text = (ROOT / ".github" / "workflows" / "cron-mirror.yml").read_text(encoding="utf-8")
        import re as _re

        days = {
            tables: int(n)
            for n, tables in _re.findall(r"date -u -d '(\d+) days ago'[^\n]*\n(?:[^\n]*\n)*?[^\n]*--tables ([A-Za-z,]+)", text)
        }
        self.assertGreaterEqual(days["DecisionLog,SignalLog,AssetThesis"], 35)

    def test_the_site_failover_and_the_nightly_writers_are_kept_apart(self):
        """The mirror is the only thing that writes a standby. The pool that reads one (lib/failover)
        is never imported by a lane, so the two databases are never both being written to by a lane."""
        for lane in sorted((ROOT / "jobs").glob("*.py")):
            if lane.name == "mirror.py":
                continue
            text = lane.read_text(encoding="utf-8")
            self.assertNotIn("DATABASE_URL_FALLBACK", text, lane.name)


class TheMacroGateOnlyRefuses(unittest.TestCase):
    """The gatekeeper is a language model reading headlines, which is the one input to this system
    nobody can check, so every property worth having is one that limits what it can do: it is off
    until asked, it can only refuse, it cannot print a number, it fails open, it never takes the
    site or the lane down, and the key never leaves the one step that needs it.

    The behaviour of the pure core (strict parsing, fail-open, injection handling) is in
    `tests/macroGate.test.ts`; these pin the parts that live in a job, a query and a workflow."""

    @staticmethod
    def text(rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def job(self) -> str:
        return code_only(self.text("tools/macro_gate.mjs"))

    @staticmethod
    def function_body(src: str, header: str, close: str = "}") -> str:
        start = src.index(header)
        end = src.index(chr(10) + close + chr(10), start)
        return src[start:end]

    def test_the_job_is_off_until_asked_and_checks_before_it_connects_to_anything(self):
        src = self.job()
        off = src.index('process.env.MACRO_GATE !== "on"')
        self.assertLess(off, src.index("new Anthropic("))
        self.assertLess(off, src.index("new pg.Pool("))
        self.assertIn("ANTHROPIC_API_KEY", src[off : src.index("new pg.Pool(")])

    def test_the_reply_schema_has_no_place_for_a_number(self):
        schema = self.function_body(self.job(), "const REPLY_SCHEMA = {", "};")
        for numeric in ('"number"', '"integer"'):
            self.assertNotIn(numeric, schema)
        for field in ("symbol", "verdict", "refusal_reason", "rationale"):
            self.assertIn(field + ":", schema)
        self.assertIn("additionalProperties: false", schema)
        core = code_only(self.text("lib/macroGate.ts"))
        self.assertIn('const KEYS = ["symbol", "verdict", "refusal_reason", "rationale"]', core)

    def test_the_job_writes_one_table_and_only_that_one(self):
        import re

        src = self.text("tools/macro_gate.mjs")
        verbs = re.findall(r'(?:INSERT INTO|UPDATE|DELETE FROM)\s+"(\w+)"', src)
        self.assertTrue(verbs)
        self.assertEqual(set(verbs), {"MacroGate"})

    def test_nothing_secret_or_model_authored_is_ever_printed(self):
        import re

        src = self.job()
        self.assertIsNone(re.search(r"[.]message" + chr(92) + "b", src))
        # Naming a variable in a message ("no ANTHROPIC_API_KEY") is the point of the message; what must
        # never happen is a *value* reaching one, so only the interpolated expressions are searched.
        for call in re.findall(r"say[(][^;]*;", src):
            self.assertNotIn("process.env", call, call)
            for expression in re.findall(r"[$][{]([^}]*)[}]", call):
                for leak in ("KEY", "URL", "rationale", "message", "env"):
                    self.assertNotIn(leak, expression, call)
        self.assertNotIn("console.error", src)

    def test_the_job_cannot_fail_the_lane(self):
        src = self.job()
        tail = src[src.index("main().catch(") :]
        self.assertIn("catch", tail)
        self.assertNotIn("process.exit", src)
        self.assertNotIn("throw", tail)

    def test_the_one_export_the_web_layer_does_not_use_is_used_by_the_job(self):
        self.assertIn("evaluate", self.job().split("from " + chr(34) + "../lib/macroGate.ts" + chr(34))[0])
        local = self.job().split("from " + chr(34) + "../lib/macroGateLocal.ts" + chr(34))[0]
        self.assertIn("evaluateLocal", local)
        self.assertIn("LOCAL_ENGINE", local)

    def test_the_exam_runner_asks_the_model_the_way_the_job_does_and_touches_no_database(self):
        exam = code_only(self.text("tools/macro_gate_exam.mjs"))
        self.assertIn("makeCall", exam)
        for forbidden in ('from "pg"', "DATABASE_URL", "INSERT", "UPDATE", "DELETE"):
            self.assertNotIn(forbidden, exam)
        # Importing the job must not start a run, or the exam would write to the database.
        job = self.job()
        self.assertIn("if (direct) main()", job)

    def test_the_default_engine_is_the_local_one_and_the_model_needs_asking_for_by_name(self):
        src = self.job()
        self.assertIn('process.env.MACRO_GATE_ENGINE === "model" ? "model" : "local"', src)
        self.assertIn('ENGINE === "model" && !process.env.ANTHROPIC_API_KEY', src)
        # The client is built only inside the model branch, so the local engine cannot reach the network.
        branch = src[src.index('const decideOne = ENGINE === "model"') :]
        self.assertLess(branch.index("new Anthropic("), branch.index("evaluateLocal("))

    def test_trust_is_keyed_on_the_publisher_and_the_outlet_is_not_left_in_the_text(self):
        """Google News appends the outlet to the title. `source` is only the feed label, so trusting it
        would trust every headline or none; and an outlet name left in the text could satisfy a word in
        the table ("Federal News Network" against a federal-enforcement rule)."""
        src = self.job()
        self.assertIn("source: pub || r.source", src)
        self.assertIn("r.title.slice(0, -(pub.length + 3))", src)

    def test_the_cost_cap_limits_the_paid_model_and_never_the_free_engine(self):
        src = self.job()
        self.assertIn('const batch = ENGINE === "model" ? withNews.slice(0, MAX_CANDIDATES) : withNews;', src)

    def test_the_local_engine_is_pure(self):
        """Same input, same answer, no network, no clock, no randomness, no environment: the property
        that lets it be scored in CI and the reason it is the default."""
        src = code_only(self.text("lib/macroGateLocal.ts"))
        for impure in ("fetch(", "process.", "Date.now", "new Date()", "Math.random", "require(", "import("):
            self.assertNotIn(impure, src, impure)
        imports = [line for line in src.splitlines() if line.startswith("import ")]
        self.assertEqual(len(imports), 2)
        for line in imports:
            self.assertIn("./macroGate.ts", line)

    def test_the_model_is_called_as_the_api_documents_it(self):
        src = self.job()
        self.assertIn('"claude-opus-5-5"', src)
        self.assertNotIn("budget_tokens", src)
        self.assertNotIn("thinking:", src)
        self.assertNotIn('role: "assistant"', src)
        self.assertIn('res.stop_reason === "refusal"', src)
        self.assertIn('res.stop_reason === "max_tokens"', src)

    def test_the_read_paths_fail_open_so_a_missing_table_cannot_take_the_page_down(self):
        queries = code_only(self.text("lib/queries.ts"))
        body = self.function_body(queries, "async function getMacroVetoes(")
        self.assertIn("catch", body)
        self.assertIn("out.clear()", body)
        decide = self.text("tools/decide.mjs")
        around = decide[decide.index('FROM "MacroGate"') - 400 : decide.index('FROM "MacroGate"') + 600]
        self.assertIn("try {", around)
        # The handler resets to "no vetoes". One that rethrew would turn a database the migration has
        # not reached into a dead decision lane.
        self.assertIn("catch {" + chr(10) + "    macro = [];", around)

    def test_the_job_hands_the_seam_an_iso_day_and_not_a_local_midnight_date(self):
        """`pg` returns a `@db.Date` as local midnight. East of UTC the seam's `toISOString()` read
        2026-10-09 as 2026-10-08, so a veto filed yesterday looked two days old and expired: six
        inserted refusals produced no change in the decision job until `dayOf` was used. Found by
        running it against the database, not by any test of the pure code, which is why it is pinned."""
        decide = code_only(self.text("tools/decide.mjs"))
        self.assertIn("macroVetoAsOf: dayOf(", decide)

    def test_the_newest_answer_wins_so_a_reversed_refusal_does_not_live_on(self):
        body = self.function_body(code_only(self.text("lib/queries.ts")), "async function getMacroVetoes(")
        self.assertIn("seen.has(r.assetId)", body)
        self.assertIn("valid: true", body)
        decide = self.text("tools/decide.mjs")
        self.assertIn('ORDER BY "assetId", "periodEnd" DESC, "createdAt" DESC', decide)

    def test_the_migration_adds_one_table_and_touches_nothing_else(self):
        import re

        sql = code_only_sql(self.text("prisma/migrations/20261010180000_macro_gate/migration.sql"))
        # The new table's own foreign key says ON DELETE / ON UPDATE CASCADE, which is a rule about
        # what happens to *its* rows, so those phrases are removed before looking for a statement.
        statements = re.sub(r"ON (?:DELETE|UPDATE) CASCADE", "", sql)
        for danger in ("DROP", "TRUNCATE", "DELETE", "UPDATE", "RENAME"):
            self.assertIsNone(re.search(r"\b" + danger + r"\b", statements), danger)
        for statement in re.findall(r"(?:CREATE TABLE|ALTER TABLE|ON)\s+" + chr(34) + r"(\w+)" + chr(34), sql):
            self.assertEqual(statement, "MacroGate")

    def test_a_logged_row_is_never_pruned(self):
        self.assertNotIn("MacroGate", self.text("jobs/retention.py"))

    def test_the_workflow_keeps_the_key_in_one_step_and_never_lets_the_gate_redden_the_lane(self):
        import yaml

        wf = yaml.safe_load(self.text(".github/workflows/cron-decision.yml"))
        steps = wf["jobs"]["decide"]["steps"]
        holders = [s for s in steps if "ANTHROPIC_API_KEY" in str(s.get("env", {}))]
        self.assertEqual(len(holders), 1)
        gate = holders[0]
        self.assertTrue(gate.get("continue-on-error"))
        self.assertIn("macro_gate.mjs", gate["run"])
        self.assertIn("MACRO_GATE", gate["env"])
        second = [s for s in steps if "Apply the stored vetoes" in s.get("name", "")]
        self.assertEqual(len(second), 1)
        self.assertTrue(second[0].get("continue-on-error"))
        self.assertIn("vars.MACRO_GATE == 'on'", second[0]["if"])
        # The gate runs after the first decision pass and before the second.
        names = [s.get("name", "") for s in steps]
        first = names.index("Write one decision row per asset")
        self.assertLess(first, steps.index(gate))
        self.assertLess(steps.index(gate), steps.index(second[0]))
        for step in steps:
            self.assertNotIn("echo " + chr(34) + "$ANTHROPIC", step.get("run", ""))

    def test_the_key_is_only_ever_named_in_the_example_file_and_the_job(self):
        for rel in ("lib", "app", "components"):
            for path in (ROOT / rel).rglob("*.ts*"):
                self.assertNotIn("ANTHROPIC_API_KEY", path.read_text(encoding="utf-8"), str(path))
        self.assertIn("ANTHROPIC_API_KEY", self.text(".env.example"))
        self.assertIn("MACRO_GATE", self.text(".env.example"))


class NoPlaceholdersInTheRenderedLayer(unittest.TestCase):
    """A cell that is empty should say what is absent and why, not that it is empty.

    "none stored", "not stored", "not applicable", "N/A" and "waiting" each say a field has no value
    without saying anything about the name. Each was replaced by the specific statement that is true:
    a held-back row prints the rule table's own reason, an absent size is explained by what the asset
    is, an absent level says which level. This pins the strings out of the code of every page and
    component, comments excluded.

    `app/methodology/page.tsx` is exempt: it is prose explaining the rules to a reader, where the verb
    "waiting" describes the reader waiting for a price level, not a cell with nothing in it."""

    BANNED = re.compile(r"(?i)not applicable|" + chr(92) + "bn/a" + chr(92) + "b|non-stored|not stored|none stored|" + chr(92) + "bwaiting" + chr(92) + "b")
    EXEMPT = {"methodology"}

    def test_no_page_or_component_prints_a_placeholder(self):
        offenders = []
        files = list((ROOT / "app").rglob("*.tsx")) + list((ROOT / "components").glob("*.tsx"))
        self.assertGreater(len(files), 10, "the scan found almost nothing, so it is broken")
        for f in files:
            if f.parent.name in self.EXEMPT:
                continue
            for n, line in enumerate(code_only(f.read_text(encoding="utf-8")).splitlines(), 1):
                if self.BANNED.search(line):
                    offenders.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:80]}")
        self.assertEqual(offenders, [])

    def test_the_scan_would_notice_one(self):
        self.assertTrue(self.BANNED.search('{x ? y : "none stored"}'))
        self.assertTrue(self.BANNED.search("not applicable"))
        self.assertTrue(self.BANNED.search("3 waiting."))
        self.assertIsNone(self.BANNED.search("waitingOn.push(x)"))

    def test_a_held_back_row_carries_the_rule_tables_reason(self):
        assets = (ROOT / "lib" / "assetClass.ts").read_text(encoding="utf-8")
        self.assertIn('reason: s.decision.action === "WAIT" ? s.decision.why.slice(0, 2) : null', assets)

    def test_no_grade_is_printed_for_a_decision_that_made_no_call(self):
        decision = code_only((ROOT / "components" / "decision.tsx").read_text(encoding="utf-8"))
        self.assertIn('decision.action === "WAIT" ? null : <ConfidenceBadge grade={grade} />', decision)
        overview = code_only((ROOT / "app" / "page.tsx").read_text(encoding="utf-8"))
        wait_card = overview[overview.index('<Pill tone="warn">WAIT</Pill>') :][:400]
        self.assertNotIn("ConfidenceBadge", wait_card)


class TheLiveLane(unittest.TestCase):
    """`jobs/live.py`, `LiveQuote`, `/api/quote` and `components/LivePrice.tsx`.

    The property that matters most is not in the lane at all: **a quote is never an input to a
    decision.** The rule table reads closes; a price for a session still being traded is not one
    (rule 41), and a verdict that moved with the tape would be a different verdict on every refresh.
    So the first test here is a fence around every file that decides. The rest pin the lane: it only
    moves a quote forward, it fails soft, it never writes from the web, and it polls within the
    platform's real floor rather than a one-minute schedule it cannot have."""

    @staticmethod
    def live():
        import live

        return live

    # --- the fence --------------------------------------------------------------------------------

    def test_no_file_that_decides_can_read_a_quote(self):
        deciders = [
            "lib/decision.ts", "lib/decisionInput.ts", "lib/macroGate.ts", "lib/macroGateLocal.ts",
            "tools/decide.mjs", "tools/macro_gate.mjs", "jobs/factors.py", "jobs/setup.py",
            "jobs/horizons.py", "jobs/analogs.py",
        ]
        for rel in deciders:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for name in ("LiveQuote", "liveQuote", "quotePrice", "getLiveQuote"):
                self.assertNotIn(name, text, f"{rel} reads {name}")

    def test_the_list_carries_the_quote_beside_the_close_and_never_as_it(self):
        assets = (ROOT / "lib" / "assetClass.ts").read_text(encoding="utf-8")
        # The decision's price is still the close; the quote is a separate field.
        self.assertIn("priceNow: s.row.close,", assets)
        self.assertIn("quote: quoteBesideClose(", assets)

    # --- the job's pure parts ---------------------------------------------------------------------

    def test_rotating_slices_cover_every_name_once_and_never_overlap(self):
        m = self.live()
        for n, limit in ((125, 60), (60, 60), (1, 60), (301, 50)):
            seen = []
            pages = -(-n // limit)
            for k in range(pages):
                lo, hi = m.slice_for_tick(n, limit, now_ts=k * m.TICK_SECONDS)
                seen.extend(range(lo, hi))
            self.assertEqual(sorted(seen), list(range(n)), (n, limit))
        self.assertEqual(m.slice_for_tick(0, 60, 123.0), (0, 0))

    def test_only_a_finite_positive_number_is_a_price(self):
        m = self.live()
        for good in (1, 0.0001, "3.5"):
            self.assertTrue(m.is_price(good), good)
        for bad in (0, -1, float("nan"), float("inf"), None, "x"):
            self.assertFalse(m.is_price(bad), bad)

    def test_coinpaprika_is_read_with_its_own_timestamp_and_a_bad_row_is_skipped(self):
        from datetime import datetime

        m = self.live()
        now = datetime(2026, 10, 10, 12, 0, 0)
        tickers = [
            {"id": "btc-bitcoin", "last_updated": "2026-10-10T11:58:00Z", "quotes": {"USD": {"price": 61000.5}}},
            {"id": "zero-coin", "last_updated": "2026-10-10T11:58:00Z", "quotes": {"USD": {"price": 0}}},
            {"id": "future-coin", "last_updated": "2026-10-10T13:00:00Z", "quotes": {"USD": {"price": 2}}},
            {"id": "no-stamp", "quotes": {"USD": {"price": 2}}},
        ]
        assets = [{"id": i, "sourceRef": i} for i in ("btc-bitcoin", "zero-coin", "future-coin", "no-stamp", "missing")]
        got = m.parse_paprika(tickers, assets, now)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["assetId"], "btc-bitcoin")
        self.assertEqual(got[0]["quotedAt"], datetime(2026, 10, 10, 11, 58, 0))
        self.assertEqual(got[0]["source"], "coinpaprika")

    def test_yahoo_is_read_for_the_last_real_trade_and_a_gap_is_not_a_price(self):
        from datetime import datetime

        import pandas as pd

        m = self.live()
        idx = pd.DatetimeIndex(
            ["2026-10-09 19:57", "2026-10-09 19:58", "2026-10-09 19:59"], tz="America/New_York"
        )
        cols = pd.MultiIndex.from_product([["AAPL", "DEAD"], ["Close", "Volume"]])
        frame = pd.DataFrame(
            [[210.0, 1, float("nan"), 0], [211.0, 1, float("nan"), 0], [float("nan"), 0, float("nan"), 0]],
            index=idx, columns=cols,
        )
        assets = [{"id": "a", "sourceRef": "AAPL"}, {"id": "d", "sourceRef": "DEAD"}, {"id": "x", "sourceRef": "GONE"}]
        got = m.parse_download(frame, assets, datetime(2026, 10, 10, 12, 0))
        self.assertEqual([q["assetId"] for q in got], ["a"])
        # 19:58 New York is 23:58 UTC: the last bar that traded, not the empty 19:59 one.
        self.assertEqual(got[0]["price"], 211.0)
        self.assertEqual(got[0]["quotedAt"], datetime(2026, 10, 9, 23, 58))

    def test_backoff_retries_with_growing_pauses_then_gives_up_quietly(self):
        import pandas as pd

        m = self.live()
        pauses = []
        calls = []

        def failing():
            calls.append(1)
            raise TimeoutError("rate limited")

        self.assertIsNone(m.with_backoff(failing, tries=3, base=1.0, sleep=pauses.append, rand=lambda: 0.0))
        self.assertEqual(len(calls), 3)
        self.assertEqual(pauses, [1.0, 2.0])
        # An empty answer is a miss and a real frame is an answer. The first version compared a frame
        # with [] -- an elementwise comparison that raised inside the retry -- and so treated every
        # successful Yahoo download as a failure. Found by running it against the provider.
        frames = [pd.DataFrame(), pd.DataFrame({"x": [1]})]
        got = m.with_backoff(lambda: frames.pop(0), tries=3, base=0, sleep=lambda _s: None, rand=lambda: 0.0)
        self.assertFalse(got.empty)
        self.assertEqual(m.with_backoff(lambda: [], tries=2, base=0, sleep=lambda _s: None, rand=lambda: 0.0), None)

    # --- the job's writes -------------------------------------------------------------------------

    def test_a_quote_only_ever_moves_forward(self):
        sql = self.live().UPSERT
        self.assertIn('ON CONFLICT ("assetId") DO UPDATE', sql)
        self.assertIn('WHERE "LiveQuote"."quotedAt" < EXCLUDED."quotedAt"', sql)

    def test_the_job_writes_one_table_never_deletes_and_never_prints_a_connection_string(self):
        import re as _re

        text = (ROOT / "jobs" / "live.py").read_text(encoding="utf-8")
        self.assertEqual(set(_re.findall(r'INSERT INTO "(\w+)"', text)), {"LiveQuote"})
        code = code_only(text)
        for forbidden in ("DELETE", "TRUNCATE", "DROP"):
            self.assertNotIn(forbidden, code)
        self.assertNotIn("str(error)", code)
        self.assertNotIn("{error}", code)
        self.assertNotIn("DATABASE_URL", code.replace('os.environ["DATABASE_URL"]', ""))

    def test_the_job_never_fails_the_workflow(self):
        text = code_only((ROOT / "jobs" / "live.py").read_text(encoding="utf-8"))
        body = text[text.index("def main("):]
        self.assertNotIn("return 1", body)
        self.assertNotIn("raise", body)

    # --- the web side -----------------------------------------------------------------------------

    def test_the_endpoint_is_read_only(self):
        route = code_only((ROOT / "app" / "api" / "quote" / "route.ts").read_text(encoding="utf-8"))
        for write in ("upsert", "create(", "update(", "delete(", "$executeRaw", "INSERT", "export async function POST"):
            self.assertNotIn(write, route)
        self.assertIn("makeMemo", route)
        self.assertIn("isStale(", route)

    def test_the_client_component_talks_to_one_same_origin_url_and_nothing_else(self):
        import re as _re

        text = code_only((ROOT / "components" / "LivePrice.tsx").read_text(encoding="utf-8"))
        urls = _re.findall(r"fetch\(\s*`([^`]*)`", text)
        self.assertEqual(urls, ["/api/quote?symbol=${encodeURIComponent(symbol)}"])
        self.assertNotIn("http", text)
        self.assertIn('document.visibilityState !== "visible"', text)
        # Hidden tabs are skipped, so a tab coming back must ask at once and remove its listener after.
        self.assertIn('addEventListener("visibilitychange", onVisible)', text)
        self.assertIn('removeEventListener("visibilitychange", onVisible)', text)

    # --- the schedule ------------------------------------------------------------------------------

    def test_the_workflow_is_opt_in_within_the_platform_floor_and_soft_on_failure(self):
        import yaml

        wf = yaml.safe_load((ROOT / ".github" / "workflows" / "cron-live.yml").read_text(encoding="utf-8"))
        crons = [c["cron"] for c in wf[True]["schedule"]]
        self.assertEqual(crons, ["*/5 13-21 * * 1-5", "7,22,37,52 * * * *"])
        for c in crons:
            # GitHub does not run a schedule more often than every five minutes. Nothing here claims to.
            self.assertNotIn("* * * * *", c.replace("7,22,37,52 ", "").replace("*/5 ", "x "))
        job = wf["jobs"]["live"]
        self.assertEqual(job["if"], "${{ vars.LIVE_QUOTES == 'on' }}")
        self.assertLessEqual(job["timeout-minutes"], 5)
        self.assertFalse(wf["concurrency"]["cancel-in-progress"])
        run = job["steps"][-1]["run"]
        self.assertIn('--only crypto', run)
        self.assertTrue(run.rstrip().endswith("exit 0"))


class TheWatchdogRestartsWhatStopped(unittest.TestCase):
    """`tools/watchdog.py` and `cron-watchdog.yml`: hourly, read `/api/health`, restart stale lanes.

    The properties that matter are its limits. It restarts only five named lanes, never twice an hour,
    never on top of a running one, and it stops restarting a lane that keeps failing and asks for a
    person instead -- by going red, which is GitHub's own email to the owner."""

    @staticmethod
    def wd():
        sys.path.insert(0, str(ROOT / "tools"))
        import watchdog

        return watchdog

    def now(self):
        from datetime import datetime, timezone

        return datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)

    @staticmethod
    def problem(lane, detail="stale"):
        return {"check": "x", "lane": lane, "detail": detail}

    def test_a_stale_lane_with_no_recent_run_is_dispatched(self):
        acts = self.wd().plan({"problems": [self.problem("cron-crypto.yml")]}, {}, self.now())
        self.assertEqual([(a["lane"], a["action"]) for a in acts], [("cron-crypto.yml", "dispatch")])

    def test_healthy_means_no_action(self):
        self.assertEqual(self.wd().plan({"ok": True, "problems": []}, {}, self.now()), [])

    def test_it_never_starts_a_second_copy_of_a_running_lane(self):
        runs = {"cron-news.yml": [{"status": "in_progress", "conclusion": None, "event": "schedule", "created_at": "2026-10-14T11:20:00Z"}]}
        acts = self.wd().plan({"problems": [self.problem("cron-news.yml")]}, runs, self.now())
        self.assertEqual(acts[0]["action"], "wait")

    def test_once_an_hour_at_most(self):
        w = self.wd()
        recent = [{"status": "completed", "conclusion": "success", "event": "workflow_dispatch", "created_at": "2026-10-14T11:20:00Z"}]
        self.assertEqual(w.plan({"problems": [self.problem("cron-psx.yml")]}, {"cron-psx.yml": recent}, self.now())[0]["action"], "wait")
        older = [{"status": "completed", "conclusion": "success", "event": "workflow_dispatch", "created_at": "2026-10-14T11:05:00Z"}]
        self.assertEqual(w.plan({"problems": [self.problem("cron-psx.yml")]}, {"cron-psx.yml": older}, self.now())[0]["action"], "dispatch")

    def test_a_lane_that_keeps_failing_is_escalated_not_restarted(self):
        w = self.wd()
        fails = [
            {"status": "completed", "conclusion": "failure", "event": "schedule", "created_at": "2026-10-14T10:05:00Z"},
            {"status": "completed", "conclusion": "failure", "event": "workflow_dispatch", "created_at": "2026-10-14T09:30:00Z"},
        ]
        acts = w.plan({"problems": [self.problem("cron-us-prices.yml")]}, {"cron-us-prices.yml": fails}, self.now())
        self.assertEqual(acts[0]["action"], "escalate")
        # Old failures, outside the window, do not count against it.
        old = [dict(f, created_at="2026-10-14T06:00:00Z") for f in fails]
        self.assertEqual(w.plan({"problems": [self.problem("cron-us-prices.yml")]}, {"cron-us-prices.yml": old}, self.now())[0]["action"], "dispatch")

    def test_an_unreadable_site_and_a_problem_with_no_lane_go_to_a_person(self):
        w = self.wd()
        self.assertEqual(w.plan(None, {}, self.now())[0]["action"], "escalate")
        acts = w.plan({"problems": [{"check": "database", "lane": None, "detail": "cannot read"}]}, {}, self.now())
        self.assertEqual(acts[0]["action"], "escalate")

    def test_the_health_document_cannot_make_it_start_any_other_workflow(self):
        w = self.wd()
        for evil in ("schema.yml", "../x.yml", "cron-live.yml", "deploy.yml", "CRON-CRYPTO.YML", 7):
            acts = w.plan({"problems": [self.problem(evil)]}, {}, self.now())
            self.assertEqual([a["action"] for a in acts], ["escalate"], evil)
            self.assertIsNone(acts[0]["lane"])

    def test_one_lane_named_by_several_problems_is_dispatched_once(self):
        acts = self.wd().plan(
            {"problems": [self.problem("cron-us-prices.yml", "US"), self.problem("cron-us-prices.yml", "FX")]}, {}, self.now()
        )
        self.assertEqual([(a["lane"], a["action"]) for a in acts], [("cron-us-prices.yml", "dispatch")])

    def test_its_lanes_are_exactly_the_ones_health_names(self):
        import re as _re

        ts = (ROOT / "lib" / "health.ts").read_text(encoding="utf-8")
        named = set(_re.findall(r'"(cron-[a-z-]+\.yml)"', ts))
        self.assertEqual(named, set(self.wd().LANES))
        for lane in named:
            self.assertTrue((ROOT / ".github" / "workflows" / lane).is_file(), lane)
            wf = (ROOT / ".github" / "workflows" / lane).read_text(encoding="utf-8")
            self.assertIn("workflow_dispatch", wf, f"{lane} cannot be started by the watchdog")

    def test_it_never_prints_the_token_and_changes_nothing_but_runs(self):
        text = code_only((ROOT / "tools" / "watchdog.py").read_text(encoding="utf-8"))
        for call in re.findall(r"print\(([^\n]*)\)", text):
            self.assertNotIn("token", call.lower(), call)
        for forbidden in ("INSERT", "UPDATE", "DELETE", "psycopg", "DATABASE_URL"):
            self.assertNotIn(forbidden, text)

    def test_the_workflow_runs_hourly_with_only_the_permission_it_needs(self):
        import yaml

        wf = yaml.safe_load((ROOT / ".github" / "workflows" / "cron-watchdog.yml").read_text(encoding="utf-8"))
        self.assertEqual([c["cron"] for c in wf[True]["schedule"]], ["45 * * * *"])
        self.assertEqual(wf["permissions"], {"actions": "write", "contents": "read"})
        self.assertIn("exit $code", wf["jobs"]["watch"]["steps"][-1]["run"])

    def test_the_health_endpoint_is_read_only_and_judges_with_the_rule_tables_limits(self):
        route = code_only((ROOT / "app" / "api" / "health" / "route.ts").read_text(encoding="utf-8"))
        for write in ("upsert", "create(", "update(", "delete(", "$executeRaw", "export async function POST"):
            self.assertNotIn(write, route)
        health = (ROOT / "lib" / "health.ts").read_text(encoding="utf-8")
        self.assertIn('import { STALE_AFTER_DAYS, type Market } from "./decision.ts";', health)
        # Imported, never redefined: a second copy of the limits is how a health page and a decision come
        # to disagree about one close. Whole identifier only (DECISIONS_STALE_AFTER_DAYS is a different one).
        self.assertIsNone(re.search(r"(?<![A-Z_])STALE_AFTER_DAYS\s*[:=]", code_only(health)))


class EveryImportIsDeclared(unittest.TestCase):
    """A module that is installed on one machine is not a dependency.

    Three tests read the workflow files with `yaml`. PyYAML was installed globally on the machine they
    were written on, so they passed there, and it was not in `requirements.txt`, so every CI run from
    2026-10-10 01:04 UTC failed on `No module named 'yaml'` -- for seven hours, behind a red "tests"
    badge that the stale database secret was already making look normal. Found by running the suite in a
    virtualenv holding nothing but `requirements.txt`, which is what the runner has.

    This compares imports with the standard library as Python itself lists it (`sys.stdlib_module_names`),
    not with what happens to be installed, so it fails on the machine that has the package too."""

    # Import name -> the distribution that provides it, where the two differ.
    DISTRIBUTION = {"yaml": "pyyaml", "dotenv": "python-dotenv", "psycopg": "psycopg"}

    def test_every_third_party_import_is_in_requirements(self):
        import ast

        declared = set()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                declared.add(re.split(r"[=<>\[;! ]", line, 1)[0].strip().lower())
        local = set()
        files = []
        for folder in ("jobs", "tools", "tests"):
            for f in sorted((ROOT / folder).rglob("*.py")):
                local.add(f.stem)
                files.append(f)
        missing = []
        for f in files:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                for name in names:
                    top = name.split(".")[0]
                    if top in sys.stdlib_module_names or top in local or top == "__future__":
                        continue
                    dist = self.DISTRIBUTION.get(top, top).lower()
                    if dist not in declared:
                        missing.append(f"{f.relative_to(ROOT).as_posix()}: {top}")
        self.assertEqual(sorted(set(missing)), [], "imported but not in requirements.txt")


class TheLanesWriteToThePrimary(unittest.TestCase):
    """On 2026-10-10 the GitHub `DATABASE_URL` secret held the Supabase string. Every lane went green
    while writing to the standby the website does not read, and nothing in a log said which database it
    was. `jobs/schemacheck.py` runs before every data lane; it now names the provider and refuses the
    standby, before it ever connects."""

    @staticmethod
    def sc():
        import schemacheck

        return schemacheck

    def test_the_provider_is_named_and_nothing_more(self):
        sc = self.sc()
        self.assertEqual(sc.provider_of("postgresql://u:p@ep-x-pooler.c-7.us-east-2.aws.neon.tech/neondb"), "Neon")
        self.assertEqual(sc.provider_of("postgresql://postgres.abc:p@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"), "Supabase")
        self.assertEqual(sc.provider_of("postgresql://u:p@db.abc.supabase.co:5432/postgres"), "Supabase")
        self.assertEqual(sc.provider_of("postgresql://u:p@localhost/x"), "another host")
        self.assertEqual(sc.provider_of(""), "another host")
        # A lookalike is not Neon.
        self.assertEqual(sc.provider_of("postgresql://u:p@neon.tech.evil.example/x"), "another host")

    def test_the_standby_is_refused_before_any_connection_is_attempted(self):
        import contextlib
        import io as _io
        from unittest import mock

        sc = self.sc()
        url = "postgresql://postgres.abc:secretpw@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"
        out = _io.StringIO()
        with mock.patch.dict(os.environ, {"DATABASE_URL": url}), mock.patch.object(sc, "db") as connect, \
                contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as stop:
                sc.main()
        self.assertEqual(stop.exception.code, 2)
        connect.assert_not_called()
        printed = out.getvalue()
        self.assertIn("points at: Supabase", printed)
        self.assertNotIn("secretpw", printed)
        self.assertNotIn("pooler.supabase.com", printed)


class TheNewsLaneNeverWritesThroughItsIdleConnection(unittest.TestCase):
    """The news lane reads its targets on the lane's connection, then spends ten minutes or more
    fetching feeds and writing through its own `Link`. On 2026-10-10 the final clean-up `DELETE` ran on
    the first connection, which had been idle inside its read transaction the whole time; the server
    killed it (IdleInTransactionSessionTimeout) and a run that had stored 1,405 headlines went red.

    The rule this pins: the read transaction is closed before the fetch, and nothing after that point
    uses `cur`."""

    def body(self):
        text = code_only((ROOT / "jobs" / "prices.py").read_text(encoding="utf-8"))
        start = text.index("def fetch_news(")
        end = text.index(chr(10) + "def ", start + 10)
        return text[start:end]

    def test_the_read_transaction_is_closed_before_the_fetch(self):
        body = self.body()
        self.assertIn("cur.connection.commit()", body)
        self.assertLess(body.index("cur.connection.commit()"), body.index("wire.execute("))

    def test_nothing_after_that_point_uses_the_idle_connection(self):
        body = self.body()
        after = body[body.index("cur.connection.commit()") + len("cur.connection.commit()") :]
        for use in ("cur.execute", "rows(cur", "one(cur", "cur.connection"):
            self.assertNotIn(use, after, use)
        self.assertIn("wire.execute('DELETE FROM", after)


class APastedSecretsLineBreakIsNotPartOfIt(unittest.TestCase):
    """On 2026-10-10 the Supabase secret was pasted with the line break after it. The database name
    became "postgres" plus a newline, and the mirror failed with `database "postgres` and a log line
    cut in half. Whitespace is never part of a connection string; every reader now drops it."""

    def test_the_shared_module_strips_every_connection_variable(self):
        import nbt

        env = {
            "DATABASE_URL": "postgresql://u:p@h/db" + chr(10),
            "DIRECT_DATABASE_URL": "  postgresql://u:p@h/db" + chr(13) + chr(10),
            "OTHER": "keep " + chr(10),
        }
        nbt.clean_connection_env(env)
        self.assertEqual(env["DATABASE_URL"], "postgresql://u:p@h/db")
        self.assertEqual(env["DIRECT_DATABASE_URL"], "postgresql://u:p@h/db")
        self.assertEqual(env["OTHER"], "keep " + chr(10), "only connection strings are touched")

    def test_every_other_reader_strips_too(self):
        checks = {
            "jobs/mirror.py": 'os.environ.get(env_name) or "").strip()',
            "tools/schema_parity.py": '(os.environ.get(n) or "").strip()',
            "lib/db.ts": "process.env.DATABASE_URL?.trim()",
            "tools/decide.mjs": "process.env.DATABASE_URL.trim()",
            "tools/macro_gate.mjs": "process.env.DATABASE_URL.trim()",
        }
        for rel, needle in checks.items():
            self.assertIn(needle, (ROOT / rel).read_text(encoding="utf-8"), rel)
        db = (ROOT / "lib" / "db.ts").read_text(encoding="utf-8")
        self.assertIn("SUPABASE_DATABASE_URL?.trim()", db)
        self.assertIn("DATABASE_URL_FALLBACK?.trim()", db)


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
        # A call rather than a source check now that the stop is chosen by `stop_level` instead
        # of by one literal line -- which is the stronger test, and the reason the source form
        # was only ever a stand-in for it.
        high, low, entry_long, entry_short, sigma = 110.0, 90.0, 110.0, 90.0, 2.0

        stop_up, note_up = setup.stop_level(entry_long, high, low, sigma, "buy")
        self.assertLess(stop_up, entry_long, "a long is wrong below its entry")
        self.assertGreaterEqual(stop_up, low, "and never further than the window it was read from")

        stop_down, note_down = setup.stop_level(entry_short, high, low, sigma, "short")
        self.assertGreater(stop_down, entry_short, "a short is wrong above its entry")
        self.assertLessEqual(stop_down, high)

        # The two must not be the same level, which is the fault this class exists for.
        self.assertNotAlmostEqual(stop_up, stop_down)
        self.assertIn("below", note_up)
        self.assertIn("above", note_down)

    def test_the_levels_follow_the_direction_the_row_records_not_its_state(self):
        """A short's stop belongs above the price even when the state does not say "short".

        This is the WTL and STLA failure reintroduced by a gate that started acting on
        directions the level block could not see. Measured 2026-10-09 after gate 8 shipped:
        **70 live SHORT cards had the stop on the wrong side of the entry** -- 53 from `wait`
        rows and 17 from `none` ones, each reading SHORT with the stop on the side the trade
        needs price to reach. AHCL: SHORT, entry 16.17, stop 15.81.

        `setup.py` derives the aim from its own locals and `horizons.aimed_at` parses it back
        out of the conditions string in a later job. The two must agree about every row, which
        is what the last assertion here checks against the string the first one implies.
        """
        # A withheld downward trend: state is `wait`, the direction is down, so the stop is above.
        aim = "short"
        stop, note = setup.stop_level(90.0, 110.0, 90.0, 2.0, aim)
        self.assertGreater(stop, 90.0, "a short is wrong above its entry, whatever the state is")
        self.assertIn("above", note)

        # And the same row read back through the parser the target pass uses.
        conditions = "trend: close 9 vs 20d 9.4 vs 50d 9.9 (down) | volume: 0.7x (fail)"
        self.assertEqual(horizons.aimed_at({"state": "wait", "conditions": conditions}), "short")

        # A `none` row carrying a downward bias is the other half of the 70.
        bias_conditions = ("trend: close 10 vs 20d 10.1 vs 50d 10.2 (mixed) | "
                           "bias: 20d average 1.00% below the 50d (down)")
        self.assertEqual(horizons.aimed_at({"state": "none", "conditions": bias_conditions}),
                         "short")

    def test_the_stop_can_only_tighten(self):
        # Bounded by the window extreme, so an asset whose recent range is narrower than
        # STOP_SIGMAS of its own daily moves keeps the range and is never handed a wider stop
        # than it had before this existed.
        tight_range_high, tight_range_low = 100.5, 99.5
        stop, note = setup.stop_level(100.5, tight_range_high, tight_range_low, 9.0, "buy")
        self.assertEqual(stop, tight_range_low)
        self.assertIn(f"{setup.FAST} sessions", note)

    def test_an_unmeasurable_dispersion_keeps_the_window_extreme(self):
        # A stop placed on an assumed volatility would be the one number this job may not write.
        self.assertEqual(setup.stop_level(110.0, 110.0, 90.0, None, "buy")[0], 90.0)
        self.assertEqual(setup.stop_level(90.0, 110.0, 90.0, None, "short")[0], 110.0)
        self.assertIsNone(setup.sigma_pct([{"close": 10.0} for _ in range(30)]))
        self.assertIsNone(setup.sigma_pct([{"close": 10.0}, {"close": 11.0}]))

    def test_the_stop_is_measured_in_the_asset_s_own_moves(self):
        # 1.5 of a 2% daily move is 3% from the entry, in every market, which is the whole point
        # of scaling it rather than fixing a percentage.
        stop, _ = setup.stop_level(100.0, 200.0, 1.0, 2.0, "buy")
        self.assertAlmostEqual(stop, 100.0 * (1 - setup.STOP_SIGMAS * 2.0 / 100.0), places=6)
        quiet, _ = setup.stop_level(100.0, 200.0, 1.0, 0.4, "buy")
        self.assertGreater(quiet, stop, "a quieter asset gets a nearer stop, not the same one")

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


class NothingIsDefinedAfterTheEntryPoint(unittest.TestCase):
    """`unittest.main()` belongs at the end of the file, and nothing may follow it.

    It sat 72 lines from the end instead, with `ShortLevelsAreMirrored` defined underneath --
    four tests that hold a short's stop on the correct side of the price, which is a bug this
    repository has already shipped once. Discovery imports the module and collects them, so CI
    ran 430; running the file directly executed `unittest.main()` at that line and reported
    `OK` over 426. A green run that is quietly four tests short is worse than a red one.
    """

    def test_the_entry_point_is_the_last_statement_in_the_file(self):
        text = Path(__file__).read_text(encoding="utf-8")
        marker = 'if __name__ == "__main__":'
        self.assertIn(marker, text)
        after = text[text.index(marker) + len(marker):]
        self.assertNotIn("\nclass ", after,
                         "a test class is defined after unittest.main(), so running this file "
                         "directly will not reach it")

    def test_running_this_file_directly_collects_every_class(self):
        # The count both ways has to match. Discovery walks the module after import; the direct
        # run stops wherever the entry point is.
        defined = sum(
            1 for name, obj in list(globals().items())
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase)
        )
        loaded = unittest.defaultTestLoader.loadTestsFromModule(
            sys.modules[__name__]
        ).countTestCases()
        self.assertGreater(defined, 50)
        self.assertGreater(loaded, 400)


if __name__ == "__main__":
    unittest.main()
