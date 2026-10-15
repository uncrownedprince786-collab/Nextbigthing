# Design Review Round 4 — Effective Sample, `label60` Threshold, Canonical Evidence Mapping

**Status:** read-only. No file, code, dataset, label, test, artifact or deployment modified.
**Head:** `eb0f276`. **New this round:** `lib/quality.ts`, `lib/resolve.ts`, and read-only
inspection of the stored benchmark CSVs in `data/foundation/benchmarks/`.

Round 4 overturns **my own primary `label60` recommendation** from the previous report, on
arithmetic that should have been done when I made it.

---

## 1. Effective sample size

### 1.1 Reconciled table — what each number actually measures

| # | Quantity | Value | Derivation | Status |
|---|---|---|---|---|
| 1 | **Raw eligible rows**, `label20` | **1,085,544** | `readiness.json → authoritativeDataset.rows` | **VERIFIED** |
| 2 | **Mature labelled rows**, `label20` | **1,085,544** | `labelCounts` UP 458,828 + FLAT 213,594 + DOWN 413,122 = 1,085,544. Immature rows are excluded upstream, never labelled FLAT | **VERIFIED** |
| 2b | Raw rows, `label60` | **1,048,726** | Round-1 count; **never independently recomputed**, and an **upper bound** — it required 60 *forward* sessions only, while any volatility- or ATR-normalised band also needs a trailing window | **ESTIMATE** |
| 3 | **Nominal horizon-normalised count** @20 | **54,277** | `1,085,544 ÷ 20` | **VERIFIED as recorded** in `readiness.json` as `effectiveIndependentExamples` |
| 3b | Nominal horizon-normalised count @60 | **17,478** | `1,048,726 ÷ 60` | **DERIVED from an estimate** |
| 4 | Overlapping vs non-overlapping windows | consecutive rows for one instrument share **19 of 20** forward sessions | `readiness.json → outcomeWindowOverlap` | **VERIFIED** |
| 5 | **Cross-sectional dependence** | **NOT MEASURED** | no ρ anywhere in the artifacts; assets by *class* not recorded | **UNKNOWN** |
| 6 | **Temporal dependence / regime persistence** | **NOT MEASURED** | `regime_coverage.json` names episodes but no persistence statistic exists | **UNKNOWN** |
| 7 | **Effective sample for a specific metric** | **NOT DERIVABLE TODAY** | depends on the correlation of *prediction errors*, which does not exist until a model does | **NOT AVAILABLE** |

**Rows ÷ horizon is item 3, not item 7.** It is a nominal horizon-normalisation that corrects
*only* for within-asset outcome-window overlap. It assumes every asset is an independent series,
which is false. `readiness.json` names it `effectiveIndependentExamples`; on the evidence that
label overstates what the number is, though its accompanying warning — *"the row count is not the
sample size"* — is correct and conservative in the right direction.

### 1.2 The 161–19,876 range is withdrawn

Both endpoints fail on inspection:

- **19,876** = `(1,936 median rows ÷ 60) × 616 assets`. Median × count implies **1,192,576 rows**,
  more than the 1,085,544 that exist. The figure is internally inconsistent; the correct nominal
  ceiling is simply item 3b, **17,478**.
- **161** = `32.3 × 5`, which assumes the five documented asset classes behave as five independent
  blocks with **perfect correlation inside each**. Five classes are documented
  (`labelBalanceByClass`); the perfect-within-class correlation is an **assumption I supplied**.
  Taking the same assumption to one common factor gives **≈32**, so the lower endpoint is not
  determined by evidence at all — it is determined by a number of factors nobody has estimated.

**Plain statement, as you asked for:** *the evidence supports raw counts and a qualitative
dependence warning, and nothing more.* The available facts are items 1–4; items 5–7 are unmeasured.
The honest range of ignorance spans roughly **32 to 17,478** — three orders of magnitude — and
quoting any point inside it as "the effective sample size" would be inventing precision.
**No replacement number is offered.**

### 1.3 The block bootstrap, assessed

**What it preserves.** Drawing contiguous blocks of *dates* and keeping **every** asset's row for
each drawn date preserves (a) cross-sectional dependence exactly, including block structure by
sector, class and market, with no equicorrelation assumption; (b) temporal dependence up to the
block length; (c) regime persistence, provided blocks are long relative to a regime.

