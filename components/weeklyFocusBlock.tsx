import Link from "next/link";
import { ConfidenceBadge, Pill } from "@/components/ui";
import { price } from "@/lib/format";
import type { Scored } from "@/lib/assetClass";
import type { Market } from "@/lib/decision";
import {
  weeklyFocus,
  weeklyWhy,
  weeklyTarget,
  targetMethodLabel,
  WEEKLY_MAX_PER_SIDE,
} from "@/lib/weeklyFocus";

/// The block that prepares a reader for the week ahead.
///
/// Its job is not to rank anything. It is to put, in one place, the names that already carry a
/// confirmed direction together with the three levels a reader needs before the week starts: where
/// the setup is live, where it is wrong, and where the measurement says it would have run its
/// course. Everything in it is already published further down the page; this block only filters,
/// orders and adds the measured exit.
///
/// Two things it must never become. It must not become a second rule table — `lib/weeklyFocus.ts`
/// subtracts and orders, it never promotes. And it must not become a forecast: a setup **favours**
/// a direction **while its stop holds**, every target is a measured level with its method named
/// beside it, and a name with no stored target says so rather than being given one.

/// Every market a reader can browse, so the block can account for all of them rather than let a
/// quiet one vanish. A market with nothing confirmed is a finding; a market silently missing is a
/// reader wondering whether it was looked at.
const MARKETS: Market[] = ["US", "PSX", "Crypto", "FX", "Commodity"];
const MARKET_LABEL: Record<string, string> = {
  US: "US",
  PSX: "PSX",
  Crypto: "Crypto",
  FX: "Forex",
  Commodity: "Commodities",
};

function Row({ item }: { item: Scored }) {
  const { row, decision, market } = item;
  const currency = row.currency;
  const why = weeklyWhy(item);
  const target = weeklyTarget(item);
  const long = decision.action === "LONG";
  const single = target ? target.low === target.high : false;

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
          <Pill tone={long ? "up" : "down"}>{decision.action}</Pill>
          <ConfidenceBadge grade={decision.confidence.toLowerCase()} />
        </span>
      </div>

      <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
        {MARKET_LABEL[market] ?? market}
        {" · "}
        Setup favours {long ? "up" : "down"} while the exit level holds.
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

      {/* The three levels, in the order a reader uses them: where it is live, where it is wrong,
          where the measurement says it would have run its course. */}
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
        <div className="min-w-0">
          <dt className="text-muted-foreground">Entry zone</dt>
          <dd className="num">
            {decision.entry
              ? `${price(decision.entry.low, currency, market)} to ${price(decision.entry.high, currency, market)}`
              : "no entry band measured"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Stop loss</dt>
          <dd className="num text-down">
            {decision.invalidation !== null ? price(decision.invalidation, currency, market) : "no stop level set"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Take profit</dt>
          <dd className={target ? "num" : "text-muted-foreground"}>
            {target
              ? single
                ? price(target.low, currency, market)
                : `${price(target.low, currency, market)} to ${price(target.high, currency, market)}`
              : "No clear target stored"}
          </dd>
        </div>
      </dl>

      {target ? (
        <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
          Prefer exit near{" "}
          <span className="num">{price(target.low, currency, market)}</span>; cut if{" "}
          <span className="num">
            {decision.invalidation !== null ? price(decision.invalidation, currency, market) : "the stop"}
          </span>{" "}
          breaks. Measured from {targetMethodLabel(target.method)} &mdash; a measured level, not a
          promise.
        </p>
      ) : (
        <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
          No target was measured for this setup, so none is shown. The stop above still applies.
        </p>
      )}
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
            ? "none this week"
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

/// One line per market, so a quiet market is accounted for rather than absent.
function Coverage({ rows }: { rows: Scored[] }) {
  const counts = MARKETS.map((m) => {
    const inMarket = rows.filter((s) => s.market === m);
    const confirmed = weeklyFocus(inMarket, Number.MAX_SAFE_INTEGER);
    return {
      market: m,
      names: inMarket.length,
      ready: confirmed.longTotal + confirmed.shortTotal,
    };
  });

  return (
    <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
      Every market is looked at:{" "}
      {counts.map((c, i) => (
        <span key={c.market}>
          {i > 0 ? " · " : ""}
          <span className="text-foreground">{MARKET_LABEL[c.market]}</span>{" "}
          {c.ready > 0 ? `${c.ready} ready` : "nothing confirmed"}
          <span className="opacity-60"> of {c.names}</span>
        </span>
      ))}
      . A market with nothing confirmed is a reading, not an omission: the rules looked and found no
      name there carrying both a direction and a confirmation beyond it.
    </p>
  );
}

export function WeeklyFocusBlock({ rows }: { rows: Scored[] }) {
  const focus = weeklyFocus(rows);
  const nothing = focus.long.length === 0 && focus.short.length === 0;

  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold tracking-tight">For the coming week</h2>
      <p className="text-muted-foreground mt-1 mb-3 max-w-2xl text-sm">
        What to have in front of you before the week starts. These are the names that already carry
        a direction and a confirmation beyond it, each with the three levels you would need: where
        the setup is live, where it is wrong, and where the measurement says it would have run its
        course. Nothing here is a new verdict &mdash; it is the same readings as the lists below,
        best evidenced first, capped at {WEEKLY_MAX_PER_SIDE} a side. Readings, not advice, and no
        outcome is promised.
      </p>

      {nothing ? (
        <div className="border-border bg-card rounded-lg border p-4">
          <p className="text-muted-foreground text-sm leading-relaxed">
            No name clears the filters going into this week. That is an answer rather than a missing
            one: the rule table acted on{" "}
            {rows.filter((s) => s.decision.action !== "WAIT").length} names, and none carries both a
            confirmation beyond its own direction and a stored level to exit at. The full lists
            below are unchanged.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Side
            title="Long side"
            lead="Setup up, longer view not against it, and at least one confirmation beyond the trend."
            items={focus.long}
            total={focus.longTotal}
            empty="Nothing on this side clears the filters going into this week. The long list below is unchanged."
          />
          <Side
            title="Short side"
            lead="Setup down, longer view not against it, and at least one confirmation beyond the trend."
            items={focus.short}
            total={focus.shortTotal}
            empty="Nothing on this side clears the filters going into this week. The short list below is unchanged."
          />
        </div>
      )}

      <Coverage rows={rows} />

      <p className="text-muted-foreground mt-2 max-w-2xl text-xs leading-relaxed">
        How a name reaches this block, and how the exit level is measured, is written out on the{" "}
        <Link href="/methodology" className="underline underline-offset-2">
          methodology page
        </Link>
        . Every target is one measured method, named beside it and never an average of several, and
        a setup with no stored target is shown without one.
      </p>
    </section>
  );
}
