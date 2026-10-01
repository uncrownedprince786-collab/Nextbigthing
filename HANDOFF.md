# Handoff — 2026-10-01, final development pass

The system is in **production / maintenance only**. This file is the state; `brain.md` is the
thinking and `ARCHITECTURE.md` is the layer map.

Read "What still needs a human" before changing anything.

## Branch, migration, and the two things not to undo

**`main` is the source of truth.** The repository default branch is still `master`, which
matters because GitHub takes a scheduled workflow's *file* from the default branch and nowhere
else. Two guards exist, and neither is documentation:

1. `refresh.yml` checks out `ref: main` and has a **"Prove this run is executing main"** step
   that compares the checked-out SHA against `origin/main` and **fails the run** if they
   differ. Verified live. Do not delete it. Switching the default branch to `main` in GitHub
   settings would make it redundant, which is the proper long-term fix.
2. **Exactly one workflow migrates.** `schema.yml` runs `prisma migrate deploy`; the data lanes
   run `jobs/schemacheck.py`, which compares the migration directories against
   `_prisma_migrations` and refuses to start if the database is behind. A test asserts both
   halves. This replaced a real failure — run `36798989654`, where `refresh.yml` also migrated
   and the two raced from different concurrency groups against one database.

The guard was proven in production on 2026-10-01: run `36863045181` refused to start because
the concurrent schema run had not yet applied `20261002050000_intraday`, and the data jobs were
**skipped instead of crashing on a missing table**.

## Workflow lanes

| Workflow | Trigger | Concurrency | Purpose |
| --- | --- | --- | --- |
| `schema.yml` | push to `main`, dispatch | `nbt-schema` | migrations + every DB-only Brain job |
| `refresh.yml` | cron 07:17 / Mon 07:43, push to its own file | `nbt-database` | ingestion + intraday |
| `backfill.yml` | push touching `psx.py`/`seed.py`/`geo.py`/`upcoming.py` | `nbt-database` | history for newly added things |
| `tests.yml` | push, PR | none | logic tests, types, lint |

`schema.yml` keeps its own lane so optional enrichment can never block a migration — a hung geo
fetch once held the shared group for 90+ minutes while the migration the site needed sat queued
behind it. `tests.yml` has no group so a red test run can never delay a migration.

**Known trap:** pushing several times in quick succession makes queued runs cancel each other.
Push once, then let it drain.

## Live acceptance, measured 2026-10-01

Every line below was read back from the production database with `SELECT`s after the jobs ran.
**23 pass, 4 partial, 0 fail.**

| Criterion | Verdict | Measured |
| --- | --- | --- |
| Data | pass | 154,873 daily bars, newest 2026-10-01 |
| Freshness | pass | news reading and newest close both 2026-10-01 |
| Partial source detection | pass | 141 complete, 55 partial, 6 unsupported sessions |
| Coverage self-audit | pass | 50 `Coverage` rows |
| Deduplication | pass | 944 items clustered into 913 stories |
| Future memory | pass | 95 scheduled dates ahead; 88 upcoming, 5 approaching, 2 live |
| Event resolution | **partial** | 0 frozen states — see below |
| No look-ahead | pass | 0 before-states dated on or after their event |
| Thesis memory | pass | 21 active theses on the `longer` horizon |
| Attribution | pass | 140 rows, 117 with a named leader, identity error 7.1e-15 |
| Graph | pass | 23 paths, max 2 hops, every row carries its chain |
| Investigation | pass | 8 investigations; 29 found, 35 absent, 8 unavailable |
| Competing hypotheses | **partial** | 32 with priors and evidence, 0 posteriors — see below |
| Historical analogs | pass | 280 rows, best match count 1,062 |
| Intraday | pass | 36 reads; 46,310 five minute bars across 36 assets |
| Swing | pass | 140 reads |
| Longer term | pass | 70 reads |
| Derived intervals | pass | 23,854 bars aggregated from the 5m series |
| Entry / invalidation | pass | 246 of 246 setups carry both |
| Target where justified | pass | 66 ranges over 25 setups by 3 methods; 59 flagged as disagreeing |
| Outcome logging | pass | 198 logged readings from 2026-09-30 |
| Calibration | **partial** | 20 rows, 0 outcomes matured — see below |
| Source learning | **partial** | 1 source row, 27 observations — see below |
| No fabrication | pass | 26,260 genuine zero volumes, none conflated with absent |
| Unavailable recorded | pass | 6 assets stored as having no intraday source |

### Why the four partials are partial, and what each waits on

All four wait on **time**, not on work. Nothing in the codebase blocks them.