**What it does not resolve.**
1. **Dependence across block boundaries** — multi-year regimes exceed any practical block.
2. **Too few independent regimes.** 2018–2026 contains one COVID crash, one 2022 drawdown and no
   2008-type event. Resampling cannot manufacture regimes the sample never contained; the interval
   will understate true uncertainty about unseen regimes. This is the binding limitation and no
   resampling scheme fixes it.
3. **Non-stationarity.** Block resampling assumes blocks are exchangeable; a trending or
   structurally changing market violates that.
4. **Survivorship**, which is a property of the universe, not of the resampling.

**Block length.** At minimum `horizon + maturity`, so that a drawn block contains whole outcome
windows rather than truncated ones; otherwise boundary rows carry outcomes decided by data outside
the block. **Preferred: draw the block on decision dates and extend it to include the full 60-session
outcome window of its last row.** Sensitise over e.g. {60, 120, 250} sessions **on training and
validation folds only**, and report the interval's sensitivity to block length as a stated
limitation. Block length is never chosen by a held-out outcome.

**Intervals.** Percentile or BCa intervals from the bootstrap distribution of the metric itself
(accuracy, per-class recall, margin over majority class) — computed per fold and pooled
chronologically, never pooled across shuffled time.

**Why this beats one global ρ.** Three reasons, the third decisive:
1. It requires no separability between temporal and cross-sectional dependence, so nothing is
   multiplied.
2. It requires no equicorrelation, which is plainly false across these classes.
3. **The ρ that matters is the correlation of prediction errors, not of returns, and it cannot be
   estimated before a model exists.** Any ρ-based effective-N computed in advance is therefore the
   wrong quantity, however carefully it is estimated. This is the flaw that produced 442 and 1,327.

**Not executed. No experiment authorised or run.**

### 1.4 Recommendation on the 60-session target

**Approve for future exploratory research.** Not deferral: the blocking question is not "is there
more history" — the dataset's span is fixed and waiting adds rows at the same correlation — and
not rejection: nothing shows the target is unjustifiable, only that nobody has measured whether it
is validatable.

**These remain separate claims, and only the first is being made:**

| Claim | Status |
|---|---|
| Create `label60` as an exploratory research label | **Recommended** |
| Position-horizon capability is validated | **Not claimed; not currently assessable** |
| Position-horizon validation is likely feasible | **Not claimed** — with items 5–7 unmeasured, anyone asserting feasibility is asserting a ρ they do not have |

---

## 2. `label60` — the target definition

### 2.1 Verified `label20` mechanics

```
tools/make_dataset.py
  HORIZONS = (1, 5, 20) ; WINDOW = max(HORIZONS) = 20 ; LABEL_THRESHOLD_PCT = 2.0
  base         = newest close ON OR BEFORE as_of                       (base_closes)
  forward_bars = <= WINDOW sessions STRICTLY AFTER as_of, close IS NOT NULL, oldest first
  fwd20        = (closes[19] / base - 1) * 100
  label20      = UP if fwd20 >= +2.0 ; DOWN if <= -2.0 ; else FLAT
  mature20     = fwd20 is not None       # immature rows excluded, never labelled FLAT
```

The as-of close is **excluded** from the forward window, and the endpoint is the **20th stored
session with a non-null close**, not a calendar date.

### 2.2 Measured: the floor is nearly inert, and `k = 1.0` fails on the project's own standard

Read-only inspection of stored benchmark CSVs (last 2,000 sessions, daily log returns):

| Series | daily sd | `σ·√60` | does the 2.0% floor bind at k=1? |
|---|---|---|---|
| US equity (GSPC) | 1.229% | **9.52%** | no |
| gold (GC=F) | 1.148% | 8.89% | no |
| brent (BZ=F) | 2.752% | 21.32% | no |
| **US dollar index (DXY)** | **0.419%** | **3.25%** | no |
| crypto (BTC) | 3.909% | 30.28% | no |

**Answer to the floor question:** at a 60-session horizon the 2.0% floor **never binds at k = 1.0**,
even for the lowest-volatility series available. It binds only for low-volatility instruments at
small `k` — for DXY the band is floor-dominated at `k ≤ 0.5` (`0.5 × 3.25 = 1.63% < 2.0%`). So the
floor is close to inert in the regime I recommended, and becomes a real constraint only if `k` is
set low.

**The decisive finding against my own recommendation.** A symmetric `k`-sigma deadband has a
*mechanical* relationship to the FLAT share:

