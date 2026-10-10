// Which measured target to show as the exit if the setup works, and never a fourth one.
//
// One rule, in one place, because three surfaces now ask the same question: the asset panel, the
// home LONG/SHORT rows and the coming-week block. Three copies of a preference order is how two of
// them come to quote different levels for one name.
//
// `jobs/horizons.py` writes up to three rows per setup, one per method, and rule 24 forbids
// averaging them: three methods that disagree are three answers, and their mean is a number
// nothing measured. So one is chosen by a stated preference and its method is printed beside it.

export interface TargetLike {
  /// "structure", "volatility" or "analog".
  method: string;
  low: number;
  high: number;
  distancePct: number | null;
  rewardRisk: number | null;
  note?: string;
}

export interface SetupLike {
  state: string;
  horizon?: string | null;
  targets?: TargetLike[] | null;
}

/// The order, and it is now the measured one rather than the readable one.
///
///  1. **volatility** — a multiple of the asset's own recent true range. Not a place anything
///     happened, but a distance this asset covers.
///  2. **structure** — the nearest price where this series has already turned. A fact about where
///     the market stopped before, which is what "where would I take this off" sounds like it
///     should mean.
///  3. **analog** — what followed similar past days. Last, because it is a distribution over a
///     sample rather than a level: it answers how far this usually got, not where it would stop.
///
/// **Structure was first and is now second, and the reason is evidence.** Measured 2026-10-09
/// over the 465 current swing setups that carry targets, against the volatility stop
/// `jobs/setup.py` now places:
///
///     method        n     median reward     reaching 1x
///     volatility  465             2.04x       463 of 465
///     structure   446             0.41x       107 of 446
///     analog      195             0.17x         3 of 195
///
/// The nearest level a series has already turned at is usually very near. As an exit it is a real
/// level and a poor payoff, and preferring it meant the typical card offered 0.41 times its own
/// risk — a trade that has to be right two and a half times over to break even.
///
/// The deciding argument is not the ratio, it is which configuration was tested. The backtest
/// behind `STOP_SIGMAS` simulated entry at the window extreme, a stop at 1.5 of the asset's daily
/// dispersion and **a target at a volatility multiple** -- 174,277 long setups, first touch over
/// 20 sessions, 46.8% reaching the target and a mean outcome of +0.139 times the risk. The
/// structural target has never been through that, and it was the one every card was showing.
///
/// One caveat worth carrying: the backtest's target was two close-to-close standard deviations
/// and `jobs/horizons.py` writes two average true ranges, which is wider. A wider target is
/// reached less often than the simulation showed, so the measured hit rate is an upper bound on
/// what production will do, not a prediction of it. `DecisionLog` records the reward on every
/// decision and matures at +1, +5 and +20 sessions, which is what will settle it.
///
/// Structure is still stored, still shown when volatility is absent, and the panel names which
/// method it is quoting, so nothing here hides the nearer level from a reader who wants it.
const PREFERENCE = ["volatility", "structure", "analog"] as const;

/// The horizon order `pickSetup` in lib/decisionInput.ts walks, declared here because that file
/// imports this one and the dependency cannot run both ways.
///
/// Shortest first: the shorter the horizon the sooner a reader has to act on it. **Intraday is
/// in the list**, and leaving it out was a real contradiction on a live page rather than a
/// tidiness point — see `decidingSetup`.
const HORIZON_ORDER = ["swing", "longer", "intraday"] as const;

/// The setup the decision rested on, mirroring `pickSetup` in lib/decisionInput.ts.
///
/// Not simply the swing row. `pickSetup` takes the first *directional* row in horizon order, so a
/// name whose swing read is `wait` and whose longer read is `buy` was decided on the longer one —
/// and reading swing-first printed "No clear target stored" for exactly those names while their
/// targets sat on the setup the verdict came from. Live on HMC and MU before this was fixed.
///
/// It walked `["swing", "longer"]` where `pickSetup` walks all three, and the missing third is
/// what this comment is really for. The asset page passes every stored horizon, so a name whose
/// only directional row is the intraday one was decided on that row and had its target looked for
/// on a row that did not decide. Live on PLTR on 2026-10-09: the panel printed **"Exit if
/// working: No clear target stored"** directly above **"Reward against risk: 0.2x"** — a figure
/// computed from the target the first line said did not exist. One panel, two answers, because
/// one question had two implementations.
///
/// The two copies are still two functions, which rule 36 says is the shape to avoid. What keeps
/// them honest is a test that a decision taken on an intraday row quotes that row's target, not a
/// comment promising they match.
function decidingSetup(setups: SetupLike[]): SetupLike | null {
  const directional = (r: SetupLike) => r.state === "buy" || r.state === "short";
  for (const horizon of HORIZON_ORDER) {
    const found = setups.find((r) => r.horizon === horizon && directional(r));
    if (found) return found;
  }
  return setups.find((r) => r.horizon === "swing") ?? setups[0] ?? null;
}

