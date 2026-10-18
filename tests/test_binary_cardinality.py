"""The binary model must have two output columns, and they must be named DOWN and UP.

    python -m unittest discover -s tests -p test_binary_cardinality.py -v

Stdlib unittest, no database and no network. It pins a defect that was found by reading the code
and confirmed against the artifacts on disk.

**The defect.** `fit_softmax` and `fit_weighted` took their output width from `len(CLASSES)`,
which is 3, while the binary experiments encode their target as {0,1}. A two-class target was
therefore fitted three-wide: labels occupied columns 0 and 1, the column `CLASSES` calls UP never
received a target row, and the three-way softmax trained a logit the model was never asked for.
Independently of that, `predictedMix` and `actualMix` in those runs indexed into `CLASSES`, so
binary index 1 -- the positive class -- was written out as `FLAT`, and `UP` was written as 0 on
every fold of `binary_context_experiment.json` and `eligible_set_experiment.json` while the real
UP rows sat under `FLAT`. Both are checked here against the preserved v1 artifacts, and the
corrected v2 artifacts are checked against them fold by fold: same rows, same actual counts,
correctly named.

**Why the three-class path is checked too.** The fix must not move the model every other
experiment and every shipped run depends on. `test_three_class_default_is_unchanged` refits the
old implementation verbatim and requires the new one to be bit-identical to it, so a change that
altered the shipped path fails here rather than in a benchmark nobody re-reads.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from baseline_experiment import CLASSES, fit_softmax, predict  # noqa: E402
from balanced_experiment import class_counts, fit_weighted  # noqa: E402
from binary_context_experiment import BINARY_CLASSES, N_BINARY  # noqa: E402
from signal_floor import fit_in_sample  # noqa: E402

DATASET = ROOT / "data" / "foundation" / "dataset"
V1_BINARY = DATASET / "binary_context_experiment.json"
V1_ELIGIBLE = DATASET / "eligible_set_experiment.json"
V1_FLOOR = DATASET / "signal_floor.json"
V2_BINARY = DATASET / "binary_context_experiment_v2.json"
V2_ELIGIBLE = DATASET / "eligible_set_experiment_v2.json"
V2_FLOOR = DATASET / "signal_floor_v2.json"


def _data(seed: int = 7, n: int = 40, d: int = 4):
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, size=(n, d))
    y3 = rng.integers(0, 3, size=n)
    yb = rng.integers(0, 2, size=n)
    return X, y3, yb


def _legacy_fit_softmax(Xtr, ytr, steps, lr, l2, seed):
    """`baseline_experiment.fit_softmax` exactly as it was before `classes` existed."""
    rng = np.random.default_rng(seed)
    n, d = Xtr.shape
    k = len(CLASSES)
    W = rng.normal(0, 0.01, size=(d + 1, k))
    Xb = np.hstack([Xtr, np.ones((n, 1))])
    Y = np.zeros((n, k))
    Y[np.arange(n), ytr] = 1.0
    for _ in range(steps):
        z = Xb @ W
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        p = e / e.sum(axis=1, keepdims=True)
        g = Xb.T @ (p - Y) / n + l2 * W
        W -= lr * g
    return W


def _legacy_fit_weighted(Xtr, ytr, weights, lr, l2, seed, tol, max_steps):
    """`balanced_experiment.fit_weighted` exactly as it was before `classes` existed."""
    rng = np.random.default_rng(seed)
    n, d = Xtr.shape
    k = len(CLASSES)
    W = rng.normal(0, 0.01, size=(d + 1, k))
    Xb = np.hstack([Xtr, np.ones((n, 1))])
    Y = np.zeros((n, k))
    Y[np.arange(n), ytr] = 1.0
    w = weights[ytr]
    w = w / w.mean()
    wcol = w[:, None]
    previous = np.inf
    steps = 0
    loss = np.inf
    for steps in range(1, max_steps + 1):
        z = Xb @ W
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        p = e / e.sum(axis=1, keepdims=True)
        loss = float(-(w * np.log((p * Y).sum(axis=1) + 1e-12)).sum() / w.sum()
                     + l2 * np.sum(W * W) / 2)
        g = Xb.T @ ((p - Y) * wcol) / w.sum() + l2 * W
        W -= lr * g
        if previous - loss < tol * max(1.0, abs(previous)):
            break
        previous = loss
    return W, steps, loss


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class OutputWidthFollowsTheTarget(unittest.TestCase):
    """The matrix is built from the target's classes, not from a module-level constant."""

    def test_binary_fit_is_two_wide(self):
        X, _, yb = _data()
        W = fit_softmax(X, yb, steps=5, classes=BINARY_CLASSES)
        self.assertEqual(W.shape, (X.shape[1] + 1, 2))
        Ww, _, _ = fit_weighted(X, yb, np.array([1.0, 1.0]), max_steps=5,
                                classes=BINARY_CLASSES)
        self.assertEqual(Ww.shape, (X.shape[1] + 1, 2))

    def test_three_class_default_stays_three_wide(self):
        X, y3, _ = _data()
        self.assertEqual(fit_softmax(X, y3, steps=5).shape, (X.shape[1] + 1, 3))
        Ww, _, _ = fit_weighted(X, y3, np.array([1.0, 1.0, 1.0]), max_steps=5)
        self.assertEqual(Ww.shape, (X.shape[1] + 1, 3))

    def test_three_class_default_is_unchanged(self):
        """The shipped path must be bit-identical to the implementation before `classes`."""
        X, y3, _ = _data(seed=11, n=60, d=6)
        for steps, lr, l2, seed in ((5, 0.5, 1e-4, 20261015), (25, 0.1, 0.0, 99)):
            self.assertTrue(np.array_equal(
                fit_softmax(X, y3, steps=steps, lr=lr, l2=l2, seed=seed),
                _legacy_fit_softmax(X, y3, steps=steps, lr=lr, l2=l2, seed=seed)))
        weights = np.array([1.0, 2.0, 0.5])
        got, got_steps, got_loss = fit_weighted(X, y3, weights, lr=0.5, l2=1e-4,
                                                seed=20261015, tol=1e-6, max_steps=40)
        want, want_steps, want_loss = _legacy_fit_weighted(X, y3, weights, lr=0.5, l2=1e-4,
                                                           seed=20261015, tol=1e-6,
                                                           max_steps=40)
        self.assertTrue(np.array_equal(got, want))
        self.assertEqual(got_steps, want_steps)
        self.assertEqual(got_loss, want_loss)
        self.assertTrue(np.array_equal(
            fit_softmax(X, y3, steps=9, classes=CLASSES),
            _legacy_fit_softmax(X, y3, steps=9, lr=0.5, l2=1e-4, seed=20261015)))

    def test_explicit_classes_matches_the_default(self):
        X, y3, _ = _data(seed=3)
        self.assertTrue(np.array_equal(
            fit_softmax(X, y3, steps=12, classes=CLASSES),
            fit_softmax(X, y3, steps=12)))

    def test_a_label_the_model_has_no_column_for_is_rejected(self):
        X, y3, _ = _data()
        with self.assertRaises(ValueError):
            fit_softmax(X, y3, steps=2, classes=BINARY_CLASSES)   # y3 holds a 2, there is no 3rd
        with self.assertRaises(ValueError):
            fit_softmax(X, np.full(len(y3), 2), steps=2, classes=BINARY_CLASSES)
        with self.assertRaises(ValueError):
            fit_weighted(X, y3, np.array([1.0, 1.0]), max_steps=2, classes=BINARY_CLASSES)
        with self.assertRaises(ValueError):
            fit_weighted(X, np.full(len(y3), -1), np.array([1.0, 1.0]), max_steps=2,
                         classes=BINARY_CLASSES)

    def test_predictions_from_a_two_wide_fit_cannot_reach_a_third_class(self):
        X, _, yb = _data(seed=5, n=80, d=5)
        W = fit_softmax(X, yb, steps=200, classes=BINARY_CLASSES)
        yp = predict(W, X)
        self.assertGreaterEqual(int(yp.min()), 0)
        self.assertLess(int(yp.max()), N_BINARY)
        self.assertTrue(set(np.unique(yp).tolist()) <= {0, 1})

    def test_the_fit_is_reproducible_and_seeded(self):
        X, y3, _ = _data(seed=13)
        a = fit_softmax(X, y3, steps=30)
        b = fit_softmax(X, y3, steps=30)
        c = fit_softmax(X, y3, steps=30, seed=20261016)
        self.assertTrue(np.array_equal(a, b))
        self.assertFalse(np.array_equal(a, c))


