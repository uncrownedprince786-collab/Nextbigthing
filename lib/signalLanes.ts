// What a validated signal lane is, and the rules for reading one — with no data in the file.
//
// Split from lib/signalValidation for the same reason lib/marketMarkets is split from
// lib/marketCapability: that file alias-imports a JSON artifact, which a bundler resolves and
// `node --test` does not. The rules are the part worth testing, so they live here where the test
// lane can reach them, and the artifact is bound to them next door.
//
// Every function takes the lane table as its first argument. That is deliberate: a reader of this
// file can see that nothing here consults a global, so a test exercising these rules is exercising
// the same code the site runs.

/// The badge a validated lane may show. There is deliberately no HIGH: every lane validated so far
/// is validated on a *holdout*, which is still a backtest, and HIGH on a backtest is the claim this
/// project exists not to make. HIGH is reserved for a lane with matured prospective outcomes.
export type Confidence = "MEDIUM" | "LOW";
export type Side = "LONG" | "SHORT";

export interface LaneEvidence {
  lift?: number;
  blockedBootstrapZ?: number;
  ci95?: [number, number];
  pBonferroni?: number;
  armsSearched?: number;
  walkForwardFolds?: number;
  walkForwardPositive?: number;
  holdoutRows?: number;
  holdoutSessions?: number;
  source?: string;
}

export interface Lane {
  market: string;
  horizonSessions: number;
  side: Side;
  validated: boolean;
  confidence: Confidence | null;
  why: string;
  evidence: LaneEvidence;
}

/// What to render for a (market, horizon) pair, as one value so a caller cannot forget a case.
///
/// Three outcomes and they are not interchangeable:
///   * `directional` — a side survived testing and may be shown with its badge.
///   * `refused`     — a side was tested and failed. The reason is shown, because "we looked and
///                     it did not hold" is more useful to a reader than silence.
///   * `untested`    — nothing has been measured here. No direction, and no implication that one
///                     would be bad if it were.
export type Verdict =
  | { kind: "directional"; side: Side; confidence: Confidence; lane: Lane }
  | { kind: "refused"; lanes: Lane[] }
  | { kind: "untested" };

export function laneFor(
  lanes: readonly Lane[], market: string, horizonSessions: number, side: Side,
): Lane | undefined {
  return lanes.find(
    (l) => l.market === market && l.horizonSessions === horizonSessions && l.side === side,
  );
}

/// Every side that may be shown as a direction for this market and horizon. Usually empty.
export function validatedSides(
  lanes: readonly Lane[], market: string, horizonSessions: number,
): Side[] {
  return (["LONG", "SHORT"] as Side[]).filter(
    (s) => laneFor(lanes, market, horizonSessions, s)?.validated === true,
  );
}

/// Whether any horizon of this market has a validated side — what a market tile needs to know.
export function marketHasValidatedSignal(lanes: readonly Lane[], market: string): boolean {
  return lanes.some((l) => l.market === market && l.validated);
}

/// The horizons of this market that carry a validated side, shortest first.
export function validatedHorizons(lanes: readonly Lane[], market: string): number[] {
  return [...new Set(lanes.filter((l) => l.market === market && l.validated)
    .map((l) => l.horizonSessions))].sort((a, b) => a - b);
}

export function verdictFor(
  lanes: readonly Lane[], market: string, horizonSessions: number,
): Verdict {
  const sides = validatedSides(lanes, market, horizonSessions);
  if (sides.length > 0) {
    const lane = laneFor(lanes, market, horizonSessions, sides[0])!;
    return { kind: "directional", side: sides[0], confidence: lane.confidence!, lane };
  }
  const tested = lanes.filter(
    (l) => l.market === market && l.horizonSessions === horizonSessions);
  return tested.length ? { kind: "refused", lanes: tested } : { kind: "untested" };
}

/// The model's class vocabulary is UP / DOWN / FLAT; a trading side is LONG / SHORT. They are not
/// the same words and comparing them directly is a bug I shipped once: the decision screen tested
/// `predicted !== side`, found `"UP" !== "LONG"`, and refused a validated signal it should have
/// shown.
///
/// FLAT maps to `null` rather than to a side, because a model saying "no move clears the band" is
/// not a model saying "short it". That distinction is the reason this returns a nullable type
/// instead of defaulting to one side.
export function sideOfClass(predicted: string | null | undefined): Side | null {
  if (predicted === "UP") return "LONG";
  if (predicted === "DOWN") return "SHORT";
  return null;
}
