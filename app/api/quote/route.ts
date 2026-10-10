import type { NextRequest } from "next/server";
import { getQuoteTarget } from "@/lib/queries";
import { fetchFreshQuote, isStale, makeMemo, MEMO_TTL_MS, quoteAgeMs, type Quote } from "@/lib/liveQuote";

// Node runtime, not Edge: the stored quote is read through the same pooled Postgres client as every
// page, and a TCP database driver does not run on Edge. What the Edge limits exist to protect --
// memory and cold-start time -- are respected anyway: one indexed read, one optional outbound request
// with a 1.5 s timeout, no body larger than a few hundred bytes.

/// Read-only. It never writes a quote: the stored table is written by `jobs/live.py` and only by it, so
/// a public endpoint cannot be used to put a price into the database.
///
/// When the stored quote is older than five minutes (or missing) it asks the provider once and answers
/// with what came back, marked `revalidated`. That answer is held for a minute per symbol, so a page
/// full of readers costs the provider one request a minute, not one each.
const memo = makeMemo<Quote | null>(MEMO_TTL_MS);
const SYMBOL = /^[A-Za-z0-9.=^-]{1,32}$/;
// A minute at the edge, matching the browser's one-minute poll: one database read per symbol per
// minute however many people have the page open, and a stale answer served while it refreshes.
const HEADERS = { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300" };

export async function GET(request: NextRequest) {
  const symbol = request.nextUrl.searchParams.get("symbol") ?? "";
  if (!SYMBOL.test(symbol)) return Response.json({ error: "symbol is not valid" }, { status: 400 });

  let target;
  try {
    target = await getQuoteTarget(symbol);
  } catch {
    return Response.json({ error: "the database could not be read" }, { status: 503 });
  }
  if (!target) return Response.json({ error: "unknown symbol" }, { status: 404 });

  const now = new Date();
  let quote: Quote | null = target.quote
    ? { price: target.quote.price, quotedAt: target.quote.quotedAt.toISOString() }
    : null;
  let revalidated = false;

  const { source, sourceRef } = target.asset;
  if (isStale(quote?.quotedAt, now) && (source === "yahoo" || source === "coinpaprika") && sourceRef) {
    const key = `${source}:${sourceRef}`;
    const kept = memo.get(key);
    const fresh = kept.hit ? kept.value : await fetchFreshQuote({ source, ref: sourceRef }, fetch, now);
    if (!kept.hit) memo.set(key, fresh);
    if (fresh && (!quote || new Date(fresh.quotedAt).getTime() >= new Date(quote.quotedAt).getTime())) {
      quote = fresh;
      revalidated = true;
    }
  }

  return Response.json(
    {
      symbol,
      price: quote?.price ?? null,
      quotedAt: quote?.quotedAt ?? null,
      ageSeconds: quote ? Math.round(quoteAgeMs(quote.quotedAt, now) / 1000) : null,
      stale: isStale(quote?.quotedAt, now),
      revalidated,
      source: quote ? source : null,
      close: target.close ? { price: target.close.close, date: target.close.date.toISOString().slice(0, 10) } : null,
    },
    { headers: HEADERS },
  );
}
