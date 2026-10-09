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
//   5      setup is up                 LONG     the direction the setup states
//   6      setup is down               SHORT    the direction the setup states
//   7      a withheld trend, or the    LONG     the direction is measured and its other
//          side the averages sit on    SHORT    conditions are not all present
//   8      anything left               WAIT     no direction was measured at all
//
// **News is a veto on gate 8 and a deduction everywhere else.** An analog set answers "what
// followed past days that looked like this one" on price, volume and the five-day return — and
// none of those past days had today's headline in it. So when `jobs/human.py` publishes a tone
// that points the opposite way, the matched days stop counting as confirmation: they are a
// sample missing the thing most likely to drive the next move. The direction still prints at
// gates 6 and 7, because there `jobs/setup.py` found and confirmed its conditions and a word
// list over headlines does not get to overrule that. At gate 8 the conditions did *not* all
// hold, so a thin case pointing one way against coverage pointing the other is refused and the
// name keeps its developing read with the coverage named as what stands in the way.
//
// The asymmetry is deliberate: coverage can take evidence away and can never add any. An
// agreeing tone is not a fourth confirmation and cannot lift a grade, because principle 5 says
// current human attention is context and not proof, and a word list with no bodies, no negation
// and no sarcasm is good enough to withdraw a claim and not good enough to make one.
//
// **What stopped being a gate, and why.** Two refusals used to sit between gate 5 and a
// direction: an unusual move with thin news, and peers moving the other way. Both are now
// printed as notes on the direction instead of replacing it. Measured against the live table on
// 2026-10-09, they were answering WAIT for 75 of 477 names — 60 and 15 — every one of which had
// a measured direction and a level to be wrong at.
//
// The case against them as gates is that neither is evidence about direction. Thin news under a
// move says the published explanation has not arrived; it does not say the move is wrong, and a
// rule table that refuses every unexplained move refuses exactly the moves that happen before
// the reason is public. A name lagging its peers is a real and often decisive fact — principle 2
// — but it is a fact about *relative* return, and vetoing an absolute direction with it discards
// the direction rather than qualifying it. Both are now in `notes`, both are printed, and
// peers-against still costs a confidence step so no grade outruns the note beside it (rule 6).
//
// **What a measured reward buys.** Gate 5 and gate 8 both read `rewardRisk`, which
// `jobs/horizons.py` computes from the setup's own target range against its own invalidation and
// refuses to write without one. A disagreement between timeframes is bypassed, and a withheld
// trend is carried, when that figure reaches `ASYMMETRY_CLEARS`. This is not new arithmetic in
// the web layer; it is one stored column read at one threshold.
//
// A dated event is NOT a gate. It is an overlay: it sets the time sense to CARE and is printed,
// and it can turn a weak direction into a WAIT, but it never produces one. A calendar row is a
// risk to size, not a reason to buy, and a rule table that lets earnings generate a LONG is the
// junk-brain failure this file exists to avoid.
//
// Confirmation sits inside gates 6 and 7 rather than above them. A direction with a level is the
// minimum; volume at or above its own average, an analog set that leans the same way, or the name
// beating the group it trades with is what separates High from Medium. When none is stored the
// direction still prints — with the confirmation named as missing — because refusing every name
// for want of a factor nobody has computed yet is how a rule table ends up answering WAIT 160
// times out of 160.
//
// **Not every instrument can supply every leg, and that is a fact about the instrument.** A
// currency pair has no consolidated tape, so `volumeRatio` is null for all 27 of them and always
// will be — and `jobs/analogs.py` matches on a volume ratio, so until it learned to match without
// one those same 27 had no stored analog either. Two of the four legs structurally absent is why
// 24 of 27 pairs sat in WAIT while every input table was fresh. The answer is never to invent the
// missing leg or to borrow one from an index; it is to count the legs the instrument actually
// has, and to say which ones it cannot have.
//
// Gates 1-4 are data faults and name the missing thing. Gate 5 is genuine disagreement in the
// data and is not a fault. Gate 9 exists because a rule table that falls through to LONG is how a
// panel ends up recommending a trade it has no reason for.
//
// Gates 1-4 are deliberately untouched by the conviction pass above, and gate 4 most of all. A
// stale close, a silent venue and a missing invalidation are not timidity: they are the absence
// of the three things a sniper entry is made of. A plan with no level to be wrong at is the one
// output this file must never print, and demanding an exact invalidation is what makes every
// reward figure below a measurement rather than a hope.

import type { TrendDirection } from "./setupConditions";

export type Action = "LONG" | "SHORT" | "WAIT";
export type TimeSense = "NOW" | "WAIT FOR LEVEL" | "CARE";
export type Confidence = "High" | "Medium" | "Low";

/// Strongest evidence first. Lives here beside the type it orders rather than in the page
/// layer, so any module that can read a `Confidence` can also sort by one without pulling in
/// the web layer's imports.
export const CONFIDENCE_ORDER: Record<Confidence, number> = { High: 0, Medium: 1, Low: 2 };
export type Direction = "up" | "down" | "flat" | "unknown";

/// Why a WAIT is a WAIT, which is the one distinction a reader cannot afford to have blurred.
///
/// Two completely different sentences have been reaching the page under the same word:
///
///   **"file"**     we do not have the measurement. No close is stored, the venue answered
///                  nothing, the close is too old to describe the present, no setup row exists,
///                  the news was never checked. Nothing has been judged, and the honest reading
///                  is "unknown", not "weak".
///   **"evidence"** we have the measurement and it does not support acting. The trend is there
///                  and volume is ordinary; the two timeframes disagree; the peers argue the
///                  other way; price sits between its own averages. Something was judged, and
///                  the answer was no.
///
/// A professional reading an incomplete file says "I cannot tell yet". A professional reading a
/// complete file that does not confirm says "the case is not there". Printing both as a grey
/// WAIT with Low beside it tells the reader neither, and tells them the second one when the
/// truth is the first — which overstates how much the system actually knows.
///
/// Null on a LONG or a SHORT: a direction was produced, so nothing was withheld.
export type WaitBasis = "file" | "evidence";
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

