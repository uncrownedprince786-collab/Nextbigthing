"""One bounded non-linear experiment: logistic gradient boosting over depth-2 trees, numpy only.

    python tools/research/boost_experiment.py [--selftest] [--inspect] [--out FILE]

**Pre-registered in this docstring before any number from this run was seen, and committed before
the run.** The model, its hyperparameters, the rows, the folds, the controls, the resource limits
and the five acceptance criteria below were fixed here first. Nothing in this file tunes anything.

Why this experiment exists
--------------------------
`eligible_set_experiment_v2` measured the corrected two-output linear softmax family on the whole
frozen universe and failed all five criteria (mean margin -0.0527, 0 of 6 folds, worst -0.0960);
`binary_context_experiment_v2` failed the same five on the crypto slice (-0.0519). Those two runs
are what the claim "the linear family has been measured and fails" now rests on -- the earlier
three-logit artifacts cannot carry it, because their output width did not match their own target.
Every axis that is not the functional form has been tested and exonerated in turn: label, band,
horizon, class balance, optimizer, feature count, capacity control, objective and eligible set.
**The one property every run in the chain has shared is linearity**, and that is the variable this
run changes: exactly one thing differs from `eligible_set_experiment_v2`, the model.

The single changed variable
----------------------------
The model. `fit_weighted`'s linear softmax over 45 x 2 weights becomes **logistic gradient
boosting over depth-2 decision trees implemented in numpy**, so the decision boundary can be any
function the trees can express and is no longer constrained to a hyperplane in feature space.
Everything else -- dataset, quarantine, rows, target, features, fold rule, embargo, preprocessing
order, class weights, seed, shuffled-label control, bootstrap, majority reference and the five
criteria with their thresholds -- is imported from or held exactly as `eligible_set_experiment_v2`
held them, which is what makes the two runs comparable and isolates the functional form.

Fixed before the run (not tunable at run time)
-----------------------------------------------
* **Rounds** 300, **learning rate** 0.05, **depth** 2 (root split plus one split per child, at most
  4 leaves), **minimum rows per child** 500, **L2 on leaf values** 1.0, **gamma** 0.0, **leaf
  clipping** +/-1.0, **histogram bins** 128 quantile edges per feature computed on the **training
  fold only**, logistic loss with gradient `w(p - y)` and hessian `w p (1-p)`, leaf value
  `-G/(L + 1)`, base score 0.0 (the class-balanced weighted prior is 0.5), **no early stopping and
  no hyperparameter search of any kind**. A second configuration of any of these is a different
  experiment and is not run on these holdouts.
* **Class weights** `n/(2 n_c)` over the two classes, mean 1, the same `class_weights` the linear
  predecessor used, so the balance is identical.
* **Determinism.** The fit has no random component: no subsampling, ties broken by first
  occurrence. `SEED = 20261015` enters through the shuffled control (`SEED + 1000 + testYear`) and
  the bootstrap (`SEED + 77`), exactly as in the predecessor.

Correctness gates (`--selftest`, also run automatically before any real row is read)
------------------------------------------------------------------------------------
There is no reference library to compare against -- deliberately, because `requirements.txt` is
import-guarded by `tests/test_brain.py` and is inside `REPLAY_CODE`, so adding a dependency would
flip every previously sealed worker run to untrusted. The implementation is therefore checked
against problems with known answers instead. The cases are chosen so the exact pre-registered
configuration can genuinely learn them and held-out accuracy is scored on rows the fit never saw:

* **Interaction (2-bit XOR parity, exactly two informative columns and no noise columns):**
  boosting must reach held-out accuracy >= 0.98 while a plain linear logistic fit on the same rows
  must stay <= 0.65 -- the harness expresses a non-linear boundary the linear family provably
  cannot, and the linear control behaves. (A first draft reused 6 noise columns and a 3-bit parity
  case; that draft was wrong for two reasons now fixed: with balanced labels a greedy depth-2 root
  has zero gain on every parity column but small positive gain on noise columns, so the root split
  could land on noise and the case was a coin flip, and 3-bit parity is unreachable at depth 2 by
  construction. A correct harness must not be gated on cases its own fixed capacity cannot express.)
* **Interaction (XOR over two continuous informative columns plus six noise columns):** boosting
  must reach held-out accuracy >= 0.98 and must beat the held-out majority by >= 0.20 while the
  linear control must not beat that majority by more than 0.02 -- the non-linear signal dominates
  the noise columns, which cannot win the split search, and the linear family cannot express it.
* **Linearly separable (axis-aligned union):** both the boosting fit and the linear logistic fit
  must reach >= 0.99 -- the harness is not blind to a linear signal.
* **Shuffled labels:** fitted on permuted labels, held-out accuracy must stay within 0.05 of its
  own majority -- the train-to-test path does not leak test rows into fitting. The control is fit
  with weights derived from the *permuted* labels, never the original ones.
* **Determinism:** the same fit twice must produce bit-identical predictions.

A failed selftest writes nothing and exits non-zero before any repository row is read; a passed
selftest is recorded in the artifact. `tests/test_boost_experiment.py` runs the selftest and the
per-repair regressions in CI, so the gate is durable rather than a one-off manual step.

Resource limits, declared before the run
-----------------------------------------
**A conservative peak-RSS ceiling and <= 45 minutes of fitting time** for the whole run (six folds,
candidate and control). The ceiling is measured at process start from the machine's actually
available physical memory (about 4 GB, and less where other work would be crowded out) rather than
a fixed 16 GB that this machine could not reach without swapping; it is enforced *during* a fit by
sampling the peak working set every few rounds, not only after a fold. Exceeding either limit
stops safely, writes `resourceLimitExceeded` with **no verdict** plus a resumable checkpoint, and
exits non-zero. A partial result reported as a result is the failure this limit exists to prevent.

Acceptance, fixed before the run
---------------------------------
The **same five criteria** as `binary_context_experiment` and `eligible_set_experiment`, so the
three runs are comparable and this one is not judged by a different bar:

* **C1** mean margin > 0. **C2** folds beating their own majority >= `min(4, foldsScored)`.
* **C3** no fold where one class is predicted on > 0.70 of rows while actually under half.
* **C4** the block-bootstrap 95% interval for (candidate margin - shuffled-control margin) has
  `p2_5 > 0`. **C5** the worst fold's margin >= -0.05.

Reported but **not** pass criteria, because they are diagnostics of where an effect lives rather
than whether the run succeeds: per-market pooled metrics, crypto-vs-rest, per-regime margins,
per-class recall, per-feature gain shares, and the train-versus-holdout margin gap (the
generalisation gap `binary_context_experiment_v2` named as its own next question).

Pre-declared reading of the outcome
-------------------------------------
* Passes all five: a candidate, not a GO. Reproduce in a fresh process before calling it anything
  else, and re-read every criterion in the artifact rather than the verdict line.
* Fails: **one** bounded non-linear configuration has failed on holdouts that every family in this
  chain has already been measured against. That is a recorded NO-GO for *this configuration*, and
  it must not be written as "non-linear models do not work" any more than the three-logit runs
  could be written as "the linear family is exhausted". **The next step after a failure is not a
  second configuration scored on these same years** -- that is tuning on seen data, which the whole
  chain exists to refuse. It is fresh data (sessions after 2026-09-25) or a different question.
* Whatever the outcome: a NO-GO is preserved as a NO-GO, no threshold moves after any metric is
  seen, and the exposure is disclosed in the artifact: these years and this universe were examined
  by every earlier run, so this is a correction-of-record measurement, not a pristine one.

Fidelity notes
--------------
The rows come from `.cache/foundation/universe_slice.npz`, the exact bytes `eligible_set_experiment`
built, so the data path is shared rather than rebuilt. That cache is not trusted because it exists:
`--verify-data` re-derives a row digest from the nine frozen `examples-v4-context-*.jsonl.gz` files
after checking every one of them against the sha256 and byte size in
`data/foundation/dataset/dataset_freeze_v4_context.json`, and compares it to the digest of the same
rows read out of the cache. The result (both digests, the source-manifest digest, the cache file's
own sha256 and a match flag) is recorded in `data/foundation/dataset/universe_slice_integrity.json`
and carried into the artifact; a mismatch stops the run rather than being papered over. Binning,
imputation and standardisation are fit on the training fold only, and the test fold is binned with
the training fold's own edges -- quantile edges computed from test rows would be the leak this
protocol exists to exclude. `trainLogLoss` here is the class-weighted logistic loss and is not
comparable to `finalLoss` in the linear artifacts, which is that optimizer's own last averaged
loss. Nothing here is a promotion.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from baseline_experiment import CLASSES, EMBARGO, REGIMES, SEED  # noqa: E402
from balanced_experiment import DEGENERATE_SHARE, MIN_FOLDS_WON, class_counts  # noqa: E402
from eligible_set_experiment import (  # noqa: E402
    ALL_FEATURES,
    BINARY_CLASSES,
    BINARY_DOWN,
    BINARY_UP,
    CACHE,
    DATASET,
    FLAT,
    UP,
    MIN_MARKET_ROWS,
    MIN_TEST,
    MIN_TRAIN,
    REGIME_LOSS,
    REGIME_MIN_ROWS,
    WORST_FOLD_FLOOR,
    class_weights,
    load_or_build,
    prep,
)
from stationarity import BLOCK_DAYS, BOOTSTRAP, block_bootstrap, over_majority  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "boost_experiment.json"
PREDECESSOR = ROOT / "data" / "foundation" / "dataset" / "eligible_set_experiment_v2.json"
PREDECESSOR_CRYPTO = ROOT / "data" / "foundation" / "dataset" / "binary_context_experiment_v2.json"

VERSION = "boost-v1"
# Fixed before the run. Every one of these is a different experiment if changed.
ROUNDS = 300
BOOST_LR = 0.05
MAX_DEPTH = 2
MIN_CHILD = 500
LAMBDA = 1.0
GAMMA = 0.0
MAX_DELTA = 1.0
BINS = 128
BASE_SCORE = 0.0
# Declared before the run. The RSS ceiling is filled in at process start from real free memory.
FIT_SECONDS_LIMIT = 45 * 60
RSS_LIMIT_CAP_MB = 4 * 1024
RSS_LIMIT_FLOOR_MB = 768
# Selftest gates, declared before the run (restored to the docstring contract).
ST_BOOST_MIN_ACC = 0.98
ST_LINEAR_MAX_ACC = 0.65
ST_MARGIN_MIN = 0.20
ST_LINEAR_MARGIN_MAX = 0.02
ST_SEPARABLE_MIN_ACC = 0.99
ST_SHUFFLE_TOL = 0.05


class ResourceLimitExceeded(RuntimeError):
    """Raised *during* a fit when the declared time or memory budget is crossed."""


class Budget:
    """The declared resource envelope, checked *during* a fit and after each fold.

    `check` raises `ResourceLimitExceeded` the moment the wall clock or the peak working set crosses
    the declared ceiling, so a single long fold cannot silently run past the whole budget.
    """

    def __init__(self, started: float, seconds_limit: int, rss_limit_mb: int):
        self.started = started
        self.seconds_limit = seconds_limit
        self.rss_limit_mb = rss_limit_mb

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def check(self, note: str) -> str:
        used = self.elapsed()
        rss = peak_rss_mb()
        if used > self.seconds_limit:
            raise ResourceLimitExceeded(
                f"{note}: fitting time {used:.0f}s exceeds the declared {self.seconds_limit}s "
                f"limit")
        if rss is not None and rss > self.rss_limit_mb:
            raise ResourceLimitExceeded(
                f"{note}: peak RSS {rss} MB exceeds the declared {self.rss_limit_mb} MB limit")
        print(f"  {note}: {used:.0f}s elapsed, peak RSS "
              f"{rss if rss is not None else 'unknown'} MB", flush=True)
        return note


def available_mb():
    """Physical memory available to new allocations in MB, or None where it cannot be read."""
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMSTATUS(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            st = MEMSTATUS()
            st.dwLength = ctypes.sizeof(MEMSTATUS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullAvailPhys // (1024 * 1024))
        except Exception:
            return None
    else:
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) // 1024
        except Exception:
            return None
    return None


def dynamic_rss_limit_mb():
    """A peak-RSS ceiling that cannot be reached only by swapping on this machine.

    Conservative by construction: at most 4 GB, and at most the available physical memory minus a
    reserve for the other processes on this box, with a floor so a nearly-full machine still fails
    loudly instead of at a nonsensical zero.
    """
    avail = available_mb()
    if avail is None:
        return RSS_LIMIT_CAP_MB
    return int(min(RSS_LIMIT_CAP_MB, max(RSS_LIMIT_FLOOR_MB, avail - 256)))



def peak_rss_mb():
    """Peak resident set size in MB, or None where it cannot be read. `resource` is Unix only."""
    try:
        import resource as _resource

        v = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
        return int(v / (1024 * 1024)) if sys.platform == "darwin" else int(v // 1024)
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            buf = PMC()
            buf.cb = ctypes.sizeof(PMC)
            h = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(buf), buf.cb):
                return int(buf.PeakWorkingSetSize // (1024 * 1024))
        except Exception:
            return None
    return None


# Filled at import and refreshed at run start from real free memory; see `dynamic_rss_limit_mb`.
RSS_LIMIT_MB = dynamic_rss_limit_mb()

FREEZE_MANIFEST = ROOT / "data" / "foundation" / "dataset" / "dataset_freeze_v4_context.json"
INTEGRITY_OUT = ROOT / "data" / "foundation" / "dataset" / "universe_slice_integrity.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _feature_row(pit):
    """Exactly `eligible_set_experiment.build_with_labels`' per-feature conversion, mirrored so a
    digest of the frozen sources can be compared to a digest of the cache they were built into.
    `tests/test_boost_experiment.py` pins this mirror against that builder on sample rows."""
    p = pit.get("f") or {}
    c = (pit.get("ctx") or {}).get("f") or {}
    row, ok = [], True
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
    return row, ok


def _digest_row(h, row, label, date, market, flagged):
    h.update(np.asarray(row, dtype="<f8").tobytes())
    h.update(np.asarray([label], dtype="<i8").tobytes())
    h.update(str(date).encode("utf-8"))
    h.update(b"\x00")
    h.update(str(market).encode("utf-8"))
    h.update(b"\x00")
    h.update(b"\x01" if flagged else b"\x00")


def source_row_digest(ds: Path) -> dict:
    """Stream the frozen sources in parse order and hash every kept row's (features, label, date,
    market, flagged). O(1) extra memory: nothing but the running hash and counters is held."""
    h = hashlib.sha256()
    kept = dropped = 0
    counts = np.zeros(len(CLASSES), dtype=np.int64)
    for f in sorted(Path(ds).glob("examples-v4-context-*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                pit = r.get("pit") or {}
                o = r.get("outcome") or {}
                if not pit.get("f") or o.get("label20") not in CLASSES or not o.get("mature20"):
                    dropped += 1
                    continue
                row, ok = _feature_row(pit)
                if not ok:
                    dropped += 1
                    continue
                dq = r.get("dataQuality") or {}
                flagged = bool(any(dq.values())) if dq else False
                label = CLASSES.index(o["label20"])
                _digest_row(h, row, label, r["asOf"], r.get("assetType") or "unknown", flagged)
                counts[label] += 1
                kept += 1
    return {"digest": h.hexdigest(), "kept": kept, "dropped": dropped,
            "labelCounts": {CLASSES[i]: int(counts[i]) for i in range(len(CLASSES))}}


def cache_row_digest(d: dict) -> dict:
    """The same digest computed from the built cache, in its stored (parse) order."""
    h = hashlib.sha256()
    X, y, dates, market, flagged = d["X"], d["y"], d["dates"], d["market"], d["flagged"]
    for i in range(len(y)):
        _digest_row(h, X[i], int(y[i]), dates[i], market[i], bool(flagged[i]))
    counts = np.bincount(np.asarray(y, dtype=np.int64), minlength=len(CLASSES))
    return {"digest": h.hexdigest(), "kept": int(len(y)),
            "labelCounts": {CLASSES[i]: int(counts[i]) for i in range(len(CLASSES))}}


def verify_data(ds: Path, cache: Path) -> dict:
    """Check the frozen sources against the freeze manifest, then check the derived cache against
    those sources. Records both digests; never mutates the sources or the cache."""
    manifest = json.loads(FREEZE_MANIFEST.read_text(encoding="utf-8"))
    declared = manifest["files"]
    files, all_match = [], True
    for name, meta in sorted(declared.items()):
        p = Path(ds) / name
        actual = {"name": name, "present": p.exists(), "expectedBytes": meta["bytes"],
                  "expectedSha256": meta["sha256"]}
        if p.exists():
            actual["bytes"] = p.stat().st_size
            actual["sha256"] = sha256_file(p)
            actual["matches"] = bool(actual["bytes"] == meta["bytes"]
                                     and actual["sha256"] == meta["sha256"])
        else:
            actual["matches"] = False
        all_match = all_match and actual["matches"]
        files.append(actual)
    src = source_row_digest(ds) if all_match else None
    cac = None
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        d = {k: z[k] for k in ("X", "y", "dates", "market", "flagged")}
        cac = cache_row_digest(d)
        del z, d
    match = bool(src is not None and cac is not None and src["digest"] == cac["digest"])
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "freezeManifest": FREEZE_MANIFEST.name,
        "freezeVersion": manifest.get("version"), "repoHead": manifest.get("repoHead"),
        "manifestDigest": sha256_file(FREEZE_MANIFEST),
        "sourceFiles": files, "allSourcesMatch": all_match,
        "sourceRowDigest": src, "cacheRowDigest": cac,
        "cacheFile": {"name": cache.name, "bytes": cache.stat().st_size,
                      "sha256": sha256_file(cache)} if cache.exists() else None,
        "cacheMatchesSources": match,
        "note": "the cache is used only if its row digest equals the digest re-derived from the "
                "manifest-verified frozen sources; a mismatch stops the run rather than being "
                "trusted, and nothing here mutates the frozen dataset",
    }


def ensure_integrity(ds: Path, cache: Path) -> dict:
    """A current integrity record for the cache, reused only when it still matches disk.

    Recomputing re-derives row digests from the frozen sources, so it is not called on every run:
    the recorded cache sha256 and manifest digest must still agree. A mismatch is fatal, not
    papered over -- the run refuses to fit on rows whose provenance it cannot establish.
    """
    if INTEGRITY_OUT.exists():
        rec = json.loads(INTEGRITY_OUT.read_text(encoding="utf-8"))
        same_cache = (rec.get("cacheFile") or {}).get("sha256") == sha256_file(cache)
        same_manifest = rec.get("manifestDigest") == sha256_file(FREEZE_MANIFEST)
        if same_cache and same_manifest and rec.get("cacheMatchesSources"):
            print(f"integrity record reused: {INTEGRITY_OUT.name}", flush=True)
            return rec
    print("verifying the frozen sources and the derived cache (re-derives row digests) ...",
          flush=True)
    rec = verify_data(ds, cache)
    INTEGRITY_OUT.parent.mkdir(parents=True, exist_ok=True)
    INTEGRITY_OUT.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    if not (rec["allSourcesMatch"] and rec["cacheMatchesSources"]):
        raise SystemExit(
            "frozen-source/cache integrity check FAILED; refusing to fit on unverified rows. "
            f"See {INTEGRITY_OUT}")
    print(f"integrity verified; wrote {INTEGRITY_OUT}", flush=True)
    return rec


def checkpoint_paths(out: Path):
    return out.with_suffix(".checkpoint.json"), out.with_suffix(".checkpoint.npz")


def write_checkpoint(out: Path, folds, pool, reason: str) -> Path:
    """Persist completed folds and their pooled rows so the same experiment can resume later."""
    jp, zp = checkpoint_paths(out)
    arrays = {k: (np.concatenate(v) if v else np.asarray([], dtype=np.int64))
              for k, v in pool.items()}
    jp.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(zp, **arrays)
    jp.write_text(json.dumps({
        "version": VERSION, "reason": reason,
        "completedYears": [f["testYear"] for f in folds],
        "folds": folds, "arrays": zp.name}, indent=1), encoding="utf-8")
    return jp


def load_checkpoint(out: Path):
    """Completed folds and pooled rows from a previous run, or empty structures when none exist."""
    jp, zp = checkpoint_paths(out)
    empty = {"y": [], "yp": [], "yc": [], "dates": [], "market": [], "gain": []}
    if not (jp.exists() and zp.exists()):
        return [], empty
    rec = json.loads(jp.read_text(encoding="utf-8"))
    z = np.load(zp, allow_pickle=True)
    pool = {k: ([z[k]] if k in z.files and z[k].size else []) for k in empty}
    return rec.get("folds", []), pool


def bin_edges(Xtr: np.ndarray) -> np.ndarray:
    """Quantile edges per feature from the training fold only. Shape (features, BINS - 1)."""
    q = np.linspace(0.0, 1.0, BINS + 1)[1:-1]
    e = np.quantile(Xtr, q, axis=0)
    return np.ascontiguousarray(e.T)


def digitize(X: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Bin index per row per feature, 0..BINS - 1, using the training fold's edges."""
    out = np.empty(X.shape, dtype=np.uint8)
    for f in range(X.shape[1]):
        out[:, f] = np.searchsorted(edges[f], X[:, f], side="right")
    return out


