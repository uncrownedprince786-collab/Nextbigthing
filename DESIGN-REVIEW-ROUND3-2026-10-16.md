# Design Review Round 3 — Resolving D9, D10 and R1–R4

**Status:** read-only. No file edited, no code, no dataset change, no label, no training, no deployment.
**Head:** `eb0f276`. **Inputs:** `BRAIN-SPEC-V1.md` (V1.1), `DESIGN-REVIEW-2026-10-16.md` (R1),
`DESIGN-REVIEW-ROUND2-2026-10-16.md` (R2), `lib/decision.ts`, `prisma/schema.prisma`,
`jobs/analogs.py`, `tools/make_dataset.py`, `tools/full_history.py`.

Round 3 overturns **four** of my own prior conclusions. Three were overturned by your challenges,
which were correct. One was overturned by arithmetic I should have done in Round 1.

---

## 0. Corrections carried into this round

| # | Prior claim | Status |
|---|---|---|
| 0.1 | Round 2: match the `FLAT` share on training rows | **RETRACTED** — your challenge is right (§1.3) |
| 0.2 | Round 2: `R1′` one-step opposition cap | **RETRACTED** — too blunt; replaced by `R1″` (§3.1) |
| 0.3 | Round 2 Finding B: F1/F5 dependence "unsolved" | **RETRACTED** — it is solved structurally (§4.3) |
| 0.4 | Round 1: 17,478 effective independent windows | **WRONG BY 11–58×** (§1.2) |

### 0.4 is the most consequential thing in this review

`rows ÷ horizon` treats 616 assets as 616 independent series. They are not. Correcting for
cross-sectional correlation with the standard effective-sample formula
`n_eff = n / (1 + (n−1)ρ)`, over 2,190 sessions (≈36.5 non-overlapping 60-session windows):

| Assumed ρ | Effective independent assets (all 616) | Effective observations | Overstatement vs 17,478 |
|---|---|---|---|
| 0.1 | 42.4 | **1,546** | 11× |
| 0.2 | 23.1 | **843** | 21× |
| 0.4 | 12.1 | **442** | 40× |
| 0.6 | 8.2 | **300** | 58× |

ρ ≈ 0.4 is unremarkable for 60-session equity returns. **The realistic effective sample is in the
hundreds, not the tens of thousands.** This is an analytic illustration with assumed ρ — ρ was not
measured, because measuring it is an experiment and this round is read-only. Measuring it is the
first item of the pre-registration (§1.6).

The same correction applies to `label20`: 54,277 becomes ≈1,327 at ρ = 0.4. The existing "no edge"
finding is unaffected — a null stays null — but **any future positive result at either horizon must
be assessed against the corrected denominator**, or it will be significance manufactured from
overlapping, correlated rows.

---

## 1. D9 — defining the 60-session target

### 1.1 What exists, verbatim

```
tools/make_dataset.py:66   HORIZONS = (1, 5, 20)            # there is no fwd60
tools/make_dataset.py:68   LABEL_THRESHOLD_PCT = 2.0
tools/make_dataset.py:135  label20 = UP   if fwd20 >= +2.0
                                    DOWN if fwd20 <= -2.0
                                    else FLAT
                           fwd20  = (closes[19] / base - 1) * 100
                           mature20 = fwd20 is not None
```

### 1.2 The three candidate definitions

#### Option 1 — fixed return deadband (`fwd60 ≥ ±X%`)

- **UP/DOWN/FLAT:** the asset gained / lost / did neither more than X% over 60 sessions.
- **Advantages:** economically literal; stationary by construction; no estimation; identical
  interpretation in 2018 and 2026; trivially reproducible.
- **Failure mode (decisive):** one band across forex (very low dispersion) and crypto (very high)
  makes the label **largely a volatility classifier**. A model can score well by inferring asset
  class — learning *which asset this is*, not *where it is going*. With 616 assets across 5
  classes this is not a corner case; it is the expected outcome.
- **Sensitivity:** high in X, and *heterogeneously* so — raising X barely moves crypto's class
  shares and empties forex's directional classes.
- **Suitability for a position horizon:** poor across a mixed universe. Defensible only within a
  single asset class.

#### Option 2 — volatility-normalised deadband, point-in-time *(RECOMMENDED)*

```
sigma_i,t = stdev of daily log returns over the 60 sessions ENDING AT t      (closes <= t only)
band_i,t  = max( k * sigma_i,t * sqrt(60) , LABEL_THRESHOLD_PCT )            (k pre-registered)
label60   = UP   if fwd60 >= +band_i,t
            DOWN if fwd60 <= -band_i,t
            else FLAT
```

- **UP/DOWN/FLAT:** the asset moved more / less than `k` standard deviations of **its own**
  typical 60-session move. This is a *risk-adjusted* outcome, which is the quantity a
  position-horizon holder actually experiences, since position size is volatility-scaled.
