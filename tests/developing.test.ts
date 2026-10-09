// The withheld direction, and what became of it.
//
// `jobs/setup.py` writes state `wait` when the trend is clear and not all the conditions behind
// it are present -- 250 of 477 swing rows on 2026-10-09. Rule 40 made that direction visible as a
// "developing" read, rule 45 taught the table to act on it when one stored figure carried it, and
// on 2026-10-09 the carrier requirement went too: **every measured direction now prints as an
// action**, with `confidence` carrying how much backs it and the gate recording whether anything
// did.
//
// So `Decision.developing` is no longer reachable: everything that could produce one now produces
// a direction instead. These tests pin that contract rather than the old one -- a measured
// direction never comes back as a refusal, the weaker reading is never called a trend, and the
// conditions the old list named are still named, in `missing`, on the direction itself.
//
// `developingRead` is kept rather than deleted because the rule it implements is sound and the
// decision to act on every direction is a policy that may move again. If it stays, that function
// and the Forming list are dead and should go -- see brain.md 50.

import assert from "node:assert/strict";
import test from "node:test";

import {
  decide,
  VOLUME_CONFIRMS_AT,
  ANALOGS_CONFIRM_MIN,
  type DecisionInput,
} from "../lib/decision.ts";
import { conditionVerdicts, trendDirectionOf } from "../lib/setupConditions.ts";

/// The exact string `jobs/setup.py` writes, down to the spacing. If this stops parsing, the two
/// parsers of one format have drifted -- see rule 23 and the header of lib/setupConditions.ts.
const STORED_CONDITIONS =
  "trend: close 118.40 vs 20d 115.02 vs 50d 110.77 (up) | " +
  "volume: 0.93x its 20-session average (0.93, fail) | " +
  "relative: 1.4 points vs its industry over 20 sessions (1.4, pass) | " +
  "position: 71% of the way up its 60-session range | " +
  "news: tone positive, catalyst no, 11 recent stories (pass)";

function input(over: Partial<DecisionInput> = {}): DecisionInput {
  return {
    symbol: "TEST",
    market: "US",
    asOf: "2026-10-07",
    today: "2026-10-07",
    lastClose: 118.4,
    // state `wait` reaches the rule table as direction "flat": measured, and withheld.
    setup: { direction: "flat", horizon: "swing", trend: "up" },
    horizon: null,
    entry: null,
    invalidation: 110,
    analogs: null,
    volumeRatio: 0.93,
    relStrength: 1.4,
    unusualMove: false,
    newsCount: 11,
    eventInDays: null,
    sourceSilent: null,
    ...over,
  };
}

test("a measured direction is an action now, never a developing read", () => {
  const up = decide(input({ setup: { direction: "flat", horizon: "swing", trend: "up" } }));
  assert.equal(up.action, "LONG");
  assert.equal(up.developing, null);

  // The short side is the one place a direction can still be refused, and the fixture's market
  // is US -- where shorts measured -0.11R with nothing behind them. One confirmation is all the
  // gate asks for, so this gives it the peer reading and the direction prints.
  const down = decide(
    input({
      setup: { direction: "flat", horizon: "swing", trend: "down" },
      relStrength: -9,
    }),
  );
  assert.equal(down.action, "SHORT");
  assert.equal(down.developing, null);

  // Without it, the gate holds it and still produces no developing read: the contract this file
  // pins is that a direction and a forming read are never both set, whichever way it goes.
  const gated = decide(input({ setup: { direction: "flat", horizon: "swing", trend: "down" } }));
  assert.equal(gated.action, "WAIT");
  assert.equal(gated.gate, "short-unbacked");
  assert.equal(gated.developing, null);
});

test("with nothing confirming it, the gate says so and the grade says so", () => {
  // The two places the old refusal's information went. A gate is one bit; the grade has three
  // values and `missing` names every absent confirmation with its own stored figure.
  const d = decide(
    input({
      setup: { direction: "flat", horizon: "swing", trend: "up" },
      volumeRatio: 0.93,
      relStrength: 0,
      analogs: null,
    }),
  );
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "unconfirmed-long");
  assert.equal(d.confidence, "Low");
  assert.ok(
    d.missing.some((m) => /similar past days/.test(m)),
    d.missing.join(" | "),
  );
});

test("one stored figure moves the gate and the grade, not the action", () => {
  const base = {
    setup: { direction: "flat", horizon: "swing", trend: "up" } as const,
    relStrength: 0,
    analogs: null,
  };
  const bare = decide(input({ ...base, volumeRatio: 0.93 }));
  const carried = decide(input({ ...base, volumeRatio: VOLUME_CONFIRMS_AT + 0.5 }));

  assert.equal(bare.action, carried.action);
  assert.equal(bare.gate, "unconfirmed-long");
  assert.equal(carried.gate, "trend-long");
  assert.equal(bare.confidence, "Low");
  assert.equal(carried.confidence, "Medium");
});

test("a direction still needs a level to be wrong at", () => {
  // The one refusal that did not go, and the reason it did not: a plan with no price at which it
  // is wrong is the single output this table must never print, whatever else is measured.
  const d = decide(
    input({ setup: { direction: "flat", horizon: "swing", trend: "up" }, invalidation: null }),
  );
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "no-invalidation");
});

test("no measured direction at all is still a WAIT", () => {
  // 8 names of 477 on 2026-10-09. A mixed trend with no bias beside it names no side, and a side
  // chosen here would be this file's choice rather than a measurement.
  for (const setup of [
    null,
    { direction: "unknown", horizon: "swing", trend: null } as const,
    { direction: "unknown", horizon: "swing", trend: "mixed", bias: "mixed" } as const,
  ]) {
    const d = decide(input({ setup }));
    assert.equal(d.action, "WAIT", JSON.stringify(setup));
  }
});

test("the stored condition format still parses, which is what rule 23 is about", () => {
  // Unchanged in substance: two parsers read this format and a horizon written in a new one has
  // to break both rather than silently producing a direction from nothing.
  assert.equal(trendDirectionOf(STORED_CONDITIONS), "up");
  const found = conditionVerdicts(STORED_CONDITIONS);
  assert.equal(found.get("volume"), "fail");
  assert.equal(found.get("relative"), "pass");
  assert.equal(found.size >= 4, true);
});

test("ANALOGS_CONFIRM_MIN is still the floor the analog leg will not grade under", () => {
  const thin = decide(
    input({
      setup: { direction: "flat", horizon: "swing", trend: "up" },
      analogs: { count: ANALOGS_CONFIRM_MIN - 1, lowPct: -2, highPct: 3, medianPct: 1, positive: 5 },
    }),
  );
  assert.equal(thin.plan?.baseRate, null);
});
