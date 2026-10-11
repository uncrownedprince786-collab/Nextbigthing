import { getHealthReadings } from "@/lib/queries";
import { cachedDecisionRows } from "@/lib/cached";
import { assess } from "@/lib/health";

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
    const health = assess(rows ? { ...readings, pool: rows.length } : readings, new Date());
    // The snapshot the pool was counted from, so a checker can tell a real parity fault from two
    // surfaces serving different snapshots (rule 93): the market pages print the same stamp.
    return Response.json({ ...health, snapshot: rows?.[0]?.dataStamp ?? null }, {
      status: 200,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      { ok: false, problems: [{ check: "database", lane: null, detail: "the database could not be read" }] },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
