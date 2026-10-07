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
//   7      peers argue the other way   WAIT     the name is being carried, not leading
//   8      setup up, horizon not down  LONG
//   9      setup down, horizon not up  SHORT
//  10      anything left               WAIT     conditions are incomplete
//
// A dated event is NOT a gate. It is an overlay: it sets the time sense to CARE and is printed,
// and it can turn a weak direction into a WAIT, but it never produces one. A calendar row is a
// risk to size, not a reason to buy, and a rule table that lets earnings generate a LONG is the
// junk-brain failure this file exists to avoid.
//
// Confirmation sits inside gates 8 and 9 rather than above them. A direction with a level is the
// minimum; volume at or above its own average, or an analog set that leans the same way, is what
// separates High from Medium. When neither is stored the direction still prints — with the
// confirmation named as missing — because refusing every name for want of a factor nobody has
// computed yet is how a rule table ends up answering WAIT 160 times out of 160.
//
// Gates 1-4 are data faults and name the missing thing. Gates 5-6 are genuine disagreement in the
// data and are not faults. Gate 9 exists because a rule table that falls through to LONG is how a
// panel ends up recommending a trade it has no reason for.

import type { TrendDirection } from "./setupConditions";

export type Action = "LONG" | "SHORT" | "WAIT";
export type TimeSense = "NOW" | "WAIT FOR LEVEL" | "CARE";
export type Confidence = "High" | "Medium" | "Low";

/// Strongest evidence first. Lives here beside the type it orders rather than in the page
/// layer, so any module that can read a `Confidence` can also sort by one without pulling in
/// the web layer's imports.
export const CONFIDENCE_ORDER: Record<Confidence, number> = { High: 0, Medium: 1, Low: 2 };
export type Direction = "up" | "down" | "flat" | "unknown";
export type Market = "US" | "PSX" | "Crypto" | "FX" | "Commodity" | "Other";

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
  // FX trades continuously from Sunday evening to Friday evening, so it keeps no exchange
  // holidays of its own -- but the daily bars come from Yahoo, which stamps one bar per
  // weekday and none at the weekend. 4 is therefore the tightest honest figure: a Friday bar
  // read on the following Tuesday is 4 days old and the market was open for one of them.
  // Tighter than US because an FX pair has no earnings halt, no suspension and no delisting to
  // explain a missing day -- a gap here is the feed, not the instrument.
  FX: 4,
  // Futures. The CME and ICE contracts here trade almost around the clock from Sunday evening
  // to Friday evening and settle once a day, so the daily bar is a weekday bar with the same
  // weekend hole an equity has -- a Friday settle read on the following Monday is 3 days old and
  // nothing was open for two of them. 5 for the same reason US equities get 5, and not tighter:
  // these venues keep the US holiday calendar, so a Thanksgiving or a Good Friday must not read
  // as a dead feed. Not looser either: unlike an equity a front-month future has no suspension
  // and no delisting to explain a missing day, and the contract itself rolls rather than stops.
  //
  // One consequence of "around the clock" that is worth stating, because it looks like a lag and
  // is not. Measured 2026-10-07 on GC=F, Yahoo reports the session as **04:00 UTC to 03:59 UTC
  // the following day** -- so a contract's bar for day D is not a finished session until the
  // morning of D+1, and `forming_sessions` correctly refuses to store it before then. The
  // decision lane runs at 22:10, so a commodity is normally read from the previous day's settle
  // where an equity is read from today's. That is the same rule 41 trade every other market
  // makes, arriving a day wider because the session is a day wide: the choice is between
  // yesterday's real settle and today's unfinished one. 5 days of allowance absorbs it with room,
  // which is part of why it is not tighter.
  Commodity: 5,
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

