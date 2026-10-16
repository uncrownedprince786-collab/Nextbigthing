// The family decision core, measured against `label20` on chronological folds.
//
//     node tools/research/family_eval.ts [--dataset DIR] [--out FILE] [--h5-analogs]
//
// **Pre-registered before any result was seen.** The references, the folds, the scoring rule and the
// acceptance clause are fixed here and none of them is chosen after looking at an outcome.
//
// **Why this runs in Node and not in Python.** It imports `lib/families.ts` itself. A Python port of
// the family rules would be a second implementation of the thing being measured, and the one fault
// this project keeps finding is two parts of one system holding different opinions about the same
// threshold. There is one implementation, and the site and this evaluation read it.
//
// **What is being scored.** The brain emits LONG, SHORT or WAIT. It never emits FLAT, so a decision
// is correct when a LONG meets `label20 = UP` or a SHORT meets `DOWN`; a FLAT outcome counts
// against it. Abstention is not scored as a miss -- it is reported as coverage, because §3.6 makes
// WAIT a legitimate terminus and an accuracy taken over all rows would punish a system for
// declining, while a precision taken over a handful would reward it for declining almost always.
// Both numbers are published together and neither is published alone.
//
// **The references, on identical samples.** §9 gate 5 requires both, measured on the same rows:
//
//   * **constant call** -- always LONG, or always SHORT, whichever is better on those rows. This is
//     the "could one fixed answer do as well" test, and it is the reference that matters, because
//     any selective filter can look accurate by keeping an easy subset. The plain majority class
//     including FLAT is reported beside it for context and is NOT the bar, since the brain cannot
//     emit FLAT and a reference it cannot imitate is not a comparison.
//   * **rule baseline** -- trend agreement, `r20` and `relStrength` both one way, the same rule
//     `baseline_experiment.py` uses, scored over the same rows by the same convention.
//
// **Acceptance, from §9.** Beat both references out-of-sample, on identical samples, in more than
// half the folds, **and not degrade in the adverse regime** -- the 2022 rate-shock bear, which is
// the clause the first experiment actually failed.
//
// **E5 history is ineligible here, and that is a data fact, not a choice about the rule.**
// `examples-v3` carries matched past days at horizons 1 and 5 only; there is no 20-session analog
// corpus. Voting a 5-session prior on a 20-session label would be the horizon mixing §D4 forbids,
// so E5 is unreadable at this horizon and the eligibility floor is met by E1-E4 alone. `--h5-analogs`
// exists to show what that choice costs and is not the default.

import { createReadStream } from "node:fs";
import { writeFileSync } from "node:fs";
import { createGunzip } from "node:zlib";
import { createInterface } from "node:readline";
import { readdir } from "node:fs/promises";
import { join } from "node:path";
import { aggregate, readFamilies, LOGIC_VERSION, FAMILIES, FAMILY_NAME, type FamilyInput } from "../../lib/families.ts";
import type { Market } from "../../lib/decision.ts";

const args = process.argv.slice(2);
const argOf = (n: string, d?: string) => (args.includes(n) ? args[args.indexOf(n) + 1] : d);
const USE_H5 = args.includes("--h5-analogs");

const DATASET = argOf("--dataset", ".cache/foundation/assembled_test") as string;
const OUT = argOf("--out", "data/foundation/dataset/family_evaluation.json") as string;

/// A 20-session label makes consecutive rows share 19 of their 20 forward sessions, so the training
/// side of every cut is trimmed by this many sessions. The same number `baseline_experiment.py` uses.
const EMBARGO = 20;
/// The adverse regime §9 names, from `historical_regimes.json`.
const ADVERSE = { name: "2022 rate-shock bear", from: "2022-01-03", to: "2022-10-12" };

interface Row {
  asOf: string;
  market: Market;
  label: "UP" | "DOWN" | "FLAT";
  input: FamilyInput;
  r20: number | null;
  relStrength: number | null;
}

