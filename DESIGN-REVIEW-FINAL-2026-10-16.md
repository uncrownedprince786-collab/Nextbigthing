# Final Design Review — Effective Sample Size, `label60`, and the Confidence Contract

**Status:** read-only. Nothing edited, generated, trained, evaluated or deployed.
**Head:** `eb0f276`. **New sources read this round:** `data/foundation/dataset/readiness.json`,
`app/api/signals/route.ts`, `app/methodology/page.tsx`, `tools/scorecard.py`, `jobs/confidence.py`,
`tools/make_dataset.py:82-138`.

Two of this round's findings reverse Round 3. One of them is a **reversal of a reversal**, made on
evidence I had not read before.

---

## 1. Effective sample size

### 1.1 How each figure was derived

| Figure | Derivation | Status |
|---|---|---|
| **54,277** | `1,085,544 ÷ 20` | **Recorded in `readiness.json`** as `effectiveIndependentExamples`, with the note *"rows / 20… any confidence interval must use the effective figure"*. It is a project artifact, not something these reviews introduced. |
| **17,478** | `1,048,726 ÷ 60` | Round 1. Same method, applied to an **estimated** `label60` row count. |
| **1,327 / 442** | `(2190 ÷ h) × Σ_class n/(1+(n−1)ρ)` with ρ = 0.4 | **Round 3. Not reproducible — see §1.3.** |

**"Effective window" means the same thing in both documented figures:** raw rows divided by the
label horizon, i.e. the number of *non-overlapping outcome windows* the rows could at most
represent. `readiness.json` states the overlap it corrects for exactly:
*"consecutive rows for one instrument share 19 of their 20 forward sessions."*

### 1.2 What the artifacts actually support

| Quantity | Value | Source |
|---|---|---|
| `label20` raw rows | **1,085,544** | `readiness.json` |
| Instruments | **616** | `readiness.json` |
| Median rows per instrument | **1,936** | `readiness.json` |
| Date range | 2018-01-01 → 2026-09-24 | `readiness.json` |
| Exact duplicate rows / identical feature vectors | 0 / 0 | `readiness.json` |
| Assets **by market** | US 280, PK 226, FX 27 (= 533 of 616) | `readiness.json` |
| Assets **by asset class** | **NOT RECORDED** | — |
| Cross-sectional correlation ρ | **NOT RECORDED, NOT MEASURED** | — |
| `label60` rows | **1,048,726 — a Round-1 estimate, never independently recomputed**, and an **upper bound** (it required 60 *forward* sessions only; a volatility-normalised band also needs 60 *trailing* sessions) | Round 1 |

Non-overlapping windows from the recorded median, rather than from a calendar guess:

```
h = 20 :  1,936 / 20 = 96.8 windows per asset  ->  x 616 = 59,629
h = 60 :  1,936 / 60 = 32.3 windows per asset  ->  x 616 = 19,876
```

These bracket the documented 54,277 and 17,478 and confirm the arithmetic of both.

### 1.3 Required conclusion on 442 and 1,327

**They are not reproducibly derived. They are illustrative at best, and two of their inputs were
assumed rather than measured.**

1. **ρ = 0.4 was asserted, not estimated.** No correlation estimator was run; no input sample,
   period, missing-data treatment or asset-class breakdown exists, because no estimate exists.
2. **The per-class asset counts (450/60/40/30/36) were invented by me** to sum to 616.
   `readiness.json` records assets **by market**, not by class, and those three markets account
   for only 533 of the 616 instruments.
3. **The method multiplied two separable adjustment factors** — a temporal factor
   (`sessions ÷ horizon`) and a cross-sectional design effect — without justifying that the two
   dependence structures are separable. You flagged exactly this, and the objection stands.
4. **Per-class `n_eff` values were summed**, which assumes asset classes are mutually
   uncorrelated. Equities and ETFs are near-duplicates of one another; that assumption is false.
5. **The design effect was applied to the wrong quantity.** `N_eff = N/(1+(N−1)ρ)` is the
   variance inflation for **the mean of an equicorrelated sample**. The relevant quantity for a
   classification result is the variance of an accuracy estimate, which depends on the
   correlation of **prediction errors**, not of returns. They are related; they are not the same
   number, and substituting one for the other is not justified.

