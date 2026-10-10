// Stored rows in, `DecisionInput` out. The only place allowed to make that translation.
//
// It is a separate file from lib/decision.ts on purpose. The rule table must stay free of column
// names so it can be read and tested as rules; every awkward fact about how this database actually
// stores things belongs here, named and explained. When a job changes a column, this is the file to
// fix, and the rule table does not move.
//
// Pure, like the rules: it takes rows and a date and returns a value. Nothing here queries.

import type { DecisionInput, Direction, Market } from "./decision.ts";
import { biasDirectionOf, trendDirectionOf } from "./setupConditions.ts";
import { preferredTarget } from "./target.ts";

/// `AssetSetup.state` is the job's vocabulary; the rule table speaks in directions.
///
/// "wait" maps to flat rather than unknown because a wait state is a real, measured reading,
/// where "none" is the absence of one and must not be allowed to look like a measurement.
///
/// **`flat` here does not mean neutral, and the rule table must not print it as though it did.**
/// Read `jobs/setup.py`: `wait` is the branch guarded by `up_trend or down_trend`, and its stored
/// headline is "The direction is clear but the conditions are not all present". The neutral state
/// is `none` — "price is between its averages, so there is no clear direction to measure
/// conditions against" — and that is the one that arrives here as `unknown`. So a `flat` setup is
/// a direction that was measured and deliberately withheld, not an absence of one.
///
/// The distinction is load-bearing twice over. `flat` is correctly not actionable, because
/// setup.py withheld the direction when its conditions failed and manufacturing one here would
/// invent the confirmation it could not find. But `flat` and `unknown` need different sentences:
/// all ten stored coins carry a `wait` swing row over an upward trend, and for as long as both
/// states printed "Setup is flat" every crypto page explained a real verdict with a description
/// of a different market. See the fall-through gate in `lib/decision.ts`.
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
  // Read off the asset and not the industry, for the same reason crypto is. The market here is
  // a property of the instrument -- what trades when, and how old a close may be before it
  // stops describing the present -- and that does not change with which group a pair is filed
  // under. It also means a pair cannot silently fall through to `Other` if an FX industry is
  // ever added without its market column being set.
  if (asset.assetType === "forex") return "FX";
  // Read off the instrument for the third time, and for the reason the other two are. A front
  // month future is not a US listing that happens to be filed under a metals group: it has its
  // own venue, its own session and no issuer, so it carries no size figure and the questions a
  // reader asks of it are the commodity's and not a company's. The funds that hold the same
  // metal -- GLD, SLV, CPER, COPX -- are `etf` and stay US listings, which is what they are.
  if (asset.assetType === "commodity") return "Commodity";
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
    // Same label as US, because it is the same fetch: `jobs/prices.py` asks Yahoo for every
    // `source = 'yahoo'` asset in one lane, futures included. A separate label here would
    // claim a separate watch that `jobs/audit.py` does not keep, and a reader sent to look for
    // it would find nothing -- which is worse than the honest answer that the lane is shared.
    case "Commodity":
      return "Yahoo Finance daily closes";
    default:
      return null;
  }
}

