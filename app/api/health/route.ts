import { getHealthReadings } from "@/lib/queries";
import { assess } from "@/lib/health";

/// The site's heartbeat: how fresh every stored reading is, and which lane would fix what is not.
///
/// Read-only and cheap (one index probe per asset and three aggregates), cached for a minute at the
/// edge. `tools/watchdog.py` reads it every hour and re-dispatches the lanes it names. A database that
/// cannot be read answers 503 with no detail, which is itself the most important thing a heartbeat
/// can report -- and the watchdog treats it as the one problem only a person can fix.
export async function GET() {
  try {
    const health = assess(await getHealthReadings(), new Date());
    return Response.json(health, {
      status: 200,
      headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=60" },
    });
  } catch {
    return Response.json(
      { ok: false, problems: [{ check: "database", lane: null, detail: "the database could not be read" }] },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
