// Which ranking rows a page is allowed to drop.
//
// This file exists because the bug it guards was invisible from the page. `jobs/rank.py` numbers
// its rows 1..N over every asset it scored, and the read path used to keep only the rows whose
// `periodEnd` equalled the newest one. Since `periodEnd` is the date of the close actually used
// for that asset, a single asset whose price had not arrived was numbered, then silently deleted
// on the way to the screen -- and what the reader saw was a ranking running 1, 2, 4, 5 with no
// row and no message where 3 had been. Nothing threw, nothing was logged, and the only way to
// notice was to count.
//
// PFE was one day behind its industry when this was written, so these are not hypotheticals.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  latestWindow,
  rankingAsOf,
  RANKING_WINDOW_LAG_DAYS,
} from "../lib/rankingWindow.ts";

type Row = { assetId: string; periodEnd: Date; rank: number; symbol: string };

const d = (iso: string) => new Date(`${iso}T00:00:00Z`);

/// One industry's rows for one basis, as `rank.py` writes them: ranks dense from 1, and each
/// asset carrying the date of the close it was actually measured on.
function industry(onDate: string, symbols: string[], lagging: Record<string, string> = {}): Row[] {
  return symbols.map((symbol, i) => ({
    assetId: `a-${symbol}`,
    symbol,
    rank: i + 1,
    periodEnd: d(lagging[symbol] ?? onDate),
  }));
}

const ranksOf = (rows: Row[]) => rows.map((r) => r.rank);
const symbolsOf = (rows: Row[]) => rows.map((r) => r.symbol);

test("an asset one day behind its industry is kept, and the ranks stay 1..N", () => {
  // Exactly the live case: four assets priced to the 6th, PFE still at the 5th.
  const rows = industry("2026-10-06", ["JNJ", "PFE", "MRK", "ABBV"], { PFE: "2026-10-05" });

  const kept = latestWindow(rows);

  assert.deepEqual(symbolsOf(kept), ["JNJ", "PFE", "MRK", "ABBV"]);
  assert.deepEqual(ranksOf(kept), [1, 2, 3, 4], "no rank may go missing because a price was late");
});

test("the gap this guards against: the old rule dropped the lagging row and left a hole", () => {
  // The previous behaviour, written out, so the regression is described and not just prevented.
  const rows = industry("2026-10-06", ["JNJ", "PFE", "MRK", "ABBV"], { PFE: "2026-10-05" });
  const newest = Math.max(...rows.map((r) => r.periodEnd.getTime()));
  const oldRule = rows.filter((r) => r.periodEnd.getTime() === newest);

  assert.deepEqual(ranksOf(oldRule), [1, 3, 4], "this is the 1, 2, 4 the reader used to see");
  assert.deepEqual(ranksOf(latestWindow(rows)), [1, 2, 3, 4]);
});

test("several assets lagging by different amounts are all kept", () => {
  const rows = industry("2026-10-06", ["A", "B", "C", "D", "E"], {
    B: "2026-10-05",
    D: "2026-09-30",
    E: "2026-08-20",
  });

  assert.deepEqual(ranksOf(latestWindow(rows)), [1, 2, 3, 4, 5]);
});

test("the older measurement window is still excluded, which is what the filter was for", () => {
  // `rank.py` writes `totalReturn` twice per industry under one basis: 2019→2021 and
  // 2021→today. Both are real and `jobs/analysis.py` reads both, so the read path has to show
  // one window rather than merging them into a table with two rank 1s.
  const current = industry("2026-10-06", ["A", "B", "C"]);
  const preAi = industry("2021-12-31", ["A", "B", "C"]);

  const kept = latestWindow([...current, ...preAi]);

  assert.equal(kept.length, 3, "one row per asset, not one per asset per window");
  assert.deepEqual(ranksOf(kept), [1, 2, 3]);
  for (const r of kept) {
    assert.equal(r.periodEnd.getTime(), d("2026-10-06").getTime());
  }
});

test("an asset that only ever had a row in the older window does not leak into the current one", () => {
  // The case that makes "newest row per asset" insufficient on its own: picking each asset's own
  // newest row would promote a delisted name's 2021 row into the 2026 table, where its rank
  // collides with a current one.
  const current = industry("2026-10-06", ["A", "B", "C"]);
  const delisted: Row = {
    assetId: "a-GONE",
    symbol: "GONE",
    rank: 2,
    periodEnd: d("2021-12-31"),
  };

  const kept = latestWindow([...current, delisted]);

  assert.deepEqual(symbolsOf(kept), ["A", "B", "C"]);
  assert.equal(
    ranksOf(kept).filter((r) => r === 2).length,
    1,
    "two rows claiming rank 2 would be a table with two second places",
  );
});

test("the window boundary is the documented one, and it is a floor rather than an equality", () => {
  const inside = industry("2026-10-06", ["A", "B"], {
    B: "2026-07-09", // 89 days behind
  });
  assert.equal(latestWindow(inside).length, 2, "89 days is inside a 90 day window");

  const outside = industry("2026-10-06", ["A", "B"], {
    B: "2026-01-01", // far beyond the floor
  });
  assert.equal(latestWindow(outside).length, 1, "a row from last winter is a different window");
  assert.equal(RANKING_WINDOW_LAG_DAYS, 90);
});

test("duplicate rows for one asset inside the window collapse to the newest", () => {
  const rows: Row[] = [
    { assetId: "a-A", symbol: "A", rank: 1, periodEnd: d("2026-10-06") },
    { assetId: "a-A", symbol: "A", rank: 1, periodEnd: d("2026-10-01") },
    { assetId: "a-B", symbol: "B", rank: 2, periodEnd: d("2026-10-06") },
  ];

  const kept = latestWindow(rows);
  assert.equal(kept.length, 2);
  assert.equal(kept[0].periodEnd.getTime(), d("2026-10-06").getTime());
});

test("no rows in, no rows out, and no crash on the empty case", () => {
  assert.deepEqual(latestWindow([]), []);
  assert.equal(rankingAsOf([]), null);
});

test("the as-of is the window's newest date, not the top-ranked asset's", () => {
  // Rank 1 is the lagging one here. Reading the as-of off row [0] -- which is what the pages did
  // when every kept row shared a date -- would report the table a day stale.
  const rows = industry("2026-10-06", ["LAGGY", "B", "C"], { LAGGY: "2026-10-05" });

  assert.equal(rankingAsOf(latestWindow(rows))!.getTime(), d("2026-10-06").getTime());
});

test("ranks come back in order even when the stored rows do not", () => {
  const rows = industry("2026-10-06", ["A", "B", "C"]).reverse();
  assert.deepEqual(ranksOf(latestWindow(rows)), [1, 2, 3]);
});
