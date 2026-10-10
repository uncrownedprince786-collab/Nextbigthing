// The rising-star marker: only the two measured entry events fire it, it says how it sits with the
// call, and it never reads as an instruction.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { earlySignalOf } from "../lib/earlySignal.ts";

test("the two measured entry events fire it, either way", () => {
  const up = earlySignalOf("squeeze_break", "up", "LONG")!;
  assert.deepEqual([up.rule, up.direction, up.label, up.stance], ["squeeze_break", "up", "Rising star", "with"]);
  const down = earlySignalOf("vol_flip", "down", "SHORT")!;
  assert.deepEqual([down.label, down.stance], ["Falling star", "with"]);
});

test("nothing else fires it: no event, an unknown rule, or a direction that is not one", () => {
  assert.equal(earlySignalOf(null, null, "LONG"), null);
  assert.equal(earlySignalOf("squeeze_break", null, "LONG"), null);
  for (const rule of ["rsi_divergence", "macd_divergence", "inflection", "news_spike", ""]) {
    assert.equal(earlySignalOf(rule, "up", "LONG"), null, rule);
  }
  for (const dir of ["UP", "flat", "sideways", ""]) assert.equal(earlySignalOf("vol_flip", dir, "LONG"), null, dir);
});

test("it says how it sits with the call: with it, against it, or held back by the rule table", () => {
  assert.equal(earlySignalOf("squeeze_break", "up", "SHORT")!.stance, "against");
  assert.equal(earlySignalOf("squeeze_break", "down", "LONG")!.stance, "against");
  const held = earlySignalOf("vol_flip", "up", "WAIT")!;
  assert.equal(held.stance, "held");
  assert.match(held.explain, /still holds this name back/);
});

test("it describes an event and never tells anyone to act", () => {
  for (const [rule, dir, action] of [["squeeze_break", "up", "LONG"], ["vol_flip", "down", "WAIT"], ["vol_flip", "up", "SHORT"]] as const) {
    const s = earlySignalOf(rule, dir, action)!;
    assert.match(s.explain, /A marker, not an instruction\./);
    assert.ok(!/asap|enter now|buy now|sell now|guarantee/i.test(s.explain), s.explain);
  }
});

test("the list and the asset page show it from the same function, beside the action", () => {
  const read = (p: string) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
  assert.ok(read("lib/assetClass.ts").includes("early: earlySignalOf("));
  assert.ok(read("app/asset/[symbol]/page.tsx").includes("earlySignalOf("));
  const decision = read("components/decision.tsx");
  const rows = decision.slice(decision.indexOf("function DecisionRows("));
  const panel = decision.slice(decision.indexOf("export function DecisionPanel("), decision.indexOf("export function ProductDecisionPanel("));
  assert.ok(rows.includes("<EarlySignalBadge"), "row has the badge");
  assert.ok(panel.includes("<EarlySignalBadge"), "panel has the badge");
  assert.ok(panel.includes('label="Early signal"'), "panel has the metrics field");
});
