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

test("the list keeps only the trend and bias of a setup's conditions, and reads them the same", async () => {
  const { listConditions, trendDirectionOf, biasDirectionOf } = await import("../lib/setupConditions.ts");
  const full =
    "trend: close 42.20 vs 20d 43.72 vs 50d 47.44 (down) | volume: 1.15x its 20d average (fail) | " +
    "relative: -11.1 points against its industry over 20 days (fail) | bias: 50d under 200d (down) | " +
    "news: tone neutral, catalyst no, 0 recent stories | calendar: Alcoa: scheduled earnings report in 5 days";
  const short = listConditions(full);
  assert.equal(short, "trend: close 42.20 vs 20d 43.72 vs 50d 47.44 (down) | bias: 50d under 200d (down)");
  assert.equal(trendDirectionOf(short), trendDirectionOf(full));
  assert.equal(biasDirectionOf(short), biasDirectionOf(full));
  assert.equal(listConditions(""), "");
  const q = readFileSync(new URL("../lib/queries.ts", import.meta.url), "utf8");
  assert.match(q, /conditions: listConditions\(row\.conditions\)/);
});

test("columns the standbys may not have are read raw and fail-open, never through the Prisma model", () => {
  // 2026-10-10: a failover to a standby without AssetFactor.atr14 made every uncached asset page a 500,
  // because Prisma selects every model column by default.
  const schema = readFileSync(new URL("../prisma/schema.prisma", import.meta.url), "utf8");
  const model = (name: string) => schema.slice(schema.indexOf(`model ${name} {`), schema.indexOf("\n}", schema.indexOf(`model ${name} {`)));
  assert.doesNotMatch(model("AssetFactor"), /^\s+atr14\s+Float/m);
  // `atrTrailingMedian` is the second column on this table kept out of the model, for the same
  // reason and added the same way (migration 20261016140000_atr_trailing_median).
  assert.doesNotMatch(model("AssetFactor"), /^\s+atrTrailingMedian\s+Float/m);
  assert.doesNotMatch(model("Asset"), /^\s+(active|poolNote)\s+/m);
  const q = readFileSync(new URL("../lib/queries.ts", import.meta.url), "utf8");
  // To this function's own return statement, not to the next `export`: the span between them holds
  // another raw query, which would make the count below measure two functions instead of one.
  const late = q.slice(q.indexOf("export async function getLateColumns("),
                       q.indexOf("return { atr, atrBaseline, inactive };"));
  assert.ok(late.length > 500, "getLateColumns was not found; this test is measuring nothing");
  // Three late reads now, and each fails open **on its own**. Selecting two late columns in one
  // query would hand them a shared failure: a standby missing only the newer one would also lose
  // `atr14`, and with it the resolver's stop distance -- a wider blast radius than the incident
  // above, reached while fixing something unrelated.
  assert.equal((late.match(/\.catch\(\(\) => undefined\)/g) ?? []).length, 3, "every late read fails open");
  assert.equal((late.match(/\$queryRaw/g) ?? []).length, 3, "the late columns share a query");
  assert.doesNotMatch(q, /atr14: true|active: true/);
});
