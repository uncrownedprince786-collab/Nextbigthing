// Read failover across an ordered list of endpoints: the primary, then each standby in turn.
//
// The properties worth testing are the ones where getting it wrong is silent:
//
//   * strict priority. A healthy tier earlier in the list is always preferred, and a later tier is
//     never touched while an earlier one works.
//   * it switches on an unreachable or over-quota endpoint, and on nothing else. A bad password
//     absorbed by a standby is a broken credential running in production for as long as the standby
//     holds out.
//   * each endpoint has its own cooldown, or one dead tier would freeze the others, and every
//     endpoint down at once must still be retried or a recovery waits out the window.
//   * it comes back. A cascade that never retried the primary is a permanent switch.
//   * a standby holding nothing is refused. "0 names" served as the site is worse than an error.
//   * it never logs a credential, and never writes.
//
// Driven by fake endpoints and a fake clock, because a real outage cannot be summoned on demand.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import {
  Failover,
  isConnectionFailure,
  withEncryption,
  COOLDOWN_MS,
  VETTING_TTL_MS,
  CONNECT_TIMEOUT_MS,
  STANDBY_MAX_CLIENTS,
  type Tier,
} from "../lib/failover.ts";

class Endpoint implements Tier<string> {
  calls = 0;
  checks = 0;
  discarded = 0;
  name: string;
  failWith: unknown;
  holdsData: boolean;
  constructor(name: string, failWith: unknown = null, holdsData = true) {
    this.name = name;
    this.failWith = failWith;
    this.holdsData = holdsData;
  }
  async connect() {
    this.calls += 1;
    if (this.failWith) throw this.failWith;
    return this.name;
  }
  async accept() {
    this.checks += 1;
    return this.holdsData;
  }
  discard() {
    this.discarded += 1;
  }
}

const refused = Object.assign(new Error("connect ECONNREFUSED 10.0.0.1:5432"), { code: "ECONNREFUSED" });
const quota = Object.assign(new Error("Your account or project has exceeded the quota."), { code: "53000" });
const badPassword = Object.assign(new Error('password authentication failed for user "x"'), { code: "28P01" });

function make(...tiers: Endpoint[]) {
  let clock = 1_000_000;
  const logs: string[] = [];
  const f = new Failover<string>(tiers, () => clock, (m) => logs.push(m));
  return { f, logs, advance: (ms: number) => (clock += ms) };
}

// --- what counts as "cannot be used right now" --------------------------------------------------

