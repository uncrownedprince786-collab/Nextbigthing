# Design Closure — Effective Sample, `label60`, Evidence and Confidence

**Status:** read-only. No code, specification, data, label, test, training artifact or deployment
was changed. **Head:** `eb0f276`.
**Scope:** one consolidated review closing the open items from Rounds 2–4. No further round is
proposed, and no future task list is opened.

This report **rejects the `1.2 × ATR14` proposal I made in Round 4** on code inspection, and
**reverses my Round-4 recommendation to drop `atr14` from the feature set.**

---

## 1. Verified facts

Only items confirmed by reading the repository or existing artifacts.

### 1.1 Labels and returns

| Fact | Source |
|---|---|
| `HORIZONS = (1, 5, 20)`; `WINDOW = max(HORIZONS) = 20`; **no `fwd60` exists** | `tools/make_dataset.py:66-67` |
| `LABEL_THRESHOLD_PCT = 2.0`, flat for every asset | `tools/make_dataset.py:68` |
| `base` = newest close **on or before** `as_of` | `tools/make_dataset.py:108` (`base_closes`) |
| forward bars = up to `WINDOW` sessions **strictly after** `as_of`, non-null close, oldest first | `tools/make_dataset.py:82-101` |
| `fwd20 = (closes[19] / base − 1) × 100`; `label20` = UP ≥ +2.0, DOWN ≤ −2.0, else FLAT; `mature20 = fwd20 is not None` | `tools/make_dataset.py:122-139` |
| **A path-dependent trade-outcome label already exists and is separate from `label20`**: `plan_outcome` returns `entryHit / stopHit / ambiguous / sessionsHeld`, and returns `ambiguous` when one close is beyond both entry and stop "because daily bars cannot order what happened inside the day" | `tools/make_dataset.py:141-161` |

### 1.2 ATR and trade-quality constants

| Fact | Source |
|---|---|
| `ATR_SPAN = 14`; `atr()` is the **simple mean of 14 true ranges, in price units**; `None` below `span + 1` bars | `jobs/factors.py:524-547` |
| True range = `max(high − low, |high − prev_close|, |low − prev_close|)`; a bar with no high/low contributes its close-to-close move instead | `jobs/factors.py:530-545` |
| **`atr()` is point-in-time by construction**: *"`bars` must already be sorted and cut off at the session being measured"* | `jobs/factors.py:534` |
| `MIN_REWARD_RISK = 1.2`; `MIN_CONFIRMATIONS = 1`; `MIN_STOP_ATR = STOP_BUFFER_ATR` | `lib/quality.ts:27-29` |
| `STOP_BUFFER_ATR = 1.0` | `lib/resolve.ts:42` |
| **The stop sits `STOP_BUFFER_ATR × atr` beyond the *entry zone edge*** (`d.entry.low` for a long), not beyond the close | `lib/resolve.ts:144-148` (`bufferStop`) |
| **Reward:risk is "measured from the entry level against that stop"** — not from the as-of close | `lib/quality.ts:13` |
| `setupCoverage = 0.6974` — roughly 30% of rows carry no setup, hence no entry zone at all | `readiness.json → authoritativeDataset` |

### 1.3 Dataset and distribution

| Fact | Value | Source |
|---|---|---|
| Raw eligible rows (`label20`) | **1,085,544** | `readiness.json` |
| Mature labelled rows | **1,085,544** (UP 458,828 + FLAT 213,594 + DOWN 413,122) | `readiness.json` |
| Instruments | 616; median rows per instrument 1,936 | `readiness.json` |
| Outcome-window overlap | consecutive rows share **19 of 20** forward sessions | `readiness.json` |
| Overall FLAT share | **0.1967** | `readiness.json` |
| FLAT by class | stock 0.178 · crypto 0.095 · **forex 0.680** · commodity 0.205 · etf 0.242 | `readiness.json` |
| Documented warning | *"the fixed 2% band is not volatility-scaled and collapses 68% of FX into FLAT; FX direction classification is weakly supported by this label"* | `readiness.json` |

### 1.4 Measured this round (read-only, from stored benchmark OHLC; written nowhere)

ATR14 replicated exactly as `jobs/factors.py` computes it:

