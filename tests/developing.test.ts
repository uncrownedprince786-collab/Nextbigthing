// The developing read: a direction the data shows and the rules will not act on yet.
//
// 162 of 266 swing rows on 2026-10-07 sit in state `wait`, which is not the neutral state -- it
// means the trend is clear and not all the conditions behind it are present. 101 of those fail on
// one leg, volume. Before this they reached the reader as entries 13 to 160 of a WAIT list ordered
// by data faults, which is the same as not reaching them at all.
//
// These tests pin the two things that make the list honest: it never becomes an action, and its
// order is a measured distance from a stored threshold rather than a feeling about which names
// look interesting.

import assert from "node:assert/strict";
import test from "node:test";

import { decide, VOLUME_CONFIRMS_AT, ANALOGS_CONFIRM_MIN, type DecisionInput } from "../lib/decision.ts";
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

test("the conditions string jobs/setup.py writes parses into its verdicts", () => {
  const v = conditionVerdicts(STORED_CONDITIONS);
  assert.equal(v.get("trend"), "up");
  // "(0.93, fail)" -- the verdict is the last comma-separated token, which is what lets a value
  // and a verdict share one bracket without a rule per condition.
  assert.equal(v.get("volume"), "fail");
  assert.equal(v.get("relative"), "pass");
  // A condition that states a value and passes no judgement is left out, never defaulted: a
  // default would manufacture agreement out of a sentence that stated none.
  assert.equal(v.has("position"), false);
});

test("a withheld direction is recovered, and absent is not mixed", () => {
  assert.equal(trendDirectionOf(STORED_CONDITIONS), "up");
  assert.equal(trendDirectionOf("trend: close 10 vs 20d 10 vs 50d 10 (mixed)"), "mixed");
  // Rule 21: a row with no trend verdict is absent, which is a different answer from a trend
  // that was measured and came back without a direction.
  assert.equal(trendDirectionOf(null), null);
  assert.equal(trendDirectionOf("position: 40% of the way up its range"), null);
});

test("a developing read names the direction and stays a WAIT", () => {
  const d = decide(input());
  // The whole point: the reader is told which way, and is not told to act.
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "incomplete");
  assert.equal(d.developing?.direction, "up");
  assert.equal(d.developing?.would, "LONG");
  assert.equal(d.confidence, "Low", "a refusal is not a confident anything");
  assert.match(d.why[0], /potential LONG/);
});

test("a falling trend develops towards a SHORT", () => {
  const d = decide(input({ setup: { direction: "flat", horizon: "swing", trend: "down" } }));
  assert.equal(d.developing?.would, "SHORT");
  assert.match(d.why[0], /falling trend/);
});

test("what it is waiting on is named with the stored value", () => {
  const d = decide(input());
  const vol = d.developing?.waitingOn.find((w) => w.includes("Volume"));
  assert.ok(vol, "the failing leg is not named");
  // The number the reader can check, and the threshold it has to clear. Not "volume is weak".
  assert.match(vol, /0\.93x/);
  assert.match(vol, new RegExp(String(VOLUME_CONFIRMS_AT)));
});

test("closeness measures the nearest leg against its own threshold", () => {
  // 0.93 / 1.2 = 0.775. This is the ordering key, and ordering is the point of the list: a name
  // at 1.15x of the gate is a different proposition from one at 0.3x.
  const near = decide(input({ volumeRatio: 1.15 })).developing;
  const far = decide(input({ volumeRatio: 0.3 })).developing;
  assert.ok(near!.closeness! > far!.closeness!);
  assert.equal(Math.round(near!.closeness! * 100) / 100, 0.96);
});

test("an unmeasurable absence is null closeness and never sorts as nearly there", () => {
  // An FX pair publishes no volume at all -- a fact about the instrument, not a quiet session.
  // Null rather than 0, because "cannot be measured" is not "measured and far away".
  const d = decide(input({ market: "FX", volumeRatio: null, relStrength: null }));
  assert.equal(d.developing?.closeness, null);
  assert.ok(d.developing?.waitingOn.some((w) => w.includes("No volume is published")));
});

test("a thin analog set reports the count it has, not a blanket absence", () => {
  const d = decide(input({ analogs: { count: 4, lowPct: -2, highPct: 3 } }));
  const line = d.developing?.waitingOn.find((w) => w.includes("similar past days"));
  assert.match(line!, new RegExp(`Only 4 .*${ANALOGS_CONFIRM_MIN} are needed`));
});

test("no developing read without a stored trend direction", () => {
  // `none` is the genuinely neutral state: price between its own averages. Printing a direction
  // for it would be the panel inventing one.
  const d = decide(input({ setup: { direction: "unknown", horizon: "swing", trend: null } }));
  assert.equal(d.developing, null);
  assert.match(d.why[0], /no clear direction/);
  // And a trend measured without a direction is not a developing anything either.
  assert.equal(decide(input({ setup: { direction: "flat", horizon: "swing", trend: "mixed" } })).developing, null);
});

test("a gate above the fall-through never produces a developing read", () => {
  // Each of these is either a data fault or a reason that argues against the direction, and the
  // reader has already been given it. A stale close is not a forming opportunity.
  const stale = decide(input({ asOf: "2026-09-01" }));
  assert.equal(stale.gate, "stale");
  assert.equal(stale.developing, null);

  const silent = decide(input({ sourceSilent: "Yahoo Finance daily closes" }));
  assert.equal(silent.developing, null);

  const noLevel = decide(input({ invalidation: null }));
  assert.equal(noLevel.gate, "no-invalidation");
  assert.equal(noLevel.developing, null);

  // Peers arguing the other way is a verdict about the evidence, not an incomplete set of it.
  const peers = decide(
    input({ setup: { direction: "up", horizon: "swing", trend: "up" }, relStrength: -9 }),
  );
  assert.equal(peers.gate, "peers-against");
  assert.equal(peers.developing, null);
});

test("a direction that arrived is not developing", () => {
  const long = decide(input({ setup: { direction: "up", horizon: "swing", trend: "up" } }));
  assert.equal(long.action, "LONG");
  assert.equal(long.developing, null, "an action and a forming read are different states");
});
