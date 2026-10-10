// The Node writers' failover (tools/writer.mjs): the same rule as jobs/nbt.py `db`, so every writer in a
// lane moves to the standby together when the primary cannot be reached, and never on a bad password.

import { test } from "node:test";
import assert from "node:assert/strict";
import { databaseKey, standbyFor, writerPool } from "../tools/writer.mjs";

const NEON = "postgresql://u:p@ep-a-pooler.c-6.aws.neon.tech/neondb?sslmode=require";
const SUPA = "postgresql://postgres.projA:p@aws-0-ap.pooler.supabase.com:5432/postgres";

function fakePool(behaviour: "ok" | Error) {
  return {
    ended: false,
    async query() {
      if (behaviour !== "ok") throw behaviour;
      return { rows: [{ "?column?": 1 }] };
    },
    async end() {
      this.ended = true;
    },
  };
}

test("the standby is never the primary, and WRITE_FAILOVER=off switches it off", () => {
  assert.deepEqual(standbyFor(NEON, { SUPABASE_DATABASE_URL: SUPA }), { name: "SUPABASE_DATABASE_URL", url: SUPA });
  assert.equal(standbyFor(SUPA, { SUPABASE_DATABASE_URL: SUPA }), null);
  assert.equal(standbyFor(NEON, { SUPABASE_DATABASE_URL: SUPA, WRITE_FAILOVER: "off" }), null);
  assert.notEqual(databaseKey(SUPA), databaseKey(SUPA.replace("projA", "projB")), "two Supabase projects on one pooler");
  assert.equal(databaseKey(NEON), databaseKey(NEON.replace("-pooler", "")), "the pooler and the direct host are one database");
});

test("a quota pause on the primary moves the writer to the standby, and says so", async () => {
  const logs: string[] = [];
  const quota = Object.assign(new Error("Your account or project has exceeded the quota"), { code: "53000" });
  const made: string[] = [];
  const { target } = await writerPool(2, {
    env: { DATABASE_URL: NEON, SUPABASE_DATABASE_URL: SUPA },
    log: (m: string) => logs.push(m),
    make: (url: string) => {
      made.push(url);
      return fakePool(url.includes("neon") ? quota : "ok") as never;
    },
  });
  assert.equal(target, "SUPABASE_DATABASE_URL");
  assert.equal(made.length, 2);
  assert.match(logs[0], /::warning title=Writing to the standby::/);
  assert.doesNotMatch(logs[0], /postgres(ql)?:\/\//, "no connection string in the log");
});

test("a healthy primary is used, a bad password is raised, and both down raises the primary's error", async () => {
  const env = { DATABASE_URL: NEON, SUPABASE_DATABASE_URL: SUPA };
  assert.equal((await writerPool(2, { env, make: () => fakePool("ok") as never })).target, "primary");
  const auth = Object.assign(new Error('password authentication failed for user "u"'), { code: "28P01" });
  await assert.rejects(writerPool(2, { env, make: (url: string) => fakePool(url.includes("neon") ? auth : "ok") as never }), /password/);
  const refused = Object.assign(new Error("connect ECONNREFUSED"), { code: "ECONNREFUSED" });
  const full = Object.assign(new Error("max clients reached"), { code: "XX000" });
  await assert.rejects(
    writerPool(2, { env, log: () => {}, make: (url: string) => fakePool(url.includes("neon") ? refused : full) as never }),
    /ECONNREFUSED/,
  );
});
