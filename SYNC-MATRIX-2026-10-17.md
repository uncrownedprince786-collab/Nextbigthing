# Operational sync matrix — 2026-10-17

One row per source or source category, built by tracing every lane from adapter through
fetch, persistence, freshness reporting and downstream consumers (WORKSTREAMS §3.2). Facts
come from the code as it stands on `dbe3004`; where a fact is not in the code it says so
rather than estimating. No live database reads were made while building this — measured
cadences below are the schedules and budgets the workflows declare, not observations of the
production database. Successful-update timestamps must be re-read from `ChunkRun`/`Coverage`
when the pooler has headroom (B3).

**Design position, stated once.** Every source here is HTTP polling on a GitHub Actions
schedule. There is no WebSocket or streaming client anywhere in `jobs/**`. That is the
correct design for these sources: exchange daily files, RSS feeds and REST APIs have no
stream to hold open, and a free-tier runner cannot hold one anyway. Second-level freshness is
therefore achieved where it is achieved by *polling often enough within the source's own
cadence* (live quotes: 5 min in-session), not by streaming. The correct cadence per source is
the row below it; polling every source every second would be both impossible and wrong.

## A. Price and quote sources

| # | Source / category | Coverage (instruments) | Calendar | Lane & schedule | Freshness target & reason | Rate/quota/storage | Retry / dedup / gap recovery | Quality & alerts | Tests |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **US equities + ETFs** (Yahoo Finance `yf.download`, `/v8/chart` fallback) | all `Asset.source='yahoo'` stock/etf (~249 names) | NYSE/Nasdaq 09:30–16:00 ET; `forming_sessions` refuses a not-yet-closed session; weekday coverage SQL `ISODOW < 6` | `run.py us-prices --chunk i/4` ← `cron-us-prices.yml` `50 1,7,13,21 * * *` (post-close 21:50 is the load-bearing slot) | `STALE_AFTER_DAYS[market]` via `lib/health.ts`; Coverage 96 h, criticality 1.0. "A Friday close is still the newest thing on a Monday" | `HOST_DELAY` 1.5 s; `YAHOO_DOWNLOAD_BUDGET=2` batch downloads/run; `MIN_ANSWER_SHARE=0.75` | upsert `(assetId,date)`; `is_full` delete+rewrite; 14-day correction window; `SourceSilent` on empty batch; breaker `OPEN_AFTER=3` | Coverage row "Yahoo Finance daily closes (US)"; ChunkRun per slice; watchdog `cron-us-prices.yml` | `test_brain.py` (partial-day, breaker), `health.test.ts`, `pricePrecision.test.ts` |
| 2 | **Crypto daily closes** (Binance→Coinbase→Kraken→Bitstamp chain) | 76 CoinPaprika-slugged coins | none — the one 7-day source; Coverage 48 h = one missed run | `run.py crypto` ← `cron-crypto.yml` `5 */2 * * *` | 48 h / crit 1.0, watched as a venue *set* (any venue's close counts) | `HOST_DELAY` 0.5–1.0 s per venue | same upsert/refusal/breaker; venue fall-through is normal and recorded in `ChunkRun.source` | Coverage `CRYPTO_VENUE_SQL`; breaker; watchdog | `test_brain.py` breaker/price-lane tests |
| 3 | **PSX equities** (dps.psx.com.pk `mkt_summary/YYYY-MM-DD.Z`, `closing11.lis`) | ~85+ Karachi names; archive from 2013-11-04 | PSX sessions; 404 = closed day, never filled; `BACKTRACK=9` for holiday runs | `run.py psx recent` ← `cron-psx.yml` `40 12,16,20 * * *` (three attempts because one run sat a day behind); `psx full` weekly | 96 h / 0.8 | 1.5 s delay; `DEEP_FETCH_BUDGET=250` dense files/run (host refuses ~600+ requests/session); stored dates never refetched (`ttl_for` 1-year cache) | magic-byte sniff (ZIP vs gzip) in `unpack()`; upsert; recent-window backfill repairs gaps; `FILLED_FRACTION=2/3` tells a crashed batch from a quiet session | Coverage "PSX daily closing files"; ChunkRun; watchdog | `test_brain.py` unpack tests (ZIP/gzip/HTML-404/truncated), cron-late test |
| 4 | **Forex + commodities daily closes** (Yahoo, same lane as #1) | 27 FX pairs, 8 commodities (incl GC=F gold, SI=F silver, CL=F oil, HG=F copper via yahoo commodity type) | weekdays for commodities; FX 24/5 but weekend bars excluded from freshness | same `us-prices` lane, chunked with #1 | Coverage 96 h / 0.8 (FX), 1.0 (commodity); split rows so one market's weekend cannot hide another's silence | same as #1 | same as #1 | Coverage rows per market + `yahoo_summary` worst-of | `forex.test.ts`, `commodities.test.ts` |
| 5 | **Live quotes** (CoinPaprika tickers + Yahoo quote endpoints) | every active asset, one `LiveQuote` row each | per-market `marketOpen()`; a closed market's stale quote is not a fault | `jobs/live.py` ← `cron-live.yml` `*/5 13-21 * * 1-5` (US session) + `7,22,37,52 * * * *` (crypto 15-min, round the clock); gated by repo var `LIVE_QUOTES` | `QUOTES_STALE_AFTER_MINUTES=60` while trading (four missed runs; GitHub dropped most of a `*/15` schedule on 2026-10-10); 72 h = lane off, reported not a fault | single batched crypto request; 1.5 s delays | forward-only upsert on `quotedAt` (never moves a quote backwards); **never an input to any decision** | `quotes:<market>` problems; watchdog lane; `/api/quote` read-only | `liveQuote.test.ts`, `runState.test.ts` |
| 6 | **Intraday bars** (Yahoo chart API, 5-min canonical, 15/30/60 derived) | active-set only: monitored assets, unusual moves, catalyst neighbours (~bounded, `MAX_REQUESTS=60`/run) | provider session phases; `expected_bars()` vs stored; PSX `unsupported` with reason | `run.py intraday` inside `cron-decision.yml` `10 22 * * *` (no standalone cron) | `STALE_AFTER_MIN_NO=90`; retention 7 days matched to `range=5d` | `MAX_REQUESTS=60` hard ceiling; 1.5 s delay; 2-hour cache within a run | "will not invent a bar": gaps stay gaps; derived bars only when every component present; forming bars not mislabelled | `IntradaySession.status`; `getIntradayHealth`/`getIntradayCoverage`; ChunkRun | `test_brain.py` intraday block (~800 lines), `gapLine.test.ts` |

## B. News, events and macro

| # | Source / category | Coverage | Calendar | Lane & schedule | Freshness target & reason | Rate/quota | Retry / dedup / gap | Quality & alerts | Tests |
|---|---|---|---|---|---|---|---|---|---|
| 7 | **Asset news** (Google News RSS per asset; Bing → Yahoo RSS fallback) | ~318–548 feeds/run across 267+ assets | rolling `NEWS_WINDOW_DAYS=30` (+3 slack) | `run.py news --chunk h/2` ← `cron-news.yml` `20 */2 * * *`; 25-min job, 20-min step | `NEWS_STALE_AFTER_HOURS=6` (three missed runs); Coverage 36 h / 0.9. Value is a function of recency | `HOST_DELAY` 2 s; `NEWS_FALLBACK_BUDGET=150` fallbacks/run (primary pass uncapped); per-host 1 s sleep makes 318 feeds a ~5-min floor | `nbt.get` retries (429/5xx, 3+12 s backoff, 8/host budget); lineage dedup (Jaccard union-find, `isOriginal`); per-lane commit | Coverage counts *feeds answered*, not rows; ChunkRun; watchdog | `test_brain.py` news-lane tests incl. timeout room and fallback budget |
| 8 | **Macro & geopolitical feeds** (`MACRO_FEEDS` + Ministry of Finance page, `MOF_ITEM_RE` parse) | untargeted rows (`assetId IS NULL`), read by `getMacroNews` and the macro gate | rolling | same `news` lane | same 6 h / Coverage row shares "Google News RSS" label family; SBP/MoF feeds group by `source` prefix so a dead feed cannot hide behind a live one | same lane budgets | same; `publishedAt` (provider) kept distinct from `createdAt` (collection) — publication time is never retrieval time | freshness panel groups by `MACRO_SOURCE_PREFIX` | `test_brain.py` macro-lane tests, `macroGate*.test.ts` |
| 9 | **Corporate calendar** (yfinance `Ticker.calendar`) | stocks/ETFs only (~126–240 requests) | forward-dated company events; "a date that moves is worth catching the day it moves" | `run.py calendar` ← `cron-calendar.yml` `40 03 * * *`; own lane since the 2026-10-04 decision-lane outage | **No Coverage row exists** (gap, see below); ChunkRun only | forced 0.5 s sleep/call | idempotent writes keyed (asset, date) | ChunkRun; watchdog re-reads health after it completes but cannot dispatch it | `test_brain.py` (upcoming in FETCH_STEPS, calendar group) |
| 10 | **Verified events / press / reactions / earnings corpora** (research foundation, GDelt + SEC evidence) | **37 of 617 instruments own-scope (6.0%)** — measured 2026-10-17, see `BRAIN-CORPUS-COVERAGE-2026-10-17.md` | historical, PIT-disciplined (strict-before events/press; closed-window reactions) | not a cron lane — acquisition harnesses under `tools/foundation/**`, frozen artifacts under `data/foundation/events/**` | research-grade, not freshness-grade | GDelt/GKG quotas apply to new acquisition | dedup with `publishedAt`; unresolved names (GME) counted not dropped | frozen manifests + coverage JSON | `test_evidence_corpus.py`, `test_historical_corpus.py` |

## C. Product and marketplace signals

| # | Source | Coverage | Lane & schedule | Freshness target | Rate/quota | Retry / dedup | Quality & alerts |
|---|---|---|---|---|---|---|---|
| 11 | **Product interest** (Google Trends, Wikipedia, HN Algolia, Google News, Reddit) | product list (~30 products) | `run.py product-signals` ← `cron-products.yml` `10 3 * * *` (matrix part `signals`, `max-parallel: 1`) | 240 h / 0.6 each, **per sub-source** — "an aggregate over independent providers cannot report any of them" | trends 6 s, reddit 9 s + `REDDIT_BUDGET_MIN=8` wall-clock; Trends 429s serialised the lane for 90 min once | upsert `(productId,source,metric,periodEnd)`; `blocked` ChunkRun status for throttled sources | 5 Coverage rows; reddit excluded from score since 2026-10-12 (`DEGRADED_SIGNALS`); watchdog **cannot** dispatch products (not in `LANES`) |
| 12 | **Marketplace ranks** (Amazon Best Sellers, 9 categories × 30) | 270 rows verified 2026-10-03; eBay absent (403) | `run.py marketplace` inside `cron-products.yml` part `geo` + weekly lane | 240 h / 0.4 — "noticing the page stopped answering *at all*" | amazon 4 s delay | upsert by item key | Coverage row; ChunkRun; **no dedicated test found** |
| 13 | **Regional breakdown** (Google Trends via pytrends: worldwide, US region, PK region) | product regions, top 15 rows/list; city granularity unavailable (empty frame, never substituted) | `run.py geo` ← `cron-products.yml` part `geo`; weekly lane only | 240 h / 0.5 — "one skipped week is late, not dead" | 8 s delay, 3 attempts, `GEO_FETCH_BUDGET_MIN=18` in cron (45 default) checked **before every breakdown** | per-product commit (interrupted run keeps rows); `why()` surfaces the real HTTP status | Coverage `ProductRegion` row (table was empty for weeks while the source was live — that is why the row exists); no watchdog lane |

## D. Derivation, mirror and operations (no external source)

| # | System | Schedule | Notes |
|---|---|---|---|
| 14 | **Decision/reasoning chain** (`pool…retention`, 23 steps, no network) | `cron-decision.yml` `10 22 * * *` | 2026-10-04: universe 160→240 killed it twice at 1197 s; `upcoming` moved out to its own lane; per-step `NBT_STEP_TIMEOUT_MIN` |
| 15 | **Mirror** (primary→Supabase standby, natural-key, additive-only) | `cron-mirror.yml` `40 23 * * *`, 150-min budget | never deletes; refuses copying a database onto itself; URLs via env not CLI |
| 16 | **Backup** (`COPY … TO STDOUT`, `REPEATABLE READ, READ ONLY`) | `cron-backup.yml` `40 4 * * *`, 7-day artifacts | excluded from watchdog restart by design; restore rehearsal is **5 migrations behind** (B1) |
| 17 | **Watchdog** (restart stale lane, escalate red after 2 failures/3 h) | `cron-watchdog.yml` `45 * * * *` + after every data-lane `workflow_run` | 6 lanes only; `cancelled`/`timed_out` count as failure (GitHub reports timeouts as "cancelled"); recovery is checked, not assumed |
| 18 | **Breaker** (circuit breaker per source, derived from ChunkRun) | on demand | `OPEN_AFTER=3`, cooldown 60→720 min ("every source probed at least twice a day however long it has been down") |
| 19 | **`tools/daily_audit.py`** (composes health constants, Coverage, freeze digests, brain manifests) | **NOT SCHEDULED** — B4 | one DB connection by design; `unknown` never counts as pass; the audit workflow that exists runs `jobs/audit.py` (the Coverage writer), not this |

## Cross-cutting findings, and what they mean

1. **`daily_audit.py` is still unscheduled.** `cron-audit.yml` runs `run.py audit`
   (`jobs/audit.py` — the lane that *writes* Coverage rows). The read-side operational audit
   that composes everything has no workflow. This is B4 and remains open; scheduling it is a
   one-workflow change but "a scheduler-ready script is not a schedule" — it must be added
   **and its first output verified**.
2. **The calendar lane (row 9) has no Coverage row, and it must not get one the obvious way.**
   Every other network lane is judged by `jobs/audit.py`'s WATCHED table; `Event` writes are
   only visible through ChunkRun. Investigated 2026-10-17 before any row was added, and the
   obvious fix is wrong. `coverage()` computes each gap as `max(0, now - newest)`
   (`jobs/audit.py:296`), and `jobs/upcoming.py` stores only forward-dated rows (`day < today`
   is skipped), so a `("Event", "date")` WATCHED entry would see a newest row up to 120 days
   in the future, clamp the gap to zero, and report **healthy forever** - a false all-clear,
   worse than the silence it would close. The model's one ingestion timestamp was checked
   live before being considered instead: `createdAt` on the 542 calendar-source rows advances
   on most days (364, 129, 0, 13, 19, 6, 11 new rows over three weeks; newest inserted
   2026-10-17 08:04) but tracks **first-discovery only** - the upsert (`ON CONFLICT (slug)
   DO UPDATE`) never touches it, so a provider publishing no *new* dates for a week would
   read stale while the lane is perfectly healthy and re-confirming everything it holds.
   Discovery cadence is not lane cadence, and the WATCHED table's own discipline (every
   entry production-verified before being kept) rejects it. The honest signal for "did the
   lane run" is `ChunkRun`, which `lane_run` already writes (`job="cron calendar"`) and
   Screen 8's lanes panel already displays. Follow-up, owner-scoped rather than done here:
   either raise a ChunkRun-based lane problem in `lib/health.ts` and add
   `cron-calendar.yml` to the watchdog's `LANES` (today's exclusion is a documented scope
   choice, not an oversight), or wait for B4 to schedule `daily_audit.py`, whose
   `jobRuns36h` check already flags a dead calendar lane from ChunkRun. Neither path is a
   Coverage-table change.