- **Event resolution.** `lifecycle.py` freezes a pre-event state when a *scheduled* date has
  passed. All 95 scheduled dates are in the future and the 8 historical events were seeded by
  hand with `scheduled = false`, so there is nothing to resolve yet. Five dates are in the
  `approaching` window now; the first frozen state appears when one passes.
- **Competing hypotheses / posteriors.** A likelihood ratio needs a measured `P(E|H)`. For the
  three measured components the evidence *is* the measurement, so an update would be circular;
  for the news hypothesis there is no matured outcome to measure from. Both reasons are stored
  on every row and the column exists, so it fills without a migration.
- **Calibration** and **source learning.** The outcome log started 2026-09-30 with **zero**
  matured rows. The earliest honest 30-day numbers are around **2026-10-30**. The machinery is
  live and measuring; it has nothing to measure yet.

## Free-tier status

**Measured**, 2026-10-01, after the retention sweep and a reclaim:

| | |
| --- | --- |
| Database | **126 MB** of a 500 MB Neon free tier |
| `PriceSnapshot` | 71 MB — seven years of daily bars, the permanent record |
| `IntradayBar` | 35 MB — ten days of five minute bars, swept each run |
| Everything else | under 3 MB each |

**Estimated** steady state: intraday is the only table that grows per run, bounded by
`RETAIN_DAYS = 10` at roughly 25–35 MB. Daily bars add about 160 rows a day.

Two numbers worth keeping, both measured the hard way:

- One run fetching a **month** of 5m bars stored 201,726 rows and took `IntradayBar` to **85 MB**
  — larger than the entire daily history for all 160 assets — for data nothing queried beyond
  the newest two sessions. The fetch window is now five days.
- **One minute bars are not fetched.** Every reader queries `interval = 5`, so they were storage
  spent on nothing. The capability is kept behind `FINE_SLICE = 0`: fetch, normalisation,
  session accounting and aggregation all still handle `interval = 1`.

Request budget: `MAX_REQUESTS = 60` per intraday run caps the provider calls whatever the active
set says, so a selection bug costs one capped run rather than a ban. A real run used 36.

## Automation status

Normal operation needs **no manual work**. The nightly `refresh` at 07:17 fetches, validates,
stores, deduplicates, updates world state and future events, runs the brain, writes the setup
states, monitors theses, investigates material moves, measures outcomes and reports. Every push
to `main` migrates and re-runs the DB-only jobs. Failures recover by backoff, retry and
idempotent upsert; `run.py` continues past a failed step and prints a table of every step with
its exit code as the **last** thing in the log, and writes the same table to
`$GITHUB_STEP_SUMMARY` — which matters because **GitHub requires a sign-in to read Actions logs
even for a public repository**, and the run summary page does not.

## What still needs a human

Only genuinely external things:

1. **Reading a failed `refresh` log** needs a GitHub sign-in. The step summary table is the way
   around it for the common case.
2. **The deployed site is behind Vercel Authentication**, so the pages cannot be read without
   signing in to that account. Everything above was verified against the database instead. The
   page-level look is the one check never performed.
3. Provider credential expiry, source format or terms change, provider shutdown, or an
   infrastructure plan change.

## Rules that are load-bearing

Everything in `brain.md` under "Rules for changes" — 26 of them, the last eight added with
this pass — and in particular:

- **One migrator.** `schema.yml` and nothing else. The data lanes check.
- **Retention touches intraday only.** `PriceSnapshot` is the permanent record. A sweep that
  reached it would delete the history every other job is built on; a test asserts the sweep's
  `DELETE` statements name only `IntradayBar` and `IntradaySession`.
- **Absent, zero and unavailable are three different values.** `IntradaySession.status`,
  `InvestigationFinding.status` and `AssetSetup.missing` all exist to keep them apart.
- **No bar is invented.** A gap stays a gap, and a derived interval is written only when every
  component bar is present.
- **`AssetThesis.openConditions` is a copy, never recomputed.** Recomputing it reintroduces
  look-ahead bias into the one place built to exclude it.
- **Attribution and investigation name what a move was shared with or preceded by, never what
  moved it.** The test suite checks the generated text for the banned causal words.
- **No LLM anywhere.** `requirements.txt` has no model SDK; every number and sentence is Python
  or SQL.
- **Quote identifiers in hand-written SQL.** `leading` is reserved in Postgres and cost a
  production run; a test now scans every `INSERT` in `jobs/` for bare reserved words.

## If something looks wrong, first

- `python jobs/stats.py` — row counts and newest date per table.
- `python jobs/schemacheck.py` — is the database behind this checkout?
- `python -m unittest discover -s tests` — 188 tests, no database or network needed.
- The `IntradaySession` rows for an asset say whether its intraday series can be trusted.
- `stale`-status session rows dated before 2026-09-26 are residue from a classification bug
  fixed in `2a012f5`; they age out with retention and can be ignored.
