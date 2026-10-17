import { getAsset, getAssetFreshness } from "@/lib/queries";

/// Resolve a browser's saved symbols to their stored readings.
///
/// The watchlist itself is `localStorage` and the server never sees it (see
/// `app/preview/watchlist/storage.ts` for why there is no table behind it). The consequence is
/// this route: the list is known only to the page, so the page has to ask for the rows it wants
/// rather than the server rendering them. It adds no query of its own -- `getAsset` and
/// `getAssetFreshness` are existing, tested readers -- which is the contract's rule that the UI
/// workstream consumes `lib/queries.ts` and does not grow a parallel data layer beside it.
///
/// POST and not GET with the symbols in the query string. A watchlist is a mildly personal thing
/// and a URL is the one part of a request that is logged everywhere by default.

/// The most instruments one request will resolve.
///
/// A watchlist is a reading list, not the universe, and the ceiling is really about the pooler:
/// the free-tier session pooler admits 15 clients in total across every server instance and every
/// job, `lib/db.ts` `primaryLimits` holds the web layer to 2, and a reader who saved all 555
/// instruments would otherwise turn one page view into eleven hundred queries. Over the cap the
/// request still answers -- for the first 50, saying how many it left out -- rather than failing,
/// because a truncated list the page can explain beats an error it cannot.
const MAX_SYMBOLS = 50;

/// Symbols resolved at a time. Small for the same reason as the cap above: the point is to stay
/// well inside the pooler's ceiling while other sessions and jobs are using it too.
const BATCH = 4;

export interface WatchlistRow {
  symbol: string;
  name: string | null;
  assetType: string | null;
  market: string | null;
  currency: string | null;
  close: number | null;
  closeDate: string | null;
  priceSource: string | null;
  /// True when no asset with this symbol is stored -- a saved row whose instrument has since been
  /// delisted, renamed, or was never in the universe. Told apart from "stored but never priced",
  /// which is an asset that exists with `close: null`.
  unknown: boolean;
}

export async function POST(request: Request) {
  let symbols: string[];
  try {
    const body: unknown = await request.json();
    const raw = (body as { symbols?: unknown })?.symbols;
    if (!Array.isArray(raw)) return Response.json({ error: "symbols must be an array" }, { status: 400 });
    symbols = [...new Set(raw.filter((s): s is string => typeof s === "string" && s.length > 0 && s.length <= 64))];
  } catch {
    return Response.json({ error: "body must be JSON" }, { status: 400 });
  }

  const omitted = Math.max(0, symbols.length - MAX_SYMBOLS);
  const wanted = symbols.slice(0, MAX_SYMBOLS);
  const rows: WatchlistRow[] = [];

  for (let i = 0; i < wanted.length; i += BATCH) {
    const batch = await Promise.all(
      wanted.slice(i, i + BATCH).map(async (symbol): Promise<WatchlistRow> => {
        const asset = await getAsset(symbol).catch(() => null);
        if (!asset) {
          return {
            symbol, name: null, assetType: null, market: null, currency: null,
            close: null, closeDate: null, priceSource: null, unknown: true,
          };
        }
        const fresh = await getAssetFreshness(asset.id).catch(() => null);
        return {
          symbol: asset.symbol,
          name: asset.name,
          assetType: asset.assetType,
          market: asset.industry?.market ?? null,
          currency: asset.currency,
          // null throughout where nothing is stored. An unpriced instrument must not arrive as a
          // zero: `null` is not known and `0` is a measured zero, and a watchlist that printed
          // 0.00 for an instrument nobody has a close for would be inventing a price.
          close: fresh?.close ?? null,
          closeDate: fresh?.newest ? new Date(fresh.newest).toISOString() : null,
          priceSource: fresh?.priceSource ?? null,
          unknown: false,
        };
      }),
    );
    rows.push(...batch);
  }

  return Response.json({ rows, omitted }, { headers: { "cache-control": "no-store" } });
}
