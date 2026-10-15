# Adversarial Design Review — Round 2: D9, D10 and R1–R4

**Status:** read-only. Nothing was edited, generated, trained, implemented or deployed.
**Head:** `eb0f276`. **Reviewed:** `BRAIN-SPEC-V1.md` (V1.1), `DESIGN-REVIEW-2026-10-16.md`,
`lib/decision.ts`, `prisma/schema.prisma`, `tools/make_dataset.py`, `tools/full_history.py`.

This round found **four errors in my own Round-1 report**, one of which makes R1 unusable as
written. They are stated first because the rest of the review depends on them.

---

## 0. Corrections to Round 1

### 0.1 R1 commits the exact fault I accused the specification of

I charged §3.4 with destroying information by subtraction: `(+1,+1,0)` and `(+1,+1,+1,−1)` both
give `NET = 2`. Then I proposed routing `dissent` into `confidence` — which maps both to
`Medium`, destroying the same distinction one layer up. **R1 as written does not fix D10c.**

Worse, `confidence` is not a free field. `lib/decision.ts:753` already computes it:

```
Confidence is how much independently confirms the direction, not how it feels.
confirmations >= 2 ? "High" : confirmations === 1 ? "Medium" : "Low"
```

Overloading it with dissent would make one published grade mean "four agree, one objects" and
"one agrees, none objects" interchangeably. **R1 is withdrawn** and replaced by **R1′** (§3.3).

### 0.2 "Unanimity" was loose; the table was not

Round 1 §1.2's column was headed *"Agreement among voters"* and §1.3 printed `(+1,+1,0)` with
`voters = 2` — both correct. But the sentence under the table said the threshold *"is unanimity in
one case"* without qualification. `(+1,+1,0)` is unanimous **among voters**, not among eligible
families. **Your correction is right about the sentence**; the table and §1.3 already carried the
distinction. The policy consequence is in §3.2 below.

### 0.3 R2 was not a definition, and part of it already ships

"Record `votingFamilies`" is a name, not a behaviour. It is also partly redundant:
`DecisionLog.legs` **already stores** which confirmations backed a direction, as stable names.
What the log has never stored is **what opposed**. R2 is restated in §3.4 as exactly one new fact.

### 0.4 Both V1.1 and my review missed that six families duplicate five shipped legs

`lib/decision.ts:731` ships `LEGS = ["timeframe", "volume", "history", "peers", "trigger"]`.

| V1.1 family | Shipped leg | Status |
|---|---|---|
| F1 trend | `timeframe` | overlapping, **different inputs** — V1.1 uses `r20` + SMA cross; the leg uses two stored timeframe verdicts |
| F2 participation | `volume` | matches `volumeBacks` |
| F3 volatility | — | **family with no leg** |
| F4 relative strength | `peers` | matches `peersConfirm` |
| F5 macro | — | correctly absent: `macroVeto` is veto-only |
| F6 event | — | correctly absent: news is context-only |
| — | **`history`** (analog base rates) | **leg with no family** |
| — | **`trigger`** (entry rule fired) | **leg with no family** |

**V1.1 drops matched-history base rates from the evidence model entirely.** `DecisionLog` stores
`baseRateShare` *and* `baseRateCount` specifically so that leg can be audited, and §3.2 of the
spec never mentions it. This is a larger defect than anything in D10 and neither round caught it.
It is raised here as **Finding A** (§7) and is not resolved by R1–R4.

---

## 1. The exact R1–R4 definitions

Round 1 gave prose, not specifications. Below, each is stated operationally. **Where Round 1 had
no exact definition, the definition is new here and is labelled `[NEW — not in Round 1]`.**

Common quantities, all computed after Stage-0 vetoes:

```
state_i    ∈ {INELIGIBLE, ELIGIBLE}            for i in F1..F6
vote_i     ∈ {-1, 0, +1}                       defined only when ELIGIBLE
eligibleFamilies = |{i : state_i = ELIGIBLE}|
NET        = Σ vote_i                          over ELIGIBLE families
d          = sign(NET)                         the candidate direction
supportFamilies  = |{i : vote_i = d}|
opposingFamilies = |{i : vote_i = -d}|
```