/// The share of matched days that must have gone the same way before history counts as support.
///
/// 0.55, and it is not a new number: `ANALOG_SHARE` in `jobs/setup.py` has required exactly this
/// of the same measurement since that file was written. This module asked for `> 0.5` instead, so
/// two parts of one system held different opinions about when a set of past days agrees, and the
/// looser one was the part that grades confidence on the page.
///
/// What the gap admitted, measured 2026-10-07: **13 of 44** directional non-Low names rested on an
/// analog share within five points of a coin flip. HMC was 377 of 748 -- 50.4%, which on that
/// sample is a fifth of one standard deviation from random -- and the page printed "Confirmed by
/// 377 of 748 similar days going the same way". A bare majority over hundreds of days is not
/// agreement, it is the absence of a finding, and calling it confirmation is the overclaim this
/// site exists not to make.
///
/// Raising it to meet `setup.py` is a tightening, so it can only ever remove confirmations and
/// lower grades. It cannot invent a direction.
export const ANALOG_SHARE_CONFIRMS = 0.55;

/// How far from its peers a name must be, in percentage points over 20 sessions, before the peer
/// reading counts for or against the direction. Per market, and that is the whole point.
///
/// Relative strength is the one factor that can contradict a rising price: a name up 4% while its
/// industry is up 10% is a laggard being carried, and the absolute return cannot say so. The band
/// is symmetric — the same distance confirms as contradicts — because it is one measurement and
/// one question, and it is deliberately wide because this is meant to catch the clear cases.
///
/// **It was a single constant of 3 points, and that was rule 42 all over again.** A threshold
/// compared against a quantity with a different scale in every market is a different threshold in
/// every market. Measured 2026-10-09 over the newest `AssetFactor` per asset, as the median of
/// |relStrength| and the share of names clearing 3 points:
///
///     market      n    median |rel|   share over 3 points
///     FX         27        1.13                 7%
///     PSX       151        3.53                55%
///     US        237        3.71                58%
///     Commodity   4        4.35                50%
///     Crypto     36        5.56                67%
///
/// So one number was doing two opposite jobs. For a currency pair it was a bar almost nothing
/// cleared — 2 of 27 — which is most of why 24 of 27 pairs sat in WAIT with every input fresh.
/// For a US equity or a coin it passed well over half the pool, and a confirmation that fires on
/// three names in five is not evidence about any of them.
///
/// Each figure below is **twice that market's own median, to the nearest half point**, which puts
/// the bar near the 75th percentile everywhere: roughly the clearest quarter of names, measured
/// in the units that market actually trades in. Doubling the median rather than taking the
/// measured p75 directly, because a quartile over 27 or 151 observations of one day moves around
/// and twice-the-middle does not.
///
/// Commodity and Other take the US figure. Four observations is not a sample to set a threshold
/// from, and a number derived from four would look measured while being arbitrary — the honest
/// choice is the general bar until there are enough peers to measure a separate one.
export const REL_BAND: Record<Market, number> = {
  FX: 2.5,
  PSX: 7.0,
  US: 7.5,
  Crypto: 11.0,
  Commodity: 7.5,
  Other: 7.5,
};

/// The band for one input's market. One lookup, so the two halves cannot drift apart.
export function relBandFor(input: DecisionInput): number {
  return REL_BAND[input.market];
}

/// Reward against risk at which a stored disagreement stops being a reason to stand aside.
///
/// Read off `SetupTarget.rewardRisk`, which `jobs/horizons.py` computes from the measured target
/// range against the setup's own invalidation level — and refuses to write at all when there is
/// no invalidation, so every figure this threshold sees has a real denominator.
///
/// 2.75 is where it is because of what the table actually holds, not because it is a round
/// number. A sixth is a minority worth naming, which is the whole job of a threshold.
///
/// **It was 2.0, and the denominator moved underneath it.** When it was set, 111 of 717 setups
/// reached 2.0 — a little under one in six. `jobs/setup.py` then stopped placing the invalidation
/// at the far end of the 20-session range and started placing it 1.5 of the asset's own daily
/// moves from the entry, which cut the median risk window from 10.4% of the price to 2.75%. Every
/// reward figure in the table roughly tripled without a single target moving, and 2.0 went from
/// catching 15% of setups to catching **44%** of them. By the argument written here when it was
/// chosen — "at 1.0 the bar would pass two thirds of the table and mean nothing" — 2.0 had
/// stopped meaning anything.
///
/// Re-measured 2026-10-09 over the 745 current setups, on the same preferred-method basis the
/// rules read: 2.0 passes 325, 2.5 passes 138, **2.75 passes 109 (15%)**, 3.0 passes 69. 2.75
/// restores the property the number was given, almost exactly — 109 against the original 111.
///
/// This is the fourth time in this file a constant has had to be re-derived because what it was
/// divided against changed. Rule 42 is the general form, and the lesson it keeps teaching is that
/// a threshold is a statement about a distribution and has to be re-read whenever the
/// distribution does.
///
/// It is used in exactly two places and both are bypasses, never promotions on their own: gate 5
/// stops refusing a disagreement, and gate 8 carries a trend whose other conditions are
/// incomplete. Neither invents a direction — the direction is already measured and stored.
export const ASYMMETRY_CLEARS = 2.75;

