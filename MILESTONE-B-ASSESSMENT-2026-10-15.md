> **SUPERSEDED 2026-10-15 — this was the read-only assessment that opened Milestone B.**
> Its findings were acted on; three of them changed shape once measured properly. The current
> state, with before/after counts, is `MILESTONE-B-CLOSEOUT-2026-10-15.md` and `brain.md` rule 142.
> Kept unchanged below for the record.

# Milestone B — read-only assessment, 2026-10-15

**Nothing was written.** One connection, `read_only = True`, aggregate queries only, plus local
file reads and two test runs. No ingestion, no backfill, no rebuild, no replay. This is the
measurement that must precede any Milestone B write, per `brain.md` rule 141.

Method and evidence: four read-only query rounds against the production database;
`tools/foundation/verify_durable.py`; `tests/test_foundation.py`; the manifests under
`data/foundation/`; and the field mapping in `jobs/psx.py:185-218`.

---

## Baseline measured today

| | Measured | At the 2026-10-16 backup |
|---|---|---|
| `PriceSnapshot` rows | 1,097,638 | 1,097,485 |
| Database size | 384 MB of 500 MB | ~380 MB |
| Assets | 616 | 616 |
| Distinct `(assetId, date)` pairs | 1,097,638 — equal to the row count | — |

The 153-row difference is the live cron lanes, which have kept running since the backup. The
acquisition artifacts are untouched: 17 of 17 durable checksums verify, 83 of 83 foundation tests
pass.

### Sources behind the price table

| Source | Bars | Assets | Range |
|---|---|---|---|
| Yahoo Finance | 604,946 | 315 | 2019-01-01 → 2026-10-14 |
| PSX daily closing file | 210,747 | 226 | 2018-01-01 → 2026-10-14 |
| Yahoo Finance Karachi listing (recovered) | 183,267 | 203 | 2019-01-01 → 2024-10-10 |
| Coinbase | 96,048 | 71 | 2018-11-04 → 2026-10-14 |
| Kraken | 2,405 | 4 | 2024-10-23 → 2026-10-14 |
| Yahoo Finance chart API | 225 | 28 | 2026-09-14 → 2026-09-24 |

---

## Findings, ranked

### F1 — 6,858 bars have a close outside their own high/low range (0.62% of the table)

A bar whose close sits outside `[low, high]` is internally inconsistent: every range, gap and
intraday-position feature computed from it is measuring something that did not happen.

| Source | Breaches | <1 bp | 1 bp–1% | 1–10% | >10% | Worst |
|---|---|---|---|---|---|---|
| Yahoo Finance | 4,176 | 961 | 3,150 | 62 | 3 | 21.77% |
| PSX daily closing file | 2,659 | 36 | 721 | 1,847 | 55 | 42.38% |
| Yahoo Finance chart API | 23 | 2 | 16 | 5 | 0 | 3.08% |
| Karachi listing (recovered) | **0** | | | | | |
| Coinbase / Kraken | **0** | | | | | |

Three separable defects hide inside that total:

- **PSX: the published range collapses.** 1,912 of the 2,659 breaches have `high = low` with a
  different close — the exchange's own file prints one value into both range columns and a close
  that disagrees with it. Across the whole PSX series 7,879 bars have `high = low`, so roughly a
  quarter of those are inconsistent. `jobs/psx.py:203-209` already maps a published `0` to `NULL`
  rather than a price, so these are genuine non-zero values, not a parsing fault. Worst case
  `JATM` 2019-06-12: high = low = 2.10, close = 2.99.
- **This is not legacy.** By year: 2018 175, 2019 355, 2020 250, 2021 83, 2022 178, 2023 178,
  **2024 763, 2025 514, 2026 163**. The live PSX lane is still writing these today, so a one-off
  cleaning pass would be undone by the next run.
- **Yahoo's breaches are almost entirely forex.** 4,150 of 4,176 are FX pairs against 49
  equities in 604,946 bars; 961 are under one basis point and are float noise. 70 FX breaches
  exceed 1%. Worst: `USDNOK` 2020-03-20, close 7.735 against a published low of 9.888.

`tools/foundation/verify_durable.py` already reports a further **370 OHLC violations in
`psx_delisted`** — the same defect in a durable artifact, flagged and not yet resolved.

### F2 — the two PSX bases are woven together, not joined at a seam

231 assets carry two sources. **None has disjoint date ranges**: all 203 PSX pairs interleave.

| Source flips per asset | Assets |
|---|---|
| 0 (single source) | 385 |
| 1–10 | 32 |
| 11–50 | 36 |
| 51–120 | 44 |
| **over 120** | **119** |

