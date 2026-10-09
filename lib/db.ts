import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@/prisma/generated/prisma/client";
import { makeFailoverPool } from "@/lib/failover";

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

function create() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Copy .env.example to .env and paste the Neon connection string.",
    );
  }
  // Opt-in read failover. With `DATABASE_URL_FALLBACK` unset this is the single-endpoint client it
  // always was, so a deployment that has not set it behaves exactly as before. See lib/failover.ts
  // for what the standby is and is not: a copy that `jobs/mirror.py` refreshes, possibly behind, and
  // never a place anything is written.
  const standby = process.env.DATABASE_URL_FALLBACK;
  const pool = makeFailoverPool(
    { connectionString: url },
    standby ? { connectionString: standby } : null,
  );
  return new PrismaClient({ adapter: new PrismaPg(pool) });
}

/// One client per process. Next.js reloads modules in development, so the client is
/// kept on globalThis to avoid exhausting the Neon connection pool.
export const prisma = globalForPrisma.prisma ?? create();

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