| k | FLAT = P(\|Z\| < k) |
|---|---|
| 0.25 | **19.7%** |
| 0.5 | 38.3% |
| 0.75 | 54.7% |
| **1.0** | **68.3%** |

`readiness.json` records the overall FLAT share as **0.1967** and warns that forex's **0.680**
means *"FX direction classification is weakly supported by this label"*.

**`k = 1.0` therefore imposes ≈68% FLAT on every asset — precisely the condition the project has
already documented as weakly supported.** My previous recommendation would have universalised the
defect it was introduced to fix. It is withdrawn.

The obvious repair — set `k ≈ 0.25` to reproduce the documented 19.7% — is **the retracted
class-share matching by another route**, and is rejected for the same reason: it defines the target
by its own distribution rather than by a financial outcome.

### 2.3 Option 4 — a band from the project's own trade-quality constants *(RECOMMENDED)*

The way out of that trilemma is an anchor that is neither interpretive nor distributional, but
**financial**. The project already defines what makes a move worth taking:

```
lib/quality.ts:27   MIN_REWARD_RISK = 1.2
lib/quality.ts:29   MIN_STOP_ATR    = STOP_BUFFER_ATR
lib/resolve.ts:42   STOP_BUFFER_ATR = 1.0
```

```
band_t  = MIN_REWARD_RISK * MIN_STOP_ATR * atr14_t  =  1.2 * atr14_t
label60 = UP   if fwd60 >= +band_t
          DOWN if fwd60 <= -band_t
          else FLAT
```

**`UP` means: the move reached the minimum reward-to-risk this project already requires of any
trade, measured against the minimum stop it already requires.** That is a documented financial
outcome, stated in the product's own published terms.

Properties:

- **No new constant.** Both numbers are frozen, used in production, and pinned by tests.
- **No √t assumption.** The band does not scale with the horizon, which is correct: "was this a
  move worth taking?" does not change with how long you waited.
- **Horizon comparability for free.** `label60` and a `label20` built the same way differ **only**
  in window length, which isolates exactly the effect the position-horizon question is about.
- **Cross-asset comparability as a consequence, not a goal.** `atr14` scales with volatility, so
  the band is roughly a constant fraction of each asset's own dispersion — ≈0.15σ₆₀ for both GSPC
  and BTC on the measured figures, despite a 3× difference in volatility.
- **Approximate consistency check:** at a 20-session window the implied band is ≈0.3σ₂₀ for
  equities → FLAT ≈ 24%, against the documented 17.8% for stocks. Same order, derived
  independently and **not tuned to it**. (Approximate: `atr14` values were not read; ATR includes
  gaps and intraday range, so it exceeds close-to-close sd by a factor I did not measure.)

**Risks and failure modes, stated:**
1. **`atr14` is already a model feature** (`readiness.json → initialTask.featureNames`). The label
   would depend on a feature. Not leakage — both are PIT — but a model given `atr14` is given the
   label's denominator. **Mitigation: drop `atr14` from the feature set for `label60` experiments**
   (14 of 15 features remain), or document the dependence explicitly. *The identical concern
   applies to any volatility-normalised band, including Option 3.*
2. At 60 sessions FLAT becomes small (≈12–13%), so the task approaches binary UP/DOWN. That is a
   consequence of a horizon-independent band and must be reported, not corrected by widening `k`.
3. `atr14` requires 14 trailing sessions — a mild eligibility cost, far smaller than Option 3's
   60-session trailing requirement.

### 2.4 Candidate comparison

Common to all: as-of = `asOf`; base = newest close ≤ `asOf`; endpoint = **60th stored session with
a non-null close, strictly after `asOf`**; `fwd60 = (closes[59]/base − 1)×100`;
`mature60 = fwd60 is not None`; immature rows **excluded, never FLAT**; corporate actions excluded
via `dataQuality.basisBreakInWindow` over the forward window **and** over the trailing estimator
window (the latter does not exist today and must be added); delisting ends the series so the final
60 sessions drop out, with no synthetic terminal value and no survivorship repair.

