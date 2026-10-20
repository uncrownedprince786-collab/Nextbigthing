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
  families: string[];
  lanes: Lane[];
  servableLanes: number;
  totalLanes: number;
}

const TABLE = raw as unknown as Table;

export const LANES_GENERATED_AT = TABLE.generatedAt;
export const LANES_STATUS = TABLE.status;
export const LANE_REQUIREMENTS = TABLE.requirements;
export const HIGH_IS_UNREACHABLE = TABLE.highIsUnreachableFromBacktest;
export const LANES: readonly Lane[] = TABLE.lanes;

/// Which model family answers for a coin.
///
/// Bitcoin has its own, fitted on four years of its own bars; every other coin is answered by the
/// pooled crypto family when one exists. A coin is never silently served Bitcoin's model: the
/// family name is on the lane, on the artifact and on every stored forecast, so what answered is
/// always visible.
export function familyFor(slug: string): string {
  return slug === "btc-bitcoin" ? "btc" : "crypto";
}

export function laneFor(family: string, horizon: HorizonKey): Lane | null {
  return LANES.find((l) => l.family === family && l.horizon === horizon) ?? null;
}

/// The lane that will actually answer for this coin and horizon, following the one fallback the
/// site allows: a coin with no family lane falls back to the pooled crypto lane, never the other
/// way round, and never from one coin's model to another coin's.
export function servingLane(slug: string, horizon: HorizonKey): Lane | null {
  const own = laneFor(familyFor(slug), horizon);
  if (own) return own;
  return familyFor(slug) === "crypto" ? null : laneFor("crypto", horizon);
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
