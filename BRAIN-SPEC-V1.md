# Brain Logic Specification V1

**Status: proposed design. Nothing here is implemented by this document.**
Written 2026-10-15 against `main` at `4f1e4de`. No code was written, no model trained, no
evaluation run for this specification.

Every claim below carries one of three labels:

| Label | Meaning |
|---|---|
| **[EXISTS]** | implemented in the repository today |
| **[VERIFIED]** | exists *and* is proven by a test or a recorded measurement |
| **[PROPOSED]** | design only; no implementation |

The project's sources of truth remain `brain.md` (reasoning log), `RESUME.md` (handoff) and
`ARCHITECTURE.md` (layer map). This file is the one place the brain's *logic* is specified; those
three point here rather than repeating it.

---

## 1. Mission and non-negotiable principles

**Mission.** For an eligible instrument at an eligible decision timestamp, produce the
best-supported directional research conclusion the available data can justify, with its evidence,
its counter-evidence, its uncertainty and the conditions that would overturn it — or decline to
produce one.

### Non-negotiable principles

1. **A conclusion is not a trade.** Directional research and execution readiness are separate
   dimensions and are never collapsed into one score. **[EXISTS]** — the engine already separates
   direction from `TimeSense`.
2. **`WAIT` is a real answer, and it has two kinds.** "I do not have the measurement" and "I have
   it and it does not support acting" are different sentences and must never print the same.
   **[EXISTS]** — `WaitBasis = "file" | "evidence"` in `lib/decision.ts`.
3. **No manufactured certainty.** A probability is published only where an evaluation supports
   calibrating one. Absent that, the system reports an ordinal strength and says so.
4. **Nothing learns from the future.** A feature may use only what was knowable at the decision
   timestamp. **[VERIFIED]** — `featureDatedAfterSession: 0`, `setupDatedAfterSession: 0` in the
   dataset manifest; `USREC` excluded with a test.
5. **History is append-only.** A decision, once recorded, is never rewritten by a later model.
   **[EXISTS]** — `DecisionLog` stores the reward-to-risk *as measured at the time*, precisely so
   a later rebuild cannot answer a different question.
6. **Unknown is not zero.** A missing cost, an unpublished volume, an absent borrow rate stay
   missing. **[VERIFIED]** — FX volume is stored null rather than the provider's `0`.
7. **Beating a weak baseline is not evidence.** Every candidate is measured against the
   majority-class reference as well as the rule baseline. **[VERIFIED]** — the first experiment
   scored 0.4211 against a 0.4204 majority class and is recorded as *no demonstrated edge*.

---

## 2. Decision contract

One decision record per (instrument, timestamp). **[PROPOSED]** except where noted.

```
direction            LONG | SHORT | WAIT                                   [EXISTS]
waitBasis            file | evidence | null                                [EXISTS]
horizon              scalp | intraday | swing | position | null
regime               trend_up | trend_down | range | high_vol | transition | unknown
setupClass           breakout | pullback | reversal | continuation | none
evidenceStrength     0..4 ordinal, per evidence family (§4)
dataQuality          complete | partial | stale | conflicted
executionReadiness   executable | unverified | blocked                     [EXISTS, partial]
probability          float | null   -- null unless calibration is evidenced
entryLow/High        float | null                                          [EXISTS]
invalidation         float | null                                          [EXISTS]
target               float | null                                          [EXISTS]
expectedHoldSessions int | null
supporting[]         {familyId, claim, sourceRef, asOf}
contradicting[]      {familyId, claim, sourceRef, asOf}
alternatives[]       {hypothesisId, whyNotChosen}
invalidatedIf[]      {condition, measurable}
historicalCases[]    {episodeId, similarity, outcome}  -- retrieval only
limitations[]        {missingField, consequence}
gate                 which rule decided                                    [EXISTS]
snapshotId           the exact data version read                           [PROPOSED]
```

**Contract rules.** `direction != WAIT` requires `invalidation != null`. `probability != null`
requires a calibration record. `executionReadiness = executable` requires a cost model, which does
not exist for any market today — so V1 may only ever emit `unverified` or `blocked`.

---

## 3. Architecture

### Recommendation: ten roles, not ten agents

Ten independent agents would be the wrong design here. Most of these responsibilities are
deterministic, cheap and must be auditable; wrapping them in autonomous agents would make them
slower, non-reproducible and harder to test, and would buy nothing. **Recommended: a single
ordered pipeline of pure functions**, each owning one role, each independently testable, with
learned components introduced only where a rule demonstrably cannot express the judgement.