| | **1. `label20` convention extended** | **2. Fixed %** | **3. PIT vol-normalised** | **4. ATR trade-quality** ✅ |
|---|---|---|---|---|
| Band | ±2.0% | ±X% | `max(k·σ_t·√60, 2.0%)` | `1.2 · atr14_t` |
| Estimator / lookback | none | none | 60 trailing sessions, daily log returns | `atr14`, 14 sessions |
| Rationale for the number | inherited | arbitrary | `k` **contested** (§2.2) | **frozen project constants** |
| UP means | gained >2% in 60 sessions | same | moved > k sd of own 60-session move | **reached the project's own minimum R:R** |
| √t needed? | no | no | **yes, and only exact for i.i.d.** | **no** |
| Cross-class behaviour | **fails** — 7.2× FLAT spread at h=20, worse at 60 | fails | comparable | comparable |
| FLAT share | collapses for FX, inflates for crypto | same | **68% at k=1 — the documented defect** | ≈12–13% at h=60 |
| Floor interaction | n/a | n/a | floor nearly inert at k=1 (§2.2) | n/a |
| Main risk | volatility classifier | volatility classifier | `k` has no non-circular anchor | label depends on a feature |

Option 1 is **not** semantically appropriate at 60 sessions: `readiness.json` already records that
the fixed band produces a 7.2× FLAT spread across classes at 20 sessions, and 60-session dispersion
makes it worse.

### 2.5 Does the proposal fix FX?

**Option 3 at `k = 1.0` does not.** DXY's `σ·√60 = 3.25%`, so the band would be 3.25% — *wider*
than the current 2%, producing *more* FLAT for FX, not less. The FX problem is not that the 2%
band is mis-scaled in the direction I assumed; it is that **any ≈1σ symmetric deadband puts ~68%
of outcomes inside it**, which is what FX already shows.

**Option 4 does fix it**, because the band tracks `atr14` rather than a sigma multiple: for a
low-volatility pair the band shrinks proportionally, holding the FLAT share near its cross-asset
level instead of collapsing the class.

### 2.6 Pre-registration protocol *(PROPOSED)*

Frozen in a committed artifact **before** the label is generated, in the manner of
`acceptance_scope.json`:

1. **Primary:** Option 4, `band = 1.2 × atr14_t`, declared now. **Control:** `label60_fixed` at
   ±2.0%, so any difference can be attributed to the horizon rather than the band.
2. **Bounded sensitivity:** multipliers {1.0, 1.2, 1.5} and Option 3 at
   `k ∈ {0.25, 0.5, 1.0}` evaluated on **training and validation folds only**. The held-out fold is
   scored **once, at the primary definition**. Grid and headline published together; the grid may
   never promote a non-primary setting to the headline.
3. **Held-out protection:** the final fold is touched once, after the primary is frozen. Repeated
   comparison is prevented structurally — a single scoring pass — not by discipline alone.
4. **Feature policy:** `atr14` dropped from the feature set for `label60` experiments, or the
   dependence documented in the pre-registration. Declared now, not after a result.
5. **Redundancy kill switches**, both before any model is fit: cross-tabulate `label60` against
   `label20` on shared rows; and test how well `fwd20` plus `atr14_t` alone recover `label60`. High
   concordance on either ⇒ `label60` is a relabelling; stop. Neither touches a held-out outcome.
6. **Purge 60 sessions** at every fold boundary — not the current 20, which would leak 40 sessions
   of every boundary row. Walk-forward, chronological, no shuffling.
7. **Report raw rows (item 1) and a block-bootstrap interval (§1.3) separately.** Never quote a row
   count as a sample size.
8. **Multiple-comparison policy written before a second horizon exists.** V1.1 has none.
9. **Claim conditions:** margin over majority class exceeds the bootstrap interval; holds on the
   worst fold; no collapse to one class; leakage 0; **both horizons published together**.

### 2.7 What `label60` adds beyond `label20` and `fwd20`

`fwd20` is a raw 20-session return; `label20` is its fixed-band discretisation. `label60` under
Option 4 differs in **two** ways — a longer window and a volatility-aware band — which is why the
`label60_fixed` control matters: without it the two effects are inseparable. The addition is
tested, not assumed, by step 5 above. **If `fwd20` and `atr14_t` largely recover `label60`, the
label adds nothing and the programme stops there** — before a model is fit, at near-zero cost.

---

## 3. Canonical evidence mapping

### 3.1 The mapping