- **Advantages:** comparable across assets, classes and regimes; uses **only information
  available at `t`**, as you required; the floor reuses the project's existing frozen constant
  (`LABEL_THRESHOLD_PCT = 2.0`) rather than inventing one, so `label60` degenerates exactly to
  `label20`'s band when volatility is negligible.
- **Failure modes, stated honestly:**
  1. `sigma` estimated at `t` can be overtaken by a regime break just after `t` (2020-03). The
     band is then wrong in a way no PIT construction can avoid. This is a real cost, not a
     technicality.
  2. The label becomes a function of a quantity that is **also a candidate feature**. That is not
     leakage (both are PIT) but it is dependence, and a model given `sigma` as a feature is partly
     given the label's own denominator. It must be documented; if `sigma` is used as a feature,
     say so.
  3. In crisis regimes the band inflates and almost everything becomes `FLAT` — arguably correct,
     but it means directional examples cluster in calm periods.
- **Sensitivity:** moderate and *homogeneous* in `k` — it shifts all assets together, which is
  what makes a sensitivity grid interpretable.

#### Option 3 — training-distribution-derived threshold **(my Round-2 recommendation — RETRACTED)**

- **UP/DOWN/FLAT:** the outcome fell in the upper / lower / middle part of the *training period's
  own* outcome distribution.
- **Your challenge is correct, and here is why in full:**
  1. **It has no financial meaning.** "Top tercile of 2018–2022" is not something anyone can act
     on, and `brain.md`'s first principle is that a published claim is a measurement of the world.
  2. **The target is non-stationary.** A bull-market training period sets a high bar; the same
     absolute move is `UP` in one era and `FLAT` in another. The thing being predicted drifts,
     which makes a stable result impossible to interpret.
  3. **It engineers the baseline it is then compared against.** Fixing `FLAT` share fixes the
     majority-class rate, so "beats majority class" measures something the designer chose.
  4. It does not solve the cross-sectional problem of Option 1 unless done per asset, and per
     asset it collapses to a pure rank, discarding magnitude entirely.
- **A balanced class distribution is a convenience, not evidence of meaning.** I treated it as a
  goal in Round 2. That was wrong.

### 1.3 Recommendation

**Option 2, with `k₀ = 1.0`.** `UP` then means "moved more than one standard deviation of its own
60-session move, upward" — a statement with a fixed meaning in every year and for every asset.

**`k₀` is chosen on interpretive grounds, not distributional ones.** The resulting `FLAT` share is
**reported, not targeted** — under a normal approximation `k = 1.0` implies `FLAT` near 68%, which
makes the majority-class baseline hard to beat. That is an honest difficulty and is **not** a
reason to move `k`. Moving `k` to obtain a more flattering baseline is precisely the retracted
Option 3 in disguise.

If you prefer a denser directional class, `k₀ = 0.5` ("half a typical move") is the only other
value with a clean verbal meaning. **That is an owner decision (§8, decision 2), and it must be
made before the label is built, not after any result is seen.**

### 1.4 Exact definitions

| Item | Definition |
|---|---|
| **Prediction timestamp** | `asOf` — the session whose close is `base`. All features and `sigma` use closes ≤ `asOf`. |
| **Outcome window** | the 60 stored sessions **after** `asOf`; `fwd60 = (closes[59]/base − 1) × 100`, matching `fwd20`'s `closes[h−1]` convention exactly |
| **Eligible observation** | ≥ 60 **trailing** sessions (for `sigma`) **and** a valid `base` close **and** no quality veto on the window |
| **Mature label** | `mature60 = fwd60 is not None` — 60 forward sessions exist in storage. Immature rows are **excluded, never imputed** |
| **Corporate actions** | a row is **excluded** when an unadjusted action falls in the trailing `sigma` window *or* the forward outcome window. `assemble.py` already flags the outcome side (`dataQuality.basisBreakInWindow`); the **trailing side is new and required by Option 2** |
| **Delisting** | the series simply ends; the final 60 sessions are immature and drop out. No synthetic terminal value, no survivorship repair — the existing measured survivorship bound stands |
| **Missing sessions** | counted in **stored sessions for that asset**, never calendar days; a gap shortens neither window, it shifts it |
| **Quality flags** | any Stage-0 integrity condition (bad bar, stale, non-session date) voids the row for both windows |
| **Threshold availability** | `band_i,t` is computable at `t` from closes ≤ `t`. **This is the test Options 1 and 3 fail differently** — Option 1 trivially passes, Option 3 passes only if the threshold is frozen from a prior period and never recomputed |

### 1.5 Splits, embargo, and the two sample counts

- **Chronological walk-forward only.** No shuffling, no random splits, no cross-asset holdout.
- **Purge, not just embargo:** every training row whose `asOf` lies within **60 sessions before a
  test block's start** has an outcome window overlapping the test period and must be dropped. A
  20-session embargo on a 60-session label leaks 40 sessions of every boundary row by
  construction.
