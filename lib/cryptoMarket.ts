// The whole crypto market as one table, built from two reads and nothing else.
//
// **Why this exists beside `lib/queries.ts`.** The asset page answers seventeen separate questions
// about one coin and takes seven to ten seconds doing it against a free-tier pooler capped at two
// connections. A market table that reached for any of that machinery would be that page times
// seventy-six. So this is one SQL statement and one HTTP call, and it is the only thing either
// crypto page reads to list coins.
//
// The SQL is two lateral joins -- the newest close and the close a week before it, per coin --
// which the planner answers from the `(assetId, date)` primary key as two index seeks each.
// Measured at 324 ms for all 76 coins, against 36 s for the obvious `ORDER BY date DESC` over the
// whole table.
//
// The HTTP call is Binance's bulk 24-hour ticker, which returns the last trade, the 24-hour change
// and the 24-hour quote volume for every requested symbol in one response. The alternative --
// a venue call per coin -- is seventy-six round trips to show one page.
//
// What comes from where, and why neither alone is enough: the venue has the live price and no idea
// what a coin's market capitalisation is; the database has the capitalisation and a close that is
// as old as the last time the daily job ran. Each number is taken from the source that actually
// knows it, and `priceAt` says which one answered.

import { prisma } from "@/lib/db";
import { VENUE_ROWS } from "@/lib/cryptoVenues";

export interface CoinRow {
  rank: number;
  slug: string;
  name: string;
  /// The ticker a reader recognises -- BTC, ETH -- derived from the venue pair, not the slug.
  ticker: string;
  price: number | null;
  /// Where `price` came from. A stored close is marked so a stale daily job is visible as staleness
  /// rather than passed off as a live quote.
  priceAt: "venue" | "close" | null;
  change24h: number | null;
  change7d: number | null;
  marketCap: number | null;
  volume24h: number | null;
  /// True when some venue in the chain serves this coin's bars, so a direction can be asked for.
  tradable: boolean;
  closeDate: Date | null;
}

export interface MarketTable {
  coins: CoinRow[];
  totalMarketCap: number;
  totalVolume24h: number;
  dominance: { btc: number | null; eth: number | null };
  /// How many rows carry a live venue price rather than a stored close.
  liveRows: number;
  venueOk: boolean;
  fetchedAt: string;
}

interface Row {
  symbol: string;
  name: string;
  lastClose: number | null;
  lastDate: Date | null;
  marketCap: number | null;
  weekAgoClose: number | null;
}

interface Ticker {
  lastPrice: number;
  changePct: number;
  quoteVolume: number;
}

/// The ticker a coin is known by, from its venue pair with the quote currency removed.
///
/// `BTCUSDT` -> `BTC`. Read from the pair rather than the slug because the slug is CoinPaprika's
/// and does not always agree -- `fetch-ai` is FET, `pol-polygon-ecosystem-token` is POL -- and a
/// table that prints a symbol nobody trades under is a table a reader cannot search.
function tickerOf(slug: string, pair: string | null): string {
  if (pair) return pair.replace(/(USDT|USDC|USD|BUSD)$/, "") || pair;
  const head = slug.split("-")[0];
  return head.toUpperCase();
}

/// Binance's 24-hour ticker for every pair we can name, in one request.
///
/// Returns an empty map rather than throwing. A market table with stored closes and no 24-hour
/// column is a worse page; a market table that 500s because a public endpoint rate-limited us is
/// not a page at all.
async function bulkTicker(pairs: string[]): Promise<Map<string, Ticker>> {
  const out = new Map<string, Ticker>();
  if (pairs.length === 0) return out;
  const url =
    "https://data-api.binance.vision/api/v3/ticker/24hr?symbols=" +
    encodeURIComponent(JSON.stringify(pairs));
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "nextbigthing" },
      // The page itself is revalidated; this must not be served from a second, longer-lived cache
      // underneath it, or the "live" column would be older than the page claiming it.
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return out;
    const body: unknown = await res.json();
    if (!Array.isArray(body)) return out;
    for (const r of body) {
      const t = r as Record<string, unknown>;
      const sym = typeof t.symbol === "string" ? t.symbol : null;
      const last = Number(t.lastPrice);
      if (!sym || !Number.isFinite(last) || last <= 0) continue;
      out.set(sym, {
        lastPrice: last,
        changePct: Number(t.priceChangePercent),
        quoteVolume: Number(t.quoteVolume),
      });
    }
  } catch {
    // Named as an absence by the caller (`venueOk`), never as a zero.
    return out;
  }
  return out;
}

