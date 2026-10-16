// The evidence families, their votes, and the arithmetic that turns them into a verdict.
//
// `BRAIN-SPEC-V1.md` §8 names the tiers this covers: T1 (each family's score and eligibility against
// synthetic vectors) and the frozen invariants T-I1, T-I2, T-I3, T-I12 and T-I13. The four
// consistency checks at the end are `BRAIN-LOGIC-CLOSURE-2026-10-16.md` §B5's own worked examples,
// reproduced here so the implementation is held to the arithmetic that was approved rather than to
// the arithmetic I happened to write.
//
// Every test states whether it expects a direction or a legitimate WAIT, because §8 requires that a
// suite cannot hide a defect behind a WAIT.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  FAMILIES,
  FAMILY_NAME,
  LOGIC_VERSION,
  MIN_FAMILIES,
  MIN_NET,
  PEERS_MIN,
  TAU,
  aggregate,
  readFamilies,
  type FamilyInput,
} from "../lib/families.ts";
import { ANALOGS_CONFIRM_MIN, ANALOG_SHARE_CONFIRMS, VOLUME_CONFIRMS_AT } from "../lib/decision.ts";

/// A row with every family unreadable. Each test turns on only what it is about, so no test can
/// pass because of a field it never mentioned.
function blank(over: Partial<FamilyInput> = {}): FamilyInput {
  return {
    market: "US",
    r20: null, sma20: null, sma50: null,
    volumeRatio: null, r1: null,
    atr14: null, atrTrailingMedian: null, rangePct: null, drawdownPct: null,
    relStrength: null, peers: 0, analogs: null,
    ...over,
  };
}

function reading(i: FamilyInput, id: string) {
  const r = readFamilies(i).find((x) => x.id === id);
  assert.ok(r, `no reading for ${id}`);
  return r;
}

// --- T1: each family's score and eligibility -----------------------------------------------------

test("E1 trend: the return and the averages are one fact and vote once", () => {
  assert.equal(reading(blank({ r20: 6.2, sma20: 11, sma50: 10 }), "E1").vote, 1);
  assert.equal(reading(blank({ r20: -6.2, sma20: 9, sma50: 10 }), "E1").vote, -1);
  // Disagreeing halves average to zero, which is eligible-and-even, not unreadable.
  const split = reading(blank({ r20: 6.2, sma20: 9, sma50: 10 }), "E1");
  assert.equal(split.score, 0);
  assert.equal(split.vote, 0);
  assert.equal(split.eligible, true);
  // Half the fact is still a readable fact, and (a+b)/2 = 0.5 is exactly the deadband.
  const half = reading(blank({ r20: 6.2 }), "E1");
  assert.equal(half.score, 0.5);
  assert.equal(half.vote, 1, "a score exactly at tau must vote");
});

test("E1 trend: nothing to read at all is ineligible, not flat", () => {
  const r = reading(blank(), "E1");
  assert.equal(r.eligible, false);
  assert.equal(r.vote, 0);
  assert.match(r.ineligibleBecause ?? "", /no 20-session return/);
});

test("E2 participation: volume confirms the move it accompanied, above the threshold only", () => {
  assert.equal(reading(blank({ volumeRatio: 1.4, r1: 0.9 }), "E2").vote, 1);
  assert.equal(reading(blank({ volumeRatio: 1.4, r1: -0.9 }), "E2").vote, -1);
  // Below the threshold it is eligible and says nothing -- an evidence fact, not a file fact.
  const quiet = reading(blank({ volumeRatio: VOLUME_CONFIRMS_AT - 0.01, r1: 0.9 }), "E2");
  assert.equal(quiet.eligible, true);
  assert.equal(quiet.vote, 0);
});

test("E2 participation: FX publishes no volume, so the family is ineligible and never zero", () => {
  // T-I1. A zero here would read as "volume was flat", which nobody measured.
  const r = reading(blank({ market: "FX", volumeRatio: null, r1: 1.1 }), "E2");
  assert.equal(r.eligible, false);
  assert.equal(r.vote, 0);
  assert.match(r.ineligibleBecause ?? "", /no volume published/);
});