/// Volume at or above this multiple of its own 20-session average counts as confirming a move.
///
/// 1.2 is not a new number: it is where `tradingWords` in lib/plain.ts starts calling a session
/// busier than usual. A move on ordinary volume is drift; the same move on heavier volume is
/// people acting, and the difference is the cheapest confirmation available from stored data.
export const VOLUME_CONFIRMS_AT = 1.2;

/// Fewer matched past days than this and the analog set cannot confirm anything.
///
/// 8 is `MIN_MATCHES_LOW` in jobs/analogs.py, the floor below which that job refuses to grade a
/// set at all. Confirming a trade on seven past days would be using a number its own producer
/// declines to stand behind.
export const ANALOGS_CONFIRM_MIN = 8;

/// How far behind its peers a name may be, in percentage points over 20 sessions, before the
/// peer reading counts as arguing against a LONG.
///
/// Relative strength is the one factor that can contradict a rising price: a name up 4% while
/// its industry is up 10% is a laggard being carried, and the absolute return cannot say so.
/// The band is symmetric and deliberately wide, because peer medians over small groups are
/// noisy and this gate only exists to catch the clear cases.
export const REL_AGAINST_AT = 3;

export interface DecisionInput {
  symbol: string;
  market: Market;
  /// Newest stored close, ISO `yyyy-mm-dd`, or null when nothing is stored at all.
  asOf: string | null;
  /// Injected, never read from the clock, so the same row always decides the same way.
  today: string;
  lastClose: number | null;
  /// Direction of the swing or longer setup, and the horizon it was measured over.
  ///
  /// `trend` is the verdict `jobs/setup.py` recorded on the trend condition, read out of the
  /// stored `conditions` string by `lib/setupConditions.ts`. It is what `direction` is not: when
  /// the state is `wait`, `direction` is "flat" — the direction was measured and withheld — and
  /// `trend` is the direction that was withheld. Null when the row carries no trend verdict.
  setup: {
    direction: Direction;
    horizon: string | null;
    trend?: TrendDirection | null;
  } | null;
  /// The longer-term reading, which may agree, disagree, or be flat.
  horizon: { direction: Direction } | null;
  /// Measured entry band. Both numbers inclusive, low <= high.
  entry: { low: number; high: number } | null;
  /// The level at which the setup is wrong. Without one there is no trade, only a hope.
  invalidation: number | null;
  /// What followed similar past days, as percentages.
  analogs: {
    count: number;
    lowPct: number | null;
    highPct: number | null;
    /// The middle outcome, and how many of the matched days rose. Together they say whether the
    /// set leaned, which a range alone cannot: -20% to +22% is the same range whether nine days
    /// in ten rose or one did.
    medianPct?: number | null;
    positive?: number | null;
  } | null;
  /// Volume as a multiple of its own 20-session average, or null when none is published.
  volumeRatio?: number | null;
  /// 20-session return minus the peer median, in percentage points. Null when too few peers.
  relStrength?: number | null;
  unusualMove: boolean;
  /// null means news was never checked, which is different from checked and found none.
  newsCount: number | null;
  /// Days until the next dated event, or null when none is stored.
  eventInDays: number | null;
  /// Name of a source that answered nothing for this asset, when one did.
  sourceSilent: string | null;
}

