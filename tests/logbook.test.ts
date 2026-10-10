// The logbook page reads JSON another program wrote; it must draw it faithfully and survive junk.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { toLines, toSummary } from "../lib/logbook.ts";

test("stored lines become rules, headings, bold lines and indented text", () => {
  const lines = toLines([
    ["", ""],
    ["=".repeat(68), ""],
    ["WEEKLY PERFORMANCE REVIEW: Oct 5 - Oct 11", "title"],
    ["=".repeat(68), ""],
    ["• Completed cycles: 3", ""],
    ["1. EXPIRED / COMPLETED CALLS", "bold"],
    ["- Asset: MRK (Merck) | Type: LONG", ""],
    ["  - Result: ACCURATE", ""],
    ["-".repeat(68), ""],
  ]);
  assert.deepEqual(lines, [
    { kind: "rule" },
    { kind: "title", text: "WEEKLY PERFORMANCE REVIEW: Oct 5 - Oct 11" },
    { kind: "rule" },
    { kind: "text", text: "• Completed cycles: 3", indent: 0 },
    { kind: "bold", text: "1. EXPIRED / COMPLETED CALLS" },
    { kind: "text", text: "- Asset: MRK (Merck) | Type: LONG", indent: 0 },
    { kind: "text", text: "- Result: ACCURATE", indent: 2 },
    { kind: "rule" },
  ]);
});

test("two dividers in a row draw as one rule", () => {
  assert.deepEqual(toLines([["=".repeat(68), ""], ["-".repeat(68), ""]]), [{ kind: "rule" }]);
});

test("junk in the column is skipped, never a crash", () => {
  assert.deepEqual(toLines(null), []);
  assert.deepEqual(toLines("text"), []);
  assert.deepEqual(toLines([5, null, ["ok", 7], [null, "bold"]]), [{ kind: "text", text: "ok", indent: 0 }]);
  // A style the page does not know is plain text.
  assert.deepEqual(toLines([["x", "blink"]]), [{ kind: "text", text: "x", indent: 0 }]);
});

test("the logbook is in the navigation", () => {
  const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  assert.match(layout, /\{ href: "\/logbook", label: "Logbook" \}/);
});

test("the summary is read back only when it is honest", () => {
  const good = {
    asOf: "2026-10-10",
    graded: 4,
    accurate: 3,
    failed: 1,
    accuratePct: 75,
    failedPct: 25,
    flips: [{ day: "2026-10-10", symbol: "VRTX", name: "Vertex", from: "SHORT", to: "LONG" }, { day: "x", symbol: "BAD" }],
    stars: [{ day: "2026-10-09", symbol: "STX", name: "Stacks", direction: "up", result: "pending" }, { result: "maybe" }],
    starsGraded: 0,
    starsAccurate: 0,
    starsAccuratePct: null,
  };
  const s = toSummary(good)!;
  assert.equal(s.accuratePct, 75);
  assert.deepEqual(s.flips.map((f) => f.symbol), ["VRTX"], "a malformed flip is dropped");
  assert.deepEqual(s.stars.map((x) => x.symbol), ["STX"], "a malformed star is dropped");
  // No rate from nothing: with nothing graded, a stored rate is ignored.
  assert.equal(toSummary({ ...good, graded: 0, accurate: 0, failed: 0, accuratePct: 0 })!.accuratePct, null);
  // Counts that do not add up, or junk, are no summary at all.
  assert.equal(toSummary({ ...good, accurate: 5 }), null);
  assert.equal(toSummary(null), null);
  assert.equal(toSummary([["text", ""]]), null);
  // A flip must change direction.
  assert.equal(toSummary({ ...good, flips: [{ day: "2026-10-10", symbol: "A", from: "LONG", to: "LONG" }] })!.flips.length, 0);
});

test("the summary leads and the daily audits fold away", () => {
  const page = readFileSync(new URL("../app/logbook/page.tsx", import.meta.url), "utf8");
  assert.ok(page.indexOf("<Scorecard") < page.indexOf("<details"), "the verdicts come first");
  assert.doesNotMatch(page, /<details[^>]*\bopen\b/, "the full audits start closed");
});
