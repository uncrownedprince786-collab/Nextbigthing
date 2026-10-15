# Resume here

## 0. BRAIN SPEC V1.1 FINALISED — THREE DECISIONS FROZEN, 2026-10-15

**Specification only. No code, dataset, experiment or deployment was changed.**
`BRAIN-SPEC-V1.md` updated in place; reasoning in `brain.md` rule 155.

### The three frozen decisions

**D4 — horizons.** Swing (~20 sessions) is claimable on `label20`. **Position is NOT**, because
`examples-v3` carries only `label20` plus raw `fwd1`/`fwd5`/`fwd20` — there is no 60-session
label anywhere in the training data. Position becomes data requirement **DR-1**: build `label60`
and evaluate it independently first. Scalp and intraday stay out of scope (intraday history is a
7-day rolling window). A long-term bias never makes a current entry actionable.

**D7 — PSX shorts.** A bearish conclusion publishes when the evidence supports it; missing
borrow, short-ineligibility or suspension downgrades `executionReadiness` to `unverified` or
`blocked` and **leaves the `SHORT` standing**. The execution gate may withhold, never reverse.

**D2 — thresholds.** `MIN_FAMILIES = 3` (how much of the file is readable) and `MIN_NET = 2`
(how decisive it is). Fixed, documented, **not to be tuned against results**.

### The formula, now exact

Six evidence families, one vote each (`-1`/`0`/`+1`), equal weight 1.
`NET = Σ v_i`, an integer in `[-6, +6]`. Conflict is handled by subtraction only.
A family is *eligible* when its inputs are present, fresh, un-vetoed and not self-contradictory.
**Eligible-but-inconclusive** (counts toward `MIN_FAMILIES`, `evidence` fact) is distinct from
**ineligible** (does not count, `file` fact). Four worked examples are in the spec.

Vetoes act at two stages and **never create or reverse a direction**.

### Corrections made to V1

`MIN_NET`/`MIN_FAMILIES` had no arithmetic definition; family scores had no formulas; the
position horizon was implied as supported. All three fixed. One V1 claim was too generous and is
corrected: the existing `Decision` contract is `{action, why, entry, invalidation, timeSense,
confidence, missing, notes, measured, gate, basis, plan, legs, intent, developing}` —
`snapshotId`, `horizon`, `regime` and `executionReadiness` are additions, not existing fields.

### Still owner-dependent

**D9** — approve building `label60` for the position horizon (scope/cost).
**D10** — the deadband τ and family thresholds (risk appetite).

**Awaiting your review and approval. Training remains NOT started.**

---

## 0. BRAIN LOGIC SPECIFICATION V1 DELIVERED, 2026-10-15

**Specification only. No code written, no training run, no evaluation executed.**
The spec is `BRAIN-SPEC-V1.md`; the reasoning behind it is `brain.md` rule 154.

**Architecture call:** ten *roles* in one ordered pipeline of pure functions, not ten agents.
Most responsibilities are deterministic rules because a rule can be read and shown to be wrong.
Three learned components are named as candidates and all three are deferred past V1.

**Aggregation:** six evidence families, one vote each, fixed published weights.
`r5`/`r20`/`sma20`/`sma50` are one family — that is the mechanism against correlated
double-counting. R1 (integrity) and R9 (risk) hold vetoes; they can force `WAIT` but never force
a direction.

**What already exists** and the spec builds on: `LONG | SHORT | WAIT` with `WaitBasis`
(`file` = no measurement vs `evidence` = measured and unconvincing), `DecisionLog` storing the
deciding gate and reward-to-risk as measured at the time, the OHLC and session integrity rules,
the 20-session embargo and the maturity concept.

**What is proposed and unbuilt:** evidence-family aggregation, the adversarial role, macro and
event wiring, and the learning lifecycle.

**Three requirements are untestable as written and labelled so:** "world-class" is a direction of
travel; behavioural science is proxy-only; and realistic trade outcomes cannot be tested at all
— no cost, spread or borrow data exists, so V1 forbids `executionReadiness = executable`.

**Owner decisions needed:** which horizons the product promises (D4), whether PSX short research
publishes without borrow data (D7), and the risk appetite setting the minimum-evidence thresholds
(D2). The other five open decisions are defaulted in the spec with reasons.

**Next phase awaits your review and approval.** Training remains NOT started.

---

## 0. ORGANISATION GATE MET — 100%, 2026-10-15

**Phase: DATA ORGANISATION ONLY.** No training, baseline or evaluation was run or changed; the
experiment artifacts and `acceptance_scope.json` are untouched.

| Metric | Before | After |
|---|---|---|
| **Organisation & validation** | 0.8333 (15/18) | **1.0000 (18/18)** |
| Data coverage | 0.9674 | 0.9674 (unchanged) |
| Training readiness | 0.9716 | 0.9716 (unchanged) |
| Context-layer integration | 0.2222 | 0.2222 (unchanged) |
| Weighted overall | 0.9274 | 0.9274 (unchanged) |

**The implementation had never matched the frozen rule.** The scope names six attributes; the
scorer checked a proxy (source + status + artifact). Fixing it to the frozen definition is a
correction, not a reweighting — so the superseded proxy count is still printed beside the new one.

**What was actually produced:** `gap_evidence.json` — 8 dated probes proving each blocked gap.
Yahoo chart 404 for HOLX/CTRA, stooq bot challenge, PSX **404 at 2008-08-27 and 2013-11-01, 200 at
2013-11-04** (archive floor established), ICE series starting 2023-10-16 against the recovered
Moody's `BAA10Y` from 2005-01-03. Plus the six attributes documented per layer, each pointing at a
file that resolves.

**The path check earned its keep on first run:** "all six present" scored 18/18, but resolving the
referenced paths dropped it to **13/18** — five layers named real files with a wrong-root path.
Corrected to 18/18.

**A blocked gap is organised, never covered.** Coverage did not move and cannot be moved by
documentation. Tests assert a blocked layer is organised but never counted as downloaded or joined.

**Verification:** 1,053 Python tests pass (9 new); `verify_durable.py` problems none; backups
verify at 197/197, 19/19 and 45/45 checksums.

**Next phase requires owner authorisation.** Training remains NOT started.

---

## 0. FOUNDATION CLOSED 92.74% · FIRST EXPERIMENT RUN · NO EDGE, 2026-10-15

Read `brain.md` rule 152. Scope was frozen **before** measurement in
`data/foundation/dataset/acceptance_scope.json`.

### Score: 0.9274 weighted — PASSES the 0.90 gate

| Domain | num / den | score | weight |
|---|---|---|---|
| prices | 1,097,903 / 1,134,858 | 0.9674 | 0.22 |
| corporate actions & lifecycle | 127 / 190 | **0.6684** | 0.10 |
| macro & rates | 63 / 63 | 1.0000 | 0.12 |
| historical crises & regimes | 12 / 12 | 1.0000 | 0.12 |
| news, events & original reports | 495 / 503 | 0.9841 | 0.14 |
| research principles & case studies | 168 / 240 | 0.7000 | 0.10 |
| provenance & licensing | 18 / 18 | 1.0000 | 0.10 |
| backup & recovery | 3 / 3 | 1.0000 | 0.10 |

Blocked items stayed in the denominator — the 63 unrecoverable delisted price histories are why
corporate-actions scores 0.6684.

**Headline metrics:** coverage **0.9674**, organisation **0.8333** (15/18 — below 90% on its own),
training readiness **0.9716**, and `contextLayerIntegration` **0.2222** (4/18), which is printed
beside readiness and never instead of it.

**One recovery:** the 2008 credit spread was wrongly recorded as licence-blocked. The ICE *index*
is blocked; Moody's `BAA10Y` is free for the whole window and peaks at **6.16%**. Four series
added. TEDRATE is now labelled bank-funding/liquidity, **not** a credit spread.

### First experiment — NO DEMONSTRATED EDGE

| | Mean accuracy |
|---|---|
| Rule baseline (trend agreement) | 0.3423 |
| **Candidate (multinomial logistic, numpy)** | **0.4211** |
| **Always predict the majority class** | **0.4204** |

The model beats the rule by 7.9 points and beats a constant predictor by **0.07 of a point**.
Per-class recall UP 0.74 / DOWN 0.24 / FLAT 0.10 — it collapsed toward the majority class, and its
worst fold is **2022**, the one year DOWN was the largest class. A model that fails in the adverse
regime has failed at the thing it was for.

6 chronological folds, 20-session embargo, per-market and per-regime reported. **Direction only —
the execution-cost layer is empty, so nothing here is net of anything.**

### The single next step

Go after the **unjoined context layers** (macro is PIT-correct and joinable on date; events and
reactions exist) rather than tuning a linear model until it looks better. `examples-v3` stays
immutable as the reference version.

---

## 0. HISTORICAL CORPUS CLOSED — READY WITH DOCUMENTED LIMITATIONS, 2026-10-15

**Training still NOT started.** Read `brain.md` rule 151. Artifacts:
`data/foundation/dataset/source_inventory.json`, `historical_regimes.json`,
`data/foundation/crisis_2008/`.

### The one table that matters: 18 data layers, 4 joined into training

| Joined into `examples-v3` (4) | Validated but **not** a feature (12) | Blocked (2) |
|---|---|---|
| instrument prices/OHLCV | benchmarks 1927+, macro (PIT), rates 1954+, 2008 package, lifecycle, events, press, reactions, principles, regimes, operational news, credit spreads* | delisted US prices, PSX pre-2013 |

11 COMPLETE · 4 PARTIAL · 2 SOURCE_BLOCKED · 1 LICENSE_BLOCKED. *credit spreads are the
licence-blocked one.

### Deep history was already on disk

`^GSPC` to 1927, `DFF` 1954, `DGS10` 1962, `DX-Y.NYB` 1971, `DCOILWTICO` 1986, `^VIX` 1990.
Measured drawdowns match the record: **1929 −86.19%**, 1973-74 −48.20%, 1987 −33.51%, dot-com
−49.15%, **2008 −56.78%**, COVID −33.92%, 2022 −25.43%. Only the last four are inside the
training window.

### 2008 package — complete as research, empty as training

18/18 FRED series (2005–2012), **481 FDIC failure/assistance records**, 13-entry chronology where
every date is labelled announcement / effective / filing / market observation / retrospective.
Validates: unemployment peak **10.00%** (2009-10), TED spread **4.58** (2008-10-10), Case-Shiller
**−27.4%**, WaMu $307bn on 2008-09-25. **None of it can be a feature** — `examples-v3` starts 2018.

### PSX has no 2008, proved

Real GETs: **2008-08-27 → 404**, **2013-11-01 → 404**, **2013-11-04 → 430 symbols**. The archive
begins 2013-11-04; the public KSE-100 endpoint starts 2021-10-15. Pakistani 2008 evidence is
documentable as events, unavailable as prices.

