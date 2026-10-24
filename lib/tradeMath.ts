// The arithmetic that turns a direction and a pair of levels into something a reader can judge.
//
// None of this is a model and none of it is new information. Every number here is a function of
// three things the page already measured: the accuracy of the band this call belongs to, the
// distance to the stop, and the distance to the target. That is exactly why it is worth printing
// -- the hard numbers are already there, and without these the reader has to do the arithmetic
// that decides whether the edge is worth anything after the stop is set where it is.
//
// The one that matters most is the **break-even win rate**. A 1.3:1 target needs to be right
// about 43% of the time to make nothing. A reader looking at "right 64% of the time" and a
// 0.5:1 target is looking at two numbers that sound good separately and lose money together, and
// no amount of accuracy fixes a reward-to-risk that is upside down. Printing the threshold next
// to the measurement is the difference between a direction and a decision.
//
// Costs are not in any of it, and the page says so. A five-minute target a quarter of a percent
// away is inside what a taker fee plus spread costs on most venues, which is a fact about the
// instrument rather than about the model, and hiding it inside an "expectancy" would be the
// worst place to put it.

export interface TradeMath {
  /// Reward against risk, from the level distances. 1.3 means the target is 1.3x the stop away.
  rr: number;
  /// The win rate at which this pair of levels breaks even, before costs: loss / (win + loss).
  breakEven: number;
  /// The measured win rate this call's band actually achieved on the holdout.
  measured: number;
  /// How far the measurement sits above the threshold. Negative means the levels need a better
  /// hit rate than the model has ever shown.
  edge: number;
  /// Expected return per unit risked: p x rr - (1 - p). In units of the stop distance.
  expectancy: number;
  /// The Kelly fraction, (b*p - q) / b. Capped at a quarter, and never negative.
  ///
  /// Printed as a ceiling rather than a recommendation. Full Kelly on a 53%-edge coin flip is a
  /// position that halves an account on a normal losing streak, and the number is here to show
  /// how small the honest size is, not to suggest taking it.
  kelly: number;
  /// What one unit of risk buys: how many coins a given dollar risk corresponds to at this stop.
  unitsPerDollarRisked: number;
}

/// `null` when any input is missing, which the page prints as an absence rather than a zero.
export function tradeMath(
  entry: number,
  stop: number,
  target: number,
  measuredWinRate: number | null,
): TradeMath | null {
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  if (!(risk > 0) || !(reward > 0) || !Number.isFinite(entry) || entry <= 0) return null;
  if (measuredWinRate === null || !Number.isFinite(measuredWinRate)) return null;

  const rr = reward / risk;
  const breakEven = risk / (reward + risk);
  const p = Math.min(Math.max(measuredWinRate, 0), 1);
  const expectancy = p * rr - (1 - p);
  // (b*p - q) / b with b = rr. Floored at zero -- a negative Kelly is "do not take this", which
  // is said in words rather than as a negative size -- and capped at a quarter, because the
  // fraction assumes the win rate is known and ours is an estimate from a holdout.
  const kelly = Math.min(0.25, Math.max(0, (rr * p - (1 - p)) / rr));

  return {
    rr,
    breakEven,
    measured: p,
    edge: p - breakEven,
    expectancy,
    kelly,
    unitsPerDollarRisked: 1 / risk,
  };
}
