> **SUPERSEDED 2026-10-16 — read this first.**
>
> This note was the read-only inventory of 2026-10-15 and its figures are no longer current. Since
> it was written: 80,162 PSX bars were recovered from the exchange archive; the benchmark, SBP,
> KIBOR, delisted and KSE-100 series were acquired; and the frozen market/macro acquisition phase
> closed at **14 of 14 targets**.
>
> Current state lives in `brain.md` rules 130–140, the manifest
> `data/foundation/acquisition/manifest.json` (`acquisition-manifest-v7-final`) and the per-target
> ledger `data/foundation/acquisition/target_ledger.json`. The one dataset held outside the
> repository, by design, is the KSE-100 2018–2021 segment in `.cache/acquire/karandaaz/`.
>
> Latest verified backup: `nbt-private/backup-2026-10-16T0600Z-acquisition-complete/`.
>
> Kept unchanged below for the record.

# NextBigThing — data inventory and coverage baseline

Measured 2026-10-14T20:35Z (local 2026-10-15). **Read-only**: no writes, no ingestion, no
backfill, no rebuild, no replay. Database read in one connection with aggregate queries only.

Evidence: `data/foundation/coverage/gaps.json` (2026-10-14T19:56:38Z), `psx_backfill/{plan,
integration_verified,seams}.json`, `price_verification/{unadjusted_actions,psx_action_factors,
quarantine_delta}.json`, `survivorship/report.json`, `macro/manifest.json`, `recovery-manifest.json`,
`brain.md` rules 115/129/130, `ChunkRun` lane log, live aggregates over `PriceSnapshot`.

**Fingerprint check.** `gaps.json` reports 1,017,296 stored bars; the live count today is
1,017,296 — identical, so the artifact is current and was reused rather than recomputed.

---

## 1. Headline metrics

| Metric | Value | Denominator |
|---|---|---|
| Universe coverage (registered universe) | **616 / 616 = 100.0%** | every asset in the `Asset` registry has ≥1 usable bar |
| Universe coverage (named target list) | **11 / 17 = 64.7%** | §2 — 6 named targets are absent from the system |
| Historical time coverage (prices) | **1,017,296 / 1,088,179 = 93.49%** | market session dates inside each asset's own stored range |
| Historical time coverage (macro) | **58,845 / 60,827 = 96.7%** | weekday/period count per series; ~100% against publication calendars |
| Overall target coverage (combined) | **1,076,141 / 1,149,006 = 93.66%** | sum of the two above |
| Freshness / sync coverage | **616 / 616 assets = 100.0%**, **4 / 4 price lanes** | each asset's newest bar within its lane's interval (96h; crypto 48h) |

Database **374 MB of the 500 MB tier** (126 MB headroom). `PriceSnapshot` 1,017,296 rows;
`IntradayBar` 115,483.

---

## 2. Named target reconciliation — VERIFIED

| Named target | Status | In the system as | Earliest | Latest |
|---|---|---|---|---|
| PSX individual stocks | **PRESENT** | 226 assets, `stock`/PKR | 2019-01-01 | 2026-10-14 |
| PSX delisted / renamed | **ABSENT** | 0 assets end before today | — | — |
| KSE-100 index | **ABSENT** | no index asset | — | — |
| Global equities | **PRESENT** | 272 US stocks + 8 ETFs | 2019-01-02 | 2026-10-13 |
| S&P 500 index | **ABSENT** | no `^GSPC`, no `SPY` | — | — |
| VIX | **PARTIAL** | `VIXCLS` FRED CSV, not a price asset | 2010-01-04 | 2026-10-12 |
| Forex | **PRESENT** | 27 pairs incl. USDPKR | 2019-01-01 | 2026-10-13 |
| DXY (ICE dollar index) | **ABSENT** | — | — | — |
| Broad USD index | **PRESENT** | `DTWEXBGS` FRED CSV | 2010-01-04 | 2026-10-09 |
| Gold — futures | **PRESENT** | `GC=F` continuous, + `GLD`/`IAU` ETFs | 2019-01-02 | 2026-10-13 |
| Gold — spot (XAU) | **ABSENT** | — | — | — |
| Brent | **PRESENT** | `BZ=F` continuous future | 2019-01-02 | 2026-10-13 |
| WTI — futures | **PRESENT** | `CL=F` continuous future | 2019-01-02 | 2026-10-13 |
| WTI — spot | **PRESENT** | `DCOILWTICO` FRED CSV | 2010-01-04 | 2026-10-06 |
| Crypto / Bitcoin | **PRESENT** | 75 assets; `btc-bitcoin` 2,901 bars | 2018-11-04 | 2026-10-13 |
| US 10Y / Fed Funds | **PRESENT** | `DGS10`, `DFF` FRED CSVs | 2010-01-04 | 2026-10-12 |
| KIBOR / SBP policy rate | **ABSENT** | no Pakistan rate series anywhere | — | — |

