// The TypeScript market-factor block against the Python one that trained the model.
//
// This is the test that makes the duplication in `lib/marketContext.ts` safe, and it is the same
// bargain `intradayParity.test.ts` strikes for the other forty-one features: the block is defined
// once in `tools/research/market_context.py`, fitted over a million rows, and recomputed on every
// request in TypeScript. A component that drifts between the two is invisible in every metric the
// site shows -- the forecasts simply stop working, slowly, and nothing goes red.
//
// The tolerance is tight on purpose. These are not two algorithms that should roughly agree; they
// are the same arithmetic written twice, and anything above float noise is a real divergence.
//
// One of the two cases is Bitcoin against itself, where the residuals are exactly zero and the
// beta is exactly one. That degenerate case is what the trainer sees on every Bitcoin row, so it
// is the one a serving path is most likely to get subtly wrong.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  contextAt,
  CONTEXT_FEATURES,
  CONTEXT_VERSION,
  N_CONTEXT,
} from "../lib/marketContext.ts";
import type { Bar } from "../lib/intradayFeatures.ts";

interface Fixture {
  contextVersion: string;
  featureNames: string[];
  warmup: number;
  cases: {
    label: string;
    symbol: string;
    bars: Bar[];
    marketBars: Bar[];
    rows: number[];
    expected: number[][];
  }[];
}

const FIX: Fixture = JSON.parse(
  readFileSync(new URL("./fixtures/marketContextParity.json", import.meta.url), "utf8"),
);

/// Float32 is what the matrix stores and float64 is what both implementations compute in, so an
/// exact comparison would fail on storage rounding alone. Anything above this is a real
/// divergence in the arithmetic.
const TOL = 2e-6;

test("the block is the same shape and the same names on both sides", () => {
  assert.equal(CONTEXT_VERSION, FIX.contextVersion,
    "the serving path is on a different context version from the fixture");
  assert.deepEqual([...CONTEXT_FEATURES], FIX.featureNames,
    "the feature names, in order, must match the definition");
  assert.equal(N_CONTEXT, FIX.featureNames.length);
});

for (const c of FIX.cases) {
  test(`${c.label}: every component matches the Python definition`, () => {
    for (let k = 0; k < c.rows.length; k++) {
      const i = c.rows[k];
      const got = contextAt(c.bars, i, c.marketBars);
      assert.ok(got, `${c.symbol} row ${i}: the serving path refused a row the definition used`);
      assert.equal(got.length, N_CONTEXT);
      for (let f = 0; f < N_CONTEXT; f++) {
        const want = c.expected[k][f];
        const scale = Math.max(1, Math.abs(want));
        const diff = Math.abs(got[f] - want) / scale;
        assert.ok(
          diff <= TOL,
          `${c.symbol} row ${i}: ${CONTEXT_FEATURES[f]} is ${got[f]} where the definition ` +
            `returned ${want} (relative ${diff.toExponential(2)} > ${TOL})`,
        );
      }
    }
  });
}

test("the factor against itself has zero residuals and unit beta", () => {
  // Asserted here as well as in the Python tests, because this is the row shape the Bitcoin lane
  // is served on and a TypeScript-only mistake would never reach `test_market_context.py`.
  const self = FIX.cases.find((c) => c.symbol === "BTCUSDT");
  assert.ok(self, "the fixture carries the self case");
  const idx = Object.fromEntries(CONTEXT_FEATURES.map((n, i) => [n, i]));
  const got = contextAt(self.bars, self.rows[self.rows.length - 1], self.marketBars);
  assert.ok(got);
  for (const name of ["relR1", "relR12", "relR48"]) {
    assert.ok(Math.abs(got[idx[name]]) < 1e-9, `${name} must be zero against itself`);
  }
  assert.ok(Math.abs(got[idx.beta48] - 1) < 1e-4, "beta against itself must be one");
  assert.ok(Math.abs(got[idx.corr48] - 1) < 1e-4, "correlation against itself must be one");
});

test("a factor window that does not reach the decision instant is refused, not imputed", () => {
  const c = FIX.cases[0];
  const i = c.rows[c.rows.length - 1];
  // Remove the factor bar at exactly the decision instant. A context vector built anyway would be
  // a set of numbers about a different moment, which is the failure this returns null for.
  const holed = c.marketBars.filter((b) => b.ts !== c.bars[i].ts);
  assert.equal(contextAt(c.bars, i, holed), null);
  // And a hole inside the regression window, which is subtler: every input still exists, the beta
  // is simply fitted across two different stretches of time.
  const inside = c.marketBars.filter((b) => b.ts !== c.bars[i - 10].ts);
  assert.equal(contextAt(c.bars, i, inside), null);
});

test("a short factor series is refused", () => {
  const c = FIX.cases[0];
  assert.equal(contextAt(c.bars, c.rows[0], c.marketBars.slice(-10)), null);
});
