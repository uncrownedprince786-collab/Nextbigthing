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

### Build status — updated 2026-10-17 (`a0c56d3`)

| # | Screen | Route | State |
|---|---|---|---|
| 1 | Overview | `/preview` | **built, verified on real data** |
| 2 | Market Explorer | `/preview/markets`, `/preview/markets/[slug]` | **built, verified** |
| 3 | Asset Detail | `/preview/asset/[symbol]` | **built** |
| 4 | Research Detail | `/preview/asset/[symbol]/research` | **built** |
| 5 | News & Events | `/preview/news` | **built, verified** |
| 6 | Watchlist | — | not started — `localStorage` only, no auth |
| 7 | Predictions | `/preview/predictions` | **built, verified** |
| 8 | Preferences / Status | — | not started |

**6 of 8 built.** Build generates **62** pages (was 60); every pre-existing route is untouched and
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

## 6. Workstream A — next milestone, unchanged

Measure whether widening the event/press/reaction corpora past the **~37 of 617** instruments they
name raises the in-sample separation floor above **+0.0332** by more than the shuffled-control
band — **before** registering any candidate. 6–12 h active.

Then, and only if that clears: register a formulation with a decision-shaped target. The
walk-forward evidence says the 20-session three-class call is not supported; **cross-sectional
ranking** (which names move most, relative to peers) is the alternative with the strongest prior,
because it does not require an absolute directional threshold at all.

---

## 7. What a release actually needs

Release is blocked on **evidence**, not engineering, for the brain. It is blocked on **work** for
the UI. The honest sequencing is: B1–B4 make operation routine; C builds the replacement against
existing readers; A continues as research with no release dependency; cutover happens when C
passes verification, with or without a validated brain — because the product is useful without a
direction and dishonest with an unvalidated one.
