import type { DecisionQueryRow } from "@/lib/queries";
import { pickTarget, targetForCall, type TargetLike } from "@/lib/target";
import { openSince, qualityGate, withOpenPosition, type GateResult } from "@/lib/quality";
import { bundleFromRow, toDecisionInput, todayISO } from "@/lib/decisionInput";
import { decideCall } from "@/lib/resolve";
import { quoteBesideClose } from "@/lib/liveQuote";
import { executionOf, type Execution } from "@/lib/execution";
import { validityOf } from "@/lib/validity";
import { earlySignalOf } from "@/lib/earlySignal";
import { latestChange } from "@/lib/stateChange";
import {
  CONFIDENCE_ORDER,
  EVENT_SOON_DAYS,
  type Decision,
  type Market,
} from "@/lib/decision";
import type { DecisionRow } from "@/components/decision";

/// The four asset classes the site is browsed by, and the pieces every page that lists them shares.
///
/// This module exists because there are now five surfaces reading the same rows -- the overview and
/// one index per class -- and the alternative was five copies of "turn a stored row into a verdict
/// and then into a list row". A second copy of that is how two pages come to disagree about what a
/// name is, which is the one thing `lib/decision.ts` is structured to prevent. The rule table is
/// still the only thing that decides; nothing here adds a rule.

/// One asset, read once: the stored row, the rule table's input, and the verdict.
///
/// The mapped `market` is kept beside the decision because it lives on the input. Taking the market
/// off the raw query row instead would print "PK" where the rest of the site says "PSX" and would
/// file every crypto name under whichever industry market it happens to sit in.
export interface Scored {
  row: DecisionQueryRow;
  market: Market;
  decision: Decision;
  /// Which stored setup decided ("swing" or "longer"), for the trade horizon. Optional so a caller
  /// that builds a Scored by hand keeps compiling; absent is read as the default daily horizon.
  setupHorizon?: string | null;
  /// The `today` the row was decided against, so the validity window is measured on the same day.
  today?: string;
  /// The measured exit the row shows and the quality gate's verdict on it (lib/quality.ts). Optional so a
  /// hand-built Scored keeps compiling; `scoreRows` always sets both.
  target?: TargetLike | null;
  gate?: GateResult;
  /// "SWING" or "POSITION": the trading style of the setup that decided; null on a WAIT.
  style?: string | null;
  /// Whether the direction can be acted on, apart from whether it is right (lib/execution.ts).
  execution?: Execution | null;
}

export { isPublished } from "@/lib/quality";

/// The measured exit for a row, from the one rule every surface shares.
export function rowTarget(row: DecisionQueryRow, decision: Decision): TargetLike | null {
  return targetForCall(
    pickTarget(
      [
        row.swing ? { ...row.swing, horizon: "swing" } : null,
        row.longer ? { ...row.longer, horizon: "longer" } : null,
      ].filter((x): x is NonNullable<typeof x> => x !== null),
    ),
    decision,
  );
}

/// Every row scored against one `today` and one source-health reading.
///
/// Both are passed in rather than read here, and that is the whole point of the signature: a page
/// that fetched `today` twice could decide half its names on one date and half on the next, and a
/// page that fetched source health twice could show a name as silent in one list and current in
/// another. One call, one answer, passed down.
export function scoreRows(
  rows: DecisionQueryRow[],
  health: Parameters<typeof bundleFromRow>[1],
  today: string,
): Scored[] {
  return rows.map((row) => {
    const input = toDecisionInput(bundleFromRow(row, health), today);
    const decision = decideCall(input);
    const target = rowTarget(row, decision);
    const setupHorizon = input.setup?.horizon ?? null;
    // The trading style is the window of the setup that decided (lib/validity.ts): Swing or Position.
    const validity = validityOf({
      action: decision.action,
      setupHorizon,
      runAction: row.callAction,
      runSince: row.callSince,
      asOf: row.closeDate,
      today,
    });
    const style = validity ? validity.label.toUpperCase() : null;
    const since = openSince({
      action: decision.action,
      publishedAction: row.publishedAction,
      publishedOn: row.publishedOn,
      lastRunAction: row.lastRunAction,
      lastRunSince: row.lastRunSince,
      validityStatus: validity?.status ?? null,
    });
    return {
      row,
      market: input.market,
      decision,
      setupHorizon,
      today,
      target,
      style,
      gate: withOpenPosition(qualityGate(decision, target, input.atr ?? null, style), since),
      execution: executionOf({ action: decision.action, closeVolume: row.closeVolume, market: input.market }),
    };
  });
}

// Re-exported from the rule table, where it now lives beside the `Confidence` type. One
// declaration, so a grade cannot sort one way here and another way in the weekly block.
export { CONFIDENCE_ORDER } from "@/lib/decision";

