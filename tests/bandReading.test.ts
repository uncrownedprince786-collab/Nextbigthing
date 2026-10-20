// A FLAT row must say what was measured about it, on the model it was measured on.
//
// Two defects are guarded here. The first is the one the site shipped: treating FLAT as an absence
// of information, so 89 of 271 US instruments read "No direction" when the model had made a
// testable magnitude claim. The second is the 2026-10-20 identity defect in its new location --
// a reading measured on `brain-v5-h5b20-us` being shown beside a prediction from
// `brain-v5-h5-us`, two models that disagreed about direction on every instrument.

import assert from "node:assert/strict";
import test from "node:test";
import {
  asTimesIn, bandDirectionIsServable, readingFor, type BandReading,
} from "../lib/bandReading.ts";

const MEASURED: BandReading = {
  market: "US",
  horizonSessions: 5,
  modelVersion: "brain-v5-h5b20-us",
  bandScale: 2.0,
  magnitude: {
    thresholdPct: 2.0,
    precisionOnRowsCalledFlat: 0.4076,
    rateAcrossAllHoldoutRows: 0.336,
    lift: 0.0716,
    holds: true,
  },
  verdict: "NO-GO",
  lift: -0.0004,
  tests: { blockedBootstrap: { ci95: [-0.0033, 0.0025], z: -0.29 } },
  n: 25769,
};

test("a reading is returned for the model it was measured on", () => {
  const v = readingFor([MEASURED], "US", 5, "brain-v5-h5b20-us");
  assert.equal(v.kind, "measured");
});

test("a reading is never shown beside a prediction from another model", () => {
  // The whole defect, restated at the presentation layer: same market, same horizon, different
  // model. The numbers belong to the 2.0x artifact and say nothing about the 1.0x one.
  const v = readingFor([MEASURED], "US", 5, "brain-v5-h5-us");
  assert.equal(v.kind, "unmeasured");
});

test("a prediction with no recorded model version gets no reading", () => {
  assert.equal(readingFor([MEASURED], "US", 5, null).kind, "unmeasured");
  assert.equal(readingFor([MEASURED], "US", 5, undefined).kind, "unmeasured");
});

test("market and horizon still have to match", () => {
  assert.equal(readingFor([MEASURED], "PK", 5, "brain-v5-h5b20-us").kind, "unmeasured");
  assert.equal(readingFor([MEASURED], "US", 20, "brain-v5-h5b20-us").kind, "unmeasured");
});

test("an INSUFFICIENT reading does not present itself as a measurement", () => {
  // Too few rows to answer is not an answer, and the card must take the honest branch.
  const thin: BandReading = { ...MEASURED, verdict: "INSUFFICIENT" };
  assert.equal(readingFor([thin], "US", 5, "brain-v5-h5b20-us").kind, "unmeasured");
});

test("no side is servable while the direction test says NO-GO", () => {
  assert.equal(bandDirectionIsServable(MEASURED), false);
  assert.equal(bandDirectionIsServable({ ...MEASURED, verdict: "GO" }), true);
});

test("the hit rate rounds to a fraction a reader can hold", () => {
  // 0.4076 is "about 2 times in 5", not "40.76% of the time".
  assert.deepEqual(asTimesIn(0.4076), { times: 2, of: 5 });
  assert.deepEqual(asTimesIn(0.336), { times: 2, of: 5 });
  assert.deepEqual(asTimesIn(0.9), { times: 5, of: 5 });
  assert.deepEqual(asTimesIn(0.5, 10), { times: 5, of: 10 });
});

test("the shipped artifact matches the shape the card reads", async () => {
  // The binding imports JSON through the `@/` alias, which `node --test` cannot resolve, so the
  // artifact is read directly here. The point is that a regenerated artifact cannot silently drop
  // a field the card depends on.
  const raw = JSON.parse(
    await (await import("node:fs/promises")).readFile(
      new URL("../data/foundation/dataset/within_band_direction.json", import.meta.url),
      "utf-8",
    ),
  ) as BandReading;
  for (const k of ["market", "horizonSessions", "modelVersion", "verdict", "magnitude"] as const) {
    assert.ok(raw[k] !== undefined, `the artifact is missing ${k}`);
  }
  assert.ok(raw.magnitude.thresholdPct > 0);
  assert.ok(raw.magnitude.precisionOnRowsCalledFlat > 0);
  // The card calls this "a real edge ... but wrong more often than it is right". If a regenerated
  // artifact ever contradicts that sentence, the sentence is wrong and this test says so.
  assert.ok(
    raw.magnitude.precisionOnRowsCalledFlat < 0.5,
    "the card's wording assumes the magnitude call is right less than half the time",
  );
  assert.ok(
    raw.magnitude.lift > 0,
    "the card calls the magnitude claim a real edge; it must actually be positive",
  );
  // And the card withholds a side on the strength of the direction test failing.
  assert.equal(raw.verdict, "NO-GO", "a GO reading would need the card to offer a LOW side");
});
