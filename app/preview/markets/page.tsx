import type { Metadata } from "next";
import Link from "next/link";
import { Empty, Note, Section, Table } from "@/components/ui";
import { getIndustriesByMarket } from "@/lib/queries";

/// Screen 2 — market explorer, the top of the browse path.
///
/// `getIndustries` returns `_count.assets` and no asset list, so this screen is markets and their
/// industries with counts, and the instruments themselves come from `getIndustry(slug)` one level
/// down. That is the shape of the data rather than a design preference: listing every instrument
/// here would mean a second query per industry, and the count is what a reader scanning markets
/// actually wants.
export const revalidate = 3600;
export const metadata: Metadata = { title: "Markets" };

const MARKET_NAME: Record<string, string> = {
  US: "United States", PK: "Pakistan (PSX)", FX: "Foreign exchange",
};

export default async function MarketsPage() {
  const groups = await getIndustriesByMarket().catch(() => []);

  if (groups.length === 0) {
    return (
      <Section title="Markets">
        <Empty>
          No industries could be read. This is a read failure, not an empty universe — the two
          would look identical if this said &ldquo;no markets&rdquo;.
        </Empty>
      </Section>
    );
  }

  return (
    <>
      <Note>
        Every industry the site covers, by market. Counts are instruments in the stored universe,
        not instruments with a reading today.
      </Note>
      {groups.map(([market, industries]) => (
        <Section key={market} title={MARKET_NAME[market] ?? market}>
          <Table
            head={
              <tr>
                <th className="px-3 py-2 text-left">Industry</th>
                <th className="px-3 py-2 text-right">Instruments</th>
              </tr>
            }
          >
            {industries.map((ind) => (
              <tr key={ind.id}>
                <td className="px-3 py-2">
                  <Link href={`/preview/markets/${ind.slug}`} className="underline underline-offset-2">
                    {ind.name}
                  </Link>
                </td>
                <td className="px-3 py-2 text-right">{ind._count.assets}</td>
              </tr>
            ))}
          </Table>
        </Section>
      ))}
    </>
  );
}
