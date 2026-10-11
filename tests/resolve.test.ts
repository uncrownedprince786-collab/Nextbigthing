// The layer after the evidence table (brain.md rule 93): a refusal stays a refusal, a direction no
// confirmation backs is WAIT, no High while the live edge is unmeasured, and faulty data is WAIT last of
// all. And the presentation and data facts that rule depends on: execution readiness, news coverage
// availability, and the run query that ends a call at its stop.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { confirmingLegs, decide, type Decision, type DecisionInput } from "../lib/decision.ts";
import {
  bufferStop,
  dataGate,
  decideCall,
  endStoppedCall,
  requireConfirmation,
  STOP_BUFFER_ATR,
} from "../lib/resolve.ts";
import { targetForCall } from "../lib/target.ts";
import { executionOf, timingOf } from "../lib/execution.ts";
import { OUTCOME_MIN_SAMPLE, outcomeCounts, outcomeStatusOf, wilson } from "../lib/outcome.ts";
import { newsCoverageOf, NEWS_READING_STALE_DAYS } from "../lib/decisionInput.ts";

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
    r1: 1,
    ...over,
  };
}

function wait(gate: string, intent: "up" | "down" | null = null): Decision {
  return {
    action: "WAIT", why: ["held"], entry: { low: 95, high: 98 }, invalidation: 94, timeSense: "WAIT FOR LEVEL",
    confidence: "Low", missing: [], notes: [], measured: "", gate, basis: "evidence", plan: null,
    legs: [], intent, developing: null,
  };
}

function call(action: "LONG" | "SHORT", over: Partial<Decision> = {}): Decision {
  return { ...wait("trend"), action, gate: action === "LONG" ? "trend-long" : "trend-short", entry: { low: 98, high: 102 }, invalidation: action === "LONG" ? 94 : 106, ...over };
}

const DOWN = { direction: "down" as const, horizon: "swing" };
const veto = { reason: "macro-warning" as const, asOf: "2026-10-10" };

// --- P0-1: a macro veto refuses, and never reverses ---------------------------------------------