/// The trade in levels and measured frequencies, for a decision that produced a direction.
///
/// Every field is a stored number or arithmetic over two of them. Nothing here is a forecast and
/// nothing here is new measurement: `entry` and `invalidation` are the levels `jobs/setup.py`
/// wrote, `target` is the range `jobs/horizons.py` measured, `rewardRisk` is that job's own
/// figure, and `baseRate` is the count of matched past days `jobs/analogs.py` stored.
///
/// `expectancyR` is the only derived value, and it is deliberately a statement about the stored
/// sample rather than about the next move: it is what the matched days would have returned per
/// unit risked, at this reward:risk, had each been taken. Principle 3 — it is never printed
/// without `baseRate.count` beside it.
export interface TradePlan {
  /// Where the trade is live and not yet wrong. The same band `Decision.entry` carries.
  entry: { low: number; high: number } | null;
  /// The level at which it is wrong. Never null: a plan is only built past gate 4.
  invalidation: number;
  /// The measured exit if it works, and which of the three methods measured it.
  target: { low: number; high: number; method: string } | null;
  /// Reward against risk as `jobs/horizons.py` measured it. Null when no target is stored.
  rewardRisk: number | null;
  /// The share of matched past days that went this way, with the sample it was taken over.
  ///
  /// A frequency over stored history, never a probability of the next move. `count` travels
  /// with `share` because a share without its denominator is the overclaim principle 3 exists
  /// to forbid, and no reader can weigh 60% without knowing whether it is 6 days or 600.
  baseRate: { share: number; count: number } | null;
  /// `share * rewardRisk - (1 - share)`, in units of the risk. Null without both inputs.
  expectancyR: number | null;
}

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
    /// Which way the two moving averages sit, when the trend itself came back mixed.
    ///
    /// Two things agreeing rather than three — the fast mean above or below the slow one, with
    /// the close somewhere between them. `jobs/setup.py` writes it only under a mixed trend, so
    /// this and `trend` are never both directional on one row. See `biasDirectionOf`.
    bias?: TrendDirection | null;
  } | null;
  /// The longer-term reading, which may agree, disagree, or be flat.
  horizon: { direction: Direction } | null;
  /// Measured entry band. Both numbers inclusive, low <= high.
  entry: { low: number; high: number } | null;
  /// The level at which the setup is wrong. Without one there is no trade, only a hope.
  invalidation: number | null;
  /// The measured exit if the setup works, from the deciding setup's own target rows.
  ///
  /// One row and not the list: rule 24 forbids averaging the three methods, so one is chosen by
  /// the stated preference in `lib/target.ts` and its method travels with it. Null when
  /// `jobs/horizons.py` wrote no target for this setup, which is the ordinary state for a name
  /// it has not reached — and which costs the decision its reward figure rather than its
  /// direction.
  target?: {
    method: string;
    low: number;
    high: number;
    /// Reward against risk, as the job measured it. Null when the job could not.
    rewardRisk: number | null;
  } | null;
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
  /// What the stored coverage reading says, when it says anything.
  ///
  /// Separate from `newsCount`, which is a volume of stories and carries no direction. This is
  /// the direction: `jobs/human.py`'s word-list verdict over the headlines that took a side,
  /// published only past `MIN_TONE_ITEMS` of them and past a `NEUTRAL_BAND` net share — so
  /// `tone` is "neutral" both when the window was balanced and when too few headlines took a
  /// side, and the counts beside it in the table are what tell those apart.
  ///
  /// Null when no `HumanSignal` row exists for this asset at all, which is a third value again:
  /// nothing was read, as against read and found balanced. Measured 2026-10-09 over 454 stored
  /// readings: 378 neutral, 55 positive, 20 negative, 1 with no tone column at all.
  ///
  /// `catalyst` is the other half and answers a different question. Tone is what a month of
  /// coverage was worded like; catalyst is whether something arrived in the last few days that
  /// was not arriving before — four stories in three days against a baseline of one a week. It
  /// is the flag that distinguishes a slow mood from an event.
  news?: {
    /// "up" for positive, "down" for negative. Null when the reading came back neutral, which
    /// is a measurement and not an absence.
    tone: "up" | "down" | null;
    catalyst: boolean;
  } | null;
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
  /// What argues against the direction, or qualifies it, without replacing it.
  ///
  /// This list is where the two demoted gates went. It is deliberately separate from `missing`:
  /// `missing` is a measurement nobody took, and a note is a measurement that was taken and
  /// does not help. A note never changes the action. `peers-against` still costs a confidence
  /// step, so rule 6 holds — the grade cannot read more confident than the note under it.
  ///
  /// Empty on most decisions, and empty on every WAIT whose own gate already said the same
  /// thing: a name refused for a stale close is not also told its peers disagree, because the
  /// peer reading was taken against a close the rules have just declared too old to use.
  notes: string[];
  /// The honesty line the reader sees under the decision.
  measured: string;
  /// Which gate decided, for the audit page and for tests. Not shown to the reader.
  gate: string;
  /// Whether this WAIT is missing a measurement or holding a measurement that does not confirm.
  /// Null on a direction. See `WaitBasis` -- this is the distinction the UI copy must preserve.
  basis: WaitBasis | null;
  /// The levels and the measured history behind a direction. Null on every WAIT.
  ///
  /// Null on a WAIT on purpose, including a WAIT with a developing read. A plan is the answer to
  /// "where do I get in, where am I wrong, where do I come out", and printing one beside a
  /// refusal invites it to be read as the trade. The developing read already names what is
  /// missing; the levels are in `entry` and `invalidation` for anyone who wants them.
  plan: TradePlan | null;
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
  // The analog leg is withdrawn when the published coverage points the other way. See
  // `newsContradicts`: those matched past days did not have today's headline in them, so a set
  // that agrees with the setup and disagrees with the present is not independent support.
  //
  // Withdrawn and not inverted. It drops from a confirmation to nothing, which costs one grade
  // step, rather than counting as evidence against — a word list is not strong enough to argue
  // the other side, only strong enough to stop this one being claimed.
  const historyConfirms =
    analogConfirms(input, direction) === true && !newsContradicts(input, direction);
  // Four legs now, not three. The fourth is the peer reading, which this function could
  // previously only ever subtract for -- see `peersConfirm`. A name beating its group is
  // evidence, and reading one measurement in one direction only was the asymmetry, not the fix.
  //
  // The High bar stays at two. It is "two independent things agree", not "half of what is
  // available", and moving it with the number of legs would silently re-grade every asset on the
  // site without a single new measurement.
  const confirmations = [
    agrees,
    volumeConfirms(input) === true,
    historyConfirms,
    peersConfirm(input, direction),
  ].filter(Boolean).length;
  const grade: Confidence = confirmations >= 2 ? "High" : confirmations === 1 ? "Medium" : "Low";

  // Rule 6: a grade must never be more confident than the note beside it. When the peer reading
  // was taken and argues the other way, the panel is printing a direction and a contradiction on
  // the same card, and High over that pair claims an agreement that does not exist. One step,
  // not two: this is a qualification, and the direction, the level and the reward are all still
  // measured. Capping is also the whole price of demoting gate 7 -- 15 names stopped being
  // refused on 2026-10-09 and none of them became a High.
  if (peersAgainst(input, direction)) return grade === "High" ? "Medium" : grade;
  return grade;
}

