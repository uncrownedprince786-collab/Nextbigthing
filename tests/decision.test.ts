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
import { readFileSync } from "node:fs";
import {
  decide,
  confirmingLegs,
  LEGS,
  type DecisionInput,
  STALE_AFTER_DAYS,
  ANALOG_SHARE_CONFIRMS,
  CONFIDENCE_ORDER,
} from "../lib/decision.ts";

/// A healthy LONG. Every test below starts from this and breaks exactly one thing, so the thing
/// being tested is the only difference from a known-good answer.
/// The stop a valid plan carries for whichever way the row points: below the close for a long,
/// above it for a short. The fixtures used 94 for both, which gave every SHORT a stop below the
/// price -- a plan already invalidated, and exactly the defect `stopCrossed` now refuses. Mirrored
/// here rather than weakened there. An explicit `invalidation` in a test still overrides it.
function stopFor(over: Partial<DecisionInput>): number {
  const s = over.setup;
  const down =
    s?.direction === "down" ||
    s?.trend === "down" ||
    (s?.trend !== "up" && s?.bias === "down");
  return down ? 106 : 94;
}

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
    invalidation: stopFor(over),
    // A measured target, so the healthy case carries a complete plan and the tests that break
    // one thing break it against a decision that had a reward figure to lose. 1.5x is
    // deliberately under `ASYMMETRY_CLEARS`: the base case must not silently qualify for a
    // bypass, or every gate below it would be tested with its escape hatch already open.
    target: { method: "structure", low: 108, high: 112, rewardRisk: 1.5 },
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

test("opposite timeframes print the nearer read and note the disagreement", () => {
  // This was a WAIT until 2026-10-09. A swing read and a quarterly read measure different
  // windows and answer different questions -- which is the sentence the horizons block on every
  // asset page has always carried -- so refusing both because they differ withheld the nearer
  // one on the strength of the further one.
  const d = decide(base({ horizon: { direction: "down" } }));
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "long");
  assert.ok(
    d.notes.some((n) => /longer view reads down where this reads up/.test(n)),
    d.notes.join(" | "),
  );
  // It still costs a grade: `confidenceFor` counts an agreeing second timeframe and there is
  // none to count. The base case is High on three legs; this has two.
  assert.equal(d.confidence, "High");
  assert.match(d.why[1], /Longer view does not disagree|does not disagree/);
});

test("the mirror case prints too", () => {
  const d = decide(
    base({ setup: { direction: "down", horizon: "swing" }, horizon: { direction: "up" } }),
  );
  assert.equal(d.action, "SHORT");
  assert.ok(
    d.notes.some((n) => /longer view reads up where this reads down/.test(n)),
    d.notes.join(" | "),
  );
});

test("an unusual move with thin news is a note on the direction, not a refusal", () => {
  // This gate was a WAIT for 60 of 477 names on 2026-10-09, every one of them over a measured
  // direction and a stored invalidation. Thin news under a move says the published explanation
  // has not arrived; it is not evidence that the direction is wrong, and the table no longer
  // treats it as though it were.
  const d = decide(base({ unusualMove: true, newsCount: 1 }));
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "long");
  assert.equal(d.notes.length, 1);
  assert.match(d.notes[0], /moved unusually on 1 recent story/i);
  // Demoted, not deleted: the reader still sees it.
  assert.match(d.notes[0], /nothing published accounts for the move/i);
});

test("news never checked reads differently from news checked and thin", () => {
  // Rule 21 survives the demotion. A null count is "no feed answered for this name" and a low
  // count is "the feeds answered and there was little there", and one sentence for both would
  // tell the reader the second when the truth is the first.
  const d = decide(base({ unusualMove: true, newsCount: null }));
  assert.equal(d.action, "LONG");
  assert.equal(d.notes.length, 1);
  assert.match(d.notes[0], /no news has been collected/i);
  assert.doesNotMatch(d.notes[0], /recent stor/i);
});

test("an unusual move with real news behind it carries no note", () => {
  const d = decide(base({ unusualMove: true, newsCount: 9 }));
  assert.equal(d.action, "LONG");
  assert.deepEqual(d.notes, []);
});

test("thin news on a quiet name is neither a gate nor a note", () => {
  // The point of pairing the two conditions: a quiet stock with no headlines is normal.
  const d = decide(base({ unusualMove: false, newsCount: 0 }));
  assert.equal(d.action, "LONG");
  assert.deepEqual(d.notes, []);
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
  // With no volume ratio the analog absence is not "still collecting": the matcher needs one,
  // so nothing can ever match. The line says the mechanism without claiming why it is missing.
  assert.ok(d.missing.some((m) => /No similar past days can be matched without a volume ratio/.test(m)));
});

test("a name far behind its peers still reads LONG, with the lag noted and the grade capped", () => {
  // -9 against the US band of 7.5. The fixture's market is US, and the band is per market now:
  // see REL_BAND, and the test below for why one number could not serve both FX and crypto.
  const d = decide(base({ relStrength: -9 }));
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "long");
  // Principle 2 has not been dropped. The lag is printed with its own measured value -- rule 21,
  // three values and not one -- and it costs a confidence step, so the grade can never read more
  // confident than the note under it (rule 6). The base case is High; this is Medium.
  assert.equal(d.confidence, "Medium");
  assert.equal(d.notes.length, 1);
  assert.match(d.notes[0], /9\.0 points behind its peers/);

  // Mirrored for a short: a name holding up better than its group is still a short, noted.
  const short = decide(
    base({ setup: { direction: "down", horizon: "swing" }, horizon: { direction: "down" }, relStrength: 9 }),
  );
  assert.equal(short.action, "SHORT");
  assert.equal(short.confidence, "Medium");
  assert.match(short.notes[0], /9\.0 points ahead of its peers/);

  // Inside the band, or unknown, is neither a note nor a cap.
  for (const rel of [-5, null]) {
    const inside = decide(base({ relStrength: rel }));
    assert.equal(inside.action, "LONG");
    assert.equal(inside.confidence, "High");
    assert.deepEqual(inside.notes, []);
  }
});