```
snapshot ─► R1 integrity ─► R2 structure ─┐
                                          ├─► R8 adversary ─► aggregate ─► R9 risk ─► decision
     R4 macro ─ R5 news ─ R6 behaviour ───┤                      │
                        R7 memory ────────┘                      └─► R3 statistics
                                                                        │
                                                        R10 learning ◄──┘ (offline)
```

| Role | Kind | Status |
|---|---|---|
| R1 Evidence & data integrity | deterministic rules | **[EXISTS]** `jobs/ohlc.py`, `basis_transitions`, `session_bar()` |
| R2 Market structure | deterministic + thresholds | **[EXISTS]** `jobs/factors.py`, `horizons.py` |
| R3 Mathematics & statistics | statistical functions | **[EXISTS]** partially — `robust_z`, analog quartiles |
| R4 Cross-market & macro | retrieval + rules | data **[EXISTS]**, wiring **[PROPOSED]** |
| R5 News & original research | retrieval + classification | corpus **[EXISTS]**, wiring **[PROPOSED]** |
| R6 Human behaviour | derived measures only | **[PROPOSED]** |
| R7 Historical memory | retrieval | corpus **[EXISTS]**, wiring **[PROPOSED]** |
| R8 Adversarial scientist | deterministic challenge set | **[PROPOSED]** |
| R9 Risk & execution | deterministic gates | **[EXISTS]** partially |
| R10 Learning & evaluation | offline only | **[EXISTS]** `DecisionLog`, `tools/scorecard.py` |

**Which capabilities should be learned?** Only three are candidates, and only after V1:
combining evidence families into a probability (R3), ranking historical analogues by relevance
(R7), and classifying event materiality (R5). Everything else should stay rules, because a rule
can be read, argued with, and shown to be wrong — which is the property this project values most.

**R6 is the most dangerous role** and is deliberately the thinnest: "fear" and "greed" are
measurable only as proxies (volatility expansion, volume extremes, crowded positioning where
data exists). V1 specifies no sentiment score derived from headline text.

---

## 4. Reasoning process and the aggregation policy

The eleven steps of the brief map onto the pipeline above. The two parts that need exact
specification are how evidence combines and how correlated signals are prevented from voting
twice.

### Evidence families

Indicators are grouped into **families**. A family casts **one** vote, regardless of how many
indicators it contains. This is the whole mechanism against double-counting: `r5`, `r20`, `sma20`
and `sma50` are four numbers describing one fact (trend), so they are one family and one vote.

| Family | Members (current features) | Independent of |
|---|---|---|
| F1 trend | r5, r20, sma20, sma50 | F2–F6 |
| F2 participation | volumeRatio | F1, F3–F6 |
| F3 volatility & range | atr14, rangePct, drawdownPct | F1, F2 |
| F4 relative strength | peerMedianR20, relStrength, peers | F1–F3 |
| F5 macro context | macro-sessions join **[PROPOSED]** | F1–F4 |
| F6 event context | event/reaction corpus **[PROPOSED]** | F1–F5 |

### Aggregation

```
net = Σ family_vote × family_weight     vote ∈ {-1, 0, +1}
```

- A family votes `0` when its inputs are missing or internally contradictory.
- Weights are **fixed and published**, not fitted, in V1.
- `|net| < MIN_NET` → `WAIT` with `waitBasis = "evidence"`.
- Fewer than `MIN_FAMILIES` families reporting → `WAIT` with `waitBasis = "file"`.
- Families that disagree do not cancel silently: both sides are recorded in `supporting[]` and
  `contradicting[]`, and the disagreement itself is a published field.

**Reconciling conflict.** There is no voting-down of a specialist. R1 (integrity) and R9 (risk)
hold **vetoes** — they can force `WAIT` but never force a direction. Every other role contributes
a vote. A veto is always recorded with its reason.

**Avoiding endless analysis.** The pipeline is a fixed, finite sequence with no loops. It always
terminates in a decision, and `WAIT` is a legitimate terminus. There is no "gather more evidence"
branch.

---

## 5. Missing, conflicting and adverse data

Full catalogue in §7. The policy is three rules:

1. **Missing input → family votes 0 and the gap is named in `limitations[]`.** Never imputed,
   never treated as neutral-positive.
2. **Conflicting sources → the conflict is the output.** Both values are preserved with their
   provenance; `dataQuality = conflicted`; the family votes 0 unless a documented authority rule
   resolves it. **[EXISTS]** — the FX 2019-05-22 disputed record is exactly this shape.
3. **Stale beyond its lane interval → `WAIT` with `waitBasis = "file"`.** **[EXISTS]**

