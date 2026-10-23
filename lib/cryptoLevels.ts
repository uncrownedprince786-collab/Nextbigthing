// Where to act, where to be wrong, and where to take it off.
//
// **These are a measurement, not a prediction, and the distinction is the whole file.** The brain
// is binary: it predicts the *sign* of the forward return and nothing else. It has no opinion on
// magnitude, so a target derived from its probability would be a size claim it never made.
//
// So the distances come from `tools/research/crypto_levels.py`, which measured -- over the
// training folds only, never the holdout -- how far price actually travelled over each window, in
// units of the coin's own 14-bar ATR at the decision bar. The stop and target multiples served
// here are chosen from that table by one rule, fixed below, and the hit rate the page prints
// beside them is the one that was measured for exactly that pair.
//
// ATR rather than a fixed percentage, because a 0.5% stop is a scratch on Bitcoin and a round
// trip on a small coin. The ATR used at serving time is the same `atr14` the model read, out of
// the same feature vector, so the level on the page and the level in the measurement are the same
// arithmetic on the same window.
//
// Nothing here is advice, a position size or a trade, and no transaction cost, spread, funding or
// slippage is in any number.

import table from "@/data/foundation/dataset/crypto_levels.json";
import { FEATURES } from "@/lib/intradayFeatures";
import type { HorizonKey } from "@/lib/cryptoHorizons";
import type { Lane } from "@/lib/cryptoLanes";

const ATR_INDEX = FEATURES.indexOf("atr14");

export interface Levels {
  /// The close the direction was measured from. Acting away from it is acting on a different
  /// claim, so it is printed rather than left implied.
  entry: number;
  stop: number;
  target: number;
  /// The multiples, in ATR units, these came from.
  stopAtr: number;
  targetAtr: number;
  /// The decision bar's ATR as a fraction of price -- the thing both levels are scaled by.
  atrPct: number;
  /// Distance to each level as a percentage of entry, which is what a reader actually compares.
  stopPct: number;
  targetPct: number;
  /// Reward against risk, from the distances above.
  rr: number;
  /// Of the measured rows that ended up going this way, how often the target came first.
  targetFirstWhenRight: number;
  stoppedWhenRight: number;
  /// How often the window simply closed with neither level touched. At one bar ahead this is most
  /// of them, and a reader who is not told that will read a target as a thing that usually
  /// happens.
  neitherWhenRight: number;
  /// Expected move in ATR units from this pair, on rows that went the right way. The number the
  /// pair was chosen by, carried so the choice can be read rather than taken on trust.
  expectedAtr: number;
  measuredRows: number;
}

interface Pair {
  stopAtr: number;
  targetAtr: number;
  reachedTargetWithoutTouchingStop: number;
  stoppedWithoutReachingTarget: number;
  touchedBoth: number;
  neither: number;
}

interface HorizonLevels {
  rows: number;
  note?: string;
  favourableExcursionAtr?: { p25: number; median: number; p75: number; p90: number };
  adverseExcursionAtr?: { p25: number; median: number; p75: number; p90: number };
  medianAtrPctOfPrice?: number;
  pairs?: Record<string, Pair>;
}

interface Doc {
  generatedAt: string;
  unit: string;
  whatThisIsNot: string[];
  families: Record<string, Record<string, HorizonLevels>>;
}

const DOC = table as unknown as Doc;

export const LEVELS_GENERATED_AT = DOC.generatedAt;
export const LEVELS_CAVEATS = DOC.whatThisIsNot;

/// The expected move in ATR units from one pair, on the rows that went the right way.
///
/// `p(target first) x target - p(stopped first) x stop`. The rows that touched both, and the rows
/// that touched neither before the window closed, contribute nothing: which of the two came first
/// is not recorded, and a window that closes flat is a scratch.
function expected(p: Pair): number {
  return (
    p.reachedTargetWithoutTouchingStop * p.targetAtr -
    p.stoppedWithoutReachingTarget * p.stopAtr
  );
}

/// Which stop/target pair to serve, chosen once rather than per request.
///
/// The rule: of the measured pairs, the one with the highest expected move above.
///
/// Not the highest hit rate, which was the first rule here and was wrong. Hit rate alone always
/// picks the tightest pair on the ladder -- a target half an ATR away is reached more often than
/// one two ATR away, necessarily -- and on a fifteen-minute Bitcoin call that produced a target
/// 0.05% from entry, which is inside the spread and is not a trade. And not the highest
/// reward-to-risk either: a 1:4 pair reached one time in nine is worse than a 1:1.5 reached half
/// the time, and picking on R alone turns a level table into a lottery ticket with a good ratio.
/// Expected value is the quantity that balances the two, so it is the one that chooses.
function bestPair(h: HorizonLevels | undefined): Pair | null {
  if (!h?.pairs) return null;
  let best: Pair | null = null;
  for (const p of Object.values(h.pairs)) {
    if (!best || expected(p) > expected(best)) best = p;
  }
  return best;
}

/// The levels for one call, or null when this window has no measured table.
///
/// Null is served as an absence on the page, never as a made-up number: a stop invented because
/// the table was missing is exactly the kind of plausible figure this repository exists not to
/// print.
export function levelsFor(
  lane: Lane,
  horizon: HorizonKey,
  direction: "UP" | "DOWN",
  entry: number,
  features: number[],
): Levels | null {
  const family = DOC.families[lane.family] ?? DOC.families.crypto;
  const h = family?.[horizon];
  const pair = bestPair(h);
  if (!pair || !h || !h.rows || !Number.isFinite(entry) || entry <= 0) return null;

  const atrPct = features[ATR_INDEX];
  if (!Number.isFinite(atrPct) || atrPct <= 0) return null;

  const sign = direction === "UP" ? 1 : -1;
  const stopDist = entry * atrPct * pair.stopAtr;
  const targetDist = entry * atrPct * pair.targetAtr;
  return {
    entry,
    stop: entry - sign * stopDist,
    target: entry + sign * targetDist,
    stopAtr: pair.stopAtr,
    targetAtr: pair.targetAtr,
    atrPct: atrPct * 100,
    stopPct: (stopDist / entry) * 100,
    targetPct: (targetDist / entry) * 100,
    rr: targetDist / stopDist,
    targetFirstWhenRight: pair.reachedTargetWithoutTouchingStop,
    stoppedWhenRight: pair.stoppedWithoutReachingTarget,
    neitherWhenRight: pair.neither,
    expectedAtr: expected(pair),
    measuredRows: h.rows,
  };
}
