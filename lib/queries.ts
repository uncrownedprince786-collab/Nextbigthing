import { prisma } from "@/lib/db";
import { pickAnalog } from "@/lib/decisionInput";
import { latestWindow } from "@/lib/rankingWindow";

// Re-exported so the pages keep a single import site for everything they read about rankings;
// the rule itself lives in a database-free module so the test lane can import it.
export { RANKING_WINDOW_LAG_DAYS, rankingAsOf } from "@/lib/rankingWindow";


export async function getIndustries() {
  return prisma.industry.findMany({
    orderBy: { sort: "asc" },
    // The home page says how many assets in an industry carry a size figure, which needs
    // the total even though the assets themselves are never listed there.
    include: { _count: { select: { assets: true } } },
  });
}

/// Industries grouped by the exchange they list on, in the order the groups should read.
///
/// The grouping is presentational, but the reason for it is not: two industry cards side
/// by side invite the reader to compare the size figures on them, and a rupee figure next
/// to a dollar one compares to nothing. Separating the groups puts a heading and a
/// currency note between them.
export async function getIndustriesByMarket() {
  const all = await getIndustries();
  const order = ["US", "PK"];
  const groups = new Map<string, typeof all>();
  for (const ind of all) {
    if (!groups.has(ind.market)) groups.set(ind.market, []);
    groups.get(ind.market)!.push(ind);
  }
  return [...groups.entries()].sort(
    (a, b) =>
      (order.indexOf(a[0]) + 1 || 99) - (order.indexOf(b[0]) + 1 || 99) ||
      a[0].localeCompare(b[0]),
  );
}

export async function getIndustry(slug: string) {
  return prisma.industry.findUnique({
    where: { slug },
    include: {
      analysis: { orderBy: { createdAt: "desc" } },
      assets: { orderBy: { name: "asc" } },
      news: { orderBy: { publishedAt: "desc" }, take: 8, include: { asset: true } },
    },
  });
}

export type Basis = "size" | "sizeNow" | "totalReturn" | "rising";

export async function getRankings(industryId: string, basis: Basis) {
  const rows = await prisma.ranking.findMany({
    where: { industryId, basis },
    orderBy: [{ periodEnd: "desc" }, { rank: "asc" }],
    include: { asset: true },
  });
  return latestWindow(rows);
}

export async function getAllIndustriesByBasis(basis: Basis) {
  const rows = await prisma.ranking.findMany({
    where: { basis },
    orderBy: [{ periodEnd: "desc" }, { rank: "asc" }],
    include: { asset: { include: { industry: true } } },
  });
  // Per industry, because the window is per industry: two exchanges close on different days, so
  // one industry's newest stored close is routinely a day away from another's.
  const byIndustry = new Map<string, typeof rows>();
  for (const r of rows) {
    const got = byIndustry.get(r.industryId);
    if (got) got.push(r);
    else byIndustry.set(r.industryId, [r]);
  }
  return [...byIndustry.values()].flatMap((group) => latestWindow(group));
}

export async function getProducts(status?: string) {
  return prisma.product.findMany({
    where: status ? { status } : undefined,
    orderBy: [{ demandScore: { sort: "desc", nulls: "last" } }, { name: "asc" }],
  });
}

export async function getProduct(slug: string) {
  return prisma.product.findUnique({
    where: { slug },
    include: {
      analysis: { orderBy: { createdAt: "desc" }, take: 1 },
      signals: { orderBy: [{ source: "asc" }, { metric: "asc" }] },
      assetLinks: { include: { asset: { include: { industry: true } } } },
      news: { orderBy: { publishedAt: "desc" }, take: 6 },
    },
  });
}

export async function getAsset(symbol: string) {
  return prisma.asset.findFirst({
    where: { symbol: { equals: symbol, mode: "insensitive" } },
    include: {
      industry: true,
      analysis: { orderBy: { createdAt: "desc" }, take: 1 },
      rankings: { orderBy: [{ periodEnd: "desc" }, { rank: "asc" }] },
      news: { orderBy: { publishedAt: "desc" }, take: 6 },
      productLinks: { include: { product: true } },
    },
  });
}

export async function getAssetPrices(assetId: string, fromYear = 2019) {
  return prisma.priceSnapshot.findMany({
    where: { assetId, date: { gte: new Date(Date.UTC(fromYear, 0, 1)) } },
    orderBy: { date: "asc" },
    select: { date: true, close: true, volume: true, marketCap: true },
  });
}

export async function getFreshness() {
  const [snap, rank, signal, news] = await Promise.all([
    prisma.priceSnapshot.aggregate({ _max: { date: true }, _count: true }),
    prisma.ranking.aggregate({ _max: { periodEnd: true }, _count: true }),
    prisma.productSignal.aggregate({ _max: { periodEnd: true }, _count: true }),
    prisma.news.aggregate({ _max: { publishedAt: true }, _count: true }),
  ]);
  return { snap, rank, signal, news };
}

/// How close two dated items for the same target have to be before the later one is read as a
/// restatement of the earlier one rather than a second event.
///
/// 7, and the number comes from the stored calendar rather than from taste. Measured across the
/// scheduled rows, consecutive earnings dates for one company sit 1 day apart 36 times and
/// never more than 6 days apart — that is the provider revising one quarter's report, not two
/// reports. Consecutive dividend dates for one company are never closer than 8 days, because
/// the two that exist are the ex-dividend day and the payment day and both are real. So a
/// window of 7 collapses every earnings restatement in the data and touches no dividend pair.
/// Widen it to 14 and EOG's ex-dividend and payment dates become one row, which would be
/// deleting a date rather than deduplicating one.
export const EVENT_DUPLICATE_WITHIN_DAYS = 7;

/// Every dated event, soonest first, with provider restatements folded away.
///
/// Soonest first and not newest first. This list is a diary, and the only question a diary
/// answers is what is next; ordered by `date desc` the first screen was January 2027, which is
/// the one date on it nobody is waiting for.
///
/// The fold keeps the soonest of a run rather than the last. A reader planning around a date
/// needs the earliest day the thing could happen, and a calendar that silently moved a report
/// later would be the more expensive way to be wrong. Rows with no target attached are never
/// folded: the historical events have no link, and two of them sharing a category is not a
/// duplicate of anything.
export async function getEvents() {
  const rows = await prisma.event.findMany({
    orderBy: [{ date: "asc" }, { name: "asc" }],
    include: {
      analysis: { orderBy: { createdAt: "desc" }, take: 1 },
      _count: { select: { impacts: true } },
      links: {
        include: {
          asset: { select: { symbol: true, name: true } },
          product: { select: { slug: true, name: true } },
        },
      },
    },
  });

  const kept: typeof rows = [];
  const soonestSeen = new Map<string, Date>();
  for (const row of rows) {
    const target = row.links[0]?.targetRef;
    if (!target) {
      kept.push(row);
      continue;
    }
    const key = `${target}|${row.category}`;
    const earlier = soonestSeen.get(key);
    if (earlier) {
      const apart = (row.date.getTime() - earlier.getTime()) / 86_400_000;
      if (apart <= EVENT_DUPLICATE_WITHIN_DAYS) continue;
    }
    soonestSeen.set(key, row.date);
    kept.push(row);
  }
  return kept;
}

