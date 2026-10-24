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
import { UNIVERSE, universeCoin } from "@/lib/cryptoUniverse";

/// A promise with a deadline, falling back rather than waiting.
///
/// The registry reads behind these pages are decoration -- market capitalisation and a seven-day
/// column -- and they run against a free-tier pooler capped at two connections that, under load,
/// does not refuse quickly: it hangs and then reports a connection timeout. `.catch()` alone
/// turns that into a fallback *after* the full wait, which is how an optional read came to be the
/// slowest thing on a page that does not need it. This bounds the wait instead.
export function withDeadline<T>(work: Promise<T>, ms: number, fallback: T): Promise<T> {
  return Promise.race([
    work.catch(() => fallback),
    new Promise<T>((resolve) => setTimeout(() => resolve(fallback), ms)),
  ]);
}

/// How long either page will wait for the registry before rendering without it.
///
/// Long enough that a healthy pooler always answers -- the query itself measures 193-324 ms --
/// and short enough that a saturated one costs a reader a market-capitalisation column rather
/// than the page.
export const REGISTRY_DEADLINE_MS = 2500;

/// The coin page's own budget for its single asset row.
///
/// Longer than the market table's, because it is one row by an indexed column rather than a
/// lateral join over the whole table, and because what is lost when it expires is much larger: the
/// market table loses a column, the coin page loses its news, its forward record, and its ability
/// to write the forecast down at all.
const SNAPSHOT_DEADLINE_MS = 6000;

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
  /// False for a coin the venue trades and the registry has never heard of: live price and a
  /// direction, but no market capitalisation, no daily history and no stored verdict.
  inRegistry: boolean;
  /// The coin's own mark, where a second source was matched to it. Null draws a lettered tile.
  logo: string | null;
  /// Pegged to a dollar or an ounce. Listed, priced, and never offered as a direction.
  pegged: boolean;
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
  change: number;
  high: number;
  low: number;
}

const BINANCE = "https://data-api.binance.vision";
const MEXC = "https://api.mexc.com";
const GATE = "https://api.gateio.ws";

