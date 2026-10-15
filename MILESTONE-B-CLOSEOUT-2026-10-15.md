# Milestone B — closeout, 2026-10-15

## Verdict: **MILESTONE B COMPLETE**

All applicable acceptance criteria pass. One material exception is explicitly bounded with
evidence rather than closed, and is stated in full below.

Scope was the four objectives of `brain.md` rule 141: provenance and timestamps, cross-source
conflicts, the raw-versus-adjusted basis, and point-in-time correctness. Nothing was trained,
no feature was engineered, and the research corpus was not touched.

---

## 1. Database and backup state

| | Before | After |
|---|---|---|
| `PriceSnapshot` rows | 1,097,638 | 1,097,638 |
| Database size | 384 MB of 500 MB | 384 MB of 500 MB |
| Assets | 616 | 616 |
| Rows inserted | — | **0** |
| Rows deleted | — | **0** |
| Rows updated | — | **216** |

**Backup verified before any write**, as the constraint required:
`C:\Users\NEW TECH\nbt-private\backup-2026-10-16T0600Z-acquisition-complete\` — 44 table dumps,
**0 corrupt** under `gzip -t`, and the `PriceSnapshot` dump holds 1,097,485 rows. No new backup was
created: the single write is 216 rows with its own key-level rollback file, which is a smaller and
more precise restore path than a fresh dump.

One correction to the existing record: that backup's `backup_manifest.json` reports
`priceSnapshotRows: 1097458`; the dump itself contains **1,097,485**. The manifest figure is a
transposition. The dump is correct and is what a restore would use.

---

## 2. Priority 1 — F2, PSX source and basis switching

### What the records actually are

203 assets carry two price bases: the exchange's own daily file (raw) and the recovered Yahoo
Karachi listing (split-adjusted). They **interleave rather than abut** — 0 of 203 have disjoint
date ranges.

| Source changes per asset | Assets |
|---|---|
| 0 (single source) | 385 |
| 1–10 | 32 |
| 11–50 | 36 |
| 51–120 | 44 |
| **over 120** | **119** |

`DLL` alternates 236 times across 1,483 bars. **188,528 of 389,494 20-session windows (48.4%)
span a basis change.** Excluding them would have quarantined half the PSX history.

### The measurement, and why insertion-date agreement was not relied on

The instruction was explicit that 0.5% agreement at the insertion date does not prove a window.
It was not used. Instead the test is the exchange's own daily price band, **derived from the
stored data, not from documentation**: over same-source transitions, **10 of 71,816** moves on a
prior close under Rs 10 exceed Rs 1.00 (0.01%), and **253 of 299,074** moves at or above Rs 10
exceed 10% (0.08%). The band is the greater of 10% and Rs 1.00, and it is a hard ceiling in the
data.

A cross-basis step is then either one a single legitimate session could have made, or it is not.

| | Transitions | Out of band | Rate |
|---|---|---|---|
| **Across a basis change** | 22,898 | **5** | **0.022%** |
| Within one source | 370,890 | 263 | 0.071% |

**Joining the two bases is three times cleaner than an ordinary session**, because the anchor rule
vetted the joins at insert time and nothing vetted the rest. The basis risk is real to ask about
and small when measured.

A per-asset robust z-score was tried first and rejected as the decision rule: it flagged `AMTEX`
2024-06-03 at z=56 as the worst step in the data. That move is five consecutive sessions closing
exactly **Rs 1.00** higher, each at the day's high — a limit-up run on a sub-rupee scrip, where
the band is absolute rather than proportional. `CHBL` and `DBCI` on the same date are the same
thing. A statistic against an asset's own history cannot tell a real limit move from a basis
artefact; a rule derived from how the market works can.

### The policy

Deterministic and source-aware, in the codebase's existing shape:

- `tools/foundation/basis_transitions.py` writes
  `data/foundation/price_verification/basis_transitions.json` — **every one of the 22,898 joins
  with both sides' close and source**, which is how the provenance of a conflict survives a
  primary key that permits one observation per asset-date.
- `actions.basis_breaks()` is the single reader, mirroring the existing `unadjusted_windows()`.
- `assemble.py` carries `dataQuality.basisBreakInWindow` beside the existing
  `unadjustedActionInWindow`.

**Windows excluded: 96 of 389,494 (0.0246%)**, not the 188,528 that merely span a change. Valid
history is preserved; only windows spanning a step no session could produce are excluded.

The 5 exceptions — `POL`, `KOHE`, `HMB`, `GCIL`, `NPL` — are all downward and all just over the
band (Rs 0.04 to Rs 5.78 over), consistent with ex-dividend adjustments. They are excluded on the
uncertainty rather than on a diagnosis.

---

## 3. Priority 2 — F1, OHLC validation and live ingestion

### Classification by source and root cause

6,858 stored bars have a close outside their own range. The ledger is
`data/foundation/price_verification/ohlc_quarantine.json` and it **reconciles exactly**:

| Class | Rows | Expected | Cause |
|---|---|---|---|
| `incoherent-range`, Yahoo FX | 3,797 | yes | the FX close is a different snapshot from the range; ~8% of sessions, median 3.6 bp |
| `collapsed-range`, PSX | 1,912 | yes | the archive prints one value into both range columns |
| `incoherent-range`, PSX | **747** | **no** | see "Remaining exception" |
| `collapsed-range`, Yahoo FX | 330 | yes | an FX session quoted at one price with a differing close |
| `incoherent-range`, chart API FX | 23 | yes | same FX snapshot property |
| `float-noise`, Yahoo equities | **49** | yes | all at ~1.7e-15; 47 below one ULP |

**6,809 quarantined + 49 float representation = 6,858**, the exact figure the database comparison
returns. The 47 sub-ULP rows are visible to Postgres and not to a parsed double; they are counted
rather than quietly dropped, which is what makes the total reconcile instead of approximate.

Three different facts, so **three expectations rather than one universal tolerance**. Yahoo's
equity feed is coherent to the last bit across 604,946 rows, so a breach there would be new and is
flagged `unexpected`; Yahoo's FX and the PSX collapsed range are known properties, counted and not
alarming.

### No valid close was changed

`jobs/ohlc.py` returns the range and never the close — the close is deliberately not a return
value of `guard()`. A bar with an untrustworthy range is stored with its close and a null range,
which is what `None` has always meant on this table (`_store_frame` has nulled Yahoo's placeholder
FX volume for the same reason). Confirmed live: `CL=F` 2020-04-20, close **−37.63** inside a range
of −40.32 to 17.85, classifies `ok` and passes through untouched.

### The ingestion fix

The defect was not legacy — **763 breaches in 2024, 514 in 2025, 163 in 2026**. All three write
paths now run the guard:

- `jobs/psx.py` — the lane still producing them
- `jobs/prices.py _store_frame` — the Yahoo path
- `jobs/prices.py chart_repair` — which had neither this rule nor the FX volume rule

Each reports a count of dropped ranges, so a bad range can never be reintroduced *silently*.

Prevention verified on the exact shapes found:

| Input | Verdict | Result |
|---|---|---|
| PSX collapsed range (`JATM` 2019-06-12) | `collapsed-range` | close kept, range dropped |
| Yahoo FX incoherent (`USDNOK` 2020-03-20) | `incoherent-range` | close kept, range dropped |
| A good bar | `ok` | stored as published |
| Negative oil settlement (`CL=F` 2020-04-20) | `ok` | stored as published |

**No existing row was edited for F1.** The raw history stands and the quarantine is a fact a
reader looks up, consistent with rule 130's "flagged rather than dropped".

---

## 4. Priority 3 — F3, the Saturday bars

Settled against the exchange itself, not inferred.

The archive answers **HTTP 200** at `https://dps.psx.com.pk/download/mkt_summary/2022-10-01.Z` and
every one of the 668 rows inside is stamped **`30SEP2022`**. Sunday 2022-10-02 returns 404, as
weekends normally do.

