# Resume here

## 0. State of play, 2026-10-06 (third session) — read this first

**Everything is committed and pushed. `main` and `master` are both at `558e137`, the working
tree is clean, and nothing is mid-operation.** Eight commits landed. The site is live and
usable at <https://nextbigthing-nu.vercel.app/> — all seven routes answered 200 after the last
deploy, and `/forex` renders 27 pairs including USDPKR.

### Read this before anything else: `master` is the default branch

**GitHub loads scheduled workflow *definitions* from the default branch, and the default branch
is `master`, not `main`.** The jobs then check out `ref: main` for their *code*. So a push to
`main` alone changes what the crons run but not *which* crons exist or how their jobs are
shaped. Two sessions have now been bitten by this; `cron-decision.yml` documents the first.

`master` had drifted five commits behind during this session, which would have made
`cron-calendar.yml` invisible to the scheduler and silently stopped the company calendars. It is
now fast-forwarded. **After every push to `main`, run `git push origin main:master`.**

### The outage this session found, which nothing had reported

`DecisionLog` had no rows for 2026-10-05 or 2026-10-06. Not stale — absent — while
`PriceSnapshot`, `AssetSetup`, `AssetAnalog` and `News` were all fresh to the day.

`cron decision` had been killed at exactly 20 minutes on three consecutive days. **GitHub
reports a timed-out job as "cancelled"**, which is why it read as a scheduling quirk rather than
as the outage it was. The cause: the `decision` group carried `upcoming`, which calls yfinance
once per Yahoo-sourced name with a forced 0.5s sleep — 126 requests, growing with the universe.
The 160 → 240 expansion on 2026-10-04 pushed the group past its budget.

The second half is worse: `tools/decide.mjs` was marked `if: always()` precisely so a failed
derivation still wrote rows, and **that net never fired, because `timeout-minutes` kills the job,
not the step.** The writer was reported `skipped` on all three days.

Fixed in `5c2a2eb`: `upcoming` joined `FETCH_STEPS` (so the `DECISION` filter excludes it) and
rides a new `cron-calendar.yml` at 03:40; `cron-decision.yml` became two jobs with `decide`
carrying `needs: derive` and `if: always()`, so it runs on its own runner with its own budget
however `derive` ended. Three guards now pin it, including that a job in the decision lane may
touch the network only if it declares a request ceiling.

### How to recover decisions by hand — this works and is 5 seconds

```
node tools/decide.mjs --dry-run    # compute and print, write nothing
node tools/decide.mjs              # write one DecisionLog row per asset
```

It reads whatever derivations are stored and needs nothing else. It was run four times this
session; the last wrote 267 of 267 rows for `periodEnd` 2026-10-06.

### What the eight commits did

| | |
|---|---|
| `ae28470` | `app/error.tsx`, `global-error.tsx`, `not-found.tsx`. Next 16 uses **`retry`**, not `reset`. No `loading.tsx` on purpose — a Suspense boundary starts the response streaming before `notFound()` is reached, and a streamed response returns 200, which would turn all four 404s into soft 404s. |
| `469e763` | Ranking rows were being silently dropped. `rank.py` stores `periodEnd` as the per-asset close date, and the read path kept only rows matching the newest — so a lagging asset was ranked and then deleted on the way to the screen, leaving ranks reading 1, 2, 4, 5. `lib/rankingWindow.ts` keeps every row in the window instead. `RANKING_WINDOW_LAG_DAYS = 90` is derived: largest observed lag 1 day, the two real windows sit 1739 days apart. |
| `5ffd0d2` | Three `daysUntil` implementations became one. The dead one in `lib/plain.ts` measured against `new Date()` rather than midnight and was a full day out for half of every day. `calendarDaysUntil` + `startOfToday` now live in `lib/format.ts`. `decisionInput.daysUntil` stays — different layer, UTC-anchored on both ends, and must not move with the renderer's time zone. |
| `a12abf7` | **An audit finding of mine was wrong and is withdrawn.** The pre-AI `totalReturn` pass is *not* dead: `jobs/analysis.py` reads both windows in `industry_shift()` and in the per-asset writer, separating them with `periodEnd <= PRE_AI_END`. Deleting it would have emptied half of every industry's analysis. The reasoning is now at the call site in `rank.py`. Also narrowed the `use client` guard, per rule 37. |
| `5c2a2eb` | The decision-lane outage above. |
| `7966895` | Forex: 27 pairs. |
| `fca7ebc` | The swing rule. |
| `558e137` | Four market pages and the front-page block. |

