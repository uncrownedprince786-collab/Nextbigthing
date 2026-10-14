"""Tests for the data-foundation tools, and acceptance gates for the datasets they produce.

The first half checks the walk-forward machinery on synthetic data where the right answer is known.
The second half is different in kind: it reads the committed datasets and fails if a stated
threshold is not met, so a claim like "25 macro series with 15 years of history" is something the
test suite enforces and not something a report asserts. A gate whose data file is absent is
skipped, never passed.
"""

from __future__ import annotations

import csv
import json
import random
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "jobs"))

import walkforward as wf  # noqa: E402

DATA = ROOT / "data" / "foundation"


def sessions(n: int, start: date = date(2020, 1, 1)) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def synthetic(n_dates=700, assets=6, edge=1.0, seed=3) -> list[dict]:
    """A feature `signal` in {-1,+1} that really does move the 20-session return by `edge` percent."""
    rng = random.Random(seed)
    recs = []
    for d in sessions(n_dates):
        for a in range(assets):
            sig = rng.choice([-1, 1])
            recs.append({"asOf": d, "symbol": f"A{a}", "assetType": "stock", "market": "US",
                         "candidate": {"signal": sig, "setupState": "buy" if sig > 0 else "short"},
                         "outcome": {"fwd20": edge * sig + rng.gauss(0, 4.0), "fwd5": rng.gauss(0, 2)}})
    return recs


class Folds(unittest.TestCase):
    def test_training_never_reaches_the_test_period(self):
        ds = sessions(900)
        for horizon, embargo in ((5, 0), (20, 5), (60, 10)):
            for f in wf.make_folds(ds, train_min=250, test_len=40, horizon=horizon, embargo=embargo):
                i = {d: k for k, d in enumerate(ds)}
                self.assertLess(i[f.train[-1]] + horizon + embargo, i[f.test[0]])
                self.assertFalse(set(f.train) & set(f.test))

    def test_tampering_is_caught(self):
        ds = sessions(600)
        f = wf.make_folds(ds, train_min=250, test_len=40, horizon=20)[0]
        bad = wf.Fold(train=f.train + (f.test[0],), test=f.test)
        with self.assertRaises(wf.LeakageError):
            wf.assert_no_overlap(bad, ds, 20, 5)
        close = wf.Fold(train=tuple(ds[:249]), test=tuple(ds[250:290]))
        with self.assertRaises(wf.LeakageError):
            wf.assert_no_overlap(close, ds, 20, 5)

    def test_rolling_window_is_bounded(self):
        for f in wf.make_folds(sessions(900), train_min=250, test_len=40, horizon=20, rolling=100):
            self.assertLessEqual(len(f.train), 100)

    def test_a_future_looking_feature_is_refused(self):
        recs = synthetic(10)
        recs[0]["candidate"]["fwd5_zscore"] = 1.0
        with self.assertRaises(wf.LeakageError):
            wf.assert_features_are_past_only(recs)
        recs = synthetic(10)
        recs[0]["label20"] = "UP"
        with self.assertRaises(wf.LeakageError):
            wf.assert_features_are_past_only(recs)

    def test_the_check_is_never_skipped_unless_a_caller_says_so(self):
        """Opting out is explicit. An earlier version cached by list identity, and CPython reuses
        the id of a collected list, so a poisoned dataset could inherit a clean verdict from one it
        never had anything to do with."""
        recs = synthetic(10)
        recs[0]["label20"] = "UP"
        for _ in range(3):
            with self.assertRaises(wf.LeakageError):
                wf.assert_features_are_past_only(recs)
        big = synthetic(400)
        big[0]["label20"] = "UP"
        with self.assertRaises(wf.LeakageError):
            wf.evaluate(big, lambda r: 1, name="poisoned")
        got = wf.evaluate(big, lambda r: 1, name="opted-out", check_features=False)
        self.assertIn("trades", got)


class Costs(unittest.TestCase):
    rec = {"assetType": "stock", "market": "US", "outcome": {"fwd20": 3.0}}

    def test_costs_reduce_a_trade_and_grow_with_the_scenario(self):
        nets = [wf.trade_net_pct(self.rec, 1, 20, s) for s in wf.SCENARIOS]
        self.assertTrue(all(n < 3.0 for n in nets))
        self.assertGreater(nets[0], nets[1])
        self.assertGreater(nets[1], nets[2])

    def test_a_short_pays_borrow_and_a_long_does_not(self):
        # the same 3 percent gross gain, taken once as a long and once as a short
        long_net = wf.trade_net_pct({**self.rec, "outcome": {"fwd20": 3.0}}, 1, 20, "base")
        short_net = wf.trade_net_pct({**self.rec, "outcome": {"fwd20": -3.0}}, -1, 20, "base")
        self.assertLess(short_net, long_net)

    def test_a_short_in_a_market_that_forbids_it_is_not_priced(self):
        r = {"assetType": "stock", "market": "PSX", "outcome": {"fwd20": -3.0}}
        self.assertIsNone(wf.trade_net_pct(r, -1, 20, "base"))
        self.assertIsNotNone(wf.trade_net_pct(r, 1, 20, "base"))

    def test_an_immature_outcome_is_not_a_zero(self):
        self.assertIsNone(wf.trade_net_pct({"assetType": "stock", "outcome": {}}, 1, 20, "base"))


