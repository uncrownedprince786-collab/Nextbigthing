import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Sparkline } from "@/components/chart";
import {
  AccuracyNote,
  AnalogBlock,
  Card,
  ConfidenceBadge,
  DiscussionBlock,
  Empty,
  Note,
  Pill,
  Section,
  SetupBlock,
  Table,
  UpcomingBlock,
  weakest,
} from "@/components/ui";
import {
  getAccuracy,
  getAnalogs,
  getAsset,
  getAssetPrices,
  getHumanSignal,
  getSetup,
  getUpcoming,
} from "@/lib/queries";
import { isoDate, longDate, money, pct, relativeTime, sizeBasisText, toneClass } from "@/lib/format";

export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ symbol: string }>;
}): Promise<Metadata> {
  const { symbol } = await params;
  const a = await getAsset(decodeURIComponent(symbol));
  if (!a) return { title: "Asset not found" };
  return { title: a.name, description: `${a.name} (${a.symbol}) in ${a.industry.name}` };
}

const BASIS_LABEL: Record<string, string> = {
  size: "Size at a past date",
  sizeNow: "Size now",
  totalReturn: "Total return between two dates",
  rising: "24 month return against its industry",
};

export default async function AssetPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const asset = await getAsset(decodeURIComponent(symbol));
  if (!asset) notFound();

  const prices = await getAssetPrices(asset.id, 2019);
  const note = asset.analysis[0];
  const [discussion, accuracy, analogs, upcoming, setup] = await Promise.all([
    getHumanSignal({ assetId: asset.id }),
    getAccuracy(30),
    getAnalogs(asset.id),
    getUpcoming({ assetId: asset.id, take: 8 }),
    getSetup(asset.id),
  ]);

  const byBasis = new Map<string, typeof asset.rankings>();
  for (const r of asset.rankings) {
    if (!byBasis.has(r.basis)) byBasis.set(r.basis, []);
    byBasis.get(r.basis)!.push(r);
  }
  const latestPrice = prices[prices.length - 1];
  const yearAgo = prices.filter((p) => p.date <= new Date(latestPrice.date.getTime() - 365 * 86_400_000)).pop();
  const oneYear = yearAgo ? ((latestPrice.close / yearAgo.close - 1) * 100) : null;

  // Current size comes from the ranking row rather than the newest price snapshot, so the
  // figure shown here is the same one the industry table ranks and grades.
  const sizeNowRow = (byBasis.get("sizeNow") ?? [])[0];
  const sizePreRow = (byBasis.get("size") ?? [])[0];
  const sizeGrade = weakest(sizeNowRow?.confidence, sizePreRow?.confidence);

  return (
    <div>
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{asset.name}</h1>
          <Pill>{asset.symbol}</Pill>
          <Pill>{asset.assetType}</Pill>
        </div>
        <p className="text-muted-foreground mt-2 text-sm">
          In{" "}
          <Link href={`/industry/${asset.industry.slug}`} className="underline underline-offset-2">
            {asset.industry.name}
          </Link>
          . Price source {asset.source}.
        </p>
        {asset.note ? <p className="mt-2 max-w-3xl text-sm leading-relaxed">{asset.note}</p> : null}
      </div>

      {note ? (
        <Card className="mt-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium">Where this sits</h2>
            <ConfidenceBadge grade={note.confidence} />
          </div>
          <p className="mt-2 text-sm leading-relaxed">{note.body}</p>
          {note.dataNote ? <Note>{note.dataNote}</Note> : null}
        </Card>
      ) : null}

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <Card>
          <p className="text-muted-foreground text-xs">Last stored close</p>
          <p className="num mt-1 text-2xl font-semibold">{latestPrice ? latestPrice.close.toFixed(2) : "not available"}</p>
          <p className="text-muted-foreground text-xs">{isoDate(latestPrice?.date)}</p>
        </Card>
        <Card>
          <p className="text-muted-foreground text-xs">Return over the last year</p>
          <p className={`num mt-1 text-2xl font-semibold ${toneClass(oneYear)}`}>{pct(oneYear)}</p>
          <p className="text-muted-foreground text-xs">
            {yearAgo ? `${isoDate(yearAgo.date)} to ${isoDate(latestPrice.date)}` : "not enough history"}
          </p>
        </Card>
        <Card>
          <div className="flex items-center justify-between gap-2">
            <p className="text-muted-foreground text-xs">Size now</p>
            <ConfidenceBadge grade={sizeGrade} />
          </div>
          <p className="num mt-1 text-2xl font-semibold">
            {sizeNowRow ? money(sizeNowRow.value, asset.currency) : "not stored"}
          </p>
          <p className="text-muted-foreground text-xs">
            {sizeNowRow
              ? `${sizeBasisText(asset.capBasis)}, newest stored close`
              : asset.capBasis === "none"
                ? sizeBasisText("none")
                : "no size ranking is stored for this asset, so no figure is shown"}
          </p>
        </Card>
      </div>

      <Section
        title="Stored price history"
        lead="Daily closes from 2019 onward, as stored. The line is the closing price only, not adjusted for dividends."
      >
        <Card>
          <Sparkline points={prices} label={asset.name} />
        </Card>
        <p className="text-muted-foreground mt-2 text-xs">
          {prices.length.toLocaleString("en-US")} stored closes from {isoDate(prices[0]?.date)} to{" "}
          {isoDate(prices[prices.length - 1]?.date)}.
        </p>
      </Section>

      <Section title="Stored rankings" lead="Every ranking row for this asset, newest window first.">
        {asset.rankings.length ? (
          <Table
            head={
              <>
                <th className="px-3 py-2 font-medium">Basis</th>
                <th className="px-3 py-2 text-right font-medium">Rank</th>
                <th className="px-3 py-2 text-right font-medium">Value</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
                <th className="px-3 py-2 text-right font-medium">From</th>
                <th className="px-3 py-2 text-right font-medium">To</th>
                <th className="px-3 py-2 font-medium">Note</th>
              </>
            }
          >
            {asset.rankings.map((r) => (
              <tr key={r.id}>
                <td className="px-3 py-2 text-xs">{BASIS_LABEL[r.basis] ?? r.basis}</td>
                <td className="num px-3 py-2 text-right">{r.rank}</td>
                <td
                  className={`num px-3 py-2 text-right ${r.basis === "totalReturn" || r.basis === "rising" ? toneClass(r.value) : ""}`}
                >
                  {r.basis === "size" || r.basis === "sizeNow"
                    ? money(r.value, asset.currency)
                    : pct(r.value)}
                </td>
                <td className="px-3 py-2" title={r.confidenceNote ?? undefined}>
                  <ConfidenceBadge grade={r.confidence} />
                </td>
                <td className="num text-muted-foreground px-3 py-2 text-right">{isoDate(r.periodStart)}</td>
                <td className="num text-muted-foreground px-3 py-2 text-right">{isoDate(r.periodEnd)}</td>
                <td className="text-muted-foreground px-3 py-2 text-xs">
                  {r.confidenceNote ?? r.note ?? "-"}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No ranking rows are stored for this asset.</Empty>
        )}
      </Section>

      {/* First, because it is the question a reader actually arrives with. Everything under
          it is the evidence the state was read from, in the order a person asks: what do the
          numbers show, what disagrees, what is coming, what happened before. */}
      <Section
        title="What the conditions say right now"
        lead="Measured conditions over stored prices, news readings and historical analogs. Every condition tested is listed, including the ones that failed and the inputs that were unavailable."
      >
        <SetupBlock setup={setup} currency={asset.currency} />
      </Section>

      <Section
        title="What followed days like this one"
        lead="Past days in the stored history whose one day return, volume multiple and five day trend were close to the latest day's, and what measurably happened next. A record of similar days, not a statement about this one."
      >
        <AnalogBlock analogs={analogs} />
      </Section>

      <Section
        title="Scheduled dates ahead"
        lead="Dated items already published for this asset. The point is not to predict them but to not be surprised by them."
      >
        <UpcomingBlock events={upcoming} showTargets={false} />
      </Section>

      <Section
        title="Current discussion"
        lead="What has been published about this asset lately, how it was worded, and whether it reads as promotion. Context for the numbers above, not evidence about them."
      >
        <DiscussionBlock signal={discussion} targetLabel={asset.name} />
        <div className="mt-3">
          <AccuracyNote accuracy={accuracy} />
        </div>
      </Section>

      <Section title="Products that touch this asset" lead="The stated relationship is why the product was linked, not a recommendation.">
        {asset.productLinks.length ? (
          <ul className="grid gap-2 sm:grid-cols-2">
            {asset.productLinks.map((l) => (
              <li key={l.id} className="border-border rounded-lg border px-3 py-2 text-sm">
                <Link href={`/product/${l.product.slug}`} className="font-medium underline underline-offset-2">
                  {l.product.name}
                </Link>
                <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{l.relation}</p>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No products are linked to this asset.</Empty>
        )}
      </Section>

      <Section title="Recent news mentioning this asset">
        {asset.news.length ? (
          <ul className="space-y-2">
            {asset.news.map((n) => (
              <li key={n.id} className="border-border border-b pb-2 text-sm last:border-0">
                <a href={n.url} target="_blank" rel="noopener noreferrer nofollow" className="underline underline-offset-2">
                  {n.title}
                </a>
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {n.publisher} · {relativeTime(n.publishedAt)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No news items matched this asset in the stored window.</Empty>
        )}
      </Section>

      <p className="text-muted-foreground mt-8 text-xs">
        Source {asset.source} · reference {asset.sourceRef} · first stored {longDate(asset.createdAt)}.
      </p>
    </div>
  );
}