/// One measured target, or null when the job stored none.
///
/// Null is a real and common state rather than an edge case: `jobs/horizons.py` writes no target
/// row at all when the setup has no invalidation to measure reward against. The surfaces then say
/// so. Nothing here computes a level — a target invented in the web layer is exactly what `jobs/`
/// exists to prevent.
export function pickTarget(setups: SetupLike[]): TargetLike | null {
  const setup = decidingSetup(setups.filter(Boolean));
  return preferredTarget(setup?.targets ?? null);
}

/// The preference order applied to one setup's own target rows.
///
/// Split out of `pickTarget` because the rule table needs the same answer from a setup it has
/// *already* chosen: `toDecisionInput` picks the deciding row with `pickSetup` and then has to
/// reduce that row's methods to one. Having it re-enter `pickTarget` would run `decidingSetup`
/// a second time over a different list and could land on another horizon's target — and writing
/// the order out again in `decisionInput.ts` would be a second copy of one preference, which is
/// the shape rule 36 warns about. One order, two callers, no second list.
/// Below this reward against risk, a "target" is sitting on the entry and is not one.
///
/// `jobs/horizons.py` measures the structural target as the nearest price where the series has
/// already turned, and takes whatever that is — so when the nearest pivot happens to sit a few
/// ticks above the entry, the row is written with a reward of 0.03x and the panel prints "0.0x".
/// Live on Algorand on 2026-10-09: entry 0.10 to 0.14, stop 0.10, structural target 0.14, reward
/// 0.0x. Every number true, and together they describe a trade with no room in it.
///
/// A tenth of the stop distance is the floor because that is the point at which the reward stops
/// being a reward: a target nearer to the entry than a tenth of the distance to being wrong is
/// inside the noise the stop was sized against. It is not a filter on quality — a 0.4x setup
/// still prints 0.4x — only on whether the method produced a target at all.
const REWARD_FLOOR = 0.1;

/// Generic over the row rather than taking `TargetLike`, because the two callers hold different
/// slices of the same stored row: the pages want `note` and `distancePct` to print, the rule
/// table wants only `rewardRisk` to size with. A shared concrete type would force one of them to
/// carry columns it has no use for, which is how a rule table ends up importing a query's shape.
///
/// Two passes over the preference order, and the second is the fallback the structural method
/// needs. The first takes the most-preferred method whose reward clears `REWARD_FLOOR`; the
/// second takes the most-preferred method at all, so a setup whose every method is flat still
/// shows its real figure rather than nothing.
///
/// This is where the volatility method earns its place in the order. It is a multiple of the
/// asset's own average true range, so it always produces a distance — where `structure` depends
/// on a pivot existing above the entry and `analog` on a median that points the right way.
/// Preferring structure is still right when structure says something; falling to the ATR
/// distance when it does not is the difference between a card that quotes a level and a card
/// that quotes the entry back to the reader.
export function preferredTarget<T extends { method: string; rewardRisk?: number | null }>(
  targets: readonly T[] | null | undefined,
): T | null {
  if (!targets || !targets.length) return null;
  const usable = (t: T) => t.rewardRisk !== null && t.rewardRisk !== undefined && t.rewardRisk >= REWARD_FLOOR;
  for (const method of PREFERENCE) {
    const found = targets.find((t) => t.method === method && usable(t));
    if (found) return found;
  }
  const anyUsable = targets.find(usable);
  if (anyUsable) return anyUsable;
  for (const method of PREFERENCE) {
    const found = targets.find((t) => t.method === method);
    if (found) return found;
  }
  return targets[0] ?? null;
}

/// What the method measured, in the reader's words rather than the job's.
export function targetMethodLabel(method: string): string {
  if (method === "structure") return "nearest level it has already turned at";
  if (method === "volatility") return "its own recent daily range";
  if (method === "analog") return "what followed similar past days";
  return method;
}