| Series | median ATR14 | `1.2 × ATR14` | vs `label20`'s flat 2.0% |
|---|---|---|---|
| US equity (GSPC) | 1.09% | 1.30% | 0.65× |
| gold (GC=F) | 1.27% | 1.52% | 0.76× |
| brent (BZ=F) | 2.70% | 3.24% | 1.62× |
| US dollar index (DXY) | 0.62% | 0.75% | 0.37× |

### 1.5 Confidence contract

| Fact | Source |
|---|---|
| `Confidence = "High" \| "Medium" \| "Low"`; `confirmations >= 2 ? High : 1 ? Medium : Low`; WAIT is always Low | `lib/decision.ts:100, 753-760` |
| One-step cap when `peersAgainst` | `lib/decision.ts:770` |
| `LEGS = ["timeframe","volume","history","peers","trigger"]` | `lib/decision.ts:731` |
| `macroVeto` is *"A veto only: it can turn a LONG or SHORT into a WAIT and can do nothing else"* | `lib/decision.ts:460` |
| Published: `confidenceIs: "evidence grade"` | `app/api/signals/route.ts:48` |
| Published: *"two or more of the five confirmations is High, one is Medium"* and *"the confidence grade is capped one step for it"* | `app/methodology/page.tsx:276, 64` |
| `DecisionLog` stores `legs`, `confidence`, `baseRateShare`, `baseRateCount`, `analogRefs`, `intent`, `gate` — **and no record of what opposed** | `prisma/schema.prisma` |
| Analog floors `MIN_MATCHES_LOW/MEDIUM/HIGH = 8 / 20 / 40` | `jobs/analogs.py:80-82` |

---

## 2. Effective sample size — closed

### 2.1 Withdrawn

**`442`, `1,327` and `161–19,876` are withdrawn.** None is reproducible:

- `442` / `1,327` required a cross-sectional correlation `ρ = 0.4` that was **never estimated**, and
  per-asset-class instrument counts that **do not exist in any artifact** (`readiness.json` records
  assets by *market* — US 280, PK 226, FX 27 — not by class). The method also multiplied a temporal
  factor by a cross-sectional design effect without justifying separability, and applied a design
  effect for the *mean of an equicorrelated sample* to a classification metric.
- `19,876` used `median rows × asset count`, implying **1,192,576 rows — more than the 1,085,544
  that exist**. Internally inconsistent.
- `161` rested on an assumption of perfect within-class correlation that I supplied; the same
  assumption taken to a single common factor yields ≈32, so the endpoint was never evidence-determined.

### 2.2 What the artifacts support, correctly named

| Named quantity | Value | What it is |
|---|---|---|
| **Raw eligible rows** | 1,085,544 | storage fact |
| **Mature labelled rows** | 1,085,544 | every stored row is mature; immature rows excluded upstream, never labelled FLAT |
| **Nominal horizon-normalised count** | 54,277 (= rows ÷ 20) | corrects **only** for within-asset outcome-window overlap. `readiness.json` names this `effectiveIndependentExamples`; on inspection that label overstates what it is, though its warning — *"the row count is not the sample size"* — is correct |
| **Effective independent observations** | **not available** | requires cross-sectional dependence, regime persistence and the correlation of *prediction errors* — none measured, and the last cannot exist before a model does |

**No replacement estimate is offered, and none should be quoted.** This topic is closed.

### 2.3 Recommended future evaluation approach (recommendation only; nothing run)

Contiguous **date-block** resampling retaining the full available cross-section per sampled date,
under a protocol declared before use: block length at least `horizon + maturity` so blocks contain
whole outcome windows; block length sensitised over a small declared set on training/validation
folds only; percentile or BCa intervals on the metric itself, per fold, pooled chronologically.
It preserves cross-sectional dependence exactly and temporal dependence up to block length, and it
requires no ρ. Its binding limitation is that the sample contains few independent regimes, which no
resampling scheme can repair.

---

## 3. `label60` — the semantic question, answered first

### 3.1 Movement or trade outcome? They are different labels

- **`label20` is a terminal-movement label.** It compares one number — the close 20 sessions later —
  against the close at `as_of`. It says nothing about the path.
- **`plan_outcome` is the trade-outcome label**, and it already exists
  (`tools/make_dataset.py:141-161`). It walks the forward bars in order, reports whether entry or
  invalidation was reached first, and refuses to guess when both are crossed in one session.

