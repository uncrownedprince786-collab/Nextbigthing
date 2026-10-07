// The weekly block subtracts; it never promotes.
//
// The risk this file exists for is a specific one. A "top picks" section is the place where a site
// quietly grows a second rule table: one more filter, one more ordering, and a name appears there
// that the main list never acted on. Every test below pins the same property from a different
// side — nothing reaches this block that the rule table did not already print as LONG or SHORT.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  qualifiesForWeek,
  weeklyFocus,
  weeklyWhy,
  byWeeklyFocus,
  WEEKLY_MAX_PER_SIDE,
} from "../lib/weeklyFocus.ts";

type Any = Parameters<typeof qualifiesForWeek>[0];

function scored(over: Record<string, unknown> = {}, row: Record<string, unknown> = {}): Any {
  const d = {
    action: "LONG",
    why: ["Setup is up on the swing view.", "Longer view agrees.", "Confirmed by volume."],
    entry: { low: 10, high: 12 },
    invalidation: 9,
    timeSense: "NOW",
    confidence: "High",
    missing: [],
    measured: "",
    gate: "long",
    developing: null,
    ...over,
  };
  return {
    row: { symbol: "AAA", name: "Aaa", currency: "USD", closeDate: new Date("2026-10-07"), ...row },
    market: "US",
    decision: d,
  } as unknown as Any;
}

test("a WAIT never reaches the block, including one with a direction forming", () => {
  // The single most important line in the file. `developing` carries a real direction and a real
  // distance, and the rule table deliberately refuses to act on it. A block headed "this week" is
  // exactly where that refusal would be hardest for a reader to see.
  assert.equal(qualifiesForWeek(scored({ action: "WAIT", gate: "incomplete" })), false);
  assert.equal(
    qualifiesForWeek(
      scored({
        action: "WAIT",
        gate: "incomplete",
        confidence: "High",
        developing: { direction: "up", would: "LONG", waitingOn: ["volume"], closeness: 0.99 },
      }),
    ),
    false,
  );
});

test("Low confidence is left in the main list", () => {
  // Low means nothing confirmed the direction beyond the direction itself. Those names are still
  // published — they are just not held up here.
  assert.equal(qualifiesForWeek(scored({ confidence: "Low" })), false);
  assert.equal(qualifiesForWeek(scored({ confidence: "Medium" })), true);
  assert.equal(qualifiesForWeek(scored({ confidence: "High" })), true);
});

test("a name with no level to be wrong at cannot appear", () => {
  // A reader cannot size or exit it. The rule table already refuses this at gate 4; the check is
  // repeated rather than trusted, because the cost of being wrong in this block is a trade.
  assert.equal(qualifiesForWeek(scored({ invalidation: null })), false);
  assert.equal(qualifiesForWeek(scored({ entry: null })), false);
});

test("both directions and every market are eligible", () => {
  assert.equal(qualifiesForWeek(scored({ action: "SHORT", gate: "short" })), true);
  for (const market of ["US", "PSX", "Crypto", "FX", "Commodity"]) {
    const s = scored();
    (s as unknown as { market: string }).market = market;
    assert.equal(qualifiesForWeek(s), true, `${market} was excluded`);
  }
});

test("High sorts above Medium, and an actionable close above one still waiting", () => {
  const high = scored({ confidence: "High" }, { symbol: "HIGH" });
  const medium = scored({ confidence: "Medium" }, { symbol: "MED" });
  assert.ok(byWeeklyFocus(high, medium) < 0);

  const now = scored({ timeSense: "NOW" }, { symbol: "NOW" });
  const level = scored({ timeSense: "WAIT FOR LEVEL" }, { symbol: "LVL" });
  const care = scored({ timeSense: "CARE" }, { symbol: "CARE" });
  assert.ok(byWeeklyFocus(now, care) < 0);
  assert.ok(byWeeklyFocus(care, level) < 0);
});

test("a fresher close breaks a tie, and never outranks evidence", () => {
  const stale = scored({ confidence: "High" }, { symbol: "OLD", closeDate: new Date("2026-10-01") });
  const fresh = scored({ confidence: "High" }, { symbol: "NEW", closeDate: new Date("2026-10-07") });
  assert.ok(byWeeklyFocus(fresh, stale) < 0);
  // But a fresher Medium must not jump a staler High.
  const freshMedium = scored(
    { confidence: "Medium" },
    { symbol: "FM", closeDate: new Date("2026-10-07") },
  );
  assert.ok(byWeeklyFocus(stale, freshMedium) < 0);
});

test("the cap truncates and the totals still say what was left out", () => {
  const many = Array.from({ length: 9 }, (_, i) =>
    scored({ confidence: "High" }, { symbol: `L${i}` }),
  );
  const got = weeklyFocus(many);
  assert.equal(got.long.length, WEEKLY_MAX_PER_SIDE);
  assert.equal(got.longTotal, 9, "the block would claim to be the whole list");
  assert.equal(got.short.length, 0);
  assert.equal(got.shortTotal, 0);
});

test("fewer than the cap is returned as fewer, never padded", () => {
  // The rule that keeps a quiet day honest. Padding to six a side would mean reaching into the
  // Low-confidence names, which is inventing confidence the data did not produce.
  const two = [scored({}, { symbol: "A" }), scored({ confidence: "Low" }, { symbol: "B" })];
  const got = weeklyFocus(two);
  assert.equal(got.long.length, 1);
  assert.equal(got.longTotal, 1);
});

test("every name in the block is one the rule table already acted on", () => {
  // The property stated directly, over a mixed set.
  const mixed = [
    scored({ action: "WAIT", gate: "incomplete", confidence: "Low" }, { symbol: "W1" }),
    scored({ action: "LONG", confidence: "High" }, { symbol: "L1" }),
    scored({ action: "SHORT", gate: "short", confidence: "Medium" }, { symbol: "S1" }),
    scored({ action: "WAIT", gate: "stale", confidence: "Low" }, { symbol: "W2" }),
  ];
  const got = weeklyFocus(mixed);
  for (const s of [...got.long, ...got.short]) {
    assert.notEqual(s.decision.action, "WAIT");
  }
  assert.deepEqual(got.long.map((s) => s.row.symbol), ["L1"]);
  assert.deepEqual(got.short.map((s) => s.row.symbol), ["S1"]);
});

test("the why keeps the confirmation line, not the middle one", () => {
  // The bug this pins was live on the page: HMC and MU printed "Only one time frame points
  // anywhere, so nothing confirms it" under a High confidence chip, because taking the first two
  // lines dropped the third -- the one saying volume and the analog set did confirm. A line that
  // contradicts the grade beside it is worse than no line.
  assert.deepEqual(weeklyWhy(scored()), [
    "Setup is up on the swing view.",
    "Confirmed by volume.",
  ]);
  // Two or fewer are kept as they are.
  assert.deepEqual(weeklyWhy(scored({ why: ["Setup is down.", "Confirmed by volume."] })), [
    "Setup is down.",
    "Confirmed by volume.",
  ]);
  assert.deepEqual(weeklyWhy(scored({ why: [] })), []);
});
