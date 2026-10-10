// Write one decision per asset per day, using the real rules.
//
// The rules live in TypeScript because the website computes them at read time
// (`lib/decision.ts`, with `lib/decisionInput.ts` as the only place allowed to turn stored rows
// into the rule table's input shape). This job needs the same verdicts written down so hit rates
// can later be measured and published — and reimplementing the gates in Python would create a
// second vocabulary for one idea, which is the fault rule 36 names. So this is a Node script that
// imports the real module: Node 24 runs TypeScript directly, so `import ... from "../lib/decision.ts"`
// is the actual rule table and not a copy of it.
//
// What it does, in order:
//   1. eleven bulk SELECTs — nine for the inputs, two to find and measure the matured rows — and
//      never one query per asset. 160 names today, maybe 1,000 later; a per-asset loop would be
//      ~1,000 round trips against a free-tier Neon endpoint, which is not a slow job but a job
//      that exhausts the pool and fails worse the more assets it covers. The query count here
//      does not change when the universe grows: only the number of rows each query returns does.
//   2. `bundleFromRow` -> `toDecisionInput` -> `decide` per asset, with ONE `today` for the whole
//      run, passed in. The rules take `today` as an input precisely so a run started at 23:59
//      cannot decide half its assets on one date and half on the next.
//   3. an idempotent upsert of one `DecisionLog` row per asset for today's `periodEnd`.
//   4. maturation of PAST rows whose +1, +5 or +20 **session** window has filled.
//   5. a summary table, printed and written to `$GITHUB_STEP_SUMMARY` when set — the raw Action
//      log needs a GitHub sign-in to read and the job summary does not.
//
// Usage:
//   node tools/decide.mjs --dry-run     compute and print, write nothing
//   node tools/decide.mjs               compute and write
//
// Exit codes: non-zero when nothing at all could be written (so a workflow goes red); 0 when some
// rows were written and others skipped, which is a partial success and says so in the summary.

import process from "node:process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "node:fs";

import { config as loadEnv } from "dotenv";

import { confirmingLegs } from "../lib/decision.ts";
import { writerPool } from "./writer.mjs";
import { decideCall } from "../lib/resolve.ts";
import { bundleFromRow, toDecisionInput, todayISO } from "../lib/decisionInput.ts";
import { pickTarget, targetForCall } from "../lib/target.ts";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// DATABASE_URL from the environment, or the project's own `.env`, exactly as the jobs and the
// other scripts in this directory read it. Never a credential path outside the repo.
loadEnv({ path: path.join(ROOT, ".env"), quiet: true });

const DRY_RUN = process.argv.includes("--dry-run");

/// How many rows go into one INSERT, and how many statements go into one transaction.
///
/// 50 assets per statement, one COMMIT per statement. Two separate reasons, both from failures
/// this repo has already had:
///
///  - The transaction must not span the whole run. `jobs/events.py` once held a single
///    transaction open across ~100,000 round trips and Neon's pooler closed the connection
///    underneath it, losing every row including the ones that had succeeded hours earlier. A
///    batch that commits is a batch that is safe once it is written.
///  - 50 rows x 18 columns is 900 bind parameters, comfortably inside Postgres's 65,535 limit
///    with room for the column list to grow. 160 assets is then four statements rather than 160.
const BATCH_ROWS = 50;

/// The forward horizons measured, in **stored trading sessions** for that asset.
const HORIZONS = [1, 5, 20];

/// How long a session window is allowed to take in calendar days before a window that still has
/// no close is called dead rather than pending.
///
/// Sessions are what is measured, but "has this window had its chance" can only be asked in
/// calendar time, because an asset whose feed died stops producing sessions altogether and would
/// otherwise sit at `open` forever. A trading week is five sessions in seven days; the +2 week
/// grace absorbs holidays, a late feed and a market closed for a stretch. So +1 is declared dead
/// after 17 days, +5 after 21, +20 after 42.
function calendarBudget(sessions) {
  return Math.ceil((sessions * 7) / 5) + 14;
}

// --- small helpers ------------------------------------------------------------------------------

