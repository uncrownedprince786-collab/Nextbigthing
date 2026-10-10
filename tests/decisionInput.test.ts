// The translation from stored rows to decision inputs, and the product rules.
//
// These exist because every bug this layer can have is a silent one: a mismapped state turns a WAIT
// into a LONG, and nothing throws. The market test in particular guards a real trap in the data.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  coverageLabelFor,
  daysUntil,
  directionOfState,
  entryZone,
  isUnusualMove,
  marketOf,
  pickAnalog,
  pickSetup,
  toDecisionInput,
  todayISO,
  bundleFromQuery,
  bundleFromRow,
  type DecisionBundle,
  type QueryRow,
} from "../lib/decisionInput.ts";
import { decideProduct, whereToCheck, type ProductDecisionInput } from "../lib/productDecision.ts";
import { decide } from "../lib/decision.ts";
import { pickTarget } from "../lib/target.ts";

test("setup states map to directions, and absence is not neutrality", () => {
  assert.equal(directionOfState("buy"), "up");
  assert.equal(directionOfState("short"), "down");
  // A measured neutral reading.
  assert.equal(directionOfState("wait"), "flat");
  // No reading at all. If this returned "flat" the rule table could not tell them apart.
  assert.equal(directionOfState("none"), "unknown");
  assert.equal(directionOfState(null), "unknown");
  assert.equal(directionOfState("something new"), "unknown");
});

test("market comes from the industry, never from the symbol", () => {
  assert.equal(marketOf({ assetType: "crypto", industry: { market: "US" } }), "Crypto");
  assert.equal(marketOf({ assetType: "stock", industry: { market: "PK" } }), "PSX");
  assert.equal(marketOf({ assetType: "stock", industry: { market: "US" } }), "US");
  assert.equal(marketOf({ assetType: "stock", industry: null }), "Other");
  // The trap: PSX is also a US ticker (Phillips 66). Reading the market off a symbol would file
  // this one in Pakistan and then apply the wrong staleness rule to it.
  assert.equal(marketOf({ assetType: "stock", industry: { market: "US" } }), "US");
});

test("every market whose feed is watched can be named when it goes silent", () => {
  assert.equal(coverageLabelFor("US"), "Yahoo Finance daily closes");
  assert.equal(coverageLabelFor("PSX"), "PSX daily closing files");
  // Crypto returned null until jobs/audit.py started watching the venue chain. The label is the
  // chain rather than a venue: Binance has been dead for ~347 days while every coin has a current
  // close from Coinbase, so a per-venue watch would report silence that is not there.
  assert.equal(coverageLabelFor("Crypto"), "crypto daily closes");
  assert.equal(coverageLabelFor("Other"), null);
});

test("a silent crypto chain is named by gate 3, not left to the staleness gate", () => {
  const health = [{ source: "crypto daily closes", status: "silent" }];
  const coin = row({ symbol: "BTC", assetType: "crypto", market: "US", closeDate: "2026-10-02" });
  const input = toDecisionInput(bundleFromRow(coin, health), "2026-10-03");
  assert.equal(input.sourceSilent, "crypto daily closes");
  const d = decide(input);
  assert.equal(d.gate, "source-silent");
  assert.match(d.why[0], /crypto daily closes/);
});

test("the entry zone is the range the two stored levels span", () => {
  assert.deepEqual(entryZone(100, 94), { low: 94, high: 100 });
  // Order of the inputs must not matter: a short has invalidation above entry.
  assert.deepEqual(entryZone(94, 100), { low: 94, high: 100 });
  assert.equal(entryZone(100, null), null);
  assert.equal(entryZone(null, 94), null);
  // A zero-width zone is not a zone, and would make "NOW" mean "to the cent".
  assert.equal(entryZone(100, 100), null);
});

test("a direction is preferred over a flat swing row, and the order is swing then longer", () => {
  // This replaced a test asserting the opposite. Preferring swing unconditionally is what made
  // every live asset read WAIT: see the production note on `pickSetup`.
  const rows = [
    { horizon: "intraday", state: "buy", entryLevel: null, invalidateLevel: null },
    { horizon: "swing", state: "wait", entryLevel: null, invalidateLevel: null },
    { horizon: "longer", state: "short", entryLevel: null, invalidateLevel: null },
  ];
  // Longer beats intraday: the same direction read over a longer window needs acting on less
  // urgently but survives a single session.
  assert.equal(pickSetup(rows)?.horizon, "longer");
  assert.equal(pickSetup([rows[0], rows[1]])?.horizon, "intraday");
  // One row, no direction: returned anyway, as the measured flat it is.
  assert.equal(
    pickSetup([{ horizon: "longer", state: "none", entryLevel: null, invalidateLevel: null }])
      ?.horizon,
    "longer",
  );
  assert.equal(pickSetup([]), null);
});

test("the five day analog is preferred, else the best supported one", () => {
  const rows = [
    { horizonDays: 1, matches: 50 },
    { horizonDays: 5, matches: 9 },
  ];
  assert.equal(pickAnalog(rows)?.horizonDays, 5);
  assert.equal(pickAnalog([{ horizonDays: 1, matches: 4 }, { horizonDays: 20, matches: 31 }])?.horizonDays, 20);
  assert.equal(pickAnalog([]), null);
});

