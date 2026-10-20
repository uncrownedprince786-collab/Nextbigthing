import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  laneFor as laneForIn, validatedSides as sidesIn,
  marketHasValidatedSignal as marketHasIn, verdictFor as verdictIn, sideOfClass,
  predictionIsCovered as coveredIn, type Lane,
} from "../lib/signalLanes.ts";
import { TIMEFRAME_ORDER, TIMEFRAME_SESSIONS } from "../lib/marketMarkets.ts";

// The artifact is read here rather than imported, because `node --test` has no bundler to resolve
// the `@/` alias lib/signalValidation uses. The rules under test are the same ones the site runs.
const TABLE = JSON.parse(readFileSync(
  new URL("../data/foundation/dataset/signal_validation.json", import.meta.url), "utf8"));
const LANES: Lane[] = TABLE.lanes;
const laneFor = (m: string, h: number, s: "LONG" | "SHORT") => laneForIn(LANES, m, h, s);
const validatedSides = (m: string, h: number) => sidesIn(LANES, m, h);
const marketHasValidatedSignal = (m: string) => marketHasIn(LANES, m);
const verdictFor = (m: string, h: number) => verdictIn(LANES, m, h);

// The decision card is allowed to print a direction only when this table says so, which makes the
// table the thing worth guarding. Each test below is a way the UI could come to show a call that
// nothing supports.

test("the only validated lane is the one that survived testing", () => {
  const validated = LANES.filter((l) => l.validated);
  assert.equal(validated.length, 1, "exactly one lane has survived");
  const [lane] = validated;
  assert.equal(lane.market, "US");
  assert.equal(lane.horizonSessions, 5);
  assert.equal(lane.side, "LONG");
});

test("the US short side is refused, and refusal is not the same as untested", () => {
  const short = laneFor("US", 5, "SHORT");
  assert.ok(short, "the short side was tested, so it has a row");
  assert.equal(short.validated, false);
  assert.equal(short.confidence, null);
  // The reason is shown to readers, so it has to say what actually happened.
  assert.match(short.why, /realised|return/i);
  assert.equal(verdictFor("US", 5).kind, "directional", "LONG still stands");
  assert.equal(verdictFor("PK", 5).kind, "untested", "an unmeasured market is untested");
});

test("no badge ever reads HIGH, because every lane is validated on a backtest", () => {
  for (const l of LANES) {
    assert.notEqual(l.confidence, "HIGH");
    if (l.validated) assert.ok(l.confidence === "MEDIUM" || l.confidence === "LOW");
  }
});

test("a validated lane carries the evidence that earned it", () => {
  const lane = laneFor("US", 5, "LONG")!;
  const e = lane.evidence;
  assert.ok((e.blockedBootstrapZ ?? 0) >= 5, "the bootstrap z is the band's own floor");
  assert.equal(e.walkForwardPositive, e.walkForwardFolds, "every fold held its sign");
  assert.ok((e.armsSearched ?? 0) >= 90, "multiplicity is recorded, not forgotten");
  assert.ok((e.holdoutSessions ?? 0) > 100);
});

test("no market other than US claims a signal", () => {
  for (const m of ["PK", "FX", "Commodity", "Crypto"]) {
    assert.equal(marketHasValidatedSignal(m), false, m);
    for (const tf of TIMEFRAME_ORDER) {
      assert.deepEqual(validatedSides(m, TIMEFRAME_SESSIONS[tf]), [], `${m}/${tf}`);
    }
  }
});

test("no horizon of US other than five sessions claims a signal", () => {
  for (const tf of TIMEFRAME_ORDER) {
    const sessions = TIMEFRAME_SESSIONS[tf];
    if (sessions === 5) continue;
    assert.deepEqual(validatedSides("US", sessions), [], `US/${tf}`);
  }
});

test("the timeframe vocabulary matches the research artifact, so a screen cannot offer a horizon the scorer does not grade", () => {
  const cap = JSON.parse(readFileSync(
    new URL("../data/foundation/dataset/market_capability.json", import.meta.url), "utf8"));
  for (const [name, sessions] of Object.entries(cap.timeframes as Record<string, number>)) {
    assert.ok(TIMEFRAME_ORDER.includes(name as never), `${name} is missing from TIMEFRAME_ORDER`);
    assert.equal(TIMEFRAME_SESSIONS[name as never], sessions, `${name} session count drifted`);
  }
  for (const tf of TIMEFRAME_ORDER) {
    assert.ok(tf in cap.timeframes, `${tf} is offered but the research table does not know it`);
  }
});

test("scalp is listed and is judged over zero sessions, so it can be shown as refused", () => {
  assert.ok(TIMEFRAME_ORDER.includes("scalp"));
  assert.equal(TIMEFRAME_SESSIONS.scalp, 0);
});

test("the model's class vocabulary maps onto a trading side, and FLAT is not a side", () => {
  // The bug this pins: the decision screen compared `predicted !== side`, i.e. "UP" !== "LONG",
  // and refused a validated signal it should have shown.
  assert.equal(sideOfClass("UP"), "LONG");
  assert.equal(sideOfClass("DOWN"), "SHORT");
  // "no move cleared the band" is not "short it".
  assert.equal(sideOfClass("FLAT"), null);
  assert.equal(sideOfClass(null), null);
  assert.equal(sideOfClass(undefined), null);
  assert.equal(sideOfClass("anything else"), null);
});

test("a recorded UP on the validated US five-session lane resolves to the side that was proven", () => {
  const v = verdictFor("US", 5);
  assert.equal(v.kind, "directional");
  if (v.kind !== "directional") return;
  assert.equal(sideOfClass("UP"), v.side, "an UP call is the LONG lane that survived");
  assert.notEqual(sideOfClass("DOWN"), v.side, "a DOWN call is not, and must stay suppressed");
});

test("a validated lane names the artifact its evidence was measured on", () => {
  // The defect this pins: the lane was keyed on market, horizon and side alone, so the UI printed
  // LONG / MEDIUM from brain-v5-h5-us beside numbers measured on brain-v5-h5b20-us. The two are
  // different models -- the 1.0x band called UP on 271 of 271 US instruments, the validated 2.0x
  // band on 182 of 271.
  const lane = laneFor("US", 5, "LONG")!;
  assert.ok(lane.modelVersion, "a lane without a model version covers nothing");
  assert.equal(lane.modelVersion, "brain-v5-h5b20-us");
  assert.equal(lane.bandScale, 2.0, "the band is part of the model's identity");
});

test("only a prediction from the validated artifact is covered by the lane", () => {
  const lane = laneFor("US", 5, "LONG")!;
  assert.equal(coveredIn(lane, "brain-v5-h5b20-us"), true);
  // The model the site used to serve. Same market, same horizon, different band: not covered.
  assert.equal(coveredIn(lane, "brain-v5-h5-us"), false);
  assert.equal(coveredIn(lane, "brain-v4-us"), false);
  assert.equal(coveredIn(lane, null), false);
});

test("a refused lane covers nothing, whatever model the prediction came from", () => {
  const short = laneFor("US", 5, "SHORT")!;
  assert.equal(short.validated, false);
  assert.equal(coveredIn(short, "brain-v5-h5b20-us"), false, "a failed side is never covered");
});

test("an undefined lane covers nothing", () => {
  assert.equal(coveredIn(undefined, "brain-v5-h5b20-us"), false);
});
