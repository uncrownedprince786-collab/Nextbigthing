"""The gradient-boosting harness must be gated on problems its own fixed capacity can answer.

    python -m unittest discover -s tests -p test_boost_experiment.py -v

Stdlib unittest, no database and no network -- the synthetic cases only. This module is the
durable form of `boost_experiment.py --selftest`, plus a regression per preflight repair the
harness needed before it was allowed to touch a market row:

* the five correctness gates (`test_selftest_passes`) with the thresholds declared in the module,
  not the lowered ones a first draft used to make a wrong case pass;
* the histogram split search is a bit-identical reformulation of the per-feature scan
  (`test_best_split_matches_reference_scan`) and refuses a non-positive gain when GAMMA is 0
  (`test_best_split_refuses_nonpositive_gain`);
* the shuffled control takes its weights from the permuted labels, never the originals
  (`test_control_weights_come_from_permuted_labels`);
* the source-digest mirror matches the builder it mirrors (`test_feature_row_mirror`).
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import boost_experiment as B  # noqa: E402
from eligible_set_experiment import build_with_labels  # noqa: E402


def _reference_best_split(Bm, idx, g, h):
    """The declared per-feature scan, kept here so the shipped histogram search is checked against
    it. Returns (feature, bin) and its gain even when the gain is non-positive, so the caller can
    check both the identity and the positive-gain rule."""
    if len(idx) < 2 * B.MIN_CHILD:
        return None, None
    gb, hb = g[idx], h[idx]
    G, L = float(gb.sum()), float(hb.sum())
    base = G * G / (L + B.LAMBDA)
    best_f, best_b, best_gain = None, None, -np.inf
    for f in range(Bm.shape[1]):
        bf = Bm[idx, f]
        cg = np.bincount(bf, weights=gb, minlength=B.BINS)
        ch = np.bincount(bf, weights=hb, minlength=B.BINS)
        cc = np.bincount(bf, minlength=B.BINS).astype(np.float64)
        cl, hl, nl = np.cumsum(cg), np.cumsum(ch), np.cumsum(cc)
        cr, hr, nr = G - cl, L - hl, len(idx) - nl
        ok = (nl >= B.MIN_CHILD) & (nr >= B.MIN_CHILD)
        if not ok.any():
            continue
        gain = 0.5 * (cl * cl / (hl + B.LAMBDA) + cr * cr / (hr + B.LAMBDA) - base) - B.GAMMA
        gain = np.where(ok, gain, -np.inf)
        b = int(np.argmax(gain))
        if gain[b] > best_gain:
            best_f, best_b, best_gain = f, b, float(gain[b])
    if best_f is None or not np.isfinite(best_gain):
        return None, None
    return (best_f, best_b), best_gain


class SelftestGates(unittest.TestCase):
    def test_selftest_passes(self):
        st = B.selftest()
        self.assertTrue(st["passed"], msg=json.dumps(st, sort_keys=True))
        for key in ("xor_pass", "interaction_pass", "separable_pass", "shuffled_pass"):
            self.assertTrue(st[key], msg=json.dumps(st, sort_keys=True))
        self.assertTrue(st["deterministic"])
        self.assertGreaterEqual(st["xor_boostingAccuracy"], B.ST_BOOST_MIN_ACC)
        self.assertLessEqual(st["xor_linearAccuracy"], B.ST_LINEAR_MAX_ACC)
        self.assertGreaterEqual(st["interaction_boostingAccuracy"], B.ST_BOOST_MIN_ACC)
        self.assertGreaterEqual(st["interaction_boostingOverMajority"], B.ST_MARGIN_MIN)
        self.assertLessEqual(st["interaction_linearOverMajority"], B.ST_LINEAR_MARGIN_MAX)
        self.assertGreaterEqual(st["separable_boostingAccuracy"], B.ST_SEPARABLE_MIN_ACC)
        self.assertGreaterEqual(st["separable_linearAccuracy"], B.ST_SEPARABLE_MIN_ACC)
        self.assertLessEqual(st["shuffled_overMajority"], B.ST_SHUFFLE_TOL)

    def test_declared_thresholds_not_lowered(self):
        self.assertGreaterEqual(B.ST_BOOST_MIN_ACC, 0.98)
        self.assertGreaterEqual(B.ST_SEPARABLE_MIN_ACC, 0.99)
        self.assertLessEqual(B.ST_LINEAR_MAX_ACC, 0.65)


class SplitSearch(unittest.TestCase):
    def test_best_split_matches_reference_scan(self):
        rng = np.random.default_rng(11)
        for trial in range(6):
            n = int(rng.integers(1500, 4000))
            nfeat = int(rng.integers(3, 9))
            edges = B.bin_edges(rng.normal(0, 1, size=(400, nfeat)))
            Bm = B.digitize(rng.normal(0, 1, size=(n, nfeat)), edges)
            y = (rng.random(n) > 0.5).astype(np.float64)
            w = B.row_weights(y.astype(np.int64))
            g = w * (0.5 - y)
            h = w * np.full(n, 0.25)
            idx = np.arange(n)
            ref, ref_gain = _reference_best_split(Bm, idx, g, h)
            got = B.best_split(Bm, idx, g, h)
            if ref_gain is not None and ref_gain > B.GAMMA:
                self.assertIsNotNone(got)
                self.assertEqual(got[0], ref)
                self.assertEqual(got[1], ref_gain)
            else:
                self.assertIsNone(got)

    def test_best_split_refuses_nonpositive_gain(self):
        rng = np.random.default_rng(3)
        n, nfeat = 3000, 5
        edges = B.bin_edges(rng.normal(0, 1, size=(400, nfeat)))
        Bm = B.digitize(rng.normal(0, 1, size=(n, nfeat)), edges)
        y = np.zeros(n, dtype=np.float64)
        idx = np.arange(n)
        g = np.zeros(n)
        h = np.full(n, 0.25)
        self.assertIsNone(B.best_split(Bm, idx, g, h))
        y = (Bm[:, 0] >= B.BINS // 2).astype(np.float64)
        w = B.row_weights(y.astype(np.int64))
        g = w * (0.5 - y)
        got = B.best_split(Bm, idx, g, h)
        self.assertIsNotNone(got)
        self.assertGreater(got[1], 0.0)

    def test_too_few_rows_is_a_leaf(self):
        rng = np.random.default_rng(5)
        Bm = B.digitize(rng.normal(0, 1, size=(10, 4)), B.bin_edges(rng.normal(0, 1, (50, 4))))
        idx = np.arange(10)
        self.assertIsNone(B.best_split(Bm, idx, np.ones(10), np.ones(10)))


class ControlWeights(unittest.TestCase):
    def test_control_weights_come_from_permuted_labels(self):
        rng = np.random.default_rng(9)
        y = np.concatenate([np.zeros(700, dtype=np.int64), np.ones(300, dtype=np.int64)])
        permuted = B.shuffled_control_target(y, rng)
        self.assertEqual(sorted(permuted.tolist()), sorted(y.tolist()))
        original_w = B.row_weights(y)
        control_w = B.row_weights(permuted)
        self.assertFalse(np.array_equal(original_w, control_w))
        self.assertTrue(np.array_equal(control_w, B.row_weights(permuted)))
        self.assertAlmostEqual(len(control_w), len(y))

    def test_row_weights_are_mean_one(self):
        y = np.concatenate([np.zeros(80, dtype=np.int64), np.ones(20, dtype=np.int64)])
        self.assertAlmostEqual(float(B.row_weights(y).mean()), 1.0, places=9)


class Integrity(unittest.TestCase):
    def test_feature_row_mirror(self):
        with tempfile.TemporaryDirectory() as td:
            ds = Path(td)
            rows = [
                {"asOf": "2020-01-02", "assetType": "equity", "pit": {"f": {
                    "momentum": 1.5, "trend": "up", "value": None, "x": 2}},
                 "outcome": {"label20": "UP", "mature20": True}, "dataQuality": {"a": False}},
                {"asOf": "2020-01-03", "assetType": "crypto", "pit": {
                    "f": {"momentum": -0.5}, "ctx": {"f": {"trend": "down", "value": 0.1,
                                                           "x": 3}}},
                 "outcome": {"label20": "DOWN", "mature20": True}},
                {"asOf": "2020-01-04", "assetType": "equity", "pit": {"f": {"momentum": 1.0}},
                 "outcome": {"label20": "FLAT", "mature20": False}},
            ]
            with gzip.open(ds / "examples-v4-context-2020.jsonl.gz", "wt",
                           encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
            built = build_with_labels(ds)
            src = B.source_row_digest(ds)
            cac = B.cache_row_digest(built)
            self.assertEqual(src["kept"], 2)
            self.assertEqual(src["kept"], cac["kept"])
            self.assertEqual(src["digest"], cac["digest"])
            self.assertEqual(src["labelCounts"], cac["labelCounts"])


class ResourceEnvelope(unittest.TestCase):
    def test_dynamic_limit_is_bounded(self):
        limit = B.dynamic_rss_limit_mb()
        self.assertLessEqual(limit, B.RSS_LIMIT_CAP_MB)
        self.assertGreaterEqual(limit, B.RSS_LIMIT_FLOOR_MB)


if __name__ == "__main__":
    unittest.main()