- **Report both counts, separately and always:**

| Quantity | Meaning |
|---|---|
| **Raw rows** | ≤ 1,048,726 (reported estimate, Round 1) — and **lower than that**, because Round 1 required only 60 *forward* sessions. Option 2 also requires 60 *trailing* sessions, removing roughly the first 60 rows of every asset plus any asset with short history. The estimate is an **upper bound** and must be recomputed. |
| **Effective independent observations** | `time_windows × n_eff`, with ρ **measured**, not assumed — order **300–1,500** on the table in §0.4, not 17,478 |

**Every statistical statement must use the second number.** The first is a storage fact.

### 1.6 Pre-registered validation plan

Written and committed **before** the label is generated, in the manner of `acceptance_scope.json`:

1. **Measure ρ first.** Mean pairwise correlation of 60-session returns, within and across asset
   classes, and publish `n_eff`. This is the only step permitted before the label exists.
2. **Kill switch, stated in advance.** If effective independent observations fall below a
   pre-committed floor, declare the position horizon **unvalidatable on this dataset** and fit
   **no model**. On §0.4's arithmetic this outcome is likely. Deciding the floor now, before
   seeing it, is the whole point.
3. **Redundancy kill switch.** Once built, cross-tabulate `label20` against `label60` on shared
   rows. If concordance exceeds a pre-stated level, `label60` is a relabelling, not a second
   horizon — stop before fitting anything. This touches no test outcome and fits nothing.
4. **Sensitivity without tuning.** Evaluate the grid `k ∈ {0.5, 0.75, 1.0, 1.25, 1.5}` on
   **training and validation folds only**. The final held-out fold is scored **once, at `k₀`**.
   Both the grid and the single headline are published together.
5. **Acceptance conditions for a position-horizon claim** — all required:
   - margin over majority class exceeds sampling error computed on **effective** observations;
   - the margin holds on the **worst fold**, not only in aggregate (the 20-session model's worst
     fold was 2022);
   - predictions do not collapse toward one class;
   - leakage count 0, purge applied at 60, both reported;
   - results at **both** horizons published together, never whichever looks better.
6. **Multiple comparisons.** V1.1 has no policy; D9 creates the need. One must be written into
   the pre-registration before a second horizon exists.

### 1.7 Recommendation on approval

**Approve `label60` as a future research target. Claim a validated position horizon only after
its own acceptance tests pass** — and note that step 2 may legitimately end the programme before
a model is ever fit. That is a successful outcome of an honest gate, not a failure.

### 1.8 Unbudgeted cost (carried from Round 2)

`DecisionLog` has `move1Pct/5Pct/20Pct` and `measured1On/5On/20On` — **no 60-session columns**.
A position-horizon capability requires a schema migration before any such decision can be scored.

---

## 2. Canonical evidence taxonomy

### 2.1 The governing rule

> **Only asset-specific evidence may vote. Market-wide evidence may withhold, qualify or inform,
> but may never cast a directional vote.**

This single rule resolves the F5/F6 overlap, the F1/F5 dependence that Round 2 declared unsolved,
and the "news cannot force direction" invariant — structurally, with no event-matching machinery.
It is also **already the shipped design**: `lib/decision.ts:460` says of `macroVeto` that it is
*"A veto only: it can turn a LONG or SHORT into a WAIT and can do nothing else."*

**Finding F — V1.1's F5 is a regression.** The specification promotes macro from the shipped
veto-only role to a voting family. A market-wide input voting per asset would hand all 616 assets
the same ±1 on macro days, which is not evidence about any one of them and would make the whole
book's decisions correlated by construction.

### 2.2 The mapping

| Canonical | V1.1 family | Shipped leg | Raw / derived | Role | Provenance & PIT | Duplicates? | Recorded as |
|---|---|---|---|---|---|---|---|
| **E1 trend** | F1 | `timeframe` | derived (`r20`, `sma20/50`, `setup`, `horizon`) | **VOTE** | own close series ≤ `asOf` | with E3, E5 (same series) | `legs` / `opposing` |
| **E2 participation** | F2 | `volume` | derived (`volumeRatio`, `r1`) | **VOTE** | own volume ≤ `asOf`; **ineligible where unpublished (FX)** | none | `legs` / `opposing` |
| **E3 volatility** | F3 | — *(no leg)* | derived (`atr14`, drawdown, range) | **VOTE** | own close series ≤ `asOf` | with E1 | `legs` / `opposing` |
| **E4 cross-sectional** | F4 | `peers` | derived (`relStrength`, `peers ≥ 3`) | **VOTE** | peer closes ≤ `asOf` | **strips the common factor by design** | `legs` / `opposing` |
| **E5 history** | **none** | `history` | derived (`analogs`, `baseRateShare/Count`) | **VOTE** *(disputed — §8.7)* | own past outcomes ≤ `asOf`; floors 8/20/40 in `jobs/analogs.py` | with E1 | `legs` / `opposing` |
| **E6 trigger** | none | `trigger` | raw event in own series (`entryTrigger`) | **TIMING** → `timeSense`, never direction | own series ≤ `asOf` | none | `notes` |
| **E7 macro** | F5 | — | derived, market-wide | **CONTEXT + VETO** | PIT join on `observation_date + publicationLagDays` | **is E8 on policy days** | `notes`, `gate: macro-veto` |
| **E8 event / news** | F6 | — | raw dated items | **CONTEXT only** | publication time < decision time | **is E7 on policy days** | `notes`, `missing`, event id |

