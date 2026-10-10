import Link from "next/link";
import { Empty, Section } from "@/components/ui";
import { DecisionList, SectorBoard } from "@/components/decision";
import { cachedDecisionRows, cachedSourceHealth } from "@/lib/cached";
import { todayISO } from "@/lib/decisionInput";
import { isoDate } from "@/lib/format";
import {
  byCloseness,
  byConfidence,
  scoreRows,
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
  const [rows, health] = await Promise.all([cachedDecisionRows(), cachedSourceHealth()]);
  const today = todayISO();

  const all = scoreRows(rows, health, today);
  const mine = all.filter(cls.holds);

  const longs = mine.filter((s) => s.decision.action === "LONG").sort(byConfidence);
  const shorts = mine.filter((s) => s.decision.action === "SHORT").sort(byConfidence);

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

  // Newest stored close across this class, compared as text: `yyyy-mm-dd` sorts correctly as text,
  // and anything that came back through the cache is a string now whatever its type says.
  const asOf = mine.reduce<string | null>((newest, s) => {
    const d = s.row.closeDate ? isoDate(s.row.closeDate) : null;
    if (!d || d === "no date") return newest;
    return newest === null || d > newest ? d : newest;
  }, null);

  return (
    <div className="space-y-2">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{cls.title}</h1>
        <p className="mt-2 max-w-2xl text-sm">{cls.lead}</p>
        <p className="text-muted-foreground mt-2 text-sm">
          {mine.length} {mine.length === 1 ? "name" : "names"}, priced to{" "}
          {asOf ?? "no stored close"}. {longs.length} long, {shorts.length} short,{" "}
          {forming.length ? `${forming.length} forming, ` : ""}
          {waits.length} held back. Readings, not advice.
        </p>
      </div>

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
                  Nothing in this class carries a direction today. That is an answer rather than a
                  missing one: the rules refuse a direction without a level to be wrong at.
                </>
              }
            />
          </Section>

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
          <details className="border-border bg-muted/30 mt-6 rounded-lg border px-4 py-1 text-sm sm:py-3">
            <summary className="-my-1 cursor-pointer py-3 font-medium select-none sm:my-0 sm:py-0">
              No direction: {waits.length} {waits.length === 1 ? "name" : "names"} with no measured
              direction at all
            </summary>
            <div className="mt-2 pb-2">
              <DecisionList
                grouped
                title={`No direction (${waits.length})`}
                lead="No direction could be read: the close is too old, the venue answered nothing, no stop level exists, or the price sits between its own averages with neither side measurable. Each row's own page says which."
                rows={waits.map(toListRow)}
                empty={<>Every name in this class has a direction.</>}
              />
            </div>
          </details>
        </>
      )}

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