/// Developing rows, nearest to confirming first.
///
/// `closeness` is the stored factor over the threshold it has to clear, so 0.96 is a name 4%
/// short of its volume gate and 0.25 is one nowhere near it. A null sorts last, because a
/// confirmation that cannot be measured is not one that is nearly there -- rule 21 again, in the
/// one place where collapsing the two would read as a recommendation.
///
/// Within equal closeness the symbol decides, so two identical rows do not swap places between
/// two reads of the same page.
///
/// It lives here beside the other two orderings rather than in `app/page.tsx`, where it was
/// written, because the class indexes now split their waiting list the same way the overview
/// does and two copies of one ordering is how `/crypto` comes to rank its forming names
/// differently from the front page.
export function byCloseness(a: Scored, b: Scored): number {
  const ca = a.decision.developing?.closeness;
  const cb = b.decision.developing?.closeness;
  const ka = ca === null || ca === undefined ? -1 : ca;
  const kb = cb === null || cb === undefined ? -1 : cb;
  if (ka !== kb) return kb - ka;
  return a.row.symbol.localeCompare(b.row.symbol);
}

/// Strongest evidence first, then alphabetical so the order is stable between two reads.
export function byConfidence(a: Scored, b: Scored): number {
  const c = CONFIDENCE_ORDER[a.decision.confidence] - CONFIDENCE_ORDER[b.decision.confidence];
  return c !== 0 ? c : a.row.symbol.localeCompare(b.row.symbol);
}

const ACTION_ORDER = { LONG: 0, SHORT: 0, WAIT: 1 } as const;

/// The order a class index and the overview's short lists are built in.
///
/// Something to do before nothing to do, then strongest evidence, then alphabetical. LONG and SHORT
/// share a rank deliberately: they are both an answer, and sorting one above the other would make
/// the top of every list a direction rather than a reading.
///
/// This is not a score and nothing is weighted. It is the order the reader asked the page a question
/// in: is there anything here, and if so which of it is best evidenced.
export function byOpportunity(a: Scored, b: Scored): number {
  const act = ACTION_ORDER[a.decision.action] - ACTION_ORDER[b.decision.action];
  if (act !== 0) return act;
  return byConfidence(a, b);
}

/// The calendar line, when the calendar is the reason a row is urgent.
///
/// Separate from `decision.why` on purpose: a dated event does not gate the rule table -- it only
/// sets the time sense -- so a row that is in WAIT for a stale close and happens to report earnings
/// today would otherwise say nothing about today.
export function eventLabel(row: DecisionQueryRow): string | null {
  const days = row.nextEventInDays;
  if (days === null || days > EVENT_SOON_DAYS) return null;
  const name = row.nextEventName ?? "a dated event";
  if (days <= 0) return `Event today: ${name}.`;
  return `Event in ${days} ${days === 1 ? "day" : "days"}: ${name}.`;
}

/// A scored row as `DecisionList` wants it.
export function toListRow(s: Scored): DecisionRow {
  return {
    symbol: s.row.symbol,
    name: s.row.name,
    market: s.market,
    action: s.decision.action,
    // The newest stored close, so the three levels beside it have something to be read against.
    // It comes off the same query row the decision was built from, not a second read, so a
    // table cannot show one price while its own verdict was computed from another.
    priceNow: s.row.close,
    // The sector heading this row belongs under, and the order sectors appear in. Carried on
    // the row rather than looked up by the list, so a list never has to know what an industry
    // is -- it groups by two fields it was handed.
    sector: s.row.sector,
    sectorSort: s.row.sectorSort,
    // A held-back row prints no levels (rule 93): an entry zone, a stop and an exit beside "Held back"
    // read as a trade the rule table did not make. Its reason is in the row.
    entry: s.decision.action === "WAIT" ? null : s.decision.entry,
    invalidation: s.decision.action === "WAIT" ? null : s.decision.invalidation,
    // A call that ended at its stop (rule 92): its cells say so rather than "not measured".
    ended: s.decision.action === "WAIT" && s.decision.gate === "stop-crossed",
    // The measured exit if it works, from the one rule every surface shares. A row that names
    // only the level it is wrong at answers half the question a reader has.
    target: s.decision.action === "WAIT" ? null : s.target !== undefined ? s.target : rowTarget(s.row, s.decision),
    execution: s.execution ?? null,
    // An open call published only because it is open: the line under the verdict says so.
    held: s.gate?.held ?? null,
    confidence: s.decision.confidence,
    // Which confirmations backed it. The table prints how many and which, because a grade of
    // "Medium" says one thing was behind a call and not what it was.
    legs: s.decision.legs,
    // The rising-star marker: the measured entry event, if one fired, and how it sits with the call.
    // The same function the asset page uses, fed the same two stored columns.
    // A verdict change made in the newest decision cycle, from the log, and what kind it was.
    change: latestChange({
      action: s.decision.action,
      runAction: s.row.callAction,
      runSince: s.row.callSince,
      runPrev: s.row.callPrev,
      runGate: s.row.callGate,
      latestCycle: s.row.callLatest,
    }),
    early: earlySignalOf(s.row.entryTrigger, s.row.triggerDirection, s.decision.action),
    // The close's own day, printed under the price so "last close" is never read as "now".
    closeDate: s.row.closeDate ? new Date(s.row.closeDate).toISOString().slice(0, 10) : null,
    // How long the call is meant to run and how long it has been running. One function shared with
    // the asset page, so the two cannot show different windows for one name.
    validity: validityOf({
      action: s.decision.action,
      setupHorizon: s.setupHorizon,
      runAction: s.row.callAction,
      runSince: s.row.callSince,
      asOf: s.row.closeDate,
      today: s.today ?? todayISO(),
    }),
    // The last trade, only where it adds something beside the close printed next to it.
    quote: quoteBesideClose(
      s.row.quotePrice !== null && s.row.quoteAt ? { price: s.row.quotePrice, quotedAt: s.row.quoteAt } : null,
      { price: s.row.close, date: s.row.closeDate },
    ),
    // Why there is no call, in the rule table's own words, for a WAIT only. A held-back row used to
    // print a grade of Low and a dash, which says nothing; the reason is what the reader came for.
    reason: s.decision.action === "WAIT" ? s.decision.why.slice(0, 2) : null,
    // PSX names are in rupees. Without this every level on the page would be printed with a dollar
    // mark in front of a rupee number, which is worse than printing no level at all.
    currency: s.row.currency,
    // A dated event never gates the rule table, so a LONG row with earnings tomorrow carries no
    // hint of it in `why` -- it reaches the reader only through the time sense.
    timeSense: s.decision.timeSense,
    eventNote: eventLabel(s.row),
  };
}

