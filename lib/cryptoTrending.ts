// What is moving right now, with the shape of the move beside it.
//
// **"Trending" has to mean something measurable or it is a decoration.** A list of coins that are
// simply up the most is a list of the smallest, thinnest coins on the exchange every single day --
// a token with eleven dollars of volume can print +300% and tell a reader nothing. A list ranked
// by volume alone is the same ten names forever.
//
// So it is both: a coin is trending when it has moved *and* someone traded it. The score is the
// absolute 24-hour move times the square root of the 24-hour dollar volume, over coins clearing a
// volume floor. The square root is there because volume spans six orders of magnitude and a raw
// product would make this a volume ranking with a rounding error attached.
//
// The floor is the honest part. Without it this is a small-cap lottery board; with it the list is
// coins a reader could actually act on.

import { UNIVERSE } from "@/lib/cryptoUniverse";
import type { CoinRow } from "@/lib/cryptoMarket";

export interface TrendingCoin {
  slug: string;
  name: string;
  ticker: string;
  price: number | null;
  change24h: number | null;
  volume24h: number | null;
  /// CoinPaprika's own logo, for the coins matched to it. Null where no match was made, and the
  /// card draws a lettered placeholder rather than a broken image.
  logo: string | null;
  /// Closes over the last few hours, oldest first, for the sparkline. Empty when the venue did
  /// not answer -- the card then shows the numbers without the picture.
  spark: number[];
}

/// At least this much 24-hour dollar volume to be eligible.
///
/// Two million. Below that a percentage move is a handful of trades, and the whole point of this
/// list is that it is not a leaderboard of illiquid tokens.
const MIN_VOLUME_USD = 2_000_000;

const HOW_MANY = 10;
/// Bars behind each sparkline: 48 five-minute bars is the last four hours, which is the window a
/// "right now" list is actually about.
const SPARK_BARS = 48;

function score(c: CoinRow): number {
  const move = Math.abs(c.change24h ?? 0);
  const vol = c.volume24h ?? 0;
  if (vol < MIN_VOLUME_USD || !Number.isFinite(move)) return -1;
  return move * Math.sqrt(vol);
}

const PAPRIKA_ID = new Map(UNIVERSE.map((u) => [u.slug, u.paprikaId ?? null]));
const VENUE = new Map(UNIVERSE.map((u) => [u.slug, { venue: u.venue, instrument: u.instrument }]));

async function sparkFor(slug: string): Promise<number[]> {
  const v = VENUE.get(slug);
  if (!v) return [];
  const url =
    v.venue === "gate"
      ? `https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair=${encodeURIComponent(v.instrument)}&interval=5m&limit=${SPARK_BARS}`
      : v.venue === "mexc"
        ? `https://api.mexc.com/api/v3/klines?symbol=${encodeURIComponent(v.instrument)}&interval=5m&limit=${SPARK_BARS}`
        : `https://data-api.binance.vision/api/v3/klines?symbol=${encodeURIComponent(v.instrument)}&interval=5m&limit=${SPARK_BARS}`;
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "nextbigthing" },
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) return [];
    const body: unknown = await res.json();
    if (!Array.isArray(body)) return [];
    // Gate puts the close third and everyone else puts it fifth. Same fault as in
    // `lib/cryptoBars.ts`, same fix: read it by name of venue rather than by position alone.
    const closeAt = v.venue === "gate" ? 2 : 4;
    return body
      .map((k) => Number((k as unknown[])[closeAt]))
      .filter((n) => Number.isFinite(n) && n > 0);
  } catch {
    return [];
  }
}

/// The ten coins worth looking at right now, with four hours of shape each.
///
/// The sparklines are fetched in parallel and only for the ten that were chosen -- ten requests,
/// not two thousand -- and a venue that does not answer costs that card its picture and nothing
/// else.
export async function trending(coins: CoinRow[]): Promise<TrendingCoin[]> {
  const ranked = coins
    .map((c) => ({ c, s: score(c) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, HOW_MANY)
    .map((x) => x.c);

  const sparks = await Promise.all(ranked.map((c) => sparkFor(c.slug)));

  return ranked.map((c, i) => {
    const id = PAPRIKA_ID.get(c.slug);
    return {
      slug: c.slug,
      name: c.name,
      ticker: c.ticker,
      price: c.price,
      change24h: c.change24h,
      volume24h: c.volume24h,
      logo: id ? `https://static.coinpaprika.com/coin/${id}/logo.png` : null,
      spark: sparks[i],
    };
  });
}
