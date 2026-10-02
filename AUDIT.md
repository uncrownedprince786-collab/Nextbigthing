# Production audit — 2026-10-02

One authoritative matrix. Every row says how it was established. Where something was not
verified, the row says so rather than reading as a pass.

**Status: NOT FROZEN — blockers remain.** The blockers are in section 4 and none of them is a
code defect.

---

## 1. How each row was established

| word | means |
| --- | --- |
| **verified** | run or read in this session, with the result quoted |
| **test-covered** | asserted by the suite, which uses no database and no network |
| **read** | established by reading the code, not by running it |
| **unverified** | believed from documentation or inference, and not checked here |
| **blocked** | cannot be established from this session; section 4 says why |

---

## 2. The audit's main finding

The data and brain layers are substantially ahead of the output layer. Of 33 Prisma models,
**27 reach a reader**; 6 are written on every run and read by nothing:

| model | written by | reaches a reader | note |
| --- | --- | --- | --- |
| `Coverage` | `audit.py`, every run | **now yes** | surfaced in this session — home page brief, methodology full |
| `SourceReliability` | `audit.py` | no | source learning; time-gated, and no reader even once it matures |
| `Calibration` | `audit.py` | no | grade calibration; time-gated, floor-gated in the job and the query layer |
| `NewsLineage` | `lineage.py` | no | story clustering. The "four stories across four publishers" versus "one story across twenty" distinction is computed and never shown |
| `EventState` | `events.py` | no | 0 rows; every scheduled date is still in the future |
| `ProductAssetLink`, `EventLink`, `ThesisCheck`, `SetupTarget`, `InvestigationFinding`, `InvestigationHypothesis` | various | **yes** | read through Prisma relation includes, not by model name — an earlier pass of this audit wrongly listed them as unsurfaced |

Method: every model name matched against `lib/`, `app/` and `components/` for both a Prisma
accessor and a relation include. The second pass is why six rows moved from "missing" to
"present" — a string match alone was wrong.

## 3. Requirement matrix

### Data and refresh

| requirement | status | evidence | limitation |
| --- | --- | --- | --- |
| Silent source distinguished from an empty one | test-covered | `require_answer` in all four batch lanes; 233 tests | the counter differs per lane by necessity — rows for Yahoo and Binance, feeds parsed for news, published trading days for PSX |
| A cached source with zero *new* rows is not called broken | test-covered | the news lane counts feeds parsed, never `written`, because `ON CONFLICT DO NOTHING` makes new rows legitimately 0 inside the cache hour | |
| A failing lane preserves the lanes that worked | test-covered | `SourceSilent` is caught per lane, the transaction commits, `fail_on_silent` exits after `conn.close()` | found by audit, after an earlier guard in this session would have discarded a whole run |
| Transient failures retried, permanent blocks not | **verified** | live probe against a 503: three attempts, 18s, `None` returned, host usable afterwards. 403 excluded deliberately | |
| A dead host cannot consume the lane | test-covered | `RETRY_HOST_BUDGET`, worst case asserted under 120s | |
| No long transaction across HTTP | read | `psx.py` fetches in phase 2 and writes in phase 3 on a fresh connection | |
| Per-source coverage reported each run | test-covered | `coverage_report` prints rows, newest date and staleness per source | the output lands in the step log, which needs a GitHub sign-in to read |
| Yahoo lane green in production | **blocked** | — | only `refresh.yml` runs it |
| Crypto lane green in production | **blocked** | — | two real defects fixed this session; neither has run in production |
| PSX lane green in production | **verified** | `backfill #7` on `92a6f37` succeeded, running `psx.py full` with the new guard | row counts are in the log, which needs a sign-in |
| News lane green in production | **blocked** | — | |
| Intraday lane green in production | unverified | last documented state was 29 checks, 0 failures on 2026-10-01 | |
| Two consecutive green `refresh.yml` runs | **blocked, 0 of 2** | — | the gate the owner set; see section 4 |

### Market brain

| requirement | status | evidence | limitation |
| --- | --- | --- | --- |
| One canonical decision state per asset | read, present | `AssetSetup` per horizon; `SETUP_WORDS` in `lib/plain.ts` gives each state a reader label and a plain sentence | |
| Directional state derived from explicit evidence | read, present | `setup.py` stores each condition tested, the ones that failed in `against`, and inputs it could not evaluate in `missing` | |
| Entry, confirmation, invalidation, target ranges | read, present | `setup.py` condition strings, `SetupTarget` with `agreement`, parsed by `thesis.py` | rule 23 requires the format stay stable; a test runs the parser over every horizon |
| Targets method-separated, never averaged | read, present | three methods stored as three rows; `METHOD_WORDS` names each as a different question; rule 24 forbids averaging | |
| Multi-horizon disagreement shown, not averaged | read, present | one `AssetSetup` row per horizon, shown side by side; `HORIZON_WORDS` gives one canonical label set | |
| Horizon words consistent across pages | **verified** | `HORIZON_WORDS` is the single map; the home page's `HORIZON_SHORT` is a scan-row abbreviation of the same three keys | |
| Thesis memory, no rewriting of history | read, present | `AssetThesis.openConditions` is a copy of the row from the day the state appeared; rules 14 and 15 forbid re-derivation and make `broken` terminal | |
| Relevance window rather than a fixed holding period | read, present | thesis status plus invalidation level, not a day count | |
| Freshness visible | read, present | `AsOf` component, per-row as-of dates, home freshness table | |