/// A `@db.Date` column comes back from `pg` as a `Date` at **local** midnight, and both the rule
/// table and the unique key speak ISO days. Formatting from the local parts is therefore
/// deliberate, and `toISOString()` is wrong here: east of UTC a local-midnight date is the previous
/// day in UTC, so `toISOString().slice(0, 10)` reported `asOf` one day early and fed a too-old date
/// into the staleness gate. `STALE_AFTER_DAYS.Crypto` is 2, so a nightly run on a non-UTC box could
/// write `stale` verdicts the website -- rendered in UTC on Vercel -- never shows.
/// `tools/decide.mjs` has always formatted this way in its own `dayOf()`; this is the same rule, so
/// the job and the site cannot disagree about which day a stored row belongs to.
function iso(value: Date | string | null | undefined): string | null {
  if (!value) return null;
  if (typeof value === "string") return value.slice(0, 10);
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, "0");
  const d = String(value.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/// One measured target range as `jobs/horizons.py` wrote it, in the fields the rules read.
///
/// Declared structurally here for the same reason every other shape in this file is: the query
/// layer's `DecisionTarget` carries `distancePct` and `note` as well, which the rule table has no
/// use for, and importing its type would tie the rules to a query's column list.
type TargetRow = {
  method: string;
  low: number;
  high: number;
  rewardRisk: number | null;
};

/// The horizon rows this asset has, newest per horizon.
type SetupRow = {
  horizon: string;
  state: string;
  entryLevel: number | null;
  invalidateLevel: number | null;
  /// Optional only because `pickSetup` is generic over rows read for other purposes. The
  /// decision path always carries it.
  conditions?: string | null;
  /// Every method's target for this setup, unreduced. Optional for the same reason, and for one
  /// more: a database on which `jobs/horizons.py` has not run has none, and the rules then
  /// report the missing reward rather than refusing the direction.
  targets?: TargetRow[] | null;
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
    /// The stored condition read. Nullable because a row written before the format existed
    /// carries none, and `trendDirectionOf` answers null for it rather than guessing.
    conditions?: string | null;
    /// This horizon's measured target ranges, one per method, unreduced. See `SetupRow`.
    targets?: TargetRow[] | null;
  }[];
  /// Newest `AssetAnalog` per horizon.
  ///
  /// `medianPct` and `positive` are not decoration. A range alone cannot say whether the matched
  /// days leaned: -20% to +22% is the same range whether nine days in ten rose or one did, and
  /// `analogConfirms` needs the lean rather than the span. They were missing from this interface
  /// and from the object `toDecisionInput` built, so the third confirmation leg returned null for
  /// every asset in the database — see the note there.
  analogs: {
    horizonDays: number;
    matches: number;
    minPct: number | null;
    maxPct: number | null;
    medianPct?: number | null;
    positive?: number | null;
  }[];
  human: {
    recentStories: number;
    /// The word-list verdict over the headlines that took a side, as `jobs/human.py` stored it:
    /// "positive", "negative" or "neutral". Optional because a row written before the column
    /// existed carries none, and null is read as "no direction" rather than guessed at.
    tone?: string | null;
    /// Whether the recent story rate spiked against its own baseline. Optional for the same
    /// reason; absent is read as false, which is the honest default for a flag that is only
    /// ever set when a threshold was cleared.
    catalyst?: boolean | null;
  } | null;
  investigation: { robustZ: number | null; trigger: string } | null;
  /// The newest `AssetFactor` row, when one has been computed.
  ///
  /// Null is the ordinary state for a name the factor job has not reached yet, and it must stay
  /// distinguishable from a factor that was computed and came out low: the rules treat an absent
  /// reading as missing evidence rather than evidence against, which is the only reason adding
  /// these gates did not empty the lists.
  factors: {
    volumeRatio: number | null;
    relStrength: number | null;
    r20?: number | null;
    /// The entry rule that fired on this session and which way, as two stored columns.
    ///
    /// Kept as the raw pair across this seam rather than as the shape the rules take, because
    /// every other field here is the stored value and converting in two places is how one of
    /// them comes to validate the direction and the other does not. `entryTriggerOf` does it
    /// once, where the bundle becomes a `DecisionInput`.
    entryTrigger?: string | null;
    triggerDirection?: string | null;
  } | null;
  nextEvent: { date: Date | string } | null;
  /// The newest stored REJECT from the macro gatekeeper for this name, or null. Raw across this seam,
  /// like every other field: `macroVetoFrom` validates it once, where the bundle becomes a
  /// `DecisionInput`. Optional so a caller that has not learned to read it keeps deciding exactly as
  /// before, which is also what the gate being off looks like.
  macroVeto?: { reason: string | null; asOf: Date | string } | null;
  /// From `getSourceHealth()`; only the newest row per source is expected.
  sourceHealth: { source: string; status: string }[];
}