class Statistics(unittest.TestCase):
    def test_inverse_normal(self):
        self.assertAlmostEqual(wf._phi_inv(0.975), 1.959964, places=4)
        self.assertAlmostEqual(wf._phi_inv(0.5), 0.0, places=6)
        self.assertAlmostEqual(wf._phi(wf._phi_inv(0.9)), 0.9, places=6)

    def test_more_trials_lower_the_deflated_sharpe(self):
        p = [wf.deflated_sharpe(0.15, 400, 0.0, 3.0, n, 0.002) for n in (1, 10, 100, 1000)]
        self.assertTrue(all(a > b for a, b in zip(p, p[1:])), p)

    def test_a_large_sharpe_survives_and_a_tiny_one_does_not(self):
        self.assertGreater(wf.deflated_sharpe(0.5, 400, 0.0, 3.0, 20, 0.002), 0.95)
        self.assertLess(wf.deflated_sharpe(0.02, 400, 0.0, 3.0, 200, 0.002), 0.5)

    def test_one_trial_reduces_to_the_ordinary_significance_test(self):
        """With a single trial there is nothing to deflate, so the expected maximum Sharpe is zero
        and the result must collapse to Phi(SR * sqrt(T-1)) for a normal return distribution. If
        this drifts, every verdict the evaluation prints is built on a different formula than the
        one it cites."""
        import math
        for sr, n in ((0.05, 400), (0.1, 250), (0.02, 1000)):
            want = wf._phi(sr * math.sqrt(n - 1) / math.sqrt(1 + 0.5 * sr * sr))
            got = wf.deflated_sharpe(sr, n, 0.0, 3.0, 1)
            self.assertAlmostEqual(got, want, places=9, msg=(sr, n))

    def test_the_expected_maximum_grows_with_the_number_of_trials(self):
        """The deflation term is the expected best-of-N Sharpe under the null; it must rise with N
        and scale with the dispersion of the trials."""
        import math
        gamma = 0.5772156649015329
        for n in (2, 10, 500):
            var = 0.004
            want = math.sqrt(var) * ((1 - gamma) * wf._phi_inv(1 - 1 / n)
                                     + gamma * wf._phi_inv(1 - 1 / (n * math.e)))
            # recover sr0 from the function: find the sr at which DSR is exactly one half
            lo, hi = 0.0, 1.0
            for _ in range(60):
                mid = (lo + hi) / 2
                if wf.deflated_sharpe(mid, 10_000, 0.0, 3.0, n, var) < 0.5:
                    lo = mid
                else:
                    hi = mid
            self.assertAlmostEqual((lo + hi) / 2, want, places=4, msg=n)

    def test_trial_log_persists_and_counts(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "trials.jsonl"
            log = wf.TrialLog(p)
            for i in range(4):
                log.add(f"r{i}", {"h": 20}, 0.1 * i, 100)
            self.assertEqual(wf.TrialLog(p).count, 4)
            self.assertIsNotNone(wf.TrialLog(p).sharpe_variance())


class Evaluation(unittest.TestCase):
    def test_a_real_edge_is_found_net_of_costs_and_controls_are_not(self):
        recs = synthetic(edge=1.5)
        log = wf.TrialLog()
        rule = lambda r: r["candidate"]["signal"]  # noqa: E731
        got = wf.evaluate(recs, rule, name="edge", log=log)
        self.assertGreater(got["meanNetPct"]["base"], 0.5)
        self.assertTrue(got["survivesBaseCost"])
        rnd = wf.evaluate(recs, wf.random_sign(5), name="random", log=log)
        self.assertLess(abs(rnd["meanGrossPct"]), 0.5)
        self.assertFalse(rnd["survivesBaseCost"])
        self.assertEqual(log.count, 2)
        self.assertLess(rnd["deflatedSharpeProbability"], 0.95)

    def test_no_edge_means_costs_make_it_lose(self):
        recs = synthetic(edge=0.0)
        got = wf.evaluate(recs, lambda r: r["candidate"]["signal"], name="noise")
        self.assertLess(got["meanNetPct"]["base"], 0.1)
        self.assertLess(got["meanNetPct"]["high"], got["meanNetPct"]["low"])

    def test_a_fitted_rule_only_ever_sees_training_data(self):
        recs = synthetic(edge=1.0)
        seen = []

        def fit(train):
            seen.append(max(r["asOf"] for r in train))
            return lambda r: r["candidate"]["signal"]

        wf.evaluate(recs, lambda r: 0, name="fitted", fit=fit)
        folds = wf.make_folds(sorted({r["asOf"] for r in recs}), train_min=250, test_len=60, horizon=20, embargo=5)
        self.assertEqual(len(seen), len(folds))
        for last, f in zip(seen, folds):
            self.assertLess(last, f.test[0])

    def test_effective_sample_is_smaller_than_the_row_count(self):
        got = wf.evaluate(synthetic(), lambda r: r["candidate"]["signal"], name="n")
        self.assertLessEqual(got["effectiveIndependentTrades"], got["trades"] / 20 + 1)

    def test_the_fast_bootstrap_matches_the_definition_it_replaces(self):
        """Resampling each date's sum and count must give the pooled mean of resampling its trades.
        Identical to floating-point accumulation order, which is the only thing that may differ."""
        import random as _r

        def naive(by_date, reps=400, seed=7):
            keys = sorted(by_date)
            rng = _r.Random(seed)
            means = []
            for _ in range(reps):
                pick = [by_date[keys[rng.randrange(len(keys))]] for _ in keys]
                flat = [x for g in pick for x in g]
                if flat:
                    means.append(sum(flat) / len(flat))
            means.sort()
            return means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1]

        rng = _r.Random(11)
        by = {f"d{i}": [rng.gauss(0.4, 2.5) for _ in range(rng.randint(1, 15))] for i in range(200)}
        a = naive(by)
        b = wf.block_bootstrap_mean(by, reps=400)
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=12)

    def test_the_interval_is_over_dates_not_rows(self):
        by = {f"d{i}": [1.0, 1.0, 1.0] for i in range(20)}
        lo, hi = wf.block_bootstrap_mean(by)
        self.assertEqual((lo, hi), (1.0, 1.0))


