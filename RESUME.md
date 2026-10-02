# Resume here

## 0. State of play, 2026-10-03

**The live site is <https://nextbigthing-nu.vercel.app/>.** That is the production alias and it
serves whatever is on `main`. The long `nextbigthing-<hash>-...vercel.app` addresses are
per-deployment aliases of the same project; they are not a different site. Vercel Deployment
Protection was turned off by the owner on 2026-10-03, so the site is publicly readable.

### Credentials — do this first

`.env` holds a live `DATABASE_URL` for the Neon branch. **That password was pasted into a chat
transcript and should be rotated**: Neon console -> Roles -> `neondb_owner` -> Reset password, then
update the Vercel environment variable and `.env`. Nothing else depends on it.

The connection string is the **direct** endpoint (no `-pooler`). That is correct for local work and
required for migrations; the deployed app uses the pooled one from Vercel's env.

### What is true now

| | |
| --- | --- |
| Refresh lane | **green**, run #12, first since 2026-09-29 |
| Yahoo / PSX / crypto newest close | all **2026-10-02** |
| Decisions | 18 LONG, 21 SHORT, 121 WAIT across 160 assets |
| Markets producing a direction | US **and** PSX. Crypto does not — see below |
| Tests | 366 Python, 80 TypeScript, all green, no database or network needed |
| Database | 158 MB of a 500 MB free tier |

### The four things that changed the most

1. **Crypto closes have four venues**, not one. `fetch_crypto` walks Binance -> Coinbase -> Kraken
   -> Bitstamp and takes the first venue whose series is *current*, not the first that answers —
   Binance replies from a laptop and refuses a GitHub runner, and a stale-but-non-empty answer was
   the trap. The row records which venue supplied it. A shallow venue never replaces a deeper
   stored series, so nothing can shrink history to save a fetch.
2. **PSX history is deep now.** It was 178 closes per symbol against the 220 `jobs/horizons.py`
   needs, because the job asked for one file a *month* before the recent window. The archive
   publishes daily back to 2013-11-04. Now 595-629 closes per symbol and PSX produces directions
   for the first time. The container switches ZIP -> gzip before 2019 and the old reader silently
   called those days market holidays.
3. **The pipeline is seven per-source cron lanes**, not one 30-minute job. Each has its own
   concurrency group, which is load-bearing: GitHub keeps one *pending* run per group, so a shared
   group means the newer run cancels the queued one. That is what kept killing `geo.py`.
4. **`jobs/factors.py` measures the session once** and everything reads its row. Before it existed
   the volume and peer gates were live but unreachable and every decision came out Low.

### Where the work stopped

Four agents were mid-flight when this was written, each owning its own files:
asset page one-screen layout (`app/asset/[symbol]/page.tsx`, `components/decision.tsx`);
crypto direction investigation (`jobs/horizons.py`, `jobs/setup.py`);
plain-words sweep (`components/ui.tsx`, `lib/plain.ts`);
events news and junk filter (`app/events/page.tsx`, events queries in `lib/queries.ts`).
If their work is uncommitted, read it before changing those files.

### Known blockers, honestly

- **Crypto never reads LONG or SHORT.** Not a data problem: 2,202-3,001 closes each, all current.
  The `longer` setups exist and read `none` or `wait`, never `buy`/`short`, so the rule table
  correctly answers "incomplete". Either a rule written for equities does not fit a 7-day market,
  or crypto is genuinely flat. That was being investigated when this was written.
- **`ProductRegion` is empty.** `geo.py` no longer loses its work — it used to fetch for 55 minutes
  and write once at the end, so a cancelled run stored zero — but Google now rate-limits this host.
  It needs a run from an unblocked IP.
- **`DecisionLog.eventInDays`** is documented as sessions and stores calendar days. Future sessions
  cannot be counted without reading past the decision date. Fix the comment or the producer.
- **Chunking is real only for the Yahoo lane.** Products still runs whole per slice.
- **Universe is 160 assets.** Expansion is measured but unbuilt: 350 MB headroom fits the S&P 500 at
  3 years plus the top 100 coins plus all of PSX, but not everything at full depth.

