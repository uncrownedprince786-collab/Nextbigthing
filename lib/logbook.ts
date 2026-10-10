/// The logbook's stored lines, read back into what the page renders.
///
/// `tools/audit_log.py` stores each entry as `[text, style]` pairs. This reads them defensively -- the
/// column is JSON written by another program -- and classifies each line once, so the page only has to
/// draw: a rule for a divider, a heading, a bold line, or plain text with its indentation kept.

export type LogLine =
  | { kind: "rule" }
  | { kind: "title"; text: string }
  | { kind: "heading"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "text"; text: string; indent: number };

export function toLines(stored: unknown): LogLine[] {
  if (!Array.isArray(stored)) return [];
  const out: LogLine[] = [];
  for (const item of stored) {
    if (!Array.isArray(item)) continue;
    const text = typeof item[0] === "string" ? item[0] : "";
    const style = typeof item[1] === "string" ? item[1] : "";
    if (/^[=-]{10,}$/.test(text.trim())) {
      out.push({ kind: "rule" });
    } else if (!text.trim()) {
      continue;
    } else if (style === "title" || style === "heading" || style === "bold") {
      out.push({ kind: style, text: text.trim() });
    } else {
      const indent = text.length - text.trimStart().length;
      out.push({ kind: "text", text: text.trim(), indent });
    }
  }
  // Two rules in a row (the review's double divider) draw as one.
  return out.filter((l, i) => !(l.kind === "rule" && out[i - 1]?.kind === "rule"));
}

/// The summary the logbook leads with, stored by the same job as one row of kind "summary".
export type Flip = { day: string; symbol: string; name: string; from: "LONG" | "SHORT"; to: "LONG" | "SHORT" };
export type Star = { day: string; symbol: string; name: string; direction: "up" | "down"; result: "accurate" | "failed" | "flat" | "pending" };
export type Summary = {
  asOf: string;
  graded: number;
  accurate: number;
  failed: number;
  accuratePct: number | null;
  failedPct: number | null;
  flips: Flip[];
  /// How many flips and stars the 30 days held; the lists keep only the newest.
  flipsTotal: number;
  stars: Star[];
  starsTotal: number;
  starsGraded: number;
  starsAccurate: number;
  starsAccuratePct: number | null;
  /// Calls the evidence rules alone would have held back, which lib/resolve.ts gave a side.
  forcedGraded: number;
  forcedAccurate: number;
  forcedAccuratePct: number | null;
};

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const count = (v: unknown) => (typeof v === "number" && Number.isInteger(v) && v >= 0 ? v : null);
const pct = (v: unknown) => (typeof v === "number" && v >= 0 && v <= 100 ? Math.round(v) : null);
const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : null);
const obj = (v: unknown) => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null);

/// Reads the stored summary back, or null when it is missing or malformed. Bad list items are dropped,
/// never guessed at; a rate is kept only when it is a real percentage.
export function toSummary(stored: unknown): Summary | null {
  const s = obj(stored);
  const asOf = s && str(s.asOf);
  if (!s || !asOf || !DAY.test(asOf)) return null;
  const graded = count(s.graded);
  const accurate = count(s.accurate);
  const failed = count(s.failed);
  if (graded === null || accurate === null || failed === null || accurate + failed > graded) return null;
  const side = (v: unknown) => (v === "LONG" || v === "SHORT" ? v : null);
  const flips: Flip[] = [];
  for (const item of Array.isArray(s.flips) ? s.flips : []) {
    const f = obj(item);
    const day = f && str(f.day);
    const symbol = f && str(f.symbol);
    const from = f && side(f.from);
    const to = f && side(f.to);
    if (f && day && DAY.test(day) && symbol && from && to && from !== to) {
      flips.push({ day, symbol, name: str(f.name) ?? symbol, from, to });
    }
  }
  const stars: Star[] = [];
  for (const item of Array.isArray(s.stars) ? s.stars : []) {
    const x = obj(item);
    const day = x && str(x.day);
    const symbol = x && str(x.symbol);
    const direction = x && (x.direction === "up" || x.direction === "down" ? x.direction : null);
    const result = x && (["accurate", "failed", "flat", "pending"].includes(x.result as string) ? (x.result as Star["result"]) : null);
    if (x && day && DAY.test(day) && symbol && direction && result) {
      stars.push({ day, symbol, name: str(x.name) ?? symbol, direction, result });
    }
  }
  return {
    asOf,
    graded,
    accurate,
    failed,
    accuratePct: graded ? pct(s.accuratePct) : null,
    failedPct: graded ? pct(s.failedPct) : null,
    flips,
    flipsTotal: Math.max(count(s.flipsTotal) ?? 0, flips.length),
    stars,
    starsTotal: Math.max(count(s.starsTotal) ?? 0, stars.length),
    starsGraded: count(s.starsGraded) ?? 0,
    starsAccurate: count(s.starsAccurate) ?? 0,
    starsAccuratePct: count(s.starsGraded) ? pct(s.starsAccuratePct) : null,
    forcedGraded: count(s.forcedGraded) ?? 0,
    forcedAccurate: count(s.forcedAccurate) ?? 0,
    forcedAccuratePct: count(s.forcedGraded) ? pct(s.forcedAccuratePct) : null,
  };
}
