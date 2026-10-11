/// The decision history and the simulated trades, as the logbook prints them (brain.md rule 95).
///
/// Runs come from "DecisionRun" (tools/decide.mjs), which records every pass once and never rewrites it;
/// the current run of a day is the newest one that finished. The trade summary is the one
/// tools/trade_sim.py stores as the day's "trades" entry in the logbook table: counts and rates over the
/// first published call of each position, each rate with its count, kept apart from directional accuracy.
/// Nothing here computes a grade: it reads, checks the shape and words what it read.

export interface RunRow {
  id: string;
  periodEnd: string;
  pass: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  commit: string | null;
  trigger: string | null;
  servedFrom: string | null;
  fingerprint: string | null;
  assets: number;
  written: number;
  published: number;
}

/// Each run with whether it is its day's current one: the newest run of that day that finished
/// ("complete" or "partial"). A failed run, or one still running, is never current.
export function markCurrent(runs: RunRow[]): (RunRow & { current: boolean })[] {
  const current = new Map<string, string>();
  for (const r of runs) {
    if (r.status !== "complete" && r.status !== "partial") continue;
    const prev = current.get(r.periodEnd);
    const prevRun = prev ? runs.find((x) => x.id === prev) : undefined;
    if (!prevRun || r.startedAt > prevRun.startedAt) current.set(r.periodEnd, r.id);
  }
  return runs.map((r) => ({ ...r, current: current.get(r.periodEnd) === r.id }));
}

export interface Rate {
  k: number;
  n: number;
  rate: number | null;
}

export interface TradeBucket {
  calls: number;
  evaluable: number;
  pending: number;
  trades: Record<string, number>;
  fillRate: Rate;
  targetFirst: Rate;
  stopFirst: Rate;
  expired: Rate;
  ambiguous: Rate;
  gapThrough: number;
  grossRExpectancy: { n: number; mean: number | null; measured: boolean };
  direction: { judged: number; right: number; wrong: number; stopped: number; flat: number; pending: number; accurate: Rate };
}

export interface TradeSummary {
  asOf: string;
  since: string | null;
  minSample: number;
  all: TradeBucket;
  byMarket: Record<string, TradeBucket>;
  bySide: Record<string, TradeBucket>;
  byHorizon: Record<string, TradeBucket>;
  byConfidence: Record<string, TradeBucket>;
  assumptions: string[];
}

const isRate = (x: unknown): x is Rate =>
  !!x && typeof x === "object" && Number.isInteger((x as Rate).k) && Number.isInteger((x as Rate).n);

function isBucket(x: unknown): x is TradeBucket {
  const b = x as TradeBucket;
  return (
    !!b &&
    typeof b === "object" &&
    Number.isInteger(b.calls) &&
    isRate(b.fillRate) &&
    isRate(b.targetFirst) &&
    isRate(b.stopFirst) &&
    !!b.trades &&
    !!b.grossRExpectancy &&
    !!b.direction
  );
}

/// The stored summary, or null when it is missing or not the shape tools/trade_sim.py writes.
export function toTradeSummary(lines: unknown): TradeSummary | null {
  const s = lines as TradeSummary;
  if (!s || typeof s !== "object" || typeof s.asOf !== "string" || !Number.isInteger(s.minSample) || !isBucket(s.all)) return null;
  for (const k of ["byMarket", "bySide", "byHorizon", "byConfidence"] as const) {
    if (!s[k] || typeof s[k] !== "object" || !Object.values(s[k]).every(isBucket)) return null;
  }
  return { ...s, assumptions: Array.isArray(s.assumptions) ? s.assumptions.map(String) : [] };
}

/// A rate as printed: always with its count, and a dash when nothing was counted.
export function rateText(r: Rate): string {
  if (r.n === 0 || r.rate === null) return "— (0)";
  return `${Math.round(r.rate * 100)}% (${r.k} of ${r.n})`;
}

/// The expectancy as printed: "not measured" until the sample the scorecard requires.
export function expectancyText(e: TradeBucket["grossRExpectancy"], minSample: number): string {
  if (e.n === 0 || e.mean === null) return `not measured (0 closed trades)`;
  const r = `${e.mean >= 0 ? "+" : ""}${e.mean.toFixed(2)}R over ${e.n}`;
  return e.measured ? r : `${r}: not measured, ${minSample} closed trades are needed`;
}
