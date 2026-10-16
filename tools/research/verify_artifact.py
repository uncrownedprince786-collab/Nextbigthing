"""Load a persisted candidate in a fresh process and make it reproduce its own recorded result.

    python tools/research/verify_artifact.py --model data/foundation/brain/brain-v2-context
                                             [--dataset DIR] [--prefix examples-v4-context]

Why this is not the same as the trainer's own round-trip check
---------------------------------------------------------------
`train_v1.py` reloads its model before writing the manifest and asserts the predictions match.
That proves the file serialises what was in memory. It cannot prove the artifact is *sufficient*:
the process still held the fitted standardisation, the imputation means, the feature order and the
loader, so a model missing any of them would still have scored.

This runs in a process that has none of that. It reads `model.json`, rebuilds the feature vectors
from the dataset by **name**, applies the preprocessing the file itself describes, scores the whole
holdout, and compares accuracy, predicted mix and per-class recall against the numbers in
`manifest.json`. If the artifact is missing anything an inference path would need, the comparison
is what notices.

That makes this the training/inference parity check as well, because rebuilding by name is what an
inference path does: a column reordered between training and serving is the classic silent
corruption, and it changes the predicted mix here rather than quietly degrading a live score.

Exit code is non-zero on any mismatch. Nothing is written and no model is modified.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

CLASSES = ("DOWN", "FLAT", "UP")


def rows_from(ds: Path, prefix: str, after: str | None):
    for f in sorted(ds.glob(f"{prefix}-*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if after and r["asOf"] <= after:
                    continue
                pit = r.get("pit") or {}
                o = r.get("outcome") or {}
                if not pit.get("f") or o.get("label20") not in CLASSES or not o.get("mature20"):
                    continue
                yield r, pit, o


def vector(pit: dict, names: list[str]) -> list[float | None]:
    """Rebuild by NAME, never by position: that is what an inference path has to do."""
    f = pit.get("f") or {}
    c = (pit.get("ctx") or {}).get("f") or {}
    out: list[float | None] = []
    for k in names:
        v = f[k] if k in f else c.get(k)
        if isinstance(v, str):
            v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
        out.append(None if v is None else float(v))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--dataset", default=str(ROOT / ".cache" / "foundation" / "dataset_v4"))
    ap.add_argument("--prefix", default="examples-v4-context")
    ap.add_argument("--train-end", default="2025-12-31")
    a = ap.parse_args()

    mdir = Path(a.model)
    model = json.loads((mdir / "model.json").read_text(encoding="utf-8"))
    manifest = json.loads((mdir / "manifest.json").read_text(encoding="utf-8"))
    names = model["features"]
    classes = model["classes"]
    W = np.asarray(model["weights"], dtype=np.float64)
    mu = np.asarray(model["standardisation"]["mean"], dtype=np.float64)
    sd = np.asarray(model["standardisation"]["sd"], dtype=np.float64)
    rule = model.get("missingValueRule", "zero")
    print(f"model      {model['modelVersion']}  {len(names)} features  weights {list(W.shape)}")
    print(f"missing    {rule}")

    if W.shape != (len(names) + 1, len(classes)):
        print(f"FAIL weight shape {W.shape} does not match {len(names)} features")
        return 1

    X, y = [], []
    for r, pit, o in rows_from(Path(a.dataset), a.prefix, a.train_end):
        v = vector(pit, names)
        X.append(v)
        y.append(classes.index(o["label20"]))
    if not X:
        print("FAIL no holdout rows found")
        return 1
    Xa = np.asarray([[np.nan if c is None else c for c in row] for row in X], dtype=np.float64)
    ya = np.asarray(y, dtype=np.int64)
    print(f"holdout    {len(ya):,} rows rebuilt by name")

    # The file's own preprocessing, applied from the file alone.
    Xa = np.where(np.isnan(Xa), mu, Xa) if "mean" in rule else np.where(np.isnan(Xa), 0.0, Xa)
    Z = (Xa - mu) / sd
    yp = (np.hstack([Z, np.ones((len(Z), 1))]) @ W).argmax(axis=1)

    acc = round(float((ya == yp).mean()), 4)
    mix = {c: int((yp == i).sum()) for i, c in enumerate(classes)}
    recall = {c: (round(float((yp[ya == i] == i).mean()), 4) if (ya == i).any() else None)
              for i, c in enumerate(classes)}

    ev = manifest["evaluation"]
    want = ev.get("context") or ev            # v2 nests its own block; v1 does not
    exp_acc = want.get("accuracy", ev.get("accuracy"))
    exp_mix = want.get("predictedMix", ev.get("predictedMix"))
    exp_recall = {c: (want.get("perClass", {}).get(c) or {}).get("recall") for c in classes}

    checks = [("accuracy", acc, exp_acc, acc == exp_acc),
              ("predictedMix", mix, exp_mix, mix == exp_mix),
              ("recall", recall, exp_recall, recall == exp_recall)]
    for name, got, exp, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {got} vs manifest {exp}")
    if not all(c[3] for c in checks):
        print("\nFAIL the artifact does not reproduce its own recorded result from the file alone")
        return 1
    print("\nok the artifact reproduces its recorded holdout result in a fresh process, "
          "with features rebuilt by name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