test("an unreachable or over-quota endpoint is a connection failure", () => {
  for (const code of ["ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "ENOTFOUND", "EAI_AGAIN", "EHOSTUNREACH"]) {
    assert.equal(isConnectionFailure(Object.assign(new Error("x"), { code })), true, code);
  }
  assert.equal(isConnectionFailure(quota), true);
  for (const code of ["08006", "08001", "53300", "57P01", "57P03"]) {
    assert.equal(isConnectionFailure(Object.assign(new Error("x"), { code })), true, code);
  }
});

test("the driver's wording counts when the code is gone, including a full pooler", () => {
  for (const m of [
    "Your account or project has exceeded the quota.",
    "timeout exceeded when trying to connect",
    "Connection terminated unexpectedly",
    "the database system is starting up",
    "sorry, too many clients already",
    "remaining connection slots are reserved",
  ]) {
    assert.equal(isConnectionFailure(new Error(m)), true, m);
  }
  assert.equal(isConnectionFailure(Object.assign(new Error("wrapped"), { cause: refused })), true);
});

test("Prisma's wrapping of the same conditions counts: what a page's query sees, not the pool", () => {
  // The exact shape a build with every tier unreachable produced on 2026-10-10 (P1001, with the
  // driver's error under meta.driverAdapterError), which went unrecognised and failed the build.
  const p1001 = Object.assign(new Error("Invalid `prisma.ranking.findMany()` invocation:\n\nCan't reach database server at 127.0.0.1:1"), {
    code: "P1001",
    meta: { modelName: "Ranking", driverAdapterError: new Error("DatabaseNotReachable") },
  });
  assert.equal(isConnectionFailure(p1001), true);
  for (const code of ["P1001", "P1002", "P1017"]) {
    assert.equal(isConnectionFailure(Object.assign(new Error("x"), { code })), true, code);
  }
  assert.equal(isConnectionFailure(Object.assign(new Error("x"), { meta: { driverAdapterError: refused } })), true);
  // A Prisma request error is still a request error: no record found, unique violation.
  for (const code of ["P2025", "P2002"]) {
    assert.equal(isConnectionFailure(Object.assign(new Error("x"), { code })), false, code);
  }
});

test("a bad credential or a bad request is not a reason to switch databases", () => {
  assert.equal(isConnectionFailure(badPassword), false);
  assert.equal(isConnectionFailure(Object.assign(new Error("syntax error"), { code: "42601" })), false);
  assert.equal(isConnectionFailure(Object.assign(new Error("duplicate key"), { code: "23505" })), false);
  assert.equal(isConnectionFailure(new Error("Tenant or user not found")), false);
  for (const v of [null, undefined, "string", 42, {}]) assert.equal(isConnectionFailure(v), false);
});

// --- strict priority ----------------------------------------------------------------------------

test("a healthy primary is used and no standby is ever touched", async () => {
  const [p, s1, s2] = [new Endpoint("p"), new Endpoint("s1"), new Endpoint("s2")];
  const { f } = make(p, s1, s2);
  for (let i = 0; i < 5; i += 1) assert.equal(await f.connect(), "p");
  assert.equal(s1.calls + s2.calls, 0);
  assert.equal(f.servingFrom, "p");
});

test("with the primary down the first standby serves, and the last is never touched", async () => {
  const [p, s1, s2] = [new Endpoint("p", quota), new Endpoint("s1"), new Endpoint("s2")];
  const { f, logs } = make(p, s1, s2);
  assert.equal(await f.connect(), "s1");
  assert.equal(s2.calls, 0, "a later tier was used while an earlier one worked");
  assert.match(logs.join("\n"), /s1/);
  assert.match(logs.join("\n"), /may be behind/);
});

// --- the cascade the platform needs: both Neon projects down, Supabase serves --------------------

test("both Neon projects failing routes traffic to Supabase", async () => {
  const primary = new Endpoint("the primary", quota);
  const neon2 = new Endpoint("the second Neon project", refused);
  const supabase = new Endpoint("Supabase");
  const { f, logs } = make(primary, neon2, supabase);

  assert.equal(await f.connect(), "Supabase");
  assert.equal(f.servingFrom, "Supabase");
  assert.equal(primary.calls, 1);
  assert.equal(neon2.calls, 1);
  assert.equal(supabase.calls, 1);

  // Said once per failing tier, then once for where the reads went.
  assert.equal(logs.filter((l) => /cannot be used/.test(l)).length, 2);
  assert.match(logs[logs.length - 1], /served from Supabase/);
  assert.match(logs[logs.length - 1], /may be behind/);
});

test("with both Neon projects in their cooldown, Supabase serves without retrying either", async () => {
  const [p, n2, sb] = [new Endpoint("p", quota), new Endpoint("n2", refused), new Endpoint("sb")];
  const { f, advance } = make(p, n2, sb);
  await f.connect();
  for (let i = 0; i < 25; i += 1) {
    advance(1000);
    assert.equal(await f.connect(), "sb");
  }
  assert.equal(p.calls, 1, "the dead primary was retried inside its cooldown");
  assert.equal(n2.calls, 1, "the dead standby was retried inside its cooldown");
  assert.equal(sb.calls, 26);
});

test("recovery is noticed tier by tier, always preferring the earliest healthy one", async () => {
  const [p, n2, sb] = [new Endpoint("p", quota), new Endpoint("n2", refused), new Endpoint("sb")];
  const { f, logs, advance } = make(p, n2, sb);
  assert.equal(await f.connect(), "sb");

  // The second Neon project comes back first: it is preferred over Supabase, the primary still down.
  n2.failWith = null;
  advance(COOLDOWN_MS + 1);
  assert.equal(await f.connect(), "n2");
  assert.equal(f.servingFrom, "n2");

  // Then the primary: reads return to it and the log says so.
  p.failWith = null;
  advance(COOLDOWN_MS + 1);
  assert.equal(await f.connect(), "p");
  assert.match(logs[logs.length - 1], /p is answering again/);
  assert.equal(await f.connect(), "p");
});

test("a cascade that never retried the primary would be a permanent switch", async () => {
  const [p, sb] = [new Endpoint("p", refused), new Endpoint("sb")];
  const { f, advance } = make(p, sb);
  await f.connect();
  p.failWith = null;
  advance(COOLDOWN_MS * 10);
  assert.equal(await f.connect(), "p");
});

// --- the cooldown is per endpoint ----------------------------------------------------------------

test("a dead standby does not stop a healthy primary being used", async () => {
  const [p, dead] = [new Endpoint("p"), new Endpoint("dead", refused)];
  const { f } = make(p, dead);
  for (let i = 0; i < 4; i += 1) assert.equal(await f.connect(), "p");
  assert.equal(dead.calls, 0, "an unneeded standby was probed");
});

test("every endpoint down at once is still retried, so a recovery does not wait out the window", async () => {
  const [p, sb] = [new Endpoint("p", refused), new Endpoint("sb", refused)];
  const { f, advance } = make(p, sb);
  await assert.rejects(f.connect(), /ECONNREFUSED/);
  assert.equal(f.usingStandby, true);

  // Seconds later Supabase is back. Both are inside their cooldown, but nothing else could serve.
  advance(2000);
  sb.failWith = null;
  assert.equal(await f.connect(), "sb");
});

test("all endpoints down raises the primary's error, once per tier and not in a loop", async () => {
  const [p, n2, sb] = [new Endpoint("p", quota), new Endpoint("n2", refused), new Endpoint("sb", refused)];
  const { f } = make(p, n2, sb);
  await assert.rejects(f.connect(), /exceeded the quota/);
  assert.deepEqual([p.calls, n2.calls, sb.calls], [1, 1, 1]);
});

// --- credentials: loud on the primary, skipped on a standby --------------------------------------

test("the primary's bad credential is raised, never absorbed by a standby", async () => {
  const [p, sb] = [new Endpoint("p", badPassword), new Endpoint("sb")];
  const { f } = make(p, sb);
  await assert.rejects(f.connect(), /password authentication failed/);
  assert.equal(sb.calls, 0);
});

test("a standby's bad credential is logged as a configuration fault and the next tier serves", async () => {
  const [p, n2, sb] = [new Endpoint("p", refused), new Endpoint("n2", badPassword), new Endpoint("sb")];
  const { f, logs } = make(p, n2, sb);
  assert.equal(await f.connect(), "sb");
  assert.match(logs.join("\n"), /configuration fault, not an outage/);
});

// --- a standby that holds nothing ----------------------------------------------------------------

test("a standby that answers but holds no data is refused, and the next tier serves", async () => {
  const [p, empty, sb] = [new Endpoint("p", refused), new Endpoint("empty", null, false), new Endpoint("sb")];
  const { f, logs } = make(p, empty, sb);
  assert.equal(await f.connect(), "sb");
  assert.equal(empty.discarded, 1, "the rejected connection was not given back");
  assert.match(logs.join("\n"), /holds no data/);
});

test("an empty standby alone is an error and not an empty site", async () => {
  const [p, empty] = [new Endpoint("p", refused), new Endpoint("empty", null, false)];
  const { f } = make(p, empty);
  await assert.rejects(f.connect(), /ECONNREFUSED/);
});

test("a standby is checked for data once, then trusted until the vetting window passes", async () => {
  const [p, s1] = [new Endpoint("p", refused), new Endpoint("s1")];
  const { f, advance } = make(p, s1);
  await f.connect();
  advance(1000);
  await f.connect();
  assert.equal(s1.checks, 1, "checked on every request");
  advance(VETTING_TTL_MS + 1);
  await f.connect();
  assert.equal(s1.checks, 2);
});

test("the primary is never asked whether it holds data", async () => {
  const p = new Endpoint("p");
  const { f } = make(p, new Endpoint("s"));
  await f.connect();
  assert.equal(p.checks, 0);
});

// --- nothing secret is logged --------------------------------------------------------------------

test("a connection string inside a driver error never reaches the log", async () => {
  const leaky = Object.assign(
    new Error("invalid connection option postgresql://user:hunter2@host.example/db?x=1"),
    { code: "ECONNREFUSED" },
  );
  const [p, sb] = [new Endpoint("p", leaky), new Endpoint("sb")];
  const { f, logs } = make(p, sb);
  await f.connect();
  const all = logs.join("\n");
  assert.ok(!all.includes("hunter2"), all);
  assert.ok(!all.includes("postgresql://user"), all);
  assert.match(all, /redacted-url/);
});

// --- encryption ----------------------------------------------------------------------------------

test("encryption is asked for when the URL names no mode, and never when it does", () => {
  // Measured against the real Supabase pooler: no mode connects unencrypted, sslmode=require fails on
  // the CA chain, and the libpq-compatible form connects encrypted.
  assert.equal(
    withEncryption("postgresql://u:p@h.example:5432/postgres"),
    "postgresql://u:p@h.example:5432/postgres?uselibpqcompat=true&sslmode=require",
  );
  assert.equal(
    withEncryption("postgresql://u:p@h.example/db?application_name=x"),
    "postgresql://u:p@h.example/db?application_name=x&uselibpqcompat=true&sslmode=require",
  );
  const neon = "postgresql://u:p@h.example/db?sslmode=require&channel_binding=require";
  assert.equal(withEncryption(neon), neon, "a URL that chose its own mode was rewritten");
  assert.equal(withEncryption("postgresql://u:p@h/db?SSLMODE=disable"), "postgresql://u:p@h/db?SSLMODE=disable");
});

test("a connection attempt has a ceiling, or a black-holed endpoint hangs instead of failing over", () => {
  assert.ok(CONNECT_TIMEOUT_MS > 0 && CONNECT_TIMEOUT_MS <= 10_000);
  const src = readFileSync(new URL("../lib/failover.ts", import.meta.url), "utf8");
  assert.match(src, /connectionTimeoutMillis: CONNECT_TIMEOUT_MS/);
});

// --- where it is wired, and where it must never be ------------------------------------------------

test("the standbys are tried in the stated order: the second Neon project, then Supabase", () => {
  const db = readFileSync(new URL("../lib/db.ts", import.meta.url), "utf8");
  const neon = db.indexOf("process.env.DATABASE_URL_FALLBACK");
  const supabase = db.indexOf("process.env.SUPABASE_DATABASE_URL");
  assert.ok(neon > 0 && supabase > 0, "a standby is not read from the environment");
  assert.ok(neon < supabase, "Supabase is ahead of the second Neon project in the priority order");
});

test("each standby is optional, so no configuration is the single-endpoint client it always was", () => {
  const db = readFileSync(new URL("../lib/db.ts", import.meta.url), "utf8");
  assert.match(db, /\.filter\(\(c\): c is \{ name: string; url: string \} => Boolean\(c\.url\)\)/);
  const failover = readFileSync(new URL("../lib/failover.ts", import.meta.url), "utf8");
  assert.match(failover, /if \(standbys\.length === 0\) return new pg\.Pool\(primary\)/);
});

test("a writer reaches a standby only through the write failover, never through the site's pool", () => {
  // Until 2026-10-10 no lane wrote a standby at all. Writes now survive a quota pause: jobs/nbt.py `db`
  // and tools/writer.mjs move a lane to the standby when the primary cannot be reached, and
  // jobs/reconcile.py copies those rows back before the primary is written again -- which is what makes
  // two written databases safe. What stays forbidden is this file's pool, which switches mid-run and
  // has no copy back, and any other job naming a standby on its own.
  const root = new URL("../", import.meta.url);
  // schemacheck.py names SUPABASE_DATABASE_URL only in the message telling the owner which .env line to use.
  // standby_parity.py reads each standby to report what a failover would serve; it writes nothing.
  const allowed = new Set(["mirror.py", "schema_parity.py", "standby_parity.py", "nbt.py", "reconcile.py", "writer.mjs", "logic_audit.py", "schemacheck.py"]);
  for (const dir of ["jobs", "tools"]) {
    for (const name of readdirSync(new URL(`${dir}/`, root))) {
      if (!/\.(py|mjs|ts)$/.test(name)) continue;
      const text = readFileSync(new URL(`${dir}/${name}`, root), "utf8");
      assert.ok(!/makeFailoverPool/.test(text), `${dir}/${name} uses the site's read pool`);
      if (allowed.has(name)) continue;
      assert.ok(!/DATABASE_URL_FALLBACK|SUPABASE_DATABASE_URL/.test(text), `${dir}/${name} names a standby itself`);
    }
  }
  for (const name of ["decide.mjs", "macro_gate.mjs"]) {
    assert.match(readFileSync(new URL(`tools/${name}`, root), "utf8"), /import \{ writerPool \} from "\.\/writer\.mjs";/, name);
  }
});

test("the environment is read in exactly one web file", () => {
  const root = new URL("../", import.meta.url);
  const hits: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(new URL(`${dir}/`, root), { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!["node_modules", ".next", "generated"].includes(entry.name)) walk(`${dir}/${entry.name}`);
      } else if (/\.tsx?$/.test(entry.name)) {
        const text = readFileSync(new URL(`${dir}/${entry.name}`, root), "utf8");
        if (/SUPABASE_DATABASE_URL|DATABASE_URL_FALLBACK/.test(text)) hits.push(`${dir}/${entry.name}`);
      }
    }
  };
  for (const dir of ["lib", "app", "components"]) walk(dir);
  assert.deepEqual(hits, ["lib/db.ts"]);
});

