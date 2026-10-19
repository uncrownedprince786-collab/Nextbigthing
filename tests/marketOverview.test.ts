// The market overview reduction: stored groups in, five markets out.
//
// The defect this guards is the one the market explorer actually had — every crypto coin and every
// front-month future shown as a US listing, because the grouping read the industry's `market`
// column and that column is US/PK/FX only. These tests assert the instrument decides the market,
// and that an industry is filed under the market most of its instruments trade in.

import { test } from "node:test";
import assert from "node:assert/strict";
import { reduceMarketOverview, marketKeyFor, type MarketOverviewInput } from "../lib/marketOverview.ts";
import { canonicalMarket, MARKET_ORDER } from "../lib/marketMarkets.ts";

function empty(): MarketOverviewInput {
  return {
    assetGroups: [],
    closeGroups: [],
    factorGroups: [],
    quoteGroups: [],
    industryRows: [],
    predictionsByMarket: new Map(),
  };
}

test("an instrument decides its market, not the industry's column", () => {
  // All four trade under industries whose stored market is US, and none of them is a US market.
  assert.equal(marketKeyFor("crypto", "US"), "Crypto");
  assert.equal(marketKeyFor("commodity", "US"), "Commodity");
  assert.equal(marketKeyFor("forex", "US"), "FX");
  // A US stock and a Karachi stock are told apart by the industry, and only by it.
  assert.equal(marketKeyFor("stock", "US"), "US");
  assert.equal(marketKeyFor("stock", "PK"), "PK");
  assert.equal(marketKeyFor("etf", "US"), "US");
});

test("an unclassifiable instrument is dropped, never filed under a default", () => {
  // No industry to fall back to and no asset type that names a market of its own.
  assert.equal(marketKeyFor("stock", null), null);
  const out = reduceMarketOverview({
    ...empty(),
    assetGroups: [{ assetType: "stock", market: null, n: 3 }],
  });
  assert.equal(out.reduce((n, m) => n + m.assets, 0), 0);
});

test("the five markets come back in the fixed order", () => {
  const out = reduceMarketOverview(empty());
  assert.deepEqual(out.map((m) => m.market), MARKET_ORDER);
  assert.deepEqual([...MARKET_ORDER], ["US", "PK", "FX", "Commodity", "Crypto"]);
});

test("crypto and commodity do not hide inside US", () => {
  const out = reduceMarketOverview({
    ...empty(),
    assetGroups: [
      { assetType: "stock", market: "US", n: 273 },
      { assetType: "stock", market: "PK", n: 226 },
      { assetType: "crypto", market: "US", n: 76 },
      { assetType: "commodity", market: "US", n: 8 },
      { assetType: "forex", market: "FX", n: 27 },
      { assetType: "etf", market: "US", n: 8 },
    ],
  });
  const by = Object.fromEntries(out.map((m) => [m.market, m.assets]));
  assert.equal(by.US, 281); // stocks + etfs, and nothing else
  assert.equal(by.PK, 226);
  assert.equal(by.FX, 27);
  assert.equal(by.Commodity, 8);
  assert.equal(by.Crypto, 76);
});

test("an industry is filed under the market most of its instruments trade in", () => {
  const out = reduceMarketOverview({
    ...empty(),
    industryRows: [
      // The US "Crypto" industry: every instrument is a coin, so it belongs to Crypto.
      { id: "i1", slug: "crypto", name: "Crypto", market: "US", assetType: "crypto", n: 76 },
      // A mixed energy group: more futures than funds, so it reads under Commodity. Both rows
      // carry the same industry id, which is what the query groups on.
      { id: "i2", slug: "energy-commodities", name: "Energy Commodities", market: "US", assetType: "commodity", n: 3 },
      { id: "i2", slug: "energy-commodities", name: "Energy Commodities", market: "US", assetType: "etf", n: 2 },
      { id: "i4", slug: "psx-banks", name: "PSX Banks", market: "PK", assetType: "stock", n: 18 },
    ],
  });
  const crypto = out.find((m) => m.market === "Crypto")!;
  const commodity = out.find((m) => m.market === "Commodity")!;
  const pk = out.find((m) => m.market === "PK")!;
  assert.deepEqual(crypto.industries.map((i) => i.slug), ["crypto"]);
  assert.deepEqual(commodity.industries.map((i) => i.slug), ["energy-commodities"]);
  // The mixed industry's total is its whole instrument count, not just the winning market's.
  assert.equal(commodity.industries[0].assets, 5);
  assert.deepEqual(pk.industries.map((i) => i.slug), ["psx-banks"]);
});

test("PSX and PK are the same market, not two", () => {
  assert.equal(canonicalMarket("PSX"), "PK");
  const out = reduceMarketOverview({ ...empty(), predictionsByMarket: new Map([["PK", 219]]) });
  assert.equal(out.find((m) => m.market === "PK")!.predictions, 219);
});

test("newest close, factor and quote are the maximum per market, and null when absent", () => {
  const out = reduceMarketOverview({
    ...empty(),
    closeGroups: [
      { assetType: "stock", market: "US", newest: "2026-10-14" },
      { assetType: "etf", market: "US", newest: "2026-10-16" },
      { assetType: "stock", market: "PK", newest: new Date("2026-10-13T00:00:00Z") },
    ],
    factorGroups: [{ assetType: "crypto", market: "US", newest: "2026-10-15" }],
    quoteGroups: [
      { assetType: "stock", market: "US", newest: new Date("2026-10-16T11:00:00Z") },
      { assetType: "forex", market: "FX", newest: new Date("2026-10-14T09:00:00Z") },
    ],
  });
  const us = out.find((m) => m.market === "US")!;
  const pk = out.find((m) => m.market === "PK")!;
  const crypto = out.find((m) => m.market === "Crypto")!;
  const fx = out.find((m) => m.market === "FX")!;
  const commodity = out.find((m) => m.market === "Commodity")!;
  assert.equal(us.newestClose, "2026-10-16");
  assert.equal(pk.newestClose, "2026-10-13");
  assert.equal(crypto.newestFactor, "2026-10-15");
  assert.equal(crypto.newestClose, null);
  assert.equal(fx.newestQuote?.toISOString(), "2026-10-14T09:00:00.000Z");
  assert.equal(commodity.newestQuote, null);
});