function marketOf(rec: { market?: string; assetType?: string }): Market {
  if (rec.market === "PK") return "PSX";
  const t = rec.assetType;
  if (t === "forex") return "FX";
  if (t === "crypto") return "Crypto";
  if (t === "commodity") return "Commodity";
  return "US";
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

async function load(dir: string): Promise<Row[]> {
  const files = (await readdir(dir)).filter((f) => /^examples-v3-.*\.jsonl\.gz$/.test(f)).sort();
  const rows: Row[] = [];
  let seen = 0;
  let excluded = 0;
  for (const f of files) {
    const rl = createInterface({ input: createReadStream(join(dir, f)).pipe(createGunzip()), crlfDelay: Infinity });
    for await (const line of rl) {
      if (!line.trim()) continue;
      seen++;
      const rec = JSON.parse(line);
      const o = rec.outcome ?? {};
      const fts = rec.pit?.f;
      if (!fts || !o.mature20 || !["UP", "DOWN", "FLAT"].includes(o.label20)) continue;
      // Quarantine: a window crossing an unadjusted corporate action carries a move no holder
      // experienced. Excluded from every arm equally.
      if (Object.values(rec.dataQuality ?? {}).some(Boolean)) {
        excluded++;
        continue;
      }
      const an5 = rec.pit?.an?.["5"];
      rows.push({
        asOf: rec.asOf,
        market: marketOf(rec),
        label: o.label20,
        r20: num(fts.r20),
        relStrength: num(fts.relStrength),
        input: {
          market: marketOf(rec),
          r20: num(fts.r20), sma20: num(fts.sma20), sma50: num(fts.sma50),
          volumeRatio: num(fts.volumeRatio), r1: num(fts.r1),
          // Present from the build that added `atrTrailingMedian` onward; `num` returns null for an
          // assembly made before it, which E3 reports as an unmeasured baseline rather than as calm.
          atr14: num(fts.atr14), atrTrailingMedian: num(fts.atrTrailingMedian),
          rangePct: num(fts.rangePct), drawdownPct: num(fts.drawdownPct),
          relStrength: num(fts.relStrength), peers: num(fts.peers) ?? 0,
          // See the header: no 20-session matched days exist. `--h5-analogs` substitutes the
          // 5-session corpus to show what the horizon rule costs.
          analogs: USE_H5 && an5 && num(an5.matches) !== null && num(an5.positive) !== null
            ? { count: an5.matches as number, positive: an5.positive as number }
            : null,
        },
      });
    }
  }
  console.log(`  ${seen.toLocaleString()} rows seen, ${rows.length.toLocaleString()} usable, ${excluded.toLocaleString()} quarantined`);
  return rows;
}

/// Trend agreement: `r20` and `relStrength` both one way, else no call. The same rule the baseline
/// experiment uses, reduced to a directional call so it is scored by this file's convention.
function ruleBaseline(r: Row): "LONG" | "SHORT" | null {
  if (r.r20 === null || r.relStrength === null) return null;
  if (r.r20 > 0 && r.relStrength > 0) return "LONG";
  if (r.r20 < 0 && r.relStrength < 0) return "SHORT";
  return null;
}

function correct(call: "LONG" | "SHORT", label: Row["label"]): boolean {
  return (call === "LONG" && label === "UP") || (call === "SHORT" && label === "DOWN");
}

function share(n: number, d: number): number | null {
  return d === 0 ? null : Number((n / d).toFixed(4));
}

interface ArmScore {
  calls: number;
  coverage: number | null;
  accuracy: number | null;
}

function scoreOn(rows: Row[], call: (r: Row) => "LONG" | "SHORT" | null, universe: number): ArmScore {
  let calls = 0;
  let right = 0;
  for (const r of rows) {
    const c = call(r);
    if (!c) continue;
    calls++;
    if (correct(c, r.label)) right++;
  }
  return { calls, coverage: share(calls, universe), accuracy: share(right, calls) };
}

/// The best a single fixed answer could do on exactly these rows.
function constantCall(rows: Row[]): { best: "LONG" | "SHORT"; accuracy: number | null } {
  const up = rows.filter((r) => r.label === "UP").length;
  const down = rows.filter((r) => r.label === "DOWN").length;
  const best = up >= down ? "LONG" : "SHORT";
  return { best, accuracy: share(Math.max(up, down), rows.length) };
}

function majorityIncludingFlat(rows: Row[]): number | null {
  const c = { UP: 0, DOWN: 0, FLAT: 0 };
  for (const r of rows) c[r.label]++;
  return share(Math.max(c.UP, c.DOWN, c.FLAT), rows.length);
}

function main() {
  console.log("loading dataset ...");
  return load(DATASET).then((rows) => {
    rows.sort((a, b) => (a.asOf < b.asOf ? -1 : a.asOf > b.asOf ? 1 : 0));
    const dates = [...new Set(rows.map((r) => r.asOf))].sort();

    // --- what each family actually reads, over the whole set -----------------------------------
    const firing: Record<string, { eligible: number; for: number; against: number; even: number; unreadable: number }> = {};
    for (const id of FAMILIES) firing[FAMILY_NAME[id]] = { eligible: 0, for: 0, against: 0, even: 0, unreadable: 0 };
    const decisions = { LONG: 0, SHORT: 0, WAIT: 0 };
    const waitBasis = { file: 0, evidence: 0 };
    const eligibleHistogram: Record<number, number> = {};

    const decided = new Map<Row, ReturnType<typeof aggregate>>();
    for (const r of rows) {
      const a = aggregate(readFamilies(r.input));
      decided.set(r, a);
      decisions[a.action]++;
      if (a.action === "WAIT" && a.basis) waitBasis[a.basis]++;
      eligibleHistogram[a.eligible] = (eligibleHistogram[a.eligible] ?? 0) + 1;
      for (const reading of a.readings) {
        const f = firing[reading.name];
        if (!reading.eligible) { f.unreadable++; continue; }
        f.eligible++;
        if (reading.vote > 0) f.for++;
        else if (reading.vote < 0) f.against++;
        else f.even++;
      }
    }

    const brainCall = (r: Row): "LONG" | "SHORT" | null => {
      const a = decided.get(r)!;
      return a.action === "WAIT" ? null : a.action;
    };

    // --- chronological folds, one per test year --------------------------------------------------
    const folds = [];
    for (let year = 2021; year <= 2026; year++) {
      const cut = `${year}-01-01`;
      const cutPos = dates.findIndex((d) => d >= cut);
      const trainEnd = dates[Math.max(0, cutPos - EMBARGO - 1)];
      const test = rows.filter((r) => r.asOf >= cut && r.asOf <= `${year}-12-31`);
      if (test.length < 100) continue;

      const brain = scoreOn(test, brainCall, test.length);
      // Both references are measured on the rows the brain actually called, which is what "identical
      // samples" has to mean for a system that abstains: a reference scored over rows the brain
      // declined would be answering a different question.
      const called = test.filter((r) => brainCall(r) !== null);
      const constant = constantCall(called);
      const rule = scoreOn(called, ruleBaseline, called.length);

      folds.push({
        testYear: year,
        trainEnds: trainEnd,
        embargoSessionsDropped: EMBARGO,
        testRows: test.length,
        brain: { ...brain },
        onTheRowsTheBrainCalled: {
          rows: called.length,
          constantCall: constant.best,
          constantCallAccuracy: constant.accuracy,
          majorityIncludingFlat: majorityIncludingFlat(called),
          ruleBaselineCalls: rule.calls,
          ruleBaselineAccuracy: rule.accuracy,
        },
        beatsConstantCall: brain.accuracy !== null && constant.accuracy !== null && brain.accuracy > constant.accuracy,
        beatsRuleBaseline: brain.accuracy !== null && rule.accuracy !== null && brain.accuracy > rule.accuracy,
      });
      console.log(`  fold ${year}: coverage ${brain.coverage ?? 0} · brain ${brain.accuracy} · constant ${constant.accuracy} · rule ${rule.accuracy}`);
    }

    // --- per market, because a single mean can hide a market that is carrying or sinking it --------
    const byMarket: Record<string, unknown> = {};
    for (const m of [...new Set(rows.map((r) => r.market))].sort()) {
      const mine = rows.filter((r) => r.market === m);
      const called = mine.filter((r) => brainCall(r) !== null);
      const s = scoreOn(mine, brainCall, mine.length);
      const constant = constantCall(called);
      byMarket[m] = {
        rows: mine.length, calls: s.calls, coverage: s.coverage, accuracy: s.accuracy,
        constantCall: constant.best, constantCallAccuracy: constant.accuracy,
        beatsConstantCall: s.accuracy !== null && constant.accuracy !== null && s.accuracy > constant.accuracy,
      };
    }

    // --- the adverse regime, which is the clause the first experiment failed ----------------------
    const adverseRows = rows.filter((r) => r.asOf >= ADVERSE.from && r.asOf <= ADVERSE.to);
    const adverseCalled = adverseRows.filter((r) => brainCall(r) !== null);
    const adverseBrain = scoreOn(adverseRows, brainCall, adverseRows.length);
    const adverseConstant = constantCall(adverseCalled);

    const scored = folds.filter((f) => f.brain.accuracy !== null);
    const beatBoth = scored.filter((f) => f.beatsConstantCall && f.beatsRuleBaseline).length;
    const meanAccuracy = scored.length ? Number((scored.reduce((s, f) => s + (f.brain.accuracy as number), 0) / scored.length).toFixed(4)) : null;
    const meanConstant = scored.length ? Number((scored.reduce((s, f) => s + (f.onTheRowsTheBrainCalled.constantCallAccuracy as number), 0) / scored.length).toFixed(4)) : null;
    const meanCoverage = scored.length ? Number((scored.reduce((s, f) => s + (f.brain.coverage as number), 0) / scored.length).toFixed(4)) : null;

    const adverseOk =
      adverseBrain.accuracy !== null && adverseConstant.accuracy !== null && adverseBrain.accuracy >= adverseConstant.accuracy;
    const criteria = {
      beatsBothReferencesInMoreThanHalfTheFolds: [beatBoth, Math.floor(scored.length / 2) + 1, beatBoth > scored.length / 2],
      doesNotDegradeInTheAdverseRegime: [adverseBrain.accuracy, adverseConstant.accuracy, adverseOk],
    };
    const ok = Object.values(criteria).every((v) => v[2] === true);

    const report = {
      version: "family-evaluation-v1",
      logicVersion: LOGIC_VERSION,
      status: "offline evaluation of the decision core; nothing deployed, nothing traded",
      specification: "BRAIN-SPEC-V1.md §3 as corrected by BRAIN-LOGIC-CLOSURE-2026-10-16.md §B4-B5",
      scoring: {
        rule: "a LONG is correct on label20 UP, a SHORT on DOWN; FLAT counts against the call",
        abstention: "reported as coverage, never scored as a miss -- WAIT is a legitimate terminus (§3.6)",
        references: "measured on exactly the rows the brain called, since a system that abstains cannot be compared on rows it declined",
        constantCallIsTheBar: "the brain cannot emit FLAT, so the majority class including FLAT is reported for context and is not the bar",
      },
      dataVersion: { dataset: "examples-v3", rows: rows.length, label: "label20", horizonSessions: 20 },
      e5History: USE_H5
        ? "SUBSTITUTED with the 5-session analog corpus (--h5-analogs): a horizon mix, shown only to price the default"
        : "INELIGIBLE: examples-v3 carries matched days at horizons 1 and 5 only, and voting a 5-session prior on a 20-session label is the horizon mixing §D4 forbids",
      familyFiring: firing,
      decisions,
      waitBasis,
      byMarket,
      eligibleFamiliesHistogram: eligibleHistogram,
      folds,
      adverseRegime: {
        ...ADVERSE,
        rows: adverseRows.length,
        brainCalls: adverseBrain.calls,
        brainCoverage: adverseBrain.coverage,
        brainAccuracy: adverseBrain.accuracy,
        constantCall: adverseConstant.best,
        constantCallAccuracy: adverseConstant.accuracy,
      },
      summary: {
        folds: scored.length,
        meanCoverage,
        meanAccuracy,
        meanConstantCallAccuracy: meanConstant,
        foldsBeatingBothReferences: beatBoth,
      },
      preDeclaredCriteria: {
        source: "BRAIN-SPEC-V1.md §9 phase gate 5",
        clause: "beat both references out-of-sample on identical samples in more than half the folds, and not degrade in the adverse regime",
        setBefore: "any result was seen",
      },
      criteriaMet: criteria,
      verdict: ok ? "GO" : "NO-GO",
    };

    writeFileSync(OUT, JSON.stringify(report, null, 1) + "\n", "utf8");
    console.log(JSON.stringify({ familyFiring: firing, decisions, waitBasis, summary: report.summary, adverseRegime: report.adverseRegime, criteriaMet: criteria, verdict: report.verdict }, null, 1));
  });
}

await main();