### Things that will bite you

- `npx prisma generate` after a checkout, or `tsc` fails on models the generated client predates.
- Never commit `tests/test_brain.py` while any `jobs/*.py` is untracked. That turned CI red twice:
  the tests arrive without the implementation they assert against.
- `master` is the default branch and GitHub takes a scheduled workflow's *file* from it. Keep it
  level with `main` — `git push origin main:master` — or switch the default branch to `main`, which
  is the real fix.
- Migrations must use the direct endpoint. `prisma migrate deploy` takes a session-level advisory
  lock and a transaction pooler hands the connection back still holding it, which failed a run with
  `P1002`.

## 0b. What 2026-10-03 found and fixed

Two reds existed, and only one was a real defect in the daily lane.

**`schema` #50 was red, and it was never a broken commit.** It failed on `d8c9be4`, which
changes two Markdown files and no code, twelve seconds into "Apply pending schema migrations":

```
Error: P1002 ... Timed out trying to acquire a postgres advisory lock
(SELECT pg_advisory_lock(72707369)). Timeout: 10000ms.
```

`prisma migrate deploy` holds a **session-level** lock and releases it by ending its session.
`DATABASE_URL` is Neon's `-pooler` host — PgBouncer in transaction mode — which hands that
server connection back to the pool **still holding the lock**. The lock outlives the process.
Twelve seconds is the signature: two of startup, ten of timeout. Fixed — the migration now runs
over the direct endpoint (`DIRECT_DATABASE_URL`, else the pooled host minus `-pooler`), a test
forbids it inheriting the pooled URL, and brain.md rule **38** records it. If a `schema` run
still answers P1002, **restart the Neon compute** to drop pooled connections: the fix stops new
leaks and cannot clear one already held.

**And the reason two lanes were migrating at all — read this one carefully.** GitHub takes a
workflow's *file* from the **default branch**, which is `master`. `master` was **34 commits
behind** `main`, and `master`'s `refresh.yml` still ran `prisma migrate deploy`. So:

- Run #11's step 8 is "Apply pending schema migrations" — **a step that does not exist on
  `main`**, where it is "Refuse to run against a schema that is behind". That is the proof.
- The dispatch button only appears on the default branch, which `refresh.yml` says itself, so
  dispatching run #11 *necessarily* ran `master`'s stale file.
- `WorkflowLanes::test_exactly_one_workflow_applies_migrations` was **green the whole time**,
  asserting an invariant over a file production was not executing. So was the `schemacheck`
  guard: it has never once run in production.

`master` was fast-forwarded to `main` on 2026-10-03 (34 commits, 0 divergence, no merge). It
triggers nothing — every workflow is `branches: [main]`. **The proper fix is still to switch the
default branch to `main` in GitHub settings**, which removes the whole class of problem; until
then `master` must be kept in step, and `schema.yml`'s comment claiming the two branches "point
at the same commit" is the assumption that went stale.

## 0c. Two things with dates on them

- **`geo` is failing, not being cancelled.** Section 4 below says queue churn cancels it. A
  `backfill` log shows `geo` **FAILED exit 1** and `upcoming` **FAILED exit 2**. That is a
  different fault from the one documented, and `=== geo` from that log is needed to say more.
  The queue-churn mechanism in section 4 is still real; it is just not the whole story.
- **`ubuntu-latest` migrates to Ubuntu 26 on 2026-10-19**, and `actions/checkout@v4`,
  `setup-python@v5` and `setup-node@v4` are already being forced onto Node 24. Pin or bump
  before that date, not after it.

---

## 1. Before anything else

```bash
cd "C:\Users\NEW TECH\Nextbigthing"
```

A second, **stale** copy of this project exists elsewhere on the owner's machine — a
snapshot from 2026-09-30, under their `Documents` folder. Do not work in it; confirm you
are in the directory above before editing anything.

**`DATABASE_URL` is required and is not in this repo.** `.env` is gitignored and absent, so no
job and no script in `tools/` will run until it is set. Ask the owner for the Neon connection
string and put it in `.env` (copy `.env.example` for the shape). Everything works once it is
there.

