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
import { getEvent, getEventImpacts, getEventWindows } from "@/lib/queries";
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
  const byWindow = await Promise.all(
    windows.map(async (w) => ({ window: w, ...(await getEventImpacts(e.id, w)) })),
  );
  const line = e.analysis[0];

  return (
    <div>
      <p className="text-muted-foreground text-xs">
        <Link href="/events" className="underline underline-offset-2">
          Event windows
        </Link>
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{e.name}</h1>
        <Pill>{e.category}</Pill>
      </div>
      <p className="text-muted-foreground num mt-1 text-sm">{longDate(e.date)}</p>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed">{e.summary}</p>
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

      <Note>
        Everything below is a price change over a fixed window that begins on the date
        above. It is not a measurement of what the event did. Markets move every day for
        reasons that have nothing to do with any one headline, and in a window this long
        most of them did.
      </Note>

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
        <Section title="Nothing measurable">
          <Empty>
            No asset on this site has stored closes on both sides of this window, so
            nothing is measured. That is a gap in the stored price history rather than a
            finding about the event.
          </Empty>
        </Section>
      )}
    </div>
  );
}
