// Reading the `conditions` string that `jobs/setup.py` writes on every `AssetSetup` row.
//
// **Why this exists at all.** 162 of 266 swing rows on 2026-10-07 are in state `wait`, which is
// not the neutral state: it means *the trend is clear and not all the conditions behind it are
// present*. `directionOfState` maps it to `flat`, and the rule table's fall-through prints "a
// direction is showing, but not all the conditions behind it are present". True, and it throws
// away the one thing the reader most wants to know — **which way**. The direction is stored. It
// is the verdict on the `trend` condition, inside this string, and nothing in the web layer was
// reading it.
//
// **The twin, declared.** `verdicts()` in `jobs/thesis.py` parses the same format for the same
// reason, and rule 23 in brain.md exists because that parser and `setup.py`'s writer must agree.
// There are now two parsers of one format, which is the shape rule 36 warns about, so: this is
// the only other one, both are tested against the same literal strings taken from `setup.py`'s
// own output, and a new horizon written in a new format breaks both tests rather than silently
// producing theses with nothing to compare and a developing list with no direction.

/// The verdict tokens `jobs/setup.py` writes. Same set as `VERDICTS` in `jobs/thesis.py`.
///
/// A condition carrying none is left out rather than defaulted, because a default manufactures
/// agreement or disagreement out of a sentence that stated neither: "position: 45% of the way up
/// its range" states a value and passes no judgement.
const VERDICTS = new Set(["pass", "fail", "up", "down", "mixed"]);

export type TrendDirection = "up" | "down" | "mixed";

/// Parse a stored `conditions` string into {condition name: verdict}.
///
/// `setup.py` writes each condition as "name: text (verdict)", pipe separated. The verdict is the
/// last comma-separated token inside the final bracket, which is what makes "(60%, pass)" and
/// "(up)" both parse without a rule per condition.
export function conditionVerdicts(conditions: string | null | undefined): Map<string, string> {
  const found = new Map<string, string>();
  if (!conditions) return found;
  for (const raw of conditions.split(" | ")) {
    const part = raw.trim();
    const colon = part.indexOf(":");
    if (colon < 0) continue;
    const name = part.slice(0, colon).trim();
    const rest = part.slice(colon + 1).trimEnd();
    if (!rest.endsWith(")")) continue;
    const open = rest.lastIndexOf("(");
    if (open < 0) continue;
    const token = rest.slice(open + 1, -1).split(",").pop()?.trim().toLowerCase() ?? "";
    if (VERDICTS.has(token)) found.set(name, token);
  }
  return found;
}

/// Which way the trend read, from the condition `setup.py` records it on.
///
/// Null when the row carries no trend verdict at all, which is a different answer from `mixed`:
/// `mixed` is a measurement that came back without a direction, and null is a row that was never
/// written in this format. Rule 21 — absent and inconclusive are two values.
export function trendDirectionOf(conditions: string | null | undefined): TrendDirection | null {
  const token = conditionVerdicts(conditions).get("trend");
  return token === "up" || token === "down" || token === "mixed" ? token : null;
}
