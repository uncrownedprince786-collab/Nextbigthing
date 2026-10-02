import { prisma } from "@/lib/db";


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
  if (!rows.length) return [];
  const latest = rows[0].periodEnd;
  return rows.filter((r) => r.periodEnd.getTime() === latest.getTime());
}

export async function getAllIndustriesByBasis(basis: Basis) {
  const rows = await prisma.ranking.findMany({
    where: { basis },
    orderBy: [{ periodEnd: "desc" }, { rank: "asc" }],
    include: { asset: { include: { industry: true } } },
  });
  const latest = new Map<string, Date>();
  for (const r of rows) {
    const key = r.industryId;
    const seen = latest.get(key);
    if (!seen || r.periodEnd > seen) latest.set(key, r.periodEnd);
  }
  return rows.filter((r) => r.periodEnd.getTime() === latest.get(r.industryId)!.getTime());
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

export async function getEvents() {
  return prisma.event.findMany({
    orderBy: { date: "desc" },
    include: {
      analysis: { orderBy: { createdAt: "desc" }, take: 1 },
      _count: { select: { impacts: true } },
    },
  });
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

/// Everything the decision panel on one asset page reads: 8 queries, issued together.
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
export async function getDecisionBundle(assetId: string) {
  const [asset, freshness, horizons, analogs, humanSignal, investigation, upcoming] =
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
    analogs: analogs.rows,
    humanSignal,
    investigation,
    nextEvent: upcoming[0] ?? null,
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
  /// Stories, not items: twenty outlets carrying one wire report is one story. The reasoning is
  /// at `getStories` and on `HumanSignal.recentStories`.
  recentStories: number | null;
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

/// The distinct days a per-asset `_max` aggregate came back with. Deduped by millisecond
/// because the jobs write every asset on the same two or three dates, so 120 aggregate rows
/// collapse to a handful of values — which is what makes the second query below cheap.
function distinctDays(maxes: (Date | null)[]): Date[] {
  const seen = new Map<number, Date>();
  for (const d of maxes) if (d) seen.set(d.getTime(), d);
  return [...seen.values()];
}

/// One row per asset for the home page's three lists: 12 queries, in two waves.
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
export async function getDecisionRows(): Promise<DecisionQueryRow[]> {
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);

  // Wave one: the asset list, the newest day per asset in each table, and the forward diary.
  const [assets, priceDays, setupDays, analogDays, signalDays, investigationDays, eventLinks] =
    await Promise.all([
      prisma.asset.findMany({
        orderBy: [{ symbol: "asc" }],
        select: {
          id: true,
          symbol: true,
          name: true,
          assetType: true,
          currency: true,
          industry: { select: { market: true, slug: true } },
        },
      }),
      prisma.priceSnapshot.groupBy({ by: ["assetId"], _max: { date: true } }),
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
  const priceDayList = distinctDays(priceDays.map((r) => r._max.date));
  const setupDayList = distinctDays(setupDays.map((r) => r._max.periodEnd));
  const analogDayList = distinctDays(analogDays.map((r) => r._max.periodEnd));
  const signalDayList = distinctDays(signalDays.map((r) => r._max.periodEnd));
  const investigationDayList = distinctDays(investigationDays.map((r) => r._max.periodEnd));

  // Wave two: the rows themselves, confined to the days wave one named. Each `findMany` is
  // skipped outright when its table turned out to be empty, because `in: []` is a query that can
  // only return nothing and still costs a round trip on a free-tier database.
  const [prices, setups, analogs, signals, investigations] = await Promise.all([
    priceDayList.length
      ? prisma.priceSnapshot.findMany({
          where: { date: { in: priceDayList } },
          orderBy: { date: "desc" },
          select: { assetId: true, date: true, close: true, source: true },
        })
      : [],
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
            confidence: true,
            periodEnd: true,
            headline: true,
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
          select: { assetId: true, horizonDays: true, minPct: true, maxPct: true, matches: true },
        })
      : [],
    signalDayList.length
      ? prisma.humanSignal.findMany({
          where: { assetId: { not: null }, periodEnd: { in: signalDayList } },
          orderBy: { periodEnd: "desc" },
          select: { assetId: true, recentStories: true },
        })
      : [],
    investigationDayList.length
      ? prisma.investigation.findMany({
          where: { periodEnd: { in: investigationDayList } },
          orderBy: { periodEnd: "desc" },
          select: { assetId: true, robustZ: true, movePct: true, trigger: true },
        })
      : [],
  ]);

  const priceByAsset = firstPerKey(prices, (r) => r.assetId);
  const setupByKey = firstPerKey(setups, (r) => `${r.assetId}|${r.horizon}`);
  const analogByAsset = firstPerKey(analogs, (r) => r.assetId);
  // HumanSignal and EventLink both carry a nullable assetId, already excluded in SQL above. The
  // `?? ""` exists to satisfy the type and can never key a row that reaches this point.
  const signalByAsset = firstPerKey(signals, (r) => r.assetId ?? "");
  const investigationByAsset = firstPerKey(investigations, (r) => r.assetId);
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
    const event = eventByAsset.get(asset.id);
    return {
      assetId: asset.id,
      symbol: asset.symbol,
      name: asset.name,
      assetType: asset.assetType,
      currency: asset.currency,
      market: asset.industry.market,
      industrySlug: asset.industry.slug,
      close: price?.close ?? null,
      closeDate: price?.date ?? null,
      priceSource: price?.source ?? null,
      swing: setupOf(asset.id, "swing"),
      longer: setupOf(asset.id, "longer"),
      analogMinPct: analog?.minPct ?? null,
      analogMaxPct: analog?.maxPct ?? null,
      analogMatches: analog?.matches ?? null,
      analogHorizonDays: analog?.horizonDays ?? null,
      recentStories: signal?.recentStories ?? null,
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
