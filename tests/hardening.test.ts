// What the rule table does at its own edges, and what it must never do anywhere.
//
// Every other test file asserts a rule. This one asserts three properties *of* the rules, and
// they are the properties whose loss is invisible on a page:
//
//   * **the boundaries are where the constants say they are.** A threshold written `>=` and
//     tested only at 2.0 and 0.5 is a threshold nobody has checked. Each one below is asserted
//     at the value itself and at one tick either side, because the whole content of a gate is
//     which side of it a name lands on.
//   * **the same stored row always decides the same way.** `decide` takes `today` as an input
//     and holds no state, so this is already true by construction -- and a construction nobody
//     tests is one a later `Date.now()` or a locale-dependent sort quietly breaks.
//   * **a degenerate row degrades rather than throws.** The rule table runs inside a page
//     render and inside the nightly log. An exception on one malformed row is a blank panel in
//     the first case and a missing session in the second, and neither failure says what it was.
//
// Nothing here needs a database, a network or a clock, for the same reason nothing else in
// tests/ does.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  decide,
  type DecisionInput,
  type Market,
  SHORT_EXPECTANCY,
  SHORT_LATE_AT,
  VOLUME_CONFIRMS_AT,
  ANALOG_SHARE_CONFIRMS,
  ANALOGS_CONFIRM_MIN,
  ASYMMETRY_CLEARS,
  REL_BAND,
  STALE_AFTER_DAYS,
  EVENT_SOON_DAYS,
} from "../lib/decision.ts";
import { marketOf } from "../lib/decisionInput.ts";

/// The stop a valid plan carries for whichever way the row points: below the close for a long,
/// above it for a short. The fixtures used 94 for both, which gave every SHORT a stop below the
/// price -- a plan already invalidated, and exactly the defect `stopCrossed` now refuses. Mirrored
/// here rather than weakened there. An explicit `invalidation` in a test still overrides it.
function stopFor(over: Partial<DecisionInput>): number {
  const s = over.setup;
  const down =
    s?.direction === "down" ||
    s?.trend === "down" ||
    (s?.trend !== "up" && s?.bias === "down");
  return down ? 106 : 94;
}

function base(over: Partial<DecisionInput> = {}): DecisionInput {
  return {
    symbol: "AAPL",
    market: "US",
    asOf: "2026-10-02",
    today: "2026-10-03",
    lastClose: 100,
    setup: { direction: "up", horizon: "swing" },
    horizon: { direction: "up" },
    entry: { low: 98, high: 102 },
    invalidation: stopFor(over),
    target: { method: "structure", low: 108, high: 112, rewardRisk: 1.5 },
    analogs: { count: 12, lowPct: -3.2, highPct: 6.4, medianPct: 1.4, positive: 8 },
    volumeRatio: 1.8,
    relStrength: 1.0,
    unusualMove: false,
    newsCount: 12,
    eventInDays: null,
    sourceSilent: null,
    ...over,
  };
}

/// A stored reward past `ASYMMETRY_CLEARS`: it carries a check 8 trend and confirms nothing, so a thin
/// trend reaches the refusals inside `direction()` (rule 93).
const ASYM = { method: "structure", low: 80, high: 84, rewardRisk: 3 };

// A thin row: nothing confirms, nothing contradicts, so one changed field decides the grade on
// its own and a boundary test measures the boundary rather than the rest of the fixture.
const THIN = {
  horizon: null,
  volumeRatio: 0.5,
  relStrength: 0,
  analogs: null,
  target: null,
} as const;

// --- boundaries: the short gate ---------------------------------------------------------------

test("a fall of exactly SHORT_LATE_AT is late, and a hair under it is not", () => {
  // The constant is `<= -SHORT_LATE_AT`, so the boundary belongs to the gated side. It has to be
  // asserted rather than read: a name sitting exactly on -10.0 is the single most likely value
  // for a rounded figure to take, and which way it falls is the whole of the rule for that name.
  const late = {
    ...THIN,
    target: ASYM,
    market: "Crypto" as const,
    setup: { direction: "flat", horizon: "swing", trend: "down" } as const,
  };
  assert.equal(decide(base({ ...late, r20: -SHORT_LATE_AT })).gate, "short-unbacked");
  assert.equal(decide(base({ ...late, r20: -SHORT_LATE_AT - 0.0001 })).gate, "short-unbacked");
  assert.equal(decide(base({ ...late, r20: -SHORT_LATE_AT + 0.0001 })).action, "SHORT");
  // -0 is a float that compares equal to 0 and is not a fall at all.
  assert.equal(decide(base({ ...late, r20: -0 })).action, "SHORT");
});

