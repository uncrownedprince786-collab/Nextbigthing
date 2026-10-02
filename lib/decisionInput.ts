// Stored rows in, `DecisionInput` out. The only place allowed to make that translation.
//
// It is a separate file from lib/decision.ts on purpose. The rule table must stay free of column
// names so it can be read and tested as rules; every awkward fact about how this database actually
// stores things belongs here, named and explained. When a job changes a column, this is the file to
// fix, and the rule table does not move.
//
// Pure, like the rules: it takes rows and a date and returns a value. Nothing here queries.

import type { DecisionInput, Direction, Market } from "./decision.ts";

/// `AssetSetup.state` is the job's vocabulary; the rule table speaks in directions.
///
/// "wait" maps to flat rather than unknown because a wait state is a real, measured reading — the
/// conditions were evaluated and came out neutral. "none" is the absence of a reading, which is a
/// different thing and must not be allowed to look like neutrality.
export function directionOfState(state: string | null | undefined): Direction {
  switch (state) {
    case "buy":
      return "up";
    case "short":
      return "down";
    case "wait":
      return "flat";
    default:
      return "unknown";
  }
}

/// Which market a name trades in.
///
/// There is no `exchange` column in this schema, so the market has to be read off three fields.
/// `assetType` settles crypto; everything else comes from the industry's `market`, which is "US" or
/// "PK". The trap worth knowing: the ticker **PSX is a US asset** (Phillips 66, seeded under
/// `energy`), so a symbol is never a market test. Only the industry is.
export function marketOf(asset: {
  assetType: string;
  industry?: { market: string } | null;
}): Market {
  if (asset.assetType === "crypto") return "Crypto";
  switch (asset.industry?.market) {
    case "PK":
      return "PSX";
    case "US":
      return "US";
    default:
      return "Other";
  }
}

/// The `Coverage` label whose silence would explain this market having no rows.
///
/// `Coverage.source` holds labels rather than raw source strings, and there is **no Coverage row
/// for crypto closes at all** — `jobs/audit.py` watches Yahoo, PSX, news, product signals and
/// Amazon, and Binance is not among them. So a silent crypto source cannot be detected here and
/// returns null; gate 2 of the rule table catches it anyway, because a blocked exchange shows up as
/// a close that stops advancing. That is a weaker signal than naming the source, and it is the
/// honest limit of what is stored.
export function coverageLabelFor(market: Market): string | null {
  switch (market) {
    case "US":
      return "Yahoo Finance daily closes";
    case "PSX":
      return "PSX daily closing files";
    default:
      return null;
  }
}

function iso(value: Date | string | null | undefined): string | null {
  if (!value) return null;
  if (typeof value === "string") return value.slice(0, 10);
  return value.toISOString().slice(0, 10);
}

/// The horizon rows this asset has, newest per horizon.
type SetupRow = {
  horizon: string;
  state: string;
  entryLevel: number | null;
  invalidateLevel: number | null;
};

/// Which row answers "what is the setup".
///
/// The swing read is preferred because it is the one the site is built around — daily closes over 20
/// and 50 sessions, which is the timeframe the entry and invalidation levels are measured on. When
/// there is no swing row, fall back to the first row that actually has a direction, which is the
/// same choice `lib/plain.ts` already makes for its summary, so the panel and the prose below it
/// cannot end up describing different horizons.
export function pickSetup<T extends SetupRow>(rows: T[]): T | null {
  const swing = rows.find((r) => r.horizon === "swing");
  if (swing) return swing;
  const directional = rows.find((r) => r.state === "buy" || r.state === "short");
  return directional ?? rows[0] ?? null;
}

/// The entry zone, from the two levels that are actually stored.
///
/// `AssetSetup` stores `entryLevel` and `invalidateLevel` as single numbers, not a band, and this
/// repository forbids pages computing their own figures — so the zone is the range those two levels
/// already span. That range has a real meaning rather than being a convenient pair: it is where the
/// trade is live but not yet wrong. Price inside it is actionable with the stop at the far edge;
/// price outside it is a reader waiting for a level, which is what the panel then says.
///
/// Widening it by a volatility multiple would be more conventional and would be new arithmetic in
/// the web layer, which is exactly what `jobs/` exists for. If a measured entry band is wanted, a
/// job should store one.
export function entryZone(
  entryLevel: number | null,
  invalidateLevel: number | null,
): { low: number; high: number } | null {
  if (entryLevel === null || invalidateLevel === null) return null;
  if (entryLevel === invalidateLevel) return null;
  return {
    low: Math.min(entryLevel, invalidateLevel),
    high: Math.max(entryLevel, invalidateLevel),
  };
}