/// A value fetched at most once per TTL per process, with concurrent callers sharing one flight.
///
/// Next's `fetch` cache is the right tool in production and does nothing in development, and a
/// page that takes four seconds while you are building it is a page you cannot tell is slow for a
/// different reason. More importantly, `revalidate` de-duplicates across *requests* but a single
/// render that asks twice still pays twice, and the coin page asks for the same 24-hour snapshot
/// the market table does.
///
/// So the upstream calls are memoised in-process as well: one flight per TTL, every caller inside
/// it awaiting the same promise. The two layers do not conflict -- this one is a few seconds wide
/// and sits above Next's, which survives between requests.
function memoised<T>(ttlMs: number, load: () => Promise<T>): () => Promise<T> {
  let at = 0;
  let inflight: Promise<T> | null = null;
  let value: T | null = null;
  return () => {
    const now = Date.now();
    if (value !== null && now - at < ttlMs) return Promise.resolve(value);
    if (inflight) return inflight;
    inflight = load()
      .then((v) => {
        value = v;
        at = Date.now();
        return v;
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  };
}



/// Every venue's 24-hour statistics, in one request each, cached and merged.
///
/// Keyed by `venue:instrument`, because the same coin is `BTCUSDT` on two venues and `BTC_USDT`
/// on the third, and a map keyed on the bare pair would have Gate silently overwriting Binance.
///
/// **Why the whole exchange and not the pairs we want.** Naming 515 symbols produces a URL of
/// about seven kilobytes and Binance answers it with `414 Request-URI Too Large` -- so the
/// filtered form silently returned nothing the moment the universe grew. The unfiltered calls are
/// one request per venue for every pair it lists; the ones we do not list are dropped on parse,
/// which costs a loop and no round trips.
///
/// `type=MINI` halves Binance's payload by omitting the bid/ask book and the weighted average,
/// none of which is printed anywhere. `priceChangePercent` goes with it, so the change is
/// computed from `lastPrice` against `openPrice` -- the same arithmetic Binance was doing.
///
/// A venue that does not answer contributes nothing and the other two still render. One exchange
/// being unreachable should cost a reader the coins only that exchange lists, not the page.
const tickerSnapshot = memoised(12_000, async (): Promise<Map<string, Ticker>> => {
  const out = new Map<string, Ticker>();
  const put = (venue: string, inst: string, last: number, open: number,
               high: number, low: number, quoteVolume: number) => {
    if (!Number.isFinite(last) || last <= 0) return;
    out.set(`${venue}:${inst}`, {
      lastPrice: last,
      changePct: Number.isFinite(open) && open > 0 ? (last / open - 1) * 100 : NaN,
      quoteVolume,
      change: Number.isFinite(open) ? last - open : NaN,
      high,
      low,
    });
  };

  const grab = async (url: string): Promise<unknown[]> => {
    try {
      const res = await fetch(url, {
        headers: { "User-Agent": "nextbigthing" },
        next: { revalidate: 15 },
        signal: AbortSignal.timeout(12000),
      });
      if (!res.ok) return [];
      const body: unknown = await res.json();
      return Array.isArray(body) ? body : [];
    } catch {
      return [];
    }
  };

  const [bin, mex, gat] = await Promise.all([
    grab(`${BINANCE}/api/v3/ticker/24hr?type=MINI`),
    grab(`${MEXC}/api/v3/ticker/24hr`),
    grab(`${GATE}/api/v4/spot/tickers`),
  ]);

  for (const r of bin) {
    const x = r as Record<string, unknown>;
    if (typeof x.symbol !== "string") continue;
    put("binance", x.symbol, Number(x.lastPrice), Number(x.openPrice),
        Number(x.highPrice), Number(x.lowPrice), Number(x.quoteVolume));
  }
  for (const r of mex) {
    const x = r as Record<string, unknown>;
    if (typeof x.symbol !== "string") continue;
    put("mexc", x.symbol, Number(x.lastPrice), Number(x.openPrice),
        Number(x.highPrice), Number(x.lowPrice), Number(x.quoteVolume));
  }
  for (const r of gat) {
    const x = r as Record<string, unknown>;
    if (typeof x.currency_pair !== "string") continue;
    // Gate publishes the change as a percentage and no open, so the open is reconstructed from
    // the pair it does publish. Same number, arrived at from the other side.
    const last = Number(x.last);
    const pct = Number(x.change_percentage);
    const open = Number.isFinite(pct) && 1 + pct / 100 > 0 ? last / (1 + pct / 100) : NaN;
    put("gate", x.currency_pair, last, open, Number(x.high_24h), Number(x.low_24h),
        Number(x.quote_volume));
  }
  return out;
});

/// The 24-hour snapshot across every venue, keyed `venue:instrument`.
async function bulkTicker(): Promise<Map<string, Ticker>> {
  return tickerSnapshot();
}

/// This coin's row out of that snapshot, from whichever venue serves it.
function tickerOf(u: { venue: string; instrument: string }, m: Map<string, Ticker>) {
  return m.get(`${u.venue}:${u.instrument}`);
}

/// Every coin the venue trades, ranked, with a live price and whatever the registry knows.
///
/// Ranked by market capitalisation where there is one and by 24-hour dollar volume where there is
/// not. Most of the universe is outside the registry and has no capitalisation at all; sorting
/// those to the bottom alphabetically would bury the liquid ones under a wall of tickers nobody
/// trades, and volume is the figure that is always present and says the same kind of thing.
export async function marketTable(): Promise<MarketTable> {
  // The registry read is **optional**, and that is the point. Everything a reader opens this page
  // for -- price, 24-hour change, volume, and the coin list itself -- comes from the venue. The
  // database adds market capitalisation and the seven-day column, and it is a free-tier pooler
  // capped at two connections that times out under load. A market table that 500s because a
  // capitalisation column could not be read is a market table nobody can use; one that renders
  // without that column is the same page with one fewer number in it.
  const [rows, tickers, paprika] = await Promise.all([
    withDeadline(
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
      REGISTRY_DEADLINE_MS,
      [] as Row[],
    ),
    bulkTicker(),
    paprikaSnapshot(),
  ]);

  // The registry's rows, keyed by slug, merged onto the universe below.
  const stored = new Map(rows.map((r) => [r.symbol, r]));

  const built: CoinRow[] = UNIVERSE.map((u) => {
    const r = stored.get(u.slug);
    const t = tickerOf(u, tickers);
    const price = t?.lastPrice ?? r?.lastClose ?? null;
    // Seven days is measured from whichever price is being shown, so the column is consistent with
    // the one beside it. Comparing a live price against a stored close is the right comparison --
    // both are prices of the same coin -- and comparing a stored close against a stored close when
    // the venue is down is still the right one.
    // The second source first, because it has one for 1,133 coins where the registry has one
    // for 76; the stored close is the fallback, not the other way round.
    const pap = u.paprikaId ? paprika.get(u.paprikaId) : undefined;
    const week =
      pap?.pct7d !== undefined && pap?.pct7d !== null
        ? pap.pct7d
        : price !== null && r?.weekAgoClose && r.weekAgoClose > 0
          ? (price / r.weekAgoClose - 1) * 100
          : null;
    return {
      rank: 0,
      slug: u.slug,
      name: u.name,
      ticker: u.ticker,
      price,
      priceAt: t ? "venue" : (r?.lastClose ?? null) !== null ? "close" : null,
      change24h: t && Number.isFinite(t.changePct) ? t.changePct : null,
      change7d: week,
      // Live where the second source has it, then the committed figure, then the registry's.
      // All three are the same quantity; they differ only in how old they are.
      marketCap: pap?.marketCap ?? u.marketCap ?? r?.marketCap ?? null,
      logo: u.paprikaId ? `https://static.coinpaprika.com/coin/${u.paprikaId}/logo.png` : null,
      pegged: u.pegged,
      volume24h: t && Number.isFinite(t.quoteVolume) ? t.quoteVolume : null,
      // Every coin in the universe has klines by construction, so every one can be asked for a
      // direction.
      tradable: true,
      closeDate: r?.lastDate ?? null,
      inRegistry: u.inRegistry,
    };
  });

  // Capitalisation first where there is one, then 24-hour volume. The rank is written after the
  // sort, so the number in the first column is the position actually shown.
  built.sort((a, b) => {
    const ca = a.marketCap ?? -1;
    const cb = b.marketCap ?? -1;
    if (ca !== cb) return cb - ca;
    return (b.volume24h ?? -1) - (a.volume24h ?? -1);
  });
  const coins: CoinRow[] = built.map((c, i) => ({ ...c, rank: i + 1 }));

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
  inRegistry: boolean;
  /// Why there is no `assetId`, when there is none.
  ///
  /// `missing` is a coin the registry genuinely does not hold. `unread` is a coin whose row could
  /// not be fetched in time -- a different fact entirely, and one the page must not describe as
  /// the first. It said "this coin is not in the registry" about **Bitcoin**, on a render where a
  /// saturated pooler missed its deadline, and silently stopped recording the forecast.
  registryRead: "ok" | "missing" | "unread";
}

/// Everything the top of a coin page needs, in one SQL statement and one ticker call.
///
/// Deliberately not `getAsset`: that returns the industry, the factors, the setups and the rest of
/// what the five-market asset page renders, and this page shows a price and a direction. The cost
/// of a page is the questions it asks, so this asks two.
export async function coinSnapshot(slug: string): Promise<CoinSnapshot | null> {
  const u = universeCoin(slug);
  const row = VENUE_ROWS.find((v) => v.slug === slug) ?? null;
  const pair = row?.binance ?? u?.on.binance ?? u?.instrument ?? null;
  if (!row && !u) return null;

  // The typed client, not `$queryRaw`. The slug here is a URL path segment -- the one piece of
  // user input the web layer has -- and `tests/test_brain.py` refuses any interpolation into a raw
  // template for exactly that reason. Prisma's tagged template does parameterise `${}`, but a
  // guard that cannot tell a safe interpolation from an unsafe one is the guard worth keeping, so
  // this is written the way the guard wants rather than the guard being loosened to fit it. It
  // costs nothing: `(assetId, date)` is the primary key, so the ordered take-1 is one index seek.
  // Same trade as the market table: the venue answers the page, the registry decorates it. A
  // coin that is in the registry but whose row could not be read this second renders exactly like
  // a venue-only coin rather than as a 404.
  // One row by an indexed column, so a generous budget costs nothing when the database is
  // healthy and buys the difference between "no news for this coin" and a correct page when it
  // is busy. `timedOut` is a sentinel rather than null: null means the row is not there, and the
  // two must not be confused.
  const TIMED_OUT = Symbol("registry read timed out");
  const [found, tickers] = await Promise.all([
    withDeadline(
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
      }).catch(() => TIMED_OUT as unknown as null),
      SNAPSHOT_DEADLINE_MS,
      TIMED_OUT as unknown as null,
    ),
    bulkTicker(),
  ]);
  const unread = (found as unknown) === TIMED_OUT;

  // A venue-only coin has no asset row. That is not a missing page -- it is a coin the registry
  // has never collected. It gets everything the venue knows and nothing the registry would have
  // added, and `assetId` is empty so the caller knows there is nothing to record against.
  if (!found || unread) {
    if (!u) return null;
    const t0 = tickerOf(u, tickers);
    return {
      assetId: "",
      slug: u.slug,
      name: u.name,
      ticker: u.ticker,
      price: t0?.lastPrice ?? null,
      priceAt: t0 ? "venue" : null,
      change24h: t0 && Number.isFinite(t0.changePct) ? t0.changePct : null,
      change24hAbs: t0 && Number.isFinite(t0.change) ? t0.change : null,
      high24h: t0 && Number.isFinite(t0.high) ? t0.high : null,
      low24h: t0 && Number.isFinite(t0.low) ? t0.low : null,
      volume24h: t0 && Number.isFinite(t0.quoteVolume) ? t0.quoteVolume : null,
      marketCap: u.marketCap,
      closeDate: null,
      tradable: true,
      inRegistry: false,
      registryRead: unread ? "unread" : "missing",
    };
  }
  const newest = found.snapshots[0] ?? null;
  const a = {
    id: found.id,
    symbol: found.symbol,
    name: found.name,
    lastClose: newest?.close ?? null,
    lastDate: newest?.date ?? null,
    marketCap: newest?.marketCap ?? null,
  };
  // A registry coin is still looked up through the universe, because the universe knows which
  // venue is actually serving it -- the registry only ever recorded a Binance pair, and a coin
  // Binance has since delisted is served from MEXC or Gate now.
  const t = u ? tickerOf(u, tickers) : undefined;
  return {
    assetId: a.id,
    slug: a.symbol,
    name: a.name,
    ticker: u?.ticker ?? a.symbol.split("-")[0].toUpperCase(),
    price: t?.lastPrice ?? a.lastClose ?? null,
    priceAt: t ? "venue" : a.lastClose !== null ? "close" : null,
    change24h: t && Number.isFinite(t.changePct) ? t.changePct : null,
    change24hAbs: t && Number.isFinite(t.change) ? t.change : null,
    high24h: t && Number.isFinite(t.high) ? t.high : null,
    low24h: t && Number.isFinite(t.low) ? t.low : null,
    volume24h: t && Number.isFinite(t.quoteVolume) ? t.quoteVolume : null,
    marketCap: u?.marketCap ?? a.marketCap ?? null,
    closeDate: a.lastDate ?? null,
    tradable: Boolean(pair || u || (row && (row.coinbase || row.kraken))),
    inRegistry: true,
    registryRead: "ok",
  };
}

