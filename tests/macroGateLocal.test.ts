// The local (no-model) macro gatekeeper: the adversarial exam scored for real, held-out cases the
// word table was not written against, and the properties that make it safe to run unattended.
//
// An exam the table was tuned to pass proves little, so the second half is cases written afterwards in
// different words: shocks phrased differently, decoys that reuse the trigger words for something else,
// and every boundary of the trust rule. A miss there is reported, not hidden -- see the last test.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  IGNORED_BELOW, MIN_EVIDENCE, TRUSTED_MEAN, assetClassOf, evaluateLocal, normalise, trustOf,
} from "../lib/macroGateLocal.ts";
import type { GateInput, GateNews } from "../lib/macroGate.ts";
import { CASES, EXAM_NOW } from "./macroGateCases.ts";
import type { ExamCase } from "./macroGateCases.ts";

const asInput = (c: ExamCase): GateInput => ({
  symbol: c.asset,
  assetClass: assetClassOf(c.asset),
  direction: c.decision.verdict,
  price: null,
  stop: c.decision.stopLoss,
  rewardRisk: c.decision.rrr,
  news: c.news,
  reliability: c.reliability,
});

const NOW = EXAM_NOW;
const ago = (minutes: number) => new Date(NOW.getTime() - minutes * 60_000).toISOString();
const TRUSTED = { source: "wire", alpha: 40, beta: 2 };

function one(over: {
  symbol?: string; assetClass?: string | null; direction?: "LONG" | "SHORT"; title: string;
  source?: string; scope?: GateNews["scope"]; reliability?: GateInput["reliability"]; minutes?: number;
}): ReturnType<typeof evaluateLocal> {
  const source = over.source ?? "wire";
  return evaluateLocal(
    {
      symbol: over.symbol ?? "BTCUSDT",
      assetClass: over.assetClass,
      direction: over.direction ?? "LONG",
      price: null, stop: null, rewardRisk: null,
      news: [{ title: over.title, publishedAt: ago(over.minutes ?? 30), source, scope: over.scope }],
      reliability: over.reliability ?? [{ ...TRUSTED, source }],
    },
    NOW,
  );
}

const tag = (r: ReturnType<typeof evaluateLocal>) => `${r.verdict}${r.reason ? " " + r.reason : ""}`;

// --- the exam ----------------------------------------------------------------------------------

test("the local engine scores 20 of 20 on the adversarial exam, deterministically", () => {
  const misses: string[] = [];
  for (const c of CASES) {
    const r = evaluateLocal(asInput(c), NOW);
    assert.equal(r.valid, true, c.id);
    if (r.verdict !== c.expectedVerdict || r.reason !== c.expectedReason) {
      misses.push(`${c.id} expected ${c.expectedVerdict}/${c.expectedReason} got ${tag(r)}`);
    }
    // Same input, same answer: the property a model cannot give.
    assert.deepEqual(evaluateLocal(asInput(c), NOW), r, c.id);
  }
  assert.deepEqual(misses, []);
});

test("the four genuine shocks are refused for the right reason, with the source and its credibility", () => {
  for (const id of ["TC-05", "TC-06", "TC-07", "TC-08"]) {
    const c = CASES.find((x) => x.id === id)!;
    const r = evaluateLocal(asInput(c), NOW);
    assert.equal(r.verdict, "REJECT", id);
    assert.equal(r.reason, c.expectedReason, id);
    assert.match(r.rationale, /credibility 0\.9\d/, id);
    assert.ok(r.rationale.includes(c.news[0].source), id);
  }
});

test("the traps cost nothing: the untrusted sources are ignored on their statistics, before any word is read", () => {
  // TC-01..04 and the blog in TC-11 say alarming or exciting things from sources under 0.30. Their
  // statistics alone decide them, so they would pass whatever the headline said.
  for (const id of ["TC-01", "TC-02", "TC-03", "TC-04"]) {
    const c = CASES.find((x) => x.id === id)!;
    assert.equal(trustOf(c.news[0].source, c.reliability).trust, "ignored", id);
    const shock = { ...asInput(c), news: [{ ...c.news[0], title: "SEC announces immediate ban on crypto derivatives trading" }] };
    assert.equal(evaluateLocal(shock, NOW).verdict, "EXECUTE", `${id}: a shock from an ignored source is not a shock`);
  }
});

// --- trust boundaries --------------------------------------------------------------------------

test("trust: 0.70 with enough evidence is believed, and every neighbour is not", () => {
  const t = (alpha: number, beta: number) => trustOf("s", [{ source: "s", alpha, beta }]).trust;
  assert.equal(TRUSTED_MEAN, 0.7);
  assert.equal(IGNORED_BELOW, 0.3);
  assert.equal(t(7, 3), "trusted"); // exactly 0.70, mass 10
  assert.equal(t(6.9, 3), "uncertain"); // 0.697
  assert.equal(t(3, 7), "uncertain"); // exactly 0.30 is not below 0.30
  assert.equal(t(2.9, 7), "ignored");
  assert.equal(t(10, 10), "uncertain"); // TC-19: mass is plenty, mean is not
  assert.equal(t(9, 0.5), "uncertain"); // mean 0.95 but mass 9.5 < MIN_EVIDENCE
  assert.equal(MIN_EVIDENCE, 10);
  assert.equal(trustOf("unlisted", []).trust, "unproven");
  assert.equal(trustOf("s", [{ source: "s", alpha: 0, beta: 5 }]).trust, "unproven");
});