### 2.3 Counting independent evidence

1. **Votes come only from E1–E5** (asset-specific). Maximum `NET` is ±5.
2. **E7 and E8 never vote**, so one monetary event cannot produce two confirmations. Deduplication
   is structural; **no event-id matching is needed**.
3. **Nothing is suppressed.** E7 can veto to `WAIT`, E8 populates `notes` and `missing`, both are
   recorded with provenance, and E6 governs timing. You asked that macro and news be retained for
   context without duplicate votes — this is exactly that.
4. **Residual within-asset correlation (E1/E3/E5 share one price series) is real and is not
   resolved by this rule.** It is mitigated only by recording family names (§3.2) so the overlap
   is visible, and it must be measured once E3 and E5 are wired. It is an open limitation, stated
   rather than hidden.
5. **Genuinely distinct observations about one event survive.** On an FOMC day, E1 reads the price
   move, E2 reads whether volume confirmed it, E4 reads whether this asset outperformed peers —
   three different questions about one event, all retained.

### 2.4 Findings carried forward

- **Finding A (Round 2) — `history` has no family.** Resolved here as **E5**. Whether it votes is
  the one genuinely open question: it is the *only* evidence with a shipped outcome-audit
  mechanism (`baseRateShare` + `baseRateCount` exist precisely so it can be scored) and a graded
  quality floor (8/20/40). Excluding the best-audited evidence while admitting E3, which has no
  leg and no audit at all, would be backwards. **Recommend E5 votes.**
- **Finding C — `trigger` has no family.** Correct as-is: it answers *when*, not *which way*.
  Canonicalised as **E6 → `timeSense`**, and the spec must say so explicitly.
- **Finding E (new) — two meanings for one field.** V1.1 never states whether family-based
  decisions **replace** the shipped leg path in `lib/decision.ts` or run beside it. If both ship,
  `confidence` means two different things on two code paths. **This must be settled before
  implementation** (§8, decision 8).

---

## 3. D10 — fully defined semantics

### 3.1 R1″ — confidence grades the net, with no cap *(supersedes R1′)*

Your challenge: *the cap may downgrade a setup regardless of the number and strength of
supporting families.* **It does, and that is not justified.** Under R1′, 5 support against 1
opposing grades the same as 2 support against 0. Worked through:

| Support | Oppose | NET | R1′ (capped) | **R1″ (net-graded)** |
|---|---|---|---|---|
| 3 | 0 | +3 | High | **High** |
| 2 | 0 | +2 | Medium | **Medium** |
| 3 | 1 | +2 | High → **Medium** | **Medium** |
| **4** | **1** | **+3** | High → **Medium** | **High** |
| **5** | **1** | **+4** | High → **Medium** | **High** |
| 4 | 2 | +2 | High → Medium | **Medium** |
| 3 | 3 | 0 | WAIT (gate 2) | WAIT (gate 2) |

R1″ answers both halves of your challenge: dissent's penalty is **proportional** (each opposing
family costs 1 of `NET`) rather than a flat cliff, and a strong majority is not flattened by a
single objection. The rows in bold are where the two rules differ.

```
R1"   if action = WAIT          -> confidence = "Low"            [shipped behaviour]
      elif |NET| >= MIN_NET + 1 -> confidence = "High"
      else                      -> confidence = "Medium"
```

- **Inputs:** `NET`, `MIN_NET`. **Output:** `Confidence`. **No new constant** — `MIN_NET + 1` is
  one family above the publication floor, derived, not chosen.
- **What happens to shipped rule 6** (*a grade must never be more confident than the note beside
  it*, `lib/decision.ts:770`)? Its purpose is preserved by **printing the objection in `notes`**,
  which is what `notes` is documented for: *"What argues against the direction, or qualifies it,
  without replacing it."* The cap existed because nothing recorded opposition; once R2′ ships, it
  does. **This is a deliberate retirement of the cap for the family path, and it is disputed —
  see §8, decision 5.**
- **Counterargument (strongest):** rule 6 is a shipped, deliberate honesty constraint, and
  retiring it lets a card print `High` with a visible contradiction under it. If you weight
  "never look more confident than the caveat" above proportionality, keep R1′.
- **Test:** score matured rows grouped by `(confidence, opposing ≠ "")`. If `High` rows with an
  objection underperform `High` rows without one, the cap was carrying information and R1″ is
  wrong.