### R1 — **WITHDRAWN** (see §0.1)

> *Was:* "Route `dissent` into `confidence`: High = 0, Medium = 1, Low ≥ 2."
> *Defect:* collides with the shipped meaning of `confidence` (a support count) and reproduces
> the information loss it was meant to cure.

### R1′ — Confidence grades support, then is capped by opposition `[NEW]`

- **V1.1 rule challenged:** none — V1.1 never says how `confidence` is set for a family decision.
- **Replacement:**

```
if action = WAIT                         -> confidence = "Low"      [shipped behaviour]
else:
    base = "High"   if supportFamilies >= MIN_NET + 1
           "Medium" if supportFamilies == MIN_NET
    confidence = (opposingFamilies >= 1) ? oneStepDown(base) : base
```

- **Why `MIN_NET + 1` is not a new tunable:** `NET = support − opposing ≥ MIN_NET` forces
  `support ≥ MIN_NET`, so `MIN_NET` is the publication floor. High is defined as *one agreeing
  family above the floor*. It is derived from `MIN_NET`, not chosen.
- **The cap is shipped behaviour generalised.** `lib/decision.ts:770` already does exactly this
  for one family: `if (peersAgainst(...)) return grade === "High" ? "Medium" : grade`, under
  rule 6 — *a grade must never be more confident than the note beside it.* R1′ extends that from
  `peers` to any opposing family. No new constant.
- **Inputs:** `supportFamilies`, `opposingFamilies`, `MIN_NET`. **Output:** `Confidence`.
- **Edge cases:** `support < MIN_NET` is unreachable while a direction publishes. `opposing ≥ 2`
  costs the same one step as `opposing = 1` — deliberately, because a second deduction would be
  a second tunable.
- **For:** reuses a shipped, already-tested rule; adds no constant; keeps "missing ≠ opposing".
- **Against (strongest):** a three-level grade cannot separate all states. `(support 2, opposing 0)`
  and `(support 3, opposing 1)` both land `Medium`. **R1′ therefore does not fix D10c either** —
  only R2′ does. R1′ is a readable summary, not the record.
- **Example that makes it necessary:** F1 +1, F2 +1, F3 +1, F4 −1 publishes `LONG` today with
  nothing marking the objection. Under R1′ it publishes `LONG / Medium`.
- **Test that would disprove it:** score matured `DecisionLog` rows grouped by grade. If `High`
  rows do not outperform `Medium` rows on realised move, the cap is adding noise, not signal.

### R2′ — Record the opposing families by name `[NEW — supersedes R2]`

- **V1.1 rule challenged:** §3.4 reports `dissent` as a number and stores nothing.
- **Replacement:** store one new field beside the existing `DecisionLog.legs`:

```
legs      (exists)  comma-separated names of families whose vote = d
opposing  (NEW)     comma-separated names of families whose vote = -d
                    "" means considered and nothing opposed; null means no direction
```

- **Everything else is derived, and must not be stored:**
  `votingFamilies = |legs| + |opposing|`; `abstainingFamilies = eligibleFamilies − votingFamilies`;
  `NET = |legs| − |opposing|`. Of the five candidate telemetry fields you listed, **two are
  redundant** (`votingFamilies`, `abstainingFamilies`) and `NET` is redundant once names are kept.
  The minimal sufficient record is `{eligibleFamilies, legs, opposing}`.
- **Why names, not counts:** `lib/decision.ts:703` states the project's own rule — *"One count,
  two readers"* — and `legs` exists precisely because *"the log held the grade and the gate and
  not the legs, so nothing could ever be learned about whether a leg earns its place."* Counts
  cannot answer which family earns its place; names can.
- **For:** this is the one fact the system has never recorded, and it is the only thing that
  actually separates `(+1,+1,0)` from `(+1,+1,+1,−1)`. **R2′ is the load-bearing recommendation**
  — Round 1 wrongly called it "a recording change with no behavioural effect".
- **Against (strongest):** it is pure cost until something reads it. `tools/scorecard.py` must be
  extended or the column is write-only.
