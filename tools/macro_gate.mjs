// The macro gatekeeper job: ask a model, once a night, whether recent headlines describe a shock
// big enough to refuse a LONG or SHORT the rule table has already produced, and store the answer.
//
//   node tools/macro_gate.mjs [--dry-run] [--print-prompt]
//
// **Two engines, one default.** `MACRO_GATE_ENGINE=local` (the default) decides with the fixed word
// table in `lib/macroGateLocal.ts`: free, offline, deterministic, no key. `MACRO_GATE_ENGINE=model`
// asks a language model instead (paid, not deterministic, needs `ANTHROPIC_API_KEY`). Either way the
// answer is stored and the rule table reads the stored answer; nothing here changes how a verdict is
// computed on the site.
//
// **Off unless asked.** It does nothing without `MACRO_GATE=on`, and prints one line saying so. With
// the gate off the table stays empty and every verdict on the site is exactly what the rule table
// decides alone. The model engine additionally needs its key; the local one needs nothing.
//
// **Veto only.** The local engine returns a verdict, one of two reasons and a sentence, and has no way
// to touch a price. The model's reply schema has four fields and none of them is a number; the reply is
// then re-validated by `lib/macroGate.ts`, which rejects anything extra. The only thing a stored
// answer can do downstream is turn a LONG or SHORT into a WAIT (`macro-veto` in `lib/decision.ts`).
//
// **Fails open.** Any API error, refusal, truncation or malformed reply is stored as an invalid
// EXECUTE and changes nothing. This job exits 0 whatever happens: a lane that failed because a third
// party was down would turn an outage over there into a red cron here.
//
// **Stored, never read at request time.** The model is not deterministic, so the website never
// consults it; it reads the answer this job stored, like any other input to `decide`.
//
// Credentials: `ANTHROPIC_API_KEY` and `DATABASE_URL` come from the environment and are never
// printed. Only counts, symbols and verdicts are.

import process from "node:process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { config as loadEnv } from "dotenv";
import pg from "pg";
import Anthropic from "@anthropic-ai/sdk";

import { MACRO_WINDOW_HOURS, evaluate, REFUSAL_REASONS, selectNews, shouldEvaluate } from "../lib/macroGate.ts";
import { LOCAL_ENGINE, evaluateLocal } from "../lib/macroGateLocal.ts";
import { todayISO } from "../lib/decisionInput.ts";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
loadEnv({ path: path.join(ROOT, ".env"), quiet: true });

const DRY_RUN = process.argv.includes("--dry-run");
const PRINT_PROMPT = process.argv.includes("--print-prompt");

/// Which engine decides. Anything but "model" is the local one, so a typo costs nothing and calls nothing.
const ENGINE = process.env.MACRO_GATE_ENGINE === "model" ? "model" : "local";
/// The model engine's default is the most capable model; `MACRO_GATE_MODEL=claude-haiku-5-5` is the cheap switch.
const MODEL = process.env.MACRO_GATE_MODEL || "claude-opus-5-5";
/// Thinking is always on for this model, so `max_tokens` has to cover it as well as the reply.
const MAX_TOKENS = 4096;
const EFFORT = process.env.MACRO_GATE_EFFORT || "low";
/// A ceiling on names asked about in one run. Only names with a direction and a fresh headline are
/// candidates, so this is a cost guard and not a quality one.
const MAX_CANDIDATES = Math.max(1, Number(process.env.MACRO_GATE_MAX) || 60);
const CONCURRENCY = 4;

/// The reply schema, written out rather than generated. It has four fields and none of them is a
/// number, which is the whole safety property: the model has nowhere to put a price, a stop or a
/// confidence. (The SDK's zod helper was tried first and, at the pinned zod, rendered the enums as
/// description text instead of `enum` constraints -- so the constraint the model sees is the one
/// written here.) `parseGateReply` re-validates every reply regardless of what the API enforced.
export const REPLY_SCHEMA = {
  type: "object",
  properties: {
    symbol: { type: "string" },
    verdict: { type: "string", enum: ["EXECUTE", "REJECT"] },
    refusal_reason: { anyOf: [{ type: "string", enum: [...REFUSAL_REASONS] }, { type: "null" }] },
    rationale: { type: "string" },
  },
  required: ["symbol", "verdict", "refusal_reason", "rationale"],
  additionalProperties: false,
};

