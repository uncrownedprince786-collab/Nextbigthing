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

Conviction
----------
`crypto_conviction.json`, when it exists, carries each lane's margin floor -- the point below
which the model's own probability says it is near-indifferent and the brain should say so rather
than name a direction. It is merged onto the lane here rather than read separately by the web
layer, for the same reason the weights are filtered by the verdict: the permission to speak, the
threshold for speaking and the evidence behind both are one decision and belong in one file.

A floor is attached **only** to a lane that is already servable and whose gated form passed its
own gates on the test fold. Conviction can quiet a lane that passed; it can never promote one that
did not, and a lane with no entry keeps answering on every bar exactly as before.
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

CONVICTION = OUT / "crypto_conviction.json"


def conviction_table() -> dict[tuple[str, str], dict]:
    """`(family, horizon) -> the lane's measured conviction block`, or empty when none was run.

    Absence is a normal state, not an error: the floors are produced by a separate measurement and
    a repository without them serves every lane ungated, which is what it did before they existed.
    """
    if not CONVICTION.exists():
        return {}
    doc = json.loads(CONVICTION.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], dict] = {}
    for l in doc.get("lanes", []):
        if not l.get("serveGated"):
            continue
        g = l["gatedOnTest"]
        out[(l["family"], l["horizon"])] = {
            "floor": l["chosenFloor"],
            "chosenOn": "the validation fold, before the test fold was read",
            "rule": doc["rule"],
            "called": {
                "accuracy": g["accuracy"],
                "coverage": g["coverage"],
                "rows": g["rows"],
                "majorityHere": g["majorityHere"],
                "marginOverMajority": g["marginOverMajority"],
                "bootstrapCi95": g["blockedBootstrap"]["ci95"],
                "walkForwardAbove": g["walkForward"]["blocksAboveMajority"],
                "walkForwardBlocks": g["walkForward"]["blocksScored"],
                "upShareCalled": g["upShareCalled"],
            },
            "ungatedAccuracy": l["ungatedOnTest"]["accuracy"],
            "testCurve": l["testCurve"],
            "measuredAt": doc["generatedAt"],
        }
    return out


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
    convictions = conviction_table()
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
            # A refused lane never carries a floor: there is nothing to quiet.
            "conviction": convictions.get((family, key)) if servable else None,
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
        "conviction":
            "a lane with a floor answers only when the model's probability is at least that far "
            "from even, and says it sees nothing otherwise. The floor is chosen on the validation "
            "fold and the gated lane is then measured once on the test fold, against the called "
            "rows' own majority. Coverage travels with every accuracy here: 'right more often on "
            "fewer bars' is only a result when both numbers are shown.",
        "families": sorted(families),
        "lanes": lanes,
        "servableLanes": len(passing),
        "gatedLanes": sum(1 for l in lanes if l.get("conviction")),
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
        c = l.get("conviction")
        gated = (f"  | floor {c['floor']:.3f}: {c['called']['accuracy']:.4f} "
                 f"on {c['called']['coverage']:.1%}" if c else "")
        print(f"  {l['family']:>6} {l['horizon']:>3}  acc {e['accuracy']:.4f} "
              f"maj {e['testMajority']:.4f} margin {e['marginOverMajority']:+.4f} "
              f"ci [{e['bootstrapCi95'][0]:+.4f},{e['bootstrapCi95'][1]:+.4f}] "
              f"wf {e['walkForwardAbove']}/{e['walkForwardBlocks']}  {mark}{gated}")
    print(f"wrote crypto_models.json: {len(models)} models, {size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