class ClassNamesCannotLieAboutABinaryTarget(unittest.TestCase):
    """Reporting binary index 1 as FLAT was the visible half of the defect."""

    def test_the_wrong_name_is_exactly_where_the_old_mapping_put_it(self):
        self.assertEqual(CLASSES[BINARY_CLASSES.index("UP")], "FLAT")
        self.assertNotEqual(CLASSES[1], "UP")
        self.assertEqual(BINARY_CLASSES[1], "UP")
        self.assertNotIn("FLAT", BINARY_CLASSES)

    def test_counts_are_named_by_the_model_not_by_the_three_class_label(self):
        values = np.array([0, 1, 1, 1, 0])
        counts = class_counts(values, BINARY_CLASSES)
        self.assertEqual(counts, {"DOWN": 2, "UP": 3})
        self.assertEqual(sum(counts.values()), len(values))
        self.assertNotIn("FLAT", counts)

    def test_a_count_cannot_be_written_under_a_name_the_target_does_not_have(self):
        with self.assertRaises(ValueError):
            class_counts(np.array([0, 1, 2]), BINARY_CLASSES)
        with self.assertRaises(ValueError):
            class_counts(np.array([-1, 0, 1]), BINARY_CLASSES)

    def test_the_cache_label_and_the_model_label_are_different_names_for_a_reason(self):
        """FLAT rows are dropped first; what is left is DOWN and UP, in that order."""
        _, y3, _ = _data(seed=17, n=300)
        up = CLASSES.index("UP")
        down = CLASSES.index("DOWN")
        flat = CLASSES.index("FLAT")
        kept = y3[y3 != flat]                        # exactly what every experiment does first
        yb = np.where(kept == up, 1, 0)
        counts = class_counts(yb, BINARY_CLASSES)
        self.assertEqual(counts["UP"], int((y3 == up).sum()))
        self.assertEqual(counts["DOWN"], int((y3 == down).sum()))
        self.assertEqual(sum(counts.values()), len(yb))
        self.assertEqual(len(yb), int((y3 != flat).sum()),
                         "the FLAT rows were not dropped before the target was built")
        self.assertEqual(counts["UP"] + counts["DOWN"], int((y3 != flat).sum()))

    def test_the_in_sample_helper_reports_two_classes_for_a_binary_target(self):
        X, y3, _ = _data(seed=19, n=120, d=3)
        keep = y3 != CLASSES.index("FLAT")
        yb = np.where(y3[keep] == CLASSES.index("UP"), 1, 0)
        cell = fit_in_sample(X[keep], yb, [0, 1, 2], BINARY_CLASSES)
        self.assertEqual(cell["outputDimension"], 2)
        self.assertEqual(cell["outputClasses"], ["DOWN", "UP"])
        self.assertNotIn("FLAT", cell["predictedMix"])
        self.assertNotIn("FLAT", cell["actualMix"])
        self.assertEqual(sum(cell["predictedMix"].values()), cell["rows"])
        self.assertEqual(sum(cell["actualMix"].values()), cell["rows"])
        self.assertLessEqual(cell["classesPredicted"], 2)

    def test_the_in_sample_helper_still_fits_three_classes_for_the_shipped_target(self):
        X, y3, _ = _data(seed=23, n=120, d=3)
        cell = fit_in_sample(X, y3, [0, 1, 2], CLASSES)
        self.assertEqual(cell["outputDimension"], 3)
        self.assertEqual(cell["outputClasses"], CLASSES)
        self.assertEqual(sum(cell["predictedMix"].values()), cell["rows"])