| Canonical | Existing field / mechanism (source) | V1.1 | Kind | Votes? | PIT requirement | Dependence | Recorded | When absent / stale / invalid |
|---|---|---|---|---|---|---|---|---|
| **E1 trend** | `setup.direction`, `horizon.direction`, `r20`, `sma20/50`; leg `timeframe` (`lib/decision.ts:731`) | F1 | derived feature, own price | **YES** | closes ≤ `asOf` | shares the price series with E3, E5 | `legs` / `opposing` | stale close → Stage-0 veto → INELIGIBLE, gate `stale` |
| **E2 participation** | `volumeRatio`, `r1`; leg `volume` | F2 | derived feature, own volume | **YES** | volume ≤ `asOf` | independent of E1 | `legs` / `opposing` | **FX publishes no volume → INELIGIBLE, never 0** |
| **E3 volatility** | `atr14`, `drawdownPct`, `rangePct` — **no leg exists** | F3 | derived feature, own price | **YES** | closes ≤ `asOf` | shares the price series with E1 | `legs` / `opposing` | insufficient history → INELIGIBLE |
| **E4 cross-sectional** | `relStrength`, `peers`; leg `peers` | F4 | derived feature, peer prices | **YES** | peer closes ≤ `asOf` | **removes the common factor by construction** | `legs` / `opposing` | `peers < 3` → INELIGIBLE |
| **E5 history** | `analogs{count,positive,medianPct}`, `DecisionLog.baseRateShare` + `baseRateCount`, `analogRefs`; leg `history`; floors 8/20/40 (`jobs/analogs.py:80-82`) | **none** | **historical prior** | **DISPUTED** (§3.3) | matched days strictly before `asOf` | **reuses the same price observations E1/E3 read** | `legs` / `opposing`, plus share **and** denominator | `< 8` matches → INELIGIBLE (the job refuses to grade) |
| **E6 trigger** | `entryTrigger{rule,direction}`; leg `trigger` | none | **raw event**, own series | **NO — timing** | own series ≤ `asOf` | independent | `notes` | silent on ~19 of 20 sessions; **never reported as missing** |
| **E7 macro** | `macroVeto{reason,asOf}` (`lib/decision.ts:460,655`), PIT macro series | F5 | **contextual + integrity gate** | **NO** | `observation_date + publicationLagDays` | **same cause as E8 on policy days** | `notes`, gate `macro-veto` | expired past `MACRO_VETO_FRESH_DAYS` → no veto |
| **E8 event / news** | `news{tone,catalyst}`, `newsCoverage`, `newsCount`, `eventInDays`, events corpus | F6 | **contextual** | **NO** | publication time < decision time | **same cause as E7 on policy days** | `notes`, `missing`, event id | `newsCoverage: "unavailable"` → **explicitly never a neutral tone** |

**Not every field is forced into a directional family.** E6 answers *when*, not *which way*, and
belongs to `timeSense`. E7 and E8 are context and refusal. E5 is a **historical prior** and its
vote eligibility is genuinely open.

### 3.2 Vote eligibility policy: only asset-specific evidence votes

> **Market-wide evidence may withhold, qualify or inform. It may never cast a directional vote.**

This is not a new rule — it is the shipped design. `lib/decision.ts:460` says of `macroVeto`:
*"A veto only: it can turn a LONG or SHORT into a WAIT and can do nothing else."* **V1.1's F5 is a
regression from production behaviour.**

How it handles each case you named:

| Case | Treatment |
|---|---|
| **One policy event in several sources** | E7 and E8 both record it with provenance; **neither votes**, so two source records can never become two confirmations. Deduplication is structural — no event-id matching needed. |
| **Announcement vs its later measured reaction** | The announcement is E7/E8 context at time `t`. The *reaction* is a price move, read by E1/E3 as ordinary evidence. These are genuinely distinct observations and both are retained — one as context, one as a vote. |
| **Cross-market common-factor moves** | E4 removes them automatically: when the whole peer group moves together, `relStrength → 0` and E4 abstains without being told an event occurred. |
| **Asset-specific vs broad information** | The dividing line *is* the rule. An 8-K about *this* registrant is asset-specific and is a legitimate V2 candidate for a voting family; a policy rate is market-wide and stays veto-only regardless. |
| **Historical priors reflecting the same observations as current features** | **Unresolved.** E5's matched days are computed from the same price series E1 and E3 read. The rule above does not address within-asset reuse, and nothing in these reviews does. |

**Nothing is suppressed.** E7 can veto to `WAIT`; E8 populates `notes` and `missing`; both are
recorded with provenance and are visible to the reader. They lose only the ability to vote.

### 3.3 E5 — the one genuinely open question

**For voting:** it is the *only* evidence with a shipped outcome-audit mechanism
(`baseRateShare` **and** `baseRateCount` exist precisely so it can be scored), it has a graded
quality floor nothing else has (8/20/40), and excluding it while admitting E3 — which has no leg,
no audit and no floor — would admit the least-evidenced family and exclude the best-evidenced one.