/// Which analog row to quote.
///
/// The five-day row is preferred because it is the horizon a swing read is answerable on; failing
/// that, take the row with the most matches, since the range is only worth printing when something
/// backs it. `jobs/analogs.py` does not grade a row below 8 matches at all.
export function pickAnalog<T extends { horizonDays: number; matches: number }>(
  rows: T[],
): T | null {
  const five = rows.find((r) => r.horizonDays === 5);
  if (five) return five;
  return [...rows].sort((a, b) => b.matches - a.matches)[0] ?? null;
}

/// Was the last move unusual enough to need a published reason?
///
/// `|robustZ| >= 2` is not a new threshold: it is where `unusualWords` in lib/plain.ts starts
/// calling a move unusual, and reusing it keeps the panel and the sentence under it from
/// disagreeing. A `trigger` of "move" or "volume" counts on its own, because `jobs/investigate.py`
/// only writes a row at all when something crossed its own bar.
export function isUnusualMove(
  investigation: { robustZ: number | null; trigger: string } | null,
): boolean {
  if (!investigation) return false;
  if (investigation.trigger === "move" || investigation.trigger === "volume") return true;
  const z = investigation.robustZ;
  return z !== null && Math.abs(z) >= 2;
}

/// Days from `today` until a dated event, or null when there is none.
export function daysUntil(dateISO: string | null, todayISO: string): number | null {
  if (!dateISO) return null;
  const a = Date.parse(todayISO + "T00:00:00Z");
  const b = Date.parse(dateISO + "T00:00:00Z");
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.round((b - a) / 86_400_000);
}

export interface DecisionBundle {
  asset: { symbol: string; assetType: string; industry?: { market: string } | null };
  freshness: { newest: Date | string | null; close: number | null };
  /// Newest `AssetSetup` per horizon.
  setups: {
    horizon: string;
    state: string;
    entryLevel: number | null;
    invalidateLevel: number | null;
  }[];
  analogs: { horizonDays: number; matches: number; minPct: number | null; maxPct: number | null }[];
  human: { recentStories: number } | null;
  investigation: { robustZ: number | null; trigger: string } | null;
  nextEvent: { date: Date | string } | null;
  /// From `getSourceHealth()`; only the newest row per source is expected.
  sourceHealth: { source: string; status: string }[];
}

/// Today in UTC, as the rule table wants it. Call this once per request and pass it down, so two
/// panels on one page cannot straddle midnight and disagree.
export function todayISO(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function toDecisionInput(bundle: DecisionBundle, today: string): DecisionInput {
  const market = marketOf(bundle.asset);
  const setup = pickSetup(bundle.setups);
  const longer = bundle.setups.find((r) => r.horizon === "longer") ?? null;
  const analog = pickAnalog(bundle.analogs);

  // A source counts as silent only when the label that feeds *this* market is the silent one. A
  // dead Amazon feed says nothing about whether a US close arrived.
  const label = coverageLabelFor(market);
  const silent =
    label && bundle.sourceHealth.some((s) => s.source === label && s.status === "silent")
      ? label
      : null;

  return {
    symbol: bundle.asset.symbol,
    market,
    asOf: iso(bundle.freshness.newest),
    today,
    lastClose: bundle.freshness.close,
    setup: setup ? { direction: directionOfState(setup.state), horizon: setup.horizon } : null,
    horizon: longer ? { direction: directionOfState(longer.state) } : null,
    entry: setup ? entryZone(setup.entryLevel, setup.invalidateLevel) : null,
    invalidation: setup?.invalidateLevel ?? null,
    analogs: analog
      ? { count: analog.matches, lowPct: analog.minPct, highPct: analog.maxPct }
      : null,
    unusualMove: isUnusualMove(bundle.investigation),
    // A missing HumanSignal row means news was never checked for this name, which the rule table
    // reports differently from a row saying zero. Keep the null.
    newsCount: bundle.human ? bundle.human.recentStories : null,
    eventInDays: daysUntil(iso(bundle.nextEvent?.date ?? null), today),
    sourceSilent: silent,
  };
}
