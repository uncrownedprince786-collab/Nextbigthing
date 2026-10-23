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

import raw from "@/data/foundation/dataset/binance_universe.json";

export interface UniverseCoin {
  pair: string;
  ticker: string;
  slug: string;
  name: string;
  inRegistry: boolean;
}

interface Doc {
  generatedAt: string;
  venue: string;
  coins: number;
  inRegistry: number;
  assets: UniverseCoin[];
}

const DOC = raw as unknown as Doc;

export const UNIVERSE: readonly UniverseCoin[] = DOC.assets;
export const UNIVERSE_GENERATED_AT = DOC.generatedAt;
export const UNIVERSE_SIZE = DOC.coins;
export const UNIVERSE_IN_REGISTRY = DOC.inRegistry;

const BY_SLUG = new Map(DOC.assets.map((a) => [a.slug, a]));

export function universeCoin(slug: string): UniverseCoin | null {
  return BY_SLUG.get(slug) ?? null;
}

/// The Binance pair for a slug, from the committed universe and never derived.
///
/// Deriving it -- uppercase the slug, append USDT -- is wrong for every registry coin whose slug
/// is CoinPaprika's (`fetch-ai` is FET, `pol-polygon-ecosystem-token` is POL) and fails as an HTTP
/// 400, which on a free endpoint looks exactly like a geo-block. So the mapping is a lookup in a
/// file a tool wrote from the venue's own instrument list.
export function pairForSlug(slug: string): string | null {
  return BY_SLUG.get(slug)?.pair ?? null;
}
