# Workstream A — Data Foundation Final Closure

**Status:** read-only reconciliation. Nothing changed. **Head:** `eb0f276`, working tree clean of
tracked changes.

## A0. Verification limits — stated before any result

Three things cannot be re-measured from this checkout. They are named here so nothing below is
read as a live re-verification.

| Limit | Consequence |
|---|---|
| **`nbt-private/` is absent** from this machine | the authoritative dataset `examples-v3-2026-10-15-run38735767762` cannot be re-checksummed or recounted here |
| **No database access** — `DATABASE_URL` is not set in this environment, and no connection was attempted | live coverage, freshness, stale-input and partial-run state cannot be re-measured |
| **No run/CI telemetry in the checkout** | **sync duration, repeated ingestion, database usage and free-tier headroom cannot be assessed at all** from this repository |

Everything below is therefore reconciled **from committed artifacts**. Those artifacts are the
latest recorded state — `data/foundation/` is unmodified since `eb0f276` — but they describe a
database as of **2026-10-15T18:12:53Z**, and drift since then is unknown. **No check was simulated.**

## A1. The historical percentages, reconciled

| Reported figure | Status | What it actually is |
|---|---|---|
| **96.74% coverage** | **CONFIRMED** | `foundation_score.json → 1_dataCoverage` = **1,097,903 / 1,134,858** instrument sessions inside listed ranges |
| **100% organisation** | **CONFIRMED** | `2_organisationAndValidation` = **18/18** layers with all six frozen attributes *and* every named repo path resolving on disk. The artifact also records the superseded proxy (16/18) so the correction stays visible |
| **92.74% overall** | **CONFIRMED, and post-correction** | `overallWeightedScore = 0.9274` against `passThreshold = 0.9`. `git log` shows `foundation_score.json` was last rewritten by `72f63c2` — the organisation correction — so 0.9274 **already includes** organisation at 1.0. The two figures do not conflict |
| **97.16% "training readiness"** | **MISLABELLED** | The number is real — `readiness.json → authoritativeDataset.featureCoverage = 0.9716` — but it is **feature coverage**, not training readiness. The readiness verdict is a *word*, not a percentage: **`PASS WITH LIMITATIONS`**, scoped to *"the agreed first training task only; not a claim that every use case is ready"* |
| **context integration 4/18** | **CONFIRMED — and it is the principal gap** | `source_inventory.json → joinedIntoTraining = 4`. Joined: prices/OHLCV, corporate actions, gold and commodities, training examples. **12 layers are preserved but not joined**; 2 are source-blocked |

Layer status overall: **COMPLETE 11 · PARTIAL 5 · SOURCE_BLOCKED 2**.

## A2. Domain scores (weights from the frozen scope)

| Domain | Score | Weight |
|---|---|---|
| prices | 0.9674 | 0.22 |
| **corporateActionsAndLifecycle** | **0.6684** | 0.10 |
| macroAndRates | 1.0000 | 0.12 |
| historicalCrisesAndRegimes | 1.0000 | 0.12 |
| newsEventsAndOriginalReports | 0.9841 | 0.14 |
| **researchPrinciplesAndCaseStudies** | **0.7000** | 0.10 |
| provenanceAndLicensing | 1.0000 | 0.10 |
| backupAndRecovery | 1.0000 | 0.10 |

## A3. Point-in-time integrity — the strongest evidence in the foundation

From `readiness.json → pointInTimeAndLeakage`, all as recorded:

- features dated after their session: **0**; setups dated after their session: **0**
- macro observations dated after their session: **0**
- future-named-field scan: **18,000 rows**, nothing found
- duplicate outcomes: **0**; duplicate features: **0**
- 2018 rebuilt **byte-identical**
- `USREC` (the ex-post NBER recession flag) **excluded from the PIT feature set, with a test asserting its absence**
- split plan: chronological walk-forward, **20-session embargo**, and explicitly `notExecuted`

**These are the committed results of checks already run. They were not re-run here, and re-running
them without a specific reason is outside this workstream's scope.**

## A4. Outstanding exceptions, each dispositioned

