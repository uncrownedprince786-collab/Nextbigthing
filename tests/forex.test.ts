// A currency pair is not a share, and the rule table has to know it.
//
// Forex is the first asset class on this site with no issuer. That single fact decides most of
// what follows: there is no share count, so there is no size; there is no exchange, so there is
// no session and no holiday; and there is no consolidated tape, so there is no volume. Each of
// those is a place where a number could be invented to fill a hole, which hard rule 2 forbids.

import { test } from "node:test";
import assert from "node:assert/strict";
import { STALE_AFTER_DAYS, type Market } from "../lib/decision.ts";
import { marketOf } from "../lib/decisionInput.ts";

test("a currency pair is its own market, read off the asset and not its industry", () => {
  // Off the asset, for the same reason crypto is. How old a close may be before it stops
  // describing the present is a property of what trades, not of which group it is filed under.
  assert.equal(marketOf({ assetType: "forex", industry: { market: "FX" } }), "FX");
  assert.equal(marketOf({ assetType: "forex", industry: { market: "US" } }), "FX");
  assert.equal(marketOf({ assetType: "forex", industry: null }), "FX");
});

test("the other classes are unmoved by forex existing", () => {
  assert.equal(marketOf({ assetType: "crypto", industry: { market: "US" } }), "Crypto");
  assert.equal(marketOf({ assetType: "stock", industry: { market: "US" } }), "US");
  assert.equal(marketOf({ assetType: "stock", industry: { market: "PK" } }), "PSX");
  assert.equal(marketOf({ assetType: "etf", industry: { market: "US" } }), "US");
  assert.equal(marketOf({ assetType: "stock", industry: { market: "???" } }), "Other");
});

test("every market has a staleness rule, so none can fall through to undefined", () => {
  // The gate reads STALE_AFTER_DAYS[market] and compares. A missing entry would be `undefined`,
  // `age > undefined` is false, and the staleness gate would silently stop firing for that whole
  // market -- the one failure a price panel must never commit, passing quietly.
  // Every member of the union, and the list is the point: a market added to `Market` and not
  // to `STALE_AFTER_DAYS` is the hole described above, and TypeScript cannot catch it here
  // because the index signature is satisfied by the type rather than by this array.
  const markets: Market[] = ["US", "PSX", "Crypto", "FX", "Commodity", "Other"];
  for (const m of markets) {
    assert.equal(typeof STALE_AFTER_DAYS[m], "number", `${m} has no staleness rule`);
    assert.ok(STALE_AFTER_DAYS[m] >= 1, `${m} allows a close from the future`);
    assert.ok(STALE_AFTER_DAYS[m] <= 14, `${m} would accept a fortnight old close as current`);
  }
});

test("forex is tighter than the equity markets and looser than crypto", () => {
  // FX runs continuously from Sunday evening to Friday evening, so it keeps no holidays -- but
  // the daily bars are stamped one per weekday, so a Friday close read on Tuesday is 4 days old.
  // Tighter than US and PSX because a pair has no earnings halt, no suspension and no delisting
  // to explain a missing day: a gap here is the feed rather than the instrument. Looser than
  // crypto because crypto genuinely prints a bar every calendar day, weekends included.
  assert.ok(STALE_AFTER_DAYS.FX < STALE_AFTER_DAYS.US);
  assert.ok(STALE_AFTER_DAYS.FX < STALE_AFTER_DAYS.PSX);
  assert.ok(STALE_AFTER_DAYS.FX > STALE_AFTER_DAYS.Crypto);
  assert.equal(STALE_AFTER_DAYS.FX, 4);
});
