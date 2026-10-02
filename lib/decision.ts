// The decision rules, and nothing else.
//
// This module is deliberately pure: no database, no imports, no clock. Every input arrives in
// `DecisionInput` and `today` is passed in rather than read, so the whole rule table is testable
// without a connection and a run cannot change its answer between two reads of the same page.
// `lib/decisionInput.ts` is the only place allowed to turn stored rows into this shape.
//
// The order of the gates is the rule table. It is written as first-match-wins because the reader
// is owed one reason, not five: a stale close and a mixed horizon both end in WAIT, and saying
// "close is 9 days old" is useful where "mixed horizons, and also stale" is noise. The gates are
// therefore ordered by how much they disqualify everything after them.
//
//   order  gate                        answer   why the reader is told
//   1      no price series             WAIT     nothing is stored for this name
//   2      close older than the        WAIT     the number on the page is not today's number
//          market's own freshness rule
//   3      a source is silent          WAIT     the source that feeds this name answered nothing
//   4      no break level              WAIT     there is no level at which being wrong is known
//   5      setup and horizon disagree  WAIT     the two timeframes want opposite things
//   6      unusual move, thin news     WAIT     the move has no published reason yet
//   7      setup up, horizon not down  LONG
//   8      setup down, horizon not up  SHORT
//   9      anything left               WAIT     conditions are incomplete
//
// Gates 1-4 are data faults and name the missing thing. Gates 5-6 are genuine disagreement in the
// data and are not faults. Gate 9 exists because a rule table that falls through to LONG is how a
// panel ends up recommending a trade it has no reason for.

export type Action = "LONG" | "SHORT" | "WAIT";
export type TimeSense = "NOW" | "WAIT FOR LEVEL" | "CARE";
export type Confidence = "High" | "Medium" | "Low";
export type Direction = "up" | "down" | "flat" | "unknown";
export type Market = "US" | "PSX" | "Crypto" | "Other";

/// How old a close may be before the panel refuses to act on it, per market, in calendar days.
///
/// Calendar days rather than trading days because the question is "is the number on this page
/// today's number", which a reader asks on a Sunday too. Crypto trades every day, so two days is
/// already a fault. US equities allow a Friday close to be read on the following Monday. PSX gets
/// one more day because it keeps more holidays, and a holiday must not read as a dead feed.
export const STALE_AFTER_DAYS: Record<Market, number> = {
  Crypto: 2,
  US: 5,
  PSX: 6,
  Other: 5,
};

/// Below this many recent stories, news counts as thin. Thin news is only a gate when the price
/// also moved unusually: a quiet name with no news is normal, a 9% move with no news is not.
///
/// 8 is not a new number: it is `MIN_ITEMS` in jobs/human.py, which is the job that decides what
/// counts as thin in the first place. lib/plain.ts carried a copy called `THIN_STORIES` until the
/// simple-read builders that used it were deleted. A second threshold for one idea is how two
/// parts of a page come to disagree about whether a name is covered, so this points at the job.
export const THIN_NEWS_BELOW = 8;

/// A dated event this close is worth a CARE, because a position opened today meets it.
export const EVENT_SOON_DAYS = 3;

/// Fewer stored analogs than this and the outcome range is not worth quoting as a range.
export const ANALOGS_MIN = 3;

export interface DecisionInput {
  symbol: string;
  market: Market;
  /// Newest stored close, ISO `yyyy-mm-dd`, or null when nothing is stored at all.
  asOf: string | null;
  /// Injected, never read from the clock, so the same row always decides the same way.
  today: string;
  lastClose: number | null;
  /// Direction of the swing or longer setup, and the horizon it was measured over.
  setup: { direction: Direction; horizon: string | null } | null;
  /// The longer-term reading, which may agree, disagree, or be flat.
  horizon: { direction: Direction } | null;
  /// Measured entry band. Both numbers inclusive, low <= high.
  entry: { low: number; high: number } | null;
  /// The level at which the setup is wrong. Without one there is no trade, only a hope.
  invalidation: number | null;
  /// What followed similar past days, as percentages.
  analogs: { count: number; lowPct: number | null; highPct: number | null } | null;
  unusualMove: boolean;
  /// null means news was never checked, which is different from checked and found none.
  newsCount: number | null;
  /// Days until the next dated event, or null when none is stored.
  eventInDays: number | null;
  /// Name of a source that answered nothing for this asset, when one did.
  sourceSilent: string | null;
}

