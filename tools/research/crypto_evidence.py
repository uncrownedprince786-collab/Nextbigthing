"""Is the crypto result real, or is it the UP collapse landing on a market that rose?

    python tools/research/crypto_evidence.py [--dataset DIR] [--out FILE] [--cache FILE]

`brain-v2-context` scored 0.5143 on the crypto slice of its holdout against a 0.4723 largest-class
share -- the only market in the run to clear its own majority. That is the one encouraging number
in an otherwise NO-GO evaluation, and it is exactly the kind of number that is usually an artefact.

The model predicted UP on 92.19% of the whole holdout. If crypto's own UP share were high enough,
a predictor that says UP everywhere would score well there by accident, and "crypto is different"
would be a story told about a coincidence. So before any crypto-specialist experiment is
registered, this measures the thing that would make it worthless:

* the crypto slice's actual class distribution;
* what an always-UP predictor scores on it;
* what `brain-v2-context` actually predicted there, per class;
* whether its crypto accuracy survives once the always-UP baseline is accounted for.

A hypothesis that cannot survive this check should not be registered, and this file runs before
the pre-registration rather than after it.

It also writes a cached crypto slice, because the full dataset takes minutes to read and the
training run that may follow should not pay that cost twice.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from baseline_experiment import CLASSES  # noqa: E402
from context_features import ContextSource  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

DEFAULT_DS = ROOT / ".cache" / "foundation" / "dataset_v4"
DEFAULT_CACHE = ROOT / ".cache" / "foundation" / "crypto_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_evidence.json"
MODEL = ROOT / "data" / "foundation" / "brain" / "brain-v2-context"
TRAIN_END = "2025-12-31"


def load_crypto(ds: Path, prefix="examples-v4-context"):
    X, y, dates, syms = [], [], [], []
    for f in sorted(ds.glob(f"{prefix}-*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("assetType") != "crypto":
                    continue
                pit = r.get("pit") or {}
                p, o = pit.get("f"), r.get("outcome") or {}
                if not p or o.get("label20") not in CLASSES or not o.get("mature20"):
                    continue
                c = (pit.get("ctx") or {}).get("f") or {}
                row = []
                ok = True
                for k in ALL_FEATURES:
                    v = p.get(k) if k in p else c.get(k)
                    if isinstance(v, str):
                        v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
                    if v is None:
                        row.append(np.nan)
                        continue
                    try:
                        row.append(float(v))
                    except (TypeError, ValueError):
                        ok = False
                        break
                if not ok:
                    continue
                X.append(row)
                y.append(CLASSES.index(o["label20"]))
                dates.append(r["asOf"])
                syms.append(r["symbol"])
    return (np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.int64),
            np.asarray(dates), np.asarray(syms))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(DEFAULT_DS))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    cache = Path(a.cache)
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        X, y, dates, syms = z["X"], z["y"], z["dates"], z["syms"]
        print(f"loaded cached crypto slice: {len(X):,} rows")
    else:
        print(f"reading crypto rows from {a.dataset} ...")
        X, y, dates, syms = load_crypto(Path(a.dataset))
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, X=X, y=y, dates=dates, syms=syms)
        print(f"crypto rows: {len(X):,}  cached to {cache}")
    if not len(X):
        raise SystemExit("no crypto rows")

    order = np.argsort(dates, kind="stable")
    X, y, dates, syms = X[order], y[order], dates[order], syms[order]
    te = dates > TRAIN_END
    yt = y[te]
    print(f"holdout crypto rows: {int(te.sum()):,} from {dates[te][0]} to {dates[te][-1]}")

    share = {c: round(float((yt == i).mean()), 4) for i, c in enumerate(CLASSES)}
    majority = max(share, key=share.get)

    # What brain-v2-context actually did on this slice, recomputed from its artifact.
    m = json.loads((MODEL / "model.json").read_text(encoding="utf-8"))
    W = np.asarray(m["weights"], dtype=np.float64)
    mu = np.asarray(m["standardisation"]["mean"], dtype=np.float64)
    sd = np.asarray(m["standardisation"]["sd"], dtype=np.float64)
    Z = (np.where(np.isnan(X[te]), mu, X[te]) - mu) / sd
    yp = (np.hstack([Z, np.ones((len(Z), 1))]) @ W).argmax(axis=1)

    acc = float((yt == yp).mean())
    always_up = float((yt == CLASSES.index("UP")).mean())
    mix = {c: int((yp == i).sum()) for i, c in enumerate(CLASSES)}
    recall = {c: (round(float((yp[yt == i] == i).mean()), 4) if (yt == i).any() else None)
              for i, c in enumerate(CLASSES)}

    verdict = (
        "the crypto result is NOT explained by the UP collapse"
        if acc > always_up + 0.01 else
        "the crypto result is largely the always-UP baseline and does not support a "
        "crypto-specialist hypothesis")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "crypto-evidence-v1",
        "question": "is brain-v2-context's 0.5143 on crypto real, or the UP collapse landing on a "
                    "market that happened to rise",
        "dataset": {"dir": str(a.dataset), "prefix": "examples-v4-context",
                    "cryptoRowsTotal": int(len(X)),
                    "holdoutRows": int(te.sum()),
                    "holdoutFrom": str(dates[te][0]), "holdoutTo": str(dates[te][-1]),
                    "distinctSymbols": int(len(set(syms[te].tolist()))),
                    "distinctDecisionDates": int(len(set(dates[te].tolist()))),
                    "effectiveIndependentWindows": int(round(int(te.sum()) / 20))},
        "classShare": share, "majorityClass": majority,
        "alwaysUpBaseline": round(always_up, 4),
        "modelOnCrypto": {"accuracy": round(acc, 4), "predictedMix": mix, "recall": recall},
        "accuracyMinusAlwaysUp": round(acc - always_up, 4),
        "holdoutPristine": False,
        "exposureNote": "this window was scored by the recorded walk-forward experiments; it is "
                        "diagnostic, never independent evidence",
        "verdict": verdict,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\nclass share on crypto holdout: {share}  (majority {majority})")
    print(f"always-UP baseline: {always_up:.4f}")
    print(f"brain-v2-context on crypto: {acc:.4f}  mix {mix}  recall {recall}")
    print(f"accuracy - alwaysUP: {acc - always_up:+.4f}")
    print(f"\n{verdict}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
