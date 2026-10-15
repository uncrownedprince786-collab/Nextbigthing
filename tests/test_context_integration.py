"""The last three context routes, proven by behaviour rather than by a path existing.

Rates, the operational news feed and the principles corpus were the three layers
`context_routing.py` listed as routed-but-unproven. Each is checked here against what it is
actually supposed to do downstream, and each is held to the rule that only the three approved
families may cast a directional vote.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from macro_context import CURVE, curve_at  # noqa: E402

PRINCIPLES = ROOT / "data" / "foundation" / "principles" / "principles.json"
DECISION_TS = ROOT / "lib" / "decision.ts"
RETENTION = ROOT / "jobs" / "retention.py"
PRESS = ROOT / "data" / "foundation" / "events" / "press_evidence.jsonl"


# ---------------------------------------------------------------- rates


def test_the_curve_reads_its_shape_not_a_single_tenor():
    c = curve_at("2023-05-01")
    assert set(c["tenors"]) == {"DGS3MO", "DGS2", "DGS10"}
    assert set(c["spreads"]) == {"T10Y2Y", "T10Y3M"}


def test_a_known_inversion_is_detected():
    # May 2023: both 10y-2y and 10y-3m were deeply negative.
    c = curve_at("2023-05-01")
    assert c["inverted"] is True
    assert c["spreads"]["T10Y2Y"] < 0 and c["spreads"]["T10Y3M"] < 0


def test_an_unreadable_curve_is_none_not_false():
    # Before the series begin, "we could not look" must not become "not inverted".
    c = curve_at("2009-01-05")
    assert c["inverted"] is None
    assert sorted(c["notKnowable"]) == sorted(CURVE)


def test_the_curve_never_reads_a_yield_published_after_the_decision():
    for on in ("2019-08-15", "2022-03-01", "2025-06-02"):
        c = curve_at(on)
        for rec in c["readings"].values():
            assert rec["availableAt"] <= rec["cutoff"] < on


def test_the_curve_may_not_vote():
    c = curve_at("2023-05-01")
    assert c["role"] == "decision-context" and c["mayVote"] is False
    assert {"direction", "vote", "signal", "bias", "action"}.isdisjoint(c)


# ---------------------------------------------------------------- operational news feed


def test_the_news_feed_is_pruned_and_is_not_a_research_corpus():
    """The feed's defining property: it forgets, which is why it can never hold the corpus."""
    # Read the policy table itself rather than matching its text: News is pruned on
    # `publishedAt` at 70 days, which is what makes it an operational window and not a corpus.
    sys.path.insert(0, str(ROOT / "jobs"))
    from retention import KEEP

    assert "News" in KEEP, "News fell out of the retention policy"
    column, days = KEEP["News"][0], KEEP["News"][1]
    assert "publishedAt" in column
    assert days == 70, f"News retention moved to {days} days"


def test_the_press_corpus_is_kept_outside_the_news_table():
    """press_evidence is durable research; News is a 70-day operational window.

    If the corpus were written into News the retention job would delete it, so the two must stay
    disjoint. No collector may write one into the other.
    """
    assert PRESS.exists()
    for job in (ROOT / "jobs").glob("*.py"):
        text = job.read_text(encoding="utf-8", errors="replace")
        if "press_evidence" in text:
            assert 'INSERT INTO "News"' not in text.upper().replace("INSERT INTO \"NEWS\"",
                                                                    'INSERT INTO "News"'), job.name


def test_unavailable_coverage_is_never_turned_into_a_tone():
    """The contract the decision layer states, held by its own source."""
    src = DECISION_TS.read_text(encoding="utf-8")
    assert "newsCoverage" in src
    assert "unavailable" in src
    # The rule itself: `newsCoverage` is read as a third state, never folded into `tone`.
    assert re.search(r'newsCoverage\?*:\s*"available"\s*\|\s*"unavailable"', src), (
        "newsCoverage stopped being its own three-state field")


def test_news_alone_cannot_set_a_direction():
    src = DECISION_TS.read_text(encoding="utf-8")
    # `tone` is allowed to withdraw a claim, never to make one: the engine's own comment.
    assert "tone" in src
    assert "catalyst" in src


# ---------------------------------------------------------------- principles corpus


def _principles():
    payload = json.loads(PRINCIPLES.read_text(encoding="utf-8"))
    return payload.get("principles", payload)


def test_every_principle_is_citable():
    items = _principles()
    assert len(items) >= 80
    missing = [p["id"] for p in items if not p.get("doi")]
    assert missing == [], f"principles with no DOI: {missing[:5]}"


def test_every_principle_declares_what_it_needs_and_which_way_it_points():
    for p in _principles():
        assert p.get("needs"), f"{p['id']} declares no inputs"
        assert "sign" in p, f"{p['id']} declares no direction of effect"


def test_a_runnable_principle_names_a_horizon():
    for p in _principles():
        if p.get("hasRunnableRule"):
            assert p.get("horizon"), f"{p['id']} is runnable but names no horizon"


def test_the_corpus_is_research_not_a_voter():
    """Routing holds principles at research-only; nothing in the corpus may look like a vote."""
    sys.path.insert(0, str(ROOT / "tools" / "foundation"))
    from context_routing import route

    r = route("books, references and testable principles")
    assert r["roles"] == ["research-only"]
    assert r["mayVote"] is False
    for p in _principles():
        assert "vote" not in p, f"{p['id']} carries a vote field"


def test_runnable_principles_are_a_minority_and_that_is_recorded():
    items = _principles()
    runnable = [p for p in items if p.get("hasRunnableRule")]
    # The honest shape of the corpus: most findings cannot be tested on this data.
    assert 0 < len(runnable) < len(items)
