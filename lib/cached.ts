import { unstable_cache } from "next/cache";
import { getDecisionRows, getSourceHealth } from "@/lib/queries";

/// The two reads every verdict on the site is built from, cached once for the whole site.
///
/// Why they live here rather than in each page: `getDecisionRows()` is twelve queries against a
/// Neon free tier, and it is now wanted by five routes -- the overview and one index per asset
/// class. Five `unstable_cache` wrappers would be five cache entries over one query set, so a
/// crawler walking the nav would run those twelve queries five times an hour instead of once.
///
/// Sharing them has a second effect that matters more than the query count. Both are inputs to the
/// rule table, and a route that fetched its own copy could show a name as silent in one list and
/// current in another at the same moment. One entry, one answer, every page.
///
/// `'use cache'` would be the Next 16 way to say this and does not work here: `cacheComponents` is
/// not enabled in next.config.ts, so the directive and `cacheLife` are unavailable and
/// `unstable_cache` is the correct API in this configuration.
///
/// **No timer** (rule 93). Both entries refresh only when `/api/revalidate` finds the database ahead of
/// them, and the pages are revalidated in the same call. They used to expire on an hourly timer of their
/// own while each page's HTML expired on another, so after a run the market pages and `/api/health` could
/// each be serving a different snapshot -- the pool-parity failure of 2026-10-10 and 10-11 (553 listed,
/// 547 counted). One trigger, one snapshot, every surface.
export const DATA_TAG = "decision-data";
const ON_DEMAND: { revalidate: false; tags: string[] } = { revalidate: false, tags: [DATA_TAG] };

export const cachedDecisionRows = unstable_cache(getDecisionRows, ["decision-rows"], ON_DEMAND);
export const cachedSourceHealth = unstable_cache(getSourceHealth, ["source-health"], ON_DEMAND);
