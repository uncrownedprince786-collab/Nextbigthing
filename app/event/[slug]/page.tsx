import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AsOf,
  ConfidenceBadge,
  Empty,
  HowToRead,
  Note,
  Pill,
  Section,
  Table,
} from "@/components/ui";
import {
  EVENT_HISTORY_MIN,
  getEvent,
  getEventCategoryHistory,
  getEventImpacts,
  getEventWindows,
} from "@/lib/queries";
import { isoDate, longDate, pct, price, toneClass } from "@/lib/format";

export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const e = await getEvent(slug);
  if (!e) return { title: "Event not found" };
  return {
    title: `${e.name}, ${isoDate(e.date)}`,
    description: `The largest measured price moves among the assets on this site in the weeks after ${isoDate(e.date)}. Measured, not explained.`,
  };
}

function ImpactTable({
  rows,
  caption,
}: {
  rows: Awaited<ReturnType<typeof getEventImpacts>>["risers"];
  caption: string;
}) {
  if (!rows.length) return <Empty>{caption} could not be measured.</Empty>;
  return (
    <Table
      head={
        <>
          <th className="px-3 py-2 font-medium">Asset</th>
          <th className="px-3 py-2 font-medium">Industry</th>
          <th className="px-3 py-2 text-right font-medium">Close at start</th>
          <th className="px-3 py-2 text-right font-medium">Close at end</th>
          <th className="px-3 py-2 text-right font-medium">Change</th>
          <th className="px-3 py-2 text-right font-medium">20 day volume</th>
          <th className="px-3 py-2 font-medium">Confidence</th>
        </>
      }
    >
      {rows.map((r) => (
        <tr key={r.id}>
          <td className="px-3 py-2">
            <Link
              href={`/asset/${encodeURIComponent(r.asset.symbol)}`}
              className="underline underline-offset-2"
            >
              {r.asset.name}
            </Link>
          </td>
          <td className="text-muted-foreground px-3 py-2">{r.asset.industry.name}</td>
          <td className="num px-3 py-2 text-right">
            {price(r.startClose, r.asset.currency)}
            <span className="text-muted-foreground ml-1 text-xs">
              {isoDate(r.startDate)}
            </span>
          </td>
          <td className="num px-3 py-2 text-right">
            {price(r.endClose, r.asset.currency)}
            <span className="text-muted-foreground ml-1 text-xs">{isoDate(r.endDate)}</span>
          </td>
          <td className={`num px-3 py-2 text-right font-medium ${toneClass(r.changePct)}`}>
            {pct(r.changePct, 1)}
          </td>
          <td className="num text-muted-foreground px-3 py-2 text-right">
            {r.volumeChangePct == null ? "not published" : pct(r.volumeChangePct)}
          </td>
          <td className="px-3 py-2" title={r.confidenceNote ?? undefined}>
            <ConfidenceBadge grade={r.confidence} />
          </td>
        </tr>
      ))}
    </Table>
  );
}