def best_split(Bm, idx, g, h):
    """Best (feature, bin) by the standard logistic-boosting gain over `idx` rows, or None.

    Left is `bin <= b`. Splits that would leave fewer than MIN_CHILD rows on either side are
    excluded, and a feature with no eligible split contributes nothing. With the declared
    `GAMMA = 0.0` only a **strictly positive** gain is accepted: when no split beats gamma the node
    stays a leaf, so a split that does not reduce the loss is never taken. Ties break by first
    occurrence (feature, then bin), matching the per-feature scan this was declared as -- the
    histogram search below is a bit-identical reformulation of that scan, checked by
    `tests/test_boost_experiment.py`.
    """
    m = len(idx)
    if m < 2 * MIN_CHILD:
        return None
    gb = g[idx]
    hb = h[idx]
    G = float(gb.sum())
    L = float(hb.sum())
    base = G * G / (L + LAMBDA)
    nfeat = Bm.shape[1]
    best_f, best_b, best_gain = None, None, -np.inf
    chunk = 4
    for c0 in range(0, nfeat, chunk):
        c1 = min(c0 + chunk, nfeat)
        k = c1 - c0
        codes = Bm[idx, c0:c1].astype(np.int32)
        codes += np.arange(k, dtype=np.int32) * BINS
        flat = codes.ravel()
        nb = k * BINS
        cg = np.bincount(flat, weights=np.repeat(gb, k), minlength=nb).reshape(k, BINS)
        ch = np.bincount(flat, weights=np.repeat(hb, k), minlength=nb).reshape(k, BINS)
        cc = np.bincount(flat, minlength=nb).reshape(k, BINS).astype(np.float64)
        cl = np.cumsum(cg, axis=1)
        hl = np.cumsum(ch, axis=1)
        nl = np.cumsum(cc, axis=1)
        cr = G - cl
        hr = L - hl
        nr = m - nl
        ok = (nl >= MIN_CHILD) & (nr >= MIN_CHILD)
        gain = 0.5 * (cl * cl / (hl + LAMBDA) + cr * cr / (hr + LAMBDA) - base) - GAMMA
        gain = np.where(ok, gain, -np.inf)
        r, b = divmod(int(np.argmax(gain)), BINS)
        v = float(gain[r, b])
        if v > best_gain:
            best_f, best_b, best_gain = c0 + int(r), int(b), v
    if best_f is None or not np.isfinite(best_gain) or best_gain <= GAMMA:
        return None
    return (best_f, best_b), best_gain


