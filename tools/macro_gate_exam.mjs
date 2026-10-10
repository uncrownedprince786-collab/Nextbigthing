// Score the real model on the adversarial exam.
//
//   ANTHROPIC_API_KEY=... node tools/macro_gate_exam.mjs [--runs N] [--model ID]
//
// The offline suite (`tests/macroGateAdversarial.test.ts`) proves what code can: the parser, the
// fail-open paths, the window and what the model is shown. It cannot prove the judgement, and thirteen
// of the twenty cases are judgement -- is a 0.5/20 telegram channel a pump, is a clearing-house halt
// a shock. This asks the model those, one real call per case per run, exactly the way the nightly job
// asks (`makeCall` is imported from it), and prints what it said against what the exam expects.
//
// Costs real money: 13 calls per run. `--runs 3` repeats each to show the one thing a single run
// hides -- the same headlines can read differently twice, which is why the site never calls the model
// at read time. A case passes only if every run agrees with the key.
//
// Nothing is written anywhere and no database is touched. The key is read from the environment and is
// never printed; the rationale the model returns is printed, because reading it is the point.

import process from "node:process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { config as loadEnv } from "dotenv";
import Anthropic from "@anthropic-ai/sdk";

import { evaluate, selectNews } from "../lib/macroGate.ts";
import { CASES, EXAM_NOW } from "../tests/macroGateCases.ts";
import { makeCall } from "./macro_gate.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
loadEnv({ path: path.join(ROOT, ".env"), quiet: true });

const arg = (name, fallback) => {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};
const RUNS = Math.max(1, Math.min(5, Number(arg("--runs", "1")) || 1));
if (arg("--model", null)) process.env.MACRO_GATE_MODEL = arg("--model", "");

if (!process.env.ANTHROPIC_API_KEY) {
  console.log("exam: no ANTHROPIC_API_KEY, so the thirteen judgement cases cannot be scored. Nothing asked.");
  console.log("      the offline half runs with: npm run test:web");
  process.exit(0);
}

const inputOf = (c) => ({
  symbol: c.asset,
  direction: c.decision.verdict,
  price: null,
  stop: c.decision.stopLoss,
  rewardRisk: c.decision.rrr,
  news: c.news,
  reliability: c.reliability,
});

const client = new Anthropic({ timeout: 60_000, maxRetries: 2 });
const call = makeCall(client);
const judged = CASES.filter((c) => c.modelJudged && selectNews(c.news, EXAM_NOW).length > 0);
console.log(`exam: ${judged.length} cases, ${RUNS} run(s) each, model ${process.env.MACRO_GATE_MODEL || "claude-opus-5-5"}`);

let failures = 0;
for (const c of judged) {
  const answers = [];
  for (let i = 0; i < RUNS; i++) answers.push(await evaluate(inputOf(c), call, EXAM_NOW));
  const agree = answers.every((a) => a.valid && a.verdict === c.expectedVerdict && a.reason === c.expectedReason);
  const unusable = answers.filter((a) => !a.valid).length;
  const split = new Set(answers.map((a) => `${a.verdict}/${a.reason}`)).size > 1;
  if (!agree) failures++;
  const first = answers[0];
  console.log(
    `${agree ? "PASS" : "FAIL"}  ${c.id}  ${c.name}\n` +
      `      expected ${c.expectedVerdict}${c.expectedReason ? " " + c.expectedReason : ""}; got ` +
      answers.map((a) => (a.valid ? `${a.verdict}${a.reason ? " " + a.reason : ""}` : "unusable")).join(", ") +
      (split ? "  [runs disagree]" : "") +
      (unusable ? `  [${unusable} unusable: ${first.fallback}]` : "") +
      (first.rationale ? `\n      ${first.rationale.slice(0, 220)}` : ""),
  );
}
console.log(`exam: ${judged.length - failures} of ${judged.length} judgement cases agree with the key.`);
process.exit(failures ? 1 : 0);