- **Test that would disprove it:** after 200 matured rows, if outcomes for `opposing = ""` and
  `opposing ≠ ""` are statistically indistinguishable, opposition carries no information and the
  cap in R1′ should be dropped.

### R3 — F6 contributes to context and materiality, never to `NET`

- **V1.1 rule challenged:** §3.3 — *"F6 may only vote in a direction already supported by at
  least one of F1–F4."*
- **Replacement:** F6 never contributes to `NET`, and is excluded from `eligibleFamilies`. It is
  recorded as context and may raise `missing`/`notes`, never a vote.
- **The argument:** the guard was written to stop news inventing direction. Its structural
  consequence is that F6 can *only* add `+1` to a direction that already exists — it is
  arithmetically incapable of ever being evidence. A term that can only amplify is a multiplier,
  not a witness. This also enforces invariant I3 more strongly than the guard does.
- **Side effect that matters:** because F6 is removed from `eligibleFamilies` too, it can no
  longer help clear `MIN_FAMILIES`. Without that, F6 would inflate the readability gate while
  contributing nothing — the worst of both.
- **For:** eliminates F5/F6 double counting entirely (§3.6), at zero cost today since F6 is
  unwired.
- **Against (strongest):** genuinely novel information — an unscheduled 8-K, a sanction — is
  real evidence that F1–F4 cannot see for days. R3 makes the system structurally unable to act
  on it. That is a deliberate, costly choice, not a free one.
- **Test that would disprove it:** on the 168-event reaction corpus, if forward returns
  conditional on event direction differ materially from the unconditional distribution *after*
  controlling for the concurrent price move, F6 carries independent information and R3 is
  discarding it.

### R4 — Retire `τ`; state F1's rule directly

- **V1.1 rule challenged:** §3.3, `τ = 0.5`, listed in D10 as an owner risk-appetite parameter.
- **Finding:** `s` is attainable only at `{−1, 0, +1}` for F2, F3 and F4, so **τ cannot change
  their vote at any value**. For F1, `s ∈ {−1, −0.5, 0, +0.5, +1}` and τ has exactly one switch
  point, between 0.5 and 0.75. τ is a one-bit choice about F1 alone.
- **Replacement (recommended):**

```
F1 votes +1  iff sign(r20) = +1 AND sma20 > sma50
F1 votes -1  iff sign(r20) = -1 AND sma20 < sma50
F1 votes  0  otherwise
```

  Equivalent to τ > 0.5. `τ` is deleted from the specification.
- **Your question — mapping a continuous F1 score to a vote without test-set tuning — rests on a
  premise that does not hold for F1 as specified:** `s_F1 = (a+b)/2` over two sign variables is
  five-valued, not continuous. If F1 is *later* made continuous (standardised momentum, say),
  then the cut must be fixed by a pre-registered rule computed on training-period rows only, and
  frozen before any model is fit — the discipline `acceptance_scope.json` already used.
- **For:** removes a parameter that cannot move three of four wired families, and stops a flat
  trend (`r20 > 0`, no SMA cross) from carrying a trend vote that F4 is likely to echo.
- **Against (strongest):** requiring both signals makes F1 abstain far more often. Since F1 is
  one of only four wired families, more F1 abstentions means more `NET < 2`, which means more
  `WAIT`. If the system says `WAIT` on almost everything it is honest and useless.
- **Test that would disprove it:** replay stored sessions under both rules and count published
  directions. If τ > 0.5 cuts directional output by more than roughly half, the cost outweighs
  the precision and τ ≤ 0.5 should stand.

---

## 2. D9 — the 60-session label

### 2.1 Reconciling the reported estimate

`1,048,726` / `96.6%` / `612 of 616` came from a read-only count over existing `examples-v3`
rows, re-deriving maturity at 60 sessions. **It has not been independently recomputed this round
and no label was built.** Treat it as a reported estimate. The figure it implies —
`17,478` effective independent windows versus `54,277` — is `rows ÷ horizon`, which is a crude
upper bound on independence, not a measurement of it.

### 2.2 Recommendation: **approve as a future research target, with the analysis frozen first**

