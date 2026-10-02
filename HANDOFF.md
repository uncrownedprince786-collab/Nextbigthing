# Handoff — 2026-10-01, final development pass

> For the short version — where work stopped and what to do next — read
> [RESUME.md](RESUME.md). This file is the detail behind it.

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

## The refresh failure, found and fixed

Carried as an open item since 2026-09-30 and closed on 2026-10-01. It was one missing import.

`jobs/prices.py` used `timedelta` on two lines and imported only `date, datetime, timezone`.
The name resolved nowhere, so the **first** job of the daily group died with `NameError` 0.1
minutes in and all sixteen behind it were skipped. That is why the runs reported failure while
the site kept serving correctly: nothing ran, so nothing was corrupted, and the previous day's
rows stayed where they were.

Found by running the production command locally and reading the per-step table, not by guessing:

    === prices yahoo crypto news: FAILED in 0.1 min ===
    NameError: name 'timedelta' is not defined

Nothing caught it. It imports, it compiles, `compileall` passes it, and the name is resolved
only when that branch executes — which it does on every run, in the one job every other job
depends on. `tests/test_brain.py::UndefinedNames` now walks every job's AST for names it never
binds, with two tests proving the walk fires on this exact shape and stays quiet on the fix.

## Seven more defects the production verification found

An end-to-end check of the intraday chain started at 20 pass / 9 fail. None was visible in the
unit tests; all are fixed and re-verified at 29 pass / 0 fail.

1. **Naive `datetime.timestamp()`.** `aggregate()` bucketed derived bars through an epoch, and
   that call reads the *machine's* local timezone. Invisible on the UTC runner; five hours
   wrong from a UTC+5 laptop, so AAPL's 15-minute bar at 08:00 held the open of the 13:00 bar.
   A timezone-dependent result is worse than a wrong one. Now pure arithmetic, guarded by one
   test that states the answer and one that forbids the construct.
2. **The bar still forming.** The provider's last element is stamped with the quote time, not a
   bar boundary. It was stored as a complete bar, made aggregation groups look full, and —
   because each run stamps a different second — accumulated instead of overwriting. 112 had
   piled up. Now discarded and counted.
3. **Cross-day session phases.** `currentTradingPeriod` describes today only; the old
   adjacent-day fallback compared a Monday bar against Friday's window. 1,100 of NVDA's 1,613
   bars were labelled pre-market, leaving the intraday read a quarter of its series.
4. **Retention wider than the refetch window.** A bar outside the window keeps whatever phase
   it was given. `RETAIN_DAYS` is now 7 to match `range=5d`; changing one without the other
   reintroduces stale labels.
5. **Analog targets straddling the entry.** The range ran from the median to the favourable
   extreme, so a median near zero put the near edge on the wrong side: AAPL `buy` at 333.08
   with an "upside" range starting at 332.77. Seven rows. The analog target now requires a
   median pointing the same way as the setup.
6. **Upserts that never retract.** When a method stopped qualifying, the previous row survived.
   `run_targets` now deletes the methods it did not produce.
7. **A reserved word.** `leading` is reserved in Postgres; the unquoted column was a syntax
   error that only appeared at the database.

## Where this stands, 2026-10-01 evening — READ THIS FIRST ON RESUME

Everything below the horizontal rule is still accurate. This section is the live state.

### The one thing still red

**`refresh.yml` fails at "Run data jobs".** Latest: run `36918247571` (commit `7df69c6`),
failure, 17m 11s. The schema guard passed; the failure is inside `jobs/run.py daily`.

Two causes were found and fixed today, and **every job in the daily group now passes when run
individually against the production database**:

| job | verified |
| --- | --- |
| `prices yahoo` | **37,537 rows stored**, PriceSnapshot 154,873 → 191,748, latest 2026-10-01 |
| `psx recent` | 12,417 snapshots, 2019-01-01 → 2026-10-01 |
| `upcoming` | 105 earnings dates, 2026-10-13 → 2026-12-24 |
| `rank`, `confidence rankings`, `analysis` | all clean |
| `events` | 1,394 impact rows in 0.6 min |
| `intraday`, `horizons all`, `thesis`, `attribution`, `graph`, `investigate` | all clean |

