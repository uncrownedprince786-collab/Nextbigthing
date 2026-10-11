// One run state per market, shared by the overview and the market page (brain.md rule 95). Live on
// 2026-10-11 the overview card said commodities had "not been through a run" -- it printed that whenever a
// market had no published call -- while /commodities reported the run of that day complete with 1 withheld,
// 5 forming and 2 held back. These tests pin the four states and that the card speaks from the same record.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { marketStatus, marketStatusLines, runStateOf } from "../lib/marketStatus.ts";
import type { Scored } from "../lib/assetClass.ts";

type Spec = { action: "LONG" | "SHORT" | "WAIT"; published?: boolean; developing?: boolean; gate?: string; day?: string | null };
const row = (s: Spec): Scored =>
  ({
    row: { callLatest: s.day === undefined ? "2026-10-11" : s.day, closeDate: "2026-10-09", market: "Commodity" },
    market: "Commodity",
    decision: { action: s.action, developing: s.developing ? {} : null, gate: s.gate ?? "none" },
    gate: s.action === "WAIT" ? null : { published: s.published ?? true },
  }) as unknown as Scored;

// The live commodities market: 8 names, all logged on 2026-10-11, none published.
const COMMODITIES = [
  row({ action: "LONG", published: false }),
  ...Array.from({ length: 5 }, () => row({ action: "WAIT", developing: true })),
  row({ action: "WAIT" }),
  row({ action: "WAIT" }),
];

test("a completed run with no published call is RUN_COMPLETE_NO_PUBLISHED_CALLS, never 'not run'", () => {
  const s = marketStatus(COMMODITIES, COMMODITIES, [], null);
  assert.equal(s.runState, "RUN_COMPLETE_NO_PUBLISHED_CALLS");
  assert.equal(s.logged, 8);
  assert.equal(s.withheld, 1);
  assert.equal(s.forming, 5);
  const text = marketStatusLines(s).join(" ");
  assert.match(text, /Decision run of 2026-10-11 completed for this market\./);
  assert.match(text, /No call passed the quality gate today\./);
  assert.doesNotMatch(text, /not been through a run|No stored reading/);
});

test("the four states", () => {
  assert.equal(runStateOf({ names: 0, decidedOn: null, processed: false, logged: 0, published: 0 }), "NO_READING");
  assert.equal(runStateOf({ names: 8, decidedOn: null, processed: false, logged: 0, published: 0 }), "NO_READING");
  assert.equal(runStateOf({ names: 8, decidedOn: "2026-10-10", processed: false, logged: 8, published: 2 }), "RUN_INCOMPLETE_OR_FAILED");
  assert.equal(runStateOf({ names: 8, decidedOn: "2026-10-11", processed: true, logged: 5, published: 2 }), "RUN_INCOMPLETE_OR_FAILED");
  assert.equal(runStateOf({ names: 8, decidedOn: "2026-10-11", processed: true, logged: 8, published: 2 }), "RUN_COMPLETE_WITH_CALLS");
  assert.equal(runStateOf({ names: 8, decidedOn: "2026-10-11", processed: true, logged: 8, published: 0 }), "RUN_COMPLETE_NO_PUBLISHED_CALLS");
});

test("a market missing from the newest run, or only partly logged, says so", () => {
  const behind = COMMODITIES.map((s) => ({ ...s, row: { ...s.row, callLatest: "2026-10-10" } }) as unknown as Scored);
  const other = [row({ action: "LONG", day: "2026-10-11" })];
  const s = marketStatus(behind, [...behind, ...other], [], null);
  assert.equal(s.runState, "RUN_INCOMPLETE_OR_FAILED");
  assert.match(marketStatusLines(s).join(" "), /Not processed in the latest run \(2026-10-11\)/);
  const partial = [...COMMODITIES.slice(0, 6), row({ action: "WAIT", day: "2026-10-10" }), row({ action: "WAIT", day: "2026-10-10" })];
  const p = marketStatus(partial, partial, [], null);
  assert.equal(p.runState, "RUN_INCOMPLETE_OR_FAILED");
  assert.match(marketStatusLines(p).join(" "), /reached 6 of these 8 names/);
});

test("a published call makes the run RUN_COMPLETE_WITH_CALLS", () => {
  const rows = [row({ action: "SHORT", published: true }), ...COMMODITIES.slice(1)];
  assert.equal(marketStatus(rows, rows, [], null).runState, "RUN_COMPLETE_WITH_CALLS");
});

test("the overview card and the market page print the run state from the same record", () => {
  const card = readFileSync(new URL("../components/topByClass.tsx", import.meta.url), "utf8");
  const page = readFileSync(new URL("../components/classIndex.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(card, /not been through a run|No stored reading yet/);
  assert.match(card, /marketStatus\(mine, rows, health/);
  assert.match(card, /data-run-state=\{status\.runState\}/);
  assert.match(card, /marketStatusLines\(status\)\.slice\(1\)/);
  assert.match(page, /data-run-state=\{status\.runState\}/);
  for (const src of [card, page]) assert.match(src, /data-names=\{status\.names\}/);
});
