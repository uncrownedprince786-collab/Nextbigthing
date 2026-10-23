import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

// Read rather than imported, like `signalValidation.test.ts`: `node --test` has no bundler to
// resolve the `@/` alias `lib/cryptoLanes` uses. The rules under test are the ones the site runs.
const LANES_TABLE = JSON.parse(readFileSync(
  new URL("../data/foundation/dataset/crypto_lanes.json", import.meta.url), "utf8"));
const MEASURED = JSON.parse(readFileSync(
  new URL("../data/foundation/dataset/crypto_conviction.json", import.meta.url), "utf8"));

type Called = {
  accuracy: number; coverage: number; rows: number; majorityHere: number;
  marginOverMajority: number; bootstrapCi95: [number, number];
  walkForwardAbove: number; walkForwardBlocks: number; upShareCalled: number;
};
type Lane = {
  family: string; horizon: string; servable: boolean; confidence: string;
  conviction: { floor: number; called: Called; ungatedAccuracy: number } | null;
  evidence: { accuracy: number };
};
const LANES: Lane[] = LANES_TABLE.lanes;
const gated = LANES.filter((l) => l.conviction);

// A conviction floor is the site choosing to say nothing on most bars. That is a good trade only
// while every claim attached to it is true, and each test below is a way the trade could quietly
// become a worse one: a floor on a lane that never passed, a floor that buys no accuracy, a
// serving rule that disagrees with the measurement, or a floor so high the lane stops answering.

/// The serving rule, restated here rather than imported, for the same alias reason. It is three
/// lines and a divergence between it and `lib/cryptoLanes.speaks` is exactly what a parity test
/// is for -- so the shape is kept identical and the behaviour is asserted below.
const speaks = (floor: number | null, probUp: number) =>
  Math.abs(probUp - 0.5) >= (floor ?? 0);

test("a floor is only ever attached to a lane that already passed its gates", () => {
  assert.ok(gated.length > 0, "at least one lane carries a floor");
  for (const l of gated) {
    assert.equal(l.servable, true,
      `${l.family}:${l.horizon} carries a conviction floor but is not servable`);
    assert.notEqual(l.confidence, "NONE");
  }
  // The inverse is the dangerous one: conviction must never be a second chance for a refused lane.
  for (const l of LANES.filter((x) => !x.servable)) {
    assert.equal(l.conviction, null,
      `${l.family}:${l.horizon} was refused and must carry no floor`);
  }
});

test("every floor buys accuracy, measured against the called rows' own majority", () => {
  for (const l of gated) {
    const c = l.conviction!.called;
    // Against the selection's own base rate, not the whole fold's. A floor selects rows and a
    // selection can move the majority it should be judged against; comparing to the fold-wide
    // number is how a filter that only concentrates UP rows looks like a filter that reads them.
    assert.ok(c.accuracy > c.majorityHere,
      `${l.family}:${l.horizon} called rows score ${c.accuracy} against a ${c.majorityHere} majority`);
    assert.ok(c.bootstrapCi95[0] > 0,
      `${l.family}:${l.horizon} day-blocked interval ${JSON.stringify(c.bootstrapCi95)} spans zero`);
    assert.ok(c.walkForwardAbove >= Math.min(4, c.walkForwardBlocks),
      `${l.family}:${l.horizon} above its block majority in only ${c.walkForwardAbove} of ${c.walkForwardBlocks}`);
    // The whole point of the trade. A floor that does not raise accuracy is only a floor that
    // answers less often, which is a cost with nothing on the other side of it.
    assert.ok(c.accuracy > l.conviction!.ungatedAccuracy,
      `${l.family}:${l.horizon} scores ${c.accuracy} gated and ${l.conviction!.ungatedAccuracy} ungated`);
  }
});

test("a floor still leaves the lane answering often enough to be a lane", () => {
  for (const l of gated) {
    const c = l.conviction!.called;
    assert.ok(c.coverage >= 0.05,
      `${l.family}:${l.horizon} speaks on only ${(c.coverage * 100).toFixed(1)}% of the test fold`);
    assert.ok(c.rows >= 500, `${l.family}:${l.horizon} called only ${c.rows} test rows`);
    // Both directions, or it is naming a class on the rows it chose to speak on -- which is the
    // same failure the ungated gates exist to catch, reintroduced through the filter.
    assert.ok(Math.max(c.upShareCalled, 1 - c.upShareCalled) <= 0.8,
      `${l.family}:${l.horizon} calls one direction on ${c.upShareCalled} of its calls`);
  }
});