So the remaining production failure is **environment-specific, not a code defect**. The strong
hypothesis, and the next thing to check: **`yfinance` is being throttled or blocked from GitHub
runner IPs.** The evidence is that the same `prices` step stored **0** rows in run `36918247571`
while storing 37,537 locally minutes later, and `fetch_yahoo` cannot distinguish an empty frame
from a blocked one — `yf.download` returns an empty DataFrame and `_store_frame` writes nothing
without raising.

**How to confirm it, since the log needs a GitHub sign-in:** `run.py` already writes a per-step
table to `$GITHUB_STEP_SUMMARY`, and `schema.yml`'s migrate step writes its output there too.
GitHub does **not** render job summaries to anonymous visitors, so reading either one needs a
sign-in. Sign in once, open the failing run, and the table names the step in one line.

**The silence is fixed (2026-10-02).** `require_answer` in `prices.py` fails the step when a
whole download batch stores **0** rows, which is a blocked or throttled host rather than a
market with no new bars — the same line `jobs/marketplace.py` draws when every Amazon category
is blocked, and the same `partial` distinction `jobs/audit.py` already made when it flagged
this one (`Yahoo Finance daily closes — partial — the newest day holds 2 records against a
recent median of 60`). A single asset answering nothing is still data and is still only
printed; brain.md rule **31** records the reasoning, and two tests guard it — one states the
answer, one forbids storing a download without the check, because the behavioural test passes
on any host Yahoo does answer.

That makes the next failing run **name** its cause in the step's own output instead of
succeeding with nothing. It does not route around a block.

**Then the real defect was found, and the "environment-specific, not a code defect" reading
above is wrong.** Two bugs in `fetch_crypto`, both introduced or exposed on 2026-10-01:

- **The crypto row shape.** `insert_snapshots` gained `open`, `high` and `low` in `aa64785`.
  The Yahoo caller was updated, the Binance one thirty lines below was not, and a six-field row
  met a nine-name COPY unpack: `ValueError: not enough values to unpack (expected 9, got 6)` on
  **every crypto insert** from that commit on — the same day the refresh lane went red. Fixed
  by building the row in `crypto_rows`, beside the writer that defines the shape, with a test
  that unpacks it with COPY's nine names. brain.md rule **32**.
- **A cap dated off an empty series.** `cap_by_day[closes[-1][0]]` ran *before* the
  `if not closes` guard. CoinPaprika answers where Binance is blocked, so the host with no
  closes is the host with a live cap: `IndexError` there, nothing locally. The guard moved
  above it.

Why nothing caught either: COPY unpacks per row at run time, so the arity needs a database to
surface; and the local runs that proved each job "passes individually" were made from a host
Binance answers. The suite now has five tests over these paths, all of which fail against the
pre-fix file.

**Next move:** re-run `refresh.yml`. The sign-in is still the only way to read a step summary,
but it is no longer the blocking step — if the lane fails again, the guards name the source.

### Session of 2026-10-02, in full

Ten commits, `b826d2e` through `6ea172e`. 259 tests passing, typecheck and lint clean, every
CI run green. `AUDIT.md` is the authoritative requirement matrix and says how each row was
established; it reads **NOT FROZEN**, on the refresh gate alone.

What was wrong and is now fixed:

1. **The crypto row shape.** Six fields to a nine-name COPY unpack, broken since `aa64785` on
   2026-10-01 — the day the refresh lane went red. Every crypto insert raised `ValueError`.
   Now built by `crypto_rows`, beside the writer that defines the shape.
2. **A cap dated off an empty series.** `closes[-1]` read before the empty-series guard.
   CoinPaprika answers where Binance is blocked, so the host with no closes is the host with a
   live cap: `IndexError` on a runner, clean on a laptop.
3. **A guard that would have discarded whole runs.** Added and then caught in the same session:
   `require_answer` raised `SystemExit` inside `with conn`, and psycopg rolls back on any
   exception leaving that block, so one blocked source would have thrown away every other
   source's rows. Now `SourceSilent`, caught per lane, exit after the commit.

What reaches the reader that did not before — the repeating fault in this repository is
**built and unused**, not unbuilt:

- `Coverage`, written per source per run since coverage existed, read by no page. Now on the
  home page briefly and on `/methodology` in full.
- `NewsLineage`'s story-versus-copy distinction, the thing that stops one syndicated release
  looking like twenty stories breaking. Now on the asset page.