| Evidence | Result |
|---|---|
| Symbols holding both 2022-09-30 and 2022-10-01 | 25 |
| Of those with byte-identical OHLCV | **25 (100%)** |
| Dates in the whole PSX history where every shared symbol repeats the previous date | **1** — this one |
| Non-crypto weekend bars in the table | 171, all on this date |

**Root cause:** the lane keyed each bar by the date whose URL it requested rather than the session
date the file stamps on its own rows.

**Fix:** `jobs/psx.py file_session_date()` reads the stamp and `read_day()` returns `None` on a
mismatch — the same answer it already gives for a closed market. Verified against the live archive:
2022-09-30 reads 668 symbols, **2022-10-01 is refused**, 2022-10-03 reads 655.

**Nothing was deleted.** The 171 rows are preserved as source evidence, and measurement shows
**0 of them pass `session_bar()`** — the canonical session filter already excludes them because
they fall on a Saturday (rule 95). The 31 bars that do pass on that date are crypto, which trades
weekends correctly. Recorded with its rollback in
`data/foundation/psx_complete/misdated_sessions.json`.

---

## 5. Priority 4 — F4 conflicts and F5 structural nulls

**Conflicts are preserved in existing sidecar form, and no schema migration was made.** The
primary key `(assetId, date)` still permits one canonical observation per asset-date — verified,
1,097,638 rows and 1,097,638 distinct pairs — so the conflict evidence lives beside it:

- `basis_transitions.json` — all 22,898 realised joins with both sides' close and source (new)
- `psx_backfill/plan.json` — 38,246 bars held back where the bases diverge (`basisDivergedAtAnchor`
  38,221, `splitBetweenAnchors` 25)
- `.cache/psx_backfill/staged/` — 203 per-symbol files of the withheld provider data, mirrored in
  the backup's `staging/psx_backfill/staged`

**Missing stays missing.** The real defect here was downstream, not in the data:

- `jobs/horizons.py` filled an absent high and low **with the close** at two call sites, which
  reads as a session that never moved. Removed. `true_range()` and `pivots()` now skip bars
  without a range via a shared `has_range()`, which is what `true_range`'s own docstring already
  promised: *"None when there is not enough history, never a default."* This mattered more after
  the F1 fix, because the fabrication would have reinvented precisely the ranges `ohlc.py`
  withholds.
