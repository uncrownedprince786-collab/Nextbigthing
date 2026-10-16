// H1: does the historical analogue prior carry directional information beyond a constant call?
//
//     node tools/research/h1_analog_prior.ts [--dataset DIR] [--out FILE]
//
// **Pre-registered in full below, before the run. Executed once.** Nothing here is chosen after
// seeing a result, and no earlier artifact is touched.
//
// ## The hypothesis
//
// > **H1.** The historical analogue prior carries directional information that the current-state
// > features do not, because it asks what followed similar past configurations rather than
// > describing today's bar.
//
// Why it is worth one test and is not a re-tune: every candidate measured so far reads the present
// state of one instrument, and all of them failed -- a classifier over the fifteen point-in-time
// columns at 0.3618 against a 0.4377 majority, the rule engine over the same information at 0.3979
// against a 0.4388 constant call. E5, the analogue prior, is the one source the policy permits to
// vote directionally that has **never had a readable vote at any evaluated horizon**, because
// `examples-v3` carries matched days at horizons 1 and 5 while the evaluated label is 20 sessions,
// and voting a 5-session prior on a 20-session label is the horizon mixing §D4 forbids.
//
// This tests it **at its own horizon**, where the data already exists, so that an expensive
// 20-session analogue corpus is only built if the cheap version survives.
//
// ## What `pit.an.5` actually is, read from the code and not the name
//
// `tools/foundation/pit_features.py` `AnalogSeries.at(t, 5)`: for the session at index `t` it finds
// past sessions `i` whose own analogue factors (one-day return, five-day return, and the volume
// ratio where volume exists) match today's within `jobs/analogs` tolerances, and for each one takes
// `(close[i+5]/close[i] - 1) * 100` -- that candidate's **forward** five-session move. `positive` is
// how many of those were above zero.
//
// It is point-in-time by construction: candidates are capped at `i <= t - horizon`, so every matched
// day's forward window had already closed by `t`. No value in the row depends on anything after the
// decision session.
//
// ## The target, and why it is the sign and not a band
//
// `outcome.fwd5 = (close[i+5]/base - 1) * 100`, `base` being the as-of close. The prior's `positive`
// is *defined* as the count of matched forward moves above zero, so the event it estimates is
// `fwd5 > 0` and the target must be that same event. A +/-2% band would be a threshold invented for
// this test; `label20`'s 2% band was set for a twenty-session horizon and carrying it to five
// sessions would be a different, unapproved label.
//
//   * UP when `fwd5 > 0`, DOWN when `fwd5 < 0`.
//   * `fwd5 == 0` is **excluded and counted**: no directional outcome occurred, so a directional call
//     on it is neither right nor wrong. Excluded from the prior and from the baseline equally.
//
// Maturity: `full_history.py` emits a row only when at least 20 forward sessions exist, so `fwd5` is
// mature on **every** row in the frozen dataset. The last 20 sessions of each asset are already
// excluded there, which is stricter than a five-session label needs and is left as it is, because
// this test may not rebuild the frozen data.
//
// ## The rule, reused and not restated
//
// The prediction rule is **E5 exactly as shipped** -- `readFamilies` from `lib/families.ts` is called
// with the analogue block and its E5 reading is taken. So the thresholds are
// `ANALOGS_CONFIRM_MIN = 8` and `ANALOG_SHARE_CONFIRMS = 0.55` from `lib/decision.ts`, which are
// pre-existing and documented: a bare majority over matched days is the absence of a finding, not a
// confirmation (brain.md, measured at 377 of 748). Eligible when `matches >= 8`; UP at a share of
// 0.55 or more, DOWN at 0.45 or less, abstain between. Nothing is fitted, so there is nothing here
// to tune.
//
// ## Eligibility and exclusions
//
//   * point-in-time features present and `outcome.fwd5` present;
//   * `fwd5 != 0`;
//   * no `dataQuality` flag set -- the same quarantine every other arm applies, because a window
//     crossing an unadjusted corporate action carries a move no holder experienced;
//   * `pit.an.5` present with `matches >= 8` and a `positive` count.
//
// ## Metric, baseline, and the acceptance criterion
//
// Primary metric: **accuracy on the rows the prior calls**. Abstention is reported as coverage and
// never scored as a miss.
//
// Baseline: the **best single constant call** (always UP, or always DOWN) on exactly those rows. A
// selective signal can always look accurate by keeping an easy subset, and a reference measured over
// rows it declined would answer a different question.
//
// Acceptance is **reused from `tools/research/context_experiment.py`**, which is the closest
// precedent in this repository -- the same shape of test, an abstaining signal scored on the rows it
// calls against a reference on identical rows. All three conditions, or it is a NO-GO:
//
//   1. mean accuracy at least **+0.02** above the constant call (`MIN_GAIN_OVER_RANDOM` there);
//   2. beats the constant call in **4 of the 5** walk-forward folds (that file required 5 of 6);
//   3. **does not degrade in the 2022 adverse regime** -- §9 gate 5's clause, the one both earlier
//      candidates actually failed.
//
// A **validity floor, which is not an acceptance condition**: at least 1,000 called rows in every
// fold. Below that the fold cannot answer the question and the verdict is INCONCLUSIVE rather than
// NO-GO, because "too little to tell" and "measured and absent" are different results.
//
// ## Splits, holdout, embargo, and what is not corrected
//
//   * Walk-forward, one fold per test year **2021-2025**.
//   * **2026 is held out entirely.** It is not used for any choice and is read once at the end as a
//     confirmatory report; it cannot change the verdict. The earlier candidates exposed 2021-2026,
//     and that is stated rather than implied.
//   * Embargo of **5 sessions at each fold boundary**, matched to the label's own horizon, so no
//     row's forward window straddles a boundary. Stated honestly: **nothing is fitted here**, so
//     there is no train-to-test leakage path for an embargo to close. It is applied for the
//     independence of the reported metric, not as a leakage control, and calling it one would be a
//     ritual.
//   * **Cross-sectional correlation is reported, not corrected.** Many assets share a decision date
//     and their five-session outcomes share a market factor, so the row count overstates
//     independence. Unique decision dates are reported beside row counts in every fold, and the
//     per-market breakdown is reported, because a single pooled mean can hide one market carrying it.