`label60` is being defined as a **terminal-movement label**, the direct 60-session analogue of
`label20`. It is not a trade-outcome label and must never be described as one.

### 3.2 The `1.2 × ATR14` proposal is rejected

My Round-4 justification — *"the move reached the minimum reward-to-risk the project already
requires"* — **does not survive reading the code.** Three distinct defects:

1. **Wrong reference point.** `MIN_REWARD_RISK` is *"measured from the entry level against that
   stop"* (`lib/quality.ts:13`), and `bufferStop` places the stop `1.0 × atr` beyond the **entry
   zone edge** (`lib/resolve.ts:144-148`). `fwd60` is measured from `base`, the as-of close. Using
   `1.2 × ATR14` as a band on `fwd60` silently assumes *entry = as-of close*, which the code never
   says and which is generally false — the entry is a zone produced by `jobs/horizons.py`.
2. **It does not apply to ~30% of rows.** `setupCoverage = 0.6974`; rows with no setup have no entry
   zone, so the quantity the justification appeals to does not exist for them.
3. **It is a ratio used as a multiplier.** `1.2` is reward ÷ risk. It becomes a multiple of ATR only
   when risk is exactly `1 × ATR` measured from the close — again, not what the code does.

**And it would import trade-execution language into a terminal label without delivering it.** A
terminal return of `+1.2 × ATR` does **not** mean a 1.2R trade succeeded: the stop could have been
hit on session 3 and the price recovered by session 60. `plan_outcome` exists precisely because that
distinction matters, and `label60` cannot borrow its vocabulary.

**`1.2` is rejected as a justified value.** It is not defended merely because it appears in
`lib/quality.ts`.

### 3.3 What survives, and the chosen definition

The **form** `band = m × ATR14_t` survives on its own merits, independent of the rejected rationale:
`atr14` is point-in-time by construction (`jobs/factors.py:534`), it scales with each asset's own
dispersion — which is what the documented 7.2× FLAT spread calls for — and it requires no
square-root-of-time assumption.

What dies is any claim that `m` is derivable. **It is not derivable from available evidence, and
that limitation is stated rather than disguised.**

**Chosen `m = 2.0`, pre-registered.** Rationale, which is continuity and not class balance:
`label20`'s flat 2.0% band corresponds to **1.83 × ATR14** for the equity benchmark (measured
median ATR14 1.09%), and equities are 83% of the dataset's rows. `m = 2.0` is that implied multiple
rounded to one significant figure, so `label60` keeps the notion of "a move" that the frozen
`label20` already uses, re-expressed to scale across assets instead of being flat.

**Limitation, stated plainly:** 1.09% is the ATR of an *index*, and individual stocks have higher
ATR% than the index they compose, so for single names `m = 2.0` yields a wider band than `label20`'s
2%. Per-instrument ATR is not available in any committed artifact, so the calibration cannot be done
better than this today. That is exactly why the sensitivity set below exists.

### 3.4 Comparison against the minimum necessary alternatives

| | **A. `label20` semantics extended to 60** | **B. Fixed percent** | **C. PIT ATR-normalised (chosen)** |
|---|---|---|---|
| Band | ±2.0% | ±X% | `2.0 × atr14_t` |
| Cross-asset behaviour | **fails** — documented 7.2× FLAT spread at h=20, worse at 60 | same failure | scales with each asset's dispersion |
| PIT? | trivially | trivially | **yes** — `jobs/factors.py:534` |
| √t assumption | none | none | **none** |
| Parameter risk | none (inherited) | arbitrary X | `m` not derivable — pre-registered, limitation stated |
| Risk of becoming a trade proxy | none | none | **none, once the R:R justification is dropped** — `m × ATR` is a movement threshold scaled by a volatility measure, nothing more |

Option A is rejected on the project's own recorded evidence. Option B is Option A with a different
arbitrary number. **Option C is chosen.**

### 3.5 Are the 20- and 60-session labels comparable?

**Not by class distribution, and they should not be made so.** A horizon-independent band produces
fewer FLATs at 60 sessions than at 20. Engineering equal base rates would be the class-share
matching already retracted.

