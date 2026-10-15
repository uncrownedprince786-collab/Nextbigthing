"""The macro layer end to end: stored CSV and vintage file -> parse -> point-in-time -> consumer.

These run against the **real** stored series, not fixtures, because the thing worth proving is
that the actual files on disk cannot hand a decision a value that was not public yet.
"""

from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from macro_context import (  # noqa: E402
    SERIES_DIR,
    VINTAGE_DIR,
    as_of,
    available_series,
    context_for,
)

# A daily series with a one-day lag; a monthly one with a 16-day lag whose values are never
# revised, so its own `availableAt` is authoritative; and a revision-tracked monthly series,
# whose CSV `value` is the final revision and therefore is NOT authoritative.
FAST = "DGS10"
SLOW_UNREVISED = "CPILFESL"
TRACKED = "CPIAUCSL"


def test_the_series_are_actually_present():
    codes = available_series()
    assert len(codes) >= 30, "the macro layer is supposed to hold 32 series"
    assert SLOW_UNREVISED in codes and FAST in codes and TRACKED in codes


def test_no_reading_is_ever_published_after_the_decision_date():
    # The leakage test. Sweep every series on several dates and assert the invariant.
    for on in ("2019-03-15", "2021-07-01", "2024-02-29", "2026-01-05"):
        block = context_for(on)
        for code, rec in block["readings"].items():
            assert rec["availableAt"] <= on, f"{code} leaked a value published {rec['availableAt']}"


def test_an_observation_is_withheld_until_its_publication_day():
    """For a series that is never revised, its own `availableAt` is the publication date."""
    with (SERIES_DIR / f"{SLOW_UNREVISED}.csv").open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["value"].strip() not in ("", ".")]
    row = next(r for r in rows[1:] if r["availableAt"] > r["observation_date"])
    obs, pub = row["observation_date"], row["availableAt"]
    day_before = (date.fromisoformat(pub) - timedelta(days=1)).isoformat()
    earlier = as_of(SLOW_UNREVISED, day_before)
    assert earlier is None or earlier["observationDate"] < obs, "published a value a day early"
    onday = as_of(SLOW_UNREVISED, pub)
    assert onday is not None and onday["observationDate"] >= obs


def test_the_csv_value_is_not_trusted_for_a_revision_tracked_series():
    """The defect this module exists to contain.

    The stored CSV pairs the *final revised* value with the *first* publication date. For CPI's
    2010-01-01 observation it holds availableAt 2010-02-16 beside 217.488, but the vintage
    history shows 217.488 is the 2015-02-28 revision and the figure actually printed in 2010 was
    217.587. A consumer that read the CSV row on its own availableAt would be five years early.
    """
    with (SERIES_DIR / f"{TRACKED}.csv").open(newline="", encoding="utf-8") as fh:
        first = next(r for r in csv.DictReader(fh) if r["value"].strip() not in ("", "."))
    # On the CSV's own availableAt, no revision had been published yet, so there is nothing to
    # return -- and in particular not the CSV's final value.
    rec = as_of(TRACKED, first["availableAt"])
    assert rec is None or rec["value"] != first["value"], "returned a later revision too early"


def test_a_tracked_series_becomes_readable_once_a_revision_is_public():
    rec = as_of(TRACKED, "2010-03-01")
    assert rec is not None, "the first revision was published 2010-02-28"
    assert rec["availableAt"] <= "2010-03-01"
    assert rec["revisionTracked"] is True


def test_provenance_travels_with_every_reading():
    rec = as_of(FAST, "2024-06-03")
    assert rec is not None
    for field in ("series", "observationDate", "value", "availableAt", "asOf", "ageDays", "source"):
        assert field in rec, field
    assert rec["source"].endswith(f"{FAST}.csv")


def test_a_reading_carries_no_direction():
    rec = as_of(FAST, "2024-06-03")
    forbidden = {"direction", "vote", "signal", "bias", "action", "score"}
    assert forbidden.isdisjoint(rec), "macro context must not expose anything vote-shaped"


def test_the_context_block_declares_it_may_not_vote():
    block = context_for("2024-06-03", [FAST])
    assert block["role"] == "decision-context"
    assert block["mayVote"] is False


def test_unknown_or_too_early_returns_none_not_a_default():
    assert as_of("NOT_A_SERIES", "2024-06-03") is None
    assert as_of(FAST, "1990-01-01") is None, "before the series began"


def test_what_could_not_be_read_is_named():
    block = context_for("2024-06-03", [FAST, "NOT_A_SERIES"])
    assert "NOT_A_SERIES" in block["notKnowable"]
    assert FAST in block["readings"]


def test_staleness_is_reported_rather_than_hidden():
    rec = as_of(SLOW_UNREVISED, "2024-06-03")
    assert rec is not None and rec["ageDays"] >= 0
    # A monthly series read mid-month is at least a couple of weeks old by observation date.
    assert rec["ageDays"] >= 14


def test_a_revision_tracked_series_uses_the_vintage_known_at_the_time():
    tracked = [p.stem for p in VINTAGE_DIR.glob("*.jsonl")]
    assert tracked, "no vintage files found"
    code = tracked[0]
    rec = as_of(code, "2026-01-05")
    assert rec is not None
    assert rec["revisionTracked"] is True
    assert rec["revisionsKnown"] >= 0
    assert rec["availableAt"] <= "2026-01-05"


def test_a_later_decision_date_never_sees_less_than_an_earlier_one():
    # Monotonicity: knowledge only accumulates, which is what a point-in-time read means.
    early = context_for("2020-01-02")
    late = context_for("2024-01-02")
    assert set(early["readings"]) <= set(late["readings"])


def test_missing_values_are_skipped_not_zero_filled():
    # FRED writes an unavailable daily print as ".", which must never become 0.0.
    rec = as_of(FAST, "2024-06-03")
    assert rec is not None and rec["value"] != "." and rec["value"] != ""
    float(rec["value"])          # parses, and the caller decides the type