test("a name ahead of its peers is confirmed by it, which it never used to be", () => {
  // The asymmetry this fixes: `peersAgainst` existed and `peersConfirm` did not, so one stored
  // measurement could subtract a grade and could never add one. Principle 2 says relative
  // strength matters more than a raw return; the rules were only ever reading its bad half.
  const bare = base({ horizon: null, volumeRatio: 0.4, relStrength: 0, analogs: null });
  assert.equal(decide(bare).confidence, "Low");
  assert.match(decide(bare).why[2], /Nothing further confirms it|Neither volume/);

  const leading = decide({ ...bare, relStrength: 9.2 });
  assert.equal(leading.confidence, "Medium");
  assert.match(leading.why[2], /9\.2 points ahead of its peers over 20 sessions/);

  // Mirrored for a short: behind its peers confirms a fall.
  const falling = decide(
    base({
      setup: { direction: "down", horizon: "swing" },
      horizon: null,
      volumeRatio: 0.4,
      analogs: null,
      relStrength: -9.2,
    }),
  );
  assert.equal(falling.action, "SHORT");
  assert.match(falling.why[2], /9\.2 points behind its peers/);

  // Inside the band is still no evidence either way, and the band is the same one both halves
  // use -- a name cannot be too close to call against and far enough ahead to confirm.
  assert.equal(decide({ ...bare, relStrength: 7.4 }).confidence, "Low");
  assert.equal(decide({ ...bare, relStrength: null }).confidence, "Low");
});

test("the peer reading is what a currency pair has instead of volume", () => {
  // A pair publishes no volume at any venue, so `volumeConfirms` is null for all 27 of them
  // permanently, and `jobs/analogs.py` could match no past day without a volume ratio until it
  // learned to. The peer gap is the one leg of the four that is populated for every pair.
  const pair = {
    market: "FX" as const,
    setup: { direction: "flat", horizon: "swing", trend: "down" } as const,
    horizon: null,
    volumeRatio: null,
    analogs: null,
    target: null,
  };
  // Without it the direction still prints -- nothing is withheld any more -- but nothing
  // confirms it either, and both facts are recorded.
  const bare = decide(base({ ...pair, relStrength: 0 }));
  assert.equal(bare.action, "SHORT");
  assert.equal(bare.gate, "unconfirmed-short");
  assert.equal(bare.confidence, "Low");

  // With it the gate and the grade both move, which is the whole difference the leg makes.
  const confirmed = decide(base({ ...pair, relStrength: -4.5 }));
  assert.equal(confirmed.gate, "trend-short");
  assert.equal(confirmed.confidence, "Medium");
  assert.match(confirmed.why[0], /4\.5 points behind its peers carries it/);
});

test("the High bar stays at two things agreeing, not at half of what is available", () => {
  // A fourth leg must not re-grade the site by arithmetic. Two independent confirmations is
  // High because two is what "independently confirmed" means, and it meant that with three legs.
  const one = base({ horizon: null, volumeRatio: 0.4, analogs: null, relStrength: 9 });
  assert.equal(decide(one).confidence, "Medium");
  const two = { ...one, volumeRatio: 1.8 };
  assert.equal(decide(two).confidence, "High");
});

test("the peer band is read per market, because a point is not one thing", () => {
  // Rule 42's shape, caught in this constant. Measured 2026-10-09 as the median |relStrength|
  // per market: FX 1.13, PSX 3.53, US 3.71, crypto 5.56. One constant of 3 points therefore
  // passed 58% of US names and 7% of currency pairs -- simultaneously too loose to be evidence
  // and too strict to ever fire. The band is twice each market's own median.
  const lean = { horizon: null, volumeRatio: 0.4, analogs: null } as const;

  // 4 points: nothing for a US equity, a clear lead for a currency pair.
  assert.equal(decide(base({ ...lean, relStrength: 4 })).confidence, "Low");
  assert.equal(decide(base({ ...lean, market: "FX", relStrength: 4 })).confidence, "Medium");

  // 9 points: a clear lead for a US equity, and still nothing for a coin.
  assert.equal(decide(base({ ...lean, relStrength: 9 })).confidence, "Medium");
  assert.equal(decide(base({ ...lean, market: "Crypto", relStrength: 9 })).confidence, "Low");

  // Both halves move together. One measurement and one question, so the distance that confirms
  // is the distance that contradicts -- a name cannot be too close to call one way and clearly
  // placed the other.
  assert.deepEqual(decide(base({ market: "FX", relStrength: -4 })).notes.length, 1);
  assert.deepEqual(decide(base({ market: "Crypto", relStrength: -4 })).notes, []);
});

test("the peer cap takes one step and never two", () => {
  // A Low direction with the peers against it stays Low rather than falling off the scale, and a
  // Medium stays Medium. The cap is a qualification, not a second veto wearing a grade's clothes.
  const low = base({
    horizon: null,
    volumeRatio: 0.4,
    analogs: { count: 12, lowPct: -3, highPct: 6, medianPct: -1.1, positive: 4 },
  });
  assert.equal(decide(low).confidence, "Low");
  assert.equal(decide({ ...low, relStrength: -9 }).confidence, "Low");
});

// --- Gate 5's bypass, and gate 8 -------------------------------------------------------------
//
// The two places a stored `rewardRisk` is allowed to change the answer. Both are bypasses of a
// refusal and neither can produce a direction on its own, which is what these tests pin down.

test("every measured direction prints, and the grade carries how much backs it", () => {
  // The last gate to go. It asked for one of three stored figures to carry a direction whose own
  // conditions were incomplete -- volume, a peer gap, or a reward at ASYMMETRY_CLEARS. Measured
  // 2026-10-09: 176 of the 187 refused names had a direction, an entry and a stop, and were held
  // back only because none of the three was present.
  //
  // `confidence` already said that, with more resolution than a gate can: a gate is one bit and
  // the grade counts four independent confirmations. The gate was the same judgement made twice,
  // the second time by deletion.
  const bare = {
    setup: { direction: "flat", horizon: "swing", trend: "up" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
  };
  const d = decide(base(bare));
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "unconfirmed-long", "recorded apart so the outcome log can judge it");
  assert.equal(d.confidence, "Low", "nothing confirms it, and the grade is where that is said");
  assert.match(d.why[0], /none of its other conditions are present/);
  assert.ok(d.missing.length, "and every absent confirmation is still listed");

  // With a carrier it is the same action under a different gate and a better grade, so the two
  // can be told apart in `DecisionLog` without either being withheld.
  const carried = decide(base({ ...bare, volumeRatio: 2.4 }));
  assert.equal(carried.action, "LONG");
  assert.equal(carried.gate, "trend-long");
  assert.equal(carried.confidence, "Medium");
  assert.match(carried.why[0], /2\.4x its 20-session average carries it/);
});

