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
import { freshnessOf, marketOpen, sessionFault, type FreshnessState } from "./sessions.ts";

/// The workflow file that refreshes each kind of reading. A problem names one so the watchdog can start
/// it; a problem with no lane is one only a person can fix.
export const LANE_FOR: Record<Market | "decisions" | "news" | "quotes", string | null> = {
  Crypto: "cron-crypto.yml",
  US: "cron-us-prices.yml",
  FX: "cron-us-prices.yml",
  Commodity: "cron-us-prices.yml",
  PSX: "cron-psx.yml",
  Other: null,
  decisions: "cron-decision.yml",
  news: "cron-news.yml",
  quotes: "cron-live.yml",
};

/// The decision lane runs once a day at 22:10 UTC, so before that the newest row is yesterday's. Two
/// days means a run was missed.
export const DECISIONS_STALE_AFTER_DAYS = 2;
/// The news lane runs every two hours. Six hours is three missed runs, not one slow feed.
export const NEWS_STALE_AFTER_HOURS = 6;
/// The live-quote lane runs every 15 minutes for crypto, around the clock, so the newest quote of any
/// kind is never meant to be older than that. An hour is four missed runs: GitHub dropped all but two
/// of the lane's scheduled runs on 2026-10-10, and the quotes sat two hours old with nothing reporting it.
export const QUOTES_STALE_AFTER_MINUTES = 60;
/// Quotes are opt-in (the LIVE_QUOTES variable). A newest quote this old means the lane was switched
/// off, not that it stalled, so it is reported and is not a problem -- or the watchdog would dispatch a
/// lane that skips itself, every hour, for ever.
export const QUOTES_OFF_AFTER_HOURS = 72;

export interface HealthReadings {
  /// The newest stored close per market, as an ISO day, or null when the market has none at all; and, when
  /// read, each active asset's newest close day (to count the names behind the market's newest session).
  closes: { market: Market; newest: string | null; assetDays?: string[] }[];
  newestDecision: string | null;
  newestNews: Date | string | null;
  /// Opt-in (`LIVE_QUOTES`): none at all, or none for days, is a lane that is off and not a fault; a
  /// lane that is on and has stopped is (see QUOTES_STALE_AFTER_MINUTES).
  newestQuote: Date | string | null;
  /// The newest live quote per market (rule 95): one market's ticks must not hide another's silence, as
  /// crypto's did while FX, US and commodity quotes sat frozen from Friday.
  quotesByMarket?: { market: Market; newest: Date | string | null }[];
  /// The last run and the last successful run of each lane that records its runs (ChunkRun).
  lanes?: { job: string; lastRun: Date | string | null; lastOk: Date | string | null }[];
  /// How many assets the universe holds, so a page that lists fewer can be caught (tools/ui_audit.py).
  pool?: number;
  /// The tier this request read from: "the primary" or a standby's name (lib/db.ts `servingTier`).
  servedFrom?: string | null;
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
  closes: {
    market: Market;
    newest: string | null;
    ageDays: number | null;
    limitDays: number;
    /// The calendar (rule 95): the newest session whose bar should be stored by now, how many expected
    /// sessions the newest close is behind, and whether a quiet market is closed or failing.
    expected: string;
    sessionsBehind: number | null;
    state: FreshnessState;
    nextSession: string;
    /// Active names whose own newest close is older than the market's expected session.
    namesBehind: number | null;
    sentence: string;
  }[];
  decisions: { newest: string | null; ageDays: number | null };
  news: { newest: string | null; ageHours: number | null };
  quotes: {
    newest: string | null;
    ageMinutes: number | null;
    markets: { market: Market; newest: string | null; ageMinutes: number | null; state: "current" | "late" | "closed" | "off" }[];
  };
  lanes: { job: string; lastRun: string | null; lastOk: string | null; minutesSinceOk: number | null }[];
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
    const f = freshnessOf(c.market, c.newest, now);
    if (ageDays === null) {
      problems.push({ check: `closes:${c.market}`, lane: LANE_FOR[c.market], detail: `no close stored for ${c.market}` });
    } else if (ageDays > limitDays) {
      problems.push({
        check: `closes:${c.market}`,
        lane: LANE_FOR[c.market],
        detail: `newest ${c.market} close is ${c.newest}, ${ageDays} days old; the rule table refuses after ${limitDays}`,
      });
    } else if (c.newest && sessionFault(c.market, c.newest, now.toISOString().slice(0, 10))) {
      // The rule table's own calendar check (lib/sessions.ts `sessionFault`), so a close is a problem here
      // exactly when every decision on it would be refused: two expected sessions without a bar, or a bar
      // dated on a day the market does not trade.
      problems.push({
        check: `closes:${c.market}`,
        lane: LANE_FOR[c.market],
        detail: sessionFault(c.market, c.newest, now.toISOString().slice(0, 10))!.why,
      });
    }
    const namesBehind = c.assetDays ? c.assetDays.filter((d) => d < f.expected).length : null;
    return {
      market: c.market,
      newest: c.newest,
      ageDays,
      limitDays,
      expected: f.expected,
      sessionsBehind: f.sessionsBehind,
      state: f.state,
      nextSession: f.nextSession,
      namesBehind,
      sentence: namesBehind ? `${f.sentence} ${namesBehind} active ${namesBehind === 1 ? "name is" : "names are"} older than ${f.expected}.` : f.sentence,
    };
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