export async function getEvent(slug: string) {
  return prisma.event.findUnique({
    where: { slug },
    include: { analysis: { orderBy: { createdAt: "desc" }, take: 1 } },
  });
}

/// The movers for one event window, largest absolute move first.
///
/// Both ends are taken, not just the top: a table showing only the biggest rises reads as
/// a list of what the event was good for, and the same window almost always contains falls
/// of a similar size. Showing one end would be a claim dressed as a selection.
export async function getEventImpacts(eventId: string, windowDays: number, take = 10) {
  const rows = await prisma.eventImpact.findMany({
    where: { eventId, windowDays },
    orderBy: { changePct: "desc" },
    include: { asset: { include: { industry: true } } },
  });
  return {
    total: rows.length,
    risers: rows.slice(0, take),
    fallers: rows.slice(-take).reverse(),
  };
}

export async function getEventWindows(eventId: string) {
  const rows = await prisma.eventImpact.findMany({
    where: { eventId },
    distinct: ["windowDays"],
    select: { windowDays: true },
    orderBy: { windowDays: "asc" },
  });
  return rows.map((r) => r.windowDays);
}

/// The newest stored run of each marketplace category.
///
/// Rows from different runs must never be mixed into one table: a rank of 4 read last week
/// and a rank of 6 read today are not a ranking, they are two rankings, and putting them
/// side by side would invent an ordering neither of them published.
export type MarketplaceRow = Awaited<
  ReturnType<typeof prisma.marketplaceItem.findMany>
>[number];

export async function getMarketplace(
  categorySlug?: string,
): Promise<{ periodEnd: Date | null; items: MarketplaceRow[] }> {
  const latest = await prisma.marketplaceItem.aggregate({ _max: { periodEnd: true } });
  const periodEnd = latest._max.periodEnd;
  if (!periodEnd) return { periodEnd: null, items: [] };
  const items = await prisma.marketplaceItem.findMany({
    where: { periodEnd, ...(categorySlug ? { categorySlug } : {}) },
    orderBy: [{ categorySlug: "asc" }, { rank: "asc" }],
  });
  return { periodEnd, items };
}

/// Listings in the newest stored run whose title contains the product's search term.
///
/// This is a text match on a title, and it is reported as exactly that. It says a listing
/// in the top thirty of its category has these words in its name; it does not say the
/// product category is selling well, and the number of matches is not a demand figure. The
/// term is required to be at least four characters so a short one does not match a
/// fragment of an unrelated word.
export async function getProductMarketplace(
  term: string,
): Promise<{ periodEnd: Date | null; items: MarketplaceRow[] }> {
  const cleaned = term.trim();
  if (cleaned.length < 4) return { periodEnd: null, items: [] };
  const latest = await prisma.marketplaceItem.aggregate({ _max: { periodEnd: true } });
  const periodEnd = latest._max.periodEnd;
  if (!periodEnd) return { periodEnd: null, items: [] };
  const items = await prisma.marketplaceItem.findMany({
    where: { periodEnd, title: { contains: cleaned, mode: "insensitive" } },
    orderBy: [{ rank: "asc" }],
    take: 8,
  });
  return { periodEnd, items };
}

/// The newest human signal reading for one target, or null when no reading has been written.
///
/// Newest rather than a named period: the job writes one row per target per run date, and a
/// page that pinned a date would go blank the first time a run was skipped.
export async function getHumanSignal(where: { assetId: string } | { productId: string }) {
  return prisma.humanSignal.findFirst({
    where,
    orderBy: { periodEnd: "desc" },
  });
}

/// The newest computed factor row for one asset, or null when the factor job has not reached it.
///
/// Null rather than a row of zeroes, and the distinction is the whole reason this is a separate
/// function instead of a `?? 0` at the call site. `volumeRatio` of null means the venue published
/// no volume and `relStrength` of null means the peer group was too small to take a median over —
/// both are "we do not know", and the rule table in `lib/decision.ts` is built to report an unknown
/// as missing evidence rather than as evidence against. A zero would read as "volume was flat" and
/// "the name matched its peers exactly", neither of which was measured.
export async function getFactor(assetId: string) {
  return prisma.assetFactor.findFirst({
    where: { assetId },
    orderBy: { periodEnd: "desc" },
    select: {
      periodEnd: true,
      volumeRatio: true,
      relStrength: true,
      peers: true,
      r20: true,
      entryTrigger: true,
      triggerDirection: true,
    },
  });
}

/// The newest measured-condition read for one asset.
export async function getSetup(assetId: string) {
  return prisma.assetSetup.findFirst({
    where: { assetId },
    orderBy: { periodEnd: "desc" },
  });
}

/// The newest near-term analog rows for one asset, one per horizon.
export async function getAnalogs(assetId: string) {
  const latest = await prisma.assetAnalog.aggregate({
    where: { assetId },
    _max: { periodEnd: true },
  });
  const periodEnd = latest._max.periodEnd;
  if (!periodEnd) return { periodEnd: null, rows: [] };
  const rows = await prisma.assetAnalog.findMany({
    where: { assetId, periodEnd },
    orderBy: { horizonDays: "asc" },
  });
  return { periodEnd, rows };
}

/// Dated items that have not happened yet, for one asset or across the site.
///
/// Ordered by date because that is the only order a diary has. A scheduled row keeps its
/// flag after its day passes, so the filter is on the date and not on the flag.
export async function getUpcoming(opts: { assetId?: string; take?: number } = {}) {
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  return prisma.event.findMany({
    where: {
      scheduled: true,
      date: { gte: today },
      ...(opts.assetId ? { links: { some: { assetId: opts.assetId } } } : {}),
    },
    orderBy: { date: "asc" },
    take: opts.take ?? 12,
    include: {
      links: {
        include: {
          asset: { select: { symbol: true, name: true } },
          product: { select: { slug: true, name: true } },
        },
      },
    },
  });
}

/// What measurably followed past events of the same category, so an upcoming date can be
/// read next to the record of its own kind rather than in isolation.
///
/// Returns counts, never a bare average: below the floor the caller says how many were found
/// instead of dividing by them.
export const EVENT_HISTORY_MIN = 5;

export async function getEventCategoryHistory(category: string, windowDays = 30) {
  const impacts = await prisma.eventImpact.findMany({
    where: { windowDays, event: { category, scheduled: false } },
    select: { changePct: true },
  });
  const moves = impacts.map((i) => i.changePct);
  const positive = moves.filter((m) => m > 0).length;
  return {
    category,
    windowDays,
    measured: moves.length,
    positive,
    enough: moves.length >= EVENT_HISTORY_MIN,
    mean: moves.length ? moves.reduce((a, b) => a + b, 0) / moves.length : null,
  };
}

