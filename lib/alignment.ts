/// Whether the market pages are on the snapshot the site's data cache holds (brain.md rule 94).
///
/// `/api/revalidate` used to judge alignment by the data cache alone: when the cached rows' stamp equalled
/// the database's, it did nothing. That missed a state seen live on 2026-10-11. After a revalidation every
/// page re-renders on its next visit, and each re-render that finds the data entry empty reads the
/// database for itself; the schema lane wrote new setups between those reads, so the five market pages
/// were rendered from one read and the stored entry came from a later one. The route then found the
/// entry current and answered "nothing to do" while every market page sat on the older snapshot, and
/// would have kept doing so until the next write. So the route now also reads the pages.

/// The pages that print the stamp they were rendered from (`data-snapshot`, components/classIndex.tsx).
export const STAMPED_PAGES = ["/stocks", "/crypto", "/psx", "/forex", "/commodities"] as const;

/// The stamp a rendered page carries, or null when it prints none.
export function snapshotOf(html: string): string | null {
  return html.match(/data-snapshot="([^"]*)"/)?.[1] || null;
}

/// True when a page is behind: served as current, yet rendered from another snapshot than `stamp`.
///
/// A page the cache reports as STALE (Vercel's `x-vercel-cache`, Next's `x-nextjs-cache`) is already
/// re-rendering after a revalidation and is not judged: counting it would revalidate again on every call
/// until the render lands, and each revalidation costs a database read. A page with no stamp cannot be
/// judged either way.
export function isBehind(page: { cache: string | null; seen: string | null }, stamp: string): boolean {
  if ((page.cache ?? "").toUpperCase() === "STALE") return false;
  return page.seen !== null && page.seen !== stamp;
}

/// The stamped pages that are behind `stamp`, read from `origin` as a visitor reads them. A page that
/// cannot be read is left out: the route's job is to act on evidence of a skew, not on a failed fetch.
export async function pagesBehind(origin: string, stamp: string): Promise<string[]> {
  const judged = await Promise.all(
    STAMPED_PAGES.map(async (path) => {
      try {
        const res = await fetch(origin + path, { cache: "no-store", headers: { "User-Agent": "nbt-revalidate" }, signal: AbortSignal.timeout(15_000) });
        if (!res.ok) return null;
        const cache = res.headers.get("x-vercel-cache") ?? res.headers.get("x-nextjs-cache");
        return isBehind({ cache, seen: snapshotOf(await res.text()) }, stamp) ? path : null;
      } catch {
        return null;
      }
    }),
  );
  return judged.filter((p): p is (typeof STAMPED_PAGES)[number] => p !== null);
}
