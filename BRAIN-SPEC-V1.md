# Brain Logic Specification V1.1

**Status: proposed design, frozen for review. Nothing here is implemented by this document.**
V1 written 2026-10-15. V1.1 finalises the three open decisions and specifies the aggregation
arithmetic exactly. No code, dataset, experiment or deployment was changed to produce it.

Labels used throughout:

| Label | Meaning |
|---|---|
| **[EXISTS]** | implemented in the repository today, verified by reading the code |
| **[VERIFIED]** | exists *and* is proven by a test or a recorded measurement |
| **[PROPOSED]** | design only; no implementation |

Sources of truth stay `brain.md` (reasoning log), `RESUME.md` (handoff), `ARCHITECTURE.md`
(layer map). This file is the only place the brain's decision logic is specified.

---

## 1. Mission and non-negotiable principles

**Mission.** For an eligible instrument at an eligible decision timestamp, produce the
best-supported directional research conclusion the data can justify — with its evidence,
counter-evidence, uncertainty and invalidation conditions — or decline to produce one.

1. **A conclusion is not a trade.** Direction and execution readiness are separate dimensions,
   never one score. **[EXISTS]** — `Decision.timeSense` is already distinct from `action`.
2. **`WAIT` has two kinds.** `file` = the measurement is unavailable. `evidence` = it is
   available and does not support acting. **[EXISTS]** — `WaitBasis` type, `Decision.basis`
   field, rendered by `WaitBasisChip`.
3. **No manufactured certainty.** A probability is published only where out-of-sample
   calibration passes (§5.6). Otherwise an ordinal strength, labelled as such.
4. **Nothing learns from the future.** **[VERIFIED]** — `featureDatedAfterSession: 0`,
   `setupDatedAfterSession: 0`; `USREC` excluded with an asserting test.
5. **History is append-only.** **[EXISTS]** — `DecisionLog` stores `rewardRisk` *as measured at
   the time*, so a later rebuild cannot answer a different question.
6. **Unknown is not zero.** **[VERIFIED]** — FX volume is stored null, never the provider's `0`.
7. **Beating a weak baseline is not evidence.** **[VERIFIED]** — the first candidate scored
   0.4211 against a 0.4204 majority class and is recorded as *no demonstrated edge*.

---

## 2. The three frozen decisions

### D4 — V1 prediction horizons: **swing only is claimable; position is a data requirement**

| Horizon | Sessions | Label available today | V1 status |
|---|---|---|---|
| scalp | < 1 | none | **out of scope** |
| intraday | 1 | `fwd1` (raw return, no label) | **out of scope** |
| **swing** | ~5–20 | **`label20`** **[VERIFIED]** | **claimable, subject to §9 tests** |
| **position** | ~60+ | **none in `examples-v3`** | **NOT claimable in V1** |

**The finding that decides this.** `examples-v3` carries exactly one label — `label20` — plus
raw returns `fwd1`, `fwd5`, `fwd20`. There is **no 60-session label**. Sixty-session outcomes
exist only in the 167-row event-reaction corpus, which is event-scoped and far too small to
validate a horizon on.

So the brief's caution is adopted literally: **a position-horizon capability may not be inferred
from `label20`.** Position becomes a *data requirement*, not a capability:

> **DR-1 [PROPOSED]** — build `label60` over the same universe and eligibility rule as `label20`
> (threshold restated for the horizon, maturity = 60 sessions, final 60 sessions excluded as
> immature), then evaluate it independently before any position-horizon claim.

**Intraday** is out of scope for a second, independent reason: intraday history is a rolling
~7-day window, not history. **[VERIFIED]**

**Horizon independence rules.**
- Each horizon is evaluated on its own samples, with its own baseline and its own embargo.
- A swing conclusion never implies a position conclusion, and vice versa.
- Every decision record carries the horizon it is about; a decision with no supported horizon
  is `WAIT`.
- **A longer-term directional bias never makes a current entry actionable.** Entry actionability
  is `timeSense`/`executionReadiness`, decided in §4 stage 5, not by direction.

**Acceptance tests per horizon** — §9 T-H1..T-H4.