/// Where attention for one product sits, newest stored breakdown only.
///
/// Grouped by the list each value came from, because a value is only meaningful against its
/// own list: "United States 100" among countries and "Wyoming 100" among US states are both
/// 100 and are not the same measurement.
export async function getProductRegions(productId: string) {
  const latest = await prisma.productRegion.aggregate({
    where: { productId },
    _max: { periodEnd: true },
  });
  const periodEnd = latest._max.periodEnd;
  if (!periodEnd) return { periodEnd: null, lists: [] };

  const all = await prisma.productRegion.findMany({
    where: { productId, periodEnd },
    orderBy: [{ scope: "asc" }, { geo: "asc" }, { rank: "asc" }],
  });

  const byList = new Map<string, typeof all>();
  for (const r of all) {
    const key = `${r.scope}|${r.geo}`;
    if (!byList.has(key)) byList.set(key, []);
    byList.get(key)!.push(r);
  }
  const LABEL: Record<string, string> = {
    "country|": "Countries, worldwide",
    "region|US": "States, inside the United States",
    "region|PK": "Provinces, inside Pakistan",
  };
  const lists = [...byList.entries()].map(([key, rows]) => ({
    key,
    label: LABEL[key] ?? key.replace("|", " "),
    rows,
    timeframe: rows[0]?.timeframe ?? "",
    source: rows[0]?.source ?? "",
  }));
  return { periodEnd, lists };
}


/// How the logged readings have actually turned out so far.
///
/// Returns counts, never a bare rate. `enough` is the caller's cue to publish a figure at
/// all: below the floor the page says how many rows exist instead of dividing by them. The
/// floor is the same judgement MIN_MEASURED makes in jobs/accuracy.py, repeated here because
/// the page must not be able to publish something the job would have withheld.
export const ACCURACY_MIN_MEASURED = 20;

export async function getAccuracy(horizon: 30 | 60 = 30) {
  const col = horizon === 30 ? "move30Pct" : "move60Pct";
  const measured = await prisma.signalLog.findMany({
    where: { [col]: { not: null } },
    select: { move30Pct: true, move60Pct: true, factors: true, issuedOn: true },
    orderBy: { issuedOn: "asc" },
  });
  const moves = measured
    .map((r) => (horizon === 30 ? r.move30Pct : r.move60Pct))
    .filter((v): v is number => v != null);
  const open = await prisma.signalLog.count({ where: { status: "open" } });
  const positive = moves.filter((m) => m > 0).length;
  return {
    horizon,
    measured: moves.length,
    positive,
    open,
    enough: moves.length >= ACCURACY_MIN_MEASURED,
    mean: moves.length ? moves.reduce((a, b) => a + b, 0) / moves.length : null,
    earliest: measured.length ? measured[0].issuedOn : null,
  };
}

/// The newest thesis for one asset, with the dated checks that produced its status.
///
/// Newest by opening day, which is not the same as "the active one": a broken thesis is the
/// most recent thing that happened to this asset's recorded reason, and hiding it in favour
/// of an older active row would show the reader the state the system has already abandoned.
///
/// The checks come oldest first because they are a sequence. Read in that order they show a
/// reason decaying; read newest first they look like a list of statuses.
export async function getThesis(assetId: string) {
  return prisma.assetThesis.findFirst({
    where: { assetId },
    orderBy: { openedOn: "desc" },
    include: { checks: { orderBy: { asOf: "asc" } } },
  });
}

/// The newest move attribution for one asset, at one window.
///
/// The window is named rather than inferred. Two rows measured over different numbers of
/// sessions are two different claims, and a page that took whichever arrived last would
/// change what it was saying without changing a word.
export async function getAttribution(assetId: string, windowDays = 20) {
  return prisma.moveAttribution.findFirst({
    where: { assetId, windowDays },
    orderBy: { periodEnd: "desc" },
  });
}

/// Paths that reached one asset from somewhere a catalyst was flagged, strongest first.
///
/// Only the newest stored walk. Mixing two nights of paths would present a neighbourhood
/// that never existed on any single day.
export async function getRelevance(assetId: string) {
  const latest = await prisma.graphRelevance.aggregate({
    where: { assetId },
    _max: { periodEnd: true },
  });
  const periodEnd = latest._max.periodEnd;
  if (!periodEnd) return { periodEnd: null, rows: [] };
  const rows = await prisma.graphRelevance.findMany({
    where: { assetId, periodEnd },
    orderBy: { score: "desc" },
  });
  return { periodEnd, rows };
}


/// Every horizon's condition read for one asset, newest per horizon, with its target ranges.
///
/// One row per horizon rather than the single newest row, because the horizons are the point:
/// the same asset reading `buy` on the hour and `wait` on the quarter is not a contradiction to
/// be resolved by picking one. Returned in the order a reader thinks in — soonest first.
export async function getHorizons(assetId: string) {
  const all = await prisma.assetSetup.findMany({
    where: { assetId },
    orderBy: { periodEnd: "desc" },
    include: { targets: { orderBy: { method: "asc" } } },
  });
  const newest = new Map<string, (typeof all)[number]>();
  for (const row of all) if (!newest.has(row.horizon)) newest.set(row.horizon, row);
  const order = ["intraday", "swing", "longer"];
  return [...newest.values()].sort(
    (a, b) =>
      (order.indexOf(a.horizon) + 1 || 99) - (order.indexOf(b.horizon) + 1 || 99),
  );
}

/// The newest investigation for one asset, with every check and every hypothesis.
///
/// Findings ordered so the ones that found something come first and the ones that could not be
/// checked come last: a reader scanning the list wants the evidence before the gaps, and the
/// gaps are still there when they reach them.
export async function getInvestigation(assetId: string) {
  return prisma.investigation.findFirst({
    where: { assetId },
    orderBy: { periodEnd: "desc" },
    include: {
      findings: { orderBy: [{ status: "asc" }, { kind: "asc" }] },
      hypotheses: { orderBy: { label: "asc" } },
    },
  });
}


/// Whether the intraday series behind an intraday read can be trusted, and what is missing.
///
/// Returned even when every session is complete, because "we checked and it is complete" is a
/// different statement from showing nothing, and the second is indistinguishable from not
/// having looked.
export async function getIntradayHealth(assetId: string) {
  const sessions = await prisma.intradaySession.findMany({
    where: { assetId },
    orderBy: [{ sessionDate: "desc" }, { interval: "asc" }],
    take: 6,
  });
  const bars = await prisma.intradayBar.groupBy({
    by: ["interval"],
    where: { assetId },
    _count: { _all: true },
    _max: { ts: true },
  });
  return {
    sessions,
    intervals: bars
      .map((b) => ({ interval: b.interval, bars: b._count._all, newest: b._max.ts }))
      .sort((a, b) => a.interval - b.interval),
  };
}

/// How much intraday coverage exists across the site, for the methodology page.
///
/// Counts by status, including `unsupported`, because an asset this provider cannot serve is a
/// stored fact rather than a gap in the job, and the two must not be added together.
export async function getIntradayCoverage() {
  const latest = await prisma.intradaySession.aggregate({ _max: { sessionDate: true } });
  const sessionDate = latest._max.sessionDate;
  if (!sessionDate) return { sessionDate: null, counts: [] as { status: string; n: number }[] };
  const grouped = await prisma.intradaySession.groupBy({
    by: ["status"],
    where: { sessionDate },
    _count: { _all: true },
  });
  const order = ["complete", "partial", "stale", "empty", "failed", "unsupported"];
  return {
    sessionDate,
    counts: grouped
      .map((g) => ({ status: g.status, n: g._count._all }))
      .sort((a, b) => (order.indexOf(a.status) + 1 || 99) - (order.indexOf(b.status) + 1 || 99)),
  };
}


