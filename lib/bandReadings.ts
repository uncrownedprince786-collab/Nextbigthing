// The binding: the measured within-band readings, tied to the rules in lib/bandReading.
//
// One artifact today -- US over five sessions at the 2.0x band -- so this is a one-element table.
// It is a table rather than a single object because the next horizon or market measured gets a
// second entry and nothing else has to change, and because `readingFor` matches on model version,
// which only means something when there is more than one thing to match against.

import raw from "@/data/foundation/dataset/within_band_direction.json";
import {
  readingFor as readingForIn,
  type BandReading,
  type BandVerdict,
} from "./bandReading.ts";

export const BAND_READINGS: readonly BandReading[] = [raw as BandReading];

export function bandReadingFor(
  market: string,
  horizonSessions: number,
  modelVersion: string | null | undefined,
): BandVerdict {
  return readingForIn(BAND_READINGS, market, horizonSessions, modelVersion);
}

export type { BandReading, BandVerdict };