export default async function EventPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const e = await getEvent(slug);
  if (!e) notFound();

  const windows = await getEventWindows(e.id);
  // What past events of this same category were followed by. Measured, floor-gated, and
  // never presented as what this one will do.
  const history = await getEventCategoryHistory(e.category);
  const byWindow = await Promise.all(
    windows.map(async (w) => ({ window: w, ...(await getEventImpacts(e.id, w)) })),
  );
  // The stored line only for a date that has happened. The analysis job writes one row per
  // event, and for a scheduled date the sentence it produces reads "no asset has stored closes
  // on both sides of this window, that is a gap in the stored price history" — which is a
  // description of the future, graded "No data", above a window that nobody has failed to
  // measure yet. The note below says the same thing correctly, so this one is not printed.
  const line = e.scheduled ? null : e.analysis[0];

  return (
    <div>
      <p className="text-muted-foreground text-xs">
        <Link href="/events" className="underline underline-offset-2">
          Event calendar
        </Link>
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{e.name}</h1>
        <Pill>{e.category}</Pill>
      </div>
      <p className="text-muted-foreground num mt-1 text-sm">{longDate(e.date)}</p>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed">{e.summary}</p>
      <p className="text-muted-foreground mt-2 max-w-3xl text-xs leading-relaxed">
        {history.enough ? (
          <>
            Across {history.measured} past {e.category} events already measured here,{" "}
            {history.positive} were followed by a rise over {history.windowDays} days and{" "}
            {history.measured - history.positive} by a fall or no change. That is what was
            observed around similar dates, not what is expected around this one.
          </>
        ) : (
          <>
            Only {history.measured} past {e.category} event
            {history.measured === 1 ? " has" : "s have"} been measured here, below the floor of{" "}
            {EVENT_HISTORY_MIN} this site needs before reporting what followed similar dates.
            Nothing is inferred from a sample that small.
          </>
        )}
      </p>
      <p className="text-muted-foreground mt-2 text-xs">
        Date and description from {e.source}.{" "}
        <a
          href={e.sourceUrl}
          rel="noopener noreferrer nofollow"
          target="_blank"
          className="underline underline-offset-2"
        >
          Check the source
        </a>
      </p>

      {line ? (
        <div className="border-primary/30 bg-card mt-4 rounded-lg border-l-2 px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm leading-relaxed">{line.body}</p>
            <ConfidenceBadge grade={line.confidence} />
          </div>
          {line.dataNote ? (
            <p className="text-muted-foreground mt-2 text-xs">{line.dataNote}</p>
          ) : null}
        </div>
      ) : null}

      {/* The two kinds of event page, kept apart in the same words the index uses. A scheduled
          row is a date somebody published; nothing after it has been measured, because the
          window it would be measured over has not happened. Printing the "everything below is a
          price change" note over an empty table told a reader the measurement had failed, when
          what it had done was not started. */}
      {e.scheduled ? (
        <Note>
          This is a date the provider has published, not a measured window. Nothing after it has
          been measured yet, and nothing here sets a direction: a date this close marks the
          timing on an asset page and leaves the direction to the price and the news. Companies
          move these dates and a time is not always published, so the day is the claim.
        </Note>
      ) : (
        <Note>
          Everything below is a price change over a fixed window that begins on the date
          above. It is not a measurement of what the event did. Markets move every day for
          reasons that have nothing to do with any one headline, and in a window this long
          most of them did.
        </Note>
      )}

      {e.scheduled ? null : (
      <HowToRead
        points={[
          <>
            <strong>Read the two tables together.</strong> If the largest rise and the
            largest fall are both around the same size, the window was a volatile one and
            neither table describes it on its own.
          </>,
          <>
            <strong>The 14 day and 30 day windows answer different questions.</strong> A
            move present at 14 days and gone by 30 came back; a move that grows between
            them kept going. Neither says why.
          </>,
          <>
            <strong>Confidence here is about measurement only.</strong> It grades how many
            peers were measurable and how close the stored closes sit to the exact window
            edges. It says nothing about whether the move mattered.
          </>,
          <>
            <strong>Percentages compare across currencies, prices do not.</strong> The
            close columns are in each asset&apos;s own currency, so a Karachi listing shows
            rupees. The change column is comparable throughout.
          </>,
        ]}
      />
      )}

      {byWindow.length ? (
        byWindow.map(({ window, total, risers, fallers }) => (
          <Section
            key={window}
            title={`The ${window} days from ${isoDate(e.date)}`}
            lead={`${total} assets have stored closes on both sides of this window. Assets missing a close at either end are left out rather than counted as unchanged.`}
            aside={<AsOf date={e.date} />}
          >
            <h3 className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
              Largest rises
            </h3>
            <ImpactTable rows={risers} caption="Rises" />
            <h3 className="text-muted-foreground mt-6 mb-2 text-xs font-medium tracking-wide uppercase">
              Largest falls
            </h3>
            <ImpactTable rows={fallers} caption="Falls" />
          </Section>
        ))
      ) : (
        <Section title="Nothing measured">
          <Empty>
            {e.scheduled ? (
              <>
                This date has not arrived, so there is no window to measure over. Nothing will be
                measured here until it has passed and closes exist on both sides of it. The{" "}
                <Link href="/events" className="underline underline-offset-2">
                  event calendar
                </Link>{" "}
                lists it with the other dates still ahead.
              </>
            ) : (
              <>
                No asset on this site has stored closes on both sides of this window, so nothing
                is measured. That is a gap in the stored price history rather than a finding about
                the event.
              </>
            )}
          </Empty>
        </Section>
      )}
    </div>
  );
}
