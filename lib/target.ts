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
  note: string;
}

export interface SetupLike {
  state: string;
  horizon?: string | null;
  targets?: TargetLike[] | null;
}

/// The reader's order, not the arithmetic's.
///
///  1. **structure** — the nearest price where this series has already turned. The only one of the
///     three that is a fact about where the market stopped before, which is what "where would I
///     take this off" actually means.
///  2. **volatility** — a multiple of the asset's own recent daily range. Not a place anything
///     happened, but a distance this asset covers.
///  3. **analog** — what followed similar past days. Last, because it is a distribution over a
///     sample rather than a level: it answers how far this usually got, not where it would stop.
const PREFERENCE = ["structure", "volatility", "analog"] as const;

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
/// Generic over the row rather than taking `TargetLike`, because the two callers hold different
/// slices of the same stored row: the pages want `note` and `distancePct` to print, the rule
/// table wants only `rewardRisk` to size with. A shared concrete type would force one of them to
/// carry columns it has no use for, which is how a rule table ends up importing a query's shape.
/// `method` is all the order is chosen on, so `method` is all this asks for.
export function preferredTarget<T extends { method: string }>(
  targets: readonly T[] | null | undefined,
): T | null {
  if (!targets || !targets.length) return null;
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