## 2. What is green

Verified against the live production database on 2026-10-01, not merely built:

| | |
| --- | --- |
| Tests | **260**, all passing, no database or network needed |
| Types, lint, build | clean |
| `schema.yml` (release lane) | **green** — run `36917629683`, 9m 3s, all 20 brain jobs |
| Every job in the daily group | passes individually against production — see the table in `HANDOFF.md` |
| Intraday chain, end to end | **29 checks, 0 failures** (`python tools/intraday_chain.py`) |
| Acceptance criteria | **23 pass, 4 partial, 0 fail** (`python tools/acceptance.py`) |
| Database | 123 MB of a 500 MB free tier |

The four partials are time-gated, not unfinished: calibration, source learning, posterior odds
and event resolution all wait on outcome rows maturing (earliest ~**2026-10-30**) or on a
scheduled date passing. The machinery is live and measuring; it has nothing to measure yet.
`HANDOFF.md` explains each one.

## 3. What is red — the one open item

> **Superseded in part by section 0b.** Run #11 has since answered the question this
> section was written around: the lane is still red, and the failing step is named. The
> reasoning below is kept because it is how the step came to be named at all, but read
> section 0 first and do not re-run the investigation it describes.

**`refresh.yml` fails at "Run data jobs".** Latest: run `36918247571`, failure, 17m 11s. The
schema guard passed; the failure is inside `python jobs/run.py daily`.

Two causes were found and fixed on 2026-10-01 (`a7cdfa4`, `3cc83ee`), and **every job in that
group now passes when run on its own against production**. So what remains is almost certainly
environmental rather than a code defect.

**The hypothesis, and the next thing to do:** `yfinance` is likely throttled or blocked from
GitHub runner IPs. The evidence is that the same `prices` step stored **0** rows on the runner
while storing **37,537** locally minutes later, and `fetch_yahoo` cannot distinguish an empty
frame from a blocked one — `yf.download` returns an empty DataFrame and nothing raises.

To confirm it you need **one GitHub sign-in**. `jobs/run.py` already writes a per-step table to
`$GITHUB_STEP_SUMMARY` and `schema.yml`'s migrate step copies its own output there, but GitHub
does not render job summaries to anonymous visitors. Sign in once, open the failing run, and the
table names the step in a line.

**Done on 2026-10-02:** the silence itself is fixed. `require_answer` in `jobs/prices.py` now
fails the step when a whole download batch stores **0** rows — a blocked or throttled host,
rather than a market with no new bars — on the same line `jobs/marketplace.py` draws when every
Amazon category is blocked. One asset answering nothing is still data and is still only printed.
Two tests guard it, and brain.md rule **31** records why. `jobs/audit.py` already made this
distinction and is what caught the original run: it reports `Yahoo Finance daily closes —
partial — the newest day holds 2 records against a recent median of 60`.

**And then the actual defect turned up, in `fetch_crypto`.** It is a code bug after all, not
only an environment:

1. `insert_snapshots` gained `open`, `high` and `low` on 2026-10-01 in `aa64785`. The Yahoo
   caller was updated; the Binance one was not. Six fields reached a nine-name COPY unpack, so
   **every crypto insert has raised `ValueError` since that commit** — the same day
   `refresh.yml` started failing. The rows go through `crypto_rows` now, and a test unpacks it
   with the nine names COPY uses.
2. In the same function the market cap was dated off `closes[-1]` **before** the empty-series
   guard. CoinPaprika is not geo-blocked and Binance is, so the one host where `closes` is
   empty is exactly the host where a cap is present: `IndexError` on a runner, clean locally.
   The guard now comes first.

Both are invisible to the 221-test suite and to running each job locally, which is why "every
job passes individually" held while the group failed. **This is the better explanation of run
`36918247571` than the Yahoo block**, and it is fixed.

**Every batch lane now reports a silent source**, since the same hole was in all of them:
Yahoo and Binance count rows stored, the news lane counts *feeds that parsed* (new rows are
legitimately 0 on a rerun inside the cache hour, and the guard sits before the 120-day
retention sweep so a fetchless run cannot delete four months of articles), and `jobs/psx.py`
counts published trading days over a 120-day window where zero cannot be a holiday. brain.md
rule 31 explains why the counter differs per lane.

