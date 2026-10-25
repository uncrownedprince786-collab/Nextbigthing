// What the site may say about a coin and a horizon, read from the artifact the research wrote.
//
// The same split as `lib/signalValidation.ts`, for the same reason: whether a horizon *can* be
// answered is a property of the data, and whether it *has survived testing* is a measurement. A
// UI that treated the first as permission would print a direction for every window it is able to
// grade, which is all of them. Nothing is re-derived here -- `tools/research/crypto_lanes.py`
// writes the table from the model manifests, so the web layer and the research layer cannot hold
// different opinions about what has been shown.
//
// A lane that is absent and a lane that is refused are different answers and must not be merged.
// Absent is "no model has been fitted for this"; refused is "one was, and it failed its gates" --
// and the second comes with the sentence saying which gate and by how much.

import raw from "@/data/foundation/dataset/crypto_lanes.json";
import type { HorizonKey } from "@/lib/cryptoHorizons";

export type LaneConfidence = "LOW" | "MEDIUM" | "NONE";

export interface LaneEvidence {
  testRows: number;
  testFrom: string | null;
  testTo: string | null;
  accuracy: number;
  testMajority: number;
  marginOverMajority: number;
  bootstrapCi95: [number, number];
  bootstrapZ: number | null;
  bootstrapBlocks: number;
  walkForwardAbove: number;
  walkForwardBlocks: number;
  predictedUpShare: number;
  linearOnTheSameTestRows: number | null;
  chosenModel: string | null;
  coverageCurve: {
    minMargin: number;
    rows: number;
    coverage: number;
    accuracy: number | null;
    majorityHere?: number;
  }[];
}

/// The point below which this lane says nothing.
///
/// A model's probability is also a statement about its own indifference, and on every lane that
/// has one, the rows furthest from even are the rows it reads best. `floor` is how far from 0.5
/// the probability must be before a direction is printed; `called` is what the lane scored on the
/// test rows it would have spoken on, measured against **those rows' own** majority, with the
/// coverage beside it because "right more often on fewer bars" is only a result when both numbers
/// are shown.
///
/// Null is the normal older state: that lane answers on every bar, as all of them did before.
export interface LaneConviction {
  floor: number;
  chosenOn: string;
  rule: string;
  called: {
    accuracy: number;
    coverage: number;
    rows: number;
    majorityHere: number;
    marginOverMajority: number;
    bootstrapCi95: [number, number];
    walkForwardAbove: number;
    walkForwardBlocks: number;
    upShareCalled: number;
  };
  /// What the same model scored answering on every test row, so the trade is visible.
  ungatedAccuracy: number;
  testCurve: {
    minMargin: number;
    rows: number;
    coverage: number;
    accuracy: number | null;
    majorityHere?: number;
  }[];
  measuredAt: string;
}

export interface Lane {
  family: string;
  horizon: HorizonKey;
  horizonMinutes: number;
  interval: "5m" | "4h";
  modelVersion: string;
  modelSha256: string;
  featureSchema: string;
  trainedOn: string[];
  servable: boolean;
  confidence: LaneConfidence;
  why: string | null;
  evidence: LaneEvidence;
  conviction: LaneConviction | null;
  acceptanceTarget: number | null;
  acceptanceTargetMet: boolean | null;
  trainingRows: number;
  generatedAt: string;
}

interface Table {
  generatedAt: string;
  status: string;
  highIsUnreachableFromBacktest: string;
  requirements: string[];
  conviction?: string;
  families: string[];
  lanes: Lane[];
  servableLanes: number;
  gatedLanes?: number;
  totalLanes: number;
}

const TABLE = raw as unknown as Table;

export const LANES_GENERATED_AT = TABLE.generatedAt;
export const LANES_STATUS = TABLE.status;
export const LANE_REQUIREMENTS = TABLE.requirements;
export const HIGH_IS_UNREACHABLE = TABLE.highIsUnreachableFromBacktest;
export const CONVICTION_RULE = TABLE.conviction ?? null;
export const LANES: readonly Lane[] = TABLE.lanes;