### Catalysts and events

| requirement | status | evidence | limitation |
| --- | --- | --- | --- |
| Candidate catalysts linked to assets | read, present | `investigate.py` writes a row per check — news, attribution, peers, volume, calendar, graph, analog, intraday, product | this is the layer the mandate asks to "build completely"; it exists and is surfaced |
| Unexplained move is a first-class state | read, present | `notFound` is a stored field with content; `FINDING_WORDS` gives "Nothing there" its own label | by design, per the job's own docstring |
| No causal language | test-covered | the suite scans generated prose for "because", "driven by", "in response to", "reaction"; rules 10 and 16 | |
| Story count not copy count | read, present | `lineage.py` counts lineages, keeping the raw item count beside it | the distinction never reaches the reader — `NewsLineage` is unsurfaced |
| Future events surfaced per asset | read, present | `Event`, `EventImpact`, `upcoming.py`, `UpcomingBlock` on the home page | |
| Frozen pre-event state | read, time-gated | `EventState`, 0 rows, all 131 scheduled dates still in the future | also unsurfaced, so nothing will show it when it populates |

### Products

| requirement | status | evidence | limitation |
| --- | --- | --- | --- |
| Rising products with evidence per source | read, present | `ProductSignal`, five sources on matched windows | |
| Marketplace rows excluded from demand scores | read, present | rule 11 | `MarketplaceItem` is empty; the weekly job has not run |
| Geography only where data supports it | read, present | `ProductRegion`; `geo.py` verified for 175 countries, 51 US states, 5 PK provinces | table was empty at session start; `backfill #7` ran `geo.py` to completion, so it is likely populated — **unverified**, the count is in a signed-in log |
| Pakistan not inferred from global demand | read, present | PSX industries are first-class; regional rows carry their own source | |
| No invented city-level demand | read, present | province is the finest PK grain stored | |
| Currency carried everywhere | test-covered | rule 12 | |

### Learning

| requirement | status | evidence | limitation |
| --- | --- | --- | --- |
| Signal logged, outcome measured later | read, present | `signals.py` writes `SignalLog`; `accuracy.py` returns at 30 and 60 days and stores only the measurement | |
| Weights not moved on small samples | read, present | floors in the job and again in the query layer | |
| Sample size shown | partial | shown where calibration surfaces; `Calibration` itself is unsurfaced | time-gated — earliest maturity about 2026-10-30 |
| No look-ahead | read, test-covered in parts | rule 14, `openConditions` copied not recomputed; accuracy measures from the close the log recorded at the time | a full fresh look-ahead sweep across all nine state types was **not** performed this session |

### Non-functional

| requirement | status | evidence | limitation |
| --- | --- | --- | --- |
| Tests | **verified** | 233 passing, no database, no network | |
| Typecheck | **verified** | `tsc --noEmit` exit 0 | |
| Lint | **verified** | `eslint .` exit 0 (slow — it exceeds a two-minute foreground budget on this machine and has to be backgrounded) | |
| Production build | **blocked** | — | `next build` prerenders pages that query Postgres; no `DATABASE_URL` here |
| Free-tier measurement | **blocked** | last documented figure was 123 MB of 500 MB | needs the database |
| Deployed-app verification | **blocked** | the deployment answers HTTP 200 with a sign-in challenge, not the site | Vercel Authentication; reading the status code alone was previously misleading |
| SQL parameterisation | test-covered | every `INSERT` in `jobs/` scanned for bare reserved words and for column/expression count mismatch | |
| Secrets | read | `.env` gitignored and absent; workflows read repository secrets | |

## 4. Blockers

Three, and none is a code defect.

1. **`refresh.yml` cannot be triggered from here.** It runs on schedule or `workflow_dispatch`
   only, never on push. A dispatch needs a GitHub sign-in, which is the account holder's to
   give. So the 2-of-2 green gate stands at **0 of 2** and cannot be advanced from this
   session. `schema.yml` green does not count: it runs the derivation jobs, not `prices.py`
   or `psx.py`.
2. **No `DATABASE_URL`.** Nothing that needs the database can be measured or run: newest dates
   per source, row counts, free-tier usage, the production build, route smoke tests, and any
   end-to-end check of the two crypto fixes.
3. **Vercel Authentication fronts the deployment.** The deployed application cannot be checked
   from outside the account. This is the single external verification limitation.

What a sign-in is and is not needed for, measured rather than assumed: run **status,
conclusion and duration are public**; **step summaries and raw logs both need a sign-in** —
the run page answers `Sign in to view logs`.

## 5. Decision

**NOT FROZEN — BLOCKERS REMAIN.**

The freeze condition the owner set is two consecutive green production refresh runs. That
number is 0 of 2 and cannot be moved from this session. Declaring anything else would be
asserting a result that was never measured, which is the one thing this project's rules exist
to prevent.

Nearest path to frozen, in order:

1. Owner supplies `DATABASE_URL`, or dispatches `refresh.yml` twice.
2. Read the per-source coverage lines the run now prints: Yahoo Finance, Binance, Pakistan
   Stock Exchange daily closing file, each with count, newest date and age.
3. If both runs are green, record 2 of 2 in `HANDOFF.md` and freeze.
