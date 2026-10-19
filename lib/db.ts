import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@/prisma/generated/prisma/client";
import { makeFailoverPool, transactionPoolUrl, withEncryption, type StandbyConfig } from "@/lib/failover";

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };
/// The failover pool behind `prisma`, kept for `servingTier`. Null with no standby configured.
let servingPool: { servingFrom?: () => string } | null = null;

/// The standbys, in the order they are tried after the primary.
///
/// The order here IS the priority: Aiven first, Supabase last. Each is optional and
/// an unset one is simply absent, so a deployment can run with none (the single-endpoint client it
/// always was), one, or both. The environment is read here and nowhere else in the web layer, and
/// the values are only ever passed on -- never logged, never put in an error.
///
/// What a standby is and is not (a copy that `jobs/mirror.py` refreshes, possibly behind, never a
/// place anything is written) is in lib/failover.ts.
/// The host, port and database a connection string selects, credentials and `-pooler` ignored, so the
/// primary and a standby that are the same database compare equal.
function databaseKey(url: string): string {
  try {
    const u = new URL(url);
    return `${u.hostname.replace("-pooler", "")}:${u.port || "5432"}${u.pathname}`;
  } catch {
    return url;
  }
}

/// Re-exported so `lib/db.ts` remains the one place the web layer's connection choices are read,
/// while the rewriting itself lives beside `withEncryption` in `lib/failover.ts` -- both are
/// "what string do we actually dial", and both have to be testable without Prisma's path aliases.
export { transactionPoolUrl };

/// How many connections the app's pool may hold, and for how long. **Two, in either mode.**
///
/// Raising this was the obvious-looking half of the transaction-mode change and it was wrong, so
/// the measurement is written down rather than left to be rediscovered. On 2026-10-19 a cold
/// dev server was swept at concurrency 4 against the transaction pooler with `max: 10`: `/events`,
/// `/logbook`, `/marketplace`, `/methodology` and `/products` returned **500**, all of them
/// `Connection terminated unexpectedly` / `timeout exceeded when trying to connect`. The same sweep
/// against the session pooler with `max: 2` returned **200 on all eight**. Connection establishment
/// was never the problem -- ten concurrent connects to the transaction pooler completed in 1.27 s.
///
/// The reason is that a bigger per-instance pool was never what transaction mode buys. In session
/// mode a client connection owns a Postgres backend until it closes, so 15 server connections are
/// 15 clients and every warm instance holding two is two the rest of the estate cannot have. In
/// transaction mode the backend returns to the pool at the end of each transaction, so those same
/// two connections per instance serve many more requests and stop being a standing reservation.
/// The win is in how long a slot is *held*, not how many an instance may open -- and asking for ten
/// simply moves the contention out of this app and into Supavisor, where it arrives as a dropped
/// socket instead of a queued acquisition.
///
/// `Gate` in `lib/failover.ts` takes its capacity from this `max`, so the number also bounds how
/// many of a cold render's fan-out are outstanding at once. Two is what that layer was measured
/// against.
export function primaryLimits(url: string): { max?: number; idleTimeoutMillis?: number; allowExitOnIdle?: boolean } {
  try {
    if (new URL(url).hostname.endsWith(".supabase.com")) {
      return { max: 2, idleTimeoutMillis: 2_000, allowExitOnIdle: true };
    }
  } catch {
    // An unparseable string is pg's problem to report, not this function's.
  }
  return {};
}

/// The primary database (brain.md rule 97), as jobs/nbt.py `primary_choice` and tools/writer.mjs pick it:
/// Supabase unless PRIMARY=neon. The owner keeps the project on free tiers, and Neon's free tier caps
/// compute hours -- the derive passes used them up twice in two days -- where Supabase's caps size and
/// connections, which `primaryLimits` already keeps small. Without a Supabase URL it is DATABASE_URL.
export function primaryUrl(env: Record<string, string | undefined> = process.env): string | undefined {
  const supabase = env.SUPABASE_DATABASE_URL?.trim();
  if ((env.PRIMARY ?? "supabase").trim().toLowerCase() === "supabase" && supabase) return supabase;
  return env.DATABASE_URL?.trim();
}

function standbys(primary: string): StandbyConfig[] {
  const candidates: { name: string; url: string | undefined }[] = [
    // Named for what they actually are. These were "the second Neon project" and "Neon" until
    // 2026-10-19: Neon was replaced on 2026-10-11 and the labels were never updated, so a failover
    // warning in production named a provider the project had already left. `DATABASE_URL_FALLBACK`
    // is Aiven; `DATABASE_URL` is the Prisma tier, currently unreachable (`planLimitReached`).
    // Trimmed: a value pasted with its trailing line break names a database that does not exist.
    { name: "Aiven", url: process.env.DATABASE_URL_FALLBACK?.trim() },
    { name: "Supabase", url: process.env.SUPABASE_DATABASE_URL?.trim() },
    { name: "the Prisma tier", url: process.env.DATABASE_URL?.trim() },
  ];
  return candidates
    .filter((c): c is { name: string; url: string } => Boolean(c.url))
    // A standby that is the primary itself (Supabase promoted to primary) is not a second chance.
    .filter((c) => databaseKey(c.url) !== databaseKey(primary))
    // One entry per database: two variables can name the same one.
    .filter((c, i, all) => all.findIndex((x) => databaseKey(x.url) === databaseKey(c.url)) === i)
    .map((c) => ({ name: c.name, config: { connectionString: withEncryption(c.url) } }));
}

function create() {
  const url = primaryUrl();
  if (!url) {
    throw new Error(
      "No primary database is configured. Copy .env.example to .env and set SUPABASE_DATABASE_URL.",
    );
  }
  // Encryption is asked for here too, and not only for the standbys (`standbys()` above).
  // `withEncryption` leaves a URL that already names a mode exactly as it was, so this changes
  // nothing for a Neon string; what it changes is the Supabase one, which names no mode at all.
  // With no mode the Node driver connects **unencrypted** -- measured against the real pooler, and
  // written down in `withEncryption`'s own comment -- so the primary was the one endpoint reached in
  // cleartext while every standby was wrapped. The asymmetry is not a decision anyone took: it is
  // that the wrapper was added where the standbys were built and the primary was passed on raw.
  // The web pool, and only the web pool, reads Supabase through the transaction pooler: see
  // `transactionPoolUrl`. `standbys()` is left on whatever its own strings name, because a standby
  // is a different provider with a different pooler and nothing here knows its modes.
  const served = transactionPoolUrl(url);
  const pool = makeFailoverPool(
    { connectionString: withEncryption(served), ...primaryLimits(served) },
    standbys(url),
  );
  servingPool = pool as unknown as { servingFrom?: () => string };
  return new PrismaClient({ adapter: new PrismaPg(pool) });
}

/// One client per process. Next.js reloads modules in development, so the client is
/// kept on globalThis to avoid exhausting the pooler's client slots.
export const prisma = globalForPrisma.prisma ?? create();

/// Which database tier the last read came from: "the primary", or a standby's name (brain.md rule 94).
/// A standby holds mirrored prices, decisions and news but not the setups, factors and analogs a call is
/// built from, which lag by a day or more; the lists publish no call from a standby read.
export function servingTier(): string {
  return servingPool?.servingFrom ? servingPool.servingFrom() : "the primary";
}

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
