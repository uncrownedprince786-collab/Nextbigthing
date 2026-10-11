// A WAIT because the file is empty is not a WAIT because the evidence is weak.
//
// These are the two sentences that had been reaching the page under one grey word. A reader who
// cannot tell them apart is told the system judged something when it did not — which overstates
// what is known, and is the one direction a data system must never err in.
//
// The worst instance, and the reason this file exists: with no setup row stored at all, the
// fall-through gate printed "There is no clear direction to measure. Price is between its own
// averages." That is a statement about where the price sits relative to measurements that were
// never taken. It reads as a finished reading and it is an empty file.

import { test } from "node:test";
import assert from "node:assert/strict";
import { decide, type DecisionInput } from "../lib/decision.ts";

const TODAY = "2026-10-07";

function input(over: Partial<DecisionInput> = {}): DecisionInput {
  return {
    symbol: "AAA",
    market: "US",
    asOf: TODAY,
    today: TODAY,
    lastClose: 100,
    sourceSilent: null,
    entry: { low: 95, high: 105 },
    invalidation: 95,
    setup: { direction: "unknown", horizon: "swing", trend: null },
    horizon: { direction: "unknown" },
    volumeRatio: 1.0,
    relStrength: 0,
    newsCount: 20,
    unusualMove: false,
    analogs: null,
    nextEventInDays: null,
    ...over,
  } as unknown as DecisionInput;
}

test("every gate that lacks a measurement reports file", () => {
  // Nothing stored, unreadable, silent venue, no level, and a close too old to describe now.
  assert.equal(decide(input({ asOf: null, lastClose: null })).basis, "file");
  assert.equal(decide(input({ asOf: "not-a-date" })).basis, "file");
  assert.equal(decide(input({ sourceSilent: "Yahoo Finance daily closes" })).basis, "file");
  assert.equal(decide(input({ invalidation: null })).basis, "file");
  assert.equal(decide(input({ asOf: "2026-09-01" })).basis, "file");
});

test("the one gate that holds a measurement and still refuses reports evidence", () => {
  // `mixed-horizons` and `peers-against` both used to live here and are notes now. What is left
  // is the fall-through over a setup row that was read and came back with no side: the job
  // looked, and found price between its own averages with neither of them far enough from the
  // other to name one. Something was judged and the answer was no.
  const fellThrough = decide(
    input({
      setup: { direction: "flat", horizon: "swing", trend: "mixed", bias: "mixed" },
      horizon: null,
    }),
  );
  assert.equal(fellThrough.action, "WAIT");
  assert.equal(fellThrough.gate, "incomplete");
  assert.equal(fellThrough.basis, "evidence");
});

test("a demoted gate reports no basis, because nothing was withheld", () => {
  // Both demotions, asserted as demotions. `basis` answers "why is this a WAIT", and a direction
  // that printed is not a WAIT -- so the field is null and the reason travels in `notes`, where a
  // null count and a low count still read differently (rule 21).
  // The fixture's default setup is `unknown`, which falls through on its own merits. A demotion
  // is only observable over a row that has a direction to print, so these two give it one.
  const directional = { direction: "up", horizon: "swing", trend: null } as const;

  const notChecked = decide(input({ setup: directional, unusualMove: true, newsCount: null }));
  assert.equal(notChecked.action, "LONG");
  assert.equal(notChecked.basis, null);
  assert.match(notChecked.notes.join(" "), /no news has been collected/i);

  const thin = decide(input({ setup: directional, unusualMove: true, newsCount: 2 }));
  assert.equal(thin.action, "LONG");
  assert.equal(thin.basis, null);
  assert.match(thin.notes.join(" "), /2 recent stories/);

  const peers = decide(
    input({
      setup: { direction: "up", horizon: "swing", trend: null },
      horizon: { direction: "flat" },
      relStrength: -9,
    }),
  );
  assert.equal(peers.action, "LONG");
  assert.equal(peers.basis, null);
  assert.match(peers.notes.join(" "), /9\.0 points behind its peers/);
});

test("the fall-through does not claim a price sits between averages nobody computed", () => {
  // The fault this file was written for.
  const noSetup = decide(input({ setup: null, horizon: null }));
  assert.equal(noSetup.gate, "incomplete");
  assert.equal(noSetup.basis, "file");
  assert.doesNotMatch(
    noSetup.why.join(" "),
    /between its own averages/,
    "claims a position against averages that were never measured",
  );
  assert.match(noSetup.why.join(" "), /missing data, not a weak reading/);
});

test("the fall-through with a stored setup is evidence, and keeps its wording", () => {
  // A row exists and came back without a direction: price really is between its own averages.
  const measured = decide(input());
  assert.equal(measured.gate, "incomplete");
  assert.equal(measured.basis, "evidence");
  assert.match(measured.why.join(" "), /between its own averages/);
});

test("a withheld direction nothing carries is a WAIT on evidence, not an action", () => {
  // `setup.py` writes `wait` when the trend is clear and the conditions behind it are not all
  // present. That used to be the row most likely to be mislabelled, because the reader saw the
  // same grey WAIT as a dead feed. It is not a WAIT any more: the direction prints, `basis` is
  // null because nothing was withheld, and how little backs it is in the gate and the grade.
  const withheld = decide(
    input({ setup: { direction: "flat", horizon: "swing", trend: "up" }, volumeRatio: 0.4 }),
  );
  // Rule 93: carried by nothing, it falls through to check 9 -- a WAIT whose basis is evidence: the job
  // looked, found a direction, and found nothing behind it.
  assert.equal(withheld.action, "WAIT");
  assert.equal(withheld.gate, "incomplete");
  assert.equal(withheld.basis, "evidence");
});

test("a direction carries no basis at all", () => {
  const long = decide(
    input({
      setup: { direction: "up", horizon: "swing", trend: null },
      horizon: { direction: "up" },
    }),
  );
  assert.equal(long.action, "LONG");
  assert.equal(long.basis, null, "a produced direction withheld nothing");
});

test("every WAIT has a basis, and no direction has one", () => {
  // The invariant stated directly, over every shape above. A WAIT with a null basis would reach
  // the page as neither, which is the state this field exists to make impossible.
  const cases = [
    input({ asOf: null, lastClose: null }),
    input({ sourceSilent: "x" }),
    input({ invalidation: null }),
    input({ asOf: "2026-09-01" }),
    input({ unusualMove: true, newsCount: null }),
    input({ unusualMove: true, newsCount: 1 }),
    input({ setup: null, horizon: null }),
    input(),
    input({ setup: { direction: "up", horizon: "swing", trend: null }, horizon: { direction: "down" } }),
    input({ setup: { direction: "up", horizon: "swing", trend: null }, horizon: { direction: "up" } }),
  ];
  for (const c of cases) {
    const d = decide(c);
    if (d.action === "WAIT") {
      assert.ok(d.basis === "file" || d.basis === "evidence", `${d.gate} has no basis`);
    } else {
      assert.equal(d.basis, null, `${d.gate} is a direction and should carry no basis`);
    }
  }
});
