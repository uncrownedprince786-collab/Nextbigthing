// The binding: the precomputed per-asset coverage table, tied to the rules in lib/coverage.
//
// Imported here and nowhere else, so the one place that reads a 197 KB artifact is visible. This
// is a server-side read on an ISR page -- the table never reaches the browser -- which is why a
// file of that size is acceptable where a client bundle would not be.

import raw from "@/data/foundation/dataset/coverage_registry.json";
import {
  readyShare as readyShareIn,
  whyNoReading as whyNoReadingIn,
  type CoverageRegistry,
  type MissingReason,
} from "./coverage.ts";

export const COVERAGE = raw as unknown as CoverageRegistry;

export function whyNoReading(symbol: string, horizonSessions: number): MissingReason {
  return whyNoReadingIn(COVERAGE, symbol, horizonSessions);
}

export function coverageReadyShare(): { ready: number; total: number } {
  return readyShareIn(COVERAGE);
}

export const COVERAGE_GENERATED_AT = COVERAGE.generatedAt;

export type { MissingReason };