### Verdict: READY WITH DOCUMENTED LIMITATIONS

The first task — 20-session direction classification, chronological, 20-session embargo — is fully
supported. Limitations that do **not** touch it: no pre-2018 instrument history, no delisted US
prices, no PSX before 2013, no 2008 credit spread, no execution costs.

---

## 0. REGIME VERIFICATION — PASS WITH LIMITATIONS, 2026-10-15

**Training still NOT started.** Artifact `data/foundation/dataset/regime_coverage.json`
(sha256 `0b7817dc3f6f12db`), reproducible with `tools/foundation/regime_coverage.py`.
Detail in `brain.md` rule 150.

### Year-wise coverage, within each asset's own listed range

| Market | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| US | — | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| PSX | 0.8782 | 0.8476 | 0.8933 | 0.9137 | 0.8800 | 0.8748 | 0.9446 | **0.9913** | **0.9985** |
| crypto | 0.9862 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| forex | — | 0.9963 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| commodity | — | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9980 | 1.0000 | 0.9995 | 1.0000 |

US begins 2019 and PSX 2018 because that is when their instruments list; a listing date is never
counted as missing. PSX's early shortfall is securities that did not trade, already classified.

### Major regimes present, and their representation in `examples-v3`

| Market | Episode | Drawdown / gain | Examples | **Effective windows** |
|---|---|---|---|---|
| US | COVID crash 2020-02-19 → 03-23 | −33.92% | 33,410 | 1,670 |
| US | 2022 bear → 2024-01-19 | −25.43% | 142,941 | 7,147 |
| US | bull 2022-10 → 2026-10 | +118.59% | 274,444 | 13,722 |
| US | bull 2020-03 → 2022-01 | +114.38% | 121,451 | 6,073 |
| PSX | bear 2018-04 → 2019-08 | −55.00% | 108,581 | 5,429 |
| PSX | bear 2021-08 → 2023-06 | −41.90% | 121,294 | 6,065 |
| PSX | bull 2023-06 → 2026-01 | +316.05% | 127,434 | 6,372 |
| crypto | bear 2021-11 → 2022-11 | −76.67% | — | 9,734 (all classes) |
| crypto | bull 2018-12 → 2021-01 | +1177.57% | 7,087 | 354 |
| commodity | bear 2020-08 → 2022-11 | −21.19% | 6,700 | 335 |

Thresholds of 10/15/20/30% are all reported; 20% is the headline.

### Two bounded limitations

- **Forex has no crash regime** — zero episodes at 20% or deeper, at any threshold. That is a
  property of currency indices, not a data gap, but a crash regime cannot be learned from FX here.
- **Crypto's two short 2021 crashes are 24 and 14 effective windows**, and its 2018 bear had only
  five to ten listed instruments with 28% of examples quality-flagged. Too few independent windows
  for a crypto-specific regime claim.

Every drawdown window is overlapped by dated events with press evidence (the 2022 US bear: 50
events, 42 with press). That is corroborating context, not causation.

---

## 0. DATA FOUNDATION CLOSED — PASS WITH LIMITATIONS, 2026-10-15

**Training has NOT started.** Read this, then `brain.md` rules 148–149. The machine-readable
package is `data/foundation/dataset/readiness.json`.

| | |
|---|---|
| Authoritative dataset | `examples-v3`, **1,085,544 rows**, 616 assets, 2018-01-01 → 2026-09-24 |
| Built from | `main` `a62b392`; PIT run **38733216507**, assemble run **38735767762** |
| Durable | `nbt-private/dataset/examples-v3-2026-10-15-run38735767762/` — 9/9 content digests verified |
| Research corpus | `nbt-private/research-corpus-2026-10-15/` (163 files, checksummed) |
| Tests | 1,031 Python + 466 web, 0 failures |

### The two numbers that matter most

**Effective sample size is ~54,277, not 1,085,544.** Zero duplicates and zero identical feature
vectors, but a 20-session label means consecutive rows share 19 of their 20 forward sessions. Any
confidence interval must use the effective figure, and **a chronological split needs a 20-session
embargo** or train and test are scored on the same future.

**The dataset contains 15 price/volume features and the outcomes — nothing else.** No macro
field, no event field, no news field. Verified by reading a row, not the documentation.

### What is in the dataset vs preserved beside it

| Layer | In `examples-v3`? |
|---|---|
| 15 price/volume features + `label20`/`fwd1`/`fwd5`/`fwd20`/`mfe`/`mae` | **yes** |
| Macro (2,844 sessions, 31 series, PIT-correct with publication age) | ships in the same bundle, **joinable on date, not joined** |
| Press corpus (1,146 refs, 627 publishers), event corpus (168), reactions (167) | **no** — preserved artifacts |

That separation is correct for a price-and-volume direction task. Integrating the event layer is a
later capability milestone, not a gap in this one.

### First task, and its label rule

20-session direction classification. `fwd20 = close[t+20]/close[t] − 1`; **UP ≥ +2.0%, DOWN ≤
−2.0%, else FLAT**. Sessions inside the final 20 of a series are excluded as immature, never
labelled FLAT. Labels: UP 458,828 / FLAT 213,594 / DOWN 413,122.

**The label hides one market:** the flat 2% band puts **68% of forex into FLAT** (equities 18%,
crypto 10%). FX direction classification is weakly supported by this label.

### Adverse coverage and diversity

DOWN share by year runs 32.6%–48.8%, highest in 2018 and 2022 — the bear periods are in the data.
616 instruments, top-5 are 1.33% of rows, median 1,936 rows each. Sample preview:
`data/foundation/dataset/sample_preview.jsonl`, 28 buckets, deliberately including deep adverse
excursions, UP-after-drawdown, inconclusive FLAT and every quality flag.

### Residual limitations, and exactly what each blocks

| Limitation | Blocks | Does not block |
|---|---|---|
| No execution-cost data (any market) | net-of-cost claims, PSX shorts | directional research |
| 62 delisted US names (4 routes tested) | unbiased absolute-return claims | relative/direction work |
| FX 68% FLAT under a 2% band | FX direction with this label | equity/crypto/commodity |
| 717 PSX quarantined bars | range/ATR/pivot on those rows | close-based features |
| Press: 148/168 with references | news-driven features | the first task |

### The single next milestone

**Build the documented rule-based baseline and evaluate it chronologically with a 20-session
embargo.** No learned model, and no performance claim without out-of-sample evidence.

---


## 0. State of play, 2026-10-15 — integrated on `main`, dataset rebuilt and validated

**Read this, then `brain.md` rule 145.**

