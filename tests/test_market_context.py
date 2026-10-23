"""The market-factor block: aligned by instant, blind to the future, honest about Bitcoin itself.

`tools/research/market_context.py` reads a *second* series to build features for the first, which
is a new way for this repository to leak. Every f1 feature is computed from `bars[:i + 1]` and
cannot see forward by construction; a context feature could, trivially, by reading the factor's
bar at `i + 1` and nobody noticing until the holdout looked too good.

So the central test here is the one that cannot be argued with: truncate the factor's series
immediately after the decision bar, recompute, and require every value to be identical. A feature
that changes is a feature that was reading something that had not happened yet.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))

from market_context import (  # noqa: E402
    CONTEXT_FEATURES,
    LINK_WINDOW,
    N_CONTEXT,
    context_for,
)

STEP = 300_000
WARMUP = 288


def series(n: int, seed: int, start: float = 100.0, drift: float = 0.0):
    """A plausible 5-minute series: ascending timestamps, positive closes, high >= close >= low."""
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, 0.002, n)
    close = start * np.exp(np.cumsum(r))
    spread = np.abs(rng.normal(0, 0.001, n)) * close
    ts = np.arange(n, dtype=np.int64) * STEP + 1_600_000_000_000
    return ts, close, close + spread, close - spread


class Alignment(unittest.TestCase):
    def test_a_bar_the_factor_does_not_have_is_unusable_not_imputed(self):
        n = WARMUP + 200
        ts, c, h, l = series(n, 1)
        # Remove a run of factor bars from the middle, the shape a venue outage actually takes.
        hole = slice(WARMUP + 50, WARMUP + 70)
        keep = np.ones(n, dtype=bool)
        keep[hole] = False
        C, ok = context_for(ts, c, ts[keep], c[keep], h[keep], l[keep], WARMUP)
        self.assertFalse(ok[hole].any(), "rows over a factor outage must not be usable")
        self.assertTrue(ok[WARMUP + 100:].any(), "rows after the outage are usable again")
        # And nothing was written into the unusable rows for a caller to read by accident.
        self.assertTrue(np.isnan(C[hole]).all())

    def test_nothing_before_the_warmup_is_usable(self):
        n = WARMUP + 100
        ts, c, h, l = series(n, 2)
        _, ok = context_for(ts, c, ts, c, h, l, WARMUP)
        self.assertFalse(ok[:WARMUP].any())

    def test_an_empty_factor_series_yields_no_usable_rows(self):
        ts, c, h, l = series(WARMUP + 50, 3)
        empty = np.zeros(0)
        C, ok = context_for(ts, c, np.zeros(0, dtype=np.int64), empty, empty, empty, WARMUP)
        self.assertFalse(ok.any())
        self.assertEqual(C.shape, (len(ts), N_CONTEXT))


class NoLookAhead(unittest.TestCase):
    """The property the whole block lives or dies by."""

    def test_truncating_the_factor_after_the_decision_bar_changes_nothing(self):
        n = WARMUP + 400
        ts, c, h, l = series(n, 11)
        mts, mc, mh, ml = series(n, 12, start=50_000.0)
        full, ok_full = context_for(ts, c, mts, mc, mh, ml, WARMUP)

        # Several decision bars across the usable range, each recomputed against a factor series
        # that simply does not contain anything after that instant.
        for i in (WARMUP + 10, WARMUP + 150, WARMUP + 399):
            cut = i + 1
            part, ok_part = context_for(ts[:cut], c[:cut], mts[:cut], mc[:cut], mh[:cut], ml[:cut],
                                        WARMUP)
            self.assertTrue(ok_full[i] and ok_part[i], f"row {i} usable both ways")
            np.testing.assert_allclose(
                part[i], full[i], rtol=1e-6, atol=1e-8,
                err_msg=f"context at row {i} changed when the future was removed -- it is "
                        f"reading forward")

    def test_a_later_factor_bar_cannot_move_an_earlier_row(self):
        n = WARMUP + 200
        ts, c, h, l = series(n, 21)
        mts, mc, mh, ml = series(n, 22, start=3000.0)
        base, ok = context_for(ts, c, mts, mc, mh, ml, WARMUP)
        # A violent move in the factor, strictly after the row being checked.
        i = WARMUP + 100
        mc2 = mc.copy()
        mc2[i + 1:] *= 3.0
        after, _ = context_for(ts, c, mts, mc2, mh, ml, WARMUP)
        np.testing.assert_allclose(after[i], base[i], rtol=1e-6, atol=1e-8)


class BitcoinAgainstItself(unittest.TestCase):
    """The degenerate case is left as it is, so it has to be exactly what it claims."""

    def test_the_factor_against_itself_has_zero_residual_and_unit_beta(self):
        n = WARMUP + 300
        ts, c, h, l = series(n, 31)
        C, ok = context_for(ts, c, ts, c, h, l, WARMUP)
        self.assertTrue(ok[WARMUP + LINK_WINDOW:].any())
        idx = {f: i for i, f in enumerate(CONTEXT_FEATURES)}
        rows = np.flatnonzero(ok)
        rows = rows[rows >= WARMUP + LINK_WINDOW]
        for name in ("relR1", "relR12", "relR48"):
            np.testing.assert_allclose(C[rows, idx[name]], 0.0, atol=1e-6,
                                       err_msg=f"{name} must be exactly zero against itself")
        np.testing.assert_allclose(C[rows, idx["beta48"]], 1.0, rtol=1e-4,
                                   err_msg="beta against itself must be one")
        np.testing.assert_allclose(C[rows, idx["corr48"]], 1.0, rtol=1e-4,
                                   err_msg="correlation against itself must be one")


class Shape(unittest.TestCase):
    def test_every_usable_row_is_finite_and_the_names_match_the_width(self):
        n = WARMUP + 300
        ts, c, h, l = series(n, 41)
        mts, mc, mh, ml = series(n, 42, start=70_000.0)
        C, ok = context_for(ts, c, mts, mc, mh, ml, WARMUP)
        self.assertEqual(C.shape[1], len(CONTEXT_FEATURES))
        self.assertTrue(np.isfinite(C[ok]).all(), "a usable row must carry no NaN or inf")

    def test_beta_is_clipped_so_a_flat_factor_cannot_produce_an_absurd_split(self):
        n = WARMUP + 200
        ts, c, h, l = series(n, 51)
        # A factor that barely moves: the regression denominator goes to nothing.
        mts = ts.copy()
        mc = np.full(n, 50_000.0) + np.arange(n) * 1e-9
        C, ok = context_for(ts, c, mts, mc, mc, mc, WARMUP)
        idx = {f: i for i, f in enumerate(CONTEXT_FEATURES)}
        beta = C[ok, idx["beta48"]]
        self.assertTrue(np.all(np.abs(beta) <= 5.0 + 1e-6), "beta must stay inside its clip")
        corr = C[ok, idx["corr48"]]
        self.assertTrue(np.all(np.abs(corr) <= 1.0 + 1e-6), "correlation must stay in [-1, 1]")


if __name__ == "__main__":
    unittest.main()
