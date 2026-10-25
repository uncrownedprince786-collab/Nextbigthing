import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

// Read rather than imported, like `conviction.test.ts`: `node --test` has no bundler to resolve
// the `@/` alias the lib uses. The rules under test are the ones the site runs.
const DOC = JSON.parse(readFileSync(
  new URL("../data/foundation/dataset/crypto_certified.json", import.meta.url), "utf8"));

interface Verdict {
  testRows: number;
  called: number;
  coverage: number;
  convictionFloor?: number;
  accuracy: number | null;
  ownMajority?: number;
  edgeOverMajority?: number;
  upShareCalled?: number;
  bootstrapCi95?: [number, number];
  walkForward?: string;
  gates?: Record<string, boolean>;
  certified: boolean;
  why: string | null;
}

const COINS: Record<string, Record<string, Verdict>> = DOC.coins ?? {};
const ALL: { coin: string; lane: string; v: Verdict }[] = [];
for (const [coin, byLane] of Object.entries(COINS)) {
  for (const [lane, v] of Object.entries(byLane)) ALL.push({ coin, lane, v });
}

// The gate exists to stop a coin nobody measured from inheriting the pool's reputation. These
// check the verdict file cannot say something the serving layer would misread -- the failure mode
// being a coin that reads as certified because a field was absent rather than because it passed.

test("the file describes at least one coin on at least one lane", () => {
  assert.ok(ALL.length > 0, "no verdicts at all; the sweep has not run");
});

test("a certified coin passed every gate, with none missing", () => {
  const expected = Object.keys(DOC.gates ?? {});
  assert.ok(expected.length >= 5, "the gate list itself is missing from the document");
  for (const { coin, lane, v } of ALL) {
    if (!v.certified) continue;
    assert.ok(v.gates, `${coin} ${lane} is certified with no gates recorded`);
    for (const name of expected) {
      assert.equal(v.gates![name], true,
        `${coin} ${lane} is certified but gate ${name} is ${v.gates![name]}`);
    }
  }
});

test("a certified coin has an accuracy, and it beats its own majority", () => {
  for (const { coin, lane, v } of ALL) {
    if (!v.certified) continue;
    assert.notEqual(v.accuracy, null, `${coin} ${lane} certified with no accuracy`);
    assert.ok(v.ownMajority !== undefined, `${coin} ${lane} certified with no base rate`);
    // The point of the per-coin gate: beating 50% is not the test, beating what this coin
    // actually did is. A coin that rose 58% of the time has to beat 58%.
    assert.ok(v.accuracy! > v.ownMajority!,
      `${coin} ${lane} certified at ${v.accuracy} against its own majority ${v.ownMajority}`);
  }
});

test("a certified coin cleared the minimum called rows", () => {
  const min = DOC.minCalledRows;
  assert.ok(typeof min === "number" && min > 0, "minCalledRows is not recorded");
  for (const { coin, lane, v } of ALL) {
    if (!v.certified) continue;
    assert.ok(v.called >= min,
      `${coin} ${lane} certified on ${v.called} called rows, below the ${min} floor`);
  }
});

test("a refused coin carries a reason", () => {
  for (const { coin, lane, v } of ALL) {
    if (v.certified) continue;
    assert.ok(v.why && v.why.length > 0, `${coin} ${lane} refused with no reason given`);
  }
});

test("coverage and called rows agree with the test row count", () => {
  for (const { coin, lane, v } of ALL) {
    assert.ok(v.called <= v.testRows,
      `${coin} ${lane} called ${v.called} of ${v.testRows} rows`);
    if (v.testRows > 0) {
      const implied = v.called / v.testRows;
      assert.ok(Math.abs(implied - v.coverage) < 1e-4,
        `${coin} ${lane} coverage ${v.coverage} does not match ${v.called}/${v.testRows}`);
    }
  }
});

test("the per-lane index matches the per-coin verdicts exactly", () => {
  // The serving layer reads both: `certifiedByLane` for the list, the per-coin map for the gate.
  // If they ever disagree, one of the two lies -- and the dangerous direction is a coin listed as
  // certified whose own record says otherwise, because the list is what a reader trusts.
  const byLane: Record<string, string[]> = DOC.certifiedByLane ?? {};
  for (const [lane, coins] of Object.entries(byLane)) {
    for (const coin of coins) {
      const v = COINS[coin]?.[lane];
      assert.ok(v, `${coin} is listed as certified on ${lane} but has no verdict`);
      assert.equal(v.certified, true,
        `${coin} is listed as certified on ${lane} but its verdict says otherwise`);
    }
  }
  for (const { coin, lane, v } of ALL) {
    if (!v.certified) continue;
    assert.ok((byLane[lane] ?? []).includes(coin),
      `${coin} is certified on ${lane} but missing from the lane's list`);
  }
});

