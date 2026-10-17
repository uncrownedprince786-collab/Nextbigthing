# Three workstreams, their contracts, and what the UI scope actually contains

Written 2026-10-17 at `75dfaeb`, with the weekly budget at 87% consumed. Its purpose is the one
the brief asks for before parallel work begins: **disjoint file ownership, the real API contract,
the screen-to-data mapping, and the bounded sync tasks** — so that three workers after the reset
do not discover each other's assumptions by breaking them.

It is a contract, not a plan. Where something is unknown it says so rather than estimating.

---

## 0. Two scope discoveries, made by inspection

These change the UI estimate and were not visible from the brief.

**There is no user.** `prisma/schema.prisma` contains **no `User`, `Account`, `Session`,
`Watchlist` or `Preference` model**, and `package.json` has **no auth dependency** — no
`next-auth`, no `@auth/*`, no `@clerk/*`, no `lucia`. Every page today is anonymous and read-only.

> **Screen 6 (Watchlist / Saved Research) and Screen 8 (Preferences) therefore require identity
> and per-user persistence that do not exist anywhere in this project.** That is a new subsystem —
> auth provider, session handling, user-scoped tables, migrations, and a privacy position for
> stored user data — not a screen. It is the single largest undeclared item in the UI workstream
> and it should be decided deliberately, not absorbed.
>
> A cheaper first cut that needs no identity: hold the watchlist in `localStorage` and keep
> Screen 6 device-local. That ships the flow, defers the subsystem, and is honest with the user
> about where their list lives.

**Nothing reads `ShadowPrediction`.** `lib/queries.ts` has 50 exported readers and none of them
touches it. **Screen 7 needs a new reader**, and it must respect the maturity rule already written
into the table: `outcomeLabel IS NULL` means *not matured*, never *no move*.

---

## 1. File ownership — disjoint by construction

| Workstream | Owns | Must not touch |
|---|---|---|
| **A — Brain** | `tools/research/**`, `tools/foundation/**`, `data/foundation/**` | `app/**`, `components/**`, `lib/queries.ts`, `jobs/**` |
| **B — Sync & ops** | `jobs/**`, `tools/daily_audit.py`, `tools/watchdog.py`, `.github/workflows/**`, `prisma/migrations/**` | `app/**`, `components/**`, `tools/research/**` |
| **C — UI** | `app/(next)/**` *(new isolated route group)*, `components/next/**` | `app/**` outside its group, `jobs/**`, `tools/**`, `prisma/schema.prisma` |

**Shared, change only by agreement:** `lib/queries.ts`, `prisma/schema.prisma`, `RESUME.md`,
`brain.md`.

**The rule that keeps C safe:** C adds routes under a **new route group** and never edits an
existing page. The live product keeps every current route, and rollback is deleting the group.

---

## 2. The API contract that already exists

`lib/queries.ts` exports **50** readers. The UI workstream consumes these; it does not write SQL
and does not add a parallel data layer.

```
getIndustries getIndustriesByMarket getIndustry getRankings getAllIndustriesByBasis
getProducts getProduct getAsset getAssetPrices getFreshness getEvents getEvent
getEventImpacts getEventWindows getMarketplace getProductMarketplace getHumanSignal
getFactor getSetup getAnalogs getUpcoming getEventCategoryHistory getProductRegions
getAccuracy getThesis getAttribution getRelevance getHorizons getInvestigation
getIntradayHealth getIntradayCoverage getPricedAssetsByIndustry getSourceHealth
getStories getRecentMarketNews getTopNews getAssetFreshness getMacroNews
getLiveQuoteFor getQuoteTarget getHealthReadings getCallRunFor getDecisionHistory
getAuditLog getLogbookSummary getTradeSummary getDecisionRuns getNewsReadOn
getDecisionBundle getLateColumns getDataStamp getDecisionRows
```

Existing routes: `/` `/stocks` `/psx` `/crypto` `/forex` `/commodities` `/asset/[symbol]`
`/industry/[slug]` `/events` `/event/[slug]` `/products` `/product/[slug]` `/marketplace`
`/logbook` `/methodology` `/privacy`. API: `/api/health` `/api/quote` `/api/revalidate`
`/api/signals`.

### Cross-workstream contracts