Not "build now". The sequence matters: **pre-registration, then the label, then one evaluation.**

The case against — that a second horizon doubles the search space while zero validated findings
exist, with no multiple-comparison correction anywhere in V1.1 — is the strongest argument in
this review. But it is an argument against **reporting**, not against **existence**. A label is
data; the integrity risk attaches to choosing which horizon to announce after seeing both. That
risk is answered by freezing the analysis plan, which costs nothing and is already this project's
established practice.

### 2.3 Answers to your six questions

**(1) Approve, defer or reject?** **Approve as a research target**, conditional on a frozen
analysis plan written and committed *before* the label is generated.

**(2) Target and deadband definition.** `label20` is, verbatim from `tools/make_dataset.py:135`:

```
fwd20   = (closes[19] / base - 1) * 100
label20 = UP if fwd20 >= +2.0, DOWN if fwd20 <= -2.0, else FLAT      (LABEL_THRESHOLD_PCT = 2.0)
```

Carrying ±2% to 60 sessions is **wrong**, because 60-session dispersion is larger and the `FLAT`
class would shrink — changing the base rate and making "beats majority class" mean something
different at the two horizons. Two defensible options, and they must not both be tried:

| Option | Band | Property |
|---|---|---|
| (a) volatility-scaled | `2.0 × √3 ≈ 3.46%` | assumes returns scale as √t |
| (b) **class-balance-matched (recommended)** | band chosen so the `FLAT` share at 60 equals the `FLAT` share at 20 | assumes nothing; uses only the label distribution |

**(b) is recommended** and is not tuning: it is computed **once, on training-period rows only,
never touching test-period data or any model output**, and frozen. Option (a) hard-codes a
√t assumption that the project has not verified.

**(3) Observation and maturity policy.** Identical in form to `mature20`:
`mature60 = fwd60 is not None`, where `fwd60 = closes[59]/base − 1`. Maturity is counted in
**stored sessions for that asset**, not calendar days. A row is immature — and excluded, not
imputed — whenever fewer than 60 forward sessions exist. This mechanically excludes the final 60
sessions of every asset, including the 4 of 616 with no mature row at all.

**(4) Split and embargo.** The 20-session work used 6 chronological folds with a 20-session
embargo. For 60:

- **Purge**, not merely embargo: every training row whose `asOf` lies within **60 sessions before
  a test block's start** has an outcome window overlapping the test period and must be dropped.
- Embargo must equal the horizon. A 20-session embargo on a 60-session label leaks by
  construction — 40 sessions of every boundary row's outcome sit inside the test block.
- Cost: roughly `folds × 60 sessions × assets` rows removed at boundaries. This must be reported
  as an explicit count, not absorbed silently.
- Folds stay chronological and strictly forward; no shuffling, no random splits.

**(5) Minimum acceptance conditions for a position-horizon claim.** All of these, pre-registered:

1. Accuracy exceeds the majority-class rate by a margin larger than the sampling error on
   **17,478 effective windows**, not on 1,048,726 rows — the row count is not the sample size.
2. The margin holds on the **worst fold**, not only in aggregate. The 20-session experiment's
   worst fold was 2022; a horizon claim that fails in one regime is a regime claim.