test("only a connection-time failure switches: the pool overrides connect and nothing else", () => {
  const src = readFileSync(new URL("../lib/failover.ts", import.meta.url), "utf8");
  const code = src.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
  // No query, transaction or write method is overridden. The one query in this file is the standby's
  // data check, a read of a single row.
  for (const forbidden of ["BEGIN", "COMMIT", "INSERT", "UPDATE", "DELETE"]) {
    assert.ok(!code.includes(forbidden), `lib/failover.ts touches ${forbidden}`);
  }
  assert.equal((code.match(/client\.query\(/g) ?? []).length, 1);
  assert.match(code, /SELECT 1 FROM "PriceSnapshot" LIMIT 1/);
});

// --- a full pooler is a full endpoint, not a bad configuration ------------------------------------

test("a pooler with no free slot is capacity exhaustion, whatever SQLSTATE it arrives under", () => {
  // Measured against the real Supabase session pooler: it answers XX000, not 53300, with this text
  // once its 15 slots are taken. It was classified as a configuration fault, so a full standby failed
  // the request instead of being skipped.
  const full = Object.assign(
    new Error("(EMAXCONNSESSION) max clients reached in session mode - max clients are limited to pool_size: 15"),
    { code: "XX000" },
  );
  assert.equal(isConnectionFailure(full), true);
  assert.equal(isConnectionFailure(new Error("max clients reached")), true);
  // A genuine internal error under the same SQLSTATE is still not one.
  assert.equal(isConnectionFailure(Object.assign(new Error("something broke"), { code: "XX000" })), false);
});

test("a standby that is full is skipped as an outage, and the next tier serves", async () => {
  const full = Object.assign(new Error("(EMAXCONNSESSION) max clients reached in session mode"), { code: "XX000" });
  const [p, s1, s2] = [new Endpoint("p", refused), new Endpoint("s1", full), new Endpoint("s2")];
  const { f, logs } = make(p, s1, s2);
  assert.equal(await f.connect(), "s2");
  assert.ok(!/configuration fault/.test(logs.join(" | ")), "a full pooler was reported as a configuration fault");
});

test("a standby pool is small, because a free pooler admits few clients in total", () => {
  // Supabase's free session pooler: 15 clients across everything that connects. Every concurrent
  // serverless instance has its own pool, so the per-process ceiling is what keeps one outage from
  // draining the pooler for the next instance.
  assert.ok(STANDBY_MAX_CLIENTS >= 1 && STANDBY_MAX_CLIENTS <= 3, String(STANDBY_MAX_CLIENTS));
  const src = readFileSync(new URL("../lib/failover.ts", import.meta.url), "utf8");
  assert.match(src, /withTimeout\(s\.config, STANDBY_MAX_CLIENTS\)/);
});

test("a Supabase primary gets two connections per instance; Neon keeps pg's default", async () => {
  const src = readFileSync(new URL("../lib/db.ts", import.meta.url), "utf8");
  assert.match(src, /makeFailoverPool\(\{ connectionString: url, \.\.\.primaryLimits\(url\) \}, standbys\(url\)\)/);
  assert.match(src, /databaseKey\(c\.url\) !== databaseKey\(primary\)/, "the primary is never its own standby");
  assert.match(src, /hostname\.endsWith\("\.supabase\.com"\)\) return \{ max: 2,/);
});