/// {industryId: how many of its assets have at least one stored close}.
///
/// The home page needs this to say *why* an industry has no ranking. "No ranking stored" on
/// its own reads as a bug; "its ten assets have no stored prices yet" is the actual state and
/// tells a reader whether to wait or to look into it.
export async function getPricedAssetsByIndustry(): Promise<Map<string, number>> {
  const withPrices = await prisma.priceSnapshot.groupBy({ by: ["assetId"] });
  if (!withPrices.length) return new Map();
  const assets = await prisma.asset.findMany({
    where: { id: { in: withPrices.map((r) => r.assetId) } },
    select: { industryId: true },
  });
  const out = new Map<string, number>();
  for (const a of assets) out.set(a.industryId, (out.get(a.industryId) ?? 0) + 1);
  return out;
}

/// The health of each source, newest reading per source, worst first.
///
/// `jobs/audit.py` has written these rows since the day coverage was added and no reader has
/// ever seen one. A feed that quietly dies looks exactly like a quiet week in the data, and
/// the whole point of the Coverage table is to tell those apart — which it cannot do for the
/// reader while it is only visible to whoever opens the database.
///
/// Deliberately returns the four reader-facing fields and not the arithmetic behind them.
/// `gapRatio`, `criticality` and `missRisk` are how the status is decided, not something a
/// reader needs on the page, and printing them would be exposing the mechanism as if it were
/// the finding.
export async function getSourceHealth(): Promise<
  { source: string; status: string; rows: number; newest: Date | null; note: string | null }[]
> {
  const rows = await prisma.coverage.findMany({
    orderBy: { computedAt: "desc" },
    select: { source: true, status: true, rows: true, newest: true, note: true, computedAt: true },
    take: 400,
  });
  const latest = new Map<string, (typeof rows)[number]>();
  for (const r of rows) if (!latest.has(r.source)) latest.set(r.source, r);
  // Worst first: a reader scanning this wants the fault, not the alphabet.
  const order = ["silent", "stale", "partial", "healthy"];
  return [...latest.values()]
    .sort(
      (a, b) =>
        (order.indexOf(a.status) + 1 || 99) - (order.indexOf(b.status) + 1 || 99) ||
        a.source.localeCompare(b.source),
    )
    .map(({ source, status, rows: n, newest, note }) => ({ source, status, rows: n, newest, note }));
}

/// The stories behind an asset's recent coverage, newest first.
///
/// `jobs/lineage.py` clusters headlines so that counting information stops counting copies: a
/// wire report picked up by twenty outlets is one story, and before clustering it looked
/// exactly like twenty. That distinction has been computed since the job was written and has
/// never reached a page, so a reader could not tell a developing situation from a press
/// release — the one confusion the clustering exists to end.
export async function getStories(assetId: string, take = 6) {
  return prisma.newsLineage.findMany({
    where: { targetRef: assetId },
    orderBy: { lastSeen: "desc" },
    take,
    select: {
      id: true, headline: true, items: true, publishers: true,
      firstSeen: true, lastSeen: true, rule: true,
    },
  });
}

/// The handful of headlines the asset page's top block may link to: 1 query.
///
/// `take` is generous relative to the three the panel shows, because the ranking happens after
/// the read: `rankHeadlines` drops the rows that are not about the business and then keeps one
/// row per story, so a window of twelve routinely reduces to four or five. Reading three would
/// mean the top block showed whichever three were newest, which is the thing being fixed.
///
/// Ordered by `publishedAt` here and re-ordered in `lib/newsRank.ts`. The database decides
/// which rows are recent; it does not decide which are material, because that rule has to be
/// readable and arguable in one file rather than spread into a SQL clause.
/// Market news and statements from the last `days` days, across every asset: 2 queries.
///
/// The event calendar is a list of *dated* items, and in a normal week almost all of them are
/// ex-dividend dates — eight of the first eight, on 2026-10-03. That is an honest calendar and a
/// poor answer to "what is happening this week", because the things that actually moved a price
/// in the last seven days were not on anybody's calendar: a refinery programme, a patent ruling,
/// a chip export story. None of those has a future date, so none of them can appear in a diary.
///
/// So this is deliberately a different kind of row from the ones above it on that page, and the
/// page says so. These have already been published; the calendar entries have not happened yet.
/// Mixing the two orderings would produce a list where "in 3 days" and "2 days ago" sit in one
/// column, which is the one thing a date-ordered page must not do.
///
/// Ranking is `lib/newsRank.ts`, the same reading the asset pages use, so a story that leads an
/// asset page is the story that leads here. The window is generous for the same reason it is
/// there: ranking drops the rows that are not about a business and then keeps one per story, so
/// a few hundred recent rows reduce to a few dozen.
export async function getRecentMarketNews(days = 7, take = 240) {
  const since = new Date(Date.now() - days * 86_400_000);
  const items = await prisma.news.findMany({
    where: { publishedAt: { gte: since }, assetId: { not: null } },
    orderBy: { publishedAt: "desc" },
    take,
    select: {
      id: true, title: true, url: true, publisher: true, publishedAt: true,
      lineageId: true, isOriginal: true,
      // No `market` column exists on Asset — it is derived from `assetType` by `marketOf`. Asking
      // for one here is the same trap `decisionInput.test.ts` guards on the decision side.
      asset: { select: { symbol: true, name: true, assetType: true } },
    },
  });

  const ids = [...new Set(items.map((n) => n.lineageId).filter((v): v is string => !!v))];
  const counts = ids.length
    ? new Map(
        (
          await prisma.newsLineage.findMany({
            where: { id: { in: ids } },
            select: { id: true, items: true },
          })
        ).map((l) => [l.id, l.items]),
      )
    : new Map<string, number>();

  return items.map((n) => ({
    ...n,
    outlets: (n.lineageId ? counts.get(n.lineageId) : null) ?? 1,
  }));
}

/// Two queries, not a join. `News.lineageId` is an indexed `String?` and not a Prisma relation
/// — `jobs/lineage.py` assigns it, and making it a foreign key would mean a migration to read a
/// count. So the stories the window actually references are fetched by id and attached here.
/// Two round trips against a free-tier endpoint is the cheaper of the two prices.
export async function getTopNews(assetId: string, take = 12) {
  const items = await prisma.news.findMany({
    where: { assetId },
    orderBy: { publishedAt: "desc" },
    take,
    select: {
      id: true, title: true, url: true, publisher: true, publishedAt: true,
      lineageId: true, isOriginal: true,
    },
  });

  const ids = [...new Set(items.map((n) => n.lineageId).filter((v): v is string => !!v))];
  const counts = ids.length
    ? new Map(
        (
          await prisma.newsLineage.findMany({
            where: { id: { in: ids } },
            select: { id: true, items: true },
          })
        ).map((l) => [l.id, l.items]),
      )
    : new Map<string, number>();

  // A row whose story is missing counts as one outlet rather than none: the row exists, so at
  // least one desk carried it, and 0 here would read as "nobody published this".
  return items.map((n) => ({
    ...n,
    outlets: (n.lineageId ? counts.get(n.lineageId) : null) ?? 1,
  }));
}

