"""Freeze a training-ready dataset version, and refuse to freeze one that fails an entry gate.

    python tools/foundation/freeze_dataset.py --dataset DIR [--full DIR] [--pit DIR]
                                              [--macro DIR] [--out FILE]

`BRAIN-SPEC-V1.md` §9 gate 4 says candidates may be trained *only* on approved, versioned datasets,
and §8 marks T4 (leakage) blocking: "training may not begin while any fails". This is the thing that
makes that enforceable rather than aspirational -- it reads the producers' own manifests, checks the
gates, and writes a freeze record carrying the digests. **A failing gate exits non-zero and writes
nothing**, so a frozen version cannot exist for a dataset that did not pass.

It asserts rather than recomputes. Each producer already measures its own integrity -- `assemble.py`
records leakage and duplicate counts, `full_history.py` reconciles generated rows against stored
price rows and leaves `unexplained` at 0 -- and recomputing those here would be a second opinion
about the same question, which is the fault this project keeps finding. What this adds is that the
checks are *read and enforced in one place*, and that what passed is pinned by content digest so a
later training run can say which bytes it learned from.

**What it does not claim.** A frozen dataset is not an edge, and freezing is not approval of a label
or a horizon. It records what was built, from what, with which exclusions, and that the gates the
specification calls blocking were green.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def head(repo: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    ds = Path(arg("--dataset") or (ROOT / ".cache" / "foundation" / "dataset_full"))
    full = Path(arg("--full")) if arg("--full") else ROOT / ".cache" / "foundation" / "full"
    pit = Path(arg("--pit")) if arg("--pit") else ROOT / ".cache" / "foundation" / "pit_full"
    macro = Path(arg("--macro")) if arg("--macro") else ROOT / ".cache" / "foundation" / "macro_rebuild"
    out = Path(arg("--out") or (ROOT / "data" / "foundation" / "dataset" / "dataset_freeze.json"))

    manifest = json.loads((ds / "manifest.json").read_text(encoding="utf-8"))
    full_manifest_path = next(iter(sorted(full.glob("manifest-full-v*.json"))), None)
    full_manifest = json.loads(full_manifest_path.read_text(encoding="utf-8")) if full_manifest_path else {}
    pit_manifest_path = pit / "manifest.json"
    pit_manifest = json.loads(pit_manifest_path.read_text(encoding="utf-8")) if pit_manifest_path.exists() else {}
    macro_manifest_path = macro / "manifest.json"
    macro_manifest = json.loads(macro_manifest_path.read_text(encoding="utf-8")) if macro_manifest_path.exists() else {}

    years = sorted(ds.glob("examples-v3-*.jsonl.gz"))
    files = {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in years}

    leakage = manifest.get("leakage", {})
    duplicates = manifest.get("duplicates", {})
    reconciliation = full_manifest.get("reconciliation", {})

    # The gates. Each is (measured, required, pass). A blocking gate that is absent is a failure, not
    # a pass: "the producer did not record it" is not "it was zero".
    def gate(value, required):
        return [value, required, value == required]

    # The future-field check is recorded in one of two shapes depending on the producer's version: an
    # older count (`futureNamedFields: 0`) or a scan record that *raises* on a hit, where a completed
    # run is itself the evidence. Both are accepted and the shape is reported, because treating an
    # absent key as a pass is how a blocking gate quietly stops blocking.
    scan = leakage.get("futureNamedFieldScan")
    if isinstance(scan, dict) and scan.get("rowsChecked"):
        future_fields: list = [f"scan of {scan['rowsChecked']} rows completed without raising",
                               "no hit", True]
    else:
        future_fields = gate(leakage.get("futureNamedFields"), 0)

    gates = {
        # §8 T4, blocking.
        "featureDatedAfterSession": gate(leakage.get("featureDatedAfterSession"), 0),
        "setupDatedAfterSession": gate(leakage.get("setupDatedAfterSession"), 0),
        "futureNamedFields": future_fields,
        # A duplicated asset-session is one observation counted twice, which inflates every count
        # downstream and cannot be detected once the rows are shuffled into folds.
        "duplicateOutcomes": gate(duplicates.get("outcomes"), 0),
        "duplicateFeatures": gate(duplicates.get("features"), 0),
        # Row accounting: every stored price row is either generated or excluded for a named reason.
        "unexplainedRows": gate(reconciliation.get("unexplained"), 0),
        # A dataset with no year files is not a dataset.
        "yearFilesPresent": [len(files), "at least 1", len(files) >= 1],
    }
    failed = {k: v for k, v in gates.items() if v[2] is not True}

    record = {
        "version": f"examples-v3-{datetime.now(timezone.utc).date().isoformat()}-local",
        "frozenAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "frozen for training" if not failed else "REFUSED -- a blocking gate failed",
        "repoHead": head(ROOT),
        "builtBy": {
            "outcomes": "tools/full_history.py",
            "features": "tools/foundation/pit_features.py",
            "assembly": "tools/foundation/assemble.py",
            "macroContext": "tools/foundation/macro_pit.py",
        },
        # Where the bytes are and how to make them again. The data derive from a third-party feed, so
        # they stay out of the repository by the rule `pit_features.py` states -- which means a digest
        # alone identifies an artifact that a later session cannot find. These are the commands that
        # produced exactly the digests below, in order; each reads the database and writes only under
        # `.cache/`, which is ignored.
        "artifactLocations": {
            "root": ".cache/foundation",
            "outcomes": ".cache/foundation/full/full-history-v2.jsonl.gz",
            "features": ".cache/foundation/pit_full/pit-<year>.jsonl.gz",
            "assembled": ".cache/foundation/dataset_full/examples-v3-<year>.jsonl.gz",
            "macroContext": ".cache/foundation/macro_rebuild/macro-sessions.jsonl.gz",
            "note": "ignored by .gitignore and disposable; rebuildable with the commands below, which "
                    "need only database access and take about 70 minutes, the feature build being the "
                    "long half at roughly an hour",
        },
        "rebuildCommands": [
            "python tools/full_history.py --out .cache/foundation/full",
            "python tools/foundation/pit_features.py --out .cache/foundation/pit_full",
            "python tools/foundation/assemble.py --full .cache/foundation/full "
            "--pit .cache/foundation/pit_full --out .cache/foundation/dataset_full",
            "python tools/foundation/macro_pit.py --out .cache/foundation/macro_rebuild",
            "python tools/foundation/freeze_dataset.py --dataset .cache/foundation/dataset_full",
        ],
        "rows": {
            "eligibleAssetSessions": manifest.get("eligibleAssetSessions"),
            "withPointInTimeFeatures": manifest.get("withPointInTimeFeatures"),
            "withoutFeatures": manifest.get("withoutFeatures"),
            "withoutFeaturesByReason": manifest.get("withoutFeaturesByReason"),
            "featureCoverage": manifest.get("featureCoverage"),
            "setupCoverage": manifest.get("setupCoverage"),
        },
        "outcomes": {
            "rows": full_manifest.get("rows"),
            "dateRange": full_manifest.get("dateRange"),
            "label20Counts": full_manifest.get("label20Counts"),
            "reconciliation": reconciliation,
            "sha256": full_manifest.get("sha256"),
        },
        "features": {
            "rows": pit_manifest.get("rows") or pit_manifest.get("produced"),
            "missingnessByAssetType": pit_manifest.get("missingnessByAssetType"),
        },
        "macroContext": {
            "sha256": macro_manifest.get("sha256"),
            "sessions": macro_manifest.get("sessions"),
            "observationsDatedAfterTheirSession": macro_manifest.get("observationsDatedAfterTheirSession"),
            "verifiedBy": "tools/foundation/macro_pit_verify.py",
            "joinedNotPreJoined": "macro is joinable on date and is NOT a column in the example rows; "
                                  "a market-wide series given to every instrument as a per-asset feature "
                                  "is one fact counted once per name",
        },
        "coverage": {
            "byAssetClass": manifest.get("byAssetClass"),
            "outcomesByAssetClass": full_manifest.get("byAssetClass"),
        },
        "qualityExclusions": manifest.get("dataQuality"),
        "files": files,
        "splitPlan": {
            "method": "chronological walk-forward, one fold per test year",
            "embargoSessions": 20,
            "embargoReason": "a 20-session label makes consecutive rows share 19 of their 20 forward "
                             "sessions, so rows either side of a cut are not independent",
            "rowsAreNotIndependentObservations": "a row count is not a sample size; the effective "
                                                 "count is nearer rows/embargo and is reported as such",
        },
        "gates": gates,
        "blockingGatesGreen": not failed,
    }

    if failed:
        print(json.dumps({"status": record["status"], "failed": failed}, indent=1))
        print("::error title=dataset freeze::a blocking gate failed; nothing was frozen")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items()
                      if k not in ("files", "coverage", "features", "qualityExclusions")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