/// The third why line: what confirmed the direction, or that nothing did.
///
/// Printed even when nothing confirms, which is the point. A LONG with no volume and no analog
/// behind it is still the best reading of what is stored, and a reader is entitled to know it is
/// resting on the setup alone rather than discovering that later.
function confirmLine(input: DecisionInput, direction: "up" | "down"): string {
  const vol = volumeConfirms(input);
  // Withdrawn here on exactly the same test `confidenceFor` applies, so the sentence and the
  // grade cannot disagree. The whole point of this pass is that a set of matched past days must
  // not print as confirmation while the published coverage points the other way; printing it
  // and quietly not counting it would be the worse of the two halves.
  const withdrawn =
    analogConfirms(input, direction) === true && newsContradicts(input, direction);
  const analog = withdrawn ? false : analogConfirms(input, direction);
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
  if (peersConfirm(input, direction) && input.relStrength !== null && input.relStrength !== undefined) {
    parts.push(
      `${Math.abs(input.relStrength).toFixed(1)} points ${
        direction === "up" ? "ahead of" : "behind"
      } its peers over 20 sessions`,
    );
  }
  if (parts.length) return `Confirmed by ${parts.join(" and ")}.`;
  // The withdrawn case gets its own sentence rather than falling into "neither confirms it",
  // which would be true of the arithmetic and wrong about the file: the matched days DO lean
  // this way, and the reason they are not being counted is the present, not the history.
  if (withdrawn) {
    return "Similar past days lean this way, but the published coverage points the other way, so they are not counted.";
  }
  if (vol === false && analog === false) return "Neither volume nor similar days confirm it.";
  return "Nothing further confirms it yet.";
}