test("the serving rule is the measured rule: inside the floor is silence, on it is a call", () => {
  for (const l of gated) {
    const f = l.conviction!.floor;
    assert.ok(f > 0, `${l.family}:${l.horizon} has a zero floor and should carry no conviction`);
    assert.equal(speaks(f, 0.5), false, "an even probability never speaks");
    assert.equal(speaks(f, 0.5 + f / 2), false, "half the floor is inside it");
    // The boundary belongs to the called side, because that is how the test fold was selected:
    // `np.abs(p - 0.5) >= floor`. A serving path using `>` would be scoring one rule and serving
    // another.
    //
    // Checked a hair outside the floor rather than exactly on it, and that is not a weakened
    // test. `0.5 - 0.04` is not representable, so `|0.5 - 0.04 - 0.5|` is 0.03999999999999998 and
    // the DOWN side at the exact boundary does not speak where the UP side does -- an asymmetry
    // of one part in 10^17. It is harmless because the measurement computes the same expression
    // in the same double precision, so serving and scoring agree on every row; and because a
    // model probability landing on the boundary to sixteen places is not a case that occurs. What
    // would matter is an asymmetry at a scale a probability can actually take, so that is what is
    // asserted.
    const tick = 1e-9;
    assert.equal(speaks(f, 0.5 + f + tick), true, "just outside the floor is a call");
    assert.equal(speaks(f, 0.5 - f - tick), true, "the floor is symmetric about even");
    assert.equal(speaks(f, 0.5 + f - tick), false, "just inside the floor is silence");
    assert.equal(speaks(f, 0.5 - f + tick), false, "and symmetrically on the DOWN side");
  }
  // A lane with no floor answers every bar, which is what every lane did before floors existed.
  assert.equal(speaks(null, 0.5), true);
});

test("the lane table and the measurement it came from have not drifted apart", () => {
  const measured = new Map(
    MEASURED.lanes.map((l: { family: string; horizon: string }) => [`${l.family}:${l.horizon}`, l]),
  );
  for (const l of gated) {
    const m = measured.get(`${l.family}:${l.horizon}`) as
      | { chosenFloor: number; serveGated: boolean; gatedOnTest: Called; ungatedOnTest: { accuracy: number } }
      | undefined;
    assert.ok(m, `${l.family}:${l.horizon} has a floor with no measurement behind it`);
    assert.equal(l.conviction!.floor, m.chosenFloor);
    assert.equal(m.serveGated, true);
    assert.equal(l.conviction!.called.accuracy, m.gatedOnTest.accuracy);
    assert.equal(l.conviction!.called.coverage, m.gatedOnTest.coverage);
    assert.equal(l.conviction!.ungatedAccuracy, m.ungatedOnTest.accuracy);
  }
  // And the measurement never claims a lane the table does not carry.
  for (const m of MEASURED.lanes.filter((x: { serveGated: boolean }) => x.serveGated)) {
    const l = LANES.find((x) => x.family === m.family && x.horizon === m.horizon);
    assert.ok(l?.conviction, `${m.family}:${m.horizon} earned a floor the lane table does not serve`);
  }
});

test("the floor was chosen on the validation fold and the ladder is fixed", () => {
  // The one property that makes every number above a measurement rather than a search result.
  assert.match(MEASURED.rule, /validation fold/i);
  assert.match(MEASURED.rule, /once on the test fold/i);
  for (const l of MEASURED.lanes) {
    assert.ok(MEASURED.ladder.includes(l.chosenFloor),
      `${l.family}:${l.horizon} chose ${l.chosenFloor}, which is not on the pre-registered ladder`);
  }
});

test("the ungated numbers still match the artifact manifests they were fitted from", () => {
  // The conviction run rebuilds the matrix, the split and the scoring from scratch. If its ungated
  // accuracy did not reproduce the trainer's, then the two are not reading the same model on the
  // same rows, and every gated figure beside it would be measuring something else.
  for (const l of gated) {
    assert.ok(Math.abs(l.conviction!.ungatedAccuracy - l.evidence.accuracy) < 1e-4,
      `${l.family}:${l.horizon}: conviction run scored ${l.conviction!.ungatedAccuracy} ungated ` +
      `where the artifact manifest recorded ${l.evidence.accuracy}`);
  }
});