/// A direction the data shows and the rules will not act on yet, with what is standing in the way.
///
/// This is the "before it is obvious" half of the panel, and it is deliberately not an action.
/// `jobs/setup.py` writes state `wait` when **the trend is clear and not all the conditions behind
/// it are present** — 162 of 266 rows on 2026-10-07, of which 101 fail on one leg, volume. Those
/// names reach the reader today as the twelfth to the hundred-and-sixtieth entry of a WAIT list
/// ordered by data faults, which is the same as not reaching them at all.
///
/// Nothing here is new arithmetic. The direction is the trend verdict `setup.py` already stored,
/// and `shortfall` is the stored factor next to the threshold it has to clear. It cannot be a
/// LONG: the confirmations genuinely are not there, and promoting it would be inventing them —
/// which is the one thing this file exists not to do. What changes is that the reader is told a
/// direction is forming, which way, and exactly what would confirm it.
export interface Developing {
  /// Which way the stored trend points. Never "mixed": a mixed trend is not a developing anything.
  direction: "up" | "down";
  /// What this would be if the missing confirmations arrived.
  would: "LONG" | "SHORT";
  /// Each confirmation that is absent or failing, in plain words, with its stored value.
  waitingOn: string[];
  /// How far the nearest measurable confirmation is from its threshold, as a ratio of the
  /// threshold, or null when nothing missing is measurable. 0.92 means 8% short of it.
  ///
  /// This is the ordering key, and ordering is the entire point of the list: a name at 1.15x of
  /// the 1.2x volume gate is a different proposition from one at 0.3x, and sorted together they
  /// are indistinguishable. Null sorts last, because "not measurable" is not "nearly there".
  closeness: number | null;
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
  /// A direction forming behind an incomplete set of conditions. Null unless that is the state.
  ///
  /// Only ever set alongside `action: "WAIT"`, and a reader must never see it as a verdict. It is
  /// set at the fall-through gate and nowhere else: a name held back by a stale close or a silent
  /// source is not developing, it is unmeasured, and a name held back by peers arguing the other
  /// way has already been given its reason.
  developing: Developing | null;
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

/// Confidence is how much independently confirms the direction, not how it feels.
///
/// Three things can confirm, and they are independent of each other: a second timeframe
/// pointing the same way, volume at or above its own average, and a set of similar past days
/// that leaned the same way. Two or more is High, exactly one is Medium, none is Low. WAIT is
/// always Low, because a refusal is not a confident anything.
///
/// Counting confirmations rather than deducting for weaknesses matters when a factor is simply
/// absent: a name with no published volume is not thereby a worse trade, it is one with less
/// evidence, and it lands at Medium rather than being punished down to Low twice over.
function confidenceFor(input: DecisionInput, action: Action): Confidence {
  if (action === "WAIT") return "Low";
  const direction = action === "LONG" ? "up" : "down";
  const agrees = Boolean(
    input.setup && input.horizon && input.setup.direction === input.horizon.direction,
  );
  const confirmations = [agrees, volumeConfirms(input) === true, analogConfirms(input, direction) === true]
    .filter(Boolean).length;
  if (confirmations >= 2) return "High";
  if (confirmations === 1) return "Medium";
  return "Low";
}

/// The third why line: what confirmed the direction, or that nothing did.
///
/// Printed even when nothing confirms, which is the point. A LONG with no volume and no analog
/// behind it is still the best reading of what is stored, and a reader is entitled to know it is
/// resting on the setup alone rather than discovering that later.
function confirmLine(input: DecisionInput, direction: "up" | "down"): string {
  const vol = volumeConfirms(input);
  const analog = analogConfirms(input, direction);
  const parts: string[] = [];
  if (vol === true && input.volumeRatio) {
    parts.push(`volume ${input.volumeRatio.toFixed(1)}x its average`);
  }
  if (analog === true && input.analogs) {
    const a = input.analogs;
    const moved = direction === "up" ? a.positive : (a.count - (a.positive ?? 0));
    // "going", not "went": this clause has to read correctly both on its own and joined
    // after the volume one. Live on the page as "Confirmed by 21 of 31 similar days went
    // the same way." whenever volume did not also confirm -- which is most of them.
    parts.push(`${moved} of ${a.count} similar days going the same way`);
  }
  if (parts.length) return `Confirmed by ${parts.join(" and ")}.`;
  if (vol === false && analog === false) return "Neither volume nor similar days confirm it.";
  return "Nothing further confirms it yet.";
}

/// What could have confirmed the direction and was not stored. Reported as missing rather than
/// silently treated as a negative.
function confirmMissing(input: DecisionInput, direction: "up" | "down"): string[] {
  const out: string[] = [];
  if (volumeConfirms(input) === null) out.push("No volume published, so the move is unconfirmed by activity.");
  if (analogConfirms(input, direction) === null) {
    // Three different absences, and they were all being reported as the first one. A name with
    // 375 matched days whose lean was not stored printed "Only 375 similar past days stored; 8
    // are needed to confirm", which is not true of 375 and tells the reader to wait for
    // something that already happened. Seen live on ABBV.
    const a = input.analogs;
    const n = a?.count ?? 0;
    if (!a || n === 0) {
      out.push("No similar past days stored, so nothing measures what usually followed.");
    } else if (n < ANALOGS_CONFIRM_MIN) {
      out.push(`Only ${n} similar past days stored; ${ANALOGS_CONFIRM_MIN} are needed to confirm.`);
    } else {
      out.push(
        `${n} similar past days are stored, but which way they went was not recorded, so they cannot confirm the direction.`,
      );
    }
  }
  return out;
}

/// Does volume back the move? A null ratio is "not published", which is not the same as "no".
function volumeConfirms(input: DecisionInput): boolean | null {
  const v = input.volumeRatio;
  return v === null || v === undefined ? null : v >= VOLUME_CONFIRMS_AT;
}

/// Does the analog set lean the way the setup points?
///
/// Both halves are required: a majority of matched days moving the right way, and a middle
/// outcome with the right sign. A set where six of ten rose but the median is negative is a set
/// where the four losses were larger, and calling that confirmation would be reading the count
/// and ignoring the size.
function analogConfirms(input: DecisionInput, direction: "up" | "down"): boolean | null {
  const a = input.analogs;
  if (!a || a.count < ANALOGS_CONFIRM_MIN) return null;
  if (a.positive === null || a.positive === undefined) return null;
  if (a.medianPct === null || a.medianPct === undefined) return null;
  const share = a.positive / a.count;
  return direction === "up" ? share > 0.5 && a.medianPct > 0 : share < 0.5 && a.medianPct < 0;
}

/// The second why line: what the longer view adds, said accurately.
///
/// "Longer view does not disagree" was doing duty for three different situations, one of which is
/// that there is no longer view at all. A reader told a second timeframe does not disagree will
/// hear corroboration; when the truth is that nothing was there to agree or disagree, that is the
/// panel overstating its own evidence in the one line meant to qualify it.
function secondLine(setup: Direction, horizon: Direction): string {
  if (horizon === setup) return "Longer view agrees.";
  if (horizon === "unknown") return "Only one time frame points anywhere, so nothing confirms it.";
  if (horizon === "flat") return "Longer view is flat.";
  return "Longer view does not disagree.";
}

function wait(
  input: DecisionInput,
  gate: string,
  why: string[],
  missing: string[],
  developing: Developing | null = null,
): Decision {
  return {
    action: "WAIT",
    why: why.slice(0, 3),
    entry: input.entry,
    invalidation: input.invalidation,
    timeSense: timeSenseFor(input, "WAIT"),
    confidence: "Low",
    missing,
    measured: measuredLine(input),
    gate,
    developing,
  };
}

/// The developing read, or null when nothing is forming.
///
/// Built from three facts already in the input and no new arithmetic: the withheld trend
/// direction, the stored volume ratio against `VOLUME_CONFIRMS_AT`, and the stored analog lean.
/// Each absent confirmation is named with its own value, so "waiting on volume" never stands in
/// for "there is no volume published" — rule 21, three values and not one.
function developingRead(input: DecisionInput): Developing | null {
  const trend = input.setup?.trend ?? null;
  if (trend !== "up" && trend !== "down") return null;

  const waitingOn: string[] = [];
  const distances: number[] = [];

  const vol = input.volumeRatio;
  if (vol === null || vol === undefined) {
    // Not a shortfall and not progress towards one. An FX pair has no consolidated tape at all,
    // so this is a fact about the instrument rather than a quiet session.
    waitingOn.push("No volume is published for this name, so activity cannot confirm it.");
  } else if (vol < VOLUME_CONFIRMS_AT) {
    waitingOn.push(
      `Volume is ${vol.toFixed(2)}x its own 20-session average; ${VOLUME_CONFIRMS_AT}x would confirm.`,
    );
    distances.push(vol / VOLUME_CONFIRMS_AT);
  }

  const analog = analogConfirms(input, trend);
  if (analog === null) {
    const n = input.analogs?.count ?? 0;
    waitingOn.push(
      n >= ANALOGS_CONFIRM_MIN
        ? `${n} similar past days are stored but their lean was not recorded.`
        : `Only ${n} similar past days are stored; ${ANALOGS_CONFIRM_MIN} are needed.`,
    );
    if (n > 0 && n < ANALOGS_CONFIRM_MIN) distances.push(n / ANALOGS_CONFIRM_MIN);
  } else if (analog === false) {
    waitingOn.push("Similar past days lean the other way.");
  }

  const rel = input.relStrength;
  if (rel === null || rel === undefined) {
    waitingOn.push("No peer comparison stored, so relative strength cannot confirm it.");
  } else if ((trend === "up" && rel < 0) || (trend === "down" && rel > 0)) {
    waitingOn.push(
      `It is ${Math.abs(rel).toFixed(1)} points ${trend === "up" ? "behind" : "ahead of"} its peers over 20 sessions.`,
    );
  }

  // Everything present and agreeing is not a developing read -- it is a row `jobs/setup.py` held
  // back for a condition this rule table does not score, and saying "waiting on nothing" would
  // be the panel claiming to know why when it does not.
  if (!waitingOn.length) return null;

  return {
    direction: trend,
    would: trend === "up" ? "LONG" : "SHORT",
    waitingOn,
    closeness: distances.length ? Math.max(...distances) : null,
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

  // 7. The peers argue the other way. A name up while its industry is up far more is being
  //    carried by the group, and buying it is buying the group at a worse price. Only the clear
  //    cases are caught: the band is wide because a peer median over a small group is noisy, and
  //    a null relative reading is no evidence rather than evidence of agreement.
  const rel = input.relStrength;
  if (rel !== null && rel !== undefined) {
    if (setup === "up" && rel <= -REL_AGAINST_AT) {
      return wait(
        input,
        "peers-against",
        [
          `Setup is up but the name is ${Math.abs(rel).toFixed(1)} points behind its peers.`,
          "It is being carried rather than leading.",
        ],
        [],
      );
    }
    if (setup === "down" && rel >= REL_AGAINST_AT) {
      return wait(
        input,
        "peers-against",
        [
          `Setup is down but the name is ${rel.toFixed(1)} points ahead of its peers.`,
          "It is holding up better than the group it trades with.",
        ],
        [],
      );
    }
  }

  // 8 and 9. A direction, with a level to be wrong at, and whatever confirms it.
  if (setup === "up" && horizon !== "down") {
    return {
      action: "LONG",
      why: [
        `Setup is up${input.setup?.horizon ? ` on the ${input.setup.horizon} view` : ""}.`,
        secondLine("up", horizon),
        confirmLine(input, "up"),
      ],
      entry: input.entry,
      invalidation: input.invalidation,
      timeSense: timeSenseFor(input, "LONG"),
      confidence: confidenceFor(input, "LONG"),
      missing: [
        ...(input.entry ? [] : ["No measured entry band stored; only the break level is set."]),
        ...confirmMissing(input, "up"),
      ],
      measured: measuredLine(input),
      gate: "long",
      // A printed direction is not developing; it has arrived.
      developing: null,
    };
  }
  if (setup === "down" && horizon !== "up") {
    return {
      action: "SHORT",
      why: [
        `Setup is down${input.setup?.horizon ? ` on the ${input.setup.horizon} view` : ""}.`,
        secondLine("down", horizon),
        confirmLine(input, "down"),
      ],
      entry: input.entry,
      invalidation: input.invalidation,
      timeSense: timeSenseFor(input, "SHORT"),
      confidence: confidenceFor(input, "SHORT"),
      missing: [
        ...(input.entry ? [] : ["No measured entry band stored; only the break level is set."]),
        ...confirmMissing(input, "down"),
      ],
      measured: measuredLine(input),
      gate: "short",
      // A printed direction is not developing; it has arrived.
      developing: null,
    };
  }

  // 9. Nothing fired. Falling through to a direction here is how a panel recommends a trade it has
  //    no reason for, so the fall-through is WAIT and it says which part is absent.
  // "Stored" and "stored, and says it found no direction" are two different states, and this
  // list used to print the first sentence for both. `horizon` is `"unknown"` either when no row
  // exists or when a row exists whose state is `none`, because `?? "unknown"` collapses the null
  // into the same word `directionOfState` returns. Only the input itself still knows which.
  //
  // Live on btc-bitcoin: the page read "No longer-term reading stored for btc-bitcoin" while a
  // `longer` row sat in the table carrying a headline, an entry and a stop — its state was
  // `none`, meaning price is between its long averages. Telling a reader a measurement is
  // missing, when it was taken and came back without a direction, is the same class of error as
  // calling a withheld direction flat: it understates how much is actually known.
  const absent: string[] = [];
  if (setup === "unknown") {
    absent.push(
      input.setup
        ? `The setup for ${input.symbol} records no direction.`
        : `No setup direction stored for ${input.symbol}.`,
    );
  }
  if (horizon === "unknown") {
    absent.push(
      input.horizon
        ? `The longer-term reading for ${input.symbol} records no direction.`
        : `No longer-term reading stored for ${input.symbol}.`,
    );
  }

  // "Setup is flat" was the wrong sentence, and it was wrong in the direction that matters.
  //
  // `directionOfState` maps `AssetSetup.state` to a direction, and only `wait` becomes `flat`.
  // But `wait` is not the neutral state in `jobs/setup.py` — it is the state where **the trend is
  // clear and the conditions behind it are not all present**, and its stored headline says so in
  // those words. The neutral state is `none`, "price is between its averages", which maps to
  // `unknown`. So `flat` here means a direction was measured and withheld, and printing "Setup is
  // flat" threw away the one thing the reader was owed.
  //
  // This is what made crypto look like an unexplained permanent WAIT. All ten stored coins carry
  // a `wait` swing row with an upward trend; every asset page said "Setup is flat. No direction to
  // act on." The verdict was right — the volume leg genuinely fails, see rule 39 — and the reason
  // given for it described a different market.
  //
  // The direction is still not acted on, and that is deliberate: `setup.py` withheld it because
  // its conditions failed, and turning it into a LONG here would be inventing the confirmation it
  // could not find. What changes is only that the reader is told which of the two situations they
  // are in. Which condition failed is already stored in the setup's own headline and printed
  // under Details.
  // The withheld direction, named. This is the one gate where a developing read belongs: the
  // conditions are incomplete, which is exactly what "forming" means, and every gate above
  // either found a data fault or found a reason that argues against the direction.
  const developing = developingRead(input);

  return wait(
    input,
    "incomplete",
    developing
      ? [
          `A ${developing.direction === "up" ? "rising" : "falling"} trend is in place, so this is a potential ${developing.would}.`,
          `Not acted on yet: ${developing.waitingOn[0]}`,
        ]
      : setup === "flat"
        ? [
            "A direction is showing, but not all the conditions behind it are present.",
            "So nothing is acted on yet.",
          ]
        : ["There is no clear direction to measure.", "Price is between its own averages."],
    absent,
    developing,
  );
}
