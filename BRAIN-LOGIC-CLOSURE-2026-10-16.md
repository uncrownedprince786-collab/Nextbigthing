# Workstream B — Brain Logic Final Closure

**Status:** read-only. No specification, code, test, API contract or methodology text changed.
**Head:** `eb0f276`. Output is an **approval-ready recommendation**, not a specification change.

Carried forward unchanged from `DESIGN-CLOSURE-2026-10-16.md` and not re-argued here: the rejection
of `1.2 × ATR14` as a reward-to-risk justification, the separation of `label60` from path/trade
outcome, the retention of `atr14` as a feature, the withdrawal of all effective-sample estimates,
and the preservation of the published evidence-grade and opposition-cap contract.

---

## B1. A units defect in my own proposed contract — found and corrected

**Verified from the implementation:**

| Quantity | Unit | Source |
|---|---|---|
| `atr()` return value | **absolute price units** — *"The average true range over the last `span` sessions, **in price units**"* | `jobs/factors.py:527-547` |
| `AssetFactor.atr14` | `Float?`, stored in price units | `prisma/schema.prisma:1897` |
| `fwd{h}` | **percent** — `(closes[h−1] / base − 1) * 100` | `tools/make_dataset.py:126-127` |
| `base` | the newest close **on or before** `as_of` | `tools/make_dataset.py:108` |

The contract I wrote in §3.6 of the closure report said `band_t = 2.0 × atr14_t`, *"in price units,
expressed as a percentage of base"* — a comparison of **a price against a percentage**, with the
conversion described in prose rather than specified. **That is a real defect and your challenge
caught it.** The measurement in §1.4 of that report was already done in percent, so the empirical
numbers stand; the formula as written did not.

**Corrected form:**

```
band_pct_t = m * atr14_t / base_t * 100
label60    = UP   if fwd60 >= +band_pct_t
             DOWN if fwd60 <= -band_pct_t
             FLAT otherwise
```

Both sides are now percent. The denominator is **`base_t`** — the same close `fwd60` is measured
from — not an independently fetched `close_t`, so the band and the return are strictly comparable
and no second price reference is introduced.

## B2. `m` — downgraded from candidate value to candidate *rule*

Your objection to the continuity argument is correct, and stronger than stated. The 1.83 figure
came from the **S&P 500 index**, which represents:

- not US single names — an index is less volatile than its constituents, so their ATR/close is higher;
- **not PSX at all** — and PK is **389,720 of 1,085,544 rows (35.9%)**, on 226 instruments
  (`readiness.json → coverageByMarket`).

So the calibration was performed on a proxy for roughly none of the universe. **`m = 2.0` is a
declared convention, not a calibration, and it is not an empirically proven optimum.**

**Recommended instead: freeze the *rule*, and compute `m` once from the actual universe before any
label exists.**

```
For each instrument i in the TRAINING-PERIOD rows only:
    implied_m_i = LABEL_THRESHOLD_PCT / (atr14_i / close_i * 100)     # = 2.0 / ATR%
m = median(implied_m_i), reported per market and per asset class, then frozen
```

This is a **descriptive statistic over an existing PIT feature and one frozen constant**
(`LABEL_THRESHOLD_PCT = 2.0`, `tools/make_dataset.py:68`). It touches no outcome, no label and no
model, so it cannot be tuned to a result — and it answers the question the index proxy could not:
*what ATR multiple does the existing frozen band already imply across the real universe?*

**Fallback if that statistic cannot be produced:** `m = 2.0`, pre-registered, with this limitation
recorded verbatim.

**Known limitations of the whole band, stated:** `m` is a convention under either route; ATR is a
*range* measure and the return is a *close-to-close* measure, so the band and the quantity it gates
are not the same kind of statistic; and per-market medians will differ, so one global `m` is a
deliberate simplification that the per-market report will make visible.

## B3. The `label60` contract — **PROPOSED**, pending approval

```
as-of               asOf ; every input uses closes <= asOf
base                newest close ON OR BEFORE asOf                [make_dataset.py:108]
forward window      60 stored sessions STRICTLY AFTER asOf, non-null close, oldest first
endpoint            closes[59]
return              fwd60 = (closes[59] / base - 1) * 100                      [percent]
band                band_pct_t = m * atr14_t / base_t * 100                    [percent]
                    atr14_t per jobs/factors.py atr(), bars cut off at asOf -- past-only
label60             UP if fwd60 >= +band_pct_t ; DOWN if <= -band_pct_t ; else FLAT
maturity            mature60 = fwd60 is not None
```