export interface Decision {
  action: Action;
  /// At most two short lines, plain words.
  why: string[];
  entry: { low: number; high: number } | null;
  invalidation: number | null;
  timeSense: TimeSense;
  confidence: Confidence;
  /// Exactly what is missing, when something is. Never empty while the action is WAIT for a data
  /// reason, because "WAIT" with no reason is the silent empty this panel exists to end.
  missing: string[];
  /// The honesty line the reader sees under the decision.
  measured: string;
  /// Which gate decided, for the audit page and for tests. Not shown to the reader.
  gate: string;
}

function daysBetween(fromISO: string, toISO: string): number {
  const a = Date.parse(fromISO + "T00:00:00Z");
  const b = Date.parse(toISO + "T00:00:00Z");
  if (Number.isNaN(a) || Number.isNaN(b)) return Number.NaN;
  return Math.round((b - a) / 86_400_000);
}

function pct(n: number): string {
  const s = n >= 0 ? "+" : "";
  return `${s}${n.toFixed(1)}%`;
}

/// The line under every decision. A range is only quoted when enough analogs back it.
function measuredLine(input: DecisionInput): string {
  const a = input.analogs;
  const head = "Measured, not guaranteed.";
  if (!a || a.count < ANALOGS_MIN || a.lowPct === null || a.highPct === null) {
    return `${head} Not enough similar past days stored to quote a range yet.`;
  }
  return `${head} Past similar days range: ${pct(a.lowPct)} to ${pct(a.highPct)}.`;
}

/// NOW only when the price is actually in the band. Otherwise the honest answer is that the reader
/// is waiting for a level, which is a different instruction from "buy now".
function timeSenseFor(input: DecisionInput, action: Action): TimeSense {
  if (input.eventInDays !== null && input.eventInDays <= EVENT_SOON_DAYS) return "CARE";
  if (action === "WAIT") return "WAIT FOR LEVEL";
  const { entry, lastClose } = input;
  if (!entry || lastClose === null) return "WAIT FOR LEVEL";
  return lastClose >= entry.low && lastClose <= entry.high ? "NOW" : "WAIT FOR LEVEL";
}

/// Confidence counts what is weak rather than scoring what is strong, because every weakness here
/// is a reason a reader could lose money and none of them cancel out.
function confidenceFor(input: DecisionInput, action: Action): Confidence {
  if (action === "WAIT") return "Low";
  let weak = 0;
  const agrees = Boolean(
    input.setup && input.horizon && input.setup.direction === input.horizon.direction,
  );
  if (!agrees) weak += 1;
  if (!input.analogs || input.analogs.count < ANALOGS_MIN) weak += 1;
  if (input.newsCount === null || input.newsCount < THIN_NEWS_BELOW) weak += 1;
  if (!input.entry) weak += 1;
  if (weak === 0) return "High";
  if (weak === 1) return "Medium";
  return "Low";
}

/// The second why line: what the longer view adds, said accurately.
///
/// "Longer view does not disagree" was doing duty for three different situations, one of which is
/// that there is no longer view at all. A reader told a second timeframe does not disagree will
/// hear corroboration; when the truth is that nothing was there to agree or disagree, that is the
/// panel overstating its own evidence in the one line meant to qualify it.
function secondLine(setup: Direction, horizon: Direction): string {
  if (horizon === setup) return "Longer view agrees.";
  if (horizon === "unknown") return "Only one horizon is directional, so nothing confirms it.";
  if (horizon === "flat") return "Longer view is flat.";
  return "Longer view does not disagree.";
}

function wait(input: DecisionInput, gate: string, why: string[], missing: string[]): Decision {
  return {
    action: "WAIT",
    why: why.slice(0, 2),
    entry: input.entry,
    invalidation: input.invalidation,
    timeSense: timeSenseFor(input, "WAIT"),
    confidence: "Low",
    missing,
    measured: measuredLine(input),
    gate,
  };
}

