# BRAIN Ω against this codebase

The target architecture, layer by layer, with what is actually built against each one. The
column that matters is the last: a layer is only "built" when a job writes rows and a page
reads them. Designed-but-absent is recorded as absent.

This file is the honest version. `brain.md` is the working brain; this is the map.

## Layer status

| Layer | Target | Here | Status |
| --- | --- | --- | --- |
| L0 Acquisition | collect from free sources | `jobs/prices.py`, `psx.py`, `signals.py`, `geo.py`, `marketplace.py`, `upcoming.py` | **built** |
| L1 Data integrity | validation, no silent loss | `source` on every row, no-invent rules, `Coverage` | **built** |
| L2 DLD / deterministic logic | boolean gates, state machines | thresholds as named constants; `SignalLog.status`, `Event.lifecycle`, `AssetThesis.status` as explicit states with named transitions | **built** — `jobs/thesis.py` is a real machine: active → weakening → broken, broken terminal |
| L3 Temporal world state | state at time t | `PriceSnapshot` (now with OHLC), `HumanSignal` per period, `Ranking` per `periodEnd`, `ThesisCheck` per assessment date | **partial** — snapshots and a frozen per-day record, no filtered state estimate |
| L4 Probabilistic inference | `P(S_t \| D_1:t)` | — | **absent** |
| L5 Statistical signal detection | robust deviation, change detection | `jobs/human.py`: robust z via median/MAD, spike vs persistent | **partial** — no CUSUM, no BOCPD |
| L6 Knowledge graph | `G_t = (V, E)` with edge provenance | `ProductAssetLink`, `EventLink`, industry membership; `jobs/graph.py` walks them | **built** — bounded two-hop propagation, every path stored in words |
| L7 Causal / systems | DAGs, mechanisms | — | **absent** |
| L8 Historical analog | distance, similarity, top-K | `jobs/analogs.py` | **built** — tolerance-based, not kernel-weighted |
| L9 Hypothesis engine | competing H, posterior odds | `jobs/attribution.py`: market / sector / specific as three exclusive accounts of one move | **partial** — magnitudes and shares measured, no posterior odds |
| L10 Attention / signal | multi-dimensional priority | catalyst radar, plus the one-step neighbourhood beside it | **partial** — two dimensions, no Pareto front |
| L11 Outcome engine | measure what followed | `SignalLog` at 1/5/30/60d, `jobs/accuracy.py` | **built** |
| L12 Learning + calibration | Brier, log loss, reliability | `jobs/audit.py`, `Calibration`, `SourceReliability` | **built** — mechanism live, data immature |
| L13 Self-audit | coverage, blindness, health | `jobs/audit.py`, `Coverage`, `jobs/stats.py` | **built** |
| L14 Explanation / UI | evidence package, provenance | every figure carries source, as-of, grade, note | **built** |

## What was violated and is now fixed

**§7 source lineage, §48 "never treat copied articles as independent confirmation".** The
catalyst flag counted `News` rows. Deduping by url cannot see syndication, because twenty
outlets genuinely have twenty urls, so one wire report read as twenty confirmations — the
exact prohibition. `jobs/lineage.py` clusters headlines into stories by token Jaccard inside
a time window, deterministically and with no model, and every count that measures
*information* now counts stories. The item count is kept beside it because the gap between
the two is itself the syndication measurement.

**§11 robust surprise.** The flag was a ratio against a mean. A news feed reliably produces
one busy day, and a mean baseline carries it into every later comparison. Now
`(x - median) / (1.4826 × MAD)`, and the ratio and the robust score must *both* clear their
thresholds — the ratio catches a jump off a quiet baseline, the robust score refuses one that
is ordinary variation for that feed.

**§12 spike vs persistent change.** Separated, because a loud afternoon and a fortnight of
heavier coverage are different events and only the second has moved the baseline that the
next comparison will be made against.

