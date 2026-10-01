# Handoff — 2026-10-02

Where the system actually stands, so work can resume without the chat that produced it.
`brain.md` is the thinking, `ARCHITECTURE.md` is the layer map, this is the state.

## Branch, and the one thing not to undo

**`main` is the source of truth.** The repository's default branch is still `master`, which
matters because GitHub takes a scheduled workflow's *file* from the default branch and
nowhere else. That is handled, and not by documentation:

- `refresh.yml` and `schema.yml` check out `ref: main` explicitly
- `refresh.yml` has a **"Prove this run is executing main"** step that compares the
  checked-out SHA against `origin/main` and **fails the run** if they differ
- `main` was pushed to `master` once to install that shim

Verified live: the proof step passed in a real run. `master` can stay frozen; the nightly
cron still executes `main`. **Do not delete that proof step** — it is the only thing stopping
a silent regression to stale code. Switching the default branch to `main` in GitHub settings
would make the shim redundant, which is the proper long-term fix.

## Workflow lanes (and why)

| Workflow | Trigger | Concurrency | Purpose |
| --- | --- | --- | --- |
| `schema.yml` | push to `main`, dispatch | `nbt-schema` | migrations + all DB-only Brain jobs |
| `refresh.yml` | cron 07:17 / Mon 07:43, push to its own file | `nbt-database` | full ingestion |
| `backfill.yml` | push touching `psx.py`/`seed.py`/`geo.py`/`upcoming.py` | `nbt-database` | history for newly added things |
| `tests.yml` | push, PR | none | logic tests, types, lint |

`schema.yml` has its **own lane** on purpose. It used to share `nbt-database`, and a geo
fetch hung on rate-limit retries held that group for 90+ minutes while the migration the
deployed site needed sat queued behind it. Optional enrichment must never block critical
ingestion. `tests.yml` has no group at all so a red test run can never delay a migration.

**Known trap:** pushing several times in quick succession makes queued runs cancel each
other. Push once, then let it drain.

## Live and working (verified on the deployed site)

- 17 industries / 160 assets, including 8 PSX sectors with **70/70** symbols priced and sized
- Catalyst radar on the front page — real output: Robot vacuum 35.0×, GLD 30.0×
- Setup block on `/asset/[symbol]` — real output for NVDA: *wait*, swing, low confidence,
  with the failing condition named (volume 0.89× its average) and levels $230.10 / $210.96
- Analog engine: 392 matches on NVDA, 218 rose over 5 sessions
- Story lineage, robust-z catalyst gating, coverage/calibration/reliability tables
- Event lifecycle, with the pre-event state frozen from observations dated strictly earlier

## Written but not yet run against the database

Three layers were added on 2026-10-02 and are **committed code with a pending migration**.
They read only rows that already exist, make no network request, and are wired into the
`schema.yml` release lane and into `run.py`'s daily and weekly plans. None of them has
produced a row yet, because the migration has not been applied.

- **`jobs/thesis.py` — thesis memory.** A thesis is the run of consecutive `AssetSetup` reads
  on which one directional state was held. The opening day's conditions are *copied* onto
  `AssetThesis`, never re-derived, and every later day is compared against them:
  `active → weakening → broken`. `broken` rests on the invalidation level the opening day
  named and is **terminal**. `ThesisCheck` keeps one frozen row per assessment date.
- **`jobs/attribution.py` — competing hypotheses, measured.** `total = market + sector +
  specific`, from medians over the exchange group and the asset's own industry peers. The
  three accounts are exclusive by construction. No probability is attached, and every row
  says so: that is still blocked on matured outcomes.
- **`jobs/graph.py` — bounded graph neighbourhood.** Carries a flagged catalyst at most two
  hops over `ProductAssetLink`, `EventLink` and industry membership, skips edge groups above
  25 members, divides every edge by its group size, and stores the chain in words.

UI: three new blocks on `/asset/[symbol]`, two new sections on the front page, and a
methodology section stating the limit of each. 78 tests green, types and lint clean.

