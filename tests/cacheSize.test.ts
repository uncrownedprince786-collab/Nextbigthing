// The site-wide decision cache only works while its entry is under Next's 2 MB limit; over it,
// `unstable_cache` stores nothing, says so only in a server log, and every list page queries itself.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("the list read leaves out the target prose that pushed the shared cache over 2 MB", () => {
  const q = readFileSync(new URL("../lib/queries.ts", import.meta.url), "utf8");
  const body = q.slice(q.indexOf("export async function getDecisionRows("), q.indexOf("// Every asset gets a row"));
  assert.ok(body.length > 0);
  const targets = body.slice(body.indexOf("targets: {"), body.indexOf("},", body.indexOf("select: {", body.indexOf("targets: {"))));
  assert.match(targets, /rewardRisk: true/);
  assert.doesNotMatch(targets, /note: true/, "the note is the asset page's, read by getHorizons");
  assert.match(readFileSync(new URL("../lib/cached.ts", import.meta.url), "utf8"), /unstable_cache\(getDecisionRows/);
});
