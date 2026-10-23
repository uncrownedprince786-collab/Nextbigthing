# The crypto brain learns when to say nothing — 2026-10-23

Picks up from `CRYPTO-FORECAST-HANDOFF-2026-10-21.md`. Everything below is in the repository and
deployed unless it says otherwise. Live: <https://nextbigthing-nu.vercel.app> · commit `48e4e30`.

---

## 1. What changed

**The brain now answers only when it has something to say.** Every served lane used to print a
direction on every bar. The best of them was right 53.1% of the time doing that — a real edge, and
thin enough that a reader on a near-indifferent bar was being handed a word the model did not mean.

Each lane now carries a **conviction floor**: how far from even its probability must be before a
direction is printed. Inside it the panel says *No clear pattern*, with the margin, the floor, the
bars it read and what the lane scores when it does speak.

| lane | every bar | when it speaks | coverage | called majority | day-blocked 95% CI | WF |
|---|---|---|---|---|---|---|
| btc m5 | 0.5153 | **0.5434** | 10.9% | 0.5178 | [+0.0131, +0.0391] | 5/5 |
| btc m15 | 0.5270 | **0.5655** | 18.4% | 0.5097 | [+0.0426, +0.0682] | 5/5 |
| btc h1 | 0.5267 | **0.5745** | 13.4% | 0.5213 | [+0.0257, +0.0843] | 4/5 |
| crypto m5 | 0.5314 | **0.6193** | 10.2% | 0.5144 | [+0.0917, +0.1182] | 5/5 |
| crypto m15 | 0.5246 | **0.5586** | 14.6% | 0.5000 | [+0.0426, +0.0733] | 5/5 |

All five servable lanes earned a floor. None of the nine refused lanes has one, by rule.

### The 90% target is still NOT met

The best lane is **61.9% on the 10.2% of bars it speaks on**. That is a large, well-tested edge —
the interval excludes zero by nine points, the walk-forward is 5/5, both directions are called —
and it is not 90%, and it is not 61.9% of *all* bars. Coverage is printed beside every accuracy on
the site for exactly that reason. Do not let a later change drop it: "right 62% of the time" with
the coverage removed is a different and false claim.

## 2. How the floor was chosen, and why it is defensible

Fixed in `tools/research/crypto_conviction.py` before the test fold was read:

> the **highest** margin floor at which the model still speaks on at least one **validation** bar
> in ten.

Accuracy on called rows rises monotonically with the floor in every lane, so maximising it without
a coverage floor selects "speak almost never". The one-in-ten floor is the product decision, stated
rather than tuned. The gated lane is then measured **once** on the test fold against the called
rows' **own** majority — a floor selects rows, and a selection moves the base rate it should be
judged against.

Its gates mirror the ungated ones: above the called majority, both directions called, a day-blocked
bootstrap excluding zero, four of five chronological blocks above their own majority, and coverage
holding above 5% out of sample.

**Conviction can quiet a lane that passed. It can never promote one that did not.** Re-running the
gates on a subset of a lane that already failed them on the whole is multiple testing, and
`crypto_lanes.py` refuses to attach a floor to a refused lane. If that is ever revisited it needs a
fresh pre-registration and a holdout this one has not touched.

Reproduced faithfully: the conviction run rebuilds the matrix, the split and the scoring from
scratch, and its ungated accuracy matches every artifact manifest to five decimal places.
`tests/conviction.test.ts` asserts that, and six other properties, on every run.

## 3. A silence is recorded like a call

Migration `20261023200000_brain_forecast_conviction` adds `called` (default TRUE, so every earlier
row reads as what it was) and `convictionFloor` to `BrainForecast`. An uncalled bar is stored with
the lean it did not print and the floor in force, and `jobs/forecast_score.py` grades it.

Nothing adds the two together. The record page, the asset panel and the scorer all report called
and quiet separately: a silence was not a claim, and the only reason to grade one is to find out
whether staying quiet was the right choice. A quiet rate near a half means the floor is working; a
quiet rate near the called rate would mean it is discarding good calls.

