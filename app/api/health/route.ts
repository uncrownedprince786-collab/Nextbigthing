import { getHealthReadings } from "@/lib/queries";
import { cachedDecisionRows } from "@/lib/cached";
import { assess } from "@/lib/health";
import { poolMode, servingTier } from "@/lib/db";

/// The site's heartbeat: how fresh every stored reading is, and which lane would fix what is not.
///
/// Read-only and cheap (one index probe per asset and three aggregates), cached for a minute at the
/// edge. `tools/watchdog.py` reads it every hour and re-dispatches the lanes it names. A database that
/// cannot be read answers 503 with no detail, which is itself the most important thing a heartbeat
/// can report -- and the watchdog treats it as the one problem only a person can fix.
export async function GET() {
  try {
    // The pool is counted from the same cached list the market pages are built from, so the page
    // checker compares the pages with what they were given. Counted from the table, it raced the
    // nightly pool job: membership changed at once, the pages within the hour, and the hourly check
    // reported a parity failure that fixed itself (2026-10-10, 523 of 528). The table count stays
    // the fallback when the cached list cannot be read.
    const [readings, rows] = await Promise.all([getHealthReadings(), cachedDecisionRows().catch(() => null)]);
    // The tier this request read from, after every read above (lib/db.ts): a standby is a problem (rule 95).
    const servedFrom = servingTier();
    const health = assess({ ...(rows ? { ...readings, pool: rows.length } : readings), servedFrom }, new Date());
    // The snapshot the pool was counted from, so a checker can tell a real parity fault from two
    // surfaces serving different snapshots (rule 93): the market pages print the same stamp.
    return Response.json({
      ...health,
      snapshot: rows?.[0]?.dataStamp ?? null,
      servedFrom,
      // Which build is answering, and how it is connected. Added 2026-10-19 because neither was
      // knowable from outside: confirming that a pooler-mode change had actually shipped meant
      // asking GitHub's deployments API, which is rate-limited to 60 calls an hour unauthenticated
      // and had been spent -- so "is the fix live" had no answer from the thing that would know.
      // `VERCEL_GIT_COMMIT_SHA` is set by the platform at build time; null anywhere else.
      build: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? null,
      // `transaction` once the web pool dials 6543 (lib/failover.ts), `session` when
      // SUPABASE_POOL_MODE=session has rolled it back, and null when the primary is not Supabase.
      // This is read from the URL the pool was actually built with, not from the intent.
      poolMode: poolMode(),
    }, {
      status: 200,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      {
        ok: false,
        // Never `servedFrom: "the primary"` here. This route reached no tier at all, and naming one
        // would be the single most misleading thing the heartbeat could say.
        servedFrom: null,
        problems: [{ check: "database", lane: null, detail: "the database could not be read" }],
        // Both 2026-10-19 saturations looked like an outage and were not one: every page kept
        // answering 200 from the ISR cache (`revalidate` 900 or 3600) while this route, which is
        // `no-store` and always reads live, answered 503. That is the two surfaces disagreeing
        // correctly, and an operator who does not know it reads a 503 next to a working site and
        // distrusts both. Said here once, rather than rediscovered each time.
        note: "this route always reads the database live and is never cached, so a 503 here is a "
          + "database that could not be reached. Pages may still be answering 200 from their "
          + "cached render; that is not a contradiction and it is not proof the data is current.",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
