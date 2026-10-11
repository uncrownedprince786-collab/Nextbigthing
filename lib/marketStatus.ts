import type { Scored } from "@/lib/assetClass";

/// The market status record and its run state (brain.md rules 93 and 95), apart from lib/assetClass.ts so
/// it imports nothing at run time and its tests can run it rather than read it.

/// Where a market stands after the decision runs, as one value (brain.md rule 95). The overview and the
/// market page both print it from this record, so they cannot disagree: the overview once told readers
/// commodities had "not been through a run" -- because none of its names was a published call -- while
/// /commodities reported the run of 2026-10-11 complete with 1 withheld, 5 forming and 2 held back.
///
///   RUN_COMPLETE_WITH_CALLS           the newest run logged every name here, and at least one call is published
///   RUN_COMPLETE_NO_PUBLISHED_CALLS   the newest run logged every name here, and none passed the quality gate
///   RUN_INCOMPLETE_OR_FAILED          this market is missing from the newest run, or only some names were logged
///   NO_READING                        no decision run has logged this market at all
export type RunState = "RUN_COMPLETE_WITH_CALLS" | "RUN_COMPLETE_NO_PUBLISHED_CALLS" | "RUN_INCOMPLETE_OR_FAILED" | "NO_READING";

/// What one market's page can say about its own state (rule 93): the newest stored close, the newest
/// decision run it was part of, and where every name went -- so "no call today" can be told apart from
/// "the run never reached this market", "the source failed" and "no price is stored". Counted from the
/// same scored rows the page lists, so the sentence cannot disagree with the rows under it.
export interface MarketStatus {
  runState: RunState;
  /// Names with a row in the newest run that logged this market.
  logged: number;
  names: number;
  latestClose: string | null;
  /// The newest decision run that logged a row for this market, and the newest run of any market.
  decidedOn: string | null;
  latestRun: string | null;
  processed: boolean;
  longs: number;
  shorts: number;
  withheld: number;
  forming: number;
  heldBack: { ended: number; noPrice: number; stale: number; silent: number; other: number };
  /// The price source for this market and its last coverage status, when one is recorded.
  source: { label: string; status: string } | null;
}

const dayText = (d: Date | string | null | undefined): string | null => {
  if (!d) return null;
  const t = d instanceof Date ? d.getTime() : Date.parse(String(d).slice(0, 10) + "T00:00:00Z");
  return Number.isFinite(t) ? new Date(t).toISOString().slice(0, 10) : null;
};

export function marketStatus(
  mine: Scored[],
  all: Scored[],
  health: { source: string; status: string }[],
  sourceLabel: string | null,
): MarketStatus {
  const newest = (xs: (string | null)[]) => xs.reduce<string | null>((m, d) => (d && (!m || d > m) ? d : m), null);
  const waits = mine.filter((s) => s.decision.action === "WAIT");
  const decidedOn = newest(mine.map((s) => dayText(s.row.callLatest)));
  const latestRun = newest(all.map((s) => dayText(s.row.callLatest)));
  const src = sourceLabel ? health.find((h) => h.source === sourceLabel) ?? (sourceLabel.startsWith("Yahoo Finance daily closes (") ? health.find((h) => h.source === "Yahoo Finance daily closes") : undefined) : undefined;
  const gateOf = (s: Scored) => s.decision.gate;
  const processed = decidedOn !== null && decidedOn === latestRun;
  const logged = decidedOn ? mine.filter((s) => dayText(s.row.callLatest) === decidedOn).length : 0;
  const longs = mine.filter((s) => s.decision.action === "LONG" && isPublishedRow(s)).length;
  const shorts = mine.filter((s) => s.decision.action === "SHORT" && isPublishedRow(s)).length;
  return {
    runState: runStateOf({ names: mine.length, decidedOn, processed, logged, published: longs + shorts }),
    logged,
    names: mine.length,
    latestClose: newest(mine.map((s) => dayText(s.row.closeDate))),
    decidedOn,
    latestRun,
    processed,
    longs,
    shorts,
    withheld: mine.filter((s) => s.decision.action !== "WAIT" && !isPublishedRow(s)).length,
    forming: waits.filter((s) => s.decision.developing !== null).length,
    heldBack: {
      ended: waits.filter((s) => gateOf(s) === "stop-crossed").length,
      noPrice: waits.filter((s) => gateOf(s) === "no-prices").length,
      stale: waits.filter((s) => gateOf(s) === "stale" || gateOf(s) === "bad-date").length,
      silent: waits.filter((s) => gateOf(s) === "source-silent").length,
      other: waits.filter(
        (s) => s.decision.developing === null && !["stop-crossed", "no-prices", "stale", "bad-date", "source-silent"].includes(gateOf(s)),
      ).length,
    },
    source: src && sourceLabel ? { label: src.source, status: src.status } : null,
  };
}

export function runStateOf(m: { names: number; decidedOn: string | null; processed: boolean; logged: number; published: number }): RunState {
  if (m.names === 0 || m.decidedOn === null) return "NO_READING";
  if (!m.processed || m.logged < m.names) return "RUN_INCOMPLETE_OR_FAILED";
  return m.published > 0 ? "RUN_COMPLETE_WITH_CALLS" : "RUN_COMPLETE_NO_PUBLISHED_CALLS";
}

function isPublishedRow(s: Scored): boolean {
  return s.gate ? s.gate.published : true;
}

/// The status as the sentences a page prints, in the order a reader needs them.
export function marketStatusLines(m: MarketStatus): string[] {
  const lines: string[] = [];
  lines.push(`${m.names} ${m.names === 1 ? "name" : "names"}, newest close stored ${m.latestClose ?? "none"}.`);
  if (!m.decidedOn) lines.push("No decision run has logged this market yet.");
  else if (!m.processed) lines.push(`Not processed in the latest run (${m.latestRun}): its newest decision is from ${m.decidedOn}.`);
  else if (m.logged < m.names) lines.push(`Decision run of ${m.decidedOn} reached ${m.logged} of these ${m.names} names; the rest have no row in it.`);
  else lines.push(`Decision run of ${m.decidedOn} completed for this market.`);
  if (m.source && m.source.status !== "healthy") lines.push(`Price source ${m.source.label}: ${m.source.status}.`);
  const published = m.longs + m.shorts;
  lines.push(
    published
      ? `${m.longs} long, ${m.shorts} short published.`
      : "No call passed the quality gate today.",
  );
  const rest: string[] = [];
  if (m.withheld) rest.push(`${m.withheld} withheld by the quality gate`);
  if (m.forming) rest.push(`${m.forming} forming`);
  if (m.heldBack.ended) rest.push(`${m.heldBack.ended} ended at their stop`);
  if (m.heldBack.noPrice) rest.push(`${m.heldBack.noPrice} with no stored price`);
  if (m.heldBack.stale) rest.push(`${m.heldBack.stale} with a stale price`);
  if (m.heldBack.silent) rest.push(`${m.heldBack.silent} whose source answered nothing`);
  if (m.heldBack.other) rest.push(`${m.heldBack.other} held back by the rule table`);
  if (rest.length) lines.push(rest.join(", ") + ".");
  return lines;
}