**Against voting:** a base rate derived from the same price series E1 and E3 read is a third
reading of one source, which is the dependence this taxonomy exists to prevent. Treating it as a
**prior that modulates confidence** rather than a vote would be internally consistent with
demoting E7/E8 for the same reason.

**Recommendation: E5 votes in V1, with its correlation against E1 measured and reported once E3
and E5 are wired.** This is a judgement call, not a derivation, and it is marked **DISPUTED**.

**Testable implication:** score matured `DecisionLog` rows with and without `history` in `legs`
(`tools/scorecard.py` already does this per leg). If outcomes are indistinguishable, E5 is
redundant with E1 and should be demoted to a prior.

---

## 4. `NET`, opposition and confidence

### 4.1 From taxonomy to formula

```
votingSet        = {E1, E2, E3, E4, E5}          (E6 timing; E7, E8 context -- never vote)
eligibleFamilies = eligible members of votingSet, INCLUDING those voting 0
NET = SUM(vote_i), vote_i in {-1, 0, +1}, equal weights
d   = sign(NET) ; support = |vote = d| ; opposing = |vote = -d|

GATE 1  eligibleFamilies < MIN_FAMILIES (3) -> WAIT, basis "file",     gate "file"
GATE 2  |NET| < MIN_NET (2)                 -> WAIT, basis "evidence", gate "thin-evidence"
GATE 3  NET >= +2 -> LONG      GATE 4  NET <= -2 -> SHORT

CONFIDENCE (R1', preserved)
        WAIT                     -> "Low"
        base: support >= 3 -> "High" ; support == 2 -> "Medium"
        cap:  opposing >= 1 -> one step down
STAGE 5 risk / execution vetoes -> lower readiness; MAY NEVER CHANGE d
```

Because `NET ≥ 2` forces `support ≥ 2`, this reduces to one publishable sentence:

> **High means at least three independent families agree and none disagrees.**

### 4.2 R1′ re-examined, not re-litigated

| Support | Oppose | NET | Grade | Reading |
|---|---|---|---|---|
| 3 | 0 | +3 | **High** | clean agreement |
| 2 | 0 | +2 | **Medium** | minimum publishable |
| 3 | 1 | +2 | **Medium** | mild dissent, narrow majority |
| 4 | 1 | +3 | **Medium** | **mild dissent, strong majority — the contested cell** |
| 4 | 2 | +2 | **Medium** | substantial opposition |
| 3 | 3 | 0 | **WAIT** | gate 2 |

**Mild vs substantial dissent** are already treated differently *before* the cap, because each
opposing family subtracts 1 from `NET` — two objections can push a call below `MIN_NET` into
`WAIT`, where one cannot. The cap adds a further single step, and is deliberately flat so that no
second tunable is introduced.

**The cap is retained.** `app/methodology/page.tsx:64` publicly states *"the confidence grade is
capped one step for it"*, and `app/api/signals/route.ts:48` publishes `confidenceIs: "evidence
grade"`. Retiring a published promise because an alternative is more elegant is not a sufficient
reason, and the alternative's cost is concrete: 4-against-1 would print `High` with no sign of the
objection in the headline.

**Clarifications the cap needs — wording, not mechanics:**
1. The methodology page says *"two or more of the five confirmations is High"*. Under the family
   path the bar is **three of five families with no dissent**. The published sentence must be
   updated **in the same change**, not after it.
2. The cap's trigger must be stated as *any opposing family*, not `peersAgainst` specifically,
   since it generalises from one family to five.
3. **Telemetry required for the cap to be auditable at all:** with only `legs` recorded, a capped
   `Medium` and an uncapped `Medium` are indistinguishable in the log. `opposing` (§4.3) is what
   makes the cap reviewable after the fact.

**Compatibility-preserving V1 design:** keep `confidence` and its published definition for the
existing leg path; ship the family path under a new **`logicVersion`**; update the methodology page
and the API `confidenceIs`/`minConfirmations` in the same commit; never redefine a stored grade's
meaning in place.

### 4.3 Persist vs derive

