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

test("every gate that holds a measurement which does not confirm reports evidence", () => {
  const mixed = decide(
    input({
      setup: { direction: "up", horizon: "swing", trend: null },
      horizon: { direction: "down" },
    }),
  );
  assert.equal(mixed.gate, "mixed-horizons");
  assert.equal(mixed.basis, "evidence");

  const peers = decide(
    input({
      setup: { direction: "up", horizon: "swing", trend: null },
      horizon: { direction: "flat" },
      relStrength: -9,
    }),
  );
  assert.equal(peers.gate, "peers-against");
  assert.equal(peers.basis, "evidence");
});

test("an unusual move splits on whether the news was ever looked at", () => {
  // The one gate that is genuinely both, and the input already knows which. A null count means no
  // feed answered, so nothing was weighed. A low count means the feeds answered and there was
  // little there, which is a measurement.
  const notChecked = decide(input({ unusualMove: true, newsCount: null }));
  assert.equal(notChecked.gate, "unexplained-move");
  assert.equal(notChecked.basis, "file");
  assert.match(notChecked.why.join(" "), /not checked/);
  assert.ok(notChecked.missing.length, "a file gate has to name what is absent");

  const thin = decide(input({ unusualMove: true, newsCount: 2 }));
  assert.equal(thin.gate, "unexplained-move");
  assert.equal(thin.basis, "evidence");
  assert.match(thin.why.join(" "), /news thin/);
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

test("a withheld direction is evidence, never a missing file", () => {
  // `setup.py` writes `wait` when the trend is clear and the conditions behind it are not all
  // present. That is a measurement that came back negative, and the most likely row to be
  // mislabelled because the reader sees the same grey WAIT.
  const withheld = decide(
    input({ setup: { direction: "flat", horizon: "swing", trend: "up" }, volumeRatio: 0.4 }),
  );
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
