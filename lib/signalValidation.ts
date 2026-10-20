// What the decision card is allowed to say, read from the artifact the research produced.
//
// `lib/marketCapability.ts` answers "can an outcome here be scored at all" -- a property of the
// data and the calendar, true for every market at swing and position. This file answers a
// different and much narrower question: has a directional call on this market, at this horizon,
// on this side, actually survived testing? Four of five markets have no such evidence, and the one
// that does has it on one side only.
//
// Keeping the two apart is the whole point. A market that can be *scored* is not a market that can
// be *called*, and a UI that read capability as permission would offer a direction on every market
// it is able to grade -- which is all of them.
//
// This file is the binding: it imports the artifact and the rules (lib/signalLanes) and ties them
// together. The rules live next door so `node --test` can exercise them without a bundler to
// resolve the `@/` alias, the same split lib/marketMarkets makes against lib/marketCapability.
// Nothing is re-derived here: `tools/research/signal_validation.py` writes the table from
// `validate_lift.json`, so the web layer and the research layer cannot hold different opinions
// about what has been proven.

import raw from "@/data/foundation/dataset/signal_validation.json";
import {
  laneFor as laneForIn,
  marketHasValidatedSignal as marketHasIn,
  validatedHorizons as horizonsIn,
  validatedSides as sidesIn,
  verdictFor as verdictIn,
  type Lane,
  type Side,
} from "./signalLanes.ts";

export type { Confidence, Lane, LaneEvidence, Side, Verdict } from "./signalLanes.ts";
export { sideOfClass, predictionIsCovered } from "./signalLanes.ts";

interface Raw {
  generatedAt: string;
  version: string;
  status: string;
  requirements: string[];
  highIsUnreachableFromBacktest: string;
  lanes: Lane[];
}

const TABLE = raw as unknown as Raw;

export const VALIDATION_GENERATED_AT = TABLE.generatedAt;
export const VALIDATION_STATUS = TABLE.status;
export const VALIDATION_REQUIREMENTS = TABLE.requirements;
export const LANES: readonly Lane[] = TABLE.lanes;

/// The lane for one market, horizon and side, or `undefined` when nothing has been measured.
///
/// `undefined` and `validated: false` are different answers and callers must not merge them: the
/// first is "nobody has tested this", the second is "somebody tested it and it failed". The US
/// short side is the second, and the reason it failed is worth showing.
export const laneFor = (market: string, h: number, side: Side) => laneForIn(LANES, market, h, side);
export const validatedSides = (market: string, h: number) => sidesIn(LANES, market, h);
export const marketHasValidatedSignal = (market: string) => marketHasIn(LANES, market);
export const validatedHorizons = (market: string) => horizonsIn(LANES, market);
export const verdictFor = (market: string, h: number) => verdictIn(LANES, market, h);
