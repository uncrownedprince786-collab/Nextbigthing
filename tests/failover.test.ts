// Read failover between two Postgres endpoints, decided when a connection is made.
//
// The properties worth testing are the ones where getting it wrong is silent:
//
//   * it must switch on an unreachable or over-quota endpoint, and on nothing else. A bad password
//     absorbed by a standby is a broken credential running in production for as long as the standby
//     holds out.
//   * it must leave the primary alone for a window after a failure, or every page pays the primary's
//     connect timeout before reaching the standby.
//   * it must come back. A failover that never retries the primary is a permanent switch.
//   * it must never be on a write path.
//
// Driven by a fake endpoint and a fake clock, because a real outage cannot be summoned on demand.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { Failover, isConnectionFailure, PRIMARY_COOLDOWN_MS } from "../lib/failover.ts";

class Endpoint {
  calls = 0;
  name: string;
  failWith: unknown;
  constructor(name: string, failWith: unknown = null) {
    this.name = name;
    this.failWith = failWith;
  }
  async connect() {
    this.calls += 1;
    if (this.failWith) throw this.failWith;
    return this.name;
  }
}

const refused = Object.assign(new Error("connect ECONNREFUSED 10.0.0.1:5432"), { code: "ECONNREFUSED" });
const quota = Object.assign(new Error("Your account or project has exceeded the quota."), { code: "53000" });
const badPassword = Object.assign(new Error('password authentication failed for user "x"'), { code: "28P01" });

function make(primary: Endpoint, standby: Endpoint | null) {
  let clock = 1_000_000;
  const logs: string[] = [];
  const f = new Failover(primary, standby, () => clock, (m) => logs.push(m));
  return { f, logs, advance: (ms: number) => (clock += ms) };
}

// --- what counts as "cannot be used right now" --------------------------------------------------

