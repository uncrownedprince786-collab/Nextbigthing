// A blank tile must name what is missing, and must not promise a reading that cannot come.
//
// The failure this guards is specific. Counting stored bars says BA is ready -- it has 1,960
// sessions -- while the recorder refuses it every run for want of `peerMedianR20` and
// `relStrength`. A page built on the bar count alone tells a reader their reading is pending when
// nothing will ever record it. So `feature-gap` is a status of its own, and the distinction
// between "the data is not there" and "the row has not been written" is asserted here rather than
// left to the component.

import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import {
  readyShare, whyNoReading, type AssetCoverage, type CoverageRegistry,
} from "../lib/coverage.ts";

// Horizons follow the status unless a case overrides them explicitly, which is what the registry
// itself does. Writing a fixture whose status and horizons disagree tests a registry that cannot
// exist -- and my first version of this file did exactly that.
const asset = (over: Partial<AssetCoverage> = {}): AssetCoverage => {
  const status = over.status ?? "ready";
  return {
    market: "US",
    bars: 1960,
    oldest: "2018-01-02",
    newest: "2026-10-19",
    sessionsBehind: 0,
    status,
    horizons: { "1": status, "5": status, "20": status, "60": status },
    ...over,
  };
};

const reg = (assets: Record<string, AssetCoverage>): Pick<CoverageRegistry, "assets"> => ({
  assets,
});

test("a data-ready asset with no row is a recorder gap, not a data gap", () => {
  const v = whyNoReading(reg({ AAPL: asset() }), "AAPL", 5);
  assert.equal(v.kind, "recorder");
});

test("a feature gap is a data gap even though the bars are all there", () => {
  // The case that made this file necessary.
  const ba = asset({
    status: "feature-gap",
    imputedCount: 4,
    why: "every feature the model saw on more than 90% of training rows must be observed: peerMedianR20, relStrength",
  });
  const v = whyNoReading(reg({ BA: ba }), "BA", 5);
  assert.equal(v.kind, "data");
  if (v.kind !== "data") return;
  assert.equal(v.status, "feature-gap");
  assert.match(v.why, /peerMedianR20/);
  assert.equal(v.coverage.bars, 1960, "the history is not the problem and the card says so");
});

test("thin history and staleness are reported as themselves", () => {
  const thin = asset({ bars: 25, status: "thin-history", why: "25 stored sessions" });
  const stale = asset({ status: "stale", sessionsBehind: 14, why: "the newest stored bar is old" });
  for (const [sym, a, want] of [["SOYASUP", thin, "thin-history"], ["OLD", stale, "stale"]] as const) {
    const v = whyNoReading(reg({ [sym]: a }), sym, 5);
    assert.equal(v.kind, "data");
    if (v.kind === "data") assert.equal(v.status, want);
  }
});

test("an asset outside the registry is admitted, not assumed", () => {
  assert.equal(whyNoReading(reg({}), "NOPE", 5).kind, "unknown");
});

test("the per-horizon entry is the authority over the top-level status", () => {
  // Today they always agree; the registry is where that could change, and the rules must read the
  // horizon rather than re-deriving it from the summary.
  const odd = asset({
    status: "ready",
    horizons: { "1": "ready", "5": "thin-history", "20": "ready", "60": "ready" },
    why: "a horizon-specific floor",
  });
  assert.equal(whyNoReading(reg({ X: odd }), "X", 1).kind, "recorder");
  assert.equal(whyNoReading(reg({ X: odd }), "X", 5).kind, "data");
});

test("readyShare counts only the assets that can actually be read", () => {
  const r = readyShare(reg({
    A: asset(),
    B: asset({ status: "feature-gap" }),
    C: asset({ status: "thin-history" }),
  }));
  assert.deepEqual(r, { ready: 1, total: 3 });
});

test("the shipped registry classifies the known cases the way the page expects", async () => {
  const raw = JSON.parse(
    await readFile(
      new URL("../data/foundation/dataset/coverage_registry.json", import.meta.url), "utf-8"),
  ) as CoverageRegistry;
  // BA is the regression case: enough bars, still refused.
  assert.equal(raw.assets.BA?.status, "feature-gap");
  assert.ok((raw.assets.BA?.bars ?? 0) > 1000, "BA's history is long, which is the whole point");
  // Asserted on the substance, not on a raw feature name: the wording now names the industry and
  // the remedy, which is the point. Pinning the identifier would make improving the sentence a
  // test failure.
  assert.match(raw.assets.BA?.why ?? "", /industry/i);
  assert.match(raw.assets.BA?.why ?? "", /are enough/,
    "the card must not blame the history, which is 1,960 sessions long");
  // Every non-ready asset carries an explanation; that is the contract the card relies on.
  for (const [sym, a] of Object.entries(raw.assets)) {
    if (a.status !== "ready") {
      assert.ok(a.why, `${sym} is ${a.status} with no explanation`);
    }
  }
  const { ready, total } = readyShare(raw);
  assert.ok(ready > 0 && ready < total, "a registry where everything or nothing is ready is a bug");
});

test("a small-industry gap is distinguished from a missing input", async () => {
  // These have different remedies: one is closed by adding assets to the industry, the other by
  // fixing a fetch. A page that conflates them tells the owner to backfill history that is
  // already there — which is exactly what the first version of this card did.
  const raw = JSON.parse(
    await readFile(
      new URL("../data/foundation/dataset/coverage_registry.json", import.meta.url), "utf-8"),
  ) as CoverageRegistry & { minPeers: number; gapKinds: Record<string, number> };
  const ba = raw.assets.BA;
  assert.equal(ba?.gapKind, "small-industry");
  assert.ok(ba?.industry, "the industry is named, since that is where the fix happens");
  assert.ok(
    (ba?.industryMembers ?? 0) - 1 < (ba?.peersNeeded ?? raw.minPeers),
    "a small-industry gap must actually be below the peer floor",
  );
  assert.match(ba?.why ?? "", /add assets to this industry/);
  // Every feature-gap asset is classified; an unclassified one would fall back to wording that
  // blames the history.
  for (const [sym, a] of Object.entries(raw.assets)) {
    if (a.status === "feature-gap") {
      assert.ok(a.gapKind, `${sym} is a feature gap with no kind`);
    }
  }
});