export function decide(input: DecisionInput): Decision {
  // 1. Nothing stored. The reader gets the name of what is absent, not an empty panel.
  if (input.asOf === null || input.lastClose === null) {
    return wait(input, "no-prices", [`No stored prices for ${input.symbol}.`], [
      `No price series stored for ${input.symbol}.`,
    ]);
  }

  // 2. Stale beyond this market's own rule. Acting on an old close is the one failure a price
  //    panel must never commit, so this gate sits above every signal.
  const age = daysBetween(input.asOf, input.today);
  const limit = STALE_AFTER_DAYS[input.market];
  if (Number.isNaN(age)) {
    return wait(input, "bad-date", ["Stored date cannot be read."], [
      `Newest close date for ${input.symbol} is not a readable date.`,
    ]);
  }
  if (age > limit) {
    return wait(
      input,
      "stale",
      [`Data stale: newest close ${input.asOf}, ${age} days old.`],
      [`Close for ${input.symbol} is ${age} days old; this market allows ${limit}.`],
    );
  }

  // 3. A silent source. Named, because "no data" and "Binance answered nothing" send the reader to
  //    two different places.
  if (input.sourceSilent) {
    return wait(input, "source-silent", [`${input.sourceSilent} answered nothing.`], [
      `${input.sourceSilent} returned no rows on the last run.`,
    ]);
  }

  // 4. No break level. Without one there is nothing to be wrong against, and an action with no
  //    invalidation is the kind this panel refuses to print.
  if (input.invalidation === null) {
    return wait(input, "no-invalidation", ["No break level computed yet."], [
      `No invalidation level stored for ${input.symbol}.`,
    ]);
  }

  const setup = input.setup?.direction ?? "unknown";
  const horizon = input.horizon?.direction ?? "unknown";

  // 5. The two timeframes want opposite things. Not a fault in the data — a real disagreement, and
  //    the reader is told which way each one points.
  if ((setup === "up" && horizon === "down") || (setup === "down" && horizon === "up")) {
    return wait(
      input,
      "mixed-horizons",
      [`Mixed horizons: setup is ${setup}, longer view is ${horizon}.`],
      [],
    );
  }

  // 6. A move with no published reason. Thin news alone is normal; thin news under an unusual move
  //    means the cause is not in yet.
  const newsThin = input.newsCount === null || input.newsCount < THIN_NEWS_BELOW;
  if (input.unusualMove && newsThin) {
    const line =
      input.newsCount === null ? "Unusual move and news not checked." : "Unusual move and news thin.";
    return wait(input, "unexplained-move", [line, "No published reason for the move yet."], []);
  }

  // 7 and 8. A direction, with a level to be wrong at.
  if (setup === "up" && horizon !== "down") {
    return {
      action: "LONG",
      why: [
        `Setup is up${input.setup?.horizon ? ` on the ${input.setup.horizon} view` : ""}.`,
        secondLine("up", horizon),
      ],
      entry: input.entry,
      invalidation: input.invalidation,
      timeSense: timeSenseFor(input, "LONG"),
      confidence: confidenceFor(input, "LONG"),
      missing: input.entry ? [] : ["No measured entry band stored; only the break level is set."],
      measured: measuredLine(input),
      gate: "long",
    };
  }
  if (setup === "down" && horizon !== "up") {
    return {
      action: "SHORT",
      why: [
        `Setup is down${input.setup?.horizon ? ` on the ${input.setup.horizon} view` : ""}.`,
        secondLine("down", horizon),
      ],
      entry: input.entry,
      invalidation: input.invalidation,
      timeSense: timeSenseFor(input, "SHORT"),
      confidence: confidenceFor(input, "SHORT"),
      missing: input.entry ? [] : ["No measured entry band stored; only the break level is set."],
      measured: measuredLine(input),
      gate: "short",
    };
  }

  // 9. Nothing fired. Falling through to a direction here is how a panel recommends a trade it has
  //    no reason for, so the fall-through is WAIT and it says which part is absent.
  const absent: string[] = [];
  if (setup === "unknown") absent.push(`No setup direction stored for ${input.symbol}.`);
  if (horizon === "unknown") absent.push(`No longer-term reading stored for ${input.symbol}.`);
  return wait(
    input,
    "incomplete",
    [setup === "flat" ? "Setup is flat." : "Conditions incomplete.", "No direction to act on."],
    absent,
  );
}
