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
  const raw = (url.searchParams.get("h") || "m15").trim();
  const h: HorizonKey = (["m5", "m15", "h1"] as const).includes(raw as "m5")
    ? (raw as HorizonKey)
    : "m15";

  const market = await marketTable().catch(() => null);
  if (!market) {
    return NextResponse.json({ error: "the market could not be read" }, { status: 503 });
  }

  const pick = [...market.coins]
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
  }[] = [];

  for (let i = 0; i < pick.length; i += BATCH) {
    const slice = pick.slice(i, i + BATCH);
    const got = await Promise.all(
      slice.map((c) =>
        forecastFor(c.slug, h).catch(() => null),
      ),
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