**Present 11, absent 6.** The absent six are not gaps in collection — they were never in the
frozen universe (`brain.md`, "Industries and assets" and "Pakistan Stock Exchange": 9 global
industries × 10 assets, 8 PSX sectors × 70 symbols, plus FX, commodities, ETFs and crypto). No
index, no spot metal, and no Pakistani rate series has ever been defined as a target.

Note on spot vs futures, as asked: `GC=F`, `CL=F`, `BZ=F`, `SI=F`, `HG=F`, `NG=F`, `PA=F`, `PL=F`
are **continuous futures series from Yahoo**, not individual dated contracts and not spot. The only
spot commodity series in the system is `DCOILWTICO` (WTI), in the macro files.

---

## 3. Per-class inventory — VERIFIED

| Class | Assets | With data | Daily data | Bars | Earliest | Latest | Start after 2019-01-31 | Source |
|---|---:|---:|---:|---:|---|---|---:|---|
| stock / PKR (PSX) | 226 | 226 | 226 | 313,852 | 2019-01-01 | 2026-10-14 | 48 | PSX closing file + Yahoo Karachi |
| stock / USD | 272 | 272 | 272 | 519,075 | 2019-01-02 | 2026-10-13 | 26 | Yahoo Finance |
| etf | 8 | 8 | 8 | 15,648 | 2019-01-02 | 2026-10-13 | 0 | Yahoo Finance |
| commodity | 8 | 8 | 8 | 15,667 | 2019-01-02 | 2026-10-13 | 0 | Yahoo Finance |
| forex | 27 | 27 | 27 | 54,676 | 2019-01-01 | 2026-10-13 | 0 | Yahoo Finance |
| crypto | 75 | 75 | 75 | 98,378 | 2018-11-04 | 2026-10-13 | 70 | Coinbase (71), Kraken (4) |
| **Total** | **616** | **616** | **616** | **1,017,296** | 2018-11-04 | 2026-10-14 | 144 | |
| macro (files) | 32 series | 32 | 11 daily | 58,845 obs | 2010-01-01 | 2026-10-13 | — | FRED CSV |
| intraday | 107 assets | — | 5-min bars | 115,483 | 2026-10-07 | 2026-10-14 | — | Yahoo chart API |

**Per source:** Yahoo Finance 604,841 (315 assets) · Yahoo Karachi listing 183,267 (203) · PSX
closing file 130,585 (226) · Coinbase 95,977 (71) · Kraken 2,401 (4) · Yahoo chart API 225 (28).

### Data-quality measurements

- **Duplicates: 0, structurally.** `PriceSnapshot` is keyed `(assetId, date)`; a duplicate cannot exist.
- **Invalid OHLC (high < low): 0** across all 1,017,296 rows.
- **Non-positive closes: 1** — `CL=F` on 2020-04-20, close −37.63, low −40.32. **This is correct
  history**, the day WTI futures settled negative. Not a defect; do not "fix" it.
- **Bars with a missing OHLC field: 178** (all `stock`), the nullable legacy columns described on
  the `PriceSnapshot` model — a close with no range, not a fabricated range.
- **Basis-incompatible records: 0 integrated.** 37,617 in-range bars were withheld for exactly
  this reason (§5). 18,760 provider seams measured, **0 where the two providers price the same
  date differently** (`psx_backfill/seams.json`).
- **Quarantined history:** 53,571 asset-sessions excluded by the corporate-action window rule and
  4,614 with no analog block (`quarantine_delta.json`); 237 action dates across 150 assets.