import { createReadStream } from "node:fs";
import { writeFileSync } from "node:fs";
import { createGunzip } from "node:zlib";
import { createInterface } from "node:readline";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { readFamilies, LOGIC_VERSION } from "../../lib/families.ts";
import { ANALOGS_CONFIRM_MIN, ANALOG_SHARE_CONFIRMS, type Market } from "../../lib/decision.ts";

const args = process.argv.slice(2);
const argOf = (n: string, d?: string) => (args.includes(n) ? args[args.indexOf(n) + 1] : d);
const DATASET = argOf("--dataset", ".cache/foundation/dataset_full") as string;
const OUT = argOf("--out", "data/foundation/dataset/h1_analog_prior.json") as string;

// Pre-declared, before the run.
const MIN_GAIN = 0.02;
const MIN_FOLDS_WON = 4;
const WALK_FORWARD = [2021, 2022, 2023, 2024, 2025];
const HELD_OUT = 2026;
const EMBARGO_SESSIONS = 5;
const MIN_CALLS_PER_FOLD = 1_000;
const ADVERSE = { name: "2022 rate-shock bear", from: "2022-01-03", to: "2022-10-12" };

interface Row { asOf: string; market: Market; up: boolean; call: "LONG" | "SHORT" | null }

function marketOf(rec: { market?: string; assetType?: string }): Market {
  if (rec.market === "PK") return "PSX";
  const t = rec.assetType;
  if (t === "forex") return "FX";
  if (t === "crypto") return "Crypto";
  if (t === "commodity") return "Commodity";
  return "US";
}

/// E5's vote, taken from the shipped rule rather than restated here.
function priorCall(matches: number, positive: number, market: Market): "LONG" | "SHORT" | null {
  const readings = readFamilies({
    market,
    r20: null, sma20: null, sma50: null, volumeRatio: null, r1: null,
    atr14: null, atrTrailingMedian: null, rangePct: null, drawdownPct: null,
    relStrength: null, peers: 0,
    analogs: { count: matches, positive },
  });
  const e5 = readings.find((r) => r.id === "E5");
  if (!e5 || !e5.eligible || e5.vote === 0) return null;
  return e5.vote > 0 ? "LONG" : "SHORT";
}

const exclusions = { noFeatures: 0, noFwd5: 0, fwd5Zero: 0, qualityFlagged: 0, noAnalog: 0, tooFewMatches: 0 };