- `getEventCategoryHistory` — what past events of a category were followed by, floor-gated at
  five. Now on the event page.
- `getIntradayCoverage`, written by its own comment for the methodology page, never called.
- `SetupTarget.rewardRisk`, stored on every target row and never shown.

Audits completed with regression tests, each mutation-tested: no look-ahead (six tests), web
safety, the reader-can-ask-why vocabulary, the dead-export ratchet, the no-fake-confidence
language scan. Performance was **measured and deliberately not changed** — `audit.py` 9
in-loop queries, `horizons.py` 10, `thesis.py` 8, unmeasurable against production from here,
so the counts are frozen as a ratchet rather than rewritten on a guess.

brain.md gained rules 31 to 37. The ones to read first are 33 (a failure signal and a
transaction boundary must be designed together), 36 (built and unused) and 37 (when a guard
fires on correct code, fix the guard).

### Two transient failures, already recovered

`schema.yml` failed twice at "Apply pending schema migrations" (runs `36882681832`,
`36883475566`), both in ~12s with every other step passing. The schema was current throughout
(19 of 19 migrations applied, checked directly) and the next run **passed** — run `36917629683`,
success, 9m 3s, all 20 brain jobs green. Neon's free-tier compute suspends when idle and the
runner's connect attempt timed out. The migrate step now copies its own output to the run
summary so a repeat says why.

### Review findings — all five shipped in `9db293f`

1. **Simple read** on `/asset/[symbol]` and `/product/[slug]`, above everything.
2. **Home scan boxes** — setups to watch, dates & cautions, product attention.
3. **Product cards** reduced to name / status / score / badge, grade paragraph behind a
   `<details>` disclosure.
4. **Automobile and Software & Cloud** were a data gap, not a UI bug: ten assets each with zero
   stored prices, because `prices.py` had been broken for two days. Both now have 10 `sizeNow`
   and 10 `rising` rankings. The card also no longer renders "as of no date".
5. **News honesty** folded into the Simple read caution chain.

### Known data gaps, each with a stated reason

- `ProductRegion` is still empty. `geo.py` works (verified: 175 countries, 51 US states, 5 PK
  provinces) but keeps being cancelled by queue churn in `backfill.yml`.
- `MarketplaceItem` is empty and `Coverage` reports Amazon Best Sellers as `silent`. It is a
  weekly job and has not run.
- `Binance` crypto closes stop at 2026-09-29.
- `EventState` is 0 — all 131 scheduled dates are still in the future, so nothing has resolved.

## What still needs a human

Only genuinely external things:

1. **Reading a failed `refresh` log** needs a GitHub sign-in. The step summary table is the way
   around it for the common case.
2. **The deployed site is behind Vercel Authentication.** Re-checked on 2026-10-01: the
   deployment answers HTTP 200 with 341 KB, and that payload is Vercel's own sign-in challenge
   rather than the site — reading the status code alone would have been misleading. So visual
   production acceptance has **not** been performed and is not claimed. What was done instead:
   the current commit was built and served locally against the production database, and the
   home page, `/asset/INTC`, `/asset/AAPL`, `/methodology`, `/events` and `/products` were all
   fetched and read. That verifies the code and the data; it does not verify the deployment.
   The remedy is one setting — disable Vercel Authentication for production, or grant access.
3. Provider credential expiry, source format or terms change, provider shutdown, or an
   infrastructure plan change.

## Rules that are load-bearing

Everything in `brain.md` under "Rules for changes" — 30 of them — and in particular:

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
- **Never call `.timestamp()` on a naive datetime.** It reads the machine's local timezone, so
  a result is correct on the UTC runner and wrong everywhere else. This mislabelled every
  derived intraday bar by five hours when a job was run from a laptop. Two tests guard it.
- **An upsert does not retract.** A job that writes a set per parent must delete the members it
  did not produce, or a stale row outlives the rule that stopped producing it.

## If something looks wrong, first

- `python jobs/stats.py` — row counts and newest date per table.
- `python jobs/schemacheck.py` — is the database behind this checkout?
- `python -m unittest discover -s tests` — 188 tests, no database or network needed.
- The `IntradaySession` rows for an asset say whether its intraday series can be trusted.
- `stale`-status session rows dated before 2026-09-26 are residue from a classification bug
  fixed in `2a012f5`; they age out with retention and can be ignored.
