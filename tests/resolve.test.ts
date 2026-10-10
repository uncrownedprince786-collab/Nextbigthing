// A priced name resolves to LONG or SHORT (brain.md rule 86) except where rule 92 leaves it WAIT: a call
// that ended at its stop, and a name nothing measured leans on. The evidence table is unchanged; this pins
// the layer after it: which side each refusal becomes, where the stop comes from, and that every caller
// goes through the one function.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { decide, type Decision, type DecisionInput } from "../lib/decision.ts";
import { ATR_STOP_MULTIPLE, bufferStop, decideCall, momentumSide, NO_DIRECTION, resolveCall, STOP_BUFFER_ATR, whipsawHold, WHIPSAW_DAYS } from "../lib/resolve.ts";

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

test("a close through the stop ends the call: no opposite call, and not the old one either", () => {
  // Rule 92. A long's stop crossed downward stays WAIT under the table's own reason; before 2026-10-11 it
  // became a SHORT stopped 2 x ATR above the close, with no measured target on that side (0 of 223).
  const ended = wait("stop-crossed", "up");
  const d = resolveCall(ended, input({ lastClose: 90, invalidation: 94 }));
  assert.equal(d, ended, "the table's WAIT, unchanged");
  // The short mirror.
  const up = wait("stop-crossed", "down");
  assert.equal(resolveCall(up, input({ setup: { direction: "down", horizon: "swing" }, lastClose: 110, invalidation: 104 })), up);
  // Through the whole path: a long setup whose stop is above the close is WAIT, gate stop-crossed.
  const whole = decideCall(input({ invalidation: 104 }));
  assert.equal(whole.action, "WAIT");
  assert.equal(whole.gate, "stop-crossed");
});

test("an unconfirmed short is SHORT, keeping its own stop when that stop is above the close", () => {
  const down = { direction: "down" as const, horizon: "swing" };
  const d = resolveCall(wait("short-unbacked", "down"), input({ setup: down, invalidation: 106 }));
  assert.equal(d.action, "SHORT");
  assert.equal(d.invalidation, 106, "the setup's own stop is kept");
  // A stop on the wrong side for the side taken is replaced by the ATR stop.
  assert.equal(resolveCall(wait("short-unbacked", "down"), input({ setup: down, invalidation: 94 })).invalidation, 105);
  assert.equal(ATR_STOP_MULTIPLE, 2);
});

test("an unconfirmed flip keeps the call the reader holds: the patient flip", () => {
  const prior = { direction: "down" as const, asOf: "2026-10-09" };
  const run = { direction: "down" as const, since: "2026-10-09", left: null };
  const d = resolveCall(wait("reversal-unconfirmed", "up"), input({ priorDirection: prior, lastRun: run, invalidation: 94 }));
  assert.equal(d.action, "SHORT");
  assert.equal(d.gate, "forced-reversal-unconfirmed");
});

test("a call that ended at its stop is never held, guarded back or revived", () => {
  // The run reads ENDED after a stop-crossed WAIT (lib/queries.ts), so `lastRun` is null; the table's last
  // call is still in `priorDirection` for the reversal gate. An unconfirmed turn then stays WAIT: there is
  // no fallback to the stopped call.
  const prior = { direction: "down" as const, asOf: "2026-10-08" };
  const held = wait("reversal-unconfirmed", "up");
  assert.equal(resolveCall(held, input({ priorDirection: prior, lastRun: null, invalidation: 94 })), held);
  // Both readers run the same SQL, and it reads a stop-crossed WAIT as the end of the run.
  const read = (f: string) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
  const ended = /CASE WHEN action IN \('LONG', 'SHORT'\) THEN action ELSE 'ENDED' END AS action\s+FROM "DecisionLog"\s+WHERE \(action IN \('LONG', 'SHORT'\) OR \(action = 'WAIT' AND gate = 'stop-crossed'\)\)/;
  assert.match(read("lib/queries.ts"), ended);
  assert.match(read("tools/decide.mjs"), ended);
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
  // A resolved call's zone is its close; a 2 x ATR stop is already past 1 ATR, so nothing changes.
  const down = { direction: "down" as const, horizon: "swing" };
  const forced = resolveCall(wait("short-unbacked", "down"), input({ setup: down, lastClose: 90, invalidation: 80 }));
  assert.equal(forced.invalidation, 90 + ATR_STOP_MULTIPLE * 2.5);
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

test("no side at all: measured momentum decides, and with nothing measured there is no call", () => {
  const down = input({ setup: { direction: "flat", horizon: "swing", trend: "down", bias: "down" }, r20: -4 });
  assert.equal(momentumSide(down), "down");
  assert.equal(resolveCall(wait("incomplete"), down).action, "SHORT");
  // A fired entry rule counts double, so it can outvote one weak reading the other way.
  assert.equal(momentumSide(input({ setup: null, r20: -1, entryTrigger: { rule: "x", direction: "up" } })), "up");
  // Rule 92: nothing measured is no direction. Before 2026-10-11 this was LONG, "the long-run drift".
  const blank = input({ setup: null, r20: null });
  assert.equal(momentumSide(blank), null);
  const d = resolveCall(wait("incomplete"), blank);
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "incomplete");
  assert.equal(d.why[1], NO_DIRECTION, "the held-back row says why there is no call");
  assert.doesNotMatch(readFileSync(new URL("../lib/resolve.ts", import.meta.url), "utf8"), /nosignal|side: "up", measured: false/);
});

test("a name with no close, a stopped call and an unmeasured name stay WAIT; a call the table made is untouched", () => {
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

test("decideCall returns WAIT for a priced name only for a stopped call or nothing measured", () => {
  for (const over of [
    { setup: { direction: "flat" as const, horizon: "swing" }, horizon: null, r20: 2 },
    { invalidation: null, r20: 2 },
    { setup: { direction: "down" as const, horizon: "swing" }, horizon: { direction: "down" as const }, invalidation: 106 },
  ]) {
    const d = decideCall(input(over));
    assert.ok(d.action === "LONG" || d.action === "SHORT", JSON.stringify(over) + " gave " + d.action);
  }
  assert.equal(decideCall(input({ invalidation: 104 })).action, "WAIT");
  assert.equal(decideCall(input({ setup: null, horizon: null, r20: null })).action, "WAIT");
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
  const runSql = /lag\(action\) OVER \(PARTITION BY "assetId" ORDER BY "periodEnd"\) AS prev\s+FROM \(SELECT "assetId", "periodEnd",/;
  assert.match(job, runSql);
  assert.match(read("lib/queries.ts"), runSql);
  assert.match(read("lib/resolve.ts"), /return bufferStop\(whipsawHold\(resolveCall\(decide\(input\), input\), input\), input\);/);
});
