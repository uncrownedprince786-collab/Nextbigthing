"""The 60-session label: units, the floor, maturity, and the calibration rule.

The unit test is the point of this file. `atr14` is in price units and `fwd60` is a percentage,
and a band that forgets the conversion compares a price against a percent and silently mislabels
every row. `test_band_is_a_percentage_not_a_price` is what pins that.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))

from label60 import (  # noqa: E402
    DOWN,
    FLAT,
    HORIZON,
    LABEL_THRESHOLD_PCT,
    UP,
    band_pct,
    calibrate_m,
    implied_multiple,
    label_of,
)


def test_horizon_is_sixty():
    assert HORIZON == 60


def test_band_is_a_percentage_not_a_price():
    # A $200 stock with a $4 ATR: at m = 1 the band is 2% of price, not 4.
    assert band_pct(4.0, 200.0, 1.0) == 2.0
    # Doubling the price halves the percentage band for the same ATR.
    assert band_pct(4.0, 400.0, 1.0) == LABEL_THRESHOLD_PCT  # 1.0 -> floored to 2.0
    assert band_pct(16.0, 400.0, 1.0) == 4.0


def test_floor_binds_only_below_the_frozen_band():
    assert band_pct(0.01, 100.0, 1.0) == LABEL_THRESHOLD_PCT  # 0.01% -> floored
    assert band_pct(10.0, 100.0, 1.0) == 10.0                 # above the floor, untouched


def test_missing_inputs_give_no_band_and_no_label():
    assert band_pct(None, 100.0, 2.0) is None
    assert band_pct(4.0, None, 2.0) is None
    assert band_pct(4.0, 0.0, 2.0) is None      # non-positive base
    assert band_pct(0.0, 100.0, 2.0) is None    # a zero ATR is not a zero band
    assert label_of(5.0, None) is None


def test_immature_window_is_excluded_never_flat():
    # fwd60 is None exactly when fewer than 60 forward sessions are stored.
    assert label_of(None, 3.0) is None
    assert label_of(None, 3.0) != FLAT


def test_label_boundaries_are_inclusive_like_label20():
    band = 3.0
    assert label_of(3.0, band) == UP       # >= band
    assert label_of(-3.0, band) == DOWN    # <= -band
    assert label_of(2.999, band) == FLAT
    assert label_of(-2.999, band) == FLAT
    assert label_of(0.0, band) == FLAT


def test_implied_multiple_inverts_the_frozen_band():
    # An instrument whose ATR is 1% of price: the frozen 2% band is two of its ATRs.
    assert implied_multiple(1.0, 100.0) == 2.0
    # One whose ATR is 2% of price: the same band is exactly one ATR.
    assert implied_multiple(2.0, 100.0) == 1.0


def test_calibrate_m_is_the_median_and_skips_unusable_rows():
    rows = [(1.0, 100.0), (2.0, 100.0), (4.0, 100.0), (None, 100.0), (1.0, 0.0)]
    # implied multiples: 2.0, 1.0, 0.5 -> median 1.0; the last two contribute nothing.
    assert calibrate_m(rows) == 1.0


def test_calibrate_m_refuses_rather_than_defaulting():
    assert calibrate_m([]) is None
    assert calibrate_m([(None, None)]) is None


def test_a_calibrated_band_reproduces_the_frozen_band_for_the_median_instrument():
    # The point of the calibration rule: at the median instrument, label60's band equals the
    # 2% band label20 already uses -- so the horizons differ by window, not by what counts
    # as a move.
    rows = [(1.0, 100.0), (1.0, 100.0), (1.0, 100.0)]
    m = calibrate_m(rows)
    assert band_pct(1.0, 100.0, m) == LABEL_THRESHOLD_PCT
