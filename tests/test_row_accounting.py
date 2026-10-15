"""Row accounting: a partition, not a second tally of flags.

The distinction this pins is the one that made three published row counts look contradictory.
`rowsCarryingEachFlag` counts every row carrying a flag, so a row with two flags is counted
twice. `pipelineAttribution` assigns each row to the first rule that rejected it, so the same
row is counted once. Both are correct; only together do they reconcile.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))

from row_accounting import FLAGS, RULES, classify  # noqa: E402


def row(features=True, base=1.0, **flags):
    return {"pit": {"f": {"atr14": 1.0}} if features else {},
            "dataQuality": dict(flags),
            "outcome": {"baseClose": base}}


def test_an_eligible_row_has_no_cause():
    assert classify(row()) is None


def test_featureless_is_claimed_before_any_flag():
    # The row carries a flag AND has no features; the pipeline attributes it to the earlier rule.
    r = row(features=False, unadjustedActionInWindow=True)
    assert classify(r) == "noPointInTimeFeatures"


def test_the_first_matching_flag_wins():
    r = row(unadjustedActionInWindow=True, windowIsNotDaily=True)
    assert classify(r) == "unadjustedActionInWindow"
    assert RULES.index("unadjustedActionInWindow") < RULES.index("windowIsNotDaily")


def test_each_flag_alone_is_attributed_to_itself():
    for flag in FLAGS:
        assert classify(row(**{flag: True})) == flag


def test_a_missing_base_close_is_its_own_cause_not_a_flag():
    assert classify(row(base=None)) == "noBaseClose"


def test_rule_order_is_declared_and_covers_every_flag():
    # Every flag must appear in RULES, or a row carrying it would be silently eligible.
    for flag in FLAGS:
        assert flag in RULES


def test_a_falsy_flag_does_not_reject():
    # Flags arrive as booleans; `False` must not be read as "present".
    assert classify(row(unadjustedActionInWindow=False)) is None
