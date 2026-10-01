import { prisma } from "@/lib/db";

/// Pages read precomputed rows only. No page fetches an external API.
export async function getLead() {
  return prisma.analysis.findFirst({ where: { kind: "siteLead" }, orderBy: { createdAt: "desc" } });
}

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

/// Everything with a catalyst flagged on its newest reading, assets and products together.
///
/// This is the miss-reduction list: the point is to see, in one place, what has started
/// being written about in the last few days. Ordered by how far above its own baseline the
/// coverage is running, because a tenfold jump on a quiet name is more likely to be the thing
/// a reader had not noticed than a 50% rise on a name that is always in the news.
export async function getCatalysts(take = 12) {
  const latest = await prisma.humanSignal.aggregate({ _max: { periodEnd: true } });
  const periodEnd = latest._max.periodEnd;
  if (!periodEnd) return { periodEnd: null, rows: [] };
  const rows = await prisma.humanSignal.findMany({
    where: { periodEnd, catalyst: true },
    orderBy: [{ spikeRatio: "desc" }],
    take,
    include: {
      asset: { select: { symbol: true, name: true } },
      product: { select: { slug: true, name: true } },
    },
  });
  return { periodEnd, rows };
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

/// The strongest path per asset across the whole site, for the reading list on the front
/// page.
///
/// One row per asset, not one per path: an asset reached from four origins has not been
/// connected to the news four times, and listing it four times would turn a busy
/// neighbourhood into an apparent pile of evidence.
export async function getNeighbourhood(take = 9) {
  const latest = await prisma.graphRelevance.aggregate({ _max: { periodEnd: true } });
  const periodEnd = latest._max.periodEnd;
  if (!periodEnd) return { periodEnd: null, rows: [] };
  const all = await prisma.graphRelevance.findMany({
    where: { periodEnd },
    orderBy: { score: "desc" },
    include: { asset: { select: { symbol: true, name: true } } },
  });
  const best = new Map<string, (typeof all)[number]>();
  for (const r of all) if (!best.has(r.assetId)) best.set(r.assetId, r);
  return { periodEnd, rows: [...best.values()].slice(0, take) };
}

/// How the recorded reasons behind the site's directional reads are holding up.
///
/// Counts per status, never a share: "68% still active" would read as a hit rate, and this
/// measures whether conditions have changed rather than whether anything worked.
export async function getThesisTally() {
  const latest = await prisma.assetThesis.aggregate({ _max: { asOf: true } });
  const asOf = latest._max.asOf;
  if (!asOf) return { asOf: null, counts: [] as { status: string; n: number }[] };
  const grouped = await prisma.assetThesis.groupBy({
    by: ["status"],
    where: { asOf },
    _count: { _all: true },
  });
  const order = ["active", "weakening", "broken"];
  return {
    asOf,
    counts: grouped
      .map((g) => ({ status: g.status, n: g._count._all }))
      .sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status)),
  };
}