### 3.2 R2′ — persist the opposing names; derive everything else

Unchanged from Round 2 and still **the load-bearing recommendation**.

```
PERSIST   eligibleFamilies : int
          legs             : names where vote = d        [EXISTS: DecisionLog.legs]
          opposing         : names where vote = -d       [NEW — one field]
DERIVE    votingFamilies   = |legs| + |opposing|
          abstainingFamilies = eligibleFamilies - votingFamilies
          NET              = |legs| - |opposing|
```

Of the five quantities you listed, **`votingFamilies` and `abstainingFamilies` are redundant**,
and so is `NET` once both name lists exist. Persisting derived values invites them to disagree
with their inputs — the fault `lib/decision.ts:703` names as *"One count, two readers"*. Names
rather than counts, because `legs` exists precisely so *"something could be learned about whether
a leg earns its place"*, and a count cannot answer which family earned it.

**Counterargument:** write-only until `tools/scorecard.py` reads it.
**Test:** after ~200 matured rows, if outcomes for `opposing = ""` and `opposing ≠ ""` are
indistinguishable, opposition carries no information and R1″'s `NET` subtraction is also suspect.

### 3.3 R3″ — only asset-specific evidence votes *(generalises R3)*

R3 (Round 2) removed **F6** from voting. R3″ removes **F5 as well**, by the §2.1 rule. Both
remain eligible as context, and **neither counts toward `MIN_FAMILIES`** — otherwise they would
inflate the readability gate while contributing nothing.

- **For:** eliminates F5/F6 double counting *and* F1/F5 dependence in one structural rule;
  restores the shipped veto-only treatment of macro; makes "news cannot force direction"
  arithmetically impossible rather than merely guarded.
- **Against (strongest):** a genuinely novel, unscheduled event — an 8-K, a sanction, a halt — is
  real, asset-specific information that E1–E5 cannot see for days. R3″ makes the system
  structurally unable to act on it. **That is a real cost and it is chosen deliberately.** A
  future V2 could admit a narrow *asset-specific, document-sourced* event family (an 8-K about
  *this* registrant is not market-wide); market-wide macro must stay veto-only regardless.
- **Test:** on the 168-event reaction corpus, if forward returns conditional on event direction
  differ from the unconditional distribution **after** controlling for the concurrent price move,
  event context carries independent information and R3″ is discarding it.

### 3.4 R4 — retire `τ`; state F1's rule directly *(unchanged, re-verified)*

`s` is attainable only at `{−1, 0, +1}` for E2/E3/E4, so **`τ` cannot change their vote at any
value**. For E1, `s ∈ {−1, −0.5, 0, +0.5, +1}` with one switch point between 0.5 and 0.75.

```
E1 votes +1  iff sign(r20) = +1 AND sma20 > sma50
E1 votes -1  iff sign(r20) = -1 AND sma20 < sma50
E1 votes  0  otherwise
```

- **Against (strongest):** E1 abstains far more often; with only 5 voting families that pushes
  more decisions below `MIN_NET` and into `WAIT`. A system that says `WAIT` on almost everything
  is honest and useless.
- **Test:** replay stored sessions under both rules and count published directions. If `τ > 0.5`
  cuts directional output by more than roughly half, the cost outweighs the precision.

### 3.5 The gate, fully specified

```
STAGE 0   integrity vetoes -> set state_i = INELIGIBLE. Never set a vote, never set a direction.

votingSet        = {E1, E2, E3, E4, E5}            (E6 timing; E7, E8 context — never vote)
eligibleFamilies = |{i in votingSet : inputs pass that family's documented gates}|
NET              = SUM(vote_i) over eligible voting families,  vote_i in {-1, 0, +1}
d                = sign(NET)
supportFamilies  = |{i : vote_i =  d}|
opposingFamilies = |{i : vote_i = -d}|

GATE 1  eligibleFamilies < MIN_FAMILIES (3) -> WAIT, basis "file",     gate "file"
GATE 2  |NET| < MIN_NET (2)                 -> WAIT, basis "evidence", gate "thin-evidence"
GATE 3  NET >= +2 -> LONG          GATE 4   NET <= -2 -> SHORT

CONFIDENCE (R1")  WAIT -> "Low" ; |NET| >= 3 -> "High" ; else "Medium"

STAGE 5   risk / execution vetoes -> lower executionReadiness and timeSense; may force WAIT.
          MAY NEVER CHANGE d.

PERSIST   eligibleFamilies, legs, opposing            (everything else derived)
```

`MIN_FAMILIES = 3` and `MIN_NET = 2` are **unchanged from V1.1**. **No threshold is added.**

### 3.6 Answers to your specific D10 questions

