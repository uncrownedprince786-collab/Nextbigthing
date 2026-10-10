// State-change badges: every kind from fixtures (the QA mode the directive asked for, without putting
// invented verdicts on a public page), when a row shows one, and the asset page's timeline.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { changeTimeline, classifyChange, gateWords, latestChange } from "../lib/stateChange.ts";

const ON = "2026-10-10";

// --- fixtures: one of every kind ---------------------------------------------------------------

test("FIXTURE every kind of change is classified, with the rule table's own reason", () => {
  const cases: [string, string, string, string, boolean][] = [
    ["LONG", "SHORT", "short", "REVERSED", true],
    ["SHORT", "LONG", "long", "REVERSED", true],
    ["LONG", "WAIT", "stop-crossed", "INVALIDATED", true],
    ["SHORT", "WAIT", "stop-crossed", "INVALIDATED", true],
    ["LONG", "WAIT", "macro-veto", "OVERRIDDEN", true],
    ["SHORT", "WAIT", "short-unbacked", "WITHDRAWN", false],
    ["LONG", "WAIT", "incomplete", "WITHDRAWN", false],
    ["WAIT", "LONG", "trend-long", "NEW CALL", false],
    ["WAIT", "SHORT", "unconfirmed-short", "NEW CALL", false],
  ];
  for (const [prev, cur, gate, kind, warn] of cases) {
    const c = classifyChange(prev, cur, gate, ON)!;
    assert.deepEqual([c.kind, c.from, c.to, c.on, c.warn], [kind, prev, cur, ON, warn], `${prev}->${cur} ${gate}`);
    assert.equal(c.reason, gateWords(gate));
  }
  assert.match(classifyChange("LONG", "WAIT", "stop-crossed", ON)!.reason, /through the stop/);
  assert.match(classifyChange("LONG", "WAIT", "macro-veto", ON)!.reason, /macro gate/);
});

test("no change is no badge: same verdict, nothing before, or WAIT to WAIT under another gate", () => {
  assert.equal(classifyChange("LONG", "LONG", "long", ON), null);
  assert.equal(classifyChange(null, "LONG", "long", ON), null);
  assert.equal(classifyChange("WAIT", "WAIT", "stop-crossed", ON), null);
  assert.equal(gateWords("some-new-gate"), "the rule table's reading changed");
});

// --- which rows show one ------------------------------------------------------------------------

const run = { action: "WAIT", runAction: "WAIT", runSince: ON, runPrev: "LONG", runGate: "stop-crossed", latestCycle: ON };

test("a row shows a change made in the newest cycle, when the page shows the verdict the log recorded", () => {
  assert.equal(latestChange(run)!.kind, "INVALIDATED");
  // An older change is history, not a badge.
  assert.equal(latestChange({ ...run, runSince: "2026-10-08" }), null);
  // The page is a cycle ahead of the log: it shows LONG, the log's newest run is a WAIT. No badge
  // describing a change to a verdict the reader is not looking at.
  assert.equal(latestChange({ ...run, action: "LONG" }), null);
  assert.equal(latestChange({ ...run, runPrev: null }), null);
});

// --- the asset page's timeline -------------------------------------------------------------------

test("the timeline lists every change in order, with the close each side was read from", () => {
  const t = changeTimeline([
    { periodEnd: "2026-10-10", action: "SHORT", gate: "short", baseClose: 198 },
    { periodEnd: "2026-10-08", action: "LONG", gate: "long", baseClose: 207 },
    { periodEnd: "2026-10-09", action: "LONG", gate: "long", baseClose: 205 },
    { periodEnd: "2026-10-11", action: "WAIT", gate: "stop-crossed", baseClose: 210 },
  ]);
  assert.deepEqual(
    t.map((x) => [x.fromOn, x.from, x.fromClose, x.on, x.to, x.toClose, x.kind]),
    [
      ["2026-10-09", "LONG", 205, "2026-10-10", "SHORT", 198, "REVERSED"],
      ["2026-10-10", "SHORT", 198, "2026-10-11", "WAIT", 210, "INVALIDATED"],
    ],
  );
  assert.deepEqual(changeTimeline([{ periodEnd: ON, action: "LONG", gate: "long", baseClose: 1 }]), []);
});

test("the list and the asset page take the change from the same functions", () => {
  const read = (p: string) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
  assert.ok(read("lib/assetClass.ts").includes("change: latestChange({"));
  const page = read("app/asset/[symbol]/page.tsx");
  assert.ok(page.includes("changeTimeline(") && page.includes("latestChange({"));
  const decision = read("components/decision.tsx");
  assert.ok(decision.slice(decision.indexOf("function DecisionRows(")).includes("<StateChangeBadge"));
});

test("PRICE: the big number and the line under it are one trade, and the close is labelled apart", () => {
  const decision = readFileSync(new URL("../components/decision.tsx", import.meta.url), "utf8");
  const rows = decision.slice(decision.indexOf("function DecisionRows("));
  const cell = rows.slice(rows.indexOf("<span className={ROW_LABEL}>Price & time</span>"), rows.indexOf("<span className={ROW_LABEL}>Entry zone</span>"));
  const quoted = cell.slice(cell.indexOf("{r.quote ? ("), cell.indexOf(") : ("));
  // Inside the quoted branch the headline is the trade's price and the line under it is the trade's time.
  assert.ok(quoted.indexOf("price(r.quote.price, currency)") < quoted.indexOf("clockUtc(r.quote.quotedAt)"));
  // The close appears only as a labelled line, never as the headline, when a newer trade exists.
  assert.match(quoted, /close \{price\(r\.priceNow, currency\)\}/);
  // The first price after the headline style is the trade's, so the close cannot be the headline.
  const head = quoted.indexOf("font-medium");
  assert.ok(head > 0 && quoted.startsWith("price(r.quote.price", quoted.indexOf("price(", head)), "the headline is the trade");
});
