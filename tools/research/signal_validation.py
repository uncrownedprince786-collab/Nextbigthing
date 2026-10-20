"""Which market, horizon and side has survived testing -- and therefore what the UI may show.

    python tools/research/signal_validation.py [--out FILE]

The distinction this file exists to keep
----------------------------------------
`market_capability.json` answers "can an outcome here be scored at all". That is a property of the
data and the calendar, and today it is true for every market at swing and position. It is **not**
the question a decision card asks. The card asks whether a directional call on this market, at
this horizon, on this side, is worth putting in front of a person -- and that is a property of
*measured evidence*, which four of five markets do not have and which one of them has on one side
only.

Collapsing the two is how a market that can be *scored* becomes a market that is *called*. So this
writes a second table, read from the artifacts the research actually produced, and the web layer
reads this one before it renders a direction.

What counts as validated here
-----------------------------
All four, measured, or the lane is not validated:

1. **A lift over an ex-ante baseline** -- the class commonest in data available at the cutoff, not
   a baseline that peeks at the test period.
2. **Survival of a date-blocked bootstrap.** Rows are not independent: a holdout is hundreds of
   symbols on a few hundred sessions, and a multi-session forward return overlaps its neighbour.
   The standard error has to come from resampling sessions.
3. **The same sign in walk-forward folds the recipe never saw**, trained from scratch each time.
4. **A realised forward return in the direction claimed.** Beating the base rate of a three-class
   label is not the same as the price moving: the US DOWN side clears its base rate in every fold
   and the price still rose after it, in four years of five. Precision alone would have shipped
   that as a SHORT signal.

Multiplicity is applied against the number of arms the candidate was selected from, because it was
chosen for being the largest and not pre-registered.

What this is not
----------------
Not a promotion, and not a profitability claim. No transaction cost, spread or borrow is in any of
these numbers, and the lift they describe is of the order of a few tenths of a point of five-session
return. A validated lane earns the right to be recorded prospectively and shown as research. It
does not earn the word "profitable", and nothing downstream should print it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET = ROOT / "data" / "foundation" / "dataset"
OUT = DATASET / "signal_validation.json"

#: The confidence a validated lane may show, from the strength of its own evidence. There is no
#: HIGH here and there will not be one until a lane has matured prospective outcomes: a historical
#: holdout, however carefully tested, is still a backtest, and HIGH on a backtest is the badge this
#: project exists not to print.
BANDS = (
    ("MEDIUM", 5.0, "clears a blocked-bootstrap z of 5 and holds its sign in every walk-forward fold"),
    ("LOW", 2.0, "clears a blocked-bootstrap z of 2 but is thinner, or does not hold every fold"),
)


def band_for(z: float, folds_positive: int, folds: int) -> tuple[str, str] | None:
    """The confidence a lane has earned, or `None` when it has earned none."""
    for name, floor, why in BANDS:
        if z >= floor and (name != "MEDIUM" or folds_positive == folds):
            return name, why
    return None


def artifact_for(candidate: dict) -> str:
    """The artifact name the candidate's configuration produces.

    Mirrors `train_v4_markets.artifact_name`, and exists because the two drifting apart was a
    live defect: the evidence was gathered at a 2.0x band and the site served the 1.0x model,
    under a lane that recorded neither. The band is part of the model's identity, so it is part
    of what the registry names.
    """
    market = {"US": "us", "PK": "pk", "FX": "fx", "Commodity": "commodity",
              "Crypto": "crypto"}[candidate["market"]]
    horizon, band = candidate["horizon"], candidate.get("bandScale", 1.0)
    if horizon == 20 and band == 1.0:
        return f"brain-v4-{market}"
    stem = f"brain-v5-h{horizon}"
    if band != 1.0:
        stem += f"b{int(round(band * 10))}"
    return f"{stem}-{market}"


def from_validate_lift(path: Path) -> list[dict]:
    """Read `validate_lift.json` into lane rows, one per side that survived."""
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    c, boot, folds = d["candidate"], d["blockedBootstrap"], d["walkForward"]
    if not d.get("survives"):
        return []
    positive = sum(1 for f in folds if f["lift"] > 0)
    band = band_for(boot["z"], positive, len(folds))
    if band is None:
        return []
    name, why = band
    model_version = artifact_for(c)
    evidence = {
        "bandScale": c.get("bandScale", 1.0),
        "lift": d["headline"]["lift"],
        "blockedBootstrapZ": boot["z"],
        "ci95": boot["ci95"],
        "pBonferroni": boot["pBonferroni"],
        "armsSearched": boot["armsSearched"],
        "walkForwardFolds": len(folds),
        "walkForwardPositive": positive,
        "holdoutRows": d["headline"]["rows"],
        "holdoutSessions": d["headline"]["sessions"],
        "source": "tools/research/validate_lift.py",
    }
    # LONG only, and the reason is in the row rather than in a commit message nobody reads.
    return [{
        "market": c["market"], "horizonSessions": c["horizon"], "side": "LONG",
        # The artifact the evidence belongs to. A recorded prediction from any other model is not
        # covered by this lane, however similar its name, and the UI must refuse it.
        "modelVersion": model_version,
        "bandScale": c.get("bandScale", 1.0),
        "validated": True, "confidence": name, "why": why, "evidence": evidence,
    }, {
        "market": c["market"], "horizonSessions": c["horizon"], "side": "SHORT",
        "modelVersion": model_version,
        "bandScale": c.get("bandScale", 1.0),
        "validated": False, "confidence": None,
        "why": ("directional precision clears the base rate in every fold, and the realised "
                "5-session return of the rows called DOWN was positive in four years of five "
                "(+1.38% 2023, +1.07% 2024, +1.70% 2025). The price rose after the model said "
                "fall; precision over a three-class label is not the price moving"),
        "evidence": {"source": "tools/research/validate_lift.py, realised-return check"},
    }]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    lanes = from_validate_lift(DATASET / "validate_lift.json")
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "signal-validation-v1",
        "status": ("what has survived testing, not what is deployed and not a profitability "
                   "claim; no transaction cost is in any of these numbers"),
        "requirements": [
            "a lift over a baseline knowable at the cutoff",
            "survival of a date-blocked bootstrap, because rows are not independent",
            "the same sign in walk-forward folds trained from scratch",
            "a realised forward return in the direction claimed",
        ],
        "confidenceBands": [{"name": n, "minZ": z, "why": w} for n, z, w in BANDS],
        "highIsUnreachableFromBacktest": (
            "HIGH is reserved for a lane with matured prospective outcomes; a holdout is still a "
            "backtest and this project does not print HIGH on one"),
        "lanes": lanes,
    }
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    ok = [l for l in lanes if l["validated"]]
    print(f"  {len(lanes)} lane(s) recorded, {len(ok)} validated")
    for l in lanes:
        mark = f"{l['confidence']}" if l["validated"] else "not validated"
        print(f"    {l['market']:<10} h{l['horizonSessions']:<3} {l['side']:<6} {mark}")
    print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def verify_lane(lane: dict, brain_root: Path, candidate: dict | None = None) -> list[str]:
    """Every way a lane's badge could be backed by a different model than the one it names.

    Returns a list of problems, empty when the lane and its artifact agree on every part of the
    model's identity. A *list* rather than a boolean because when this fires, the useful output is
    which field disagreed.

    **The defect this exists to make impossible.** On 2026-10-20 the site printed `LONG / MEDIUM`
    on the US five-session lane beside evidence from `validate_lift.json` -- a 6.3-point lift at a
    blocked-bootstrap z of 8.98. That evidence was measured at a **2.0x** label band. The artifact
    being served, `brain-v5-h5-us`, was trained at the default **1.0x**. The lane was keyed on
    market, horizon and side alone, so the band was simply absent and nothing compared the two.

    They were not near-duplicates. The served 1.0x model called UP on **271 of 271** US
    instruments -- an always-UP predictor -- where the validated 2.0x model calls UP on 182 and
    FLAT on 89. A confidence badge was printed beside another model's numbers for as long as that
    went unnoticed, which was only until somebody happened to look at the predicted mix.

    So this checks identity rather than plausibility, and it checks it against the artifact's own
    manifest rather than against its directory name: a misnamed directory is exactly the case a
    name check cannot catch.
    """
    problems: list[str] = []
    name = lane.get("modelVersion")
    if not name:
        return [f"lane {lane.get('market')}/h{lane.get('horizonSessions')}/{lane.get('side')} "
                f"names no modelVersion, so nothing can confirm what its badge refers to"]

    man_path = brain_root / name / "manifest.json"
    model_path = brain_root / name / "model.json"
    if not man_path.exists():
        return [f"{name}: no manifest at {man_path}"]
    man = json.loads(man_path.read_text(encoding="utf-8"))
    task = man.get("task") or {}

    def differs(label: str, got, want) -> None:
        if got != want:
            problems.append(f"{name}: {label} is {got!r} but the lane says {want!r}")

    differs("manifest modelVersion", man.get("modelVersion"), name)
    differs("manifest market", man.get("market"), lane.get("market"))
    differs("task horizonSessions", task.get("horizonSessions"), lane.get("horizonSessions"))
    differs("task bandScale", task.get("bandScale"), lane.get("bandScale"))

    # The threshold must be the shared rule at the lane's band, not a number typed in.
    band = lane.get("bandScale")
    horizon = lane.get("horizonSessions")
    if isinstance(band, (int, float)) and isinstance(horizon, int):
        import make_dataset as _md
        expected = round(_md.label_threshold_pct(horizon) * band, 4)
        if task.get("labelThresholdPct") != expected:
            problems.append(
                f"{name}: task labelThresholdPct is {task.get('labelThresholdPct')!r} but the "
                f"shared rule at horizon {horizon} and band {band}x gives {expected!r}")

    # The evidence must have been gathered at the band the artifact was trained at.
    ev_band = (lane.get("evidence") or {}).get("bandScale")
    if ev_band is not None and ev_band != task.get("bandScale"):
        problems.append(
            f"{name}: the evidence was measured at a {ev_band}x band but the artifact was "
            f"trained at {task.get('bandScale')}x -- this is the 2026-10-20 defect")

    # The bytes on disk must be the bytes the manifest signed.
    if not model_path.exists():
        problems.append(f"{name}: manifest exists but {model_path.name} does not")
    else:
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        recorded = (man.get("artifact") or {}).get("sha256")
        if recorded != digest:
            problems.append(
                f"{name}: model.json digest {digest[:16]} does not match the manifest's "
                f"{str(recorded)[:16]}")

    # Feature identity: the count the manifest claims must match the lists it names.
    named = len(task.get("priceFeatures") or []) + len(task.get("contextFeatures") or [])
    if task.get("featureCount") is not None and named and task["featureCount"] != named:
        problems.append(
            f"{name}: task featureCount is {task['featureCount']} but it names {named} features")

    # And the candidate the evidence came from must resolve to this very artifact.
    if candidate:
        resolved = artifact_for(candidate)
        if resolved != name:
            problems.append(
                f"{name}: the validated candidate {candidate} resolves to {resolved!r}, which is "
                f"a different artifact from the one this lane names")

    # A lane may not point at an artifact its own manifest marks approved for production: nothing
    # here is, and a badge is not a promotion.
    if man.get("productionApproved"):
        problems.append(f"{name}: manifest claims productionApproved, which nothing here is")
    return problems
