import { revalidatePath, revalidateTag } from "next/cache";
import { cachedDecisionRows, DATA_TAG } from "@/lib/cached";
import { getDataStamp } from "@/lib/queries";

/// Bring every surface onto the database's current snapshot, at once (brain.md rule 93).
///
/// The site's two cached reads (lib/cached.ts) refresh only through here, and the pages with them: the
/// data tag and every page under the root layout are revalidated in one call, so the market pages, the
/// asset pages, `/api/signals` and `/api/health` read one snapshot. Called by the decision workflow when
/// it finishes, by the hourly watchdog, and by `tools/ui_audit.py` before it reads anything.
///
/// **It acts only when the database is ahead of the cache**, which is why it needs no secret: a fresh
/// stamp (`getDataStamp`) is compared with the stamp the cached rows were read with, and when they match
/// the call does nothing. A caller can make it do work at most once per change in the data. A stamp that
/// cannot be read is treated as a change, because serving a snapshot that cannot be checked is the worse
/// of the two outcomes.
export async function POST() {
  try {
    const [fresh, rows] = await Promise.all([getDataStamp(), cachedDecisionRows().catch(() => null)]);
    const cached = rows?.[0]?.dataStamp ?? null;
    if (fresh !== null && cached === fresh) {
      return Response.json({ revalidated: false, stamp: fresh }, { headers: { "Cache-Control": "no-store" } });
    }
    revalidateTag(DATA_TAG, { expire: 0 });
    revalidatePath("/", "layout");
    return Response.json({ revalidated: true, from: cached, to: fresh }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ revalidated: false, error: "the stamp could not be read" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
