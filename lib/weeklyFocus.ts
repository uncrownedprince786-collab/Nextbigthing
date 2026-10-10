// The weekly focus list, and nothing about how it is drawn.
//
// What this is: the names that already passed the rule table as LONG or SHORT, narrowed to the
// ones a reader could actually act on this week, capped so the block stays readable. What it is
// NOT: a second opinion, a score, or a ranking of its own. **Every name here is already in the
// LONG or SHORT list below it** — this block reorders and truncates, it never promotes.
//
// That constraint is the whole design. A "top picks" section that applied its own rules would be a
// second rule table, and the site would then have two answers for one name with nothing saying
// which is the real one. So the filters below are all *subtractive*: each one can only remove a
// name that the main table already acted on.
//
// The honesty rules it exists under, stated here because they are easy to erode one word at a
// time: nothing in this block may promise an outcome. A setup favours a direction while its stop
// holds; it does not "go up". No target is printed here at all — the measured analog range already
// sits on the asset page, where its sample size and window sit beside it, and a range lifted away
// from those reads as a forecast.

import type { Scored } from "./assetClass.ts";
import { CONFIDENCE_ORDER, type TimeSense } from "./decision.ts";
import type { DecisionTarget } from "./queries.ts";
import { pickTarget, targetForCall } from "./target.ts";

/// How many names a side may carry.
///
/// 6, and the number is about the block rather than the data: two columns of six is one screen on
/// a laptop and one scroll on a phone, which is the length at which a reader still compares rows
/// instead of skimming past them. The cap is a cap and not a quota — see `weeklyFocus`, which
/// returns fewer whenever fewer qualify and never pads.
export const WEEKLY_MAX_PER_SIDE = 6;

/// Where the close sits relative to the entry band, as an ordering.
///
/// NOW first because the close is already inside the band, so the reading is actionable today.
/// CARE next: also actionable, with a dated event close enough that a position opened now meets
/// it — a reason to size smaller, not a reason to drop the name. WAIT FOR LEVEL last, because the
/// price has to come to the reader before anything happens.
const TIME_ORDER: Record<TimeSense, number> = { NOW: 0, CARE: 1, "WAIT FOR LEVEL": 2 };

/// Whether a scored row may appear in the weekly block at all.
///
/// Every clause is a subtraction from what the rule table already decided:
///
///  * **It has a direction.** WAIT never appears here, including a WAIT carrying a `developing`
///    read. A direction forming is not a direction, and this block is the one place on the site
///    where that difference is most likely to be misread.
///  * **It is not Low confidence.** Low means no confirmation beyond the direction itself. Those
///    names stay in the main list, where the confidence column is read next to a hundred others
///    rather than in a block headed "this week".
///  * **It has a level to be wrong at, and a band to act in.** A row without an invalidation is
///    one a reader cannot size or exit, and a row without an entry band has nowhere to act. The
///    rule table already refuses to print an action with no invalidation (gate 4); this repeats
///    the check rather than trusting it, because the cost of being wrong here is a trade.
export function qualifiesForWeek(s: Scored): boolean {
  if (s.decision.action === "WAIT") return false;
  if (s.decision.confidence === "Low") return false;
  if (s.decision.invalidation === null) return false;
  if (s.decision.entry === null) return false;
  return true;
}

/// A date as a sortable number, oldest-last. Null dates sort last.
function freshness(value: Date | string | null | undefined): number {
  if (!value) return Number.NEGATIVE_INFINITY;
  const t = typeof value === "string" ? Date.parse(value) : value.getTime();
  return Number.isNaN(t) ? Number.NEGATIVE_INFINITY : t;
}

/// Best evidenced and most immediately actionable first.
///
/// The order is: confidence, then how close the price already is to the band, then how fresh the
/// close is, then the symbol so two reads of the same data never disagree. Freshness sits below
/// the other two deliberately — it breaks ties between equally evidenced names rather than
/// lifting a thin one, since every row here is already inside its own market's staleness rule.
export function byWeeklyFocus(a: Scored, b: Scored): number {
  const c = CONFIDENCE_ORDER[a.decision.confidence] - CONFIDENCE_ORDER[b.decision.confidence];
  if (c !== 0) return c;
  const t = TIME_ORDER[a.decision.timeSense] - TIME_ORDER[b.decision.timeSense];
  if (t !== 0) return t;
  const f = freshness(b.row.closeDate) - freshness(a.row.closeDate);
  if (f !== 0) return f;
  return a.row.symbol.localeCompare(b.row.symbol);
}

export interface WeeklyFocus {
  long: Scored[];
  short: Scored[];
  /// How many directional names existed before the cap, so the block can say what it left out
  /// rather than implying it is the whole list.
  longTotal: number;
  shortTotal: number;
}

