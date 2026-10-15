# Design Review — D9 (position horizon) and D10 (thresholds)

**Round:** collaborative review with mandatory constructive challenge.
**Status:** review only. No specification was revised, no code changed, no label built, no model run.
**Head at review:** `eb0f276`.

This review disagrees with the specification in four places and with **my own prior
recommendations in two of them**. Where I was wrong, that is said plainly rather than softened.

---

## 1. Verified facts

Everything below was measured read-only during this review, or read from the committed record.

### 1.1 A 60-session label is abundant, not scarce

Counted over the same universe and eligibility rule `label20` uses, with maturity moved to 60
sessions and the final 60 sessions excluded as immature:

| | |
|---|---|
| `label20` examples (actual, in `examples-v3`) | **1,085,544** |
| `label60`-eligible rows (same universe) | **1,048,726** — 96.6% of `label20` |
| Assets with at least one 60-mature row | **612 of 616** |
| By class | stock 873,659 · crypto 92,483 · forex 52,543 · commodity 15,031 · etf 15,010 |

Effective **independent** windows, rows ÷ horizon:

| Horizon | Effective independent windows |
|---|---|
| 20 sessions | **54,277** |
| 60 sessions | **17,478** |

### 1.2 `MIN_NET = 2` means a different thing at every eligible count

Enumerating every vote combination that passes `NET >= 2`:

| Eligible families | Minimum agreeing | Maximum dissenting | Weakest passing split | Agreement among voters |
|---|---|---|---|---|
| 3 | 2 | 0 | 2L–0S–1 abstain | **100%** |
| 4 | 3 | 1 | 3L–1S–0 abstain | 75% |
| 5 | 3 | 1 | 3L–1S–1 abstain | 75% |
| 6 | 4 | 2 | 4L–2S–0 abstain | **67%** |

The same published threshold is unanimity in one case and a two-thirds majority in another.

### 1.3 `MIN_FAMILIES` counts families that have no opinion

Both of these publish `LONG`, and the record does not distinguish them:

```
eligible = 3   votes = (+1, +1, 0)                 NET = 2   voters = 2
eligible = 6   votes = (+1, +1, 0, 0, 0, 0)        NET = 2   voters = 2
```

So does this, on four agreeing families against two opposing:

```
eligible = 6   votes = (+1, +1, +1, +1, -1, -1)    NET = 2   voters = 6
```

Three materially different evidential states, one identical output.

### 1.4 `τ = 0.5` is not a dial

Attainable scores under §3.3 as written:

| Family | Attainable `s` |
|---|---|
| F1 trend | −1, **−0.5**, 0, **+0.5**, +1 |
| F2 participation | −1, 0, +1 |
| F3 volatility | −1, 0, +1 |
| F4 relative strength | −1, 0, +1 |

F2, F3 and F4 never produce a value strictly between 0 and 1, so **τ cannot change their vote at
any setting**. It binds on F1 alone, and there it has exactly one switch point:

| `s_F1` | τ=0.25 | τ=0.5 | τ=0.75 | τ=1.0 |
|---|---|---|---|---|
| ±0.5 | ±1 | ±1 | **0** | **0** |

τ is therefore a one-bit choice about F1 and nothing else: *does F1 vote when one of its two
signals is directional and the other is neutral, or only when both agree?*

### 1.5 F5 and F6 read the same causal object

Of 240 candidate events, by category: **26 monetary**, **4 macro-data** — the second-largest
category in the corpus. A policy decision is one cause that F5 sees as a macro series, F6 sees as
a dated event, and F1 sees as the price move it produced.

### 1.6 The standing result the thresholds sit on top of

The first candidate model scored **0.4211 against a 0.4204 majority class** — no edge. Nothing in
D9 or D10 changes that, and no threshold setting creates an edge that the data does not contain.

---

## 2. Disputed decisions, each with its strongest counterargument

### D9 — build `label60`?

**What V1.1 says.** Position is a *data requirement*, not a capability; `label20` may not be
stretched to a 60-session claim. **That conclusion stands and I do not dispute it.**

**Where I was wrong.** I classified D9 as a **scope-and-cost** decision, which implied producing
`label60` is a substantial lift. §1.1 contradicts me. The rows exist — 96.6% of the `label20`
count, across 612 of 616 assets. The transformation is the one that already produced `label20`
with a different maturity constant. Production cost is near zero. My framing was wrong and the
owner should not weigh this as a build-effort question.

**The strongest argument against building it anyway** — and it is stronger than my original one:

> Independence, not volume, is the binding constraint: 17,478 effective windows against 54,277,
> and a 60-session embargo consumes correspondingly more of every fold. The 20-session model
> already shows no edge. Building a second horizon before one validated finding exists doubles
> the search space and creates a second place to look for significance, with no multiple-comparison
> correction specified anywhere in V1.1. For a project whose central claim is *no fake certainty*,
> quietly acquiring a second lottery ticket is the specific failure mode to avoid.

**The counter to that.** The horizons are not substitutes and a null result at 60 sessions is
itself an honest, publishable finding. The danger is not the label; it is reporting whichever
horizon happens to look better. That danger is answered by pre-committing the analysis, not by
withholding the data.

### D10a — `MIN_NET` as an absolute threshold on a variable-length sum

**Counterargument:** a fixed integer cut on a sum whose length varies between 3 and 6 is not a
consistent standard (§1.2). It silently demands unanimity when little of the file is readable and
permits a third of families to dissent when all of it is. If anything, that is backwards — the
thinner the evidence, the *less* the sum should be trusted.

### D10b — `MIN_FAMILIES` counts abstainers

**Counterargument:** the gate is specified as a statement about *how much of the file is
readable*, which is a coherent purpose. But in combination with `MIN_NET` it allows a published
direction resting on **two opinions and one shrug** (§1.3), reported identically to one resting on
four. The gate is not wrong; the **record** is incomplete.

### D10c — conflict handled by subtraction

**Counterargument, against my own V1.1 text.** V1.1 defends subtraction with: *"`dissent` is
reported but is not a separate gate — a second threshold would be a second thing to tune."*
That argument is **insufficient**, and I retract it. It assumes the only alternative is another
threshold. It is not. Subtraction makes agreement and absence arithmetically identical: `+1,+1,0`
and `+1,+1,+1,-1` both yield NET = 2, and the second — where a family actively disagrees — is the
weaker case. Information is destroyed at the point where it matters most.

### D10d — F5 and F6 are not independent, and F6 can only amplify

**Counterargument:** NET sums families as if each were a separate witness. On the 30 monetary and
macro-data events (§1.5) F5 and F6 are one witness counted twice, and F1 reads the same cause a
third time through price. Worse, the guard in §3.3 — *"F6 may only vote in a direction already
supported by at least one of F1–F4"* — was written to stop news from inventing direction. Its
structural consequence is that **F6 can never contribute an independent vote at all**: by
construction it only ever adds +1 to a direction that already exists. A family that can only
amplify is not evidence; it is a multiplier wearing evidence's clothes.

### D10e — τ presented as a risk-appetite parameter

**Counterargument:** D10 lists τ as a parameter needing an owner risk call. §1.4 shows it is inert
for three of the four wired families and is a single yes/no about F1. Asking the owner to set a
number implies a sensitivity that does not exist and invites later tuning of something that cannot
move.

---

## 3. Recommended resolution, with hand-calculable examples

Four recommendations. Each is expressible in fields that already exist in `lib/decision.ts` and
`DecisionLog`; none adds a tunable number.

- **R1 — Keep `MIN_NET = 2` and `MIN_FAMILIES = 3`. Add no second threshold. Route `dissent` into
  the existing `confidence` field:** `High` when dissent = 0, `Medium` at 1, `Low` at ≥ 2. This
  answers D10a and D10c without a new knob — confidence is a report, not a gate, so there is
  nothing to tune against results.
- **R2 — Record `votingFamilies` (count of non-zero votes) beside `eligible` on every decision.**
  Answers D10b by making the difference in §1.3 visible instead of changing the gate.
- **R3 — F6 contributes to `confidence` and materiality, never to `NET`.** Follows directly from
  D10d: a family that may only agree cannot be a vote. This costs nothing today — F6 is
  ineligible until wired — and is far cheaper to decide now than after it ships.
- **R4 — Replace τ with a stated F1 rule.** Recommended: **F1 votes only when `sign(r20)` and the
  SMA cross agree** (equivalent to τ > 0.5). It produces more `WAIT`, which is the correct
  direction of error for this project, and it stops a single signal from carrying a family vote
  that F4 is likely to echo.

### Worked examples (every number hand-checkable)

Throughout: `eligible` = families passing §3.2; votes in family order F1–F4; F5/F6 unwired.

**(a) Balanced evidence — publishes today, should not read as confident**

```
F1 +1   F2 -1   F3 +1   F4 +1
eligible = 4   NET = +2   longVotes = 3   shortVotes = 1   dissent = 1
V1.1 today : LONG, confidence unaffected
With R1/R2 : LONG, votingFamilies = 4, confidence = Medium (one family disagrees)
```

**(b) Strong directional — the case the rule exists to pass**