### Forex, as built

27 pairs in four industries (`fx-majors` 10, `fx-asia` 10, `fx-emerging` 4, `fx-europe` 3),
~2,020 daily bars each back to 2019-01-01.

- **Source is Yahoo, not Frankfurter.** Frankfurter is free and ECB-backed but **has no PKR**,
  which makes it useless here. Yahoo serves `USDPKR=X` and needed no new integration at all:
  `yahoo_assets` selects on `source = 'yahoo'` and never on assetType.
- **Three candidates were checked and dropped:** USDAED and USDSAR are hard pegs, USDHKD trades
  in a ~1% band. Ranking them by return is ranking noise. A test pins their absence.
- **Yahoo answers `volume = 0` for every FX bar** because FX is OTC with no consolidated tape.
  It is stored as NULL. Writing the 0 would be read as real by `avg_volume` in `rank.py`, by
  `write_rising`'s volume check, and by `VOLUME_CONFIRMS_AT` which divides a session by its own
  average — 0/0. Verified: volume rows 0 on all 27.
- `capBasis` is `none` for all of them, so the size tables on an FX industry page hold no rows
  by construction and the page says so in words.
- `STALE_AFTER_DAYS.FX = 4`. `marketOf` reads forex off the **asset**, not the industry.
- The FX industry pages are not in `generateStaticParams` (it keys off `sizeNow` rankings, which
  FX has none of by design) so they render on demand. That is fine, not a bug.

### The swing rule, and why it had never produced a short

`jobs/setup.py` required an AND of four conditions. Measured across all 267 assets on
2026-10-06: **volume sits at or above its own average for 9% of them, and news tone reads
negative for 3%.** The conjunction produced 2 buy setups out of 266 and, in the whole life of the
table, not one short. It also made FX structurally impossible — no pair has volume to satisfy.

Now the trend is mandatory and the other three are counted, `CONFIRMS_NEEDED = 2`. Two and not
one, because trend-plus-one calls 146 of 267 names directional on the same day, which is not a
signal. **A missing input cannot count toward the two**, which is what keeps it honest rather
than merely looser.

```
swing setups   buy  2 -> 20     short 0 -> 9
decisions      LONG 29 -> 36    SHORT 19 -> 25
confidence     High 5 -> 17
```

### Where the signal stands, 2026-10-06

267 assets: 203 stock, 27 forex, 27 crypto, 8 etf, 2 commodity.

```
LONG 36   SHORT 25   WAIT 206
High 17   Medium 24  Low 226
gates: incomplete 163, long 36, unexplained-move 32, short 25, peers-against 10, no-invalidation 1
```

Input coverage is complete: prices, factors, rankings and decisions all 267/267, setups 266/267.
**Entry bands are 75/267 and that is correct, not a gap** — a band only exists for a directional
setup, and there are 75 of those. An earlier note in this session calling it a gap was wrong.

## 0a. What is pending, in the order I would do it

1. **The products card is missing from the front-page block.** The ask was five cards — stocks,
   crypto, PSX **and products**. Four were built. Products carry a different decision shape
   (`lib/productDecision.ts`, `decideProduct`), so the card needs its own wiring rather than
   `ASSET_CLASSES`. This is the first thing to finish.
2. **`incomplete` is 163 of 267.** Down from 176, and the rule is no longer the binding
   constraint — the inputs are. News is missing for 40 assets and relative strength for 7.
   Raising those raises the signal honestly; loosening the gate further would not.
3. **The scheduled `cron decision` has not yet gone green on its own.** Next run is 15:10 UTC.
   The writer was exercised by hand four times, and the architecture guarantees rows even if
   `derive` overruns, but the schedule itself is unproven. **Check this first next session:**
   `curl -s "https://api.github.com/repos/uncrownedprince786-collab/Nextbigthing/actions/workflows/cron-decision.yml/runs?per_page=5"`
4. **`npm audit`: 5 high advisories, all in build/CLI tooling** (`mysql2` and `deepmerge-ts` via
   the prisma CLI, `source-map-js` via postcss). None on the request path. **Do not run
   `npm audit fix --force`** — it downgrades prisma 7.10 to 6.19, which is far worse than the
   exposure. Wait for a prisma patch.
