// Every priced name resolves to LONG or SHORT (brain.md rule 86). The evidence table is unchanged; this
// pins the layer after it: which side each refusal becomes, where the stop comes from, and that every
// caller goes through the one function.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { decide, type Decision, type DecisionInput } from "../lib/decision.ts";
import { ATR_STOP_MULTIPLE, bufferStop, decideCall, momentumSide, resolveCall, STOP_BUFFER_ATR, whipsawHold, WHIPSAW_DAYS } from "../lib/resolve.ts";

function input(over: Partial<DecisionInput> = {}): DecisionInput {
  return {
    symbol: "AAPL",
    market: "US",
    asOf: "2026-10-09",
    today: "2026-10-10",
    lastClose: 100,
    setup: { direction: "up", horizon: "swing" },
    horizon: { direction: "up" },
    entry: { low: 98, high: 102 },
    invalidation: 94,
    analogs: null,
    volumeRatio: null,
    relStrength: null,
    unusualMove: false,
    newsCount: 0,
    eventInDays: null,
    sourceSilent: null,
    atr: 2.5,
    ...over,
  };
}

function wait(gate: string, intent: "up" | "down" | null = null): Decision {
  return {
    action: "WAIT", why: ["held"], entry: null, invalidation: null, timeSense: "WAIT FOR LEVEL",
    confidence: "Low", missing: [], notes: [], measured: "", gate, basis: "evidence", plan: null,
    legs: [], intent, developing: null,
  };
}

test("a close through a long's stop becomes SHORT, stopped 2 x ATR above the close", () => {
  const d = resolveCall(wait("stop-crossed", "up"), input({ lastClose: 90, invalidation: 94 }));
  assert.equal(d.action, "SHORT");
  assert.equal(d.gate, "forced-stop-crossed");
  assert.equal(d.invalidation, 90 + ATR_STOP_MULTIPLE * 2.5);
  assert.deepEqual(d.entry, { low: 90, high: 90 });
  // And a close up through a short's stop becomes LONG.
  const up = resolveCall(
    wait("stop-crossed", "down"),
    input({ setup: { direction: "down", horizon: "swing" }, lastClose: 110, invalidation: 104 }),
  );
  assert.equal(up.action, "LONG");
  assert.equal(up.invalidation, 110 - ATR_STOP_MULTIPLE * 2.5);
});

test("an unconfirmed short is SHORT, keeping its own stop when that stop is above the close", () => {
  const down = { direction: "down" as const, horizon: "swing" };
  const d = resolveCall(wait("short-unbacked", "down"), input({ setup: down, invalidation: 106 }));
  assert.equal(d.action, "SHORT");
  assert.equal(d.invalidation, 106, "the setup's own stop is kept");
  // A stop on the wrong side for the side taken is replaced by the ATR stop.
  assert.equal(resolveCall(wait("short-unbacked", "down"), input({ setup: down, invalidation: 94 })).invalidation, 105);
  // A broken long's stop is never reused for the short, even though it sits above the close.
  assert.equal(resolveCall(wait("stop-crossed", "up"), input({ lastClose: 90, invalidation: 94 })).invalidation, 95);
});

test("an unconfirmed flip keeps the last call: the patient flip", () => {
  const prior = { direction: "down" as const, asOf: "2026-10-09" };
  const d = resolveCall(wait("reversal-unconfirmed", "up"), input({ priorDirection: prior, invalidation: 94 }));
  assert.equal(d.action, "SHORT");
  assert.equal(d.gate, "forced-reversal-unconfirmed");
});

test("a held flip keeps the call the reader holds, not the table's last call", () => {
  // The audit's case: the table said SHORT on the 7th, a close through its stop made a forced LONG on
  // the 8th, and on the 9th the setup turns up without a confirmation. The gate fires against the 7th's
  // SHORT; the call the reader holds is the LONG, and that is what is kept.
  const d = resolveCall(
    wait("reversal-unconfirmed", "up"),
    input({
      today: "2026-10-09",
      priorDirection: { direction: "down", asOf: "2026-10-07" },
      lastRun: { direction: "up", since: "2026-10-08", left: "down" },
    }),
  );
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "forced-reversal-unconfirmed");
});

function call(action: "LONG" | "SHORT", over: Partial<Decision> = {}): Decision {
  return { ...wait("trend"), action, gate: action === "LONG" ? "trend-long" : "trend-short", entry: { low: 98, high: 102 }, invalidation: action === "LONG" ? 94 : 106, ...over };
}