class HistoricalV1ArtifactsArePreservedAndShowTheDefect(unittest.TestCase):
    """The corrected runs must not have overwritten the records they correct."""

    def setUp(self):
        for path in (V1_BINARY, V1_ELIGIBLE, V1_FLOOR):
            self.assertTrue(path.exists(), f"missing historical artifact {path.name}")

    def test_versions_are_still_the_historical_ones(self):
        self.assertEqual(_read(V1_BINARY)["version"], "binary-context-v1")
        self.assertEqual(_read(V1_ELIGIBLE)["version"], "eligible-set-v1")
        self.assertEqual(_read(V1_FLOOR)["version"], "signal-floor-v1")

    def test_binary_v1_still_declares_the_three_column_construction_it_was_written_for(self):
        model = _read(V1_BINARY)["model"]
        self.assertIn("whyThreeColumns", model,
                      "v1 was regenerated by the corrected code; the historical record is gone")
        self.assertNotIn("outputDimension", model)

    def test_floor_v1_has_not_been_regenerated_with_the_corrected_width(self):
        binary = _read(V1_FLOOR)["results"]["binaryUpDown_allFeatures"]
        self.assertNotIn("outputDimension", binary)
        self.assertNotIn("outputClasses", binary)

    def test_v1_binary_reports_its_positive_class_under_the_wrong_name(self):
        """The defect, on disk: UP is 0 and the real UP rows are under FLAT, in every fold."""
        folds = _read(V1_BINARY)["folds"]
        self.assertTrue(folds, "no folds recorded")
        for fold in folds:
            actual, predicted = fold["actualMix"], fold["predictedMix"]
            self.assertEqual(actual.get("UP", 0), 0,
                             f"{fold['testYear']}: v1 recorded no UP rows at all")
            self.assertEqual(predicted.get("UP", 0), 0,
                             f"{fold['testYear']}: v1 predicted index 2 never occurred")
            self.assertGreater(actual["FLAT"], 0,
                               f"{fold['testYear']}: the real UP rows were under FLAT")
            self.assertEqual(actual["DOWN"] + actual["FLAT"], fold["testRows"])
            self.assertEqual(predicted["DOWN"] + predicted["FLAT"], fold["testRows"])

    def test_v1_eligible_reports_the_same_defect(self):
        for fold in _read(V1_ELIGIBLE)["folds"]:
            self.assertEqual(fold["actualMix"].get("UP", 0), 0)
            self.assertEqual(fold["predictedMix"].get("UP", 0), 0)
            self.assertGreater(fold["actualMix"]["FLAT"], 0)
            self.assertEqual(fold["actualMix"]["DOWN"] + fold["actualMix"]["FLAT"],
                             fold["testRows"])