test("an unreachable or over-quota endpoint is a connection failure", () => {
  for (const code of ["ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "ENOTFOUND", "EAI_AGAIN", "EHOSTUNREACH"]) {
    assert.equal(isConnectionFailure(Object.assign(new Error("x"), { code })), true, code);
  }
  // Neon's quota arrives as Postgres class 53 during startup -- the failure that took the site down.
  assert.equal(isConnectionFailure(quota), true);
  for (const code of ["08006", "08001", "53300", "57P01", "57P03"]) {
    assert.equal(isConnectionFailure(Object.assign(new Error("x"), { code })), true, code);
  }
});

test("the driver's wording counts when the code is gone", () => {
  assert.equal(isConnectionFailure(new Error("Your account or project has exceeded the quota.")), true);
  assert.equal(isConnectionFailure(new Error("timeout exceeded when trying to connect")), true);
  assert.equal(isConnectionFailure(new Error("Connection terminated unexpectedly")), true);
  assert.equal(isConnectionFailure(new Error("the database system is starting up")), true);
  // And through a wrapper, which is how the adapter delivers it.
  assert.equal(isConnectionFailure(Object.assign(new Error("wrapped"), { cause: refused })), true);
});

test("a bad credential or a bad request is not a reason to switch databases", () => {
  // 28xxx: a wrong password is a configuration fault that must be loud.
  assert.equal(isConnectionFailure(badPassword), false);
  assert.equal(isConnectionFailure(Object.assign(new Error("syntax error"), { code: "42601" })), false);
  assert.equal(isConnectionFailure(Object.assign(new Error("duplicate key"), { code: "23505" })), false);
  assert.equal(isConnectionFailure(new Error("something else")), false);
  for (const v of [null, undefined, "string", 42, {}]) assert.equal(isConnectionFailure(v), false);
});

// --- routing ------------------------------------------------------------------------------------

test("a healthy primary is used and the standby is never touched", async () => {
  const primary = new Endpoint("primary");
  const standby = new Endpoint("standby");
  const { f } = make(primary, standby);
  for (let i = 0; i < 5; i += 1) assert.equal(await f.connect(), "primary");
  assert.equal(standby.calls, 0);
});

test("a failed primary hands out the standby and says so once", async () => {
  const primary = new Endpoint("primary", quota);
  const standby = new Endpoint("standby");
  const { f, logs } = make(primary, standby);
  assert.equal(await f.connect(), "standby");
  assert.equal(f.usingStandby, true);
  assert.equal(logs.length, 1);
  assert.match(logs[0], /could not be reached/);
  assert.match(logs[0], /may be behind/, "the standby's staleness has to be in the log line");
  assert.match(logs[0], /exceeded the quota/);
});

test("the primary is left alone for the cooldown, so a down primary costs one slow request", async () => {
  const primary = new Endpoint("primary", refused);
  const standby = new Endpoint("standby");
  const { f, advance } = make(primary, standby);
  await f.connect();
  assert.equal(primary.calls, 1);
  for (let i = 0; i < 20; i += 1) {
    advance(1000);
    assert.equal(await f.connect(), "standby");
  }
  assert.equal(primary.calls, 1, "the primary was retried inside its cooldown");
});

test("after the cooldown the primary is tried again, and a recovery is noticed", async () => {
  const primary = new Endpoint("primary", refused);
  const standby = new Endpoint("standby");
  const { f, logs, advance } = make(primary, standby);
  await f.connect();

  // Still down at the first retry: back on the standby, and the cooldown starts over.
  advance(PRIMARY_COOLDOWN_MS + 1);
  assert.equal(await f.connect(), "standby");
  assert.equal(primary.calls, 2);
  assert.equal(logs.length, 1, "a continuing outage must not log on every retry");

  // Recovered at the next one.
  primary.failWith = null;
  advance(PRIMARY_COOLDOWN_MS + 1);
  assert.equal(await f.connect(), "primary");
  assert.equal(f.usingStandby, false);
  assert.match(logs[logs.length - 1], /answering again/);
  // And the routing is back to normal.
  assert.equal(await f.connect(), "primary");
});

test("a failover that never retried the primary would be a permanent switch", async () => {
  const primary = new Endpoint("primary", refused);
  const standby = new Endpoint("standby");
  const { f, advance } = make(primary, standby);
  await f.connect();
  primary.failWith = null;
  advance(PRIMARY_COOLDOWN_MS * 10);
  assert.equal(await f.connect(), "primary");
});

test("a bad credential is raised, never absorbed by the standby", async () => {
  const primary = new Endpoint("primary", badPassword);
  const standby = new Endpoint("standby");
  const { f } = make(primary, standby);
  await assert.rejects(f.connect(), /password authentication failed/);
  assert.equal(standby.calls, 0);
  assert.equal(f.usingStandby, false);
});

test("with no standby the primary's error is raised unchanged", async () => {
  const { f, logs } = make(new Endpoint("primary", quota), null);
  await assert.rejects(f.connect(), /exceeded the quota/);
  assert.equal(logs.length, 0);
});

test("both endpoints down is an error, not a loop", async () => {
  const primary = new Endpoint("primary", refused);
  const standby = new Endpoint("standby", refused);
  const { f } = make(primary, standby);
  await assert.rejects(f.connect(), /ECONNREFUSED/);
  assert.equal(primary.calls, 1);
  assert.equal(standby.calls, 1);
});

// --- where it is, and where it must never be ----------------------------------------------------

test("the failover is off unless a fallback is configured", () => {
  const db = readFileSync(new URL("../lib/db.ts", import.meta.url), "utf8");
  assert.match(db, /standby \? \{ connectionString: standby \} : null/);
  assert.match(db, /DATABASE_URL_FALLBACK/);
});

test("no writer reaches the standby: the nightly lanes never import the failover pool", () => {
  // Two databases both being written to is split-brain and nothing here resolves it. The lanes
  // connect with `DATABASE_URL` directly and must stay that way.
  const root = new URL("../", import.meta.url);
  for (const dir of ["jobs", "tools"]) {
    for (const name of readdirSync(new URL(`${dir}/`, root))) {
      if (!/\.(py|mjs|ts)$/.test(name)) continue;
      const text = readFileSync(new URL(`${dir}/${name}`, root), "utf8");
      assert.ok(!/failover|DATABASE_URL_FALLBACK/i.test(text.replace(/mirror/gi, "")) || name === "mirror.py",
        `${dir}/${name} references the failover`);
    }
  }
});

test("only a connection-time failure switches: the pool overrides connect and nothing else", () => {
  const src = readFileSync(new URL("../lib/failover.ts", import.meta.url), "utf8");
  const code = src.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
  assert.equal((code.match(/\bconnect\(/g) ?? []).length >= 3, true);
  // No query, transaction or write method is overridden.
  for (const forbidden of ["query(", "BEGIN", "COMMIT", "INSERT", "UPDATE", "DELETE"]) {
    assert.ok(!code.includes(forbidden), `lib/failover.ts touches ${forbidden}`);
  }
});