**Assumptions of `N_eff = N/(1+(N−1)ρ)`:** equal variance across units, equal pairwise
correlation between every pair, and a linear statistic (a mean). On this panel all three fail —
volatility differs by orders of magnitude across classes, correlation is block-structured by
sector and class, and the statistic of interest is not a mean.

### 1.4 What can be said without estimating ρ

Bounds, using only the recorded median and instrument count:

| Horizon | Upper bound (zero cross-correlation) | If the 5 asset classes behave as 5 blocks | Floor (one common factor) |
|---|---|---|---|
| 20 | **59,629** | 484 | 97 |
| 60 | **19,876** | 161 | 32 |

**The true effective sample lies somewhere in a two-order-of-magnitude range, and that range
spans "comfortably validatable" and "not validatable at all."** That is the honest statement.
The *direction* of Round 3's correction is certain — 54,277 and 17,478 are upper bounds that
assume zero cross-asset dependence, which is plainly false. Its *magnitude* was manufactured.

### 1.5 The recommended methodology — stop estimating ρ

Round 3 recommended "measure ρ first". **I withdraw that too.** Decomposing dependence into a
temporal factor and a cross-sectional factor is what produced the unjustified multiplication in
the first place. The dependence-aware alternative needs no ρ at all:

> **Block bootstrap over dates, resampling the whole cross-section.** Draw contiguous blocks of
> trading dates of length ≥ 2 × horizon; for each drawn date, take **every** asset's row for that
> date. Temporal dependence is preserved by the block length; cross-sectional dependence is
> preserved exactly, because the cross-section is never broken apart. The confidence interval
> falls out of the bootstrap distribution directly, and "effective sample size" never has to be
> named as a number.

This is **proposed as the later evaluation method**; nothing was run here.

### 1.6 The three claims, kept apart

| Claim | Verdict |
|---|---|
| "`label60` should be abandoned" | **Not supported.** The evidence does not establish that validation is infeasible — it establishes that nobody has measured whether it is. |
| "`label60` is an acceptable exploratory research target" | **Supported**, conditional on §2 specifying it coherently and §2.6 pre-registering it. |
| "Position-horizon validation is likely feasible" | **Not supported, and currently not assessable.** With a plausible range of 161–19,876 effective observations, feasibility is unknown. Anyone asserting it is feasible is asserting ρ they have not measured. |

**Recommendation: proceed as an exploratory research target.** Not abandonment, and explicitly
not a prediction of success.

---

## 2. D9 — the `label60` definition

### 2.1 Verified mechanics of `label20`

```
tools/make_dataset.py
  HORIZONS = (1, 5, 20) ; WINDOW = max(HORIZONS) = 20 ; LABEL_THRESHOLD_PCT = 2.0
  base         = each asset's newest close ON OR BEFORE as_of           (base_closes)
  forward_bars = up to WINDOW sessions STRICTLY AFTER as_of, oldest first, close IS NOT NULL
  fwd20        = (closes[19] / base - 1) * 100
  label20      = UP if fwd20 >= +2.0 ; DOWN if <= -2.0 ; else FLAT
  mature20     = fwd20 is not None
```

Two things this settles that column names could not: the as-of close is **excluded** from the
forward window (so a zero-session return cannot masquerade as a one-session one), and the
endpoint is the **20th stored session with a non-null close**, not a calendar date. A `label60`
requires `WINDOW = 60`, which changes the dataset query itself.

### 2.2 The evidence that decides between candidates — already in the repository

`readiness.json → labelBalanceByClass` records what the fixed band does:

| class | rows | UP | FLAT | DOWN |
|---|---|---|---|---|
| stock | 903,427 | 0.439 | 0.178 | 0.383 |
| crypto | 96,953 | 0.401 | **0.095** | 0.503 |
| forex | 54,163 | 0.177 | **0.680** | 0.142 |
| commodity | 15,511 | 0.447 | 0.205 | 0.348 |
| etf | 15,490 | 0.440 | 0.242 | 0.318 |

and carries the project's own warning: *"the fixed 2% band is not volatility-scaled and collapses
68% of FX into FLAT; FX direction classification is weakly supported by this label."*

