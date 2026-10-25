// What acting on a lane's calls would actually have done, after the fee.
//
// **This is the number the page was missing, and its absence was the most misleading thing on
// it.** A reader saw "right 64.2% of the time" next to an entry, a stop and a target, and the
// only honest conclusion from those three things together is that following them makes money.
// Measured, it does not: `tools/research/crypto_backtest.py` walks every call forward bar by bar
// and charges ten basis points a round trip, and every lane comes back negative on the holdout.
//
// The split between gross and net is the whole story and both are carried here. On the intraday
// lanes the gross expectancy is still **positive** on data the model never saw -- the direction is
// real, exactly as the accuracy figures say -- and the fee is what turns each of them negative. A
// fifteen-minute move is about 0.14% of price and a retail round trip is 0.10%: the edge is real
// and it is smaller than the toll.
//
// Which also says what would change the answer, and the page says it: a lower fee. The
// break-even round trip is a few basis points, which a maker order on a volume tier can reach
// and a retail taker cannot.
//
// Absent for a lane nobody has swept yet, and absence is printed as absence.

import raw from "@/data/foundation/dataset/crypto_strategy.json";
import type { HorizonKey } from "@/lib/cryptoHorizons";

export interface LaneStrategy {
  band: string;
  stopAtr: number;
  targetAtr: number;
  chosenOn: string;
  validationNetR: number;
  test: {
    netExpectancyR: number;
    grossExpectancyR: number;
    winRate: number;
    breakEvenWinRate: number;
    profitFactor: number | null;
    maxDrawdownR: number;
    sharpePerTrade: number | null;
    trades: number;
    meanCostInR: number;
  };
}

interface Doc {
  generatedAt: string;
  costBps: number;
  lanes: Record<string, LaneStrategy>;
}

const DOC = raw as unknown as Doc;

export const STRATEGY_COST_BPS = DOC.costBps;
export const STRATEGY_GENERATED_AT = DOC.generatedAt;

export function strategyFor(family: string, horizon: HorizonKey): LaneStrategy | null {
  return DOC.lanes[`${family}:${horizon}`] ?? null;
}

/// The round trip, in basis points, at which this lane's measured gross edge exactly pays for
/// itself. Null when the gross edge is negative, because then no fee makes it work.
///
/// `cost_in_R` scales linearly with the fee, so the break-even fee is the current one times the
/// ratio of gross expectancy to current cost. It is the single most actionable number here: it
/// turns "this loses money" into "this loses money above N basis points", which a reader can
/// check against their own account.
export function breakEvenFeeBps(s: LaneStrategy, costBps: number): number | null {
  if (s.test.grossExpectancyR <= 0 || s.test.meanCostInR <= 0) return null;
  return costBps * (s.test.grossExpectancyR / s.test.meanCostInR);
}
