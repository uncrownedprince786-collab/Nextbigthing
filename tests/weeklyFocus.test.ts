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
  weeklyTarget,
  targetMethodLabel,
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
    row: {
      symbol: "AAA", name: "Aaa", currency: "USD",
      closeDate: new Date("2026-10-07"),
      swing: { targets: [] },
      longer: null,
      ...row,
    },
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

const target = (method: string, low = 100, high = 110) => ({
  method, low, high, distancePct: 5, rewardRisk: 1.5, note: `measured from ${method}`,
});

test("the exit-if-working target is one measured method, never an average", () => {
  // Rule 24: three methods that disagree are three answers, and their mean is a fourth that
  // nothing measured. So one is chosen and its method is named beside the number.
  const s = scored({}, { swing: { targets: [target("analog", 200, 300), target("structure", 120, 120)] } });
  const got = weeklyTarget(s);
  assert.equal(got?.method, "structure", "structure is the level the market actually turned at");
  assert.equal(got?.low, 120);
  // Nothing anywhere produces a blended number.
  assert.notEqual(got?.low, 160);
});

test("the preference order is volatility, then structure, then analog", () => {
  // Structure led until 2026-10-09 and now follows. The reason is in lib/target.ts: against the
  // volatility stop, the nearest level a series already turned at offered a median reward of
  // 0.41x the risk over 446 setups where the volatility target offered 2.04x -- and the
  // volatility target is the one the stop width was backtested against.
  const all = (...m: string[]) => scored({}, { swing: { targets: m.map((x) => target(x)) } });
  assert.equal(weeklyTarget(all("analog", "volatility", "structure"))?.method, "volatility");
  assert.equal(weeklyTarget(all("analog", "structure"))?.method, "structure");
  assert.equal(weeklyTarget(all("analog"))?.method, "analog");
});

test("no stored target: a projection at twice the risk, named as one, never a measured method", () => {
  // Since 2026-10-11 every active call shows an exit (the owner's rule). Where the job measured none on
  // the call's side, the exit is projected at 2 x the risk from the entry level and printed as a
  // projection; it never borrows a measured method's name.
  for (const s of [scored({}, { swing: { targets: [] } }), scored({}, { swing: null, longer: null })]) {
    const t = weeklyTarget(s);
    assert.equal(t?.method, "projection");
    assert.equal(t?.rewardRisk, 2);
  }
});

test("a target is read off the longer setup when there is no swing one", () => {
  const s = scored({}, { swing: null, longer: { targets: [target("volatility", 50, 50)] } });
  assert.equal(weeklyTarget(s)?.method, "volatility");
});

test("every method has reader-facing words, and an unknown one falls back to itself", () => {
  for (const m of ["structure", "volatility", "analog"]) {
    assert.notEqual(targetMethodLabel(m), m, `${m} is shown to a reader as the raw method name`);
    assert.ok(targetMethodLabel(m).length > 8);
  }
  assert.equal(targetMethodLabel("something-new"), "something-new");
});

test("the target comes from the setup the decision actually rested on", () => {
  // `pickSetup` takes the first DIRECTIONAL row in horizon order, so a name whose swing read is
  // `wait` and whose longer read is `buy` was decided on the longer one. Reading swing-first
  // printed "No clear target stored" for exactly those names while the targets sat on the setup
  // the verdict came from -- live on HMC and MU.
  const s = scored({}, {
    swing: { state: "wait", targets: [] },
    longer: { state: "buy", targets: [target("structure", 42, 42)] },
  });
  assert.equal(weeklyTarget(s)?.method, "structure");
  assert.equal(weeklyTarget(s)?.low, 42);

  // And when the swing row IS the directional one, it still wins.
  const swingFirst = scored({}, {
    swing: { state: "buy", targets: [target("structure", 20, 20)] },
    longer: { state: "buy", targets: [target("structure", 99, 99)] },
  });
  assert.equal(weeklyTarget(swingFirst)?.low, 20);
});

test("one grade's slots are spread across the markets before any market gets a second", () => {
  // Measured on the live site at 477 names: the short side came back six of six Pakistani,
  // because that is where the best evidenced shorts happened to sit. Thirty-five qualifying
  // shorts existed. A reader who follows US names was shown a side with nothing in it for them,
  // and nothing on the page said why.
  const rows = [
    ...["P1", "P2", "P3", "P4", "P5", "P6", "P7"].map((s) =>
      scored({ confidence: "High" }, { symbol: s }),
    ).map((x) => ({ ...x, market: "PSX" }) as typeof x),
    ...["U1", "U2"].map((s) => scored({ confidence: "High" }, { symbol: s })),
  ];
  const got = weeklyFocus(rows as never[]);
  const markets = got.long.map((s) => s.market);
  assert.equal(got.long.length, WEEKLY_MAX_PER_SIDE);
  assert.ok(markets.includes("US"), "a market with a qualifying name must reach the block");
  assert.equal(markets.filter((m) => m === "US").length, 2, "both US names fit before a seventh PSX one");
  assert.equal(got.longTotal, 9, "the total still counts everything that qualified");
});

test("balance never lifts a weaker grade over a stronger one", () => {
  // The block's first promise is that what is shown is the best evidenced. Spreading across
  // markets is a tie-break between equals; a Medium name from an absent market must not displace
  // a High one, because that would make the block a quota rather than a reading.
  const rows = [
    ...["P1", "P2", "P3", "P4", "P5", "P6"].map((s) =>
      ({ ...scored({ confidence: "High" }, { symbol: s }), market: "PSX" }),
    ),
    { ...scored({ confidence: "Medium" }, { symbol: "U1" }), market: "US" },
  ];
  const got = weeklyFocus(rows as never[]);
  assert.equal(got.long.length, WEEKLY_MAX_PER_SIDE);
  assert.ok(
    got.long.every((s) => s.decision.confidence === "High"),
    "a Medium name displaced a High one to balance the markets",
  );
});

test("a target on the wrong side of the call is never shown, and a resolved call's reward is its own", async () => {
  const { targetForCall } = await import("../lib/target.ts");
  const t = { method: "structure", low: 120, high: 125, distancePct: null, rewardRisk: 3 };
  const long = { action: "LONG", entry: { low: 100, high: 100 }, invalidation: 90, gate: "long" };
  // Kept, with its reward:risk measured against the stop the call carries: (120 - 100) / (100 - 90).
  assert.deepEqual(targetForCall(t, long), { ...t, rewardRisk: 2 }, "a long's target above the entry is kept, re-measured");
  // A close through a long's stop resolved to SHORT: the long's target sits above the price, so it is
  // not shown -- the exit is a projection at 2 x the risk below the entry instead.
  const short = { action: "SHORT", entry: { low: 100, high: 100 }, invalidation: 105, gate: "forced-stop-crossed" };
  assert.deepEqual(targetForCall(t, short), { method: "projection", low: 90, high: 90, distancePct: null, rewardRisk: 2 });
  // A short whose projection would reach zero or below has none.
  assert.equal(targetForCall(null, { ...short, invalidation: 160 }), null);
  // A resolved short with a target below: reward:risk against its own stop, 10 / 5.
  const below = { ...t, low: 88, high: 90, rewardRisk: 9 };
  assert.equal(targetForCall(below, short)?.rewardRisk, 2);
  assert.equal(targetForCall(below, { ...short, invalidation: null })?.rewardRisk, null);
});
