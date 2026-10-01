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

## Released and verified on 2026-10-01

Three layers were added, pushed, and the migration applied in run `36857164898` at
11:43:58Z. All three jobs ran green in that run, and the row counts below were read back
from the database afterwards.

| Table | Rows after the first run |
| --- | --- |
| `AssetThesis` | **0 — the designed empty case.** Verified: every one of the 140 stored `AssetSetup` rows is `wait` (92) or `none` (48), and there is only one distinct `periodEnd`. A thesis exists only for `buy` or `short`, so there is nothing to open. The block renders its empty state, which is correct. |
| `ThesisCheck` | 0, for the same reason |
| `MoveAttribution` | 140 — leaders: specific 54, sector 34, market 30, none named 22. The `market + sector + specific = total` identity was checked against a real row and is exact to six decimals. |
| `GraphRelevance` | 95 on the first run, **23 after the fix below** — 12 one-hop product, 9 one-hop industry, 2 two-hop product |

**Two bugs were found by reading those rows, not by the tests.** Both jobs exited 0 and
wrote wrong output, which is the thing to remember: a green run here means the SQL was
valid, not that the numbers mean what the page says they mean.

- `graph.py` computed the product-origin weight by hand and skipped `DECAY`, so a product
  origin's first hop scored 1.0 while an asset origin's identical first hop scored 0.4. The
  list ordered by which *kind* of thing the catalyst sat on rather than by distance. Fixed in
  `f41bef7` by scoring the product as its own group of N+1 through `edge_weight`/`hop_score`,
  so the two paths cannot drift apart again.
- `attribution.py` said "the move is mostly shared with what is left after both" whenever the
  remainder led — self-contradictory, since that part is by definition the part that is *not*
  shared. 54 of 140 rows read that way. Fixed in `f41bef7`; the leading component now gets
  its own sentence.

**`GraphRelevance` went 95 → 23, and that is the fix working.** Before it, 72 of the 95
paths were two-hop product→industry chains scoring exactly 0.0222 — a single tie, so the
front page's nine rows were drawn arbitrarily from 72 indistinguishable ones. With `DECAY`
applied they score 0.0089, below the stated `MIN_SCORE` of 0.02, so they drop. That is
`MIN_SCORE` finally doing what its comment claims: a two-hop walk over two weak edges is
arithmetically real and means nothing.

The surviving scores are 0.4 and 0.2 (one hop, product), 0.16 and 0.08 (two hops, product),
and 0.0222 (one hop, industry). Note that a two-hop product chain now outranks a one-hop
industry link. That is deliberate and the docstring says so — the ordering is by closeness
*and* edge specificity, and sharing a ten-member sector is a weaker statement than two
recorded product links — but it does mean "fewer hops" alone does not predict the order.

What each one is:

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
methodology section stating the limit of each. 82 tests green, types and lint clean.

**The page-level check is still outstanding.** The Vercel project sits behind Vercel
Authentication, so the deployed site returns a login wall to anyone not signed in and cannot
be read anonymously. Everything above was verified by read-only `SELECT`s against the
database instead. The homepage's *inputs* are present and fresh — PK 8 industries / 70 assets
with 70/70 priced, 598 `Ranking` rows to 2026-09-30, `Analysis` regenerated at 11:46:18Z, 11
catalysts on the newest reading — but whether the page renders was not checked.

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

1. **Read the three new blocks on a real asset page.** This is the one thing in the release
   that has not been checked, because the site is behind Vercel Authentication. **AXP** is
   the best single page: 1 setup, 0 theses, 1 attribution and 2 relevance paths, so one view
   exercises a populated attribution block, a populated neighbourhood block and the thesis
   block's *empty* state. INTC, JPM, BAC, COPX, CPER, GC=F and IAU each have one relevance
   path and work too. The thesis block should say no directional read has been held, not show
   a blank card, and each neighbourhood row should print its chain in words.
2. **The failing `refresh` runs are two different failures, not one.** The previous handoff
   said "it fails at Run data jobs". That was true of the two earlier runs and **not** of the
   most recent one, which failed a step earlier:

   | Run | Event | Failed at | Data jobs |
   | --- | --- | --- | --- |
   | `36724733326` | schedule, 09-30 13:51 | Run data jobs | ran, failed |
   | `36789424283` | push, 09-30 23:07 | Run data jobs | ran, failed |
   | `36798989654` | push, 10-01 01:00 | **Apply pending schema migrations** | **skipped** |

   So there are two problems:

   **(a) The migrate step races `schema.yml`.** Run `36798989654` started at the same second
   as schema run `36798989644`, on the same push, and both run `npx prisma migrate deploy`.
   They sit in *different* concurrency groups (`nbt-database` and `nbt-schema`) — which is
   correct and deliberate for the data jobs — so nothing serialises the two migrations. The
   schema run won and the refresh run failed. Note that `Row counts after the run` succeeded
   in the same job, so the credential and the connection are fine; this is not a secrets
   problem. **`refresh.yml`'s own comment says "The schema is migrated here and nowhere
   else", and that is no longer true** — `schema.yml` migrates too. The fix is to delete the
   migrate step from `refresh.yml` and let `schema.yml` own it, which also makes the comment
   true again. Not done, because it changes the failure behaviour of the nightly run and
   deserves to be a deliberate decision rather than a drive-by.

   **(b) Something inside `run.py daily` fails.** Still undiagnosed, and still needs the log.
   `run.py` now prints a table of every step with its exit code as the **last** thing in the
   log, and writes the same table to `$GITHUB_STEP_SUMMARY`, which lands on the run's own
   summary page. Confirmed the hard way: GitHub shows **"Sign in to view logs"** even though
   this repository is public, and the public annotations API gives only
   `Process completed with exit code 1`. The step summary is the way around that wall, and it
   has not been exercised yet because no `refresh` run has happened since the change — the
   next scheduled run at 07:17 will produce it.
3. **Product geography has no rows.** `geo.py` works — verified live: 175 countries, 51 US
   states, 5 PK provinces, and city resolution genuinely returns empty. It kept being
   cancelled by queue churn. Re-run `backfill` and it populates.
4. **`upcoming.py` has not run against the database yet**, so no scheduled dates are stored.
   Verified working against the provider (NVDA 2026-11-18, AAPL 2026-10-30).
5. **Thesis memory cannot say anything until a `buy` or `short` appears.** Right now every
   condition read is `wait` or `none`, so `AssetThesis` is legitimately empty — that is the
   design, not a fault, and it was verified rather than assumed. Two separate things have to
   happen before the layer does any work: a directional state has to be written at all, and
   then a second day's read has to exist to compare against. If a directional state does
   appear and the thesis still reads `active` after a week of moving prices, the verdict
   parser in `thesis.py` has stopped matching what `setup.py` writes — the `ThesisParsing`
   tests pin the current format, so check those first.
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
