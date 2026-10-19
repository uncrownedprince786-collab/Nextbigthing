// The market capability contract, read from the artifact the research tools produce.
//
// This file is the one place the web layer learns what a market can and cannot be judged on. It
// deliberately does **not** re-derive that answer: `tools/research/market_capability.py` writes
// `data/foundation/dataset/market_capability.json` from `shadow_markets.capability`, and this
// imports it. A UI that decided strategy availability itself would be a second opinion that can
// disagree with the model layer, and the disagreement would show as a market offered a timeframe
// the pipeline cannot score.
//
// The three axes are kept apart on purpose. Whether the inputs exist, whether a market-specific
// model exists, and whether an outcome can be judged fail independently, and collapsing them into
// one "supported" flag is how a market silently becomes covered by a model that was never built
// for it. Today every market has inputs and a judgeable swing outcome, and **no** market has a
// market-specific model — one global model is applied to all five — so `prediction.marketSpecific`
// is false everywhere and the UI must say so rather than print a market-model badge.
//
// The vocabulary lives in lib/marketMarkets and is re-exported here so callers have one import.

import raw from "@/data/foundation/dataset/market_capability.json";
import type { MarketName, TimeframeName } from "./marketMarkets.ts";

export { MARKET_LABELS, MARKET_ORDER, canonicalMarket } from "./marketMarkets.ts";
export type { MarketName, TimeframeName } from "./marketMarkets.ts";

export interface CapabilityInput {
  available: boolean;
  note: string;
}
export interface CapabilityPrediction {
  marketSpecific: boolean;
  note: string;
}
export interface CapabilityOutcome {
  verifiable: boolean;
  judgedOn: string;
  reason: string;
}
export interface CapabilityRow {
  market: MarketName;
  timeframe: TimeframeName;
  horizonSessions: number;
  judgedOn: string;
  input: CapabilityInput;
  prediction: CapabilityPrediction;
  outcome: CapabilityOutcome;
  /// Kept identical to `outcome.verifiable` for callers that predate the split.
  verifiable: boolean;
  reason: string;
}
export interface MarketProfile {
  market: MarketName;
  tradesOnWeekends: boolean;
  priceSource: string;
  sessionRule: string;
}
export interface CapabilityContract {
  generatedAt: string;
  version: string;
  status: string;
  markets: MarketName[];
  timeframes: Record<TimeframeName, number>;
  profiles: MarketProfile[];
  matrix: CapabilityRow[];
  live?: {
    status: string;
    byMarket: Record<string, { assets: number; newestSession: string | null }>;
  };
}

export const CAPABILITY = raw as unknown as CapabilityContract;

const TIMEFRAME_ORDER: TimeframeName[] = ["scalp", "intraday", "swing", "position"];

/// One market's whole capability row set, in the fixed timeframe order.
export function capabilityForMarket(market: MarketName): CapabilityRow[] {
  return TIMEFRAME_ORDER
    .map((tf) => CAPABILITY.matrix.find((r) => r.market === market && r.timeframe === tf) ?? null)
    .filter((r): r is CapabilityRow => r !== null);
}

export function capabilityFor(market: MarketName, timeframe: TimeframeName): CapabilityRow | null {
  return CAPABILITY.matrix.find((r) => r.market === market && r.timeframe === timeframe) ?? null;
}

export function profileFor(market: MarketName): MarketProfile | null {
  return CAPABILITY.profiles.find((p) => p.market === market) ?? null;
}