/// A stored refusal read into the shape the rules take, or null when it is not one.
///
/// The reason is **checked against the two words rather than cast**: `MacroGate.reason` is a
/// `String?`, and a cast would turn anything a job or a hand-written UPDATE put there into a printed
/// refusal. An unrecognised reason or an unreadable date yields null, which is the same as no veto
/// and costs nothing -- the one direction in which this seam may fail.
function macroVetoFrom(
  v: { reason: string | null; asOf: Date | string } | null | undefined,
): { reason: "macro-warning" | "sentiment-conflict"; asOf: string } | null {
  if (!v) return null;
  if (v.reason !== "macro-warning" && v.reason !== "sentiment-conflict") return null;
  const t = v.asOf instanceof Date ? v.asOf.getTime() : Date.parse(String(v.asOf));
  if (!Number.isFinite(t)) return null;
  return { reason: v.reason, asOf: new Date(t).toISOString().slice(0, 10) };
}

/// The two stored columns read into the pair the rules take, or null when they are not one.
///
/// Both or neither. `jobs/factors.py` writes them together and a row carrying a rule name with
/// no direction has lost half of itself somewhere between the job and here; confirming a
/// direction from that half would be reading a measurement that was never completed.
///
/// The direction is **checked against the two words rather than cast to them**. `triggerDirection`
/// is a `String?` in Postgres, so it can hold anything a future job or a hand-written UPDATE puts
/// there, and `as "up" | "down"` would turn a typo into a silent confirmation of whichever
/// direction the card happened to be printing. An unrecognised word yields null, which is the
/// same as no trigger and costs nothing.
function entryTriggerOf(
  rule: string | null | undefined,
  direction: string | null | undefined,
): { rule: string; direction: "up" | "down" } | null {
  if (!rule) return null;
  if (direction !== "up" && direction !== "down") return null;
  return { rule, direction };
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
    setup: setup
      ? {
          direction: directionOfState(setup.state),
          horizon: setup.horizon,
          // The withheld direction. `directionOfState` returns "flat" for state `wait`, which
          // is the state meaning "the trend is clear and the conditions behind it are not all
          // present" -- so the direction exists and only this field carries it.
          trend: trendDirectionOf(setup.conditions),
          // The weaker sibling, present only where the trend itself came back mixed. Carried
          // separately so the rule table can tell three things agreeing from two, and say which
          // one it acted on rather than calling both "the trend".
          bias: biasDirectionOf(setup.conditions),
        }
      : null,
    horizon: longer ? { direction: directionOfState(longer.state) } : null,
    entry: setup ? entryZone(setup.entryLevel, setup.invalidateLevel) : null,
    invalidation: setup?.invalidateLevel ?? null,
    // The deciding setup's own target, reduced to one by `preferredTarget` — the same preference
    // order `lib/target.ts` applies on the pages, imported rather than restated, so the panel's
    // printed exit and the reward the rules size the trade against are the same row.
    //
    // Taken off `setup` and never off the list: `pickSetup` has already chosen which horizon
    // decided, and a target lifted from a different horizon would size a swing trade against a
    // quarterly exit. That is the bug `decidingSetup` in `lib/target.ts` exists to prevent, and
    // this is the same fix one step earlier.
    target: preferredTarget(setup?.targets),
    // `medianPct` and `positive` travel with the count and the band. They used not to, and that
    // one omission disabled a third of the confidence grading for every asset on the site.
    //
    // `analogConfirms` in lib/decision.ts returns null the moment either is missing, so with them
    // dropped here it returned null 160 times out of 160, for every direction, always. Two
    // consequences, and the second is worse than the first. `confidenceFor` counts three
    // confirmations and could only ever reach two, so the grade was capped below what the stored
    // evidence supported. And `confirmMissing` printed its "stored, but which way they went was
    // not recorded" branch on every directional asset — a sentence about an absent measurement,
    // printed over 150 assets whose `positive` and `medianPct` were both sitting in the table.
    // ATRL showed "102 similar past days are stored, but which way they went was not recorded"
    // while holding both columns.
    //
    // Nothing upstream was at fault: `jobs/analogs.py` writes both columns, `lib/queries.ts`
    // selects them, and `bundleFromQuery` carries them. They were lost in this object literal.
    // Read against the live table the leg discriminates — 23 true, 16 false over the 40
    // directional names — so this restores a leg that argues, not one that flatters.
    analogs: analog
      ? {
          count: analog.matches,
          lowPct: analog.minPct,
          highPct: analog.maxPct,
          medianPct: analog.medianPct ?? null,
          positive: analog.positive ?? null,
        }
      : null,
    volumeRatio: bundle.factors?.volumeRatio ?? null,
    relStrength: bundle.factors?.relStrength ?? null,
    // The asset's own 20-session return, for the short gate. Fifth field to cross this seam and
    // the fifth to get a test for it: an optional field that is never named here is dropped
    // silently, which has now happened four times.
    r20: bundle.factors?.r20 ?? null,
    // Sixth field across this seam, and the count in the comment above is the reason it has its
    // own test rather than being assumed to arrive.
    entryTrigger: entryTriggerOf(
      bundle.factors?.entryTrigger,
      bundle.factors?.triggerDirection,
    ),
    // Seventh field across this seam, and it has its own test for the reason the sixth did.
    macroVeto: macroVetoFrom(bundle.macroVeto),
    unusualMove: isUnusualMove(bundle.investigation),
    // A missing HumanSignal row means news was never checked for this name, which the rule table
    // reports differently from a row saying zero. Keep the null.
    newsCount: bundle.human ? bundle.human.recentStories : null,
    // The direction of the coverage, kept apart from its volume. `newsCount` above is how many
    // stories there were and carries no opinion; this is the opinion. `jobs/human.py` writes
    // "neutral" both for a balanced window and for one where too few headlines took a side, and
    // both of those correctly arrive here as a null tone -- the rules must only ever act on an
    // actual disagreement, never on the absence of one.
    news: bundle.human
      ? {
          tone:
            bundle.human.tone === "positive"
              ? "up"
              : bundle.human.tone === "negative"
                ? "down"
                : null,
          catalyst: bundle.human.catalyst === true,
        }
      : null,
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
    /// The stored condition read, carried for the trend verdict inside it.
    ///
    /// Optional for the same reason `medianPct` below is, and lost the same way on its first
    /// attempt: this seam re-declares every field by hand, so a column the query selects and the
    /// rules read still has to be named *here* or it is dropped between them with nothing failing.
    /// That is now the third field it has happened to. The guard is the test that asserts a
    /// developing read survives the seam, not the type -- an optional field cannot fail to exist.
    conditions?: string | null;
    /// The fourth field it has happened to, caught before it shipped rather than after. Both
    /// query paths already fetch these rows -- `getHorizons` includes them and `getDecisionRows`
    /// selects them -- so the only thing between a stored reward and the rule that reads it is
    /// this line and the one in `bundleFromQuery` below. The test that asserts a reward survives
    /// the seam is the guard, for the reason stated above.
    targets?: TargetRow[] | null;
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
  humanSignal: { recentStories: number; tone?: string | null; catalyst?: boolean | null } | null;
  investigation: { robustZ: number | null; trigger: string } | null;
  nextEvent: { date: Date | string } | null;
  /// Newest `AssetFactor`, when the factor job has written one for this asset.
  factor?: {
    volumeRatio: number | null;
    relStrength: number | null;
    r20?: number | null;
    entryTrigger?: string | null;
    triggerDirection?: string | null;
  } | null;
  /// Newest stored REJECT from the macro gatekeeper; see `DecisionBundle.macroVeto`.
  macroVeto?: { reason: string | null; asOf: Date | string } | null;
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
      conditions: h.conditions ?? null,
      // Reduced to one later and never here. `toDecisionInput` picks the deciding horizon first
      // and applies the preference order to that row's methods; choosing a method at this seam
      // would pick one before knowing which setup decided. Rule 24 — the three are not averaged
      // and they are not thrown away either.
      targets: h.targets ?? null,
    })),
    analogs: row.analogs.map((a) => ({
      horizonDays: a.horizonDays,
      matches: a.matches,
      minPct: a.minPct,
      maxPct: a.maxPct,
      medianPct: a.medianPct ?? null,
      positive: a.positive ?? null,
    })),
    human: row.humanSignal
      ? {
          recentStories: row.humanSignal.recentStories,
          tone: row.humanSignal.tone ?? null,
          catalyst: row.humanSignal.catalyst ?? false,
        }
      : null,
    investigation: row.investigation
      ? { robustZ: row.investigation.robustZ, trigger: row.investigation.trigger }
      : null,
    nextEvent: row.nextEvent ? { date: row.nextEvent.date } : null,
    factors: row.factor
      ? {
          volumeRatio: row.factor.volumeRatio,
          relStrength: row.factor.relStrength,
          r20: row.factor.r20 ?? null,
          entryTrigger: row.factor.entryTrigger ?? null,
          triggerDirection: row.factor.triggerDirection ?? null,
        }
      : null,
    macroVeto: row.macroVeto ?? null,
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
  /// `conditions` is the stored condition read, carried for the trend verdict inside it. Both
  /// readers of this shape -- the home page and `tools/decide.mjs` -- must select it, or the
  /// nightly log and the page would disagree about which names have a direction forming.
  swing: {
    state: string;
    entryLevel: number | null;
    invalidateLevel: number | null;
    conditions?: string | null;
    /// This horizon's measured target ranges. `getDecisionRows` already selects them onto both
    /// of these rows, and the spread in `bundleFromRow` carries them without naming them -- but
    /// they are declared here anyway, because an undeclared field that happens to survive a
    /// spread is a field nothing guarantees and three have already been lost that way.
    targets?: TargetRow[] | null;
  } | null;
  longer: {
    state: string;
    entryLevel: number | null;
    invalidateLevel: number | null;
    conditions?: string | null;
    targets?: TargetRow[] | null;
  } | null;
  analogMinPct: number | null;
  analogMaxPct: number | null;
  analogMatches: number | null;
  analogHorizonDays: number | null;
  recentStories: number | null;
  /// The stored coverage verdict and the catalyst flag beside it. Optional so a caller that has
  /// not learned to select them yet keeps deciding -- the rules then read no direction, which is
  /// the same answer a neutral window gives and is the one that changes nothing.
  newsTone?: string | null;
  newsCatalyst?: boolean | null;
  robustZ: number | null;
  trigger: string | null;
  nextEventDate: Date | string | null;
  /// From the newest `AssetFactor`. Optional so the lists keep working on a database where the
  /// factor job has not run yet — the rules then report the confirmation as missing.
  analogMedianPct?: number | null;
  analogPositive?: number | null;
  volumeRatio?: number | null;
  relStrength?: number | null;
  /// This asset's own 20-session return, for the short gate.
  r20?: number | null;
  /// The entry rule that fired this session, for the fifth confirmation. Named `entryTrigger`
  /// and not `trigger`: `trigger` on this same row is the investigation's, a different thing
  /// from a different table, and two fields one word apart is how a list comes to confirm a
  /// direction with an unusual-move flag.
  entryTrigger?: string | null;
  triggerDirection?: string | null;
  /// The newest stored macro REJECT and the session it was made for. Both or neither: a reason with
  /// no date cannot be aged, so it is not a veto.
  macroVetoReason?: string | null;
  macroVetoAsOf?: Date | string | null;
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
      humanSignal:
        row.recentStories !== null
          ? {
              recentStories: row.recentStories,
              tone: row.newsTone ?? null,
              catalyst: row.newsCatalyst ?? false,
            }
          : null,
      investigation: row.trigger !== null ? { robustZ: row.robustZ, trigger: row.trigger } : null,
      nextEvent: row.nextEventDate ? { date: row.nextEventDate } : null,
      factor:
        row.volumeRatio === undefined && row.relStrength === undefined
          ? null
          : {
              volumeRatio: row.volumeRatio ?? null,
              relStrength: row.relStrength ?? null,
              r20: row.r20 ?? null,
              entryTrigger: row.entryTrigger ?? null,
              triggerDirection: row.triggerDirection ?? null,
            },
      macroVeto:
        row.macroVetoReason && row.macroVetoAsOf
          ? { reason: row.macroVetoReason, asOf: row.macroVetoAsOf }
          : null,
    },
    sourceHealth,
  );
}
