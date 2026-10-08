import Link from "next/link";
import { Empty, Section } from "@/components/ui";
import { DecisionList } from "@/components/decision";
import { cachedDecisionRows, cachedSourceHealth } from "@/lib/cached";
import { todayISO } from "@/lib/decisionInput";
import { isoDate } from "@/lib/format";
import {
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
  const waits = mine.filter((s) => s.decision.action === "WAIT").sort(byConfidence);

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
          {waits.length} waiting. Readings, not advice.
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
          <DecisionList
            title={`Long (${longs.length})`}
            lead="Setup is up and the longer view does not disagree. The stop is the level the reading is wrong at."
            rows={longs.map(toListRow)}
            empty={
              <>
                Nothing in this class reads long today. That is an answer, not a missing one: the
                rules looked and found no name whose trend and confirmations agree.
              </>
            }
          />

          <DecisionList
            title={`Short (${shorts.length})`}
            lead="Setup is down and the longer view does not disagree."
            rows={shorts.map(toListRow)}
            empty={<>Nothing in this class reads short today.</>}
          />

          {/* Collapsed, and complete inside.

              This list is the index: it is where a reader looks a specific name up, so capping
              it would remove the only place a waiting name can be found. But it is also most of
              the page -- 175 of the 249 US names on the day this was written, which is a 1.3 MB
              document whose first screen is a table nobody came for.

              So it keeps every row and opens closed. Same `<details>` the overview uses for its
              industry cards, and for the same reason: a reader who wants it wants to be
              somewhere other than the two lists above. The count is in the summary, so what is
              inside is never a surprise and never looks like a gap. */}
          <details className="border-border bg-muted/30 mt-6 rounded-lg border px-4 py-1 text-sm sm:py-3">
            <summary className="-my-1 cursor-pointer py-3 font-medium select-none sm:my-0 sm:py-0">
              Waiting: {waits.length} {waits.length === 1 ? "name" : "names"} with no direction
              today
            </summary>
            <div className="mt-2 pb-2">
              <DecisionList
                title={`Waiting (${waits.length})`}
                lead="Conditions are incomplete, the close is stale, or the move has no published reason yet. Each row's own page says which."
                rows={waits.map(toListRow)}
                empty={<>Nothing in this class is waiting, which means every name has a direction.</>}
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
