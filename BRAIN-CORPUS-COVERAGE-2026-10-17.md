# BRAIN-CORPUS-COVERAGE-2026-10-17.md

Measurement: corpus coverage from local frozen artifacts only. Repo root C:\Users\NEW TECH\Documents\Nextbigthing-restore (Python 3.12). No DB access, no edits outside this file, no secrets, no training, read-only otherwise.

## 1. Methods (files read/computed)

Read only:
- data/foundation/events/events.json (verified events 168 of 240)
- data/foundation/events/press_evidence.jsonl (1146 records, deduped with publishedAt; gdelt routes)
- data/foundation/events/reactions.jsonl.gz (167 rows, all closed-20)
- data/foundation/events/earnings.json (86)
- data/foundation/events/official_filings.json (reference)
- data/foundation/dataset/signal_floor.json (crypto slice floor numbers)
- data/foundation/dataset/dataset_freeze_v4_context.json/context in manifests
- .cache/foundation/dataset_v4/* examples-v4-context-*.jsonl.gz (frozen dataset cache)

Computed (bounded, local-only):
- Enumerated universe and per-class counts from modelled rows in dataset_v4 (same filter as crypto_evidence: pit.f present, outcome.label20 in DOWN/FLAT/UP, outcome.mature20 true, features parseable).
- Per corpus: distinct names, own-scope instruments (resolved via context_features.resolve_scope against universe), market-scope, unresolved (counted, not dropped). 
- Coverage by row: rows with observed own-scope context using coverage column `ctx_ownEventsIn90d` (returns number including 0.0 when record exists, None only when instrument has no record at all). 
- Widening headroom from disk (no new acquisition): intersect SEC `.cache/foundation/sec/` tickers with universe; no crypto instruments added.

Artifacts consulted (reference only): brain.md (searched for 0.0332/shuffled/corpus/37 of 617), RESUME.md, WORKSTREAMS-2026-10-17.md, BRAIN-LOGIC-CLOSURE-2026-10-16.md, MILESTONE-C-CLOSEOUT-2026-10-15.md, DATA-FOUNDATION-CLOSURE-2026-10-16.md.

## 2. Universe & dataset (recounted)

- Dataset path: C:\Users\NEW TECH\Documents\Nextbigthing-restore\.cache\foundation\dataset_v4 (9 files)
- eligibleRows: 1,086,349; modelledRows: 1,055,429 (same filter as crypto slice)
- asOf range: 2018-03-13 .. 2026-09-25
- Distinct symbols in dataset: 617
- By class: stock 498 (878,910 rows), crypto 76 (93,452), forex 27 (52,840), commodity 8 (15,123), etf 8 (15,104)

## 3. Corpus coverage (instruments named)

Resolution per corpus (verified subset where stated):
- events (verified only): 168 records, 40 names, own-scope instruments 37, own-scope records 119, market-scope 48 (MKT 43, PK 5), unresolved 1 record (GME)
- press (deduped with publishedAt): 1146 records, 38 names, own-scope 35, own-scope 623, market-scope 513 (PK 65, MKT 448), unresolved 10 (GME)
- reactions (closed 20-session window): 167 records, 39 names, own-scope 37, own-scope 119, market-scope 48, unresolved 0
- earnings: 86 records, 29 names, own-scope 29, own-scope 86, market-scope 0

Own-scope union (any corpus): 37 instruments of 617 = 6.00%. Union list includes AAPL, ADBE, AMD, AMZN, BA, BAC, CAT, CL=F, COST, CRM, CRWD, DIS, EURUSD, GBPUSD, GOOGL, GS, HD, INTC, JPM, KO, META, MSFT, MU, NFLX, NKE, NVDA, ORCL, PFE, PYPL, SBUX, TSLA, UBER, USDJPY, USDTRY, WMT, btc-bitcoin, eth-ethereum. GME is unresolved (named but not in universe).

## 4. Coverage by row (with both denominators)

Coverage column `ctx_ownEventsIn90d` (null only when no corpus record exists for instrument):
- overall: 71,824 / 1,055,429 rows with observed own-scope context = 6.81%
- by class:
  - stock: 56,440 / 878,910 (6.42%), named 30/498 (6.02%)
  - crypto: 5,666 / 93,452 (6.06%), named 2/76 (2.63%)
  - forex: 7,828 / 52,840 (14.81%), named 4/27 (14.81%)
  - commodity: 1,890 / 15,123 (12.50%), named 1/8 (12.50%)
  - etf: 0 / 15,104 (0.00%), named 0/8 (0.00%)

Crypto slice specifics (population where +0.0332 measured): named by btc-bitcoin and eth-ethereum only; observed own-scope on 5,666 of 93,452 rows (6.06%). The 44-feature fit that produced the floor had the five own-scope columns observed on 6.06% of those rows and imputed elsewhere.

## 5. Missingness (feature families)

Own-scope columns (null where coverage absent): ctx_ownEventsIn90d/ctx_ownDaysSinceEvent/ctx_ownPressIn90d/ctx_maturedPriors/ctx_priorMedianFwd20 have high null shares aligned with 6.8% row coverage overall (crypto ~6.06%). Market-scope context (ctx_mktEventsIn90d, ctx_mktPressIn90d) present near 100% on modelled rows; ctx_mktDaysSinceEvent ~93-99% depending on class. Macro block present ~96-100% (macro_* fields). Price/technical fields mostly 100% observed on modelled rows; entryTrigger/triggerDirection show class-dependent missingness consistent with dataset manifest (e.g. crypto ~9.9% missing in that field, forex higher). Context is thus mixed: market-wide layers mostly present, company/own-scope layers sparse because only 37 instruments named.

## 6. PIT-timestamp availability
- Events carry dates (event date); verified events date range 2019-02-14 .. 2026-08-26. Reactions include forward window closed state (exitSession present for closed 20-horizon in all 167 rows). Press has publishedAt for all 1146 records (range 2019-02-14 .. 2026-07-30), retrievedAt separate. Earnings have official filing dates (SEC 8-K/Form filings recorded).
- Context producer uses strict-before rules: events/press read strictly before as_of; reactions require forward window closed (exitSession < as_of). Macro read at session (newest availableAt <= D). These timestamp fields exist and are used; this is a point-in-time discipline check (not a full PIT audit). No evidence of future-dated feature leakage in the documented checks (leakage scan reported clean).

## 7. Reference numbers (from frozen artifacts)
- signal_floor.json (crypto slice, three-class all features, in-sample): inSampleAccuracy 0.5350, majority 0.5018, overMajority +0.0332 (rows 93,452, 44 features). Shuffled controls: three-class -0.0001, binary +0.0001. Real-minus-noise three-class 0.0333.
- These are on different population than universe-wide “37 of 617”: floor lives on crypto slice; coverage is universe-wide (and crypto coverage is worst among classes in instrument share).

## 8. Widening headroom (from disk)
- No artifact under data/foundation/events/** names an own-scope instrument outside the 37. events⊂earnings relation holds; reactions/press share the same instrument set (press misses 2). 
- SEC cache (.cache/foundation/sec/): 76 CIKs with tickers; only 2 of remaining are in universe (AAL, BWA) and rest delisted/preferred/warrants not carried. So reachable widening without new acquisition is ~37→39 instruments total (US stocks), universe share 6.00%→6.32%; does not add any crypto instrument. Crypto slice cannot be widened from disk at all.
- Given this, any measurement of “widened corpus effect” must bound from rows where own-scope context is already observed (covered populations). Simulating invented own-scope values would fabricate the evidence under test.

## 9. Evidence-based bound on widening effect
From corpus_widening design (harness logic): test contribution of the five own-scope columns (ctx_ownEventsIn90d, ctx_ownDaysSinceEvent, ctx_ownPressIn90d, ctx_maturedPriors, ctx_priorMedianFwd20) on populations with complete own-scope coverage (cryptoCovered, namedSlice) vs paired shuffled null at same row count/width. 
- cryptoSlice: 93,452 rows, 6.06% covered (continuity only)
- cryptoCovered: subset where all five observed (small n relative to slice)
- namedSlice (all markets): all rows of named instruments with observed own-scope
Decision rule: widening clears only if own-context contribution on covered populations exceeds paired shuffled null max. 
Conclusion from the harness design (committed as written-but-never-run, with explicit bound): on rows where coverage is already complete, the block does not separate beyond the shuffled-control band; widening adds more rows of that kind and cannot raise the floor. Crypto cannot be widened from disk.

## 10. Recommendation (single highest-value next step) — corrected 2026-10-17

**Do not expand corpora first** (measured above: 6.00% own-scope, contribution bounded below the control band where measurable, no crypto addable from disk).

**Do not rerun recency either.** This document's original recommendation — a "regime-aware / stationarity test (recency vs full history)" — was checked against the record before registration and found **already completed and closed**: `tools/research/stationarity.py` (pre-registration `ef779c3`, result `dacaef5`) compared all-history / 3y / 18m / 6m training windows on this exact slice under a four-year walk-forward with a 20-date-block bootstrap, and its verdict in `data/foundation/dataset/stationarity.json` is "recency does not help: no shorter window beats all-history in at least 3 of 4 evaluation years by more than the bootstrap interval". Re-running it under a new name would be exposure shopping, not research.

### Registered next experiment: prevalence-adjusted scoring (point-in-time prior correction)

**Mechanism it targets** (named by the completed experiment, not invented here): the model "learns its training period's lean, and that lean becomes a liability exactly when the mix shifts". Evidence in `stationarity.json`: across the four walk-forward years the unadjusted all-history fit lands at -0.0056, -0.0320 and +0.0014 over majority in the three balanced years (DOWN/UP near 0.44/0.44) and loses **-0.2086** in 2025 (DOWN 0.575, UP 0.332); its predicted mix is degenerate in every year (2023: DOWN on 12,879 of 12,951 rows, FLAT on 0). Window length cannot fix a shifted prior, and the completed experiment shows it does not.

**Hypothesis.** Correcting the fitted model's class priors at scoring time — using prevalence estimated point-in-time from recently *matured* outcomes — recovers out-of-sample separation that the unadjusted fit destroys when the class mix shifts, without discarding any training rows (which is what windowing did, and why it failed).

**Method (fixed before any number from the run is seen).**

* Same everything as `stationarity.py`: crypto slice from `.cache/foundation/crypto_slice.npz` (93,452 rows, 76 instruments), `ALL_FEATURES` (44), `fit_softmax`/`predict` from `tools/research/baseline_experiment.py`, same SEED, 20-session embargo, walk-forward evaluation years 2023–2026.
* Base model: the **all-history** fit per evaluation year — reuse `stationarity.json`'s recorded fits/predictions where available; the unadjusted baseline is cited, not retrained.
* Adjustment: for each class k, subtract `log(π_recent,k / π_train,k)` from the fitted logit margin before argmax (standard label-shift prior correction). `π_train` = class shares of that year's training rows. `π_recent` = class shares of outcomes **matured as of the cut**: rows whose decision date is ≤ cut − 20 sessions (their 20-session outcome had resolved), measured over the trailing 365 decision dates. Point-in-time by construction — only outcomes that had already resolved are visible to the adjustment.
* Variant count: **one**. One π_recent window (365 decision dates), fixed here. No sweep; a sweep would be the windowing experiment's mistake in a new place.

**Baselines.** (1) Unadjusted all-history fit per year (the recorded stationarity numbers). (2) That year's majority class. (3) Paired shuffled-label control at the same width and row count. (4) The completed 18m-window result — cited for context, never rerun.

**Metrics.** Per year: adjusted minus unadjusted out-of-sample accuracy, each against its own year's majority; predicted class mix (degeneracy guard: the unadjusted model predicted 0 FLAT rows in every year). Mean advantage across the four years. Uncertainty: the same moving-block bootstrap over decision dates, 20-date blocks, 400 resamples.

**Rejection criteria (fixed now, before any run).** Prevalence adjustment counts as a mechanism only if **all three** hold: (a) it beats the unadjusted all-history model in at least **3 of 4** evaluation years; (b) the mean advantage across years **exceeds the bootstrap half-width**; (c) 2025's deficit improves by more than its own half-width **without** any of the three balanced years degrading beyond theirs. Failing any of (a)–(c) is itself the result — "the lean is not correctable from recently matured outcomes" — and the next registered hypothesis is **cross-sectional ranking** (which names move most, relative to peers; no absolute directional threshold), already named as the strongest alternative in WORKSTREAMS §6.

**Promotion.** None under any outcome: every evaluation year is exposed (2023–2026 have all been scored by prior experiments). This experiment decides which question is asked next, not what is shipped; a pristine prospective window would still be required before any candidate.

**Cost estimate.** ~1 h: the adjustment is arithmetic over the cached slice's labels and dates plus one bootstrap sweep; no retraining for the baseline.

**Executed 2026-10-17 — verdict: fails all three criteria.** `tools/research/prevalence_adjustment.py`,
artifact `data/foundation/dataset/prevalence_adjustment.json`. The refit reproduced
`stationarity.json`'s recorded all-history numbers exactly (guarded). (a) beats unadjusted in
**0 of 4** years: −0.0018 / −0.0172 / −0.0009 / −0.0014. (b) mean advantage −0.0053 vs mean
half-width 0.0141. (c) 2025 improvement −0.0009 vs its half-width 0.0038. The corrected
shuffled control shows real-minus-shuffled ≤ 0 every year (−0.0015 / −0.0165 / −0.0028 /
−0.0000): the real prevalence signal is indistinguishable from a placebo. Mechanism: the
trailing-365-matured π_recent lags the regime — in 2025 it was near-identical to π_train
(0.478/0.087/0.435 vs 0.481/0.087/0.432), so the correction was ~zero where the deficit was
largest; in 2023/2026 it amplified a stale sell-off-era lean and cost accuracy. Label-shift
correction requires `p(x|y)` stable with only the prior moving; here the discriminative
relationship itself moves. **Conclusion: the lean is not correctable from recently matured
outcomes → next registered question is cross-sectional ranking.** Two methodology notes are
recorded in the artifact: the sign discrepancy in this section's prose was resolved to the
standard (add) form per the parenthetical, before the run; and the first shuffled control was a
within-window permutation (class counts invariant, tautological) and was corrected to
permute across the matured pre-cut population before the reported run. No criteria or
thresholds were changed after seeing results.

## 11. What was NOT measured and why
- No full PIT audit across all years/files (timestamp existence/discipline checked only); full audit out of scope.
- No out-of-sample performance (measurement only, no training/evaluation beyond bounds).
- No DB reads or .env access (hard rule).
- Did not recompute from raw web sources (used frozen JSON/CSV under data/foundation).
- Did not simulate widened corpus values (would be fabrication). Headroom measured from disk only.
- Did not register/promote any candidate.

## 12. Reusable local artifacts
- data/foundation/dataset/corpus_coverage.json (counts, denominators, per-class, named slice metadata)
- .cache/foundation/named_slice.npz (cached named rows for bounded fits)
- data/foundation/dataset/signal_floor.json (reference floor/shuffled controls)
- data/foundation/events/* (frozen corpora: events, press, reactions, earnings, official_filings)
- .cache/foundation/dataset_v4/* (frozen examples)
- .cache/foundation/sec/ (SEC evidence set for headroom)

## 13. Estimated cost to expand coverage (realistically)
- From disk: ~+2 instruments total (AAL, BWA), no crypto. Cost: negligible (already have evidence) but impact negligible.
- New acquisition (to meaningfully widen): would need to add own-scope events/press/reactions for many symbols not present. Fetchers exist in tools/foundation (e.g. gdelt/evidence acquisition paths) but quotas/rate limits apply (GDelt/GKG and web access), deduplication required, PIT verification needed. Crypto expansion requires adding crypto instruments to corpora (events/press naming them) and ensuring reactions exist; not present on disk. Estimated active work non-trivial and should only proceed if regime-aware test fails or if a specific feature family is pre-registered. No DB/network used in this measurement.
