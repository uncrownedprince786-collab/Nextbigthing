import Link from "next/link";
import {
  AsOf,
  Card,
  ConfidenceBadge,
  CurrencyNote,
  Empty,
  HowToRead,
  Note,
  Pill,
  Section,
  Table,
} from "@/components/ui";
import {
  getAllIndustriesByBasis,
  getFreshness,
  getIndustriesByMarket,
  getLead,
  getProducts,
} from "@/lib/queries";
import { isoDate, money, pct, sizeLabel, toneClass } from "@/lib/format";

const MARKET_NAME: Record<string, string> = {
  US: "United States listings",
  PK: "Pakistan Stock Exchange",
};

const MARKET_LEAD: Record<string, string> = {
  US: "Seven sectors of US listed assets plus crypto, all quoted in dollars.",
  PK: "Eight Karachi sectors, quoted in rupees, read from the exchange's own end of day files. Size is published for the latest close only, because the exchange publishes a current share count with no history behind it.",
};

export const revalidate = 3600;

export default async function Home() {
  const [lead, byMarket, risers, sizeNow, risingProducts, fresh] = await Promise.all([
    getLead(),
    getIndustriesByMarket(),
    getAllIndustriesByBasis("rising"),
    getAllIndustriesByBasis("sizeNow"),
    getProducts("rising"),
    getFreshness(),
  ]);

  const byIndustry = new Map<string, typeof risers>();
  for (const r of risers) {
    if (!byIndustry.has(r.industryId)) byIndustry.set(r.industryId, []);
    byIndustry.get(r.industryId)!.push(r);
  }

  // Current size lives in its own table, keyed by asset. It cannot be read off a rising
  // row, whose value is a return rather than a size.
  const sizeByAsset = new Map(sizeNow.map((r) => [r.assetId, r]));
  const largestByIndustry = new Map<string, (typeof sizeNow)[number]>();
  for (const r of sizeNow) {
    const seen = largestByIndustry.get(r.industryId);
    if (!seen || r.rank < seen.rank) largestByIndustry.set(r.industryId, r);
  }
  // How many assets in each industry actually have a size figure. Precious metals is the
  // hard case: 3 of its 10 assets publish one, so "largest" there means largest of three
  // and the card has to say so.
  const sizeCountByIndustry = new Map<string, number>();
  for (const r of sizeNow) {
    sizeCountByIndustry.set(r.industryId, (sizeCountByIndustry.get(r.industryId) ?? 0) + 1);
  }

  return (
    <div className="space-y-2">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          What is gaining ground, measured from public data
        </h1>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm">
          Stocks, crypto, funds and consumer products are ranked by what can actually be
          observed: size, return against their own industry, and demand read from search,
          pageviews, forums and news. Every number names its source and its as of date.
          Nothing here is a prediction.
        </p>
        {lead ? (
          <p className="border-primary/30 bg-card mt-4 rounded-lg border-l-2 px-4 py-3 text-sm">
            {lead.body}
          </p>
        ) : null}
      </div>

      {byMarket.map(([market, industries]) => (
        <Section
          key={market}
          title={MARKET_NAME[market] ?? market}
          lead={MARKET_LEAD[market]}
          aside={<CurrencyNote currency={industries[0].currency} market={market} />}
        >
          <div className="grid gap-3 sm:grid-cols-2">
          {industries.map((ind) => {
            const top = byIndustry.get(ind.id)?.slice(0, 3) ?? [];
            const largest = largestByIndustry.get(ind.id);
            const l = largest?.asset;
            const assetTotal = ind._count.assets;
            const withSize = sizeCountByIndustry.get(ind.id) ?? 0;
            const partial = withSize > 0 && withSize < assetTotal;
            return (
              <Card key={ind.id} href={`/industry/${ind.slug}`}>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-medium">{ind.name}</h3>
                  <AsOf date={top[0]?.periodEnd} />
                </div>
                <p className="text-muted-foreground mt-1 text-xs">{ind.summary}</p>
                {l ? (
                  <p className="mt-3 text-sm">
                    Largest now:{" "}
                    <Link href={`/asset/${encodeURIComponent(l.symbol)}`} className="underline underline-offset-2">
                      {l.name}
                    </Link>{" "}
                    <span className="num">{money(largest.value, ind.currency)}</span>
                    <ConfidenceBadge grade={largest.confidence} className="ml-1.5 align-middle" />
                    <span className="text-muted-foreground ml-1.5 text-xs">
                      {sizeLabel(l.capBasis)}
                    </span>
                    {partial ? (
                      <span className="text-muted-foreground block text-xs">
                        Largest of the {withSize} of {assetTotal} assets here that publish a size
                        figure.
                      </span>
                    ) : null}
                  </p>
                ) : (
                  <p className="text-muted-foreground mt-3 text-sm">
                    No asset in this industry publishes a size figure, so there is nothing to
                    rank here. Returns are shown instead.
                  </p>
                )}
                {top.length ? (
                  <ul className="mt-2 space-y-0.5 text-sm">
                    {top.map((r) => (
                      <li key={r.id} className="flex items-center justify-between gap-3">
                        <span>{r.asset.name}</span>
                        <span className="flex items-center gap-2">
                          <span className={`num ${toneClass(r.value)}`}>{pct(r.value)}</span>
                          <ConfidenceBadge grade={r.confidence} />
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground mt-2 text-sm">
                    No 24 month ranking stored yet.
                  </p>
                )}
              </Card>
            );
          })}
          </div>
        </Section>
      ))}

      <HowToRead
        points={[
          <>
            <strong>Nothing here is a forecast.</strong> Every figure is something that
            has already happened, measured between two dates that are always shown.
          </>,
          <>
            <strong>The confidence badge grades the evidence, not the direction.</strong>{" "}
            High means the number is well measured. It does not mean the asset is a good
            one, and a high confidence fall is still a fall.
          </>,
          <>
            <strong>Compare percentages, not sizes, across markets.</strong> A return is a
            ratio and travels between currencies. A market capitalisation does not: the
            Karachi sectors are in rupees and their size figures are not comparable with
            the dollar figures above them.
          </>,
          <>
            <strong>&ldquo;Beat its peers&rdquo; is not &ldquo;went up&rdquo;.</strong> The
            relative strength table subtracts the industry average, so an asset can lead
            its sector while falling, if the sector fell further.
          </>,
          <>
            <strong>Check the freshness table at the bottom.</strong> If a job failed, the
            previous rows stay and the page keeps working. The dates there are how you
            find out.
          </>,
        ]}
      />

      <Section
        title="Strongest relative performers"
        lead="24 month return minus the average return of the asset's own industry. A positive number means the asset beat its peers, not that it went up. Each asset is only ever compared with its own industry, so a Karachi listing is measured against Karachi peers and the currency never enters the comparison."
        aside={<AsOf date={risers[0]?.periodEnd} />}
      >
        {risers.length ? (
          <Table
            head={
              <>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Asset</th>
                <th className="px-3 py-2 font-medium">Industry</th>
                <th className="px-3 py-2 text-right font-medium">vs industry</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
                <th className="px-3 py-2 text-right font-medium">Size now</th>
                <th className="px-3 py-2 text-right font-medium">Size rank in industry</th>
              </>
            }
          >
            {risers.slice(0, 20).map((r) => {
              const size = sizeByAsset.get(r.assetId);
              return (
                <tr key={r.id}>
                  <td className="num text-muted-foreground px-3 py-2">{r.rank}</td>
                  <td className="px-3 py-2">
                    <Link href={`/asset/${encodeURIComponent(r.asset.symbol)}`} className="underline underline-offset-2">
                      {r.asset.name}
                    </Link>
                  </td>
                  <td className="text-muted-foreground px-3 py-2">{r.asset.industry.name}</td>
                  <td className={`num px-3 py-2 text-right font-medium ${toneClass(r.value)}`}>
                    {pct(r.value)}
                  </td>
                  <td className="px-3 py-2" title={r.confidenceNote ?? undefined}>
                    <ConfidenceBadge grade={r.confidence} />
                  </td>
                  <td className="num px-3 py-2 text-right">
                    {size ? (
                      <>
                        {money(size.value, size.asset.currency)}
                        <span className="text-muted-foreground ml-1 text-xs">
                          {sizeLabel(size.asset.capBasis)}
                        </span>
                      </>
                    ) : (
                      <span className="text-muted-foreground">
                        {r.asset.capBasis === "none"
                          ? "not published"
                          : "not stored"}
                      </span>
                    )}
                  </td>
                  <td className="num text-muted-foreground px-3 py-2 text-right">
                    {size?.sizeRank ?? "-"}
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : (
          <Empty>No 24 month ranking has been computed yet.</Empty>
        )}
      </Section>

      <Section
        title="Products whose demand read is rising"
        lead="A product appears here only when every demand source that answered points up. The score is the plain average of those sources, so it is not weighted and not a forecast."
      >
        {risingProducts.length ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {risingProducts.map((p) => (
              <Card key={p.id} href={`/product/${p.slug}`}>
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-medium">{p.name}</h3>
                  <Pill tone="up">rising</Pill>
                </div>
                <p className="text-muted-foreground mt-1 text-xs">{p.category}</p>
                <div className="mt-3 flex items-baseline justify-between gap-2">
                  <span className="num text-lg font-semibold text-up">{pct(p.demandScore)}</span>
                  <ConfidenceBadge grade={p.confidence} />
                </div>
                <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
                  {p.sourcesAnswered} of 5 sources answered, {p.sourcesAgree} point the same
                  way.
                </p>
                {p.confidenceNote ? (
                  <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                    {p.confidenceNote}
                  </p>
                ) : null}
              </Card>
            ))}
          </div>
        ) : (
          <Empty>
            No product has every answered source pointing up in the latest run. This is
            normal for a short window, and products with a partial read are still listed
            under <Link href="/products" className="underline underline-offset-2">Products</Link>.
          </Empty>
        )}
        <Note>
          A single source is never enough to call a product rising, and a source that did
          not answer is not counted as agreement. The average is a plain mean of the sources
          that answered, so one large reading can carry it, which is why the confidence grade
          is shown next to every figure and says when that happened.
        </Note>
      </Section>

      <Section title="Data freshness" lead="What is stored right now, so a stale page is obvious rather than hidden.">
        <Table
          head={
            <>
              <th className="px-3 py-2 font-medium">Table</th>
              <th className="px-3 py-2 text-right font-medium">Rows</th>
              <th className="px-3 py-2 text-right font-medium">Newest</th>
            </>
          }
        >
          <tr>
            <td className="px-3 py-2">Price snapshots</td>
            <td className="num px-3 py-2 text-right">{fresh.snap._count.toLocaleString("en-US")}</td>
            <td className="num px-3 py-2 text-right">{isoDate(fresh.snap._max.date)}</td>
          </tr>
          <tr>
            <td className="px-3 py-2">Rankings</td>
            <td className="num px-3 py-2 text-right">{fresh.rank._count.toLocaleString("en-US")}</td>
            <td className="num px-3 py-2 text-right">{isoDate(fresh.rank._max.periodEnd)}</td>
          </tr>
          <tr>
            <td className="px-3 py-2">Product signals</td>
            <td className="num px-3 py-2 text-right">{fresh.signal._count.toLocaleString("en-US")}</td>
            <td className="num px-3 py-2 text-right">{isoDate(fresh.signal._max.periodEnd)}</td>
          </tr>
          <tr>
            <td className="px-3 py-2">News items</td>
            <td className="num px-3 py-2 text-right">{fresh.news._count.toLocaleString("en-US")}</td>
            <td className="num px-3 py-2 text-right">{isoDate(fresh.news._max.publishedAt)}</td>
          </tr>
        </Table>
      </Section>
    </div>
  );
}