def _assert_two_class_artifact(case: unittest.TestCase, artifact: dict, name: str):
    """Everything a corrected binary artifact has to say about itself and its folds."""
    case.assertEqual(artifact["version"].endswith("-v2"), True, f"{name}: version not v2")
    model = artifact["model"]
    case.assertEqual(model["outputDimension"], 2, f"{name}: not a two-column model")
    case.assertEqual(model["outputClasses"], ["DOWN", "UP"], f"{name}: wrong class names")
    case.assertEqual("FLAT" not in str(model["outputClasses"]), True)
    case.assertEqual(artifact["target"]["classes"], ["DOWN", "UP"])
    for fold in artifact["folds"]:
        year = fold["testYear"]
        for key in ("predictedMix", "actualMix"):
            counts = fold[key]
            case.assertNotIn("FLAT", counts, f"{name} {year}: {key} still reports FLAT")
            case.assertEqual(sorted(counts), sorted(["DOWN", "UP"]),
                             f"{name} {year}: {key} is not exactly DOWN/UP")
            case.assertEqual(sum(counts.values()), fold["testRows"],
                             f"{name} {year}: {key} does not cover the fold's rows")
        case.assertGreater(fold["actualMix"]["UP"], 0,
                           f"{name} {year}: no UP rows recorded, the rows are still mis-counted")
        case.assertGreaterEqual(fold["actualMix"]["DOWN"], 0)