test("E3 volatility: stress votes against, and the constructive arm is reachable", () => {
  assert.equal(reading(blank({ drawdownPct: -17 }), "E3").vote, -1);
  // The volatility stress clause, when a baseline exists.
  assert.equal(reading(blank({ drawdownPct: -2, atr14: 3, atrTrailingMedian: 2 }), "E3").vote, -1);
  // §3.3 writes the constructive arm as the *lower* half of `rangePct`, which cannot co-occur with a
  // drawdown above -5 because `rangePct` is a position in the trailing range and not a width. As
  // written it fired 0 times in 21,753 rows while the stress arm fired 8,734, leaving E3 able only
  // to vote against. Corrected to the column's documented unit; see `e3` in lib/families.ts.
  assert.equal(reading(blank({ drawdownPct: -3, rangePct: 80 }), "E3").vote, 1);
  assert.equal(reading(blank({ drawdownPct: -3, rangePct: 20 }), "E3").vote, 0);
  // Stress still wins over constructive when both could read, so a 20% drawdown near its own high
  // is not called constructive.
  assert.equal(reading(blank({ drawdownPct: -17, rangePct: 80 }), "E3").vote, -1);
});

test("E3 volatility: the constructive arm must be reachable at all, which is what it was not", () => {
  // A rule arm that cannot fire is not a conservative threshold, it is a broken rule: it turns the
  // family into a one-sided one and biases every NET it contributes to. Held as its own test because
  // the defect was invisible in the unit tests that asserted only the literal specification.
  const constructive = reading(blank({ drawdownPct: -1, rangePct: 99 }), "E3");
  assert.equal(constructive.vote, 1);
  const stressed = reading(blank({ drawdownPct: -40, rangePct: 1 }), "E3");
  assert.equal(stressed.vote, -1);
});

test("E3 volatility: an unstored volatility baseline is unmeasured, never 'not stressed'", () => {
  // T-I1 again, in the shape that is easiest to get wrong: `atr14` is present, its trailing median
  // is not, and the stress clause must simply not fire rather than resolve to false.
  const r = reading(blank({ atr14: 9, atrTrailingMedian: null, drawdownPct: -2, rangePct: 20 }), "E3");
  assert.equal(r.vote, 0);
  assert.match(r.detail, /volatility baseline not stored/);
});

test("E4 cross-sectional: too few peers is ineligible, and the gap must clear its market's band", () => {
  assert.equal(reading(blank({ relStrength: 9, peers: PEERS_MIN - 1 }), "E4").eligible, false);
  assert.equal(reading(blank({ relStrength: 9, peers: 11 }), "E4").vote, 1);
  assert.equal(reading(blank({ relStrength: -9, peers: 11 }), "E4").vote, -1);
  // Inside the band: measured, and not a finding.
  assert.equal(reading(blank({ relStrength: 1, peers: 11 }), "E4").vote, 0);
  // The band is per market, so the same gap can clear in FX and not in US.
  assert.equal(reading(blank({ market: "FX", relStrength: 3, peers: 11 }), "E4").vote, 1);
  assert.equal(reading(blank({ market: "US", relStrength: 3, peers: 11 }), "E4").vote, 0);
});

test("E5 history: the floor is the stored one, and a near coin flip is not agreement", () => {
  assert.equal(reading(blank({ analogs: { count: ANALOGS_CONFIRM_MIN - 1, positive: 7 } }), "E5").eligible, false);
  assert.equal(reading(blank({ analogs: { count: 100, positive: 61 } }), "E5").vote, 1);
  assert.equal(reading(blank({ analogs: { count: 100, positive: 39 } }), "E5").vote, -1);
  // 377 of 748 -- the measured case the 0.55 floor exists for. A bare majority is the absence of a
  // finding, not a confirmation.
  const coinflip = reading(blank({ analogs: { count: 748, positive: 377 } }), "E5");
  assert.equal(coinflip.eligible, true);
  assert.equal(coinflip.vote, 0);
  assert.ok(ANALOG_SHARE_CONFIRMS >= 0.55);
});