/// Does this lane's probability clear its own floor?
///
/// True when the lane has no floor, because a lane without one answers on every bar -- the same
/// behaviour every lane had before the floors existed, and the reason adding one to a single lane
/// does not change any other.
export function speaks(lane: Lane, probUp: number): boolean {
  const floor = lane.conviction?.floor ?? 0;
  return Math.abs(probUp - 0.5) >= floor;
}

/// Coins fitted on their own bars alone, by slug.
///
/// **A dedicated model beats the pooled one on the coin it was fitted for, and the pooled result
/// hid that.** A model trained on nine coins together scores 51.89% where the 140-coin pool
/// scores 53.69%, so narrowing the pool looked settled -- but that is a pool of nine, not a
/// model of one. Fitted alone, with its own floor, these coins beat what the pooled lane managed
/// on them: ETH 56.65% at fifteen minutes where the pool refused it outright, XRP 55.33% and
/// LINK 53.47% likewise refused, ADA 54.91%, SOL 54.57%.
///
/// Why it works here and not for a pool of nine: the pooled model spends eleven of its features
/// on how a coin moves *relative to Bitcoin*, which for a coin fitted alone is still useful, and
/// its remaining capacity on reconciling 140 different markets. One market gets all of it.
///
/// Each still needs 540 days of its own bars to be fitted at all, which is why this is a list
/// rather than a rule.
const OWN_MODEL: Record<string, string> = {
  "btc-bitcoin": "btc",
  "eth-ethereum": "eth",
  "sol-solana": "sol",
  "xrp-xrp": "xrp",
  "ada-cardano": "ada",
  "link-chainlink": "link",
  "avax-avalanche": "avax",
  "dot-polkadot": "dot",
  "sui-sui": "sui",
};

/// Which model family answers for a coin.
///
/// A coin with its own fitted model uses it; everything else is answered by the pooled crypto
/// family. A coin is never silently served another coin's model: the family name is on the lane,
/// on the artifact and on every stored forecast, so what answered is always visible, and
/// `tests/laneRouting.test.ts` holds that to near-misses like wbtc-wrapped-bitcoin.
export function familyFor(slug: string): string {
  return OWN_MODEL[slug] ?? "crypto";
}

export function laneFor(family: string, horizon: HorizonKey): Lane | null {
  return LANES.find((l) => l.family === family && l.horizon === horizon) ?? null;
}

/// The lane that will actually answer for this coin and horizon.
///
/// The coin's own model where it has one **and that lane is servable**, the pooled lane
/// otherwise, and the coin's own refused lane last so the page can explain the refusal rather
/// than show nothing. The servable check matters: a dedicated lane that failed its gates is
/// worse than the pooled lane that passed, and routing to it on the strength of the name alone
/// would quietly downgrade the coin.
///
/// The fallback runs one way only. A coin is never handed another coin's model because one
/// happens to exist.
export function servingLane(slug: string, horizon: HorizonKey): Lane | null {
  const family = familyFor(slug);
  const own = laneFor(family, horizon);
  if (own?.servable) return own;
  const pooled = family === "crypto" ? null : laneFor("crypto", horizon);
  if (pooled?.servable) return pooled;
  return own ?? pooled;
}

export function lanesFor(slug: string): { horizon: HorizonKey; lane: Lane | null }[] {
  const keys: HorizonKey[] = ["m5", "m15", "h1", "h4", "d1", "d5", "d20"];
  return keys.map((h) => ({ horizon: h, lane: servingLane(slug, h) }));
}

/// The measured accuracy on the band of test rows whose confidence matched this one.
///
/// Shown beside a direction so a reader is told how often a call like this one has been right on
/// the holdout, rather than being handed a bare word. Returns null when the band held too few
/// rows to report, which the caller prints as an absence rather than as a number.
export function accuracyAtMargin(lane: Lane, margin: number): { accuracy: number; coverage: number; rows: number } | null {
  const curve = lane.evidence.coverageCurve.filter((c) => c.accuracy !== null);
  let best: (typeof curve)[number] | null = null;
  for (const c of curve) if (c.minMargin <= margin && (!best || c.minMargin > best.minMargin)) best = c;
  if (!best || best.accuracy === null) return null;
  return { accuracy: best.accuracy, coverage: best.coverage, rows: best.rows };
}