**A 7.2× spread in `FLAT` share across classes, already documented before these reviews began.**
This is not my finding; it is the project's, and it is the strongest argument against carrying a
fixed band to 60 sessions, where dispersion is larger and the distortion worse.

### 2.3 Candidate comparison

Common to all three: as-of timestamp = `asOf`; base = newest close ≤ `asOf`; endpoint = the 60th
stored session with a non-null close **strictly after** `asOf`; `fwd60 = (closes[59]/base − 1)×100`;
`mature60 = fwd60 is not None`; immature rows **excluded, never labelled FLAT**; corporate actions
excluded via `dataQuality.basisBreakInWindow` over the forward window (and, for Option 2, over the
trailing window as well — **which does not exist today**); delisting ends the series, so the final
60 sessions drop out with no synthetic terminal value.

| | **Option 1 — fixed ±2%** | **Option 2 — PIT vol-normalised** | **Option 3 — training-distribution** |
|---|---|---|---|
| Band | `2.0%` | `max(k·σ_t·√60, 2.0%)` | quantile of training outcomes |
| UP means | gained > 2% in 60 sessions | moved > k sd of **its own** typical 60-session move | fell in the upper part of a past period's distribution |
| Threshold available at `t`? | yes, trivially | **yes** — σ from closes ≤ `t` | only if frozen from a prior period and never recomputed |
| Cross-class behaviour | **fails** — 7.2× FLAT spread, worse at 60 | comparable by construction | fails unless per-asset, and per-asset it collapses to rank |
| Across vol regimes | directional classes inflate in crises | band widens with vol — stable | drifts with the training era |
| Main failure mode | becomes a **volatility classifier**: a model scores by inferring asset class | σ_t can be overtaken by a regime break just after `t`; band depends on a quantity that may also be a feature | **no financial meaning**; non-stationary target; engineers its own baseline |
| Selection risk | none | `k` must be pre-registered | **high** — invites balance-chasing |

**Option 3 stays retracted.** A convenient `FLAT` share is not evidence of financial meaning.

### 2.4 The √t assumption — qualified, not assumed

`σ_t·√60` scales a daily standard deviation to 60 sessions. That is exact only for i.i.d. returns.
On this data it is not exact:

- **Serial dependence.** `Var(Σ₆₀) = 60·σ² · (1 + 2·Σₖ(1 − k/60)·ρₖ)`. Any momentum or
  mean-reversion makes the multiplier ≠ 60. √t is the special case `ρₖ = 0 ∀k`.
- **Volatility clustering.** Trailing realised vol is autocorrelated and mean-reverting, so σ_t
  systematically under-forecasts after calm periods and over-forecasts after stress — and √60
  magnifies the error.
- **Fat tails.** √t scaling of the *standard deviation* survives non-normality (given finite
  variance); the implied *quantile* does not. The UP share at a given `k` will not match the
  normal-theory figure.
- **Missing sessions.** Counting in stored sessions keeps σ and the window on the same clock;
  calendar-day counting would not.

**Why this does not invalidate Option 2:** the band is a **definition of the target**, not an
estimate of a distribution. √t imperfection does not make a labelled row wrong — it makes the UP
rate less perfectly comparable across assets and regimes than the idealisation suggests. That
residual comparability error must be **reported**, not assumed away.

**Option 2b, the assumption-free variant** — set `σ₆₀` directly from the dispersion of **trailing
60-session returns** (closes ≤ `t`), with no √t scaling at all. Cleaner, but it needs years of
history per asset and overlapping windows make it noisy, so it would cut eligible rows sharply.
**Recommended as the pre-registered sensitivity check, not the primary.**

### 2.5 Recommendation

