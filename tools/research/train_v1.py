"""Brain V1: the first candidate trained to a persisted, loadable artifact.

    python tools/research/train_v1.py [--dataset DIR] [--out DIR] [--train-end YYYY-MM-DD]

What this adds, and what it deliberately does not
-------------------------------------------------
`baseline_experiment.py` measured the first candidate walk-forward and recorded NO-GO.
`balanced_experiment.py` tested whether that result was the optimiser collapsing rather than the
features being empty, and recorded NO-GO. Both wrote a **report**. Neither wrote a **model**: the
weights lived inside a process and died with it, so nothing afterwards could load the candidate,
read its coefficients, or reproduce one prediction. A JSON file saying a model scored 0.4211 is
evidence about a model; it is not the model.

This file changes that one thing, and only that one thing. The feature list, the fit, the
prediction function and every hyperparameter are **imported from `baseline_experiment.py` and are
not redefined here**, so there is no seam at which something could be quietly retuned on the way
to being persisted. If that file changes, this one trains the changed thing and says so by digest.

**This is not a new experiment and it may not be read as one.** The recorded verdicts stand. What
runs here is the already pre-registered first training task from `readiness.json` -- 20-session
direction classification on the 15 `pit.f` features -- fitted once on a fixed chronological span
and scored once on the span after it, so that a reusable artifact exists where previously only a
report did. A result from here cannot overturn a recorded NO-GO, because it is the same hypothesis
on the same data.

The holdout is not pristine, and the artifact says so
-----------------------------------------------------
Walk-forward folds for 2021 through 2026 were scored by the two recorded experiments, and the
second changed its configuration after seeing the first. Every calendar year this dataset can
offer has therefore been seen. `holdoutPristine` is **false** in the manifest and in the report,
and the honest reading of the evaluation below is *a reproduction*, not an independent validation.
A pristine holdout for this feature set needs sessions after the dataset's last date, or a feature
set that has not been scored on these years. Neither is manufactured here.

What is written
---------------
* `<brain>/model.json`   -- classes, feature names **in order**, the fitted weight matrix, the
  training-fold standardisation, and the exact hyperparameters. Small, textual, inspectable, and
  committed: a coefficient matrix is an aggregate, not a redistribution of the price feed.
* `<brain>/manifest.json` -- what it was trained on (every dataset file by sha256), what produced
  it, what it scored, and whether it is eligible for promotion.
* `data/foundation/dataset/brain_v1_training.json` -- the public record of the run.

`load_model` and `predict_rows` are the reusable half: a consumer gets the same answer the
training process got, from the file alone, with no numpy array left over from the fit. That is the
property `tests/test_brain_v1.py` pins, because an artifact nobody can reload is the failure this
file exists to end.

The dataset is verified before it is read
-----------------------------------------
Every year file is hashed and compared with `dataset_freeze.json`. A mismatch aborts rather than
training on a mutated dataset and recording the frozen version's name beside it -- the silent
dataset mutation the freeze exists to prevent. Nothing here writes to any database.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from baseline_experiment import (  # noqa: E402
    CLASSES, EMBARGO, FEATURES, L2, LR, SEED, STEPS, fit_softmax, load, metrics, predict,
)

OUT_DIR = ROOT / "data" / "foundation" / "dataset"
BRAIN_DIR = ROOT / "data" / "foundation" / "brain" / "brain-v1"
DEFAULT_DS = ROOT / ".cache" / "foundation" / "dataset_full"
FREEZE = OUT_DIR / "dataset_freeze.json"

#: The last session that may be trained on. Fixed here rather than taken from the data, so that a
#: later dataset extension does not silently move the split under an artifact that claims this one.
TRAIN_END = "2025-12-31"

MODEL_VERSION = "brain-v1"

#: Fixed before this file was first run, and identical in substance to the criteria the recorded
#: experiments were judged by. They are restated rather than imported because a criterion that can
#: be edited from another file is not a pre-registration.
CRITERIA = {
    "accuracyAboveHoldoutMajority": "strictly above the holdout's largest-class share",
    "notDegenerate": "no predicted class exceeds 0.7 of the holdout while being under half of it",
    "adverseClassIsPredicted": "recall for DOWN is at least 0.2, so the model has not stopped "
                               "saying the word",
    "setBefore": "any number from this run was seen",
}


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def verify_dataset(ds: Path, freeze_path: Path = FREEZE) -> dict:
    """Hash every frozen year file and refuse to train on anything that moved.

    Returns the per-file record that goes into the manifest. Raises `SystemExit` on any
    mismatch, missing file or unreadable freeze: training on a changed dataset while recording
    the frozen dataset's name is precisely the provenance failure the freeze exists to stop.
    """
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    expected = freeze["files"]
    files, bad = {}, []
    for name, want in sorted(expected.items()):
        p = ds / name
        if not p.exists():
            bad.append(f"{name}: missing from {ds}")
            continue
        got = sha256_file(p)
        files[name] = {"sha256": got, "bytes": p.stat().st_size}
        if got != want["sha256"]:
            bad.append(f"{name}: sha256 {got[:16]} != frozen {want['sha256'][:16]}")
    if bad:
        raise SystemExit("dataset does not match the freeze; refusing to train:\n  "
                         + "\n  ".join(bad))
    return {"version": freeze["version"], "frozenAt": freeze["frozenAt"],
            "blockingGatesGreen": bool(freeze.get("blockingGatesGreen")),
            "fileCount": len(files), "files": files}


def encode_row(f: dict) -> list[float] | None:
    """One `pit.f` block as the feature vector the model consumes, in `FEATURES` order.

    The coercions are the ones `baseline_experiment.load` applies while reading the dataset --
    an absent value is 0.0 after standardisation moved it, and `triggerDirection` is the one
    categorical field, carried as up/down/flat rather than as a string. They are written out
    here because a persisted model is useless without the encoder that fed it, and
    `tests/test_brain_v1.py` asserts this function reproduces `load`'s vectors exactly.

    Returns None when a field cannot be read as a number, which is how `load` drops a row; a
    consumer must treat None as "no prediction", never as a neutral one.
    """
    row = []
    for k in FEATURES:
        v = f.get(k)
        if v is None:
            v = 0.0
        if isinstance(v, str):
            v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
        try:
            row.append(float(v))
        except (TypeError, ValueError):
            return None
    return row


def save_model(path: Path, W: np.ndarray, mu: np.ndarray, sd: np.ndarray, extra: dict) -> str:
    """Write the artifact and return its sha256. Keys are sorted so the digest is stable."""
    payload = {
        "modelVersion": MODEL_VERSION,
        "kind": "multinomial logistic regression",
        "classes": list(CLASSES),
        "features": list(FEATURES),
        "featureOrderMatters": True,
        "standardisation": {"mean": [float(x) for x in mu], "sd": [float(x) for x in sd],
                            "fittedOn": "the training span only, never the holdout"},
        "weights": [[float(x) for x in row] for row in W],
        "weightShape": list(W.shape),
        "biasRow": "the last row of weights is the intercept; the input is standardised and "
                   "then a constant 1.0 is appended",
        "hyperparameters": {"seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2},
        **extra,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=1, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    return sha256_text(text)


def load_model(path: Path) -> dict:
    """Read a persisted model back into the shape `predict_rows` needs.

    This is the half that makes the artifact an artifact. It validates the parts a silent
    mismatch would corrupt -- the feature count against the weight shape, and the class count
    against the weight columns -- because a model loaded with its columns transposed predicts
    confidently and wrongly.
    """
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    W = np.asarray(m["weights"], dtype=np.float64)
    mu = np.asarray(m["standardisation"]["mean"], dtype=np.float64)
    sd = np.asarray(m["standardisation"]["sd"], dtype=np.float64)
    d = len(m["features"])
    if W.shape != (d + 1, len(m["classes"])):
        raise ValueError(f"weights {W.shape} do not match {d} features and "
                         f"{len(m['classes'])} classes")
    if mu.shape != (d,) or sd.shape != (d,):
        raise ValueError("standardisation does not match the feature count")
    if (sd == 0).any():
        raise ValueError("a zero standard deviation would divide a feature by nothing")
    return {"meta": m, "W": W, "mu": mu, "sd": sd,
            "features": list(m["features"]), "classes": list(m["classes"])}


def predict_rows(model: dict, rows: list[dict]) -> list[str | None]:
    """Class names for a list of `pit.f` blocks, or None where a block could not be encoded.

    A None is a refusal, not a FLAT. The caller decides what to do without a prediction; this
    function will not invent one, which is the same rule the families follow when an input is
    missing.
    """
    out: list[str | None] = []
    keep, idx = [], []
    for i, f in enumerate(rows):
        v = encode_row(f)
        out.append(None)
        if v is not None:
            keep.append(v)
            idx.append(i)
    if not keep:
        return out
    X = (np.asarray(keep, dtype=np.float64) - model["mu"]) / model["sd"]
    yp = predict(model["W"], X)
    for i, c in zip(idx, yp):
        out[i] = model["classes"][int(c)]
    return out


def degeneracy(yp: np.ndarray, yt: np.ndarray) -> dict:
    """Is the model answering, or has it collapsed onto one word?

    A class predicted on most of the holdout while being a minority of it is the failure mode the
    first candidate showed and the second was built to test. Reported as a measurement either way.
    """
    worst, flag = None, False
    for i, c in enumerate(CLASSES):
        share_pred = float((yp == i).mean())
        share_true = float((yt == i).mean())
        if worst is None or share_pred > worst["predictedShare"]:
            worst = {"class": c, "predictedShare": round(share_pred, 4),
                     "actualShare": round(share_true, 4)}
        if share_pred > 0.7 and share_true < 0.5:
            flag = True
    return {"largestPredicted": worst, "degenerate": flag}


def repo_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # a checkout without git is not a reason to refuse to train
        return "unknown"


def main() -> int:
    ds = Path(arg("--dataset", DEFAULT_DS))
    out_dir = Path(arg("--out", OUT_DIR))
    brain_dir = Path(arg("--brain", BRAIN_DIR))
    train_end = arg("--train-end", TRAIN_END)

    print(f"verifying {ds} against {FREEZE.name}")
    data_version = verify_dataset(ds)
    print(f"  {data_version['fileCount']} files match the freeze "
          f"({data_version['version']}, gates green: {data_version['blockingGatesGreen']})")

    print(f"loading {ds}")
    X, y, dates, cls, flags = load(ds)
    print(f"usable examples: {len(X):,}  features: {X.shape[1]}")
    if not len(X):
        raise SystemExit("no usable examples; refusing to write a model trained on nothing")

    order = np.argsort(dates, kind="stable")
    X, y, dates, cls = X[order], y[order], dates[order], cls[order]
    udates = np.unique(dates)
    didx = {d: i for i, d in enumerate(udates)}
    pos = np.asarray([didx[d] for d in dates])

    # The embargo is dropped from the end of the *training* span, not the start of the holdout:
    # a 20-session label makes the last training rows and the first holdout rows score the same
    # forward sessions, and the holdout must keep every row it is entitled to.
    cut_candidates = [d for d in udates if d > train_end]
    if not cut_candidates:
        raise SystemExit(f"no sessions after {train_end}; there is nothing to hold out")
    cut_pos = didx[cut_candidates[0]]
    tr = pos < (cut_pos - EMBARGO)
    te = dates > train_end
    print(f"train {int(tr.sum()):,} rows to {udates[max(0, cut_pos - EMBARGO - 1)]}  "
          f"holdout {int(te.sum()):,} rows from {dates[te][0]} to {dates[te][-1]}")
    if tr.sum() < 5000 or te.sum() < 500:
        raise SystemExit("split too small to train or to score")

    mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
    sd[sd == 0] = 1.0
    Xtr = (X[tr] - mu) / sd
    W = fit_softmax(Xtr, y[tr])

    # Determinism, measured rather than asserted: the same rows and the same seed must give the
    # same weights. Run on a slice so the check costs seconds, not another full fit.
    probe = min(20000, int(tr.sum()))
    w1 = fit_softmax(Xtr[:probe], y[tr][:probe])
    w2 = fit_softmax(Xtr[:probe], y[tr][:probe])
    deterministic = bool(np.array_equal(w1, w2))

    yp = predict(W, (X[te] - mu) / sd)
    yt = y[te]
    m = metrics(yt, yp)
    holdout_majority = float(max((yt == i).mean() for i in range(len(CLASSES))))
    train_majority_class = int(np.bincount(y[tr], minlength=len(CLASSES)).argmax())
    train_const_on_holdout = float((yt == train_majority_class).mean())
    deg = degeneracy(yp, yt)
    recall_down = m.get(f"recall_{CLASSES[0]}")

    checks = {
        "accuracyAboveHoldoutMajority": [m["accuracy"], round(holdout_majority, 4),
                                         bool(m["accuracy"] > holdout_majority)],
        "notDegenerate": [deg["degenerate"], False, not deg["degenerate"]],
        "adverseClassIsPredicted": [recall_down, 0.2, bool((recall_down or 0) >= 0.2)],
    }
    passed = all(v[2] for v in checks.values())
    verdict = "GO" if passed else "NO-GO"

    by_market = {}
    for mk in sorted(set(cls[te])):
        sel = cls[te] == mk
        if sel.sum() < 200:
            continue
        mm = metrics(yt[sel], yp[sel])
        by_market[mk] = {"n": mm["n"], "accuracy": mm["accuracy"],
                         "majority": round(float(max((yt[sel] == i).mean()
                                                     for i in range(len(CLASSES)))), 4)}

    evaluation = {
        "holdout": {"from": str(dates[te][0]), "to": str(dates[te][-1]),
                    "rows": m["n"], "effectiveIndependentWindows": m["effectiveIndependentWindows"],
                    "pristine": False,
                    "exposure": "calendar years 2021-2026 were all scored by the recorded "
                                "walk-forward experiments, and the second of them chose its "
                                "configuration after seeing the first. No unseen span exists in "
                                "this dataset, so this is a reproduction and not an independent "
                                "validation."},
        "accuracy": m["accuracy"],
        "holdoutMajorityShare": round(holdout_majority, 4),
        "marginOverHoldoutMajority": round(m["accuracy"] - holdout_majority, 4),
        "trainMajorityClass": CLASSES[train_majority_class],
        "trainMajorityConstantOnHoldout": round(train_const_on_holdout, 4),
        "marginOverDeployableConstant": round(m["accuracy"] - train_const_on_holdout, 4),
        "perClass": {c: {"recall": m.get(f"recall_{c}"), "precision": m.get(f"precision_{c}")}
                     for c in CLASSES},
        "predictedMix": m["predictedMix"],
        "actualMix": m["actualMix"],
        "degeneracy": deg,
        "byMarket": by_market,
    }

    model_extra = {
        "trainedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trainSpan": {"to": str(udates[max(0, cut_pos - EMBARGO - 1)]),
                      "rows": int(tr.sum()), "embargoSessionsDropped": EMBARGO},
        "dataset": data_version["version"],
        "status": verdict,
        "productionApproved": False,
    }
    brain_dir.mkdir(parents=True, exist_ok=True)
    model_path = brain_dir / "model.json"
    model_sha = save_model(model_path, W, mu, sd, model_extra)

    # The artifact must survive the round trip before anything claims it exists: reload it from
    # disk and require the same predictions, from the file alone.
    reloaded = load_model(model_path)
    yp2 = predict(reloaded["W"], (X[te] - reloaded["mu"]) / reloaded["sd"])
    round_trips = bool(np.array_equal(yp, yp2))

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modelVersion": MODEL_VERSION,
        "artifact": {"path": str(model_path.relative_to(ROOT)).replace("\\", "/"),
                     "sha256": model_sha,
                     "reloadReproducesPredictions": round_trips,
                     "fitIsDeterministic": deterministic},
        "producedBy": "tools/research/train_v1.py",
        "configurationImportedFrom": "tools/research/baseline_experiment.py",
        "configurationSha256": sha256_file(HERE / "baseline_experiment.py"),
        "repoHead": repo_head(),
        "task": {"label": "label20", "classes": list(CLASSES), "features": list(FEATURES),
                 "featureCount": len(FEATURES),
                 "rule": "UP when fwd20 >= +2%, DOWN when <= -2%, else FLAT",
                 "outcomeFieldsUsedAsFeatures": 0},
        "hyperparameters": {"seed": SEED, "steps": STEPS, "learningRate": LR, "l2": L2,
                            "embargoSessions": EMBARGO,
                            "standardisation": "training span only"},
        "dataVersion": data_version,
        "preDeclaredCriteria": CRITERIA,
        "criteriaMet": checks,
        "evaluation": evaluation,
        "verdict": verdict,
        "eligibleForPromotion": False,
        "promotionNote": (
            "NO-GO: not eligible. Preserved as an experiment artifact." if not passed else
            "Criteria met on an already-exposed span. This is a reproduction, not an independent "
            "validation, so it does not by itself qualify the model for promotion; a pristine "
            "holdout is required first."),
        "limitations": [
            "direction only. No execution cost, spread or borrow data exists for any market, so "
            "nothing here is a profitability claim and none of it may be reported as net.",
            "the effective sample is rows / 20; the row count is not the sample size.",
            "survivorship: the universe is today's registered assets, so the bias is a measured "
            "lower bound rather than something removed.",
            "forex is 68% FLAT under a fixed 2% band, so its accuracy is dominated by one class.",
            "the holdout is not pristine; see evaluation.holdout.exposure.",
        ],
    }
    (brain_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    report = dict(manifest)
    report["status"] = "offline training run; nothing deployed, nothing traded"
    report["statement"] = (
        f"{verdict}. The persisted candidate scores {m['accuracy']:.4f} on "
        f"{m['n']:,} holdout rows against a largest-class share of {holdout_majority:.4f}, a "
        f"margin of {m['accuracy'] - holdout_majority:+.4f}. A reusable artifact now exists at "
        f"{manifest['artifact']['path']} and reloads to the same predictions; that is what this "
        f"run was for. It does not overturn the recorded verdicts and it is not approved for "
        f"production.")
    (out_dir / "brain_v1_training.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"\naccuracy {m['accuracy']:.4f}  holdout majority {holdout_majority:.4f}  "
          f"margin {m['accuracy'] - holdout_majority:+.4f}")
    print(f"deployable constant ({CLASSES[train_majority_class]}) on the holdout: "
          f"{train_const_on_holdout:.4f}")
    for k, v in checks.items():
        print(f"  {'ok ' if v[2] else 'FAIL'} {k}: {v[0]} vs {v[1]}")
    print(f"reload reproduces predictions: {round_trips}   fit is deterministic: {deterministic}")
    print(f"\nVERDICT {verdict}; eligible for promotion: False")
    print(f"wrote {model_path} (sha256 {model_sha[:16]})")
    print(f"wrote {brain_dir / 'manifest.json'}")
    print(f"wrote {out_dir / 'brain_v1_training.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
