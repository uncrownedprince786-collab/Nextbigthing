"""What the site is allowed to say about each coin and horizon, and the model it may say it with.

    python tools/research/crypto_lanes.py

Reads every `brain-c1-*` manifest and writes two artifacts:

  * `data/foundation/dataset/crypto_lanes.json` -- the permission table. One row per
    (family, horizon) with the verdict, the measured numbers behind it, and, where a lane is
    refused, which pre-registered gate it failed.
  * `data/foundation/dataset/crypto_models.json` -- the weights, **for the passing lanes only**.

Why the models are filtered by the verdict
------------------------------------------
Because the alternative has already failed here once. `brain-v5-h5-us` was trained at a 1.0x band
while the evidence that licensed the badge was gathered at 2.0x, and the site printed
`LONG · MEDIUM` beside numbers from a different model -- not a cosmetic error: the served model
called UP on 271 of 271 instruments where the validated one called UP on about 47%. Shipping only
the artifacts that passed makes the serving bundle and the permission table the same decision,
written once, so a lane cannot be servable without its evidence or evidenced without its weights.

Confidence
----------
Never HIGH. Everything here is measured on a historical holdout, which is a backtest however
carefully it is split, and no forecast in it was made before its own data existed. MEDIUM needs
the lane to pass every gate, hold a lower bootstrap bound of at least one point over the majority,
and be above majority in all five walk-forward blocks. Everything else that passes is LOW.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from crypto_horizons import HORIZONS, ORDER  # noqa: E402

BRAIN_ROOT = ROOT / "data" / "foundation" / "brain"
OUT = ROOT / "data" / "foundation" / "dataset"

#: A lane must clear this much of a lower bootstrap bound over the test majority, and be above
#: majority in every walk-forward block, before a badge may read MEDIUM rather than LOW.
MEDIUM_MIN_LOWER_BOUND = 0.01


def confidence_of(m: dict) -> str:
    ev = m["evaluation"]
    wf = ev["walkForward"]
    if not m.get("gatesMet"):
        return "NONE"
    strong = (
        ev["blockedBootstrap"]["ci95"][0] >= MEDIUM_MIN_LOWER_BOUND
        and wf["blocksScored"] > 0
        and wf["blocksAboveMajority"] == wf["blocksScored"]
    )
    return "MEDIUM" if strong else "LOW"


def why_refused(m: dict) -> str:
    failed = [k for k, v in (m.get("gates") or {}).items() if not v]
    if not failed:
        return "no gate failed"
    ev = m["evaluation"]
    words = {
        "aboveTestMajority":
            f"its accuracy of {ev['accuracy']:.4f} did not clear the test fold's own larger class "
            f"({ev['testMajority']:.4f}), so it read no better than naming one direction",
        "bothDirectionsPredicted":
            f"it called one direction on {max(ev['predictedUpShare'], ev['predictedDownShare']):.0%} "
            f"of the test fold, which is leaning on a class rather than reading direction",
        "bootstrapExcludesZero":
            f"a day-blocked bootstrap put its edge between "
            f"{ev['blockedBootstrap']['ci95'][0]:+.4f} and {ev['blockedBootstrap']['ci95'][1]:+.4f}, "
            f"an interval that spans zero",
        "walkForwardMajority":
            f"it beat its own block majority in only "
            f"{ev['walkForward']['blocksAboveMajority']} of {ev['walkForward']['blocksScored']} "
            f"chronological blocks",
    }
    return "; and ".join(words.get(f, f) for f in failed)


def main() -> int:
    lanes = []
    models: dict[str, dict] = {}
    families: set[str] = set()
    for d in sorted(BRAIN_ROOT.glob("brain-c1-*")):
        mf = d / "manifest.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text(encoding="utf-8"))
        name = m["modelVersion"]
        # brain-c1-<family>-<horizon>
        rest = name[len("brain-c1-"):]
        family, _, key = rest.rpartition("-")
        if key not in HORIZONS:
            continue
        families.add(family)
        ev = m["evaluation"]
        conf = confidence_of(m)
        servable = bool(m.get("gatesMet"))
        lane = {
            "family": family,
            "horizon": key,
            "horizonMinutes": HORIZONS[key]["minutes"],
            "interval": HORIZONS[key]["interval"],
            "modelVersion": name,
            "modelSha256": m["artifact"]["sha256"],
            "featureSchema": m["featureSchema"],
            "trainedOn": m["symbols"],
            "servable": servable,
            "confidence": conf,
            "why": None if servable else why_refused(m),
            "evidence": {
                "testRows": ev["rows"],
                "testFrom": m["split"]["testFrom"],
                "testTo": m["split"]["testTo"],
                "accuracy": ev["accuracy"],
                "testMajority": ev["testMajority"],
                "marginOverMajority": ev["marginOverMajority"],
                "bootstrapCi95": ev["blockedBootstrap"]["ci95"],
                "bootstrapZ": ev["blockedBootstrap"]["z"],
                "bootstrapBlocks": ev["blockedBootstrap"]["blocks"],
                "walkForwardAbove": ev["walkForward"]["blocksAboveMajority"],
                "walkForwardBlocks": ev["walkForward"]["blocksScored"],
                "predictedUpShare": ev["predictedUpShare"],
                "linearOnTheSameTestRows": m.get("linearOnTheSameTestRows"),
                "chosenModel": m.get("chosenModel"),
                "coverageCurve": ev["coverageCurve"],
            },
            "acceptanceTarget": m.get("acceptanceTarget"),
            "acceptanceTargetMet": m.get("acceptanceTargetMet"),
            "trainingRows": m["rows"]["train"],
            "generatedAt": m["generatedAt"],
        }
        lanes.append(lane)
        if servable:
            models[f"{family}:{key}"] = json.loads((d / "model.json").read_text(encoding="utf-8"))

    lanes.sort(key=lambda l: (l["family"], ORDER.index(l["horizon"])))
    passing = [l for l in lanes if l["servable"]]
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_lanes.py",
        "status": "what has survived testing on a historical holdout, not what has been proven "
                  "forward and not a profitability claim; no transaction cost, spread or funding "
                  "is in any number here",
        "highIsUnreachableFromBacktest":
            "a badge never reads HIGH: every number here comes from a holdout, which is still a "
            "backtest. HIGH is reserved for a lane whose prospective forecasts have matured and "
            "held, which none has yet.",
        "requirements": [
            "the task is binary: the sign of the forward return, with no FLAT class and no row "
            "converted into a direction",
            "accuracy strictly above the test fold's own larger class",
            "neither direction called on more than 80% of the test fold",
            "a day-blocked bootstrap interval for the edge that excludes zero",
            "above its own block majority in at least four of five chronological blocks",
            "the test fold is after the training and validation folds in time, with an embargo "
            "of the feature window plus the horizon between them",
        ],
        "families": sorted(families),
        "lanes": lanes,
        "servableLanes": len(passing),
        "totalLanes": len(lanes),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "crypto_lanes.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    (OUT / "crypto_models.json").write_text(json.dumps(models, separators=(",", ":")),
                                            encoding="utf-8")
    size = (OUT / "crypto_models.json").stat().st_size
    print(f"wrote crypto_lanes.json: {len(lanes)} lanes, {len(passing)} servable")
    for l in lanes:
        mark = f"{l['confidence']}" if l["servable"] else "refused"
        e = l["evidence"]
        print(f"  {l['family']:>6} {l['horizon']:>3}  acc {e['accuracy']:.4f} "
              f"maj {e['testMajority']:.4f} margin {e['marginOverMajority']:+.4f} "
              f"ci [{e['bootstrapCi95'][0]:+.4f},{e['bootstrapCi95'][1]:+.4f}] "
              f"wf {e['walkForwardAbove']}/{e['walkForwardBlocks']}  {mark}")
    print(f"wrote crypto_models.json: {len(models)} models, {size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