| Detail | Rule |
|---|---|
| **UP / DOWN** | the terminal 60-session move exceeded `m` times the asset's own average true range |
| **FLAT** | it did not — a **measured outcome**, never an imputation for a missing one |
| **Eligibility** | ≥ 15 trailing bars (`atr()` returns `None` below `span + 1`) and a valid `base` |
| **Immature** | fewer than 60 forward sessions → **row excluded, never labelled FLAT** |
| **Corporate actions** | excluded when an unadjusted action falls in the forward window (`basisBreakInWindow`, already computed) **or** in the 15-session ATR window — *the trailing-window exclusion does not exist today and must be added* |
| **Delisting** | series ends; final 60 sessions immature and dropped. No synthetic terminal value, no survivorship repair |
| **Quality flags** | the five `dataQualityExclusions` columns applied explicitly, not assumed filtered |
| **Implementation note** | `WINDOW = max(HORIZONS)` must become 60, changing the `forward_bars` query (`make_dataset.py:82-101`) |
| **Embargo** | 60-session purge at every fold boundary — the recorded plan is 20 (`readiness.json → splitPlan`), which would leak 40 sessions of every boundary row |

**Limits of the label, restated so it cannot be over-read:** it is a **terminal-movement** label.
It does not say a trade would have survived its path — `plan_outcome`
(`tools/make_dataset.py:141-161`) is the path-dependent label and remains separate. Class
distributions at 20 and 60 sessions will differ and must **not** be equalised; each horizon is
judged against its own majority class.

## B4. Canonical evidence mapping