/// ---------------------------------------------------------------------------
/// The decision panel: one asset's read, and the same read across every asset.
/// ---------------------------------------------------------------------------

/// Every date below leaves as a `Date`, exactly as the rest of this file returns them.
/// Picked for consistency and not for convenience: a bundle whose `periodEnd` were an ISO
/// string while `getHorizons` next to it returned a `Date` would be the one place on the site
/// where two stored days could not be compared with `getTime()`, and that comparison — "is the
/// setup as new as the price?" — is the one the panel exists to make. The cost is that a caller
/// handing any of this to a client component must convert first. A `Date` survives the
/// serialization boundary; a formatted string would be this query's decision about a reader's
/// locale, which is not a query's decision to make.

/// The newest stored close for one asset: 1 query.
///
/// Pages have been answering "is what you are reading current?" by taking the last element of
/// `getAssetPrices`, which drags every close since 2019 across the wire to learn a single date.
/// The decision panel asks that question above the fold on every asset page, and a panel whose
/// whole job is to say how stale the data is must not itself be the slowest thing on the page.
/// The source travels with the date because "yesterday" means different things coming from
/// Yahoo and from the PSX closing file, and the panel says which one it is trusting.
export async function getAssetFreshness(assetId: string): Promise<{
  newest: Date | null;
  close: number | null;
  priceSource: string | null;
}> {
  const row = await prisma.priceSnapshot.findFirst({
    where: { assetId },
    orderBy: { date: "desc" },
    select: { date: true, close: true, source: true },
  });
  // All three null together rather than a bare null: "no close has ever been stored for this
  // asset" is a state the panel reports in words, and the caller should not have to branch on
  // the shape of the object to find out which of the three it is missing.
  if (!row) return { newest: null, close: null, priceSource: null };
  return { newest: row.date, close: row.close, priceSource: row.source };
}

/// Everything the decision panel on one asset page reads: 9 queries, issued together.
///
/// Flat and not nested. The panel's whole claim is that these readings are being looked at
/// together — a `buy` on the swing horizon next to a four-day-old close next to an
/// investigation that found nothing is a different statement from any one of them alone — and
/// a caller awaiting each piece separately would be free to render the ones that arrived and
/// drop the ones that did not, which is the selective reading the panel is built to prevent.
/// One `Promise.all` also puts the round-trip cost of the panel in one visible place.
///
/// `market`, `currency` and `assetType` are carried because US, PSX and crypto are not
/// interchangeable here: they keep different hours, so "newest close is yesterday" is healthy
/// for one and stale for another. `market` comes from the industry and never from the symbol —
/// the ticker PSX is Phillips 66, a US asset, and a panel that read the market off the letters
/// would call it Pakistani and then judge its freshness against the wrong calendar.
///
/// `factor` joins the same `Promise.all` rather than being awaited after it. It is one of the three
/// things the rule table can use to confirm a direction — volume against its own average, and the
/// name against its peer group — and a panel that fetched its confirmations in a second round trip
/// would be free to render the direction before they arrived, which is exactly the selective reading
/// argued against above.
export async function getDecisionBundle(assetId: string) {
  const [asset, freshness, horizons, analogs, humanSignal, investigation, upcoming, factor] =
    await Promise.all([
      prisma.asset.findUnique({
        where: { id: assetId },
        select: {
          symbol: true,
          name: true,
          assetType: true,
          currency: true,
          industry: { select: { market: true, slug: true, name: true } },
        },
      }),
      getAssetFreshness(assetId),
      // Reused rather than reimplemented: the reason one row per horizon is returned instead of
      // the single newest row is argued at `getHorizons`, and it already pulls the target ranges
      // the panel needs. Duplicating that logic here would let the panel and the horizons table
      // on the same page disagree about what the asset currently reads.
      getHorizons(assetId),
      getAnalogs(assetId),
      getHumanSignal({ assetId }),
      getInvestigation(assetId),
      // take 1: the panel shows the next dated thing, not a diary. A list here would compete
      // with the page's own events section and say the same thing twice.
      getUpcoming({ assetId, take: 1 }),
      // Newest row, by the same `periodEnd desc` rule every other reading on this panel uses, so
      // "the current factor" means the same day's measurement here, in `getDecisionRows` and in
      // `tools/decide.mjs`.
      getFactor(assetId),
    ]);

  return {
    assetId,
    symbol: asset?.symbol ?? null,
    name: asset?.name ?? null,
    assetType: asset?.assetType ?? null,
    currency: asset?.currency ?? null,
    market: asset?.industry.market ?? null,
    industrySlug: asset?.industry.slug ?? null,
    industryName: asset?.industry.name ?? null,
    newestClose: freshness.close,
    newestCloseDate: freshness.newest,
    priceSource: freshness.priceSource,
    horizons,
    analogPeriodEnd: analogs.periodEnd,
    // Whole rows, so `medianPct` and `positive` travel with the band. `getAnalogs` takes no
    // `select`, so those two columns were already arriving here — what was missing was never the
    // read, it was that nothing downstream looked at them. `QueryBundle.analogs` declares both as
    // optional and `bundleFromQuery` forwards them, so quoting a band and saying whether the
    // matched days leaned is now one object rather than two reads that could disagree.
    analogs: analogs.rows,
    humanSignal,
    investigation,
    nextEvent: upcoming[0] ?? null,
    // Shaped as `QueryBundle.factor` expects: the row itself when one exists, null when the factor
    // job has not written for this asset. Not flattened into two top-level fields, because
    // `{ volumeRatio: null, relStrength: null }` and "no factor row at all" are different states and
    // flattening them would make the second indistinguishable from the first.
    factor: factor
      ? {
          volumeRatio: factor.volumeRatio,
          relStrength: factor.relStrength,
          r20: factor.r20,
          entryTrigger: factor.entryTrigger,
          triggerDirection: factor.triggerDirection,
        }
      : null,
    factorPeriodEnd: factor?.periodEnd ?? null,
    /// How many peers the relative reading was taken over. Carried so a panel can say *why*
    /// `relStrength` is null — a group of four names rather than a measurement that came out even.
    factorPeers: factor?.peers ?? null,
  };
}

/// One horizon's stored read, reduced to the fields the home page's lists print.
export type DecisionSetup = {
  state: string;
  entryLevel: number | null;
  invalidateLevel: number | null;
  confidence: string;
  periodEnd: Date;
  headline: string;
  /// The condition read `jobs/setup.py` wrote, verbatim. Carried because the trend verdict
  /// inside it is the only record of which way a withheld direction pointed, and a `wait` row
  /// without it is a row that knows a direction and cannot say it. Parsed by
  /// `lib/setupConditions.ts`, never read as prose.
  conditions: string;
  /// The measured target ranges `jobs/horizons.py` computed for this setup, one row per method.
  ///
  /// Carried as the list and never reduced here. Rule 24: targets are never averaged, because
  /// three methods that disagree are three answers and their mean is a fourth that nothing
  /// measured. A reader that needs one picks a method and names it.
  targets: DecisionTarget[];
};