| Quantity | Decision | Reason |
|---|---|---|
| Supporting families | **PERSIST as names** — `DecisionLog.legs` *(exists)* | exists so *"something could be learned about whether a leg earns its place"* |
| Opposing families | **PERSIST as names** — `opposing` *(one new field)* | the only fact never recorded; required to audit the cap (§4.2) |
| Eligible families | **PERSIST** — `eligibleFamilies` | not derivable from the two name lists |
| Eligible-but-inconclusive | **DERIVE** = `eligible − |legs| − |opposing|` | |
| Unavailable / invalid | **DERIVE** — the complement of eligible; detail in `missing` | a `file` fact, **never a 0 vote** |
| Voting families | **DERIVE** = `|legs| + |opposing|` | |
| `NET` | **DERIVE** = `|legs| − |opposing|` | persisting it invites disagreement with its own inputs — the *"one count, two readers"* fault (`lib/decision.ts:703`) |
| `confidence` | **PERSIST, unchanged** + `logicVersion` | published contract |
| Historical model performance | **SEPARATE** — experiment artifacts, matured rows | never a per-decision field |
| Execution readiness | **SEPARATE** — `executionReadiness`, `timeSense` | never changes `d` |

`confidence` encodes **support count capped by dissent**, and the information the single grade
cannot carry lives in `legs` and `opposing` — which is why R2′ is load-bearing rather than
cosmetic.

### 4.4 Worked examples — one rule set throughout

**(a) Clean agreement**

| E1 | E2 | E3 | E4 | E5 |
|---|---|---|---|---|
| +1 | +1 | +1 | INELIG (peers 1) | INELIG (5 matches) |

`eligible 3 · NET +3 · support 3 · opposing 0` → **LONG / High** ·
`legs "trend,volume,volatility" | opposing ""`

**(b) Mixed votes**

| E1 | E2 | E3 | E4 | E5 |
|---|---|---|---|---|
| +1 | +1 | +1 | **−1** | 0 |

`eligible 5 · NET +2 · support 3 · opposing 1` → base High, capped → **LONG / Medium** ·
`legs "trend,volume,volatility" | opposing "peers"`
*With E3 at −1 instead:* `NET 0` → **WAIT, basis `evidence`**, gate `thin-evidence`, Low.

**(c) Low information** — FX: no volume → E2 INELIG; `peers 0` → E4 INELIG; 5 matches → E5 INELIG.

`eligible 2 · NET +2 (E1 +1, E3 +1)` → **GATE 1 fails** → **WAIT, basis `file`**, gate `file`, Low.
`NET` would have cleared `MIN_NET`; Gate 1 runs first so a coverage failure is never reported as
weak evidence.

**(d) Duplicate macro/news** — one FOMC decision:

| E1 | E2 | E3 | E4 | E5 | E7 | E8 |
|---|---|---|---|---|---|---|
| +1 | +1 | 0 | **0** | 0 | context | context |

E4 reads 0 because the whole peer group moved on the same announcement.
`eligible 5 · NET +2 · support 2 · opposing 0` → **LONG / Medium** · `legs "trend,volume"` ·
context records the rate move and the event id.
**Under V1.1 as written**, F5 and F6 each add +1 → `NET +4` → `High`: one cause as four
confirmations.

**(e) Strong majority, one objection** — the contested cell:

| E1 | E2 | E3 | E5 | E4 |
|---|---|---|---|---|
| +1 | +1 | +1 | +1 | **−1** |

`eligible 5 · NET +3 · support 4 · opposing 1` → base High (support 4), capped → **LONG / Medium**
· `legs "trend,volume,volatility,history" | opposing "peers"`

The four supporting names are in the record; the headline does not claim `High` over a recorded
contradiction. **Five-against-one is unreachable** under this taxonomy — with E7/E8 demoted there
are only five voting families.

---

## 5. Strongest counterarguments to my own recommendations

1. **Against Option 4:** the band is defined by `atr14`, which is a model feature. Dropping it
   costs a feature; keeping it ties the label to a predictor. Option 1 has neither problem and its
   only flaw is cross-class incomparability — which, for a single-asset-class study, would not
   matter at all.
2. **Against Option 4, second:** a horizon-independent band means `label60` is nearly binary
   (≈12–13% FLAT). If FLAT is meant to represent "not worth trading", a 60-session FLAT class that
   small may be the wrong shape for the question.
3. **Against withdrawing the effective-N range:** refusing to give a number leaves the owner with
   no planning figure at all. A clearly-labelled assumption-based range is arguably more useful
   than "unknown to three orders of magnitude" — provided nobody later quotes it as measured, which
   is exactly what happened to 442 and 1,327.
