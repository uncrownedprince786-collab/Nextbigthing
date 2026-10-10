// The quality gate (lib/quality.ts): which calls the signal lists publish, and why the rest are withheld.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { isPublished, MIN_REWARD_RISK, MIN_STOP_ATR, qualityGate } from "../lib/quality.ts";
import type { Decision } from "../lib/decision.ts";

type Call = Pick<Decision, "action" | "entry" | "invalidation" | "legs">;

const LONG: Call = { action: "LONG", entry: { low: 102.5, high: 106.19 }, invalidation: 100.5, legs: ["volume"] };
const TARGET = { method: "structure", low: 112, high: 114, distancePct: null, rewardRisk: 1.6 };

test("a complete, measured call with reward:risk of at least 1.5 and a confirmation is published", () => {
  assert.equal(MIN_REWARD_RISK, 1.5);
  assert.equal(MIN_STOP_ATR, 1);
  assert.deepEqual(qualityGate(LONG, TARGET, 2), { published: true, reasons: [] });
  const short: Call = { action: "SHORT", entry: { low: 50, high: 52 }, invalidation: 53, legs: ["peers"] };
  assert.equal(qualityGate(short, { ...TARGET, low: 40, high: 41, rewardRisk: 2.5 }, 1).published, true);
});

test("every missing or weak part withholds the call, and each is named", () => {
  const why = (call: Call, target: typeof TARGET | null, atr: number | null) => qualityGate(call, target, atr).reasons;
  // APL's case: no measured target.
  assert.deepEqual(why(LONG, null, 2), ["no measured target"]);
  // PRL and NRL's case: a measured target, but reward:risk under the floor.
  assert.deepEqual(why(LONG, { ...TARGET, rewardRisk: 0.8 }, 2), ["reward:risk 0.8, under 1.5"]);
  // No confirmation.
  assert.deepEqual(why({ ...LONG, legs: [] }, TARGET, 2), ["no confirmation"]);
  // ATRL's case: the stop on the zone's edge.
  assert.deepEqual(why({ ...LONG, invalidation: 102.5 }, TARGET, 2), ["stop within 1 x ATR of the entry zone"]);
  // No ATR to set the stop by.
  assert.deepEqual(why(LONG, TARGET, null), ["no average true range stored to set the stop by"]);
  // Several at once are all named.
  assert.equal(why({ ...LONG, legs: [] }, null, 2).length, 2);
  // A WAIT is not a call.
  assert.deepEqual(qualityGate({ ...LONG, action: "WAIT" as never }, TARGET, 2), { published: false, reasons: ["no direction"] });
});

test("a hand-built row with no gate is published, and every list reads the gate", () => {
  assert.equal(isPublished({}), true);
  assert.equal(isPublished({ gate: { published: false, reasons: ["x"] } }), false);
  const read = (p: string) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
  for (const f of ["components/classIndex.tsx", "app/page.tsx"]) {
    const src = read(f);
    assert.match(src, /action === "LONG" && isPublished\(s\)/, f);
    assert.match(src, /action === "SHORT" && isPublished\(s\)/, f);
    assert.match(src, /<WithheldList rows=\{withheld\.map/, f);
  }
  assert.match(read("lib/weeklyFocus.ts"), /s\.gate \? s\.gate\.published : true/);
  assert.match(read("components/topByClass.tsx"), /s\.gate \? s\.gate\.published : true/);
  assert.match(read("lib/assetClass.ts"), /gate: qualityGate\(decision, target, input\.atr \?\? null\)/);
  assert.match(read("app/asset/[symbol]/page.tsx"), /withheld=\{gate\.published \? null : gate\.reasons\}/);
});