**Comparability is achieved instead by always reporting the margin over each horizon's own
majority class** — exactly what the existing baseline does (0.4211 against a 0.4204 majority). Each
horizon is judged against its own base rate; neither is judged against the other's.

### 3.6 The proposed contract

> **PROPOSED — not approved. No label has been generated.**

```
as-of timestamp     asOf; every input uses closes <= asOf
base                newest close ON OR BEFORE asOf                 [as label20, make_dataset.py:108]
forward window      the 60 stored sessions STRICTLY AFTER asOf with a non-null close
endpoint            closes[59]  (the 60th such session)            [as label20's closes[h-1]]
return              fwd60 = (closes[59] / base - 1) * 100
band                band_t = 2.0 * atr14_t, in price units, expressed as a percentage of base
                    atr14_t from jobs/factors.py atr(), bars cut off at asOf -- past-only
label60             UP   if fwd60 >= +band_t
                    DOWN if fwd60 <= -band_t
                    FLAT otherwise
maturity            mature60 = fwd60 is not None
```

| Detail | Rule |
|---|---|
| **UP / DOWN** | the terminal 60-session move exceeded twice the asset's own average true range, up or down |
| **FLAT** | it did not. FLAT is a measured outcome, **never** an imputation for a missing one |
| **Eligibility** | ≥ 15 trailing bars (`atr()` returns `None` below `span + 1`) **and** a valid base close |
| **Immature windows** | fewer than 60 forward sessions → **row excluded, never labelled FLAT** (as `mature20`) |
| **Corporate actions** | row excluded when an unadjusted action falls in the forward window (`dataQuality.basisBreakInWindow`, already computed) **or** in the 15-session ATR window — *the trailing-window exclusion does not exist today and would need to be added* |
| **Delistings** | the series ends; the final 60 sessions are immature and drop out. No synthetic terminal value, no survivorship repair |
| **Quality flags** | any Stage-0 integrity condition (bad bar, stale, non-session date) voids the row for both windows |
| **Implementation note** | `WINDOW = max(HORIZONS)` must become 60, which changes the `forward_bars` query |

**Pre-registration** (frozen before the label is built, as `acceptance_scope.json` was):
`m = 2.0` primary; narrow declared sensitivity `m ∈ {1.0, 2.0, 3.0}` evaluated on **training and
validation folds only**, with the held-out fold scored **once** at `m = 2.0`; a 60-session purge at
every fold boundary; walk-forward chronological splits; raw rows and a block-bootstrap interval
reported separately; before any model is fit, cross-tabulate `label60` against `label20` on shared
rows — high concordance means it is a relabelling and the work stops there.

### 3.7 Exploratory label ≠ validated capability

Approving `label60` as an exploratory research label authorises building and studying it. It does
**not** validate a position-trading capability, and the existence of labelled rows never will. The
one measured model has no edge (0.4211 vs 0.4204 majority), and effective independent observations
are unmeasured (§2.2).

---

## 4. `atr14` as a feature — retain

**Recommendation: RETAIN. My Round-4 recommendation to drop it is reversed.**

Information flow, from the code:

- `atr14` is computed from bars *"cut off at the session being measured"* (`jobs/factors.py:534`) —
  strictly `≤ asOf`.
- `band_t = 2.0 × atr14_t` uses only `≤ asOf` information.
- Only `fwd60` uses `asOf+1 … asOf+60`.

**There is no leakage.** Leakage is future information reaching a predictor; `atr14_t` is not
future information, and nothing about the outcome window enters it. There is also no train/serve
mismatch: at decision time both the feature and the band are computable from the same data.

Volatility is legitimate predictive information — of regime, of move magnitude, and of the
reliability of other features. Dropping a genuine PIT predictor because it also appears in the
target's denominator would discard real information to avoid a problem that does not exist.

**The one real caveat, which is an interpretation rule, not a reason to exclude:** `atr14`'s
measured feature importance will partly reflect the label's construction rather than market
predictability, because the model knows the band's denominator. **This must be stated in the
pre-registration and whenever feature importances are reported.** It does not affect whether the
predictions are useful, which is what the acceptance conditions test.

---

## 5. Canonical evidence mapping

Implementation is the source of truth. Governing rule, which is the **shipped** design
(`lib/decision.ts:460`): **only asset-specific evidence may cast a directional vote; market-wide
evidence may qualify, withhold or veto, but never votes.**