| Contract | Owner | Shape |
|---|---|---|
| Brain output | A | `model.json` + `manifest.json`: `modelVersion`, `modelSha256`, ordered `features`, `standardisation`, `status`, `productionApproved` |
| Prediction record | A/B | `ShadowPrediction`: `modelVersion`, `modelSha256`, `quality` ∈ ok/degraded/refused, `imputed[]`, `maturesAfter`, `approved` (false) |
| Freshness & provenance | B | `getFreshness`, `getDataStamp`, `getAssetFreshness`, `getSourceHealth`, `getHealthReadings`; staleness defined once in `lib/health.ts` |
| Unavailable data | all | render the absence; **never** substitute a default. `null` means *not known*, `0` means *measured zero* |

---

## 3. Screen → data mapping (all eight)

| # | Screen | Existing readers | Gap |
|---|---|---|---|
| 1 | Home / Overview | `getRankings`, `getDecisionRows`, `getUpcoming`, `getTopNews`, `getDataStamp`, `getFreshness` | none |
| 2 | Market Explorer | `getIndustriesByMarket`, `getPricedAssetsByIndustry`, `getAllIndustriesByBasis` | none |
| 3 | Asset Detail | `getAsset`, `getAssetPrices`, `getLiveQuoteFor`, `getAssetFreshness`, `getFactor`, `getAnalogs`, `getEvents` | none |
| 4 | Research / Decision | `getDecisionBundle`, `getSetup`, `getHorizons`, `getThesis`, `getAttribution`, `getCallRunFor` | **must suppress direction** — see §4 |
| 5 | News, Events, Catalysts | `getStories`, `getRecentMarketNews`, `getEvents`, `getEvent`, `getEventImpacts`, `getNewsReadOn`, `getUpcoming` | none |
| 6 | Watchlist / Saved | — | **identity + persistence do not exist** |
| 7 | Predictions & Outcomes | `getDecisionHistory`, `getAccuracy`, `getTradeSummary`, `getDecisionRuns` | **no `ShadowPrediction` reader** |
| 8 | Preferences & Status | `getHealthReadings`, `getSourceHealth`, `getIntradayHealth`, `getFreshness` | preferences need persistence (§0) |

**Six of eight screens are servable from readers that already exist and are already tested.**

### Build status — updated 2026-10-17 (screens 6 and 8)

| # | Screen | Route | State |
|---|---|---|---|
| 1 | Overview | `/preview` | **built, verified on real data** |
| 2 | Market Explorer | `/preview/markets`, `/preview/markets/[slug]` | **built, verified** |
| 3 | Asset Detail | `/preview/asset/[symbol]` | **built, verified** (Save button added for Screen 6) |
| 4 | Research Detail | `/preview/asset/[symbol]/research` | **built, verified** |
| 5 | News & Events | `/preview/news` | **built, verified** |
| 6 | Watchlist | `/preview/watchlist` | **built, verified** — `localStorage` only, no auth |
| 7 | Predictions | `/preview/predictions` | **built, verified** |
| 8 | Preferences / Status | `/preview/status` | **built, verified** — preferences are `localStorage` only |

**8 of 8 built.** Screen 6 holds the list in the browser (`app/preview/watchlist/storage.ts`),
resolves symbols through `/preview/api/watchlist` (existing readers `getAsset` +
`getAssetFreshness`, capped at 50 symbols for the pooler), and says on every surface that the list
is device-local. Screen 8 prints each source's own recorded status word (never recomputed from a
timestamp) beside market freshness, lane runs and intraday coverage; its two preference switches
are consumed by the watchlist (`recentFirst` orders it, `verboseProvenance` shows full source and
time inline). Build generates **65** pages (was 62); every pre-existing route is untouched and
rollback is deleting `app/preview/`.

---

## 4. Screen 4 is the one with a correctness rule, not a design question

There is **no validated directional model**. Four artifacts, four NO-GO, `productionApproved:
false` in every one.

So Screen 4 must show what is measured — **price structure, range, volatility state, event
context, and the rule engine's own published calls where the quality gate passed** — and must not
present a model direction. The existing site already does this correctly: the rule engine's calls
carry `gate`, `published` and `gateReasons`, and the home page says *"readings, not tips"*.

**The replacement must not quietly drop those qualifiers to look cleaner.** A validated model may
later add a direction to this screen; until one exists, the honest screen is the complete one.

---

## 5. Workstream B — bounded tasks, with dependencies