test("a macro veto on a LONG is WAIT, never SHORT", () => {
  const d = decideCall(input({ macroVeto: veto, volumeRatio: 2 }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "macro-veto");
  assert.equal(d.intent, "up", "it names the side it refused");
});

test("a macro veto on a SHORT is WAIT, never LONG", () => {
  const d = decideCall(input({ setup: DOWN, horizon: { direction: "down" }, invalidation: 106, macroVeto: veto, volumeRatio: 2, r1: -1 }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "macro-veto");
  assert.equal(d.intent, "down");
});

test("the veto never changes the sign: with it and without it, the only difference is WAIT", () => {
  for (const over of [{}, { setup: DOWN, horizon: { direction: "down" as const }, invalidation: 106, r1: -1 }]) {
    const clean = decideCall(input({ ...over, volumeRatio: 2 }));
    const vetoed = decideCall(input({ ...over, volumeRatio: 2, macroVeto: veto }));
    assert.ok(clean.action === "LONG" || clean.action === "SHORT");
    assert.equal(vetoed.action, "WAIT");
    assert.notEqual(vetoed.action, clean.action === "LONG" ? "SHORT" : "LONG");
  }
});

// --- P0-2: faulty data never carries a direction ------------------------------------------------

test("a stale, silent, missing or unreadable close is WAIT through every path", () => {
  const stale = decideCall(input({ asOf: "2026-10-01", volumeRatio: 2 }));
  assert.equal(stale.action, "WAIT");
  assert.equal(stale.gate, "stale");
  assert.equal(decideCall(input({ sourceSilent: "Yahoo Finance daily closes", volumeRatio: 2 })).gate, "source-silent");
  assert.equal(decideCall(input({ lastClose: null })).gate, "no-prices");
  assert.equal(decideCall(input({ asOf: null })).action, "WAIT");
  assert.equal(decideCall(input({ asOf: "not a date", volumeRatio: 2 })).action, "WAIT");
});

test("the final data gate overrides a direction whatever produced it", () => {
  // A LONG built by hand, as any earlier step might have, on data that fails its own freshness rule.
  for (const bad of [{ asOf: "2026-10-01" }, { sourceSilent: "PSX daily closing files" }, { lastClose: null }, { asOf: null }]) {
    const d = dataGate(call("LONG", { confidence: "High", legs: ["volume", "peers"] }), input(bad));
    assert.equal(d.action, "WAIT", JSON.stringify(bad));
    assert.equal(d.timeSense, "WAIT FOR LEVEL", "never NOW on faulty data");
    assert.equal(d.plan, null);
  }
  // Fresh data passes untouched.
  const ok = call("LONG");
  assert.equal(dataGate(ok, input()), ok);
});

test("NOW only when the fresh close is inside the entry zone", () => {
  assert.equal(decideCall(input({ volumeRatio: 2, lastClose: 100 })).timeSense, "NOW");
  assert.equal(decideCall(input({ volumeRatio: 2, lastClose: 104, invalidation: 94 })).timeSense, "WAIT FOR LEVEL");
});

// --- P0-3: the opposite side needs its own evidence ---------------------------------------------

test("two timeframes agreeing on one side never confirm the other", () => {
  const both = input({ setup: { direction: "up", horizon: "swing" }, horizon: { direction: "up" } });
  assert.ok(confirmingLegs(both, "up").includes("timeframe"));
  assert.ok(!confirmingLegs(both, "down").includes("timeframe"), "the longer view confirms only the side both read");
});

test("mixed timeframes, a recent opposite call, or a veto give WAIT with the reason, never the other side", () => {
  const mixed = decideCall(input({ horizon: { direction: "down" }, volumeRatio: 2 }));
  assert.equal(mixed.action, "WAIT");
  const turned = decideCall(
    input({ setup: DOWN, horizon: null, invalidation: 106, priorDirection: { direction: "up", asOf: "2026-10-08" } }),
  );
  assert.equal(turned.action, "WAIT");
  assert.equal(turned.gate, "reversal-unconfirmed");
  assert.equal(turned.intent, "down", "the turn it refused, not the call it replaced");
});

// --- P0-5: no forced direction, and none without a confirmation ---------------------------------

test("every refusal of the table stays a refusal", () => {
  // short-unbacked, a crossed stop, no stop at all, and a fall-through: each was turned into a call by
  // the layer this file used to hold (rule 86).
  const cases: Partial<DecisionInput>[] = [
    { setup: { direction: "flat", horizon: "swing", trend: "down" }, horizon: null, invalidation: 106, target: { method: "structure", low: 80, high: 84, rewardRisk: 3 } },
    { invalidation: 104 },
    { invalidation: null },
    { setup: { direction: "flat", horizon: "swing" }, horizon: null },
    { setup: null, horizon: null },
  ];
  for (const over of cases) {
    const d = decideCall(input(over));
    assert.equal(d.action, "WAIT", JSON.stringify(over) + " gave " + d.action + " " + d.gate);
    assert.ok(!d.gate.startsWith("forced-"), d.gate);
  }
  const src = readFileSync(new URL("../lib/resolve.ts", import.meta.url), "utf8");
  assert.doesNotMatch(src, /forcedCall|momentumSide|resolvedSide|whipsawHold|flip\(/, "the forced layer is gone");
});

test("a direction no confirmation backs is WAIT, naming the side it read and the confirmations absent", () => {
  // A setup in state `buy` with all five confirmations absent: the table prints LONG at Low.
  const bare = input({ horizon: null });
  assert.equal(decide(bare).action, "LONG");
  const d = decideCall(bare);
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "no-confirmation");
  assert.equal(d.intent, "up");
  assert.match(d.why[1], /Absent: the longer view reading the same way, volume at or above its average/);
  // One confirmation is enough to stay a direction.
  assert.equal(decideCall(input({ horizon: null, volumeRatio: 2 })).action, "LONG");
  assert.equal(requireConfirmation(call("LONG"), input({ volumeRatio: 2 })).action, "LONG");
});

test("a call that ended at its stop keeps its stop and loses its entry and plan, on every surface", () => {
  const d = decideCall(input({ invalidation: 104 }));
  assert.equal(d.gate, "stop-crossed");
  assert.equal(d.entry, null);
  assert.equal(d.invalidation, 104);
  assert.equal(endStoppedCall(call("LONG")).entry !== null, true, "a live call is untouched");
  const stored = { method: "structure", low: 80, high: 82, distancePct: null, rewardRisk: 3.4 };
  assert.equal(targetForCall(stored, d), null, "no exit for an ended call");
});

// --- confidence: no High while the edge is unmeasured -------------------------------------------

test("the grade is the evidence for the reading, and outcome status is a separate label", () => {
  // Rule 94 withdrew rule 93's cap: the grade counts confirmations and is shown as counted, on every
  // surface; whether calls have been right is outcome status, printed beside it.
  const healthy = input({ volumeRatio: 2, relStrength: 9, analogs: { count: 30, lowPct: -2, highPct: 6, medianPct: 2, positive: 22 } });
  assert.equal(decide(healthy).confidence, "High");
  assert.equal(decideCall(healthy).confidence, "High", "the call shows the table's evidence grade unchanged");
  assert.doesNotMatch(readFileSync(new URL("../lib/resolve.ts", import.meta.url), "utf8"), /capUnmeasured\(|HIGH_AWAITS_MEASURED_EDGE =/);
  // Outcome status from the logbook's graded counts.
  assert.equal(outcomeStatusOf(null).status, "untested");
  assert.equal(outcomeStatusOf({ graded: 0, accurate: 0 }).status, "untested");
  assert.match(outcomeStatusOf({ graded: 0, accurate: 0 }).sentence, /no edge is claimed/);
  assert.equal(outcomeStatusOf({ graded: 12, accurate: 9 }).status, "pending", "under the sample, no rate is reported");
  assert.equal(outcomeStatusOf({ graded: 12, accurate: 9 }).rate, null);
  assert.equal(outcomeStatusOf({ graded: 40, accurate: 30 }).status, "validated", "75% of 40: the interval clears 50%");
  assert.equal(outcomeStatusOf({ graded: 40, accurate: 22 }).status, "not validated", "55% of 40: the interval does not");
  const [lo, hi] = wilson(30, 40);
  assert.ok(lo > 0.59 && lo < 0.61 && hi > 0.85 && hi < 0.87, `${lo} ${hi}`);
  // The published calls are what readers were shown, and what the status reports when counted.
  assert.deepEqual(outcomeCounts({ graded: 50, accurate: 30, publishedGraded: 12, publishedAccurate: 7 }), { graded: 12, accurate: 7 });
  assert.deepEqual(outcomeCounts({ graded: 50, accurate: 30, publishedGraded: null, publishedAccurate: null }), { graded: 50, accurate: 30 });
  assert.equal(outcomeCounts(null), null);
  // The sample equals the scorecard's own.
  const scorecard = readFileSync(new URL("../tools/scorecard.py", import.meta.url), "utf8");
  assert.match(scorecard, new RegExp(`^MIN_SAMPLE = ${OUTCOME_MIN_SAMPLE}\\b`, "m"));
});

test("every surface prints the same outcome sentence from the logbook's counts", () => {
  const read = (f: string) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
  assert.match(read("app/api/signals/route.ts"), /outcome: outcomeStatusOf\(rows\[0\]\?\.outcome \?\? null\)/);
  assert.match(read("app/asset/[symbol]/page.tsx"), /outcome=\{outcomeStatusOf\(cachedRow\?\.outcome \?\? null\)\}/);
  assert.match(read("components/weeklyFocusBlock.tsx"), /outcomeStatusOf\(rows\[0\]\?\.row\.outcome \?\? null\)\.sentence/);
  assert.match(read("components/classIndex.tsx"), /outcomeStatusOf\(rows\[0\]\?\.outcome \?\? null\)\.sentence/);
  assert.match(read("app/logbook/page.tsx"), /outcomeStatusOf\(outcomeCounts\(summary\)\)\.sentence/);
  assert.match(read("lib/queries.ts"), /const outcome = outcomeCounts\(logSummary\);/);
  assert.match(read("lib/queries.ts"), /const logRead = getLogbookSummary\(\)/);
});

// --- the stop buffer (rule 91) --------------------------------------------------------------------

test("the stop sits 1 ATR beyond the entry zone, never on its edge: the Askari Bank case", () => {
  const long = call("LONG", { entry: { low: 102.5, high: 106.19 }, invalidation: 102.5 });
  const d = bufferStop(long, input({ atr: 2 }));
  assert.equal(STOP_BUFFER_ATR, 1);
  assert.equal(d.invalidation, 100.5);
  assert.deepEqual(d.why, long.why, "a table call keeps its reasons");
  assert.match(d.notes.at(-1)!, /1 x the 14-session average true range beyond the entry zone/);
  const far = call("LONG", { entry: { low: 102.5, high: 106.19 }, invalidation: 95.12345678912 });
  assert.equal(bufferStop(far, input({ atr: 2 })), far);
  const nke = call("SHORT", { entry: { low: 34.709999084472656, high: 34.709999084472656 }, invalidation: 36.66999816894531 });
  assert.equal(bufferStop(nke, input({ atr: 1.1607144219534737 })).invalidation, 36.66999816894531);
  assert.equal(bufferStop(call("SHORT", { entry: { low: 50, high: 52 }, invalidation: 52 }), input({ atr: 1 })).invalidation, 53);
  assert.equal(bufferStop(call("LONG", { entry: { low: 102.5, high: 106.19 }, invalidation: 102.5 }), input({ atr: null })).invalidation, 102.5);
  assert.equal(bufferStop(wait("stale"), input()).invalidation, 94, "WAIT is never touched");
});

test("the plan's reward:risk is re-measured against the moved stop, from the entry level", () => {
  const plan = { entry: { low: 100, high: 104 }, invalidation: 100, target: { low: 112, high: 115, method: "structure" }, rewardRisk: 2, baseRate: { share: 0.6, count: 30 }, expectancyR: 0.8 };
  const d = bufferStop(call("LONG", { entry: { low: 100, high: 104 }, invalidation: 100, plan }), input({ atr: 2 }));
  assert.equal(d.invalidation, 98);
  assert.equal(d.plan?.invalidation, 98);
  assert.ok(Math.abs((d.plan?.rewardRisk ?? 0) - 8 / 6) < 1e-12);
});

// --- P0-9: execution readiness is separate from direction ---------------------------------------

test("a SHORT is never an executable call on data that cannot confirm it", () => {
  assert.equal(executionOf({ action: "SHORT", closeVolume: 5000, market: "US" })?.status, "unverified");
  assert.match(executionOf({ action: "SHORT", closeVolume: 5000, market: "PSX" })!.reasons.join(" "), /no short-sale eligibility data/);
  // A pair or a future is sold as easily as bought: no eligibility question, only the volume one.
  assert.equal(executionOf({ action: "SHORT", closeVolume: 5000, market: "Commodity" })?.status, "checked");
  assert.deepEqual(executionOf({ action: "SHORT", closeVolume: null, market: "FX" })?.reasons, ["this market publishes no volume, so liquidity cannot be measured"]);
  assert.equal(executionOf({ action: "LONG", closeVolume: 0 })?.status, "blocked");
  assert.equal(executionOf({ action: "SHORT", closeVolume: 0 })?.status, "blocked");
  assert.equal(executionOf({ action: "LONG", closeVolume: null })?.status, "unverified", "no volume published: liquidity unmeasured");
  assert.equal(executionOf({ action: "LONG", closeVolume: 12000 })?.status, "checked");
  assert.equal(executionOf({ action: "WAIT", closeVolume: 12000 }), null);
});

test("timing names the close it read; in the zone is never 'WAIT FOR LEVEL'", () => {
  // CHBL, 2026-10-11: close Rs.8.82 inside Rs.8.80-9.17, execution unverified, printed as WAIT FOR LEVEL.
  const unverified = { status: "unverified" as const, reasons: ["x"] };
  const checked = { status: "checked" as const, reasons: ["x"] };
  const at = (close: number, execution: typeof checked | typeof unverified | null, timeSense = "NOW") =>
    timingOf({ action: "SHORT", timeSense, entry: { low: 8.8, high: 9.17 }, close, closeDate: "2026-10-09", execution });
  assert.deepEqual(at(8.82, unverified), { label: "IN ZONE", price: 8.82, on: "2026-10-09", inZone: true });
  assert.equal(at(8.82, checked)?.label, "NOW");
  assert.equal(at(8.82, null)?.label, "NOW");
  // Boundaries are inclusive, both ends; a hair outside is outside.
  assert.equal(at(8.8, checked)?.inZone, true);
  assert.equal(at(9.17, checked)?.inZone, true);
  assert.equal(at(8.7999999, checked, "WAIT FOR LEVEL")?.inZone, false);
  assert.equal(at(9.1700001, checked, "WAIT FOR LEVEL")?.inZone, false);
  // Display rounding: Rs.8.80 printed for 8.7999999 must still say outside, which is why the raw
  // close is carried and said under the pill.
  assert.equal(at(8.7999999, unverified, "WAIT FOR LEVEL")?.label, "WAIT FOR LEVEL");
  // The rule table and the zone agree at both edges.
  for (const close of [98, 102]) assert.equal(decideCall(input({ volumeRatio: 2, lastClose: close })).timeSense, "NOW");
  assert.equal(decideCall(input({ volumeRatio: 2, lastClose: 102.0001 })).timeSense, "WAIT FOR LEVEL");
  // Every surface reads the shared function: the panel, the scored row (lists, coming week, API).
  const read = (f: string) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
  assert.match(read("components/decision.tsx"), /const timing = timingOf\(/);
  assert.match(read("lib/assetClass.ts"), /timing: timingOf\(/);
  assert.match(read("lib/assetClass.ts"), /timing: s\.timing \?\? null/, "the API record (toSignal) carries it");
  assert.doesNotMatch(read("components/decision.tsx"), /"WAIT FOR LEVEL" : decision\.timeSense/);
});

// --- P0-4: coverage that cannot be read is never neutral ------------------------------------------

test("news coverage is unavailable when the database holds no recent reading or the source is silent", () => {
  assert.equal(newsCoverageOf(undefined, [], "2026-10-10"), "available", "a hand-built input predates the field");
  assert.equal(newsCoverageOf(null, [], "2026-10-10"), "unavailable", "a standby with no news rows");
  assert.equal(newsCoverageOf("2026-10-10", [], "2026-10-10"), "available");
  const old = new Date(Date.UTC(2026, 9, 10) - (NEWS_READING_STALE_DAYS + 1) * 86_400_000).toISOString().slice(0, 10);
  assert.equal(newsCoverageOf(old, [], "2026-10-10"), "unavailable");
  assert.equal(newsCoverageOf("2026-10-10", [{ source: "Google News RSS", status: "silent" }], "2026-10-10"), "unavailable");
});

test("with coverage unavailable, similar past days do not confirm and the reader is told", () => {
  const analogs = { count: 30, lowPct: -2, highPct: 6, medianPct: 2, positive: 22 };
  assert.ok(confirmingLegs(input({ analogs }), "up").includes("history"));
  const blind = input({ analogs, newsCoverage: "unavailable" });
  assert.ok(!confirmingLegs(blind, "up").includes("history"));
  const d = decide({ ...blind, volumeRatio: 2 });
  assert.ok(d.notes.some((n) => /News coverage could not be read/.test(n)), d.notes.join(" | "));
});

// --- every caller goes through one function -----------------------------------------------------

test("every caller goes through decideCall, and the pipeline only removes", () => {
  const read = (p: string) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
  assert.match(read("lib/assetClass.ts"), /const decision = decideCall\(input\);/);
  assert.match(read("app/asset/[symbol]/page.tsx"), /scoreRows\(\[cachedRow\], cachedHealth, today\)/, "the asset page decides from the lists' own row");
  const job = read("tools/decide.mjs");
  assert.match(job, /const decision = decideCall\(decisionInput\)/);
  assert.doesNotMatch(job, /[^.\w]decide\(decisionInput\)/);
  assert.match(read("lib/resolve.ts"), /return dataGate\(bufferStop\(requireConfirmation\(endStoppedCall\(decide\(input\)\), input\), input\), input\);/);
  // Both readers run the same run SQL, which reads a stop-crossed WAIT as the end of the run.
  const ended = /CASE WHEN action IN \('LONG', 'SHORT'\) THEN action ELSE 'ENDED' END AS action\s+FROM "DecisionLog"\s+WHERE \(action IN \('LONG', 'SHORT'\) OR \(action = 'WAIT' AND gate = 'stop-crossed'\)\)/;
  assert.match(read("lib/queries.ts"), ended);
  assert.match(job, ended);
  // And the same news-reading date.
  assert.match(job, /newsReadOn: input\.newsReadOn/);
  assert.match(read("lib/queries.ts"), /newsReadOn: await newsRead/);
});