What is still open: the Yahoo-block hypothesis is now only a hypothesis, unconfirmed and no
longer needed to explain the failure. Confirming anything still wants one GitHub sign-in to
read the step summary — but the useful next move is simply to **re-run `refresh.yml`** and see
whether it passes. If it fails again, the new guards name the source in the step's own output.
**What a GitHub sign-in is and is not needed for**, measured on 2026-10-02 rather than
assumed: a run's **status, conclusion and duration are public** and readable anonymously from
the Actions list, so `tests #22`, `tests #23` and `schema #40` are confirmed green from
outside. **Step summaries and raw logs both need a sign-in** — the run page answers
`Sign in to view logs` — so the per-step table `run.py` writes is still unreadable without
one. Do not spend time looking for an anonymous route to a log; there is not one.

**And `schema.yml` green says nothing about this item.** It runs the derivation jobs — seed,
lifecycle, lineage, human, analogs, accuracy, setup, thesis, attribution, graph, horizons,
investigate, audit, analysis, stats. `prices.py` and `psx.py` run **only** in `refresh.yml`,
which triggers on schedule or dispatch and not on push. So the two crypto fixes are correct by
test and by reading, and **unverified against production** until that lane runs — tonight on
its schedule, or sooner by dispatching it, which needs the sign-in.

## 4. Known data gaps, each with its reason

- **`ProductRegion` is empty.** `geo.py` works (verified: 175 countries, 51 US states, 5 PK
  provinces) but keeps being cancelled by queue churn in `backfill.yml`.

  **The mechanism, found on 2026-10-02.** This is not a flaky lane. With
  `cancel-in-progress: false`, GitHub keeps only **one pending run per concurrency group**:
  queue a newer run and the one already waiting is cancelled. So several commits in quick
  succession cancel the intermediate runs in `nbt-schema` and `nbt-database` while they are
  still queued — never failed, never run. Nine pushes in one session reproduced it exactly
  once (`schema #47`, cancelled while `#48` queued behind it).

  Two consequences. A data lane that only ever runs on a push in a busy session may never
  execute, which is why `geo.py` has not completed. And **the refresh gate is vulnerable to
  it**: dispatching `refresh.yml` twice in quick succession can cancel the first while it
  waits, leaving one run rather than two. Let each refresh finish before starting the next.
  `backfill #7` on 2026-10-02 is what a run looks like when nothing supersedes it: `psx.py
  full` and `geo.py` both completed.
- **`MarketplaceItem` is empty** and `Coverage` reports Amazon Best Sellers as `silent`. It is a
  weekly job and has not run.
- **Binance crypto closes stop at 2026-09-29.**
- **`EventState` is 0.** All 131 scheduled dates are still in the future, so nothing has
  resolved. The first frozen pre-event state appears when one passes.

## 5. Not verified, and not claimed

**Visual production acceptance has not been performed.** The Vercel deployment sits behind
Vercel Authentication: it answers `HTTP 200` with a 341 KB body, and that body is the sign-in
challenge rather than the site. Reading the status code alone was misleading, which is worth
remembering.

What was done instead: the current commit was built and served locally against the production
database, and `/`, `/asset/INTC`, `/asset/AAPL`, `/methodology`, `/events` and `/products` were
all fetched and read. That verifies the code and the data. It does not verify the deployment.
The remedy is one setting — disable Vercel Authentication for production, or grant access.

## 5a. The audit, and what it found (2026-10-02)

`AUDIT.md` is the authoritative requirement matrix: every row says whether it was verified,
test-covered, read, unverified or blocked, and nothing reads as a pass on inference alone.

Its finding in one line: **the data and brain layers are well ahead of the output layer.** Of
33 models, 27 reach a reader. `Coverage` was surfaced in this session — concise on the home
page, in full on `/methodology`. Four remain written and unread: `SourceReliability`,
`Calibration`, `NewsLineage` and `EventState`. The first two are time-gated anyway; the third
hides a distinction the reader would want (four stories across four publishers versus one
across twenty); the fourth has no rows yet.

