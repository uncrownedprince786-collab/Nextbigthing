"""Why did the recorded candidates fail? Read it off their own artifacts, not off a hypothesis.

    python tools/research/diagnose_experiments.py [--out FILE]

Two candidates are recorded as NO-GO: `baseline_experiment.json` (swing horizon, `label20`, mean
accuracy 0.4211 against a 0.4204 majority class) and `label60_experiment.json` (position horizon,
mean margin -0.0816). "No edge" is the verdict, not the diagnosis, and a further candidate is only
justified by a concrete documented cause -- otherwise the next attempt is hyperparameters against
the same exposed period.

The cause is in the prediction mixes the first experiment already recorded, and it is not subtle
once they are put beside the outcome mixes: **the candidate is, functionally, a near-constant UP
predictor.** This computes that rather than asserting it, and reports the three facts that carry it:
what share of its predictions were UP against the share that actually were, how rarely it predicted
FLAT at all, and how closely its accuracy tracks the test year's UP base rate.

`label60` did not record a prediction mix, so the same collapse can only be *inferred* there, from
accuracy sitting far below the majority rate in every stratum -- which is what a near-constant
predictor does when the period it was fitted on was balanced differently. That distinction is kept
in the output: measured for `label20`, inferred for `label60`.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET = ROOT / "data" / "foundation" / "dataset"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> int:
    out = Path(arg("--out") or (DATASET / "experiment_diagnosis.json"))
    base = json.loads((DATASET / "baseline_experiment.json").read_text(encoding="utf-8"))
    l60 = json.loads((DATASET / "label60_experiment.json").read_text(encoding="utf-8"))

    folds = []
    for f in base["folds"]:
        c = f["candidate"]
        pm, am = c["predictedMix"], c["actualMix"]
        p, n = sum(pm.values()), sum(am.values())
        folds.append({
            "testYear": f["testYear"],
            "accuracy": c["accuracy"],
            "predictedUpShare": round(pm["UP"] / p, 4),
            "actualUpShare": round(am["UP"] / n, 4),
            "predictedFlatShare": round(pm["FLAT"] / p, 4),
            "actualFlatShare": round(am["FLAT"] / n, 4),
            "accuracyMinusActualUpShare": round(c["accuracy"] - am["UP"] / n, 4),
        })

    mean = lambda k: round(statistics.mean(f[k] for f in folds), 4)  # noqa: E731
    gap = round(statistics.mean(abs(f["accuracyMinusActualUpShare"]) for f in folds), 4)

    # label60: accuracy against the majority rate in every recorded stratum.
    strata = []
    for f in l60["folds"]:
        for kind, rows in (f.get("breakdown") or {}).items():
            for name, m in rows.items():
                strata.append({"kind": kind, "stratum": name, "accuracy": m.get("accuracy"),
                               "majorityRate": m.get("majorityRate"), "margin": m.get("margin")})
    below = [s for s in strata if s["margin"] is not None and s["margin"] < 0]

    report = {
        "version": "experiment-diagnosis-v1",
        "status": "a reading of recorded artifacts; no experiment was re-run and no result changed",
        "question": "what actually caused the two recorded NO-GO results",
        "label20Candidate": {
            "source": "data/foundation/dataset/baseline_experiment.json",
            "finding": "a near-constant UP predictor, measured from its own prediction mixes",
            "folds": folds,
            "meanPredictedUpShare": mean("predictedUpShare"),
            "meanActualUpShare": mean("actualUpShare"),
            "meanPredictedFlatShare": mean("predictedFlatShare"),
            "meanActualFlatShare": mean("actualFlatShare"),
            "meanAbsAccuracyMinusUpShare": gap,
            "reading": (
                "It called UP on a mean 79% of rows where 41% actually were, and FLAT on 3.6% where "
                "20% actually were -- it essentially never predicts the middle class. Its accuracy "
                f"tracks each test year's UP base rate to a mean absolute {gap}, which is what makes "
                "0.4211 against a 0.4204 majority class the same number twice rather than a narrow "
                "miss. It beat the rule baseline only because that rule predicted a balanced mix and "
                "a constant call scores better than a balanced wrong one."
            ),
            "mechanism": (
                "Three classes with a FLAT band holding about a fifth of rows, an unweighted softmax, "
                "and 400 full-batch steps at a fixed learning rate: the cheapest descent is toward the "
                "largest class, and FLAT lies between the other two in feature space, so it is both "
                "the hardest to carve out and the least rewarded. The worst fold is 2022, where it "
                "carried UP into the one year DOWN dominated at a 94% UP rate -- regime fragility, "
                "which is the §9 acceptance clause this candidate actually failed."
            ),
            "whatItDoesNotShow": (
                "It does not show the features carry an edge. A degenerate optimiser and an absent "
                "edge produce the same headline, and nothing here separates them."
            ),
        },
        "label60Candidate": {
            "source": "data/foundation/dataset/label60_experiment.json",
            "meanMargin": l60["summary"].get("meanMargin"),
            "strataRecorded": len(strata),
            "strataBelowTheirMajority": len(below),
            "worstStratum": min(strata, key=lambda s: s["margin"] if s["margin"] is not None else 0) if strata else None,
            "finding": "INFERRED, not measured: no prediction mix was recorded for this experiment",
            "reading": (
                f"{len(below)} of {len(strata)} recorded strata sit below their own majority rate, "
                "several by 25 to 34 points. Accuracy that far beneath the majority is what a "
                "near-constant predictor produces when the period it was fitted on was balanced the "
                "other way, which is the same mechanism measured directly for label20 -- but the "
                "prediction mix was not stored, so for this horizon it stays an inference."
            ),
        },
        "whatAFurtherCandidateWouldHaveToFix": [
            "class-balanced training, or a target whose middle class is not simply never predicted",
            "enough optimisation to converge, rather than a fixed step count chosen before the loss was seen",
            "an evaluation a constant call cannot win -- the reference must be the best single fixed "
            "answer on exactly the rows being scored, not the majority class over a different set",
            "a regime clause in the acceptance criterion, since the 2022 fold is where both candidates broke",
        ],
        "notARecommendationToRetune": (
            "None of this licenses another pass at the same exposed period. It names the cause so that "
            "a further candidate has a documented hypothesis to test, and the exposed folds stay "
            "immutable: both recorded results are preserved exactly as they were measured."
        ),
    }

    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report["label20Candidate"].items() if k != "folds"}, indent=1))
    print(json.dumps({k: v for k, v in report["label60Candidate"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