5. **Cross-language constants are a comment, not a constraint.** `THIN_NEWS_BELOW` (TS) and
   `MIN_ITEMS` (`jobs/human.py`) are both 8, and `ANALOGS_CONFIRM_MIN` and `MIN_MATCHES_LOW`
   are both 8, with nothing pinning either pair. A test reading both files would close it.

## 0b. Things that cost time this session — do not repeat them

- **Do not run `jobs/run.py decision` from a non-US host.** Round trip to Neon from Pakistan is
  **238 ms**, and `rank.py` is a per-asset query loop (~2,670 queries at 267 assets), so `rank`
  alone took **14.0 min** locally against roughly **0.2–1.3 min** on a same-region runner. Local
  timings of these jobs are ~15x inflated and are **not** a production signal. Let CI run the
  lane; use `decide.mjs` locally, which is 5 seconds.
- **A local derivation run sat 41 minutes on `lineage` with no output** and had to be killed,
  almost certainly lock contention with a CI `backfill` triggered by the same push. Kill a job
  that has produced no output for five minutes rather than waiting on it.
- **Several jobs buffer stdout to the end.** `setup.py` printed nothing until it finished.
  Check progress by querying the table it writes, not by tailing the log.
- **`setup.py` stamps `periodEnd` from `date.today()` (local) while `decide.mjs` uses UTC.** On a
  UTC runner they agree; from a UTC+5 host they differ by a day. Harmless in CI, confusing
  locally — it is why `AssetSetup` read 2026-10-07 while decisions read 2026-10-06.

## 0. State of play, 2026-10-04 (second session) — read this first

**The 240-asset expansion is finished and every one of the 240 has a verdict.** The whole
decision lane ran green from this host and `DecisionLog` now holds one row per asset for
`periodEnd` 2026-10-04. Nothing is mid-operation. Two code fixes are committed on `main` and
**not pushed**.

### What the previous session's backfill actually needed

The three price steps it listed were already done by the time this session looked — the cron
lanes had filled them. All 240 assets had closes: crypto 27 (newest that day), US and metals 128
and PSX 85 (newest 2026-10-02). The real gap was two steps further down, and it was not visible
from the price tables at all:

- **all 80 new assets had no `AssetFactor` row**, and
- **all 80 had no `DecisionLog` row** — the table sat at exactly 160 assets, the old universe.

### Why `DecisionLog` had stopped at 160: the writer did not parse

**`tools/decide.mjs` was not a runnable file, and had not been since the commit that taught the
three readers of `AssetAnalog` to agree on one row.** That commit added a SQL comment inside a
template literal which quoted a helper name in backticks — ```pickAnalog``` — and a backtick
inside a template literal ends the template literal. Node refused the module outright with
`SyntaxError: missing ) after argument list`, pointing 20 lines up at the query whose string it
was still reading.

So the last step of the previous session could never have run, whatever else was true. This is
the second time an interrupted session has left a non-parsing file on `main` — the first was the
doubled quote in `components/ui.tsx`. **`node --check` on a tool, before concluding a lane is
flaky, is cheaper than anything else here.** The comment is now unquoted, matching the SQL
comments around it.

### The run, all of it green

Run in three stages rather than one `run.py decision`, because that call died at the session's
two-hour background limit last time and the result was never seen. Every step rc=0:

| stage | steps | time |
| --- | --- | --- |
| — | `factors` | 10s |
| 1 | `analogs` 5m33s, `upcoming` 3m30s, `lifecycle` 31s, `rank` 13m44s, `confidence rankings` 4m49s, `events` 45s | ~29 min |
| 2 | `lineage` 32m27s, `human` 7m40s, `setup` 8m01s, `thesis` 5m44s, `attribution` 3m15s, `graph` 12s, `intraday` 6m19s, `horizons` 6m09s | ~70 min |
| — | `node tools/decide.mjs` | wrote **240 of 240** |
| 3 | `investigate` 4m07s, `accuracy` 1m18s, `analysis` 7m25s, `audit` 14s | ~13 min |

`lineage` is still the one that looks like a hang: 32 minutes for 3,900 stored headlines, and it
prints nothing from start to finish. It is not stuck.

