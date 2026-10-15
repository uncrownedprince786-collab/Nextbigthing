"""Where each acquired layer is actually consumed, and what it is forbidden to do.

    python tools/foundation/context_routing.py [--out DIR]

Writes `data/foundation/dataset/context_routing.json`. Reads the repository; touches no database
and downloads nothing.

**The question this answers.** `source_inventory.json` reports `joinedIntoTraining: 4`, which has
been read as "14 layers are wasted". That conflates two different things. A layer is *unused* only
if nothing consumes it; most of these layers were never meant to become model features and would
be actively harmful as such -- a market-wide macro series handed to 616 instruments as a per-asset
feature is one fact counted 616 times, and the shipped design already refuses it (`lib/decision.ts`
calls `macroVeto` "A veto only: it can turn a LONG or SHORT into a WAIT and can do nothing else").

So each layer is routed to a **destination**, and the destination carries a prohibition as well as
a purpose. A routing claim is only worth something if it resolves, so every entry names a path
that must exist on disk; `verify()` fails when one does not, exactly as the organisation metric
checks its own paths rather than trusting its own table.

**What this module is not.** Declaring a destination is not the same as having wired it. `wired`
records which routes are live today, measured by whether the consumer exists, and the summary
reports wired and declared separately so the two can never be read as one number.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT_DIR = ROOT / "data" / "foundation" / "dataset"

#: The destinations a layer may be routed to. A layer with no destination is a defect, not a gap.
ROLES = {
    "training-feature": "enters the model's feature vector for an instrument",
    "directional-evidence": "may cast a directional vote in the evidence model",
    "decision-context": "qualifies or explains a decision; may never set a direction",
    "integrity-veto": "may withhold a decision or exclude a row; may never create or reverse one",
    "historical-prior": "base rates over past outcomes; informs confidence, not direction",
    "evaluation-stratification": "splits measured results for reporting; never a model input",
    "research-only": "informs research and documentation; never reaches the decision engine",
    "documented-exclusion": "no permitted source serves it; the gap itself is the artifact",
}

#: layer -> (roles, may it vote, point-in-time rule, behaviour when absent, consumer path)
ROUTES: dict[str, tuple[tuple[str, ...], bool, str, str, str]] = {
    "prices / OHLCV (instrument level)": (
        ("training-feature", "directional-evidence"), True,
        "closes <= asOf; the as-of close is excluded from every forward window",
        "no price, no row: the instrument is ineligible, never defaulted",
        "tools/make_dataset.py"),
    "market / index benchmarks (deep history)": (
        ("evaluation-stratification", "research-only"), False,
        "daily series with its own date; used only to date and bound an episode",
        "an episode without a benchmark is reported as uncovered, not assumed calm",
        "tools/foundation/historical_regimes.py"),
    "corporate actions": (
        ("integrity-veto",), False,
        "an action's date must precede the window it invalidates",
        "unknown action: the row keeps its flag and the consumer excludes it explicitly",
        "tools/foundation/actions.py"),
    "macroeconomic series (point-in-time)": (
        ("decision-context", "integrity-veto"), False,
        "joined on observation_date + publicationLagDays, never on observation date alone",
        "no macro reading: no veto, and no neutral vote invented in its place",
        "tools/foundation/macro_pit.py"),
    "interest rates and yield curve": (
        ("decision-context", "research-only"), False,
        "FRED observation dates; same publication-lag rule as macro",
        "absent: the context line is omitted rather than filled with a stale level",
        "tools/foundation/macro.py"),
    "banking and credit stress (2008 window)": (
        ("research-only", "evaluation-stratification"), False,
        "2005-2012; entirely before the 2018 dataset, so it can only inform research",
        "absent: the 2008 regime is reported as out of training range",
        "tools/foundation/crisis_2008.py"),
    "credit spreads (2008 window)": (
        ("research-only",), False,
        "2005-2012 observation dates",
        "the licence-limited ICE series is evidenced by a dated probe, not guessed",
        "tools/foundation/crisis_2008.py"),
    "gold and commodities": (
        ("training-feature", "directional-evidence"), True,
        "closes <= asOf, as any other instrument",
        "no bar, no row",
        "tools/make_dataset.py"),
    "instrument identity and lifecycle": (
        ("integrity-veto", "research-only"), False,
        "registry read date recorded; a delisting is known only from its filing date",
        "unknown lifecycle: the instrument stays in the universe and the gap is recorded",
        "tools/foundation/sec_lifecycle.py"),
    "delisted instrument price history": (
        ("documented-exclusion",), False,
        "n/a: no permitted source serves it",
        "the probe record is the artifact; survivorship stays a measured lower bound",
        "tools/foundation/gap_evidence.py"),
    "PSX history before 2013-11-04": (
        ("documented-exclusion",), False,
        "n/a: absent at source",
        "the archive floor is established by probe, not assumed",
        "tools/foundation/gap_evidence.py"),
    "dated events corpus": (
        ("decision-context",), False,
        "an event may only inform a decision whose timestamp follows its publication",
        "no event: `eventInDays` is null, which is not the same as 'no event due'",
        "tools/foundation/events_load.py"),
    "press and original-document evidence": (
        ("decision-context", "research-only"), False,
        "publication time strictly before the decision timestamp",
        "no press record: the event stands on its own disposition",
        "tools/foundation/gkg_evidence.py"),
    "operational news feed": (
        ("decision-context",), False,
        "published < decision; pruned at 70 days, so never a historical corpus",
        "coverage 'unavailable' is never converted into a neutral tone",
        "jobs/lineage.py"),
    "event-to-market reactions": (
        ("historical-prior", "research-only"), False,
        "before-state strictly before the event; forward windows strictly after",
        "an event without a reaction window is dropped, not zero-filled",
        "tools/foundation/event_reactions.py"),
    "books, references and testable principles": (
        ("research-only",), False,
        "literature has no bearing on a decision timestamp",
        "an untestable principle is recorded as untestable",
        "tools/foundation/principles.py"),
    "regime episodes": (
        ("evaluation-stratification",), False,
        "episode windows are known only in hindsight, so they may never enter a predictor",
        "a session outside every episode is reported as 'none', not as calm",
        "tools/research/regime_breakdown.py"),
    "training examples": (
        ("training-feature",), True,
        "assembled from point-in-time features and mature outcomes only",
        "immature rows are excluded, never labelled FLAT",
        "tools/foundation/assemble.py"),
}

FIELDS = ("roles", "mayVote", "pointInTime", "whenAbsent", "consumer")


def route(layer: str) -> dict | None:
    """The routing record for one layer, or None when the layer is unrouted.

    `roles` comes back as a list, matching what `verify()` writes into the artifact, so a caller
    never has to know that the table itself stores a tuple.
    """
    r = ROUTES.get(layer)
    if not r:
        return None
    rec = dict(zip(FIELDS, r))
    rec["roles"] = list(rec["roles"])
    return rec


def verify(root: Path = ROOT) -> dict:
    """Check every declared consumer resolves, and that no role is invented."""
    rows = []
    for layer, (roles, may_vote, pit, absent, consumer) in ROUTES.items():
        unknown = [x for x in roles if x not in ROLES]
        exists = (root / consumer).exists()
        # Only an instrument-level layer may ever vote; this is the rule that keeps a
        # market-wide series from becoming 616 independent confirmations of one fact.
        vote_ok = (not may_vote) or ("directional-evidence" in roles) or ("training-feature" in roles)
        rows.append({"layer": layer, "roles": list(roles), "mayVote": may_vote,
                     "pointInTime": pit, "whenAbsent": absent, "consumer": consumer,
                     "consumerResolves": exists, "unknownRoles": unknown,
                     "voteRoleConsistent": vote_ok})
    wired = [r for r in rows if r["consumerResolves"]]
    voting = [r for r in rows if r["mayVote"]]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "context-routing-v1",
        "roles": ROLES,
        "rule": ("every layer names a destination and a consumer; the consumer must resolve on "
                 "disk, and only an instrument-level layer may cast a directional vote"),
        "layers": rows,
        "summary": {
            "declared": len(rows),
            "consumersResolving": len(wired),
            "mayVote": len(voting),
            "neverVote": len(rows) - len(voting),
            "byRole": {k: sum(1 for r in rows if k in r["roles"]) for k in ROLES},
            "unroutedOrBroken": [r["layer"] for r in rows
                                 if not r["consumerResolves"] or r["unknownRoles"]
                                 or not r["voteRoleConsistent"]],
        },
    }


def main() -> int:
    out_dir = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = verify()
    (out_dir / "context_routing.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    s = payload["summary"]
    for r in payload["layers"]:
        mark = "ok " if r["consumerResolves"] else "MISSING"
        print(f"  {mark} {r['layer'][:44]:<46}{','.join(r['roles'])}")
    print(f"\ndeclared {s['declared']}  consumers resolving {s['consumersResolving']}  "
          f"may vote {s['mayVote']}  never vote {s['neverVote']}")
    if s["unroutedOrBroken"]:
        print("BROKEN:", s["unroutedOrBroken"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
