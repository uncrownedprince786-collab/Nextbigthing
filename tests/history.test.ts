// Append-only decision history (brain.md rule 95). A second decision pass on a day used to overwrite the
// first: 2026-10-10 carries the computedAt of eight passes, and 55 LONG and 12 SHORT calls made at 20:15
// survive nowhere after the 23:14 pass turned them into WAIT. Every run is now recorded once, with its
// calls; these tests pin the recording (against a fake client), the identity of a run, and how the
// logbook marks the current run and prints the trade summary.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { expectancyText, markCurrent, rateText, toTradeSummary, type RunRow } from "../lib/history.ts";
import { CALL_COLUMNS, finishRun, inputFingerprint, newestSessions, recordRun, runIdentity } from "../tools/decide.mjs";

type Query = { sql: string; params: unknown[] };

/// A client that records every statement and answers the run lookup with `status` (or no row).
function fakeClient(status: string | null) {
  const queries: Query[] = [];
  return {
    queries,
    async query(sql: string, params: unknown[] = []) {
      queries.push({ sql, params });
      if (/SELECT status FROM "DecisionRun"/.test(sql)) return { rows: status ? [{ status }] : [], rowCount: status ? 1 : 0 };
      if (/INSERT INTO "DecisionCall"/.test(sql)) return { rows: [], rowCount: (params.length / CALL_COLUMNS.length) | 0 };
      return { rows: [], rowCount: 0 };
    },
  };
}

const decision = (symbol: string, action = "LONG", published = true) => ({
  assetId: `id-${symbol}`, symbol, market: "US", action, gate: "confirmed", confidence: "High",
  entryLow: 98, entryHigh: 100, invalidation: 95, target: 110, rewardRisk: 2, baseClose: 101,
  baseSession: "2026-10-09", atr14: 2, published, gateReasons: published ? null : "no measured exit",
  execution: "checked", horizon: "swing", validFrom: "2026-10-09", validUntil: "2026-10-16", legs: "volume", intent: null,
});

const RUN = { id: "gh-1-1-decide", pass: "decide", commit: "abc", trigger: "schedule", servedFrom: "primary", fingerprint: "f", sessions: {}, sourceHealth: [] };

test("a new run is opened, its calls inserted once, and nothing is ever updated or removed", async () => {
  const c = fakeClient(null);
  const got = await recordRun(c, RUN, [decision("AAPL"), decision("MSFT", "SHORT", false)], "2026-10-11");
  assert.equal(got.replay, false);
  assert.equal(got.written, 2);
  const sql = c.queries.map((q) => q.sql).join("\n");
  assert.match(sql, /INSERT INTO "DecisionRun"[\s\S]*'running'/);
  assert.match(sql, /INSERT INTO "DecisionCall"[\s\S]*ON CONFLICT \("runId", "assetId"\) DO NOTHING/);
  // The only UPDATE closes runs abandoned six hours ago; no call is updated and nothing is deleted.
  assert.doesNotMatch(sql, /UPDATE "DecisionCall"|DELETE/);
  const updates = c.queries.filter((q) => /^\s*UPDATE/.test(q.sql));
  assert.equal(updates.length, 1);
  assert.match(updates[0].sql, /status = 'running' AND "startedAt" < now\(\) - interval '6 hours'/);
  // Each call row carries the run, the session it was read from, its plan, its gate and its execution.
  const insert = c.queries.find((q) => /INSERT INTO "DecisionCall"/.test(q.sql))!;
  const first = Object.fromEntries(CALL_COLUMNS.map((col, i) => [col, insert.params[i]]));
  assert.equal(first.runId, RUN.id);
  assert.equal(first.baseSession, "2026-10-09");
  assert.equal(first.stop, 95);
  assert.equal(first.target, 110);
  assert.equal(first.published, true);
  assert.equal(first.execution, "checked");
  assert.equal(first.validUntil, "2026-10-16");
});

test("an idempotent replay of a finished run writes nothing", async () => {
  for (const status of ["complete", "partial", "failed"]) {
    const c = fakeClient(status);
    const got = await recordRun(c, RUN, [decision("AAPL")], "2026-10-11");
    assert.deepEqual(got, { replay: true, written: 0, failures: [] }, status);
    assert.equal(c.queries.length, 1, status);
  }
  // A run that is still open (a retried step of the same attempt) adds only what is missing.
  const open = fakeClient("running");
  await recordRun(open, RUN, [decision("AAPL")], "2026-10-11");
  assert.ok(!open.queries.some((q) => /INSERT INTO "DecisionRun"/.test(q.sql)));
  assert.ok(open.queries.some((q) => /ON CONFLICT \("runId", "assetId"\) DO NOTHING/.test(q.sql)));
});

test("a run is closed exactly once", async () => {
  const c = fakeClient(null);
  await finishRun(c, RUN.id, { status: "partial", written: 1, published: 1, note: "one batch failed" });
  assert.match(c.queries[0].sql, /WHERE id = \$1 AND status = 'running'/);
  assert.deepEqual(c.queries[0].params, [RUN.id, "partial", 1, 1, "one batch failed"]);
});