### D7 — PSX bearish research vs executable short: **publish the research, withhold the execution**

A bearish conclusion is published when the evidence supports it. Execution is a separate gate.

| Condition | `action` | `executionReadiness` | Rule |
|---|---|---|---|
| Bearish evidence passes §4, borrow unknown | `SHORT` | `unverified` | research stands |
| Bearish evidence passes, security short-ineligible | `SHORT` | `blocked` | research stands |
| Bearish evidence passes, instrument suspended | `SHORT` | `blocked` | research stands |
| Bearish evidence passes, execution fully verified | `SHORT` | `executable` | **unreachable in V1** — no cost data exists for any market |
| Bearish evidence fails §4 | `WAIT` | n/a | basis `evidence` |

**Invariant D7-I.** The execution gate may withhold executability. It may **never** invent the
opposite direction, and it may never convert a failed `SHORT` into a `LONG`. A `LONG` requires
its own evidence passing §4 independently. **[EXISTS in spirit]** — `short-unbacked` is already a
distinct gate that withholds rather than reverses.

Tests: §9 T-D7a..T-D7d.

### D2 — Minimum evidence: **`MIN_NET = 2`, `MIN_FAMILIES = 3`**

Fixed initial thresholds, documented, **not to be tuned against evaluation results**. They are
design choices, not calibrated or optimal values, and no edge is claimed for them.

- **`MIN_FAMILIES = 3`** — at least 3 of the 6 families must be **eligible** (§3.2). Fewer →
  `WAIT` with basis `file`. This is a statement about *how much of the file is readable*.
- **`MIN_NET = 2`** — `|NET|` must be ≥ 2. Below → `WAIT` with basis `evidence`. This is a
  statement about *how decisive the readable evidence is*.

Changing either requires a specification amendment and a recorded reason; neither may move in
response to a result.

---

## 3. Evidence families and the aggregation formula

### 3.1 Sign convention

One convention everywhere: **positive supports LONG, negative supports SHORT, zero supports
neither.** No family has a private convention.

### 3.2 The six families

Correlated columns live in one family and produce **one vote**. `r5`, `r20`, `sma20` and `sma50`
are four numbers describing one fact; they are F1 and they vote once.

| Family | Inputs (current feature names) | Weight |
|---|---|---|
| **F1 trend** | `r5`, `r20`, `sma20`, `sma50` | 1 |
| **F2 participation** | `volumeRatio`, `r1` | 1 |
| **F3 volatility & range** | `atr14`, `rangePct`, `drawdownPct` | 1 |
| **F4 relative strength** | `relStrength`, `peerMedianR20`, `peers` | 1 |
| **F5 macro context** | point-in-time macro join **[PROPOSED]** | 1 |
| **F6 event context** | event/reaction corpus **[PROPOSED]** | 1 |

**Equal weights (all 1) are retained from V1.** Nothing yet justifies unequal weights, and fitted
weights would require an edge that does not exist.

**Eligibility.** A family is **eligible** when *all* hold:
1. at least one input is present and non-null,
2. no input is stale beyond its lane interval,
3. no integrity veto applies to its inputs (§3.5),
4. its inputs are not mutually contradictory in a way the family cannot resolve.

An **ineligible** family does not count toward `MIN_FAMILIES` and contributes 0 to `NET`.
An **eligible but inconclusive** family counts toward `MIN_FAMILIES` and contributes 0 to `NET`.
These two are recorded distinctly — the first is a `file` fact, the second an `evidence` fact.

### 3.3 Family score and vote

Each eligible family computes a score `s ∈ [-1, +1]`, then a vote by deadband `τ = 0.5`:

```
v = +1  if s >=  τ
v = -1  if s <= -τ
v =  0  otherwise
```

**F1 trend.** `a = sign(r20)`, `b = +1 if sma20 > sma50 else -1 if sma20 < sma50 else 0`.
`s_F1 = (a + b) / 2`.

**F2 participation.** Volume confirms the direction of the move it accompanied.
`s_F2 = sign(r1)` if `volumeRatio >= 1.2`; `0` if `volumeRatio < 1.2`.
Where volume is not published (FX), F2 is **ineligible**, never 0-as-neutral. **[VERIFIED]**