export interface LivePrice {
  p: number;
  /// 24-hour change in percent, so a polling page can repaint the change column too.
  c: number | null;
}

/// Every coin's last trade and 24-hour change, keyed by slug.
///
/// The one read behind `/api/crypto/prices`, which is the single same-origin URL the market table
/// and the coin page poll. Keyed by slug rather than by venue pair, because a browser knows the
/// slug it is looking at and should not have to carry the venue map to use this.
const priceSnapshot = memoised(1500, async (): Promise<Map<string, number>> => {
  const m = new Map<string, number>();
  const grab = async (url: string): Promise<unknown[]> => {
    try {
      const res = await fetch(url, {
        headers: { "User-Agent": "nextbigthing" },
        next: { revalidate: 2 },
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) return [];
      const body: unknown = await res.json();
      return Array.isArray(body) ? body : [];
    } catch {
      return [];
    }
  };
  // The last trade only. Binance and MEXC publish a price-only endpoint that is a fraction of the
  // 24-hour payload, which is what makes a two-second poll affordable; Gate has no equivalent, so
  // its prices come from the twelve-second snapshot and are at most that old. Said here rather
  // than hidden, because "live" meaning two different things on one page should be written down.
  const [bin, mex] = await Promise.all([
    grab(`${BINANCE}/api/v3/ticker/price`),
    grab(`${MEXC}/api/v3/ticker/price`),
  ]);
  for (const [venue, rows] of [["binance", bin], ["mexc", mex]] as const) {
    for (const r of rows) {
      const row = r as Record<string, unknown>;
      const sym = typeof row.symbol === "string" ? row.symbol : null;
      const v = Number(row.price);
      if (sym && Number.isFinite(v) && v > 0) m.set(`${venue}:${sym}`, v);
    }
  }
  return m;
});

/// CoinPaprika's own snapshot: a live market capitalisation and a seven-day change, by its id.
///
/// **Why the seven-day column was empty for most of the market.** It was computed from a stored
/// close seven days old, and only the 76 coins in the registry have stored closes -- so 2,248 of
/// 2,324 rows printed an em dash in that column. No venue publishes a seven-day change; the
/// 24-hour ticker is 24 hours by definition.
///
/// This is one request for 2,000 coins, which covers 1,133 of ours. Keyed by CoinPaprika's own
/// id rather than by ticker, because a ticker is not an identifier -- that is the whole lesson of
/// `crypto_universe.py`, and the ids were matched there by price agreement, so a row read through
/// one is a row about this coin.
///
/// Five minutes of cache. A seven-day change that is five minutes old is a seven-day change; the
/// price beside it is two seconds old and comes from the venue.
interface PaprikaRow {
  pct7d: number | null;
  marketCap: number | null;
}

const paprikaSnapshot = memoised(300_000, async (): Promise<Map<string, PaprikaRow>> => {
  const out = new Map<string, PaprikaRow>();
  try {
    const res = await fetch("https://api.coinpaprika.com/v1/tickers?quotes=USD", {
      headers: { "User-Agent": "nextbigthing" },
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return out;
    const body: unknown = await res.json();
    if (!Array.isArray(body)) return out;
    for (const r of body) {
      const x = r as Record<string, unknown>;
      const id = typeof x.id === "string" ? x.id : null;
      const usd = (x.quotes as Record<string, Record<string, unknown>> | undefined)?.USD;
      if (!id || !usd) continue;
      const pct = Number(usd.percent_change_7d);
      const cap = Number(usd.market_cap);
      out.set(id, {
        pct7d: Number.isFinite(pct) ? pct : null,
        marketCap: Number.isFinite(cap) && cap > 0 ? cap : null,
      });
    }
  } catch {
    // An absence, never a zero: the column simply stays blank for this render.
    return out;
  }
  return out;
});

export async function livePrices(): Promise<Record<string, LivePrice>> {
  // The last trade only: 154 KB and about a quarter of the time of the 24-hour statistics, which
  // is what makes a two-second poll affordable. The 24-hour change travels with it from the
  // fifteen-second cache above, so a repainting page gets a per-second price and a change figure
  // that is at worst fifteen seconds old -- the right split, because the price is what moves.
  const [prices, stats] = await Promise.all([
    priceSnapshot(),
    bulkTicker(),
  ]);

  const out: Record<string, LivePrice> = {};
  for (const u of UNIVERSE) {
    const p = prices.get(`${u.venue}:${u.instrument}`);
    const s = tickerOf(u, stats);
    const last = p ?? s?.lastPrice;
    if (last === undefined) continue;
    out[u.slug] = {
      p: last,
      // Recomputed against the 24-hour open rather than taken from the cached snapshot, so the
      // change column moves with the price instead of stepping every fifteen seconds.
      c: s && Number.isFinite(s.change) && s.lastPrice - s.change > 0
        ? (last / (s.lastPrice - s.change) - 1) * 100
        : (s && Number.isFinite(s.changePct) ? s.changePct : null),
    };
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

