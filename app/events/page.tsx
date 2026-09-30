import type { Metadata } from "next";
import Link from "next/link";
import { Card, ConfidenceBadge, Empty, HowToRead, Note, Pill, Section } from "@/components/ui";
import { getEvents } from "@/lib/queries";
import { isoDate, longDate } from "@/lib/format";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Event windows",
  description:
    "What the largest measured price moves were in the weeks after a dated public event. The moves are measured; the reasons behind them are not, and no causation is claimed.",
};

const CATEGORY_TONE: Record<string, "default" | "warn" | "up" | "down"> = {
  conflict: "warn",
  policy: "default",
  technology: "up",
  market: "down",
};

export default async function EventsPage() {
  const events = await getEvents();

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Event windows</h1>
      <p className="text-muted-foreground mt-2 max-w-3xl text-sm">
        A short list of dated events from the public record, and the largest price moves
        among the assets on this site in the weeks that followed. The dates are sourced and
        the moves are measured from stored closes. Why anything moved is not measured here,
        and this page does not claim any event caused anything.
      </p>

      <Note>
        Over any thirty day window some asset has the largest move, whether or not anything
        happened. A big number in one of these tables is evidence that the asset moved. It
        is not evidence that the event moved it, and the two are easy to confuse precisely
        because the table puts them next to each other.
      </Note>

      <HowToRead
        title="How to read an event window"
        points={[
          <>
            <strong>Start with the window, not the number.</strong> The heading says how
            many days were measured and from what date. A move measured over 30 days
            contains everything else that happened in those 30 days too.
          </>,
          <>
            <strong>Look at both ends of the table.</strong> Each event page lists the
            largest rises and the largest falls. If they are similar in size, the window
            was volatile rather than directional, and a story told from the top of the
            table alone would be the opposite of one told from the bottom.
          </>,
          <>
            <strong>Check how many assets were measurable.</strong> An event from 2022 can
            be measured across most of the list; one from before the stored history starts
            cannot be measured at all, and the page says so rather than showing a short
            table that looks complete.
          </>,
          <>
            <strong>Compare the same asset across several events.</strong> An asset that
            appears at the top of every window is a volatile asset, not an asset uniquely
            sensitive to each of those events.
          </>,
        ]}
      />

      <Section title="Events" lead="Newest first. Each date links to its source.">
        {events.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {events.map((e) => {
              const line = e.analysis[0];
              return (
                <Card key={e.id} href={`/event/${e.slug}`}>
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="font-medium">{e.name}</h2>
                    <Pill tone={CATEGORY_TONE[e.category] ?? "default"}>{e.category}</Pill>
                  </div>
                  <p className="text-muted-foreground num mt-1 text-xs">
                    {longDate(e.date)}
                  </p>
                  <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
                    {e.summary}
                  </p>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <span className="text-muted-foreground text-xs">
                      {e._count.impacts
                        ? `${e._count.impacts} measured rows`
                        : "no stored closes span this window"}
                    </span>
                    {line ? <ConfidenceBadge grade={line.confidence} /> : null}
                  </div>
                </Card>
              );
            })}
          </div>
        ) : (
          <Empty>
            No event has been seeded yet. The list lives in <code>jobs/events.py</code> and
            is written by hand, because a detector would end up selecting the events that
            fit the moves.
          </Empty>
        )}
      </Section>

      <Section title="Why this list is short and written by hand">
        <div className="text-muted-foreground max-w-3xl space-y-3 text-sm leading-relaxed">
          <p>
            There is no automatic event feed here. If events were detected from the price
            series, the list would fill with whatever dates happen to sit next to large
            moves, and every row would then appear to confirm a relationship the selection
            had already created.
          </p>
          <p>
            So the events are chosen first, from the public record, with a source link for
            the date, and the measurement happens afterwards. That ordering is the only
            thing keeping this section honest, and it means the list is small.
          </p>
          <p>
            Adding one is an edit to <code>EVENTS</code> in <code>jobs/events.py</code>: a
            slug, a name, a date, a category, a factual summary and the URL the date came
            from. The next run measures it.{" "}
            <Link href="/methodology" className="underline underline-offset-2">
              The methodology page
            </Link>{" "}
            sets out the rest of the rules.
          </p>
        </div>
      </Section>

      <p className="text-muted-foreground mt-8 text-xs">
        Event dates are sourced individually and shown on each event page. Price moves are
        measured from closes stored by this site, as of {isoDate(new Date())}.
      </p>
    </div>
  );
}
