/// Every name gets a direction: the owner's binary rule on top of the evidence table.
///
/// `decide()` in lib/decision.ts is the evidence table and is unchanged: it still says WAIT where the
/// evidence it requires is not there, and its tests still pin that. This layer runs after it and turns
/// every WAIT into LONG or SHORT, by the reason the table gave (brain.md rule 86, which replaces the
/// refusal in rule 85 at the owner's instruction):
///
///   * `stop-crossed`         the close went through the setup's stop, so the call follows the break;
///   * `short-unbacked`       the setup reads down and nothing independent confirms it: SHORT anyway;
///   * `reversal-unconfirmed` the flip is not confirmed yet, so the call the reader holds is kept --
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
/// After that, one guard on every call, the evidence table's included (`whipsawHold`): a call may not return
/// to the direction it left within `WHIPSAW_DAYS` unless the return is confirmed.
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
  type TradePlan,
} from "./decision.ts";

/// Stop distance in average true ranges, as the owner specified.
export const ATR_STOP_MULTIPLE = 2;

/// The gate prefix every resolved call is logged under.
export const FORCED = "forced-";

/// Calendar days, counted from the day the current direction began, inside which a call may not go back
/// to the direction it replaced without a confirmation. The final audit (2026-10-10) found SHORT, then a
/// forced LONG on a stop-cross, then SHORT again on an unconfirmed turn: two reversals in three days, the
/// whipsaw rule 80 exists to prevent, reachable because the reversal gate reads only calls the evidence
/// table made (rightly: a forced call is logged daily and would keep a turn "recent" for ever). This guard
/// reads the run's *start*, which a daily re-log does not move, so it cannot hold a call for ever either.
export const WHIPSAW_DAYS = 3;

/// The stop's least distance beyond the entry zone, in 14-session average true ranges (the owner's rule,
/// 2026-10-11). The zone runs from the setup's stop to its entry level, so the stop sat exactly on the
/// zone's edge -- Askari Bank's band Rs.102.50 to Rs.106.19 with its stop at Rs.102.50 -- and a reader
/// buying at the bottom of the band was buying at the stop. Now the stop is
/// `min(zone low - 1.5 x ATR, the structural stop)` for a LONG, mirrored for a SHORT.
export const STOP_BUFFER_ATR = 1.5;

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
    // The call the reader holds, which after a forced flip is not the table's last call: keeping the
    // table's SHORT after a forced LONG printed SHORT, LONG, SHORT and said "the last call holds".
    return { side: input.lastRun?.direction ?? input.priorDirection.direction, gate: FORCED + d.gate };
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
  "whipsaw-hold": `It would go back to the side it left under ${WHIPSAW_DAYS} days ago with nothing confirming the return, so the current call holds.`,
  nosignal: "Nothing measured leans either way; the call follows the long-run drift.",
};

/// A WAIT turned into a direction, or the decision unchanged when it already has one.
export function resolveCall(d: Decision, input: DecisionInput): Decision {
  if (d.action !== "WAIT") return d;
  const r = resolvedSide(d, input);
  if (!r) return d;
  return forcedCall(d, input, r);
}

function daysBetween(fromISO: string, toISO: string): number {
  const a = Date.parse(fromISO + "T00:00:00Z");
  const b = Date.parse(toISO + "T00:00:00Z");
  return Number.isNaN(a) || Number.isNaN(b) ? Number.NaN : Math.round((b - a) / 86_400_000);
}

/// The whipsaw guard: a call that would go back, unconfirmed, to the direction the reader's current call
/// replaced under `WHIPSAW_DAYS` ago keeps the current call instead. A confirmed return is a real turn and
/// passes; so does any return once the current direction is older than the window.
export function whipsawHold(d: Decision, input: DecisionInput): Decision {
  const run = input.lastRun;
  if (!run || !run.left || run.left === run.direction) return d;
  if (d.action !== "LONG" && d.action !== "SHORT") return d;
  const side: Side = d.action === "LONG" ? "up" : "down";
  if (side !== run.left) return d;
  const age = daysBetween(run.since, input.today);
  if (!Number.isFinite(age) || age < 1 || age > WHIPSAW_DAYS) return d;
  if (confirmingLegs(input, side).length > 0) return d;
  const close = input.lastClose;
  if (close === null || !Number.isFinite(close)) return d;
  return forcedCall(d, input, { side: run.direction, gate: FORCED + "whipsaw-hold" });
}

/// A call on the given side, with its stop, legs, confidence cap and reason: what every resolution and
/// the whipsaw guard produce.
function forcedCall(d: Decision, input: DecisionInput, r: { side: Side; gate: string }): Decision {
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
  return bufferStop(whipsawHold(resolveCall(decide(input), input), input), input);
}

/// The stop moved to at least `STOP_BUFFER_ATR` average true ranges beyond the entry zone, never nearer
/// than the structural stop it replaces, with the plan's reward:risk re-measured against it. A name with
/// no stored ATR keeps its stop: a volatility figure is not invented (every active name had one on
/// 2026-10-11), and `tools/logic_audit.py` reports any stop left on the zone's edge.
export function bufferStop(d: Decision, input: DecisionInput): Decision {
  if ((d.action !== "LONG" && d.action !== "SHORT") || !d.entry) return d;
  const atr = input.atr;
  if (atr == null || !Number.isFinite(atr) || atr <= 0) return d;
  const long = d.action === "LONG";
  const edge = long ? d.entry.low : d.entry.high;
  const buffered = long ? edge - STOP_BUFFER_ATR * atr : edge + STOP_BUFFER_ATR * atr;
  if (!(buffered > 0)) return d;
  const own = d.invalidation;
  const hasOwn = own !== null && Number.isFinite(own);
  // Eight significant digits, as resolvedStop rounds: a fixed number of decimals would flatten a coin.
  const stop = Number((hasOwn ? (long ? Math.min(buffered, own) : Math.max(buffered, own)) : buffered).toPrecision(8));
  if (hasOwn && stop === own) return d;
  const sentence = `The stop is ${STOP_BUFFER_ATR} x the 14-session average true range beyond the entry zone, so it never sits on the zone's edge.`;
  const forced = d.gate.startsWith(FORCED);
  return {
    ...d,
    invalidation: stop,
    // A resolved call's second line is its stop sentence; a call the table made keeps its reasons and
    // gains the sentence as a note.
    why: forced ? [d.why[0], sentence, ...d.why.slice(2)] : d.why,
    notes: forced ? d.notes : [...d.notes, sentence],
    plan: d.plan ? replan(d.plan, d.entry, stop, long) : null,
  };
}

/// The plan re-measured against a moved stop: reward:risk from the entry level the call trades from, and
/// the expectancy that rests on it. A target on the loss side has no reward to weigh.
function replan(plan: TradePlan, entry: { low: number; high: number }, stop: number, long: boolean): TradePlan {
  const from = long ? entry.high : entry.low;
  const risk = Math.abs(from - stop);
  const near = plan.target ? (long ? plan.target.low : plan.target.high) : null;
  const rewardRisk =
    near !== null && risk > 0 && (long ? near > from : near < from) ? Math.abs(near - from) / risk : null;
  const expectancyR =
    plan.baseRate && rewardRisk !== null ? plan.baseRate.share * rewardRisk - (1 - plan.baseRate.share) : null;
  return { ...plan, invalidation: stop, rewardRisk, expectancyR };
}
