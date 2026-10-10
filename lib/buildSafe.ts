import { connection } from "next/server";
import { isConnectionFailure } from "@/lib/failover";

/// A page's data load that cannot fail a deploy because the database is unreachable.
///
/// The ISR pages are prerendered by `next build`, which means querying Postgres on Vercel's build
/// machine. On 2026-10-10 two production builds failed that way -- the primary over its quota, then a
/// connect timeout -- and while the primary stayed down nothing could ship, a fix included.
///
/// So when a build cannot reach any database tier (the same "this endpoint cannot be used" test the
/// failover makes), the page is not failed: `connection()` tells Next to render it at request time in
/// this deployment instead of prerendering it. The data still comes from the same queries and the same
/// caches; the next build that reaches the database prerenders it again. Anything that is not a
/// connection failure -- a bad query, a missing column -- still fails the build, loudly, as it should.
///
/// Outside a build this is the load and nothing else.
export async function loadOrDefer<T>(load: () => Promise<T>): Promise<T> {
  if (process.env.NEXT_PHASE !== "phase-production-build") return load();
  try {
    return await load();
  } catch (error) {
    if (!isConnectionFailure(error)) throw error;
    console.warn("build: no database tier answered, so this page renders at request time in this deployment");
    await connection();
    throw error;
  }
}

/// `generateStaticParams` with the same escape: no database at build time means no pages listed in
/// advance, and every one is rendered on its first visit and cached from then on.
export async function paramsOrNone<T>(load: () => Promise<T[]>): Promise<T[]> {
  if (process.env.NEXT_PHASE !== "phase-production-build") return load();
  try {
    return await load();
  } catch (error) {
    if (!isConnectionFailure(error)) throw error;
    console.warn("build: no database tier answered, so this route's pages are rendered on first visit");
    return [];
  }
}
