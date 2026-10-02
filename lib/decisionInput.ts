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
/// `Coverage.source` holds labels rather than raw source strings. Crypto returned null here until
/// 2026-10-03, because `jobs/audit.py` watched Yahoo, PSX, news, product signals and Amazon and no
/// exchange at all — so a blocked venue could only be seen as a close that stopped advancing, which
/// is gate 2 catching late what gate 3 should have named at once.
///
/// It now watches the whole venue chain under one label. That it is the chain and not a venue is
/// the point: `source = 'Binance'` would have read silent for 347 days while every coin had
/// yesterday's close from Coinbase, and watching Coinbase alone would read silent the first day the
/// chain fell through to Kraken. The only question Coverage can answer here is whether *any* venue
/// produced a close.
export function coverageLabelFor(market: Market): string | null {
  switch (market) {
    case "US":
      return "Yahoo Finance daily closes";
    case "PSX":
      return "PSX daily closing files";
    case "Crypto":
      return "crypto daily closes";
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
/// A **directional** row wins, and that is the whole point. This function first preferred the swing
/// read, on the reasoning that swing is the timeframe the levels are measured on — and against the
/// live database that produced WAIT for all 160 assets, because `jobs/setup.py` had written 125
/// `wait` and 35 `none` swing rows and not one `buy` or `short`. The direction in this data lives in
/// the `longer` rows from `jobs/horizons.py`: 17 buy and 12 short. Preferring swing therefore threw
/// away every signal the site had and printed a verdict of WAIT that no reader could have argued
/// with, because the input to the rule was wrong rather than the rule.
///
/// Preferring a direction is also what `lib/plain.ts` already did for its summary, so this is the
/// convention the repository had and this file had departed from.
///
/// Order among directional rows is swing, then longer, then intraday: the shorter the horizon the
/// sooner the reader has to act on it, and intraday is last because a front page that re-reads
/// itself through the session is a different page on every visit. With nothing directional, the
/// swing row is returned as the honest "measured, and flat".
export function pickSetup<T extends SetupRow>(rows: T[]): T | null {
  const directional = (r: T) => r.state === "buy" || r.state === "short";
  for (const horizon of ["swing", "longer", "intraday"]) {
    const found = rows.find((r) => r.horizon === horizon && directional(r));
    if (found) return found;
  }
  return rows.find((r) => r.horizon === "swing") ?? rows[0] ?? null;
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
/// `|robustZ| >= 2` is not a new threshold: it is the bar `jobs/investigate.py` and the wording
/// helpers have both used for an unusual move. lib/plain.ts had a copy of it in `unusualWords`,
/// which went when the prose block that called it was deleted, so this points at the job instead.
/// A `trigger` of "move" or "volume" counts on its own, because that job only writes a row at all
/// when something crossed its own bar.
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
  /// The newest `AssetFactor` row, when one has been computed.
  ///
  /// Null is the ordinary state for a name the factor job has not reached yet, and it must stay
  /// distinguishable from a factor that was computed and came out low: the rules treat an absent
  /// reading as missing evidence rather than evidence against, which is the only reason adding
  /// these gates did not empty the lists.
  factors: { volumeRatio: number | null; relStrength: number | null } | null;
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
  const analog = pickAnalog(bundle.analogs);

  // The longer view is a second opinion, so it only counts when it is a second row. In this data
  // the directional read is usually the longer one itself, and passing it as both the setup and
  // the thing confirming the setup would have it agree with itself: gate 5 could never fire, and
  // every single-horizon signal would be graded as though two timeframes had lined up. Null here
  // instead, which costs the row a confidence step — correctly, because one horizon is less
  // evidence than two.
  const longerRow = bundle.setups.find((r) => r.horizon === "longer") ?? null;
  const longer = longerRow && longerRow !== setup ? longerRow : null;

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
    volumeRatio: bundle.factors?.volumeRatio ?? null,
    relStrength: bundle.factors?.relStrength ?? null,
    unusualMove: isUnusualMove(bundle.investigation),
    // A missing HumanSignal row means news was never checked for this name, which the rule table
    // reports differently from a row saying zero. Keep the null.
    newsCount: bundle.human ? bundle.human.recentStories : null,
    eventInDays: daysUntil(iso(bundle.nextEvent?.date ?? null), today),
    sourceSilent: silent,
  };
}

// --- From what the query layer actually returns -------------------------------------------------
//
// `getDecisionBundle` and `getDecisionRows` return flat rows, which is the right shape for a query
// and the wrong shape for a rule table. The two functions below are that seam. They are declared
// structurally — plain field lists rather than imported Prisma or query types — so this file keeps
// no dependency on either, and a query that grows a column does not reach the rules.

/// The parts of `getDecisionBundle(assetId)` a decision needs. Nullable where that function is:
/// its asset fields come from a left-ish read and are typed optional.
export interface QueryBundle {
  symbol: string | null;
  assetType: string | null;
  /// "US" or "PK", from the industry. Never a symbol.
  market: string | null;
  newestClose: number | null;
  newestCloseDate: Date | string | null;
  horizons: {
    horizon: string;
    state: string;
    entryLevel: number | null;
    invalidateLevel: number | null;
  }[];
  analogs: {
    horizonDays: number;
    matches: number;
    minPct: number | null;
    maxPct: number | null;
    /// Optional because the query layer supplies them only where it selects them. A missing
    /// median is not a flat one: `analogConfirms` returns null and the direction prints with the
    /// gap named, rather than being refused for want of a column.
    medianPct?: number | null;
    positive?: number | null;
  }[];
  humanSignal: { recentStories: number } | null;
  investigation: { robustZ: number | null; trigger: string } | null;
  nextEvent: { date: Date | string } | null;
  /// Newest `AssetFactor`, when the factor job has written one for this asset.
  factor?: { volumeRatio: number | null; relStrength: number | null } | null;
}

/// `sourceHealth` is passed in rather than fetched, because it is one site-wide read that every
/// panel on a page shares. Fetching it per asset would turn one query into one per name.
export function bundleFromQuery(
  row: QueryBundle,
  sourceHealth: { source: string; status: string }[],
): DecisionBundle {
  return {
    // A nameless asset would otherwise produce "No stored prices for null." The fallback is only
    // ever reached if an asset row vanished between two queries.
    asset: {
      symbol: row.symbol ?? "this asset",
      assetType: row.assetType ?? "",
      industry: row.market ? { market: row.market } : null,
    },
    freshness: { newest: row.newestCloseDate, close: row.newestClose },
    setups: row.horizons.map((h) => ({
      horizon: h.horizon,
      state: h.state,
      entryLevel: h.entryLevel,
      invalidateLevel: h.invalidateLevel,
    })),
    analogs: row.analogs.map((a) => ({
      horizonDays: a.horizonDays,
      matches: a.matches,
      minPct: a.minPct,
      maxPct: a.maxPct,
      medianPct: a.medianPct ?? null,
      positive: a.positive ?? null,
    })),
    human: row.humanSignal ? { recentStories: row.humanSignal.recentStories } : null,
    investigation: row.investigation
      ? { robustZ: row.investigation.robustZ, trigger: row.investigation.trigger }
      : null,
    nextEvent: row.nextEvent ? { date: row.nextEvent.date } : null,
    factors: row.factor
      ? { volumeRatio: row.factor.volumeRatio, relStrength: row.factor.relStrength }
      : null,
    sourceHealth,
  };
}

/// The parts of one `getDecisionRows()` row a decision needs.
///
/// It carries the swing and longer setups as two named fields rather than a list, because the home
/// page deliberately leaves intraday out — a front page that re-ordered itself through the trading
/// day would be a different page on every visit.
export interface QueryRow {
  symbol: string;
  assetType: string;
  market: string;
  close: number | null;
  closeDate: Date | string | null;
  swing: { state: string; entryLevel: number | null; invalidateLevel: number | null } | null;
  longer: { state: string; entryLevel: number | null; invalidateLevel: number | null } | null;
  analogMinPct: number | null;
  analogMaxPct: number | null;
  analogMatches: number | null;
  analogHorizonDays: number | null;
  recentStories: number | null;
  robustZ: number | null;
  trigger: string | null;
  nextEventDate: Date | string | null;
  /// From the newest `AssetFactor`. Optional so the lists keep working on a database where the
  /// factor job has not run yet — the rules then report the confirmation as missing.
  analogMedianPct?: number | null;
  analogPositive?: number | null;
  volumeRatio?: number | null;
  relStrength?: number | null;
}

export function bundleFromRow(
  row: QueryRow,
  sourceHealth: { source: string; status: string }[],
): DecisionBundle {
  const setups: DecisionBundle["setups"] = [];
  if (row.swing) setups.push({ horizon: "swing", ...row.swing });
  if (row.longer) setups.push({ horizon: "longer", ...row.longer });

  return bundleFromQuery(
    {
      symbol: row.symbol,
      assetType: row.assetType,
      market: row.market,
      newestClose: row.close,
      newestCloseDate: row.closeDate,
      horizons: setups,
      // A band with no horizon is not a measurement, so a row missing either is no analog at all
      // rather than a range printed as though something backed it.
      analogs:
        row.analogMatches !== null && row.analogHorizonDays !== null
          ? [
              {
                horizonDays: row.analogHorizonDays,
                matches: row.analogMatches,
                minPct: row.analogMinPct,
                maxPct: row.analogMaxPct,
                medianPct: row.analogMedianPct ?? null,
                positive: row.analogPositive ?? null,
              },
            ]
          : [],
      humanSignal: row.recentStories !== null ? { recentStories: row.recentStories } : null,
      investigation: row.trigger !== null ? { robustZ: row.robustZ, trigger: row.trigger } : null,
      nextEvent: row.nextEventDate ? { date: row.nextEventDate } : null,
      factor:
        row.volumeRatio === undefined && row.relStrength === undefined
          ? null
          : { volumeRatio: row.volumeRatio ?? null, relStrength: row.relStrength ?? null },
    },
    sourceHealth,
  );
}