---

## 6. Memory and the learning lifecycle

### What is recorded, immutably

**[EXISTS]** — `DecisionLog` already stores `periodEnd`, `action`, `gate`, `confidence`,
`entryLow/High`, `invalidation`, `legs`, `intent`, and reward-to-risk *as measured at the time*.

**[PROPOSED]** additions: `snapshotId`, `hypothesisId`, `invalidatedIf[]`, `expectedHoldSessions`.

### Lifecycle

```
decide ─► freeze (append-only) ─► wait for maturity (20 sessions)
   ─► evaluate: correct | incorrect | ambiguous | unevaluable
   ─► classify failure ─► propose correction ─► validate out-of-sample ─► accept or reject
```

**Rules.** No outcome is read before it matures. No correction is accepted on in-sample evidence.
A rejected correction is recorded, not deleted — the record of what did not work is as valuable
as what did. **[VERIFIED]** the maturity concept exists: `mature20` is on every example and
sessions inside the final 20 of a series are excluded rather than labelled FLAT.

### How research materials are used — and not used

| Material | Role | May become a predictor? |
|---|---|---|
| price/volume + outcomes | predictors and labels | **yes** — already is |
| macro (point-in-time) | context | yes, joined on `observation_date + publicationLag` |
| events / reactions | context and hypothesis source | yes, with explicit availability timestamps |
| press references | retrieval only | **no** — references, text never fetched |
| principles / citations | hypothesis source | **no** — they generate *tests*, not features |
| regime episodes | retrieval and stratification | **no** — identified with future prices |

**The leak this table prevents:** a regime label knows the future by construction (a peak is only
a peak afterwards). Regimes may stratify *evaluation*; they may never be an input feature.

---

## 7. Edge-case catalogue

Each row: condition → expected behaviour → output state → required regression test.

| # | Condition | Behaviour | Output | Test |
|---|---|---|---|---|
| E1 | Fewer than N sessions of history | family votes 0 | WAIT/file | synthetic short series |
| E2 | Whole feature group missing | family votes 0, named | WAIT/file if < MIN_FAMILIES | drop a family |
| E3 | Two providers disagree | preserve both, vote 0 | conflicted | FX 2019-05-22 fixture **[EXISTS]** |
| E4 | Stale price beyond lane interval | veto | WAIT/file | aged snapshot |
| E5 | close outside high/low | range withheld | partial | `jobs/ohlc.py` **[VERIFIED]** |
| E6 | Unadjusted corporate action in window | flag; family 0 | partial | `unadjustedActionInWindow` **[VERIFIED]** |
| E7 | Delisted instrument | excluded; bias noted | n/a | survivorship fixture |
| E8 | Non-trading day / holiday | not a session | n/a | `session_bar()` **[VERIFIED]** |
| E9 | Missing volume (FX) | F2 votes 0 | partial | FX fixture **[VERIFIED]** |
| E10 | News about the wrong company | link rejected | n/a | ambiguous-ticker fixture |
| E11 | Republished old story | dedupe by content hash | n/a | duplicate fixture **[EXISTS]** |
| E12 | Negated headline | no vote from text | n/a | negation fixture |
| E13 | Macro revised after timestamp | original vintage used | n/a | ALFRED vintage **[EXISTS]** |
| E14 | Limit move / halt | structure invalid | WAIT/file | PSX band fixture **[EXISTS]** |
| E15 | Flash crash | volatility veto | WAIT/evidence | COVID window |
| E16 | False breakout | recorded as failure | — | labelled fixture |
| E17 | Timeframes disagree | explicit mixed gate | WAIT/evidence | **[EXISTS]** |
| E18 | Correlated indicators | one family, one vote | — | family-independence test |
| E19 | Direction fine, execution unknown | direction published, `unverified` | — | cost-absent test |
| E20 | Label overlap at split | 20-session embargo | — | **[VERIFIED]** |
| E21 | Class imbalance (FX 68% FLAT) | report per class | — | per-class metrics **[VERIFIED]** |
| E22 | Model drift | degradation alarm | — | rolling-window test |

---

## 8. Testing strategy

**Acceptance principle:** a test suite that cannot distinguish a legitimate `WAIT` from a hidden
defect is useless. Every test states which it expects.

