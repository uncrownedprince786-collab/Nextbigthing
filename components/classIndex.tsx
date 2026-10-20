import Link from "next/link";
import { Empty, Section } from "@/components/ui";
import { WithheldList, DecisionList, SectorBoard } from "@/components/decision";
import { AssetDirectory } from "@/components/assetDirectory";
import { cachedDecisionRows, cachedSourceHealth } from "@/lib/cached";
import { getPoolExclusions } from "@/lib/queries";
import { loadOrDefer } from "@/lib/buildSafe";
import { coverageLabelFor, todayISO } from "@/lib/decisionInput";
import { outcomeStatusOf } from "@/lib/outcome";
import {
  marketStatus,
  marketStatusLines,
  byCloseness,
  byConfidence,
  scoreRows,
  isPublished,
  toListRow,
  type AssetClass,
} from "@/lib/assetClass";

/// One asset class, every name in it, one reading each.
///
/// Shared by the four class routes rather than copied into them, because the only thing that
/// differs between those pages is which rows belong and what the heading says -- both of which are
/// data in `ASSET_CLASSES`. Four copies of this file is how `/crypto` comes to sort differently
/// from `/stocks` after someone fixes one of them.
///
/// Three lists and nothing else, in the same order and the same component the overview uses: a
/// reader who learned to read the front page has not got to learn a second layout here. The
/// difference from the overview is that this page is complete -- no cap on any list, because the
/// question this page answers is "show me all of them". The waiting list, which is most of the
/// names, opens collapsed: complete inside, and not the first thing on the page.
export async function ClassIndex({ cls }: { cls: AssetClass }) {
  const [rows, health, excluded] = await loadOrDefer(() =>
    Promise.all([cachedDecisionRows(), cachedSourceHealth(), getPoolExclusions()]),
  );
  const today = todayISO();

  const all = scoreRows(rows, health, today);
  const mine = all.filter(cls.holds);

  // Published calls only (lib/quality.ts); the rest are named, folded, with the rule each failed.
  const longs = mine.filter((s) => s.decision.action === "LONG" && isPublished(s)).sort(byConfidence);
  const shorts = mine.filter((s) => s.decision.action === "SHORT" && isPublished(s)).sort(byConfidence);
  const withheld = mine.filter((s) => s.decision.action !== "WAIT" && !isPublished(s));

  // The waiting list, split the way the overview has always split it and this page did not.
  //
  // Rule 40: a developing row is **lifted out** of the WAIT list rather than added beside it. The
  // front page does that; these five index pages did not, so a name with a measured direction and
  // one named shortfall was filed under "no direction today" next to a name whose feed is dead.
  // Measured 2026-10-09: 203 of the 214 refused names carry a forming read, so this was almost
  // the whole list -- `/crypto` said "32 waiting" when 14 of those had a direction and a number
  // saying how far off it was.
  //
  // Nothing here changes a verdict. Every one of these is still `action: "WAIT"`, still graded
  // Low, and still carries the word "potential" on its own page. What changes is that the reader
  // is told which of the two kinds of waiting a name is, which is the distinction `WaitBasis` and
  // `Developing` were both built to make and which this page was collapsing.
  const allWaits = mine.filter((s) => s.decision.action === "WAIT");
  const forming = allWaits.filter((s) => s.decision.developing !== null).sort(byCloseness);
  const waits = allWaits.filter((s) => s.decision.developing === null).sort(byConfidence);

  // The market's own state, counted from the rows below it (rule 93): newest close, newest run, source,
  // and where every name went. It replaced a header that called every held-back name "with no stored
  // price" -- 123 of them on /stocks had ended at their stop.
  const market = mine[0]?.market ?? null;
  const status = marketStatus(mine, all, health, market ? coverageLabelFor(market) : null);

  // Matched on the class's own slug rather than on the row's market word, because the two
  // vocabularies differ for exactly one class (`PSX` here, `PK` in the industry column) and a
  // mismatch would quietly show an empty list rather than an error.
  const ASSET_TYPE_OF: Record<string, string | null> = {
    crypto: "crypto", forex: "forex", commodities: "commodity", stocks: null, psx: null,
  };
  const wantType = ASSET_TYPE_OF[cls.slug];
  const NOUN: Record<string, string> = {
    crypto: "coin", forex: "pair", commodities: "contract", stocks: "name", psx: "name",
  };
  const outOfPool = excluded.filter((a) =>
    wantType !== null
      ? a.assetType === wantType
      : (a.assetType === "stock" || a.assetType === "etf") &&
        (cls.slug === "psx" ? a.market === "PK" : a.market !== "PK"),
  );

  return (
    <div className="space-y-2">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{cls.title}</h1>
        <p className="mt-2 max-w-2xl text-sm">{cls.lead}</p>
        <p className="text-muted-foreground mt-2 text-sm" data-market-status data-snapshot={rows[0]?.dataStamp ?? ""} data-run-state={status.runState} data-names={status.names} data-published={status.longs + status.shorts}>
          {marketStatusLines(status).join(" ")} {outcomeStatusOf(rows[0]?.outcome ?? null).sentence} Readings, not advice.
        </p>
      </div>

      {/* The complete list, first, flat and alphabetical. The analysis below it answers "what is
          there to do today"; this answers "where is the one I came for", and before 2026-10-21
          the page could only answer the first -- a name outside the active pool appeared nowhere
          at all, which on /crypto was ten of seventy-six coins. */}
      <AssetDirectory
        noun={NOUN[cls.slug] ?? "name"}
        rows={[
          ...mine.map((s) => ({ symbol: s.row.symbol, name: s.row.name, inPool: true })),
          ...outOfPool.map((a) => ({ symbol: a.symbol, name: a.name, inPool: false })),
        ].sort((a, b) => a.name.localeCompare(b.name))}
      />

      {mine.length === 0 ? (
        <Section title="Nothing stored yet">
          <Empty>
            No asset in this class has a stored reading. That is a gap in the data rather than a
            verdict: the pipeline writes one row per name per session, so an empty page here means
            the class has not been through a run.
          </Empty>
        </Section>
      ) : (
        <>
          {/* One block per sector, holding both directions.
              
              Two detached Long and Short sections answered "what should I do" first and buried
              the sector: a reader watching Banking had to read two lists and join them in their
              head. The action is still the first coloured thing in every row, so the directional
              question is a glance; what changes is that the sector is now a thing you can look
              at. Longs lead inside each block, then shorts, each best-evidenced first.
              
              Sectors past ten rows scroll inside themselves, so a 40-name sector is a box on the
              page rather than a page of its own. */}
          <Section
            title={`Directions (${longs.length + shorts.length})`}
            lead={`${longs.length} long and ${shorts.length} short, grouped by sector. Each block is best-evidenced first within its direction; the stop is the level the reading is wrong at.`}
          >
            <SectorBoard
              rows={[...longs, ...shorts].map(toListRow)}
              empty={
                <>
                  No call in this class passed the quality gate today. That is an answer rather than a
                  missing one: each withheld call is named below with the rule it failed.
                </>
              }
            />
          </Section>

          <WithheldList rows={withheld.map((s) => ({ symbol: s.row.symbol, name: s.row.name, reasons: s.gate?.reasons ?? [] }))} />

          {/* Rendered only when it has rows, which after 2026-10-09 is almost never: every
              measured direction now prints as an action, so `Decision.developing` is set at a
              gate nothing reaches. The block is kept rather than deleted because the rule behind
              it is sound and acting on every direction is a policy that may move again -- see
              brain.md 50. An always-empty section on five pages is clutter, so it waits. */}
          {forming.length ? (
          <DecisionList
            title={`Forming (${forming.length})`}
            lead="A direction is measured and not all of its confirmations are present. Not an action: each name's page says exactly what is missing and how far off it is."
            rows={forming.map(toListRow)}
            empty={
              <>
                Nothing in this class has a direction forming. Every name here either has one
                already or has no measured direction at all.
              </>
            }
          />
          ) : null}

          {/* Collapsed, and complete inside.

              This list is the index: it is where a reader looks a specific name up, so capping
              it would remove the only place a held-back name can be found. But it is also most of
              the page -- 175 of the 249 US names on the day this was written, which is a 1.3 MB
              document whose first screen is a table nobody came for.

              So it keeps every row and opens closed. Same `<details>` the overview uses for its
              industry cards, and for the same reason: a reader who wants it wants to be
              somewhere other than the two lists above. The count is in the summary, so what is
              inside is never a surprise and never looks like a gap. */}
          {/* Every priced name resolves to LONG or SHORT (lib/resolve.ts, brain.md rule 86), so this
              renders only for a name with no stored close at all -- none today. Kept so such a name is
              still listed somewhere, which is what the pool-parity check counts. */}
          {waits.length ? (
          <details className="border-border bg-muted/30 mt-6 rounded-lg border px-4 py-1 text-sm sm:py-3">
            <summary className="-my-1 cursor-pointer py-3 font-medium select-none sm:my-0 sm:py-0">
              Held back: {waits.length} {waits.length === 1 ? "name" : "names"} with no call today
            </summary>
            <div className="mt-2 pb-2">
              <DecisionList
                grouped
                title={`Held back (${waits.length})`}
                lead="No call could be made: the close is too old, the venue answered nothing, no stop level exists, or the price sits between its own averages with neither side measurable. Each row's own page says which."
                rows={waits.map(toListRow)}
                empty={<>Every name in this class has a direction.</>}
              />
            </div>
          </details>
          ) : null}
        </>
      )}

      {/* The rest of the registry.

          The lists above are the **active pool**, which is the right population for a list of
          calls: a name under its market's liquidity floor has no call to make. It is the wrong
          population for the other thing this page is -- the place a reader looks a name up. On
          2026-10-21 ten of the seventy-six coins in the registry were outside the pool, and
          /crypto answered "no such coin" for every one of them.

          So the registry is completed here rather than by widening the pool, which would put
          names with no call into the directions list. Each row says why it is out, in the pool
          job's own words, and links to its page, where the stored history and the brain's own
          read are unaffected by pool membership. */}
      {outOfPool.length ? (
        <details className="border-border bg-muted/30 mt-6 rounded-lg border px-4 py-1 text-sm sm:py-3">
          <summary className="-my-1 cursor-pointer py-3 font-medium select-none sm:my-0 sm:py-0">
            Also tracked, outside the pool: {outOfPool.length}{" "}
            {outOfPool.length === 1 ? "name" : "names"}
          </summary>
          <p className="text-muted-foreground mt-2 text-sm">
            These are in the registry and keep their stored history, and they are left out of the
            lists above because they are under their market&apos;s liquidity floor. No call is made
            for them; everything else on their own page still is.
          </p>
          <ul className="mt-3 mb-2 space-y-2">
            {outOfPool.map((a) => (
              <li key={a.id} className="border-border border-t pt-2 first:border-t-0 first:pt-0">
                <Link
                  href={`/asset/${encodeURIComponent(a.symbol)}`}
                  className="font-medium underline underline-offset-2"
                >
                  {a.name}
                </Link>{" "}
                <span className="text-muted-foreground num text-xs">{a.symbol}</span>
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {a.note ?? "Out of the pool; the job recorded no reason."}{" "}
                  {a.closes > 0
                    ? `${a.closes.toLocaleString()} stored closes, newest ${new Date(a.newestClose!).toISOString().slice(0, 10)}.`
                    : "No stored close."}
                </p>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <p className="text-muted-foreground mt-8 text-xs">
        Every reading here is the same one the name&apos;s own page shows, from the rule table in{" "}
        <code>lib/decision.ts</code>.{" "}
        <Link href="/methodology" className="underline underline-offset-2">
          How each number is measured, and what is missing
        </Link>
        .
      </p>
    </div>
  );
}