function say(line) {
  console.log(`macro gate: ${line}`);
}

export function makeCall(client) {
  return async ({ system, user }) => {
    const res = await client.messages.create({
      model: MODEL,
      max_tokens: MAX_TOKENS,
      system,
      messages: [{ role: "user", content: user }],
      output_config: { effort: EFFORT, format: { type: "json_schema", schema: REPLY_SCHEMA } },
    });
    if (res.stop_reason === "refusal") return { kind: "refusal" };
    if (res.stop_reason === "max_tokens") return { kind: "truncated" };
    const block = res.content.find((b) => b.type === "text");
    return block ? { kind: "text", text: block.text } : { kind: "truncated" };
  };
}

async function candidates(db, today) {
  return (
    await db.query(
      `SELECT d."assetId", a.symbol, a."assetType"::text AS "assetType", a."industryId", d.action, d."baseClose", d.invalidation, d."rewardRisk"
         FROM "DecisionLog" d JOIN "Asset" a ON a.id = d."assetId"
        WHERE d."periodEnd" = $1::date
          AND d.action IN ('LONG', 'SHORT')
          AND NOT EXISTS (SELECT 1 FROM "MacroGate" m
                           WHERE m."assetId" = d."assetId" AND m."periodEnd" = d."periodEnd" AND m.valid)
        ORDER BY a.symbol ASC`,
      [today],
    )
  ).rows;
}

async function headlines(db, rows) {
  const assetIds = rows.map((r) => r.assetId);
  const industryIds = [...new Set(rows.map((r) => r.industryId).filter(Boolean))];
  const [own, sector] = await Promise.all([
    db.query(
      `SELECT "assetId" AS key, title, publisher, source, "publishedAt" FROM "News"
        WHERE "assetId" = ANY($1) AND "publishedAt" >= now() - interval '48 hours'
        ORDER BY "publishedAt" DESC`,
      [assetIds],
    ),
    db.query(
      `SELECT "industryId" AS key, title, publisher, source, "publishedAt" FROM "News"
        WHERE "industryId" = ANY($1) AND "assetId" IS NULL AND "publishedAt" >= now() - interval '48 hours'
        ORDER BY "publishedAt" DESC`,
      [industryIds],
    ),
  ]);
  const byKey = (rowsIn, scope) => {
    const m = new Map();
    for (const r of rowsIn) {
      if (!m.has(r.key)) m.set(r.key, []);
      m.get(r.key).push({
        scope,
        title: r.publisher && r.publisher !== r.source ? `${r.title} (via ${r.publisher})` : r.title,
        publishedAt: r.publishedAt,
        source: r.source,
      });
    }
    return m;
  };
  return { own: byKey(own.rows, "asset"), sector: byKey(sector.rows, "sector") };
}

async function reliabilityOf(db, sources) {
  if (!sources.length) return [];
  const { rows } = await db.query(
    `SELECT DISTINCT ON (source) source, alpha, beta FROM "SourceReliability"
      WHERE source = ANY($1) ORDER BY source, observations DESC`,
    [sources],
  );
  return rows.map((r) => ({ source: r.source, alpha: Number(r.alpha), beta: Number(r.beta) }));
}

async function store(db, row, today, result, engineLabel) {
  await db.query(
    `INSERT INTO "MacroGate" ("assetId", "periodEnd", direction, verdict, reason, rationale, valid, fallback, model, "newsCount")
     VALUES ($1, $2::date, $3, $4, $5, $6, $7, $8, $9, $10)
     ON CONFLICT ("assetId", "periodEnd") DO UPDATE
        SET direction = EXCLUDED.direction, verdict = EXCLUDED.verdict, reason = EXCLUDED.reason,
            rationale = EXCLUDED.rationale, valid = EXCLUDED.valid, fallback = EXCLUDED.fallback,
            model = EXCLUDED.model, "newsCount" = EXCLUDED."newsCount", "createdAt" = now()
      WHERE "MacroGate".valid = false`,
    [
      row.assetId, today, row.direction, result.verdict, result.reason, result.rationale,
      result.valid, result.fallback, engineLabel, row.newsCount,
    ],
  );
}

