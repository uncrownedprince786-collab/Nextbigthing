/// Choosing which stored `Ranking` rows belong to the window a page is showing.
///
/// This lives apart from `lib/queries.ts` for the same reason `lib/decision.ts` does: it is
/// arithmetic over rows with no database in it, and `queries.ts` constructs a Prisma client at
/// import time, so anything that imports it needs a `DATABASE_URL`. Keeping the rule here is what
/// lets `tests/rankingWindow.test.ts` run in the no-network, no-database test lane, which is the
/// only place a silent row-dropping bug would ever be caught.

/// How far behind the newest stored `periodEnd` a ranking row may sit and still be read as the
/// same measurement window rather than an older one.
///
/// 90, and like `EVENT_DUPLICATE_WITHIN_DAYS` the number comes from the stored rows rather than
/// from taste. Two things have to be told apart here, and they are orders of magnitude apart in
/// the data.
///
/// The first is one asset lagging its peers inside a single run. `jobs/rank.py` stores
/// `periodEnd` as the date of the close it actually used for that asset -- `close_on` returns the
/// newest snapshot on or before the window end, per asset -- so an asset whose price did not
/// arrive gets an earlier `periodEnd` than the rest of its industry. Measured across every
/// covered asset, the largest such lag is **1 day** (PFE, healthcare).
///
/// The second is the genuine second window. `rank.py` writes `totalReturn` twice per industry,
/// once for 2019→2021 and once for 2021→today, under the same `basis`, and `jobs/analysis.py`
/// reads both -- `industry_shift` and the per-asset writer separate them with
/// `periodEnd <= PRE_AI_END`. Those two windows sit **1739 days** apart in every one of the 17
/// industries that has them.
///
/// So 90 sits about ninety times above the largest observed lag and about nineteen times below
/// the smallest real window gap. Any value in that range behaves identically on today's data; 90
/// is chosen because it is wide enough to hold an asset halted for a quarter and still nowhere
/// near merging two windows.
export const RANKING_WINDOW_LAG_DAYS = 90;

const DAY_MS = 86_400_000;

/// The newest measurement window's rows, one per asset, ranks intact.
///
/// This replaces a `periodEnd === max(periodEnd)` filter, which silently deleted rows. Because
/// `periodEnd` is the per-asset close date (see above), that filter kept only the assets whose
/// price happened to arrive on the newest day and dropped every asset that lagged -- while the
/// `rank` column it kept was numbered by `rank.py` over the *full* scored list. The result on the
/// page was a ranking reading 1, 2, 4, 5 with nothing saying a row was missing, and no amount of
/// reading the page would reveal which asset had gone. PFE is one day behind its industry right
/// now, so the next `rank.py` run would have produced exactly that.
///
/// Keeping every row inside the window is what makes the numbering safe again: `rank.py` assigns
/// 1..N over the assets it scored for one window, so if none of them is discarded the kept ranks
/// are contiguous by construction. Nothing is renumbered here, which also keeps this list
/// agreeing with `/asset/[symbol]`, where the same rows are listed with the ranks the job wrote.
export function latestWindow<T extends { assetId: string; periodEnd: Date; rank: number }>(
  rows: T[],
): T[] {
  if (!rows.length) return [];
  let newest = rows[0].periodEnd.getTime();
  for (const r of rows) newest = Math.max(newest, r.periodEnd.getTime());
  const floor = newest - RANKING_WINDOW_LAG_DAYS * DAY_MS;

  // One row per asset, the newest inside the window. The uniqueness constraint plus `rank.py`
  // clearing the table each run means there should only ever be one, but picking the newest costs
  // nothing and means a stray older row cannot outrank the current one.
  const best = new Map<string, T>();
  for (const r of rows) {
    if (r.periodEnd.getTime() < floor) continue;
    const seen = best.get(r.assetId);
    if (!seen || r.periodEnd > seen.periodEnd) best.set(r.assetId, r);
  }
  return [...best.values()].sort((a, b) => a.rank - b.rank);
}

/// The window's own as-of date: the newest `periodEnd` among the rows, or null if there are none.
///
/// Needed because `latestWindow` deliberately keeps rows whose `periodEnd` lags the rest. Before
/// it did, every surviving row carried the same date and a page could read the as-of off the
/// first one; now the first row is rank 1, whose price is not necessarily the newest one in the
/// table. Reading the as-of off `rows[0]` would therefore under-report the window by however far
/// the top-ranked asset happens to lag, so the pages ask for the maximum instead.
export function rankingAsOf(rows: { periodEnd: Date }[]): Date | null {
  let newest: Date | null = null;
  for (const r of rows) if (!newest || r.periodEnd > newest) newest = r.periodEnd;
  return newest;
}