test("no unconfirmed return to the side just left: SHORT, LONG, SHORT inside three days is held", () => {
  const down = { direction: "down" as const, horizon: "swing" };
  const held = whipsawHold(
    call("SHORT"),
    input({ setup: down, invalidation: 106, lastRun: { direction: "up", since: "2026-10-09", left: "down" } }),
  );
  assert.equal(held.action, "LONG");
  assert.equal(held.gate, "forced-whipsaw-hold");
  assert.ok(held.invalidation !== null && held.invalidation < 100, "a held LONG's stop is below the close");
  assert.match(held.why[0], /side it left/);
  // Through the whole path too, not only the guard on its own.
  assert.equal(WHIPSAW_DAYS, 3);
});

test("the guard lets a confirmed return through, and any return once the window has passed", () => {
  const down = { direction: "down" as const, horizon: "swing" };
  const run = { direction: "up" as const, since: "2026-10-09", left: "down" as const };
  // Confirmed: similar past days lean down (the analog leg), so the return is a real turn.
  const confirmed = whipsawHold(
    call("SHORT"),
    input({ setup: down, invalidation: 106, lastRun: run, analogs: { count: 30, lowPct: -9, highPct: 2, medianPct: -3, positive: 8 } }),
  );
  assert.equal(confirmed.action, "SHORT");
  // The current direction began four days ago: outside the window.
  const old = whipsawHold(call("SHORT"), input({ setup: down, invalidation: 106, lastRun: { ...run, since: "2026-10-06" } }));
  assert.equal(old.action, "SHORT");
  // Continuing the current direction, or a run with nothing before it, is never touched.
  assert.equal(whipsawHold(call("LONG"), input({ lastRun: run })).gate, "trend-long");
  assert.equal(whipsawHold(call("SHORT"), input({ setup: down, lastRun: { ...run, left: null } })).action, "SHORT");
  assert.equal(whipsawHold(call("SHORT"), input({ setup: down })).action, "SHORT");
});

test("the stop sits 1 ATR beyond the entry zone, never on its edge: the Askari Bank case", () => {
  // Band Rs.102.50 to Rs.106.19 with the stop at Rs.102.50, ATR Rs.2: the stop moves to 102.50 - 2.00.
  const long = call("LONG", { entry: { low: 102.5, high: 106.19 }, invalidation: 102.5 });
  const d = bufferStop(long, input({ atr: 2 }));
  assert.equal(STOP_BUFFER_ATR, 1);
  assert.equal(d.invalidation, 100.5);
  assert.ok(d.invalidation! < d.entry!.low, "strictly below the band");
  assert.deepEqual(d.why, long.why, "a table call keeps its reasons");
  assert.match(d.notes.at(-1)!, /1 x the 14-session average true range beyond the entry zone/);
  // A structural stop already further away is kept exactly, with no rounding and no sentence: NKE's
  // setup stop 36.66999816894531 was being rounded to 36.669998 and labelled as a buffer it was not.
  const far = call("LONG", { entry: { low: 102.5, high: 106.19 }, invalidation: 95.12345678912 });
  assert.equal(bufferStop(far, input({ atr: 2 })), far);
  const nke = call("SHORT", { entry: { low: 34.709999084472656, high: 34.709999084472656 }, invalidation: 36.66999816894531 });
  assert.equal(bufferStop(nke, input({ atr: 1.1607144219534737 })).invalidation, 36.66999816894531);
  // The short mirror: max(zone high + 1 ATR, the structural stop).
  const short = call("SHORT", { entry: { low: 50, high: 52 }, invalidation: 52 });
  assert.equal(bufferStop(short, input({ atr: 1 })).invalidation, 53);
});

test("the buffer leaves a 2 x ATR resolved stop alone, moves a nearer one, and invents no volatility", () => {
  // A resolved call's zone is its close; a 2 x ATR stop is already past 1.5 ATR, so nothing changes.
  const forced = resolveCall(wait("stop-crossed", "up"), input({ lastClose: 90, invalidation: 94 }));
  assert.equal(bufferStop(forced, input({ lastClose: 90, atr: 2.5 })).invalidation, forced.invalidation);
  // The setup's own stop 1 below a close of 100 is nearer than 1 x 2.5: it moves to 97.5, and the
  // stop sentence says so.
  const own = resolveCall(wait("incomplete", "up"), input({ invalidation: 99 }));
  assert.equal(own.invalidation, 99);
  const moved = bufferStop(own, input({ invalidation: 99 }));
  assert.equal(moved.invalidation, 97.5);
  assert.match(moved.why[1], /beyond the entry zone/);
  // No stored ATR: the stop is left as it was rather than buffered by a made-up range.
  const bare = call("LONG", { entry: { low: 102.5, high: 106.19 }, invalidation: 102.5 });
  assert.equal(bufferStop(bare, input({ atr: null })).invalidation, 102.5);
  // WAIT is never touched.
  assert.equal(bufferStop(wait("stale"), input()).invalidation, null);
});

