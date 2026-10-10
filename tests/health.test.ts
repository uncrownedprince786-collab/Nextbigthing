// The heartbeat's judgement: what counts as stale, and which lane each problem names.
//
// The property worth most is that "stale" here means exactly what it means to the rule table, so the
// health page and every decision on the site cannot disagree about whether a close is too old.

import { test } from "node:test";
import assert from "node:assert/strict";
import { DECISIONS_STALE_AFTER_DAYS, LANE_FOR, NEWS_STALE_AFTER_HOURS, assess, type HealthReadings } from "../lib/health.ts";
import { STALE_AFTER_DAYS } from "../lib/decision.ts";

const NOW = new Date("2026-10-14T12:00:00Z"); // a Wednesday

function healthy(over: Partial<HealthReadings> = {}): HealthReadings {
  return {
    closes: [
      { market: "Crypto", newest: "2026-10-14" },
      { market: "US", newest: "2026-10-13" },
      { market: "PSX", newest: "2026-10-13" },
      { market: "FX", newest: "2026-10-13" },
      { market: "Commodity", newest: "2026-10-13" },
    ],
    newestDecision: "2026-10-13",
    newestNews: "2026-10-14T10:30:00Z",
    newestQuote: "2026-10-14T11:57:00Z",
    ...over,
  };
}

test("a healthy set of readings has no problems", () => {
  const h = assess(healthy(), NOW);
  assert.equal(h.ok, true);
  assert.deepEqual(h.problems, []);
  assert.equal(h.quotes.ageMinutes, 3);
  assert.equal(h.news.ageHours, 1.5);
});

test("a close is stale here exactly when the rule table would refuse it, market by market", () => {
  for (const market of ["Crypto", "US", "PSX", "FX", "Commodity"] as const) {
    const limit = STALE_AFTER_DAYS[market];
    const at = (days: number) => new Date(NOW.getTime() - days * 86_400_000).toISOString().slice(0, 10);
    const closes = healthy().closes.map((c) => (c.market === market ? { market, newest: at(limit) } : c));
    assert.equal(assess(healthy({ closes }), NOW).ok, true, `${market} at its limit is still fresh`);
    const older = healthy().closes.map((c) => (c.market === market ? { market, newest: at(limit + 1) } : c));
    const h = assess(healthy({ closes: older }), NOW);
    assert.equal(h.ok, false, `${market} one day past its limit`);
    assert.deepEqual(h.problems.map((p) => [p.check, p.lane]), [[`closes:${market}`, LANE_FOR[market]]]);
  }
});

test("each problem names the lane that would fix it", () => {
  assert.equal(LANE_FOR.Crypto, "cron-crypto.yml");
  assert.equal(LANE_FOR.US, "cron-us-prices.yml");
  assert.equal(LANE_FOR.FX, "cron-us-prices.yml");
  assert.equal(LANE_FOR.Commodity, "cron-us-prices.yml");
  assert.equal(LANE_FOR.PSX, "cron-psx.yml");
  assert.equal(LANE_FOR.decisions, "cron-decision.yml");
  assert.equal(LANE_FOR.news, "cron-news.yml");
  assert.equal(LANE_FOR.Other, null);
});

test("decisions: yesterday's row is normal before the evening run, two days is a missed run", () => {
  assert.equal(DECISIONS_STALE_AFTER_DAYS, 2);
  assert.equal(assess(healthy({ newestDecision: "2026-10-13" }), NOW).ok, true);
  const missed = assess(healthy({ newestDecision: "2026-10-12" }), NOW);
  assert.deepEqual(missed.problems.map((p) => p.lane), ["cron-decision.yml"]);
  assert.deepEqual(assess(healthy({ newestDecision: null }), NOW).problems.map((p) => p.check), ["decisions"]);
});

test("news: six hours is the limit, and no news at all is a problem, not a quiet day", () => {
  assert.equal(NEWS_STALE_AFTER_HOURS, 6);
  assert.equal(assess(healthy({ newestNews: "2026-10-14T06:00:00Z" }), NOW).ok, true);
  assert.deepEqual(assess(healthy({ newestNews: "2026-10-14T05:59:00Z" }), NOW).problems.map((p) => p.lane), ["cron-news.yml"]);
  assert.deepEqual(assess(healthy({ newestNews: null }), NOW).problems.map((p) => p.check), ["news"]);
});

test("quotes are opt-in: none, or none for days, is a lane that is off and never a problem", () => {
  const h = assess(healthy({ newestQuote: "2026-10-01T00:00:00Z" }), NOW);
  assert.equal(h.ok, true);
  assert.ok((h.quotes.ageMinutes ?? 0) > 10_000);
  assert.equal(assess(healthy({ newestQuote: null }), NOW).ok, true);
});

test("a quote lane that is on and has stopped is a problem the watchdog can restart", () => {
  // NOW is 12:00. Two hours is eight missed 15-minute runs, the state GitHub's dropped schedules left
  // on 2026-10-10.
  const h = assess(healthy({ newestQuote: "2026-10-14T10:00:00Z" }), NOW);
  assert.equal(h.ok, false);
  assert.deepEqual(h.problems.map((p) => [p.check, p.lane]), [["quotes", "cron-live.yml"]]);
  // Inside the hour: one or two late runs are not an outage.
  assert.equal(assess(healthy({ newestQuote: "2026-10-14T11:01:00Z" }), NOW).ok, true);
  // The edges: just past the hour is a problem, just past three days is a lane switched off.
  assert.equal(assess(healthy({ newestQuote: "2026-10-14T10:59:00Z" }), NOW).ok, false);
  assert.equal(assess(healthy({ newestQuote: "2026-10-11T11:59:00Z" }), NOW).ok, true);
});

test("a market with no close at all is a problem, and every problem is reported, not the first", () => {
  const h = assess(
    healthy({ closes: [{ market: "PSX", newest: null }, { market: "Crypto", newest: "2026-10-01" }], newestNews: null }),
    NOW,
  );
  assert.deepEqual(h.problems.map((p) => p.check).sort(), ["closes:Crypto", "closes:PSX", "news"]);
});