/// What could have confirmed the direction and was not stored. Reported as missing rather than
/// silently treated as a negative.
function confirmMissing(input: DecisionInput, direction: "up" | "down"): string[] {
  const out: string[] = [];
  // The measured exit, reported absent rather than silently left out of the plan. Without it
  // there is no reward figure, so there is no reward against risk and no expectancy -- three
  // numbers the reader can see are not there, from one row that was not written.
  if (!input.target) {
    out.push("No measured target stored, so there is nothing to size the reward against.");
  } else if (input.target.rewardRisk === null) {
    out.push(
      `A target is stored by the ${input.target.method} method but its reward against risk was not computed, so the trade cannot be sized.`,
    );
  }
  if (volumeConfirms(input) === null) out.push("No volume published, so the move is unconfirmed by activity.");
  if (analogConfirms(input, direction) === null) {
    // Three different absences, and they were all being reported as the first one. A name with
    // 375 matched days whose lean was not stored printed "Only 375 similar past days stored; 8
    // are needed to confirm", which is not true of 375 and tells the reader to wait for
    // something that already happened. Seen live on ABBV.
    const a = input.analogs;
    const n = a?.count ?? 0;
    if (!a || n === 0) {
      // A fourth absence, and the one that reads most wrongly. "No similar past days stored"
      // sounds like history still being collected. When there is no volume ratio it is neither
      // collected nor collectable: `jobs/analogs.py` matches on a volume ratio among its three
      // factors and treats a missing one as "not a match", so no day can match another however
      // long the series grows. Measured 2026-10-07: all 27 currency pairs hold zero analogs,
      // because FX publishes no volume at any venue, while every other class is near-complete.
      //
      // The sentence names the mechanism and stops there. `volumeRatio` is also null when the
      // baseline was too thin to divide by, which is a different and temporary reason, so this
      // must not say the venue publishes none -- that is true of a pair and false of a share.
      out.push(
        input.volumeRatio === null
          ? "No similar past days can be matched without a volume ratio, and none is stored for this name."
          : "No similar past days stored, so nothing measures what usually followed.",
      );
    } else if (n < ANALOGS_CONFIRM_MIN) {
      out.push(`Only ${n} similar past days stored; ${ANALOGS_CONFIRM_MIN} are needed to confirm.`);
    } else {
      out.push(
        `${n} similar past days are stored, but which way they went was not recorded, so they cannot confirm the direction.`,
      );
    }
  } else if (analogConfirms(input, direction) === false) {
    // The branch that did not exist, and the reason the distinction this pass is about has to
    // reach one level further down. `null` means the set could not be judged and every sentence
    // above names which absence that was. `false` means it WAS judged and came back disagreeing
    // -- and nothing was printed, so a reader saw no line about history at all and could not tell
    // "not checked" from "checked, and it does not agree". The second is a finding and belongs on
    // the page.
    //
    // It is also the branch that tightening `ANALOG_SHARE_CONFIRMS` to 0.55 moved names into: a
    // share between half and 0.55 used to confirm, and now correctly does not.
    const a = input.analogs;
    const n = a?.count ?? 0;
    const same = direction === "up" ? (a?.positive ?? 0) : n - (a?.positive ?? 0);
    out.push(
      `${same} of ${n} similar past days went this way, short of the ${Math.round(
        ANALOG_SHARE_CONFIRMS * 100,
      )}% needed before history counts as agreement.`,
    );
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
  // Both halves, and the share has to clear the band rather than merely cross the midpoint. A
  // majority *and* a median of the right sign, because six of ten rising with a negative median is
  // a set where the four falls were larger -- counting the days and ignoring their size.
  return direction === "up"
    ? share >= ANALOG_SHARE_CONFIRMS && a.medianPct > 0
    : share <= 1 - ANALOG_SHARE_CONFIRMS && a.medianPct < 0;
}

/// Reward against risk for the deciding setup, or null when no target was measured.
function rewardRisk(input: DecisionInput): number | null {
  const rr = input.target?.rewardRisk;
  return rr === null || rr === undefined ? null : rr;
}

/// Is the stored reward asymmetric enough to carry a direction past a disagreement?
///
/// False when no target exists, which is the honest answer rather than a cautious one: an
/// unmeasured reward is not a small one, but it also cannot pay for bypassing anything. The name
/// of the missing target reaches the reader through `confirmMissing`'s sibling below.
function asymmetric(input: DecisionInput): boolean {
  const rr = rewardRisk(input);
  return rr !== null && rr >= ASYMMETRY_CLEARS;
}

/// Does the stored coverage reading point the other way from the direction being taken?
///
/// **Why this exists, and why it is not symmetric.** An analog set answers "what followed past
/// days that looked like this one" — on price, volume and the five-day return, which is every
/// factor `jobs/analogs.py` matches on. None of those past days had today's headline. So when
/// the published coverage carries a direction and it is the opposite one, the matched days are
/// not weak evidence for the trade, they are evidence drawn from a sample that is missing the
/// thing most likely to drive the next move. A set that would otherwise confirm is then
/// confirming a different situation, and a rule table that lets it is walking into the trap
/// that the analog looked good.
///
/// It can only ever take evidence away. An agreeing tone is deliberately **not** a fourth
/// confirmation and cannot lift a grade, because principle 5 is explicit: current human
/// attention is context, not proof. A word list over headlines — no bodies, no negation, no
/// sarcasm, as every surface that shows it says — is not the thing to promote a trade on. It is
/// good enough to withdraw a claim and not good enough to make one, and those are different
/// bars on purpose.
///
/// Null when no reading exists or the reading was neutral. Rule 21 again: "no row" and "read,
/// and it took no side" are not the same as "read, and it disagrees", and only the third one
/// is allowed to change anything.
function newsContradicts(input: DecisionInput, direction: "up" | "down"): boolean {
  const tone = input.news?.tone ?? null;
  if (tone === null) return false;
  return tone !== direction;
}

/// How often the matched past days went this way, with the sample it was taken over.
///
/// Null below `ANALOGS_CONFIRM_MIN`, the floor `jobs/analogs.py` refuses to grade under. A share
/// over seven days is a number its own producer declines to stand behind, and quoting one here
/// would be this file standing behind it instead.
function baseRate(
  input: DecisionInput,
  direction: "up" | "down",
): { share: number; count: number } | null {
  const a = input.analogs;
  if (!a || a.count < ANALOGS_CONFIRM_MIN) return null;
  if (a.positive === null || a.positive === undefined) return null;
  const same = direction === "up" ? a.positive : a.count - a.positive;
  return { share: same / a.count, count: a.count };
}

/// The levels and the measured history behind a direction.
///
/// `invalidation` is non-null by construction: nothing calls this before gate 4 has refused every
/// input without one, and the signature says so rather than re-testing it and inventing a
/// branch that cannot be reached.
function planFor(input: DecisionInput, direction: "up" | "down", invalidation: number): TradePlan {
  const rr = rewardRisk(input);
  const rate = baseRate(input, direction);
  return {
    entry: input.entry,
    invalidation,
    target: input.target
      ? { low: input.target.low, high: input.target.high, method: input.target.method }
      : null,
    rewardRisk: rr,
    baseRate: rate,
    // Both or nothing. An expectancy computed against an assumed reward, or against a share
    // taken from six days, is a figure that looks like arithmetic and is a guess with a decimal
    // point on it -- which is the single failure this whole module is arranged to prevent.
    expectancyR: rate && rr !== null ? rate.share * rr - (1 - rate.share) : null,
  };
}

/// What argues against the direction or qualifies it, without replacing it.
///
/// The two demoted gates live here, in the order they used to sit in the table, plus the dated
/// event that was always an overlay rather than a gate. Each one names its own stored value:
/// "peers argue the other way" standing in for a measured 4.2 points would be the one-value
/// shorthand rule 21 forbids.
function notesFor(input: DecisionInput, direction: "up" | "down"): string[] {
  const out: string[] = [];

  // Formerly gate 6. Thin news under an unusual move is the state in which a published reason
  // has not arrived, and the two absences still read differently: a null count means no feed
  // answered for this name at all, where a low count means the feeds answered and there was
  // little there. The sentence says which, and stops -- what the quiet means is not a thing
  // this file can measure, and naming it would be the causal claim hard rule 4 forbids.
  if (input.unusualMove && (input.newsCount === null || input.newsCount < THIN_NEWS_BELOW)) {
    out.push(
      input.newsCount === null
        ? "It moved unusually and no news has been collected for this name, so nothing published accounts for the move."
        : `It moved unusually on ${input.newsCount} recent ${
            input.newsCount === 1 ? "story" : "stories"
          }, so nothing published accounts for the move yet.`,
    );
  }

  // Formerly gate 7. Still the one factor that can contradict a rising price -- principle 2 --
  // and still costed, in `confidenceFor`. What changed is that it qualifies the direction
  // instead of deleting it.
  const rel = input.relStrength;
  if (rel !== null && rel !== undefined) {
    if (direction === "up" && rel <= -relBandFor(input)) {
      out.push(
        `It is ${Math.abs(rel).toFixed(1)} points behind its peers over 20 sessions, so the group is carrying it rather than the other way round.`,
      );
    }
    if (direction === "down" && rel >= relBandFor(input)) {
      out.push(
        `It is ${rel.toFixed(1)} points ahead of its peers over 20 sessions, so it is holding up better than the group it trades with.`,
      );
    }
  }

  // The confluence note. Printed whenever the published coverage points the other way, whether
  // or not an analog set was there to be withdrawn -- a reader taking a LONG into a month of
  // negatively worded coverage is owed that fact even when no matched days existed.
  //
  // Two sentences, because `catalyst` is a different finding from `tone` and merging them would
  // lose the one that matters most: a mood held over a month is not the same as something that
  // arrived in the last few days against a baseline that had nothing in it.
  if (newsContradicts(input, direction)) {
    const coverage = direction === "up" ? "negatively" : "positively";
    out.push(
      input.news?.catalyst
        ? `Recent coverage is worded ${coverage} and arrived as a spike against its own baseline, so the present contradicts the setup rather than merely lagging it.`
        : `Recent coverage is worded ${coverage}, which is the opposite of the direction being taken.`,
    );
    // The consequence, spelled out with its own numbers, and only when there is a consequence.
    //
    // It is here rather than in the why line because `confirmLine` can only say this when
    // nothing else confirms: with volume also confirming, the sentence becomes "Confirmed by
    // volume 1.8x its average" and the withdrawn set vanishes from the page entirely. A
    // confirmation that was found and then deliberately not counted is exactly the kind of
    // thing a reader has to be told, so it is stated where the qualifications live.
    const a = input.analogs;
    if (analogConfirms(input, direction) === true && a) {
      const same = direction === "up" ? (a.positive ?? 0) : a.count - (a.positive ?? 0);
      out.push(
        `${same} of ${a.count} similar past days went this way, and they are not counted as confirmation: none of them had this coverage in it.`,
      );
    }
  }

  // Never a gate, and it was never meant to be one: a calendar row is a risk to size, not a
  // reason to act. It already sets the time sense to CARE; this is the same fact in words.
  if (input.eventInDays !== null && input.eventInDays <= EVENT_SOON_DAYS) {
    out.push(
      input.eventInDays <= 0
        ? "A dated event falls today, so a position opened now is open across it."
        : `A dated event is ${input.eventInDays} ${
            input.eventInDays === 1 ? "day" : "days"
          } away, so a position opened now is open across it.`,
    );
  }

  return out;
}

/// Does the peer reading argue against this direction? The one note that costs a grade.
function peersAgainst(input: DecisionInput, direction: "up" | "down"): boolean {
  const rel = input.relStrength;
  if (rel === null || rel === undefined) return false;
  return direction === "up" ? rel <= -relBandFor(input) : rel >= relBandFor(input);
}

/// Does the peer reading back this direction? The mirror of `peersAgainst`, and it did not exist.
///
/// **This asymmetry was a bug in the rule table, not a design.** Relative strength is principle 2
/// — "relative strength against peers matters more than a raw return" — and until now the rules
/// could only ever use it to argue *against* a direction. A name 11 points behind its group cost
/// a grade; a name 11 points ahead of its group counted for nothing. One measurement, read in one
/// direction only.
///
/// It is a real third leg and not a fourth copy of the first two. Volume says how much trading
/// happened, the analog set says what followed days that looked like this one, and this says
/// whether the asset is beating the names it trades with. The three can and do disagree.
///
/// Same band as `peersAgainst`, deliberately: one threshold for one idea, so a name cannot be
/// simultaneously too close to call against and far enough ahead to confirm. Null is still no
/// evidence rather than evidence either way — 22 of 477 assets have no peer reading, mostly
/// commodities and funds in groups too small for `jobs/factors.py` to take a median over.
///
/// Measured 2026-10-09: of the 150 refused names carrying a clear trend, this carries **49** —
/// 44 stocks, 2 crypto, 2 commodities, 1 currency pair. It is not a formality and it is not a
/// floodgate.
function peersConfirm(input: DecisionInput, direction: "up" | "down"): boolean {
  const rel = input.relStrength;
  if (rel === null || rel === undefined) return false;
  return direction === "up" ? rel >= relBandFor(input) : rel <= -relBandFor(input);
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
  basis: WaitBasis,
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
    // A refusal carries no notes. Every gate that produces one has already printed the single
    // reason the reader is owed, and a second list under it arguing the same way is the "five
    // reasons where one was wanted" this file's ordering exists to avoid.
    notes: [],
    measured: measuredLine(input),
    gate,
    basis,
    // No plan on a refusal. See `Decision.plan`.
    plan: null,
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
  // Same fallback as the gate below, for the same reason and in the same order: a name whose
  // averages have a side but whose trend does not is forming, and a developing list that could
  // not say so left 119 names describable by nothing at all.
  const withheld = input.setup?.trend ?? null;
  const trend: "up" | "down" | null =
    withheld === "up" || withheld === "down"
      ? withheld
      : input.setup?.bias === "up" || input.setup?.bias === "down"
        ? input.setup.bias
        : null;
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

  // First, because it is the one thing in this list that is about the present rather than about
  // a measurement that has not filled yet, and a reader scanning one line gets that line. It is
  // also why the name is here at all rather than carried by gate 8: a contradicted trend is
  // refused there and lands exactly in this list.
  if (newsContradicts(input, trend)) {
    waitingOn.push(
      `Recent coverage is worded ${trend === "up" ? "negatively" : "positively"}, against the trend${
        input.news?.catalyst ? ", and arrived as a spike against its own baseline" : ""
      }.`,
    );
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
    return wait(input, "no-prices", "file", [`No stored prices for ${input.symbol}.`], [
      `No price series stored for ${input.symbol}.`,
    ]);
  }

  // 2. Stale beyond this market's own rule. Acting on an old close is the one failure a price
  //    panel must never commit, so this gate sits above every signal.
  const age = daysBetween(input.asOf, input.today);
  const limit = STALE_AFTER_DAYS[input.market];
  if (Number.isNaN(age)) {
    return wait(input, "bad-date", "file", ["Stored date cannot be read."], [
      `Newest close date for ${input.symbol} is not a readable date.`,
    ]);
  }
  if (age > limit) {
    return wait(
      input,
      "stale",
      "file",
      [`Data stale: newest close ${input.asOf}, ${age} days old.`],
      [`Close for ${input.symbol} is ${age} days old; this market allows ${limit}.`],
    );
  }

  // 3. A silent source. Named, because "no data" and "Binance answered nothing" send the reader to
  //    two different places.
  if (input.sourceSilent) {
    return wait(input, "source-silent", "file", [`${input.sourceSilent} answered nothing.`], [
      `${input.sourceSilent} returned no rows on the last run.`,
    ]);
  }

  // 4. No break level. Without one there is nothing to be wrong against, and an action with no
  //    invalidation is the kind this panel refuses to print.
  if (input.invalidation === null) {
    return wait(input, "no-invalidation", "file", ["No break level computed yet."], [
      `No invalidation level stored for ${input.symbol}.`,
    ]);
  }

  const setup = input.setup?.direction ?? "unknown";
  const horizon = input.horizon?.direction ?? "unknown";
  // `invalidation` is non-null from here down: gate 4 refused every input without one. Narrowed
  // once into a local so the three direction builders below take a number rather than each
  // re-testing a branch that gate 4 has already made unreachable.
  const invalidation = input.invalidation;

  /// One direction, built once. The three ways in — a `buy`/`short` state, the same state over a
  /// disagreeing horizon, and a withheld trend carried by one confirmation — differ only in
  /// their opening sentence and their gate name, and writing the object out three times is how
  /// two of the three come to carry different fields.
  const direction = (dir: "up" | "down", gate: string, opening: string): Decision => {
    const action: Action = dir === "up" ? "LONG" : "SHORT";
    return {
      action,
      why: [opening, secondLine(dir, horizon), confirmLine(input, dir)],
      entry: input.entry,
      invalidation,
      timeSense: timeSenseFor(input, action),
      confidence: confidenceFor(input, action),
      missing: [
        ...(input.entry ? [] : ["No measured entry band stored; only the break level is set."]),
        ...confirmMissing(input, dir),
      ],
      notes: [
        // The demoted horizon disagreement, printed where every other qualification is. It
        // already costs a confidence step -- `confidenceFor` counts an agreeing second timeframe
        // and there is none to count -- so this is the sentence, not a second penalty.
        ...((dir === "up" && horizon === "down") || (dir === "down" && horizon === "up")
          ? [
              `The longer view reads ${horizon} where this reads ${dir}. They measure different windows, so this is a disagreement to size rather than a contradiction.`,
            ]
          : []),
        ...notesFor(input, dir),
      ],
      measured: measuredLine(input),
      gate,
      // A direction was produced, so nothing was withheld and there is no basis to report.
      basis: null,
      plan: planFor(input, dir, invalidation),
      // A printed direction is not developing; it has arrived.
      developing: null,
    };
  };

  /// What is carrying a direction its own conditions do not support, named with its own value.
  const carriedBy = (dir: "up" | "down"): string => {
    const rr = rewardRisk(input);
    if (volumeConfirms(input) === true && input.volumeRatio) {
      return `volume at ${input.volumeRatio.toFixed(1)}x its 20-session average`;
    }
    if (peersConfirm(input, dir) && input.relStrength !== null && input.relStrength !== undefined) {
      return `${Math.abs(input.relStrength).toFixed(1)} points ${
        dir === "up" ? "ahead of" : "behind"
      } its peers`;
    }
    return rr !== null ? `reward at ${rr.toFixed(1)}x the risk` : "a stored confirmation";
  };

  // 5. The two timeframes wanting opposite things is a note now, not a refusal.
  //
  // It was the last soft veto in the table. A disagreement between a swing read and a quarterly
  // one is a real finding and it is not evidence that the shorter one is wrong -- the two measure
  // different windows and answer different questions, which is the sentence the horizons block on
  // every asset page has always carried. Refusing both because they differ withheld the nearer
  // read on the strength of the further one.
  //
  // It costs a confidence step through `confidenceFor`, where the agreeing-timeframe leg simply
  // does not count, and it prints under "What argues against it". One name sat here on
  // 2026-10-09; the demotion is written for the shape rather than for the count.
  // 6 and 7. A direction, with a level to be wrong at, and whatever confirms it.
  if (setup === "up") {
    return direction(
      "up",
      "long",
      `Setup is up${input.setup?.horizon ? ` on the ${input.setup.horizon} view` : ""}.`,
    );
  }
  if (setup === "down") {
    return direction(
      "down",
      "short",
      `Setup is down${input.setup?.horizon ? ` on the ${input.setup.horizon} view` : ""}.`,
    );
  }

  // 8. The withheld trend, carried.
  //
  // This is the largest change in the table and the one that needs stating plainly. `setup.py`
  // writes state `wait` when **the trend is clear and not all the conditions behind it are
  // present**, and `directionOfState` maps that to `flat` — so a measured direction arrived here
  // with nowhere to go and fell through to "conditions are incomplete". Measured 2026-10-09:
  // **247 of 477 swing rows are in that state, and every one of them carries a trend verdict**
  // (61 up, 186 down, 0 mixed). That is the majority of the pool reaching the reader as the
  // middle of a WAIT list.
  //
  // What this gate does NOT do is invent the missing confirmations. It requires one of exactly
  // two stored things to carry the trend, and both are the ones the directive calls the math and
  // the volume:
  //
  //   * volume at or above `VOLUME_CONFIRMS_AT` — people acting, not drift; or
  //   * reward at or above `ASYMMETRY_CLEARS` — a tight invalidation against a wide measured
  //     target, which is an asymmetry worth taking a thinner case on.
  //
  // Neither is a majority: 149 of 477 names confirm on volume, 111 of 717 setups on reward. A
  // trend with neither still falls through to gate 9 and still reaches the reader as a developing
  // read with its shortfall named — because in that case the math and the volume did not align,
  // which is the condition the promotion was written for and not a formality to route around.
  //
  // The horizon still has a veto here, on the same terms as gate 5: a withheld trend pointing
  // into a disagreeing longer view is carried only when the reward is asymmetric. The opening
  // sentence says the conditions are incomplete, every absent confirmation is still listed in
  // `missing`, and the confidence grade counts the same three confirmations as everywhere else,
  // so a carried trend grades Medium or Low on its own evidence rather than by decree.
  // The withheld direction, or failing that the side the two averages sit on.
  //
  // `trend` first and `bias` only when the trend has nothing to say, which is the order of how
  // much each one is: a trend is the close, the fast mean and the slow mean lined up; a bias is
  // the two means with the close between them. `jobs/setup.py` writes `bias` only under a mixed
  // trend, so these never compete for one row -- the fallback is a fallback and not a preference.
  //
  // What it reaches is the largest block the table had no answer for at all: 123 refused names on
  // 2026-10-09 whose swing state was `none`, meaning price sits between its own averages. **119
  // of them have a measurable side** and nothing was reading it. They remain subject to every
  // requirement below -- a carrier, a horizon that does not disagree, coverage that does not
  // contradict -- so the weaker reading buys a chance at this gate rather than a pass through it,
  // and the sentence it prints says which of the two it acted on.
  const trendRead = input.setup?.trend ?? null;
  const biasRead = input.setup?.bias ?? null;
  const fromTrend = trendRead === "up" || trendRead === "down";
  const trend: "up" | "down" | null = fromTrend
    ? (trendRead as "up" | "down")
    : biasRead === "up" || biasRead === "down"
      ? biasRead
      : null;
  if (trend === "up" || trend === "down") {
    // **No carrier is required any more, and this is the last filter to go.**
    //
    // It asked for one of three stored figures -- volume at or above its own average, a peer gap
    // wide enough for the market, or a reward at `ASYMMETRY_CLEARS`. Measured 2026-10-09 after
    // every other change in this file: **176 of the 187 refused names had a measured direction,
    // an entry and a stop, and were held back only because none of those three was present.**
    //
    // The argument for the carrier was that a direction whose own conditions failed should not
    // print as an action. The argument against it, which wins, is that `confidence` already says
    // exactly that and says it with more resolution than a gate can. A gate is one bit: acted on,
    // or not. The grade counts four independent confirmations and reports none of them as Low,
    // one as Medium, two or more as High -- so a carrier-less direction was already distinguished
    // from a confirmed one by the field built to distinguish them, and the gate was the same
    // judgement made twice, the second time by deletion.
    //
    // What this does not do is invent anything. The direction is `jobs/setup.py`'s own stored
    // trend or bias verdict, the stop is the measured level 1.5 of the asset's daily moves from
    // the entry, and the target and reward are `jobs/horizons.py`'s. A name with none of the
    // three carriers prints Low, says in its own why line that nothing confirms it, and lists
    // every absent confirmation under what is missing.
    //
    // **And it is recorded as its own gate so it can be judged.** `unconfirmed-long` and
    // `unconfirmed-short` are written to `DecisionLog` beside `trend-long` and `long`, which
    // matures at +1, +5 and +20 sessions. Letting a thinner case through is defensible only
    // because the loop that measures whether it pays is already running -- principle 7, and the
    // reason this change is a change in what is printed rather than in what is claimed.
    const carriers =
      volumeConfirms(input) === true || peersConfirm(input, trend) || asymmetric(input);
    const gate = carriers
      ? trend === "up"
        ? "trend-long"
        : "trend-short"
      : trend === "up"
        ? "unconfirmed-long"
        : "unconfirmed-short";
    const opening = fromTrend
      ? carriers
        ? `The trend is ${trend} and not all of its conditions are present; ${carriedBy(trend)} carries it.`
        : `The trend is ${trend} and none of its other conditions are present.`
      : carriers
        ? `Price is between its own averages, with the 20 day ${
            trend === "up" ? "above" : "below"
          } the 50 day; ${carriedBy(trend)} carries it.`
        : `Price is between its own averages, with the 20 day ${
            trend === "up" ? "above" : "below"
          } the 50 day, and nothing else confirms it.`;
    return direction(trend, gate, opening);
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

  // Whether this fall-through is an open file or a closed one, and the two need different words.
  //
  // `input.setup` is null when no setup row exists for this asset at all -- the job has not
  // reached it, or could not measure it. Nothing was judged. The sentence this gate used to print
  // in that case was **"There is no clear direction to measure. Price is between its own
  // averages."**, which is a statement about where the price sits relative to measurements that
  // were never taken. It reads as a finished reading and it is an empty file, which is the exact
  // confusion this basis field exists to end.
  //
  // With a setup row, the gate is evidence: the job looked, and either withheld a direction whose
  // conditions were incomplete (`wait` -> flat) or found the price between its own averages
  // (`none` -> unknown). Both of those are measurements that came back negative.
  const measured = input.setup !== null;

  return wait(
    input,
    "incomplete",
    measured ? "evidence" : "file",
    developing
      ? [
          `A ${developing.direction === "up" ? "rising" : "falling"} trend is in place, so this is a potential ${developing.would}.`,
          `Not acted on yet: ${developing.waitingOn[0]}`,
        ]
      : !measured
        ? [
            `No setup has been measured for ${input.symbol} yet.`,
            "Nothing is being judged here: this is missing data, not a weak reading.",
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