def build_tree(Bm, idx, g, h, depth, tval):
    """One tree of at most MAX_DEPTH splits. Writes this tree's contribution into `tval`."""
    best = best_split(Bm, idx, g, h) if depth < MAX_DEPTH else None
    if best is None:
        G = float(g[idx].sum())
        L = float(h[idx].sum())
        v = float(np.clip(-G / (L + LAMBDA), -MAX_DELTA, MAX_DELTA))
        tval[idx] = v
        return {"split": None, "gain": None, "value": v}
    (f, b), gain = best
    m = Bm[idx, f] <= b
    node = {"split": (f, b), "gain": gain}
    node["L"] = build_tree(Bm, idx[m], g, h, depth + 1, tval)
    node["R"] = build_tree(Bm, idx[~m], g, h, depth + 1, tval)
    return node


def leaf_rules(node, conds=()):
    """Flatten a tree into (conditions, value) leaves. A condition is (feature, bin, isLeft)."""
    if node["split"] is None:
        return [(list(conds), node["value"])]
    f, b = node["split"]
    return (leaf_rules(node["L"], conds + ((f, b, True),))
            + leaf_rules(node["R"], conds + ((f, b, False),)))


def walk_gains(node, out):
    if node["split"] is None:
        return
    f = node["split"][0]
    out[f] += node["gain"]
    walk_gains(node["L"], out)
    walk_gains(node["R"], out)


