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
    long: long.slice(0, cap),
    short: short.slice(0, cap),
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


/// Which measured target to quote as the exit if the setup works, and never a fourth one.
///
/// `jobs/horizons.py` writes up to three rows per setup, one per method, and rule 24 forbids
/// averaging them: three methods that disagree are three answers, and their mean is a number
/// nothing measured. So one is chosen, by a stated preference, and the method is printed beside
/// it so a reader knows which question was answered.
///
/// The order is the reader's, not the arithmetic's:
///
///  1. **structure** — the nearest price where this series has already turned. It is the only one
///     of the three that is a fact about where the market stopped before, which is what someone
///     asking "where would I take this off" means.
///  2. **volatility** — a multiple of the asset's own recent daily range. Not a place anything
///     happened, but a distance this asset actually covers.
///  3. **analog** — what followed similar past days. Last because it is a distribution over a
///     sample rather than a level, so it answers "how far did this usually get" and not "where".
///
/// Returns null when the job stored nothing, which is a real and common state: no invalidation
/// means no target row is written at all. The block then says so rather than reaching for a
/// number, because a target invented in the web layer is exactly what `jobs/` exists to prevent.
const TARGET_PREFERENCE = ["structure", "volatility", "analog"] as const;

export function weeklyTarget(s: Scored): DecisionTarget | null {
  // The setup the DECISION rested on, which is not always the swing one. `pickSetup` in
  // lib/decisionInput.ts takes the first *directional* row in horizon order swing -> longer, so a
  // name whose swing read is `wait` and whose longer read is `buy` was decided on the longer one.
  // Reading `swing ?? longer` blindly printed "No clear target stored" for exactly those names --
  // HMC and MU on the live page -- while the targets sat on the setup the verdict came from. The
  // same mirroring trap the decision verifier fell into.
  const directional = (r: { state: string } | null | undefined) =>
    r != null && (r.state === "buy" || r.state === "short");
  const setup =
    (directional(s.row.swing) && s.row.swing) ||
    (directional(s.row.longer) && s.row.longer) ||
    s.row.swing ||
    s.row.longer;
  const targets = setup?.targets ?? [];
  if (!targets.length) return null;
  for (const method of TARGET_PREFERENCE) {
    const found = targets.find((t) => t.method === method);
    if (found) return found;
  }
  return targets[0] ?? null;
}

/// What the method measured, in the reader's words rather than the job's.
export function targetMethodLabel(method: string): string {
  if (method === "structure") return "nearest level it has already turned at";
  if (method === "volatility") return "its own recent daily range";
  if (method === "analog") return "what followed similar past days";
  return method;
}