| Tier | Scope | Failure means |
|---|---|---|
| T1 Unit | each role's contract in isolation | role is wrong |
| T2 Integration | pipeline end-to-end on fixtures | wiring is wrong |
| T3 Lineage | every feature traced to source + timestamp | provenance broken |
| T4 Leakage | no future value reachable from any predictor | **blocks training** |
| T5 Corruption | missing source, truncated file, bad bar | recovery broken |
| T6 Regime | crisis, bull, bear, transition fixtures | brittle in the case that matters |
| T7 Adversarial | false news, source conflict, correlated evidence | over-confident |
| T8 Survivorship | delisted names | bias understated |
| T9 Execution | cost absent → never `executable` | over-claims tradability |
| T10 Reproducibility | same snapshot ⇒ same decision, byte-identical | not scientific |
| T11 History | old decisions unchanged after a model change | memory corrupted |

T4, T10 and T11 are **blocking**: training may not begin while any fails.

---

## 9. Evaluation standards and gates

### Pre-training gates (all must pass)

1. T4 leakage, T10 reproducibility, T11 history — green.
2. Feature lineage complete for every predictor.
3. Chronological split defined with a 20-session embargo. **[VERIFIED]**
4. Effective sample size reported, not row count. **[VERIFIED]** — 1,085,544 rows ≈ 54,277
   independent windows.
5. References fixed in advance: majority-class **and** rule baseline. **[VERIFIED]**

### Accept / reject a candidate

**Accept** only if it beats *both* references out-of-sample, on identical samples, with the
improvement holding in **more than half the folds** and **not vanishing in the adverse regime**.
The first candidate failed exactly this last clause — its worst fold was 2022.

**Reject** if it beats only the rule baseline, if the gain is inside the confidence interval, if
it is driven by one market or one year, or if it collapses toward the majority class. Accuracy is
never the sole objective: calibration and behaviour in drawdowns count equally.

### Post-training and deployment

Post-training: rerun T1–T11, compare against the preserved reference, publish per-market,
per-regime, per-horizon and per-class metrics with sample counts.
Deployment is a **separate** decision requiring independent acceptance evidence and is out of
scope for V1.

---

## 10. Unresolved decisions

| # | Decision | Recommended default | Rationale |
|---|---|---|---|
| D1 | Family weights | equal weights in V1 | nothing yet justifies unequal ones; fitted weights need an edge that does not exist |
| D2 | `MIN_NET` / `MIN_FAMILIES` | 2 and 3 | must be set *before* seeing results and then left alone |
| D3 | Publish a probability? | **no** in V1 | no calibration evidence exists; an ordinal strength is honest |
| D4 | Horizons supported | swing + position only | intraday history is a 7-day rolling window, not history |
| D5 | Join macro into features? | yes, next milestone | it is PIT-correct and joinable; the largest available gain |
| D6 | Event features | defer to V2 | 167 reaction rows is too few to fit on |
| D7 | PSX shorts | **blocked** | no borrow data; direction may still publish |
| D8 | Learned components | none in V1 | a rule that loses is more useful than a model that cannot be read |

**Owner-dependent (cannot be resolved from existing requirements):** D4 (which horizons the
product promises), D7 (whether PSX short research publishes at all), and the risk appetite that
sets D2.

---

## Review: contradictions, untestable requirements, trade-offs

**Resolved contradictions.**
- *"Decisive without manufacturing certainty"* vs *"return WAIT when evidence fails"* — resolved
  by making `WAIT` a first-class answer with a stated basis, not a failure to decide.
- *"Calibrated probability"* vs *no demonstrated edge* — resolved by D3: no probability in V1.
- *"Ten specialists"* vs *auditability* — resolved as ten **roles**, one pipeline.

**Genuinely untestable as written.**
- "World-class mathematician/scientist" is a direction of travel, not an acceptance criterion;
  nothing in this spec tests it and nothing should claim it.
- "Behavioural science" (R6) is only testable through proxies. V1 keeps it thin deliberately
  rather than inventing a sentiment number that cannot be falsified.
- "Realistic trade outcomes" is **untestable today** — no cost data exists for any market. Any
  simulated fill would be fiction, so V1 forbids `executable`.

**Major trade-offs accepted.**
- Rules over learned components: less ceiling, far more auditability. Given the first candidate
  showed no edge, auditability is worth more right now.
- One vote per family: deliberately discards information to avoid correlated double-counting.
  A correlated-but-real signal will be under-weighted. Accepted.
- 20-session embargo cuts the effective sample to ~54k. Accepted — the alternative is a number
  that is not real.

**The honest summary.** This specification describes a system that is mostly *not built*. What
exists today is the data foundation, the decision contract, the gate/log machinery and the
integrity rules. What is proposed is the evidence-family aggregation, the adversarial role, the
macro/event wiring and the learning lifecycle. The first candidate model produced no edge, and
nothing in this document should be read as predicting that the designed system will.