**F3 volatility & range.** `s_F3 = +1` if `drawdownPct > -5` and `rangePct` is in its lower
half (constructive); `-1` if `drawdownPct <= -15` or `atr14` exceeds its trailing median by
≥ 50% (stress); else `0`.

**F4 relative strength.** `s_F4 = sign(relStrength)` when `peers >= 3`; otherwise **ineligible**.

**F5 macro context [PROPOSED].** Joined on `observation_date + publicationLagDays`, never on
observation date alone. `s_F5` from a declared, published rule table. Until wired: **ineligible**.

**F6 event context [PROPOSED].** From dated events whose publication time precedes the decision
timestamp. **News alone can never set a direction** (§5.3): F6 may only vote in a direction
already supported by at least one of F1–F4. Until wired: **ineligible**.

All thresholds above (`τ = 0.5`, `1.2`, `-5`, `-15`, `50%`, `peers >= 3`) are **[PROPOSED]
design defaults**, chosen before any evaluation, and are not empirical findings.

### 3.4 NET, and how conflict affects it

```
eligible     = { families passing §3.2 }
NET          = Σ  w_i · v_i        over eligible families,  w_i = 1
longVotes    = count(v_i = +1)
shortVotes   = count(v_i = -1)
dissent      = min(longVotes, shortVotes)
```

`NET` is an integer in `[-6, +6]`. **Conflict is handled by subtraction**: every opposing family
reduces `|NET|` by 1. `dissent` is reported but is not a separate gate — a second threshold would
be a second thing to tune.

### 3.5 Vetoes, and when they apply

Two veto stages. **Neither can create or reverse a direction.**

**Stage 0 — integrity vetoes (before any voting).** Stale price beyond lane interval; bad bar
(close outside its own range) where the family needs the range; insufficient history; unadjusted
corporate action inside the window; non-session date. Effect: the affected inputs are withheld,
which may make families ineligible. If `eligible < MIN_FAMILIES` → `WAIT` / `file`.
**[EXISTS]** — `jobs/ohlc.py`, `session_bar()`, `stale` gate.

**Stage 5 — risk & execution vetoes (after a direction exists).** Missing borrow, short
ineligibility, suspension, unverifiable cost, invalidation already crossed. Effect: downgrade
`executionReadiness` and `timeSense`; may force `WAIT`. **May never flip the sign.**
**[EXISTS, partial]** — `stop-crossed` and `short-unbacked` already withhold without reversing.

### 3.6 Resolution table

Evaluated top to bottom; first match wins.

| # | Condition | `action` | `basis` | `gate` |
|---|---|---|---|---|
| 1 | Stage-0 veto leaves `eligible < MIN_FAMILIES` | `WAIT` | `file` | `file` / `stale` |
| 2 | `eligible < MIN_FAMILIES` | `WAIT` | `file` | `file` |
| 3 | `|NET| < MIN_NET` | `WAIT` | `evidence` | `thin-evidence` |
| 4 | `NET >= MIN_NET` | `LONG` | `null` | `long` |
| 5 | `NET <= -MIN_NET` | `SHORT` | `null` | `short` |
| 6 | Stage-5 veto on a direction from 4/5 | direction **kept**, `executionReadiness` downgraded; `WAIT` only if the veto is absolute | `null` | e.g. `short-unbacked` |

A tie (`NET = 0`) is row 3. There is no row that produces a direction from an absent one.

### 3.7 Worked examples (hand-calculable)

**Example A — a clean LONG.**
`r20=+6.2`, `sma20 > sma50`, `volumeRatio=1.4`, `r1=+0.9`, `drawdownPct=-3.1`, `rangePct` low,
`relStrength=+2.4`, `peers=11`. F5, F6 not wired.

| Family | eligible | s | v |
|---|---|---|---|
| F1 | yes | (+1 +1)/2 = **+1.0** | **+1** |
| F2 | yes | sign(+0.9) = **+1.0** | **+1** |
| F3 | yes | **+1.0** | **+1** |
| F4 | yes | sign(+2.4) = **+1.0** | **+1** |
| F5 | no | — | 0 |
| F6 | no | — | 0 |