4. **Against E5 voting:** it is a third reading of the price series E1 and E3 already read, and
   admitting it contradicts the dependence principle used to demote E7/E8.
5. **Against R1′:** it compresses genuinely different evidential states onto `Medium`, and the
   grade is the field most readers actually look at.
6. **Against the whole programme:** none of this creates an edge. The measured model has none. A
   more rigorous aggregator over evidence with no demonstrated predictive value yields more
   defensible `WAIT`s, not better calls. That is the honest goal and should be said plainly.

---

## 6. Decision register

| Item | Status |
|---|---|
| Raw rows 1,085,544; mature = labelled; 616 instruments; 19-of-20 overlap | **AGREED** (verified) |
| `effectiveIndependentExamples = 54,277 = rows ÷ 20` is a **nominal** horizon-normalisation | **AGREED** |
| ρ, regime persistence and metric-specific effective N are **unmeasured** | **AGREED** |
| 7.2× FLAT spread across classes; FX 68% warning | **AGREED** (recorded in `readiness.json`) |
| `MIN_REWARD_RISK = 1.2`, `STOP_BUFFER_ATR = 1.0`; `confidence` published in API + methodology | **AGREED** (verified) |
| `MIN_FAMILIES = 3` (0-votes included), `MIN_NET = 2`, no `MIN_VOTERS` | **AGREED** |
| **161–19,876 range** | **WITHDRAWN** — 19,876 internally inconsistent; 161 assumption-driven |
| **Option 3 with `k₀ = 1.0`** | **WITHDRAWN** — imposes the documented 68%-FLAT defect on every asset |
| 442 / 1,327; "measure ρ first"; R1″ | **WITHDRAWN** in earlier rounds; not reopened |
| Only raw counts + qualitative dependence warnings are supportable | **PROPOSED** |
| Block bootstrap over date blocks ≥ horizon + maturity | **PROPOSED** |
| **Option 4**: `band = 1.2 × atr14_t`, with `label60_fixed` as control | **PROPOSED** |
| Drop `atr14` from features for `label60` experiments | **PROPOSED** |
| 60-session purge; raw rows and bootstrap interval reported separately | **PROPOSED** |
| **R2′** persist `opposing`; derive the rest | **PROPOSED** |
| **R3″** only asset-specific evidence votes (F5 → veto-only) | **PROPOSED** |
| **R4** retire `τ`; E1 requires both signals | **PROPOSED** |
| **R1′** cap retained, wording and telemetry clarified | **PROPOSED** |
| `logicVersion`; methodology page + API updated in the same change | **PROPOSED** |
| **E5 `history` votes** | **DISPUTED** |
| Within-asset reuse across E1 / E3 / E5 | **DISPUTED — open**, unresolved by anything here |
| Withholding an effective-N figure entirely | **DISPUTED** (counterargument 3) |

---

## 7. Remaining owner choices

| # | Choice | Recommendation |
|---|---|---|
| 1 | `label60` **approved for exploratory research** (not deferred, not rejected)? | **Approve** |
| 2 | **Option 4** (`1.2 × atr14_t`) as primary, with `label60_fixed` as declared control? | **Yes** |
| 3 | Drop `atr14` from the feature set for `label60`, or document the dependence? | **Drop** |
| 4 | Block bootstrap, and **no** single effective-N figure published? | **Yes** |
| 5 | **R1′** cap retained, with the methodology page updated in the same change? | **Yes** |
| 6 | **R2′** persist `opposing`? | **Yes** |
| 7 | **R3″** only asset-specific evidence votes? | **Yes** |
| 8 | **R4** retire `τ`? | **Yes**, subject to the replay test |
| 9 | Does **E5 `history`** vote, or modulate confidence as a prior? | **Votes**, measured later |
| 10 | `logicVersion` rather than redefining `confidence` in place? | **Yes** |

---

## 8. Confirmation

- **No file, specification, code, dataset, label, test, training artifact or deployment modified.**
- `BRAIN-SPEC-V1.md` unmodified; `data/foundation/dataset/` unmodified; working tree clean of
  tracked changes against `eb0f276`.
- `label60` does not exist. ρ not measured. No bootstrap run. No model fit, tuned or evaluated.
- Benchmark CSVs were **read only**; the volatility figures in §2.2 are computed in memory from
  already-stored files and written nowhere.
- The only new file is this review. **No specification will be edited and no implementation begun
  until choices 1–10 are settled by explicit agreement.**
