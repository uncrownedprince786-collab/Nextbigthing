import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

// Read rather than imported, like conviction.test.ts: `node --test` has no bundler to resolve
// the `@/` alias. The rule under test is the one the site runs.
const LANES = JSON.parse(readFileSync(
  new URL("../data/foundation/dataset/crypto_lanes.json", import.meta.url), "utf8"));
const UNIVERSE = JSON.parse(readFileSync(
  new URL("../data/foundation/dataset/crypto_universe.json", import.meta.url), "utf8"));

interface Lane {
  family: string;
  horizon: string;
  servable: boolean;
  trainedOn?: string[];
  modelVersion: string;
}
const ALL: Lane[] = LANES.lanes;

/// Mirrors lib/cryptoLanes.familyFor. Duplicated deliberately: if the serving rule changes and
/// this does not, these tests fail, which is the point of having them -- and it did, when the
/// eight new per-coin families landed and this copy still knew only Bitcoin.
const OWN_MODEL: Record<string, string> = {
  "btc-bitcoin": "btc",
  "eth-ethereum": "eth",
  "sol-solana": "sol",
  "xrp-xrp": "xrp",
  "ada-cardano": "ada",
  "link-chainlink": "link",
  "avax-avalanche": "avax",
  "dot-polkadot": "dot",
  "sui-sui": "sui",
};
const familyFor = (slug: string): string => OWN_MODEL[slug] ?? "crypto";
const laneFor = (family: string, horizon: string): Lane | null =>
  ALL.find((l) => l.family === family && l.horizon === horizon) ?? null;
const servingLane = (slug: string, horizon: string): Lane | null => {
  const family = familyFor(slug);
  const own = laneFor(family, horizon);
  if (own?.servable) return own;
  const pooled = family === "crypto" ? null : laneFor("crypto", horizon);
  if (pooled?.servable) return pooled;
  return own ?? pooled;
};

const HORIZONS = ["m5", "m15", "h1", "h4", "d1", "d5", "d20"];

// Bitcoin having its own models is a real split in the serving path, and the failure it invites
// is quiet: a coin answered by a model fitted on a different coin's bars produces a confident
// direction about a market the model has never seen. Nothing on the page would look wrong.

test("only Bitcoin is routed to the Bitcoin family", () => {
  // The match is on the exact slug, so the near-misses are what matter: a wrapped or renamed
  // Bitcoin, or any slug that merely contains the letters.
  for (const slug of [
    "wbtc-wrapped-bitcoin", "btcb-bitcoin-bep2", "bitcoin-cash", "bch-bitcoin-cash",
    "btc", "bitcoin", "tbtc-tbtc", "btc-bitcoin-wrapped", "xbt-bitcoin",
    // Near-misses for the eight new per-coin families, which are the same hazard again.
    "weth-weth", "steth-lido-staked-ether", "ethw-ethereum-pow", "eth",
    "sol", "solana", "wsol-wrapped-solana", "link", "ada", "sui", "dot", "avax", "xrp",
    "xrp-ripple", "linka-linka", "adax-adax",
  ]) {
    assert.equal(familyFor(slug), "crypto",
      `${slug} must not be routed to Bitcoin's own model`);
  }
  assert.equal(familyFor("btc-bitcoin"), "btc");
});

test("a single-coin lane is only reachable by the coin it was fitted on", () => {
  // Nine coins now have their own models, so "only btc is single-coin" is no longer the rule.
  // The rule that matters never changed: a lane fitted on one coin's bars must be unreachable
  // by every other coin. Checked by resolving each single-coin lane's family back through the
  // routing and insisting the slug that lands there is that same coin.
  const bySlug = new Map(
    (UNIVERSE.assets as { slug: string; ticker: string }[]).map((c) => [c.slug, c]),
  );
  for (const l of ALL) {
    if (!l.servable) continue;
    const pool = l.trainedOn ?? [];
    if (pool.length !== 1) continue;
    const only = pool[0].toUpperCase();

    // Every slug that routes to this family must be the coin the lane was fitted on.
    const reaching = [...bySlug.keys()].filter((s) => familyFor(s) === l.family);
    assert.ok(reaching.length > 0,
      `${l.modelVersion} is fitted on ${only} but no slug routes to it`);
    for (const slug of reaching) {
      const ticker = (bySlug.get(slug)?.ticker ?? "").toUpperCase();
      assert.ok(only === `${ticker}USDT` || only === ticker,
        `${slug} routes to ${l.modelVersion}, which was fitted on ${only} alone`);
    }
  }
});

test("every coin in the universe resolves to a lane fitted on a pool that could contain it", () => {
  const bySlugAll = new Map(
    (UNIVERSE.assets as { slug: string; ticker: string }[]).map((c) => [c.slug, c]),
  );
  const sample: string[] = UNIVERSE.assets
    .slice(0, 400)
    .map((a: { slug: string }) => a.slug)
    .filter((s: string): s is string => typeof s === "string");
  assert.ok(sample.length > 50, "universe sample is too small to be a check");

  for (const slug of [...sample, "btc-bitcoin"]) {
    for (const h of HORIZONS) {
      const lane = servingLane(slug, h);
      if (!lane || !lane.servable) continue;
      const pool = lane.trainedOn ?? [];
      if (pool.length !== 1) continue;
      // A single-coin lane may only answer for that coin -- checked against the coin's own
      // ticker rather than a hardcoded slug, now that nine coins have their own models.
      const ticker = (bySlugAll.get(slug)?.ticker ?? "").toUpperCase();
      const only = pool[0].toUpperCase();
      assert.ok(only === `${ticker}USDT` || only === ticker,
        `${slug} at ${h} resolves to ${lane.modelVersion}, fitted only on ${pool[0]}`);
    }
  }
});

test("a crypto coin never falls back to the Bitcoin family", () => {
  // The fallback runs one way on purpose. A coin with no pooled lane is served nothing; it is
  // never handed Bitcoin's weights because those happen to exist.
  for (const h of HORIZONS) {
    const pooled = laneFor("crypto", h);
    if (pooled) continue;              // nothing to fall back from
    const got = servingLane("sol-solana", h);
    assert.equal(got, null,
      `with no crypto lane at ${h}, a coin must be served nothing, not ${got?.modelVersion}`);
  }
});

test("a coin uses its own lane when that lane is servable, and the pool otherwise", () => {
  // "When one exists" was the old rule and it was wrong: a dedicated lane that failed its gates
  // is worse than the pooled lane that passed, so routing on the name alone would quietly
  // downgrade the coin. btc:h4 is exactly that case -- it exists, it is refused, and Bitcoin is
  // correctly answered by crypto:h4 instead.
  for (const slug of Object.keys(OWN_MODEL)) {
    const family = familyFor(slug);
    for (const h of HORIZONS) {
      const own = laneFor(family, h);
      const got = servingLane(slug, h);
      if (!got) continue;
      if (own?.servable) {
        assert.equal(got.modelVersion, own.modelVersion,
          `${slug} at ${h} has a servable own lane but was served ${got.modelVersion}`);
      } else if (got.servable) {
        assert.equal(got.family, "crypto",
          `${slug} at ${h} fell back to ${got.family}, which is neither its own nor the pool`);
      }
    }
  }
});

test("every servable lane records what it was trained on", () => {
  // Without this the checks above silently pass on absence rather than on agreement.
  for (const l of ALL) {
    if (!l.servable) continue;
    assert.ok(Array.isArray(l.trainedOn) && l.trainedOn.length > 0,
      `${l.modelVersion} is servable but records no training pool`);
  }
});
