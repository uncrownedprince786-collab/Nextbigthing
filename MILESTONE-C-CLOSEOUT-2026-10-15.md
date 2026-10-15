# Milestone C — data foundation completion, closeout 2026-10-15

## Verdicts

| Gate | Verdict |
|---|---|
| **Data foundation** | **PASS**, with two documented source limitations |
| **Brain-training readiness** | **BLOCKED** on one named dependency (§8) |

Branch `milestone-c-research-corpus`, cut from the protected Milestone B commit
`ba06cd1a0702f20feed7d6f5e7e3cfd3663e0f62`. Milestone B was not reopened, re-audited or modified.

---

## 1. What was already complete and reused

Measured once, not re-derived. Everything in this table is evidence from earlier phases that this
milestone relied on rather than rebuilt.

| Area | State reused | Evidence |
|---|---|---|
| Price history | 1,097,638 bars, 616 assets, 2018-01-01 → 2026-10-14, 6 sources | Milestone B counts |
| Range validity | 6,858 contradictions classified; 6,809 quarantined, 49 float | `ohlc_quarantine.json` |
| Basis integrity | cross-basis step out of band 0.022% vs 0.071% same-source | `basis_transitions.json` |
| Corporate actions | 239 candidates, 237 actions across 150 assets, single reader | `unadjusted_actions.json`, `actions.py` |
| Survivorship | 127 S&P removals measured, 124 absent from the universe | `survivorship/report.json` |
| Macro point-in-time | 32 series, every row with `availableAt`, 10 revision-tracked | `macro/manifest.json`, vintages |
| Benchmarks | 13 series at source floors (^GSPC to 1927) | `benchmarks/manifest.json` |
| Freshness | 0 of 616 assets stale beyond 7 days | Milestone B |
| Durable artifacts | 17 of 17 checksums verify | `verify_durable.py` |

No expensive job was re-run to reconfirm any of it.

---

## 2. Coverage matrix

| # | Category | Status | Evidence / missing proof |
|---|---|---|---|
| A1 | Asset identity, class, currency, calendar | **complete** | 616 assets typed and currency-tagged; `session_bar()` is the one calendar rule, mirrored in `lib/sessions.ts` |
| A2 | OHLCV, timestamps, session boundaries | **complete** | 1,097,638 bars; ranges validated at ingest and classified historically |
| A3 | Gaps, duplicates, invalid prices | **complete** | PK makes duplicates impossible (1,097,638 = distinct pairs); PSX residuals classified into no-trade / empty-archive |
| A4 | Corporate actions, splits, delistings | **complete** | 237 actions; 24,613 delisted bars across 21 symbols |
| A5 | Cross-asset: indices, FX, commodities, rates | **complete** | 13 benchmark series + 32 macro series + 27 FX pairs |
| A6 | Availability at decision time (survivorship) | **incomplete** | bias measured and bounded, not removed: 63 of 127 S&P removals have no free daily history left |
| A7 | Shorting, borrow, spread, trading cost | **not applicable → blocked** | no free source for PSX borrow or historical spreads; no cost model is asserted anywhere |
| B1 | Company announcements / earnings | **incomplete** | 86 verified earnings events; no filings corpus |
| B2 | Macro releases, central-bank communications | **complete** | 32 FRED series with availability lags; 18 verified monetary events |
| B3 | Pakistan-specific developments | **incomplete** | SBP policy rate + KIBOR complete; 5 PSX-proxy events verified; no Pakistani news archive |
| B4 | Global economic / geopolitical events | **complete** | 19 geopolitical + 6 political + 4 disaster verified events, 2019–2026 |
| B5 | Source provenance per record | **complete** | every event carries source, sourceUrl, tier, evidence groups, `discoveredAt` ≠ `date` |
| B6 | Deduplication without losing corroboration | **complete** | `NewsLineage` clusters 8,134 items into 5,002 stories keeping publisher counts |
| B7 | **Historical news archive** | **blocked** | News spans **2026-09-08 → 2026-10-15 only (37 days)**. §7 |
| C1 | Event → asset linkage | **complete** | 119 of 168 verified events linked to a stored asset; 48 are market proxies; 1 (`GME`) not in the universe |
| C2 | Pre-event market state | **complete** | 167 rows, each from bars strictly before the event session |
| C3 | Post-event reaction across horizons | **complete** | 1d/5d/20d 167 of 167; 60d 164 of 167 (3 windows still open) |
| C4 | Return, excess, MFE/MAE, drawdown, duration | **complete** | all present per horizon; excess return on 92 rows where a benchmark applies |
| C5 | Transaction cost / execution feasibility | **blocked** | same as A7 |
| D1 | Publication vs event vs ingestion time | **complete** | `Event.date` / `discoveredAt`; `News.publishedAt` / `createdAt`; macro `availableAt` / `firstSeen` |
| D2 | Original vs revised macro data | **complete** | 10 series × 400 ALFRED snapshots, `leftCensored` flagged |
| D3 | Universe membership and actions over time | **incomplete** | same limitation as A6 |
| D4 | Feature cutoffs and label horizons | **complete** | enforced in the artifact: 0 leakage on three checks (§4) |
| D5 | Leakage, duplicate and overlap checks | **complete** | `USREC` excluded with a test; 0 future-dated bars; 0 analogs before `periodEnd` |
| D6 | Chronological / walk-forward splits | **complete** | `walkforward.py` + `determinism_check.py` exist and are tested |

