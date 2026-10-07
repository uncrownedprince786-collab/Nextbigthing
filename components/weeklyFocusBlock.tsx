import Link from "next/link";
import { ConfidenceBadge, Pill } from "@/components/ui";
import { price } from "@/lib/format";
import type { Scored } from "@/lib/assetClass";
import { weeklyFocus, weeklyWhy, WEEKLY_MAX_PER_SIDE } from "@/lib/weeklyFocus";

/// The weekly focus block: the confirmed names, narrowed to what a reader could act on.
///
/// Every row here is already in the LONG or SHORT list further down the page. This block does not
/// decide anything — `lib/weeklyFocus.ts` only filters and orders — and the heading says so, so a
/// reader cannot take it for a stronger claim than the list it was drawn from.
///
/// The wording is the careful part. A setup **favours** a direction **while its stop holds**; it
/// does not go up. No target is printed: the measured analog range lives on the asset page, beside
/// the sample size and window that qualify it, and the same numbers lifted into a block headed
/// "this week" would read as a forecast.

function Row({ item }: { item: Scored }) {
  const { row, decision, market } = item;
  const currency = row.currency;
  const why = weeklyWhy(item);

  return (
    <li className="border-border min-w-0 border-t py-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <Link
          href={`/asset/${encodeURIComponent(row.symbol)}`}
          className="min-w-0 flex-1 truncate text-sm underline-offset-2 hover:underline"
          title={row.name}
        >
          <span className="num font-medium">{row.symbol}</span>{" "}
          <span className="text-muted-foreground">{row.name}</span>
        </Link>
        <span className="flex shrink-0 items-baseline gap-x-2">
          {decision.timeSense === "CARE" ? <Pill tone="warn">CARE</Pill> : null}
          <Pill tone={decision.action === "LONG" ? "up" : "down"}>{decision.action}</Pill>
          <ConfidenceBadge grade={decision.confidence.toLowerCase()} />
        </span>
      </div>

      <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
        {market}
        {" · "}
        {/* The one claim this block makes, and it is conditional on the stop by construction. */}
        Setup favours {decision.action === "LONG" ? "up" : "down"} while the exit level holds.
      </p>

      {why.length ? (
        <ul className="mt-1 space-y-0.5">
          {why.map((line, i) => (
            <li key={i} className="text-muted-foreground text-xs leading-relaxed">
              {line}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="text-muted-foreground mt-1 text-xs">
        Entry{" "}
        <span className="num">
          {decision.entry
            ? `${price(decision.entry.low, currency)} to ${price(decision.entry.high, currency)}`
            : "none stored"}
        </span>
        {" · "}Exit if wrong{" "}
        <span className="num">
          {decision.invalidation !== null ? price(decision.invalidation, currency) : "none stored"}
        </span>
        {decision.timeSense === "NOW" ? " · the last close is inside the band" : null}
      </p>
    </li>
  );
}

function Side({
  title,
  lead,
  items,
  total,
  empty,
}: {
  title: string;
  lead: string;
  items: Scored[];
  total: number;
  empty: string;
}) {
  return (
    <div className="border-border bg-card min-w-0 rounded-lg border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
        <span className="text-muted-foreground text-xs">
          {total === 0
            ? "none today"
            : total > items.length
              ? `${items.length} of ${total}`
              : `${items.length}`}
        </span>
      </div>
      <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{lead}</p>
      {items.length === 0 ? (
        <p className="text-muted-foreground mt-3 text-xs leading-relaxed">{empty}</p>
      ) : (
        <ul className="mt-3">
          {items.map((item) => (
            <Row key={item.row.symbol} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function WeeklyFocusBlock({ rows }: { rows: Scored[] }) {
  const focus = weeklyFocus(rows);
  const nothing = focus.long.length === 0 && focus.short.length === 0;

  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold tracking-tight">This week — tighter setups</h2>
      <p className="text-muted-foreground mt-1 mb-3 max-w-2xl text-sm">
        The same readings as the lists below, narrowed to the ones that carry a direction, a
        confirmation beyond the direction, an entry band and a level to be wrong at. Nothing here is
        a new verdict &mdash; it is the confirmed names, best evidenced first, capped at{" "}
        {WEEKLY_MAX_PER_SIDE} a side so the block stays readable. These are readings, not advice,
        and no outcome is promised.
      </p>

      {nothing ? (
        <div className="border-border bg-card rounded-lg border p-4">
          <p className="text-muted-foreground text-sm leading-relaxed">
            No name clears the filters today. That is an answer rather than a missing one: the rule
            table acted on {rows.filter((s) => s.decision.action !== "WAIT").length} names, and none
            of them carries both a confirmation beyond its own direction and a stored level to exit
            at. The full lists below are unchanged.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Side
            title="Long focus"
            lead="Setup up, longer view not against it, and at least one confirmation beyond the trend."
            items={focus.long}
            total={focus.longTotal}
            empty="Nothing on this side clears the filters today. The long list below is unchanged."
          />
          <Side
            title="Short focus"
            lead="Setup down, longer view not against it, and at least one confirmation beyond the trend."
            items={focus.short}
            total={focus.shortTotal}
            empty="Nothing on this side clears the filters today. The short list below is unchanged."
          />
        </div>
      )}

      <p className="text-muted-foreground mt-3 max-w-2xl text-xs leading-relaxed">
        How a name reaches this block is written out on the{" "}
        <Link href="/methodology" className="underline underline-offset-2">
          methodology page
        </Link>
        . No price target is shown here: the measured range from similar past days sits on each
        asset&rsquo;s own page, next to the sample size and window that qualify it.
      </p>
    </section>
  );
}
