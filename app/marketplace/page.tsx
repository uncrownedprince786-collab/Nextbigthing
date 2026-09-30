import type { Metadata } from "next";
import Link from "next/link";
import { AsOf, Empty, HowToRead, Note, Pill, Section, Table } from "@/components/ui";
import { getMarketplace } from "@/lib/queries";
import { isoDate } from "@/lib/format";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Marketplace rankings",
  description:
    "The first page of Amazon's Best Sellers charts for the categories this site follows, stored as read, with each listing's movement against the previous stored run.",
};

/// How a listing moved against the previous stored run of the same category.
///
/// A listing absent from the previous run is reported as new, never as a rise from
/// position 31. It may have been at 31 or at 4,000, and the page did not publish either,
/// so there is no move to state.
function Move({ rank, previousRank }: { rank: number; previousRank: number | null }) {
  if (previousRank == null) {
    return <Pill>new to this chart</Pill>;
  }
  const diff = previousRank - rank;
  if (diff === 0) return <span className="text-muted-foreground text-xs">unchanged</span>;
  return (
    <Pill tone={diff > 0 ? "up" : "down"}>
      {diff > 0 ? "up" : "down"} {Math.abs(diff)} from {previousRank}
    </Pill>
  );
}

export default async function MarketplacePage() {
  const { periodEnd, items } = await getMarketplace();

  const byCategory = new Map<string, typeof items>();
  for (const it of items) {
    if (!byCategory.has(it.categorySlug)) byCategory.set(it.categorySlug, []);
    byCategory.get(it.categorySlug)!.push(it);
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
        Marketplace rankings
      </h1>
      <p className="text-muted-foreground mt-2 max-w-3xl text-sm">
        The first page of Amazon&apos;s public Best Sellers chart for each category this
        site follows, stored exactly as it was published on the day it was read. Movement
        is measured against the previous stored run of the same category.
      </p>

      <Note>
        This is deliberately not part of any product&apos;s demand score. A search trend
        says people are looking; a bestseller rank says one listing is outselling others in
        its category. Averaging the two would produce a number whose meaning depended on
        which sources happened to answer that week.
      </Note>

      <HowToRead
        title="How to read a bestseller rank, and what it cannot tell you"
        points={[
          <>
            <strong>A rank is relative, and the scale is hidden.</strong> Position 1 in
            Garden and Outdoor and position 1 in Electronics are not comparable volumes.
            Amazon publishes the order, never the units, so nothing here says how much of
            anything sold.
          </>,
          <>
            <strong>Movement is the useful part, not position.</strong> A listing holding
            the top spot for months tells you the category is settled. A listing new to the
            chart, or up twenty places, is the thing worth looking at.
          </>,
          <>
            <strong>&ldquo;New to this chart&rdquo; means exactly that.</strong> The
            listing was not in the previous stored run of the top thirty. It might have
            been at 31 or nowhere near; the page does not publish positions past thirty, so
            no rise is claimed.
          </>,
          <>
            <strong>One listing is not a category.</strong> A single product at the top can
            be a brand with a large advertising budget. Several new entrants in the same
            category within a few weeks is the pattern that is harder to buy.
          </>,
          <>
            <strong>Check the date.</strong> These charts move daily and this table is a
            snapshot of one run. It is evidence about the day it was read, nothing more.
          </>,
        ]}
      />

      {periodEnd ? (
        [...byCategory.entries()].map(([slug, rows]) => {
          const fresh = rows.filter((r) => r.previousRank == null).length;
          const climbers = rows.filter(
            (r) => r.previousRank != null && r.previousRank - r.rank >= 5,
          ).length;
          return (
            <Section
              key={slug}
              title={rows[0].categoryName}
              lead={
                rows.some((r) => r.previousRank != null)
                  ? `${fresh} of these ${rows.length} positions were not in the previous stored run, and ${climbers} climbed five places or more.`
                  : `First stored run of this category, so no movement can be reported yet.`
              }
              aside={<AsOf date={periodEnd} />}
            >
              <Table
                head={
                  <>
                    <th className="px-3 py-2 font-medium">#</th>
                    <th className="px-3 py-2 font-medium">Listing</th>
                    <th className="px-3 py-2 font-medium">Since the last run</th>
                  </>
                }
              >
                {rows.map((it) => (
                  <tr key={it.id}>
                    <td className="num text-muted-foreground px-3 py-2">{it.rank}</td>
                    <td className="px-3 py-2">
                      <a
                        href={it.url}
                        rel="noopener noreferrer nofollow"
                        target="_blank"
                        className="underline underline-offset-2"
                      >
                        {it.title}
                      </a>
                    </td>
                    <td className="px-3 py-2">
                      <Move rank={it.rank} previousRank={it.previousRank} />
                    </td>
                  </tr>
                ))}
              </Table>
            </Section>
          );
        })
      ) : (
        <Section title="Nothing stored yet">
          <Empty>
            No marketplace run has been stored. The job is{" "}
            <code>python jobs/marketplace.py</code> and it runs weekly.
          </Empty>
        </Section>
      )}

      <Section title="What is not here">
        <div className="text-muted-foreground max-w-3xl space-y-3 text-sm leading-relaxed">
          <p>
            <strong>eBay.</strong> The sold and completed listings search returns 403 to an
            ordinary request and there is no free public endpoint behind it. It is absent
            rather than estimated from something else.
          </p>
          <p>
            <strong>Sales volumes, revenue and margin.</strong> No marketplace publishes
            these for free, and none of them can be derived from a rank.
          </p>
          <p>
            <strong>Anything past position thirty.</strong> Only the first page of each
            chart is rendered server side. The rank counter restarts on the second page, so
            reading it would mean guessing an offset and mislabelling every row.
          </p>
          <p>
            <strong>Local marketplaces.</strong> Daraz, OLX and Facebook Marketplace
            publish no free ranking endpoint. Where a local angle is worth checking, the
            product pages say what to check by hand rather than showing a number that does
            not exist.
          </p>
        </div>
      </Section>

      <p className="text-muted-foreground mt-8 text-xs">
        Source: Amazon Best Sellers, first page of each category, read{" "}
        {isoDate(periodEnd)}. See{" "}
        <Link href="/methodology" className="underline underline-offset-2">
          methodology
        </Link>
        .
      </p>
    </div>
  );
}