---

## 3. What was implemented in this milestone

### 3.1 The verified event corpus reached the database

`tools/foundation/events.py` verified 168 of 240 candidate events against Wikipedia, Wikidata and
a measured market move in 2026-10. **None of it had ever been loaded.** `jobs/events.py` seeds a
hand-written list of eight events, and eight was what every downstream reader had seen.

`tools/foundation/events_load.py` loads the verified set with its provenance.

| | Before | After |
|---|---|---|
| Historical `Event` rows | 8 | **176** |
| `EventLink` rows | 523 | **642** |
| Historical events with an asset link | 8 | **119** |
| Years spanned | 2022–2025 | **2019–2026** |
| Categories | 4 | **12** |

Idempotent: a second `--apply` run inserted 0 and left both counts unchanged.

### 3.2 The event-to-reaction corpus

`tools/foundation/event_reactions.py` writes `data/foundation/events/reactions.jsonl.gz`
(41,185 bytes) and a manifest. **167 of 168 verified events** (`GME` is not in the universe).

Each row keeps three things apart, and this separation is the point:

- `before` — state from bars dated **strictly before** the event session. The only part usable as
  a model input.
- `day0` — the event session's own move. Reaction evidence and a classification label; **not
  actionable**, because the information arrived during that session.
- `forward` — returns from the session **after** day0, over 1/5/20/60 sessions. The only part fit
  to be an outcome label.

Per horizon: return, benchmark-excess return, max favourable and adverse excursion, max drawdown,
realised volatility, sessions to peak and trough, direction, and continuation of the day-0 move.

### 3.3 A known defect fixed

`tools/foundation/events.py` built its PSX reaction series with `source ILIKE 'Pakistan%'`, which
reads the exchange file and silently skips the **183,267 bars recovered from the Karachi listing** —
roughly half the stored PSX history. `brain.md` rule 130 named this line as the one to change at
the next rebuild. This is that rebuild. The predicate is now `a.currency = 'PKR'`, which selects
the market rather than the vendor, and the same rule is used by the reaction builder.

---

## 4. Point-in-time and leakage evidence

Run over the committed artifact, all 167 rows:

| Check | Result |
|---|---|
| Before-state dated on or after its event | **0** |
| Forward window starting at or before the event session | **0** |
| Window exit at or before its entry | **0** |

The distribution is the second kind of evidence — a corpus of only winners would be selection bias
wearing a label:

| Horizon | n | up | down | median | mean |
|---|---|---|---|---|---|
| 1d | 167 | 74 | 93 | −0.225% | +0.093% |
| 5d | 167 | 79 | 88 | −0.352% | −0.433% |
| 20d | 167 | 88 | 79 | +0.409% | +1.886% |
| 60d | 164 | 104 | 60 | +3.538% | +6.543% |

**20-session continuation of the day-0 move: 44.9%** — near coin-flip, which is what an honest
event corpus looks like. Median 20-day excess return over 92 benchmarked rows: **−0.197%**, i.e.
no abnormal return on average. Positive, negative and inconclusive cases are all present, and
three 60-day windows are reported open rather than shortened.

The private Karandaaz KSE-100 segment was **not read**. The PSX benchmark is an equal-weighted
return across stored PKR-quoted assets, so no committed artifact carries values derived from it.

---

## 5. Tests

| Suite | Result |
|---|---|
| Python | **1,019 passed**, 0 failed (998 before; 21 new) |
| Web | **466 passed**, 0 failed |
| `verify_durable.py` | 17 of 17 checksums, problems none, exit 0 |