---

## 4. How each percentage was calculated

1. **Universe coverage** = assets with ≥1 usable bar ÷ assets in the registry = 616/616. The
   second figure is against the 17 named targets in the request, counted in §2.
2. **Historical time coverage** = stored bars ÷ market session dates falling inside each asset's
   own stored range, summed over assets (`gaps.json` `byMarket.sessions` vs `.stored`). Pre-listing
   and post-coverage dates are excluded by construction, so a late listing is not counted missing.
   PSX 313,852/384,676 · US 519,075/519,075 · crypto 98,378/98,382 · fx 54,676/54,702 ·
   futures+ETF 31,315/31,344.
3. **Overall target coverage** = the same ratio aggregated, plus macro observations against their
   per-frequency denominators (business days for daily, weeks, months, quarters).
4. **Freshness** = assets whose newest bar is within the interval `jobs/audit.py` defines for that
   source: 96h for Yahoo US/commodity/FX and the PSX file, 48h for crypto. Measured gaps at
   2026-10-14T20:35Z: Yahoo 44.6h, PSX 20.6h, Coinbase 44.6h, Kraken 44.6h — all inside.

**Calendar caveat, stated plainly.** The market calendar in `gaps.json` is derived from the data
("a date is a session when any asset of that market has a bar"). The independent check is
`calendarCompleteness`, which divides session dates by *weekdays elapsed*: PSX now reads
0.935–0.958 per year and US 0.956–0.966 — both consistent with real exchange calendars (~250 of
261 weekdays). Before the 2026-10-14 PSX recovery, PSX read 0.046–0.05, which is why the old
per-asset PSX coverage of 0.983 was meaningless. The denominator is now credible; it was not.

---

## 5. PSX recovery reconciliation — VERIFIED against artifacts

| Claim | Verified | Evidence |
|---|---|---|
| 183,267 Yahoo Karachi bars integrated | **YES** | `perSource` shows 183,267 rows / 203 assets under `Yahoo Finance Karachi listing` |
| 38,246 withheld across 69 symbols | **YES** | `plan_full.json`: 38,221 basis-diverged + 25 split-between-anchors; 37,617 of them fall inside a symbol's stored range |
| 23 symbols HTTP 404 | **YES** | `fetch_state.json` `notServed`, each confirmed by a direct status request |
| Existing exchange history preserved | **YES** | 130,585 exchange bars before and now; 0 lost, 0 closes changed |

Withheld bars are **not** counted as recovered. Their symbols are **not** counted as missing
either: all 69 hold full post-2024 history and partial earlier history — they contribute 37,617
gaps, not 69 empty series.

### Every PSX gap, attributed (sums to exactly the 70,824 in `gaps.json`)

| Reason | Bars |
|---|---:|
| Provider served a valid bar, basis diverged → withheld | 37,617 |
| Provider bar rejected by validation (flat zero-volume pad, incomplete OHLC, disordered) | 32,519 |
| Provider does not list the symbol (the 23 404s) | 662 |
| Neither provider covers the date | 26 |
| **Total** | **70,824** |

---

## 6. Residual gap table