| Canonical | Implementation (source) | V1.1 | Kind | Votes | PIT requirement | Duplication risk | Recorded | Absent / stale / invalid |
|---|---|---|---|---|---|---|---|---|
| **E1 trend** | `setup.direction`, `horizon.direction`, `r20`, `sma20/50`; leg `timeframe` (`lib/decision.ts:731`) | F1 | derived, own price | **YES** | closes ≤ `asOf` | shares price series with E3, E5 | `legs` / `opposing` | stale → Stage-0 veto, gate `stale` |
| **E2 participation** | `volumeRatio`, `r1`; leg `volume` | F2 | derived, own volume | **YES** | volume ≤ `asOf` | independent | `legs` / `opposing` | **FX has no volume → INELIGIBLE, never 0** |
| **E3 volatility** | `atr14`, `drawdownPct`, `rangePct` — **no leg exists today** | F3 | derived, own price | **YES** | closes ≤ `asOf` | shares price series with E1 | `legs` / `opposing` | < 15 bars → INELIGIBLE |
| **E4 cross-sectional** | `relStrength`, `peers`; leg `peers` | F4 | derived, peer prices | **YES** | peer closes ≤ `asOf` | **removes the common factor by construction** | `legs` / `opposing` | `peers < 3` → INELIGIBLE |
| **E5 history** | `analogs`, `baseRateShare` + `baseRateCount`, `analogRefs`; leg `history`; floors 8/20/40 (`jobs/analogs.py:80-82`) | **none** | **historical prior** | **DISPUTED** | matched days strictly before `asOf` | **re-reads the observations E1/E3 use** | `legs` / `opposing`, with share **and** denominator | < 8 matches → INELIGIBLE |
| **E6 trigger** | `entryTrigger`; leg `trigger` | none | raw event, own series | **NO — timing** | own series ≤ `asOf` | independent | `notes` → `timeSense` | silent ~19 of 20 sessions; **never reported as missing** |
| **E7 macro** | `macroVeto` (`lib/decision.ts:460, 655`), PIT macro series | F5 | contextual + integrity gate | **NO** | `observation_date + publicationLagDays` | **same cause as E8 on policy days** | `notes`, gate `macro-veto` | expired → no veto |
| **E8 event / news** | `news{tone,catalyst}`, `newsCoverage`, `newsCount`, `eventInDays`, events corpus | F6 | contextual | **NO** | publication time < decision time | **same cause as E7 on policy days** | `notes`, `missing`, event id | `newsCoverage:"unavailable"` → **never a neutral tone** |

**Reconciliation with the six candidate families:** F1–F4 become E1–E4 and vote. **F5 and F6 are
demoted to context** — V1.1 promoting macro to a voting family is a regression from shipped
behaviour. **E5 is added**, filling the gap where `history` had a leg and a `DecisionLog` audit
record but no family. **E6 is explicitly not a family**: it answers *when*, not *which way*.
Votes remain `{-1, 0, +1}` with equal weights; **`MIN_FAMILIES = 3` and `MIN_NET = 2` are
unchanged** and no new threshold is introduced.

**How duplicate information is prevented from voting twice:** structurally. E7 and E8 cannot vote,
so one monetary event cannot become two confirmations and no event-id matching is required. E4
neutralises common-factor moves on its own — when the whole peer group moves, `relStrength → 0`.
**Genuinely distinct observations survive:** the announcement is context; the price reaction it
caused is read by E1/E3 as ordinary evidence; whether volume confirmed it is E2. **Unresolved and
recorded as such:** E1, E3 and E5 all re-read one price series.

---

## 6. Confidence contract — preserved

### 6.1 The rule

```
votingSet        = {E1..E5}
eligibleFamilies = eligible members, INCLUDING those voting 0
NET = SUM(vote_i) ; d = sign(NET) ; support = |vote = d| ; opposing = |vote = -d|

GATE 1  eligibleFamilies < 3 -> WAIT, basis "file",     gate "file"
GATE 2  |NET| < 2            -> WAIT, basis "evidence", gate "thin-evidence"
GATE 3  NET >= +2 -> LONG        GATE 4  NET <= -2 -> SHORT

CONFIDENCE (R1', preserved)  WAIT -> Low
                             base: support >= 3 -> High ; support == 2 -> Medium
                             cap:  opposing >= 1 -> one step down
STAGE 5  risk / execution vetoes lower readiness; MAY NEVER CHANGE d
```