/// Six slots, filled best-evidenced first, and inside one grade spread across the markets.
///
/// Sorting by evidence alone and cutting at six is correct arithmetic and, on a real day, a
/// misleading block. Measured on the live site at 477 names: the short side came back six of six
/// Pakistani, because that is where the best evidenced shorts happened to sit, and a reader who
/// follows US names was shown a short side with nothing in it for them -- while thirty-five
/// qualifying shorts existed, some of them American.
///
/// So within a grade the markets take turns: the best High in each market before the second High
/// in any market, then the same for Medium. A grade boundary is never crossed to balance -- a
/// Medium name cannot displace a High one, because the block's first promise is that what is
/// shown is the best evidenced. Balance is a tie-break between equals, not a quota over them.
///
/// Everything else about the block is unchanged: it is still subtractive, every name in it is
/// already in the list below, and fewer than six is the ordinary case rather than a failure.
function spreadAcrossMarkets(sorted: Scored[], cap: number): Scored[] {
  const byGrade = new Map<string, Map<string, Scored[]>>();
  for (const s of sorted) {
    const grade = byGrade.get(s.decision.confidence) ?? new Map<string, Scored[]>();
    const market = grade.get(s.market) ?? [];
    market.push(s);
    grade.set(s.market, market);
    byGrade.set(s.decision.confidence, grade);
  }

  const out: Scored[] = [];
  // Grades in the order the sorted list already put them, so this never re-ranks evidence.
  for (const grade of byGrade.values()) {
    const queues = [...grade.values()];
    let round = 0;
    while (out.length < cap) {
      const taken = out.length;
      for (const queue of queues) {
        if (out.length >= cap) break;
        if (round < queue.length) out.push(queue[round]);
      }
      if (out.length === taken) break;
      round += 1;
    }
    if (out.length >= cap) break;
  }
  return out;
}

/// The two lists, each capped, each possibly empty.
///
/// Returning fewer than the cap is the normal case and not a failure: on a quiet day the rule
/// table produces few confirmed names, and a block that padded itself to six a side with weaker
/// rows would be inventing confidence the data did not produce. A side with nothing in it says so
/// in words rather than disappearing, because an empty answer and a missing section look identical
/// otherwise.
export function weeklyFocus(rows: Scored[], cap = WEEKLY_MAX_PER_SIDE): WeeklyFocus {
  const eligible = rows.filter(qualifiesForWeek);
  const long = eligible.filter((s) => s.decision.action === "LONG").sort(byWeeklyFocus);
  const short = eligible.filter((s) => s.decision.action === "SHORT").sort(byWeeklyFocus);
  return {
    long: spreadAcrossMarkets(long, cap),
    short: spreadAcrossMarkets(short, cap),
    longTotal: long.length,
    shortTotal: short.length,
  };
}

/// The one or two lines under a name: the direction, and what confirms it.
///
/// Taken from the decision's own `why`, never written here. The rule table already states its
/// reason in plain words, and a second phrasing in this block would be a second claim about the
/// same name that no test compares against the first.
///
/// **The first and the last, not the first two.** A directional `why` is three lines: the setup's
/// own direction, how the second timeframe relates to it, and what confirms the whole thing. The
/// confirmation is last, so taking the first two drops it — and the middle line, read alone, can
/// flatly contradict the grade beside it. Measured on the live page: HMC and MU both printed
/// "Only one time frame points anywhere, so nothing confirms it" under a High confidence chip,
/// because the line that said volume and the analog set *did* confirm had been cut off. The
/// middle line is the one to lose: it qualifies the direction, where the last line is the evidence
/// the grade was computed from.
export function weeklyWhy(s: Scored): string[] {
  const lines = s.decision.why.filter(Boolean);
  if (lines.length <= 2) return lines;
  return [lines[0], lines[lines.length - 1]];
}


/// The measured exit, for a scored row.
///
/// The rule itself lives in `lib/target.ts` because three surfaces now ask it — this block, the
/// asset panel and the home rows — and three copies of a preference order is how two of them come
/// to quote different levels for one name.
export function weeklyTarget(s: Scored): DecisionTarget | null {
  // Through `targetForCall`, like the rows and the asset panel: a target on the wrong side of the
  // call (a resolved call going against its setup) is not shown here either.
  return targetForCall(
    pickTarget(
      [
        s.row.swing ? { ...s.row.swing, horizon: "swing" } : null,
        s.row.longer ? { ...s.row.longer, horizon: "longer" } : null,
      ].filter((x): x is NonNullable<typeof x> => x !== null),
    ),
    s.decision,
  ) as DecisionTarget | null;
}

export { targetMethodLabel, targetSourceSentence } from "./target.ts";