test("the plan's reward:risk is re-measured against the moved stop, from the entry level", () => {
  const plan = { entry: { low: 100, high: 104 }, invalidation: 100, target: { low: 112, high: 115, method: "structure" }, rewardRisk: 2, baseRate: { share: 0.6, count: 30 }, expectancyR: 0.8 };
  const d = bufferStop(call("LONG", { entry: { low: 100, high: 104 }, invalidation: 100, plan }), input({ atr: 2 }));
  // Stop 100 - 2 = 98; reward 112 - 104 = 8; risk 104 - 98 = 6.
  assert.equal(d.invalidation, 98);
  assert.equal(d.plan?.invalidation, 98);
  assert.ok(Math.abs((d.plan?.rewardRisk ?? 0) - 8 / 6) < 1e-12);
  assert.ok(Math.abs((d.plan?.expectancyR ?? 0) - (0.6 * (8 / 6) - 0.4)) < 1e-12);
});

test("a macro veto on one side gives the other side", () => {
  assert.equal(resolveCall(wait("macro-veto", "up"), input()).action, "SHORT");
});

test("no side at all: momentum decides, and nothing measured at all is LONG and logged as such", () => {
  const down = input({ setup: { direction: "flat", horizon: "swing", trend: "down", bias: "down" }, r20: -4 });
  assert.deepEqual(momentumSide(down), { side: "down", measured: true });
  assert.equal(resolveCall(wait("incomplete"), down).action, "SHORT");
  // A fired entry rule counts double, so it can outvote one weak reading the other way.
  assert.equal(momentumSide(input({ setup: null, r20: -1, entryTrigger: { rule: "x", direction: "up" } })).side, "up");
  const blank = input({ setup: null, r20: null });
  const d = resolveCall(wait("incomplete"), blank);
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "forced-nosignal");
});

test("only a name with no close at all stays WAIT, and a call the table made is untouched", () => {
  assert.equal(resolveCall(wait("no-prices"), input({ lastClose: null })).action, "WAIT");
  const real = decide(input({ volumeRatio: 1.8, relStrength: 1, analogs: { count: 12, lowPct: -3, highPct: 6, medianPct: 1.4, positive: 8 } }));
  assert.equal(resolveCall(real, input()), real);
});

test("a resolved call is never graded High, and no stop is invented without a range", () => {
  const d = resolveCall(wait("short-unbacked", "down"), input({ invalidation: 94, atr: null }));
  // (an up setup's stop below the close is no stop for a short, and with no range there is none)
  assert.equal(d.invalidation, null);
  assert.notEqual(d.confidence, "High");
  assert.match(d.why.join(" "), /No stop could be measured/);
});

test("decideCall never returns WAIT for a priced name", () => {
  for (const over of [
    { invalidation: 104 }, // a long setup whose stop sits above the close: stop-crossed
    { setup: { direction: "flat" as const, horizon: "swing" }, horizon: null },
    { invalidation: null },
    { setup: { direction: "down" as const, horizon: "swing" }, horizon: { direction: "down" as const }, invalidation: 106 },
  ]) {
    const d = decideCall(input(over));
    assert.ok(d.action === "LONG" || d.action === "SHORT", JSON.stringify(over) + " gave " + d.action);
  }
});

test("every caller goes through decideCall, and the reversal gate reads only calls the table made", () => {
  const read = (p: string) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
  assert.match(read("lib/assetClass.ts"), /const decision = decideCall\(input\);/);
  assert.match(read("app/asset/[symbol]/page.tsx"), /const decision = decideCall\(decisionInput\)/);
  const job = read("tools/decide.mjs");
  assert.match(job, /const decision = decideCall\(decisionInput\)/);
  assert.doesNotMatch(job, /[^.\w]decide\(decisionInput\)/);
  assert.match(job, /gate NOT LIKE 'forced-%'/);
  assert.match(read("lib/queries.ts"), /NOT: \{ gate: \{ startsWith: "forced-" \} \}/);
  // The run the whipsaw guard reads comes from one SQL text in both readers, and the guard runs last.
  const runSql = /lag\(action\) OVER \(PARTITION BY "assetId" ORDER BY "periodEnd"\) AS prev\s+FROM "DecisionLog"\s+WHERE action IN \('LONG', 'SHORT'\)/;
  assert.match(job, runSql);
  assert.match(read("lib/queries.ts"), runSql);
  assert.match(read("lib/resolve.ts"), /return bufferStop\(whipsawHold\(resolveCall\(decide\(input\), input\), input\), input\);/);
});