// --- the frozen invariants -----------------------------------------------------------------------

test("T-I2: a file WAIT stays distinct from an evidence WAIT", () => {
  // Two families agreeing, three required: unreadable file.
  const thinFile = aggregate(readFamilies(blank({ r20: 6, sma20: 11, sma50: 10, drawdownPct: -3, rangePct: 80 })));
  assert.equal(thinFile.action, "WAIT");
  assert.equal(thinFile.basis, "file");
  assert.equal(thinFile.gate, "file");

  // Three families readable and the evidence does not add up: readable file, thin evidence.
  const thinEvidence = aggregate(readFamilies(blank({
    r20: 6, sma20: 11, sma50: 10,           // E1 +1
    volumeRatio: 1.4, r1: -0.9,             // E2 -1
    drawdownPct: -2, rangePct: 20,          // E3  0, eligible
  })));
  assert.equal(thinEvidence.action, "WAIT");
  assert.equal(thinEvidence.basis, "evidence");
  assert.equal(thinEvidence.gate, "thin-evidence");
});

test("T-I3: macro and news are not in the voting set at all, so news alone cannot set a direction", () => {
  // Structural, not procedural: there is no family for them to vote through, which is why no
  // event-id matching is needed to stop one announcement becoming two confirmations.
  assert.deepEqual(FAMILIES, ["E1", "E2", "E3", "E4", "E5"]);
  const src = readFileSync(new URL("../lib/families.ts", import.meta.url), "utf8");
  const code = src.split("\n").filter((l) => !/^\s*(\/\/|\/\/\/|\*)/.test(l)).join("\n");
  for (const f of ["macroVeto", "newsCount", "newsCoverage", "tone", "catalyst"]) {
    assert.ok(!code.includes(f), `a family rule reads ${f}`);
  }
});

test("T-I12: unknown or conflicting is never forced into a direction", () => {
  // Everything unreadable.
  const nothing = aggregate(readFamilies(blank()));
  assert.equal(nothing.action, "WAIT");
  assert.equal(nothing.basis, "file");
  assert.equal(nothing.net, 0);

  // Perfectly conflicting, and readable: still no direction.
  const conflict = aggregate(readFamilies(blank({
    r20: 6, sma20: 11, sma50: 10,                      // E1 +1
    volumeRatio: 1.4, r1: -0.9,                        // E2 -1
    relStrength: 9, peers: 11,                         // E4 +1
    analogs: { count: 100, positive: 39 },             // E5 -1
    drawdownPct: -2, rangePct: 20,                     // E3  0
  })));
  assert.equal(conflict.net, 0);
  assert.equal(conflict.action, "WAIT");
  assert.equal(conflict.basis, "evidence");
  assert.equal(conflict.dissent, 2);
});

test("T-I13: an ineligible family subtracts nothing -- a veto never creates or reverses a direction", () => {
  const base = blank({
    r20: 6, sma20: 11, sma50: 10,            // E1 +1
    volumeRatio: 1.4, r1: 0.9,               // E2 +1
    relStrength: 9, peers: 11,               // E4 +1
    drawdownPct: -2, rangePct: 20,           // E3  0
  });
  const clean = aggregate(readFamilies(base));
  assert.equal(clean.action, "LONG");
  assert.equal(clean.net, 3);

  // A stage-0 integrity finding on the volume family withholds it. `NET` falls to +2 -- it does not
  // become -1, and the direction does not flip.
  const vetoed = aggregate(readFamilies({ ...base, integrityVeto: { E2: "bad bar" } }));
  assert.equal(vetoed.net, 2);
  assert.equal(vetoed.action, "LONG");
  assert.ok(vetoed.ineligible.includes(FAMILY_NAME.E2));
  assert.ok(!vetoed.opposing.includes(FAMILY_NAME.E2), "a withheld family was counted against the direction");
});

