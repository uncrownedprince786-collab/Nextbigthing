"""Every acquired layer has a destination, and only instrument-level layers may vote.

The rule worth pinning is the second one. A market-wide series handed to 616 instruments as a
per-asset directional vote is one fact counted 616 times, and the shipped design already refuses
it -- `lib/decision.ts` calls `macroVeto` a veto only. These tests stop that refusal being
quietly undone by adding a role to a table.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools" / "research"))

from context_routing import ROLES, ROUTES, route, verify  # noqa: E402
from regime_breakdown import OUTSIDE, episode_of, episodes_in_training, stratify  # noqa: E402

INVENTORY = ROOT / "data" / "foundation" / "dataset" / "source_inventory.json"


def test_every_inventory_layer_is_routed():
    layers = [L["layer"] for L in json.loads(INVENTORY.read_text(encoding="utf-8"))["layers"]]
    assert sorted(layers) == sorted(ROUTES), "a layer with no destination is a defect, not a gap"


def test_every_declared_consumer_resolves_on_disk():
    report = verify(ROOT)
    missing = [r["layer"] for r in report["layers"] if not r["consumerResolves"]]
    assert missing == [], f"routed to a consumer that does not exist: {missing}"


def test_no_layer_invents_a_role():
    for layer, (roles, *_rest) in ROUTES.items():
        for r in roles:
            assert r in ROLES, f"{layer} claims unknown role {r}"


def test_only_instrument_level_layers_may_vote():
    for layer, (roles, may_vote, *_rest) in ROUTES.items():
        if may_vote:
            assert "directional-evidence" in roles or "training-feature" in roles, layer


def test_macro_news_and_events_never_vote():
    for layer in ("macroeconomic series (point-in-time)", "dated events corpus",
                  "operational news feed", "press and original-document evidence",
                  "interest rates and yield curve"):
        assert route(layer)["mayVote"] is False, f"{layer} must not cast a directional vote"


def test_regime_episodes_are_evaluation_only():
    r = route("regime episodes")
    assert r["roles"] == ["evaluation-stratification"]
    assert r["mayVote"] is False, "a window known only in hindsight cannot feed a predictor"


def test_blocked_layers_are_documented_not_silently_dropped():
    for layer in ("delisted instrument price history", "PSX history before 2013-11-04"):
        assert route(layer)["roles"] == ["documented-exclusion"]


def test_verify_reports_nothing_broken():
    assert verify(ROOT)["summary"]["unroutedOrBroken"] == []


# ---------------------------------------------------------------- regime assignment


def test_only_episodes_inside_the_training_data_are_used():
    eps = episodes_in_training()
    assert eps, "no episode overlaps the training data"
    for _name, lo, _hi in eps:
        assert lo >= "2018-01-01", "examples-v3 begins 2018-01-01"


def test_a_session_outside_every_episode_is_none_not_calm():
    eps = [("x", "2020-01-01", "2020-12-31")]
    assert episode_of("2019-05-01", eps) == OUTSIDE
    assert episode_of("2020-06-01", eps) == "x"


def test_overlapping_windows_resolve_to_the_earliest_start():
    eps = [("early", "2020-01-01", "2020-12-31"), ("late", "2020-06-01", "2021-06-30")]
    assert episode_of("2020-08-01", eps) == "early"


def test_each_group_is_scored_against_its_own_majority():
    dates = ["2020-03-02"] * 4 + ["2019-01-02"] * 4
    truth = [0, 0, 0, 1, 1, 1, 1, 0]
    pred = [0, 0, 0, 0, 1, 1, 1, 1]
    out = stratify(dates, truth, pred, {"g": ["a"] * 4 + ["b"] * 4})["g"]
    assert out["a"]["n"] == 4 and out["b"]["n"] == 4
    # group a: 3 of 4 correct, majority 3 of 4 -> margin 0
    assert out["a"]["accuracy"] == 0.75 and out["a"]["majorityRate"] == 0.75
    assert out["a"]["margin"] == 0.0
    # group b: 3 of 4 correct against its own 3-of-4 majority
    assert out["b"]["majorityRate"] == 0.75


def test_a_proving_test_is_named_and_exists_or_is_honestly_blank():
    """A route may be unproven, but it may not claim a test that is not there."""
    for layer, (*_rest, proof) in ROUTES.items():
        if proof:
            assert (ROOT / proof).exists(), f"{layer} names a test that does not exist: {proof}"


def test_the_matrix_separates_resolved_from_proven():
    s = verify(ROOT)["summary"]
    assert s["consumersResolving"] == s["declared"], "every consumer must resolve"
    assert s["integrationProven"] <= s["consumersResolving"]
    # The unproven ones are named rather than folded into the total.
    assert len(s["routedNotYetProven"]) == s["declared"] - s["integrationProven"]


def test_macro_is_proven_and_still_may_not_vote():
    r = route("macroeconomic series (point-in-time)")
    assert r["consumer"].endswith("macro_context.py")
    assert r["provingTest"] == "tests/test_macro_context.py"
    assert r["mayVote"] is False