class CorrectedV2ArtifactsReportTheRightClasses(unittest.TestCase):
    """Same rows as v1, same actual counts, correctly named -- and a genuinely two-wide fit."""

    def test_the_corrected_artifacts_exist(self):
        for path in (V2_BINARY, V2_ELIGIBLE, V2_FLOOR):
            self.assertTrue(path.exists(),
                            f"{path.name} is missing; the corrected experiment has not been run")

    def test_binary_v2_is_a_two_class_model(self):
        _assert_two_class_artifact(self, _read(V2_BINARY), "binary-context-v2")

    def test_eligible_v2_is_a_two_class_model(self):
        _assert_two_class_artifact(self, _read(V2_ELIGIBLE), "eligible-set-v2")

    def test_binary_v2_keeps_v1s_rows_and_renames_only_its_actual_counts(self):
        """The fit width changed, the data did not: v1's FLAT is v2's UP, fold for fold."""
        v1 = {f["testYear"]: f for f in _read(V1_BINARY)["folds"]}
        v2 = {f["testYear"]: f for f in _read(V2_BINARY)["folds"]}
        self.assertEqual(sorted(v1), sorted(v2), "the corrected run scored different years")
        for year in sorted(v2):
            self.assertEqual(v2[year]["trainRows"], v1[year]["trainRows"], year)
            self.assertEqual(v2[year]["testRows"], v1[year]["testRows"], year)
            self.assertEqual(v2[year]["actualMix"]["DOWN"], v1[year]["actualMix"]["DOWN"], year)
            self.assertEqual(v2[year]["actualMix"]["UP"], v1[year]["actualMix"]["FLAT"], year)
            self.assertEqual(v1[year]["actualMix"]["UP"], 0, year)

    def test_eligible_v2_keeps_v1s_rows_and_renames_only_its_actual_counts(self):
        v1 = {f["testYear"]: f for f in _read(V1_ELIGIBLE)["folds"]}
        v2 = {f["testYear"]: f for f in _read(V2_ELIGIBLE)["folds"]}
        self.assertEqual(sorted(v1), sorted(v2), "the corrected run scored different years")
        for year in sorted(v2):
            self.assertEqual(v2[year]["trainRows"], v1[year]["trainRows"], year)
            self.assertEqual(v2[year]["testRows"], v1[year]["testRows"], year)
            self.assertEqual(v2[year]["actualMix"]["DOWN"], v1[year]["actualMix"]["DOWN"], year)
            self.assertEqual(v2[year]["actualMix"]["UP"], v1[year]["actualMix"]["FLAT"], year)

    def test_the_corrected_runs_disclose_that_the_holdout_was_already_seen(self):
        for path in (V2_BINARY, V2_ELIGIBLE, V2_FLOOR):
            correction = _read(path).get("correctionOf")
            self.assertIsNotNone(correction, f"{path.name}: no correction record")
            self.assertTrue(correction.get("preservedUnchanged"),
                            f"{path.name}: does not record that v1 is preserved")
            exposure = correction.get("exposure", "")
            self.assertIn("examin", exposure,
                          f"{path.name}: does not say the holdout was already examined")
        for path in (V2_BINARY, V2_ELIGIBLE):
            self.assertIn("not a pristine", _read(path)["correctionOf"]["exposure"],
                          f"{path.name}: does not qualify the result as non-independent")

    def test_the_corrected_binary_artifact_does_not_keep_the_old_claims(self):
        payload = _read(V2_BINARY)
        self.assertNotIn("whyThreeColumns", payload["model"])
        self.assertNotIn("three-column softmax with no FLAT targets",
                         payload["fidelityLimitations"])
        self.assertIn("binary_context_experiment.json", payload["correctionOf"]["artifact"])

    def test_thresholds_were_not_moved_by_the_correction(self):
        """The criteria and their thresholds are the same five, with the same strings."""
        v1 = _read(V1_BINARY)["criteria"]
        v2 = _read(V2_BINARY)["criteria"]
        self.assertEqual(sorted(v1), sorted(v2))
        for key, spec in v1.items():
            self.assertEqual(v2[key][1], spec[1], f"{key}: acceptance threshold changed")
        v1e = _read(V1_ELIGIBLE)["criteria"]
        v2e = _read(V2_ELIGIBLE)["criteria"]
        self.assertEqual(sorted(v1e), sorted(v2e))
        for key, spec in v1e.items():
            self.assertEqual(v2e[key][1], spec[1], f"{key}: acceptance threshold changed")

    def test_the_corrected_floor_keeps_the_three_class_results_identical(self):
        """Reproducibility of the untouched path: v2's three-class cells equal v1's."""
        v1 = _read(V1_FLOOR)["results"]
        v2 = _read(V2_FLOOR)["results"]
        for cell in ("threeClass_allFeatures", "threeClass_priceOnly",
                     "shuffledControl_threeClass"):
            for field in ("rows", "inSampleAccuracy", "majorityClass", "overMajority"):
                self.assertEqual(v2[cell][field], v1[cell][field], f"{cell}.{field} moved")
            renamed = {CLASSES[int(k)]: v for k, v in v1[cell]["predictedMix"].items()}
            self.assertEqual(v2[cell]["predictedMix"], renamed, f"{cell} mix moved")

    def test_the_corrected_floors_binary_cell_is_two_class(self):
        v2 = _read(V2_FLOOR)["results"]["binaryUpDown_allFeatures"]
        self.assertEqual(v2["outputDimension"], 2)
        self.assertEqual(v2["outputClasses"], ["DOWN", "UP"])
        self.assertNotIn("FLAT", v2["predictedMix"])
        self.assertNotIn("FLAT", v2["actualMix"])
        self.assertEqual(sum(v2["predictedMix"].values()), v2["rows"])
        self.assertEqual(sum(v2["actualMix"].values()), v2["rows"])
        self.assertLessEqual(v2["classesPredicted"], 2)
        self.assertGreater(v2["actualMix"]["UP"], 0)

    def test_the_corrected_floors_binary_cell_measures_the_same_rows_as_v1(self):
        v1 = _read(V1_FLOOR)["results"]["binaryUpDown_allFeatures"]
        v2 = _read(V2_FLOOR)["results"]["binaryUpDown_allFeatures"]
        self.assertEqual(v2["rows"], v1["rows"])
        self.assertEqual(v2["features"], v1["features"])
        self.assertEqual(v2["actualMix"]["UP"] + v2["actualMix"]["DOWN"], v1["rows"])
        self.assertEqual(sorted(v1["predictedMix"]), ["0", "1"],
                         "v1 named its binary cells by index, which is how the third column and "
                         "the FLAT label both stayed invisible")


if __name__ == "__main__":
    unittest.main()
