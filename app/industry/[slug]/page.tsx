import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AsOf, Card, Empty, Note, Section, Table } from "@/components/ui";
import { getAllIndustriesByBasis, getIndustry, getRankings } from "@/lib/queries";
import { isoDate, longDate, money, pct, relativeTime, sizeLabel, toneClass } from "@/lib/format";

export const revalidate = 3600;

export async function generateStaticParams() {
  const all = await getAllIndustriesByBasis("sizeNow");
  const slugs = new Set(all.map((r) => r.asset.industry.slug));
  return [...slugs].map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const ind = await getIndustry(slug);
  if (!ind) return { title: "Industry not found" };
  return { title: ind.name, description: ind.summary };
}

export default async function IndustryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const ind = await getIndustry(slug);
  if (!ind) notFound();

  const [sizePre, sizeNow, total, rising] = await Promise.all([
    getRankings(ind.id, "size"),
    getRankings(ind.id, "sizeNow"),
    getRankings(ind.id, "totalReturn"),
    getRankings(ind.id, "rising"),
  ]);

  const shift = ind.analysis.find((a) => a.kind === "industryShift");
  const forward = ind.analysis.find((a) => a.kind === "forwardLook");
  const movers = ind.analysis.find((a) => a.kind === "forwardLook" && a.headline.includes("current data"));

  const preByAsset = new Map(sizePre.map((r) => [r.assetId, r]));
  const ranked = sizeNow.length ? sizeNow : sizePre;

  return (
    <div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{ind.name}</h1>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm">{ind.summary}</p>
      </div>

      {shift ? (
        <div className="mt-6 space-y-3">
          <Card>
            <h2 className="font-medium">{shift.headline}</h2>
            <p className="mt-2 text-sm leading-relaxed">{shift.body}</p>
            {shift.dataNote ? <Note>{shift.dataNote}</Note> : null}
            <p className="text-muted-foreground mt-2 text-xs">Sources: {shift.source}</p>
          </Card>
          {movers ? (
            <Card>
              <h2 className="font-medium">{movers.headline}</h2>
              <p className="mt-2 text-sm leading-relaxed">{movers.body}</p>
              {movers.dataNote ? <Note>{movers.dataNote}</Note> : null}
            </Card>
          ) : null}
        </div>
      ) : (
        <p className="text-muted-foreground mt-6 text-sm">No stored analysis for this industry yet.</p>
      )}

      <Section
        title="Size ranking: before the AI wave and now"
        lead={
          sizeNow.length
            ? "Rank by size at the end of 2021, and by size at the newest stored close. Columns are the two dates, not a forecast."
            : "No current size figure is stored for this industry, so only the pre-AI ranking is shown."
        }
        aside={
          <span className="text-muted-foreground text-xs">
            {isoDate(sizePre[0]?.periodEnd)} against {isoDate(sizeNow[0]?.periodEnd)}
          </span>
        }
      >
        {ranked.length ? (
          <Table
            head={
              <>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Asset</th>
                <th className="px-3 py-2 text-right font-medium">Size at end 2021</th>
                <th className="px-3 py-2 text-right font-medium">Size now</th>
                <th className="px-3 py-2 text-right font-medium">Move</th>
              </>
            }
          >
            {ranked.map((r) => {
              const pre = preByAsset.get(r.assetId);
              const nowRank = sizeNow.find((x) => x.assetId === r.assetId)?.rank;
              const preRank = pre?.rank;
              const move = preRank && nowRank ? preRank - nowRank : null;
              return (
                <tr key={r.id}>
                  <td className="num text-muted-foreground px-3 py-2">{nowRank ?? preRank}</td>
                  <td className="px-3 py-2">
                    <Link href={`/asset/${encodeURIComponent(r.asset.symbol)}`} className="underline underline-offset-2">
                      {r.asset.name}
                    </Link>
                    <span className="text-muted-foreground ml-2 text-xs">{r.asset.symbol}</span>
                  </td>
                  <td className="num px-3 py-2 text-right">
                    {pre ? money(pre.value) : "not available"}
                  </td>
                  <td className="num px-3 py-2 text-right">
                    {sizeNow.length ? money(r.value) : "not available"}
                  </td>
                  <td className={`num px-3 py-2 text-right ${toneClass(move)}`}>
                    {move == null ? "not available" : move === 0 ? "unchanged" : move > 0 ? `up ${move}` : `down ${-move}`}
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : (
          <Empty>
            No size figure is stored for this industry at either date, because the free
            sources do not publish one for these assets. Returns are shown below instead.
          </Empty>
        )}
        {ranked.length ? (
          <p className="text-muted-foreground mt-2 text-xs">
            Size is {sizeLabel(ranked[0].asset.capBasis)}. It is price multiplied by shares,
            taken from Yahoo Finance, and for crypto from CoinPaprika. It is not a valuation.
          </p>
        ) : null}
      </Section>

      <Section
        title="Return since 2021"
        lead="Total return from the last stored close of 2021 to the newest stored close, per asset."
        aside={<AsOf date={total[0]?.periodEnd} />}
      >
        {total.length ? (
          <Table
            head={
              <>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Asset</th>
                <th className="px-3 py-2 text-right font-medium">Return</th>
                <th className="px-3 py-2 text-right font-medium">Size rank</th>
              </>
            }
          >
            {total.map((r) => (
              <tr key={r.id}>
                <td className="num text-muted-foreground px-3 py-2">{r.rank}</td>
                <td className="px-3 py-2">
                  <Link href={`/asset/${encodeURIComponent(r.asset.symbol)}`} className="underline underline-offset-2">
                    {r.asset.name}
                  </Link>
                </td>
                <td className={`num px-3 py-2 text-right font-medium ${toneClass(r.value)}`}>{pct(r.value)}</td>
                <td className="num text-muted-foreground px-3 py-2 text-right">{r.sizeRank ?? "not applicable"}</td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No return window is stored for this industry.</Empty>
        )}
      </Section>

      <Section
        title="Relative strength over 24 months"
        lead="24 month return minus the average 24 month return of this industry. Positive means the asset beat its own peers. Volume trend is used as a second check where a volume series exists."
        aside={<AsOf date={rising[0]?.periodEnd} />}
      >
        {rising.length ? (
          <Table
            head={
              <>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Asset</th>
                <th className="px-3 py-2 text-right font-medium">vs industry</th>
                <th className="px-3 py-2 font-medium">Check</th>
              </>
            }
          >
            {rising.map((r) => (
              <tr key={r.id}>
                <td className="num text-muted-foreground px-3 py-2">{r.rank}</td>
                <td className="px-3 py-2">
                  <Link href={`/asset/${encodeURIComponent(r.asset.symbol)}`} className="underline underline-offset-2">
                    {r.asset.name}
                  </Link>
                </td>
                <td className={`num px-3 py-2 text-right font-medium ${toneClass(r.value)}`}>{pct(r.value)}</td>
                <td className="text-muted-foreground px-3 py-2 text-xs">
                  {r.note ?? "volume trend confirmed"}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>Not enough price history is stored to build a 24 month window for this industry.</Empty>
        )}
      </Section>

      <Section title="Recent news collected for this industry" aside={<span className="text-muted-foreground text-xs">Google News RSS, last items stored</span>}>
        {ind.news.length ? (
          <ul className="space-y-2">
            {ind.news.map((n) => (
              <li key={n.id} className="border-border border-b pb-2 text-sm last:border-0">
                <a href={n.url} target="_blank" rel="noopener noreferrer nofollow" className="underline underline-offset-2">
                  {n.title}
                </a>
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {n.publisher} · {relativeTime(n.publishedAt)} ·{" "}
                  {n.asset ? n.asset.name : ind.name}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No news items are stored for this industry yet.</Empty>
        )}
      </Section>

      {forward ? (
        <p className="text-muted-foreground mt-8 text-xs">
          Last recalculated {longDate(shift?.createdAt ?? ind.createdAt)}.
        </p>
      ) : null}
    </div>
  );
}