| Asset class / series | Target | Usable | Coverage | Missing bars | Last obs. | Reason | Minimum next action |
|---|---:|---:|---:|---:|---|---|---|
| PSX stocks | 226 | 226 | 81.6% | 70,824 | 2026-10-14 | mixed, see §5 | none without a raw-price PSX provider |
| — basis-withheld subset | 69 | 69 | partial | 37,617 | 2026-10-14 | corporate-action / price-basis mismatch | de-adjust via a sourced split factor, or find a raw provider; **needs authorization** |
| — validation-rejected subset | 203 | 203 | partial | 32,519 | 2026-10-14 | data-quality rejection (provider padding) | none — rejecting these is correct |
| — unlisted-at-provider subset | 23 | 23 | partial | 662 | 2026-10-14 | source unavailable (HTTP 404) | none from approved free sources |
| US stocks | 272 | 272 | 100.0% | 0 | 2026-10-13 | — | none |
| ETFs | 8 | 8 | 99.9%* | 29* | 2026-10-13 | isolated gaps | none |
| Commodities (futures) | 8 | 8 | 99.9%* | 29* | 2026-10-13 | isolated gaps | none |
| Forex | 27 | 27 | 99.95% | 26 | 2026-10-13 | 24 quorum-thin | none |
| Crypto | 75 | 75 | 99.996% | 4 | 2026-10-13 | isolated gaps | none |
| Macro (32 FRED series) | 32 | 32 | ~100% | 0 | 2026-10-13 | holiday non-publication | none |
| **S&P 500 index** | 1 | 0 | 0% | all | — | not in frozen scope | add `^GSPC` to the seed — **scope decision** |
| **KSE-100 index** | 1 | 0 | 0% | all | — | not in frozen scope | scope decision |
| **DXY** | 1 | 0 | 0% | all | — | not in frozen scope | scope decision |
| **Gold spot** | 1 | 0 | 0% | all | — | not in frozen scope | scope decision |
| **KIBOR / SBP rate** | 2 | 0 | 0% | all | — | not in frozen scope; no verified free source | source evaluation first |
| **PSX delisted / renamed** | unknown | 0 | **UNMEASURABLE** | unknown | — | no delisting registry for PSX | obtain a delisting list; denominator does not exist today |
| US delisted (survivorship) | 124 | 0 | 0% | — | — | survivor-only universe | 61 have ≥1y recoverable history |

\* ETF and commodity are reported together in `gaps.json` as `us-futures-and-etf` (16 assets,
31,315/31,344 stored, 29 gaps); the split by class is not separately measured.

### UNMEASURABLE figures

- **PSX delisted/renamed coverage.** No delisting or symbol-change registry exists in the project
  or from any verified free source, so there is no denominator. What is needed: an authoritative
  PSX delisting/rename list with effective dates.
- **ETF vs commodity gap split.** `gaps.json` groups them; separating them needs a re-run, which
  this task forbids.
- **Sync history before the `ChunkRun` retention window.** The lane log holds recent runs only;
  "latest successful sync" is verified, long-run reliability is not.

---

## 7. Resource constraints

- Supabase **374 MB / 500 MB** — 126 MB headroom. The 2026-10-14 recovery added ~38 MB.
- Session pooler admits **15 clients**; one database-intensive job at a time (brain.md rule 129).
- GitHub API unauthenticated (60 req/h); no `gh` CLI. Sealed CI artifacts cannot be downloaded,
  so the dataset assembly cannot be rebuilt from this machine.
- `cron mirror` has no recent `ChunkRun` row; the standby refresh remains the known IPv4/IPv6
  issue from the Phase 2 notes. Non-price lanes with failures: Reddit 0/3 ok, Wikipedia 0/3 ok,
  Google Trends 1/3 (last ok 2026-10-12).

---

## 8. Three conclusions

**What percentage of the defined data target has actually been achieved?**
Against the project's own frozen universe: **93.5% of expected price observations** (1,017,296 of
1,088,179) and **100% of instruments** (616 of 616 hold usable daily data), with macro at ~100%
against publication calendars — **93.66% combined**. Against the seventeen targets named in this
request: **64.7% of series exist at all** (11 of 17), because six were never in scope.

**What remains missing or unusable, by asset class?**
Almost all of it is PSX: 70,824 bars, of which 37,617 are withheld over a price-basis mismatch,
32,519 are provider padding correctly rejected, 662 belong to 23 symbols the provider does not
list, and 26 are covered by nobody. Every other price class is at 99.9%+ or exact. Outside the
price classes: no index series (S&P 500, KSE-100, DXY), no spot gold, no Pakistani rate series,
and no delisted securities in any market — the universe is survivor-only, with a measured
survivorship bias of −182 pp median across 61 removed S&P names.

**The single highest-priority next recovery task.**
Resolve the **37,617 basis-withheld PSX bars across 69 symbols**. It is the largest recoverable
block by an order of magnitude, the data is already fetched and staged, the blocker is a known and
bounded one — the exchange file is raw and the provider's is split-adjusted — and ten split factors
are already confirmed against the provider's own calendar. It needs an explicit decision on whether
de-adjusting a sourced factor is acceptable, because it writes a derived price. **Not started.**
