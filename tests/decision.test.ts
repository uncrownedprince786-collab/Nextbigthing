// Every gate in the rule table, asserted. Run with `npm run test:web`.
//
// These tests need no database, no network and no clock: `decide` takes `today` as an input, so a
// staleness test cannot start passing or failing because of the date it is run on. That is the
// whole reason the rule table is a pure module.
//
// What each test is really guarding is the *order* of the gates. A rule table is easy to write and
// easy to reorder by accident, and reordering it changes what a reader is told to do with money.

import { test } from "node:test";
import assert from "node:assert/strict";
import { decide, type DecisionInput, STALE_AFTER_DAYS } from "../lib/decision.ts";

/// A healthy LONG. Every test below starts from this and breaks exactly one thing, so the thing
/// being tested is the only difference from a known-good answer.
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
    invalidation: 94,
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

test("the healthy case is LONG, NOW, High", () => {
  const d = decide(base());
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "long");
  assert.equal(d.timeSense, "NOW");
  assert.equal(d.confidence, "High");
  assert.deepEqual(d.missing, []);
  assert.equal(d.invalidation, 94);
});

test("a down setup with a down longer view is SHORT", () => {
  const d = decide(base({ setup: { direction: "down", horizon: "swing" }, horizon: { direction: "down" } }));
  assert.equal(d.action, "SHORT");
  assert.equal(d.confidence, "High");
});

// --- Gate 1: nothing stored -------------------------------------------------------------------

test("no stored prices is WAIT and names the symbol", () => {
  for (const over of [{ asOf: null }, { lastClose: null }]) {
    const d = decide(base(over as Partial<DecisionInput>));
    assert.equal(d.action, "WAIT");
    assert.equal(d.gate, "no-prices");
    assert.equal(d.missing.length, 1);
    assert.match(d.missing[0], /AAPL/);
  }
});

// --- Gate 2: staleness ------------------------------------------------------------------------