**§29/§30 coverage is not a score.** `Coverage` stores `gapRatio`, `missRisk`,
`criticality` and a status per source instead of a completeness percentage, because a dead
feed and a quiet week are identical in the data and only one of them is a finding.

**§31/§32 low evidence ≠ hidden.** The tone direction used to be *withheld* below eight
headlines. That was over-filtering: the site noticed something and said nothing, at exactly
the moment being early is possible. It is now published with a `thin` label and the count
beside it. Evidence strength controls interpretation, not visibility.

**§35 calibration.** A grade is a claim about frequency and was resting on nothing. Each
grade now carries an explicitly declared claimed hit rate, and `jobs/audit.py` measures
Brier, log loss and the actual rate against it. The declared rates are a starting point, not
a measurement, and they are visible so they can be argued with and revised.

**A state with no memory.** `AssetSetup` was honest about today and silent about yesterday.
A `buy` read written two weeks ago on conditions that had since reversed rendered identically
to one written this morning, which made the freshest and the stalest reading on the site
indistinguishable. `jobs/thesis.py` closes it: a thesis is the run of consecutive reads on
which one directional state was held, the opening day's conditions are *copied* onto the row
rather than re-derived, and every later day is measured against them. `broken` rests on the
invalidation level — the one part of a setup committed to in advance — and is terminal, so a
later recovery cannot erase the fact that it was passed. `ThesisCheck` keeps one frozen row
per assessment date, which is what makes the decay of a reason readable as a sequence rather
than as a status showing its last value.

**§44 no black-box arithmetic.** Every number above is computed in Python or SQL. No model
produces a figure, a probability, a date difference or a return anywhere in this codebase.

## Known gaps, and why each one is a gap

- **L4 / L9 — probabilistic state and posterior odds.** Competing hypotheses now exist as
  *measured magnitudes*: `jobs/attribution.py` splits a move into the part shared with the
  exchange group, the part shared with its own industry, and the remainder, which are
  exclusive by construction (`total = market + sector + specific`) rather than by argument.
  What is still absent is the probability attached to them. A likelihood ratio needs a
  measured `P(E|H)` and `P(E|¬H)`, and this system has zero matured outcome rows; choosing
  those numbers by hand is §48's "manufacture a number". The outcome log started on
  2026-10-01, so the earliest real likelihood ratios are 30 days after that. Every
  attribution row says in its own note that no probability is attached, so the partial state
  is visible on the page and not only here.
- **L7 — causal.** Same reason, plus the asset list is 160 names. Difference-in-differences
  and synthetic controls need either many units or a clean intervention, and a free daily
  close series for 160 tickers supports neither yet.
- **L6 propagation — §19/§20.** Built, and bounded. `jobs/graph.py` carries a flagged
  catalyst at most two hops over the stored edges, skips any edge group large enough to be a
  fact about the group rather than a connection between two of its members, and divides every
  edge by the size of the group it came from so a 20 name sector cannot outrank a two asset
  product link. What travels is *relevance*, meaning a reason to look — never impact. Every
  row stores the chain in words, which is what keeps it from being the "unsupported chain"
  §24 warns about: a reader can follow it and reject it.
- **L10 — full attention model.** Two dimensions now: the radar orders by spike size, and
  the neighbourhood beside it orders by graph distance from a spike. Pareto dominance across
  importance, evidence, urgency, novelty, surprise, historical support, network impact and
  coverage is the right shape and is still not implemented.
- **Regime engine (§13), Monte Carlo (§27), EVT (§28), hazard models (§17).** All need
  longer or denser history than is stored. PSX history is monthly before the last 120 days;
  product signals began on 2026-09-29.

## The rule these gaps follow

Everything above either reads stored rows or is absent. Nothing is half-built behind a
confident label, and no layer reports a number it cannot derive. That is the only way the
gap list stays useful: when a layer here says **absent**, it means no page is quietly showing
its output anyway.