| # | Task | Depends on | Cost | Note |
|---|---|---|---|---|
| B1 | Fresh backup + restore rehearsal at current schema | pooler capacity | 1–2 h | rehearsal is **5 migrations behind**; highest value |
| B2 | Diagnose `cron products` (blocked ×2, empty ×1 / 104 slices) | B's DB access | 1–2 h | read `ChunkRun.note`; deferred product feature, real red lane |
| B3 | Classify the 8 stale sources: real failure vs legitimate slower cadence | — | 1–2 h | document expected intervals; some are weekly by nature |
| B4 | Schedule `daily_audit.py` for real and verify it ran | B1 | 1 h | **a scheduler-ready script is not a schedule**; add to a workflow and check its output |
| B5 | Aiven standby: repair or formally retire | owner decision | 1 h | it times out; "configured" ≠ "working" |
| B6 | Storage headroom: 493/500 MB | **owner authorisation** | 0.5 h | `VACUUM FULL "EventImpact"` returns ~57 MB |

**B1 → B4 is the only hard ordering.** B2, B3, B5 are independent.

---

## 6. Workstream A — widening measured (answer: no); next experiment registered

**Widening: measured 2026-10-17, answer no.** `BRAIN-CORPUS-COVERAGE-2026-10-17.md` measured
the corpora from the frozen artifacts: own-scope coverage is **37 of 617 instruments (6.00%)**,
6.81% of modelled rows carry observed own-scope context; widening from disk reaches only ~39
instruments (the SEC cache adds AAL and BWA, no crypto); and where the own-scope block's
contribution can be tested on populations that already have complete coverage it sits **below
the paired shuffled-control band**, so more rows of that kind cannot raise the floor. The 6–12 h
acquisition estimate is **not spent**.

**Recency: already tested and closed before that milestone was written.**
`tools/research/stationarity.py` (pre-registration `ef779c3`, result `dacaef5`, verdict in
`data/foundation/dataset/stationarity.json`): no shorter training window beats all-history in
at least 3 of 4 walk-forward years by more than the bootstrap half-width. The mechanism it
named is **prevalence shift** — 2025's class mix (DOWN 0.575 / UP 0.332) is the year the model
loses 0.2086 to majority, while it sits within ~0.03 of majority in the three balanced years.

**Registered experiment — executed 2026-10-17, verdict: fails.** Full spec was in
`BRAIN-CORPUS-COVERAGE-2026-10-17.md` §10, fixed before any run: **prevalence-adjusted scoring**,
a point-in-time label-shift prior correction on the all-history crypto-slice fits, with π_recent
from the trailing 365 decision dates of already-matured outcomes, one variant only, the same
four-year walk-forward and block bootstrap, rejection criteria (a)–(c). Run:
`tools/research/prevalence_adjustment.py`, artifact `data/foundation/dataset/prevalence_adjustment.json`.
**All three criteria fail, decisively.** (a) wins 0 of 4 years — the adjusted model is *worse*
than unadjusted in every year: −0.0018, −0.0172, −0.0009, −0.0014 over majority. (b) mean
advantage −0.0053 against mean half-width 0.0141. (c) 2025's advantage −0.0009 against its
half-width 0.0038 (no balanced year degraded, but 2025 did not improve). Real-minus-shuffled
corrected control is ≤ 0 in every year (−0.0015, −0.0165, −0.0028, −0.0000) — the real
prevalence signal is indistinguishable from a placebo. The mechanism: the trailing-365-matured
window lags the regime — in 2025, π_recent (0.478/0.087/0.435) was near-identical to π_train
(0.481/0.087/0.432), so the correction was ~zero exactly where the deficit was largest; in 2023
and 2026 it amplified a stale sell-off-era lean and cost accuracy. Label-shift theory assumes
`p(x|y)` is stable and only the prior moves; on this slice the discriminative relationship itself
moves. **Conclusion: the lean is not correctable from recently matured outcomes.**

**Registered question — cross-sectional ranking — executed 2026-10-17, verdict: fails.**
Full spec was registered in the docstring of `tools/research/cross_sectional_ranking.py` before
any run (target = the cross-sectional rank of `fwd20` within each decision date; ≥10 instruments
per date; the same four-year walk-forward with a 20-decision-date embargo; scores `momentum`,
`reversal`, `rankModel` (ridge on the 44 features), `directionModel` (the existing 3-class setup)
and a `random` control; the same 20-date-block bootstrap; rejection criteria (a)–(d) fixed
first). Artifact `data/foundation/dataset/cross_sectional_ranking.json`. **Result: negative.**
Best candidate `momentum` has mean IC > 0 in **2 of 4** years (2023 +0.0591, 2025 +0.0225; 2024
−0.0089, 2026 −0.0467) — criterion (a) needs 3. Its mean IC +0.0065 is far under the mean
half-width 0.0563 — (b) fails. Its long-short spread is positive in 4 of 4 years but small
(+8.48/+2.29/+1.32/+0.98%) and the `random` control's spread is ~0, so the spread reflects the
slice's own dispersion, not the score's ordering. It beats `directionModel` (`P(UP)−P(DOWN)`) on
IC in only **1 of 4** years — (d) fails; in fact `directionModel` beat price-only momentum in
3 of 4 years, so removing the directional threshold helped nothing. Every per-year half-width
exceeds its mean IC. **Conclusion: the 20-session cross-sectional form is also negative.**