**When is `MIN_FAMILIES` satisfied, and do inconclusive-but-eligible families count?**
It counts **all eligible voting families, including those voting 0**. This is correct because the
gate measures *how much of the file is readable* — a question about coverage, not about
decisiveness. The two gates emit different bases (`file` vs `evidence`) precisely to keep those
apart, and collapsing them would make "we could not look" and "we looked and it was balanced"
indistinguishable.

**Must a zero vote ever mean "unavailable"?** No, and V1.1 §3.2 already forbids it: unavailable
data makes a family `INELIGIBLE` (a `file` fact); eligible-but-inconclusive votes `0` (an
`evidence` fact). This matches shipped precedent — `newsCoverage: "unavailable"` is explicitly
never converted to a neutral tone, and a null `r20` is treated as "not late" rather than late.
**Verified existing behaviour; no change required.**

**Is `MIN_NET = 2` kept?** Yes. I found no contradiction that survives scrutiny. Round 1 called
its varying meaning a defect; **I partly retract that** — scaling the threshold with
`eligibleFamilies` would make richer coverage face a *higher* bar for identical evidence, which is
worse. Keep it absolute and make the difference auditable through R2′.

**`MIN_VOTERS`?** **Declined.** Three eligible families with two votes (`+1,+1,0`) stays legal:
R1″ grades it `Medium`, and R2′ shows `legs` of length 2 against `eligibleFamilies = 3`. The
defect is solved structurally, so a new tunable is not warranted.

**Reporting threshold sensitivity without tuning.** Report the published direction counts and
outcome distributions across a grid of `MIN_NET ∈ {1, 2, 3}` on **training and validation folds
only**, with `MIN_NET = 2` scored once on the held-out fold, and publish grid and headline
together. Changing `MIN_NET` after seeing a held-out result is forbidden by V1.1 §D2 and this
review does not reopen it.

### 3.7 The six dimensions, kept distinct

| # | Dimension | Where it lives | Never |
|---|---|---|---|
| 1 | Supporting evidence | `legs` (names), `supportFamilies` (derived) | — |
| 2 | Opposing evidence | `opposing` (names) + `notes` | not folded into 1 |
| 3 | Eligible independent families | `eligibleFamilies` | not conflated with 1 or 2 |
| 4 | Data quality | Stage-0 vetoes, `missing`, `basis: "file"` | never a vote |
| 5 | Historical model performance | experiment artifacts; `DecisionLog` matured outcomes | never shown as per-decision confidence |
| 6 | Execution readiness | `executionReadiness`, `timeSense`, Stage-5 | never changes `d` |

**None of these is a calibrated probability of success, and `confidence` must never be rendered
as a percentage.** No calibration has been demonstrated; the one measured model has no edge.

---

## 4. Worked scenarios

All use §3.5 unchanged: `MIN_FAMILIES = 3`, `MIN_NET = 2`, R1″, R2′, R3″, R4. Voting families are
E1–E5; E6 is timing; E7/E8 are context.

### Case A — clean directional agreement

| | E1 trend | E2 vol'ume | E3 volatility | E4 peers | E5 history | E6 | E7 | E8 |
|---|---|---|---|---|---|---|---|---|
| state | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE | — | no veto | none |
| vote | **+1** | **+1** | **+1** | **0** | **+1** | n/a | n/a | n/a |

`r20 > 0` and `sma20 > sma50` (passes R4) · `volumeRatio 1.6` on an up session ·
drawdown −3%, range in lower half · `relStrength +0.2`, inside band · 31 matched days leaning up
(above `MIN_MATCHES_MEDIUM = 20`).

```
eligibleFamilies = 5   NET = +4   support = 4   opposing = 0   abstaining = 1
GATE 1  5 >= 3  pass        GATE 2  |+4| >= 2  pass        GATE 3  -> LONG
CONFIDENCE  |NET| = 4 >= 3  -> HIGH
PERSIST  eligibleFamilies 5 | legs "trend,volume,volatility,history" | opposing ""
```

**`LONG`, `High`.**

### Case B — mixed evidence

| | E1 | E2 | E3 | E4 | E5 | E7 | E8 |
|---|---|---|---|---|---|---|---|
| state | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE | no veto | none |
| vote | **+1** | **+1** | **+1** | **−1** | **0** | n/a | n/a |

```
eligibleFamilies = 5   NET = +2   support = 3   opposing = 1   abstaining = 1
GATE 1 pass   GATE 2 |+2| >= 2 pass   GATE 3 -> LONG
CONFIDENCE  |NET| = 2 < 3  -> MEDIUM
PERSIST  eligibleFamilies 5 | legs "trend,volume,volatility" | opposing "peers"
notes    "peers argue the other way"
```

**`LONG`, `Medium`.** It stays directional because three independent asset-specific families agree
and one disagrees; the objection costs exactly one of `NET` and is named in the record. **The
fields that distinguish it from Case A are `opposing` (non-empty) and `confidence` (Medium).**

**B2 — the same rule turning to WAIT.** With E3 `−1` instead of `+1`:

```
NET = 0  ->  GATE 2 fails  ->  WAIT, basis "evidence", gate "thin-evidence", confidence "Low"
PERSIST  eligibleFamilies 5 | legs null | opposing null        (no direction, so no d)
```

### Case C — low information

An FX pair. No published volume → E2 `INELIGIBLE` (**never 0**). `peers = 0` → E4 `INELIGIBLE`.
Matched days `= 5`, below `MIN_MATCHES_LOW = 8` → E5 `INELIGIBLE`.

| | E1 | E2 | E3 | E4 | E5 |
|---|---|---|---|---|---|
| state | ELIGIBLE | **INELIGIBLE** | ELIGIBLE | **INELIGIBLE** | **INELIGIBLE** |
| vote | **+1** | — | **+1** | — | — |

```
eligibleFamilies = 2   NET = +2
GATE 1  2 < MIN_FAMILIES 3  ->  WAIT, basis "file", gate "file", confidence "Low"
missing  "volume not published" | "fewer than 3 peers" | "fewer than 8 matched days"
```

**`WAIT`, basis `file`.** `NET = +2` **would have cleared `MIN_NET`** — Gate 1 runs before Gate 2
for exactly this reason. The refusal is about coverage, not about weak evidence.

**`file` vs `evidence`:** `file` = a measurement was **not available** (Case C). `evidence` = the
measurements **were** available and did not decide (Case B2). "We could not look" and "we looked
and it was balanced" are different claims and are never collapsed.

### Case D — duplicate causal evidence

An FOMC decision. Price rose on it; the policy rate series moved; the event is in the corpus
(one of the 26 `monetary` events of 240).

| | E1 | E2 | E3 | E4 | E5 | E7 macro | E8 event |
|---|---|---|---|---|---|---|---|
| state | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE | context | context |
| vote | **+1** | **+1** | **0** | **0** | **0** | **never votes** | **never votes** |

E4 reads `0` **because the whole peer group rose on the same announcement** — relative strength is
designed to strip the common factor, and here it does so automatically.

```
eligibleFamilies = 5   NET = +2   support = 2   opposing = 0   abstaining = 3
GATE 3 -> LONG      CONFIDENCE |NET| = 2 -> MEDIUM
PERSIST  eligibleFamilies 5 | legs "trend,volume" | opposing ""
CONTEXT  macro: DFF move (PIT, publicationLagDays applied) | event: FOMC <eventId>, retained
```

**Under V1.1 as written**, F5 and F6 would each add `+1` (F6 permitted, since F1 already supports
the direction) giving `NET = +4` and `High` — **one cause presented as four confirmations.**
Under R3″ it is `NET = +2`, `Medium`, with the macro move and the event both **retained and
recorded** as context. Nothing is suppressed; nothing is counted twice.

### Opposition-cap tests (R1′ vs R1″)

| Scenario | Support | Oppose | NET | R1′ | **R1″** | Which is right? |
|---|---|---|---|---|---|---|
| Mild dissent, strong majority | 4 | 1 | +3 | Medium | **High** | R1″ — one objection should not flatten a 4-to-1 majority |
| Mild dissent, narrow majority | 3 | 1 | +2 | Medium | **Medium** | agree |
| No dissent, minimum majority | 2 | 0 | +2 | Medium | **Medium** | agree |
| Substantial opposition | 4 | 2 | +2 | Medium | **Medium** | agree — opposition already cost 2 of `NET` |
| Even split | 3 | 3 | 0 | WAIT | **WAIT** | agree |

**Not all dissent gets the same penalty under R1″** — it is proportional, because each opposing
family subtracts from `NET`, which is what the grade reads. **And credible contradictory
information is never ignored:** it costs `NET`, it is named in `opposing`, and it is printed in
`notes`.

---

## 5. Invariants

| Invariant | Status |
|---|---|
| Vetoes withhold; never force or invert direction | **Preserved** — Stage 0 sets only `INELIGIBLE`; Stage 5 cannot change `d` |
| Missing / stale / invalid is not a neutral vote | **Preserved and strengthened** — Case C; matches shipped `newsCoverage: "unavailable"` |
| Correlated indicators are not independent confirmations | **Strengthened** — §2.1 removes E7/E8 votes entirely. **Residual E1/E3/E5 within-asset overlap remains open** (§2.3.4) |
| News alone cannot force LONG or SHORT | **Strengthened** — arithmetically impossible under R3″, not merely guarded |
| PSX bearish research valid while execution blocked | **Preserved** — D7 untouched |
| No look-ahead from outcomes or retrospective regimes | **Preserved and tightened** — §1.4 adds a **trailing**-window corporate-action exclusion that does not exist today |
| Decisions and source snapshots immutable | **Preserved** — nothing altered |
| Learning / rule updates versioned and evaluated before acceptance | **Preserved** — §1.6 pre-registration; V1.1 §D2 still forbids post-hoc threshold moves |
| Decisive reasoning, never fabricated certainty | **Preserved** — §3.7: `confidence` is never a probability; §0.4 corrects a number that flattered the project |