def apply_trees(Bm, trees):
    """Sum the fitted trees over binned rows. Every row must reach exactly one leaf per tree."""
    F = np.zeros(len(Bm), dtype=np.float64)
    ones = np.ones(len(Bm), dtype=bool)
    for rules in trees:
        out = np.zeros(len(Bm), dtype=np.float64)
        covered = np.zeros(len(Bm), dtype=bool)
        for conds, val in rules:
            m = ones.copy()
            for (f, b, is_left) in conds:
                t = Bm[:, f] <= b
                m &= t if is_left else ~t
            out[m] = val
            covered |= m
        if not covered.all():
            raise AssertionError("a row reached no leaf; the rules do not cover the space")
        F += out
    return F * BOOST_LR


def fit_boost(Xtr, ytr, w, Xte, budget=None):
    """Boosting fit on the training rows, returning the model and both score vectors.

    `Xtr`/`Xte` are already prepped by `prep` (imputed and standardised on the training fold).
    `w` is the per-row weight vector (see `row_weights`). If `budget` is given, its `check` is
    called during the round loop, so the declared time and memory limits are enforced *inside* a
    fit rather than only after a fold returns -- a single fold at the largest test year does not
    fit inside the whole budget otherwise.
    """
    n, n_feat = Xtr.shape
    edges = bin_edges(Xtr)
    Btr = digitize(Xtr, edges)
    Bte = digitize(Xte, edges)
    y = ytr.astype(np.float64)
    wv = np.asarray(w, dtype=np.float64)
    F = np.full(n, BASE_SCORE, dtype=np.float64)
    tval = np.empty(n, dtype=np.float64)
    row_idx = np.arange(n)
    trees, gains = [], np.zeros(n_feat, dtype=np.float64)
    for r in range(ROUNDS):
        if budget is not None and r % 25 == 0:
            budget.check(f"round {r} of {ROUNDS} on {n:,} rows")
        p = 1.0 / (1.0 + np.exp(-np.clip(F, -60.0, 60.0)))
        g = wv * (p - y)
        h = wv * p * (1.0 - p)
        tval[:] = 0.0
        node = build_tree(Btr, row_idx, g, h, 0, tval)
        walk_gains(node, gains)
        F += BOOST_LR * tval
        trees.append(leaf_rules(node))
    return {"edges": edges, "trees": trees, "gains": gains}, F, apply_trees(Bte, trees)


def fit_logistic(Xtr, ytr, w, Xte, steps=400, lr=0.5):
    """Plain linear logistic fit, used only by the selftest as the linear control.

    Same class-weighted loss shape as `fit_weighted` (L2 = 1e-4, mean-1 weights), so a selftest
    that says "linear cannot fit this" is saying it about the family this chain actually ships.
    """
    n = len(ytr)
    y = ytr.astype(np.float64)
    wv = np.asarray(w, dtype=np.float64)
    W = np.zeros(Xtr.shape[1] + 1, dtype=np.float64)
    Xb = np.hstack([Xtr, np.ones((n, 1))])
    for _ in range(steps):
        z = np.clip(Xb @ W, -60.0, 60.0)
        p = 1.0 / (1.0 + np.exp(-z))
        err = wv * (p - y)
        W -= lr * (Xb.T @ err + 1e-4 * W) / n
    Xteb = np.hstack([Xte, np.ones((len(Xte), 1))])
    return (Xteb @ W) > 0.0


def row_weights(ytr: np.ndarray) -> np.ndarray:
    """Per-row class-balanced weights with mean 1: `class_weights` gives one value per class,
    which is what `fit_weighted` expects; the boosting loss needs one value per row."""
    return class_weights(ytr)[ytr]


def shuffled_control_target(ytr: np.ndarray, rng) -> np.ndarray:
    """The shuffled-label control target: the training labels permuted within the training fold.

    The weights for the control fit must be derived from *this* permuted vector, not from the
    original labels -- otherwise the control is fit with the real class balance and its margin is
    not the null the criteria compare against. Kept as one function so the property is testable.
    """
    return rng.permutation(ytr)


def _score(y, pred):
    acc = float((y == pred).mean())
    maj = float(np.bincount(y, minlength=2).max() / len(y))
    return acc, maj, acc - maj


