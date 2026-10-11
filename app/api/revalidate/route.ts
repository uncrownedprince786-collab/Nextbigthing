import { revalidatePath, revalidateTag } from "next/cache";
import { pagesBehind } from "@/lib/alignment";
import { cachedDecisionRows, DATA_TAG } from "@/lib/cached";
import { getDataStamp } from "@/lib/queries";

/// Bring every surface onto the database's current snapshot, at once (brain.md rule 93).
///
/// The site's two cached reads (lib/cached.ts) refresh only through here, and the pages with them: the
/// data tag and every page under the root layout are revalidated in one call, so the market pages, the
/// asset pages, `/api/signals` and `/api/health` read one snapshot. Called by the decision and schema
/// workflows when they finish, by the hourly watchdog, and by `tools/ui_audit.py` before it reads anything.
///
/// **It acts only when the site is behind the database**, which is why it needs no secret: a fresh
/// stamp (`getDataStamp`) is compared with the stamp the cached rows were read with, and when they match,
/// with the stamps the market pages print (lib/alignment.ts, rule 94) -- a page re-rendered from an
/// earlier read than the one the cache kept is behind even when the cache is not. When everything matches
/// the call does nothing, so a caller can make it do work at most once per change in the data. A stamp
/// that cannot be read is treated as a change, because serving a snapshot that cannot be checked is the
/// worse of the two outcomes.
export async function POST(request: Request) {
  try {
    const [fresh, rows] = await Promise.all([getDataStamp(), cachedDecisionRows().catch(() => null)]);
    const cached = rows?.[0]?.dataStamp ?? null;
    if (fresh !== null && cached === fresh) {
      const behind = await pagesBehind(new URL(request.url).origin, fresh);
      if (behind.length === 0) {
        return Response.json({ revalidated: false, stamp: fresh }, { headers: { "Cache-Control": "no-store" } });
      }
      revalidatePath("/", "layout");
      return Response.json({ revalidated: true, pagesBehind: behind, to: fresh }, { headers: { "Cache-Control": "no-store" } });
    }
    revalidateTag(DATA_TAG, { expire: 0 });
    revalidatePath("/", "layout");
    return Response.json({ revalidated: true, from: cached, to: fresh }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ revalidated: false, error: "the stamp could not be read" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
