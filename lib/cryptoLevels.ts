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
  /// Net expectancy per unit of risk, measured on the validation fold with the fee charged. The
  /// number the pair was chosen by, carried so the choice can be read rather than taken on trust.
  /// Negative means these levels lost money there, which the page says in those words.
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
  /// The pair `crypto_backtest.py` found best on the validation fold, net of costs, together
  /// with what it did there. Absent until that sweep has been run for this lane.
  servedPair?: {
    stopAtr: number;
    targetAtr: number;
    netExpectancyR: number;
    grossExpectancyR: number;
    meanCostInR: number;
    winRate: number;
    profitFactor: number | null;
    trades: number;
    fold: string;
  };
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

/// Which stop/target pair to serve, and why it is no longer chosen here.
///
/// **The first two rules were both wrong, and the backtest is what found it.** Ranking by hit
/// rate picked the tightest pair on the ladder, because a target half an ATR away is reached more
/// often than one two ATR away, necessarily -- it produced a fifteen-minute target 0.05% from
/// entry. Ranking by expected move per unit of risk after costs looked right and was still wrong,
/// for a subtler reason: the hit rates in `pairs` are measured **on the rows that went the right
/// way**, and a trade is taken on every call, right or wrong. Optimising a conditional quantity
/// and living with the unconditional one picked 0.75/1.5 for the pooled hour, where the realised
/// net expectancy was worse than three other pairs on the same ladder.
///
/// So the pair is chosen by `tools/research/crypto_backtest.py`, which simulates every candidate
/// bar by bar on the **validation** fold -- entry at the close, stop and target walked forward,
/// a bar touching both scored as a loss, the fee charged on every trade -- and writes the winner
/// into `servedPair`. Chosen on validation, because choosing on the holdout is fitting the one
/// thing kept back for measuring.
///
/// `pairs` is still read, for the hit rates the page prints beside the levels. It is no longer
/// read to decide anything.
function bestPair(h: HorizonLevels | undefined): Pair | null {
  if (!h?.pairs) return null;
  const served = h.servedPair;
  if (served) {
    const exact = Object.values(h.pairs).find(
      (p) => p.stopAtr === served.stopAtr && p.targetAtr === served.targetAtr,
    );
    if (exact) return exact;
  }
  // No backtested choice for this lane yet: serve nothing rather than a pair chosen by a rule
  // that has now been measured and found wanting twice.
  return null;
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
    expectedAtr: h.servedPair?.netExpectancyR ?? 0,
    measuredRows: h.rows,
  };
}