def selftest() -> dict:
    """The five declared gates. Synthetic data only: no repository row is read here."""
    checks = {}
    rng = np.random.default_rng(SEED)
    n = 4000

    def split(X, y):
        i = rng.permutation(n)
        X, y = X[i], y[i]
        return X[:3000], X[3000:], y[:3000], y[3000:]

    # 1: XOR parity (2-bit) over exactly two informative columns, no noise. A greedy depth-2 tree
    # can express XOR exactly, so held-out accuracy must saturate while the linear control cannot.
    xb = rng.integers(0, 2, size=(n, 2))
    X, y = xb.astype(np.float64), (xb.sum(axis=1) % 2).astype(np.int64)
    Xtr, Xte, ytr, yte = split(X, y)
    Ztr, Zte = prep(Xtr, Xte)
    w = row_weights(ytr)
    _, _, Fte = fit_boost(Ztr, ytr, w, Zte)
    boost_acc, boost_maj, boost_over = _score(yte, (Fte > 0).astype(np.int64))
    lin_acc, _, _ = _score(yte, fit_logistic(Ztr, ytr, w, Zte))
    checks["xor_boostingAccuracy"] = round(boost_acc, 4)
    checks["xor_linearAccuracy"] = round(lin_acc, 4)
    checks["xor_pass"] = bool(boost_acc >= ST_BOOST_MIN_ACC and lin_acc <= ST_LINEAR_MAX_ACC)

    # 2: XOR over two continuous informative columns plus six noise columns. Non-additive, so a
    # linear boundary cannot represent it (the control sits on its majority), and the informative
    # columns carry enough signal that noise columns cannot win the split search.
    X = rng.normal(0.0, 1.0, size=(n, 8))
    y = ((X[:, 0] > 0.0) ^ (X[:, 1] > 0.0)).astype(np.int64)
    Xtr, Xte, ytr, yte = split(X, y)
    Ztr, Zte = prep(Xtr, Xte)
    w = row_weights(ytr)
    _, _, Fte = fit_boost(Ztr, ytr, w, Zte)
    inter_acc, inter_maj, inter_over = _score(yte, (Fte > 0).astype(np.int64))
    lin_acc, lin_maj, lin_over = _score(yte, fit_logistic(Ztr, ytr, w, Zte))
    checks["interaction_boostingAccuracy"] = round(inter_acc, 4)
    checks["interaction_boostingOverMajority"] = round(inter_over, 4)
    checks["interaction_linearAccuracy"] = round(lin_acc, 4)
    checks["interaction_linearOverMajority"] = round(lin_over, 4)
    checks["interaction_pass"] = bool(
        inter_acc >= ST_BOOST_MIN_ACC and inter_over >= ST_MARGIN_MIN
        and lin_over <= ST_LINEAR_MARGIN_MAX)

    # 3: a linearly separable set (a single axis-aligned threshold) must be fitted by both, or the
    # harness is blind to a linear signal.
    X = rng.normal(0.0, 1.0, size=(n, 6))
    y = (X[:, 0] > 0.0).astype(np.int64)
    Xtr, Xte, ytr, yte = split(X, y)
    Ztr, Zte = prep(Xtr, Xte)
    w = row_weights(ytr)
    _, _, Fte = fit_boost(Ztr, ytr, w, Zte)
    sep_boost, _, _ = _score(yte, (Fte > 0).astype(np.int64))
    sep_lin, _, _ = _score(yte, fit_logistic(Ztr, ytr, w, Zte))
    checks["separable_boostingAccuracy"] = round(sep_boost, 4)
    checks["separable_linearAccuracy"] = round(sep_lin, 4)
    checks["separable_pass"] = bool(sep_boost >= ST_SEPARABLE_MIN_ACC
                                    and sep_lin >= ST_SEPARABLE_MIN_ACC)

    # 4: shuffled labels must not beat the held-out majority -- the test path does not leak. The
    # control is fit with weights derived from the permuted labels, never the original ones.
    X = rng.normal(0.0, 1.0, size=(n, 6))
    y = (X[:, 0] + X[:, 1] > 0.0).astype(np.int64)
    Xtr, Xte, ytr, yte = split(X, y)
    Ztr, Zte = prep(Xtr, Xte)
    y_control = shuffled_control_target(ytr, rng)
    _, _, Fc = fit_boost(Ztr, y_control, row_weights(y_control), Zte)
    acc, maj, over = over_majority(yte, (Fc > 0).astype(np.int64))
    checks["shuffled_accuracy"] = round(acc, 4)
    checks["shuffled_majority"] = round(maj, 4)
    checks["shuffled_overMajority"] = round(over, 4)
    checks["shuffled_pass"] = bool(over <= ST_SHUFFLE_TOL)

    # 5: determinism -- the same fit twice must be bit-identical.
    X, y = Xtr, ytr
    w = row_weights(ytr)
    _, _, F1 = fit_boost(Ztr, ytr, w, Zte)
    _, _, F2 = fit_boost(Ztr, ytr, w, Zte)
    checks["deterministic"] = bool(np.array_equal(F1, F2))

    checks["passed"] = bool(
        checks["xor_pass"] and checks["interaction_pass"] and checks["separable_pass"]
        and checks["shuffled_pass"] and checks["deterministic"])
    return checks



