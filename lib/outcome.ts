/// Outcome status: whether the calls have demonstrated anything in matured results (brain.md rule 94).
///
/// It is a different question from the evidence grade, and the two were briefly confused. The grade
/// (High / Medium / Low) says how much independent evidence backs *this reading*: how many of the five
/// confirmations are present. Outcome status says whether readings like it have been *right*, measured on
/// calls whose five-session window has closed. Rule 93 capped the grade at Medium until outcomes matured,
/// which answered the second question with the first's label; rule 94 withdrew the cap and prints both,
/// side by side, so neither can be read as the other.
///
/// The counts are the logbook's own (`tools/audit_log.py`, stored as the `summary` entry and read by
/// `getLogbookSummary`): every directional call logged, graded by the scorecard's verdict -- stop first,
/// then the sign of the five-session move. One source, so the logbook, the asset pages, the lists and
/// `/api/signals` cannot disagree about it.

/// Matured calls needed before a rate is reported as a measurement. Equal to `MIN_SAMPLE` in
/// tools/scorecard.py, which a test pins.
export const OUTCOME_MIN_SAMPLE = 30;

export interface OutcomeStatus {
  status: "untested" | "pending" | "validated" | "not validated";
  graded: number;
  accurate: number;
  /// Share graded accurate, and its 95% Wilson interval; null until `OUTCOME_MIN_SAMPLE` are graded.
  rate: number | null;
  interval: [number, number] | null;
  sentence: string;
}

/// The 95% Wilson score interval for k of n. Chosen over the normal approximation because it stays inside
/// [0, 1] and behaves at small n, which is where this site will be for weeks.
export function wilson(k: number, n: number): [number, number] {
  if (n <= 0) return [0, 1];
  const z = 1.959964;
  const p = k / n;
  const den = 1 + (z * z) / n;
  const mid = (p + (z * z) / (2 * n)) / den;
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / den;
  return [Math.max(0, mid - half), Math.min(1, mid + half)];
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

/// The counts outcome status reads from a logbook summary: the published calls when the summary has them,
/// which is what readers were shown; every logged call only for a summary written before they were counted.
export function outcomeCounts(
  s: { graded: number; accurate: number; publishedGraded?: number | null; publishedAccurate?: number | null } | null | undefined,
): { graded: number; accurate: number } | null {
  if (!s) return null;
  if (s.publishedGraded != null && s.publishedAccurate != null) return { graded: s.publishedGraded, accurate: s.publishedAccurate };
  return { graded: s.graded, accurate: s.accurate };
}

export function outcomeStatusOf(summary: { graded: number; accurate: number } | null | undefined): OutcomeStatus {
  const graded = summary && Number.isInteger(summary.graded) && summary.graded >= 0 ? summary.graded : 0;
  const accurate = summary && Number.isInteger(summary.accurate) && summary.accurate >= 0 ? Math.min(summary.accurate, graded) : 0;
  if (graded === 0) {
    return {
      status: "untested",
      graded,
      accurate,
      rate: null,
      interval: null,
      sentence: "Outcome: untested. No published call has a matured five-session result yet, so no edge is claimed.",
    };
  }
  if (graded < OUTCOME_MIN_SAMPLE) {
    return {
      status: "pending",
      graded,
      accurate,
      rate: null,
      interval: null,
      sentence: `Outcome: pending. ${graded} of the ${OUTCOME_MIN_SAMPLE} matured five-session results needed before a rate is reported.`,
    };
  }
  const rate = accurate / graded;
  const interval = wilson(accurate, graded);
  const validated = interval[0] > 0.5;
  return {
    status: validated ? "validated" : "not validated",
    graded,
    accurate,
    rate,
    interval,
    sentence: `Outcome: ${validated ? "validated" : "not validated"}. ${accurate} of ${graded} matured published calls were accurate after five sessions (${pct(rate)}, 95% interval ${pct(interval[0])} to ${pct(interval[1])})${validated ? "" : "; the interval does not clear 50%"}.`,
  };
}