test("an unusual move reuses the threshold the prose already uses", () => {
  assert.equal(isUnusualMove(null), false);
  assert.equal(isUnusualMove({ robustZ: 0.4, trigger: "catalyst" }), false);
  // 2 is where lib/plain.ts starts calling a move unusual.
  assert.equal(isUnusualMove({ robustZ: 2, trigger: "catalyst" }), true);
  assert.equal(isUnusualMove({ robustZ: -3.1, trigger: "catalyst" }), true);
  // A move or volume trigger counts on its own: the job only writes a row when it crossed its bar.
  assert.equal(isUnusualMove({ robustZ: null, trigger: "move" }), true);
  assert.equal(isUnusualMove({ robustZ: null, trigger: "volume" }), true);
});

test("daysUntil is calendar days and tolerates nonsense", () => {
  assert.equal(daysUntil("2026-10-06", "2026-10-03"), 3);
  assert.equal(daysUntil("2026-10-03", "2026-10-03"), 0);
  assert.equal(daysUntil(null, "2026-10-03"), null);
  assert.equal(daysUntil("nope", "2026-10-03"), null);
});

test("todayISO is a plain UTC date", () => {
  assert.equal(todayISO(new Date("2026-10-03T23:59:00Z")), "2026-10-03");
  assert.match(todayISO(), /^\d{4}-\d{2}-\d{2}$/);
});

function bundle(over: Partial<DecisionBundle> = {}): DecisionBundle {
  return {
    asset: { symbol: "AAPL", assetType: "stock", industry: { market: "US" } },
    freshness: { newest: new Date("2026-10-02T00:00:00Z"), close: 97 },
    setups: [
      { horizon: "swing", state: "buy", entryLevel: 100, invalidateLevel: 94 },
      { horizon: "longer", state: "buy", entryLevel: 101, invalidateLevel: 90 },
    ],
    analogs: [{ horizonDays: 5, matches: 22, minPct: -4.1, maxPct: 7.7 }],
    human: { recentStories: 14 },
    investigation: null,
    nextEvent: null,
    // No factor row by default: that is the ordinary state on a database where the factor job
    // has not reached this asset, and the rules must still produce a verdict from it.
    factors: null,
    sourceHealth: [{ source: "Yahoo Finance daily closes", status: "healthy" }],
    ...over,
  };
}

test("a full bundle maps to an actionable input", () => {
  const input = toDecisionInput(bundle(), "2026-10-03");
  assert.equal(input.market, "US");
  assert.equal(input.asOf, "2026-10-02");
  assert.equal(input.lastClose, 97);
  assert.deepEqual(input.setup, { direction: "up", horizon: "swing", trend: null, bias: null });
  assert.deepEqual(input.horizon, { direction: "up" });
  assert.deepEqual(input.entry, { low: 94, high: 100 });
  assert.equal(input.invalidation, 94);
  assert.deepEqual(input.analogs, {
    count: 22,
    lowPct: -4.1,
    highPct: 7.7,
    medianPct: null,
    positive: null,
  });
  assert.equal(input.newsCount, 14);
  assert.equal(input.sourceSilent, null);

  // And it survives the rule table as the thing a reader can act on.
  const d = decide(input);
  assert.equal(d.action, "LONG");
  assert.equal(d.timeSense, "NOW");
});

test("a silent source is only reported when it is this market's source", () => {
  const amazonDead = [
    { source: "Amazon Best Sellers", status: "silent" },
    { source: "Yahoo Finance daily closes", status: "healthy" },
  ];
  assert.equal(toDecisionInput(bundle({ sourceHealth: amazonDead }), "2026-10-03").sourceSilent, null);

  const yahooDead = [{ source: "Yahoo Finance daily closes", status: "silent" }];
  assert.equal(
    toDecisionInput(bundle({ sourceHealth: yahooDead }), "2026-10-03").sourceSilent,
    "Yahoo Finance daily closes",
  );

  // A PSX name is not affected by Yahoo being out.
  const psx = bundle({
    asset: { symbol: "LUCK", assetType: "stock", industry: { market: "PK" } },
    sourceHealth: yahooDead,
  });
  assert.equal(toDecisionInput(psx, "2026-10-03").sourceSilent, null);
});

test("no human signal row means news was never checked, not that there is none", () => {
  assert.equal(toDecisionInput(bundle({ human: null }), "2026-10-03").newsCount, null);
  assert.equal(toDecisionInput(bundle({ human: { recentStories: 0 } }), "2026-10-03").newsCount, 0);
});

test("a missing price series maps to nulls and the rule table catches it", () => {
  const empty = bundle({ freshness: { newest: null, close: null } });
  const input = toDecisionInput(empty, "2026-10-03");
  assert.equal(input.asOf, null);
  assert.equal(decide(input).gate, "no-prices");
});

test("a @db.Date at local midnight keeps its own day, east or west of UTC", () => {
  // What `pg` hands back for a `@db.Date`: midnight in the box's zone, not in UTC. East of UTC
  // that instant is the previous day in UTC, so `toISOString().slice(0, 10)` used to report the
  // day before the stored one. `asOf` feeds the staleness gate, and `STALE_AFTER_DAYS.Crypto` is
  // 2, so the shift was enough to turn a current crypto reading into a `stale` verdict on a
  // non-UTC box while the UTC-rendered site showed it fine. Built from local parts on purpose:
  // this asserts the stored day survives, whatever zone the test runs in.
  const localMidnight = new Date(2026, 9, 4);
  const input = toDecisionInput(bundle({ freshness: { newest: localMidnight, close: 97 } }), "2026-10-04");
  assert.equal(input.asOf, "2026-10-04");
  // The consequence that mattered: a current reading must not be gated as stale.
  assert.notEqual(decide(input).gate, "stale");
});