test("a close past the market's own limit is WAIT with the age in the reason", () => {
  const d = decide(base({ asOf: "2026-09-20", today: "2026-10-03" }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "stale");
  assert.match(d.why[0], /stale/i);
  assert.match(d.why[0], /2026-09-20/);
  assert.match(d.why[0], /13 days old/);
});

test("the staleness limit differs per market, and crypto is the strict one", () => {
  // Three days old: fine for a US equity over a weekend, already a fault for a coin.
  const asOf = "2026-09-30";
  const today = "2026-10-03";
  assert.equal(decide(base({ market: "US", asOf, today })).action, "LONG");
  assert.equal(decide(base({ market: "Crypto", asOf, today })).gate, "stale");
  assert.equal(decide(base({ market: "PSX", asOf, today })).action, "LONG");
  assert.ok(STALE_AFTER_DAYS.Crypto < STALE_AFTER_DAYS.US);
  assert.ok(STALE_AFTER_DAYS.US < STALE_AFTER_DAYS.PSX);
});

test("exactly at the limit is still actionable, one day past it is not", () => {
  const today = "2026-10-03";
  // US allows 5 calendar days.
  assert.equal(decide(base({ market: "US", asOf: "2026-09-28", today })).action, "LONG");
  assert.equal(decide(base({ market: "US", asOf: "2026-09-27", today })).gate, "stale");
});

test("an unreadable stored date is WAIT, not a crash and not a trade", () => {
  const d = decide(base({ asOf: "not-a-date" }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "bad-date");
});

// --- Gate 3: a silent source ------------------------------------------------------------------

test("a silent source is WAIT and the source is named", () => {
  const d = decide(base({ sourceSilent: "Binance" }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "source-silent");
  assert.match(d.why[0], /Binance/);
  assert.match(d.missing[0], /Binance/);
});

// --- Gate 4: no level to be wrong at ----------------------------------------------------------

test("no invalidation level is WAIT however good the setup looks", () => {
  const d = decide(base({ invalidation: null }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "no-invalidation");
  assert.equal(d.missing.length, 1);
});

// --- Gate 5: disagreement ---------------------------------------------------------------------

test("opposite timeframes are WAIT and both directions are stated", () => {
  const d = decide(base({ setup: { direction: "up", horizon: "swing" }, horizon: { direction: "down" } }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "mixed-horizons");
  assert.match(d.why[0], /setup is up/i);
  assert.match(d.why[0], /longer view is down/i);
  // A disagreement is not a data fault, so nothing is reported missing.
  assert.deepEqual(d.missing, []);
});

test("the mirror case is also WAIT", () => {
  const d = decide(base({ setup: { direction: "down", horizon: "swing" }, horizon: { direction: "up" } }));
  assert.equal(d.gate, "mixed-horizons");
});

// --- Gate 6: a move nobody has explained ------------------------------------------------------

test("an unusual move with thin news is WAIT", () => {
  const d = decide(base({ unusualMove: true, newsCount: 1 }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "unexplained-move");
  assert.match(d.why[0], /news thin/i);
});

test("news never checked reads differently from news checked and thin", () => {
  const d = decide(base({ unusualMove: true, newsCount: null }));
  assert.equal(d.gate, "unexplained-move");
  assert.match(d.why[0], /not checked/i);
});

test("an unusual move with real news behind it still trades", () => {
  assert.equal(decide(base({ unusualMove: true, newsCount: 9 })).action, "LONG");
});

test("thin news on a quiet name is not a gate", () => {
  // The point of pairing the two conditions: a quiet stock with no headlines is normal.
  assert.equal(decide(base({ unusualMove: false, newsCount: 0 })).action, "LONG");
});

// --- Gate 9: the fall-through -----------------------------------------------------------------

test("a flat setup falls through to WAIT rather than to a direction", () => {
  const d = decide(base({ setup: { direction: "flat", horizon: null } }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "incomplete");
  // `flat` is setup.py's `wait`: the trend was clear and the conditions behind it were not all
  // present, so the direction was measured and withheld. It is deliberately not acted on, and
  // the sentence must not call it neutral — "flat" is what `unknown` is, and the two arrive here
  // from different branches of the job. See directionOfState in lib/decisionInput.ts.
  assert.match(d.why[0], /a direction is showing/i);
  assert.doesNotMatch(d.why.join(" "), /between its own averages/i);
});

test("an absent setup says the direction is missing, not that it is neutral", () => {
  // The other half of the pair. `unknown` is setup.py's `none` — price between its averages —
  // and this is the one that is genuinely directionless. Printing one sentence for both states
  // is what made every crypto page explain a real verdict with the wrong market.
  const d = decide(base({ setup: { direction: "unknown", horizon: null } }));
  assert.equal(d.gate, "incomplete");
  assert.match(d.why.join(" "), /no clear direction to measure/i);
  assert.doesNotMatch(d.why[0], /a direction is showing/i);
});

test("an absent setup is WAIT and says which reading is absent", () => {
  const d = decide(base({ setup: null, horizon: null }));
  assert.equal(d.gate, "incomplete");
  assert.equal(d.missing.length, 2);
  assert.ok(d.missing.some((m) => /setup direction/i.test(m)));
  assert.ok(d.missing.some((m) => /longer-term/i.test(m)));
});

test("no gate can return an empty reason", () => {
  // The one invariant across the whole table: a reader is never shown a bare verdict. Every WAIT
  // has either a why line or a named missing item, and every action has a why line.
  const cases: Partial<DecisionInput>[] = [
    {},
    { asOf: null },
    { asOf: "2026-01-01" },
    { asOf: "nope" },
    { sourceSilent: "Yahoo Finance" },
    { invalidation: null },
    { setup: { direction: "up", horizon: null }, horizon: { direction: "down" } },
    { unusualMove: true, newsCount: 0 },
    { setup: { direction: "flat", horizon: null } },
    { setup: null, horizon: null },
    { setup: { direction: "down", horizon: "swing" }, horizon: { direction: "down" } },
  ];
  for (const over of cases) {
    const d = decide(base(over));
    assert.ok(d.why.length > 0 || d.missing.length > 0, `silent verdict for ${JSON.stringify(over)}`);
      assert.ok(d.why.length <= 3, `more than three why lines for ${JSON.stringify(over)}`);
    assert.ok(d.measured.startsWith("Measured, not guaranteed."));
  }
});

// --- Time sense ------------------------------------------------------------------------------

test("a dated event soon outranks everything else in the time sense", () => {
  assert.equal(decide(base({ eventInDays: 1 })).timeSense, "CARE");
  assert.equal(decide(base({ eventInDays: 3 })).timeSense, "CARE");
  assert.equal(decide(base({ eventInDays: 9 })).timeSense, "NOW");
  // Including when the action itself is WAIT: an event is a reason to pay attention either way.
  assert.equal(decide(base({ eventInDays: 1, invalidation: null })).timeSense, "CARE");
});

test("a price outside the band is WAIT FOR LEVEL, not NOW", () => {
  assert.equal(decide(base({ lastClose: 110 })).timeSense, "WAIT FOR LEVEL");
  assert.equal(decide(base({ lastClose: 98 })).timeSense, "NOW");
  assert.equal(decide(base({ lastClose: 102 })).timeSense, "NOW");
});

test("no entry band means the reader cannot be told NOW", () => {
  const d = decide(base({ entry: null }));
  assert.equal(d.action, "LONG");
  assert.equal(d.timeSense, "WAIT FOR LEVEL");
  assert.ok(d.missing.some((m) => /entry band/.test(m)), d.missing.join(" | "));
});

// --- Confidence ------------------------------------------------------------------------------

test("confidence counts what confirms the direction, and WAIT is always Low", () => {
  // Three confirmations: a second horizon agreeing, volume above its average, and an analog set
  // leaning the same way.
  assert.equal(decide(base()).confidence, "High");

  // Two of the three is still High.
  assert.equal(decide(base({ horizon: { direction: "flat" } })).confidence, "High");

  // One alone is Medium: the horizon agrees, but volume is unpublished and the analog set is
  // below the floor that its own job will grade.
  assert.equal(
    decide(base({ volumeRatio: null, analogs: { count: 4, lowPct: -1, highPct: 1 } })).confidence,
    "Medium",
  );

  // Nothing confirms: one directional horizon, no volume, no usable analogs.
  assert.equal(
    decide(base({ horizon: null, volumeRatio: null, analogs: null })).confidence,
    "Low",
  );

  assert.equal(decide(base({ setup: { direction: "flat", horizon: null } })).confidence, "Low");
});

test("an absent factor is missing evidence, not evidence against", () => {
  // The distinction that keeps a lane from emptying itself: no published volume must not read
  // the same as volume that failed to confirm.
  const unpublished = decide(base({ volumeRatio: null }));
  const failed = decide(base({ volumeRatio: 0.4 }));
  assert.equal(unpublished.action, "LONG");
  assert.equal(failed.action, "LONG");
  assert.ok(unpublished.missing.some((m) => /No volume published/.test(m)));
  assert.ok(!failed.missing.some((m) => /No volume published/.test(m)));
});

test("a direction still prints when nothing confirms it, and says so", () => {
  // Refusing every name for want of a factor nobody has computed is how the lists emptied once
  // already. The direction prints at Low with the gap named.
  const d = decide(base({ horizon: null, volumeRatio: null, analogs: null }));
  assert.equal(d.action, "LONG");
  assert.equal(d.confidence, "Low");
  assert.match(d.why[2], /Nothing further confirms it/);
  assert.ok(d.missing.some((m) => /No volume published/.test(m)));
  assert.ok(d.missing.some((m) => /No similar past days/.test(m)));
});

test("a name far behind its peers does not read LONG", () => {
  const d = decide(base({ relStrength: -4 }));
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "peers-against");
  assert.match(d.why[0], /behind its peers/);
  // Mirrored for a short: a name holding up better than its group is not a short.
  const short = decide(
    base({ setup: { direction: "down", horizon: "swing" }, horizon: { direction: "down" }, relStrength: 4 }),
  );
  assert.equal(short.gate, "peers-against");
  // Inside the band, or unknown, is not a gate.
  assert.equal(decide(base({ relStrength: -1 })).action, "LONG");
  assert.equal(decide(base({ relStrength: null })).action, "LONG");
});

// --- The honesty line -------------------------------------------------------------------------

test("the measured line quotes a range only when enough analogs back it", () => {
  assert.match(decide(base()).measured, /Past similar days range: -3\.2% to \+6\.4%\./);
  assert.match(
    decide(base({ analogs: { count: 2, lowPct: -1, highPct: 1 } })).measured,
    /Not enough similar past days/,
  );
  assert.match(decide(base({ analogs: null })).measured, /Not enough similar past days/);
  assert.match(
    decide(base({ analogs: { count: 9, lowPct: null, highPct: null } })).measured,
    /Not enough similar past days/,
  );
});

test("decide is pure: the same input twice gives the same answer", () => {
  const input = base({ unusualMove: true, newsCount: 1 });
  assert.deepEqual(decide(input), decide(input));
});

// --- The second why line must not claim corroboration that does not exist ---------------------
//
// Added after the live database produced WAIT for all 160 assets. The cause was upstream, in which
// horizon was read as the setup, but it exposed this too: a single-horizon signal was being
// described as one the longer view did not disagree with, which a reader hears as a second opinion.

test("an agreeing longer view says so", () => {
  assert.equal(decide(base()).why[1], "Longer view agrees.");
  const short = base({
    setup: { direction: "down", horizon: "swing" },
    horizon: { direction: "down" },
  });
  assert.equal(decide(short).why[1], "Longer view agrees.");
});

test("no longer view says that, rather than implying one agreed", () => {
  const d = decide(base({ horizon: null }));
  assert.equal(d.action, "LONG");
  assert.match(d.why[1], /Only one time frame points anywhere/);
  // Volume and the analog set still confirm, so it is High on two counts rather than three.
  assert.equal(d.confidence, "High");
  // With nothing else behind it, the same missing horizon lands at Low.
  assert.equal(decide(base({ horizon: null, volumeRatio: null, analogs: null })).confidence, "Low");
});

test("a flat longer view is named as flat", () => {
  assert.equal(decide(base({ horizon: { direction: "flat" } })).why[1], "Longer view is flat.");
});

test("a large analog set with no recorded lean says so, instead of asking for more days", () => {
  // Seen live: ABBV printed "Only 375 similar past days stored; 8 are needed to confirm". The set
  // was large; what was absent was the lean. Telling a reader to wait for 8 of something they
  // already have 375 of is worse than saying nothing.
  const d = decide(base({ analogs: { count: 375, lowPct: -11, highPct: 16.1, medianPct: null, positive: null } }));
  assert.equal(d.action, "LONG");
  const line = d.missing.find((m) => /similar past days/.test(m));
  assert.ok(line, d.missing.join(" | "));
  assert.doesNotMatch(String(line), /Only 375/);
  assert.match(String(line), /which way they went was not recorded/);
  // The genuinely-too-few case still reads the old way.
  const few = decide(base({ analogs: { count: 3, lowPct: -1, highPct: 1, medianPct: 0.2, positive: 2 } }));
  assert.ok(few.missing.some((m) => /Only 3 similar past days/.test(m)), few.missing.join(" | "));
  // And none at all is its own sentence.
  const none = decide(base({ analogs: null }));
  assert.ok(none.missing.some((m) => /No similar past days stored/.test(m)));
});