test("the thresholds are the frozen ones and the logic is versioned", () => {
  // D2: fixed initial values, not tuned against a result. A change needs a specification amendment,
  // and this test is where that shows up as a deliberate edit.
  assert.equal(MIN_FAMILIES, 3);
  assert.equal(MIN_NET, 2);
  assert.equal(TAU, 0.5);
  assert.match(LOGIC_VERSION, /^families-v/);
});

// --- §B5 consistency checks, votes in E1..E5 order ------------------------------------------------

test("B5: clean agreement -- +1,+1,+1,INELIG,INELIG is LONG / High", () => {
  const a = aggregate(readFamilies(blank({
    r20: 6.2, sma20: 11, sma50: 10,          // E1 +1
    volumeRatio: 1.4, r1: 0.9,               // E2 +1
    drawdownPct: -3, rangePct: 80,           // E3 +1
    peers: 0,                                 // E4 ineligible
    analogs: null,                            // E5 ineligible
  })));
  assert.equal(a.eligible, 3);
  assert.equal(a.net, 3);
  assert.equal(a.supporting.length, 3);
  assert.equal(a.opposing.length, 0);
  assert.equal(a.action, "LONG");
  assert.equal(a.confidence, "High");
  assert.deepEqual(a.supporting, ["trend", "volume", "volatility"]);
});

test("B5: strong majority with one objection -- +1,+1,+1,-1,+1 is LONG, capped to Medium", () => {
  const a = aggregate(readFamilies(blank({
    r20: 6.2, sma20: 11, sma50: 10,          // E1 +1
    volumeRatio: 1.4, r1: 0.9,               // E2 +1
    drawdownPct: -3, rangePct: 80,           // E3 +1
    relStrength: -9, peers: 11,              // E4 -1
    analogs: { count: 100, positive: 61 },   // E5 +1
  })));
  assert.equal(a.eligible, 5);
  assert.equal(a.net, 3);
  assert.equal(a.supporting.length, 4);
  assert.deepEqual(a.opposing, ["peers"]);
  assert.equal(a.action, "LONG");
  assert.equal(a.confidence, "Medium", "the published opposition cap did not apply");
});

test("B5: low information -- gate 1 fails first, and NET would have cleared MIN_NET", () => {
  // An FX pair: no volume, no peers, five matched days. Only E1 and E3 are readable, both +1.
  const i = blank({
    market: "FX",
    r20: 6.2, sma20: 11, sma50: 10,          // E1 +1
    volumeRatio: null,                        // E2 ineligible
    drawdownPct: -3, rangePct: 80,           // E3 +1
    peers: 0,                                 // E4 ineligible
    analogs: { count: 5, positive: 4 },      // E5 ineligible
  });
  const a = aggregate(readFamilies(i));
  assert.equal(a.eligible, 2);
  assert.equal(a.net, 2, "the arithmetic itself would have passed");
  assert.ok(Math.abs(a.net) >= MIN_NET);
  assert.equal(a.action, "WAIT");
  assert.equal(a.basis, "file", "a coverage failure was reported as weak evidence");
  assert.equal(a.gate, "file");
  // And the published record says which families could not be read.
  assert.deepEqual(a.ineligible.sort(), ["history", "peers", "volume"]);
});

test("B5: one cause cannot become four votes, because macro and news do not vote", () => {
  // The case V1.1 as written would have reached NET +4 and High from a single monetary event: F5
  // macro and F6 news both voting with the price families. Here the same row reaches +2 / Medium,
  // because the announcement is context and only the price reaction it caused is evidence.
  const a = aggregate(readFamilies(blank({
    r20: 6.2, sma20: 11, sma50: 10,          // E1 +1
    volumeRatio: 1.4, r1: 0.9,               // E2 +1
    drawdownPct: -2, rangePct: 20,           // E3  0
    relStrength: 1, peers: 11,               // E4  0
    analogs: { count: 748, positive: 377 },  // E5  0
  })));
  assert.equal(a.eligible, 5);
  assert.equal(a.net, 2);
  assert.equal(a.action, "LONG");
  assert.equal(a.confidence, "Medium");
  assert.deepEqual(a.abstaining.sort(), ["history", "peers", "volatility"]);
});