async function load(dir: string): Promise<Row[]> {
  const files = (await readdir(dir)).filter((f) => /^examples-v3-.*\.jsonl\.gz$/.test(f)).sort();
  const rows: Row[] = [];
  for (const f of files) {
    const rl = createInterface({ input: createReadStream(join(dir, f)).pipe(createGunzip()), crlfDelay: Infinity });
    for await (const line of rl) {
      if (!line.trim()) continue;
      const rec = JSON.parse(line);
      if (!rec.pit?.f) { exclusions.noFeatures++; continue; }
      const fwd5 = rec.outcome?.fwd5;
      if (typeof fwd5 !== "number") { exclusions.noFwd5++; continue; }
      if (fwd5 === 0) { exclusions.fwd5Zero++; continue; }
      if (Object.values(rec.dataQuality ?? {}).some(Boolean)) { exclusions.qualityFlagged++; continue; }
      const a5 = rec.pit?.an?.["5"];
      if (!a5 || typeof a5.matches !== "number" || typeof a5.positive !== "number") { exclusions.noAnalog++; continue; }
      if (a5.matches < ANALOGS_CONFIRM_MIN) { exclusions.tooFewMatches++; continue; }
      const market = marketOf(rec);
      rows.push({ asOf: rec.asOf, market, up: fwd5 > 0, call: priorCall(a5.matches, a5.positive, market) });
    }
  }
  return rows;
}

function score(rows: Row[]) {
  const called = rows.filter((r) => r.call !== null);
  const right = called.filter((r) => (r.call === "LONG") === r.up).length;
  const up = called.filter((r) => r.up).length;
  const down = called.length - up;
  const dates = new Set(called.map((r) => r.asOf)).size;
  const round = (n: number) => Number(n.toFixed(4));
  return {
    rows: rows.length,
    calls: called.length,
    uniqueDecisionDates: dates,
    coverage: rows.length ? round(called.length / rows.length) : null,
    accuracy: called.length ? round(right / called.length) : null,
    constantCall: up >= down ? "LONG" : "SHORT",
    constantCallAccuracy: called.length ? round(Math.max(up, down) / called.length) : null,
  };
}

function gain(s: ReturnType<typeof score>): number | null {
  return s.accuracy !== null && s.constantCallAccuracy !== null
    ? Number((s.accuracy - s.constantCallAccuracy).toFixed(4)) : null;
}