The audit's verdict is **NOT FROZEN**, for one reason only: the owner's gate is two consecutive
green production refreshes and that stands at 0 of 2, unreachable from a session that cannot
dispatch `refresh.yml` or read its log.

## 6. Where to read next

| file | what it holds |
| --- | --- |
| `HANDOFF.md` | the live state in full: the acceptance matrix with measured figures, the nine defects the acceptance pass found, the free-tier numbers, and what still needs a human |
| `brain.md` | **37 rules for changes.** Read these before editing a job; the last fifteen were earned by real bugs |
| `ARCHITECTURE.md` | the layer map, with every layer marked built / partial / absent honestly |
| `tools/README.md` | the four read-only verification harnesses and the two results that are easy to misread |
| `README.md` | how the system is put together and how to run it |

## 6a. The refresh lane, and the gate on it (2026-10-02)

The owner's standing instruction: **`refresh.yml` must come back green twice in a row before
any new feature work.** Neither has happened yet, and nothing in this session could make them
happen — `refresh.yml` triggers on schedule or dispatch, never on push, and a dispatch needs a
GitHub sign-in. `schema.yml` green does **not** count: it runs the derivation jobs, not
`prices.py` or `psx.py`.

What was made ready for those runs, all of it test-covered and none of it verified against
production:

| | |
| --- | --- |
| A blocked source costs its own rows only | `SourceSilent` is caught per lane, the transaction commits what answered, the step exits non-zero after `conn.close()`. Raising inside `with conn` would have discarded the whole run — rule 33 |
| Empty is told apart from success | `require_answer` in every batch lane, with the counter that is zero only when the source is silent — rows for Yahoo and Binance, feeds parsed for news, published trading days for PSX. Rule 31 |
| Transient failures retry | `nbt.get` retries a 429/500/502/503/504 or a timeout twice, pausing 3s then 12s, and stops retrying a host after `RETRY_HOST_BUDGET` so a dead source cannot eat the lane. Verified live against a 503: three attempts, 18s, then None, host still usable |
| Coverage is reported per source | every run prints rows, newest date and how stale each source is. Rule 34 |

**After the next refresh, read these three lines from the step output** — Yahoo Finance,
Binance, Pakistan Stock Exchange daily closing file — each with its count, newest date and age.
That is the pass/fail report, and it is in the log rather than the job summary on purpose.

## 6b. What the owner can and cannot do for you

Nothing is needed from them to make the system run. It is already automated: `refresh.yml` is
scheduled daily at **07:17 UTC** (12:17 in Pakistan) and weekly on Mondays, and `DATABASE_URL`
is already a repository secret, which is why the runs work at all.

**The default branch is `master`, not `main`,** and `master` is 33 commits behind. GitHub takes
a scheduled workflow's *file* from the default branch only — but this was already solved on
2026-10-01 in master's tip commit `4446a95`: the checkout names `ref: main`, so the file comes
from master while the code that runs is main's, and a verification step fails the run if the
checked-out SHA is not `origin/main`. Verified by reading master's actual file. Do not
"fix" this by assuming the schedule runs stale code; it does not.

What this session could not do, and what would change that:

| blocked | what unblocks it |
| --- | --- |
| Dispatching a workflow, reading any run log or step summary | `gh` is not installed. `winget install --id GitHub.cli` then `gh auth login`, run by the owner — they type the credentials and no agent sees them |
| Running any job, measuring newest dates, row counts or free-tier use, `next build`, route smoke tests | `DATABASE_URL` in `.env`. Gitignored and absent; the owner has it |
| Seeing the deployed site | Vercel Authentication fronts it. One setting, theirs to change |

## 7. Freeze status

Feature development was declared complete on 2026-10-01. Only these are in scope now:

1. a real production bug
2. a security issue
3. provider or source breakage
4. a free-tier or storage violation
5. required maintenance
6. the already-defined calibration, source-learning and event-resolution mechanisms, when their
   evidence naturally matures

The open item in section 3 falls under (1) and (3). Everything else should be left alone.
