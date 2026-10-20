// Which venue instruments each stored coin is, from the checked map.
//
// `tools/foundation/crypto_venue_map.py` asks Binance and Coinbase for their own instrument lists
// and records what exists; this reads that answer. The alternative -- deriving a pair from the
// CoinPaprika slug at request time -- is wrong for several coins in the registry (`fetch-ai` is
// FET, `pol-polygon-ecosystem-token` is POL, `s-sonic` is S) and fails as an HTTP 400, which on a
// free endpoint looks exactly like the geo-block that took Binance off GitHub's runners.
//
// Every coin in the registry is in this table, including the ones with no venue pair at all. That
// is the point: the site lists the whole registry, so each listed coin needs a stored answer to
// "what can be read for this one", not an absence.

import raw from "@/data/foundation/dataset/crypto_venue_map.json";

export interface VenueRow {
  slug: string;
  name: string;
  inActivePool: boolean;
  dailySnapshots: number;
  newestClose: string | null;
  binance: string | null;
  coinbase: string | null;
  /// Kraken's own pair name, where one is mapped. It matters most for the coins Binance has
  /// delisted: Monero is served here and nowhere else in the chain.
  kraken: string | null;
  intraday: boolean;
  why: string | null;
}

interface Doc {
  generatedAt: string;
  venueListsChecked: boolean;
  coins: number;
  withIntradaySource: number;
  inActivePool: number;
  assets: VenueRow[];
}

const DOC = raw as unknown as Doc;

export const VENUE_MAP_GENERATED_AT = DOC.generatedAt;
export const VENUE_ROWS: readonly VenueRow[] = DOC.assets;
export const COINS_WITH_INTRADAY = DOC.withIntradaySource;
export const COINS_TOTAL = DOC.coins;

const BY_SLUG = new Map(DOC.assets.map((a) => [a.slug, a]));

export function venueRowFor(slug: string): VenueRow | null {
  return BY_SLUG.get(slug) ?? null;
}

/// The instruments the bar fetcher should try, in no particular order -- `lib/cryptoBars.ts` owns
/// the venue order, because that is a property of the venues and not of the coin.
export function instrumentsFor(slug: string): { binance: string | null; coinbase: string | null; kraken: string | null } {
  const row = BY_SLUG.get(slug);
  return {
    binance: row?.binance ?? null,
    coinbase: row?.coinbase ?? null,
    kraken: row?.kraken ?? null,
  };
}

/// True when some venue can serve this coin's bars at all.
export function hasIntradaySource(slug: string): boolean {
  const i = instrumentsFor(slug);
  return Boolean(i.binance || i.coinbase || i.kraken);
}