/// Every coin, ranked by market capitalisation, with a live price where a venue has one.
export async function marketTable(): Promise<MarketTable> {
  const pairBySlug = new Map(VENUE_ROWS.map((v) => [v.slug, v.binance]));
  const tradable = new Set(
    VENUE_ROWS.filter((v) => v.binance || v.coinbase || v.kraken).map((v) => v.slug),
  );

  const [rows, tickers] = await Promise.all([
    prisma.$queryRaw<Row[]>`
      SELECT a.symbol, a.name,
             n.close        AS "lastClose",
             n.date         AS "lastDate",
             n."marketCap"  AS "marketCap",
             w.close        AS "weekAgoClose"
        FROM "Asset" a
        LEFT JOIN LATERAL (
               SELECT close, date, "marketCap" FROM "PriceSnapshot"
                WHERE "assetId" = a.id ORDER BY date DESC LIMIT 1) n ON true
        LEFT JOIN LATERAL (
               SELECT close FROM "PriceSnapshot"
                WHERE "assetId" = a.id AND date <= (CURRENT_DATE - INTERVAL '7 days')
                ORDER BY date DESC LIMIT 1) w ON true
       WHERE a."assetType" = 'crypto'
       ORDER BY n."marketCap" DESC NULLS LAST`,
    bulkTicker([...new Set(VENUE_ROWS.map((v) => v.binance).filter((p): p is string => !!p))]),
  ]);

  const coins: CoinRow[] = rows.map((r, i) => {
    const pair = pairBySlug.get(r.symbol) ?? null;
    const t = pair ? tickers.get(pair) : undefined;
    const price = t?.lastPrice ?? r.lastClose ?? null;
    // Seven days is measured from whichever price is being shown, so the column is consistent with
    // the one beside it. Comparing a live price against a stored close is the right comparison --
    // both are prices of the same coin -- and comparing a stored close against a stored close when
    // the venue is down is still the right one.
    const week =
      price !== null && r.weekAgoClose && r.weekAgoClose > 0
        ? (price / r.weekAgoClose - 1) * 100
        : null;
    return {
      rank: i + 1,
      slug: r.symbol,
      name: r.name,
      ticker: tickerOf(r.symbol, pair),
      price,
      priceAt: t ? "venue" : r.lastClose !== null ? "close" : null,
      change24h: t && Number.isFinite(t.changePct) ? t.changePct : null,
      change7d: week,
      marketCap: r.marketCap ?? null,
      volume24h: t && Number.isFinite(t.quoteVolume) ? t.quoteVolume : null,
      tradable: tradable.has(r.symbol),
      closeDate: r.lastDate ?? null,
    };
  });

  const totalMarketCap = coins.reduce((s, c) => s + (c.marketCap ?? 0), 0);
  const totalVolume24h = coins.reduce((s, c) => s + (c.volume24h ?? 0), 0);
  const capOf = (slug: string) => coins.find((c) => c.slug === slug)?.marketCap ?? null;
  const share = (cap: number | null) =>
    cap !== null && totalMarketCap > 0 ? (cap / totalMarketCap) * 100 : null;

  return {
    coins,
    totalMarketCap,
    totalVolume24h,
    // Dominance over the coins this site covers, which is not the whole market. The header says so;
    // a figure computed over 76 names and labelled as though it were computed over 8,000 would be
    // a number that looks like CoinMarketCap's and is not.
    dominance: { btc: share(capOf("btc-bitcoin")), eth: share(capOf("eth-ethereum")) },
    liveRows: coins.filter((c) => c.priceAt === "venue").length,
    venueOk: tickers.size > 0,
    fetchedAt: new Date().toISOString(),
  };
}

export interface CoinSnapshot {
  assetId: string;
  slug: string;
  name: string;
  ticker: string;
  price: number | null;
  priceAt: "venue" | "close" | null;
  change24h: number | null;
  change24hAbs: number | null;
  high24h: number | null;
  low24h: number | null;
  volume24h: number | null;
  marketCap: number | null;
  closeDate: Date | null;
  tradable: boolean;
}

