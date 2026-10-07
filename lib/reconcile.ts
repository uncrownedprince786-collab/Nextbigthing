/// Reconciling a strong direction with a weak grade, in one sentence.
///
/// Pure, and in `lib/` rather than beside the panel that prints it, for two reasons. It decides
/// nothing about markets — it reads what `lib/decision.ts` already decided and puts it into a
/// sentence — so it belongs with the rules rather than with the rendering. And Node runs `.ts`
/// directly but not `.tsx`, so logic that lives in a component file cannot be tested without a
/// build step; `tests/gapLine.test.ts` is the reason this file exists at all.

import type { Decision } from "@/lib/decision";

/// Phrases that `lib/decision.ts` prints, recognised here so the gap line can be built from them.
///
/// This is the ugly part of this file and it should not survive. `confidenceFor` in lib/decision.ts
/// counts exactly three confirmations — a longer view pointing the same way, volume at or above its
/// own average, and a set of similar past days that leaned the same way — and then throws the count
/// away, returning only "High" / "Medium" / "Low". The three states are already decided there; the
/// `Decision` shape just has nowhere to carry them. So the panel reads them back out of the two
/// strings that module already wrote: `secondLine` for the longer view, `confirmLine` for the other
/// two, and `confirmMissing` for the difference between "weak" and "never published".
///
/// No new rule is applied. Nothing here decides anything — it recognises what was decided. If a
/// sentence in lib/decision.ts is reworded, `gapLine` returns fewer parts and the line simply does
/// not print, which is the right way for this to fail: a panel that goes quiet, never one that
/// invents a weakness. The proper fix belongs in the file that owns the rules and is named in the
/// report alongside this change.
/// The four things `secondLine` in lib/decision.ts can say about the confirming view, and the
/// phrase each becomes here. Keyed on the stored sentence because that is the only handle the
/// `Decision` shape offers — see the note above.
///
/// The distinction this table exists to keep: **"nothing confirms it" is not "something
/// disagrees"**. Gate 5 turns a longer view pointing the other way into a WAIT before this panel
/// ever runs, so a LONG can only ever mean the second view agreed, was flat, added nothing, or
/// was not there at all. An earlier draft of this line printed "the longer view does not agree"
/// for all three of the last cases, and on Attock Refinery that put "the longer view does not
/// agree" directly above a Why line reading "Setup is up on the longer view" — which is the
/// contradictory tone this whole line was added to remove. The two phrases are about different
/// views: `why[0]`'s names the horizon the *setup* was read from, and this one names the view
/// that was meant to corroborate it.
const AGREES = "Longer view agrees.";
const SECOND_VIEW: ReadonlyArray<readonly [string, string]> = [
  ["Only one time frame points anywhere", "only one time frame points anywhere"],
  ["Longer view is flat", "the longer view is flat"],
  ["Longer view does not disagree", "the longer view adds nothing either way"],
];
const VOLUME_CONFIRMED = /volume [\d.]+x its average/;
const VOLUME_UNPUBLISHED = "No volume published";
// "going", matching the wording `confirmLine` builds in lib/decision.ts. The two must move
// together: this regex is how the reconcile line knows the analog set confirmed, and a
// mismatch here fails open and silently stops explaining a grade it should explain.
const DAYS_CONFIRMED = /similar days going the same way/;
// Three different absences share the words "similar past days", so matching on that phrase alone
// folded them into one sentence. Each gets its own test, most specific first, because "the lean
// was never recorded" is not "there is not enough history" — it was printed over 102 stored days
// on ATRL, which is plenty of history and none of it was the problem.
const DAYS_UNAVAILABLE = "similar past days";
const DAYS_UNRECORDED = "which way they went was not recorded";
const DAYS_TOO_FEW = "are needed to confirm";
const DAYS_NONE = "No similar past days stored";

/// The one line that explains a strong direction carrying a weak grade.
///
/// A reader shown LONG in 48px type next to the words "Low confidence" has been handed a
/// contradiction and left to resolve it. Both halves are true — the direction really did clear
/// every gate, and the evidence behind it really is thin — and the thing that reconciles them is
/// naming *which* leg is short. "Volume is weak" is a sentence a reader can act on; a grade on its
/// own is one they can only distrust.
///
/// Returns null when there is nothing to reconcile: a WAIT is not a strong direction, a High grade
/// is not a weak one, and if no weakness can be named then nothing is printed rather than hedged.
export function gapLine(decision: Decision): string | null {
  if (decision.action !== "LONG" && decision.action !== "SHORT") return null;
  if (decision.confidence === "High") return null;

  const why = decision.why.join(" ");
  const missing = decision.missing.join(" ");
  const weak: string[] = [];

  // The confirming view, named as whichever of the three non-agreeing states actually applies.
  // Nothing is pushed when none of them matches: an unrecognised sentence means lib/decision.ts
  // was reworded, and the right failure is a shorter line, never a guessed one.
  if (!decision.why.includes(AGREES)) {
    const second = SECOND_VIEW.find(([stored]) => why.includes(stored));
    if (second) weak.push(second[1]);
  }

  // Volume. Three states, and the third is the one worth separating: a ratio below its average is
  // a measurement that came out weak, while no ratio at all is a measurement nobody took. Telling
  // a reader volume is weak when the truth is that none is published is a quiet lie about evidence.
  if (!VOLUME_CONFIRMED.test(why)) {
    weak.push(missing.includes(VOLUME_UNPUBLISHED) ? "no volume is published" : "volume is weak");
  }

  // Similar past days. Four states, and they are not interchangeable: the set can lean against
  // the direction, be absent entirely, be too small to use, or be stored without its lean. The
  // full reason is printed under "What is missing" a few lines below, so this names the leg in a
  // clause and does not restate it — but the clause has to be true on its own terms.
  if (!DAYS_CONFIRMED.test(why)) {
    if (!missing.includes(DAYS_UNAVAILABLE)) {
      // Nothing was reported missing, so the leg was measured and came out against.
      weak.push("similar past days do not back it");
    } else if (missing.includes(DAYS_UNRECORDED)) {
      weak.push("the past days stored for it have no direction recorded");
    } else if (missing.includes(DAYS_NONE) || missing.includes(DAYS_TOO_FEW)) {
      weak.push("there is not enough history to compare");
    }
  }

  if (!weak.length) return null;

  const trend = decision.action === "LONG" ? "up" : "down";
  // Oxford-less "a, b and c", because this is a sentence and not a list, and it has to still read
  // as one sentence after wrapping to three lines at 375px.
  const list =
    weak.length === 1
      ? weak[0]
      : `${weak.slice(0, -1).join(", ")} and ${weak[weak.length - 1]}`;
  return `The trend is clearly ${trend}, but ${list}, so confidence is only ${decision.confidence.toLowerCase()}.`;
}