---

## 6. Decision table

| Item | Status | Note |
|---|---|---|
| `label20` definition, `HORIZONS = (1,5,20)`, no `fwd60` | **AGREED** | verified in source |
| `Confidence` / rule-6 cap / `LEGS` / `WaitBasis` / analog floors 8-20-40 | **AGREED** | verified shipped behaviour |
| `MIN_FAMILIES = 3`, `MIN_NET = 2`, absolute | **AGREED** | unchanged from V1.1; Round 1's objection partly retracted |
| Zero vote ≠ unavailable | **AGREED** | already correct in V1.1 §3.2 |
| Effective sample is 300–1,500, not 17,478 | **PROPOSED** | analytic; ρ must be measured |
| **Option 2** PIT volatility-normalised band | **PROPOSED** | retracts Round 2's Option 3 |
| `k₀ = 1.0` | **DISPUTED** | `k₀ = 0.5` is defensible; owner's call |
| 60-session purge; two sample counts reported separately | **PROPOSED** | |
| Pre-registration with ρ and redundancy kill switches | **PROPOSED** | |
| **R1″** net-graded confidence, cap retired | **DISPUTED** | trades shipped rule 6 for proportionality |
| **R2′** persist `opposing`; derive the rest | **PROPOSED** | load-bearing |
| **R3″** only asset-specific evidence votes | **PROPOSED** | supersedes R3; demotes F5 |
| **R4** retire `τ`; E1 needs both signals | **PROPOSED** | subject to the replay test |
| **E5 history votes** (Finding A) | **DISPUTED** | best-audited evidence, but correlated with E1 |
| E6 `trigger` → `timeSense`, not direction (Finding C) | **PROPOSED** | |
| Family path replaces or coexists with shipped leg path (Finding E) | **DISPUTED** | must be settled before implementation |
| Residual E1/E3/E5 within-asset correlation | **DISPUTED — open** | not solved by anything here |
| R1 (original) | **WITHDRAWN** | |
| Round 2's Option 3 label; Round 2 Finding B as unsolvable | **RETRACTED** | |

---

## 7. Strongest counterarguments, collected

1. **Against Option 2:** it makes the label depend on a PIT estimate that a regime break can
   invalidate the day after `t`, and ties the target to a quantity that may also be a feature.
   Option 1 has neither problem and is simpler; its cost is only that it mixes asset classes.
2. **Against the §0.4 correction:** `n_eff = n/(1+(n−1)ρ)` assumes equicorrelation, which is
   false — correlation is blocky by sector and class. The true figure is higher than the table
   shows, though still far below 17,478. **The direction of the correction is certain; its
   magnitude is not.**
3. **Against R1″:** it retires a shipped honesty constraint so that a card can print `High` with a
   contradiction beneath it.
4. **Against R3″:** it makes the system structurally blind to genuinely novel asset-specific news.
5. **Against E5 voting:** analogs derive from the same price series as E1 and E3, so a fifth vote
   may be a third reading of one series.
6. **Against the whole exercise:** none of this creates an edge. The measured model has none. A
   more rigorous aggregator over evidence with no demonstrated predictive value produces more
   defensible `WAIT`s, not better calls — which is the honest goal, but it should be said plainly.

---

## 8. Owner decisions required

| # | Decision | Recommendation |
|---|---|---|
| 1 | Approve `label60` as a research target, built **only after** pre-registration? | **Yes** |
| 2 | Band definition: **Option 2** PIT volatility-normalised? | **Yes** |
| 3 | `k₀ = 1.0` (≈68% FLAT, hard honest baseline) or `k₀ = 0.5`? | **1.0** |
| 4 | Pre-register the ρ/power kill switch — abandon the horizon if effective N is below a floor set **now**? | **Yes** |
| 5 | **R1″** (net-graded, cap retired) or keep **R1′** (shipped rule-6 cap)? | **R1″** |
| 6 | **R2′** — persist `opposing`, derive the rest? | **Yes** |
| 7 | **R3″** — only asset-specific evidence votes (demotes F5 to veto-only)? | **Yes** |
| 8 | **R4** — retire `τ`, E1 requires both signals? | **Yes**, subject to replay |
| 9 | **E5 history votes**, or is it a reported prior only? | **Votes** |
| 10 | **Finding E** — does the family path replace the shipped leg path, or coexist? | **Replace**; two meanings for `confidence` is not acceptable |

---

## 9. Confirmation

- No file edited; no specification revised; `BRAIN-SPEC-V1.md` unmodified.
- No label generated, no dataset altered; `label60` does not exist; ρ was **not** measured.
- No code, training, evaluation, tuning or deployment. Decisions and artifacts untouched.
- The only new file is this review. **No revised specification will be produced until decisions
  1–10 are settled and explicit agreement is reached.**