test("the fall is reported with the sign the reader expects at the boundary", () => {
  const d = decide(
    base({
      ...THIN,
      target: ASYM,
      market: "Crypto",
      setup: { direction: "flat", horizon: "swing", trend: "down" },
      r20: -SHORT_LATE_AT,
    }),
  );
  assert.match(d.why[1], /already fallen 10\.0%/);
  assert.doesNotMatch(d.why[1], /-10/);
});

test("every market the rules can produce has a short expectancy, and an unknown one is strict", () => {
  // `SHORT_EXPECTANCY[input.market]` with a missing key yields undefined, and `undefined < 0` is
  // false -- so a market that fell out of this table would be waved through the gate silently,
  // which is the one failure mode a lookup like this has.
  const markets: Market[] = ["US", "PSX", "Crypto", "FX", "Commodity", "Other"];
  for (const market of markets) {
    assert.equal(typeof SHORT_EXPECTANCY[market], "number", market);
    assert.ok(Number.isFinite(SHORT_EXPECTANCY[market]), market);
    assert.equal(typeof STALE_AFTER_DAYS[market], "number", market);
    assert.equal(typeof REL_BAND[market], "number", market);
  }
  // An unmeasured market takes the stricter of the two directions a guess could go.
  assert.ok(SHORT_EXPECTANCY.Other < 0);
  assert.equal(SHORT_EXPECTANCY.Other, SHORT_EXPECTANCY.US);
});

test("an industry the seed does not recognise classifies as Other and is gated, not waved through", () => {
  // The ambiguous classification, end to end. `marketOf` has an exhaustive default rather than a
  // cast, so a new exchange added to Industry without a case here lands on the strict side.
  for (const market of ["", "GB", "unknown", "pk", "us"]) {
    assert.equal(marketOf({ assetType: "stock", industry: { market } }), "Other", market);
  }
  assert.equal(marketOf({ assetType: "stock", industry: null }), "Other");
  assert.equal(marketOf({ assetType: "stock" }), "Other");
  const d = decide(
    base({
      ...THIN,
      target: ASYM,
      market: "Other",
      setup: { direction: "flat", horizon: "swing", trend: "down" },
    }),
  );
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "short-unbacked");
});

// --- boundaries: the confirmations --------------------------------------------------------------

test("each confirmation fires exactly at its own constant", () => {
  const thin = { ...THIN, setup: { direction: "up", horizon: "swing" } as const };

  // Volume: `>= VOLUME_CONFIRMS_AT`.
  assert.equal(decide(base({ ...thin, volumeRatio: VOLUME_CONFIRMS_AT })).confidence, "Medium");
  assert.equal(
    decide(base({ ...thin, volumeRatio: VOLUME_CONFIRMS_AT - 0.0001 })).confidence,
    "Low",
  );

  // Peers: `>= REL_BAND[market]`, and the band is read per market rather than as one number.
  const band = REL_BAND.US;
  assert.equal(decide(base({ ...thin, relStrength: band })).confidence, "Medium");
  assert.equal(decide(base({ ...thin, relStrength: band - 0.0001 })).confidence, "Low");

  // Matched days: `>= ANALOGS_CONFIRM_MIN` of them, leaning `>= ANALOG_SHARE_CONFIRMS`, with a
  // median of the right sign. All three are required, so each is broken on its own.
  const atShare = Math.ceil(ANALOGS_CONFIRM_MIN * ANALOG_SHARE_CONFIRMS);
  const confirming = {
    count: ANALOGS_CONFIRM_MIN,
    positive: atShare,
    lowPct: -4,
    highPct: 6,
    medianPct: 0.4,
  };
  assert.equal(decide(base({ ...thin, analogs: confirming })).confidence, "Medium");
  assert.equal(
    decide(base({ ...thin, analogs: { ...confirming, count: ANALOGS_CONFIRM_MIN - 1 } })).confidence,
    "Low",
    "one matched day short of the floor is not a set",
  );
  assert.equal(
    decide(base({ ...thin, analogs: { ...confirming, positive: atShare - 1 } })).confidence,
    "Low",
    "a lean one day short of the share is not a lean",
  );
  assert.equal(
    decide(base({ ...thin, analogs: { ...confirming, medianPct: 0 } })).confidence,
    "Low",
    "a median of exactly zero has no sign, so the set did not lean",
  );
});

