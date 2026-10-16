"""The persisted Brain V1 artifact: can it be reloaded, and will it refuse what it should?

    python -m unittest tests.test_brain_v1 -v

Stdlib unittest, no database, no network, no dataset. Every fixture here is written into a
temporary directory, so these run on any checkout in under a second.

What is covered is the half that a report cannot prove. `baseline_experiment.json` could say a
model scored 0.4211 whether or not the weights still existed anywhere; the claim this file makes
is stronger and therefore testable -- that an artifact on disk reloads into the same predictions,
that the encoder which fed it is the same one the dataset loader used, and that the loader refuses
a dataset that has moved under the freeze rather than training on it quietly.

Where a case is here because it is a failure mode this project has actually seen, the test says so.
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))

import baseline_experiment as be  # noqa: E402
import train_v1 as t  # noqa: E402


def a_row(f: dict, *, as_of="2024-03-01", label="UP", symbol="AAA") -> dict:
    """A dataset row shaped the way `assemble.py` writes one."""
    return {"asOf": as_of, "symbol": symbol, "assetType": "stock", "market": "US",
            "outcome": {"label20": label, "mature20": True, "fwd20": 3.1},
            "pit": {"n": 400, "f": f}, "candidate": None,
            "coverage": {"pit": True, "setup": False}, "dataQuality": {}}


def full_f(**over) -> dict:
    """A `pit.f` block carrying every feature the model reads, with sane distinct values."""
    f = {k: float(i + 1) for i, k in enumerate(t.FEATURES)}
    f["triggerDirection"] = "up"
    f.update(over)
    return f


def write_dataset(d: Path, rows: list[dict], year: int = 2024) -> Path:
    p = d / f"examples-v3-{year}.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def a_model(seed: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    d, k = len(t.FEATURES), len(t.CLASSES)
    return (rng.normal(0, 1, size=(d + 1, k)), rng.normal(0, 1, size=d),
            np.abs(rng.normal(1, 0.1, size=d)) + 0.5)


class TheEncoderMatchesTheDatasetLoader(unittest.TestCase):
    """A persisted model is useless beside a different encoder than the one that fed it.

    The two live in separate files -- `train_v1.encode_row` and the inline coercion inside
    `baseline_experiment.load` -- so nothing but a test keeps them the same. If they drift, the
    model keeps predicting and starts being wrong, which is the quiet kind of failure.
    """

    def test_encode_row_reproduces_the_loaders_vectors(self):
        rows = [a_row(full_f()),
                a_row(full_f(triggerDirection="down", r20=-4.0), label="DOWN"),
                a_row(full_f(triggerDirection=None, volumeRatio=None), label="FLAT")]
        with tempfile.TemporaryDirectory() as d:
            write_dataset(Path(d), rows)
            X, y, dates, cls, flags = be.load(Path(d))
        self.assertEqual(len(X), 3)
        for i, r in enumerate(rows):
            self.assertEqual(t.encode_row(r["pit"]["f"]), list(X[i]))

    def test_an_absent_value_is_zero_and_not_a_dropped_row(self):
        v = t.encode_row(full_f(atr14=None))
        self.assertIsNotNone(v)
        self.assertEqual(v[t.FEATURES.index("atr14")], 0.0)

    def test_the_categorical_field_carries_a_sign_not_a_hash(self):
        up = t.encode_row(full_f(triggerDirection="up"))
        down = t.encode_row(full_f(triggerDirection="down"))
        none = t.encode_row(full_f(triggerDirection=None))
        i = t.FEATURES.index("triggerDirection")
        self.assertEqual((up[i], down[i], none[i]), (1.0, -1.0, 0.0))

    def test_an_unreadable_value_refuses_the_row(self):
        self.assertIsNone(t.encode_row(full_f(r20=object())))


class TheArtifactSurvivesTheRoundTrip(unittest.TestCase):
    """The property the whole file exists for: weights on disk predict what weights in memory did."""

    def test_saving_then_loading_gives_the_same_predictions(self):
        W, mu, sd = a_model()
        rows = [full_f(r1=float(i), returnZ=float(i % 3) - 1.0) for i in range(50)]
        X = np.asarray([t.encode_row(f) for f in rows], dtype=np.float64)
        want = [t.CLASSES[int(c)] for c in be.predict(W, (X - mu) / sd)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "model.json"
            t.save_model(p, W, mu, sd, {"status": "NO-GO", "productionApproved": False})
            got = t.predict_rows(t.load_model(p), rows)
        self.assertEqual(got, want)

    def test_the_digest_is_stable_across_two_identical_saves(self):
        W, mu, sd = a_model()
        with tempfile.TemporaryDirectory() as d:
            one = t.save_model(Path(d) / "a.json", W, mu, sd, {"status": "NO-GO"})
            two = t.save_model(Path(d) / "b.json", W, mu, sd, {"status": "NO-GO"})
        self.assertEqual(one, two)

    def test_a_row_that_cannot_be_encoded_is_refused_and_does_not_shift_the_others(self):
        """A refusal must be None in its own slot, never a FLAT and never an off-by-one.

        Dropping the bad row and returning a shorter list would hand every later prediction to
        the wrong instrument, which is worse than having no prediction at all.
        """
        W, mu, sd = a_model()
        rows = [full_f(r1=1.0), full_f(r20=object()), full_f(r1=2.0)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "model.json"
            t.save_model(p, W, mu, sd, {"status": "NO-GO"})
            model = t.load_model(p)
            got = t.predict_rows(model, rows)
            alone = t.predict_rows(model, [rows[0], rows[2]])
        self.assertEqual(len(got), 3)
        self.assertIsNone(got[1])
        self.assertEqual([got[0], got[2]], alone)

    def test_no_rows_gives_no_predictions_rather_than_raising(self):
        W, mu, sd = a_model()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "model.json"
            t.save_model(p, W, mu, sd, {"status": "NO-GO"})
            self.assertEqual(t.predict_rows(t.load_model(p), []), [])


class TheLoaderRefusesAMisshapenModel(unittest.TestCase):
    """A model loaded with its axes confused predicts confidently and wrongly."""

    def _write(self, d: Path, mutate) -> Path:
        W, mu, sd = a_model()
        p = d / "model.json"
        t.save_model(p, W, mu, sd, {"status": "NO-GO"})
        m = json.loads(p.read_text(encoding="utf-8"))
        mutate(m)
        p.write_text(json.dumps(m), encoding="utf-8")
        return p

    def test_transposed_weights_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            def flip(m):
                m["weights"] = [list(r) for r in zip(*m["weights"])]
            p = self._write(Path(d), flip)
            with self.assertRaises(ValueError):
                t.load_model(p)

    def test_a_feature_dropped_from_the_list_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(Path(d), lambda m: m["features"].pop())
            with self.assertRaises(ValueError):
                t.load_model(p)

    def test_a_standardisation_of_the_wrong_length_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(Path(d), lambda m: m["standardisation"]["mean"].pop())
            with self.assertRaises(ValueError):
                t.load_model(p)

    def test_a_zero_standard_deviation_is_rejected_rather_than_dividing_by_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            def zero(m):
                m["standardisation"]["sd"][0] = 0.0
            p = self._write(Path(d), zero)
            with self.assertRaises(ValueError):
                t.load_model(p)


class TheFreezeIsCheckedBeforeTraining(unittest.TestCase):
    """Training on a mutated dataset while recording the frozen name beside it is the exact
    provenance failure the freeze exists to prevent, so it must abort rather than warn."""

    def _freeze(self, d: Path, files: dict) -> Path:
        p = d / "freeze.json"
        p.write_text(json.dumps({"version": "examples-v3-test", "frozenAt": "2026-10-16T00:00:00",
                                 "blockingGatesGreen": True, "files": files}), encoding="utf-8")
        return p

    def test_a_matching_dataset_is_accepted_and_reports_what_it_checked(self):
        with tempfile.TemporaryDirectory() as d:
            ds = Path(d)
            p = write_dataset(ds, [a_row(full_f())])
            fz = self._freeze(ds, {p.name: {"sha256": t.sha256_file(p), "bytes": p.stat().st_size}})
            rec = t.verify_dataset(ds, fz)
        self.assertEqual(rec["fileCount"], 1)
        self.assertEqual(rec["version"], "examples-v3-test")
        self.assertTrue(rec["blockingGatesGreen"])

    def test_a_changed_byte_aborts(self):
        with tempfile.TemporaryDirectory() as d:
            ds = Path(d)
            p = write_dataset(ds, [a_row(full_f())])
            fz = self._freeze(ds, {p.name: {"sha256": t.sha256_file(p), "bytes": p.stat().st_size}})
            write_dataset(ds, [a_row(full_f(), label="DOWN")])   # same name, different contents
            with self.assertRaises(SystemExit):
                t.verify_dataset(ds, fz)

    def test_a_missing_file_aborts(self):
        with tempfile.TemporaryDirectory() as d:
            ds = Path(d)
            fz = self._freeze(ds, {"examples-v3-2024.jsonl.gz": {"sha256": "0" * 64, "bytes": 1}})
            with self.assertRaises(SystemExit):
                t.verify_dataset(ds, fz)


class TheCollapseIsMeasuredNotAssumed(unittest.TestCase):
    """The first candidate collapsed toward UP; the flag that would have named it is tested here."""

    def test_one_word_on_most_of_a_minority_class_is_degenerate(self):
        yp = np.full(100, t.CLASSES.index("UP"))
        yt = np.asarray([t.CLASSES.index("UP")] * 30 + [t.CLASSES.index("DOWN")] * 70)
        d = t.degeneracy(yp, yt)
        self.assertTrue(d["degenerate"])
        self.assertEqual(d["largestPredicted"]["class"], "UP")

    def test_a_model_that_answers_three_ways_is_not_degenerate(self):
        yp = np.asarray([0, 1, 2] * 33 + [0])
        yt = np.asarray([0, 1, 2] * 33 + [0])
        self.assertFalse(t.degeneracy(yp, yt)["degenerate"])

    def test_predicting_a_class_that_really_is_the_majority_is_not_degenerate(self):
        """A dataset that genuinely is 80% one class does not make its predictor degenerate."""
        yp = np.full(100, t.CLASSES.index("UP"))
        yt = np.asarray([t.CLASSES.index("UP")] * 80 + [t.CLASSES.index("DOWN")] * 20)
        self.assertFalse(t.degeneracy(yp, yt)["degenerate"])


class TheCommittedArtifactSaysWhatItIs(unittest.TestCase):
    """Run against the artifact in the repository, when one has been trained.

    These are the claims a reader of the repository is entitled to rely on: the file loads, its
    recorded digest is its own, its verdict agrees with its own criteria, and nothing in it
    describes itself as production-approved while carrying a NO-GO.
    """

    @classmethod
    def setUpClass(cls):
        cls.model_path = t.BRAIN_DIR / "model.json"
        cls.manifest_path = t.BRAIN_DIR / "manifest.json"
        if not cls.model_path.exists() or not cls.manifest_path.exists():
            raise unittest.SkipTest("no trained artifact in this checkout")
        cls.manifest = json.loads(cls.manifest_path.read_text(encoding="utf-8"))

    def test_the_model_loads(self):
        m = t.load_model(self.model_path)
        self.assertEqual(m["features"], list(t.FEATURES))
        self.assertEqual(m["classes"], list(t.CLASSES))

    def test_the_manifest_records_the_models_own_digest(self):
        self.assertEqual(self.manifest["artifact"]["sha256"],
                         t.sha256_text(self.model_path.read_text(encoding="utf-8")))

    def test_the_verdict_agrees_with_its_own_criteria(self):
        met = all(v[2] for v in self.manifest["criteriaMet"].values())
        self.assertEqual(self.manifest["verdict"], "GO" if met else "NO-GO")

    def test_a_no_go_is_never_eligible_for_promotion(self):
        if self.manifest["verdict"] == "NO-GO":
            self.assertFalse(self.manifest["eligibleForPromotion"])
        self.assertFalse(json.loads(self.model_path.read_text(encoding="utf-8"))
                         ["productionApproved"])

    def test_the_holdout_is_not_described_as_pristine(self):
        """Every calendar year here has been scored before. Claiming otherwise would be the
        manufactured-success failure the directive names, so it is pinned."""
        self.assertFalse(self.manifest["evaluation"]["holdout"]["pristine"])

    def test_the_artifact_reloaded_to_the_same_predictions_when_it_was_written(self):
        self.assertTrue(self.manifest["artifact"]["reloadReproducesPredictions"])
        self.assertTrue(self.manifest["artifact"]["fitIsDeterministic"])

    def test_no_outcome_field_is_listed_as_a_feature(self):
        forbidden = {"fwd1", "fwd5", "fwd20", "mfe", "mae", "label20", "label60"}
        self.assertEqual(forbidden & set(self.manifest["task"]["features"]), set())


if __name__ == "__main__":
    unittest.main()
