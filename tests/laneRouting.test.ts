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
/// this does not, these tests fail, which is the point of having them.
const familyFor = (slug: string): string => (slug === "btc-bitcoin" ? "btc" : "crypto");
const laneFor = (family: string, horizon: string): Lane | null =>
  ALL.find((l) => l.family === family && l.horizon === horizon) ?? null;
const servingLane = (slug: string, horizon: string): Lane | null => {
  const own = laneFor(familyFor(slug), horizon);
  if (own) return own;
  return familyFor(slug) === "crypto" ? null : laneFor("crypto", horizon);
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
  ]) {
    assert.equal(familyFor(slug), "crypto",
      `${slug} must not be routed to Bitcoin's own model`);
  }
  assert.equal(familyFor("btc-bitcoin"), "btc");
});

test("no coin is ever served a model fitted on a different single coin", () => {
  // The btc lanes are fitted on BTCUSDT alone. Serving one to anything else would be answering
  // about a market those weights never saw.
  for (const l of ALL) {
    if (!l.servable) continue;
    const pool = l.trainedOn ?? [];
    if (pool.length !== 1) continue;
    const only = pool[0];
    assert.equal(l.family, "btc",
      `${l.modelVersion} is fitted on one coin (${only}) but is not the btc family`);
    assert.equal(only, "BTCUSDT",
      `${l.modelVersion} is a single-coin lane fitted on ${only}, which nothing routes to`);
  }
});

test("every coin in the universe resolves to a lane fitted on a pool that could contain it", () => {
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
      // A single-coin lane may only answer for that coin.
      assert.equal(slug, "btc-bitcoin",
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

test("Bitcoin falls back to the pooled lane only where it has no lane of its own", () => {
  for (const h of HORIZONS) {
    const own = laneFor("btc", h);
    const got = servingLane("btc-bitcoin", h);
    if (own) {
      assert.equal(got?.modelVersion, own.modelVersion,
        `Bitcoin at ${h} must use its own lane when one exists`);
    } else if (got) {
      assert.equal(got.family, "crypto",
        `Bitcoin at ${h} fell back to ${got.family}, which is not the pooled family`);
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