test("the asymmetry bypass fires exactly at ASYMMETRY_CLEARS", () => {
  // `asymmetric` is what lets a withheld trend be carried and what names the carrier. The
  // constant is the whole rule, so the row either side of it has to land on opposite sides.
  const withheld = {
    ...THIN,
    setup: { direction: "flat", horizon: "swing", trend: "up" } as const,
  };
  const at = decide(
    base({
      ...withheld,
      target: { method: "structure", low: 120, high: 130, rewardRisk: ASYMMETRY_CLEARS },
    }),
  );
  assert.equal(at.gate, "trend-long");
  const under = decide(
    base({
      ...withheld,
      target: { method: "structure", low: 120, high: 130, rewardRisk: ASYMMETRY_CLEARS - 0.0001 },
    }),
  );
  // Under it nothing carries the trend, and it falls through to check 9 (rule 93).
  assert.equal(under.gate, "incomplete");
});

test("staleness is measured against the market's own limit, at the day it turns", () => {
  for (const market of Object.keys(STALE_AFTER_DAYS) as Market[]) {
    const limit = STALE_AFTER_DAYS[market];
    const asOf = "2026-10-01";
    const onLimit = new Date(Date.UTC(2026, 9, 1) + limit * 86400000)
      .toISOString()
      .slice(0, 10);
    const pastLimit = new Date(Date.UTC(2026, 9, 1) + (limit + 1) * 86400000)
      .toISOString()
      .slice(0, 10);
    assert.notEqual(decide(base({ market, asOf, today: onLimit })).gate, "stale", market);
    assert.equal(decide(base({ market, asOf, today: pastLimit })).gate, "stale", market);
  }
});

test("a dated event is urgent at exactly EVENT_SOON_DAYS and not a day later", () => {
  assert.equal(decide(base({ eventInDays: EVENT_SOON_DAYS })).timeSense, "CARE");
  assert.notEqual(decide(base({ eventInDays: EVENT_SOON_DAYS + 1 })).timeSense, "CARE");
  // Today, and already past. Both are "open across it" rather than one of them being ignored.
  for (const days of [0, -1, -30]) {
    const d = decide(base({ eventInDays: days }));
    assert.equal(d.timeSense, "CARE", String(days));
    assert.ok(d.notes.some((n) => /falls today/.test(n)), String(days));
  }
});

// --- determinism ---------------------------------------------------------------------------------

/// Every input worth varying, as a small set of values each. The product is swept twice.
const AXES: Record<string, unknown[]> = {
  market: ["US", "PSX", "Crypto", "FX", "Commodity", "Other"],
  setup: [
    null,
    { direction: "up", horizon: "swing" },
    { direction: "down", horizon: "swing" },
    { direction: "flat", horizon: "swing", trend: "down" },
    { direction: "unknown", horizon: null, bias: "up" },
  ],
  horizon: [null, { direction: "up" }, { direction: "down" }, { direction: "flat" }],
  volumeRatio: [null, 0.5, VOLUME_CONFIRMS_AT, 3],
  relStrength: [null, -9, 0, 9],
  r20: [null, -SHORT_LATE_AT, -2, 14],
  entryTrigger: [
    null,
    { rule: "squeeze_break", direction: "up" },
    { rule: "vol_flip", direction: "down" },
  ],
  news: [null, { tone: "up", catalyst: false }, { tone: "down", catalyst: true }],
  eventInDays: [null, 0, 2, 40],
  unusualMove: [false, true],
  newsCount: [null, 0, 20],
};