export type AssetClassSlug = "stocks" | "crypto" | "psx" | "forex" | "commodities";

export interface AssetClass {
  slug: AssetClassSlug;
  /// The word in the header nav. One or two syllables; the nav is already seven items long.
  nav: string;
  /// The page's own heading, which may be longer than the nav word and has to be exact about
  /// what is in the list.
  title: string;
  /// One sentence under the heading. What is covered, and what the figures are.
  lead: string;
  /// Which scored rows belong to this class.
  ///
  /// Decided on the mapped `Market`, never on the symbol and never on the industry column. The
  /// trap this avoids is a real one and is documented in `marketOf`: the ticker PSX is a US asset
  /// (Phillips 66, seeded under `energy`), so a symbol is never a market test.
  holds: (s: Scored) => boolean;
}

export const ASSET_CLASSES: AssetClass[] = [
  {
    slug: "stocks",
    nav: "Stocks",
    title: "US stocks and funds",
    lead:
      "Every US listed name the site covers, with one reading each. Prices and levels are in US " +
      "dollars. The funds that hold a metal are here, because that is what they are; the " +
      "contracts on the metal itself are under Commodities.",
    holds: (s) => s.market === "US",
  },
  {
    slug: "psx",
    nav: "PSX",
    title: "Pakistan Stock Exchange",
    lead:
      "Every Karachi listed name the site covers, with one reading each. Prices and levels are " +
      "in rupees, so they do not compare with the dollar figures elsewhere on the site.",
    holds: (s) => s.market === "PSX",
  },
  {
    slug: "crypto",
    nav: "Crypto",
    title: "Crypto",
    lead:
      "Every coin the site covers, with one reading each. Crypto trades every day, so a close " +
      "two days old is already treated as stale here where five days is allowed for a share.",
    holds: (s) => s.market === "Crypto",
  },
  {
    slug: "forex",
    nav: "Forex",
    title: "Currencies",
    lead:
      "Every pair the site covers, with one reading each. A pair has no issuer, so there is no " +
      "size figure and no published volume anywhere on this page -- those columns are absent " +
      "rather than zero.",
    holds: (s) => s.market === "FX",
  },
  {
    slug: "commodities",
    nav: "Commodities",
    title: "Commodities",
    lead:
      "Gold, silver, platinum, palladium, copper, crude oil and natural gas, as the front " +
      "month contract on each. A contract has no issuer, so there is no size figure -- but " +
      "unlike a currency pair it does have a published volume, so the volume confirmation " +
      "applies here the same way it does to a share.",
    holds: (s) => s.market === "Commodity",
  },
];

/// What one market's page can say about its own state (rule 93): the newest stored close, the newest
/// decision run it was part of, and where every name went -- so "no call today" can be told apart from
/// "the run never reached this market", "the source failed" and "no price is stored". Counted from the
/// same scored rows the page lists, so the sentence cannot disagree with the rows under it.
export interface MarketStatus {
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
  const src = sourceLabel ? health.find((h) => h.source === sourceLabel) : undefined;
  const gateOf = (s: Scored) => s.decision.gate;
  return {
    names: mine.length,
    latestClose: newest(mine.map((s) => dayText(s.row.closeDate))),
    decidedOn,
    latestRun,
    processed: decidedOn !== null && decidedOn === latestRun,
    longs: mine.filter((s) => s.decision.action === "LONG" && isPublishedRow(s)).length,
    shorts: mine.filter((s) => s.decision.action === "SHORT" && isPublishedRow(s)).length,
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
    source: src && sourceLabel ? { label: sourceLabel, status: src.status } : null,
  };
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

export function classBySlug(slug: string): AssetClass | null {
  return ASSET_CLASSES.find((c) => c.slug === slug) ?? null;
}
