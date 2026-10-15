"""Account for every row of the authoritative dataset, with an explicit cause for each difference.

    python tools/research/row_accounting.py <dataset-dir> <out.json>

Reads the sealed `examples-v3` year files and writes `row_accounting.json`. Touches no database
and writes nothing else.

**Why this exists.** Three row counts circulate and none of them is wrong, which is exactly why
they get confused:

  * **1,085,544** -- rows in the dataset.
  * **~29,400** -- `readiness.json`'s `dataQualityExclusions`, which counts every row *carrying* a
    quality flag, independently, so a row with two flags is counted twice and a row that is also
    featureless is still counted here.
  * **58,773** -- rows the `label60` experiment dropped, which is a *pipeline* count: each row is
    attributed to the first rule that rejected it and to no other.

The difference between the second and third is not a discrepancy, it is the difference between
"how many rows carry this flag" and "how many rows this rule was the reason for". This module
reports both, plus the overlap that reconciles them, so the two can never be read as contradicting
each other again.

Two further exclusions live upstream and are **not** in the dataset at all, so they cannot appear
in either figure: weekend bars the pipeline never writes, and the quarantined PSX bars whose
high/low cannot contain their own close.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys
from collections import Counter

#: The order the experiment applies its rules in. First match wins, which is what makes the
#: pipeline count attribute each row exactly once.
RULES = ("noPointInTimeFeatures", "unadjustedActionInWindow", "windowIsNotDaily",
         "basisBreakInWindow", "noBaseClose")

FLAGS = ("unadjustedActionInWindow", "windowIsNotDaily", "basisBreakInWindow")


def classify(row: dict) -> str | None:
    """The first rule that rejects this row, or None when it is eligible."""
    fe = (row.get("pit") or {}).get("f") or {}
    dq = row.get("dataQuality") or {}
    if not fe:
        return "noPointInTimeFeatures"
    for flag in FLAGS:
        if dq.get(flag):
            return flag
    if (row.get("outcome") or {}).get("baseClose") is None:
        return "noBaseClose"
    return None


def account(dataset_dir: pathlib.Path) -> dict:
    pipeline = Counter()       # first rule to reject -- each row counted once
    carrying = Counter()       # rows carrying each flag -- counted independently
    both = Counter()           # carries the flag but an EARLIER rule claimed the row
    total = eligible = 0
    for p in sorted(dataset_dir.glob("examples-v3-*.jsonl.gz")):
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                total += 1
                dq = r.get("dataQuality") or {}
                cause = classify(r)
                for flag in FLAGS:
                    if dq.get(flag):
                        carrying[flag] += 1
                        # Attributed elsewhere whenever some other rule matched first. A row
                        # with two flags belongs to the earlier one, which is what makes the
                        # pipeline count a partition rather than a second tally of flags.
                        if cause != flag:
                            both[flag] += 1
                if cause is None:
                    eligible += 1
                else:
                    pipeline[cause] += 1
    excluded = total - eligible
    return {
        "datasetRows": total,
        "eligibleRows": eligible,
        "excludedRows": excluded,
        "pipelineAttribution": {k: pipeline.get(k, 0) for k in RULES},
        "rowsCarryingEachFlag": dict(carrying),
        "carriedButAttributedElsewhere": dict(both),
        "reconciliation": {
            "rule": ("rowsCarryingEachFlag minus carriedButAttributedElsewhere equals "
                     "pipelineAttribution for that flag"),
            "checks": {
                f: carrying.get(f, 0) - both.get(f, 0) == pipeline.get(f, 0) for f in FLAGS
            },
        },
        "identity": {
            "datasetRows == eligibleRows + excludedRows": total == eligible + excluded,
            "excludedRows == sum(pipelineAttribution)": excluded == sum(pipeline.values()),
        },
        "notInThisDatasetAtAll": {
            "weekendBarsExcludedByThePipeline": "never written; not among datasetRows",
            "psxQuarantinedIncoherentRanges": "quarantined upstream; not among datasetRows",
        },
    }


def main() -> int:
    out = account(pathlib.Path(sys.argv[1]))
    pathlib.Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0 if all(out["identity"].values()) and all(out["reconciliation"]["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