## 4. Carried forward from the last handoff

- **Binance from Vercel is solved.** Measured on the deployed site: `data.venue` is
  `Binance (public data mirror)` and `data.quality` is `ok`, with nothing imputed. The train/serve
  feature mismatch that marked every production forecast degraded is gone.
- **Latency is fine on the forecast path.** `/api/forecast` answers in 1.2–4.5 s; the asset page's
  seven-to-ten seconds is still its seventeen other database reads, not the model.
- The prospective record now holds real results: 531 graded, 52.0% overall — 54.6% at five minutes,
  50.0% at fifteen, 43.0% at an hour. All from before the floors existed, so all ungated, and all
  below the 30-per-lane bar at which a rate is shown per lane.

## 5. What I measured and did not ship

A validation-fold capacity sweep on `btc m5` over depths 3 to 6
(`data/foundation/dataset/crypto_capacity_btc_m5.json`): 0.5158, 0.5171, 0.5167, 0.5189. The
deepest tree gains 0.31 points on 62,483 **overlapping** rows, which is inside the noise once the
day blocking that every other number here uses is applied. **No model was retrained on it.** The
sweep is committed as the measurement that found nothing, which is worth as much as one that does.

`tools/research/crypto_capacity.py` reads the validation fold only; the test fold is not loaded by
that file at all. `train_crypto_short.py` remains the only thing that reads it, once.

## 6. What I would do next

### a. Give the pooled model market-wide context

The strongest idea left, and the only one that adds *information* rather than capacity. Every
feature in `crypto-intraday-f1` is computed from one coin's own bars. Crypto is heavily
factor-driven — most of an altcoin's five-minute move is Bitcoin's move — so the pooled model is
currently being asked to read idiosyncratic direction without being shown the factor it is
idiosyncratic *to*.

Concretely: the coin's return minus Bitcoin's over the same windows, Bitcoin's own state at that
instant, and the coin's recent beta to it. That is a feature-schema change (`f2`), so it needs the
Python definition, the `lib/intradayFeatures.ts` mirror, a new parity fixture, a retrain and a
re-measure — and the conviction floors recomputed on the new artifacts afterwards.

Measure it before building it: `crypto_capacity.py` already loads a pooled matrix and scores a
validation fold, so a column block appended to `crypto_matrix.py` answers "does this help" without
touching the serving path.

### b. The session-and-longer horizons are a genuine negative result

Every horizon from one UTC day out fails its gates, pooled across 65 coins and on Bitcoin alone,
on 4-hour history back to 2017. That is not a tuning problem and should not be presented as one.
Conviction will not rescue them — see §2 on why a floor may not promote a refused lane.

### c. Smaller things

- `train_crypto_short.py` writes `rowStride: 1` into every manifest regardless of `--stride`:
  `res` never carries the value `res.get("stride", 1)` reads. The pooled fits used stride 5.
  Harmless to the models, wrong in the record.
- `.claude/launch.json` still carries the unrelated pre-existing change. Left alone, again.
- A pooled `flow` sweep (what the three taker features are actually worth, for a Coinbase
  fallback) was started and stopped unfinished: one configuration on 645,329 rows ran for over an
  hour, and the question it answers stopped mattering the moment the Binance mirror came back
  reachable. Worth running if the chain ever falls past Binance again; not worth five hours now.

## 7. Where the new things are

```
tools/research/crypto_matrix.py      the pooled feature matrix, cached on disk by corpus content
tools/research/crypto_conviction.py  choose a floor on validation, measure it once on test
tools/research/crypto_capacity.py    validation-only capacity and feature-set sweep
tests/conviction.test.ts             seven properties the floors must keep
lib/cryptoLanes.ts                   LaneConviction, and `speaks()` -- the serving rule
lib/cryptoForecast.ts                the `quiet` kind
components/cryptoBrain.tsx           QuietBody
prisma/migrations/20261023200000_brain_forecast_conviction
```

Recompute the floors after any retrain:

```bash
python tools/research/crypto_conviction.py
python tools/research/crypto_lanes.py
npm run test:web
```