test("trust: source names match without regard to case or padding, and only exactly", () => {
  const rel = [{ source: "Reuters.com", alpha: 45, beta: 1 }];
  assert.equal(trustOf("  reuters.com ", rel).trust, "trusted");
  assert.equal(trustOf("reuters.com.evil.co", rel).trust, "unproven");
  assert.equal(trustOf("reuter.com", rel).trust, "unproven");
  assert.equal(trustOf("reuters", rel).trust, "unproven", "a prefix of a trusted name is not that name");
  assert.equal(trustOf("com", rel).trust, "unproven");
});

// --- held-out shocks: different words from the exam -------------------------------------------

test("held-out genuine shocks are refused", () => {
  const cases: [string, Parameters<typeof one>[0], string][] = [
    ["unscheduled hike", { title: "Fed holds unscheduled meeting, raises rates 75 basis points" }, "REJECT macro-warning"],
    ["stablecoin ban", { symbol: "ETHUSDT", title: "Regulators ban stablecoin trading nationwide" }, "REJECT macro-warning"],
    ["global halt", { symbol: "AAPL", title: "Global stock exchanges suspend trading amid systemic crisis" }, "REJECT macro-warning"],
    ["war", { symbol: "AAPL", title: "Government declares war, markets plunge" }, "REJECT macro-warning"],
    ["crypto venue failure", { symbol: "ETHUSDT", title: "Major crypto exchange hacked, withdrawals suspended" }, "REJECT macro-warning"],
    ["enforcement", { symbol: "AAPL", title: "Prosecutors raid company headquarters in fraud probe" }, "REJECT sentiment-conflict"],
    ["going concern", { symbol: "AAPL", title: "Company files for bankruptcy after delisting notice" }, "REJECT sentiment-conflict"],
    ["short is vetoed by a macro shock too", { direction: "SHORT", title: "Regulators ban crypto derivatives nationwide" }, "REJECT macro-warning"],
  ];
  for (const [name, over, want] of cases) assert.equal(tag(one(over)), want, name);
});

// --- held-out decoys: the trigger words, used for something else --------------------------------

test("held-out decoys that reuse the trigger words are not refused", () => {
  const cases: [string, Parameters<typeof one>[0]][] = [
    ["ban on smoking", { symbol: "AAPL", title: "Government bans smoking in federal buildings" }],
    ["production halt", { symbol: "AAPL", title: "Company halts production line for scheduled maintenance" }],
    ["rumoured hike", { title: "Fed may announce emergency rate hike, sources say" }],
    ["denied ban", { title: "Regulator denies plans to ban crypto trading nationwide" }],
    ["trading resumes", { symbol: "AAPL", title: "Exchange resumes trading after global halt" }],
    ["ban lifted", { title: "Nationwide ban on crypto trading lifted by regulators" }],
    ["unrelated emergency", { symbol: "AAPL", title: "Emergency room wait times rise as flu season begins" }],
    ["fraud elsewhere in a sector headline", { symbol: "AAPL", title: "Auditor resigns citing accounting fraud", scope: "sector" }],
    ["a crypto shock on a stock", { symbol: "AAPL", title: "Major crypto exchange hacked, withdrawals suspended" }],
    ["good news", { title: "Record institutional inflows and expansion announced" }],
  ];
  for (const [name, over] of cases) assert.equal(one(over).verdict, "EXECUTE", name);
});

test("corporate bad news supports a short, so it does not conflict with one", () => {
  const title = "Auditor resigns citing severe accounting fraud";
  assert.equal(one({ symbol: "AAPL", direction: "LONG", title }).reason, "sentiment-conflict");
  assert.equal(one({ symbol: "AAPL", direction: "SHORT", title }).verdict, "EXECUTE");
});

test("a trusted source with too little history, an uncertain one and an unlisted one cannot veto alone", () => {
  const title = "SEC announces immediate ban on crypto derivatives trading";
  assert.equal(one({ title, reliability: [{ source: "wire", alpha: 9, beta: 0.5 }] }).verdict, "EXECUTE");
  assert.equal(one({ title, reliability: [{ source: "wire", alpha: 10, beta: 10 }] }).verdict, "EXECUTE");
  assert.equal(one({ title, reliability: [] }).verdict, "EXECUTE");
  assert.equal(one({ title }).verdict, "REJECT");
});

test("the 24-hour window: a shock just inside counts, just outside does not", () => {
  const title = "SEC announces immediate ban on crypto derivatives trading";
  assert.equal(one({ title, minutes: 24 * 60 - 1 }).verdict, "REJECT");
  assert.equal(one({ title, minutes: 24 * 60 + 1 }).verdict, "EXECUTE");
});