test("a crypto name gets the strict staleness rule", () => {
  const coin = bundle({
    asset: { symbol: "BTC-USD", assetType: "crypto", industry: { market: "US" } },
    freshness: { newest: "2026-09-29", close: 97 },
  });
  const input = toDecisionInput(coin, "2026-10-03");
  assert.equal(input.market, "Crypto");
  // Binance stopping on 2026-09-29 is exactly the real case this guards.
  assert.equal(decide(input).gate, "stale");
});

// --- Product rules ----------------------------------------------------------------------------

function product(over: Partial<ProductDecisionInput> = {}): ProductDecisionInput {
  return {
    name: "Standing desk converter",
    term: "standing desk converter",
    status: "rising",
    demandScore: 61,
    sourcesAnswered: 4,
    sourcesAgree: 3,
    confidence: "medium",
    regions: [{ name: "United States", scope: "country", geo: "" }],
    marketplaceItems: 2,
    ...over,
  };
}

test("rising attention with agreeing sources is YES LOOK", () => {
  const d = decideProduct(product());
  assert.equal(d.attention, "RISING");
  assert.equal(d.sellInterest, "YES LOOK");
  assert.equal(d.geo, "United States");
  assert.equal(d.missing.length, 0);
});

test("one source answering is NO CLEAR SIGNAL, whatever the score says", () => {
  const d = decideProduct(product({ sourcesAnswered: 1, sourcesAgree: 1, demandScore: 99 }));
  assert.equal(d.sellInterest, "NO CLEAR SIGNAL");
  assert.match(d.risk, /single source/i);
  // Links still appear: thin data is when the next click matters most.
  assert.equal(d.where.length, 5);
});

test("no source answering says so rather than showing a blank", () => {
  const d = decideProduct(product({ sourcesAnswered: 0, sourcesAgree: 0 }));
  assert.equal(d.sellInterest, "NO CLEAR SIGNAL");
  assert.match(d.why[0], /No demand source answered/);
  assert.match(d.risk, /nothing behind this reading/i);
});

test("rising but weakly graded is NOT YET", () => {
  assert.equal(decideProduct(product({ confidence: "low" })).sellInterest, "NOT YET");
  assert.equal(decideProduct(product({ sourcesAgree: 1 })).sellInterest, "NOT YET");
  assert.equal(decideProduct(product({ status: "flat" })).sellInterest, "NOT YET");
  assert.equal(decideProduct(product({ status: "early" })).sellInterest, "NOT YET");
});

test("an unmeasured status is named, not silently treated as flat", () => {
  const d = decideProduct(product({ status: "unknown" }));
  assert.equal(d.attention, null);
  assert.match(String(d.attentionMissing), /No attention reading/);
  assert.ok(d.missing.some((m) => /Attention has not been measured/.test(m)));
});

test("empty geo and no marketplace match are reported, never blank", () => {
  const d = decideProduct(product({ regions: [], marketplaceItems: 0 }));
  assert.equal(d.geo, null);
  assert.ok(d.missing.some((m) => /Geography not measured yet/.test(m)));
  assert.ok(d.missing.some((m) => /No marketplace listing/.test(m)));
});

test("every product decision carries exactly one risk line and five links", () => {
  for (const over of [
    {},
    { sourcesAnswered: 0, sourcesAgree: 0 },
    { sourcesAnswered: 1, sourcesAgree: 1 },
    { status: "unknown" },
    { status: "flat" },
    { confidence: "none" },
    { sourcesAgree: 2, sourcesAnswered: 5 },
  ]) {
    const d = decideProduct(product(over));
    assert.ok(d.risk.length > 0, `no risk line for ${JSON.stringify(over)}`);
    assert.equal(d.where.length, 5);
    assert.ok(d.why.length > 0 && d.why.length <= 2);
  }
});

