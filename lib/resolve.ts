/// Every name gets a direction: the owner's binary rule on top of the evidence table.
///
/// `decide()` in lib/decision.ts is the evidence table and is unchanged: it still says WAIT where the
/// evidence it requires is not there, and its tests still pin that. This layer runs after it and turns
/// every WAIT into LONG or SHORT, by the reason the table gave (brain.md rule 86, which replaces the
/// refusal in rule 85 at the owner's instruction):
///
///   * `stop-crossed`         the close went through the setup's stop, so the call follows the break;
///   * `short-unbacked`       the setup reads down and nothing independent confirms it: SHORT anyway;
///   * `reversal-unconfirmed` the flip is not confirmed yet, so the previous direction is kept --
///                            the patient flip; it lifts when a confirmation arrives or after a week;
///   * `macro-veto`           the gatekeeper refused one side on breaking news: the other side;
///   * anything else          the side the table was leaning toward when it has one, else momentum.
///
/// A stop is kept when the call goes the setup's way and its stop sits on the right side of the close for
/// the direction taken; otherwise it is the close plus or minus `ATR_STOP_MULTIPLE` times the 14-session average
/// true range. Every resolved call is logged with its gate as `forced-<reason>`, so the logbook can
/// grade these calls apart from the ones the evidence table made itself. Confidence is capped at
/// Medium: a call the table refused is never printed as its strongest grade.
///
/// The one case that cannot be resolved is a name with no stored close at all: there is no price to
/// put a stop against. None of the 576 has that today; if one appears it stays WAIT and the page
/// checker's held-back count says so.

import {
  confirmingLegs,
  decide,
  EVENT_SOON_DAYS,
  type Confidence,
  type Decision,
  type DecisionInput,
} from "./decision.ts";

/// Stop distance in average true ranges, as the owner specified.
export const ATR_STOP_MULTIPLE = 2;

/// The gate prefix every resolved call is logged under.
export const FORCED = "forced-";

type Side = "up" | "down";

const flip = (d: Side): Side => (d === "up" ? "down" : "up");
const sign = (v: number | null | undefined): number => (v == null || !Number.isFinite(v) || v === 0 ? 0 : v > 0 ? 1 : -1);

/// The momentum read for a name whose setup takes no side: one vote each from the trend (close
/// against its 20- and 50-day averages), the longer-timeframe bias, the 20-session return, the gap to
/// its peers and the similar past days; two from an entry rule that fired on this session on volume.
/// A tie goes to the 20-session return, then the trend, then the last call; with nothing at all it is
/// LONG, the long-run drift of most markets, and logged as `forced-nosignal`.
export function momentumSide(input: DecisionInput): { side: Side; measured: boolean } {
  const t = (d: string | null | undefined) => (d === "up" ? 1 : d === "down" ? -1 : 0);
  const votes =
    t(input.setup?.trend) +
    t(input.setup?.bias) +
    sign(input.r20) +
    sign(input.relStrength) +
    sign(input.analogs?.medianPct) +
    2 * t(input.entryTrigger?.direction);
  if (votes !== 0) return { side: votes > 0 ? "up" : "down", measured: true };
  const tie = sign(input.r20) || t(input.setup?.trend) || t(input.priorDirection?.direction);
  if (tie !== 0) return { side: tie > 0 ? "up" : "down", measured: true };
  return { side: "up", measured: false };
}

/// Which way a WAIT resolves, and the gate it is logged under.
export function resolvedSide(d: Decision, input: DecisionInput): { side: Side; gate: string } | null {
  const close = input.lastClose;
  if (close === null || !Number.isFinite(close)) return null;
  if (d.gate === "stop-crossed") {
    // The close is through the stop: below it breaks down, above it breaks up.
    const stop = input.invalidation;
    if (stop !== null && Number.isFinite(stop) && stop !== close) {
      return { side: close < stop ? "down" : "up", gate: FORCED + d.gate };
    }
    if (d.intent) return { side: flip(d.intent), gate: FORCED + d.gate };
  }
  if (d.gate === "short-unbacked") return { side: "down", gate: FORCED + d.gate };
  if (d.gate === "reversal-unconfirmed" && input.priorDirection) {
    return { side: input.priorDirection.direction, gate: FORCED + d.gate };
  }
  if (d.gate === "macro-veto" && d.intent) return { side: flip(d.intent), gate: FORCED + d.gate };
  if (d.intent) return { side: d.intent, gate: FORCED + d.gate };
  const m = momentumSide(input);
  return { side: m.side, gate: FORCED + (m.measured ? d.gate : "nosignal") };
}

/// The stop for a resolved call: the setup's own when the call goes the setup's way and the stop is on
/// the right side of the close, else 2 x ATR. A stop that belongs to the other direction is never
/// reused, even when it happens to sit on the right side: after a break it is the level that just
/// failed, not a measurement of where the new call is wrong.
export function resolvedStop(side: Side, input: DecisionInput): number | null {
  const close = input.lastClose;
  if (close === null) return null;
  const own = input.invalidation;
  const sameWay = input.setup?.direction === side;
  if (sameWay && own !== null && Number.isFinite(own) && (side === "up" ? own < close : own > close)) return own;
  const atr = input.atr;
  if (atr == null || !Number.isFinite(atr) || atr <= 0) return null;
  const stop = side === "up" ? close - ATR_STOP_MULTIPLE * atr : close + ATR_STOP_MULTIPLE * atr;
  // Eight significant digits, not a fixed number of decimals: a fixed six would flatten a sub-cent coin.
  return stop > 0 ? Number(stop.toPrecision(8)) : null;
}

const WORDS: Record<string, string> = {
  "stop-crossed": "The close went through the old stop, so the call follows the break.",
  "short-unbacked": "The setup reads down; no independent confirmation yet.",
  "reversal-unconfirmed": "The setup turned, but the turn is not confirmed yet, so the last call holds.",
  "macro-veto": "Breaking news ruled out the other side.",
  nosignal: "Nothing measured leans either way; the call follows the long-run drift.",
};

/// A WAIT turned into a direction, or the decision unchanged when it already has one.
export function resolveCall(d: Decision, input: DecisionInput): Decision {
  if (d.action !== "WAIT") return d;
  const r = resolvedSide(d, input);
  if (!r) return d;
  const action = r.side === "up" ? "LONG" : "SHORT";
  const stop = resolvedStop(r.side, input);
  const legs = confirmingLegs(input, r.side);
  const confidence: Confidence = legs.length >= 1 ? "Medium" : "Low";
  const reason = r.gate.slice(FORCED.length);
  const why = [
    WORDS[reason] ?? "The momentum read decides the side.",
    stop === null
      ? "No stop could be measured: no stored stop on this side and no range to measure one from."
      : stop === input.invalidation
        ? "The stop is the setup's own."
        : `The stop is ${ATR_STOP_MULTIPLE} x the 14-session average true range from the close.`,
  ];
  const close = input.lastClose as number;
  return {
    ...d,
    action,
    why,
    entry: { low: close, high: close },
    invalidation: stop,
    timeSense: input.eventInDays !== null && input.eventInDays <= EVENT_SOON_DAYS ? "CARE" : "NOW",
    confidence,
    gate: r.gate,
    basis: null,
    plan: null,
    legs,
    intent: r.side,
    developing: null,
  };
}

/// What every caller uses: the evidence table, then the binary rule. One function, so the lists, the
/// asset page and the nightly log cannot resolve the same name two ways.
export function decideCall(input: DecisionInput): Decision {
  return resolveCall(decide(input), input);
}
