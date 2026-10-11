/// Which days each market trades, when its daily bar is final, and how far behind a stored close is
/// (brain.md rule 95).
///
/// Freshness used to be counted in calendar days only (STALE_AFTER_DAYS), so nothing knew that a currency
/// pair has no Saturday. Yahoo began answering Saturday and Sunday stub bars for currency pairs after
/// 2026-10-10 and they were stored as sessions: health read "FX newest 2026-10-11, 0 days old" on a Sunday,
/// and 16 of the 18 FX calls logged for 10-10 were read from a Saturday stub. A weekday market's weekend
/// bar is not a close, and a close two expected sessions old is stale whatever the calendar-day count says.
///
/// Holidays are not known here -- no exchange holiday calendar is stored, and none is invented -- so one
/// missing session is reported as "behind" (a holiday or a late feed) and only two make a close stale.
/// Times are the venues' published hours; US and futures hours follow New York daylight time.

import type { Market } from "./decision.ts";

export type FreshnessState = "current" | "closed" | "behind" | "stale" | "none";

/// Two expected sessions without a close: the feed has failed, or the market has been shut for a run of
/// days this module cannot tell from a failure. Either way no call is read from it.
export const STALE_AFTER_SESSIONS = 2;

const DAY_MS = 86_400_000;
const isoOf = (t: number) => new Date(t).toISOString().slice(0, 10);
const dayStart = (iso: string) => Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);

/// Crypto trades every day; every other market here trades Monday to Friday.
export function tradesOn(market: Market, iso: string): boolean {
  if (market === "Crypto") return true;
  const t = dayStart(iso);
  if (Number.isNaN(t)) return false;
  const dow = new Date(t).getUTCDay();
  return dow !== 0 && dow !== 6;
}

// The same rule in SQL is written inline where closes are read -- `(a."assetType" = 'crypto' OR
// EXTRACT(ISODOW FROM s.date) < 6)` in lib/queries.ts and tools/decide.mjs -- and as `session_bar` in
// jobs/sessions.py for the jobs. The web layer assembles no SQL, so there is no helper here; a test pins
// every one of those reads.

/// Session days strictly after `after` and on or before `through`.
export function sessionsAfter(market: Market, after: string, through: string): number {
  const a = dayStart(after);
  const b = dayStart(through);
  if (Number.isNaN(a) || Number.isNaN(b) || b <= a) return 0;
  let n = 0;
  for (let t = a + DAY_MS; t <= b; t += DAY_MS) if (tradesOn(market, isoOf(t))) n++;
  return n;
}

/// The New York offset from UTC, in minutes, at instant `t` (-240 in daylight time, -300 otherwise).
function newYorkOffset(t: number): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(new Date(t));
  const get = (k: string) => Number(parts.find((p) => p.type === k)?.value);
  const wall = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour") % 24, get("minute"));
  return Math.round((wall - t) / 60_000);
}

/// The instant of a New York wall-clock time on `iso`.
function newYork(iso: string, hour: number, minute = 0): number {
  const guess = dayStart(iso) + (hour * 60 + minute) * 60_000;
  const first = guess - newYorkOffset(guess) * 60_000;
  return guess - newYorkOffset(first) * 60_000;
}

/// When the daily bar for session `iso` is final, with an hour's grace for the provider to write it.
///   US         16:00 New York close
///   FX         17:00 New York, the end of the FX trading day
///   Commodity  Yahoo's futures day runs 04:00 to 03:59 UTC, so day D settles the next morning
///   PSX        15:30 Karachi (10:30 UTC)
///   Crypto     the UTC day's end
export function barFinalAt(market: Market, iso: string): number {
  const grace = 60 * 60_000;
  switch (market) {
    case "US":
    case "Other":
      return newYork(iso, 16) + grace;
    case "FX":
      return newYork(iso, 17) + grace;
    case "Commodity":
      return dayStart(iso) + DAY_MS + 4 * 3_600_000 + grace;
    case "PSX":
      return dayStart(iso) + (10 * 60 + 30) * 60_000 + grace;
    case "Crypto":
      return dayStart(iso) + DAY_MS + grace;
  }
}

/// The newest session whose daily bar should be final at `now`.
export function lastFinalSession(market: Market, now: Date): string {
  let t = dayStart(now.toISOString());
  for (let i = 0; i < 14; i++, t -= DAY_MS) {
    const iso = isoOf(t);
    if (tradesOn(market, iso) && barFinalAt(market, iso) <= now.getTime()) return iso;
  }
  return isoOf(t);
}