// --- properties --------------------------------------------------------------------------------

test("input order does not matter, and a trusted shock is not buried by newer routine headlines", () => {
  const shock: GateNews = { title: "SEC announces immediate ban on crypto derivatives trading", publishedAt: ago(40), source: "wire" };
  const noise: GateNews[] = Array.from({ length: 12 }, (_, i) => ({ title: `Routine update ${i}`, publishedAt: ago(i + 1), source: "wire" }));
  const input = (news: GateNews[]): GateInput => ({
    symbol: "BTCUSDT", direction: "LONG", price: null, stop: null, rewardRisk: null, news, reliability: [{ ...TRUSTED }],
  });
  const a = evaluateLocal(input([shock, ...noise]), NOW);
  const b = evaluateLocal(input([...noise].reverse().concat(shock)), NOW);
  assert.deepEqual(a, b);
  // 13 headlines and the shock is 40 minutes old, older than all twelve routine ones: the model engine's
  // cap of eight would never have shown it. This engine has no prompt to bound, so it reads them all.
  assert.deepEqual([a.verdict, a.reason], ["REJECT", "macro-warning"]);
});

test("the result carries only a verdict, a reason, a sentence and flags: nothing numeric about the trade", () => {
  const r = one({ title: "SEC announces immediate ban on crypto derivatives trading" });
  assert.deepEqual(Object.keys(r).sort(), ["fallback", "rationale", "reason", "valid", "verdict"]);
  assert.ok(!/stop|target|entry|reward/i.test(r.rationale));
  assert.ok(!/[\u0000-\u001f]/.test(r.rationale));
});

test("garbage in is an EXECUTE out, and never a throw", () => {
  const bad = [
    { symbol: "X", direction: "WAIT" },
    { symbol: "X", direction: "LONG", news: null, reliability: null },
    { symbol: "X", direction: "LONG", news: [{ title: null, publishedAt: "nope", source: undefined }], reliability: [null] },
    {},
  ];
  for (const b of bad) {
    const r = evaluateLocal(b as unknown as GateInput, NOW);
    assert.equal(r.verdict, "EXECUTE");
    assert.equal(r.reason, null);
  }
});

test("a systemic warning outranks a company-level conflict, whichever is newer", () => {
  for (const [macroAge, corpAge] of [[90, 10], [10, 90]]) {
    const macro: GateNews = { title: "Regulators ban crypto derivatives nationwide", publishedAt: ago(macroAge), source: "wire" };
    const corp: GateNews = { title: "Auditor resigns citing accounting fraud", publishedAt: ago(corpAge), source: "wire" };
    for (const news of [[macro, corp], [corp, macro]]) {
      const r = evaluateLocal(
        { symbol: "BTCUSDT", direction: "LONG", price: null, stop: null, rewardRisk: null, news, reliability: [{ ...TRUSTED }] },
        NOW,
      );
      assert.equal(r.reason, "macro-warning", `macro ${macroAge}m old, conflict ${corpAge}m old`);
    }
  }
});

test("an input that throws mid-read is an unusable EXECUTE, flagged, not an exception", () => {
  const hostile = {
    symbol: "BTCUSDT", direction: "LONG", price: null, stop: null, rewardRisk: null, reliability: [{ ...TRUSTED }],
    news: [{ get title(): string { throw new Error("boom"); }, publishedAt: ago(5), source: "wire" }],
  };
  const r = evaluateLocal(hostile as unknown as GateInput, NOW);
  assert.deepEqual([r.verdict, r.reason, r.valid], ["EXECUTE", null, false]);
  assert.ok(r.fallback);
});

test("asset class: the stored type wins, and a symbol is only read when none is stored", () => {
  assert.equal(assetClassOf("AAPL", "crypto"), "crypto");
  assert.equal(assetClassOf("BTC-USD"), "crypto");
  assert.equal(assetClassOf("ETHUSDT"), "crypto");
  assert.equal(assetClassOf("EURUSD=X"), "forex");
  assert.equal(assetClassOf("GC=F"), "commodity");
  assert.equal(assetClassOf("ENGRO.KA"), "stock");
  assert.equal(normalise("<b>Fed</b>   RAISES\trates!"), "b fed b raises rates");
});

test("KNOWN LIMIT: a shock phrased outside the table passes, and the test says so rather than hiding it", () => {
  // Paraphrases the table does not list. Each is a real shock and each passes, because this engine
  // reads words and not meaning. That is the safe direction (the rule table's verdict stands) and it
  // is the reason the model engine exists as an option. If one of these starts being refused, the
  // table grew; move it to the shocks above.
  const missed = [
    "Treasury secretary resigns as bond market seizes up",
    "Largest US lender wiped out overnight as depositors flee",
    "Oil facilities hit in overnight drone attack, supply cut by half",
  ];
  for (const title of missed) assert.equal(one({ symbol: "AAPL", title }).verdict, "EXECUTE", title);
});
