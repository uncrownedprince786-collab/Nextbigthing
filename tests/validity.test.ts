// Trade horizon and the validity window: one function shared by every list row and the asset page.

import { test } from "node:test";
import assert from "node:assert/strict";
import { HORIZONS, horizonKey, shortDay, validityOf } from "../lib/validity.ts";

const base = {
  action: "LONG",
  setupHorizon: "swing",
  runAction: "LONG",
  runSince: "2026-10-07",
  asOf: "2026-10-09",
  today: "2026-10-10",
};

test("the horizon is the setup that decided: swing is 1-7 days, longer is a 1-4 week position", () => {
  assert.equal(horizonKey("swing"), "swing");
  assert.equal(horizonKey("longer"), "longer");
  assert.equal(horizonKey(null), "swing", "a daily direction with no stored horizon is the default daily one");
  assert.equal(horizonKey("intraday"), "swing");
  assert.deepEqual(HORIZONS.swing, { label: "Swing", span: "1–7 days", validDays: 7 });
  assert.deepEqual(HORIZONS.longer, { label: "Position", span: "1–4 weeks", validDays: 28 });
});

test("valid from is the day the current call began, from the log, and runs for the horizon", () => {
  const v = validityOf(base)!;
  assert.deepEqual([v.from, v.until, v.status, v.day, v.label], ["2026-10-07", "2026-10-14", "Active", 4, "Swing"]);
  const p = validityOf({ ...base, setupHorizon: "longer" })!;
  assert.deepEqual([p.from, p.until, p.label, p.span], ["2026-10-07", "2026-11-04", "Position", "1–4 weeks"]);
});

test("a call the log has not seen yet begins at the close it is read from", () => {
  // The log's newest run is a different verdict: this LONG began with today's reading.
  assert.equal(validityOf({ ...base, runAction: "SHORT" })!.from, "2026-10-09");
  assert.equal(validityOf({ ...base, runAction: null, runSince: null })!.from, "2026-10-09");
  assert.equal(validityOf({ ...base, runAction: null, runSince: null, asOf: null })!.from, "2026-10-10");
});

test("a call older than its horizon is shown as expired, not quietly carried", () => {
  const v = validityOf({ ...base, runSince: "2026-10-01" })!;
  assert.deepEqual([v.until, v.status], ["2026-10-08", "Expired"]);
  // The last day of the window is still active.
  assert.equal(validityOf({ ...base, runSince: "2026-10-03" })!.status, "Active");
});

test("a WAIT has no horizon and no window: it is not a call", () => {
  assert.equal(validityOf({ ...base, action: "WAIT" }), null);
});

test("dates are printed the same way everywhere, in UTC", () => {
  assert.equal(shortDay("2026-10-07"), "Oct 7");
  assert.equal(shortDay("2026-11-04"), "Nov 4");
  const fromDate = validityOf({ ...base, runSince: new Date("2026-10-07T00:00:00Z") })!;
  assert.equal(fromDate.from, "2026-10-07");
});

test("the list and the asset panel print the same columns under the same names, from one function", async () => {
  const { readFileSync } = await import("node:fs");
  const read = (p: string) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
  const decision = read("components/decision.tsx");
  const panel = decision.slice(decision.indexOf("export function DecisionPanel("), decision.indexOf("export function ProductDecisionPanel("));
  const rows = decision.slice(decision.indexOf("function DecisionRows("));
  for (const label of ["Price", "Entry zone", "Stop loss", "Measured exit", "Reward:risk", "Horizon & validity", "Confirmations"]) {
    assert.ok(rows.includes(`>${label}</span>`), `list row has no ${label}`);
    assert.ok(panel.includes(`label="${label}"`), `asset panel has no ${label}`);
  }
  assert.ok(panel.includes("<HorizonValidity") && rows.includes("<HorizonValidity"), "one component renders the window in both");
  assert.ok(read("lib/assetClass.ts").includes("validity: validityOf({"));
  assert.ok(read("app/asset/[symbol]/page.tsx").includes("const validity = validityOf({"));
});
