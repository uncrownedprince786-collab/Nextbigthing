import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@/prisma/generated/prisma/client";
import { makeFailoverPool, withEncryption, type StandbyConfig } from "@/lib/failover";

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };
/// The failover pool behind `prisma`, kept for `servingTier`. Null with no standby configured.
let servingPool: { servingFrom?: () => string } | null = null;

/// The standbys, in the order they are tried after the primary.
///
/// The order here IS the priority: the second Neon project first, Supabase last. Each is optional and
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

/// A Supabase pooler admits 15 session clients in all, shared by every server instance and every job;
/// pg's default of 10 per instance would fill it on the second instance. So a Supabase primary gets
/// two connections per instance, let go after two seconds idle. Neon is unchanged.
export function primaryLimits(url: string): { max?: number; idleTimeoutMillis?: number; allowExitOnIdle?: boolean } {
  try {
    if (new URL(url).hostname.endsWith(".supabase.com")) return { max: 2, idleTimeoutMillis: 2_000, allowExitOnIdle: true };
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
    // Trimmed: a value pasted with its trailing line break names a database that does not exist.
    { name: "the second Neon project", url: process.env.DATABASE_URL_FALLBACK?.trim() },
    { name: "Supabase", url: process.env.SUPABASE_DATABASE_URL?.trim() },
    // Neon, when Supabase is the primary (rule 97).
    { name: "Neon", url: process.env.DATABASE_URL?.trim() },
  ];
  return candidates
    .filter((c): c is { name: string; url: string } => Boolean(c.url))
    // A standby that is the primary itself (Supabase promoted to primary) is not a second chance.
    .filter((c) => databaseKey(c.url) !== databaseKey(primary))
    // One entry per database: the second Neon project and Neon can be the same one.
    .filter((c, i, all) => all.findIndex((x) => databaseKey(x.url) === databaseKey(c.url)) === i)
    .map((c) => ({ name: c.name, config: { connectionString: withEncryption(c.url) } }));
}

function create() {
  const url = primaryUrl();
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Copy .env.example to .env and paste the Neon connection string.",
    );
  }
  const pool = makeFailoverPool({ connectionString: url, ...primaryLimits(url) }, standbys(url));
  servingPool = pool as unknown as { servingFrom?: () => string };
  return new PrismaClient({ adapter: new PrismaPg(pool) });
}

/// One client per process. Next.js reloads modules in development, so the client is
/// kept on globalThis to avoid exhausting the Neon connection pool.
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
