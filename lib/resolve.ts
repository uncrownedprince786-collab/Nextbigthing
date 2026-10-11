/// The layer after the evidence table: what every caller prints, logs and publishes (brain.md rule 93).
///
/// `decide()` in lib/decision.ts is the evidence table. This layer used to turn its refusals into calls
/// (rule 86, the "binary rule"): a stopped call into the opposite side, an unconfirmed short into SHORT
/// anyway, a macro veto into the other side, a stale or silent name into whatever its momentum leaned,
/// an unconfirmed turn or return into the call it replaced. Rule 92 removed the first two; rule 93
/// removes the rest. **A refusal of the table stays a refusal.** Nothing here can produce a direction
/// the table did not, and three steps can only take one away:
///
///   1. `endStoppedCall` -- a call that ended at its stop keeps the stop it ended at and loses its entry
///      band and plan, so no surface prints a zone to enter for a finished plan (rule 92);
///   2. `requireConfirmation` -- a direction no confirmation backs is WAIT, naming the five that are
///      absent. Rule 93: no name shows LONG or SHORT anywhere on a setup alone;
///   3. `bufferStop` -- the stop at least `STOP_BUFFER_ATR` beyond the entry zone (rule 91);
///   4. `dataGate` -- last, after everything: a stale, silent, missing or unreadable close is WAIT
///      whatever came before it, with the data reason.
///
/// Rule 93 also capped the grade at Medium until outcomes matured; rule 94 withdrew the cap. The grade is
/// the evidence for this reading and outcome validation is a separate question with its own label
/// (lib/outcome.ts), shown beside the grade wherever a call is.
///
/// One function (`decideCall`) is used by the lists, the asset page, `/api/signals` and the nightly log,
/// so they cannot resolve the same name two ways.

import {
  confirmingLegs,
  decide,
  LEGS,
  STALE_AFTER_DAYS,
  type Decision,
  type DecisionInput,
  type TradePlan,
} from "./decision.ts";

/// The stop's least distance beyond the entry zone, in 14-session average true ranges (the owner's rule,
/// 2026-10-11, first given as 1.5 and settled at 1.0). The zone runs from the setup's stop to its entry
/// level, so the stop sat exactly on the zone's edge -- Askari Bank's band Rs.102.50 to Rs.106.19 with its
/// stop at Rs.102.50 -- and a reader buying at the bottom of the band was buying at the stop. Now the stop
/// is `min(zone low - 1.0 x ATR, the structural stop)` for a LONG, mirrored for a SHORT. Chosen, not
/// measured: no outcome had matured when it was set.
export const STOP_BUFFER_ATR = 1.0;

const LEG_WORDS: Record<(typeof LEGS)[number], string> = {
  timeframe: "the longer view reading the same way",
  volume: "volume at or above its average",
  history: "similar past days leaning this way",
  peers: "a gap against its peers",
  trigger: "an entry event on this session",
};

/// A call that ended at its stop keeps the level it ended at -- which its reason quotes -- and loses its
/// entry band and plan: an ended call printing a zone to enter and a reward to weigh reads as a live trade.
export function endStoppedCall(d: Decision): Decision {
  return d.action === "WAIT" && d.gate === "stop-crossed" ? { ...d, entry: null, plan: null } : d;
}

/// A direction no confirmation backs is not printed as one (rule 93). The table can still read a side --
/// a setup in state `buy` or `short`, a trend gate 8 carried on a reward figure -- and the five
/// confirmations can all be absent; before this, 96 names on 2026-10-11 showed LONG or SHORT that way.
/// It becomes WAIT, keeps the side it read as `intent`, and names every absent confirmation.
export function requireConfirmation(d: Decision, input: DecisionInput): Decision {
  if (d.action !== "LONG" && d.action !== "SHORT") return d;
  const side = d.action === "LONG" ? "up" : "down";
  if (confirmingLegs(input, side).length > 0) return d;
  const read = side === "up" ? "rising" : "falling";
  return {
    ...d,
    action: "WAIT",
    why: [
      `The rule table reads a ${read} setup, and none of the five confirmations backs it.`,
      `Absent: ${LEGS.map((l) => LEG_WORDS[l]).join(", ")}.`,
    ],
    timeSense: "WAIT FOR LEVEL",
    confidence: "Low",
    notes: [],
    gate: "no-confirmation",
    basis: "evidence",
    plan: null,
    legs: [],
    intent: side,
    developing: null,
  };
}

function daysBetween(fromISO: string, toISO: string): number {
  const a = Date.parse(fromISO + "T00:00:00Z");
  const b = Date.parse(toISO + "T00:00:00Z");
  return Number.isNaN(a) || Number.isNaN(b) ? Number.NaN : Math.round((b - a) / 86_400_000);
}

/// The data reason a direction must not be printed under, or null when the data holds (rule 93). The same
/// tests as the table's gates 1 to 3, run again on the final output, so no step between them and here can
/// carry a direction past them: no close, an unreadable date, a close older than its market allows, or a
/// price source that answered nothing.
export function dataFault(input: DecisionInput): { gate: string; why: string } | null {
  const close = input.lastClose;
  if (input.asOf === null || close === null || !Number.isFinite(close)) {
    return { gate: "no-prices", why: `No stored close for ${input.symbol}.` };
  }
  const age = daysBetween(input.asOf, input.today);
  if (Number.isNaN(age)) return { gate: "bad-date", why: "Stored date cannot be read." };
  const limit = STALE_AFTER_DAYS[input.market];
  if (age > limit) {
    return { gate: "stale", why: `Data stale: newest close ${input.asOf}, ${age} days old; this market allows ${limit}.` };
  }
  if (input.sourceSilent) return { gate: "source-silent", why: `${input.sourceSilent} answered nothing.` };
  return null;
}

/// The final hard gate: a direction on faulty data is WAIT with the data reason, whatever produced it.
export function dataGate(d: Decision, input: DecisionInput): Decision {
  if (d.action !== "LONG" && d.action !== "SHORT") return d;
  const fault = dataFault(input);
  if (!fault) return d;
  return {
    ...d,
    action: "WAIT",
    why: [fault.why, "No call is made on data that fails its own freshness rule."],
    timeSense: "WAIT FOR LEVEL",
    confidence: "Low",
    notes: [],
    gate: fault.gate,
    basis: "file",
    plan: null,
    legs: [],
    intent: null,
    developing: null,
  };
}

/// What every caller uses. Each step after `decide` can only remove a direction or weaken a grade.
export function decideCall(input: DecisionInput): Decision {
  return dataGate(bufferStop(requireConfirmation(endStoppedCall(decide(input)), input), input), input);
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
  // min(buffered, structural) for a LONG, max for a SHORT: a structural stop already at least the buffer
  // away is the answer as it stands -- untouched, unrounded, and with no sentence claiming otherwise.
  if (own !== null && Number.isFinite(own) && (long ? own <= buffered : own >= buffered)) return d;
  // Eight significant digits, not a fixed number of decimals: a fixed six would flatten a sub-cent coin.
  const stop = Number(buffered.toPrecision(8));
  const sentence = `The stop is ${STOP_BUFFER_ATR} x the 14-session average true range beyond the entry zone, so it never sits on the zone's edge.`;
  return {
    ...d,
    invalidation: stop,
    notes: [...d.notes, sentence],
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