  // Quotes, per market and by its hours (rule 95): a market that is trading must have a quote under an hour
  // old; a closed market's last quote is expected to sit still and is not a fault. Without per-market
  // readings (an older caller) the newest quote of any kind is judged, as before.
  const quoteMs = msAge(r.newestQuote, now);
  const markets = (r.quotesByMarket ?? []).map((q) => {
    const ms = msAge(q.newest, now);
    const ageMinutes = ms === null ? null : Math.round(ms / 60_000);
    let state: "current" | "late" | "closed" | "off";
    if (ms === null || ms > QUOTES_OFF_AFTER_HOURS * 3_600_000) state = "off";
    else if (!marketOpen(q.market, now)) state = "closed";
    else state = ms > QUOTES_STALE_AFTER_MINUTES * 60_000 ? "late" : "current";
    if (state === "late") {
      problems.push({
        check: `quotes:${q.market}`,
        lane: LANE_FOR.quotes,
        detail: `${q.market} is trading and its newest live quote is ${ageMinutes} minutes old; the lane runs every 15`,
      });
    }
    return { market: q.market, newest: q.newest ? new Date(q.newest).toISOString() : null, ageMinutes, state };
  });
  if (!r.quotesByMarket && quoteMs !== null && quoteMs > QUOTES_STALE_AFTER_MINUTES * 60_000 && quoteMs <= QUOTES_OFF_AFTER_HOURS * 3_600_000) {
    problems.push({
      check: "quotes",
      lane: LANE_FOR.quotes,
      detail: `newest live quote is ${Math.round(quoteMs / 60_000)} minutes old; the lane runs every 15`,
    });
  }
  // A standby read publishes nothing (rule 94), so a site serving from one is not healthy whatever its
  // freshness says. No lane fixes it -- the primary is down or over its quota -- so it names none, and
  // the watchdog hands it to a person. On 2026-10-11 health read green for hours while the primary was
  // over quota and every list was empty (rule 95).
  if (r.servedFrom && r.servedFrom !== "the primary") {
    problems.push({
      check: "database",
      lane: null,
      detail: `reads are served from ${r.servedFrom} because the primary cannot be used, so no call is published`,
    });
  }
  const lanes = (r.lanes ?? []).map((l) => {
    const ok = msAge(l.lastOk, now);
    return {
      job: l.job,
      lastRun: l.lastRun ? new Date(l.lastRun).toISOString() : null,
      lastOk: l.lastOk ? new Date(l.lastOk).toISOString() : null,
      minutesSinceOk: ok === null ? null : Math.round(ok / 60_000),
    };
  });
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
      markets,
    },
    lanes,
    pool: r.pool ?? null,
  };
}
