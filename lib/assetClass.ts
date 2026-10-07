import type { DecisionQueryRow } from "@/lib/queries";
import { bundleFromRow, toDecisionInput } from "@/lib/decisionInput";
import {
  CONFIDENCE_ORDER,
  decide,
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
    return { row, market: input.market, decision: decide(input) };
  });
}

// Re-exported from the rule table, where it now lives beside the `Confidence` type. One
// declaration, so a grade cannot sort one way here and another way in the weekly block.
export { CONFIDENCE_ORDER } from "@/lib/decision";

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
    entry: s.decision.entry,
    invalidation: s.decision.invalidation,
    confidence: s.decision.confidence,
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

export function classBySlug(slug: string): AssetClass | null {
  return ASSET_CLASSES.find((c) => c.slug === slug) ?? null;
}
