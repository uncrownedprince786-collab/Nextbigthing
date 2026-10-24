import type { Metadata } from "next";
import { CoinTable, type Row } from "@/components/CoinTable";
import { TrendingCoins } from "@/components/TrendingCoins";
import { trending } from "@/lib/cryptoTrending";
import { compactUsd, marketTable } from "@/lib/cryptoMarket";
import {
  UNIVERSE_GENERATED_AT,
  UNIVERSE_SIZE,
  UNIVERSE_STATS,
  UNIVERSE_VENUES,
} from "@/lib/cryptoUniverse";

/// The crypto market, as a table.
///
/// **What this replaced.** `/crypto` used to render `ClassIndex` -- the same component the four
/// other asset classes use -- which asks the database one question per reading per coin and prints
/// a paragraph above each block. It was the same page as `/stocks` with different rows, and what a
/// reader opening a crypto index wants is the thing every exchange shows them: price, what it did
/// today, what it did this week, how big it is, how much traded. Those are columns.
///
/// Two reads behind the whole page (`lib/cryptoMarket.ts`): one SQL statement and one bulk ticker
/// call. It is cached for a minute rather than an hour, because a price column that is an hour old
/// is not a price column.
export const revalidate = 60;

export const metadata: Metadata = {
  title: "Crypto",
  description: "Every coin covered, with a live price and a direction behind each one.",
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="num mt-0.5 text-sm font-semibold">{value}</div>
    </div>
  );
}

export default async function Page() {
  const m = await marketTable();
  // Chosen from the rows already in hand, so this costs ten sparkline fetches and no second pass
  // over the market.
  const hot = await trending(m.coins).catch(() => []);
  // The numbers go across raw and the table formats them. It has to anyway -- the prices it
  // repaints every two seconds arrive as numbers -- and two formatters would be two roundings.
  const rows: Row[] = m.coins.map((c) => ({
    rank: c.rank,
    slug: c.slug,
    name: c.name,
    ticker: c.ticker,
    price: c.price,
    change24h: c.change24h,
    change7d: c.change7d,
    marketCap: c.marketCap,
    volume24h: c.volume24h,
    tradable: c.tradable,
    logo: c.logo,
    isNew: !c.inRegistry,
    pegged: c.pegged,
  }));

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-6">
      <h1 className="text-xl font-semibold">Crypto</h1>

      <div className="border-border mt-3 grid grid-cols-2 gap-4 rounded-lg border px-4 py-3 sm:grid-cols-5">
        <Stat label="Coins" value={m.coins.length.toLocaleString()} />
        <Stat label="Market cap" value={compactUsd(m.totalMarketCap)} />
        <Stat label="Volume (24h)" value={compactUsd(m.totalVolume24h)} />
        <Stat
          label="BTC share"
          value={m.dominance.btc === null ? "—" : `${m.dominance.btc.toFixed(1)}%`}
        />
        <Stat
          label="ETH share"
          value={m.dominance.eth === null ? "—" : `${m.dominance.eth.toFixed(1)}%`}
        />
      </div>

      <div className="mt-6">
        <TrendingCoins coins={hot} />
      </div>

      <div className="mt-6">
        <CoinTable rows={rows} />
      </div>

      {/* One line, and only when it is not true that the prices are live. A banner that is always
          there is a banner nobody reads, and the fact worth printing is the exception. */}
      {!m.venueOk ? (
        <p className="text-muted-foreground mt-3 text-xs">
          The venue did not answer, so every price here is the last stored close
          {m.coins[0]?.closeDate ? ` (${m.coins[0].closeDate.toISOString().slice(0, 10)})` : ""} and
          the 24h column is blank.
        </p>
      ) : m.liveRows < m.coins.length ? (
        <p className="text-muted-foreground mt-3 text-xs">
          {m.liveRows} of {m.coins.length} prices are live from the venue; the rest are the last
          stored close.
        </p>
      ) : null}

      <p className="text-muted-foreground mt-2 text-xs">
        {UNIVERSE_SIZE.toLocaleString()} coins across {UNIVERSE_VENUES.toLowerCase()}, every
        one of which can be asked for a direction. {UNIVERSE_STATS.withMarketCap?.toLocaleString()}{" "}
        carry a market capitalisation, matched to a second source only where its price agreed with
        the venue&apos;s to within 10% — {UNIVERSE_STATS.priceDisagreed} were refused for
        disagreeing, and an em dash in that column is an absence rather than a zero. Shares above
        are of the coins listed here, not of the whole market. Instrument lists checked{" "}
        {UNIVERSE_GENERATED_AT.slice(0, 10)}. Research, not advice.
      </p>
    </main>
  );
}
