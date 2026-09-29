import Link from "next/link";
import { AsOf, Card, Empty, Note, Pill, Section, Table } from "@/components/ui";
import {
  getAllIndustriesByBasis,
  getFreshness,
  getIndustries,
  getLead,
  getProducts,
} from "@/lib/queries";
import { isoDate, money, pct, toneClass } from "@/lib/format";

export const revalidate = 3600;

export default async function Home() {
  const [lead, industries, risers, risingProducts, fresh] = await Promise.all([
    getLead(),
    getIndustries(),
    getAllIndustriesByBasis("rising"),
    getProducts("rising"),
    getFreshness(),
  ]);

  const byIndustry = new Map<string, typeof risers>();
  for (const r of risers) {
    if (!byIndustry.has(r.industryId)) byIndustry.set(r.industryId, []);
    byIndustry.get(r.industryId)!.push(r);
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

      <Section
        title="Industries"
        lead="Size, return and relative strength for seven sectors. Open one to see the pre-AI snapshot against today."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {industries.map((ind) => {
            const top = byIndustry.get(ind.id)?.slice(0, 3) ?? [];
            const largest = risers
              .filter((r) => r.industryId === ind.id && r.basis === "sizeNow")
              .sort((a, b) => a.rank - b.rank)[0];
            const l = largest?.asset;
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
                    <span className="num">
                      {money(largest.value)}
                    </span>
                  </p>
                ) : (
                  <p className="text-muted-foreground mt-3 text-sm">
                    No size figure stored for this industry.
                  </p>
                )}
                {top.length ? (
                  <ul className="mt-2 space-y-0.5 text-sm">
                    {top.map((r) => (
                      <li key={r.id} className="flex justify-between gap-3">
                        <span>{r.asset.name}</span>
                        <span className={`num ${toneClass(r.value)}`}>{pct(r.value)}</span>
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

      <Section
        title="Strongest relative performers"
        lead="24 month return minus the average return of the asset's own industry. A positive number means the asset beat its peers, not that it went up."
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
                <th className="px-3 py-2 text-right font-medium">Size now</th>
                <th className="px-3 py-2 text-right font-medium">In industry</th>
              </>
            }
          >
            {risers.slice(0, 20).map((r) => (
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
                <td className="num px-3 py-2 text-right">
                  {r.asset.capBasis === "none" ? "not applicable" : money(r.value)}
                </td>
                <td className="num text-muted-foreground px-3 py-2 text-right">{r.sizeRank ?? "-"}</td>
              </tr>
            ))}
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
                <p className="num mt-3 text-lg font-semibold text-up">{pct(p.demandScore)}</p>
                <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{p.demandNote}</p>
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
          A single source is never enough to call a product rising. Products backed by one
          answer are marked early or flat on the products page, with the source named.
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
