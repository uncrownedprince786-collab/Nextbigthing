// The logbook page reads JSON another program wrote; it must draw it faithfully and survive junk.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { toLines } from "../lib/logbook.ts";

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