`eligible = 4 ≥ 3` ✓ · `NET = +4` · `|NET| = 4 ≥ 2` ✓ → **LONG**, gate `long`, dissent 0.

**Example B — conflict pulls it under the bar.**
F1 `+1`, F4 `+1`, F2 `-1` (heavy volume on a down session), F3 `-1` (−17% drawdown).

`eligible = 4` ✓ · `NET = +1 +1 −1 −1 = 0` · `|NET| = 0 < 2` → **WAIT**, basis `evidence`,
gate `thin-evidence`, dissent 2. Both sides are published in `supporting[]`/`contradicting[]`.

**Example C — thin file, not thin evidence.**
FX pair: no volume (F2 ineligible **[VERIFIED]**), `peers = 0` (F4 ineligible), F5/F6 not wired.
Only F1 and F3 eligible, both `+1`.

`eligible = 2 < 3` → **WAIT**, basis **`file`**, gate `file`. Note `NET = +2` would have passed
`MIN_NET` — the decision is withheld because too little of the file is readable, which is a
different statement and is the one published.

**Example D — PSX bearish, execution withheld (D7).**
F1 `−1`, F3 `−1`, F4 `−1`, F2 eligible and `0`. `eligible = 4` ✓, `NET = −3` → **SHORT**.
Stage 5: borrow unknown → `executionReadiness = unverified`, `timeSense` not `NOW`,
gate `short-unbacked`. **The `SHORT` stands.** No `LONG` is produced.

---

## 4. Reasoning pipeline

One ordered, finite, loop-free sequence. It always terminates; `WAIT` is a legitimate terminus.
There is no "gather more evidence" branch.

```
0  snapshot + integrity        R1   → may veto (stage 0)
1  market state + horizon      R2   → regime, setupClass, horizon eligibility (D4)
2  hypotheses (bounded set)    R2/R7
3  evidence per family         R2 R3 R4 R5 R6
4  historical retrieval        R7   → retrieval only, never a feature
5  adversarial challenge       R8   → must state what would falsify each hypothesis
6  aggregate (§3)              —    → NET, eligible, dissent
7  risk & execution gates      R9   → may withhold, never reverse (stage 5)
8  emit decision + record      R10  → append-only
```

---

## 5. Specialist roles

Ten **roles**, one pipeline, not ten agents. Ten autonomous agents would make a deterministic,
cheap, auditable process slow, non-reproducible and hard to test, and buy nothing. A rule can be
read, argued with and shown wrong — the property this project has relied on every time a number
turned out to be an artefact.

| Role | Kind | Inputs | Outputs | On failure | Consumed by |
|---|---|---|---|---|---|
| **R1** integrity | deterministic | raw bars, sources, timestamps | validated snapshot, veto flags | veto → `WAIT`/`file` | all |
| **R2** structure | deterministic | validated snapshot | regime, setupClass, F1–F3 scores | family ineligible | R8, §3 |
| **R3** statistics | statistical | family scores, history | dispersion, sample counts, intervals | reports insufficiency | R8, R10 |
| **R4** macro | retrieval + rules | PIT macro join | F5 score | ineligible | §3 |
| **R5** news/events | retrieval + classification | dated events, filings | F6 score, materiality | ineligible | §3 |
| **R6** behaviour | derived measures only | volatility, volume extremes, positioning | behavioural hypotheses | silent | R8 |
| **R7** memory | retrieval | regimes, analogues, principles, past decisions | comparable cases | empty list | R8, R10 |
| **R8** adversary | deterministic challenge set | all of the above | falsification conditions, alternatives | must not be empty for a direction | §3, record |
| **R9** risk/execution | deterministic | direction, costs, eligibility | executionReadiness, timeSense | withhold only | record |
| **R10** learning | offline only | matured outcomes | evaluation, proposals | no silent change | humans |

**Learned components.** Only three are candidates, all **after** V1: evidence combination (R3),
analogue ranking (R7), event materiality (R5). Everything else stays rules.

**R6 is deliberately the thinnest.** Fear and greed are measurable only through proxies. V1
specifies **no sentiment score derived from headline text**; R6 produces hypotheses for R8 to
challenge, never a vote.