3. **Freshness is never inferred from retrieval time** anywhere in the pipeline: prices carry
   the session date, quotes carry `quotedAt`, news carries provider `publishedAt` separate
   from `createdAt`, events carry their own dates. The UI contract (Screens 3/5/8) depends on
   this and the readers preserve it.
4. **Polling is the right shape everywhere it is used.** No source offers a stream that a
   free-tier runner could hold. The efficiency work that matters is the one already done:
   chunking, per-symbol staleness ordering ("poll the stalest quotes, not the slice of the
   alphabet the clock points at"), fetch caches, and budgets with declared ceilings.
5. **Storage growth is capped by `jobs/retention.py`** on the working-set tables; the
   permanent record (`DecisionLog`, `PriceSnapshot`, …) is never pruned. 493/500 MB was the
   last reported figure; reclaiming ~57 MB via `VACUUM FULL "EventImpact"` needs owner
   authorisation and is **not** run here.
6. **Watchdog coverage gaps** (by design, documented): products, calendar, geo, backup and
   mirror lanes cannot be auto-restarted by the watchdog — only escalated. That is a
   deliberate scope choice recorded in `tools/watchdog.py`'s LANES, not an oversight, but it
   means those lanes rely on their own retry logic and the daily audit (once scheduled).

## What this matrix does not claim

* Measured successful-update timestamps and the eight stale sources' current status (B3)
  need live `Coverage`/`ChunkRun` reads; not done here to protect the pooler.
* Backup/restore rehearsal currency (B1) not verified.
* No claim that any lane is currently healthy — this is the contract of the system as
  written, not a health report.
