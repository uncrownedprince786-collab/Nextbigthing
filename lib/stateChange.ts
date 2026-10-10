/// Did the verdict change since the last decision cycle, and what kind of change was it?
///
/// Read from the decision log, which stores every day's verdict and the gate that decided it, so a
/// change is a stored fact and its reason is the rule table's own -- not a description written after
/// the event. One function for the list rows and the asset page.
///
/// The kinds, in order of how much a reader holding the old call needs to know:
///   * REVERSED     a direction flipped (LONG to SHORT or back);
///   * INVALIDATED  a direction ended because price crossed its stop (`stop-crossed`);
///   * OVERRIDDEN   a direction ended because the macro gate refused it on the news (`macro-veto`);
///   * WITHDRAWN    a direction ended for another stated reason (a confirmation it needed fell away);
///   * NEW CALL     a WAIT became a direction.
/// The first three are warnings. The last two are changes worth seeing, not alarms.

export type ChangeKind = "REVERSED" | "INVALIDATED" | "OVERRIDDEN" | "WITHDRAWN" | "NEW CALL";

export interface StateChange {
  kind: ChangeKind;
  from: string;
  to: string;
  /// The decision cycle the change happened in, ISO day, UTC.
  on: string;
  /// Why, in the rule table's terms.
  reason: string;
  /// True for the three kinds a holder of the old call must not miss.
  warn: boolean;
}

const DIRECTIONS = new Set(["LONG", "SHORT"]);

/// The rule table's gate, said in words. A gate this map does not know is still said, generically.
const GATE_WORDS: Record<string, string> = {
  "stop-crossed": "price moved through the stop",
  "macro-veto": "the macro gate refused it on breaking news",
  "short-unbacked": "nothing independent confirms the short any more",
  incomplete: "the setup no longer reads a direction",
  "no-invalidation": "no stop level is stored any more",
  "no-prices": "no close is stored",
  stale: "the newest close is too old",
  "source-silent": "the price source went silent",
  long: "the setup turned up with its confirmations",
  short: "the setup turned down with its confirmations",
  "trend-long": "the trend turned up",
  "trend-short": "the trend turned down",
  "unconfirmed-long": "the setup turned up, with nothing yet confirming it",
  "unconfirmed-short": "the setup turned down, with nothing yet confirming it",
};

export function gateWords(gate: string | null | undefined): string {
  return (gate && GATE_WORDS[gate]) || "the rule table's reading changed";
}

function iso(d: Date | string | null | undefined): string | null {
  if (!d) return null;
  const t = d instanceof Date ? d.getTime() : Date.parse(String(d).slice(0, 10) + "T00:00:00Z");
  return Number.isFinite(t) ? new Date(t).toISOString().slice(0, 10) : null;
}

/// One change, from the verdict before it, the verdict after it and the gate that decided the after.
/// Null when nothing changed or there is nothing before to compare with.
export function classifyChange(
  prev: string | null | undefined,
  cur: string,
  gate: string | null | undefined,
  on: Date | string,
): StateChange | null {
  if (!prev || prev === cur) return null;
  const day = iso(on);
  if (!day) return null;
  let kind: ChangeKind;
  if (DIRECTIONS.has(prev) && DIRECTIONS.has(cur)) kind = "REVERSED";
  else if (DIRECTIONS.has(prev) && gate === "stop-crossed") kind = "INVALIDATED";
  else if (DIRECTIONS.has(prev) && gate === "macro-veto") kind = "OVERRIDDEN";
  else if (DIRECTIONS.has(prev)) kind = "WITHDRAWN";
  else if (DIRECTIONS.has(cur)) kind = "NEW CALL";
  else return null; // WAIT to WAIT under another gate is not a change of verdict
  return { kind, from: prev, to: cur, on: day, reason: gateWords(gate), warn: kind !== "WITHDRAWN" && kind !== "NEW CALL" };
}

/// The change a list row shows: only one made in the newest decision cycle, and only when the verdict
/// on the page is the one the log recorded (between a refresh and the nightly log the page can be a
/// cycle ahead, and a badge describing yesterday's change on a different verdict would be wrong).
export function latestChange(o: {
  action: string;
  runAction: string | null | undefined;
  runSince: Date | string | null | undefined;
  runPrev: string | null | undefined;
  runGate: string | null | undefined;
  latestCycle: Date | string | null | undefined;
}): StateChange | null {
  if (o.runAction !== o.action) return null;
  const since = iso(o.runSince);
  if (!since || since !== iso(o.latestCycle)) return null;
  return classifyChange(o.runPrev, o.action, o.runGate, since);
}

export interface Transition extends StateChange {
  /// The close each side of the change was read from, when the log stored one.
  fromClose: number | null;
  toClose: number | null;
  fromOn: string;
}

/// Every change in a run of logged days, oldest first, for the asset page's timeline.
export function changeTimeline(
  rows: { periodEnd: Date | string; action: string; gate: string | null; baseClose: number | null }[],
): Transition[] {
  const sorted = [...rows].sort((a, b) => (iso(a.periodEnd)! < iso(b.periodEnd)! ? -1 : 1));
  const out: Transition[] = [];
  for (let i = 1; i < sorted.length; i++) {
    const c = classifyChange(sorted[i - 1].action, sorted[i].action, sorted[i].gate, sorted[i].periodEnd);
    if (c) {
      out.push({ ...c, fromOn: iso(sorted[i - 1].periodEnd)!, fromClose: sorted[i - 1].baseClose, toClose: sorted[i].baseClose });
    }
  }
  return out;
}