```
F1 +1   F2 +1   F3 +1   F4 +1
eligible = 4   NET = +4   dissent = 0
V1.1 today : LONG
With R1/R2 : LONG, votingFamilies = 4, confidence = High
```

**(c) Conflicting families — subtraction hides the conflict**

```
F1 +1   F2 +1   F3 +1   F4 -1       NET = +2   dissent = 1
F1 +1   F2 +1   F3  0   F4  0       NET = +2   dissent = 0
```

Identical output today. Under R1 the first is `Medium`, the second `High` — and the second is
genuinely the stronger case, because nothing opposes it.

**(d) Low-information input — the gate working correctly**

```
FX pair: F2 ineligible (no published volume), F4 ineligible (peers = 0), F5/F6 unwired.
F1 +1   F3 +1
eligible = 2  <  MIN_FAMILIES = 3   ->   WAIT, basis = file, gate = file
```

Withheld because too little of the file is readable — not because the evidence was weak. The
distinction is already correct in V1.1 and R1–R4 do not disturb it.

**(e) Risk veto — withholds, never reverses**

```
F1 -1   F2 -1   F3 -1   F4  0    eligible = 4   NET = -3   ->   SHORT
Stage-5: borrow unknown   ->   action stays SHORT, executionReadiness = unverified
```

The direction survives; only executability is downgraded. Invariant D7-I holds under every
recommendation here — none of R1–R4 touches sign.

**(f) The τ choice, shown rather than argued** — `r20 > 0`, `sma20 = sma50` (no cross):

```
s_F1 = (+1 + 0)/2 = +0.5
tau = 0.5 (V1.1 today) -> F1 votes +1 ; with F3 +1 and F4 +1, NET = +3 -> LONG
R4 (both must agree)   -> F1 votes  0 ; with F3 +1 and F4 +1, NET = +2 -> LONG, dissent 0,
                                        but a flat trend no longer carries a trend vote
```

---

## 4. The exact decisions needed from you

Nothing proceeds until these are answered. Each is a plain yes/no.

| # | Decision | My recommendation | Why it is yours, not mine |
|---|---|---|---|
| **1** | Build `label60` now, with the analysis pre-committed before it is evaluated? | **Yes** — cost is near zero and a null result is honest | Doubling the search space before one validated finding is a research-integrity call |
| **2** | Adopt **R1** — `dissent` drives `confidence`, no second threshold? | **Yes** | How much dissent you are willing to publish under is risk appetite |
| **3** | Adopt **R3** — F6 contributes to confidence, never to `NET`? | **Yes** | Decides whether event context can ever carry direction |
| **4** | Adopt **R4** — F1 requires both signals to agree (τ retired as a parameter)? | **Yes** | It trades fewer calls for fewer weak calls; that is your tolerance to set |

R2 is a recording change with no behavioural effect; I recommend it regardless of 1–4.

If decision 1 is **yes**, the pre-commitment must be written and frozen **before** `label60` is
built — the same discipline `acceptance_scope.json` used, for the same reason.

---

## 5. Assumptions to reject outright

1. **That more eligible families means more evidence.** F5, F6 and F1 can be one cause counted
   three times (§1.5).
2. **That `NET` is a confidence or a probability.** It is an unweighted integer vote count over a
   variable number of dependent voters. It must never be rendered as a percentage.
3. **That `label60` is blocked by insufficient data.** 1,048,726 rows across 612 assets say
   otherwise. **This was my own error and it is corrected here.**
4. **That τ is a risk dial.** It cannot change three of four wired families at any value (§1.4).
5. **That a passing threshold implies an edge.** The thresholds are declared design defaults. The
   one measured model has no edge. A `LONG` that clears `MIN_NET` is a statement about the rule,
   not about the market.
6. **That `dissent` subtraction preserves the information it consumes.** It does not (§1.3, §2 D10c).
7. **That these thresholds may be adjusted after seeing evaluation results.** V1.1 forbids it and
   this review does not reopen it.

---

## 6. Confirmation: nothing was changed

Verified against `eb0f276`:

- `BRAIN-SPEC-V1.md` — **unmodified**. No revised specification produced this round, per the brief.
- No application code touched. No file under `lib/`, `jobs/`, `tools/` or `prisma/` modified.
- **No labels generated and no dataset altered.** `label60` does **not** exist; §1.1 is a count
  over existing rows, computed in a temporary script that was run and deleted and wrote nothing.
- No training, evaluation or tuning run. `acceptance_scope.json`, `readiness.json` and the
  baseline experiment artifacts are untouched.
- Nothing deployed.
- The only new file is this review.
