// The one countdown the site displays.
//
// There used to be three implementations of "how many days until". Two agreed by duplication --
// the events page and `UpcomingBlock` each anchored to local midnight and each rounded, in their
// own copy of the arithmetic -- and the third, exported from `lib/plain.ts`, measured against
// `Date.now()` rather than against midnight and was a full day out for half of every day. It was
// imported nowhere, so it was never wrong on screen; it was a trap for whoever imported it next.
//
// Now there is one, and these tests are what keep the two surviving callers agreeing.

import { test } from "node:test";
import assert from "node:assert/strict";
import { calendarDaysUntil, startOfToday } from "../lib/format.ts";

/// A stored `@db.Date`, which Prisma hands back at UTC midnight.
const stored = (iso: string) => new Date(`${iso}T00:00:00Z`);

/// The anchor as `startOfToday` builds it: local midnight on the given day.
const localMidnight = (y: number, m: number, d: number) => new Date(y, m - 1, d);

test("a date today is 0, tomorrow is 1, yesterday is -1", () => {
  const today = localMidnight(2026, 10, 7);
  assert.equal(calendarDaysUntil(stored("2026-10-07"), today), 0);
  assert.equal(calendarDaysUntil(stored("2026-10-08"), today), 1);
  assert.equal(calendarDaysUntil(stored("2026-10-06"), today), -1);
});

test("the answer does not move with the hour the page is rendered", () => {
  // The defect this replaces: measuring against the current instant instead of midnight made
  // the same stored date read 0 in the morning and -1 in the afternoon, so two rows of one
  // render could disagree about what yesterday was.
  const date = stored("2026-10-07");
  const answers = new Set<number>();
  for (const hour of [0, 6, 11, 12, 13, 18, 23]) {
    const now = new Date(2026, 9, 7, hour, 30, 0);
    now.setHours(0, 0, 0, 0); // what startOfToday does
    answers.add(calendarDaysUntil(date, now));
  }
  assert.deepEqual([...answers], [0], "every hour of one day must give one answer");
});

test("rounding absorbs the gap between a UTC stored date and a local anchor", () => {
  // The two ends are anchored differently by design. Rounding is what keeps that fraction of a
  // day from becoming a whole one, which is why this is not a floor.
  const today = localMidnight(2026, 10, 7);
  const offsetHours = -today.getTimezoneOffset() / 60;
  assert.equal(
    calendarDaysUntil(stored("2026-10-07"), today),
    0,
    `a date stored today must read 0 at UTC${offsetHours >= 0 ? "+" : ""}${offsetHours}`,
  );
  assert.equal(calendarDaysUntil(stored("2026-10-14"), today), 7);
});

test("a week and a month out count as whole days", () => {
  const today = localMidnight(2026, 10, 7);
  assert.equal(calendarDaysUntil(stored("2026-10-14"), today), 7);
  assert.equal(calendarDaysUntil(stored("2026-11-06"), today), 30);
  assert.equal(calendarDaysUntil(stored("2026-09-07"), today), -30);
});

test("startOfToday is midnight, so it carries no time of day into the arithmetic", () => {
  const t = startOfToday();
  assert.equal(t.getHours(), 0);
  assert.equal(t.getMinutes(), 0);
  assert.equal(t.getSeconds(), 0);
  assert.equal(t.getMilliseconds(), 0);
});

test("a date crossing a month or year boundary is still counted in days", () => {
  assert.equal(calendarDaysUntil(stored("2027-01-01"), localMidnight(2026, 12, 31)), 1);
  assert.equal(calendarDaysUntil(stored("2026-11-01"), localMidnight(2026, 10, 31)), 1);
});