---

## 6. Frozen invariants (each testable)

| # | Invariant | Test |
|---|---|---|
| I1 | Missing data never becomes neutral or positive evidence | T-I1 |
| I2 | `file` WAIT stays distinct from `evidence` WAIT | T-I2 |
| I3 | News alone cannot force a directional vote (F6 needs F1–F4 agreement) | T-I3 |
| I4 | No future observation, outcome label or regime label reaches a predictor | T-I4 **blocking** |
| I5 | Regimes may stratify evaluation; never a feature | T-I5 |
| I6 | No probability published without passing calibration | T-I6 |
| I7 | Data-quality confidence is never presented as win probability | T-I7 |
| I8 | Stale or out-of-range price cannot support `NOW` | T-I8 |
| I9 | Costs/spread/slippage/borrow are never zero when unavailable | T-I9 |
| I10 | Decisions and snapshots immutable after recording | T-I10 **blocking** |
| I11 | Any rule/model change is versioned and evaluated before acceptance | T-I11 |
| I12 | Unknown or conflicting never forced into LONG/SHORT | T-I12 |
| I13 | A veto never creates or reverses a direction | T-I13 |

---

## 7. Edge cases

Condition → expected behaviour → output → test.

| # | Condition | Behaviour | Output |
|---|---|---|---|
| E1 | < N sessions history | families ineligible | WAIT/file |
| E2 | Whole feature group missing | family ineligible, named in `missing[]` | WAIT/file if eligible < 3 |
| E3 | Providers disagree | preserve both, family ineligible | WAIT/file, `conflicted` |
| E4 | Stale beyond lane interval | stage-0 veto | WAIT/file **[EXISTS]** |
| E5 | close outside high/low | range withheld; F3 ineligible | partial **[VERIFIED]** |
| E6 | Unadjusted action in window | flagged; affected families ineligible | **[VERIFIED]** |
| E7 | Delisted instrument | excluded; bias noted | n/a |
| E8 | Holiday / non-session | not a decision point | n/a **[VERIFIED]** |
| E9 | No published volume (FX) | **F2 ineligible**, not 0 | **[VERIFIED]** |
| E10 | News matched to wrong company | link rejected, F6 ineligible | — |
| E11 | Republished old story | dedupe by content hash | — **[EXISTS]** |
| E12 | Negated headline | no F6 vote | — |
| E13 | Macro revised after timestamp | original vintage used | — **[EXISTS]** |
| E14 | Limit move / halt | structure invalid | WAIT/file **[EXISTS]** |
| E15 | Flash crash | F3 stress → opposes | usually WAIT/evidence |
| E16 | False breakout | recorded as failure, not revived | — |
| E17 | Timeframes disagree | explicit mixed gate | WAIT/evidence **[EXISTS]** |
| E18 | Correlated indicators | one family, one vote | — |
| E19 | Direction fine, execution unknown | direction kept, `unverified` | **D7** |
| E20 | Label overlap at split | 20-session embargo | **[VERIFIED]** |
| E21 | Class imbalance (FX 68% FLAT) | per-class metrics required | **[VERIFIED]** |
| E22 | Model drift / unseen regime | degradation alarm; no silent change | — |
| E23 | A stopped setup revived later | forbidden; invalidation is terminal for that hypothesis | — |

---

## 8. Test matrix

| Tier | Scope | Fixture | Failure means |
|---|---|---|---|
| T1 unit | each family's score and eligibility | synthetic vectors | family rule wrong |
| T2 integration | pipeline on fixtures | recorded snapshots | wiring wrong |
| T3 lineage | every predictor traced to source + timestamp | manifest | provenance broken |
| T4 leakage | no future value reachable | dataset scan | **blocks training** |
| T5 corruption | missing source, truncated file, bad bar | mutated fixtures | recovery broken |
| T6 regime | COVID, 2022, 2018, bull runs | `regime_coverage.json` windows | brittle where it matters |
| T7 adversarial | false news, conflict, correlated evidence | crafted | over-confident |
| T8 survivorship | delisted names | `sec_lifecycle.json` | bias understated |
| T9 execution | cost absent ⇒ never `executable` | PSX fixture | over-claims tradability |
| T10 reproducibility | same snapshot ⇒ identical decision | snapshot id | not scientific |
| T11 history | old decisions unchanged after a model change | `DecisionLog` | memory corrupted |
| **T-H1..H4** | per-horizon: label exists, maturity, embargo, independent baseline | per horizon | horizon claim unfounded |
| **T-D7a..d** | bearish + borrow unknown / ineligible / suspended / verified | PSX fixtures | D7 violated |
| **T-I1..I13** | the frozen invariants | targeted | invariant broken |

