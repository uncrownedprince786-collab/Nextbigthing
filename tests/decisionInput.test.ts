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
  type DecisionBundle,
} from "../lib/decisionInput.ts";
import { decideProduct, whereToCheck, type ProductDecisionInput } from "../lib/productDecision.ts";
import { decide } from "../lib/decision.ts";

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

test("crypto has no coverage label, because nothing watches that feed", () => {
  assert.equal(coverageLabelFor("US"), "Yahoo Finance daily closes");
  assert.equal(coverageLabelFor("PSX"), "PSX daily closing files");
  // jobs/audit.py does not watch Binance or CoinPaprika, so silence there is undetectable.
  assert.equal(coverageLabelFor("Crypto"), null);
  assert.equal(coverageLabelFor("Other"), null);
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

test("the swing row is the setup, and a directional row is the fallback", () => {
  const rows = [
    { horizon: "intraday", state: "buy", entryLevel: null, invalidateLevel: null },
    { horizon: "swing", state: "wait", entryLevel: null, invalidateLevel: null },
    { horizon: "longer", state: "short", entryLevel: null, invalidateLevel: null },
  ];
  assert.equal(pickSetup(rows)?.horizon, "swing");
  // No swing row: take the first with an actual direction, matching what lib/plain.ts does.
  assert.equal(pickSetup([rows[0], rows[2]])?.horizon, "intraday");
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
    sourceHealth: [{ source: "Yahoo Finance daily closes", status: "healthy" }],
    ...over,
  };
}

test("a full bundle maps to an actionable input", () => {
  const input = toDecisionInput(bundle(), "2026-10-03");
  assert.equal(input.market, "US");
  assert.equal(input.asOf, "2026-10-02");
  assert.equal(input.lastClose, 97);
  assert.deepEqual(input.setup, { direction: "up", horizon: "swing" });
  assert.deepEqual(input.horizon, { direction: "up" });
  assert.deepEqual(input.entry, { low: 94, high: 100 });
  assert.equal(input.invalidation, 94);
  assert.deepEqual(input.analogs, { count: 22, lowPct: -4.1, highPct: 7.7 });
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
  assert.ok(d.missing.some((m) => /Geo not stored yet/.test(m)));
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
