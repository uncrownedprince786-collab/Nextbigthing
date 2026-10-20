import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Empty, Note, Section, Table } from "@/components/ui";
import { getIndustry } from "@/lib/queries";
import { marketOf } from "@/lib/decisionInput";
import { MARKET_LABELS, canonicalMarket } from "@/lib/marketCapability";

/// Screen 2, one level down — the instruments inside an industry.
///
/// Symbols are shown exactly as stored. A Karachi listing, a coinpaprika id and a Yahoo ticker
/// are not the same kind of name, and normalising them for tidiness would make them un-lookupable
/// against their own sources.
///
/// Each instrument's market is read with `marketOf` rather than the industry's own `market` column,
/// because an industry can hold instruments from more than one market: the "Crypto" group is filed
/// in the database under US, and its coins trade in neither. The market column on the row is the
/// instrument's, and the note lists every market the industry actually spans.
export const revalidate = 3600;

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> },
): Promise<Metadata> {
  const { slug } = await params;
  const ind = await getIndustry(slug).catch(() => null);
  return { title: ind?.name ?? "Industry" };
}

export default async function IndustryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const ind = await getIndustry(slug).catch(() => null);
  if (!ind) notFound();

  const markets = [
    ...new Set(
      ind.assets
        .map((a) => canonicalMarket(marketOf({ assetType: a.assetType, industry: { market: ind.market } })))
        .filter((m): m is NonNullable<ReturnType<typeof canonicalMarket>> => m !== null),
    ),
  ];

  return (
    <>
      <Section title={ind.name}>
        <Note>
          {ind.assets.length} instrument{ind.assets.length === 1 ? "" : "s"} stored in this
          industry
          {markets.length === 1
            ? <>, in <strong>{MARKET_LABELS[markets[0]]}</strong></>
            : markets.length > 1
              ? <>: {markets.map((m) => MARKET_LABELS[m]).join(", ")}</>
              : null}
          . Symbols are shown as the source publishes them.
        </Note>
        {ind.assets.length === 0 ? (
          <Empty>No instruments are stored in this industry.</Empty>
        ) : (
          <Table
            head={
              <>
                <th className="px-3 py-2 text-left">Symbol</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-left">Kind</th>
                <th className="px-3 py-2 text-left">Market</th>
                <th className="px-3 py-2 text-left">Currency</th>
              </>
            }
          >
            {ind.assets.map((a) => {
              const market = canonicalMarket(
                marketOf({ assetType: a.assetType, industry: { market: ind.market } }),
              );
              return (
                <tr key={a.id}>
                  <td className="px-3 py-2 font-mono text-xs">
                    <Link href={`/asset/${encodeURIComponent(a.symbol)}`}
                          className="underline underline-offset-2">
                      {a.symbol}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{a.name}</td>
                  <td className="px-3 py-2">{a.assetType}</td>
                  <td className="px-3 py-2">
                    {market ? MARKET_LABELS[market] : <span className="text-muted-foreground">not classified</span>}
                  </td>
                  <td className="px-3 py-2">{a.currency}</td>
                </tr>
              );
            })}
          </Table>
        )}
      </Section>
    </>
  );
}