/// One input per combination of a single axis's values against the base row, which is every
/// value of every axis rather than their full product: the product is 6*5*4*4*4*4*3*3*4*2*3 and
/// a test that takes a minute is a test that stops being run.
function sweep(): DecisionInput[] {
  const out: DecisionInput[] = [];
  for (const [key, values] of Object.entries(AXES)) {
    for (const value of values) {
      out.push(base({ [key]: value } as Partial<DecisionInput>));
      out.push(
        base({
          [key]: value,
          analogs: null,
          target: null,
          entry: null,
        } as Partial<DecisionInput>),
      );
    }
  }
  return out;
}

test("the same stored row decides the same way every time it is read", () => {
  // Twice in a row, and then once more after every other input in the sweep has been decided, so
  // a cache or a module-level accumulator between calls would show up as a difference.
  const inputs = sweep();
  const first = inputs.map((i) => JSON.stringify(decide(i)));
  const second = inputs.map((i) => JSON.stringify(decide(i)));
  assert.deepEqual(second, first);
  const third = inputs.map((i) => JSON.stringify(decide(i)));
  assert.deepEqual(third, first);
  assert.ok(inputs.length > 50, "the sweep stopped covering anything");
});

test("the decision does not depend on the order the input's own keys were written in", () => {
  // A row assembled by `bundleFromRow` and one assembled by `bundleFromQuery` carry the same
  // fields in a different order. Nothing should read an object's key order, and the cheapest
  // way to be sure is to reverse it.
  for (const input of sweep()) {
    const reversed = Object.fromEntries(
      Object.entries(input).reverse(),
    ) as unknown as DecisionInput;
    assert.equal(JSON.stringify(decide(reversed)), JSON.stringify(decide(input)), input.symbol);
  }
});

test("the rule table reads no clock, no locale and no randomness", () => {
  // `today` is an input precisely so the table cannot read a clock, and the whole nightly log
  // rests on that: `decide.mjs` passes ONE `today` for the run so a pass started at 23:59 cannot
  // date half its rows to the next day. A `new Date()` anywhere in here would break that
  // silently, and a locale-sensitive comparison would make the answer depend on the runner.
  const src = readFileSync(new URL("../lib/decision.ts", import.meta.url), "utf8");
  const code = src
    .split("\n")
    .filter((l) => !/^\s*(\/\/|\/\/\/|\*)/.test(l))
    .join("\n");
  for (const forbidden of [
    "Date.now",
    "new Date",
    "Math.random",
    "localeCompare",
    "toLocaleString",
    "toLocaleDateString",
    "Intl.",
    "process.env",
  ]) {
    assert.ok(!code.includes(forbidden), `lib/decision.ts reads ${forbidden}`);
  }
});

test("every list ordering ends in a tie-break on the symbol", () => {
  // The property that matters for a stable page is not which row wins a tie but that there are
  // no ties. A comparator returning 0 for two distinct rows leaves their order decided by the
  // order the query happened to return them in, and `ORDER BY` without a unique key does not
  // promise the same order twice -- so a page would reshuffle between two reads of identical
  // data, which reads to a user as the readings having changed.
  //
  // Read out of the source rather than exercised, because `lib/assetClass.ts` imports through
  // the `@/` alias and `node --test` resolves no alias. The three comparators are short enough
  // that the check is exact: each must end by comparing the symbols.
  //
  // NOTE, and it is the one thing here that is not pinned: `localeCompare` with no locale takes
  // the runtime's default collation, so the ORDER of two symbols differing only in case or in
  // punctuation -- `btc-bitcoin`, `AUDUSD=X`, `GC=F` -- can differ between a machine with full
  // ICU and one without. It is a total order either way, which is what stops a page reshuffling
  // against itself; it is not guaranteed to be the SAME total order on two different runtimes.
  const src = readFileSync(new URL("../lib/assetClass.ts", import.meta.url), "utf8");
  for (const name of ["byCloseness", "byConfidence", "byOpportunity"]) {
    const start = src.indexOf(`export function ${name}(`);
    assert.ok(start > 0, `${name} is gone from lib/assetClass.ts`);
    const body = src.slice(start, src.indexOf("\n}", start));
    const breaks =
      body.includes("a.row.symbol.localeCompare(b.row.symbol)") ||
      body.includes("byConfidence(a, b)");
    assert.ok(breaks, `${name} can return 0 for two distinct rows`);
  }
});

// --- degradation ------------------------------------------------------------------------------