`NET ≥ 2` forces `support ≥ 2`, so this reduces to one publishable sentence: **High means at least
three independent families agree and none disagrees.**

**The R1′ cap is preserved.** `app/methodology/page.tsx:64` publicly states it and
`app/api/signals/route.ts:48` publishes `confidenceIs: "evidence grade"`. No contradiction was found
that requires retiring it; mild and substantial dissent are already treated differently *before* the
cap, because each opposing family subtracts 1 from `NET` and two objections can push a call below
`MIN_NET` into `WAIT` where one cannot.

### 6.2 The eight quantities, kept distinct

| Quantity | Meaning | Persist or derive |
|---|---|---|
| Support count | families voting the published direction | **PERSIST as names** — `DecisionLog.legs` *(exists)* |
| Opposing families | families voting against it | **PERSIST as names** — `opposing` *(one new field)* |
| Abstentions | eligible, measured, inconclusive | **DERIVE** = `eligible − |legs| − |opposing|` |
| Eligible families | passed their documented gates | **PERSIST** — not derivable from the name lists |
| Unavailable / invalid | **never a 0 vote** — a `file` fact; detail in `missing` | **DERIVE** (complement of eligible) |
| `NET` | `|legs| − |opposing|` | **DERIVE** — persisting it invites disagreement with its own inputs, the *"one count, two readers"* fault (`lib/decision.ts:703`) |
| Evidence grade | `confidence`; **never a probability of success** | **PERSIST, unchanged**, with `logicVersion` |
| Measured model performance | experiment artifacts; matured `DecisionLog` outcomes | **SEPARATE** — never a per-decision field |
| Execution readiness | `executionReadiness`, `timeSense`, Stage-5 | **SEPARATE** — never changes `d` |

### 6.3 Minimum auditable opposition record

**`opposing`, as stable family names, is the minimum.** Without it a capped `Medium` and an
uncapped `Medium` are indistinguishable in the log, so the cap — a published promise — could never
be reviewed after the fact. Names rather than a count, for the reason `DecisionLog.legs` already
exists: a count cannot say *which* family earned its place.

**Contract change discipline:** `confidence` is **not** redefined in place. A family-based path
ships under a new **`logicVersion`**, with `app/methodology/page.tsx` and the API's
`confidenceIs`/`minConfirmations` updated in the same change. Historical rows keep their meaning.

### 6.4 Hand-calculable consistency checks

Same rule set throughout; votes in order E1–E5.

**(a) Clean agreement** — `+1, +1, +1, INELIGIBLE (peers 1), INELIGIBLE (5 matches)`
`eligible 3 · NET +3 · support 3 · opposing 0` → **LONG / High** · `legs "trend,volume,volatility" · opposing ""`

**(b) Strong majority, one objection — what the cap is for** — `+1, +1, +1, −1, +1`
`eligible 5 · NET +3 · support 4 · opposing 1` → base High, capped → **LONG / Medium** ·
`legs "trend,volume,volatility,history" · opposing "peers"`
The four supporting names remain in the record; the headline does not claim High over a recorded
contradiction.

**(c) Low information — `file` not `evidence`** — FX: no volume → E2 INELIGIBLE; `peers 0` → E4
INELIGIBLE; 5 matches → E5 INELIGIBLE. `eligible 2 · NET +2 (E1 +1, E3 +1)`
**GATE 1 fails first** → **WAIT, basis `file`**, gate `file`, Low. `NET` would have cleared
`MIN_NET`; a coverage failure is never reported as weak evidence.

**(d) Duplicate macro/news** — one policy decision: `+1, +1, 0, 0, 0`, E7 and E8 context.
E4 reads 0 because the whole peer group moved. `eligible 5 · NET +2 · support 2` → **LONG / Medium**.
Under V1.1 as written F5 and F6 would each add +1 → `NET +4` → High: one cause as four confirmations.

---

## 7. Decision register