// --- T7 adversarial: what a rule engine with deadbands can be made to do -------------------------

test("T7: a direction does not flip on noise smaller than the deadband", () => {
  // A vote is discrete, so the hazard is a hair's-breadth input change crossing a threshold and
  // reversing a published verdict. The guard is that no single family's flip can reverse NET on its
  // own: reversing a +2 needs two families to change their minds at once.
  const base: FamilyInput = blank({
    r20: 6.2, sma20: 11, sma50: 10,          // E1 +1
    volumeRatio: 1.4, r1: 0.9,               // E2 +1
    drawdownPct: -3, rangePct: 80,           // E3 +1
    relStrength: 9, peers: 11,               // E4 +1
  });
  const before = aggregate(readFamilies(base));
  assert.equal(before.action, "LONG");
  assert.equal(before.net, 4);

  // Nudge every input by a hair, in the direction that hurts.
  const nudged = aggregate(readFamilies({
    ...base,
    r20: 6.19, sma20: 10.999, sma50: 10,
    volumeRatio: 1.399, r1: 0.899,
    drawdownPct: -3.001, rangePct: 79.9,
    relStrength: 8.99,
  }));
  assert.equal(nudged.action, "LONG", "a hair of noise reversed a published direction");
  assert.equal(nudged.net, 4);
});

test("T7: one family can never carry a direction by itself", () => {
  // `MIN_NET = 2` is what stops a single measurement -- or a single broken source -- publishing a
  // call. One family at +1 with the rest eligible and even reaches NET +1 and is held.
  const alone = aggregate(readFamilies(blank({
    r20: 6.2, sma20: 11, sma50: 10,          // E1 +1
    volumeRatio: 1.0, r1: 0.9,               // E2  0, eligible (below the volume threshold)
    drawdownPct: -3, rangePct: 20,           // E3  0, eligible
  })));
  assert.equal(alone.net, 1);
  assert.equal(alone.action, "WAIT");
  assert.equal(alone.basis, "evidence");
  // What leaned is still recorded on a withheld call -- that is the point of publishing the
  // evidence either way -- but no direction is published from it.
  assert.deepEqual(alone.supporting, ["trend"]);
  assert.equal(alone.gate, "thin-evidence");
});

test("T7: four correlated trend inputs are one vote, not four", () => {
  // The whole reason E1 exists as a family: `r20`, `sma20` and `sma50` describe one fact. If they
  // voted separately, one trending price would be three confirmations and `MIN_NET` would be met by
  // a single observation.
  const r = reading(blank({ r20: 6.2, sma20: 11, sma50: 10 }), "E1");
  assert.equal(r.vote, 1);
  const all = readFamilies(blank({ r20: 6.2, sma20: 11, sma50: 10 }));
  assert.equal(all.filter((x) => x.eligible).length, 1, "the trend inputs produced more than one family");
});

test("a direction records what argued against it, so a capped grade can be reviewed afterwards", () => {
  // Without `opposing` by name, a capped Medium and an uncapped Medium are indistinguishable in the
  // log, and the cap is a promise the methodology page publishes.
  const a = aggregate(readFamilies(blank({
    r20: 6.2, sma20: 11, sma50: 10,          // E1 +1
    volumeRatio: 1.4, r1: 0.9,               // E2 +1
    relStrength: -9, peers: 11,              // E4 -1
    drawdownPct: -2, rangePct: 20,           // E3  0
    analogs: { count: 100, positive: 61 },   // E5 +1  -- NET +2, the bar exactly
  })));
  assert.equal(a.action, "LONG");
  assert.deepEqual(a.opposing, ["peers"]);
  // NET, support, opposition and abstention all reproduce from the three recorded lists.
  assert.equal(a.supporting.length - a.opposing.length, a.net);
  assert.equal(a.supporting.length + a.opposing.length + a.abstaining.length, a.eligible);
  assert.equal(a.eligible + a.ineligible.length, FAMILIES.length);
});
