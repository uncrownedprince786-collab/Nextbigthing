/// The quality gate: which calls are published on the signal lists (the owner's rule, 2026-10-11).
///
/// Every priced name still gets a call (rule 86) and every call is still logged and graded: the gate
/// decides only what the lists *publish*. A call is published when, and only when, it has everything a
/// reader acts on, measured rather than assumed:
///
///   * a direction, LONG or SHORT;
///   * an entry range and a stop, as numbers;
///   * a stop at least `MIN_STOP_ATR` average true ranges beyond the entry zone (lib/resolve.ts
///     `bufferStop` puts it there; a name with no stored ATR cannot show it, so it is not published);
///   * a measured take profit on the call's side -- never a projection, whose reward:risk would be the
///     multiple it was projected at and so could never fail the test below;
///   * a reward:risk of at least `MIN_REWARD_RISK`, measured from the entry level against that stop;
///   * at least `MIN_CONFIRMATIONS` of the five independent confirmations.
///
/// The rest are named on the market page, folded, with the rule each one failed -- no direction and no
/// levels, because they are not signals -- so a reader can see what was withheld and why.
import type { Decision } from "./decision.ts";
import type { TargetLike } from "./target.ts";
import { STOP_BUFFER_ATR } from "./resolve.ts";

export const MIN_REWARD_RISK = 1.5;
export const MIN_CONFIRMATIONS = 1;
export const MIN_STOP_ATR = STOP_BUFFER_ATR;

export interface GateResult {
  published: boolean;
  /// Every rule the call failed, in reader's words. Empty when published.
  reasons: string[];
}

const ok = (v: number | null | undefined): v is number => v != null && Number.isFinite(v) && v > 0;

export function qualityGate(
  call: Pick<Decision, "action" | "entry" | "invalidation" | "legs">,
  target: TargetLike | null,
  atr: number | null | undefined,
): GateResult {
  const reasons: string[] = [];
  if (call.action !== "LONG" && call.action !== "SHORT") return { published: false, reasons: ["no direction"] };
  const long = call.action === "LONG";
  const entry = call.entry;
  const stop = call.invalidation;
  if (!entry || !ok(entry.low) || !ok(entry.high) || entry.low > entry.high) reasons.push("no entry range");
  if (!ok(stop)) reasons.push("no stop");
  if (!ok(atr)) {
    reasons.push("no average true range stored to set the stop by");
  } else if (entry && ok(stop)) {
    const beyond = long ? entry.low - stop : stop - entry.high;
    // 1e-6 relative: stops are rounded to eight significant digits.
    if (beyond < MIN_STOP_ATR * atr * (1 - 1e-6)) reasons.push(`stop within ${MIN_STOP_ATR} x ATR of the entry zone`);
  }
  if (!target) {
    reasons.push("no measured target");
  } else if (target.rewardRisk == null || !Number.isFinite(target.rewardRisk)) {
    reasons.push("no reward:risk");
  } else if (target.rewardRisk < MIN_REWARD_RISK) {
    reasons.push(`reward:risk ${target.rewardRisk.toFixed(1)}, under ${MIN_REWARD_RISK}`);
  }
  if ((call.legs?.length ?? 0) < MIN_CONFIRMATIONS) reasons.push("no confirmation");
  return { published: reasons.length === 0, reasons };
}

/// Whether the lists publish a scored row. One built without a gate (a test's hand-made row) is treated
/// as published; `scoreRows` always sets one.
export function isPublished(s: { gate?: GateResult }): boolean {
  return s.gate ? s.gate.published : true;
}