**T4, T10, T11 are blocking.** Training may not begin while any fails.
Every test declares whether it expects a direction or a legitimate `WAIT`, so a suite cannot hide
a defect behind a `WAIT`.

---

## 9. Phase gates

1. **Approve and freeze this specification.** ← awaiting owner
2. Implement roles and rules; write regression tests **during** development.
3. Validate input contracts, lineage, leakage (T3, T4).
4. Train candidates **only** on approved, versioned datasets.
5. Compare against **both** the majority-class reference and the rule baseline, on identical
   chronological windows with the 20-session embargo.
6. Full regression + adversarial run after training.
7. Deployment is a separate decision requiring independent acceptance evidence.

**Accept a candidate** only if it beats both references out-of-sample, on identical samples, in
more than half the folds, **and does not degrade in the adverse regime**. The first experiment
failed exactly this last clause — its worst fold was 2022. That artifact is preserved and is not
re-run, tuned or extended by this specification.

---

## 10. Open decisions after V1.1

D2, D4 and D7 are **frozen** above. Remaining:

| # | Decision | Default | Owner input needed? |
|---|---|---|---|
| D1 | Family weights | equal (1) | no — amendment only |
| D3 | Publish a probability | no in V1 | no |
| D5 | Wire macro into F5 | yes, next milestone | no |
| D6 | Wire events into F6 | defer to V2 | no |
| D8 | Learned components | none in V1 | no |
| **D9** | Build `label60` for the position horizon (DR-1) | recommend yes | **yes — scope/cost** |
| **D10** | Deadband `τ` and family thresholds (§3.3) | as defaulted | **yes — risk appetite** |

---

## Review: consistency, untestable requirements, trade-offs

**Internal consistency.** The document is now internally consistent. Three V1 ambiguities were
resolved: `MIN_NET`/`MIN_FAMILIES` had no arithmetic definition and now do (§3.4); family scores
had no formulas and now do (§3.3); "position horizon" was implied as supported and is now
correctly a data requirement (D4). One V1 statement was **too generous and is corrected here**:
V1 implied the full decision contract existed, when what exists is `Decision{action, why, entry,
invalidation, timeSense, confidence, missing, notes, measured, gate, basis, plan, legs, intent,
developing}` — `snapshotId`, `horizon`, `regime`, `executionReadiness` and the family breakdown
are additions.

**Untestable as written, and labelled.**
- "Scientist-grade" / "world-class" is a direction of travel, not an acceptance criterion.
- R6 behavioural science is proxy-only; no falsifiable sentiment measure is specified.
- "Realistic trade outcomes" is untestable today — no cost, spread or borrow data exists for any
  market — so `executionReadiness = executable` is **unreachable in V1** by construction.

**Trade-offs accepted.**
- One vote per family discards information: a correlated-but-real signal is under-weighted. The
  alternative is four columns voting four times for one fact and calling it agreement.
- Equal weights are certainly not optimal. They are honest, and fitting them needs an edge that
  does not exist.
- `MIN_FAMILIES = 3` will produce many `file` WAITs on FX and thin PSX names. That is the correct
  failure direction: silence over invention.
- Conflict handled by subtraction only — no second dissent threshold, because a second threshold
  is a second thing to tune.

**The honest summary.** Most of this is not built. What exists is the data foundation, the
`Decision` contract, the gate ladder, `WaitBasis`, `DecisionLog` and the integrity rules. What is
proposed is the family aggregation, R6, R8, the macro/event wiring and the learning lifecycle.
The first candidate model showed no edge, and nothing here predicts the designed system will.