Mean flip rate among mixed assets is 5.25% of bars. `DLL` alternates 236 times across 1,483 bars.

Rule 130's anchor rule vetted each *inserted date* against the nearest stored date on both sides,
within 0.5%, and the 18,760 measured seams agreed. That proves each insertion point. It does not
measure what a 20-session factor window spanning ten basis switches inherits — and that window,
not the single date, is what every stored factor actually reads. **This is the largest unquantified
risk in the dataset and the one I would measure first.**

### F3 — one Saturday session: 2022-10-01, 171 PSX bars

PSX trades Monday to Friday. All 171 assets on that Saturday **also carry Friday 2022-09-30**, and
162 carry Monday 2022-10-03 — so it is an extra session between two intact ones, not a stand-in for
a missing one. It is the only weekend date in the PSX series (crypto weekends are expected and
correct: 27,425 Coinbase, 686 Kraken).

It is either a genuine special session the exchange held or a mis-stamped archive file. Deciding
needs the exchange calendar. Note that rule 141's four-way distinction — no trade, holiday, nothing
published, missing record — has no bucket for "a session that should not exist", so classifying
this correctly may mean adding one.

### F4 — the schema cannot hold a cross-source conflict

`PriceSnapshot`'s primary key is `(assetId, date)`; measured, 1,097,638 rows and 1,097,638 distinct
pairs. One source wins per date and the other is not stored. Rule 141's objective to "resolve
duplicates and conflicting prices between sources **without silently overwriting either**"
therefore cannot be met inside this table as designed.

That is a design decision, not a bug, and it is the owner's: either a side table of rejected or
alternate quotes, or an explicit acceptance that conflict evidence lives only in the foundation
artifacts. The 500 MB tier has ~116 MB of headroom, which bounds the first option.

### F5 — structural nulls that are the denominators for any new feature

1,719 PSX bars have no `open` (rows written before the column existed); 54,487 Yahoo bars have no
`volume` (forex, which has none to publish); 3,318 bars have zero volume. These are correct as
stored — the schema comment on `PriceSnapshot` explains why a blank is not back-filled with the
close — but any range or liquidity feature must state them rather than coerce them.

---

## Verified correct — do not "clean" these

- **`CL=F` 2020-04-20, close −37.63.** The single non-positive close in the database is the real
  negative WTI settlement. `DCOILWTICO` carries the same day. Both are correct data and a naive
  "close must be positive" rule would destroy them.
- **No look-ahead found on the paths checked.** 0 future-dated bars. 0 of 4,250 `AssetAnalog` rows
  computed before their own `periodEnd`.
- **Macro point-in-time is in good order.** Every row carries `availableAt`; 32 series with
  declared availability lags; 10 revision-tracked from ALFRED vintages with `leftCensored` flags
  on observations older than the first snapshot.
- **`USREC` is correctly quarantined.** The NBER recession flag is an ex-post label declared months
  after the fact — the most dangerous look-ahead series a dataset can carry. It is deliberately
  excluded from the PIT feature set (`tools/foundation/macro_pit.py:125`) and a test asserts its
  absence (`tests/test_foundation.py:843`).
- **Freshness is clean.** 0 of 616 assets are stale beyond 7 days, across all five asset types.

---

## Proposed Milestone B sequence, against rule 141's four objectives

Each step measures before it writes, and nothing writes without a verified backup and a stated
row-level effect, rollback path and storage cost.

1. **Basis integrity across windows (objective 3, F2).** Measure the return distribution of every
   window that spans a source flip against windows that do not, per asset. Decide from the
   measurement whether the woven series is usable as one series, needs a per-window flag like the
   existing `dataQuality.unadjustedActionInWindow`, or needs one basis chosen per asset.
2. **Containment classification (objective 1, F1).** Classify the 6,858 breaches into: float noise
   (<1 bp), collapsed-range PSX rows, and materially wrong bars. Fix the live PSX lane first so the
   set stops growing, then flag — not overwrite — the historical rows, consistent with rule 130.
3. **The Saturday (objective 1, F3).** Resolve 2022-10-01 against the exchange calendar and
   classify it with evidence.
4. **Conflict representation (objective 2, F4).** Owner decision before any schema change.
5. **Point-in-time re-verification (objective 4).** Extend the per-reader bound tests of rule 129
   to any reader added since, and re-run `tools/determinism_check.py` on a fresh stratified sample.

---

## What needs the owner before I go further

- **F4** is a schema decision and costs storage on a tier with ~116 MB free.
- **Step 2 changes a live ingestion lane**, which is a production write path.
- Everything in steps 1, 3 and 5 is measurement and can proceed read-only.
