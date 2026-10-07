// A front month contract is not a US listing that happens to be filed under a metals group.
//
// The site had carried gold and silver futures since the precious metals group was seeded, and
// they sat in market `US` among a hundred and twenty-eight shares. That had three consequences,
// and only the first is cosmetic: they were unfindable; they were compared against shares; and
// the page they appeared on promised "US stocks, funds and commodities" while the two futures on
// it were the only commodities the site held -- no copper contract, and no barrel of oil behind
// eight listed oil companies.
//
// What separates this class from forex, which was the last one added, is volume. A pair has no
// consolidated tape so it can never be confirmed; a future publishes a volume on every bar, so
// the confirmation applies to it exactly as it does to a share. That is why this is its own
// market and not an extension of FX.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { STALE_AFTER_DAYS, VOLUME_CONFIRMS_AT, type Market } from "../lib/decision.ts";
import { marketOf } from "../lib/decisionInput.ts";

// `lib/assetClass.ts` imports through the `@/` alias, which only the bundler resolves, so it
// cannot be imported here the way `decision.ts` can -- which is why no test in this directory
// imports it. The three facts below are therefore read off the source. A source scan is a weaker
// test than a call, and it is the one available: the alternative is no guard at all on the step
// where a market becomes a page, and that step is exactly where the futures were lost.
const classes = readFileSync(new URL("../lib/assetClass.ts", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");

test("a contract is its own market, read off the asset and not its industry", () => {
  // Off the asset, for the same reason crypto and forex are. What trades when, and how old a
  // close may be before it stops describing the present, is a property of the instrument.
  assert.equal(marketOf({ assetType: "commodity", industry: { market: "US" } }), "Commodity");
  assert.equal(marketOf({ assetType: "commodity", industry: null }), "Commodity");
});

test("a fund that holds the metal is still a US listing", () => {
  // GLD, SLV, CPER and COPX are `etf`, and an ETF is a US listed fund with an issuer, a share
  // count and a size figure. Sweeping them into Commodities because of what they track would
  // put a size on a page that says there is none, and would take them off the page where a
  // reader comparing them against other US funds expects to find them.
  assert.equal(marketOf({ assetType: "etf", industry: { market: "US" } }), "US");
  assert.equal(marketOf({ assetType: "stock", industry: { market: "US" } }), "US");
});

test("the other classes are unmoved by commodities existing", () => {
  assert.equal(marketOf({ assetType: "crypto", industry: { market: "US" } }), "Crypto");
  assert.equal(marketOf({ assetType: "forex", industry: { market: "FX" } }), "FX");
  assert.equal(marketOf({ assetType: "stock", industry: { market: "PK" } }), "PSX");
  assert.equal(marketOf({ assetType: "stock", industry: { market: "???" } }), "Other");
});

test("a contract gets a staleness rule, and it is the weekday one", () => {
  // These venues trade almost around the clock from Sunday evening to Friday evening and settle
  // once a day, so the daily bar has the same weekend hole an equity's has. 5 for the reason US
  // equities get 5: the CME and ICE keep the US holiday calendar, and a Good Friday must not
  // read as a dead feed. Not tighter, for that reason; not looser, because a front month
  // contract rolls rather than stops and has no suspension to explain a missing day.
  assert.equal(typeof STALE_AFTER_DAYS.Commodity, "number");
  assert.equal(STALE_AFTER_DAYS.Commodity, 5);
  assert.equal(STALE_AFTER_DAYS.Commodity, STALE_AFTER_DAYS.US);
  assert.ok(STALE_AFTER_DAYS.Commodity > STALE_AFTER_DAYS.Crypto);
});

test("volume confirmation is available here, which is what separates it from forex", () => {
  // The distinction worth pinning. `VOLUME_CONFIRMS_AT` is unreachable for a pair because no
  // volume is published anywhere in FX, and `closeness` is null for one rather than 0. A future
  // publishes a volume per bar, so the volume leg of a setup is a real test on this class and
  // the reading can reach High the way a share's can.
  assert.equal(typeof VOLUME_CONFIRMS_AT, "number");
  assert.ok(VOLUME_CONFIRMS_AT > 1);
});

test("every market a reader can browse has exactly one class claiming it", () => {
  // The fault this change fixes, stated generally. A market with no class is a set of assets
  // that are priced, ranked and decided on and then rendered nowhere -- which is what
  // `Commodity` would be the moment `marketOf` learned to return it and nothing claimed it, and
  // close to what the futures were while they were filed as US. A market claimed twice is the
  // same name on two pages with two sort orders.
  const browsable: Market[] = ["US", "PSX", "Crypto", "FX", "Commodity"];
  for (const market of browsable) {
    const owners = classes.match(new RegExp(`market === "${market}"`, "g")) ?? [];
    assert.equal(owners.length, 1, `${market} is claimed by ${owners.length} asset classes`);
  }
});

test("the class is reachable: a slug, a route and a place in the nav", () => {
  // Three separate things had to be added for the page to exist and be findable, and a reader
  // cannot get to it if any one of them is missing. The route is the one that fails silently --
  // a nav entry pointing at a path with no page is a 404 the build does not complain about.
  assert.match(classes, /slug: "commodities"/);
  assert.ok(
    existsSync(new URL("../app/commodities/page.tsx", import.meta.url)),
    "the nav points at /commodities but no route renders it",
  );
  assert.match(layout, /href: "\/commodities"/);
});

test("the stocks page no longer promises commodities it does not hold", () => {
  // It read "US stocks, funds and commodities" while holding two futures, and now holds none:
  // the contracts have their own class. A heading that over-claims is the same class of error as
  // a missing page, because a reader who believes it stops looking.
  assert.ok(
    !/title: "US stocks, funds and commodities"/.test(classes),
    "the stocks class still claims the commodities that moved out of it",
  );
});