/// Everything the top of a coin page needs, in one SQL statement and one ticker call.
///
/// Deliberately not `getAsset`: that returns the industry, the factors, the setups and the rest of
/// what the five-market asset page renders, and this page shows a price and a direction. The cost
/// of a page is the questions it asks, so this asks two.
export async function coinSnapshot(slug: string): Promise<CoinSnapshot | null> {
  const row = VENUE_ROWS.find((v) => v.slug === slug) ?? null;
  const pair = row?.binance ?? null;

  // The typed client, not `$queryRaw`. The slug here is a URL path segment -- the one piece of
  // user input the web layer has -- and `tests/test_brain.py` refuses any interpolation into a raw
  // template for exactly that reason. Prisma's tagged template does parameterise `${}`, but a
  // guard that cannot tell a safe interpolation from an unsafe one is the guard worth keeping, so
  // this is written the way the guard wants rather than the guard being loosened to fit it. It
  // costs nothing: `(assetId, date)` is the primary key, so the ordered take-1 is one index seek.
  const [found, tickers] = await Promise.all([
    prisma.asset.findFirst({
      where: { assetType: "crypto", symbol: slug },
      select: {
        id: true,
        symbol: true,
        name: true,
        snapshots: {
          orderBy: { date: "desc" },
          take: 1,
          select: { close: true, date: true, marketCap: true },
        },
      },
    }),
    pair ? bulkTickerFull([pair]) : Promise.resolve(new Map<string, FullTicker>()),
  ]);

  if (!found) return null;
  const newest = found.snapshots[0] ?? null;
  const a = {
    id: found.id,
    symbol: found.symbol,
    name: found.name,
    lastClose: newest?.close ?? null,
    lastDate: newest?.date ?? null,
    marketCap: newest?.marketCap ?? null,
  };
  const t = pair ? tickers.get(pair) : undefined;
  return {
    assetId: a.id,
    slug: a.symbol,
    name: a.name,
    ticker: tickerOf(a.symbol, pair),
    price: t?.lastPrice ?? a.lastClose ?? null,
    priceAt: t ? "venue" : a.lastClose !== null ? "close" : null,
    change24h: t && Number.isFinite(t.changePct) ? t.changePct : null,
    change24hAbs: t && Number.isFinite(t.change) ? t.change : null,
    high24h: t && Number.isFinite(t.high) ? t.high : null,
    low24h: t && Number.isFinite(t.low) ? t.low : null,
    volume24h: t && Number.isFinite(t.quoteVolume) ? t.quoteVolume : null,
    marketCap: a.marketCap ?? null,
    closeDate: a.lastDate ?? null,
    tradable: Boolean(row && (row.binance || row.coinbase || row.kraken)),
  };
}

interface FullTicker extends Ticker {
  change: number;
  high: number;
  low: number;
}

async function bulkTickerFull(pairs: string[]): Promise<Map<string, FullTicker>> {
  const out = new Map<string, FullTicker>();
  if (pairs.length === 0) return out;
  const url =
    "https://data-api.binance.vision/api/v3/ticker/24hr?symbols=" +
    encodeURIComponent(JSON.stringify(pairs));
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "nextbigthing" },
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return out;
    const body: unknown = await res.json();
    if (!Array.isArray(body)) return out;
    for (const r of body) {
      const t = r as Record<string, unknown>;
      const sym = typeof t.symbol === "string" ? t.symbol : null;
      const last = Number(t.lastPrice);
      if (!sym || !Number.isFinite(last) || last <= 0) continue;
      out.set(sym, {
        lastPrice: last,
        changePct: Number(t.priceChangePercent),
        quoteVolume: Number(t.quoteVolume),
        change: Number(t.priceChange),
        high: Number(t.highPrice),
        low: Number(t.lowPrice),
      });
    }
  } catch {
    return out;
  }
  return out;
}

/// Compact money, the way a market table prints it: $2.72T, $61.98B, $342.28M.
export function compactUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(2)}K`;
  return `$${value.toFixed(2)}`;
}

/// A coin price, with enough decimals to be a price rather than a rounding.
///
/// SHIB at two decimals is $0.00. The number of decimals is chosen from the magnitude, so a
/// six-figure coin and an eight-decimal one are both readable in the same column.
export function coinPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  const digits = abs >= 1000 ? 2 : abs >= 1 ? 4 : abs >= 0.01 ? 5 : abs >= 0.0001 ? 6 : 8;
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function signedPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}