test("no degenerate row throws, and every one of them still names a gate", () => {
  // The rule table runs inside a page render and inside the nightly writer. An exception on one
  // malformed row is a blank panel in the first case and a missing session in the second, and
  // neither failure tells anyone which row did it. Every value below has either been seen in the
  // table or is one float operation away from a value that has.
  const degenerate: Partial<DecisionInput>[] = [
    { lastClose: 0 },
    { lastClose: -5 },
    { lastClose: Number.NaN },
    { lastClose: Number.POSITIVE_INFINITY },
    { invalidation: 0 },
    { invalidation: Number.NaN },
    { entry: { low: 102, high: 98 } },
    { entry: { low: Number.NaN, high: Number.NaN } },
    { asOf: "" },
    { asOf: "not-a-date" },
    { asOf: "2026-13-45" },
    { today: "" },
    { symbol: "" },
    { analogs: { count: 0, lowPct: null, highPct: null, medianPct: null, positive: null } },
    { analogs: { count: -4, lowPct: 0, highPct: 0, medianPct: 0, positive: 99 } },
    { analogs: { count: 10, lowPct: 0, highPct: 0, medianPct: Number.NaN, positive: 7 } },
    { volumeRatio: Number.NaN },
    { volumeRatio: Number.POSITIVE_INFINITY },
    { volumeRatio: -1 },
    { relStrength: Number.NaN },
    { r20: Number.NaN },
    { target: { method: "", low: Number.NaN, high: Number.NaN, rewardRisk: Number.NaN } },
    { target: { method: "structure", low: 1, high: 0, rewardRisk: Number.POSITIVE_INFINITY } },
    { newsCount: -1 },
    { eventInDays: Number.NaN },
    { entryTrigger: { rule: "", direction: "up" } },
    { sourceSilent: "" },
  ];
  for (const over of degenerate) {
    const label = JSON.stringify(over);
    const d = decide(base(over));
    assert.ok(["LONG", "SHORT", "WAIT"].includes(d.action), label);
    assert.ok(d.gate.length > 0, label);
    assert.ok(d.why.length > 0, label);
    assert.ok(["High", "Medium", "Low"].includes(d.confidence), label);
    // No sentence a reader sees may contain a float artefact. "NaN" on a page is worse than a
    // blank one, because it reads as a number that was measured.
    for (const line of [...d.why, ...d.missing, ...d.notes, d.measured]) {
      assert.doesNotMatch(line, /NaN|Infinity|undefined|null/, `${label} -> ${line}`);
    }
  }
});

test("an entirely empty row is a WAIT that names what is absent", () => {
  // The state of every asset on a fresh database, and the one the lists must survive.
  const empty = decide({
    symbol: "NEW",
    market: "Other",
    asOf: null,
    today: "2026-10-03",
    lastClose: null,
    setup: null,
    horizon: null,
    entry: null,
    invalidation: null,
    analogs: null,
    unusualMove: false,
    newsCount: null,
    eventInDays: null,
    sourceSilent: null,
  });
  assert.equal(empty.action, "WAIT");
  assert.equal(empty.gate, "no-prices");
  assert.ok(empty.missing.length > 0);
  assert.equal(empty.plan, null);
  assert.equal(empty.developing, null);
});

test("a WAIT always carries a reason and a direction always carries a plan", () => {
  // The two shape invariants every surface relies on. A WAIT with an empty `missing` and an
  // empty `why` is the silent blank panel this whole module exists to prevent, and a printed
  // direction with no plan is a recommendation with nowhere to be wrong.
  for (const input of sweep()) {
    const d = decide(input);
    if (d.action === "WAIT") {
      assert.ok(d.why.length > 0, `silent WAIT at ${d.gate}`);
      assert.equal(d.plan, null, `a WAIT carries a plan at ${d.gate}`);
      assert.ok(d.basis === "file" || d.basis === "evidence", `no basis at ${d.gate}`);
    } else {
      assert.ok(d.plan !== null, `no plan at ${d.gate}`);
      assert.equal(typeof d.plan?.invalidation, "number", `no stop at ${d.gate}`);
      assert.equal(d.developing, null, `a direction is still developing at ${d.gate}`);
      assert.equal(d.basis, null, `a direction carries a wait basis at ${d.gate}`);
    }
  }
});