/// One measured target range, as `jobs/horizons.py` wrote it.
export type DecisionTarget = {
  /// "structure", "volatility" or "analog".
  method: string;
  low: number;
  high: number;
  /// Distance from the entry to the near edge, in percent. Signed: negative for a short.
  distancePct: number | null;
  /// Against the setup's own invalidation. Null when there is no invalidation, in which case
  /// `jobs/horizons.py` writes no target row at all.
  rewardRisk: number | null;
  /// What this range was measured from, and what it is not. Written by the job, shown verbatim.
  note: string;
};

/// What is *stored* about one asset, which is not the same thing as what the home page shows.
///
/// Named `DecisionQueryRow` rather than `DecisionRow` because `components/decision.tsx` already
/// owns that name for the rendered row — symbol, action, entry band, confidence — and the two are
/// deliberately different objects: this one is evidence, that one is a verdict, and the rule table
/// in `lib/decision.ts` is the only thing allowed to turn the first into the second. Sharing a
/// name would invite a page to pass one where the other was expected and have it very nearly work.
export type DecisionQueryRow = {
  assetId: string;
  symbol: string;
  name: string;
  assetType: string;
  currency: string;
  /// "US" or "PK", from the industry the asset sits in. Never inferred from the symbol.
  market: string;
  industrySlug: string;
  /// The industry's own name and sort order, for grouping a list into sectors.
  ///
  /// Stored, never derived from the slug: "psx-oil-gas" is not a heading and title-casing it
  /// would invent one. `sector` is what `jobs/seed.py` wrote and `sectorSort` is the order every
  /// other surface already shows industries in, so a sector cannot sit in one place on the
  /// stocks page and another on the overview.
  sector: string;
  sectorSort: number;
  close: number | null;
  closeDate: Date | null;
  priceSource: string | null;
  /// Only the two horizons the home page sorts on. Intraday is deliberately absent: a front
  /// page that re-ordered itself through the trading day would be a different page every time
  /// a reader came back to it, and none of the versions would be wrong.
  swing: DecisionSetup | null;
  longer: DecisionSetup | null;
  analogMinPct: number | null;
  analogMaxPct: number | null;
  analogMatches: number | null;
  /// Which horizon the analog band above was measured over. Carried because a band without its
  /// horizon is not a measurement, and the lists must not print one as if it were.
  analogHorizonDays: number | null;
  /// The middle outcome of the matched days, and how many of them rose.
  ///
  /// Both, never one. A range of -20% to +22% is the same range whether nine of ten matched days
  /// rose or one did, so `analogConfirms` in `lib/decision.ts` requires a majority *and* a median
  /// of the right sign before it will call an analog set confirmation. Selecting only the median
  /// would let a set where the losses were larger read as agreement.
  analogMedianPct: number | null;
  analogPositive: number | null;
  /// From the newest `AssetFactor`. `volumeRatio` is a multiple of this asset's own 20-session
  /// average (1.0 = average), `relStrength` is percentage points of 20-session return above or below
  /// the peer median. Both stay null where the measurement was not possible — no published volume,
  /// or a peer group `jobs/factors.py` judged too small — and the rules read a null as missing
  /// evidence rather than as evidence against.
  volumeRatio: number | null;
  relStrength: number | null;
  /// This asset's own 20-session return, read by the short gate in lib/decision.ts.
  r20: number | null;
  /// The entry rule that fired on this session and which way, for the fifth confirmation.
  /// Null on about nineteen sessions in twenty, which is the rule being silent and not a
  /// measurement that failed — see `DecisionInput.entryTrigger`.
  entryTrigger: string | null;
  triggerDirection: string | null;
  /// Stories, not items: twenty outlets carrying one wire report is one story. The reasoning is
  /// at `getStories` and on `HumanSignal.recentStories`.
  recentStories: number | null;
  /// The word-list verdict over the headlines that took a side, and whether the recent story
  /// rate spiked against its own baseline. Two different findings and both are carried: a mood
  /// held over a month is not an event, and the rules word them apart.
  ///
  /// Here because the rule table reads them -- an analog set stops confirming a direction the
  /// published coverage points away from -- and the asset-page bundle was already getting them
  /// for free from `getHumanSignal`, which takes no `select`. Without this line the home page
  /// and the asset page would apply that rule to different inputs for one name.
  newsTone: string | null;
  newsCatalyst: boolean | null;
  robustZ: number | null;
  movePct: number | null;
  trigger: string | null;
  nextEventDate: Date | null;
  nextEventName: string | null;
  nextEventInDays: number | null;
};

/// The horizons the home page reads. Named once so the `groupBy` and the `findMany` below
/// cannot drift apart, which would otherwise return a horizon `DecisionQueryRow` has no slot for and
/// silently drop it.
const DECISION_HORIZONS = ["swing", "longer"] as const;

/// Newest-first rows reduced to one per key, keeping the first seen — the same dedupe
/// `getSourceHealth`, `getNeighbourhood` and `getDirectionalSetups` each spell out inline.
function firstPerKey<T>(rows: T[], key: (row: T) => string): Map<string, T> {
  const out = new Map<string, T>();
  for (const row of rows) if (!out.has(key(row))) out.set(key(row), row);
  return out;
}

/// The analog row each asset's reading should quote, by the one rule that decides it.
///
/// `firstPerKey` cannot answer this. It keeps whatever the SQL ordering put first, which was
/// `horizonDays asc` — the 1-day row — while `pickAnalog` on the asset page prefers the 5-day
/// one, and the comment above that ordering claimed it was getting the 5-day band. So the home
/// list and the asset page quoted different measurements of the same asset: ABBV printed
/// "-11.0% to +16.1%" on its own page (5-day, 285 matches) and -7.0% to +8.7% in the list
/// (1-day, 286 matches).
///
/// Not cosmetic once the lean reaches the rules. WTL's 1-day row has a `medianPct` of exactly 0,
/// so the same asset would confirm on its own page and fail to confirm in the list and in the
/// nightly `DecisionLog`. Three readers of one table must not each pick their own row — rule 36 —
/// so all three now call `pickAnalog`, and this groups the rows so it can.
function analogPerAsset<T extends { assetId: string; horizonDays: number; matches: number }>(
  rows: T[],
): Map<string, T> {
  const grouped = new Map<string, T[]>();
  for (const row of rows) {
    const list = grouped.get(row.assetId);
    if (list) list.push(row);
    else grouped.set(row.assetId, [row]);
  }
  const out = new Map<string, T>();
  for (const [assetId, list] of grouped) {
    const picked = pickAnalog(list);
    if (picked) out.set(assetId, picked);
  }
  return out;
}

/// The distinct days a per-asset `_max` aggregate came back with. Deduped by millisecond
/// because the jobs write every asset on the same two or three dates, so 120 aggregate rows
/// collapse to a handful of values — which is what makes the second query below cheap.
function distinctDays(maxes: (Date | null)[]): Date[] {
  const seen = new Map<number, Date>();
  for (const d of maxes) if (d) seen.set(d.getTime(), d);
  return [...seen.values()];
}