test("search links are built from the term and are properly encoded", () => {
  const links = whereToCheck("air fryer & grill");
  for (const l of links) {
    assert.ok(!l.url.includes(" "), `${l.label} has an unencoded space`);
    assert.ok(l.url.includes("air%20fryer%20%26%20grill"), `${l.label} did not encode the term`);
  }
  assert.deepEqual(
    links.map((l) => l.label),
    ["Google Trends", "Amazon search", "eBay search", "Daraz search", "Facebook Marketplace"],
  );
  for (const l of links) {
    assert.match(l.url, /^https:\/\//);
    assert.ok(l.why.length > 0, `${l.label} has no reason to click it`);
  }
});

test("the term falls back to the name when no trends term is stored", () => {
  const d = decideProduct(product({ term: "" }));
  assert.ok(d.where[0].url.includes(encodeURIComponent("Standing desk converter")));
});

// --- The seam with the query layer ------------------------------------------------------------
//
// These matter because the query layer returns flat rows and the rules want a nested shape, and a
// mismapped field here is silent: it turns a WAIT into a LONG without anything throwing.

test("a flat query bundle becomes an actionable input", () => {
  const input = toDecisionInput(
    bundleFromQuery(
      {
        symbol: "AAPL",
        assetType: "stock",
        market: "US",
        newestClose: 97,
        newestCloseDate: new Date("2026-10-02T00:00:00Z"),
        horizons: [
          { horizon: "swing", state: "buy", entryLevel: 100, invalidateLevel: 94 },
          { horizon: "longer", state: "buy", entryLevel: 101, invalidateLevel: 90 },
        ],
        analogs: [{ horizonDays: 5, matches: 22, minPct: -4.1, maxPct: 7.7 }],
        humanSignal: { recentStories: 14 },
        investigation: null,
        nextEvent: null,
      },
      [{ source: "Yahoo Finance daily closes", status: "healthy" }],
    ),
    "2026-10-03",
  );
  assert.equal(input.market, "US");
  assert.deepEqual(input.entry, { low: 94, high: 100 });
  assert.equal(decide(input).action, "LONG");
});

test("a bundle with nothing stored still names the asset rather than null", () => {
  const input = toDecisionInput(
    bundleFromQuery(
      {
        symbol: null,
        assetType: null,
        market: null,
        newestClose: null,
        newestCloseDate: null,
        horizons: [],
        analogs: [],
        humanSignal: null,
        investigation: null,
        nextEvent: null,
      },
      [],
    ),
    "2026-10-03",
  );
  assert.equal(input.market, "Other");
  const d = decide(input);
  assert.equal(d.gate, "no-prices");
  // "No stored prices for null." would be the alternative.
  assert.ok(!d.why[0].includes("null"), d.why[0]);
});

function row(over: Partial<QueryRow> = {}): QueryRow {
  return {
    symbol: "LUCK",
    assetType: "stock",
    market: "PK",
    close: 97,
    closeDate: "2026-10-02",
    swing: { state: "short", entryLevel: 94, invalidateLevel: 100 },
    longer: { state: "short", entryLevel: 92, invalidateLevel: 103 },
    analogMinPct: -6.2,
    analogMaxPct: 3.3,
    analogMatches: 18,
    analogHorizonDays: 5,
    recentStories: 11,
    robustZ: null,
    trigger: null,
    nextEventDate: null,
    ...over,
  };
}

test("a home page row decides the same way a full bundle would", () => {
  const input = toDecisionInput(bundleFromRow(row(), []), "2026-10-03");
  assert.equal(input.market, "PSX");
  assert.deepEqual(input.setup, { direction: "down", horizon: "swing", trend: null, bias: null });
  assert.deepEqual(input.entry, { low: 94, high: 100 });
  assert.equal(decide(input).action, "SHORT");
});

test("a row with no setup rows is WAIT and says which reading is absent", () => {
  const input = toDecisionInput(bundleFromRow(row({ swing: null, longer: null }), []), "2026-10-03");
  assert.deepEqual(input.setup, null);
  const d = decide(input);
  assert.equal(d.action, "WAIT");
  // Gate 4 fires before gate 9: with no setup there is also no break level.
  assert.equal(d.gate, "no-invalidation");
  assert.ok(d.missing.length > 0);
});

test("an analog band with no horizon is dropped rather than printed", () => {
  const got = toDecisionInput(bundleFromRow(row({ analogHorizonDays: null }), []), "2026-10-03");
  assert.equal(got.analogs, null);
  assert.match(decide(got).measured, /Not enough similar past days/);
});

test("a row with no news row keeps the difference between unchecked and zero", () => {
  assert.equal(toDecisionInput(bundleFromRow(row({ recentStories: null }), []), "2026-10-03").newsCount, null);
  assert.equal(toDecisionInput(bundleFromRow(row({ recentStories: 0 }), []), "2026-10-03").newsCount, 0);
});

test("a row's investigation only counts when a trigger is stored", () => {
  assert.equal(toDecisionInput(bundleFromRow(row(), []), "2026-10-03").unusualMove, false);
  assert.equal(
    toDecisionInput(bundleFromRow(row({ trigger: "move", robustZ: null }), []), "2026-10-03").unusualMove,
    true,
  );
});

test("a PSX row is not disturbed by Yahoo being silent", () => {
  const health = [{ source: "Yahoo Finance daily closes", status: "silent" }];
  assert.equal(toDecisionInput(bundleFromRow(row(), health), "2026-10-03").sourceSilent, null);
  const us = row({ market: "US" });
  assert.equal(
    toDecisionInput(bundleFromRow(us, health), "2026-10-03").sourceSilent,
    "Yahoo Finance daily closes",
  );
});

// --- Which horizon is the setup ----------------------------------------------------------------
//
// This is the case that mattered in production. jobs/setup.py writes swing rows that are almost
// always `wait`, and the direction lives in the `longer` rows from jobs/horizons.py. Preferring
// swing unconditionally made every one of 160 live assets read WAIT.

test("a directional row beats a flat swing row", () => {
  const rows = [
    { horizon: "swing", state: "wait", entryLevel: 10, invalidateLevel: 9 },
    { horizon: "longer", state: "buy", entryLevel: 12, invalidateLevel: 8 },
  ];
  const got = pickSetup(rows);
  assert.equal(got?.horizon, "longer");
  assert.equal(got?.state, "buy");
});

test("swing still wins when swing is the directional one", () => {
  const rows = [
    { horizon: "swing", state: "buy", entryLevel: 10, invalidateLevel: 9 },
    { horizon: "longer", state: "short", entryLevel: 12, invalidateLevel: 8 },
  ];
  assert.equal(pickSetup(rows)?.horizon, "swing");
});

test("intraday is used only when nothing longer is directional", () => {
  const rows = [
    { horizon: "intraday", state: "buy", entryLevel: 1, invalidateLevel: 2 },
    { horizon: "swing", state: "wait", entryLevel: 10, invalidateLevel: 9 },
    { horizon: "longer", state: "none", entryLevel: 12, invalidateLevel: 8 },
  ];
  assert.equal(pickSetup(rows)?.horizon, "intraday");
});

test("nothing directional returns the swing row as a measured flat", () => {
  const rows = [
    { horizon: "swing", state: "wait", entryLevel: 10, invalidateLevel: 9 },
    { horizon: "longer", state: "none", entryLevel: 12, invalidateLevel: 8 },
  ];
  assert.equal(pickSetup(rows)?.horizon, "swing");
});

test("the longer row cannot be both the setup and its own confirmation", () => {
  // The live shape: swing is flat, longer carries the direction.
  const input = toDecisionInput(
    bundleFromRow(
      row({
        swing: { state: "wait", entryLevel: 100, invalidateLevel: 94 },
        longer: { state: "buy", entryLevel: 101, invalidateLevel: 90 },
      }),
      [],
    ),
    "2026-10-03",
  );
  assert.deepEqual(input.setup, { direction: "up", horizon: "longer", trend: null, bias: null });
  // Null, not { direction: "up" }: it would otherwise agree with itself and be graded as two
  // timeframes lining up.
  assert.equal(input.horizon, null);
  const d = decide(input);
  assert.equal(d.action, "LONG");
  assert.match(d.why[1], /Only one time frame points anywhere/);
});

/// The fixture is a PSX short; these tests need a clean long, on both horizons. Setting only the
/// swing leaves the longer view opposed, which gate 5 correctly refuses.
// A buy: entry above the close (the level a move has to clear) and the stop below it. It was
// entry 94 and stop 100 against a close of 97, a LONG already below its own stop.
const UP = { state: "buy", entryLevel: 100, invalidateLevel: 94 };

// --- Factors reaching the rules ----------------------------------------------------------------
//
// The gates for volume and peer-relative strength existed before anything fed them, so every live
// decision came out Low: `DecisionBundle` had no factor fields and the rules could only ever see
// null. These assert the seam itself, because a silently unwired factor looks exactly like a factor
// that did not confirm.

test("a factor row reaches the rules and lifts the confidence", () => {
  const withoutFactors = toDecisionInput(bundleFromRow(row({ swing: UP, longer: UP }), []), "2026-10-03");
  assert.equal(withoutFactors.volumeRatio, null);
  assert.equal(decide(withoutFactors).confidence, "Medium");

  const withFactors = toDecisionInput(
    bundleFromRow(
      row({
        swing: UP,
        longer: UP,
        volumeRatio: 2.1,
        analogMedianPct: 1.6,
        analogPositive: 13,
      }),
      [],
    ),
    "2026-10-03",
  );
  assert.equal(withFactors.volumeRatio, 2.1);
  const d = decide(withFactors);
  assert.equal(d.action, "LONG");
  assert.equal(d.confidence, "High");
  assert.match(d.why[2], /Confirmed by/);
});

test("peer-relative strength reaches the rule that uses it", () => {
  const laggard = toDecisionInput(
    bundleFromRow(row({ swing: UP, longer: UP, relStrength: -7 }), []),
    "2026-10-03",
  );
  assert.equal(laggard.relStrength, -7);
  // It stopped being a gate and did not stop being read. The direction stands, the lag is
  // printed with its own value, and the grade is capped one step for it.
  const d = decide(laggard);
  assert.equal(d.action, "LONG");
  assert.ok(
    d.notes.some((n) => /7\.0 points behind its peers/.test(n)),
    d.notes.join(" | "),
  );
  assert.notEqual(d.confidence, "High");
});

// --- Targets reaching the rules ----------------------------------------------------------------
//
// The fourth field to be declared at this seam, and the first to be tested on the way in rather
// than after a live page printed something wrong. Three before it -- `conditions`, `medianPct`,
// `positive` -- were fetched by the query layer, read by the rule table and lost in an object
// literal in between, with nothing failing. An optional field cannot fail to exist, so the type
// is not the guard and this is.

test("a setup's measured target reaches the rules and sizes the trade", () => {
  const input = toDecisionInput(
    bundleFromRow(
      row({
        swing: {
          ...UP,
          targets: [
            { method: "volatility", low: 118, high: 124, rewardRisk: 0.9 },
            { method: "structure", low: 108, high: 112, rewardRisk: 2.6 },
          ],
        },
        longer: UP,
      }),
      [],
    ),
    "2026-10-03",
  );
  // The preference order from lib/target.ts, applied once: volatility leads.
  assert.equal(input.target?.method, "volatility");
  assert.equal(input.target?.rewardRisk, 0.9);
  assert.equal(decide(input).plan?.rewardRisk, 0.9);
});

test("a target sitting on the entry falls through to the one that measured a distance", () => {
  // Live on Algorand on 2026-10-09 and on 608 setups that had just been given targets: the
  // nearest structural pivot sat a few ticks above the entry, so the preferred method produced
  // a reward of 0.0x and the card quoted the entry back to the reader as its exit.
  //
  // The volatility method is the fallback because it cannot fail to produce a distance -- it is
  // a multiple of the asset's own average true range -- where structure needs a pivot above the
  // entry and analog needs a median pointing the right way.
  const withFlatStructure = toDecisionInput(
    bundleFromRow(
      row({
        swing: {
          ...UP,
          targets: [
            { method: "structure", low: 94.1, high: 94.1, rewardRisk: 0.02 },
            { method: "volatility", low: 118, high: 124, rewardRisk: 1.8 },
          ],
        },
        longer: UP,
      }),
      [],
    ),
    "2026-10-03",
  );
  assert.equal(withFlatStructure.target?.method, "volatility");
  assert.equal(withFlatStructure.target?.rewardRisk, 1.8);
  // And with the leading method flat, the next one that measured a distance is taken.
  const flatVolatility = toDecisionInput(
    bundleFromRow(
      row({
        swing: {
          ...UP,
          targets: [
            { method: "volatility", low: 94.1, high: 94.1, rewardRisk: 0.03 },
            { method: "structure", low: 112, high: 112, rewardRisk: 1.4 },
          ],
        },
        longer: UP,
      }),
      [],
    ),
    "2026-10-03",
  );
  assert.equal(flatVolatility.target?.method, "structure");

  // And when every method is flat, the real figure is still shown rather than nothing. A trade
  // with no room is a finding, and hiding it would be the one dishonest outcome here.
  const allFlat = toDecisionInput(
    bundleFromRow(
      row({
        swing: {
          ...UP,
          targets: [
            { method: "structure", low: 94.1, high: 94.1, rewardRisk: 0.02 },
            { method: "volatility", low: 94.2, high: 94.2, rewardRisk: 0.04 },
          ],
        },
        longer: UP,
      }),
      [],
    ),
    "2026-10-03",
  );
  assert.equal(allFlat.target?.method, "volatility");
  assert.equal(allFlat.target?.rewardRisk, 0.04);
});

test("the target is taken off the setup that decided, not off whichever row has one", () => {
  // `pickSetup` prefers a directional row, and here that is `longer`. A target lifted from the
  // swing row would size a quarterly trade against a swing exit -- the same fault `decidingSetup`
  // in lib/target.ts exists to prevent, one step earlier in the pipe.
  const input = toDecisionInput(
    bundleFromRow(
      row({
        swing: {
          state: "wait",
          entryLevel: 94,
          invalidateLevel: 100,
          targets: [{ method: "structure", low: 80, high: 84, rewardRisk: 4.0 }],
        },
        longer: {
          ...UP,
          targets: [{ method: "structure", low: 108, high: 112, rewardRisk: 1.1 }],
        },
      }),
      [],
    ),
    "2026-10-03",
  );
  assert.equal(input.target?.rewardRisk, 1.1);
});

test("the panel's exit and the rules' reward come off the same row, intraday included", () => {
  // The contradiction this pins down was live on PLTR on 2026-10-09. `pickSetup` walks
  // swing, longer, intraday and took the intraday row -- the only directional one -- while
  // `decidingSetup` in lib/target.ts walked only swing and longer and found nothing. The panel
  // printed "Exit if working: No clear target stored" directly above "Reward against risk: 0.2x",
  // which is a figure computed from the target the line above said did not exist.
  //
  // Two functions answer "which setup decided". This is the test that keeps them answering the
  // same thing, because a comment saying they mirror each other is what was there before.
  const setups = [
    { horizon: "swing", state: "wait", entryLevel: 196, invalidateLevel: 197, conditions: null, targets: [] },
    { horizon: "longer", state: "none", entryLevel: null, invalidateLevel: null, conditions: null, targets: [] },
    {
      horizon: "intraday",
      state: "buy",
      entryLevel: 196.84,
      invalidateLevel: 199.1,
      conditions: null,
      targets: [{ method: "structure", low: 201, high: 203, rewardRisk: 0.2, distancePct: 1.1, note: "" }],
    },
  ];

  const input = toDecisionInput(
    {
      asset: { symbol: "PLTR", assetType: "stock", industry: { market: "US" } },
      freshness: { newest: "2026-10-08", close: 198.78 },
      setups,
      analogs: [],
      human: null,
      investigation: null,
      factors: null,
      nextEvent: null,
      sourceHealth: [],
    },
    "2026-10-09",
  );
  assert.equal(input.target?.rewardRisk, 0.2);
  // And the page's own picker agrees, over the same list the asset page hands it.
  assert.equal(pickTarget(setups)?.rewardRisk, 0.2);
});

test("the coverage verdict reaches the rule that reads it", () => {
  // The fifth field to cross this seam, and the reason each one gets a test: `conditions`,
  // `medianPct`, `positive` and `targets` were all fetched by the query layer, read by the rule
  // table, and dropped in an object literal in between with nothing failing.
  const withTone = toDecisionInput(
    bundleFromRow(
      row({
        swing: UP,
        longer: UP,
        recentStories: 11,
        newsTone: "negative",
        newsCatalyst: true,
        volumeRatio: 2.1,
        analogMedianPct: 1.6,
        analogPositive: 16,
      }),
      [],
    ),
    "2026-10-03",
  );
  assert.deepEqual(withTone.news, { tone: "down", catalyst: true });
  const d = decide(withTone);
  assert.equal(d.action, "LONG");
  assert.ok(
    d.notes.some((n) => /worded negatively/.test(n)),
    d.notes.join(" | "),
  );
});

test("a stored tone of neutral arrives as no direction, not as a disagreement", () => {
  // `jobs/human.py` writes "neutral" both for a balanced window and for one where too few
  // headlines took a side. Neither is a finding against the setup, and mapping either to a
  // direction here would make the commonest reading in the table -- 378 of 454 on 2026-10-09 --
  // into a deduction on almost every name.
  const input = toDecisionInput(
    bundleFromRow(row({ swing: UP, longer: UP, recentStories: 11, newsTone: "neutral" }), []),
    "2026-10-03",
  );
  assert.equal(input.news?.tone, null);
  assert.deepEqual(decide(input).notes, []);
});

test("a database with no targets decides without one, and names the gap", () => {
  const d = decide(toDecisionInput(bundleFromRow(row({ swing: UP, longer: UP }), []), "2026-10-03"));
  assert.equal(d.action, "LONG");
  assert.equal(d.plan?.rewardRisk, null);
  assert.ok(
    d.missing.some((m) => /No measured target stored/.test(m)),
    d.missing.join(" | "),
  );
});

test("a database with no factor rows still decides, and says what is missing", () => {
  // The state on every deployment until the factor job has run once. It must not empty the lists.
  const d = decide(toDecisionInput(bundleFromRow(row({ swing: UP, longer: UP }), []), "2026-10-03"));
  assert.equal(d.action, "LONG");
  assert.ok(d.missing.some((m) => /No volume published/.test(m)), d.missing.join(" | "));
});


test("the analog lean survives the trip into the rules", () => {
  // The regression this file exists to prevent, and the most expensive single omission found in
  // this codebase so far. `toDecisionInput` used to build `{ count, lowPct, highPct }` and drop
  // `medianPct` and `positive` on the floor. `analogConfirms` returns null the instant either is
  // missing, so one of the three legs `confidenceFor` counts was dead for every asset in the
  // database — 160 of 160, every direction, always.
  //
  // Two things went wrong and the second is worse. Grades were capped below what the stored rows
  // supported: restoring these two fields moved 21 assets from Low to Medium with no change to
  // any rule or threshold. And `confirmMissing` printed "stored, but which way they went was not
  // recorded" over assets whose lean was sitting in the table — ATRL said it about 102 matched
  // days while holding both columns.
  //
  // Nothing upstream was broken: jobs/analogs.py writes both, lib/queries.ts selects both,
  // and both bundle builders carry them. Only the object literal in the middle dropped them.
  const withLean = toDecisionInput(
    bundle({
      analogs: [
        { horizonDays: 5, matches: 40, minPct: -9, maxPct: 14, medianPct: 2.4, positive: 26 },
      ],
    }),
    "2026-10-03",
  );
  assert.equal(withLean.analogs?.medianPct, 2.4);
  assert.equal(withLean.analogs?.positive, 26);
});

test("an analog row with no lean recorded still reads as absent", () => {
  // The other half. A row genuinely missing the lean — jobs/analogs.py leaves both null when it
  // matched nothing — must still reach the rules as null, so `analogConfirms` keeps returning
  // null rather than reading an absence as a flat outcome. Carrying the fields through is not
  // the same as inventing them.
  const noLean = toDecisionInput(
    bundle({ analogs: [{ horizonDays: 5, matches: 0, minPct: null, maxPct: null }] }),
    "2026-10-03",
  );
  assert.equal(noLean.analogs?.medianPct, null);
  assert.equal(noLean.analogs?.positive, null);
});

// --- The entry trigger crossing the seam -------------------------------------------------------
//
// The sixth field to cross this seam, and the count is the argument for the test: `conditions`,
// `medianPct`, `positive`, `targets` and the coverage verdict were each fetched by the query
// layer, read by the rule table, and dropped in an object literal in between with nothing
// failing. `r20` made it six -- it crossed into `lib/` and was never added to `tools/decide.mjs`,
// so the nightly log decided late shorts on half the gate for a day. An optional field cannot
// fail to exist, so the type is not the guard and this is.

test("the entry trigger reaches the rules and confirms the direction", () => {
  const silent = toDecisionInput(
    bundleFromRow(row({ swing: UP, longer: null, volumeRatio: 0.4 }), []),
    "2026-10-03",
  );
  assert.equal(silent.entryTrigger, null);
  assert.equal(decide(silent).confidence, "Low");

  const fired = toDecisionInput(
    bundleFromRow(
      row({
        swing: UP,
        longer: null,
        volumeRatio: 0.4,
        entryTrigger: "squeeze_break",
        triggerDirection: "up",
      }),
      [],
    ),
    "2026-10-03",
  );
  assert.deepEqual(fired.entryTrigger, { rule: "squeeze_break", direction: "up" });
  const d = decide(fired);
  assert.equal(d.confidence, "Medium");
  assert.match(d.why[2], /quietest stretch in six months this session/);
});

test("a rule with no direction beside it is not half a confirmation", () => {
  // Both columns or neither. `jobs/factors.py` writes them together, so a row carrying a rule
  // name and no direction has lost half of itself somewhere between the job and here -- and
  // confirming a direction from the surviving half would be reading a measurement that was never
  // completed.
  const halved = toDecisionInput(
    bundleFromRow(
      row({ swing: UP, longer: null, volumeRatio: 0.4, entryTrigger: "squeeze_break" }),
      [],
    ),
    "2026-10-03",
  );
  assert.equal(halved.entryTrigger, null);
  assert.equal(decide(halved).confidence, "Low");
});

test("a direction the rules do not recognise is refused rather than cast", () => {
  // `triggerDirection` is a String? in Postgres, so it can hold anything a later job or a
  // hand-written UPDATE puts there. `as "up" | "down"` would turn a typo into a silent
  // confirmation of whichever way the card happened to be printing.
  for (const direction of ["UP", "long", "rising", ""]) {
    const input = toDecisionInput(
      bundleFromRow(
        row({
          swing: UP,
          longer: null,
          volumeRatio: 0.4,
          entryTrigger: "squeeze_break",
          triggerDirection: direction,
        }),
        [],
      ),
      "2026-10-03",
    );
    assert.equal(input.entryTrigger, null, direction);
    assert.equal(decide(input).confidence, "Low", direction);
  }
});

test("the asset-page bundle carries the trigger as well as the list row", () => {
  // Two paths reach `toDecisionInput`: `bundleFromRow` for the lists and `bundleFromQuery` for
  // the asset page. A field wired into one and not the other is the shape of fault where a name
  // reads Medium in a list and Low on its own page, with nothing raising anywhere.
  const input = toDecisionInput(
    bundleFromQuery(
      {
        symbol: "AAPL",
        assetType: "stock",
        market: "US",
        newestClose: 97,
        newestCloseDate: new Date("2026-10-02T00:00:00Z"),
        horizons: [{ horizon: "swing", state: "buy", entryLevel: 100, invalidateLevel: 94 }],
        analogs: [],
        humanSignal: null,
        investigation: null,
        nextEvent: null,
        factor: {
          volumeRatio: 0.4,
          relStrength: null,
          r20: null,
          entryTrigger: "vol_flip",
          triggerDirection: "down",
        },
      },
      [],
    ),
    "2026-10-03",
  );
  assert.deepEqual(input.entryTrigger, { rule: "vol_flip", direction: "down" });
});

// --- The macro veto crossing the seam ----------------------------------------------------------
//
// The seventh field to cross it, and the reason it has a test is the one above: an optional field
// that is never named in an object literal is dropped without anything failing. Here the failure is
// the harmless-looking one -- a stored refusal that never reaches the rules -- so the gate would be
// running, costing money, and changing nothing.

test("a stored macro refusal reaches the rules from both the list and the asset page", () => {
  const veto = { macroVetoReason: "macro-warning", macroVetoAsOf: "2026-10-03" };
  const fromRow = toDecisionInput(bundleFromRow(row({ swing: UP, longer: null, ...veto }), []), "2026-10-03");
  assert.deepEqual(fromRow.macroVeto, { reason: "macro-warning", asOf: "2026-10-03" });
  assert.equal(decide(fromRow).gate, "macro-veto");

  const query = (macroVeto: object | null | undefined) =>
    toDecisionInput(
      bundleFromQuery(
        {
          symbol: "AAPL",
          assetType: "stock",
          market: "US",
          newestClose: 97,
          newestCloseDate: new Date("2026-10-02T00:00:00Z"),
          horizons: [{ horizon: "swing", state: "buy", entryLevel: 100, invalidateLevel: 94 }],
          analogs: [{ horizonDays: 5, matches: 22, minPct: -4.1, maxPct: 7.7 }],
          humanSignal: { recentStories: 14 },
          investigation: null,
          nextEvent: null,
          macroVeto: macroVeto as never,
        },
        [],
      ),
      "2026-10-03",
    );
  const page = query({ reason: "sentiment-conflict", asOf: new Date("2026-10-03T00:00:00Z") });
  assert.deepEqual(page.macroVeto, { reason: "sentiment-conflict", asOf: "2026-10-03" });
  assert.equal(query(undefined).macroVeto, null);
});

test("a stored refusal that is not one is no veto, and a row without one is unchanged", () => {
  const plain = toDecisionInput(bundleFromRow(row({ swing: UP, longer: null }), []), "2026-10-03");
  assert.equal(plain.macroVeto, null);
  const half = (v: object) => toDecisionInput(bundleFromRow(row({ swing: UP, longer: null, ...v }), []), "2026-10-03").macroVeto;
  assert.equal(half({ macroVetoReason: "macro-warning" }), null);
  assert.equal(half({ macroVetoAsOf: "2026-10-03" }), null);
  assert.equal(half({ macroVetoReason: "vibes", macroVetoAsOf: "2026-10-03" }), null);
  assert.equal(half({ macroVetoReason: "macro-warning", macroVetoAsOf: "garbage" }), null);
});
