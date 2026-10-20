/// Apply pending migrations to the primary, from a laptop, over the endpoint `.env` names.
///
///     node tools/migrate.mjs            apply
///     node tools/migrate.mjs status     say what is pending and apply nothing
///
/// `prisma7.config.ts` points the CLI at `DATABASE_URL`, which since 2026-10-11 is a **standby**
/// (brain.md rule 97) -- the primary is `SUPABASE_DATABASE_URL`. So a bare `prisma migrate deploy`
/// run here aims at the wrong database, and the fix on the command line is to paste a connection
/// string into a shell, which is how credentials end up in a history file. This does the same
/// substitution `.github/workflows/schema.yml` does in CI, reading the value from `.env` and
/// passing it to the child process only.
///
/// It prints no connection string, ever. The endpoint is named by its variable.
import { config } from "dotenv";
import { spawnSync } from "node:child_process";

config({ quiet: true });

// The primary and nothing else. There is deliberately no fallback to `DATABASE_URL`: that is a
// **standby** (brain.md rule 97), and a migration aimed at a standby would put the schema on a
// copy while the database the site reads stayed behind -- the exact failure
// `.github/workflows/schema.yml` migrates the standbys separately to avoid. With no primary
// configured this refuses rather than migrating something else.
const url = (process.env.SUPABASE_DATABASE_URL || "").trim();
if (!url) {
  console.error(
    "No primary is configured: set SUPABASE_DATABASE_URL in .env. This tool will not fall back " +
      "to DATABASE_URL, which is a standby.",
  );
  process.exit(1);
}
const name = "SUPABASE_DATABASE_URL";

const mode = process.argv[2] === "status" ? "status" : "deploy";
console.log(`prisma migrate ${mode} against ${name}`);
const r = spawnSync("npx", ["prisma", "migrate", mode], {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: { ...process.env, DATABASE_URL: url },
});
process.exit(r.status ?? 1);
