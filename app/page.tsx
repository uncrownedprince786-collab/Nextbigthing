import type { Metadata } from "next";
import Link from "next/link";
import { unstable_cache } from "next/cache";
import { Card, Note, Section } from "@/components/ui";
import { getFreshness, getMarketOverview } from "@/lib/queries";
import { marketHasValidatedSignal, validatedHorizons } from "@/lib/signalValidation";
import { UNIVERSE_SIZE } from "@/lib/cryptoUniverse";

/// The overview — the first step of the journey, and deliberately small.
///
/// **What this page used to be, and why it is not that any more.** Until 2026-10-20 the root
/// served a heading that read "Today's calls: LONG or SHORT" over several hundred rows of LONG
/// and SHORT candidates with confidence badges, drawn from the fixed rule table. Those readings
/// are real and they are still served — at `/readings`, and on each market's own index — but
/// they are **not** the trained brain, and a reader arriving at a page captioned "today's calls"
/// has no way to tell the difference between a deterministic rule firing and a model that has
/// survived testing. Exactly one lane has survived testing. A homepage that opened with hundreds
/// of directional calls was, in effect, claiming the opposite.
///
/// So the root is now the choice a reader actually has to make first — which market — and says
/// for each one whether anything there has been validated. Four of the five say no.
///
/// The counts and freshness are read live and stay deliberately thin: how many instruments, how
/// recent the stored close. Enough to tell a working pipeline from a stopped one, and not a
/// second copy of the market pages, which are one click away and do that job properly.
export const revalidate = 900;

export const metadata: Metadata = {
  title: "NextBigThing — market research from free public data",
  description:
    "Pick a market, an instrument and a trading style, and see what the brain says — where a "
    + "direction has survived testing. Every figure names its source and its as-of date. No "
    + "forecasts presented as fact, no paid data.",
};

const HOUR = { revalidate: 3600 };
const cachedMarkets = unstable_cache(getMarketOverview, ["market-overview-home"], HOUR);
const cachedFreshness = unstable_cache(getFreshness, ["freshness-home"], HOUR);

/// The five markets, in reading order, each with the index it opens on. The hrefs are the
/// existing published list routes: those pages already show a market's instruments with their
/// stored freshness, which is exactly the second step of the journey.
const MARKETS = [
  { key: "US", href: "/stocks", label: "Stocks", blurb: "US listings and funds" },
  { key: "PK", href: "/psx", label: "PSX", blurb: "Pakistan Stock Exchange" },
  { key: "Crypto", href: "/crypto", label: "Crypto", blurb: "Every coin three venues trade" },
  { key: "FX", href: "/forex", label: "Forex", blurb: "Currency pairs" },
  { key: "Commodity", href: "/commodities", label: "Commodities", blurb: "Metals and energy" },
] as const;

function day(d: Date | string | null | undefined): string {
  return d ? new Date(d).toISOString().slice(0, 10) : "—";
}

export default async function HomePage() {
  const [markets, fresh] = await Promise.all([
    cachedMarkets().catch(() => null),
    cachedFreshness().catch(() => null),
  ]);
  const counts = new Map((markets ?? []).map((m) => [m.market, m.assets]));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Market research from free public data
        </h1>
        <p className="mt-3 max-w-2xl text-sm">
          Pick a market, then an instrument, then the trading style you have in mind. The brain
          gives a direction only where one has survived testing. Everything else says so, rather
          than filling the space with a number nobody measured.
        </p>
        <p className="text-muted-foreground mt-2 text-sm">
          Read only. Nothing here is advice, and no figure is a promise that anything will happen.
        </p>
      </div>

      <Section title="Choose a market">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {MARKETS.map((m) => {
            const proven = marketHasValidatedSignal(m.key);
            const horizons = validatedHorizons(m.key);
            // Crypto is counted from the venues' own instrument lists, not from the stored
            // registry. The registry is the 76 coins the daily job collects closes for; the
            // crypto pages serve every coin a venue trades, and the card said 76 while the page
            // behind it listed 2,324.
            const n = m.key === "Crypto" ? UNIVERSE_SIZE : counts.get(m.key);
            return (
              <Link
                key={m.key}
                href={m.href}
                className="border-border hover:border-foreground/30 hover:bg-muted/50 rounded-xl border px-5 py-4 transition"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-lg font-medium">{m.label}</span>
                  {n ? (
                    <span className="text-muted-foreground text-xs">{n} instruments</span>
                  ) : null}
                </div>
                <div className="text-muted-foreground mt-1 text-sm">{m.blurb}</div>
                <div className="mt-3">
                  {proven ? (
                    <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-700 dark:text-amber-400">
                      Validated · {horizons.map((h) => `${h} sessions`).join(", ")}
                    </span>
                  ) : (
                    <span className="text-muted-foreground border-border rounded-full border px-2.5 py-1 text-xs">
                      No validated signal
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      </Section>

      <Section title="What the badge means">
        <Card>
          <p className="text-sm">
            A market is marked <strong>validated</strong> only where a direction has beaten a
            baseline knowable at the time, survived a bootstrap that resamples whole trading
            sessions rather than rows, held its sign in every walk-forward fold, and moved the
            price the way it claimed. One lane clears all four today: US equities over five
            sessions, long side only.
          </p>
          <p className="text-muted-foreground mt-3 text-sm">
            A confidence badge never reads HIGH. Everything validated so far is validated on a
            historical holdout, which is still a backtest — HIGH is reserved for a lane whose
            prospective calls have matured and been graded. The first of those mature on
            2026-10-23.
          </p>
        </Card>
      </Section>

      <Section title="Where the data stands">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Card>
            <div className="text-muted-foreground text-xs">Newest stored close</div>
            <div className="mt-1 text-lg font-medium">{day(fresh?.snap._max.date)}</div>
          </Card>
          <Card>
            <div className="text-muted-foreground text-xs">Newest headline</div>
            <div className="mt-1 text-lg font-medium">{day(fresh?.news._max.publishedAt)}</div>
          </Card>
          <Card>
            <div className="text-muted-foreground text-xs">Instruments covered</div>
            <div className="mt-1 text-lg font-medium">
              {[...counts.values()].reduce((a, b) => a + b, 0) || "—"}
            </div>
          </Card>
        </div>
        <Note>
          Freshness per market, per source, with the lane that fixes each one, is on{" "}
          <Link href="/status" className="underline underline-offset-2">status</Link>. The five
          markets side by side, with what each can and cannot be judged on, is on{" "}
          <Link href="/markets" className="underline underline-offset-2">markets</Link>.
        </Note>
      </Section>

      <Section title="The rule-table readings">
        <Note>
          Separately from the brain, the site reads every covered instrument through a fixed rule
          table and publishes one reading each. Those are deterministic rules over stored data,
          not a trained model, and they are kept apart for that reason.{" "}
          <Link href="/readings" className="font-medium underline underline-offset-2">
            See the full reading list →
          </Link>
        </Note>
      </Section>
    </div>
  );
}
