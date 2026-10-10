// The write pool for the Node jobs (tools/decide.mjs, tools/macro_gate.mjs): the primary, or the standby
// when the primary cannot be reached. The same rule as `db()` in jobs/nbt.py, which every Python job
// uses, so a quota pause moves every writer in a lane to the same database, and jobs/reconcile.py copies
// the standby's rows back once the primary answers. Not used by the site, which only reads and fails
// over through lib/failover.ts; it lives here, outside the web layer, for that reason. A wrong password
// is a configuration fault and is raised, never failed over. WRITE_FAILOVER=off turns it off.

import pg from "pg";
import { isConnectionFailure, withEncryption } from "../lib/failover.ts";

/// What selects a database: host without the pooler suffix, port, name, and for a Supabase pooler the
/// user, which is where Supabase puts the project. Matches `database_key` in jobs/nbt.py.
/** @param {string} url @returns {string} */
export function databaseKey(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace("-pooler", "");
    const user = host.endsWith("supabase.com") ? decodeURIComponent(u.username) : "";
    return `${host}:${u.port || "5432"}${u.pathname}|${user}`;
  } catch {
    return url;
  }
}

/// The standby a writer may use when the primary is down: { name, url }, or null.
/**
 * @param {string} primary
 * @param {Record<string, string | undefined>} [env]
 * @returns {{ name: string, url: string } | null}
 */
export function standbyFor(primary, env = process.env) {
  if ((env.WRITE_FAILOVER ?? "").trim().toLowerCase() === "off") return null;
  for (const name of ["SUPABASE_DATABASE_URL", "DATABASE_URL_FALLBACK"]) {
    const url = env[name]?.trim();
    if (url && databaseKey(url) !== databaseKey(primary)) return { name, url };
  }
  return null;
}

/// A pool on the primary, proven with one query; or on the standby when the primary cannot be reached.
/// Resolves to { pool, target }, target being "primary" or the standby's variable name.
/**
 * @param {number} max
 * @param {{ env?: Record<string, string | undefined>, log?: (m: string) => void, make?: (url: string) => import("pg").Pool }} [options]
 * @returns {Promise<{ pool: import("pg").Pool, target: string }>}
 */
export async function writerPool(
  max,
  {
    env = process.env,
    log = (m) => console.log(m),
    make = (url) => new pg.Pool({ connectionString: withEncryption(url), max, connectionTimeoutMillis: 20_000 }),
  } = {},
) {
  // Trimmed: a secret pasted with its trailing line break names a database that does not exist.
  const primary = (env.DATABASE_URL ?? "").trim();
  const first = make(primary);
  try {
    await first.query("SELECT 1");
    return { pool: first, target: "primary" };
  } catch (error) {
    await first.end().catch(() => {});
    const standby = standbyFor(primary, env);
    if (!standby || !isConnectionFailure(error)) throw error;
    const second = make(standby.url);
    try {
      await second.query("SELECT 1");
    } catch {
      await second.end().catch(() => {});
      throw error; // both down: the primary's failure is the one an operator needs
    }
    const why = (error instanceof Error ? error.message : String(error))
      .replace(/postgres(?:ql)?:\/\/\S+/gi, "<redacted>")
      .split("\n")[0]
      .slice(0, 160);
    log(
      `::warning title=Writing to the standby::The primary could not be reached (${why}), so this run writes ${standby.name}. jobs/reconcile.py copies these rows back the first time a lane reaches the primary again.`,
    );
    return { pool: second, target: standby.name };
  }
}