**Registered question — the outcome horizon — executed 2026-10-18, verdict: fails.** Full spec
was registered in the docstring of `tools/research/horizon_experiment.py` before any run: the 5-session
target `label5` (UP/DOWN at ±1.0% `fwd5`, the 20-session ±2.0% scaled by `sqrt(5/20)`), the same
frozen slice and four-year walk-forward with a 20-decision-date embargo, the same seeds and verbatim
block bootstrap, the 20-session side embedded as a fidelity-guarded re-derivation (it reproduced
`stationarity.json`'s recorded numbers exactly), and criteria (a)-(c) fixed first. Artifact
`data/foundation/dataset/horizon_experiment.json`. **Result: negative.** h5 accuracy-over-majority
per year: −0.0290 / +0.0087 / −0.1164 / +0.0030; (a) beats majority in **2 of 4** years (needs 3);
(b) mean **−0.0334** vs mean half-width **0.0509**; (c) holds — h5 mean −0.0334 beats h20's −0.0612,
and h5 beats h20 in 3 of 4 years. The fit is still class-degenerate in two years and the
shuffled-label control is at or above h5 in three, so the apparent skill is not distinguishable from
a placebo. **Conclusion: the horizon change points the right way but does not rescue the directional
formulation; both horizons are negative.**

**Next registered question — the eligible set / target family.** With the window family (recency),
the prior-correction family (label-shift), the 20-session cross-sectional form, and now the 5-session
horizon all negative with mechanisms named, the remaining untouched dimension is **which rows are
eligible** and **what the target is a function of** (the frozen rows carry `fwd1`/`fwd5`/`fwd20` and
`mfe`/`mae` beside the class labels). Any such test must be registered in full (target, eligible set,
walk-forward, baselines, fixed rejection criteria) before a run — not a rerun of any completed
experiment, and not another horizon. Nothing here is promotable; every evaluation period is exposed.

---

## 7. What a release actually needs

Release is blocked on **evidence**, not engineering, for the brain. It is blocked on **work** for
the UI. The honest sequencing is: B1–B4 make operation routine; C builds the replacement against
existing readers; A continues as research with no release dependency; cutover happens when C
passes verification, with or without a validated brain — because the product is useful without a
direction and dishonest with an unvalidated one.

---

## 8. The `tests` lane is green — 2026-10-18 (CI failure closed)

The `tests` workflow had failed on every push since **2026-10-15T16:03Z**. **GitHub Actions
`tests` run #291 on commit `3c5952d` completed `success`**, both jobs and every step:
**`types and lint`** (type check, decision rules, **lint**) and **`brain logic`** (compile every
job, **brain logic tests**). Closing commits: `65754a6` and `3c5952d`.

**Root causes.** (1) `data/foundation/crisis_2008/*.csv` (22 series) plus `fdic_failures.json`
and `chronology.json` recorded sha256 values over Windows **CRLF** bytes while git stores and CI
checks out **LF**; LF is canonical (the generator writes `newline=""`), so the manifest's 24
digests were corrected and `*.csv` / `data/foundation/crisis_2008/*.json` pinned to `eol=lf`.
(2) Next 16's React Compiler lint rules fired on the preview client components' post-mount
`localStorage` reads — refactored to `useSyncExternalStore`; one justified `react-hooks/purity`
disable for the ISR server clock; `.cache/` added to the eslint ignores.

**Local gates (re-run this session).** Python **1,163 OK**; web **500/500**; `eslint .` **exit 0**;
`tsc --noEmit` clean; `next build` clean (all `/preview` routes and every production route present).

**Next closure actions.** (a) prepare and verify the controlled **cutover + rollback runbook**
(`UI-CUTOVER-RUNBOOK-2026-10-18.md`) — production cutover is *not* performed here; (b) complete the
**local sync checks** and, when the pooler has headroom, **B1 → B4**; (c) the explicit brain
**NO-GO → GO** pathway (§6). Release stays gated on **brain evidence**, not on build or test
health.