### What the site says now, confirmed against the database

The live home page serves "priced to 2026-10-04" and its counts match `DecisionLog` exactly —
checked both sides rather than trusting one.

| | |
| --- | --- |
| LONG | 32 (4 High, 25 Medium, 3 Low) |
| SHORT | 25 (2 High, 13 Medium, 10 Low) |
| WAIT | 183 |
| directional confidence | **6 High, 38 Medium, 13 Low** |
| assets with no verdict | **0** |

Gates behind the 183 WAITs: `incomplete` 159, `unexplained-move` 14, `peers-against` 9,
`no-invalidation` 1.

**17 of the 80 new names came out directional** and now appear on the home list — TER (the only
new High), ACN, AMAT, CRWD, MA, MRVL, NET, SNPS, SWKS, TMO, V, SPGI, UBER, BSX, SYK,
`near-near-protocol` and `uni-uniswap`. The other 63 read WAIT, almost all on `incomplete`.

**No asset was skipped.** The two thinnest PSX names are genuinely short histories rather than
failed fetches — TISL has 29 stored closes and SELECT 58, both recent listings — and `factors`
reported the one below its 51-close floor in the row's own `bars` field rather than hiding it.

### The timezone fault is fixed, and it mattered to this run

`iso()` in `lib/decisionInput.ts` formatted a `@db.Date` with `toISOString()`. `pg` materialises
a date column at **local** midnight, and east of UTC that instant is the previous day in UTC, so
`asOf` came out a day early on any non-UTC box. **This host is UTC+5**, which is the direction
that breaks, and `asOf` feeds the staleness gate with `STALE_AFTER_DAYS.Crypto` of 2 — so it
would have written `stale` verdicts for current coins during the very run above. It was fixed
before `decide` ran, not after. `iso()` now formats from local parts, the rule `dayOf()` in
`decide.mjs` already used.

**369 Python tests and 107 TypeScript tests pass.** Note the Python count: `tests/test_brain.py`
is the only Python test file and it reports 369, not the 373 this file claimed earlier.


## 0a. The refresh lane — proven green, from this host

`python jobs/run.py daily` was run against production on 2026-10-04 and **17 consecutive steps
came back green with zero failures** before the session's own two-hour background limit stopped
it during step 18 (`investigate`). It was not a failure and nothing in the lane errored.

```
prices yahoo crypto news  ok 15.2 min    <- the step that fails on GitHub runners
psx recent                ok  2.7 min
factors                   ok  0.2 min
analogs                   ok  3.8 min
upcoming                  ok  2.2 min
lifecycle                 ok  0.2 min
rank                      ok  9.0 min
confidence rankings       ok  3.1 min
events                    ok  0.6 min
lineage                   ok 20.5 min    <- see below
human                     ok  5.4 min
setup                     ok  5.6 min
thesis                    ok  3.7 min
attribution               ok  2.1 min
graph                     ok  0.7 min
intraday                  ok  6.8 min
horizons                  ok  4.6 min
investigate               killed by the session, not by an error
```

Two things worth carrying forward. **`lineage` takes 20.5 minutes and prints nothing while it
runs**, which is the single slowest step and looks indistinguishable from a hang; it clusters
~2,900 stored headlines. And **`prices` is green from a laptop** — 880 Yahoo rows, 26,902 crypto
rows from Binance — which is consistent with the standing hypothesis that the GitHub failures are
the runner's IP and not the code. That still needs one signed-in look at a real run to confirm.

## 0b. What was fixed on 2026-10-04, and why each one mattered

An audit of five live assets against the rule table found eight faults. **Five are fixed and
deployed; three are written down in section 0c and are not done.**

1. **The tree did not compile.** A doubled quote in `components/ui.tsx` left by an interrupted
   agent. Nothing could have been built or deployed from `main` until it was removed. One
   character, and it blocked everything else.

2. **A short's stop was on the winning side.** `jobs/setup.py` and `jobs/horizons.py` both chose
   `entry = the window's high` and `invalidation = its low` without consulting `state`. Right for
   an up read, inverted for a down one — WTL read SHORT at Rs.1.00 and the panel printed "Exit if
   wrong Rs.0.99", a stop one percent below a short, on the side the trade needs price to reach.
   STLA was the same at $4.40 with a $4.36 stop. Both levels and both stored notes are mirrored
   by state now. `run_targets` in horizons.py had always branched on `state`, so the repository
   already held the correct form of the statement while two of its three level-writers disagreed.