| # | Exception | Evidence | Disposition |
|---|---|---|---|
| 1 | **Only 4 of 18 layers reach training.** Macro, rates, credit stress, events, press evidence, event reactions, regimes, principles, identity/lifecycle and benchmarks are acquired, checksummed and **unused by the model** | `source_inventory.json → joinedIntoTraining: 4`, `preservedButNotJoined` (12) | **ACCEPTABLE for the frozen first task**, which is explicitly a 15-feature price/volume baseline. **BLOCKING for any claim that macro, events or regimes inform the brain.** This is the single largest gap in the foundation and it is a design decision, not a data defect |
| 2 | **Quality flags are columns, not filters.** `unadjustedActionInWindow` 24,224 · `windowIsNotDaily` 3,009 · `basisBreakInWindow` 1,278 · `weekendBarsExcludedByThePipeline` 171 · `psxQuarantinedIncoherentRanges` 717 | `readiness.json → dataQualityExclusions`, whose own note says a run *"excludes them explicitly rather than hoping they were filtered upstream"* | **ACCEPTABLE as data; a live precondition for training.** Any training run that does not apply these filters trains on ~29,400 flagged rows. **This belongs in the training gate, not the data gate** |
| 3 | **`corporateActionsAndLifecycle` at 0.6684** — the weakest domain | `foundation_score.json → domains` | **ACCEPTABLE WITH DOCUMENTATION.** It is already inside the 0.9274 weighted result against a scope frozen before measurement; raising it now would be scope movement after the fact |
| 4 | **`researchPrinciplesAndCaseStudies` at 0.70** | same | **ACCEPTABLE.** 80/80 citations verified, 69 testable, 19 runnable; the shortfall is testability, not provenance |
| 5 | **Two layers source-blocked** — delisted US price history; PSX before 2013-11-04 | `blockedStillCounted`; `gap_evidence.json` holds dated probes (Yahoo 404s, stooq bot challenge not circumvented, PSX 404 at 2013-11-01 vs 200 at 2013-11-04) | **ACCEPTABLE.** Counted in the denominator rather than excused, and evidenced by reproducible probes. Nothing further is obtainable from permitted sources |
| 6 | **Backup integrity is evidenced; a restore rehearsal is not.** `backupAndRecovery` scores 1.0 on checksums (`SHA256SUMS.txt` per folder, `manifest.json` per-file sha256) | `organisation_attributes.py`; `foundation_score.json` | **DOCUMENTED EXCEPTION.** A checksum proves a file is intact, not that a restore has been performed end-to-end. The 1.0 should be read as *integrity verified*, not *recovery rehearsed* |
| 7 | **20-session embargo only** | `readiness.json → splitPlan.embargoSessions: 20` | **CORRECT for `label20`.** A 60-session label would require a 60-session purge — a Workstream B precondition, not a Workstream A defect |
| 8 | **Sync duration, repeated ingestion, DB usage, free-tier headroom** | — | **NOT ASSESSED.** No telemetry in the checkout and no database access (§A0). Not claimed either way |

## A5. Gate result

> ### **PASS WITH DOCUMENTED EXCEPTIONS**

Against the frozen rule in `acceptance_scope.json` — *"passThreshold 0.9 … andAlso: every mandatory
gate must pass"*:

- **Weighted score 0.9274 ≥ 0.90** ✔ (and the scope was frozen before measurement:
  `scopeFrozenBeforeMeasurement: true`)
- **Seven mandatory gates** — recorded as satisfied in the committed artifacts, with the PIT
  evidence in §A3 standing behind the first five. **They were not independently re-executed here**
  (§A0), so this is a reconciliation of recorded results, not a fresh attestation.
- **Eight exceptions above are documented and dispositioned**; exceptions 1 and 2 carry forward as
  conditions, not as data failures.

**The percentage alone is not the pass.** The pass rests on the frozen scope, the gate list, and
the exceptions being named rather than absorbed. `trainingStarted` remains `false`, and
`readiness.json`'s own verdict — **`PASS WITH LIMITATIONS`, scoped to the first training task
only** — is the honest ceiling on what this foundation currently supports.

## A6. What would change this result

Only two things, and neither is a review:

1. **Joining more of the 12 preserved layers into training** would raise what the brain can claim —
   and would require its own PIT discipline per layer (macro already carries `availableAt`).
2. **A rehearsed restore** would convert exception 6 from documented to closed.

Neither is started here. No further Data Foundation audit is proposed.

## A7. Change confirmation

No code, specification, configuration, dataset, artifact, label, test, training run or deployment
was modified. No database was contacted. No sync was run. `git diff HEAD` reports no tracked file
changed; the only new files in the tree are review reports.