`tests/test_milestone_c.py` pins the loader's provenance and slug stability, the reaction
arithmetic on synthetic series where the answer is known, the three leakage gates, the
distribution bounds, manifest/artifact agreement, the PSX predicate fix, and that no code path
opens the private cache.

**Omitted deliberately:** the full point-in-time feature build and dataset assembly
(`data-pit-features.yml`, `data-assemble.yml`). They run on a GitHub runner and the assembly needs
the sealed replay artifacts, which require an authenticated GitHub API this session does not have.
This is the §8 blocker, and re-running it locally was measured at roughly an hour in an earlier
phase without being able to complete the assembly afterwards.

---

## 6. Resource impact

| | Before | After |
|---|---|---|
| Database size | 384 MB of 500 MB | **385 MB** |
| `PriceSnapshot` rows | 1,097,638 | 1,097,638 (unchanged) |
| Rows written | — | 168 `Event` upserts, 119 `EventLink` upserts |
| New file artifacts | — | 41,185 bytes |

Deliberately **not** built: the cartesian product of 168 events × 616 assets × horizons, which was
estimated at roughly 197,000 rows and ~30 MB against 115 MB of headroom. It was rejected on
substance as well as storage — "every asset's move after an unrelated event" manufactures
causal-looking rows, which is the error `jobs/events.py` was written to avoid. Linkage follows the
corpus's own verified instrument instead.

No backfill, no resync, no migration, no deletion. Both writers are idempotent upserts.

---

## 7. Blocked sources and known gaps

**B7 — historical news. The material gap.** `News` holds 8,134 items across **37 days**
(2026-09-08 → 2026-10-15), because RSS serves only a recent window and no free source provides a
historical news archive at scale for either PSX or global coverage. Paid APIs and logged-in
scraping are out of scope by instruction.

*Impact:* a model cannot be trained on historical headline text, and news-derived features exist
only from 2026-09 forward.
*Safeguard:* the event corpus carries the historical catalyst layer instead — 168 verified, dated,
sourced events with measured reactions — and `lib/macroGateLocal.ts` already restricts news input
to a declared outlet list and fails open. Nothing presents thin news coverage as complete: the
manifest states the 37-day span.

**A7 / C5 — trading costs, borrow and spreads.** No free historical source for PSX borrow
availability or quoted spreads. No cost model is asserted anywhere, so no backtest can quietly
assume free execution; any future strategy claim must state its own assumptions.

**A6 / D3 — survivorship.** Measured and bounded, not removed: 63 of 127 S&P 500 removals since
2019 have no free daily history left, so the measurement is a lower bound by construction.

---

## 8. Brain-training readiness

**BLOCKED**, on one concrete dependency, not on a list.

What is ready: 1.1M validated bars with point-in-time factors; a walk-forward harness
(`walkforward.py`) and a determinism check; labelled outcomes with MFE/MAE and maturity flags; a
167-row event-reaction corpus with zero measured leakage; abstention already modelled in the rule
baseline, which stays separate from any learned model.

**The blocker:** the authoritative training dataset has not been rebuilt since the Milestone B and
C changes. The locally available assembly is **22,868 examples** in
`.cache/foundation/assembled_test3/` — a probe run, gitignored, built before
`dataQuality.basisBreakInWindow` existed and before the event layer. The authoritative build runs
as `data-pit-features.yml` → `data-assemble.yml` on a GitHub runner and needs the sealed replay
artifacts through an authenticated GitHub API that this session does not have.

Until that rebuild runs, any training would use a dataset that predates the quality flags Milestone
B added, which is exactly the "silently appears current" failure the brief forbids.

---

## 9. Git state

| | |
|---|---|
| Branch | `milestone-c-research-corpus` |
| Cut from | `ba06cd1a0702f20feed7d6f5e7e3cfd3663e0f62` (Milestone B, protected) |
| Working tree | changes staged in this milestone; the two acquisition-phase notes remain untracked and unmixed |
| Pushed | **not yet** — no remote state has been verified, so nothing here claims it was |

---

## 10. The single next step

**Run the dataset rebuild on CI** — `data-pit-features.yml` then `data-assemble.yml` — so the
training dataset carries `dataQuality.basisBreakInWindow`, the corrected PSX series and the event
layer, and promote the result from a scratch directory to a durable, checksummed artifact.

That is the whole of the next step. Nothing else is proposed.