3. Predictions do not collapse toward a single class (the 20-session model's failure mode).
4. No feature carries information dated after `asOf`; leakage count 0, as `assemble.py` reports.
5. The comparison is stated against **both** the majority class and the `label20` result, and
   whichever horizon looks better is reported **together with the other**, never alone.

**(6) Does `label60` add information beyond `label20` and `fwd20`?** This is answerable cheaply
and without any model: once built, cross-tabulate `label20` against `label60` on the same rows
and measure concordance. **If agreement is very high, `label60` is a relabelling, not a second
horizon**, and the position-horizon claim should be abandoned before a single model is fit. This
test touches no test-set outcome and fits nothing, so it cannot be tuned. It should be written
into the pre-registration as a **kill switch**, with its threshold stated in advance.

### 2.4 A cost neither the specification nor Round 1 mentioned

`DecisionLog` carries `move1Pct/move5Pct/move20Pct` and `measured1On/5On/20On` — **there is no
60-session column**. A position-horizon capability requires a schema migration before a single
position decision can ever be scored. That is a real, unbudgeted cost of D9.

---

## 3. D10 — the recommended aggregation policy, fully defined

### 3.1 The formula

```
STAGE 0   integrity vetoes       -> may set state_i = INELIGIBLE. Never sets a vote.

eligibleFamilies = |{i : state_i = ELIGIBLE}|          (F6 excluded entirely, per R3)
NET              = Σ vote_i   over ELIGIBLE families
d                = sign(NET)
supportFamilies  = |{i : vote_i =  d}|
opposingFamilies = |{i : vote_i = -d}|

GATE 1    eligibleFamilies < MIN_FAMILIES (3)  -> WAIT, basis "file",     gate "file"
GATE 2    |NET| < MIN_NET (2)                  -> WAIT, basis "evidence", gate "thin-evidence"
GATE 3    NET >= +2                            -> LONG
GATE 4    NET <= -2                            -> SHORT

CONFIDENCE (R1′)
          WAIT                                 -> "Low"
          supportFamilies >= MIN_NET + 1       -> "High"
          supportFamilies == MIN_NET           -> "Medium"
          then: opposingFamilies >= 1          -> one step down

STAGE 5   risk / execution vetoes  -> may lower executionReadiness and timeSense, and may force
                                      WAIT. May never change d.

RECORD    eligibleFamilies, legs (supporting names), opposing (opposing names)
```

`MIN_FAMILIES = 3` and `MIN_NET = 2` are **unchanged from V1.1**. No threshold is added.

### 3.2 Answers to your D10 questions

**Does `MIN_FAMILIES` count all eligible, only voters, or both?** V1.1 §3.2 counts **all
eligible**, including eligible-but-inconclusive. Keep it. It measures *how much of the file is
readable*, which is a different question from *how decisive it is*, and the two gates emit
different bases (`file` vs `evidence`) precisely to keep them apart. Voters are recorded
separately via R2′ and are derivable, so both quantities exist without a second gate.

**Can 3 eligible families with only 2 directional votes qualify?** Yes: `(+1,+1,0)` → `NET = 2` →
`LONG`. **I do not recommend blocking it.** A `MIN_VOTERS` threshold would be a new tunable, and
the structural alternative is sufficient: under R1′ that case grades `Medium` (support = MIN_NET),
and under R2′ the record shows `legs` of length 2 against `eligibleFamilies = 3`. The reader sees
exactly what it rests on. **This is a deliberate refusal to add the threshold you invited.**

**Does a zero vote conflate "inconclusive" with "unavailable"?** No — V1.1 §3.2 already separates
them: unavailable data makes a family **INELIGIBLE** (a `file` fact); eligible-but-inconclusive
votes **0** (an `evidence` fact). This matches shipped precedent, where `newsCoverage:
"unavailable"` is explicitly never converted to a neutral tone, and a null `r20` is treated as
"not late" rather than late. **Verified existing behaviour; no change needed.** The defect is only
that `NET` alone cannot express the difference — which R2′ fixes.

**Is `MIN_NET = 2` consistent across 3 versus 6 eligible families?** No, and **I now partly
retract Round 1's framing of this as a defect needing repair.** Round 1 implied the inconsistency
was itself wrong. On reflection the fixed absolute threshold is the better of the available
designs: it states *"at least two more families agree than disagree"*, which is coherent and
direction-independent. Scaling the threshold with `eligibleFamilies` would make an asset with
richer coverage face a **higher** bar for identical evidence — penalising data availability,
which is worse. **Keep `MIN_NET = 2` absolute; make the difference auditable via R2′ rather than
repairing it in the gate.**

**Can equal `NET` carry different reliability?** Yes — `(+1,+1,0)` and `(+1,+1,+1,−1)` both give
`NET = 2`. R1′ grades the second `Medium` via the cap… and the first `Medium` too, via the
support floor. **The published grade does not separate them. Only the record does.** This is
stated plainly rather than hidden: a three-level scale cannot carry four-plus distinct states,
and pretending otherwise would be the fake certainty this project exists to avoid.

**Can one event be double-counted?** Yes. 30 of 240 corpus events are `monetary` (26) or
`macro-data` (4). **R3 fully eliminates the F5/F6 pair.** It does **not** eliminate F1/F5: a
policy decision moves price (F1 reads it as trend) and moves the macro series (F5 reads it
directly). **Nothing in V1.1, in Round 1, or in R1–R4 solves F1/F5 dependence.** It is an open
defect (§7, Finding B), and an owner decision.

**What does τ control?** F1 only; see R4. **Where is a threshold actually necessary?** Only at
`MIN_FAMILIES` and `MIN_NET`. Every other published number in §3.3 (`1.2`, `−5`, `−15`, `50%`,
`peers >= 3`) is an eligibility or scoring boundary inside one family, and each needs the same
pre-registration discipline — none may be moved after seeing a result.

### 3.3 Are the five candidate telemetry fields right?

| Field | Verdict |
|---|---|
| `eligibleFamilies` | **keep** — not derivable from the others |
| `supportFamilies` | **keep, as names** — already shipped as `DecisionLog.legs` |
| `opposingFamilies` | **keep, as names** — the one genuinely new fact |
| `votingFamilies` | **redundant** = support + opposing |
| `abstainingFamilies` | **redundant** = eligible − support − opposing |

`NET` is also redundant once both name lists are stored. Storing derived values invites them to
disagree with their inputs — the "one count, two readers" fault `lib/decision.ts` names explicitly.

---

## 4. The four mandatory scenarios

All use the §3.1 formula unchanged — `MIN_FAMILIES = 3`, `MIN_NET = 2`, R1′, R2′, R3, R4.
F5 and F6 are `INELIGIBLE` in A–C because they are unwired today.

### Case A — clean directional agreement

| Family | State | Vote |
|---|---|---|
| F1 trend | ELIGIBLE | **+1** (`r20 > 0` and `sma20 > sma50` — passes R4) |
| F2 participation | ELIGIBLE | **+1** (`volumeRatio 1.6`, up session) |
| F3 volatility | ELIGIBLE | **+1** (drawdown −3%, range in lower half) |
| F4 rel. strength | ELIGIBLE | **0** (`relStrength +0.2`, inside band) |
| F5 macro | INELIGIBLE | — |
| F6 event | excluded (R3) | — |

```
eligibleFamilies = 4   NET = +3   support = 3   opposing = 0   abstaining = 1
GATE 1: 4 >= 3 pass    GATE 2: |+3| >= 2 pass   GATE 3: LONG
CONFIDENCE: support 3 >= MIN_NET+1 = 3 -> High ; opposing 0 -> no cap -> HIGH
RECORD: eligibleFamilies 4 | legs "trend,volume,volatility" | opposing ""
```

**Output: `LONG`, confidence `High`.**

### Case B — mixed directional evidence

**B1 — resolves to WAIT:**

| F1 | F2 | F3 | F4 | F5 | F6 |
|---|---|---|---|---|---|
| **+1** | **+1** | **−1** | **−1** | INELIGIBLE | excluded |

```
eligibleFamilies = 4   NET = 0   GATE 1 pass   GATE 2: |0| < 2 -> WAIT
basis "evidence"   gate "thin-evidence"   confidence "Low" (WAIT is always Low)
RECORD: eligibleFamilies 4 | legs null | opposing null   (no direction, so no d)
```

**Output: `WAIT`, basis `evidence`.** The file was readable; it did not decide.

**B2 — stays directional, same rule, no threshold changed:**

| F1 | F2 | F3 | F4 | F5 | F6 |
|---|---|---|---|---|---|
| **+1** | **+1** | **+1** | **−1** | INELIGIBLE | excluded |

```
eligibleFamilies = 4   NET = +2   support = 3   opposing = 1
GATE 3: LONG
CONFIDENCE: support 3 -> High ; opposing 1 -> capped -> MEDIUM
RECORD: eligibleFamilies 4 | legs "trend,volume,volatility" | opposing "peers"
```

**Output: `LONG`, confidence `Medium`.** Under V1.1 today this publishes `LONG` with the
objection recorded nowhere.

### Case C — low information

An FX pair. No published volume → F2 `INELIGIBLE` (never 0). `peers = 0` → F4 `INELIGIBLE`.

| F1 | F2 | F3 | F4 | F5 | F6 |
|---|---|---|---|---|---|
| **+1** | INELIGIBLE | **+1** | INELIGIBLE | INELIGIBLE | excluded |

```
eligibleFamilies = 2   NET = +2
GATE 1: 2 < MIN_FAMILIES 3 -> WAIT, basis "file", gate "file"
```

**Output: `WAIT`, basis `file`.** Note `NET = +2` **would have cleared `MIN_NET`** — this is
exactly the case where a numeric threshold is met and the answer is still withheld, because too
little of the file could be read. Gate 1 runs before Gate 2 for this reason. `missing` names the
two unreadable families, and the WAIT is not reported as weak evidence.

### Case D — overlapping causal evidence

A policy decision. Price rose on it (F1), the macro series moved (F5), the dated event is in the
corpus (F6). F2 and F3 are independent of the event.

| Family | State | Vote |
|---|---|---|
| F1 trend | ELIGIBLE | **+1** — reads the price move the decision caused |
| F2 participation | ELIGIBLE | **+1** — independent |
| F3 volatility | ELIGIBLE | **+1** — independent |
| F4 rel. strength | INELIGIBLE | — |
| F5 macro | ELIGIBLE | **+1** — reads the same decision |
| F6 event | — | the same decision again |

```
V1.1 AS WRITTEN:
  F6 permitted (direction already supported by F1) -> eligible 5, NET = +5, support 5
  Output: LONG, and the record shows five agreeing families for what is partly ONE cause.

UNDER R3 (F6 never votes, excluded from eligibleFamilies):
  eligibleFamilies = 4   NET = +4   support = 4   opposing = 0
  Output: LONG, confidence HIGH
  RECORD: legs "trend,volume,volatility,macro" | opposing "" | F6 recorded in notes as context
```

R3 stops the single event being counted **three** times and holds it to two (F1 and F5), while
F2 and F3 — genuinely distinct evidence — still count in full. **The residual F1/F5 overlap is
not solved**, and the record makes it visible rather than invisible: a reader seeing `trend` and
`macro` both firing on a policy session can see the shared cause. That visibility is the
mitigation on offer; it is not a fix, and §7 Finding B puts the real fix to you.

### `file` versus `evidence` WAIT

| Basis | Meaning | Cases here |
|---|---|---|
| `file` | A measurement was **not available**. Too little of the file could be read for any verdict. Emitted by Gate 1 and by Stage-0 vetoes. | **C** |
| `evidence` | Measurements **were** available and do not decide. The file was readable; it said nothing conclusive. | **B1** |

The distinction is already shipped (`WaitBasis = "file" | "evidence"`, rendered by
`WaitBasisChip`) and must not be collapsed: "we could not look" and "we looked and it was
balanced" are different claims about the world.

---

## 5. Invariants: all preserved

| Invariant | Status under R1′–R4 |
|---|---|
| Vetoes block, never force or reverse direction | **Preserved** — Stage 0 only sets `INELIGIBLE`; Stage 5 only lowers readiness. No recommendation touches `d`. |
| Missing/stale/invalid is not a neutral vote | **Preserved and strengthened** — Case C shows `INELIGIBLE ≠ 0`. Matches shipped `newsCoverage: "unavailable"`. |
| Correlated indicators are not independent confirmations | **Partly** — R3 fixes F5/F6; F1/F5 remains open (Finding B). |
| News is context, cannot force a direction | **Strengthened** — R3 makes it structurally impossible, not merely guarded. |
| Bearish PSX research valid when execution blocked | **Preserved** — D7 untouched; Case-E logic from Round 1 still holds. |
| Execution readiness separate from direction | **Preserved** — Stage 5 is after `d`. |
| No calibrated win probability without out-of-sample calibration | **Preserved** — `NET` must never render as a percentage (§5 of Round 1). |
| No look-ahead from regime labels or outcomes | **Preserved** — D9 §2.3(4) requires leakage count 0; the 60-session purge in 2.3(4) is stricter than today's. |
| Historical decisions and experiment artifacts preserved | **Preserved** — nothing altered this round. |

---

## 6. Verified existing behaviour versus proposed change

| Item | Status |
|---|---|
| `Confidence = "High"\|"Medium"\|"Low"`, `confirmations >= 2 ? High : …` | **VERIFIED EXISTING** — `lib/decision.ts:100, 753` |
| Rule-6 one-step cap on `peersAgainst` | **VERIFIED EXISTING** — `lib/decision.ts:770` |
| `LEGS = timeframe, volume, history, peers, trigger`; `DecisionLog.legs` | **VERIFIED EXISTING** |
| `WaitBasis = "file" \| "evidence"` | **VERIFIED EXISTING** |
| `label20 = UP if fwd20 >= +2.0, DOWN if <= -2.0, else FLAT` | **VERIFIED EXISTING** — `tools/make_dataset.py:68,135` |
| `mature20 = fwd20 is not None` | **VERIFIED EXISTING** |
| No `move60Pct` / `measured60On` in `DecisionLog` | **VERIFIED ABSENT** |
| `τ` inert for F2/F3/F4 | **VERIFIED** by enumeration of attainable scores |
| 26 `monetary` + 4 `macro-data` of 240 events | **VERIFIED** from `data/foundation/events/events.json` |
| 1,048,726 `label60`-eligible rows; 17,478 effective windows | **REPORTED ESTIMATE** — Round 1, not recomputed here |
| R1′, R2′, R3, R4 | **PROPOSED — none implemented** |
| `label60` itself | **DOES NOT EXIST** |

---

## 7. Open findings neither round resolves

- **Finding A — `history` has no family.** V1.1's six families omit matched-history base rates,
  which ship as a confirmation leg and are logged with `baseRateShare` + `baseRateCount` for
  audit. Either the spec gains an F7 for base rates, or it must state why the strongest-audited
  leg is excluded. **Not addressed by R1–R4.**
- **Finding B — F1/F5 dependence is unsolved.** R3 removes F6. A policy decision still reaches
  `NET` twice, through price and through the macro series.
- **Finding C — `trigger` has no family**, though it is arguably timing (`timeSense`) rather than
  direction, and may legitimately belong outside the evidence model. Needs an explicit statement.
- **Finding D — no multiple-comparison policy exists** anywhere in V1.1, and D9 makes one necessary.

---

## 8. Owner decisions still needed

| # | Decision | Recommendation |
|---|---|---|
| **1** | Approve `label60` as a research target, label built **only after** a frozen analysis plan? | **Yes** |
| **2** | `label60` band: class-balance-matched on training rows only (b), or √3-scaled (a)? | **(b)** |
| **3** | Adopt **R1′** (support-graded confidence, one-step cap generalising rule 6)? | **Yes** |
| **4** | Adopt **R2′** (record opposing family names; store nothing derivable)? | **Yes — the load-bearing one** |
| **5** | Adopt **R3** (F6 never votes, excluded from `eligibleFamilies`)? | **Yes** |
| **6** | Adopt **R4** (retire `τ`; F1 requires both signals)? | **Yes**, subject to the replay test in R4 |
| **7** | **Finding A** — add a base-rate family, or state why not? | Add it; this is the larger defect |
| **8** | **Finding B** — accept F1/F5 overlap as visible-but-unfixed, or define a dependence rule? | Accept as visible for V1; revisit when F5 is wired |

**R1 (original) is withdrawn and needs no decision.**

---

## 9. Confirmation

- No file edited; no specification revised; `BRAIN-SPEC-V1.md` unmodified.
- No label generated, no dataset altered; `label60` does not exist.
- No training, evaluation, tuning or deployment. No code implemented.
- Historical decisions and experiment artifacts untouched.
- The only new file is this review. **No revised specification has been produced, and none will
  be until decisions 1–8 are settled.**