| Decision | Status | Evidence / reason |
|---|---|---|
| `442`, `1,327`, `161–19,876` withdrawn | **AGREED** | ρ never estimated; class counts absent; `19,876` implies more rows than exist |
| Raw rows, mature rows, nominal horizon-normalised count correctly named | **AGREED** | `readiness.json`; `rows ÷ 20` corrects only within-asset overlap |
| Effective independent observations **not available**; no replacement offered | **AGREED** | items 5–7 unmeasured; error-correlation cannot exist pre-model |
| `label20` is terminal-movement; `plan_outcome` is the trade-outcome label | **AGREED** | `tools/make_dataset.py:122-161` |
| `atr()` is PIT, simple 14-session mean, price units | **AGREED** | `jobs/factors.py:524-547` |
| R:R measured from the entry level; stop `1 × atr` beyond the **entry zone** | **AGREED** | `lib/quality.ts:13`, `lib/resolve.ts:144-148` |
| **`1.2 × ATR14` rejected** | **AGREED** | wrong reference point; absent for ~30% of rows; ratio used as multiplier |
| `MIN_FAMILIES = 3`, `MIN_NET = 2`, votes `{-1,0,+1}`, equal weights — unchanged | **AGREED** | not altered by anything here |
| R1′ cap preserved | **AGREED** | published at `app/methodology/page.tsx:64`; no contradiction found |
| **`band = 2.0 × atr14_t`** as `label60` primary | **PROPOSED** | continuity with `label20`'s implied 1.83× ATR for 83% of rows; `m` not derivable — limitation stated |
| `m ∈ {1.0, 2.0, 3.0}` on train/validation only; held-out scored once | **PROPOSED** | prevents threshold selection on test outcomes |
| **`atr14` retained as a feature** | **PROPOSED** | PIT; no leakage; no train/serve mismatch. Importance-interpretation caveat recorded |
| Trailing-window corporate-action exclusion added | **PROPOSED** | does not exist today |
| E7/E8 contextual only (F5 demoted) | **PROPOSED** | restores shipped `macroVeto` semantics |
| `opposing` persisted as names; `NET`/voting/abstaining derived | **PROPOSED** | minimum auditable record for the cap |
| `logicVersion` + coordinated methodology/API update | **PROPOSED** | historical grades must not silently change meaning |
| Retire `τ`; E1 requires both signals | **PROPOSED** | `τ` inert for E2–E4 at any value |
| **E5 `history` votes** | **DISPUTED** | best-audited evidence, but re-reads E1/E3's price series |
| Within-asset reuse across E1/E3/E5 | **DISPUTED — open** | unresolved; recorded, not hidden |

---

## 8. Owner decisions

Only choices that require your authority. Everything else above was settled by inspection.

| # | Decision | Recommended default | Consequence of the alternative |
|---|---|---|---|
| 1 | Approve `label60` as an **exploratory research label** (not a capability claim)? | **Approve** | Declining closes the position horizon for V1; the swing horizon is unaffected |
| 2 | Freeze `m = 2.0` with sensitivity `{1.0, 2.0, 3.0}`? | **Freeze at 2.0** | A different fixed `m` is equally pre-registerable; leaving `m` open invites selection on results, which the protocol exists to prevent |
| 3 | Does **E5 `history`** vote, or modulate confidence as a prior? | **Votes**, with its correlation to E1 measured once wired | As a prior it never reaches `NET`, so more decisions fall below `MIN_NET` into `WAIT` |
| 4 | Ship the family path under a new `logicVersion`, updating the methodology page and API in the same change? | **Yes** | Redefining `confidence` in place leaves stored values intact while changing what they mean, corrupting longitudinal analysis |

---

## 9. Change confirmation

This review made **no** changes of any kind:

- No code, specification, configuration or test modified. `BRAIN-SPEC-V1.md` unmodified.
- No dataset, artifact or experiment output modified; `data/foundation/` unmodified.
- **No label generated.** `label60` does not exist.
- No training, evaluation, tuning, ablation or bootstrap run. No ML experiment launched.
- No deployment and no destructive action.
- Benchmark CSVs and source files were **read only**; the figures in §1.4 were computed in memory
  and written nowhere.
- `git diff HEAD` reports no tracked file changed. The only new file is this report.

**The design review is closed.** No further round is proposed. Implementation awaits your explicit
approval of decisions 1–4.
