import Link from "next/link";
import {
  AsOf,
  Card,
  ConfidenceBadge,
  CurrencyNote,
  Empty,
  HowToRead,
  NeighbourhoodBlock,
  Note,
  WhatMattersBlock,
  Pill,
  Section,
  Table,
  UpcomingBlock,
} from "@/components/ui";
import {
  getAllIndustriesByBasis,
  getCatalysts,
  getFreshness,
  getIndustriesByMarket,
  getLead,
  getNeighbourhood,
  getProducts,
  getWhatMatters,
  getThesisTally,
  getUpcoming,
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
  const [
    lead,
    byMarket,
    risers,
    sizeNow,
    risingProducts,
    fresh,
    catalysts,
    upcoming,
    neighbourhood,
    theses,
    matters,
  ] = await Promise.all([
    getLead(),
    getIndustriesByMarket(),
    getAllIndustriesByBasis("rising"),
    getAllIndustriesByBasis("sizeNow"),
    getProducts("rising"),
    getFreshness(),
    getCatalysts(12),
    getUpcoming({ take: 10 }),
    getNeighbourhood(9),
    getThesisTally(),
    getWhatMatters(8),
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

      {/* The first question, above the radar and above every ranking.
          "What matters now" is not "what moved most": these are the moves that are large for
          the asset that made them, which is a different and more useful list. Each card leads
          with a sentence and keeps the figure beside it, and the asset page behind it carries
          the evidence. */}
      <Section
        title="What matters now"
        lead="Assets whose latest day is unusual against their own history, each already checked against company news, its industry, the calendar and the related names. Most unusual first, not largest first."
        aside={<AsOf date={matters.periodEnd} />}
      >
        <WhatMattersBlock matters={matters} />
      </Section>

      {/* Directly under the lead, not at the bottom. The whole value of a catalyst is that
          it is seen before a reader has heard about it elsewhere, and a radar you have to
          scroll to find is not a radar. It is deliberately the first thing after the
          headline, ahead of the rankings, which change slowly by comparison. */}
      <Section
        title="Catalyst radar"
        lead="Assets and products where news started arriving in the last three days at several times the rate of the month before. It counts headlines; it does not read them."
        aside={<AsOf date={catalysts.periodEnd} />}
      >
        {catalysts.rows.length ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {catalysts.rows.map((c) => {
                const href = c.asset
                  ? `/asset/${encodeURIComponent(c.asset.symbol)}`
                  : c.product
                    ? `/product/${c.product.slug}`
                    : undefined;
                const name = c.asset?.name ?? c.product?.name ?? "unknown";
                return (
                  <Card key={c.id} href={href}>
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-medium">{name}</h3>
                      <Pill tone="warn">
                        {c.spikeRatio != null ? `${c.spikeRatio.toFixed(1)}×` : "spike"}
                      </Pill>
                    </div>
                    <p className="text-muted-foreground mt-1 text-[11px]">
                      {c.asset ? c.asset.symbol : "product"}
                    </p>
                    <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
                      {c.recentItems} items in 3 days
                      {c.baselineDaily != null ? (
                        <> against {c.baselineDaily.toFixed(2)} a day before</>
                      ) : null}
                      .
                    </p>
                    <div className="mt-2">
                      <ConfidenceBadge grade={c.confidence} />
                    </div>
                  </Card>
                );
              })}
            </div>
            <Note>
              A spike is the shape of news breaking, and nothing more. It cannot tell you
              whether what arrived was good, bad, or one story rewritten by four outlets, and
              a quiet name reaches a high multiple on very few articles. Open the target to
              read the headlines the count is built from.
            </Note>
          </>
        ) : (
          <Empty>
            Nothing is above its own news baseline today. That is the ordinary state: a flag
            here means something changed, so most days this list is short or empty.
          </Empty>
        )}
      </Section>

      {/* Straight after the radar, because it is the radar's second half. The radar lists
          what the news has reached; this lists what sits one or two recorded relationships
          away from it and would otherwise be found out about later. */}
      <Section
        title="One step from the radar"
        lead="Assets that sit next to something a catalyst was flagged on, over relationships already stored: a shared product, a shared dated item, or a small enough industry. The chain is shown on every row."
        aside={<AsOf date={neighbourhood.periodEnd} />}
      >
        <NeighbourhoodBlock relevance={neighbourhood} />
      </Section>

      {/* Counts, never a share. "68% still active" would read as a hit rate, and this
          measures whether conditions have changed rather than whether anything worked. */}
      {theses.counts.length ? (
        <Section
          title="How the recorded reasons are holding up"
          lead="Every directional read the site is currently holding, by whether the conditions it was recorded on are still there. A broken reason means the level named in advance was passed; it does not say the read was wrong, and it is left broken rather than revised."
          aside={<AsOf date={theses.asOf} />}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            {theses.counts.map((c) => (
              <Card key={c.status}>
                <p className="text-muted-foreground text-xs">
                  {c.status === "active"
                    ? "Reason intact"
                    : c.status === "weakening"
                      ? "Reason weakening"
                      : "Reason broken"}
                </p>
                <p className="num mt-1 text-2xl font-semibold">{c.n}</p>
                <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                  {c.status === "active"
                    ? "every condition that carried a verdict on the opening day still carries the same one"
                    : c.status === "weakening"
                      ? "a condition has flipped or become unavailable, and the level named in advance has not been passed"
                      : "the level named on the opening day was passed, or the read now names the opposite direction"}
                </p>
              </Card>
            ))}
          </div>
        </Section>
      ) : null}

      {/* Next to the radar, because the two answer the same worry from opposite ends: one
          catches what has already started arriving, the other what is already on the
          calendar. Between them they cover most of what a reader finds out too late. */}
      <Section
        title="Dates ahead"
        lead="Scheduled items already published: earnings, dividend and ex-dividend dates. Remembering them is the point; nothing here says what a date will do."
      >
        <UpcomingBlock events={upcoming} />
      </Section>

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
