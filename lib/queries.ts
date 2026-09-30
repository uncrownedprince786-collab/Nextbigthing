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
