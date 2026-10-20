// The TypeScript feature set against the Python one that trained the model.
//
// This is the test that makes the duplication in `lib/intradayFeatures.ts` safe. The model is
// fitted in Python over four hundred thousand bars and served from a Node request handler, so one
// feature set has two implementations; a component that drifts between them is invisible in every
// metric the site shows -- the forecasts simply stop working, slowly, and nothing goes red.
//
// `tools/research/write_parity_fixture.py` writes the fixture from real bars (three windows, two
// intervals) and records what `intraday_features.features_at` -- the definition -- returned for
// each. Here the TypeScript recomputes them and every component is compared. The fixture is
// committed, so this needs neither Python, a corpus nor a network.
//
// The tolerance is tight on purpose. These are not two algorithms that should roughly agree; they
// are the same arithmetic written twice, and anything above float noise is a real divergence.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { featuresAt, contiguous, FEATURES, FEATURE_VERSION, WARMUP, type Bar } from "../lib/intradayFeatures.ts";
import { HORIZONS, HORIZON_ORDER, horizonFrom, maturesAt } from "../lib/cryptoHorizons.ts";
import { probabilityUp, type Artifact } from "../lib/cryptoModel.ts";

interface Fixture {
  featureSchema: string;
  featureNames: string[];
  warmup: number;
  cases: {
    symbol: string;
    interval: string;
    bars: Bar[];
    expect: { i: number; features: number[] }[];
  }[];
}

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/intradayParity.json", import.meta.url), "utf8"),
) as Fixture;

test("the fixture was produced by the feature set this build computes", () => {
  assert.equal(fixture.featureSchema, FEATURE_VERSION);
  assert.equal(fixture.warmup, WARMUP);
  assert.deepEqual(fixture.featureNames, [...FEATURES]);
});

test("every feature matches the Python definition on real bars", () => {
  let checked = 0;
  let worst = 0;
  let worstAt = "";
  for (const c of fixture.cases) {
    for (const e of c.expect) {
      const got = featuresAt(c.bars, e.i);
      assert.ok(got, `${c.symbol} ${c.interval} row ${e.i}: TypeScript refused a row Python read`);
      assert.equal(got.length, e.features.length);
      for (let j = 0; j < got.length; j++) {
        // Relative where the value is large, absolute where it is near zero -- a log return of
        // 1e-5 would otherwise need an impossible relative tolerance, and a price-scaled feature
        // would hide a real error behind an absolute one.
        const scale = Math.max(1, Math.abs(e.features[j]));
        const d = Math.abs(got[j] - e.features[j]) / scale;
        if (d > worst) {
          worst = d;
          worstAt = `${c.symbol} ${c.interval} row ${e.i} ${FEATURES[j]}: ` +
            `${got[j]} vs ${e.features[j]}`;
        }
        checked += 1;
      }
    }
  }
  assert.ok(checked > 300, `only ${checked} components compared`);
  assert.ok(worst < 1e-9, `largest divergence ${worst.toExponential(3)} at ${worstAt}`);
});

test("a short window and a window over a gap are both refused", () => {
  const bars = fixture.cases[0].bars;
  assert.equal(featuresAt(bars, WARMUP - 1), null);
  assert.equal(featuresAt(bars, bars.length), null);

  const step = bars[1].ts - bars[0].ts;
  assert.equal(contiguous(bars, WARMUP, step), true);
  // Take one bar out of the middle. The window ending at `WARMUP` now reaches one interval
  // further back than it should, which is exactly what a venue outage looks like, and it must be
  // refused even though the array still holds enough rows.
  const holed = [...bars.slice(0, 10), ...bars.slice(11)];
  assert.equal(contiguous(holed, WARMUP, step), false);
});

test("a horizon is a duration, and every one has a model family name", () => {
  assert.deepEqual(HORIZON_ORDER, Object.keys(HORIZONS));
  for (const k of HORIZON_ORDER) {
    const h = HORIZONS[k];
    assert.equal(h.key, k);
    const stepMinutes = h.interval === "5m" ? 5 : 240;
    // The reach in minutes has to be the bar count times the interval, or a stored forecast
    // matures at a time the model was never trained to reach.
    assert.equal(h.minutes, h.bars * stepMinutes, `${k} minutes disagree with bars x interval`);
    // Nothing in a horizon's words may name a direction: that confusion is the whole reason this
    // vocabulary replaced the trading-style one.
    assert.ok(!/\b(long|short)\b/i.test(h.label), `${k} label names a direction: ${h.label}`);
  }
  assert.equal(horizonFrom("m5")?.key, "m5");
  assert.equal(horizonFrom("swing"), null);
  assert.equal(horizonFrom(undefined), null);
  const asOf = new Date("2026-10-21T00:00:00.000Z");
  assert.equal(maturesAt(asOf, HORIZONS.m15).toISOString(), "2026-10-21T00:15:00.000Z");
  assert.equal(maturesAt(asOf, HORIZONS.d20).toISOString(), "2026-11-10T00:00:00.000Z");
});

test("the model walks a tree the way the trainer scored it", () => {
  // A two-feature stump: bin 0 of feature 0 goes left. Checks the three things that can be
  // wrong independently -- the bin boundary is `<=` on the left, the bias is added once, and the
  // learning rate multiplies the leaf rather than the score.
  const artifact: Artifact = {
    modelVersion: "test",
    featureSchema: FEATURE_VERSION,
    features: ["a", "b"],
    warmupBars: 0,
    interval: "5m",
    barsAhead: 1,
    minutesAhead: 5,
    classes: ["DOWN", "UP"],
    model: {
      kind: "gbm-logistic",
      bias: 0,
      lr: 0.5,
      bins: 2,
      edges: [[0], [0]],
      trees: [{ f: 0, b: 0, l: { leaf: -2 }, r: { leaf: 2 } }],
    },
  };
  const low = probabilityUp(artifact, [-1, 0]);
  const high = probabilityUp(artifact, [1, 0]);
  assert.ok(Math.abs(low - 1 / (1 + Math.exp(1))) < 1e-12);
  assert.ok(Math.abs(high - 1 / (1 + Math.exp(-1))) < 1e-12);
  // A value exactly on an edge falls in the bin *below* it: numpy's `searchsorted(..., "left")`
  // counts edges strictly less than the value, so an edge of 0 leaves 0 in bin 0 and the split
  // `code <= b` sends it left. Pinned here because getting it backwards would shift a slice of
  // every feature into the wrong leaf, which no accuracy number would announce.
  assert.equal(probabilityUp(artifact, [0, 0]), low);

  assert.throws(() => probabilityUp(artifact, [1]), /wants 2 features/);
  assert.throws(() => probabilityUp(artifact, [Number.NaN, 0]), /not finite/);
});