class Determinism(unittest.TestCase):
    """The leakage re-check picks its sample and its reference copy deterministically."""

    def setUp(self):
        import determinism_check as dc
        self.dc = dc

    def test_sample_covers_every_year_and_both_ends_and_is_reproducible(self):
        days = sessions(1900, date(2019, 1, 2))
        a = self.dc.stratified(days, 40, 11)
        self.assertEqual(a, self.dc.stratified(days, 40, 11))
        self.assertIn(days[0], a)
        self.assertIn(days[-1], a)
        self.assertEqual({d[:4] for d in a}, {d[:4] for d in days})
        self.assertNotEqual(a, self.dc.stratified(days, 40, 12))

    def test_only_trusted_valid_outputs_are_a_reference(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for run, trusted in (("100", True), ("200", True), ("300", False)):
                d = root / f"nbt-worker-output-{run}"
                d.mkdir()
                (d / "setups-2020-01-02.jsonl").write_text('{"a":1}', encoding="utf-8")
                (d / "decisions-2020-01-02.json").write_text(
                    json.dumps({"asOf": "2020-01-02", "setups": 1, "byAction": {"WAIT": 1}}), encoding="utf-8")
            runs = {"100": {"trusted": True}, "200": {"trusted": True}, "300": {"trusted": False}}
            got = self.dc.canonical(root, runs)
            self.assertEqual(got["2020-01-02"]["run"], "200")  # newest trusted, not the untrusted 300
            (root / "nbt-worker-output-200" / "decisions-2020-01-02.json").write_text("junk", encoding="utf-8")
            self.assertEqual(self.dc.canonical(root, runs)["2020-01-02"]["run"], "100")


class PointInTime(unittest.TestCase):
    """The point-in-time builder cannot see the future and matches the live analog loop."""

    @staticmethod
    def bars(n, seed, volume=True, start=date(2020, 1, 1)):
        rng, price, out = random.Random(seed), 100.0, []
        for ds in sessions(n, start):
            price *= 1 + rng.gauss(0.0004, 0.015)
            out.append({"date": date.fromisoformat(ds), "close": price,
                        "volume": rng.uniform(1e5, 5e5) if volume else None,
                        "high": price * 1.01, "low": price * 0.99})
        return out

    def universe(self, volume=True):
        assets = [{"id": f"a{i}", "symbol": f"S{i}", "industryId": "ind", "assetType": "stock"} for i in range(3)]
        return assets, {a["id"]: self.bars(420, i + 1, volume) for i, a in enumerate(assets)}

    def test_rows_before_a_session_do_not_change_when_every_later_bar_does(self):
        import pit_features as pit
        for volume in (True, False):
            assets, series = self.universe(volume)
            base = {(r["a"], r["d"]): r for r in pit.build(assets, series)}
            cut = 300
            cut_date = series["a0"][cut]["date"]
            rng = random.Random(9)
            bent = {k: [dict(b) for b in v] for k, v in series.items()}
            for k in bent:
                for b in bent[k]:
                    if b["date"] > cut_date:
                        b["close"] *= rng.uniform(0.2, 5.0)
                        b["volume"] = None if not volume else rng.uniform(1, 1e9)
            after = {(r["a"], r["d"]): r for r in pit.build(assets, bent)}
            checked = 0
            for key, row in base.items():
                if date.fromisoformat(key[1]) <= cut_date:
                    self.assertEqual(row, after[key], f"{key} changed when only later bars did (volume={volume})")
                    checked += 1
            self.assertGreater(checked, 500)

    def test_vectorised_analogs_equal_the_live_loop(self):
        import pit_features as pit
        for volume in (True, False):
            bars = self.bars(420, 5, volume)
            ours = pit.AnalogSeries(bars)
            rng = random.Random(2)
            for t in [rng.randrange(60, 420) for _ in range(14)] + [419]:
                for h in (1, 5):
                    a, b = ours.at(t, h), pit.live_oracle(bars, t, h)
                    if b is None:
                        self.assertIsNone(a, (t, h, volume))
                        continue
                    self.assertEqual(a["matches"], b["matches"], (t, h, volume))
                    self.assertEqual(a["grade"], b["grade"], (t, h, volume))
                    if b["matches"]:
                        for k in ("positive", "mean", "median", "min", "max"):
                            self.assertAlmostEqual(a[k], b[k], places=9, msg=(t, h, k, volume))

    def test_a_row_exists_for_every_session_from_the_threshold_and_none_before(self):
        import pit_features as pit
        assets, series = self.universe()
        rows = list(pit.build(assets, series))
        self.assertEqual(len(rows), sum(len(v) - pit.MIN_BARS + 1 for v in series.values()))
        self.assertEqual(len({(r["a"], r["d"]) for r in rows}), len(rows))

    def test_a_window_reports_the_calendar_days_it_really_covers(self):
        """Daily bars give a span of roughly 1.5 days per session. Monthly bars give about 30, and
        nothing else in the row would say so -- which is exactly the PSX case before 2024."""
        import pit_features as pit
        assets, series = self.universe()
        rows = [r for r in pit.build(assets, series) if r["a"] == "S0"]
        self.assertTrue(all("spanDays" in r for r in rows))
        deep = [r for r in rows if r["n"] >= 200][-1]
        per_session = deep["spanDays"] / min(deep["n"], pit.WINDOW)
        self.assertLess(per_session, 2.0, "daily bars should span about 1.5 calendar days each")

        # the same asset with its bars thinned to one a month
        monthly = {a["id"]: v[::21] for a, v in zip(assets, series.values())}
        thin = [r for r in pit.build(assets, monthly) if r["a"] == "S0"]
        if thin:
            worst = thin[-1]
            self.assertGreater(worst["spanDays"] / min(worst["n"], pit.WINDOW), 10.0,
                               "monthly bars must not look like a daily window")

    def test_the_span_counts_back_from_the_window_not_the_whole_series(self):
        import pit_features as pit
        assets, series = self.universe()
        rows = [r for r in pit.build(assets, series) if r["a"] == "S0"]
        for r in rows:
            self.assertLessEqual(r["spanDays"], min(r["n"], pit.WINDOW) * 7,
                                 "a window cannot span more than seven calendar days a session")

    def test_the_analog_never_uses_an_outcome_after_the_session(self):
        import pit_features as pit
        bars = self.bars(300, 4)
        t = 200
        base = pit.AnalogSeries(bars).at(t, 5)
        future = [dict(b) for b in bars]
        for b in future[t + 1:]:
            b["close"] *= 10
        self.assertEqual(base, pit.AnalogSeries(future).at(t, 5))


class Assembly(unittest.TestCase):
    """The assembly joins on (symbol, session) and accounts for every row it cannot join."""

    @staticmethod
    def write_gz(path: Path, rows: list[dict]):
        import gzip
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + chr(10))

    def make(self, root: Path, pit_after=False):
        days = sessions(120)
        full = [{"asOf": d, "assetId": "id1", "symbol": "AAA", "assetType": "stock", "market": "US",
                 "outcome": {"fwd20": 1.0}} for d in days]
        pit = [{"a": "AAA", "t": "stock", "d": (days[i + 1] if pit_after and i == 70 else d), "n": i + 1,
                "f": {"r1": 0.1, "volumeRatio": None}} for i, d in enumerate(days) if i >= 50]
        (root / "full").mkdir()
        (root / "pit").mkdir()
        self.write_gz(root / "full" / "full-history-v2.jsonl.gz", full)
        self.write_gz(root / "pit" / "pit-2020.jsonl.gz", pit)
        return days

    def run_main(self, root: Path):
        import assemble
        sys.argv = ["assemble", "--full", str(root / "full"), "--pit", str(root / "pit"), "--out", str(root / "out")]
        rc = assemble.main()
        return rc, json.loads((root / "out" / "manifest.json").read_text(encoding="utf-8"))

    def test_every_session_is_joined_or_has_a_named_reason(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make(root)
            rc, m = self.run_main(root)
            self.assertEqual(rc, 0)
            self.assertEqual(m["eligibleAssetSessions"], 120)
            self.assertEqual(m["withPointInTimeFeatures"], 70)
            self.assertEqual(m["withoutFeaturesByReason"], {"history shorter than the feature threshold": 50})
            self.assertEqual(m["unexplained"], 0)
            self.assertTrue(m["reproducible"]["match"])

    def test_a_feature_dated_after_its_session_fails_the_run(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make(root, pit_after=True)
            rc, m = self.run_main(root)
            self.assertEqual(rc, 1)
            self.assertTrue(m["duplicates"]["features"] or m["unexplained"], "a misdated feature row must surface as a duplicate or an unexplained session")

    def test_the_setup_join_prefers_the_newest_trusted_run(self):
        """Two runs replayed the same session. Only output from code matching the current replay
        may be used, and of those the newest wins."""
        import assemble
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for run, state in (("100", "buy"), ("200", "short"), ("300", "wait")):
                d = root / f"nbt-worker-output-{run}"
                d.mkdir()
                (d / "setups-2020-03-16.jsonl").write_text(
                    json.dumps({"assetId": "id1", "periodEnd": "2020-03-16", "state": state}),
                    encoding="utf-8")
            runs = {"100": {"trusted": True}, "200": {"trusted": True}, "300": {"trusted": False}}
            got = assemble.setups_for_year(root, runs, 2020)
            self.assertEqual(got[("id1", "2020-03-16")]["state"], "short")   # 200, not the untrusted 300

    def test_a_setup_carried_from_an_earlier_session_is_not_joined(self):
        """A file named for one session can hold a row whose periodEnd is an earlier close, when
        that asset did not trade. Joining it to this session's outcome would date it wrongly."""
        import assemble
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            d = root / "nbt-worker-output-100"
            d.mkdir()
            (d / "setups-2020-03-16.jsonl").write_text(
                json.dumps({"assetId": "fresh", "periodEnd": "2020-03-16", "state": "buy"}) + chr(10)
                + json.dumps({"assetId": "stale", "periodEnd": "2020-03-13", "state": "short"}),
                encoding="utf-8")
            got = assemble.setups_for_year(root, {"100": {"trusted": True}}, 2020)
            self.assertIn(("fresh", "2020-03-16"), got)
            self.assertNotIn(("stale", "2020-03-16"), got)
            self.assertNotIn(("stale", "2020-03-13"), got)

    def test_no_replay_directory_means_no_setups_rather_than_an_error(self):
        import assemble
        self.assertEqual(assemble.setups_for_year(None, {}, 2020), {})

    def test_the_setup_join_is_reconciled_like_the_feature_join(self):
        """A bare coverage ratio is not a reconciliation. Every eligible session without a setup
        must carry a named reason, and setupUnexplained must be zero or the run fails."""
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make(root)
            rc, m = self.run_main(root)
            self.assertEqual(rc, 0)
            self.assertEqual(m["withoutSetup"], m["eligibleAssetSessions"] - m["withReplayedSetup"])
            self.assertEqual(sum(m["withoutSetupByReason"].values()), m["withoutSetup"])
            self.assertEqual(m["setupUnexplained"], 0)

    def test_the_leakage_block_reports_a_scan_not_a_literal(self):
        """futureNamedFields used to be a hardcoded 0, which is not evidence of anything."""
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make(root)
            _, m = self.run_main(root)
            self.assertNotIn("futureNamedFields", m["leakage"])
            self.assertGreater(m["leakage"]["futureNamedFieldScan"]["rowsChecked"], 0)

    def test_an_action_poisons_every_later_session_not_just_a_window(self):
        """The analog pool is the asset's whole history, so a window-sized flag misses sessions
        years after the action whose match pool still contains it."""
        import assemble
        from datetime import date as _d
        stats = __import__("collections").Counter()
        days = sessions(900, _d(2020, 1, 1))
        rows = [{"asOf": d, "assetId": "id1", "symbol": "AAA", "assetType": "stock",
                 "market": "US", "outcome": {"fwd20": 1.0}} for d in days]
        actions = {"AAA": [days[100]]}
        out = list(assemble.assemble_year(2020, rows, None, {}, stats, actions, set()))
        flagged = {r["asOf"] for r in out if r["dataQuality"]["unadjustedActionInWindow"]}
        # Every session from the action onward: its analog pool can contain the fabricated move.
        for d in days[100:]:
            self.assertIn(d, flagged, f"{d} is after the action and was not flagged")
        # Plus sessions shortly BEFORE it, whose 20-session outcome window crosses it. That is the
        # window rule still doing its own job, so the total is larger than the tail alone.
        self.assertGreater(len(flagged), len(days) - 100)
        self.assertNotIn(days[0], flagged, "a session long before the action is not affected")
        self.assertTrue(out[-1]["dataQuality"]["unadjustedActionInWindow"],
                        "a session two years after the action still draws on a poisoned pool")

    def test_missingness_is_reported_per_factor(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make(root)
            _, m = self.run_main(root)
            self.assertEqual(m["missingnessByAssetClass"]["stock"]["volumeRatio"], 1.0)
            self.assertEqual(m["missingnessByAssetClass"]["stock"]["r1"], 0.0)


class PrincipleRules(unittest.TestCase):
    """The evaluated rules are functions of the point-in-time features and nothing else."""

    def setUp(self):
        import evaluate_principles as ep
        self.ep = ep

    @staticmethod
    def rec(**f):
        return {"asOf": "2021-06-01", "symbol": "AAA", "assetType": "stock", "market": "US",
                "pit": {"n": 300, "f": {"r1": None, "r5": None, "r20": None, "returnZ": None,
                                        "volumeRatio": None, "entryTrigger": None,
                                        "triggerDirection": None, "sma20": None, "sma50": None,
                                        "rangePct": None, "drawdownPct": None, "atr14": None,
                                        "peerMedianR20": None, "relStrength": None, "peers": 0} | f,
                        "an": None},
                "candidate": None, "outcome": {"fwd20": 5.0}, "coverage": {"pit": True, "setup": False}}

    def test_no_rule_reads_the_outcome(self):
        """Poison every outcome field; a rule that changes its mind was reading the future."""
        base = self.rec(r1=1.0, r5=-2.0, r20=3.0, returnZ=2.5, volumeRatio=2.4, sma20=10.0,
                        sma50=9.0, rangePct=95.0, drawdownPct=-30.0, atr14=0.1,
                        relStrength=1.5, triggerDirection="up")
        poisoned = {**base, "outcome": {"fwd1": -99, "fwd5": -99, "fwd20": -99, "mfe": -99,
                                        "mae": -99, "label20": "DOWN"}}
        for pid, _, rule in self.ep.RULES:
            self.assertEqual(rule(base), rule(poisoned), pid)

    def test_every_rule_returns_a_side_and_abstains_on_missing_features(self):
        empty = self.rec()
        for pid, _, rule in self.ep.RULES:
            self.assertIn(rule(empty), (-1, 0, 1), pid)
            self.assertEqual(rule(empty), 0, f"{pid} took a side with no features")

    def test_a_macro_rule_sees_only_the_session_it_is_given(self):
        """The macro lookup is keyed by the row's own session date. A rule that found a figure for
        a date it was not given would be reading another session's state."""
        self.ep.MACRO.clear()
        self.ep.MACRO["2021-06-01"] = {"VIXCLS": {"v": 35.0, "age": 1},
                                       "T10Y3M": {"v": -0.5, "age": 1},
                                       "DFF": {"v": 0.08, "age": 1, "chg": 0.25}}
        try:
            here = self.rec()
            self.assertEqual(self.ep.r_macro_feargauge(here), 1)
            self.assertEqual(self.ep.r_macro_curve(here), 0)      # inverted: stand aside
            self.assertEqual(self.ep.r_macro_tightening(here), -1)  # rate rose
            elsewhere = {**here, "asOf": "2021-06-02"}
            for rule in (self.ep.r_macro_feargauge, self.ep.r_macro_curve, self.ep.r_macro_tightening):
                self.assertEqual(rule(elsewhere), 0, "a rule found macro state for another session")
        finally:
            self.ep.MACRO.clear()

    def test_the_calendar_rules_need_no_features_at_all(self):
        self.assertEqual(self.ep.r_cal_halloween({"asOf": "2021-12-15"}), 1)
        self.assertEqual(self.ep.r_cal_halloween({"asOf": "2021-07-15"}), 0)
        self.assertEqual(self.ep.r_cal_january({"asOf": "2022-01-04"}), 1)
        self.assertEqual(self.ep.r_cal_january({"asOf": "2022-02-04"}), 0)

    def test_each_rule_names_a_principle_in_the_corpus(self):
        path = DATA / "principles" / "principles.json"
        if not path.exists():
            self.skipTest("principles corpus not present")
        known = {r["id"] for r in json.loads(path.read_text(encoding="utf-8"))["principles"]}
        for pid, _, _ in self.ep.RULES:
            if not pid.startswith("NBT-"):
                self.assertIn(pid, known, f"{pid} is not a principle in the corpus")

    def test_a_quarantined_row_never_reaches_a_rule(self):
        """Flagging is not protection. A row whose window crosses an unadjusted corporate action,
        or whose bars are not daily, must be excluded from the evaluation rather than entering a
        rule's statistics as an ordinary price movement."""
        src = (ROOT / "tools" / "foundation" / "evaluate_principles.py").read_text(encoding="utf-8")
        self.assertIn("unadjustedActionInWindow", src)
        self.assertIn("windowIsNotDaily", src)
        self.assertIn("rows = [r for r in rows if usable(r)]", src)
        # and the slimmed row must still carry the flags, or the filter has nothing to read
        slim = self.ep.slim({"asOf": "2021-06-01", "symbol": "A", "assetType": "stock",
                             "market": "US", "outcome": {"fwd20": 1.0}, "pit": None,
                             "candidate": None,
                             "dataQuality": {"unadjustedActionInWindow": True,
                                             "windowIsNotDaily": False}}, 20)
        self.assertTrue(slim["dataQuality"]["unadjustedActionInWindow"])
        self.assertFalse(slim["dataQuality"]["windowIsNotDaily"])

    def test_a_row_with_no_quality_block_is_treated_as_clean(self):
        slim = self.ep.slim({"asOf": "2021-06-01", "symbol": "A", "assetType": "stock",
                             "market": "US", "outcome": {"fwd20": 1.0}, "pit": None,
                             "candidate": None}, 20)
        self.assertFalse(slim["dataQuality"]["unadjustedActionInWindow"])
        self.assertFalse(slim["dataQuality"]["windowIsNotDaily"])

    def test_the_verdict_requires_beating_both_controls(self):
        controls = {"buy-and-hold": {"meanNetPct": {"base": 1.0}},
                    "coin-flip": {"meanNetPct": {"base": -0.2}}}
        strong = {"trades": 500, "meanNetPct": {"base": 2.0}, "meanNetBaseCI95": [0.5, 3.0],
                  "deflatedSharpeProbability": 0.99}
        self.assertEqual(self.ep.verdict(strong, controls)["verdict"], "PASS")
        for broken in ({"meanNetPct": {"base": 0.5}},                      # loses to buy-and-hold
                       {"meanNetBaseCI95": [-0.1, 3.0]},                   # interval includes zero
                       {"deflatedSharpeProbability": 0.5},                 # not past the trials
                       {"meanNetPct": {"base": -1.0}}):                    # loses money
            self.assertEqual(self.ep.verdict({**strong, **broken}, controls)["verdict"], "FAIL", broken)
        self.assertEqual(self.ep.verdict({**strong, "trades": 10}, controls)["verdict"], "INSUFFICIENT")


# ------------------------------------------------------------------ acceptance gates


def need(path: Path) -> Path:
    if not path.exists():
        raise unittest.SkipTest(f"{path.relative_to(ROOT)} not present")
    return path


class MacroGate(unittest.TestCase):
    def manifest(self):
        return json.loads(need(DATA / "macro" / "manifest.json").read_text(encoding="utf-8"))

    def test_at_least_25_series_with_15_years(self):
        m = self.manifest()["series"]
        long_ = [k for k, v in m.items()
                 if (date.fromisoformat(v["last"]) - date.fromisoformat(v["first"])).days >= 15 * 365]
        self.assertGreaterEqual(len(long_), 25, f"only {len(long_)} series reach 15 years")

    def test_every_value_is_available_after_the_period_it_describes(self):
        for sid, v in self.manifest()["series"].items():
            if v["availability"] == "none":
                continue
            with open(DATA / "macro" / f"{sid}.csv", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self.assertGreaterEqual(row["availableAt"], row["observation_date"],
                                            f"{sid} {row['observation_date']}")

    def test_the_recession_flag_is_never_offered_as_a_feature(self):
        with open(need(DATA / "macro" / "USREC.csv"), encoding="utf-8") as f:
            self.assertTrue(all(r["availableAt"] == "" for r in csv.DictReader(f)))

    def test_shorter_series_are_reported_not_counted(self):
        m = self.manifest()
        for sid in m.get("shorterThan15Years", {}):
            self.assertNotIn(sid, m["series"])


class MacroVintageGate(unittest.TestCase):
    """Revision history: what was first published, what it became, and where we cannot know."""

    def files(self):
        d = DATA / "macro" / "vintages"
        if not d.exists() or not list(d.glob("*.jsonl")):
            raise unittest.SkipTest("no vintage files present")
        return sorted(d.glob("*.jsonl"))

    def rows(self, p):
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_at_least_ten_series_have_revision_history(self):
        self.assertGreaterEqual(len(self.files()), 10)

    def test_no_observation_is_first_seen_before_the_period_it_describes(self):
        for p in self.files():
            for r in self.rows(p):
                self.assertGreaterEqual(r["firstSeen"], r["obs"], f"{p.stem} {r['obs']}")

    def test_an_observation_older_than_the_first_snapshot_is_marked_left_censored(self):
        """Its firstSeen is when we first looked, not when it was published, and saying otherwise
        would turn a collection artefact into a release date."""
        for p in self.files():
            rows = self.rows(p)
            earliest = min(r["firstSeen"] for r in rows)
            for r in rows:
                self.assertEqual(r["leftCensored"], r["firstSeen"] <= earliest, f"{p.stem} {r['obs']}")

    def test_enough_observations_have_a_real_first_publication(self):
        real = sum(1 for p in self.files() for r in self.rows(p) if not r["leftCensored"])
        self.assertGreaterEqual(real, 1500, f"only {real} observations were first seen after collection began")

    def test_revisions_match_the_stored_history(self):
        for p in self.files():
            for r in self.rows(p):
                self.assertEqual(r["revisions"], len(r["history"]) - 1, f"{p.stem} {r['obs']}")
                self.assertEqual(r["firstValue"], r["history"][0][1])
                self.assertEqual(r["latestValue"], r["history"][-1][1])


class MacroPointInTime(unittest.TestCase):
    """The macro state attached to a session is what had been published by that session."""

    def setUp(self):
        if not (DATA / "macro" / "manifest.json").exists():
            self.skipTest("macro dataset not present")
        import macro_pit
        self.mp = macro_pit
        self.series = macro_pit.load_series()

    def test_the_recession_flag_is_excluded(self):
        self.assertNotIn("USREC", self.series)

    def test_nothing_in_a_session_state_was_published_after_that_session(self):
        for day in ("2019-03-15", "2020-03-16", "2022-06-15", "2026-09-01"):
            for sid in self.mp.state_at(self.series, day):
                i = self.mp.bisect_right(self.series[sid]["avail"], day) - 1
                self.assertLessEqual(self.series[sid]["avail"][i], day, f"{sid} on {day}")

    def test_a_slow_series_still_shows_the_figure_from_before_a_shock(self):
        """On 16 March 2020 the March unemployment rate did not exist yet. A join that showed the
        spike would be the look-ahead this whole availability column exists to prevent."""
        st = self.mp.state_at(self.series, "2020-03-16")
        self.assertIn("UNRATE", st)
        self.assertLess(st["UNRATE"]["v"], 5.0, "March 2020 unemployment leaked into a 16 March session")
        self.assertGreater(st["UNRATE"]["age"], 30, "a monthly figure cannot be fresher than its lag")

    def test_a_daily_series_is_fresh_and_a_quarterly_one_is_not(self):
        st = self.mp.state_at(self.series, "2024-06-14")
        self.assertLessEqual(st["DGS10"]["age"], 7)
        self.assertGreaterEqual(st["GDPC1"]["age"], 60)

    def test_every_state_value_carries_its_age(self):
        for sid, row in self.mp.state_at(self.series, "2023-05-10").items():
            self.assertIn("v", row)
            self.assertGreaterEqual(row["age"], 0, sid)


class CoverageDenominator(unittest.TestCase):
    """A completeness share is only meaningful if its denominator is the right calendar.

    Two defects an adversarial review of the gate verdicts found: weekdays are the wrong
    denominator for a market that trades every day, which made a complete crypto year read 1.398
    and forced the thin-year check to exclude crypto entirely; and a full-year denominator is
    wrong for the year in progress, which made every market read about 0.75 for 2026 when only
    205 of 261 weekdays had happened.
    """

    @staticmethod
    def denom(market, year, last_in_data):
        from datetime import timedelta
        d, n, last = date(year, 1, 1), 0, min(date(year, 12, 31), last_in_data)
        while d <= last:
            if market == "crypto" or d.weekday() < 5:
                n += 1
            d += timedelta(days=1)
        return n

    def test_a_complete_crypto_year_is_one_not_one_point_four(self):
        self.assertEqual(self.denom("crypto", 2023, date(2026, 10, 13)), 365)
        self.assertAlmostEqual(365 / self.denom("crypto", 2023, date(2026, 10, 13)), 1.0)

    def test_the_year_in_progress_counts_only_elapsed_days(self):
        last = date(2026, 10, 13)
        self.assertLess(self.denom("US", 2026, last), self.denom("US", 2025, last))
        self.assertAlmostEqual(196 / self.denom("US", 2026, last), 0.961, places=2)

    def test_the_source_no_longer_special_cases_crypto(self):
        src = (ROOT / "tools" / "foundation" / "coverage_gaps.py").read_text(encoding="utf-8")
        self.assertNotIn('m != "crypto"', src,
                         "excluding crypto from the thin-year check hid a whole market")
        self.assertIn("daysElapsed", src)


class PrinciplesGate(unittest.TestCase):
    def doc(self):
        return json.loads(need(DATA / "principles" / "principles.json").read_text(encoding="utf-8"))

    def test_at_least_50_verified_and_testable(self):
        s = self.doc()["summary"]
        self.assertGreaterEqual(s["verifiedAndTestableNow"], 50)

    def test_ids_are_unique_and_each_is_specified(self):
        rows = self.doc()["principles"]
        self.assertEqual(len({r["id"] for r in rows}), len(rows))
        for r in rows:
            for k in ("signal", "horizon", "needs", "test", "doi", "finding"):
                self.assertTrue(r.get(k), f"{r['id']} lacks {k}")
            self.assertEqual(r["status"], "untested", "a principle is untested until a walk-forward result exists")

    def test_the_corpus_says_which_principles_actually_have_a_rule(self):
        """"Testable" and "tested" are different claims and the corpus must not blur them."""
        import evaluate_principles as ep
        doc = self.doc()
        have = {pid for pid, _, _ in ep.RULES}
        for r in doc["principles"]:
            self.assertEqual(r["hasRunnableRule"], r["id"] in have, r["id"])
            if r["hasRunnableRule"]:
                self.assertTrue(r["testable_now"], f"{r['id']} has a rule but is marked untestable")
        s = doc["summary"]
        self.assertEqual(s["withRunnableRule"], sum(r["hasRunnableRule"] for r in doc["principles"]))
        self.assertGreater(s["testableWithoutARuleYet"], 0,
                           "if every testable principle has a rule, say so rather than hiding the field")

    def test_testable_means_every_input_is_stored(self):
        for r in self.doc()["principles"]:
            if "fundamentals" in r["needs"] or "term structure" in r["needs"] or "foreign short rates" in r["needs"]:
                self.assertFalse(r["testable_now"], r["id"])


class EventsGate(unittest.TestCase):
    def doc(self):
        return json.loads(need(DATA / "events" / "events.json").read_text(encoding="utf-8"))

    @staticmethod
    def has_primary_evidence(e):
        wiki = bool(e.get("wikipedia") and e["wikipedia"].get("url"))
        official = any(o.get("dateInDocument") or o.get("accession") for o in e.get("official", []))
        return wiki or official

    def test_at_least_100_distinct_verified_clusters(self):
        s = self.doc()["summary"]
        self.assertGreaterEqual(s["distinctVerifiedClusters"], 100)

    def test_events_span_at_least_eight_categories(self):
        by = self.doc()["summary"]["byCategory"]
        self.assertGreaterEqual(sum(1 for v in by.values() if v["verified"] >= 4), 8)

    def test_every_verified_event_has_primary_evidence(self):
        for e in self.doc()["events"]:
            if e["verified"]:
                self.assertTrue(self.has_primary_evidence(e), e["name"])
                self.assertIn(e["tier"], ("A", "B"))

    def test_an_event_with_no_article_and_no_official_record_is_never_counted(self):
        for e in self.doc()["events"]:
            if not self.has_primary_evidence(e):
                self.assertFalse(e["verified"], e["name"])

    def test_price_screened_events_do_not_count_the_screen_as_evidence(self):
        for e in self.doc()["events"]:
            if e.get("selection") == "price-screened":
                self.assertNotIn("market-move", e["evidenceGroups"], e["name"])

    def test_multi_source_count_is_reported_separately(self):
        s = self.doc()["summary"]
        self.assertLessEqual(s["distinctMultiSourceClusters"], s["distinctVerifiedClusters"])


if __name__ == "__main__":
    unittest.main()