test("a falling trend with nothing behind it is gated where shorts measured negative", () => {
  // The short gate. 171,010 shorts over eight years: pooled they lose, and split by market the
  // whole of the loss is the 105,705 US observations while crypto, PSX and FX are positive. A
  // US short with none of the four confirmations is a position whose own history argues against
  // it, so it is refused rather than printed and graded Low.
  const bare = {
    setup: { direction: "flat", horizon: "swing", trend: "down" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
  };
  const gated = decide(base({ ...bare, market: "US" }));
  assert.equal(gated.action, "WAIT");
  assert.equal(gated.gate, "short-unbacked");
  assert.match(gated.why[1], /measured -0\.11R per unit risked/);

  // The same row in a market where shorts measured positive prints, because there is nothing in
  // the history to hold it back.
  for (const market of ["Crypto", "PSX", "FX"] as const) {
    const through = decide(base({ ...bare, market }));
    assert.equal(through.action, "SHORT", market);
    assert.equal(through.gate, "unconfirmed-short", market);
  }
});

test("one confirmation is all the short gate asks for", () => {
  // It is a gate on *unbacked* shorts, not a ban on US shorts. A single confirmation satisfies
  // it, because the measurement is about shorts with nothing behind them.
  const bare = {
    market: "US" as const,
    setup: { direction: "flat", horizon: "swing", trend: "down" } as const,
    horizon: null,
    relStrength: 0,
    analogs: null,
    target: null,
  };
  assert.equal(decide(base({ ...bare, volumeRatio: 0.5 })).action, "WAIT");
  assert.equal(decide(base({ ...bare, volumeRatio: 2.4 })).action, "SHORT");
});

test("a late short is gated in every market, including the ones that measured positive", () => {
  // The second half of the gate, and it is independent of the first. Shorts entered after a
  // fall of more than 10% measured -0.10R where earlier ones measured +0.01R, over 59,187 and
  // 44,761 observations, so this one applies wherever the name is listed.
  const late = {
    market: "Crypto" as const,
    setup: { direction: "flat", horizon: "swing", trend: "down" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
  };
  assert.equal(decide(base({ ...late, r20: -4 })).action, "SHORT", "not late, prints");
  const gated = decide(base({ ...late, r20: -18 }));
  assert.equal(gated.action, "WAIT");
  assert.match(gated.why[1], /already fallen 18\.0%/);

  // Unmeasured is not late. A null r20 is a factor row the job has not reached, and treating it
  // as a large fall would gate on an absence.
  assert.equal(decide(base({ ...late, r20: null })).action, "SHORT");
});

test("longs are not gated, because longs measured positive everywhere", () => {
  // The asymmetry is in the data, not in the table's opinion of the two sides.
  const bare = {
    market: "US" as const,
    setup: { direction: "flat", horizon: "swing", trend: "up" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
    r20: -18,
  };
  assert.equal(decide(base(bare)).action, "LONG");
  assert.equal(decide(base(bare)).gate, "unconfirmed-long");
});

test("contradicting coverage no longer refuses a thin direction, it notes it", () => {
  // The last soft veto inside gate 7. It still withdraws the analog leg and still prints, which
  // is rule 44's substance; what it stopped doing is deleting the direction.
  const d = decide(
    base({
      setup: { direction: "flat", horizon: "swing", trend: "up" },
      horizon: null,
      volumeRatio: 2.4,
      news: { tone: "down", catalyst: true },
    }),
  );
  assert.equal(d.action, "LONG");
  assert.ok(
    d.notes.some((n) => /worded negatively/.test(n)),
    d.notes.join(" | "),
  );
});

test("a price between its averages still has a side, and the sentence says which reading it is", () => {
  // The largest block the table had nothing to say about: 123 refused names on 2026-10-09 whose
  // swing state was `none` — price between its own averages — of which 119 had the fast mean
  // measurably above or below the slow one. `trend` correctly says `mixed` there, because three
  // things do not agree; `bias` says which way the two that remain are pointing.
  const between = {
    setup: { direction: "unknown", horizon: "swing", trend: "mixed", bias: "up" } as const,
    horizon: null,
    volumeRatio: 2.4,
  };
  const d = decide(base(between));
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "trend-long");
  // It must not claim a trend. Three things agreeing and two things agreeing are different
  // findings, and promoting the weaker into the stronger one's word is the overclaim.
  assert.doesNotMatch(d.why[0], /The trend is/);
  assert.match(d.why[0], /Price is between its own averages, with the 20 day above the 50 day/);
  assert.match(d.why[0], /2\.4x its 20-session average carries it/);

  // Down is the mirror, and it was the commoner side: 64 of the 119 had the fast mean below.
  const falling = decide(
    base({ ...between, setup: { direction: "unknown", horizon: "swing", trend: "mixed", bias: "down" } }),
  );
  assert.equal(falling.action, "SHORT");
  assert.match(falling.why[0], /20 day below the 50 day/);
});

test("a bias is still named as a bias, whatever carries it", () => {
  // Three things agreeing and two things agreeing are different findings. The weaker one is
  // acted on now, and it still must not borrow the stronger one's word.
  const between = {
    setup: { direction: "unknown", horizon: "swing", trend: "mixed", bias: "up" } as const,
    horizon: null,
    target: null,
  };
  for (const over of [{ volumeRatio: 0.5, relStrength: 0 }, { volumeRatio: 2.4 }]) {
    const d = decide(base({ ...between, ...over }));
    assert.equal(d.action, "LONG");
    assert.doesNotMatch(d.why[0], /The trend is/);
    assert.match(d.why[0], /Price is between its own averages, with the 20 day above the 50 day/);
  }

  // A disagreeing longer view no longer refuses it either; it is a note and a lost grade.
  const opposed = decide(base({ ...between, volumeRatio: 2.4, horizon: { direction: "down" } }));
  assert.equal(opposed.action, "LONG");
  assert.ok(opposed.notes.some((n) => /longer view reads down/.test(n)), opposed.notes.join(" | "));
});

test("a trend beats a bias and the two never compete", () => {
  // `jobs/setup.py` writes `bias` only under a mixed trend, so a row carrying both a directional
  // trend and a bias cannot occur. If one ever did, the stronger reading wins and says so.
  const d = decide(
    base({
      setup: { direction: "flat", horizon: "swing", trend: "down", bias: "up" },
      horizon: null,
      volumeRatio: 2.4,
    }),
  );
  assert.equal(d.action, "SHORT");
  assert.match(d.why[0], /The trend is down/);
});

test("a mixed bias under a mixed trend carries nothing", () => {
  // Inside `BIAS_MIN_GAP` the two averages are not far enough apart to read, which `setup.py`
  // records as `mixed`. A measurement that came back without a side is still not a side.
  const d = decide(
    base({
      setup: { direction: "unknown", horizon: "swing", trend: "mixed", bias: "mixed" },
      horizon: null,
      volumeRatio: 5,
    }),
  );
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "incomplete");
});

test("a mixed trend with no bias recorded carries nothing, however loud the volume", () => {
  // `mixed` is a measurement that came back without a direction. With no `bias` beside it there
  // is nothing left to read, and promoting it would be the rule table inventing the direction
  // `setup.py` declined to state. This is a row written before `bias` existed, or one whose
  // averages fell inside the floor -- the test above covers the second explicitly.
  const d = decide(
    base({ setup: { direction: "flat", horizon: "swing", trend: "mixed" }, volumeRatio: 5 }),
  );
  assert.equal(d.action, "WAIT");
  assert.equal(d.gate, "incomplete");
});

// --- News against the pattern -----------------------------------------------------------------
//
// The confluence rule. An analog set answers "what followed past days that looked like this one",
// matched on price, volume and the five-day return -- and none of those past days had today's
// headline in them. So a set that agrees with the setup while the published coverage disagrees
// with the present is a sample missing the thing most likely to drive the next move.

test("a contradicting tone withdraws the history leg and says so", () => {
  // The base case confirms on two legs -- the agreeing horizon and volume -- plus history, and
  // grades High. With the coverage pointing the other way the history leg drops out.
  const clean = decide(base());
  assert.equal(clean.confidence, "High");
  assert.match(clean.why[2], /similar days going the same way/);

  const against = decide(base({ news: { tone: "down", catalyst: false } }));
  assert.equal(against.action, "LONG", "coverage qualifies a confirmed setup, it does not veto it");
  // The why line stops claiming history. Volume still confirms, so that is all it may say.
  assert.doesNotMatch(against.why[2], /similar days going the same way/);
  assert.match(against.why[2], /Confirmed by volume/);
  assert.ok(
    against.notes.some((n) => /worded negatively/.test(n)),
    against.notes.join(" | "),
  );
  // And the withdrawn set is named with its own counts rather than disappearing. This is the
  // branch `confirmLine` cannot reach: with volume confirming, its sentence is about volume.
  assert.ok(
    against.notes.some((n) => /8 of 12 similar past days went this way, and they are not counted/.test(n)),
    against.notes.join(" | "),
  );
});

test("with nothing else confirming, the why line itself carries the withdrawal", () => {
  // The other half of the pair above. Volume off, horizon absent: `confirmLine` has no parts to
  // print, so it must say why rather than falling into "neither volume nor similar days confirm
  // it" -- which would be true of the arithmetic and wrong about the file.
  const d = decide(
    base({ horizon: null, volumeRatio: 0.4, news: { tone: "down", catalyst: false } }),
  );
  assert.match(d.why[2], /lean this way, but the published coverage points the other way/);
});

test("a catalyst makes the contradiction a different sentence", () => {
  const spike = decide(base({ news: { tone: "down", catalyst: true } }));
  assert.ok(
    spike.notes.some((n) => /spike against its own baseline/.test(n)),
    spike.notes.join(" | "),
  );
  // A mood held over a month is not an event, and the two must not print the same line.
  const mood = decide(base({ news: { tone: "down", catalyst: false } }));
  assert.ok(mood.notes.every((n) => !/spike/.test(n)), mood.notes.join(" | "));
});

test("coverage can take a confirmation away and can never add one", () => {
  // Principle 5: current human attention is context, not proof. A word list with no bodies, no
  // negation and no sarcasm is good enough to withdraw a claim and not good enough to make one,
  // so an agreeing tone must leave every grade exactly where it was.
  for (const over of [{}, { volumeRatio: 0.4 }, { horizon: null }]) {
    const quiet = decide(base({ ...over, news: null }));
    const neutral = decide(base({ ...over, news: { tone: null, catalyst: true } }));
    const agreeing = decide(base({ ...over, news: { tone: "up", catalyst: true } }));
    assert.equal(neutral.confidence, quiet.confidence);
    assert.equal(agreeing.confidence, quiet.confidence);
    assert.deepEqual(agreeing.notes, quiet.notes);
  }
});

test("a neutral reading and no reading at all both change nothing", () => {
  // Rule 21 once more. "No HumanSignal row" and "read, and the window took no side" are two
  // values, and neither is "read, and it disagrees" -- only the third may act.
  const none = decide(base({ news: null }));
  const neutral = decide(base({ news: { tone: null, catalyst: false } }));
  assert.equal(none.confidence, "High");
  assert.equal(neutral.confidence, "High");
  assert.deepEqual(neutral.notes, []);
});

test("coverage withdraws the history leg on a thin direction too, and prints", () => {
  // Rule 44 made contradicting coverage a veto at this gate, on the argument that a thin case
  // pointing one way against published coverage pointing the other is the blind trap. The veto
  // is gone with every other veto; what remains is the substance of the rule -- the matched past
  // days stop counting, the grade falls, and the contradiction is printed.
  const carried = {
    setup: { direction: "flat", horizon: "swing", trend: "up" } as const,
    horizon: null,
    volumeRatio: 2.4,
  };
  const clean = decide(base(carried));
  const against = decide(base({ ...carried, news: { tone: "down", catalyst: true } }));

  assert.equal(against.action, "LONG");
  assert.ok(
    against.notes.some((n) => /spike against its own baseline/.test(n)),
    against.notes.join(" | "),
  );
  assert.ok(
    CONFIDENCE_ORDER[against.confidence] >= CONFIDENCE_ORDER[clean.confidence],
    "a withdrawn confirmation can only lower the grade, never raise it",
  );
});

test("a confirmed setup is not vetoed by coverage, only graded down", () => {
  // The asymmetry between gate 8 and gates 6/7, asserted as the pair it is. At gates 6 and 7
  // `jobs/setup.py` found and confirmed the conditions; a word list over headlines does not
  // overrule that.
  const d = decide(base({ news: { tone: "down", catalyst: true } }));
  assert.equal(d.action, "LONG");
  assert.equal(d.gate, "long");
  // The base case confirms on all three legs, so losing one leaves two and the grade is still
  // High. Withdrawing a leg is a deduction of one, not a collapse -- which is why the grade has
  // to be tested on a name that was resting on two.
  assert.equal(d.confidence, "High");

  // Resting on two legs -- volume and history, with no second timeframe. Withdrawing history
  // leaves one, which is the single step this rule is allowed to cost.
  const onTwo = base({ horizon: null });
  assert.equal(decide(onTwo).confidence, "High");
  assert.equal(decide({ ...onTwo, news: { tone: "down", catalyst: false } }).confidence, "Medium");

  // And on history alone it falls to Low, never past it: a withdrawn confirmation is not
  // evidence against, so there is no second deduction waiting underneath.
  const onOne = base({ horizon: null, volumeRatio: 0.4 });
  assert.equal(decide(onOne).confidence, "Medium");
  assert.equal(decide({ ...onOne, news: { tone: "down", catalyst: true } }).confidence, "Low");
});

// --- The plan ---------------------------------------------------------------------------------

test("a direction carries the levels and the measured history, and a WAIT carries none", () => {
  const d = decide(base());
  assert.equal(d.plan?.invalidation, 94);
  assert.deepEqual(d.plan?.entry, { low: 98, high: 102 });
  assert.deepEqual(d.plan?.target, { low: 108, high: 112, method: "structure" });
  assert.equal(d.plan?.rewardRisk, 1.5);
  // 8 of 12 matched days went this way. The share travels with its denominator, always.
  assert.deepEqual(d.plan?.baseRate, { share: 8 / 12, count: 12 });
  // 0.6667 * 1.5 - 0.3333, in units of the risk.
  assert.ok(Math.abs(d.plan!.expectancyR! - (8 / 12 * 1.5 - 4 / 12)) < 1e-9);

  assert.equal(decide(base({ invalidation: null })).plan, null);
});

test("expectancy needs both halves, and says nothing on one", () => {
  // No target: there is no reward to multiply the share by.
  assert.equal(decide(base({ target: null })).plan?.expectancyR, null);
  // A target whose reward the job could not compute is the same answer by a different route.
  const uncomputed = decide(
    base({ target: { method: "analog", low: 105, high: 109, rewardRisk: null } }),
  );
  assert.equal(uncomputed.plan?.expectancyR, null);
  assert.ok(
    uncomputed.missing.some((m) => /reward against risk was not computed/.test(m)),
    uncomputed.missing.join(" | "),
  );
  // Too few matched days: `jobs/analogs.py` will not grade a set under 8, so neither will this.
  const thin = decide(base({ analogs: { count: 5, lowPct: -2, highPct: 3, medianPct: 1, positive: 4 } }));
  assert.equal(thin.plan?.baseRate, null);
  assert.equal(thin.plan?.expectancyR, null);
});

test("the base rate counts the direction being taken, not the days that rose", () => {
  // 8 of 12 rose, so a SHORT's base rate is the other 4. Reading `positive` straight through
  // would have every short quote the long's frequency.
  const d = decide(
    base({ setup: { direction: "down", horizon: "swing" }, horizon: { direction: "down" } }),
  );
  assert.equal(d.action, "SHORT");
  assert.deepEqual(d.plan?.baseRate, { share: 4 / 12, count: 12 });
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

test("the confirm wording reads correctly alone, and reconcile still recognises it", () => {
  // Two faults in one line, both found on the live page rather than in review.
  //
  // `confirmLine` joins its parts after "Confirmed by ", so the analog clause has to be a phrase
  // that works on its own as well as after the volume one. It was "N of M similar days went the
  // same way", which printed as "Confirmed by 21 of 31 similar days went the same way." on every
  // name where volume did not also confirm -- most of them.
  //
  // And `lib/reconcile.ts` matches that exact wording to decide whether the analog set confirmed.
  // A regex in one file against a template literal in another is a coupling nothing enforces: it
  // fails open, so the reconcile line would simply stop explaining a grade it should explain, with
  // nothing failing. This test is that enforcement.
  const decision = readFileSync(new URL("../lib/decision.ts", import.meta.url), "utf8");
  const reconcile = readFileSync(new URL("../lib/reconcile.ts", import.meta.url), "utf8");

  const clause = decision.match(/\$\{moved\} of \$\{a\.count\} ([^`]+)`/);
  assert.ok(clause, "the analog confirm clause in confirmLine no longer matches; check both files");
  const phrase = clause[1].trim();
  assert.ok(
    /\bgoing\b/.test(phrase),
    `"Confirmed by 12 of 20 ${phrase}." has to read as English on its own`,
  );

  const pattern = reconcile.match(/const DAYS_CONFIRMED = \/([^/]+)\//);
  assert.ok(pattern, "DAYS_CONFIRMED is gone from reconcile.ts");
  assert.match(
    phrase,
    new RegExp(pattern[1]),
    "reconcile.ts no longer recognises the sentence decision.ts builds",
  );
});

test("the analog share agrees with the job that computes the same judgement", () => {
  // The cross-language pair this repository has listed as "a comment, not a constraint" for
  // several sessions, closed for the one that was actually disagreeing. `jobs/setup.py` has
  // required ANALOG_SHARE = 0.55 of the same measurement since it was written; `analogConfirms`
  // asked for `> 0.5`, so the page graded confidence on a looser rule than the job that decides
  // whether history supports a setup at all.
  //
  // Measured 2026-10-07 before the change: 13 of 44 directional non-Low names rested on a share
  // within five points of a coin flip, HMC at 377/748 = 50.4%, printed as "Confirmed by".
  const py = readFileSync(new URL("../jobs/setup.py", import.meta.url), "utf8");
  const m = py.match(/ANALOG_SHARE\s*=\s*([\d.]+)/);
  assert.ok(m, "ANALOG_SHARE is gone from jobs/setup.py");
  assert.equal(
    Number(m[1]),
    ANALOG_SHARE_CONFIRMS,
    "jobs/setup.py and lib/decision.ts disagree about when matched days count as agreement",
  );
});

test("a bare majority of matched days is not confirmation", () => {
  // The case the old rule admitted. 51% of 200 days with a positive median used to confirm.
  const bare = decide(
    base({ analogs: { count: 200, positive: 102, lowPct: -5, highPct: 5, medianPct: 0.4 } }),
  );
  // The analog clause is simply absent: the volume leg still confirms in this fixture, so the
  // test is that history is no longer counted among the confirmations, not that nothing is.
  assert.doesNotMatch(bare.why[2], /similar days going the same way/);
  assert.ok(bare.missing.some((m) => /similar past days/.test(m)), "the gap should be named");

  // And a real lean still does.
  const lean = decide(
    base({ analogs: { count: 200, positive: 120, lowPct: -5, highPct: 5, medianPct: 0.4 } }),
  );
  assert.match(lean.why[2], /similar days going the same way/);
});

// --- the fifth confirmation: an entry rule firing this session --------------------------------
//
// brain.md rule 54. Four candidate entry rules were measured against the moving-average stack on
// identical terms; three were earlier and slightly better and all three were far rarer, so the
// two that beat it are stored as a fifth confirmation rather than swapped in as the entry. What
// these tests guard is that it behaves like a confirmation and not like a shortcut: it lifts a
// grade exactly as far as any other single leg does, it is never reported as missing, and it is
// counted only when it points the way the decision is going.

test("an entry rule firing this way counts as a confirmation", () => {
  // One leg and nothing else, against the same row with no trigger on it. Medium against Low is
  // the whole claim: one confirmation, same as volume alone.
  const thin = {
    setup: { direction: "up", horizon: "swing" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
  };
  assert.equal(decide(base(thin)).confidence, "Low");
  const fired = decide(
    base({ ...thin, entryTrigger: { rule: "squeeze_break", direction: "up" } }),
  );
  assert.equal(fired.action, "LONG");
  assert.equal(fired.confidence, "Medium");
});

test("the High bar is still two independent things, not half of what is available", () => {
  // The fifth leg must not make High cheaper. A trigger plus volume is two, and a trigger alone
  // is one, exactly as it was when there were four legs and when there were three.
  const thin = {
    setup: { direction: "up", horizon: "swing" } as const,
    horizon: null,
    relStrength: 0,
    analogs: null,
    target: null,
    entryTrigger: { rule: "vol_flip", direction: "up" } as const,
  };
  assert.equal(decide(base({ ...thin, volumeRatio: 0.5 })).confidence, "Medium");
  assert.equal(decide(base({ ...thin, volumeRatio: 2.4 })).confidence, "High");
});

test("a trigger pointing the other way confirms nothing", () => {
  // The direction is stored beside the rule precisely so this cannot happen: a squeeze that
  // broke downwards is not evidence for a long, and counting the rule without its direction
  // would make every fired trigger confirm whichever way the card happened to be printing.
  const thin = {
    setup: { direction: "up", horizon: "swing" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
  };
  const against = decide(
    base({ ...thin, entryTrigger: { rule: "squeeze_break", direction: "down" } }),
  );
  assert.equal(against.confidence, "Low");
  assert.doesNotMatch(against.why[2], /quietest stretch/);
});

test("the card says which rule caught it, in words", () => {
  const d = decide(base({ entryTrigger: { rule: "squeeze_break", direction: "up" } }));
  assert.match(d.why[2], /a break out of its quietest stretch in six months this session/);
  const flip = decide(base({ entryTrigger: { rule: "vol_flip", direction: "up" } }));
  assert.match(flip.why[2], /five-session momentum turning on heavy volume this session/);
});

test("a rule the table has not been taught prints its own name rather than vanishing", () => {
  // Same contract lib/target.ts gives an unknown method. A sixth rule from the next research
  // sweep reaches a reader as its own name, which is ugly and honest, instead of silently
  // confirming a direction with no sentence to show for it.
  const d = decide(base({ entryTrigger: { rule: "gap_fill", direction: "up" } }));
  assert.match(d.why[2], /gap_fill this session/);
});

test("a silent entry rule is never reported as missing evidence", () => {
  // The distinction the whole `missing` list exists for. No published volume is a measurement
  // nobody could take and a reader is owed it. No trigger is a rule that did not fire, which is
  // the state of nineteen sessions in twenty and is not news -- printing it would bury the two
  // absences that matter under one that never means anything.
  const d = decide(
    base({ volumeRatio: null, analogs: null, target: null, entryTrigger: null }),
  );
  assert.ok(d.missing.some((m) => /No volume published/.test(m)));
  assert.ok(!d.missing.some((m) => /trigger|squeeze|momentum/i.test(m)));
});

test("a trigger backs a short the gate would otherwise refuse", () => {
  // The gate asks for one of the five, not one of the four. A US short with nothing behind it is
  // refused; the same row with a squeeze that broke downwards this session has one independent
  // thing behind it and prints, graded Medium on that one leg.
  const bare = {
    market: "US" as const,
    setup: { direction: "flat", horizon: "swing", trend: "down" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
  };
  assert.equal(decide(base(bare)).gate, "short-unbacked");
  const backed = decide(
    base({ ...bare, entryTrigger: { rule: "squeeze_break", direction: "down" } }),
  );
  assert.equal(backed.action, "SHORT");
  assert.equal(backed.confidence, "Medium");

  // And a trigger pointing the wrong way does not back it, which is the same rule as everywhere
  // else and matters most here: this is the one gate that refuses rather than downgrades.
  assert.equal(
    decide(base({ ...bare, entryTrigger: { rule: "squeeze_break", direction: "up" } })).gate,
    "short-unbacked",
  );
});

test("a late short is still gated, and a trigger is what releases it", () => {
  // The second half of the short gate is independent of the market, so a crypto name already
  // down 18% needs a confirmation like any other. The trigger is one.
  const late = {
    market: "Crypto" as const,
    setup: { direction: "flat", horizon: "swing", trend: "down" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
    r20: -18,
  };
  assert.equal(decide(base(late)).gate, "short-unbacked");
  assert.equal(
    decide(base({ ...late, entryTrigger: { rule: "vol_flip", direction: "down" } })).action,
    "SHORT",
  );
});

test("a withheld trend caught at the start is logged under its own gate and named first", () => {
  // Gate 8 prints either way; what the carrier decides is which gate name reaches DecisionLog,
  // and that is the point -- a withheld trend whose compression broke this session is a
  // different row from one carried by nothing, and only the gate name can say so.
  const withheld = {
    setup: { direction: "flat", horizon: "swing", trend: "up" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
  };
  assert.equal(decide(base(withheld)).gate, "unconfirmed-long");
  const caught = decide(
    base({ ...withheld, entryTrigger: { rule: "squeeze_break", direction: "up" } }),
  );
  assert.equal(caught.gate, "trend-long");
  // Named ahead of volume in the carrying sentence, because it is the rarer and more specific
  // fact: 1.3x volume is true of hundreds of sessions a day and this is true of about one in
  // twenty.
  const both = decide(
    base({
      ...withheld,
      volumeRatio: 2.4,
      entryTrigger: { rule: "squeeze_break", direction: "up" },
    }),
  );
  assert.match(both.why[0], /quietest stretch in six months carries it/);
});

test("the trigger clause sits last in the confirmation sentence", () => {
  // Every other clause describes a standing state; this one describes this session. Reading it
  // after the others is what makes the sentence say "all of that was true, and then this
  // happened" rather than burying the event among the conditions.
  const d = decide(
    base({
      volumeRatio: 2.4,
      relStrength: 9,
      entryTrigger: { rule: "vol_flip", direction: "up" },
    }),
  );
  const vol = d.why[2].indexOf("volume 2.4x");
  const trig = d.why[2].indexOf("five-session momentum");
  assert.ok(vol >= 0 && trig > vol, d.why[2]);
});

// --- plan validity: a stop that price has already moved through ---------------------------------
//
// Measured 2026-10-10: 189 of 404 live directional decisions, 47%, carried a stop on the wrong side
// of the close. `jobs/setup.py` anchors the entry at the 20-session window extreme and measures the
// stop from *that*, so a name in a pullback has a stop that price is already past. A stop is the
// level at which the reason for the trade stops being true, so a crossed one is a finished plan.

test("a long whose stop is at or above the close is refused, not graded", () => {
  const crossed = decide(base({ lastClose: 100, invalidation: 104 }));
  assert.equal(crossed.action, "WAIT");
  assert.equal(crossed.gate, "stop-crossed");
  assert.equal(crossed.basis, "evidence");
  assert.match(crossed.why[1], /stop is 104\.00 and it last closed at 100\.00/);
  assert.equal(crossed.plan, null);

  // Exactly at the close is crossed too: a stop with no distance to be wrong across has no
  // reward-to-risk to speak of, and "a close below it" is already true of a close that equals it.
  assert.equal(decide(base({ lastClose: 100, invalidation: 100 })).gate, "stop-crossed");
  // And one tick the right side of it is a plan.
  assert.equal(decide(base({ lastClose: 100, invalidation: 99.99 })).action, "LONG");
});

test("a short whose stop is at or below the close is refused, mirrored", () => {
  const down = { setup: { direction: "down", horizon: "swing" } as const, horizon: { direction: "down" } as const };
  const crossed = decide(base({ ...down, lastClose: 100, invalidation: 96 }));
  assert.equal(crossed.action, "WAIT");
  assert.equal(crossed.gate, "stop-crossed");
  assert.match(crossed.why[1], /already above the level a short needed to stay under/);
  assert.equal(decide(base({ ...down, lastClose: 100, invalidation: 100 })).gate, "stop-crossed");
  assert.equal(decide(base({ ...down, lastClose: 100, invalidation: 100.01 })).action, "SHORT");
});

test("the stop check runs before the short gate and before any confirmation counts", () => {
  // A US short with nothing behind it would be `short-unbacked`; with a crossed stop it is
  // `stop-crossed`, because the plan is finished whatever the history says. And a name with every
  // confirmation present is refused all the same: confirmation grades a live plan, it does not
  // revive a dead one.
  const bare = {
    market: "US" as const,
    setup: { direction: "flat", horizon: "swing", trend: "down" } as const,
    horizon: null,
    volumeRatio: 0.5,
    relStrength: 0,
    analogs: null,
    target: null,
    lastClose: 100,
    invalidation: 96,
  };
  assert.equal(decide(base(bare)).gate, "stop-crossed");
  assert.equal(
    decide(base({ ...bare, volumeRatio: 3, relStrength: -12, entryTrigger: { rule: "vol_flip", direction: "down" } })).gate,
    "stop-crossed",
  );
});

test("it covers all three ways a direction can be reached", () => {
  // The direction builder is shared by a stated state, a withheld trend and a bias, and the check
  // lives in the builder so none of them can print a crossed plan.
  const stated = decide(base({ lastClose: 100, invalidation: 104 }));
  const withheld = decide(
    base({ setup: { direction: "flat", horizon: "swing", trend: "up" }, lastClose: 100, invalidation: 104 }),
  );
  const bias = decide(
    base({
      setup: { direction: "unknown", horizon: "swing", trend: "mixed", bias: "up" },
      lastClose: 100,
      invalidation: 104,
    }),
  );
  for (const d of [stated, withheld, bias]) assert.equal(d.gate, "stop-crossed");
});

test("a missing or unreadable stop is not this gate's business", () => {
  // Gate 4 refuses a missing stop and gate 1 a missing close; this gate must not invent a second
  // reason for them, and a non-finite figure is unmeasured rather than crossed.
  assert.equal(decide(base({ invalidation: null })).gate, "no-invalidation");
  assert.notEqual(decide(base({ invalidation: Number.NaN })).gate, "stop-crossed");
  assert.notEqual(decide(base({ lastClose: Number.POSITIVE_INFINITY })).gate, "stop-crossed");
});


// --- what the learning loop reads: which legs backed a call, and which side a refusal refused ---

test("the legs are named in a fixed order, as identifiers a log can keep", () => {
  assert.deepEqual([...LEGS], ["timeframe", "volume", "history", "peers", "trigger"]);
  // Everything confirming at once: the full list, in `LEGS` order whatever order they were found in.
  const all = base({
    volumeRatio: 2.4,
    relStrength: 12,
    entryTrigger: { rule: "vol_flip", direction: "up" },
  });
  assert.deepEqual(confirmingLegs(all, "up"), ["timeframe", "volume", "history", "peers", "trigger"]);
});

test("a direction nothing backs has an empty list, which is a finding and not an absence", () => {
  const bare = base({ ...{ horizon: null, volumeRatio: 0.5, relStrength: 0, analogs: null, target: null } });
  assert.deepEqual(confirmingLegs(bare, "up"), []);
});

test("the legs name the side being asked about and no other", () => {
  const input = base({ entryTrigger: { rule: "squeeze_break", direction: "down" }, relStrength: -12 });
  assert.ok(confirmingLegs(input, "down").includes("trigger"));
  assert.ok(confirmingLegs(input, "down").includes("peers"));
  assert.ok(!confirmingLegs(input, "up").includes("trigger"));
  assert.ok(!confirmingLegs(input, "up").includes("peers"));
});

test("the list and the grade are one computation, so they cannot disagree", () => {
  // The grade is High at two legs, Medium at one, Low at none. Swept across the legs one at a time
  // and in pairs, so a refactor that let the list and the count drift apart fails here.
  const thin = { horizon: null, volumeRatio: 0.5, relStrength: 0, analogs: null, target: null } as const;
  const one: Partial<DecisionInput>[] = [
    { volumeRatio: 2.4 },
    { relStrength: 12 },
    { entryTrigger: { rule: "vol_flip", direction: "up" } },
  ];
  for (const over of one) {
    const input = base({ ...thin, ...over });
    assert.equal(confirmingLegs(input, "up").length, 1);
    assert.equal(decide(input).confidence, "Medium");
  }
  const two = base({ ...thin, volumeRatio: 2.4, relStrength: 12 });
  assert.equal(confirmingLegs(two, "up").length, 2);
  assert.equal(decide(two).confidence, "High");
});

test("a refusal carries the side it refused, and a direction or a plain WAIT carries none", () => {
  const crossed = decide(base({ lastClose: 100, invalidation: 104 }));
  assert.equal(crossed.gate, "stop-crossed");
  assert.equal(crossed.intent, "up");

  const unbacked = decide(
    base({
      market: "US",
      setup: { direction: "flat", horizon: "swing", trend: "down" },
      horizon: null,
      volumeRatio: 0.5,
      relStrength: 0,
      analogs: null,
      target: null,
    }),
  );
  assert.equal(unbacked.gate, "short-unbacked");
  assert.equal(unbacked.intent, "down");

  assert.equal(decide(base()).intent, null, "a printed direction names its side by its action");
  assert.equal(decide(base({ asOf: null })).intent, null, "a data fault refuses no particular side");
});

// --- the macro veto: a stored refusal that can only ever remove a verdict ----------------------
//
// `lib/macroGate.ts` asks a model; this table only reads what was stored. The properties that
// matter are asymmetric: a veto may turn a LONG or SHORT into a WAIT and may do nothing else --
// not raise a grade, not touch a level, not rescue a name that was already refused.

const VETO = { reason: "macro-warning", asOf: "2026-10-03" } as const;

test("a fresh macro veto turns a LONG into a refusal that records the side it refused", () => {
  const alone = decide(base());
  assert.equal(alone.action, "LONG");
  const vetoed = decide(base({ macroVeto: VETO }));
  assert.equal(vetoed.action, "WAIT");
  assert.equal(vetoed.gate, "macro-veto");
  assert.equal(vetoed.basis, "evidence");
  assert.equal(vetoed.intent, "up");
  assert.equal(vetoed.plan, null);
  assert.match(vetoed.why[0], /trend reads up/);
});

test("a fresh macro veto turns a SHORT into a refusal, mirrored", () => {
  const down = { setup: { direction: "down", horizon: "swing" } as const, horizon: { direction: "down" } as const };
  const vetoed = decide(base({ ...down, macroVeto: { reason: "sentiment-conflict", asOf: "2026-10-03" } }));
  assert.equal(vetoed.action, "WAIT");
  assert.equal(vetoed.gate, "macro-veto");
  assert.equal(vetoed.intent, "down");
});

test("a veto counts for today and yesterday and for no longer, and never from the future", () => {
  const at = (asOf: string) => decide(base({ macroVeto: { reason: "macro-warning", asOf } })).gate;
  assert.equal(at("2026-10-03"), "macro-veto");
  assert.equal(at("2026-10-02"), "macro-veto");
  assert.equal(at("2026-10-01"), "long");
  assert.equal(at("2026-09-01"), "long");
  assert.equal(at("2026-10-04"), "long");
  assert.equal(at("not-a-date"), "long");
});

test("a macro veto never changes anything it does not refuse", () => {
  // No veto, null, and an expired one all decide exactly as the rule table alone does.
  const alone = decide(base());
  assert.deepEqual(decide(base({ macroVeto: null })), alone);
  assert.deepEqual(decide(base({ macroVeto: { reason: "macro-warning", asOf: "2026-09-01" } })), alone);
  // A name already refused for another reason keeps that reason: the veto is not a second opinion.
  const stale = base({ asOf: "2026-09-01" });
  assert.deepEqual(decide({ ...stale, macroVeto: VETO }), decide(stale));
  // And a plan that is already finished is reported as finished, not as vetoed.
  const crossed = base({ lastClose: 100, invalidation: 104 });
  assert.equal(decide({ ...crossed, macroVeto: VETO }).gate, "stop-crossed");
});

test("the veto is deterministic and prints only fixed words, never the model's text", () => {
  const input = base({ macroVeto: VETO });
  assert.deepEqual(decide(input), decide(input));
  const printed = JSON.stringify(decide(input));
  assert.match(printed, /an extreme market-wide shock/);
  const conflict = JSON.stringify(decide(base({ macroVeto: { reason: "sentiment-conflict", asOf: "2026-10-03" } })));
  assert.match(conflict, /directly contradict that direction/);
});

test("an unrecognised veto reason is no veto at all, and the freshness window matches the gate's", async () => {
  const odd = decide(base({ macroVeto: { reason: "vibes" as never, asOf: "2026-10-03" } }));
  assert.equal(odd.gate, "long");
  const mod = await import("../lib/macroGate.ts");
  const src = (await import("node:fs")).readFileSync(new URL("../lib/decision.ts", import.meta.url), "utf8");
  assert.match(src, new RegExp(`const MACRO_VETO_FRESH_DAYS = ${mod.MACRO_VETO_FRESH_DAYS};`));
});

// --- patient flips: a reversal against a recent call must be confirmed -------------------------
//
// A direction can flip on the trend alone and print at Low confidence with nothing confirming it;
// that is the case most exposed to flipping straight back. Inside a week of the opposite call, the
// flip waits for one independent confirmation. A refusal only: it never creates a call.

const BARE = { volumeRatio: 0.4, relStrength: null, analogs: null, horizon: null, entryTrigger: null } as const;
const SHORT_YESTERDAY = { direction: "down", asOf: "2026-10-02" } as const;

test("an unconfirmed flip against yesterday's call waits, and records the side it would have taken", () => {
  const alone = decide(base(BARE));
  assert.equal(alone.action, "LONG", `fixture should be a bare LONG, got ${alone.gate}`);
  assert.equal(alone.legs.length, 0);
  const held = decide(base({ ...BARE, priorDirection: SHORT_YESTERDAY }));
  assert.equal(held.action, "WAIT");
  assert.equal(held.gate, "reversal-unconfirmed");
  assert.equal(held.basis, "evidence");
  assert.equal(held.intent, "up");
  assert.match(held.why[0], /against the SHORT call of 2026-10-02/);
});

test("a confirmed flip goes through at once, which is the reversal worth taking", () => {
  const confirmed = decide(base({ priorDirection: SHORT_YESTERDAY }));
  assert.equal(confirmed.action, "LONG");
  assert.ok(confirmed.legs.length > 0);
});

test("the buffer is a week, never today's own call, and never a call in the same direction", () => {
  const at = (asOf: string, direction: "up" | "down" = "down") =>
    decide(base({ ...BARE, priorDirection: { direction, asOf } })).gate;
  assert.equal(at("2026-09-26"), "reversal-unconfirmed"); // 7 days
  assert.notEqual(at("2026-09-25"), "reversal-unconfirmed"); // 8 days: aged out
  assert.notEqual(at("2026-10-03"), "reversal-unconfirmed"); // today is not "before today"
  assert.notEqual(at("2026-10-02", "up"), "reversal-unconfirmed"); // same side, not a flip
  assert.notEqual(at("not-a-day"), "reversal-unconfirmed");
});

test("a crossed stop or a macro veto is still reported first, and the rule never creates a call", () => {
  assert.equal(
    decide(base({ ...BARE, priorDirection: SHORT_YESTERDAY, lastClose: 100, invalidation: 104 })).gate,
    "stop-crossed",
  );
  assert.equal(
    decide(base({ ...BARE, priorDirection: SHORT_YESTERDAY, macroVeto: { reason: "macro-warning", asOf: "2026-10-03" } })).gate,
    "macro-veto",
  );
  // A WAIT stays a WAIT whatever came before.
  const stale = base({ asOf: "2026-09-01", priorDirection: SHORT_YESTERDAY });
  assert.equal(decide(stale).action, "WAIT");
  assert.notEqual(decide(stale).gate, "reversal-unconfirmed");
});