| | |
|---|---|
| Canonical branch | **`main`** — now the repository default; `master` left at `767d26b` as a legacy reference |
| `origin/main` | `a62b392` (merge of PR #1); Milestones B `ba06cd1` and C `3ab7f18` both ancestors |
| Stage A | run **38733216507**, success, 1,066,708 point-in-time rows, 0 duplicates, 240/240 live-equivalence |
| Stage B | run **38735767762**, success, **1,085,544 examples**, consumed pit artifact `11972311495` |
| Durable copy | `nbt-private/dataset/examples-v3-2026-10-15-run38735767762/` (283 MB, `PROVENANCE.json`, `SHA256SUMS.txt`) |
| Verdicts | Integration **PASS** · Rebuild **PASS** · Validation **PASS** · Training readiness **PASS for one defined task** |

**The dataset carries the Milestone B safeguards, verified in the rows rather than assumed:**
`dataQuality.basisBreakInWindow` present on every row and true on **1,278**; manifest
`basisBreaksKnown: 5`; and `withoutFeaturesByReason` lists **171 "weekend bar of a non-crypto
asset"** — the 2022-10-01 Saturday, excluded by the pipeline with no special case written for it.
Leakage: `featureDatedAfterSession` **0**, `setupDatedAfterSession` **0**, future-named-field scan
clean over 18,000 rows. Duplicates **0**. Reproducibility: 2018 rebuilt byte-identical.
Content digests: **9 of 9 years match** the manifest (hashed over the JSON lines, which is how
`assemble.py` defines them — not over the gzip container).

**What the dataset does not contain:** any event or reaction field. `assemble.py` builds from
`PriceSnapshot`, the point-in-time features and the replayed setups. The Milestone C corpus is a
**parallel** labelled dataset on main (`data/foundation/events/reactions.jsonl.gz`, 167 rows with
zero measured leakage). Saying the event layer is "in the training set" would be false.

### Historical evidence: acquisition CLOSED, 2026-10-15

**0 events pending.** Every one of the 168 verified events has exactly one evidence disposition.

| Disposition | Events | Meaning |
|---|---|---|
| `PRESS_EVIDENCE_FOUND` | **148** | one or more dated, relevant press references recovered and linked |
| `SEARCHED_NO_MATCH` | 14 | the listed searches completed and returned nothing relevant |
| `SOURCE_LIMITED` | 4 | the archive file for that date is not held by the server |
| `OFFICIAL_SOURCE_ONLY` | 2 | primary-source evidence exists; no press reference recovered |
| `PENDING` | **0** | — |

**1,127 references from 616 distinct publishers**, median 8 independent publishers per covered
event. Artifact `data/foundation/events/press_evidence.jsonl`, 622,753 bytes,
sha256 `cada04b29fae7e60`. Durable copy with per-file checksums at
`nbt-private/research-corpus-2026-10-15/` (163 files, 1.4 MB, including the per-date caches).

**Route.** The DOC API answers `429 Please limit requests to one every 5 seconds` and keeps
answering it well past five seconds once tripped — measured, logged in
`.cache/foundation/gdelt_requests.log`. The bulk GKG archive has no quota: 158 named daily files,
31.6 MB each measured before fetching, streamed and deleted one at a time. Nothing was bypassed;
one door was shut and the other was open.

**Precision was fixed before shipping.** The first pass returned 1,647 references and looked
excellent until a spot check showed `MU earnings release` matching `/new-music-releases/` — only
78 of 400 earnings references named their own ticker. Whole-word matching, a required distinctive
term, and matching in the URL *path* rather than the host (`.mu` is Mauritius) took earnings
precision from **20% to 100%** (312/312). The corpus honestly shrank to 1,127.

**Retention cannot delete it.** `Event`/`EventLink`/`EventImpact`/`EventState` are in
`NEVER_PRUNED`; `retention.py` references no foundation artifact; tests assert both, plus that no
collector writes into `News` (pruned at 70 days).

### Acquisition register — multi-source recovery, 2026-10-15

Every remaining non-PSX price gap was taken to its own primary source. Status per the agreed
vocabulary: `COMPLETE`, `SOURCE-LIMITED`, `INCOMPLETE`, `BLOCKED`.

| Gap | Scope | Sources searched | Outcome | Status |
|---|---|---|---|---|
| Crypto 4 bars, `bch-bitcoin-cash` 2018-11-16..19 | 4 / 98,457 | Coinbase (the series' own venue) | Coinbase serves no candles either — trading halted across the Bitcoin Cash hard fork | **COMPLETE** — a closure, not a gap |
| Commodity 5 bars, 2023-11-23 & 2025-07-04 | 5 / 15,680 | CME calendar | US Thanksgiving and Independence Day | **COMPLETE** — closures |
| Forex 26 bars, mostly 2019-05-22 | 26 / 54,729 = 0.047% | Yahoo (gap), **ECB via Frankfurter** (has the date) | ECB differs from the stored close by median **0.178%**, p90 0.477%, max 2.09% — a 16:00 CET reference vs a daily close, breaching the project's 0.5% splice bar at the tail | **SOURCE-LIMITED** — recorded as disputed, not merged |
| US delisted price history | 63 / 127 removals | Yahoo download (404), **Yahoo v8 chart API (404, tested)**, stooq (bot challenge — not circumvented), EDGAR (no prices by design) | no permitted free source serves delisted OHLCV | **SOURCE-LIMITED** — three doors tried |
| US instrument identity & lifecycle | 127 removals + 280 assets | **SEC EDGAR** (official) | all 127 resolved: **65 still listed**, **62 absent from the live map**, 12 with a former name; 279/280 of our universe currently listed (`COPX` is an ETF, absent by design) | **COMPLETE** |
| Historical press evidence | 168 verified events | GDELT DOC API (rate-limited), **GDELT bulk GKG archive** (no quota) | 148 events with references, 1,127 records, 616 publishers; 0 pending | **COMPLETE** — see the disposition table above |
| PSX borrow / spread / execution cost | all PSX | no free source found | none | **BLOCKED** — restricts executable-short claims only |

**The survivorship finding that changes a number.** Treating "removed from the S&P 500" as
"delisted" would have overstated the failure population by half: **65 of 127 are still listed**
under the same ticker, removed for market-cap drift. The 62 genuinely absent agree closely with
the 63 whose bars the vendor cannot serve — two independent sources, same story. Prices for them
remain unrecoverable, so the bias figure stays a measured lower bound.

**New durable artifacts:** `data/foundation/survivorship/sec_lifecycle.json` (official identity
and lifecycle) and, once the throttled run completes,
`data/foundation/events/press_evidence.jsonl` + its manifest. Press evidence is deliberately **not**
written to `News`, which `jobs/retention.py` prunes at 70 days.

### Master completion register, measured 2026-10-15

Denominator for "within range" is each asset's own first-to-last stored session on its market's
calendar, which is the only denominator that does not punish a late listing.

| Market | Prices (within range) | Identity / lifecycle | News & evidence | Event links | Reactions | Costs | PIT | Dataset |
|---|---|---|---|---|---|---|---|---|
| **US** 280 assets | **PASS** 535,003/535,003 = 100.00%, 0 missing, all 280 complete | PASS WITH LIMITATIONS — 0 assets ended; survivorship a measured lower bound | BLOCKED — 37-day window | PASS 617 links | PASS | BLOCKED — no data | PASS 0 leakage | PASS |
| **PSX** 226 assets | **PASS WITH LIMITATIONS** 394,069/430,989 = 91.43%; all 36,920 absences classified | PASS WITH LIMITATIONS — 21 delisted/renamed recovered; 0 current assets ended | BLOCKED — no PKR archive ingested | PASS WITH LIMITATIONS — 5 proxy events | PASS | **BLOCKED** — no borrow/spread | PASS | PASS |
| **Crypto** 75 assets | **PASS** 98,453/98,457 = 100.00%, 4 missing, 74/75 complete | PASS — late listings are legitimate, 2018→2026 | BLOCKED — 37-day window | PASS WITH LIMITATIONS 7 links | PASS | BLOCKED — no venue fee data | PASS | PASS |
| **Forex** 27 pairs | **PASS** 54,703/54,729 = 99.95%, 26 missing | PASS — 27 pairs from 2019-01-01 | PASS WITH LIMITATIONS — 31 macro series with `availableAt` | PASS WITH LIMITATIONS 6 links | PASS | BLOCKED — no spread/rollover | PASS | PASS |
| **Commodity** 8 | **PASS** 15,675/15,680 = 99.97% | PASS | BLOCKED — 37-day window | PASS 14 links | PASS | BLOCKED | PASS | PASS |

Freshness: every market current to 2026-10-14/15, 616 of 616 assets inside their lane interval.
Intraday exists only as a rolling recent window (US 63,595 bars / 99 assets, crypto 35,835 / 14),
not history.

**Three things this register corrects.** Crypto is not at 45% — that was the full-calendar grid
punishing coins for not existing yet. PSX's 36,920 "missing" bars equal
`residual_classification.json` exactly: 36,762 sessions a security did not trade plus 158 on empty
archive dates. And the 37-day news window is `jobs/retention.py` pruning at **70 days**, not a
source limit — a GDELT query for April 2022 returned 8 dated relevant articles, free and
unauthenticated, though it rate-limits (429) and the retention floor would delete anything fetched.

**The 747 PSX bars are resolved as far as the source allows.** 40 of 40 sampled stored rows are
identical to the exchange's published file, and the file itself prints a close outside its own
range: an upstream source error, not a transformation defect here. The correct value is
unknowable, so the quarantine stands. Dependent calculations that must exclude them:
`horizons.true_range` (ATR), `horizons.pivots` (structural levels) — both already skip bars with
no range via `has_range()` — and any future range, gap or intraday-position feature. Closes are
unaffected and are used everywhere.

The Milestone B guard is working on live data: PSX withheld ranges **712 → 824**, incoherent
**747 → 717**, collapsed **1,912 → 1,831**, six withheld in the last 30 days.

**Replay inputs preserved.** All 45 sealed artifacts and checkpoints copied to
`nbt-private/replay-inputs-2026-10-15/` (200 MB, per-file checksums, `PROVENANCE.json`) before
their 2026-11-12/13 expiry.

### The defined first training task, and why it is eligible

**Task:** 20-session direction classification over the 616-asset universe, chronological
walk-forward, with abstention. Labels `UP` 458,828 / `FLAT` 213,594 / `DOWN` 413,122, every row
`mature20`, 2018-01-01 → 2026-09-24. Inputs are the `pit` block only; `outcome` is a separate key
and never an input.

**Eligible because** the leakage, duplicate, maturity and reproducibility gates all pass on
measured evidence, and the quality flags let a run exclude `unadjustedActionInWindow` (24,224),
`windowIsNotDaily` (3,009) and `basisBreakInWindow` (1,278) rows explicitly.

**Not eligible, and why:** any task needing historical news (37 days of coverage only), realistic
execution cost or shorting feasibility (no free PSX borrow or spread data), or survivorship-free
backtesting (measured as a lower bound, not removed). The 747 quarantined PSX bars stay
quarantined; their ranges feed nothing.

### The single next step

**Build the documented rule-based baseline and run chronological walk-forward evaluation on it
before any learned model.** Keep the baseline and any future model separate, and make no
predictive claim without out-of-sample evidence.

---

## 0. State of play, 2026-10-15 — Milestone C COMPLETE, training readiness BLOCKED

**Read this, then `brain.md` rules 142 and 143. Full evidence:
`MILESTONE-C-CLOSEOUT-2026-10-15.md`.**

| | |
|---|---|
| Branch | `milestone-c-research-corpus` at `3ab7f18`, cut from Milestone B `ba06cd1` (protected, do not reopen) |
| Database | 1,097,638 rows, **385 MB** of 500 MB; no price row added or changed |
| Tests | **1,019 Python** (21 new), **466 web**, 0 failures; `verify_durable.py` exit 0 |
| Data-foundation gate | **PASS**, two documented source limitations |
| Training readiness | **BLOCKED** — see "the one blocker" below |

**What this milestone did.** The verified event corpus — 168 events checked against Wikipedia,
Wikidata and a measured market move back in October — existed only as a file. The database held
eight. Loading it took historical events from **8 to 176**, asset links to **119**, and the span
from 2022–2025 to **2019–2026** across 12 categories. On top of it,
`data/foundation/events/reactions.jsonl.gz` holds **167 event-reaction rows** over 1/5/20/60
sessions with excess return, MFE/MAE, drawdown and duration.

**The leakage guarantee, measured not asserted.** Every row keeps `before` (bars strictly before
the event), `day0` (the event session's own move — evidence, never a feature) and `forward` (from
the session after day0 — the only outcome label) apart. Over all 167 rows: 0 before-states dated
on or after their event, 0 forward windows starting at or before it, 0 inverted windows. 20-day
continuation of the day-0 move is **44.9%** and median excess return **−0.197%** — a corpus with
wins, losses and inconclusive cases, which is the point.

**Also closed:** rule 130's open line. `events.py` built the PSX series with
`source ILIKE 'Pakistan%'`, skipping the 183,267 recovered Karachi bars; it now reads
`a.currency = 'PKR'`.

### Known limitations, bounded and documented

- **Historical news is absent.** `News` spans **37 days** (2026-09-08 → 2026-10-15). No free
  source carries a news archive at scale. The event corpus is the historical catalyst layer; no
  artifact presents news coverage as complete.
- **No execution-cost data.** No free source for PSX borrow or historical spreads, so no cost
  model is asserted and no backtest may assume free execution.
- **Survivorship is measured, not removed.** 63 of 127 S&P removals since 2019 have no free daily
  history left, so the bias figure is a lower bound.

### Pushed, and the rebuild is blocked on main (verified 2026-10-15)

`milestone-c-research-corpus` is pushed: `origin/milestone-c-research-corpus` == local at
`4374623`, 0 ahead / 0 behind, both milestone commits on the remote. `origin/main` and
`origin/master` are untouched at `767d26b`.

**The CI rebuild cannot be run from this branch, and not because CI is broken.** Read
`brain.md` rule 144. `data-pit-features.yml` and `data-assemble.yml` each (1) trigger only on
dispatch or a push to **main** touching `ops/*.json`, (2) hardcode `checkout ref: main` with no
input to override it, and (3) carry the **"Prove this run is executing main"** guard that fails
when `HEAD != origin/main` — a guard 16 workflows share and the handoff says not to delete. A
dispatch today would rebuild from `767d26b`, producing a dataset with no
`dataQuality.basisBreakInWindow` and no event layer **while exiting 0**.

Second, independent blocker: no `gh` and no token here. Measured: unauthenticated dispatch POST
returns **401**, artifact download **401**.

**Nothing has expired.** All 58 workflow artifacts are live, including the sealed replay inputs
and `nbt-dataset-38593680381` (233 MB, built 2026-10-14T16:03Z) — the current authoritative
dataset, which predates both milestones. Its inputs expire **2026-11-13**, which is the real
deadline.

### The one blocker, and the single next step

The training dataset has not been rebuilt since Milestones B and C. What exists locally is 22,868
examples in `.cache/foundation/assembled_test3/` — a gitignored probe run predating
`dataQuality.basisBreakInWindow` and the event layer. The authoritative build is
`data-pit-features.yml` → `data-assemble.yml` on a GitHub runner; the assembly needs the sealed
replay artifacts through an authenticated GitHub API this session does not have.

**Next step: get Milestone B and C onto `main` (a merge or fast-forward, the repository's own
sanctioned path), then dispatch `data-pit-features.yml` → `data-assemble.yml` in that order and
let the first finish before starting the second — they are separate concurrency groups and the
assembly reads the feature artifact the first one uploads.** Only then does the rebuild carry the
milestone changes. Nothing else is proposed.

---

## 0. State of play, 2026-10-15 — Milestone B is COMPLETE

**Read this, then `brain.md` rule 142. The acquisition section below it is still accurate about
what was acquired; this section supersedes its "what is next".**

Cleaning and point-in-time integrity closed against the four objectives of rule 141. The full
evidence is `MILESTONE-B-CLOSEOUT-2026-10-15.md`.

| | |
|---|---|
| Branch | `restore-db-utility` |
| Database | 1,097,638 rows, 384 MB of the 500 MB tier — **unchanged in row count** |
| Database writes | **216 rows**, one UPDATE, rollback at `data/foundation/price_verification/forex_volume_rollback.json` |
| Tests | 998 Python (27 new), 466 web, 0 failures |
| Durable artifacts | 17 of 17 checksums verify; `verify_durable.py` now exits clean |

**What changed, in one line each.**

- **Ranges that contradict their own close are no longer stored.** `jobs/ohlc.py` is the single
  definition; both price lanes and the chart-repair path run it. The close is never altered.
- **The 6,858 stored contradictions are classified, not edited** —
  `data/foundation/price_verification/ohlc_quarantine.json`, reconciling exactly to 6,809
  quarantined ranges plus 49 float-representation rows.
- **The two PSX bases were measured and are safe to mix.** A cross-basis step falls outside the
  exchange's own daily price band 0.022% of the time against 0.071% for an ordinary same-source
  session, so 96 of 389,494 windows are excluded rather than the 188,528 that span a basis change.
  Ledger: `basis_transitions.json`; flag: `dataQuality.basisBreakInWindow`.
- **2022-10-01 is not a PSX session.** The exchange serves Friday's file at the Saturday URL; the
  lane now trusts the date inside the file. The 171 rows are preserved and were already excluded
  by `session_bar()`.
- **Missing fields stay missing.** `jobs/horizons.py` no longer fills an absent high/low with the
  close, and 216 fabricated FX zero-volumes became nulls.

### What is next

**Not started, and none of it is begun:** historical news and original documents, the major crash
and bull-run timelines, pre-event information, catalysts and post-event market reactions. That
corpus is a separate research-data phase and must not be described as complete.

One material exception is carried forward rather than closed: **747 PSX bars** whose published
close sits outside a real traded range. They are quarantined with their evidence; settling the
mechanism needs the exchange's own specification. See the closeout's "Remaining exception".

---

## 0. State of play, 2026-10-16 — market and macro data acquisition is COMPLETE

**Everything below section 0 predates 2026-10-14 and is stale. Read this section, then
`brain.md` rules 129–141. Ignore the older instruction to "read AUDIT.md first"; AUDIT.md
describes a production state that this branch has moved well past.**

### Where the work is

| | |
|---|---|
| Branch | `restore-db-utility` (not `main`; `origin/main` is still at `767d26b`, well behind) |
| Last acquisition commit | `e457276` — "closeout: frozen market and macro acquisition complete at 14 of 14" |
| Latest verified backup | `C:\Users\NEW TECH\nbt-private\backup-2026-10-16T0600Z-acquisition-complete\` (44/44 tables, 25 key files checksummed, 0 mismatches) |
| Database | 1,097,485 rows, 44 tables, ~380 MB of the 500 MB free tier |

### What is done — do not redo any of it

**Frozen market/macro acquisition: 14 of 14 targets.** The authoritative ledger is
`data/foundation/acquisition/target_ledger.json` (a required floor per target, decided before the
data was read) and the manifest is `data/foundation/acquisition/manifest.json`
(`acquisition-manifest-v7-final`).

- **PSX**: 394,014 bars, 2018-01-01 onward, from the exchange's own archive — every published
  session since 2018 was swept. Remaining gaps are 36,762 sessions where a security did not trade
  plus 158 on four empty/absent archive dates; classified with evidence, not assumed.
- **KSE-100**: complete from 2018-01-01. Two segments — the Karandaaz file (2018-01-01 to
  2021-10-14, **close only**, **private**) and the exchange EOD endpoint (2021-10-15 onward,
  `data/foundation/psx_index/KSE100.csv`). They agree on 1,228 shared dates with **zero failures**
  and a maximum difference of **0.000026%**. All 2,171 published sessions covered, none missing.
- **Benchmarks and macro**: 13 series in `data/foundation/benchmarks/` at their sources' own floors
  (^GSPC to 1927, ^VIX to 1990, DX-Y.NYB to 1971, DGS10 to 1962, DFF to 1954, Bitcoin to 2011).
- **SBP**: KIBOR 93,300 observations across 18 series and the policy rate, in `data/foundation/sbp/`.
- **PSX delisted/renamed**: 24,613 bars, 21 symbols, `data/foundation/psx_delisted/`.
- 17 of 17 durable artifact checksums verify. 971 tests pass.

### Two things that must not be undone

1. **The Karandaaz KSE-100 dataset is private.** It lives in `.cache/acquire/karandaaz/`
   (gitignored) and in the PC backup. Permission for internal research and model development was
   confirmed by the owner on 2026-10-16; the written conditions were not supplied, so **no broader
   redistribution right is assumed** — never commit it, never publish it, never serve it.
2. **The Open Data Pakistan CSV is rejected on index identity.** Its values differ from the
   verified KSE-100 by a non-constant ratio (1.01–1.51); on 2021-02-23 it reads 31,626.19 where
   the verified series reads 45,728.75. **Never merge it into the KSE-100 series.**

### What is next

**Milestone B — data cleaning and point-in-time integrity.** Not started. Its objectives and
acceptance criteria are in `brain.md` rule 141. It needs the owner's explicit go-ahead.

**Still later, and not begun:** historical news and original documents, the major crash and
bull-run timelines, pre-event information, catalysts and post-event market reactions. That corpus
is a separate research-data phase — nothing in the acquisition work touched it, and it must not be
described as complete.

**No further acquisition, broad resync or source research is required** unless specific evidence of
a real defect appears.

---

*Everything from here down is the older resume note, kept unchanged for the record.*


## 0. State of play, 2026-10-10 (eleventh session, final audit) — read AUDIT.md first

`AUDIT.md` is the current, authoritative state (PRODUCTION LOCKED on `c36d2a0`): what was verified, what was fixed in `f77e2d7`, `f548e85` and `c36d2a0`
(builds no longer depend on the database, news/products/mirror/watchdog/retry repaired, one-line
action cell, sub-cent formatter, asset page reads the same horizons as the lists), the open findings
ranked, and the owner actions still open (bump `next`, decide the
patient-flip whipsaw). The `PRIMARY` variable and Vercel's unmaintained fallback were removed by the
owner and verified. brain.md rule 89 records why; `tools/logic_audit.py` re-checks the arithmetic. The tenth-session notes below are still accurate about the database move.

## 0. State of play, 2026-10-10 (tenth session) — read this first

**The database is a different one now, and several things below this section describe the old one.**
The Neon project that held everything through 2026-10-09 exceeded its quota and refused every
connection. A fresh project was made, all 25 migrations applied, the seed
run, and every source refetched. **Nothing from before 2026-10-09 survived the move**, and the old
project is still over quota, so the matured decision history from 2026-10-01 to 10-09 is not yet
recoverable. `python jobs/mirror.py --from OLD --to NEW --tables DecisionLog` is the way to bring it
back when that quota resets; it translates asset ids by (industry, symbol) because the two projects
hold different UUIDs for the same stock.

### What must be checked by a person, and cannot be from the repository

| item | why it matters |
| --- | --- |
| **GitHub Actions secret `DATABASE_URL`** | Separate from Vercel's. Eleven workflows read it, including `schema.yml` and every cron lane. If it still names the old project they are all failing on the quota. `gh` is not installed here. |
| **`master` and `main`** | Kept identical. Vercel's production branch follows the repository default, which is `master`; for a day nothing deployed because `master` was 13 commits behind. Push both. |
| **`vercel` CLI is installed and authenticated** | `vercel ls`, `vercel inspect <url> --logs`, `vercel env ls`. This diagnosed the outage in one command after hours of inferring from HTTP headers. Use it first. |

### What changed, in the order it matters (full reasoning is brain.md rules 55 to 70)
* **Heartbeat and watchdog** (rule 75). `/api/health` judges every stored reading with the rule table's own limits; `cron-watchdog.yml` reads it hourly and restarts the stale lane (five lanes only, once an hour, never on a running copy) and goes red, which emails the owner, when a lane keeps failing. Until the `DATABASE_URL` secret is fixed it will escalate every hour, by design. Quotes are stale after 3 minutes and refresh on demand.
* **Live quotes beside the closes, and no placeholder cells** (rule 74). `LiveQuote` (one row per asset), `jobs/live.py`, `cron-live.yml` (every 5 min in the US session, 15 min for crypto; opt-in with the repository **variable** `LIVE_QUOTES=on`), read-only `/api/quote`, and `components/LivePrice.tsx`. Quotes never enter a decision. The list column is now "Last close" with the last trade under it. The lag that prompted it was the stale `DATABASE_URL` secret, not the cadence.
* **Macro gatekeeper: a veto-only model check, built and OFF** (rule 72). `tools/macro_gate.mjs` asks a model once a night whether recent headlines justify refusing a LONG or SHORT; the answer is stored in `MacroGate` and the rule table reads it as an input (`macro-veto`). It can turn a direction into a WAIT and nothing else, fails open everywhere, and does nothing until you set the repository **variable** `MACRO_GATE=on` and the **secret** `ANTHROPIC_API_KEY`. The default engine is now LOCAL (`lib/macroGateLocal.ts`, rule 73): a fixed word table, no model, no key, 20 of 20 on the adversarial exam. It is **inert until the news lane writes to the new database** (the `News` table is empty there) and it trusts only a short declared list of outlets until per-publisher statistics exist. The model engine (`MACRO_GATE_ENGINE=model`) has not been run against the real API. Migration applied to Neon and Supabase (parity identical).

* **47% of printed directions had a stop price had already passed** (rule 65). Now refused as
  `stop-crossed`. Directions 404 to 215; `tools/rederive.py` contradictions 300 to 1.
* **The log now records which confirmation legs backed each call, and which side a refusal refused**
  (rule 66): `DecisionLog.legs` and `.intent`. `tools/scorecard.py` reports per-leg lift with an interval
  over distinct names and never re-weights anything. **No outcome has matured yet.** The first +1
  session measurements arrive after the 2026-10-12 close; +20 around 2026-11-06.
* **Column headers**: no market page had any (rule 67). Pinned header per sector, ten columns including
  Reward:risk and Confirmations. Verified at 1280, 1024, 768 and 375.
* **Universe 477 to 576** (rule 68): 30 coins and 69 PSX shares, proposed by `tools/universe.py` with a
  stated reason for every refusal. PSX deep history backfilled (it had ~85 closes per name).
* **Storage and query cost** (rules 60, 61, 63): 233 MB at 477 assets, the hot query 209 ms to 3.2 ms,
  unchanged rows not rewritten, `PriceSnapshot.id` dropped. Nothing is pruned: the analog leg reads
  every stored close.
* **Three-tier read failover, opt-in** (rules 69 and 71): primary Neon, then `DATABASE_URL_FALLBACK`, then
  Supabase (`SUPABASE_DATABASE_URL`, Session pooler, ap-northeast-2). `jobs/mirror.py` fills the standbys
  and `cron-mirror.yml` refreshes them nightly. Supabase holds a verified-identical schema and is being
  filled; see the next section for what is live and what is not.

### Two things that were wrong in earlier notes

* "477 verdicts re-derived with no contradiction" described the old database and the old engine. Today
  it is 576 verdicts and 1 contradiction (AGTL, close 0.1% above its 20-day).
* An earlier message said the 300 contradictions were the engine breaking the moving-average contract.
  They were the stop-side defect, almost entirely.

### Open, in the order I would do it

1. Confirm the GitHub secret, then re-run `refresh.yml`. Nothing else gates on it.
2. When the old project's quota resets, import its `DecisionLog` with the mirror, then run the scorecard.
3. Decide whether `short-unbacked` and `stop-crossed` refusals should print on the page as refusals; today
   they appear as WAIT with their reason.
4. `rederive.py` still asserts the stack contract for gate 8 and the bias reads; one name trips it.

## 0. State of play, 2026-10-08 (ninth session) — read this first

**Pushed, deployed, verified.** 432 Python tests, 179 web tests, 18 of 18 derivation steps ok,
477 verdicts re-derived with no contradiction, acceptance 24 PASS / 3 PARTIAL / 0 FAIL.

The eighth session's entry is below and still true. This one did four things: made the
derivation lane ten times faster, gave the derived tables a ceiling, grew the pool from 331 to
477, and cut the two pages that had quietly become unreadable.

### Speed, because the pool could not grow without it

Every reasoning job read and wrote one asset at a time. Invisible on a host inside the
database's region; the entire runtime from anywhere else. The full group took **2h50m** from a
host ~240ms away, and the nightly lane's budget is 30 minutes.

| job | before | after | what changed |
| --- | --- | --- | --- |
| lineage | 59.3 min | **0.3** | two statements per story became two for the run |
| rank | 17.2 | **2.4** | `close_on`/`avg_volume` per asset became one query each |
| setup | 11.8 | **0.15** | five reads per asset became five for the universe |
| human | 10.8 | **0.2** | four news windows per target became two for the run |
| analysis | 8.9 | **3.3** | rankings and event impacts read once, lines written once |
| thesis | 8.2 | **0.13** | eight reads per asset became four for the universe |
| analogs | 7.0 | **0.6** | whole-history reads chunked, write batched |
| horizons | 6.0 | **0.3** | bars, peers and sessions read once per horizon |
| confidence | 5.7 | **0.14** | 1,356 single-row updates became four statements |
| investigate | 4.6 | **1.8** | findings and hypotheses batched |
| attribution | 4.3 | **0.1** | write batched |

The whole chain now runs **21.6 minutes at 477 names**, where 331 took 170. Nothing about any
rule changed: every bulk read returns the same rows in the same order as the per-asset read it
replaces, and every batched write keeps its conflict clause.

**Where a window was already a slice of one in hand, it is taken in memory.** `human.py` asked
for four news windows per target; the catalyst and baseline windows are slices of the other
two. That is the pattern to look for first in anything still slow.

**One real bug fell out of it.** `run_targets` selected setups on the newest `periodEnd` for a
horizon — the same set as "the current read per asset" only while one date covers the whole
universe. After the eighth session's per-asset dating, that would have written targets for 157
Pakistani names and none for 249 American ones. It now takes the newest row per (asset,
horizon), and applies the state filter *after* that choice, so a name whose current read is
`wait` cannot have an older `buy` row revived underneath it.

### The tests were hiding four of their own, and the ratchet was blind

`unittest.main()` sat 72 lines from the end of `tests/test_brain.py` with `ShortLevelsAreMirrored`
underneath it. Discovery collected 430; running the file directly printed **OK over 426**.

The query ratchet matched a query only where the call was written inline, so a read reached
through a helper was free — `jobs/rank.py` measured **zero** while issuing seven statements per
asset. It now finds module-level functions that query and counts a call to one inside a loop.
Every baseline was re-measured; each held or rose because a round trip that was always there
became visible.

### The tier, and what now stops it filling

`jobs/retention.py` caps the working set. The window on each table is set by the reader that
looks back furthest, not by taste, and the file names what it will **never** prune so that an
omission reads as a decision: `DecisionLog`, `SignalLog`, `AssetThesis`, `ThesisCheck`,
`EventState`, `Calibration` and the whole of `PriceSnapshot`.

`AssetSetup` needed a guard before it could be capped at 14 days. `thesis.py` walks the run of
those rows to find the session a state first appeared on, and a run whose start has been pruned
appears to begin at the edge of what is stored — which would open a *second* thesis and restart
the clock on a reason that never changed. A run reaching that edge is now matched to the thesis
that already holds its real opening day.

**The sweep does not take an exclusive lock.** `VACUUM FULL` hands pages back to the operating
system and takes ACCESS EXCLUSIVE to do it; its first run killed the news fetch mid-request
("server closed the connection unexpectedly") and the same lock would stall the website's reads.
A plain `VACUUM` does what the job is for. `--reclaim` keeps the rewrite for a human who has
stopped the lanes.

The runway line now separates what grows from what is capped. Counting the capped tables'
arrivals as growth dated the tier's exhaustion to a wall the system no longer walks into:
**383 MB of 500, the permanent record growing 743 rows a session, full around 2027-07-29; the
capped tables settle near 97 MB and stop.**

### Pool: 331 → 477, and seventeen industries that did not exist

| | before | after |
| --- | --- | --- |
| US | 163 | **249** |
| PSX | 97 | **157** |
| crypto | 36 | 36 |
| FX | 27 | 27 |
| commodities | 8 | 8 |

Directional went 86 → **133** (61 LONG, 72 SHORT), High 11 → 19, Medium 41 → 55.

Eleven US industries and six Karachi ones are new, and **none is a category invented to hold a
name**. Each exists because a measured, liquid field had nowhere to sit — which is also why the
2026-10-08 first pass left seventy-two liquid PSX symbols on the floor.

Three names were re-filed where the exchange and the split put them: **ENGROH** out of
Fertilizer into Investment (it was the single row teaching the sector map that Karachi
brokerages grow urea), **KOSM** Textile → Spinning, **PGR** Banks → Insurance.

**The Karachi exchange's own listing is measured, liquid and deliberately absent.** Its ticker
is PSX, which is Phillips 66 in New York, and `/asset/[symbol]` resolves by symbol alone. The
reason is written into `seed.py` rather than left as a gap. `tools/candidates.py` learned the
same lesson: it now checks a candidate against the symbols stored *in that market*, because
checking against every symbol anywhere is what dropped the exchange as "already followed".

### Three pages that had stopped being readable

- **Overview.** The LONG and SHORT tables were the only blocks that printed everything they
  had. Both cut at twelve and say so — the number WAIT already cuts at, because four blocks
  cutting at four different figures read as four different rules.
- **The coming week was six of six Pakistani on the short side.** Thirty-five qualifying shorts
  existed. Inside one grade the markets now take turns; a grade boundary is never crossed to
  balance, so a Medium name cannot displace a High one. Both halves are pinned by a test.
- **`/stocks` was 1.3 MB** whose first screen was the waiting table: 175 of 249 names. It keeps
  every row — capping it would remove the only place a waiting name can be looked up — and
  opens collapsed, with the count in the summary.

### What to look at next

1. `rank.py` is 14 in-loop queries, the highest in the repository, and the only job whose cost
   still rises steeply with the pool. 4.2 minutes of the 21.6.
2. `intraday` (5.9) and `analysis` (5.5) are now the two largest, and `intraday` is network
   bound — `MAX_REQUESTS = 60` caps it, so it does not grow with the pool.
3. News coverage for a newly added name arrives over the following cron cycles. A name with
   none reads NOT MEASURED, which is correct and is also why a big batch looks thin on its
   first day.

## 0. State of play, 2026-10-08 (eighth session) — read this first

**Pushed, deployed, verified.** 432 Python tests, 177 web tests, 17 of 17 derivation steps ok,
331 verdicts re-derived with no contradiction, acceptance 24 PASS / 3 PARTIAL / **0 FAIL**.

### The one thing that was actually broken

`run_intraday` had been raising `ZeroDivisionError` since **2026-10-04**. The volume ratio was
computed in three places — once behind a guard that checks the average for zero, twice inline
without it — and an asset whose last twenty five-minute bars all printed a genuine zero volume
took the unguarded path. This repository stores a real zero volume as a zero rather than a null
on purpose, 29,863 of them, so the input was correct and the arithmetic was not.

It is the first thing `horizons.main()` calls, so the crash took `run_longer` and `run_targets`
down with it in the same process. **Four days with no intraday read and no target range from
the nightly lane**, visible only as an exit code. The symptom in the data was one line:
`AssetSetup` held intraday rows to 2026-10-04 while `IntradayBar` ran to 10-08.

Rule 36 again, and the sharpest version of it so far: the three copies did not disagree about
the threshold, they disagreed about whether the denominator could be zero.

### Four jobs were dating measurements with the calendar

The loophole `setup.py` was fixed for on 2026-10-07, still open in four more files. Measured
that morning from a host five hours ahead of UTC: every close ended 10-07, and 1,788
attribution rows, 3,524 analogs and 283 investigations read `periodEnd` 2026-10-08. The numbers
were right; the date was a day nothing traded. Every reader takes the newest `periodEnd` per
asset, so a row dated forward does not read oddly — **it wins**.

Each now dates from its own data: attribution from the asset's newest close, analogs from the
bar the comparison was made from, investigate from the day the move happened, horizons from the
newest bar in its own window. `tools/future_rows.py` found and removed the 542 left behind,
because an upsert keyed on the date that was wrong has no reason to replace them.

**`setup.py` then went a step further, and this one is new.** It took `max(PriceSnapshot.date)`
across every asset. Two exchanges do not close together: Karachi publishes its file hours
before New York stops trading, so between those two moments the site-wide maximum is a session
a US name has not had yet. Each row is now dated to the newest close of the asset it describes
— the stricter reading of the sentence the file already carried.

`jobs/factors.py` keeps the global anchor **on purpose**: its period is also the "now" its event
distances and news ages are measured from, and that is one question for the whole run. Do not
"fix" it to match the others without dealing with that.

### The test file was hiding four of its own tests

`unittest.main()` sat 72 lines from the end of `tests/test_brain.py` with `ShortLevelsAreMirrored`
defined underneath — four tests that hold a short's stop above the price, a bug this repository
has already shipped once. Discovery imports the module and collects everything, so CI ran 430;
running the file directly executed the entry point at that line and printed **OK over 426**. A
green run that is quietly four tests short is worse than a red one. Moved, with a test that
nothing may follow it and a second that the two run modes agree.

### The query ratchet could not see a round trip through a helper

It matched the query call only where it was written inline, so `jobs/rank.py` measured **zero**
while issuing about seven statements per asset through `close_on`, `avg_volume` and
`size_ranks`. It now finds module-level functions that query and counts a call to one inside a
loop. Every baseline was re-measured; each held or rose because a round trip that was always
there became visible, and none rose because a query was added.

This matters more than it reads. `rank.py` is `14` — the highest in the repository — and it took
**17.2 minutes** of the 2h50m local run. The decision lane's budget is 30 minutes.

### Pool: 273 → 331

| | before | after | directional |
| --- | --- | --- | --- |
| US | 126 | **163** | 66 (8 High, 32 Medium) |
| PSX | 85 | **97** | 16 (3 High, 9 Medium) |
| crypto | 27 | **36** | 1 |
| FX | 27 | 27 | 3 |
| commodities | 8 | 8 | 0 |

`tools/candidates.py` measures a candidate against its own free source before it is written
down, which the 2026-10-04 batch did by hand and left no record of. Three things in it are
worth keeping:

1. **Crypto is asked through `prices.crypto_closes`**, the same four-venue chain the fetch job
   walks. TRON is followed here and Coinbase serves no `TRX-USD` at all, so a check written
   against one exchange would reject a coin this site prices daily. The floor is $4M of median
   daily turnover — the *median of the 27 already stored*, not a number chosen to sound strict:
   the $20M Binance figure the last batch used rejects two thirds of the existing universe.
2. **PSX names are placed by the exchange's own sector code**, field three of every row in
   `mkt_summary`, mapped to an industry by reading which code the followed names carry. A code
   counts only with **at least three** followed names behind it. That floor is load bearing:
   `ENGROH` is a holding company the exchange files under its investment-company code and this
   project placed in PSX Fertilizer, and on its own it taught the map that Arif Habib, Trust
   Brokerage and five other brokerages were fertilizer producers.
3. **Two new US industries**, because the alternative was a wrong label. Precious Metals is
   written as futures and the funds that *hold the metal*; a peer median mixing bullion with a
   levered producer describes neither. Eleven miners and thirteen base-metal and steel names
   have their own groups. Seventy-two liquid PSX symbols were ranked and left out for the same
   reason — there is no industry here for steel, sugar, pharmaceuticals, chemicals, food,
   property, insurance or the terminals.

### Crypto and FX, measured rather than asserted

- **crypto: 36 of 36 carry both a volume ratio and a peer-relative reading.** Every leg the
  rules can use is present. One directional verdict. That is a market condition, not a gap.
- **FX: 27 of 27 carry a peer-relative reading, 0 of 27 carry volume.** The volume absence is
  structural and stays proven: no venue publishes spot FX volume. CME currency futures do
  publish volume and were considered and rejected — futures volume is not spot volume, and
  quoting it as "EURUSD traded 1.4x its average" would be a different instrument's number under
  this one's name.

### The limit that is now visible: 2027-02-12

`tools/acceptance.py` prints the date the 500 MB free tier is reached, from the measured rows a
session adds and the measured bytes a row costs. Today: **339 MB, 1,934 rows a session at 684
bytes a row, full around 2027-02-12 — 127 days.** `IntradayBar` does not grow (7-day sweep);
`PriceSnapshot` and the per-session derived tables do.

**Nothing was deleted to buy room, deliberately.** The accuracy loop matures `DecisionLog` over
60 days and `thesis.py` reads a run of `AssetSetup` rows, so a retention sweep written in a
hurry is a next-week problem where 127 days is not. It is the first thing to design properly.

### Timing, for whoever runs these locally

The full `run.py decision` took **2h50m from a host ~240ms from the database**; a CI runner is
~5ms, so the same work is roughly fifty times faster there. `lineage` 59.3 min, `rank` 17.2,
`setup` 11.8, `human` 10.8, `analysis` 8.9, `thesis` 8.2, `analogs` 7.0. Do not read a local
runtime as a production one, and do not read the nightly budget as safe because a local run
finished — check the lane.

## 0. State of play, 2026-10-07 (seventh session) — read this first

**Pushed, deployed, verified.** 424 Python tests, 177 web tests, build green, 273 verdicts
re-derived with no contradiction.

### Legs recovered, and what was structural

| | crypto | forex |
| --- | --- | --- |
| volume | 2 of 27 pass | **0 — no venue publishes FX volume** |
| relative | 24 of 27 pass | 16 of 27 pass, **0 unavailable (was 7)** |
| news tone directional | 12 of 27 | 2 of 27 |
| analogs stored | 27 of 27 | **0 — and never possible** |
| directional verdicts | 1 | 2 |

**Crypto's blocker is not a missing leg.** 22 of 27 coins have no aligned trend at all, which is a
market condition. The recoverable fault was the forming UTC day: `fetch_crypto` stored the day in
progress as a close, and `cron-crypto` runs every two hours, so at 02:05 UTC the "close" was two
hours of trading. Guarded now.

**Forex's two absences are structural and say so.** No venue publishes FX volume, and
`jobs/analogs.py` cannot match a day without a volume ratio, so no pair can ever hold an analog
set. The recoverable one was the peer reading: `fx-emerging` held 4 and `fx-europe` 3 against
`MIN_PEERS = 5`, so 7 pairs had none. Merged into one group of 7 — the only repair that does not
move a threshold, since 7 cannot split into two fives.

**What that merge did is worth reading carefully: directional FX went 3 to 2.** USDTRY lost its
LONG because the peer reading it gained argued against it at -1.6. More evidence withdraws a
direction as readily as it confirms one, and a leg recovered is not a leg that agrees.

**FX can reach Medium but not High, by construction.** Confidence counts timeframe agreement,
volume and analogs; two of the three are permanently unavailable, so one confirmation is the
ceiling. No pair has timeframe agreement today, which is why FX shows 0 Medium.

### The analog floor, aligned

`analogConfirms` asked `> 0.5` while `jobs/setup.py` has required `ANALOG_SHARE = 0.55` since it
was written. 13 of 44 directional non-Low names rested on a share within five points of a coin
flip. Aligned, with a test reading both files — the cross-language pair this file has listed as "a
comment, not a constraint" for several sessions. It is a tightening and can only remove
confirmations: High went 14 to 12.

It also exposed a missing branch. `confirmMissing` spoke only when the analog set could not be
*judged*; when it was judged and disagreed it said nothing, so a reader could not tell "not
checked" from "checked, and it does not agree". Now printed with its numbers.

### Exit if working, everywhere

One rule in `lib/target.ts` — never averaged, method named, "no clear target stored" when the job
wrote none — used by the asset panel, the home LONG/SHORT rows and the coming-week block, so three
surfaces cannot quote one name three levels. Verified live on AAPL: $342.99 on all three.

### The accuracy loop

`matureRows` in `tools/decide.mjs` already measured moves; nothing scored them against the stated
direction and stop. `tools/scorecard.py` is that half. **It writes nothing** — scores are derived
on demand, so there is no second copy of the truth to drift.

**At 5 sessions: 0 of 264 matured.** The log starts 2026-10-02. No rate is published and the tool
says so. At 1 session: 197 matured, 98 right / 63 wrong / 34 stopped / 2 flat — and the tool prints
that those are **78 distinct names over 4 sessions**, not 197 independent trials, and refuses any
rate under 30 rows.

### A trap worth knowing

A local seed change was reverted once between two reads, and I could not establish what did it.
`backfill.yml` triggers on `jobs/seed.py` changes but does not run seed. **Commit before relying on
a local data change, and verify from a fresh process rather than the connection that wrote it.**

### Not started

**Phased pool expansion.** Left deliberately for a verified-green base rather than begun while a
recompute was in flight.

## 0. State of play, 2026-10-07 (sixth session) — read this first

**Committed and pushed; `main` and `master` current; production deployed and verified.**

### The one change that matters

**A WAIT now says which kind it is.** `Decision.basis` is `file` (a measurement is absent, nothing
was judged) or `evidence` (the measurement exists and does not support acting), rendered as one
chip — NOT MEASURED or NO CONFIRMATION — from a single component, so home, the weekly block and
the asset panel cannot drift. Live proof, two PSX names on the same gate:

    KEL   WAIT  NO CONFIRMATION  "Unusual move and news thin."
    DFML  WAIT  NOT MEASURED     "Unusual move and news not checked.
                                  No news has been collected for DFML, so none was weighed."

Before, both were an identical grey WAIT with Low beside it.

Measured over all 273: **202 evidence WAITs, 4 file WAITs, 67 directional.** So the WAITs are
overwhelmingly real readings, not empty files — which is the answer to "is the system being
timid", and it is now checkable rather than asserted.

### Loopholes closed

1. **`jobs/setup.py` stamped `periodEnd` with `date.today()`.** `jobs/factors.py` states the rule
   in `session_end` and obeys it; setup.py did not. All 272 swing setups read 2026-10-08 while
   every close, factor and decision read 10-07, because the job ran from a UTC+5 host after 19:00
   UTC. `thesis.py` copied the date onto 11 theses. Now anchored to the newest stored close; the
   calendar is kept for event lookups, which really are questions about now. The 283 rows dated to
   a session that never traded were deleted — they outranked the correct rows in every
   `ORDER BY periodEnd DESC`.
2. **The fall-through claimed a position against averages nobody computed.** With no setup row it
   printed "Price is between its own averages." Now it says the setup has not been measured.
3. **"No similar past days stored" read as a collection gap.** With no volume ratio it is not
   collectable: `analogs.py` matches on one among three factors. All 27 FX pairs hold zero analogs
   for that reason and always will. The line names the mechanism and stops — `volumeRatio` is also
   null on a thin baseline, so it must not claim the venue publishes none.

### `tools/rederive.py` — run this before believing anything

Re-derives every published verdict from raw bars **without importing the rule table**, because a
rule table cannot audit itself. Trend against the windows of the horizon the verdict actually
rested on (not always swing), stop on the breachable side, close inside the market's own
allowance, and each WAIT's claimed kind against the data. **273 verdicts, no contradiction.**

### Numbers, this pass

| | before | after |
| --- | --- | --- |
| LONG / SHORT / WAIT | 35 / 29 / 209 | 37 / 30 / 206 |
| High / Medium / Low | 15 / 29 / 229 | 14 / 35 / 224 |
| swing buy / short | 12 / 21 | 17 / 22 |

### Known and deliberately not changed

- **`analogConfirms` accepts a bare majority.** 13 of 44 directional non-Low names sit within 5
  points of a coin flip; HMC was 377/748 = 50.4%, printed as "Confirmed by". `jobs/setup.py`
  already uses `ANALOG_SHARE = 0.55` for the same judgement. Aligning them reclassifies 16 of 61
  names — a brain change, so it needs its own measured decision, not a bolt-on.
- **FX can never hold an analog** (above). Fixable only by letting `similar()` match on two
  factors when volume is unavailable by construction — rule 21 — which re-cuts every stored set.

## 0. State of play, 2026-10-07 (fifth session) — read this first

**Everything is committed and pushed; `main` and `master` are both current and the tree is
clean.** Eight commits. The standing rule held every time: after each push to `main`, run
`git push origin main:master`.

### What was asked, and the one-line answer

The ask was to stop the site answering WAIT and Low everywhere, to gather more data before
deciding, to add commodities, to cover products by country and state, and to regression-test
responsiveness. **Four real production bugs were found and fixed, every one of them a
denominator, an ordering or a clock — and the honest headline is that the WAIT count barely
moved.** It went 207 of 267 to 209 of 273, which is 77.5% to 76.6%. What changed is that those
WAITs are now produced by correct arithmetic instead of by broken arithmetic.

### The four faults, in the order they cost the most

| | |
|---|---|
| **A part-day stored as the day's close** | `cron-us-prices` fetched at 13:50 UTC into a session running 13:30-20:00. AAPL's bar for 2026-10-07 held **8.0M shares against 30-50M** on its neighbours; across 155 US names the newest bar's volume ran at a **median 0.21x its own average** against a 1.2x gate. Every US setup's volume leg failed on the clock. PSX read 0.84x the same day — the control that identified it. Fixed by `forming_sessions` (a guard, because a schedule cannot be trusted to stay correct) plus moving the fetch to 21:50 and the decision to 22:10. **Verified after: AAPL 31,250,163 shares, US median 0.757.** |
| **The volume threshold meant a different thing in every market** | The ratio divided by the *mean* of a right-skewed window. Over 15,411 asset-sessions a typical PSX day read 0.614 and a typical crypto day 0.931, so `VOL_ACTIVE` at 1.2 demanded ~2.0x normal in Karachi and ~1.3x in crypto. Median instead of mean centres every market 0.83-1.06. |
| **A net news tone divided by headlines that had no tone** | `(positive - negative) / items` where **only 11.1% of headlines carry any tone word** and the median asset has **2**. The bar therefore rose with coverage: 64 headlines at 7 positive and 0 negative read "neutral". Now divided by the opinionated subset with a floor of 5. Directional tone 55 -> 69 of 265. |
| **PSX was a day late, invisibly** | One fetch at 12:40 UTC on a margin that was not there. On 10-07 the file was absent at 18:40 and present at 19:10, so the close was only ever picked up by the *next* day's run — hidden because `psx.py` backfills recent sessions and `STALE_AFTER_DAYS.PSX` is 6. Three attempts now; 20:40 is the one that matters. |

### The measurement, before and after — read this before claiming anything

Baseline is 2026-10-07 18:40 UTC, before any fix reached the data. After is the same day's close,
same rule table, corrected inputs.

| | before | after |
| --- | --- | --- |
| LONG / SHORT / WAIT | 36 / 24 / 207 | 35 / 29 / 209 |
| of 267 / 273 assets | 77.5% WAIT | 76.6% WAIT |
| **High confidence** | 9 | **15** |
| Medium | 26 | 29 |
| Low | 232 | 229 |
| gate `incomplete` | 166 | 161 |
| gate `unexplained-move` | 29 | 35 |
| swing setups buy / short | 13 / 8 | 12 / **21** |
| assets with a directional news tone | 55 | 69 |

**What that says, stated plainly so the next session does not oversell it.** High confidence rose
67% and swing shorts went from 8 to 21, which is the gate that had never produced a short in the
life of the table. The *count* of WAITs did not fall. On this day, with correct data, most names
genuinely do not have two of three confirmations — and that is now a finding rather than an
artefact. `unexplained-move` went **up** (29 -> 35), which is the honest direction: with real
closes, more names show a move whose size the news does not account for.

**Do not "fix" the WAIT count by loosening a threshold.** Every number above came from correcting
a denominator, and the owner's standing instruction is that a WAIT is acceptable when the data
justifies it. If more action is wanted, the lever is more evidence per asset, not a lower bar.

### What is new on the site

- **Commodities are their own market and page.** Copper (HG=F), WTI (CL=F), Brent (BZ=F), natural
  gas (NG=F), platinum and palladium added; gold and silver futures moved out of the US stock
  list where they had been filed since seeding. ~1,950 bars each back to 2019. CPER and COPX
  re-filed to a new `industrial-metals` group — copper was being measured against gold by the
  relative-strength leg.
- **A commodity reads from the previous day's settle, and that is correct.** GC=F's session runs
  04:00 UTC to 03:59 the next day, so its bar for day D is not finished until D+1. See the note
  on `STALE_AFTER_DAYS.Commodity`.
- **Product regions: 9 of 30 products had data, now 24.** `geo.py` ordered products `ORDER BY
  name` under a 45-minute budget, so the back of the alphabet was never asked about and never
  would be. Now ordered by how stale each product's own coverage is. The remaining 6 sort first
  on the next run; Google Trends 429s are what caps a single run, not the ordering.
- **The phone layout was cutting the verdict off.** Cards laid out 411px inside a 343px track
  under `overflow-x-clip`, so the right-hand end of every row — part of the pill and the whole
  confidence column — was clipped, not scrollable. `min-w-0` on the card. Swept every route at
  320/375/768/1280.

### Verified, and how

- 422 Python tests, 150 web tests, `tsc` clean, `eslint` clean, **`npm run build` passes**.
- Every new guard was run against the old behaviour and fails on it — the two schedule guards,
  the three volume-baseline tests, the tone tests.
- **An independent verifier** (`scratchpad/verify_decision.py`, not kept) re-derived published
  verdicts from raw bars without importing the rule table: trend, volume, relative strength, news
  counts, invalidation on the correct side, close age inside the market's own limit. It reported
  **no contradiction** across the sampled directional calls.
- Demo-traded one as a reader: LCID SHORT, High, close $3.89, entry $3.89-$4.32, stop $4.32,
  reason "setup down, longer view agrees, volume 1.3x, 23 of 37 similar days went the same way",
  with a Reuters headline about a deliveries miss sitting under it. Coherent and actionable.

### Two things I got wrong this session, recorded so they are not repeated

- I assumed the part-day bug also invalidated `CONFIRMS_NEEDED = 2`. **It does not.** Re-measured
  on complete sessions only, the volume pass rate was still ~9% on a single day's cross-section,
  so that threshold stands on its own evidence. Measure before rewriting a justification.
- My own verifier reported a false contradiction on HMC, because it checked the 20/50 averages
  unconditionally. `pickSetup` takes the first **directional** row in horizon order swing ->
  longer, so when the swing read is `wait` and the longer read is `buy`, the decision rests on the
  100/200 trend. The tool was wrong, not the system.

### Still pending, unchanged from the fourth session

1. **The products card is missing from the front-page block.** Products carry a different decision
   shape (`lib/productDecision.ts`), so it needs its own wiring rather than `ASSET_CLASSES`.
2. **`npm audit`: 5 high advisories**, all in build/CLI tooling, none on the request path. **Do
   not run `npm audit fix --force`** — it downgrades prisma 7.10 to 6.19.
3. **Cross-language constants are still a comment, not a constraint.** `THIN_NEWS_BELOW` (TS) and
   `MIN_ITEMS` (`human.py`) are both 8; `ANALOGS_CONFIRM_MIN` and `MIN_MATCHES_LOW` both 8.
4. **`lineage` has 1,013 un-lineaged News rows.** A local run stalled on a dead connection and was
   killed; its committed work (6,920 clusters) is intact and the job is resumable. An un-lineaged
   item counts as its own story, which inflates catalyst counts slightly until it runs.
5. **The refresh gate is still 0 of 2** and still blocked on `gh` not being installed.

### Do not repeat these

- **This machine's network dropped twice** during the session, each time taking out DNS entirely
  and killing whatever job was mid-flight. The jobs failed loudly rather than writing partial
  data, which is the designed behaviour. If a job exits in a fraction of its usual time, suspect
  the network before the data.
- **`$?` after a `$(...)` substitution is the substitution's exit code**, not the job's. A runner
  script reported "exit 0" for three steps that had all failed on DNS; only a 12-second runtime on
  a 9-minute job gave it away. Capture the status into a variable on the line that follows the
  command.
- **Do not run `jobs/run.py decision` from a non-US host.** It carries `rank` (14 min local) and
  `lineage` (32 min). Run `factors -> human -> setup -> thesis` individually, then
  `node tools/decide.mjs`, which is seconds. `decide.mjs` reads no `AssetThesis`, so it can be run
  before `thesis` to land the verdict sooner.

## 0. State of play, 2026-10-07 (fourth session) — read this first

**Everything is committed and pushed. `main` and `master` are both at `f68357d`, the working
tree is clean, and nothing is mid-operation.** Two commits landed. Both were pushed together,
so the `master` fast-forward is already done — it had drifted 9 behind again before this
session, which is twice in two sessions. **The standing rule still holds: after every push to
`main`, run `git push origin main:master`.**

### What this session was asked for, and what it found

The ask was data coverage, fallback sources, and a sharper directional read. The first half of
it turned out not to be a coverage problem at all.

**Prices are healthy in every market.** Measured 2026-10-07: all 267 assets have a close inside
their own staleness rule — Crypto 27, FX 27, PSX 85, US 128, worst case one day old. The
four-venue crypto chain is doing exactly what it was built for: **Binance has been silent since
2025-10-21** and Coinbase is carrying 26 of 27 coins with Kraken on the last one. Nothing needs
a price fallback. Do not go looking for one.

**The binding constraint was news, and the cause was a sort order.** Google News RSS answers a
search by **relevance over its whole index, not by date**. The first six items of `"Hub Power"
Pakistan` were dated 24 Jul, 22 Jul, 28 Jul, 10 Aug, 4 Jun and **5 Mar 2024**, out of 97 offered.
`NEWS_PER_ASSET` keeps the first six, `ON CONFLICT DO NOTHING` drops them as already stored, and
the asset is frozen at six rows for ever. HUBC, MEBL and SYS each held exactly 6 rows, newest
7 Sep. 21 PSX names and 3 FX pairs held nothing from the last 30 days; 74 of 85 PSX names were
below the 8 headlines `jobs/human.py` needs to publish a tone direction.

Nothing in the lane could see it. The feed returns 200, parses, and hands back a hundred items,
so every guard rule 31 put in place reads healthy. **This is the third time a fault here has
turned out to be a denominator or an ordering rather than a missing source** — see rule 9, rule
39, and now rule 31's note on counters. Check what the data is being *compared* or *sorted*
against before concluding a source is absent.

### The two commits

| | |
|---|---|
| `027a09c` | News: every feed asks `when:30d` through one url builder **and** checks each item's own `pubDate`, because the operator is a request and the date is the evidence. A per-asset relevance guard, since narrowing the window promotes weaker matches — an Indian biogas story filed against SYS is a tone reading built from articles about someone else. Tickers match as capitalised whole words (`SYS` had matched "Micro Irrigation **Sys**tem"). A bounded junk filter for rate tables (`Convert 1 USDC to SEK — Bybit`, 36 of them on USDSEK alone). A fallback chain: Bing News RSS first everywhere, Yahoo's per-ticker feed for US listings only. Counters are **per source**, so a fallback can never vouch for a silent primary. |
| `f68357d` | `Decision.developing`: the withheld trend direction, which was sitting in the stored `conditions` string unread. 112 of 267 now carry a direction forming — 45 towards LONG, 67 towards SHORT — ordered on the front page by `closeness`, the stored factor over the threshold it has to clear. Led by ASML at 1.19x of the 1.2x volume gate. |

### Verified in production, 2026-10-07 — the news lane was run by hand and it worked

`python jobs/run.py news` ran from a laptop against the live database: **1,143 rows written,
17.8 minutes, exit 0.** This is the check the section below asks for, already done.

| | before | after |
| --- | --- | --- |
| PSX assets with an item in 30d | 64 of 85 | **76 of 85** |
| PSX with zero news | 21 | **9** |
| PSX items | 265 | **431** |
| FX with zero news | 3 | **0** |
| FX items | 89 | **197** |
| US with zero news | 1 | **0** |
| US thin (under 8 stories) | 10 | **4** |
| News rows total | 6,696 | **7,839** |

The chain fired for **49 assets** and **Bing answered 61 of 61 feeds**, so the fallback works in
production and not only in a dry run. 12 assets still have nothing from any source — ALTN, APL,
AVN, DFML, GAL, GATM, INDU, KTML, PIOC, PKGP, PTC, WTL — which is a real absence reported as
"no recent coverage", not borrowed coverage.

**17.8 minutes is also what proved the lane had outgrown its timeout.** `cron-news.yml` killed
the job at 15, so the next scheduled run would have died and been reported as "cancelled" —
the `cron decision` trap, one lane over, reached by adding work instead of adding assets. Fixed
in `1a3f158`: `NEWS_FALLBACK_BUDGET = 150` bounds the variable half and the timeout went to 25.

### What was still mid-flight when this session ended — READ THIS FIRST

The derivations that turn news into verdicts were **running when the session was cut**, so they
are very likely **incomplete**:

```
factors  DONE  -- 267 rows written for 2026-10-07
human    was running when the session ended
setup    not reached
thesis   not reached
decide   not reached
```

**So `DecisionLog` is still on `periodEnd 2026-10-06` and its verdicts do not yet reflect the
1,143 new articles.** `AssetFactor` is fresh for 2026-10-07; `HumanSignal` may be partly written
for today, because these jobs upsert per asset and a killed run leaves the assets it reached
updated and the rest not.

**Nothing needs repairing.** Every one of these jobs is idempotent per asset and the scheduled
lanes re-run them on their own clock — `cron-decision` at 15:10 UTC owns the whole chain. The
honest options next session, in order of preference:

1. **Do nothing and let the lanes converge.** Check `cron decision` went green, then read the
   stored spread. This is the cheapest and it is what production is designed to do.
2. If you want today's numbers now, the chain that turns news into verdicts is
   `factors -> human -> setup -> thesis`, then `node tools/decide.mjs`. Roughly 17 minutes
   locally. **Do not** run `jobs/run.py decision`: it includes `rank` (14 min local) and
   `lineage` (32 min, prints nothing the whole time), both of which are about a minute on a
   same-region runner.

`lineage` was deliberately skipped, so the new rows carry no `lineageId` yet and story counts
still measure the older clusters. It is not in the news lane — `GROUPS["news"]` is
`prices news` alone — so the decision lane is what will assign them.

### What to expect once that chain completes

`decide.mjs --dry-run` before the news run reported **112 of 267 with a direction forming**, 45
towards LONG and 67 towards SHORT, led by ASML at 1.19x of the 1.2x volume gate. That figure was
computed on the *old* news, so expect it to move: tone and the news leg of `setup.py` now have
real coverage on 67 names that previously had none or nearly none. **Whether it moves up or down
is not predictable and must not be presented as an improvement either way** — more evidence can
just as well withdraw a direction as confirm one, and a gate loosening because a reading got
better-evidenced is the honest outcome in both directions.

### What is verified and what is not

- **Verified:** 398 Python tests, 138 web tests (21 new), eslint clean, `tsc` clean,
  `npm run build` clean, `node tools/decide.mjs --dry-run` reports the 112 against the live
  database, and the rendered front page leads with ASML at 99% of its threshold.
- **Verified against live feeds, dry run, no writes:** USDPKR 0 → 6 real rupee stories, USDBDT
  0 → 6, USDSEK 0 → 6, HUBC 0 → 2, MEBL 0 → 4.
- **NOT yet verified in production.** No news row has been written with the new code. The
  improvement lands on the **next `cron-news` run** (`20 */2 * * *`). **First thing next
  session:** check that the stored counts actually moved, not just that the lane went green.

```sql
SELECT count(DISTINCT n."assetId") FILTER (WHERE n."publishedAt" > now() - interval '30 days')
  FROM "News" n JOIN "Asset" a ON a.id = n."assetId"
  JOIN "Industry" i ON i.id = a."industryId" WHERE i.market = 'PK';
-- was 64 of 85 with any item, and 21 with none at all
```

  Also check `source` on the new rows: `Bing News RSS` appearing at all proves the chain fires,
  and it appearing *everywhere* would mean the primary has stopped answering from the runner.

### Residuals, deliberately left

- **`SYS` collides and cannot be fixed by name matching.** "Systems Limited" is a legal name of
  two generic words and also matches **Organic Recycling Systems Limited** and **Inter State Gas
  Systems Limited**. The country word does not separate them either. A rule strict enough to
  catch it would reject "Pakistan's Systems Limited eyes acquisitions", and dropping real
  coverage of twenty names to clean two items is the wrong trade. A hint in `ASSET_NEWS_HINTS`
  is the lever if it ever matters more than it does.
- **`INDU` reads 0 and that is honest.** Indus Motor's coverage is real and all of it predates
  the window. Do not widen the window for one name.
- **The workflow has been called "rss ingest, dedupe, junk filter" since it was written and no
  junk filter existed.** One exists now, and it is deliberately narrow: the single measured
  shape, matched at the start of a title. Widening it is how real stories start disappearing.
- **FX has no volume by construction** — OTC, no consolidated tape — so the volume leg can never
  confirm an FX pair, and `closeness` is null for it rather than 0. That is rule 21, not a gap.

### Still pending from the third session, unchanged

1. **The products card is missing from the front-page block.** Four of the five asked-for cards
   were built. Products carry a different decision shape (`lib/productDecision.ts`,
   `decideProduct`), so the card needs its own wiring rather than `ASSET_CLASSES`.
2. **`incomplete` is still the largest gate at 163**, but it now reads differently: 112 of those
   have a named direction and a named missing confirmation. The remainder are state `none` —
   price between its own averages — which is genuinely nothing to report.
3. **`npm audit`: 5 high advisories, all in build/CLI tooling.** None on the request path. **Do
   not run `npm audit fix --force`** — it downgrades prisma 7.10 to 6.19.
4. **Cross-language constants are still a comment, not a constraint.** `THIN_NEWS_BELOW` (TS) and
   `MIN_ITEMS` (`jobs/human.py`) are both 8; `ANALOGS_CONFIRM_MIN` and `MIN_MATCHES_LOW` both 8.
   A test reading both files would close it. **There is now a third pair worth pinning the same
   way:** `prices.NEWS_FLOOR` is asserted against `human.MIN_ITEMS`, which is the shape the other
   two want.

### Do not repeat these

- **Do not run `jobs/run.py decision` from a non-US host.** Round trip to Neon from Pakistan is
  238 ms and `rank.py` is a per-asset query loop, so `rank` alone takes 14 minutes locally
  against 0.2–1.3 on a runner. Local timings are ~15x inflated and are not a production signal.
  Use `decide.mjs` locally: 5 seconds.
- **`bundleFromQuery` re-declares every field by hand.** `conditions` was selected by both
  queries, read by the rules, and dropped in between with nothing failing — exactly as
  `medianPct` and `positive` were before it. **That is three fields lost at the same seam.** An
  optional field cannot fail to exist, so the guard has to be a test that the value survives the
  seam, never the type. Check this seam first when a stored column reads as absent.
- **Two parsers of the `conditions` format now exist** (`jobs/thesis.py` and
  `lib/setupConditions.ts`), which rule 23 is the reason to declare rather than hide. Both are
  tested against the same literal strings from `setup.py`'s output. A new horizon written in a
  new format breaks both tests rather than silently producing theses with nothing to compare.

## 0a. State of play, 2026-10-06 (third session)

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

### Credentials

`.env` holds a live `DATABASE_URL` for the Neon branch.

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
