import Link from "next/link";
import { Pill } from "@/components/ui";
import { byOpportunity, marketStatus, marketStatusLines, type AssetClass, type MarketStatus, type Scored } from "@/lib/assetClass";
import { coverageLabelFor } from "@/lib/decisionInput";

/// How many names each class card carries.
///
/// 5, and the number is about the card rather than about the data: four cards of five rows is
/// twenty lines, which fits one screen beside a heading. Ten would make the reader scroll past the
/// browse block to reach the lists it is meant to introduce, which would make it a wall rather
/// than an index.
export const TOP_PER_CLASS = 5;

const TONE = { LONG: "up", SHORT: "down", WAIT: "default" } as const;

/// The best evidenced names in one class, as one card.
///
/// "Best evidenced" and not "best": the order is something-to-do before nothing-to-do, then
/// strongest evidence, then alphabetical -- see `byOpportunity`. Nothing is weighted and no score
/// is computed, because a score would be a new number the site would then have to source.
/// What a card says when it has no published call to list (rule 95). It is the market page's own status
/// sentence, from the same record, so "0 published" can no longer be printed as "never run": that card
/// used to tell readers that every class with no published call had never been run at all.
function emptyCardText(status: MarketStatus): string {
  if (status.runState === "NO_READING") {
    return "No decision run has logged this market yet, so this is a market with no reading rather than a reading with nothing in it.";
  }
  return marketStatusLines(status).slice(1).join(" ");
}

function ClassCard({ cls, rows, status }: { cls: AssetClass; rows: Scored[]; status: MarketStatus }) {
  // Published calls only (lib/quality.ts): a withheld call is not a signal on any list.
  const top = rows.filter((s) => s.decision.action !== "WAIT" && (s.gate ? s.gate.published : true)).sort(byOpportunity).slice(0, TOP_PER_CLASS);
  const directional = status.longs + status.shorts;

  return (
    // `min-w-0` is load-bearing on a phone and does nothing anywhere else. A grid item defaults
    // to `min-width: auto`, which refuses to shrink below its content's min-content width, and
    // the rows inside this card have a floor: a truncating name plus a `shrink-0` verdict pill
    // and a `w-12` confidence. Measured at 375px, every card laid out 411px wide inside a 343px
    // track -- and `main` is `overflow-x-clip`, so the extra 68px was not scrolled to, it was
    // cut off. What sat in the cut was the right-hand end of each row: part of the pill and the
    // whole confidence column, which is to say the verdict itself on the one layout where the
    // reader has the least room to begin with.
    <div
      className="border-border bg-card min-w-0 rounded-lg border p-4"
      data-market={cls.slug}
      data-run-state={status.runState}
      data-names={status.names}
      data-published={directional}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <Link
          href={`/${cls.slug}`}
          className="text-sm font-semibold tracking-tight underline-offset-2 hover:underline"
        >
          {cls.nav}
        </Link>
        <span className="text-muted-foreground text-xs">
          {rows.length} {rows.length === 1 ? "name" : "names"}
          {rows.length ? `, ${directional} with a direction` : ""}
        </span>
      </div>

      {top.length > 0 && status.runState === "RUN_INCOMPLETE_OR_FAILED" ? (
        <p className="text-warn mt-3 text-xs">{marketStatusLines(status)[1]}</p>
      ) : null}
      {top.length === 0 ? (
        <p className="text-muted-foreground mt-3 text-xs" data-card-status>
          {emptyCardText(status)}
        </p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {top.map((s) => (
            <li key={s.row.symbol} className="flex items-baseline justify-between gap-x-3">
              <Link
                href={`/asset/${encodeURIComponent(s.row.symbol)}`}
                className="min-w-0 flex-1 truncate text-sm underline-offset-2 hover:underline"
                title={s.row.name}
              >
                <span className="num font-medium">{s.row.symbol}</span>{" "}
                <span className="text-muted-foreground">{s.row.name}</span>
              </Link>
              <span className="flex shrink-0 items-baseline gap-x-2">
                <Pill tone={TONE[s.decision.action]}>{s.decision.action}</Pill>
                <span className="text-muted-foreground text-micro w-12 text-right">
                  {s.decision.confidence}
                </span>
                {/* Execution on every call (rules 94, 95), so this list never reads as a verified shortlist. */}
                {s.execution ? (
                  <span
                    className={`${s.execution.status === "checked" ? "text-muted-foreground" : "text-warn"} text-micro`}
                    title={s.execution.reasons.join("; ")}
                    data-execution={s.execution.status}
                  >
                    {s.execution.status}
                  </span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}

      <Link
        href={`/${cls.slug}`}
        className="text-muted-foreground hover:text-foreground mt-3 inline-block text-xs underline underline-offset-2"
      >
        All {rows.length} {cls.nav.toLowerCase()} &rarr;
      </Link>
    </div>
  );
}

/// The browse block: four classes, five names each, above the three lists.
///
/// Deliberately not filtered by the market and confidence chips below it. Those chips narrow the
/// three lists, and a browse block that emptied itself when a reader filtered the lists would be
/// answering a question nobody asked -- the point of this block is that it is always the whole
/// site, five rows at a time, whatever the lists are currently showing.
export function TopByClass({
  classes,
  rows,
  health,
}: {
  classes: AssetClass[];
  rows: Scored[];
  health: { source: string; status: string }[];
}) {
  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold tracking-tight">Best evidenced, by market</h2>
      <p className="text-muted-foreground mt-1 mb-3 max-w-2xl text-sm">
        Five names per market, ordered by whether there is a reading to act on and how well
        evidenced it is. Follow a market for all of its names.
      </p>
      {/* Five columns because there are five classes. At four, the fifth card dropped onto a
          row of its own and read as an afterthought rather than as one of the site's five
          top-level browse targets -- which is close to what commodities had been before they
          were separated out. The cards carry `min-w-0`, so a narrower track truncates a long
          name rather than overflowing the one before it. */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {classes.map((cls) => {
          const mine = rows.filter(cls.holds);
          const market = mine[0]?.market ?? null;
          // The same call the market page makes (components/classIndex.tsx), over the same rows.
          const status = marketStatus(mine, rows, health, market ? coverageLabelFor(market) : null);
          return <ClassCard key={cls.slug} cls={cls} rows={mine} status={status} />;
        })}
      </div>
    </section>
  );
}
