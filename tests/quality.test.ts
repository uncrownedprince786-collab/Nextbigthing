// The quality gate (lib/quality.ts): which calls the signal lists publish, and why the rest are withheld.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { isPublished, MIN_REWARD_RISK, MIN_STOP_ATR, openSince, qualityGate, withOpenPosition } from "../lib/quality.ts";
import type { Decision } from "../lib/decision.ts";

type Call = Pick<Decision, "action" | "entry" | "invalidation" | "legs">;

const LONG: Call = { action: "LONG", entry: { low: 102.5, high: 106.19 }, invalidation: 100.5, legs: ["volume"] };
const TARGET = { method: "structure", low: 112, high: 114, distancePct: null, rewardRisk: 1.6 };

test("a complete, measured call with reward:risk of at least 1.2 and a confirmation is published", () => {
  assert.equal(MIN_REWARD_RISK, 1.2);
  assert.equal(MIN_STOP_ATR, 1);
  assert.deepEqual(qualityGate(LONG, TARGET, 2), { published: true, reasons: [] });
  const short: Call = { action: "SHORT", entry: { low: 50, high: 52 }, invalidation: 53, legs: ["peers"] };
  assert.equal(qualityGate(short, { ...TARGET, low: 40, high: 41, rewardRisk: 2.5 }, 1).published, true);
});

test("every missing or weak part withholds the call, and each is named", () => {
  const why = (call: Call, target: typeof TARGET | null, atr: number | null) => qualityGate(call, target, atr).reasons;
  // APL's case: no measured exit.
  assert.deepEqual(why(LONG, null, 2), ["no measured exit"]);
  // PRL and NRL's case: a measured target, but reward:risk under the floor.
  assert.deepEqual(why(LONG, { ...TARGET, rewardRisk: 0.8 }, 2), ["reward:risk 0.80, under 1.2"]);
  assert.deepEqual(why(LONG, { ...TARGET, rewardRisk: 1.19 }, 2), ["reward:risk 1.19, under 1.2"]);
  // No confirmation.
  assert.deepEqual(why({ ...LONG, legs: [] }, TARGET, 2), ["no confirmation"]);
  // ATRL's case: the stop on the zone's edge.
  assert.deepEqual(why({ ...LONG, invalidation: 102.5 }, TARGET, 2), ["stop within 1 x ATR of the entry zone"]);
  // Exactly 1 ATR away after rounding to eight significant digits passes (ATRL-sized price, small ATR).
  assert.deepEqual(why({ ...LONG, entry: { low: 1165, high: 1210 }, invalidation: Number((1165 - 3.3333333).toPrecision(8)) }, { ...TARGET, low: 1300, high: 1310 }, 3.3333333), []);
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
  // The coming-week block lists new ideas: a call held open past its entry rules is not one.
  assert.match(read("lib/weeklyFocus.ts"), /s\.gate \? s\.gate\.published && !s\.gate\.held : true/);
  assert.match(read("components/topByClass.tsx"), /s\.gate \? s\.gate\.published : true/);
  assert.match(read("lib/assetClass.ts"), /gate: withOpenPosition\(qualityGate\(decision, target, input\.atr \?\? null, style\), since\)/);
  assert.match(read("app/asset/[symbol]/page.tsx"), /withheld=\{gate\.published \? null : gate\.reasons\}/);
});

test("a published call needs a trading style: SWING or POSITION, never an invented SCALPING or INTRADAY", () => {
  const T = { method: "structure", low: 112, high: 114, distancePct: null, rewardRisk: 1.6 };
  assert.equal(qualityGate(LONG, T, 2, "SWING").published, true);
  assert.equal(qualityGate(LONG, T, 2, "POSITION").published, true);
  assert.deepEqual(qualityGate(LONG, T, 2, null).reasons, ["no trading style"]);
  const api = readFileSync(new URL("../app/api/signals/route.ts", import.meta.url), "utf8");
  assert.match(api, /SCALPING: "not produced", INTRADAY: "not produced"/);
  assert.match(api, /scoreRows\(rows, health, today\)/, "the API scores rows by the function the pages use");
  assert.match(api, /cachedDecisionRows\(\)/, "from the pages' own cached list");
});

test("an open published call is held to its stop, not dropped, and a call cannot keep itself open", () => {
  const open = { action: "LONG", publishedAction: "LONG", publishedOn: "2026-10-12", lastRunAction: "LONG", lastRunSince: "2026-10-12", validityStatus: "Active" };
  assert.equal(openSince(open), "2026-10-12");
  // A different direction since (the stop was crossed and the call turned), an older run, an expired
  // window, or nothing published: not open.
  assert.equal(openSince({ ...open, action: "SHORT" }), null);
  assert.equal(openSince({ ...open, lastRunAction: "SHORT" }), null);
  assert.equal(openSince({ ...open, publishedOn: "2026-10-09", lastRunSince: "2026-10-12" }), null);
  assert.equal(openSince({ ...open, validityStatus: "Expired" }), null);
  assert.equal(openSince({ ...open, publishedOn: null }), null);
  // Drifted under the floor or lost its confirmation: still listed, marked open, with today's shortfall.
  const drift = withOpenPosition({ published: false, reasons: ["reward:risk 1.05, under 1.2", "no confirmation"] }, "2026-10-12");
  assert.deepEqual(drift, { published: true, reasons: [], held: { since: "2026-10-12", todays: ["reward:risk 1.05, under 1.2", "no confirmation"] } });
  // Can no longer be acted on as printed: withheld, saying it had been published -- never silently gone.
  assert.deepEqual(withOpenPosition({ published: false, reasons: ["no measured exit"] }, "2026-10-12"), {
    published: false,
    reasons: ["published 2026-10-12, now no measured exit"],
  });
  // Not open, or already published: unchanged.
  assert.deepEqual(withOpenPosition({ published: false, reasons: ["no confirmation"] }, null), { published: false, reasons: ["no confirmation"] });
  assert.deepEqual(withOpenPosition({ published: true, reasons: [] }, "2026-10-12"), { published: true, reasons: [] });
});

test("the log records the reward:risk the reader saw, and reads publication back at the gate's own floor", () => {
  const read = (p: string) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
  assert.match(read("tools/decide.mjs"), /rewardRisk: shown\?\.rewardRisk \?\? null/);
  const q = read("lib/queries.ts");
  assert.ok(q.includes(`"rewardRisk" >= ${MIN_REWARD_RISK}`), "getPublishedRuns reads the gate's floor");
  assert.match(q, /"periodEnd" < CURRENT_DATE AND "periodEnd" >= DATE '2026-10-10'/, "before today, and never before the gate existed");
});
