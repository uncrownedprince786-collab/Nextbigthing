// The one line that reconciles a strong direction with a weak grade. Run with `npm run test:web`.
//
// Why this has its own file. A reader shown LONG in 48px type beside the words "Low confidence"
// has been handed a contradiction and left to resolve it, and the fix is to name which leg of the
// evidence is short. That makes this line the one piece of copy on the page whose job is to agree
// with three other pieces of copy — so it is also the one most able to contradict them.
//
// It did, in the first draft. On Attock Refinery it printed "the longer view does not agree"
// directly above a Why line reading "Setup is up on the longer view", because it folded three
// different states of the confirming view into one phrase. Both sentences were generated from the
// same `Decision`. These tests exist so that cannot come back.
//
// `gapLine` reads the strings `lib/decision.ts` wrote, which is a seam and is documented as one
// in `lib/reconcile.ts`. The last test here is the one that makes the seam safe: reword the rules and
// this line goes quiet rather than guessing.

import { test } from "node:test";
import assert from "node:assert/strict";
import { gapLine } from "../lib/reconcile.ts";
import type { Decision } from "../lib/decision.ts";

function decision(over: Partial<Decision> = {}): Decision {
  return {
    action: "LONG",
    why: ["Setup is up on the longer view.", "Longer view agrees.", "Volume 1.8x its average."],
    entry: { low: 1086, high: 1199 },
    invalidation: 1086,
    timeSense: "NOW",
    confidence: "Low",
    missing: [],
    measured: "Measured, not guaranteed.",
    gate: "long",
    ...over,
  } as Decision;
}

test("a High grade has nothing to reconcile", () => {
  assert.equal(gapLine(decision({ confidence: "High" })), null);
});

test("a WAIT has no strong direction to reconcile", () => {
  assert.equal(gapLine(decision({ action: "WAIT" })), null);
});

test("it never says a view disagreed when there was only one view", () => {
  // Attock Refinery, as stored on 2026-10-03. This is the exact pair that contradicted.
  const d = decision({
    why: [
      "Setup is up on the longer view.",
      "Only one time frame points anywhere, so nothing confirms it.",
      "Nothing further confirms it yet.",
    ],
    missing: ["102 similar past days are stored, but which way they went was not recorded."],
  });
  const line = gapLine(d);
  assert.ok(line);
  assert.match(line, /only one time frame points anywhere/);
  // The contradiction itself: this phrasing must not appear while a Why line says the setup
  // *is* up on the longer view.
  assert.doesNotMatch(line, /longer view does not agree/);
});

test("no sentence in the line contradicts a sentence in Why", () => {
  // The general form of the test above. A LONG can never have a disagreeing longer view — gate 5
  // turns that into a WAIT — so the word "disagree" has no business in this line at all.
  for (const second of [
    "Longer view agrees.",
    "Only one time frame points anywhere, so nothing confirms it.",
    "Longer view is flat.",
    "Longer view does not disagree.",
  ]) {
    for (const action of ["LONG", "SHORT"] as const) {
      const line = gapLine(decision({ action, why: ["Setup is up.", second, "Nothing confirms it yet."] }));
      if (line) assert.doesNotMatch(line, /\bdisagree/, `${action} / ${second}`);
    }
  }
});

test("a weak volume and an unpublished one are different sentences", () => {
  // Telling a reader volume is weak when the truth is that none is published is a quiet lie
  // about how much evidence exists.
  const weak = gapLine(decision({ why: ["Setup is up.", "Longer view agrees.", "no confirmation"] }));
  assert.match(weak!, /volume is weak/);

  const absent = gapLine(
    decision({
      why: ["Setup is up.", "Longer view agrees.", "no confirmation"],
      missing: ["No volume published for this asset."],
    }),
  );
  assert.match(absent!, /no volume is published/);
  assert.doesNotMatch(absent!, /volume is weak/);
});

test("the direction word matches the action", () => {
  assert.match(gapLine(decision({ action: "LONG" }))!, /trend is clearly up/);
  assert.match(gapLine(decision({ action: "SHORT" }))!, /trend is clearly down/);
});

test("it reads as one sentence and names the grade it is explaining", () => {
  const line = gapLine(decision({ confidence: "Medium" }))!;
  assert.match(line, /^The trend is clearly up, but .*, so confidence is only medium\.$/);
  // One sentence, so exactly one full stop, at the end.
  assert.equal(line.split(".").length - 1, 1);
});

test("rewording the rules makes this line go quiet, not wrong", () => {
  // The seam. `gapLine` recognises what lib/decision.ts decided by reading what it wrote, so a
  // reworded rule must produce a shorter line or none — never an invented weakness. A panel that
  // goes quiet is a bug worth fixing; a panel that makes something up is a bug worth not having.
  const reworded = gapLine(
    decision({
      why: ["Setup trends upward.", "The slower read concurs.", "Turnover exceeded its norm."],
    }),
  );
  if (reworded) {
    assert.doesNotMatch(reworded, /\bdisagree/);
    assert.match(reworded, /^The trend is clearly up, but /);
  }
});
