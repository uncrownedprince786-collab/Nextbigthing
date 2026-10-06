import Link from "next/link";
import { Pill } from "@/components/ui";
import { byOpportunity, type AssetClass, type Scored } from "@/lib/assetClass";

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
function ClassCard({ cls, rows }: { cls: AssetClass; rows: Scored[] }) {
  const top = [...rows].sort(byOpportunity).slice(0, TOP_PER_CLASS);
  const directional = rows.filter((s) => s.decision.action !== "WAIT").length;

  return (
    <div className="border-border bg-card rounded-lg border p-4">
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

      {top.length === 0 ? (
        <p className="text-muted-foreground mt-3 text-xs">
          No stored reading yet. The pipeline writes one row per name per session, so this is a
          class that has not been through a run rather than a class with nothing in it.
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
export function TopByClass({ classes, rows }: { classes: AssetClass[]; rows: Scored[] }) {
  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold tracking-tight">Best evidenced, by market</h2>
      <p className="text-muted-foreground mt-1 mb-3 max-w-2xl text-sm">
        Five names per market, ordered by whether there is a reading to act on and how well
        evidenced it is. Follow a market for all of its names.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {classes.map((cls) => (
          <ClassCard key={cls.slug} cls={cls} rows={rows.filter(cls.holds)} />
        ))}
      </div>
    </section>
  );
}