/// `@db.Date` columns come back from `pg` as a local-midnight `Date`; the rules and the unique key
/// both speak ISO days. Formatting from the local parts rather than `toISOString()` is deliberate:
/// a local-midnight date east of UTC shifts back a day under `toISOString()`.
function dayOf(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value.slice(0, 10);
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, "0");
  const d = String(value.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function daysBetween(fromISO, toISO) {
  const a = Date.parse(`${fromISO}T00:00:00Z`);
  const b = Date.parse(`${toISO}T00:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b)) return Number.NaN;
  return Math.round((b - a) / 86_400_000);
}

function firstPerKey(rows, key) {
  const out = new Map();
  for (const row of rows) if (!out.has(key(row))) out.set(key(row), row);
  return out;
}

/// Every row per key, in the order they arrived. The sibling of `firstPerKey`, for the one table
/// where keeping all of them is the point: a setup's three target methods are three answers and
/// reducing them here would be this job choosing between them before the rules do.
function groupPerKey(rows, key) {
  const out = new Map();
  for (const row of rows) {
    const k = key(row);
    const got = out.get(k);
    if (got) got.push(row);
    else out.set(k, [row]);
  }
  return out;
}

async function tableExists(db, name) {
  const { rows } = await db.query(
    "SELECT to_regclass($1) IS NOT NULL AS present",
    [`public."${name}"`],
  );
  return rows[0].present === true;
}

// --- the bulk reads -----------------------------------------------------------------------------

/// Everything the rules need for every asset, in nine SELECTs.
///
/// Nine, not eight: `AssetFactor` joined this list so the volume-confirmation rule and the
/// peer-relative gate have something to read. Before it was here both were unreachable — not
/// wrong, unreachable, because `volumeRatio` and `relStrength` arrived undefined on every row and
/// `volumeConfirms` reads an undefined ratio as "not published". The measurable symptom was 159
/// Low and 1 Medium out of 160 verdicts: confidence counts confirmations, and with volume never
/// available only a second agreeing timeframe could ever count.
///
/// Each per-asset table is read with `DISTINCT ON`, so Postgres picks the newest row per asset and
/// the network carries 160 rows instead of every row ever stored. The ORDER BY of each one is the
/// rule for which row wins, and matches `getDecisionRows()` in `lib/queries.ts` on purpose: the job
/// and the website must not disagree about which stored row is "the current reading".
///
/// `db` is the pool rather than one connection: nine queries issued in parallel on a single
/// client are serialised by `pg` anyway (and warned about), while a small pool really overlaps them.
async function readInputs(db, today) {
  const [assets, prices, setups, targets, analogs, signals, investigations, factors, events, coverage] =
    await Promise.all([
      db.query(
        // Active names only (jobs/pool.py): an asset below its market's liquidity floor is out of the
        // pool and gets no call, here and on the lists alike.
        `SELECT a.id, a.symbol, a."assetType"::text AS "assetType", i.market
           FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId"
          WHERE a.active
          ORDER BY a.symbol ASC`,
      ),
      db.query(
        `SELECT DISTINCT ON ("assetId") "assetId", date, close
           FROM "PriceSnapshot" ORDER BY "assetId", date DESC`,
      ),
      // Newest row per (asset, horizon). intraday is deliberately absent: the lists and this log
      // read the same two horizons the home page does, because a verdict that re-decided itself
      // through the session would be a different verdict on every run.
      db.query(
        // `conditions` rides along because the trend verdict inside it is the only record of
        // which way a withheld direction pointed, and lib/queries.ts selects it for the same
        // reason. Two readers of one table must not each decide what a `wait` row knows.
        `SELECT DISTINCT ON ("assetId", horizon)
                id, "assetId", horizon, state, "entryLevel", "invalidateLevel", conditions
           FROM "AssetSetup" WHERE horizon IN ('swing', 'longer')
          ORDER BY "assetId", horizon, "periodEnd" DESC`,
      ),
      // The measured target ranges, for the setups the query above just picked.
      //
      // `jobs/horizons.py` writes up to three rows per setup, one per method, and `rewardRisk`
      // is the figure gate 5's bypass and gate 8's promotion both read. Without this the rules
      // see no target at all, which is not the same as seeing a poor one: an unmeasured reward
      // cannot carry a disagreement, so every bypass would be dead and every promotion would
      // have to rest on volume alone -- the exact shape of unreachable rule the `AssetFactor`
      // read above was added to fix.
      //
      // The subselect repeats the DISTINCT ON rather than filtering on ids collected in JS,
      // because the two must agree about which setup is current and a list of ids marshalled
      // through the client would be a second definition of that. One extra round trip, bounded
      // by assets x 2 horizons x 3 methods.
      db.query(
        `SELECT t."setupId", t.method, t.low, t.high, t."rewardRisk"
           FROM "SetupTarget" t
           JOIN (SELECT DISTINCT ON ("assetId", horizon) id
                   FROM "AssetSetup" WHERE horizon IN ('swing', 'longer')
                  ORDER BY "assetId", horizon, "periodEnd" DESC) s ON s.id = t."setupId"
          ORDER BY t.method ASC`,
      ),
      // Newest day, and within that day the shortest horizon, so the band quoted answers "what
      // now" rather than letting a 60-day band win on some assets and a 5-day band on others.
      // `medianPct` and positive are selected from the row the band already came from, never from
      // a separate read. `analogConfirms` needs both halves — a majority of matched days moving the
      // right way AND a middle outcome of the right sign — because six of ten rising with a negative
      // median is a set where the four falls were larger, and calling that confirmation would be
      // counting the days and ignoring their size.
      db.query(
        `SELECT DISTINCT ON ("assetId")
                "assetId", id, "horizonDays", "minPct", "maxPct", matches,
                "medianPct", positive
           FROM "AssetAnalog"
          -- The 5-day row first, then the shortest. pickAnalog in lib/decisionInput.ts prefers
          -- horizon 5 because it is the one a swing read is answerable on, and this used to take
          -- the shortest unconditionally — so the nightly log and the asset page could quote
          -- different rows for one asset, and WTL's 1-day median of exactly 0 would confirm in
          -- one place and not the other. Three readers of this table, one rule.
          ORDER BY "assetId", "periodEnd" DESC, ("horizonDays" = 5) DESC, "horizonDays" ASC`,
      ),
      // HumanSignal also describes products, which have no place in a list of assets.
      db.query(
        // `tone` and `catalyst` ride along with the story count, because the rule table reads
        // all three and `lib/queries.ts` selects all three for the same table. An analog set no
        // longer confirms a direction the published coverage points away from, and a withheld
        // trend is not carried into one -- so a job that fetched only the count would write a
        // different verdict from the page for any name whose coverage disagrees with it.
        `SELECT DISTINCT ON ("assetId") "assetId", "recentStories", tone::text AS tone, catalyst
           FROM "HumanSignal" WHERE "assetId" IS NOT NULL
          ORDER BY "assetId", "periodEnd" DESC`,
      ),
      db.query(
        `SELECT DISTINCT ON ("assetId") "assetId", "robustZ", trigger
           FROM "Investigation" ORDER BY "assetId", "periodEnd" DESC`,
      ),
      // The newest factor row per asset. `ORDER BY "assetId", "periodEnd" DESC` is the same rule
      // `getDecisionRows()` applies to this table in `lib/queries.ts` — deliberately, so that on a
      // day the factor job wrote twice the nightly log and the home page cannot disagree about which
      // reading is current. Nulls are carried through as nulls: `volumeRatio` is null where the
      // venue publishes no volume and `relStrength` is null where `jobs/factors.py` found too few
      // peers to take a median over, and both are absences of a measurement rather than a flat one.
      db.query(
        `SELECT DISTINCT ON ("assetId") "assetId", "volumeRatio", "relStrength", "r20", "atr14",
                "entryTrigger", "triggerDirection"
           FROM "AssetFactor" ORDER BY "assetId", "periodEnd" DESC`,
      ),
      // The *soonest* future scheduled event per asset. A diary has one order and it is not
      // "newest written".
      db.query(
        `SELECT DISTINCT ON (l."assetId") l."assetId", e.date
           FROM "EventLink" l JOIN "Event" e ON e.id = l."eventId"
          WHERE l."assetId" IS NOT NULL AND e.scheduled = true AND e.date >= $1::date
          ORDER BY l."assetId", e.date ASC`,
        [today],
      ),
      // One site-wide read, shared by every asset. Per-asset it would be 160 copies of one answer.
      db.query(
        `SELECT DISTINCT ON (source) source, status
           FROM "Coverage" ORDER BY source, "computedAt" DESC`,
      ),
    ]);

  // The macro gatekeeper's stored refusals, read apart from the nine above and **fail-open**: a
  // database the migration has not reached has no such table, and a decision run that died on that
  // would take the whole log down for the want of an optional layer. Any failure here is "no vetoes",
  // which decides every name exactly as the rule table alone would. The newest valid answer per name
  // wins, so a later EXECUTE supersedes an earlier REJECT; the rule table ages what it is given.
  let macro = [];
  try {
    macro = (
      await db.query(
        `SELECT DISTINCT ON ("assetId") "assetId", verdict, reason, "periodEnd"
           FROM "MacroGate"
          WHERE valid AND "periodEnd" >= ($1::date - 4)
          ORDER BY "assetId", "periodEnd" DESC, "createdAt" DESC`,
        [today],
      )
    ).rows.filter((r) => r.verdict === "REJECT");
  } catch {
    macro = [];
  }

  // The most recent directional verdict logged before today, within a week: the call a flip has to be
  // confirmed against. The same rule and window as `getPriorDirections` in lib/queries.ts, so the log
  // and the page judge a reversal against the same stored past. Fail-open like the macro read above.
  let prior = [];
  try {
    prior = (
      await db.query(
        `SELECT DISTINCT ON ("assetId") "assetId", action, "periodEnd"
           FROM "DecisionLog"
          WHERE action IN ('LONG', 'SHORT') AND gate NOT LIKE 'forced-%'
            AND "periodEnd" < $1::date AND "periodEnd" >= ($1::date - 7)
          ORDER BY "assetId", "periodEnd" DESC`,
        [today],
      )
    ).rows;
  } catch {
    prior = [];
  }

  // The current run of directional calls before today, whichever gate made them: the same query as
  // `getLastRuns` in lib/queries.ts, so the log and the page hold the same call and apply the same
  // whipsaw guard (lib/resolve.ts). A stop-crossed WAIT is read as ENDED there too: the call stopped.
  // Fail-open like the reads above.
  let lastRun = [];
  try {
    lastRun = (
      await db.query(
        `SELECT DISTINCT ON ("assetId") "assetId", action, "periodEnd" AS since, prev
           FROM (SELECT "assetId", action, "periodEnd",
                        lag(action) OVER (PARTITION BY "assetId" ORDER BY "periodEnd") AS prev
                   FROM (SELECT "assetId", "periodEnd",
                                CASE WHEN action IN ('LONG', 'SHORT') THEN action ELSE 'ENDED' END AS action
                           FROM "DecisionLog"
                          WHERE (action IN ('LONG', 'SHORT') OR (action = 'WAIT' AND gate = 'stop-crossed'))
                            AND "periodEnd" < $1::date AND "periodEnd" >= ($1::date - 30)) d) t
          WHERE prev IS DISTINCT FROM action
          ORDER BY "assetId", "periodEnd" DESC`,
        [today],
      )
    ).rows;
  } catch {
    lastRun = [];
  }

  return {
    assets: assets.rows,
    priceByAsset: firstPerKey(prices.rows, (r) => r.assetId),
    setupByKey: firstPerKey(setups.rows, (r) => `${r.assetId}|${r.horizon}`),
    // Every method's row, grouped by the setup it belongs to. Not reduced to one here: rule 24
    // forbids averaging the three, and which one is preferred is `lib/target.ts`'s decision, made
    // once `pickSetup` has chosen which horizon decided.
    targetsBySetup: groupPerKey(targets.rows, (r) => r.setupId),
    analogByAsset: firstPerKey(analogs.rows, (r) => r.assetId),
    signalByAsset: firstPerKey(signals.rows, (r) => r.assetId),
    investigationByAsset: firstPerKey(investigations.rows, (r) => r.assetId),
    factorByAsset: firstPerKey(factors.rows, (r) => r.assetId),
    eventByAsset: firstPerKey(events.rows, (r) => r.assetId),
    macroByAsset: firstPerKey(macro, (r) => r.assetId),
    priorByAsset: firstPerKey(prior, (r) => r.assetId),
    lastRunByAsset: firstPerKey(lastRun, (r) => r.assetId),
    sourceHealth: coverage.rows.map((r) => ({ source: r.source, status: r.status })),
  };
}

/// One `QueryRow` per asset, in the shape `lib/decisionInput.ts` declares.
///
/// Field names are not re-invented here and nothing is mapped by hand past this point:
/// `bundleFromRow` owns the translation into a bundle and `toDecisionInput` owns the translation
/// into the rules' input, so a column that moves is fixed in that one file and this job follows.
function rowsForDecisions(input) {
  const setupOf = (assetId, horizon) => {
    const row = input.setupByKey.get(`${assetId}|${horizon}`);
    if (!row) return null;
    return {
      state: row.state,
      entryLevel: row.entryLevel,
      invalidateLevel: row.invalidateLevel,
      conditions: row.conditions,
      // Declared on `QueryRow.swing`/`.longer` in lib/decisionInput.ts and carried through
      // `bundleFromRow` with the rest of the row. Empty rather than absent when the job wrote
      // none: `preferredTarget` answers null for both, and an empty list says "asked and there
      // were none" where undefined would say "this reader does not fetch targets".
      targets: input.targetsBySetup.get(row.id) ?? [],
    };
  };

  // Every asset gets a row, including one with nothing stored against it: an asset missing from
  // the log would later read as a judgement about that name rather than as a job that has not run.
  return input.assets.map((asset) => {
    const price = input.priceByAsset.get(asset.id);
    const analog = input.analogByAsset.get(asset.id);
    const signal = input.signalByAsset.get(asset.id);
    const investigation = input.investigationByAsset.get(asset.id);
    const factor = input.factorByAsset.get(asset.id);
    const event = input.eventByAsset.get(asset.id);
    const veto = input.macroByAsset.get(asset.id);
    const prior = input.priorByAsset.get(asset.id);
    const run = input.lastRunByAsset.get(asset.id);
    return {
      assetId: asset.id,
      analogId: analog?.id ?? null,
      row: {
        symbol: asset.symbol,
        assetType: asset.assetType,
        market: asset.market,
        close: price?.close ?? null,
        closeDate: price?.date ?? null,
        swing: setupOf(asset.id, "swing"),
        longer: setupOf(asset.id, "longer"),
        analogMinPct: analog?.minPct ?? null,
        analogMaxPct: analog?.maxPct ?? null,
        analogMatches: analog?.matches ?? null,
        analogHorizonDays: analog?.horizonDays ?? null,
        analogMedianPct: analog?.medianPct ?? null,
        analogPositive: analog?.positive ?? null,
        // Units, because they are the one thing a reader of this file cannot infer: `volumeRatio`
        // is a multiple of the asset's own 20-session average, so 1.0 is an average day and
        // `VOLUME_CONFIRMS_AT` compares against it as a multiple; `relStrength` is in percentage
        // points of 20-session return above or below the peer median, so `REL_BAND` is points and
        // not a ratio -- and it is read per market, because a point means a different thing to a
        // currency pair than to a coin. Passing one in the other's units would make both rules
        // fire on the wrong names and neither would look broken.
        volumeRatio: factor?.volumeRatio ?? null,
        relStrength: factor?.relStrength ?? null,
        // **This was missing, and its absence made the log disagree with the site.** `r20` is
        // the asset's own 20-session return and it is half of `shortNeedsBacking`: a short on a
        // name already down past SHORT_LATE_AT needs one of the five confirmations, in any
        // market. The column was added to `lib/decisionInput.ts`, `lib/queries.ts` and the rule
        // table on 2026-10-09 and this file was not touched, so every row written since has
        // decided late shorts on four of the gate's two conditions.
        //
        // Where it bit: Crypto, PSX and FX measured positive, so the market half of the gate
        // never fires there and the fall half was the only thing standing between a late short
        // and a printed SHORT. The site refused those names and the log recorded them as taken
        // -- which is the one disagreement this file cannot have, because the log is what the
        // refusal will eventually be judged by.
        r20: factor?.r20 ?? null,
        atr14: factor?.atr14 ?? null,
        // The fifth confirmation, on the same terms and in the same place, so the two cannot
        // drift apart again in the same way.
        entryTrigger: factor?.entryTrigger ?? null,
        triggerDirection: factor?.triggerDirection ?? null,
        // The stored macro refusal, if any, on the same terms and in the same place as the site
        // reads it (`getMacroVetoes` in lib/queries.ts), so the log and the page cannot disagree.
        macroVetoReason: veto?.reason ?? null,
        // `dayOf`, not the Date: `pg` hands back a `@db.Date` as local midnight, and east of UTC the
        // seam's `toISOString()` would read it as the day before and expire the veto a day early.
        macroVetoAsOf: dayOf(veto?.periodEnd),
        priorAction: prior?.action ?? null,
        priorAsOf: dayOf(prior?.periodEnd),
        lastRunAction: run?.action ?? null,
        lastRunSince: dayOf(run?.since),
        lastRunPrev: run?.prev ?? null,
        recentStories: signal?.recentStories ?? null,
        newsTone: signal?.tone ?? null,
        newsCatalyst: signal?.catalyst ?? null,
        robustZ: investigation?.robustZ ?? null,
        trigger: investigation?.trigger ?? null,
        nextEventDate: event?.date ?? null,
      },
    };
  });
}

// --- today's decisions --------------------------------------------------------------------------

function decideAll(input, today) {
  const out = [];
  for (const { assetId, analogId, row } of rowsForDecisions(input)) {
    const bundle = bundleFromRow(row, input.sourceHealth);
    const decisionInput = toDecisionInput(bundle, today);
    const decision = decideCall(decisionInput);
    // The take profit the lists show, by the same two functions (lib/assetClass.ts `rowTarget`).
    const shown = targetForCall(
      pickTarget(
        [row.swing ? { ...row.swing, horizon: "swing" } : null, row.longer ? { ...row.longer, horizon: "longer" } : null].filter(Boolean),
      ),
      decision,
    );
    out.push({
      assetId,
      symbol: row.symbol,
      market: decisionInput.market,
      action: decision.action,
      gate: decision.gate,
      confidence: decision.confidence,
      // Carried for the summary only, and deliberately not a column. `DecisionLog` records what
      // the rules *decided*, and a forming read is by definition not a decision -- storing it
      // would put a row in the outcome log that no gate produced and that accuracy.py would then
      // measure as though it had. The page computes it live from the same stored rows.
      developing: decision.developing
        ? `${decision.developing.would} (${decision.developing.closeness === null ? "not measurable" : Math.round(decision.developing.closeness * 100) + "%"})`
        : null,
      entryLow: decision.entry?.low ?? null,
      entryHigh: decision.entry?.high ?? null,
      invalidation: decision.invalidation,
      // A reference to the row the reading came from, not a copy of it. `analogRefs` is text
      // rather than a relation so that recomputing an analog cannot rewrite history.
      analogRefs: analogId ?? "",
      eventInDays: decisionInput.eventInDays,
      baseClose: decisionInput.lastClose,
      // What the trade was worth when it was decided: the reward:risk the lists printed beside it --
      // the measured target against the call's own stop, from the entry level -- since 2026-10-10,
      // when the quality gate began reading it back (getPublishedRuns). Null on every WAIT and on a
      // direction with no measured target on its side. Recorded rather than recomputed later:
      // `jobs/horizons.py` rewrites "SetupTarget" every run.
      rewardRisk: shown?.rewardRisk ?? null,
      baseRateShare: decision.plan?.baseRate?.share ?? null,
      baseRateCount: decision.plan?.baseRate?.count ?? null,
      // What the learning loop reads. `legs` names the confirmations that backed the direction
      // this row is about, in a fixed order and as stable identifiers; `intent` is the side a
      // refusal was refusing. Both are recorded at decision time because they cannot be
      // reconstructed later: the rows they were computed from are rewritten every night.
      //
      // The direction is the decided one for a LONG or SHORT and the refused one for a
      // `stop-crossed` or `short-unbacked`. Every other WAIT names no side, so it logs neither --
      // null, not an empty string, because "no legs backed it" is a finding and "not applicable"
      // is not, and a comma list cannot say which of the two it is.
      legs: (() => {
        const dir = decision.action === "LONG" ? "up" : decision.action === "SHORT" ? "down" : decision.intent;
        return dir ? confirmingLegs(decisionInput, dir).join(",") : null;
      })(),
      intent: decision.intent,
    });
  }
  return out;
}

/// Upsert today's rows, `BATCH_ROWS` at a time, committing each batch.
///
/// `ON CONFLICT ("assetId", "periodEnd")` is what makes a rerun safe: the table is unique on that
/// pair, so a second run on the same day updates the verdict instead of duplicating it or dying on
/// the index. The measured columns and `status` are deliberately NOT touched on conflict — a rerun
/// re-decides today, and overwriting a measurement with `open` would throw away the only thing in
/// this table that cannot be recomputed from current data.
/// The columns every database has, and the three that arrive with 20261009000000_decision_sizing.
///
/// Split because the schema reaches the database from `schema.yml` and the data lanes run on
/// their own cron: between a push and the next migration there is a window in which this job
/// runs against a table without these columns, and an unconditional INSERT naming them would
/// fail every batch — turning the one output the whole site is built around into zero rows for
/// the sake of three optional figures. The job writes what the table can hold and says which.
const CORE_COLUMNS = [
  "assetId", "periodEnd", "action", "gate", "confidence",
  "entryLow", "entryHigh", "invalidation", "factorId", "analogRefs",
  "eventInDays", "baseClose",
];
const SIZING_COLUMNS = ["rewardRisk", "baseRateShare", "baseRateCount"];
/// The two the learning loop reads, added by 20261010150000_decision_legs. Optional for the same
/// reason as the sizing columns, and independently of them: a database can have either group.
const LEARNING_COLUMNS = ["legs", "intent"];
const OPTIONAL_COLUMNS = [...SIZING_COLUMNS, ...LEARNING_COLUMNS];

/// Which of `names` exist on `table` right now. Asked once per run, not once per batch.
async function presentColumns(db, table, names) {
  const { rows } = await db.query(
    `SELECT column_name FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = $1 AND column_name = ANY($2)`,
    [table, names],
  );
  return new Set(rows.map((r) => r.column_name));
}

/// The columns a rerun may change: everything this job writes except `computedAt` and the key.
///
/// Derived from the same two lists the INSERT is built from rather than written out a second
/// time. A column named in one place and forgotten in the other would make a genuinely changed
/// row compare as unchanged and never be stored -- the one failure mode a skip clause has, and
/// the kind that leaves no trace anywhere: no error, no row, and a log that silently keeps
/// yesterday's verdict under today's date.
function changingColumns(extra) {
  return [...CORE_COLUMNS, ...extra].filter((c) => c !== "assetId" && c !== "periodEnd");
}

/// `extra` is the optional columns this database actually has, in `OPTIONAL_COLUMNS` order.
async function writeDecisions(client, decisions, today, extra) {
  const columns = [...CORE_COLUMNS, ...extra];
  let written = 0;
  const failures = [];

  for (let i = 0; i < decisions.length; i += BATCH_ROWS) {
    const batch = decisions.slice(i, i + BATCH_ROWS);
    const values = [];
    const tuples = batch.map((d, n) => {
      const base = n * columns.length;
      values.push(
        d.assetId, today, d.action, d.gate, d.confidence,
        d.entryLow, d.entryHigh, d.invalidation, null, d.analogRefs,
        d.eventInDays, d.baseClose,
      );
      for (const c of extra) values.push(d[c]);
      const marks = columns.map((_, c) => `$${base + c + 1}`);
      marks[1] = `${marks[1]}::date`;
      return `(${marks.join(", ")})`;
    });

    const sql =
      `INSERT INTO "DecisionLog" (${columns.map((c) => `"${c}"`).join(", ")})
` +
      `VALUES ${tuples.join(", ")}
` +
      `ON CONFLICT ("assetId", "periodEnd") DO UPDATE SET
` +
      `  action = EXCLUDED.action, gate = EXCLUDED.gate, confidence = EXCLUDED.confidence,
` +
      `  "entryLow" = EXCLUDED."entryLow", "entryHigh" = EXCLUDED."entryHigh",
` +
      `  invalidation = EXCLUDED.invalidation, "factorId" = EXCLUDED."factorId",
` +
      `  "analogRefs" = EXCLUDED."analogRefs", "eventInDays" = EXCLUDED."eventInDays",
` +
      `  "baseClose" = EXCLUDED."baseClose", "computedAt" = now()` +
      extra.map((c) => `,
  "${c}" = EXCLUDED."${c}"`).join("") +
      // Skip the write entirely when today's verdict is identical to the one already stored.
      //
      // Not about duplicate rows: the unique key already made those impossible, and this lane
      // re-decides the same `periodEnd` whenever it runs twice in a day. It is about what an
      // UPDATE that changes nothing costs. Postgres writes a new row version regardless, marks
      // the old one dead and journals both -- so a second run of a 477-name lane doubles the
      // table's dead tuples in order to store exactly what was already there.
      //
      // The comparison covers the decided columns only. `computedAt` is `now()` and would differ
      // on every run, which would defeat the clause outright. The measured columns and `status`
      // are deliberately absent from the SET above and so cannot appear here either -- which is
      // the property that matters most, because it means a skipped write can never touch a
      // maturation that has already been collected.
      //
      // `IS DISTINCT FROM` and not `<>`: half of these columns are legitimately null -- no entry
      // band, no target, no dated event -- and `<>` against a null is null rather than true, so
      // a row that went from null to a number would compare as unchanged and never be written.
      `
WHERE (${changingColumns(extra).map((c) => `"DecisionLog"."${c}"`).join(", ")})
` +
      `   IS DISTINCT FROM (${changingColumns(extra).map((c) => `EXCLUDED."${c}"`).join(", ")})`;

    // One batch, one transaction. A failed batch is rolled back and named; the batches that
    // already committed stay written, which is the whole point of batching.
    try {
      await client.query("BEGIN");
      await client.query(sql, values);
      await client.query("COMMIT");
      written += batch.length;
    } catch (error) {
      await client.query("ROLLBACK").catch(() => {});
      failures.push(`${batch[0].symbol}..${batch[batch.length - 1].symbol}: ${error.message}`);
    }
  }
  return { written, failures };
}

// --- maturation ---------------------------------------------------------------------------------

/// Fill the measured columns of past rows whose forward window has filled.
///
/// The horizons are +1, +5 and +20 **sessions stored for that asset**, not calendar days. The
/// distinction is not cosmetic: 20 calendar days after a decision is about 14 trading days, so
/// measuring on calendar days would silently report a 14-session outcome in a column labelled 20
/// and every published hit rate for that horizon would be measuring something other than its name.
/// Crypto makes it worse rather than better — it trades every day, so the same calendar arithmetic
/// would be right for crypto and wrong for equities, and the error would hide in the mix.
///
/// Three bulk reads: the candidate rows, and the stored sessions of the assets they belong to.
async function matureRows(client, today, dryRun) {
  const { rows: candidates } = await client.query(
    `SELECT id, "assetId", "periodEnd", "baseClose", status,
            "move1Pct", "move5Pct", "move20Pct"
       FROM "DecisionLog"
      WHERE "periodEnd" < $1::date AND status IN ('open', 'measured1', 'measured5')
      ORDER BY "assetId", "periodEnd"`,
    [today],
  );
  if (candidates.length === 0) return { candidates: 0, updated: 0, byStatus: {}, failures: [] };

  // One read for every session any candidate could need, rather than one per row. Bounded below
  // by the oldest candidate's day so the whole price history does not cross the wire.
  const oldest = candidates
    .map((r) => dayOf(r.periodEnd))
    .reduce((a, b) => (a < b ? a : b));
  const assetIds = [...new Set(candidates.map((r) => r.assetId))];
  const { rows: sessionRows } = await client.query(
    `SELECT "assetId", date, close FROM "PriceSnapshot"
      WHERE "assetId" = ANY($1::text[]) AND date >= $2::date
      ORDER BY "assetId", date ASC`,
    [assetIds, oldest],
  );

  /// Sessions per asset, oldest first. The index into this list IS the session count, which is the
  /// only reason the ordering above matters.
  const sessionsByAsset = new Map();
  for (const r of sessionRows) {
    let list = sessionsByAsset.get(r.assetId);
    if (!list) sessionsByAsset.set(r.assetId, (list = []));
    list.push({ day: dayOf(r.date), close: r.close });
  }

  const updates = [];
  for (const row of candidates) {
    const periodEnd = dayOf(row.periodEnd);
    const sessions = sessionsByAsset.get(row.assetId) ?? [];

    // The base session is the newest stored session at or before the decision's day — the session
    // whose close the decision was read from. `baseClose` is the number the row itself recorded,
    // and it is preferred over re-reading the price, so a later correction to a close cannot
    // silently restate a past decision's starting point.
    let baseIndex = -1;
    for (let i = 0; i < sessions.length; i += 1) {
      if (sessions[i].day <= periodEnd) baseIndex = i;
      else break;
    }
    const base = row.baseClose ?? (baseIndex >= 0 ? sessions[baseIndex].close : null);

    const next = { move1Pct: null, measured1On: null, move5Pct: null, measured5On: null,
                   move20Pct: null, measured20On: null };
    let highest = 0;   // the furthest horizon actually measured
    let dead = false;  // a window whose calendar budget ran out with no session to measure on

    for (const n of HORIZONS) {
      const target = baseIndex >= 0 ? sessions[baseIndex + n] : undefined;
      if (base !== null && base !== 0 && target) {
        next[`move${n}Pct`] = ((target.close - base) / base) * 100;
        next[`measured${n}On`] = target.day;
        highest = n;
        continue;
      }
      // No session there yet. Still pending, or never coming?
      if (daysBetween(periodEnd, today) >= calendarBudget(n)) dead = true;
      break;
    }

    // `unmeasurable` is reserved for a row that measured nothing and never will — no base close,
    // or a feed that stopped before the first forward session arrived. A row that reached +5 and
    // then lost its feed stays `measured5`: that is what it measured, and it is a terminal answer
    // to the +5 question even though +20 will never be answered.
    const status = highest === 20
      ? "measured20"
      : highest > 0
        ? `measured${highest}`
        : dead || base === null
          ? "unmeasurable"
          : "open";

    // Only rows that actually moved on are sent back, so a daily run updates the handful whose
    // window just filled rather than rewriting every past row it read.
    const changed =
      status !== row.status ||
      (next.move1Pct !== null && row.move1Pct === null) ||
      (next.move5Pct !== null && row.move5Pct === null) ||
      (next.move20Pct !== null && row.move20Pct === null);
    if (changed) updates.push({ id: row.id, status, ...next });
  }

  const byStatus = {};
  for (const u of updates) byStatus[u.status] = (byStatus[u.status] ?? 0) + 1;
  if (dryRun) return { candidates: candidates.length, updated: updates.length, byStatus, failures: [] };

  // Same batching rule as the writes above, and for the same reason: a long transaction over a
  // pooled connection is how this repo lost 100,000 rows once already.
  let updated = 0;
  const failures = [];
  for (let i = 0; i < updates.length; i += BATCH_ROWS) {
    const batch = updates.slice(i, i + BATCH_ROWS);
    const sql =
      `UPDATE "DecisionLog" AS d SET
         "move1Pct" = v.move1, "measured1On" = v.on1,
         "move5Pct" = v.move5, "measured5On" = v.on5,
         "move20Pct" = v.move20, "measured20On" = v.on20,
         status = v.status
       FROM (VALUES ${batch
         .map((_, n) => {
           const b = n * 8;
           return `($${b + 1}::text, $${b + 2}::float8, $${b + 3}::date, $${b + 4}::float8,` +
                  ` $${b + 5}::date, $${b + 6}::float8, $${b + 7}::date, $${b + 8}::text)`;
         })
         .join(", ")}) AS v(id, move1, on1, move5, on5, move20, on20, status)
       WHERE d.id = v.id`;
    const values = batch.flatMap((u) => [
      u.id, u.move1Pct, u.measured1On, u.move5Pct, u.measured5On, u.move20Pct, u.measured20On,
      u.status,
    ]);
    try {
      await client.query("BEGIN");
      const res = await client.query(sql, values);
      await client.query("COMMIT");
      updated += res.rowCount;
    } catch (error) {
      await client.query("ROLLBACK").catch(() => {});
      failures.push(`maturation batch at ${i}: ${error.message}`);
    }
  }
  return { candidates: candidates.length, updated, byStatus, failures };
}

// --- the summary --------------------------------------------------------------------------------

function tally(rows, key) {
  const out = new Map();
  for (const r of rows) out.set(r[key], (out.get(r[key]) ?? 0) + 1);
  return [...out.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
}

/// The same table twice: plain text for whoever is watching the run, Markdown for the job summary.
///
/// Both, not one: the raw Action log needs a GitHub sign-in to open and the step summary does not,
/// so a summary that only exists in the log is a summary half the readers cannot see.
function renderSummary({ today, decisions, written, failures, maturation, dryRun, tableMissing }) {
  const lines = [];
  const md = [];
  const head = `Decisions for ${today}${dryRun ? "  (DRY RUN — nothing written)" : ""}`;
  lines.push(head, "=".repeat(head.length));
  md.push(`## ${head}`, "");

  const actions = tally(decisions, "action");
  const gates = tally(decisions, "gate");
  const markets = tally(decisions, "market");
  const confidences = tally(decisions, "confidence");

  const block = (title, pairs) => {
    lines.push("", `${title}:`);
    for (const [name, n] of pairs) lines.push(`   ${String(name).padEnd(20)} ${String(n).padStart(5)}`);
    md.push(`### ${title}`, "", "| | count |", "| --- | --- |");
    for (const [name, n] of pairs) md.push(`| ${name} | ${n} |`);
    md.push("");
  };

  block("by action", actions);
  // Counted next to the gates, because "incomplete 163" is the number that reads as a dead end
  // and this is the half of it that is not. A direction is in place for each of these and the
  // conditions behind it are not all present yet.
  const forming = decisions.filter((d) => d.developing);
  if (forming.length) {
    const ups = forming.filter((d) => d.developing.startsWith("LONG")).length;
    lines.push(
      "",
      `developing: ${forming.length} of ${decisions.length} have a direction forming ` +
        `(${ups} towards LONG, ${forming.length - ups} towards SHORT)`,
    );
    md.push(
      `**Developing:** ${forming.length} of ${decisions.length} have a direction forming ` +
        `(${ups} towards LONG, ${forming.length - ups} towards SHORT). Not actions.`,
      "",
    );
  }
  block("by gate", gates);
  block("by market", markets);
  block("by confidence", confidences);

  const writeLine = dryRun
    ? `would write ${decisions.length} rows for periodEnd ${today}`
    : `wrote ${written} of ${decisions.length} rows for periodEnd ${today}`;
  const matLine = maturation
    ? `maturation: ${maturation.candidates} past rows checked, ` +
      `${maturation.updated} ${dryRun ? "would be " : ""}updated` +
      (Object.keys(maturation.byStatus).length
        ? ` (${Object.entries(maturation.byStatus).map(([s, n]) => `${s} ${n}`).join(", ")})`
        : "")
    : "maturation: skipped";

  lines.push("", writeLine, matLine);
  md.push(`**${writeLine}**`, "", matLine, "");

  if (tableMissing) {
    const note =
      'The "DecisionLog" table does not exist in this database yet, so nothing could be ' +
      "written or matured. The migration for it is still pending.";
    lines.push("", note);
    md.push(`> ${note}`, "");
  }
  for (const f of failures) {
    lines.push(`  skipped: ${f}`);
    md.push(`- skipped: ${f}`);
  }
  if (!dryRun && failures.length && written > 0) {
    const note = "Partial success: some rows were written and some batches were skipped.";
    lines.push("", note);
    md.push("", note);
  }

  return { text: lines.join("\n"), markdown: md.join("\n") };
}

// --- main ---------------------------------------------------------------------------------------

async function main() {
  if (!process.env.DATABASE_URL) {
    throw new Error(
      "DATABASE_URL is not set. Copy .env.example to .env and paste the connection string, " +
      "or export it in this shell.",
    );
  }

  // ONE `today` for the whole run, read once and passed everywhere: into the rules, into
  // `periodEnd`, and into the maturation window. A run that read the clock twice could straddle
  // midnight and write two different days in one pass.
  const today = todayISO();

  // A small pool for the parallel reads; the writes take one connection out of it and keep it, so
  // every BEGIN and its COMMIT are certainly on the same connection. The primary, or the standby when the
  // primary cannot be reached (tools/writer.mjs), the same rule every Python job in the lane follows.
  const { pool } = await writerPool(4);

  let decisions = [];
  let written = 0;
  let failures = [];
  let maturation = null;
  let tableMissing = false;

  try {
    const input = await readInputs(pool, today);
    decisions = decideAll(input, today);

    const present = await tableExists(pool, "DecisionLog");
    tableMissing = !present;

    if (present) {
      const client = await pool.connect();
      try {
        maturation = await matureRows(client, today, DRY_RUN);
        if (!DRY_RUN) {
          // Asked of the live table rather than assumed from the migration folder: the schema
          // lane and the data lanes are separate workflows on separate schedules, and this job
          // must keep writing its 477 rows through the window where the code is ahead of the
          // column. Reported in the summary so "no reward figures" never reads as "no rewards".
          const present = await presentColumns(client, "DecisionLog", OPTIONAL_COLUMNS);
          const extra = OPTIONAL_COLUMNS.filter((c) => present.has(c));
          const missing = OPTIONAL_COLUMNS.filter((c) => !present.has(c));
          if (missing.length) {
            console.log(
              `  "DecisionLog" has no ${missing.join(", ")} column(s) yet, so ${missing.length === 1 ? "it is" : "they are"} ` +
                "not logged this run. Everything else is written as usual.",
            );
          }
          const result = await writeDecisions(client, decisions, today, extra);
          written = result.written;
          failures = [...maturation.failures, ...result.failures];
        } else {
          failures = maturation.failures;
        }
      } finally {
        client.release();
      }
    }
  } finally {
    await pool.end();
  }

  const { text, markdown } = renderSummary({
    today, decisions, written, failures, maturation, dryRun: DRY_RUN, tableMissing,
  });
  console.log(text);
  if (process.env.GITHUB_STEP_SUMMARY) {
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${markdown}\n`);
  }

  // Red when nothing at all landed; green when some rows landed and others were named as skipped,
  // because a partial run that said so is a success a workflow should not block on.
  if (decisions.length === 0) {
    console.error("No assets produced a decision at all.");
    process.exitCode = 1;
    return;
  }
  if (DRY_RUN) return;
  if (tableMissing || written === 0) {
    console.error('Nothing was written to "DecisionLog".');
    process.exitCode = 1;
  }
}

// Only run when this file is the command, so the writing and maturing halves can be imported and
// exercised against a scratch table instead of only ever being tried for the first time on
// production. `--dry-run` proves the reads; this is what lets the writes be proved too.
if (import.meta.main) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

export { readInputs, decideAll, writeDecisions, matureRows, renderSummary, calendarBudget, BATCH_ROWS };
