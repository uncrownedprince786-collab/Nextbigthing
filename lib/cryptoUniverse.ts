// Every coin the site can price and forecast, which is a much larger set than the registry.
//
// **Two populations, and the difference matters on every page.** The registry is the 76 coins
// `jobs/prices.py` collects daily closes and market capitalisations for; it is what the rule
// table, the analogs and the research page need. The universe is the 515 Binance USDT pairs that
// have a live price and the 5-minute klines the brain reads.
//
// A coin in the universe and not the registry has no market capitalisation, no daily history and
// no stored asset row -- so it cannot carry a verdict or be written to the forecast record -- but
// it can carry a price, a 24-hour change, a volume and a direction. Listing only the registry was
// leaving 450 coins unreachable because a different job had never heard of them, and the pages
// this file serves are about price and direction.
//
// `inRegistry` is on every row so a page can tell the two apart rather than discovering the
// difference by finding a null.

import raw from "@/data/foundation/dataset/crypto_universe.json";

export interface UniverseCoin {
  ticker: string;
  slug: string;
  name: string;
  /// The venue that serves this coin's bars first. Binance wherever it is listed, because it is
  /// the only free source carrying taker-buy volume and a trade count.
  venue: "binance" | "mexc" | "gate";
  /// That venue's own name for the pair. `BTCUSDT` on Binance and MEXC, `BTC_USDT` on Gate.
  instrument: string;
  /// Every venue that lists it, so the bar fetcher can fall past one that is down.
  on: { binance?: string; mexc?: string; gate?: string };
  inRegistry: boolean;
  /// From CoinPaprika, attached only where its USD price agreed with the venue's. Null is an
  /// absence -- a ticker shared by two coins gets no figure rather than the wrong one.
  marketCap: number | null;
  rank: number | null;
  /// CoinPaprika's own id for the matched coin, which is also where its logo lives. Null where no
  /// match was made, and the pages draw a lettered placeholder rather than a broken image.
  paprikaId: string | null;
  /// Pegged to something rather than priced by its own supply and demand -- a stablecoin, or a
  /// gold token. Still listed, because readers look up what USDC is doing; never offered as a
  /// direction, because a model fitted on assets that move has nothing to say about one
  /// engineered not to, and a 0.668 probability on a coin designed to print 1.0000 is reading
  /// rounding dust.
  pegged: boolean;
  /// How far the second source's price sat from the venue's, in percent. The cross-venue audit:
  /// a drifted feed or a stale pair shows up here as a number.
  priceDisagreementPct: number | null;
}

interface Doc {
  generatedAt: string;
  venues: string;
  coins: number;
  stats: Record<string, number>;
  assets: UniverseCoin[];
}

const DOC = raw as unknown as Doc;

export const UNIVERSE: readonly UniverseCoin[] = DOC.assets;
export const UNIVERSE_GENERATED_AT = DOC.generatedAt;
export const UNIVERSE_SIZE = DOC.coins;
export const UNIVERSE_STATS = DOC.stats;
export const UNIVERSE_VENUES = DOC.venues;

const BY_SLUG = new Map(DOC.assets.map((a) => [a.slug, a]));

export function universeCoin(slug: string): UniverseCoin | null {
  return BY_SLUG.get(slug) ?? null;
}

/// Every venue instrument for a slug, from the committed universe and never derived.
///
/// Deriving one -- uppercase the slug, append USDT -- is wrong for every registry coin whose slug
/// is CoinPaprika's (`fetch-ai` is FET, `pol-polygon-ecosystem-token` is POL) and fails as an HTTP
/// 400, which on a free endpoint looks exactly like a geo-block. And Gate spells the same pair
/// differently again (`BTC_USDT`). So the mapping is a lookup in a file a tool wrote from each
/// venue's own instrument list.
export function instrumentsForSlug(slug: string): {
  binance: string | null;
  mexc: string | null;
  gate: string | null;
} {
  const on = BY_SLUG.get(slug)?.on ?? {};
  return { binance: on.binance ?? null, mexc: on.mexc ?? null, gate: on.gate ?? null };
}