- 712 bars with no range, 1,719 with no open and 54,487 with no volume are left as nulls.

### The one database write

216 currency-pair bars carried `volume = 0`. FX has no consolidated tape, so that 0 is a
placeholder and not a measurement — `_store_frame` has always nulled it, and `chart_repair` did
not. The project's own comment names the three readers that take it as real: `avg_volume` in
`jobs/rank.py`, `write_rising`, and `VOLUME_CONFIRMS_AT` in `lib/decision.ts`.

| | |
|---|---|
| Rows | 216 — 27 pairs × 8 sessions, 2026-09-14 to 2026-09-24 |
| Source | `Yahoo Finance chart API` only (the tool refuses to run if that widens) |
| Change | `volume` 0 → NULL; close, range and source untouched |
| Result | 216 updated, **0 fabricated zeros remaining** |
| Rollback | `data/foundation/price_verification/forex_volume_rollback.json` — every key with its prior value |

Zero-volume bars on other asset types — 1,966 commodity, 1,136 equity — are **real sessions that
did not trade** and were deliberately left alone.

---

## 6. Point-in-time integrity

Re-verified, nothing regressed: **0** future-dated bars, **0** of 4,250 `AssetAnalog` rows computed
before their own `periodEnd`, every macro row carries `availableAt`, and `USREC` — the NBER
ex-post recession label, the most dangerous look-ahead series a dataset can hold — remains
excluded from the PIT feature set with a test asserting its absence.

---

## 7. Tests and validators

Run once after the fixes, as instructed.

| | Result |
|---|---|
| Python suite | **998 passed**, 0 failed (971 before; 27 new) |
| Web suite | **466 passed**, 0 failed |
| `verify_durable.py` | **17 of 17 checksums ok, problems: none, exit 0** |

The validator previously exited 1 on two items, both now resolved correctly rather than silenced:

- `DCOILWTICO: 1 non-positive value` was **WTI settling at −37.63 on 2020-04-20** — a real event
  the validator was calling a defect. It is named with its exact count, so that row passes and a
  second non-positive value in the same file still fails.
- `psx_delisted: 370 OHLC violations` is the same F1 defect in a checksummed artifact. It now
  classifies as 232 `collapsed-range` + 138 `incoherent-range` and is **pinned at those exact
  counts**, so one more of either still fails. The file was not rewritten: satisfying a rule by
  editing the evidence is not a fix.

The validator's OHLC check now uses `jobs/ohlc.py` rather than a 1e-6 absolute tolerance that was
simultaneously too tight for a cheap scrip and too loose for an expensive one.

New regression tests (`tests/test_milestone_b.py`, 27 tests) pin: the range classifier including
the negative-oil case, both lanes calling the guard, the session-date parser and its refusal path,
the absence of the range fabrication, `true_range`/`pivots` skipping range-less bars, the basis
reader, and the exact reconciliation of the quarantine ledger.

---

## 8. Remaining material exception

**747 PSX bars whose close sits outside a real traded range** (`high ≠ low`, close still outside).

| | |
|---|---|
| Direction | 358 above the high, 389 below the low |
| Magnitude | 65% within 2%; median 1.56%; worst 11.0% |
| Shape | half occur on sessions whose entire range is within 2% of its own low |
| Status | quarantined — range not read, close kept |

An early reading of the worst rows suggested an upper-band artefact. That did not survive the full
population: the breaches run in both directions and cluster at 0–3%, which is not what a band
produces. The pattern is consistent with the exchange publishing a closing price computed on a
different basis from the intraday range, but **that is a hypothesis and the exchange's own
specification would be needed to settle it**. They are quarantined on the uncertainty, not on a
diagnosis, and the reason is recorded per group in the ledger.

This is bounded, not open-ended: the rows are identified, their ranges are not read by anything,
their closes are unaffected, and the live lane no longer adds to the set.

---

## 9. Changes made

**New**
- `jobs/ohlc.py` — the single definition of a trustworthy range
- `tools/foundation/basis_transitions.py` + `basis_transitions.json`
- `tools/foundation/ohlc_audit.py` + `ohlc_quarantine.json`
- `tools/foundation/fix_forex_volume.py` + `forex_volume_rollback.json`
- `data/foundation/psx_complete/misdated_sessions.json`
- `tests/test_milestone_b.py`

**Changed**
- `jobs/psx.py` — range guard, `file_session_date()`, mismatch refusal
- `jobs/prices.py` — range guard in `_store_frame` and `chart_repair`, FX volume rule in `chart_repair`
- `jobs/horizons.py` — `has_range()`; fabrication removed; `true_range`/`pivots` skip range-less bars
- `tools/foundation/actions.py` — `basis_breaks()` reader
- `tools/foundation/assemble.py` — `dataQuality.basisBreakInWindow` and its summary
- `tools/foundation/verify_durable.py` — shared classifier, named real-event and known-defect pins
- `RESUME.md`, `brain.md` (rule 142) — handoff updated

Out of scope and not done: no schema migration, no reset, no resync, no rebuild, no source
research, no paid sources, no training. The private Karandaaz data was not read, moved or
committed.
