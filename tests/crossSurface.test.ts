// One canonical call record on every surface (brain.md rule 94). CHBL read "SHORT · High" in the overview's
// coming-week block while its own page read Medium; the coming week also showed entry, stop and exit with no
// execution state. Every surface now reads the same scored record -- the evidence grade, the timing with the
// close it read, and the execution status -- and these tests pin that each one does.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { weeklyFocus } from "../lib/weeklyFocus.ts";

const read = (f: string) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

type Any = Parameters<typeof weeklyFocus>[0][number];

function scored(symbol: string, confidence: "High" | "Medium", execution: { status: string; reasons: string[] }): Any {
  return {
    row: { symbol, name: symbol, currency: "PKR", closeDate: new Date("2026-10-09"), swing: { targets: [] }, longer: null },
    market: "PSX",
    decision: {
      action: "SHORT", why: ["Setup is down on the longer view."], entry: { low: 8.8, high: 9.17 }, invalidation: 9.8,
      timeSense: "NOW", confidence, missing: [], notes: [], measured: "", gate: "short", basis: null, plan: null,
      legs: ["history", "peers"], intent: null, developing: null,
    },
    gate: { published: true, reasons: [] },
    execution,
    timing: { label: "IN ZONE", price: 8.82, on: "2026-10-09", inZone: true },
  } as unknown as Any;
}

test("the coming-week block carries each name's own scored record, unchanged", () => {
  const chbl = scored("CHBL", "Medium", { status: "unverified", reasons: ["the site holds no short-sale eligibility data for this security"] });
  const focus = weeklyFocus([chbl]);
  assert.equal(focus.short[0], chbl, "the same object the lists and the API read: no second grade can exist");
  assert.equal(focus.short[0].decision.confidence, "Medium");
  assert.equal(focus.short[0].execution?.status, "unverified");
  assert.equal(focus.short[0].timing?.label, "IN ZONE");
});

test("every surface reads grade, timing and execution from the scored record", () => {
  // The API record is `toSignal` of the scored row; the market row is `toListRow`; the asset page scores
  // the lists' own cached row; the coming-week and top-by-class blocks render the scored row.
  const assetClass = read("lib/assetClass.ts");
  assert.match(assetClass, /confidence: s\.decision\.confidence,\s+validFrom/);
  assert.match(assetClass, /execution: s\.execution \?\? null,\s+\/\/ The timing shown/);
  assert.match(read("app/api/signals/route.ts"), /\.map\(\(s\) => toSignal\(s, today\)\)/);
  assert.match(assetClass, /export function toListRow\(s: Scored\): DecisionRow/);
  assert.match(assetClass, /execution: s\.execution \?\? null,/);
  const asset = read("app/asset/[symbol]/page.tsx");
  assert.match(asset, /const decision = scored \? scored\.decision : decideCall\(decisionInput\);/);
  assert.match(asset, /priceNow=\{cachedRow \? cachedRow\.close/, "the timing's close is the decision's close");
  const week = read("components/weeklyFocusBlock.tsx");
  assert.match(week, /<ConfidenceBadge grade=\{decision\.confidence\.toLowerCase\(\)\} \/>/);
  assert.match(week, /item\.execution && item\.execution\.status !== "checked"/);
  assert.match(week, /item\.timing && item\.timing\.label !== "WAIT FOR LEVEL"/);
  const top = read("components/topByClass.tsx");
  assert.match(top, /\{s\.decision\.confidence\}/);
  assert.match(top, /s\.execution && s\.execution\.status !== "checked"/);
  // A longer-term setup's own grade is labelled as that timeframe's and is not the call's.
  assert.doesNotMatch(week, /setup\.confidence/);
});

test("the live audit compares grade, timing and execution across the API, asset pages and the coming week", () => {
  const audit = read("tools/logic_audit.py");
  assert.match(audit, /def cross_surface\(calls: list\[dict\]\) -> list\[str\]:/);
  assert.match(audit, /"grade\/timing\/execution differ across surfaces": len\(pg\["surface_mismatch"\]\)/);
});
