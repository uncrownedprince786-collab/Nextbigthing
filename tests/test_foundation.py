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

    def test_missingness_is_reported_per_factor(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make(root)
            _, m = self.run_main(root)
            self.assertEqual(m["missingnessByAssetClass"]["stock"]["volumeRatio"], 1.0)
            self.assertEqual(m["missingnessByAssetClass"]["stock"]["r1"], 0.0)


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