Governing rule, which is the **shipped** design (`lib/decision.ts:460` — `macroVeto` is *"A veto
only: it can turn a LONG or SHORT into a WAIT and can do nothing else"*): **only asset-specific
evidence may cast a directional vote.**

| Canonical | Implementation | V1.1 | Kind | Votes | PIT | Duplication | Recorded | Absent / invalid |
|---|---|---|---|---|---|---|---|---|
| **E1 trend** | `setup`, `horizon`, `r20`, `sma20/50`; leg `timeframe` (`decision.ts:731`) | F1 | derived, own price | **YES** | closes ≤ `asOf` | shares series with E3, E5 | `legs`/`opposing` | stale → Stage-0 veto |
| **E2 participation** | `volumeRatio`, `r1`; leg `volume` | F2 | derived, own volume | **YES** | volume ≤ `asOf` | independent | `legs`/`opposing` | **FX: no volume → INELIGIBLE, never 0** |
| **E3 volatility** | `atr14`, `drawdownPct`, `rangePct`; **no leg today** | F3 | derived, own price | **YES** | closes ≤ `asOf` | shares series with E1 | `legs`/`opposing` | < 15 bars → INELIGIBLE |
| **E4 cross-sectional** | `relStrength`, `peers`; leg `peers` | F4 | derived, peer prices | **YES** | peers ≤ `asOf` | **removes the common factor by construction** | `legs`/`opposing` | `peers < 3` → INELIGIBLE |
| **E5 history** | `analogs`, `baseRateShare`+`baseRateCount`, `analogRefs`; leg `history`; floors 8/20/40 (`analogs.py:80-82`) | **none** | **historical prior** | **DISPUTED** | matched days < `asOf` | **re-reads E1/E3's observations** | `legs`/`opposing`, with share **and** denominator | < 8 matches → INELIGIBLE |
| **E6 trigger** | `entryTrigger`; leg `trigger` | none | raw event | **NO — timing** | own series ≤ `asOf` | independent | `notes` → `timeSense` | silent ~19 of 20 sessions; never "missing" |
| **E7 macro** | `macroVeto` (`decision.ts:460,655`) | F5 | context + integrity gate | **NO** | `observation_date + publicationLagDays` | **same cause as E8 on policy days** | `notes`, gate `macro-veto` | expired → no veto |
| **E8 event/news** | `news`, `newsCoverage`, `newsCount`, `eventInDays` | F6 | context | **NO** | published < decision | **same cause as E7** | `notes`, `missing`, event id | `"unavailable"` → **never a neutral tone** |

**Reconciliation with the six candidate families:** F1–F4 → E1–E4 and vote. **F5, F6 demoted to
context** (V1.1 promoting macro to a voting family is a regression from shipped behaviour).
**E5 added**, filling the gap where `history` had a leg and a `DecisionLog` audit record but no
family. **E6 explicitly not a family** — it answers *when*, not *which way*. Votes stay `{-1,0,+1}`,
equal weights; **`MIN_FAMILIES = 3` and `MIN_NET = 2` unchanged**; no new threshold introduced.

**Double counting is prevented structurally**, not procedurally: E7/E8 cannot vote, so one monetary
event cannot become two confirmations and no event-id matching is needed. E4 neutralises
common-factor moves on its own. Genuinely distinct observations survive: the announcement is
context, the price reaction it caused is E1/E3, whether volume confirmed it is E2. **Unresolved and
recorded:** E1, E3 and E5 all re-read one price series.

## B5. Votes, NET, confidence and the auditable record

```
votingSet        = {E1..E5}
eligibleFamilies = eligible members, INCLUDING those voting 0
NET = SUM(vote_i) ; d = sign(NET) ; support = |vote = d| ; opposing = |vote = -d|

GATE 1  eligibleFamilies < 3 -> WAIT, basis "file",     gate "file"
GATE 2  |NET| < 2            -> WAIT, basis "evidence", gate "thin-evidence"
GATE 3  NET >= +2 -> LONG       GATE 4  NET <= -2 -> SHORT
CONFIDENCE  WAIT -> Low ; support >= 3 -> High ; support == 2 -> Medium
            then opposing >= 1 -> one step down          [the published cap, preserved]
STAGE 5  risk/execution vetoes lower readiness; MAY NEVER CHANGE d
```

Because `NET ≥ 2` forces `support ≥ 2`, this reduces to: **High means at least three independent
families agree and none disagrees.**

**Persist vs derive** — avoid redundant counts; keep everything reproducible from traceable evidence:

| | Decision |
|---|---|
| Supporting families | **PERSIST as names** — `DecisionLog.legs` *(exists)* |
| Opposing families | **PERSIST as names** — `opposing` *(one new field)* |
| Eligible families | **PERSIST** — not derivable from the name lists |
| Abstentions, voting count, `NET` | **DERIVE** — persisting invites disagreement with their own inputs, the *"one count, two readers"* fault (`decision.ts:703`) |
| Unavailable / invalid | **DERIVE** (complement of eligible); detail in `missing`. **Never a 0 vote** |
| `confidence` | **PERSIST, unchanged**, with `logicVersion` |
| Measured model performance | **SEPARATE** — experiment artifacts; never a per-decision field |
| Execution readiness | **SEPARATE** — never changes `d` |

**Minimum auditable record for a capped grade: `eligibleFamilies`, `legs`, `opposing`.** Without
`opposing`, a capped `Medium` and an uncapped `Medium` are indistinguishable in the log, so the
cap — a promise published at `app/methodology/page.tsx:64` — could never be reviewed after the
fact. Names, not counts, for the reason `legs` already exists: a count cannot say *which* family
earned its place. From those three, `NET`, support, opposition and abstention counts all reproduce
exactly.

**`logicVersion` requirement.** `confidence` is a published contract — `confidenceIs: "evidence
grade"` (`app/api/signals/route.ts:48`) and the count-plus-cap rule
(`app/methodology/page.tsx:276, 64`). It is **not redefined in place**. A family-based path ships
under a new `logicVersion`, with the methodology page and the API field updated in the same change,
so historical rows keep their meaning and `tools/scorecard.py` never averages two semantics.

### Consistency checks (same rule set throughout; votes in E1–E5 order)

- **Clean agreement** `+1,+1,+1,INELIG,INELIG` → `eligible 3 · NET +3 · support 3 · opposing 0` →
  **LONG / High** · `legs "trend,volume,volatility" · opposing ""`
- **Strong majority, one objection** `+1,+1,+1,−1,+1` → `eligible 5 · NET +3 · support 4 · opposing 1`
  → base High, **capped → LONG / Medium** · `opposing "peers"`
- **Low information** (FX: no volume, `peers 0`, 5 matches) → `eligible 2 · NET +2` →
  **GATE 1 fails first → WAIT, basis `file`** — `NET` would have cleared `MIN_NET`; a coverage
  failure is never reported as weak evidence
- **Duplicate macro/news** `+1,+1,0,0,0` with E7/E8 context → `NET +2` → **LONG / Medium**
  (V1.1 as written would reach `NET +4` / High from one cause)

---

## B6. The four owner decisions, recovered verbatim and reassessed

From `DESIGN-CLOSURE-2026-10-16.md` §8, as written there.

### Decision 1 — *"Approve `label60` as an exploratory research label (not a capability claim)?"*

- **Evidence making it necessary:** `HORIZONS = (1,5,20)` — no `fwd60` exists
  (`tools/make_dataset.py:66`); `readiness.json` scopes its PASS to *"the agreed first training task
  only"*.
- **Recommended default: APPROVE** as exploratory only.
- **Strongest counterargument:** effective independent observations are unmeasured and
  unmeasurable in advance (the ρ that matters is the correlation of *prediction errors*), so the
  horizon may be unvalidatable and the work may yield only a null.
- **Why it still prevails:** a null is an honest, publishable result, and the two pre-registered
  kill switches stop the work before a model is fit if the label is redundant.
- **Alternative's consequence:** declining closes the position horizon for V1; the swing horizon is
  unaffected.
- **Objective or owner?** **OWNER** — it commits effort and opens a research direction. No code
  inspection resolves it.

### Decision 2 — *"Freeze `m = 2.0` with sensitivity `{1.0, 2.0, 3.0}`?"*

- **Evidence making it necessary:** `atr14` is in price units and `fwd60` in percent
  (§B1); `label20`'s band is a flat 2.0%; the 1.83 continuity figure came from an index proxy
  representing neither US single names nor the 35.9% of rows that are PSX.
- **Recommended default — CHANGED from the closure report: freeze the *rule*, not the value.**
  Compute `m` once as the median implied multiple over training-period rows, report it per market
  and asset class, then freeze. Fallback `m = 2.0` if that statistic cannot be produced.
- **Strongest counterargument:** a universe-median `m` is still one number imposed on markets whose
  ATR/close distributions differ, and the median hides that spread.
- **Why it still prevails:** the per-market report makes the spread visible, and the rule uses only
  a PIT feature and a frozen constant — no outcome, no label, no model — so it cannot be tuned.
- **Alternative's consequence:** freezing 2.0 outright keeps a convention calibrated on a proxy for
  almost none of the universe; leaving `m` open invites selection on results.
- **Objective or owner?** **OWNER** — the band is a product definition, and `m` is not derivable
  from evidence under either route.

### Decision 3 — *"Does E5 `history` vote, or modulate confidence as a prior?"*

- **Evidence making it necessary:** `history` is a shipped leg (`decision.ts:731`) with a graded
  floor (8/20/40, `analogs.py:80-82`) and the only per-leg audit record in `DecisionLog`
  (`baseRateShare` **and** `baseRateCount`) — yet V1.1 has no family for it.
- **Recommended default: it VOTES**, with its correlation against E1 measured once E3 and E5 are wired.
- **Strongest counterargument:** analogs are derived from the same price series E1 and E3 read, so a
  fifth vote may be a third reading of one source — the dependence used to demote E7/E8.
- **Why it still prevails:** excluding the best-audited evidence while admitting E3, which has no
  leg, no floor and no audit record, would be backwards.
- **Alternative's consequence:** as a prior it never reaches `NET`, so more decisions fall below
  `MIN_NET` into `WAIT`.
- **Objective or owner?** **OWNER.** `tools/scorecard.py` is built to settle this empirically — it
  *"compares matured outcomes with and without each leg"* — but **no scorecard output artifact
  exists in the repository** and the database is not reachable here, so the evidence that would
  decide it cannot be produced now.

### Decision 4 — *"Ship the family path under a new `logicVersion`, updating the methodology page and API in the same change?"*

- **Evidence:** `confidence` is published (`app/api/signals/route.ts:48`;
  `app/methodology/page.tsx:276, 64`), consumed by ~13 UI/API surfaces and by
  `tools/scorecard.py` (`SELECT … d.confidence …`), and the project's own invariant requires that
  decisions and evidence snapshots stay immutable.
- **Assessment: THIS IS NOT AN OWNER CHOICE — it is settled by inspection.** Redefining a published
  grade in place leaves stored values intact while silently changing what they mean, which corrupts
  every longitudinal comparison and breaks the immutability invariant in effect. The alternative is
  strictly worse on the evidence, with no trade-off to weigh.
- **Resolved as: version it.** Presenting this as a choice would be presenting a resolved
  code-inspection question as owner authority. *Whether the family path ships at all* remains a
  product decision and is covered by the specification freeze, not by this item.

---

## B7. Consolidated approval register

| # | Decision | Recommended default | Needs owner? |
|---|---|---|---|
| 1 | Approve `label60` as an **exploratory research label** (not a capability claim) | **Approve** | **YES** |
| 2 | Set `m` by the frozen **rule** (universe median implied multiple, training rows only, reported per market), fallback `m = 2.0` | **Approve the rule** | **YES** |
| 3 | Does **E5 `history`** vote, or modulate confidence as a prior? | **Votes**, measured once wired | **YES** |
| 4 | `logicVersion` rather than redefining `confidence` in place | **Version it** | **NO — resolved by inspection** |

**Three decisions require your authority.** Nothing in this report has been implemented, and the
specification is unchanged.

## B8. Change confirmation

No change was made to `BRAIN-SPEC-V1.md`, code, tests, API contracts, methodology text, datasets,
labels, training artifacts or deployments. No label generated, no model fit, no experiment run.
`git diff HEAD` reports no tracked file changed.