test("a re-run is a new run; the same attempt and pass is the same run", () => {
  const a = runIdentity({ GITHUB_RUN_ID: "38101299192", GITHUB_RUN_ATTEMPT: "1", GITHUB_SHA: "bc7316d", GITHUB_EVENT_NAME: "schedule" }, "decide");
  const b = runIdentity({ GITHUB_RUN_ID: "38101299192", GITHUB_RUN_ATTEMPT: "2", GITHUB_SHA: "bc7316d" }, "decide");
  const m = runIdentity({ GITHUB_RUN_ID: "38101299192", GITHUB_RUN_ATTEMPT: "1", GITHUB_SHA: "bc7316d" }, "macro");
  assert.equal(a.id, "gh-38101299192-1-decide");
  assert.notEqual(a.id, b.id);
  assert.notEqual(a.id, m.id);
  assert.equal(a.id, runIdentity({ GITHUB_RUN_ID: "38101299192", GITHUB_RUN_ATTEMPT: "1", GITHUB_SHA: "x" }, "decide").id);
  assert.equal(a.commit, "bc7316d");
  assert.equal(a.trigger, "schedule");
  const local = runIdentity({}, "decide", new Date("2026-10-11T12:00:00Z"));
  assert.equal(local.id, "local-2026-10-11T12:00:00.000Z-decide");
});

test("the fingerprint is the inputs: the same data gives the same one, any change a different one", () => {
  const input = (close: number) => ({
    assets: [{ id: "a", symbol: "AAPL", assetType: "stock", market: "US" }],
    priceByAsset: new Map([["a", { assetId: "a", date: "2026-10-09", close, volume: 10 }]]),
    setupByKey: new Map(), targetsBySetup: new Map(), analogByAsset: new Map(), signalByAsset: new Map(),
    newsReadOn: null, investigationByAsset: new Map(), factorByAsset: new Map(), eventByAsset: new Map(),
    macroByAsset: new Map(), priorByAsset: new Map(), lastRunByAsset: new Map(), sourceHealth: [],
  });
  assert.equal(inputFingerprint(input(100)), inputFingerprint(input(100)));
  assert.notEqual(inputFingerprint(input(100)), inputFingerprint(input(100.01)));
  assert.match(inputFingerprint(input(100)), /^[0-9a-f]{64}$/);
  assert.deepEqual(newestSessions([decision("A"), { ...decision("B"), market: "PSX", baseSession: "2026-10-10" }]), { US: "2026-10-09", PSX: "2026-10-10" });
});

test("the job records the run before the day's current row, and the macro pass is its own run", () => {
  const src = readFileSync(new URL("../tools/decide.mjs", import.meta.url), "utf8");
  assert.ok(src.indexOf("recorded = await recordRun(") > 0);
  assert.ok(src.indexOf("recorded = await recordRun(") < src.indexOf("const result = await writeDecisions(client, decisions, today, extra)"));
  const wf = readFileSync(new URL("../.github/workflows/cron-decision.yml", import.meta.url), "utf8");
  assert.match(wf, /node tools\/decide\.mjs --pass=macro/);
  assert.match(wf, /python tools\/trade_sim\.py --write/);
});

const run = (over: Partial<RunRow>): RunRow => ({
  id: "r", periodEnd: "2026-10-11", pass: "decide", status: "complete", startedAt: "2026-10-11T22:10:00.000Z",
  finishedAt: null, commit: null, trigger: null, servedFrom: "primary", fingerprint: null, assets: 553, written: 553, published: 18,
  ...over,
});

test("the current run of a day is the newest one that finished", () => {
  const marked = markCurrent([
    run({ id: "a", startedAt: "2026-10-11T00:30:00.000Z" }),
    run({ id: "b", startedAt: "2026-10-11T01:24:00.000Z" }),
    run({ id: "c", startedAt: "2026-10-11T02:00:00.000Z", status: "failed" }),
    run({ id: "d", startedAt: "2026-10-11T03:00:00.000Z", status: "running" }),
    run({ id: "e", periodEnd: "2026-10-10", startedAt: "2026-10-10T23:14:00.000Z", status: "partial" }),
  ]);
  assert.deepEqual(marked.filter((r) => r.current).map((r) => r.id).sort(), ["b", "e"]);
});

test("the trade summary is read only in the shape the grader writes, and every rate prints its count", () => {
  assert.equal(toTradeSummary(null), null);
  assert.equal(toTradeSummary({ asOf: "2026-10-11" }), null);
  const bucket = {
    calls: 1, evaluable: 1, pending: 0, trades: { NOT_FILLED: 1 },
    fillRate: { k: 0, n: 1, rate: 0 }, targetFirst: { k: 0, n: 0, rate: null }, stopFirst: { k: 0, n: 0, rate: null },
    expired: { k: 0, n: 0, rate: null }, ambiguous: { k: 0, n: 0, rate: null }, gapThrough: 0,
    grossRExpectancy: { n: 0, mean: null, measured: false },
    direction: { judged: 1, right: 1, wrong: 0, stopped: 0, flat: 0, pending: 0, accurate: { k: 1, n: 1, rate: 1 } },
  };
  const s = toTradeSummary({ asOf: "2026-10-11", since: "2026-10-11", minSample: 30, all: bucket, byMarket: { US: bucket }, bySide: {}, byHorizon: {}, byConfidence: {}, assumptions: ["R is gross"] });
  assert.ok(s);
  assert.equal(rateText(s!.all.fillRate), "0% (0 of 1)");
  assert.equal(rateText(s!.all.targetFirst), "— (0)");
  assert.equal(expectancyText(s!.all.grossRExpectancy, 30), "not measured (0 closed trades)");
  assert.equal(expectancyText({ n: 4, mean: 0.5, measured: false }, 30), "+0.50R over 4: not measured, 30 closed trades are needed");
});

test("the logbook prints direction and trade apart, and the run history with the current run marked", () => {
  const page = readFileSync(new URL("../app/logbook/page.tsx", import.meta.url), "utf8");
  assert.match(page, /<Trades t=\{trades\} \/>/);
  assert.match(page, /<Runs runs=\{runs\} \/>/);
  assert.match(page, /data-current=\{r\.current \? "true" : "false"\}/);
  assert.match(page, /No\s+rate here is a win probability or an edge/);
});