**First run order matters.** `schema.yml` applies the migration and then runs the three jobs
in the same run, in the order `setup → thesis → attribution → graph`. `thesis.py` produces
nothing on its first run beyond opening rows, because a run of one day has nothing to compare
against; the statuses only become interesting on the second day.

## Not implemented (deliberately, with reasons)

- **Intraday.** Only daily closes are stored. Do not manufacture intraday from daily bars.
- **Investigation engine.** Nothing fetches filings or related-company news *in response* to
  a move. The catalyst flag detects that something arrived; `graph.py` now says what sits
  near it, but neither goes looking.
- **Bayesian posteriors.** Blocked on data, not effort: a likelihood ratio needs a measured
  `P(E|H)`, and **zero outcome rows have matured**. The log started 2026-10-01, so the
  earliest honest ones are ~2026-10-31. `attribution.py` is the half that can be measured
  without them; the posterior is the half that cannot.
- **Full attention model.** Two dimensions now (spike size, graph distance). Pareto dominance
  across the eight in `brain.md` is not built.
- **Causal / systems (L7), regime engine, Monte Carlo, EVT, hazard models.** All need longer
  or denser history than is stored.

## Next, in order

1. **Apply the pending migration.** `20261002030000_thesis_attribution_graph` creates
   `AssetThesis`, `ThesisCheck`, `MoveAttribution` and `GraphRelevance`. A push to `main`
   does it, and the same run then populates all four. Until it lands, the three new blocks
   render their empty states — which is correct, but the pages are quietly waiting.
2. **Diagnose the failing `refresh` run.** It fails at "Run data jobs" (the proof step
   passes, so it is running the right code). `run.py` continues past a failed step and exits
   non-zero at the end, so at least one of ~17 jobs is failing while the rest work.
   `run.py` now prints a table of every step with its exit code as the **last** thing in the
   log, and writes the same table to `$GITHUB_STEP_SUMMARY`, so the failing step is readable
   from the run's own page instead of by scrolling the log. **Still needs a GitHub sign-in to
   read it** — that is the blocker, not the diagnosis.
3. **Product geography has no rows.** `geo.py` works — verified live: 175 countries, 51 US
   states, 5 PK provinces, and city resolution genuinely returns empty. It kept being
   cancelled by queue churn. Re-run `backfill` and it populates.
4. **`upcoming.py` has not run against the database yet**, so no scheduled dates are stored.
   Verified working against the provider (NVDA 2026-11-18, AAPL 2026-10-30).
5. **Thesis memory needs two days to say anything.** After the migration lands, check on the
   second day that statuses other than the opening ones appear. If every thesis is still
   `active` after a week of moving prices, the verdict parser in `thesis.py` has stopped
   matching what `setup.py` writes — which the `ThesisParsing` tests are there to catch, so
   check them against the current format first.
6. Attribution's posterior half, once outcome rows mature (~2026-10-31), then the Pareto
   attention front.

## Rules that are load-bearing

Everything in `brain.md` under "Rules for changes" — now 18 of them, the last five added
with these three layers — plus:

- Never count copies as confirmations. Counts that measure *information* count stories
  (`NewsLineage`), not rows.
- An unavailable input is recorded as unavailable, never as satisfied (`AssetSetup.missing`,
  and a condition that became unavailable counts as *changed* in `AssetThesis`).
- Conditions that disagree are always rendered (`AssetSetup.against`).
- No LLM anywhere. `requirements.txt` has no model SDK; every number and sentence is Python
  or SQL. Keep it that way.
- Pre-event state is frozen from observations dated **strictly earlier** than the event
  (`EventState`), which is what makes look-ahead bias structurally impossible rather than a
  rule to remember. `AssetThesis.openConditions` is the same idea applied to a state instead
  of an event: it is a copy, and anything that recomputes it has reintroduced the bias into
  the one place built to exclude it.
- Attribution names what a move was shared *with*, never what moved it. The test suite checks
  the generated sentence for the banned causal words.
- Relevance from `graph.py` is a reading order, never an impact estimate, and a score is
  never shown without the path that produced it.