**Primary: Option 2, `k₀ = 1.0`, σ from 60 trailing sessions of daily log returns, floor
`LABEL_THRESHOLD_PCT = 2.0`** (the project's existing frozen constant — no new number invented;
the band degenerates to `label20`'s exactly when volatility is negligible).

`UP` = "moved more than one standard deviation of its own typical 60-session move, upward." That
meaning is identical in 2018 and 2026 and identical for a Karachi small-cap and for BTC. **`k₀` is
chosen for that interpretability, not for the class balance it produces.** The resulting `FLAT`
share is reported, whatever it is; a high `FLAT` share makes the majority-class baseline hard to
beat, which is an honest difficulty and **not** grounds to move `k`.

**Plus a declared control: `label60_fixed` at ±2%.** `label20` is fixed-band and frozen; comparing
a vol-normalised `label60` against it confounds *horizon* with *band definition*. Building both,
both pre-registered and both reported, is the only way to attribute a difference to the horizon.
This is not multiplying comparisons — it is the control that makes the primary interpretable.

### 2.6 Pre-registered protocol (written and frozen **before** the label is built)

1. `k₀ = 1.0`, σ lookback = 60 trailing sessions, floor = 2.0%, declared now.
2. **Sensitivity:** `k ∈ {0.5, 0.75, 1.0, 1.25, 1.5}` and Option 2b evaluated on **training and
   validation folds only**; the held-out fold scored **once, at `k₀`**; grid and headline
   published together.
3. **Redundancy kill switch:** cross-tabulate `label60` against `label20` on shared rows, and
   separately test how well `fwd20` plus `σ_t` alone recover `label60`. If either shows high
   concordance, `label60` is a relabelling — stop before fitting a model. Neither test touches a
   held-out outcome or fits anything.
4. **Purge of 60 sessions** at every fold boundary (not the current 20 — a 20-session embargo on a
   60-session label leaks 40 sessions of every boundary row by construction). Walk-forward,
   chronological, no shuffling.
5. **Report raw rows and a dependence-aware interval separately**, the latter from the §1.5 block
   bootstrap. Never quote a row count as a sample size.
6. **Multiple-comparison policy written before a second horizon exists.** V1.1 has none.
7. Acceptance conditions for a *claim*: margin over majority class exceeds the bootstrap interval;
   holds on the worst fold; no collapse to one class; leakage 0; **both horizons published
   together, never whichever looks better.**

**Approve `label60` as a research target.** The target definition, eligibility policy and
validation plan above are coherent and complete, which was your stated condition. Whether a
position-horizon capability can be *claimed* remains entirely open and is deliberately not
decided here.

---

## 3. The `NET`, dissent and `confidence` contracts

### 3.1 The evidence that reverses Round 3

`confidence` is not an internal field. It is a **published contract**:

- `app/api/signals/route.ts:48` ships `confidenceIs: "evidence grade"` in the public rules block.
- `app/methodology/page.tsx:276` publicly states the rule: *"two or more of the five confirmations
  is High, one is Medium. It says nothing about results."*
- `app/methodology/page.tsx:64` publicly states **the cap**: *"the confidence grade is capped one
  step for it."*
- ~13 UI/API surfaces and `tools/scorecard.py` (`SELECT … d.confidence …`) consume it.
- A separate `jobs/confidence.py` grades `Ranking.confidence` and `Product.confidence` — a
  different namespace that must not be conflated.

**Round 3's R1″ retired a cap that the product publicly promises.** I had not read the methodology
page when I recommended it. **I withdraw R1″ and restore R1′.**

### 3.2 R1′ restored — and why it is not excessively punitive

Under the recommended taxonomy a direction requires `NET ≥ 2`, which forces `support ≥ 2`. So:

```
base       = "High"   if supportFamilies >= 3
             "Medium" if supportFamilies == 2
confidence = (opposingFamilies >= 1) ? oneStepDown(base) : base
WAIT       -> "Low"                                          [shipped behaviour]
```

which collapses to one sentence:

> **High means at least three independent families agree and none disagrees.**

That is crisper than R1″'s `|NET| ≥ 3`, it preserves a published promise, and it never prints
`High` over a recorded contradiction.

**Your two tests, answered directly:**

- *Is a blanket cap excessively punitive when a strong majority faces one objection?* It costs one
  step — 4-against-1 grades `Medium`, as does 2-against-0. **The grade collides; the record does
  not.** `legs` holds four names in the first case and two in the second. A three-level grade
  cannot carry four-plus states, and inflating it to try is the fake precision this project
  exists to avoid.
- *Can removing the cap conceal material contradictory evidence?* **Yes — that is the decisive
  point.** Under R1″, 4-against-1 publishes `High`, and a reader scanning grades sees no sign of
  the objection. Rule 6 exists precisely to forbid that, and the methodology page promises it.

**Counterargument (the strongest against R1′, and it is real):** the cap makes `High` relatively
rare and compresses genuinely different evidential states onto `Medium`. If you weight
proportionality above the published no-false-confidence promise, R1″ is defensible. **Marked
DISPUTED; the call is yours.**

### 3.3 Confidence contract — explicit decision

**`confidence` keeps its published meaning: a confirmation-count grade with a one-step opposition
cap. It is NOT silently redefined.** A family-based decision path is a *different logic*, and if
it ships it must be versioned, not substituted:

- every `DecisionLog` row carries a **`logicVersion`**, so leg-path and family-path rows are
  separable and `tools/scorecard.py` never averages two different meanings;
- `app/methodology/page.tsx` and the `confidenceIs` field in the API are updated **deliberately
  and in the same change**, never after the fact;
- historical rows keep their meaning. Redefining a published grade in place would leave the stored
  values intact while silently changing what they mean — breaking the immutability invariant in
  effect if not in letter.

**Downstream contracts that must change together, enumerated:** `lib/decision.ts` (`confidenceFor`,
`confirmingLegs`, `LEGS`), `prisma/schema.prisma` (`DecisionLog.confidence`, `legs`, plus new
`opposing` and `logicVersion`), `app/api/signals/route.ts` (`confidenceIs`, `minConfirmations`),
`app/methodology/page.tsx` (both the count rule and the cap), `components/decision.tsx`,
`components/ui.tsx`, `components/topByClass.tsx`, `components/weeklyFocusBlock.tsx`, the six `app/`
pages that render a grade, and `tools/scorecard.py`.

**`confidence` is an evidence grade and never a probability of success.** No calibration has been
demonstrated; the one measured model has no edge.

### 3.4 Persist / derive / separate

| Quantity | Decision | Reason |
|---|---|---|
| Supporting evidence | **PERSIST as names** — `DecisionLog.legs` (**exists**) | `legs` exists so *"something could be learned about whether a leg earns its place"*; a count cannot answer that |
| Opposing evidence | **PERSIST as names** — `opposing` (**one new field**) | the only fact the log has never recorded; load-bearing for everything above |
| Eligible-family count | **PERSIST** — `eligibleFamilies` | not derivable from the two name lists |
| Voting-family count | **DERIVE** = `|legs| + |opposing|` | redundant |
| Abstaining-family count | **DERIVE** = `eligible − voting` | redundant |
| `NET` | **DERIVE** = `|legs| − |opposing|` | redundant; persisting it invites it to disagree with its own inputs — the *"one count, two readers"* fault `lib/decision.ts:703` names |
| `confidence` | **PERSIST, unchanged** (+ `logicVersion`) | published contract (§3.3) |

All derived aggregates are exactly reproducible from the three persisted facts.

### 3.5 The eight distinctions, kept separate

| Concept | Where it lives | Never |
|---|---|---|
| Support for the direction | `legs` | — |
| Opposing directional evidence | `opposing`, `notes` | not folded into support |
| Eligible independent families | `eligibleFamilies` | not conflated with either |
| Inconclusive but valid | vote `0`; counts toward `MIN_FAMILIES` | never `INELIGIBLE` |
| Unavailable / stale / invalid | `INELIGIBLE`; `missing`; `basis: "file"` | **never a `0` vote** |
| Directional evidence grade | `confidence` | never a probability |
| Historical predictive performance | experiment artifacts; matured `DecisionLog` rows | never a per-decision field |
| Execution readiness | `executionReadiness`, `timeSense`, Stage-5 vetoes | never changes direction |

### 3.6 Evidence taxonomy (carried from Round 3, unchanged)

Governing rule: **only asset-specific evidence may vote; market-wide evidence may withhold,
qualify or inform, but never votes.** This is already the shipped design —
`lib/decision.ts:460` says of `macroVeto` that it is *"A veto only… can do nothing else."*

| Canonical | V1.1 | Leg | Class | Role |
|---|---|---|---|---|
| E1 trend | F1 | `timeframe` | derived, own price | **VOTE** |
| E2 participation | F2 | `volume` | derived, own volume | **VOTE** (ineligible where unpublished — FX) |
| E3 volatility | F3 | *none* | derived, own price | **VOTE** |
| E4 cross-sectional | F4 | `peers` | derived, peer prices | **VOTE** (strips the common factor by design) |
| E5 history | *none* | `history` | historical prior, own past outcomes | **VOTE** (floors 8/20/40 in `jobs/analogs.py`) |
| E6 trigger | *none* | `trigger` | raw event, own series | **TIMING** → `timeSense` |
| E7 macro | F5 | — | contextual, market-wide | **CONTEXT + VETO** |
| E8 event/news | F6 | — | contextual, dated items | **CONTEXT only** |

E7 and E8 never vote, so one monetary event cannot become two confirmations — **deduplication is
structural; no event-id matching is needed.** Nothing is suppressed: E7 can veto to `WAIT`, E8
populates `notes`/`missing`, both are recorded with provenance. **Residual within-asset
correlation (E1, E3 and E5 all read one price series) is real, is not solved here, and must be
measured once E3 and E5 are wired.**

### 3.7 The gate

```
votingSet        = {E1..E5}
eligibleFamilies = eligible members of votingSet            (0-votes INCLUDED)
NET = Σ vote_i ;  d = sign(NET) ;  support = |vote = d| ;  opposing = |vote = -d|

GATE 1  eligibleFamilies < 3  -> WAIT, basis "file",     gate "file"
GATE 2  |NET| < 2             -> WAIT, basis "evidence", gate "thin-evidence"
GATE 3  NET >= +2 -> LONG        GATE 4  NET <= -2 -> SHORT
CONFIDENCE (R1')  WAIT -> Low ; base by support (>=3 High, ==2 Medium) ; cap one step if opposing >= 1
STAGE 5  risk/execution vetoes -> lower readiness; MAY NEVER CHANGE d
PERSIST  eligibleFamilies, legs, opposing, confidence, logicVersion
```

`MIN_FAMILIES = 3` counts eligible families **including those voting 0**, because it measures how
much of the file is readable — a coverage question, distinct from decisiveness, which is why the
two gates emit different bases. `MIN_NET = 2` stays absolute: scaling it with `eligibleFamilies`
would make richer coverage face a *higher* bar for identical evidence. **No new threshold is
added, and `MIN_VOTERS` is declined** — case 3 below shows why it is unnecessary.

---

## 4. Worked cases

All six use §3.7 unchanged. Votes are E1–E5; E6 timing; E7/E8 context.

### Case 1 — three eligible families support LONG, no dissent

| | E1 | E2 | E3 | E4 | E5 | E7 | E8 |
|---|---|---|---|---|---|---|---|
| state | ELIG | ELIG | ELIG | **INELIG** (peers 1) | **INELIG** (5 matches < 8) | no veto | none |
| vote | **+1** | **+1** | **+1** | — | — | n/a | n/a |

```
eligible 3   NET +3   support 3   opposing 0   abstaining 0
GATE 1 3>=3 pass   GATE 2 3>=2 pass   -> LONG
base: support 3 -> High ; opposing 0 -> no cap  ->  HIGH
PERSIST  eligibleFamilies 3 | legs "trend,volume,volatility" | opposing ""
```

**`LONG` / `High`.** Confidence means: three independent families agree, none disagrees.

### Case 2 — mixed LONG/SHORT

| | E1 | E2 | E3 | E4 | E5 |
|---|---|---|---|---|---|
| vote | **+1** | **+1** | **+1** | **−1** | **0** (eligible, inconclusive) |

```
eligible 5   NET +2   support 3   opposing 1   abstaining 1   -> LONG
base High (support 3) ; opposing 1 -> capped  ->  MEDIUM
PERSIST  legs "trend,volume,volatility" | opposing "peers" ; notes "peers argue the other way"
```

**`LONG` / `Medium`.** **2b:** make E3 `−1` → `NET 0` → **`WAIT`, basis `evidence`**, gate
`thin-evidence`, `Low`. Evidence was present and did not decide.

### Case 3 — two LONG votes plus one eligible-but-inconclusive family

| | E1 | E2 | E3 | E4 | E5 |
|---|---|---|---|---|---|
| state | ELIG | ELIG | **ELIG** | INELIG | INELIG |
| vote | **+1** | **+1** | **0** | — | — |

```
eligible 3 (the 0-vote counts)   NET +2   support 2   opposing 0   abstaining 1
GATE 1 3>=3 pass   GATE 2 2>=2 pass   -> LONG
base: support 2 == MIN_NET -> Medium ; no cap  ->  MEDIUM
PERSIST  eligibleFamilies 3 | legs "trend,volume" | opposing ""
```

**`LONG` / `Medium`.** This is the `(+1,+1,0)` case. It publishes on two opinions, and
`eligibleFamilies 3` against `legs` of length 2 makes that visible in the record — which is why
**no `MIN_VOTERS` threshold is needed.**

### Case 4 — low information

An FX pair: no published volume → E2 `INELIGIBLE` (**never 0**); `peers 0` → E4 `INELIGIBLE`;
5 matched days → E5 `INELIGIBLE`.

```
eligible 2   NET +2   (E1 +1, E3 +1)
GATE 1  2 < 3  ->  WAIT, basis "file", gate "file", confidence "Low"
missing  "volume not published" | "fewer than 3 peers" | "fewer than 8 matched days"
```

**`WAIT`, basis `file`.** `NET = +2` **would have cleared `MIN_NET`** — Gate 1 runs first
precisely so a coverage failure is never reported as weak evidence.

### Case 5 — five supporting versus one opposing

**This case is unreachable under the recommended taxonomy, and that is worth stating rather than
fudging.** With E7/E8 demoted to context there are only **five** voting families, so six voters
cannot occur. Both the realisable case and the V1.1 case:

| Variant | support | oppose | NET | R1′ (recommended) | R1″ (Round 3) |
|---|---|---|---|---|---|
| **4 vs 1** (max under E1–E5) | 4 | 1 | +3 | **Medium** | High |
| **5 vs 1** (only if F5 votes, as V1.1 allows) | 5 | 1 | +4 | **Medium** | High |

```
4-vs-1 worked:  E1 +1  E2 +1  E3 +1  E5 +1  E4 -1
eligible 5   NET +3   support 4   opposing 1   -> LONG
base High (support 4) ; opposing 1 -> capped  ->  MEDIUM
PERSIST  legs "trend,volume,volatility,history" | opposing "peers"
```

**This is exactly the case where R1′ and R1″ disagree**, and it is the one your challenge
targeted. R1′ grades it `Medium` and names the objection; R1″ would publish `High` over a recorded
contradiction, which `app/methodology/page.tsx:64` promises not to do. The four supporting names
are in `legs`, so the strength is preserved in the record, not in the headline.

### Case 6 — one monetary event in both macro and news

| | E1 | E2 | E3 | E4 | E5 | E7 macro | E8 event |
|---|---|---|---|---|---|---|---|
| state | ELIG | ELIG | ELIG | ELIG | ELIG | context | context |
| vote | **+1** | **+1** | **0** | **0** | **0** | **never** | **never** |

E4 reads `0` because the whole peer group moved on the same announcement — relative strength
strips the common factor automatically, without being told about the event.

```
eligible 5   NET +2   support 2   opposing 0   abstaining 3   -> LONG
base: support 2 -> Medium ; no cap  ->  MEDIUM
PERSIST  legs "trend,volume" | opposing ""
CONTEXT  macro: policy-rate move (PIT, publicationLagDays applied) | event: FOMC <eventId>, retained
```

**Under V1.1 as written**, F5 and F6 each add `+1` (F6 is permitted because F1 already supports the
direction) → `NET +4` → `High`: **one cause presented as four confirmations.** Here it is `+2` /
`Medium`, with both the macro move and the event retained and attributed. Nothing suppressed,
nothing double-counted.

---

## 5. Invariants

| Invariant | Status |
|---|---|
| Vetoes withhold, never force or invert | **Preserved** — Stage 0 sets only `INELIGIBLE`; Stage 5 cannot change `d` |
| Missing/stale/invalid is not a neutral vote | **Preserved** — Case 4; matches shipped `newsCoverage: "unavailable"` |
| Correlated indicators are not independent confirmations | **Strengthened** (E7/E8 cannot vote); **E1/E3/E5 within-asset overlap remains open** |
| News cannot force a directional call | **Strengthened** — arithmetically impossible, not merely guarded |
| PSX bearish research valid while execution blocked | **Preserved** — D7 untouched |
| No look-ahead from outcomes or retrospective regimes | **Preserved and tightened** — §2.3 adds a trailing-window corporate-action exclusion that does not exist today |
| Decisions and evidence snapshots immutable | **Preserved and strengthened** — §3.3 refuses to redefine a published grade in place; `logicVersion` instead |
| No calibrated win probability without out-of-sample validation | **Preserved** — §3.3; `confidence` is never rendered as a percentage |
| A decision must not be forced merely to avoid WAIT | **Preserved** — Cases 2b and 4 both resolve to `WAIT` |

---

## 6. Decision register

| Item | Status |
|---|---|
| `label20` mechanics; `WINDOW = 20`; as-of excluded from forward window | **AGREED** (verified in source) |
| `effectiveIndependentExamples = 54,277 = rows/20` | **AGREED** (recorded in `readiness.json`) |
| 7.2× `FLAT` spread across classes; FX warning | **AGREED** (recorded in `readiness.json`) |
| `confidence` = count grade + one-step cap; published in API and methodology page | **AGREED** (verified) |
| `MIN_FAMILIES = 3` (0-votes included), `MIN_NET = 2` absolute, no `MIN_VOTERS` | **AGREED** |
| Zero vote ≠ unavailable | **AGREED** (already correct in V1.1 §3.2) |
| **442 / 1,327** | **WITHDRAWN — not reproducible** (§1.3) |
| "Measure ρ first" (Round 3) | **WITHDRAWN** — replaced by block bootstrap (§1.5) |
| **R1″** net-graded confidence | **WITHDRAWN** — retires a published promise (§3.1) |
| **R1′** restored: support grade + one-step cap | **PROPOSED** — *also* **DISPUTED**: compresses states onto `Medium` |
| Effective sample is bounded, not known; 161–19,876 at h=60 | **PROPOSED** |
| Block bootstrap over date blocks ≥ 2×horizon | **PROPOSED** |
| Option 2, `k₀ = 1.0`, σ over 60 trailing sessions, 2.0% floor | **PROPOSED** |
| `label60_fixed` ±2% as a declared control | **PROPOSED** |
| 60-session purge; raw rows and bootstrap interval reported separately | **PROPOSED** |
| **R2′** persist `opposing`; derive voting/abstaining/`NET` | **PROPOSED** |
| **R3″** only asset-specific evidence votes (F5 → veto-only) | **PROPOSED** |
| **R4** retire `τ`; E1 requires both signals | **PROPOSED** |
| E5 `history` votes | **DISPUTED** — best-audited evidence, but shares E1's price series |
| `logicVersion` stamp; methodology page and API updated in the same change | **PROPOSED** |
| Residual E1/E3/E5 within-asset correlation | **DISPUTED — open**, unresolved by anything here |
| `k₀ = 1.0` vs `0.5` | **DISPUTED** |

---

## 7. Remaining owner decisions

| # | Decision | Recommendation |
|---|---|---|
| 1 | `label60` as an **exploratory** research target — not a feasibility claim? | **Yes** |
| 2 | Option 2 band, `k₀ = 1.0`, with `label60_fixed` as the declared control? | **Yes** |
| 3 | Block bootstrap over date blocks, abandoning the ρ estimate entirely? | **Yes** |
| 4 | **R1′ or R1″** — cap retained (never `High` over a contradiction) or proportional grading? | **R1′** |
| 5 | **R2′** — persist `opposing`, derive the rest? | **Yes** |
| 6 | **R3″** — only asset-specific evidence votes? | **Yes** |
| 7 | **R4** — retire `τ`? | **Yes**, subject to the replay test |
| 8 | Does E5 `history` vote, or is it a reported prior? | **Votes** |
| 9 | Version the family path with `logicVersion` and update the methodology page and API in the same change, rather than redefining `confidence` in place? | **Yes** |

---

## 8. Confirmation

- No file edited; no specification revised; `BRAIN-SPEC-V1.md` unmodified.
- No label generated, no dataset altered, `label60` absent, ρ **not** measured, no bootstrap run.
- No code, training, evaluation, tuning or deployment. All experiment artifacts preserved.
- The only new file is this review. **No revised specification will be produced until decisions
  1–9 are settled by explicit agreement.**
