import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@/prisma/generated/prisma/client";
import { makeFailoverPool, withEncryption, type StandbyConfig } from "@/lib/failover";

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

/// The standbys, in the order they are tried after the primary.
///
/// The order here IS the priority: the second Neon project first, Supabase last. Each is optional and
/// an unset one is simply absent, so a deployment can run with none (the single-endpoint client it
/// always was), one, or both. The environment is read here and nowhere else in the web layer, and
/// the values are only ever passed on -- never logged, never put in an error.
///
/// What a standby is and is not (a copy that `jobs/mirror.py` refreshes, possibly behind, never a
/// place anything is written) is in lib/failover.ts.
function standbys(): StandbyConfig[] {
  const candidates: { name: string; url: string | undefined }[] = [
    { name: "the second Neon project", url: process.env.DATABASE_URL_FALLBACK },
    { name: "Supabase", url: process.env.SUPABASE_DATABASE_URL },
  ];
  return candidates
    .filter((c): c is { name: string; url: string } => Boolean(c.url))
    .map((c) => ({ name: c.name, config: { connectionString: withEncryption(c.url) } }));
}

function create() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Copy .env.example to .env and paste the Neon connection string.",
    );
  }
  const pool = makeFailoverPool({ connectionString: url }, standbys());
  return new PrismaClient({ adapter: new PrismaPg(pool) });
}

/// One client per process. Next.js reloads modules in development, so the client is
/// kept on globalThis to avoid exhausting the Neon connection pool.
export const prisma = globalForPrisma.prisma ?? create();

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