3. **The analog lean never reached the rules.** `toDecisionInput` built `{count, lowPct, highPct}`
   and dropped `medianPct` and `positive`. `analogConfirms` returns null the instant either is
   missing, so one of the three legs `confidenceFor` counts was dead for all 160 assets, both
   directions, always. Nothing upstream was broken — analogs.py writes both columns, queries.ts
   selects them, both bundle builders carry them. Restoring two fields in one object literal moved
   **Low 154 / Medium 4 to Low 133 / Medium 25** with no rule, threshold or grade touched. ATRL
   went Low to Medium on 102 stored days.

4. **The crypto volume denominator.** A seven-day market measured against a weekday-dominated
   average reports the calendar, not the market. All ten coins failed the 1.2x volume gate on a
   Saturday bar at 0.11x-0.52x while every trend read up. Baseline now drawn from comparable
   sessions; zero US or PSX ratios moved. **It changed no verdict** — the ratios roughly doubled
   and none crossed 1.2 — and that was kept rather than papered over. brain.md **rule 39**.

5. **Four sentences that lied.** "Setup is flat" over a direction the job had measured and
   withheld; "No longer-term reading stored" over a stored row whose state was `none`; "not
   enough history to compare" over 102 stored days; and the home list and asset page quoting
   different analog rows (ABBV printed one range on its page and another in the list) because
   three readers of one table each picked their own.

Also: the news on an asset page is ranked rather than newest-first — ATRL led with a sustainability
award over a $5bn government programme — an events page strip of market news beside the dividend
dates, and plain words plus a legend on the home page.

**373 Python tests and 106 TypeScript tests pass.**

## 0c. The two faults that are NOT fixed

These are real, they are evidenced, and nobody should rediscover them from scratch.

- **"When NOW" over a level that has not been reached.** `entryLevel` is a trigger to be exceeded
  — setup.py's own `entryNote` says "a close above it would be a move past where it recently
  stalled" — but `entryZone` turns `[stop, trigger]` into an inclusive band and `timeSenseFor`
  reports NOW for any close inside it. Live: ABBV says NOW at 262.82 against a trigger of 266.28;
  ATRL says NOW at 1,189.43 against 1,199. This is also why every entry band's low equals its
  stop. Fixing it means deciding what the band is actually for, which is a design question and
  not a typo.
- **`jobs/setup.py`'s `failed` list is incomplete.** For the `wait` state it covers only three
  cases, and the news one is guarded by `and up_trend`. A down trend blocked by a non-negative
  tone produces an empty list and the headline "...the conditions are not all present: some
  inputs are unavailable" while the row's own `missing` column says "none". Live on STLA and WTL.

The third one on this list, the timezone-dependent `iso()`, **is fixed** — see section 0. It was
fixed first because it would have corrupted the 240 rows `decide` was about to write from this
UTC+5 host.

Note what both remaining faults have in common with it: each is a disagreement between two
readers of the same stored row, not a bad measurement.

## 0d. Still true, still outstanding

- **Rotate the Neon password.** It was pasted into a chat transcript. Neon console -> Roles ->
  `neondb_owner` -> Reset password, then update the Vercel environment variable and `.env`.
  Nothing else depends on it. **Outstanding for three sessions now**, and it is the only item
  here that is a standing exposure rather than a tidiness problem.
- **`gh` is not installed**, so no workflow can be dispatched and no run log or step summary can
  be read from here. The owner's gate of two consecutive green `refresh.yml` runs is still 0 of 2
  as far as GitHub is concerned, whatever a laptop proves.
- **The default branch is `master`.** Pushes have to go to both `main` and `master` to keep them
  level, because GitHub takes a scheduled workflow's file from the default branch. Switching the
  default to `main` in GitHub settings removes the whole class of problem.
- **Two commits sit on local `main`, unpushed**: the `decide.mjs` parse fix and the `iso()`
  timezone fix with its regression test. Pushing them deploys, so it was left to the owner.
- **`ubuntu-latest` moves to Ubuntu 26 on 2026-10-19.** Pin or bump the actions before then.

---

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