async function main() {
  if (process.env.MACRO_GATE !== "on") return say("off (set MACRO_GATE=on to enable). Nothing asked, nothing stored.");
  if (ENGINE === "model" && !process.env.ANTHROPIC_API_KEY && !PRINT_PROMPT) {
    return say("off (the model engine needs ANTHROPIC_API_KEY; the default local engine needs none). Nothing asked, nothing stored.");
  }
  if (!process.env.DATABASE_URL) return say("no DATABASE_URL. Nothing asked, nothing stored.");

  const today = todayISO();
  const now = new Date();
  const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL, max: 3 });
  try {
    const present = await pool.query(`SELECT to_regclass('public."MacroGate"') AS t`);
    if (!present.rows[0].t) return say("the MacroGate table does not exist here yet (migration pending). Nothing stored.");

    const all = await candidates(pool, today);
    const feed = await headlines(pool, all);
    const withNews = [];
    for (const c of all) {
      const news = [...(feed.own.get(c.assetId) ?? []), ...(feed.sector.get(c.industryId) ?? [])];
      // Every headline in the window. The model's prompt is capped by `buildUserPrompt`; the local engine
      // reads them all, so a shock is not hidden behind newer routine items.
      const recent = selectNews(news, now, MACRO_WINDOW_HOURS, 500);
      if (shouldEvaluate(c.action, recent)) withNews.push({ ...c, news: recent });
    }
    const batch = withNews.slice(0, MAX_CANDIDATES);
    say(`${all.length} directional names today, ${withNews.length} with fresh headlines, asking about ${batch.length}.`);
    if (!batch.length) return;

    const sources = [...new Set(batch.flatMap((b) => b.news.map((n) => n.source)))];
    const reliability = await reliabilityOf(pool, sources);

    const inputOf = (b) => ({
      symbol: b.symbol,
      assetClass: b.assetType,
      direction: b.action,
      price: b.baseClose,
      stop: b.invalidation,
      rewardRisk: b.rewardRisk,
      news: b.news,
      reliability,
    });

    if (PRINT_PROMPT && ENGINE === "model") {
      const { buildUserPrompt } = await import("../lib/macroGate.ts");
      console.log(buildUserPrompt(inputOf(batch[0]), now));
      return;
    }
    if (DRY_RUN) return say("dry run: no model call, nothing stored.");

    const label = ENGINE === "model" ? MODEL : LOCAL_ENGINE;
    const decideOne = ENGINE === "model"
      ? ((call) => (input) => evaluate(input, call, now))(makeCall(new Anthropic({ timeout: 60_000, maxRetries: 2 })))
      : async (input) => evaluateLocal(input, now);
    const counts = { REJECT: 0, EXECUTE: 0, invalid: 0, stored: 0, storeFailed: 0 };
    let next = 0;
    const worker = async () => {
      for (;;) {
        const i = next++;
        if (i >= batch.length) return;
        const b = batch[i];
        const result = await decideOne(inputOf(b));
        counts[result.valid ? result.verdict : "invalid"]++;
        if (result.valid && result.verdict === "REJECT") say(`${b.symbol} ${b.action} refused: ${result.reason}`);
        try {
          await store(pool, { ...b, direction: b.action, newsCount: b.news.length }, today, result, label);
          counts.stored++;
        } catch (error) {
          counts.storeFailed++;
          say(`could not store ${b.symbol} (${error instanceof Error ? error.name : "error"})`);
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, batch.length) }, worker));
    say(
      `${counts.REJECT} refused, ${counts.EXECUTE} let through, ${counts.invalid} unusable (fail-open), ` +
        `${counts.stored} stored, ${counts.storeFailed} not stored. engine ${label}.`,
    );
  } finally {
    await pool.end().catch(() => {});
  }
}

// Only when run directly: `tools/macro_gate_exam.mjs` imports `makeCall` from here so the exam asks the
// model exactly the way the nightly job does, and importing must not start a run.
const direct = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (direct) main().catch((error) => {
  // Name only: an SDK or driver error can carry request detail, and this lane must never fail.
  say(`stopped early (${error instanceof Error ? error.name : "error"}). Nothing here can change a verdict.`);
});