/// The next session after `now`'s newest final one: the day the next bar is expected for.
export function nextSession(market: Market, now: Date): string {
  let t = dayStart(lastFinalSession(market, now)) + DAY_MS;
  for (let i = 0; i < 14 && !tradesOn(market, isoOf(t)); i++) t += DAY_MS;
  return isoOf(t);
}

/// Whether the market is trading at `now`: when a live quote is expected to move.
export function marketOpen(market: Market, now: Date): boolean {
  const t = now.getTime();
  const iso = now.toISOString().slice(0, 10);
  switch (market) {
    case "Crypto":
      return true;
    case "US":
    case "Other":
      return tradesOn(market, iso) && t >= newYork(iso, 9, 30) && t < newYork(iso, 16);
    case "PSX": {
      const mins = now.getUTCHours() * 60 + now.getUTCMinutes();
      return tradesOn(market, iso) && mins >= 4 * 60 + 30 && mins < 10 * 60 + 30;
    }
    case "FX":
    case "Commodity": {
      // Sunday 17:00 (FX) or 18:00 (futures) New York to Friday 17:00 New York; futures pause 17:00-18:00
      // every weekday. Judged on the New York calendar day, which can differ from the UTC one.
      const nyWall = new Date(t + newYorkOffset(t) * 60_000);
      const nyDow = nyWall.getUTCDay();
      const nyMins = nyWall.getUTCHours() * 60 + nyWall.getUTCMinutes();
      const opensAt = market === "FX" ? 17 * 60 : 18 * 60;
      if (nyDow === 6) return false;
      if (nyDow === 0) return nyMins >= opensAt;
      if (nyDow === 5) return nyMins < 17 * 60;
      return market === "FX" ? true : nyMins < 17 * 60 || nyMins >= 18 * 60;
    }
  }
}

export interface Freshness {
  /// The newest session whose bar should be stored by now.
  expected: string;
  /// Expected sessions after the newest stored close.
  sessionsBehind: number | null;
  state: FreshnessState;
  /// The next session a new bar is expected for.
  nextSession: string;
  sentence: string;
}

/// How current a market's newest stored close is, in sessions, and in words that tell a closed market from
/// a failed feed.
export function freshnessOf(market: Market, newest: string | null, now: Date): Freshness {
  const expected = lastFinalSession(market, now);
  const next = nextSession(market, now);
  if (!newest) {
    return { expected, sessionsBehind: null, state: "none", nextSession: next, sentence: `No ${market} close is stored.` };
  }
  const behind = newest >= expected ? 0 : sessionsAfter(market, newest, expected);
  if (behind === 0) {
    const open = marketOpen(market, now) || market === "Crypto";
    return {
      expected,
      sessionsBehind: 0,
      state: open ? "current" : "closed",
      nextSession: next,
      sentence: open
        ? `Current: the newest ${market} close is ${newest}, the latest finished session.`
        : `Market closed as expected: the newest ${market} close is ${newest}, and no new bar is due before the ${next} session ends.`,
    };
  }
  if (behind < STALE_AFTER_SESSIONS) {
    return {
      expected,
      sessionsBehind: behind,
      state: "behind",
      nextSession: next,
      sentence: `One session behind: the newest ${market} close is ${newest} and ${expected} has no bar yet -- a holiday or a late feed.`,
    };
  }
  return {
    expected,
    sessionsBehind: behind,
    state: "stale",
    nextSession: next,
    sentence: `Stale: the newest ${market} close is ${newest}, ${behind} expected sessions ago.`,
  };
}

/// Why a close cannot be acted on by the calendar, or null (the rule table's gate 2b and `dataFault`).
///   bad-date  the close is dated on a day this market does not trade -- a provider's stub, not a session
///   stale     two or more expected sessions have passed with no close
export function sessionFault(market: Market, asOf: string, today: string): { gate: "bad-date" | "stale"; why: string } | null {
  if (!tradesOn(market, asOf)) {
    const day = new Date(dayStart(asOf)).toLocaleDateString("en-US", { weekday: "long", timeZone: "UTC" });
    return { gate: "bad-date", why: `Newest close is dated ${day} ${asOf.slice(0, 10)}, a day ${market} does not trade, so it is not a session's close.` };
  }
  const missed = sessionsSince(market, asOf, today);
  if (missed >= STALE_AFTER_SESSIONS) {
    return { gate: "stale", why: `Data stale: newest close ${asOf.slice(0, 10)}, and ${missed} expected sessions since have no close.` };
  }
  return null;
}

/// Expected sessions between a call's close and the day it is read on: the sessions after `asOf` and
/// before `today`. The rule table reads this with the date alone, so today's own session never counts.
export function sessionsSince(market: Market, asOf: string, today: string): number {
  const before = isoOf(dayStart(today) - DAY_MS);
  return sessionsAfter(market, asOf, before);
}
