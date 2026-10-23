import { NextResponse } from "next/server";
import { livePrices } from "@/lib/cryptoMarket";

/// Every coin's last trade, for the pages that keep themselves fresh.
///
///     /api/crypto/prices
///
/// **Why one endpoint for every coin rather than one per coin.** The market table shows seventy-six
/// rows and the coin page shows one, and both want the same thing a second or two old. A per-coin
/// endpoint would make the table seventy-six requests a tick; this is one, and the coin page reads
/// its own row out of the same answer. The upstream is a single Binance bulk ticker call, so the
/// fan-in is 1:1 however many browsers are watching.
///
/// Same-origin and nothing else, which is what lets the client components that poll it stay inside
/// the rule `tests/test_brain.py` holds them to: they talk to this, and this talks to the venue.
///
/// It reads no database and takes no input, so there is nothing here a path segment could reach.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const started = Date.now();
  const prices = await livePrices();
  return NextResponse.json(
    {
      prices,
      coins: Object.keys(prices).length,
      at: new Date().toISOString(),
      servedInMs: Date.now() - started,
    },
    {
      headers: {
        // Two seconds of shared cache in front of a venue that updates about once a second: a
        // hundred watching browsers become at most one upstream call every two seconds, and no
        // reader is looking at a price more than two seconds older than the one beside them.
        "Cache-Control": "public, s-maxage=2, stale-while-revalidate=4",
      },
    },
  );
}
