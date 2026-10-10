/// Is the data the site is reading fresh, and if not, which lane would fix it?
///
/// Pure: the readings and the clock are parameters, so every rule here is testable without a database.
/// `/api/health` feeds it the newest stored rows; `tools/watchdog.py` reads the answer every hour and
/// re-dispatches the lane each problem names. That pair is the self-healing this platform can actually
/// run: a serverless site cannot hold an "infinite heartbeat loop", but a scheduled job can look, and a
/// lane that silently stopped can be started again without a person noticing first.
///
/// **One definition of stale.** A market's close is stale here exactly when the rule table would refuse
/// to act on it: `STALE_AFTER_DAYS` is imported, not copied. A health page that called a close fresh
/// while every decision on it read "stale" -- or the reverse -- would be two answers to one question.

import { STALE_AFTER_DAYS, type Market } from "./decision.ts";

/// The workflow file that refreshes each kind of reading. A problem names one so the watchdog can start
/// it; a problem with no lane is one only a person can fix.
export const LANE_FOR: Record<Market | "decisions" | "news", string | null> = {
  Crypto: "cron-crypto.yml",
  US: "cron-us-prices.yml",
  FX: "cron-us-prices.yml",
  Commodity: "cron-us-prices.yml",
  PSX: "cron-psx.yml",
  Other: null,
  decisions: "cron-decision.yml",
  news: "cron-news.yml",
};

/// The decision lane runs once a day at 22:10 UTC, so before that the newest row is yesterday's. Two
/// days means a run was missed.
export const DECISIONS_STALE_AFTER_DAYS = 2;
/// The news lane runs every two hours. Six hours is three missed runs, not one slow feed.
export const NEWS_STALE_AFTER_HOURS = 6;

export interface HealthReadings {
  /// The newest stored close per market, as an ISO day, or null when the market has none at all.
  closes: { market: Market; newest: string | null }[];
  newestDecision: string | null;
  newestNews: Date | string | null;
  /// Information only: quotes are opt-in (`LIVE_QUOTES`), so an old quote is not a fault by itself.
  newestQuote: Date | string | null;
  /// How many assets the universe holds, so a page that lists fewer can be caught (tools/ui_audit.py).
  pool?: number;
}

export interface Problem {
  check: string;
  lane: string | null;
  detail: string;
}

export interface Health {
  ok: boolean;
  checkedAt: string;
  problems: Problem[];
  closes: { market: Market; newest: string | null; ageDays: number | null; limitDays: number }[];
  decisions: { newest: string | null; ageDays: number | null };
  news: { newest: string | null; ageHours: number | null };
  quotes: { newest: string | null; ageMinutes: number | null };
  pool: number | null;
}

function dayAge(iso: string | null, now: Date): number | null {
  if (!iso) return null;
  const a = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(a)) return null;
  const today = Date.parse(`${now.toISOString().slice(0, 10)}T00:00:00Z`);
  return Math.round((today - a) / 86_400_000);
}

function msAge(when: Date | string | null, now: Date): number | null {
  if (!when) return null;
  const t = new Date(when).getTime();
  return Number.isNaN(t) ? null : now.getTime() - t;
}

export function assess(r: HealthReadings, now: Date): Health {
  const problems: Problem[] = [];

  const closes = r.closes.map((c) => {
    const ageDays = dayAge(c.newest, now);
    const limitDays = STALE_AFTER_DAYS[c.market];
    if (ageDays === null) {
      problems.push({ check: `closes:${c.market}`, lane: LANE_FOR[c.market], detail: `no close stored for ${c.market}` });
    } else if (ageDays > limitDays) {
      problems.push({
        check: `closes:${c.market}`,
        lane: LANE_FOR[c.market],
        detail: `newest ${c.market} close is ${c.newest}, ${ageDays} days old; the rule table refuses after ${limitDays}`,
      });
    }
    return { market: c.market, newest: c.newest, ageDays, limitDays };
  });

  const decisionAge = dayAge(r.newestDecision, now);
  if (decisionAge === null || decisionAge >= DECISIONS_STALE_AFTER_DAYS) {
    problems.push({
      check: "decisions",
      lane: LANE_FOR.decisions,
      detail: decisionAge === null ? "no decision has been logged" : `newest decision is ${r.newestDecision}, ${decisionAge} days old`,
    });
  }

  const newsMs = msAge(r.newestNews, now);
  const newsHours = newsMs === null ? null : Math.round((newsMs / 3_600_000) * 10) / 10;
  // Judged on the unrounded age: the one decimal shown is for reading, and rounding 6 h 1 min down to
  // "6.0" would hide exactly the minute that matters.
  if (newsMs === null || newsMs > NEWS_STALE_AFTER_HOURS * 3_600_000) {
    problems.push({
      check: "news",
      lane: LANE_FOR.news,
      detail: newsHours === null ? "no headline is stored" : `newest headline is ${newsHours} hours old`,
    });
  }

  const quoteMs = msAge(r.newestQuote, now);
  return {
    ok: problems.length === 0,
    checkedAt: now.toISOString(),
    problems,
    closes,
    decisions: { newest: r.newestDecision, ageDays: decisionAge },
    news: { newest: r.newestNews ? new Date(r.newestNews).toISOString() : null, ageHours: newsHours },
    quotes: {
      newest: r.newestQuote ? new Date(r.newestQuote).toISOString() : null,
      ageMinutes: quoteMs === null ? null : Math.round(quoteMs / 60_000),
    },
    pool: r.pool ?? null,
  };
}
