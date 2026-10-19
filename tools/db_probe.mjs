/// What each configured endpoint actually is, and what it will admit.
///
///     node tools/db_probe.mjs
///
/// Answers the three questions a connection fault needs and nothing else: can the endpoint be
/// reached, what does it allow, and how much of that is already in use. The answers are measured,
/// not read off a provider's pricing page -- `brain.md` rule 156 is a list of four things that were
/// called unreachable and were not, each from a single negative check generalised into an absence.
///
/// **It never prints a connection string, a credential or a host.** Each endpoint is named by its
/// environment variable and its role, which is all an operator needs to act, and the failure line is
/// put through the same redaction `lib/failover.ts` uses for its logs. The one piece of the URL it
/// does report is whether the string asks for encryption, because `withEncryption` is applied to
/// standbys and not to the primary and the difference is not otherwise visible.
import { config } from "dotenv";
import pg from "pg";

config();

/// The endpoints in the order `lib/db.ts` builds them: the primary first, then the standbys as
/// `standbys()` lists them. The names match the labels the failover logs use.
/// Pass `--saturate` to add the primary's client-ceiling measurement, which takes real slots while
/// it runs. Off by default so the plain probe stays safe to run beside a live server.
const SATURATE = process.argv.includes("--saturate");

const ENDPOINTS = [
  { env: "SUPABASE_DATABASE_URL", role: "primary (PRIMARY=supabase)" },
  { env: "DATABASE_URL_FALLBACK", role: "standby 1, Aiven" },
  { env: "DATABASE_URL", role: "standby 2, 'Neon'" },
];

/// One line about a failure, safe to log -- the same redaction as `lib/failover.ts` `describe`,
/// because a driver's error can carry the whole connection string.
function describe(error) {
  if (!(error instanceof Error)) return "unknown";
  return error.message
    .replace(/postgres(?:ql)?:\/\/\S+/gi, "<redacted-url>")
    .split("\n")[0]
    .slice(0, 160);
}

/// Does the string ask for encryption, and would `withEncryption` change it? Mirrors that function's
/// test exactly so the answer is the one the web layer acts on.
function encryption(url) {
  return /[?&]sslmode=/i.test(url) ? "names a sslmode" : "NO sslmode -- cleartext unless wrapped";
}

/// How many clients the primary's pooler will actually admit at once.
///
/// `max_connections` is the Postgres server's number and a session-mode pooler sits in front of it
/// with its own, lower one -- which is the number `primaryLimits` is trying to respect. The only way
/// to know it is to ask for connections until one is refused, so that is what this does: one at a
/// time, stopping at the first refusal or at `CEILING`, and closing every one it opened. Run it when
/// nothing else is using the endpoint, because what it measures is a shared total.
const CEILING = 24;

async function saturate() {
  const url = process.env.SUPABASE_DATABASE_URL?.trim();
  if (!url) return console.log("\nsaturation: SUPABASE_DATABASE_URL is not set");
  console.log(`\nsaturation of the primary: opening clients one at a time, up to ${CEILING}`);
  const open = [];
  let refusedAt = null;
  let refusal = "";
  try {
    for (let i = 1; i <= CEILING; i++) {
      const client = new pg.Client({ connectionString: url, connectionTimeoutMillis: 10_000 });
      try {
        await client.connect();
        await client.query("SELECT 1");
        open.push(client);
      } catch (error) {
        refusedAt = i;
        refusal = describe(error);
        try {
          await client.end();
        } catch {
          // Never connected; nothing to close.
        }
        break;
      }
    }
    console.log(
      refusedAt === null
        ? `  ${open.length} concurrent clients held, none refused -- the ceiling is above ${CEILING}`
        : `  refused at client ${refusedAt} with ${open.length} held: ${refusal}`,
    );
  } finally {
    // Every slot taken is given back, whatever happened: this runs against the live primary.
    await Promise.all(open.map((c) => c.end().catch(() => {})));
    console.log(`  released ${open.length} clients`);
  }
}

for (const { env, role } of ENDPOINTS) {
  const url = process.env[env]?.trim();
  console.log(`\n${env}  (${role})`);
  if (!url) {
    console.log("  not set");
    continue;
  }
  console.log(`  string: ${encryption(url)}`);

  // Encryption is asked for here the way the standby path asks for it, so an endpoint that only
  // accepts TLS is not reported unreachable for the want of a query parameter.
  const connectionString = /[?&]sslmode=/i.test(url)
    ? url
    : `${url}${url.includes("?") ? "&" : "?"}uselibpqcompat=true&sslmode=require`;
  const client = new pg.Client({ connectionString, connectionTimeoutMillis: 10_000 });
  const started = Date.now();
  try {
    await client.connect();
    const connectMs = Date.now() - started;
    const { rows } = await client.query(`
      SELECT current_setting('max_connections')::int        AS limit_total,
             (SELECT count(*) FROM pg_stat_activity)        AS in_use,
             current_setting('server_version')              AS version,
             (SELECT count(*) FROM information_schema.tables
               WHERE table_schema = 'public')               AS public_tables,
             pg_size_pretty(pg_database_size(current_database())) AS size,
             -- Reported, but read with care: behind a pooler this describes the pooler's own
             -- connection to Postgres, not this client's connection to the pooler. Both endpoints
             -- here are pooled and both answer false even when the client asked for TLS, so it says
             -- nothing about the leg that crosses the network. Whether this side is encrypted is
             -- decided by the connection string, which is what the "string:" line above reports.
             (SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()) AS backend_leg_encrypted
    `);
    const r = rows[0];
    console.log(`  reached in ${connectMs}ms, PostgreSQL ${r.version}`);
    console.log(`  connections: ${r.in_use} in use of ${r.limit_total} allowed`);
    console.log(`  database: ${r.public_tables} public tables, ${r.size}`);
    console.log(`  pooler's own backend leg: ${r.backend_leg_encrypted ? "encrypted" : "not encrypted"} (not this client's leg)`);
  } catch (error) {
    console.log(`  FAILED after ${Date.now() - started}ms: ${describe(error)}`);
  } finally {
    try {
      await client.end();
    } catch {
      // An endpoint that never connected has nothing to close.
    }
  }
}

if (SATURATE) await saturate();
