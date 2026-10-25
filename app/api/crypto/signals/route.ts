import { NextResponse } from "next/server";
import { forecastFor } from "@/lib/cryptoForecast";
import { marketTable } from "@/lib/cryptoMarket";
import type { HorizonKey } from "@/lib/cryptoHorizons";

/// Which of the liquid coins the brain is calling up, and which down, right now.
///
///     /api/crypto/signals?h=m15
///
/// **Why this is its own endpoint and not part of the market table.** A direction costs a venue
/// call for 289 bars and a scoring pass. Doing that for 2,324 coins on every page load is not a
/// page. So the table renders instantly from prices alone, and the bullish and bearish tabs ask
/// for this when a reader opens one.
///
/// **And why only the top of the book.** A direction on a coin with eleven dollars of volume is
/// not an opportunity, it is a number. The list is the most-traded coins, which are also the ones
/// the pooled model was fitted on and the only ones a reader could act on at size.
///
/// The strong calls are the point. On the holdout, the pooled five-minute lane is right 64.2% of
/// the time on the 13.1% of bars that clear its floor and 53.7% over everything -- so a board of
/// "which coins are strong right now" is the difference between the model's best output and its
/// average one. Those come back first.
export const dynamic = "force-dynamic";
export const revalidate = 0;

/// How many coins to score. Each is one venue call, run in parallel in batches.
const HOW_MANY = 40;
/// Batch size, so forty coins is a few waves rather than forty simultaneous connections.
const BATCH = 8;

export async function GET(request: Request) {
  const started = Date.now();
  const url = new URL(request.url);
  const raw = (url.searchParams.get("h") || "any").trim();
  const ALL: HorizonKey[] = ["m5", "m15", "h1"];
  /// Which windows to read.
  ///
  /// **"any" is the default, and it is the question the board is actually asked.** A reader
  /// wants to know whether the brain is confident about their coin *right now*, not whether it
  /// happens to be confident over the one window the endpoint was hardcoded to. Scoring a single
  /// horizon meant a coin the model called strongly over five minutes was absent from a board
  /// reading fifteen, with nothing to say it had been looked at.
  ///
  /// Each coin is read over every servable window and keeps its strongest call that clears that
  /// window's own floor -- so the board answers "is there anything here", and the row says which
  /// window the answer belongs to.
  const horizons: HorizonKey[] = ALL.includes(raw as HorizonKey) ? [raw as HorizonKey] : ALL;
  const h: HorizonKey = horizons[horizons.length - 1];

  const market = await marketTable().catch(() => null);
  if (!market) {
    return NextResponse.json({ error: "the market could not be read" }, { status: 503 });
  }

  // An explicit list, when the caller has one.
  //
  // The board is a watchlist of nine coins and the endpoint was scoring the forty most-traded
  // ones over three windows -- a hundred and twenty forecasts to display nine. Worse, the filter
  // ran on the client, so the slowest part of the page was work whose results were discarded.
  // With `coins` the caller names what it needs and the cost falls to twenty-seven.
  const asked = (url.searchParams.get("coins") || "")
    .split(",").map((s) => s.trim()).filter(Boolean);

  const pick = asked.length
    ? market.coins.filter((c) => asked.includes(c.slug))
    : [...market.coins]
    // Pegged coins are excluded outright. A stablecoin is the most-traded thing on any venue, so
    // a board ranked by volume is otherwise most of the way to a list of dollar tokens -- and a
    // direction on one is noise with a probability attached.
        .filter((c) => !c.pegged && (c.volume24h ?? 0) > 0)
        .sort((a, b) => (b.volume24h ?? 0) - (a.volume24h ?? 0))
        .slice(0, HOW_MANY);

  const out: {
    slug: string;
    name: string;
    ticker: string;
    logo: string | null;
    price: number | null;
    change24h: number | null;
    direction: "UP" | "DOWN";
    strength: "strong" | "weak" | null;
    probUp: number;
    marginPts: number;
    /// Which window this call belongs to, because the board now mixes them.
    horizon: HorizonKey;
    horizonMinutes: number;
    /// The bar the call was read from, and the instant it is answerable.
    ///
    /// Without these a reader is shown a direction with no idea what window it covers or when it
    /// stops being the current one -- the board said DOWN and the coin page, opened a bar later,
    /// said something else, with nothing on either screen to explain that they were answers
    /// about two different fifteen minutes.
    asOf: string;
    maturesAt: string;
    floor: number;
  }[] = [];

  for (let i = 0; i < pick.length; i += BATCH) {
    const slice = pick.slice(i, i + BATCH);
    const got = await Promise.all(
      slice.map(async (c) => {
        // Every window for this coin, keeping the strongest call that cleared its own floor --
        // and falling back to the strongest lean when none did, so the row still carries a
        // direction for the coin's own page to explain.
        const reads = await Promise.all(
          horizons.map((hz) => forecastFor(c.slug, hz).catch(() => null)),
        );
        const directions = reads.filter(
          (f): f is Extract<typeof f, { kind: "direction" }> => !!f && f.kind === "direction",
        );
        if (directions.length === 0) return null;
        const strong = directions.filter((f) => f.strength === "strong");
        const pool = strong.length > 0 ? strong : directions;
        return pool.reduce((best, f) => (f.margin > best.margin ? f : best));
      }),
    );
    got.forEach((f, k) => {
      if (!f || f.kind !== "direction") return;
      const c = slice[k];
      out.push({
        slug: c.slug,
        name: c.name,
        ticker: c.ticker,
        logo: c.logo,
        price: c.price,
        change24h: c.change24h,
        direction: f.direction,
        strength: f.strength,
        probUp: Number(f.probUp.toFixed(4)),
        marginPts: Number((f.margin * 200).toFixed(1)),
        asOf: f.asOf.toISOString(),
        maturesAt: f.maturesAt.toISOString(),
        floor: f.floor,
        horizon: f.horizon.key,
        horizonMinutes: f.horizon.minutes,
      });
    });
  }

  // Strong first, then by how far from even -- so the top of each board is the model's best work
  // rather than whichever coin happens to trade most.
  out.sort((a, b) => {
    const sa = a.strength === "strong" ? 1 : 0;
    const sb = b.strength === "strong" ? 1 : 0;
    if (sa !== sb) return sb - sa;
    return b.marginPts - a.marginPts;
  });

  return NextResponse.json(
    {
      horizon: h,
      scored: out.length,
      asked: pick.length,
      strong: out.filter((x) => x.strength === "strong").length,
      up: out.filter((x) => x.direction === "UP").length,
      down: out.filter((x) => x.direction === "DOWN").length,
      signals: out,
      servedInMs: Date.now() - started,
      disclaimer:
        "Research, not advice. Direction only, with no transaction cost, spread or funding in " +
        "any number here, and every accuracy figure is measured on a historical holdout.",
    },
    {
      // A direction is read from the last closed bar, so it cannot change faster than the bar
      // does. Thirty seconds of shared cache turns a board every reader opens into one sweep.
      headers: { "Cache-Control": "public, s-maxage=30, stale-while-revalidate=60" },
    },
  );
}