/// One row per asset for the home page's three lists: 14 queries, in two waves.
///
/// That number does not change when the asset list grows. The obvious shape — call
/// `getDecisionBundle` once per asset — would be eight queries per name across 120-odd US
/// tickers plus the PSX names plus crypto, so roughly a thousand round trips to paint one page.
/// Against Neon's free tier that is not a slow page; it is a page that exhausts the connection
/// pool and fails, and fails worse the more assets the site covers. So every table is read in
/// bulk and stitched together here.
///
/// Each table costs two queries, and the split is the point:
///
///   1. a `groupBy` asking Postgres for the newest stored day per asset. This half has to
///      happen in the database — it reads an index and returns one small row per asset instead
///      of the table.
///   2. a `findMany` confined to the few distinct days that came back, deduped here.
///
/// Step 2 filters on `periodEnd in (those days)` rather than on 120 explicit (asset, day) pairs
/// because the jobs write every asset on the same handful of dates, so the day filter is nearly
/// exact at a fraction of the SQL. It over-fetches only rows belonging to an asset that also
/// has a row on some *other* asset's newest day, bounded by assets x distinct-days. Correctness
/// does not rest on that staying small: each asset's own newest day is guaranteed to be in the
/// set, and the dedupe keeps the newest row it sees per asset, so an asset that stopped being
/// written still yields its own stale row rather than someone else's fresh one.
///
/// `distinct` was considered and rejected. Without the `nativeDistinct` preview feature Prisma
/// deduplicates in the client, so `distinct: ["assetId"]` on PriceSnapshot would pull every
/// close since 2019 into Node to learn 120 dates — the exact waste `getAssetFreshness` exists
/// to end, moved to the page that can least afford it.
///
/// `AssetFactor` was added as a fourteenth query — one more table, so one more pair of waves — and
/// it was added as a pair rather than as a `findFirst` inside the `assets.map` below for the reason
/// this whole function exists. A per-asset read there is 160 round trips today and one per name
/// forever after, which on Neon's free tier is the failure mode described above and not merely a
/// slower page. Two bulk queries cost the same whether the universe is 160 names or 1,000.
export async function getDecisionRows(): Promise<DecisionQueryRow[]> {
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);

  // Wave one: the asset list, the newest day per asset in each table, and the forward diary.
  const [
    assets,
    newestPrices,
    setupDays,
    analogDays,
    signalDays,
    investigationDays,
    factorDays,
    eventLinks,
  ] = await Promise.all([
      prisma.asset.findMany({
        orderBy: [{ symbol: "asc" }],
        select: {
          id: true,
          symbol: true,
          name: true,
          assetType: true,
          currency: true,
          // `name` and `sort` ride along with the slug they already travelled with. The class
          // pages group their rows by sector, and a group needs a heading a reader recognises
          // and an order that is the same on every page -- both of which are columns on
          // `Industry` and neither of which was being selected.
          industry: { select: { market: true, slug: true, name: true, sort: true } },
        },
      }),
      // **The newest close per asset, by one index probe per asset rather than by reading the
      // table.** This was `groupBy({ by: ["assetId"], _max: { date: true } })`, and the comment
      // above claimed it "reads an index and returns one small row per asset instead of the
      // table". Measured on 2026-10-10 against 628,675 stored closes, it does not: Postgres has
      // no loose index scan for `GROUP BY assetId, max(date)` and plans a **parallel sequential
      // scan of the whole table** -- 13,061 shared buffers, about 102 MB of buffer traffic, 209
      // ms -- on every render of every list page.
      //
      // An index does not fix it. `(assetId, date DESC)` was built and measured and the planner
      // still chose the seq scan: same buffers, same time, 41 MB spent for nothing. It was
      // dropped again.
      //
      // The shape fixes it. A lateral probe per asset walks the primary key backwards once per
      // name -- 477 index lookups against a 628,675-row scan -- and it fetches the close and the
      // source at the same time, which is why the second price query below is gone:
      //
      //     groupBy + findMany        13,061 buffers     209 ms
      //     one lateral               1,921 buffers      3.2 ms
      //
      // Raw because Prisma cannot express a lateral join. The cost of that is the hand-written
      // row type below and the `$queryRaw` tag, and the thing bought is the hottest query on the
      // site going from reading the whole price history to reading an index -- which on a
      // metered endpoint is compute time on every request, not merely a slow page.
      prisma.$queryRaw<
        { assetId: string; date: Date | null; close: number | null; source: string | null }[]
      >`
        SELECT a.id AS "assetId", p.date, p.close, p.source
          FROM "Asset" a
          LEFT JOIN LATERAL (
            SELECT s.date, s.close, s.source
              FROM "PriceSnapshot" s
             WHERE s."assetId" = a.id
             ORDER BY s.date DESC
             LIMIT 1
          ) p ON true
      `,
      prisma.assetSetup.groupBy({
        by: ["assetId", "horizon"],
        where: { horizon: { in: [...DECISION_HORIZONS] } },
        _max: { periodEnd: true },
      }),
      prisma.assetAnalog.groupBy({ by: ["assetId"], _max: { periodEnd: true } }),
      // HumanSignal also describes products, which have no place in a list of assets.
      prisma.humanSignal.groupBy({
        by: ["assetId"],
        where: { assetId: { not: null } },
        _max: { periodEnd: true },
      }),
      prisma.investigation.groupBy({ by: ["assetId"], _max: { periodEnd: true } }),
      prisma.assetFactor.groupBy({ by: ["assetId"], _max: { periodEnd: true } }),
      // One query for the whole site's forward diary — small enough to read whole, so it skips
      // the two-step. Ordered by the event's own date, ascending, so the dedupe keeps the
      // *soonest* event per asset: a diary has only one order, and it is not "newest written".
      // The `scheduled` flag and the date are both tested for the reason given at `getUpcoming`.
      prisma.eventLink.findMany({
        where: { assetId: { not: null }, event: { scheduled: true, date: { gte: today } } },
        orderBy: { event: { date: "asc" } },
        select: { assetId: true, event: { select: { name: true, date: true } } },
      }),
    ]);

  // PriceSnapshot dates its rows `date` rather than `periodEnd`, so its aggregate is unwrapped
  // here instead of teaching the helper both column names.
  // `priceDayList` is gone with the query that produced it: the lateral above already returned
  // one row per asset, so there is no day list to filter a second read by and no second read.
  const setupDayList = distinctDays(setupDays.map((r) => r._max.periodEnd));
  const analogDayList = distinctDays(analogDays.map((r) => r._max.periodEnd));
  const signalDayList = distinctDays(signalDays.map((r) => r._max.periodEnd));
  const investigationDayList = distinctDays(investigationDays.map((r) => r._max.periodEnd));
  const factorDayList = distinctDays(factorDays.map((r) => r._max.periodEnd));

  // Wave two: the rows themselves, confined to the days wave one named. Each `findMany` is
  // skipped outright when its table turned out to be empty, because `in: []` is a query that can
  // only return nothing and still costs a round trip on a free-tier database.
  const [setups, analogs, signals, investigations, factors] = await Promise.all([
    setupDayList.length
      ? prisma.assetSetup.findMany({
          where: { horizon: { in: [...DECISION_HORIZONS] }, periodEnd: { in: setupDayList } },
          orderBy: { periodEnd: "desc" },
          select: {
            assetId: true,
            horizon: true,
            state: true,
            entryLevel: true,
            invalidateLevel: true,
            conditions: true,
            confidence: true,
            periodEnd: true,
            headline: true,
            // One extra relation on a read that was already happening. The weekly block needs a
            // measured exit as well as a measured stop, and inventing one in the web layer is
            // exactly what `jobs/` exists to prevent.
            targets: {
              orderBy: { method: "asc" },
              select: {
                method: true, low: true, high: true,
                distancePct: true, rewardRisk: true, note: true,
              },
            },
          },
        })
      : [],
    analogDayList.length
      ? prisma.assetAnalog.findMany({
          where: { periodEnd: { in: analogDayList } },
          // Shortest horizon first within a day, so the dedupe keeps the nearest-term analog.
          // The lists ask "what now", and a 5-day band answers that; letting a 60-day band win
          // on some assets would print two different measurements in one column.
          orderBy: [{ periodEnd: "desc" }, { horizonDays: "asc" }],
          // `medianPct` and `positive` ride along with the band they describe. Two more columns on
          // a read that was already happening, not a second query: the lean and the range are one
          // measurement of one row, and fetching them apart would let the lists print a band from
          // one day next to a lean from another.
          select: {
            assetId: true,
            horizonDays: true,
            minPct: true,
            maxPct: true,
            matches: true,
            medianPct: true,
            positive: true,
          },
        })
      : [],
    signalDayList.length
      ? prisma.humanSignal.findMany({
          where: { assetId: { not: null }, periodEnd: { in: signalDayList } },
          orderBy: { periodEnd: "desc" },
          select: { assetId: true, recentStories: true, tone: true, catalyst: true },
        })
      : [],
    investigationDayList.length
      ? prisma.investigation.findMany({
          where: { periodEnd: { in: investigationDayList } },
          orderBy: { periodEnd: "desc" },
          select: { assetId: true, robustZ: true, movePct: true, trigger: true },
        })
      : [],
    // `periodEnd desc` and nothing else, matching the `DISTINCT ON ("assetId") ... ORDER BY
    // "assetId", "periodEnd" DESC` that `tools/decide.mjs` uses for the same table. Both must agree
    // about which stored row is the current reading, or the nightly log and the home page would
    // grade the same asset differently on a day the factor job wrote twice.
    factorDayList.length
      ? prisma.assetFactor.findMany({
          where: { periodEnd: { in: factorDayList } },
          orderBy: { periodEnd: "desc" },
          select: {
            assetId: true,
            volumeRatio: true,
            relStrength: true,
            r20: true,
            entryTrigger: true,
            triggerDirection: true,
          },
        })
      : [],
  ]);

  // One row per asset already, by construction: the lateral returns exactly one per `Asset`.
  // `firstPerKey` is kept rather than a plain Map so an asset with no stored close -- the
  // LEFT JOIN's null row -- is treated the same way it was when the day filter could miss it.
  const priceByAsset = firstPerKey(newestPrices, (r) => r.assetId);
  const setupByKey = firstPerKey(setups, (r) => `${r.assetId}|${r.horizon}`);
  const analogByAsset = analogPerAsset(analogs);
  // HumanSignal and EventLink both carry a nullable assetId, already excluded in SQL above. The
  // `?? ""` exists to satisfy the type and can never key a row that reaches this point.
  const signalByAsset = firstPerKey(signals, (r) => r.assetId ?? "");
  const investigationByAsset = firstPerKey(investigations, (r) => r.assetId);
  const factorByAsset = firstPerKey(factors, (r) => r.assetId);
  const eventByAsset = firstPerKey(eventLinks, (r) => r.assetId ?? "");

  const DAY = 24 * 60 * 60 * 1000;

  const setupOf = (assetId: string, horizon: string): DecisionSetup | null => {
    const row = setupByKey.get(`${assetId}|${horizon}`);
    if (!row) return null;
    return {
      state: row.state,
      entryLevel: row.entryLevel,
      invalidateLevel: row.invalidateLevel,
      confidence: row.confidence,
      periodEnd: row.periodEnd,
      headline: row.headline,
      conditions: row.conditions,
      targets: row.targets ?? [],
    };
  };

  // Every asset gets a row, including one with nothing stored against it. Returning only the
  // assets that happen to have a setup would make the three lists add up to fewer names than the
  // site covers, and a reader counting them would read that gap as a judgement about the missing
  // ones rather than as a job that has not run.
  return assets.map((asset): DecisionQueryRow => {
    const price = priceByAsset.get(asset.id);
    const analog = analogByAsset.get(asset.id);
    const signal = signalByAsset.get(asset.id);
    const investigation = investigationByAsset.get(asset.id);
    const factor = factorByAsset.get(asset.id);
    const event = eventByAsset.get(asset.id);
    return {
      assetId: asset.id,
      symbol: asset.symbol,
      name: asset.name,
      assetType: asset.assetType,
      currency: asset.currency,
      market: asset.industry.market,
      industrySlug: asset.industry.slug,
      sector: asset.industry.name,
      sectorSort: asset.industry.sort,
      close: price?.close ?? null,
      closeDate: price?.date ?? null,
      priceSource: price?.source ?? null,
      swing: setupOf(asset.id, "swing"),
      longer: setupOf(asset.id, "longer"),
      analogMinPct: analog?.minPct ?? null,
      analogMaxPct: analog?.maxPct ?? null,
      analogMatches: analog?.matches ?? null,
      analogHorizonDays: analog?.horizonDays ?? null,
      analogMedianPct: analog?.medianPct ?? null,
      analogPositive: analog?.positive ?? null,
      // `?? null` collapses "no factor row for this asset" and "a factor row whose column was
      // null" into the same value, and here that is correct rather than lazy: both mean the
      // measurement is unavailable, and `lib/decision.ts` already treats an unavailable reading as
      // missing evidence. The asset-page bundle keeps the two apart, because a panel can afford a
      // sentence explaining which it is and a row in a list cannot.
      volumeRatio: factor?.volumeRatio ?? null,
      relStrength: factor?.relStrength ?? null,
      r20: factor?.r20 ?? null,
      entryTrigger: factor?.entryTrigger ?? null,
      triggerDirection: factor?.triggerDirection ?? null,
      recentStories: signal?.recentStories ?? null,
      newsTone: signal?.tone ?? null,
      newsCatalyst: signal?.catalyst ?? null,
      robustZ: investigation?.robustZ ?? null,
      movePct: investigation?.movePct ?? null,
      trigger: investigation?.trigger ?? null,
      nextEventDate: event?.event.date ?? null,
      nextEventName: event?.event.name ?? null,
      // Whole days from today, rounded. Both ends are already UTC midnight — `date` is a
      // `@db.Date` and `today` was floored above — so this is a subtraction and not a timezone
      // calculation wearing one's clothes.
      nextEventInDays: event
        ? Math.round((event.event.date.getTime() - today.getTime()) / DAY)
        : null,
    };
  });
}