async function main() {
  console.log("loading frozen dataset ...");
  const rows = await load(DATASET);
  console.log(`  ${rows.length.toLocaleString()} eligible rows`, JSON.stringify(exclusions));

  const freeze = JSON.parse(await readFile("data/foundation/dataset/dataset_freeze.json", "utf8"));
  const allDates = [...new Set(rows.map((r) => r.asOf))].sort();

  type Fold = ReturnType<typeof score> & {
    testYear: number; testWindow: string[]; embargoSessionsDropped: number;
    gainOverConstantCall: number | null; beatsConstantCall: boolean; meetsValidityFloor: boolean;
  };
  const folds: Fold[] = [];
  for (const year of WALK_FORWARD) {
    // The embargo trims the start of each test window so no row's five-session forward return
    // straddles the boundary from the previous period.
    const cutIndex = allDates.findIndex((d) => d >= `${year}-01-01`);
    const from = allDates[Math.min(allDates.length - 1, Math.max(0, cutIndex + EMBARGO_SESSIONS))];
    const test = rows.filter((r) => r.asOf >= from && r.asOf <= `${year}-12-31`);
    const s = score(test);
    folds.push({
      testYear: year, testWindow: [from, `${year}-12-31`], embargoSessionsDropped: EMBARGO_SESSIONS,
      ...s, gainOverConstantCall: gain(s),
      beatsConstantCall: (gain(s) ?? -1) > 0,
      meetsValidityFloor: s.calls >= MIN_CALLS_PER_FOLD,
    });
    console.log(`  fold ${year}: calls ${s.calls} · acc ${s.accuracy} · constant ${s.constantCallAccuracy} · gain ${gain(s)}`);
  }

  const adverseRows = rows.filter((r) => r.asOf >= ADVERSE.from && r.asOf <= ADVERSE.to);
  const adverse = score(adverseRows);
  const heldOut = score(rows.filter((r) => r.asOf >= `${HELD_OUT}-01-01` && r.asOf <= `${HELD_OUT}-12-31`));

  const byMarket: Record<string, unknown> = {};
  for (const m of [...new Set(rows.map((r) => r.market))].sort()) {
    const s = score(rows.filter((r) => r.market === m));
    byMarket[m] = { ...s, gainOverConstantCall: gain(s) };
  }

  const mean = (pick: (f: Fold) => number | null) => {
    const vals = folds.map(pick).filter((v): v is number => v !== null);
    return vals.length ? Number((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(4)) : null;
  };
  const meanAccuracy = mean((f) => f.accuracy);
  const meanConstant = mean((f) => f.constantCallAccuracy);
  const meanGain = meanAccuracy !== null && meanConstant !== null
    ? Number((meanAccuracy - meanConstant).toFixed(4)) : null;
  const won = folds.filter((f) => f.beatsConstantCall).length;
  const allValid = folds.every((f) => f.meetsValidityFloor);
  const adverseGain = gain(adverse);

  const criteria = {
    meanGainAtLeast: [meanGain, MIN_GAIN, meanGain !== null && meanGain >= MIN_GAIN],
    foldsBeatingConstantCall: [won, MIN_FOLDS_WON, won >= MIN_FOLDS_WON],
    doesNotDegradeInTheAdverseRegime: [adverseGain, 0, adverseGain !== null && adverseGain >= 0],
  };
  const passed = Object.values(criteria).every((c) => c[2] === true);
  const verdict = !allValid ? "INCONCLUSIVE" : passed ? "PASS" : "NO-GO";

  const report = {
    version: "h1-analog-prior-v1",
    status: "offline falsification test; nothing deployed, nothing traded, no model fitted",
    hypothesis: "the historical analogue prior carries directional information beyond the best "
      + "constant call on the same rows, at the five-session horizon where the data already exists",
    logicVersion: LOGIC_VERSION,
    rule: {
      source: "E5 as shipped in lib/families.ts, called through readFamilies -- not restated here",
      eligibleWhen: `matches >= ${ANALOGS_CONFIRM_MIN}`,
      callsLongAt: `share >= ${ANALOG_SHARE_CONFIRMS}`,
      callsShortAt: `share <= ${(1 - ANALOG_SHARE_CONFIRMS).toFixed(2)}`,
      fitted: "nothing; there is no parameter in this test to tune",
    },
    target: {
      definition: "sign(outcome.fwd5); UP when fwd5 > 0, DOWN when fwd5 < 0",
      whyTheSign: "the prior's `positive` counts matched forward moves above zero, so the event it "
        + "estimates is fwd5 > 0; a band would be a threshold invented for this test",
      zeroOutcome: "excluded and counted -- no directional outcome occurred",
      maturity: "fwd5 is mature on every row: full_history.py emits a row only with 20 forward sessions",
    },
    dataVersion: {
      dataset: freeze.version, frozenAt: freeze.frozenAt, blockingGatesGreen: freeze.blockingGatesGreen,
      rowsWithFeatures: freeze.rows?.withPointInTimeFeatures, repoHead: freeze.repoHead,
    },
    eligibleRows: rows.length,
    exclusions,
    preDeclaredCriteria: {
      reusedFrom: "tools/research/context_experiment.py -- the same shape of test, an abstaining "
        + "signal scored on the rows it calls against a reference on identical rows",
      meanGainOverConstantCall: MIN_GAIN,
      foldsBeatingConstantCall: `${MIN_FOLDS_WON} of ${WALK_FORWARD.length}`,
      adverseRegime: ADVERSE.name,
      validityFloorCallsPerFold: MIN_CALLS_PER_FOLD,
      setBefore: "the run",
    },
    splitPlan: {
      walkForward: WALK_FORWARD, heldOut: HELD_OUT,
      heldOutTreatment: "not used for any choice; read once as a confirmatory report and cannot change the verdict",
      embargoSessions: EMBARGO_SESSIONS,
      embargoIsNotALeakageControl: "nothing is fitted, so there is no train-to-test path; the embargo "
        + "keeps a row's forward window from straddling a fold boundary",
      exposureNote: "2021-2026 were exposed by the earlier candidates; this is not a pristine holdout "
        + "except for 2026, which this test protected",
    },
    crossSectional: {
      handling: "reported, not corrected",
      why: "many assets share a decision date and their five-session outcomes share a market factor, "
        + "so the row count overstates independence; unique decision dates are reported per fold",
    },
    folds,
    adverseRegime: { ...ADVERSE, ...adverse, gainOverConstantCall: adverseGain },
    heldOut2026: { ...heldOut, gainOverConstantCall: gain(heldOut), usedForAnyChoice: false },
    byMarket,
    summary: {
      folds: folds.length, meanAccuracy, meanConstantCallAccuracy: meanConstant, meanGain,
      foldsBeatingConstantCall: won, allFoldsMeetValidityFloor: allValid,
    },
    criteriaMet: criteria,
    verdict,
  };

  writeFileSync(OUT, JSON.stringify(report, null, 1) + "\n", "utf8");
  console.log(JSON.stringify({ summary: report.summary, adverseRegime: report.adverseRegime,
    heldOut2026: report.heldOut2026, byMarket, criteriaMet: criteria, verdict }, null, 1));
}

await main();
