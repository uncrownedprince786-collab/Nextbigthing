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
- 32 tests green; the insert-shape test covers all 21 INSERTs in `jobs/`

## Not implemented (deliberately, with reasons)

- **Intraday.** Only daily closes are stored. Do not manufacture intraday from daily bars.
- **Investigation engine.** Nothing fetches filings or related-company news *in response* to
  a move. The catalyst flag detects that something arrived; it does not go looking.
- **Thesis memory.** `AssetSetup` records *why* a state exists, but nothing compares today
  against the day the state first appeared, so ACTIVE → WEAKENING → BROKEN does not exist.
- **Competing hypotheses, graph propagation, budget tiers.**
- **Bayesian posteriors.** Blocked on data, not effort: a likelihood ratio needs a measured
  `P(E|H)`, and **zero outcome rows have matured**. The log started 2026-10-01, so the
  earliest honest ones are ~2026-10-31. Choosing those numbers by hand is fabrication.

## Next, in order

1. **Diagnose the failing `refresh` run.** It fails at "Run data jobs" (the proof step
   passes, so it is running the right code). `run.py` continues past a failed step and exits
   non-zero at the end, so at least one of ~14 jobs is failing while the rest work. The log
   needs a GitHub sign-in to read.
2. **Product geography has no rows.** `geo.py` works — verified live: 175 countries, 51 US
   states, 5 PK provinces, and city resolution genuinely returns empty. It kept being
   cancelled by queue churn. Re-run `backfill` and it populates.
3. **`upcoming.py` has not run against the database yet**, so no scheduled dates are stored.
   Verified working against the provider (NVDA 2026-11-18, AAPL 2026-10-30).
4. Thesis memory, then attribution (company vs sector vs market-wide as competing
   hypotheses over stored evidence), then bounded graph neighbourhood.

## Rules that are load-bearing

Everything in `brain.md` under "Rules for changes", plus:

- Never count copies as confirmations. Counts that measure *information* count stories
  (`NewsLineage`), not rows.
- An unavailable input is recorded as unavailable, never as satisfied (`AssetSetup.missing`).
- Conditions that disagree are always rendered (`AssetSetup.against`).
- No LLM anywhere. `requirements.txt` has no model SDK; every number and sentence is Python
  or SQL. Keep it that way.
- Pre-event state is frozen from observations dated **strictly earlier** than the event
  (`EventState`), which is what makes look-ahead bias structurally impossible rather than a
  rule to remember.