def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--selftest", action="store_true",
                    help="run the declared synthetic correctness gates and exit; read no data")
    ap.add_argument("--inspect", action="store_true",
                    help="report markets/labels/quarantine and the fold plan; fit nothing")
    ap.add_argument("--verify-data", action="store_true",
                    help="verify the frozen sources against the freeze manifest and the derived "
                         "cache against those sources; write the integrity record and exit")
    ap.add_argument("--resume", action="store_true",
                    help="reuse folds already completed in a previous run's checkpoint")
    a = ap.parse_args()

    if a.selftest:
        st = selftest()
        print(json.dumps(st, indent=1, sort_keys=True))
        return 0 if st["passed"] else 1

    t_run0 = time.monotonic()
    st = selftest()
    if not st["passed"]:
        print("selftest FAILED, refusing to read any row: " + json.dumps(st, sort_keys=True))
        return 1
    print(f"selftest passed ({json.dumps(st, sort_keys=True)[:200]}...)", flush=True)

    global RSS_LIMIT_MB
    RSS_LIMIT_MB = dynamic_rss_limit_mb()

    if a.verify_data:
        v = verify_data(Path(a.dataset), Path(a.cache))
        INTEGRITY_OUT.parent.mkdir(parents=True, exist_ok=True)
        INTEGRITY_OUT.write_text(json.dumps(v, indent=1), encoding="utf-8")
        print(json.dumps({k: v[k] for k in ("allSourcesMatch", "cacheMatchesSources")},
                         sort_keys=True))
        print(f"wrote {INTEGRITY_OUT}")
        return 0 if (v["allSourcesMatch"] and v["cacheMatchesSources"]) else 1

    integrity = ensure_integrity(Path(a.dataset), Path(a.cache))
    print(f"resource ceiling: peak RSS <= {RSS_LIMIT_MB} MB (available now {available_mb()} MB), "
          f"fitting time <= {FIT_SECONDS_LIMIT}s", flush=True)

    d = load_or_build(Path(a.dataset), Path(a.cache))
    Xf, yf, datesf, marketf, flaggedf = d["X"], d["y"], d["dates"], d["market"], d["flagged"]
    if Xf.shape[1] != len(ALL_FEATURES):
        raise SystemExit(f"rows have {Xf.shape[1]} columns, ALL_FEATURES has {len(ALL_FEATURES)}")

    rows_parsed = int(len(flaggedf))
    keep_idx = np.flatnonzero(~flaggedf)
    quarantine_dropped = rows_parsed - int(len(keep_idx))
    keep_idx = keep_idx[np.argsort(datesf[keep_idx], kind="stable")]
    y = yf[keep_idx]
    dates = datesf[keep_idx]
    market = marketf[keep_idx]
    rows_after_quarantine = int(len(keep_idx))
    market_counts = {str(m): int(c) for m, c in zip(*np.unique(market, return_counts=True))}
    print(f"rows parsed {rows_parsed:,}  quarantine dropped {quarantine_dropped:,}"
          f"  kept {rows_after_quarantine:,}")

    if a.inspect:
        keepy = y != FLAT
        udates = np.unique(dates)
        didx = {x: i for i, x in enumerate(udates)}
        pos = np.asarray([didx[x] for x in dates])
        print(f"after dropping FLAT: {int(keepy.sum()):,}  UP "
              f"{float((y[keepy] == UP).mean()):.4f}")
        print("\nfold plan (nothing fitted, nothing written):")
        for cut_year in range(2021, 2027):
            cut = f"{cut_year}-01-01"
            cand = [x for x in udates if x >= cut]
            if not cand:
                continue
            cut_pos = didx.get(cut, didx[cand[0]])
            tr = pos < (cut_pos - EMBARGO)
            te = (dates >= cut) & (dates <= f"{cut_year}-12-31")
            fits = tr.sum() >= MIN_TRAIN and te.sum() >= MIN_TEST
            print(f"  {cut_year}: train {tr.sum():>8,} test {te.sum():>8,}  "
                  f"{'fits' if fits else 'SKIPPED'}")
        return 0

    keepy = y != FLAT
    sel = np.flatnonzero(keepy)
    X = Xf[keep_idx[sel]]
    y = y[sel]
    dates = dates[sel]
    market = market[sel]
    cache_files = list(d["files"])
    dropped_during_parse = d["dropped"]
    del Xf, yf, datesf, marketf, flaggedf, keep_idx, d
    udates = np.unique(dates)
    didx = {x: i for i, x in enumerate(udates)}
    pos = np.asarray([didx[x] for x in dates])
    yb = np.where(y == UP, BINARY_UP, BINARY_DOWN).astype(np.int64)
    assert set(np.unique(yb).tolist()) <= {BINARY_DOWN, BINARY_UP}
    print(f"rows for the binary target: {len(yb):,}  UP {yb.mean():.4f}", flush=True)

    folds, pool = [], {"y": [], "yp": [], "yc": [], "dates": [], "market": [], "gain": []}
    done_years = set()
    if a.resume:
        folds, pool = load_checkpoint(Path(a.out))
        done_years = {f["testYear"] for f in folds}
        if done_years:
            print(f"resuming: folds {sorted(done_years)} already completed", flush=True)
    if "gain" not in pool:
        pool["gain"] = []
    budget = Budget(t_run0, FIT_SECONDS_LIMIT, RSS_LIMIT_MB)
    exhausted = None
    try:
        for cut_year in range(2021, 2027):
            if cut_year in done_years:
                continue
            cut = f"{cut_year}-01-01"
            cand = [d for d in udates if d >= cut]
            if not cand:
                continue
            cut_pos = didx.get(cut, didx[cand[0]])
            tr = pos < (cut_pos - EMBARGO)
            te = (dates >= cut) & (dates <= f"{cut_year}-12-31")
            if tr.sum() < MIN_TRAIN or te.sum() < MIN_TEST:
                continue

            Ztr, Zte = prep(X[tr], X[te])
            if not np.isfinite(Ztr).all() or not np.isfinite(Zte).all():
                raise SystemExit("non-finite value after prep; the imputation path is broken")
            wtr = row_weights(yb[tr])
            model, Ftr, Fte = fit_boost(Ztr, yb[tr], wtr, Zte, budget)
            if Fte.shape != (int(te.sum()),):
                raise SystemExit(f"expected {int(te.sum())} scores, got {Fte.shape}")
            yp = (Fte > 0).astype(np.int64)
            if yp.min() < 0 or yp.max() >= len(BINARY_CLASSES):
                raise SystemExit(f"prediction outside {BINARY_CLASSES}")

            rng = np.random.default_rng(SEED + 1000 + cut_year)
            y_control = shuffled_control_target(yb[tr], rng)
            _, _, Fc = fit_boost(Ztr, y_control, row_weights(y_control), Zte, budget)
            yc = (Fc > 0).astype(np.int64)

            acc, maj, over = over_majority(yb[te], yp)
            acc_c, maj_c, over_c = over_majority(yb[te], yc)
            tr_acc, tr_maj, tr_over = over_majority(yb[tr], (Ftr > 0).astype(np.int64))
            pred_mix = np.bincount(yp, minlength=len(BINARY_CLASSES)) / len(yp)
            act_mix = np.bincount(yb[te], minlength=len(BINARY_CLASSES)) / len(yb[te])
            worst_i = int(pred_mix.argmax())
            degenerate = bool(pred_mix[worst_i] > DEGENERATE_SHARE and act_mix[worst_i] < 0.5)
            rec = {BINARY_CLASSES[c]: round(float((yp[yb[te] == c] == c).mean()), 4)
                   for c in range(len(BINARY_CLASSES))}
            total_gain = float(model["gains"].sum())
            top = sorted(zip(ALL_FEATURES, model["gains"].tolist()), key=lambda kv: -kv[1])[:5]
            test_ll = float(np.mean(np.logaddexp(0.0, Fte) - yb[te] * Fte))
            train_ll = float(np.mean(wtr * (np.logaddexp(0.0, Ftr) - yb[tr] * Ftr)))

            folds.append({"testYear": cut_year, "trainRows": int(tr.sum()),
                          "testRows": int(te.sum()),
                          "trainEnds": str(udates[max(0, cut_pos - EMBARGO - 1)]),
                          "testBegins": str(dates[te][0]), "testEnds": str(dates[te][-1]),
                          "rounds": ROUNDS, "earlyStopped": False,
                          "trainAccuracy": round(tr_acc, 4), "trainMajority": round(tr_maj, 4),
                          "trainMargin": round(tr_over, 4), "trainLogLoss": round(train_ll, 6),
                          "accuracy": acc, "majority": maj, "margin": over,
                          "testLogLoss": round(test_ll, 6),
                          "beatsMajority": bool(over > 0),
                          "shuffledControlAccuracy": acc_c, "shuffledControlMargin": over_c,
                          "candidateMinusControl": round(over - over_c, 4),
                          "predictedMix": class_counts(yp, BINARY_CLASSES),
                          "actualMix": class_counts(yb[te], BINARY_CLASSES),
                          "worstPredictedShare": round(float(pred_mix[worst_i]), 4),
                          "actualShareOfWorstPredicted": round(float(act_mix[worst_i]), 4),
                          "degenerate": degenerate, "perClassRecall": rec,
                          "topFeatureGains": [{"feature": f, "gain": round(g, 4)}
                                              for f, g in top if g > 0],
                          "totalGain": round(total_gain, 4)})
            pool["y"].append(yb[te])
            pool["yp"].append(yp)
            pool["yc"].append(yc)
            pool["dates"].append(dates[te])
            pool["market"].append(market[te])
            pool["gain"].append(model["gains"])
            print(f"  fold {cut_year}: acc {acc:.4f}  majority {maj:.4f}  margin {over:+.4f}  "
                  f"control {over_c:+.4f}  train {tr_over:+.4f}  rounds {ROUNDS}"
                  f"{'  DEGENERATE' if degenerate else ''}", flush=True)
            budget.check(f"after fold {cut_year}")
    except ResourceLimitExceeded as exc:
        exhausted = str(exc)

    def resource_payload(reason: str, checkpoint: Path) -> dict:
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "version": VERSION,
            "question": "does a non-linear decision function on the same 44 features beat its own "
                        "majority out-of-sample where the correctly-shaped linear softmax did not?",
            "selfTest": st,
            "dataIntegrity": integrity,
            "model": {"algorithm": "logistic gradient boosting over depth-2 trees, numpy only",
                      "rounds": ROUNDS, "learningRate": BOOST_LR, "maxDepth": MAX_DEPTH,
                      "minChildRows": MIN_CHILD, "l2Leaf": LAMBDA, "gamma": GAMMA,
                      "bins": BINS},
            "resourceLimitExceeded": {
                "reason": reason,
                "limits": {"fitSeconds": FIT_SECONDS_LIMIT, "peakRssMB": RSS_LIMIT_MB},
                "peakRssMB": peak_rss_mb(),
                "availableMBAtStart": available_mb(),
                "elapsedSeconds": round(time.monotonic() - t_run0, 1)},
            "completedFolds": [f["testYear"] for f in folds],
            "resumableCheckpoint": str(checkpoint.relative_to(ROOT)),
            "verdict": None,
            "note": "the pre-declared resource limits were exceeded, so this run records no "
                    "verdict rather than a partial one. A partial result reported as a result is "
                    "the failure the limit exists to prevent. Completed folds are preserved in the "
                    "checkpoint; `--resume` continues the same pre-registered experiment after the "
                    "resource or implementation problem is corrected.",
            "notAPromotion": "no verdict, no criteria, nothing to read as a result",
        }

    if exhausted:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        ckpt = write_checkpoint(out, folds, pool, exhausted)
        out.write_text(json.dumps(resource_payload(exhausted, ckpt), indent=1), encoding="utf-8")
        print(f"RESOURCE LIMIT: {exhausted}")
        print(f"completed folds {[f['testYear'] for f in folds]}; checkpoint {ckpt}")
        print(f"wrote {out} with no verdict")
        return 1
    if not folds:
        raise SystemExit("no fold met the pre-declared minimums")

    fit_seconds = round(time.monotonic() - t_run0, 1)
    peak_rss = peak_rss_mb()

    y_all = np.concatenate(pool["y"])
    yp_all = np.concatenate(pool["yp"])
    yc_all = np.concatenate(pool["yc"])
    d_all = np.concatenate(pool["dates"])
    m_all = np.concatenate(pool["market"])
    boot = block_bootstrap(d_all, y_all, yp_all, yc_all, np.random.default_rng(SEED + 77))

    won = sum(1 for f in folds if f["beatsMajority"])
    need = min(MIN_FOLDS_WON, len(folds))
    margins = [f["margin"] for f in folds]
    controls = [f["shuffledControlMargin"] for f in folds]
    mean_margin = float(np.mean(margins))
    worst_margin = float(min(margins))
    degenerate_folds = [f["testYear"] for f in folds if f["degenerate"]]
    p25 = boot.get("p2_5")

    criteria = {
        "C1_meanMarginPositive": [round(mean_margin, 4), "> 0", mean_margin > 0],
        "C2_foldsWon": [won, f">= {need}", won >= need],
        "C3_noDegenerateFold": [degenerate_folds, "== []", not degenerate_folds],
        "C4_controlIntervalExcludesZero": [p25, "> 0", (p25 is not None and p25 > 0)],
        "C5_worstFoldMargin": [round(worst_margin, 4), f">= {WORST_FOLD_FLOOR}",
                               worst_margin >= WORST_FOLD_FLOOR],
    }
    failing = [k for k, v in criteria.items() if not v[2]]

    def pooled(sel):
        n = int(sel.sum())
        if n < MIN_MARKET_ROWS:
            return None
        a_r, m_r, o_r = over_majority(y_all[sel], yp_all[sel])
        return {"rows": n, "accuracy": a_r, "majority": m_r, "margin": o_r}

    by_market = {m: pooled(m_all == m) for m in sorted(set(m_all.tolist()))}
    by_market = {k: v for k, v in by_market.items() if v}
    crypto = pooled(m_all == "crypto")
    rest = pooled(m_all != "crypto")

    regimes = []
    for name, lo, hi in REGIMES:
        sel = (d_all >= lo) & (d_all <= hi)
        r = pooled(sel)
        if r and r["rows"] >= 200:
            regimes.append({"regime": name, **r,
                            "qualification": bool(r["rows"] >= REGIME_MIN_ROWS
                                                  and r["margin"] <= REGIME_LOSS)})

    recalls = {BINARY_CLASSES[c]: round(float((yp_all[y_all == c] == c).mean()), 4)
               for c in range(len(BINARY_CLASSES))}
    gains_total = (np.sum(np.asarray(pool["gain"]), axis=0) if pool["gain"]
                   else np.zeros(len(ALL_FEATURES), dtype=np.float64))
    g_sum = float(gains_total.sum())
    feature_gains = ([{"feature": f, "gainShare": round(g / g_sum, 4),
                       "gain": round(g, 4)}
                      for f, g in sorted(zip(ALL_FEATURES, gains_total.tolist()),
                                         key=lambda kv: -kv[1])]
                     if g_sum > 0 else [])
    mean_train_margin = float(np.mean([f["trainMargin"] for f in folds]))

    pred_mean = pred_crypto = None
    if PREDECESSOR.exists():
        pred_mean = json.loads(PREDECESSOR.read_text(encoding="utf-8")).get(
            "summary", {}).get("meanMargin")
    if PREDECESSOR_CRYPTO.exists():
        pred_crypto = json.loads(PREDECESSOR_CRYPTO.read_text(encoding="utf-8")).get(
            "summary", {}).get("meanMargin")

    qualified = [r["regime"] for r in regimes if r["qualification"]]
    if not failing:
        verdict = ("GO-CANDIDATE: the non-linear model clears every criterion the corrected "
                   "linear model failed. Worth reproducing in a fresh process; not a promotion.")
    else:
        verdict = (f"NO-GO: {', '.join(failing)} failed the criteria fixed before this run. "
                   "This is a recorded failure of one bounded non-linear configuration, not of "
                   "non-linear models in general.")
    if qualified:
        verdict += f" Qualification: adverse in {', '.join(qualified)}."

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": VERSION,
        "question": "does a non-linear decision function on the same 44 features beat its own "
                    "majority out-of-sample where the correctly-shaped linear softmax did not?",
        "whyNotARerun": "every out-of-sample run in this chain fitted a linear softmax, so the one "
                        "property they all share -- linearity -- was the only axis never moved. "
                        "eligible_set_experiment_v2 is the same rows, folds, weights, controls "
                        "and criteria with a different functional form, which isolates it",
        "predecessor": {
            "artifact": PREDECESSOR.name, "version": "eligible-set-v2",
            "meanMargin": pred_mean,
            "note": "the corrected two-output linear baseline on exactly these rows",
            "cryptoArtifact": PREDECESSOR_CRYPTO.name, "cryptoVersion": "binary-context-v2",
            "cryptoMeanMargin": pred_crypto,
            "deltaVsPredecessor": (round(mean_margin - pred_mean, 4)
                                   if pred_mean is not None else None)},
        "exposure": {
            "statement": "these calendar years and this universe were examined by every earlier "
                         "run, so this run re-measures an already-observed holdout. It is not a "
                         "pristine independent result, and no threshold was changed after any "
                         "metric was seen.",
            "pristine": False},
        "data": {"dataset": str(Path(a.dataset).relative_to(ROOT)),
                 "files": cache_files,
                 "rowsParsed": rows_parsed,
                 "quarantineDropped": quarantine_dropped,
                 "quarantine": "any(dataQuality) true drops the row before any split",
                 "rowsKept": rows_after_quarantine,
                 "rowsAfterDroppingFlat": int(len(yb)),
                 "markets": market_counts,
                 "dateRange": [str(min(dates)), str(max(dates))],
                 "features": len(ALL_FEATURES),
                 "droppedDuringParse": dropped_during_parse},
        "dataIntegrity": integrity,
        "target": {"label": "binary UP vs DOWN, FLAT dropped", "up": 1, "down": 0,
                   "construction": "signal_floor.py lines 102-104, identical to "
                                   "eligible_set_experiment_v2",
                   "classes": list(BINARY_CLASSES)},
        "model": {"algorithm": "logistic gradient boosting over depth-2 trees",
                  "implementation": "numpy only; no third-party machine-learning library, no "
                                    "torch, requirements.txt untouched",
                  "dependency": "numpy, already pinned at 2.2.1 in requirements.txt",
                  "rounds": ROUNDS, "learningRate": BOOST_LR, "maxDepth": MAX_DEPTH,
                  "leavesPerTreeMax": 2 ** MAX_DEPTH, "minChildRows": MIN_CHILD,
                  "l2Leaf": LAMBDA, "gamma": GAMMA, "leafClip": MAX_DELTA, "bins": BINS,
                  "binning": "128 quantile edges per feature computed on the training fold only; "
                             "the test fold is binned with the training fold's own edges",
                  "loss": "logistic; gradient w(p - y), hessian w p (1-p), leaf -G/(L + 1) "
                          "clipped to +/-1",
                  "classWeights": "n/(2 n_c) over the two classes, mean 1, identical to the "
                                  "linear predecessor's",
                  "baseScore": BASE_SCORE,
                  "earlyStopping": "none; the round count is fixed before the run",
                  "seed": SEED,
                  "seedNote": "the fit is deterministic -- no subsampling, ties by first "
                              "occurrence -- so SEED enters only through the shuffled control "
                              "(SEED + 1000 + testYear) and the bootstrap (SEED + 77)",
                  "fixedBeforeRun": True},
        "selfTest": st,
        "resources": {"fitSeconds": fit_seconds, "fitSecondsLimit": FIT_SECONDS_LIMIT,
                      "peakRssMB": peak_rss, "peakRssMbLimit": RSS_LIMIT_MB,
                      "withinDeclaredLimits": True},
        "protocol": {"folds": "baseline_experiment's rule: one fold per test year 2021..2026",
                     "embargoDecisionDates": EMBARGO, "seed": SEED,
                     "imputation": "training-fold column nan-mean, then training-fold standard "
                                   "deviation (stationarity.fit_window order)",
                     "standardisation": "training-fold only",
                     "minTrainRows": MIN_TRAIN, "minTestRows": MIN_TEST,
                     "uncertainty": f"moving-block bootstrap, {BLOCK_DAYS}-date blocks, "
                                    f"{BOOTSTRAP} resamples, candidate minus shuffled control",
                     "reference": "over_majority imported unchanged from stationarity"},
        "criteria": criteria,
        "criteriaSource": "the same five criteria as binary_context_experiment and "
                          "eligible_set_experiment, fixed in this module's docstring before any "
                          "number from this run was seen; thresholds identical",
        "diagnosticsNotCriteria": ["byMarket", "cryptoVsRest", "byRegime", "perClassRecall",
                                   "featureGains", "trainVsHoldout"],
        "folds": folds,
        "summary": {"foldsScored": len(folds), "foldsWon": won, "foldsRequired": need,
                    "meanMargin": round(mean_margin, 4),
                    "meanShuffledControlMargin": round(float(np.mean(controls)), 4),
                    "worstFoldMargin": round(worst_margin, 4),
                    "worstFoldYear": int(folds[int(np.argmin(margins))]["testYear"]),
                    "degenerateFolds": degenerate_folds,
                    "anyFoldDegenerate": bool(degenerate_folds),
                    "pooledRows": int(len(y_all)), "bootstrap": boot,
                    "meanTrainMargin": round(mean_train_margin, 4),
                    "generalisationGap": round(mean_train_margin - mean_margin, 4),
                    "predecessorEligibleSetMeanMargin": pred_mean,
                    "predecessorCryptoMeanMargin": pred_crypto,
                    "deltaVsPredecessor": (round(mean_margin - pred_mean, 4)
                                           if pred_mean is not None else None)},
        "byMarket": by_market,
        "cryptoVsRest": {"crypto": crypto, "everythingElse": rest},
        "byRegime": regimes,
        "perClassRecall": recalls,
        "featureGains": feature_gains,
        "fidelityLimitations": [
            "one configuration only: rounds, depth, learning rate, leaf penalty and bin count were "
            "fixed before the run and are not searched, so a failure is about this configuration "
            "and not about non-linear models",
            "these holdouts were examined by every earlier run, so this measures an observed "
            "result rather than a fresh one",
            "depth 2 expresses interactions up to order 2 only; higher-order structure would need "
            "a different experiment, which is not this one"],
        "verdict": verdict,
        "failingCriteria": failing,
        "nextQuestion": (
            "one bounded non-linear configuration has now failed on the same years every other "
            "family has been measured against. The next move is not a second configuration on "
            "these holdouts -- that is tuning on seen data. It is fresh data (sessions after "
            "2026-09-25) or a different question, and that decision belongs to the owner"
            if failing else
            "reproduce in a fresh process first, then read the per-feature gains and the "
            "by-market table for where the effect lives"),
        "notAPromotion": "a passing verdict is a candidate for reproduction, never a GO",
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\n{'year':<6}{'acc':>9}{'majority':>10}{'margin':>10}{'control':>10}"
          f"{'train':>10}{'rounds':>8}")
    for f in folds:
        print(f"{f['testYear']:<6}{f['accuracy']:>9.4f}{f['majority']:>10.4f}"
              f"{f['margin']:>+10.4f}{f['shuffledControlMargin']:>+10.4f}"
              f"{f['trainMargin']:>+10.4f}{f['rounds']:>8}")
    print(f"\nmean margin {mean_margin:+.4f}  worst {worst_margin:+.4f}  won {won}/{len(folds)}"
          f" (needed {need})")
    print(f"mean train margin {mean_train_margin:+.4f}  generalisation gap "
          f"{mean_train_margin - mean_margin:+.4f}")
    if pred_mean is not None:
        print(f"predecessor (eligible-set-v2, linear) mean {pred_mean:+.4f}   "
              f"delta {mean_margin - pred_mean:+.4f}")
    for name, v in by_market.items():
        print(f"  market {name:<12} n {v['rows']:>8,}  acc {v['accuracy']:.4f}  "
              f"maj {v['majority']:.4f}  margin {v['margin']:+.4f}")
    if crypto and rest:
        print(f"  crypto {crypto['margin']:+.4f}   everything else {rest['margin']:+.4f}")
    print("\ntop feature gains: " + ", ".join(
        f"{g['feature']} {g['gainShare']:.3f}" for g in feature_gains[:5]))
    print(f"\n{verdict}")
    print(f"fit {fit_seconds}s (limit {FIT_SECONDS_LIMIT}s), peak RSS "
          f"{peak_rss if peak_rss is not None else 'unknown'} MB (limit {RSS_LIMIT_MB} MB)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