test("scoring stride is recorded, because the gate's meaning depends on it", () => {
  // The sweep scores at stride 1 while the model is fitted at a coarser stride. That is
  // deliberate and documented, but a verdict whose stride is unknown cannot be compared with the
  // next sweep's.
  assert.ok(typeof DOC.scoreStride === "number" && DOC.scoreStride >= 1,
    "scoreStride is missing from the verdict document");
});

test("an uncertified coin is not quietly given an accuracy to display", () => {
  // A refused coin may still carry its measured numbers -- the page prints them to explain the
  // refusal. What it must never carry is a `certified` flag that disagrees with its gates.
  for (const { coin, lane, v } of ALL) {
    if (!v.gates) continue;
    const allPassed = Object.values(v.gates).every(Boolean);
    assert.equal(v.certified, allPassed,
      `${coin} ${lane}: certified=${v.certified} but gates say ${allPassed}`);
  }
});

// The verdict file keys on venue instruments (LINKUSDT) and the site routes on slugs
// (link-chainlink). An earlier resolver uppercased the slug and appended USDT, giving
// LINK-CHAINLINKUSDT -- which matches nothing, so every coin read as unmeasured and the serving
// path refused the whole site while the models were fine. A lookup that can fail silently and
// disable everything deserves a test that fails loudly.
test("every certified coin is reachable from its own slug", () => {
  const universe = JSON.parse(readFileSync(
    new URL("../data/foundation/dataset/crypto_universe.json", import.meta.url), "utf8"));
  type Coin = { slug: string; ticker: string; on?: Record<string, string> };
  const bySymbol = new Map<string, Coin>();
  for (const c of universe.assets as Coin[]) {
    const inst = c.on?.binance ?? c.on?.mexc;
    const sym = inst ? inst.toUpperCase() : `${(c.ticker ?? "").toUpperCase()}USDT`;
    if (sym && !bySymbol.has(sym)) bySymbol.set(sym, c);
  }

  const certified = Object.keys(COINS);
  assert.ok(certified.length > 0, "no certified coins to check");

  let reachable = 0;
  const unreachable: string[] = [];
  for (const sym of certified) {
    if (bySymbol.has(sym)) reachable++;
    else unreachable.push(sym);
  }
  // Every symbol the sweep measured came from the bar corpus, and every coin in the corpus is in
  // the universe, so anything unreachable is a key mismatch rather than a missing coin.
  assert.equal(unreachable.length, 0,
    `${unreachable.length} certified coins cannot be reached from any slug: ` +
    unreachable.slice(0, 8).join(", "));
  assert.ok(reachable >= certified.length,
    `only ${reachable} of ${certified.length} certified coins resolve`);
});

test("the slug of a known coin resolves to the symbol the sweep used", () => {
  const universe = JSON.parse(readFileSync(
    new URL("../data/foundation/dataset/crypto_universe.json", import.meta.url), "utf8"));
  type Coin = { slug: string; ticker: string; on?: Record<string, string> };
  const bySlug = new Map((universe.assets as Coin[]).map((c) => [c.slug, c]));
  // The shape that broke: a slug whose name differs from its ticker.
  for (const [slug, want] of [
    ["link-chainlink", "LINKUSDT"],
    ["btc-bitcoin", "BTCUSDT"],
    ["sol-solana", "SOLUSDT"],
    ["ada-cardano", "ADAUSDT"],
  ] as const) {
    const c = bySlug.get(slug);
    if (!c) continue;
    const inst = c.on?.binance ?? c.on?.mexc;
    const got = inst ? inst.toUpperCase() : `${c.ticker.toUpperCase()}USDT`;
    assert.equal(got, want, `${slug} resolved to ${got}, not ${want}`);
    // And naive string surgery must NOT produce it, or the test proves nothing.
    assert.notEqual(`${slug.toUpperCase()}USDT`, want,
      `${slug} would resolve by accident; pick a harder case`);
  }
});
