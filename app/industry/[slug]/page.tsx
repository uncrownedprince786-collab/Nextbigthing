import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AsOf,
  Card,
  ConfidenceBadge,
  CurrencyNote,
  Empty,
  HowToRead,
  Note,
  Section,
  Table,
  weakest,
} from "@/components/ui";
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
  // The size table only lists the assets that actually have a size figure, so without this
  // count a reader of the metals industry sees three rows and may take it for three assets.
  // The gaps are not all the same kind, so they are counted separately rather than lumped.
  const nowByAsset = new Map(sizeNow.map((r) => [r.assetId, r]));
  const withSize = new Set(ranked.map((r) => r.assetId));
  const missing = ind.assets.filter((a) => !withSize.has(a.id));
  const noBasis = missing.filter((a) => a.capBasis === "none");
  const oneDateOnly = missing.filter((a) => preByAsset.has(a.id) || nowByAsset.has(a.id));
  const noFigure = missing.filter(
    (a) => !noBasis.includes(a) && !oneDateOnly.includes(a),
  );

  return (
    <div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{ind.name}</h1>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm">{ind.summary}</p>
        <div className="mt-2 max-w-3xl">
          <CurrencyNote currency={ind.currency} market={ind.market} />
        </div>
        <HowToRead
          points={[
            <>
              <strong>Start with the size table, then the return table.</strong> They
              answer different questions: one is how big a company is now, the other is
              what its price did over a stated period. A small company can top the return
              table and still be last on size.
            </>,
            <>
              <strong>An empty size cell is a missing figure, not a zero.</strong> Futures
              publish no size at all, crypto has no history for it, and the Karachi sectors
              have a current figure only. The paragraph under the table counts each of
              these separately rather than lumping them.
            </>,
            <>
              <strong>Relative strength subtracts this industry&apos;s own average.</strong>{" "}
              +20 means the asset beat its peers by 20 points. In a sector that fell 30%,
              that is still a fall.
            </>,
            <>
              <strong>Read the confidence note, not just the badge.</strong> Hover a badge
              and it says why. The most common reason for a downgrade here is that the
              industry average sits far from its median, which means one or two assets are
              pulling a figure the typical peer does not resemble.
            </>,
            ind.market === "PK" ? (
              <>
                <strong>Rupee returns include the currency.</strong> A Karachi listing
                whose price rose 40% over a period when the rupee weakened has not gained
                40% of purchasing power. No conversion is applied here, and none is
                implied.
              </>
            ) : (
              <>
                <strong>Returns are price returns.</strong> Dividends are not added back,
                so a high yielding asset looks weaker here than a total return figure
                would make it.
              </>
            ),
          ]}
        />
      </div>

      {shift ? (
        <div className="mt-6 space-y-3">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-medium">{shift.headline}</h2>
              <ConfidenceBadge grade={shift.confidence} />
            </div>
            <p className="mt-2 text-sm leading-relaxed">{shift.body}</p>
            {shift.dataNote ? <Note>{shift.dataNote}</Note> : null}
            <p className="text-muted-foreground mt-2 text-xs">Sources: {shift.source}</p>
          </Card>
          {movers ? (
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-medium">{movers.headline}</h2>
                <ConfidenceBadge grade={movers.confidence} />
              </div>
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
                <th className="px-3 py-2 font-medium">Confidence</th>
                <th className="px-3 py-2 text-right font-medium">Move</th>
              </>
            }
          >
            {ranked.map((r) => {
              const pre = preByAsset.get(r.assetId);
              const nowRow = sizeNow.find((x) => x.assetId === r.assetId);
              const nowRank = nowRow?.rank;
              const preRank = pre?.rank;
              const move = preRank && nowRank ? preRank - nowRank : null;
              // The weaker of the two dates that were actually stored. An asset with no
              // 2021 figure is graded on the current one, and its empty cell is the
              // disclosure, so the badge does not claim "no data" for a known number.
              const grade = weakest(nowRow?.confidence, pre?.confidence);
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
                    {pre ? money(pre.value, ind.currency) : "not available"}
                  </td>
                  <td className="num px-3 py-2 text-right">
                    {sizeNow.length ? money(r.value, ind.currency) : "not available"}
                  </td>
                  <td className="px-3 py-2">
                    <ConfidenceBadge grade={grade} />
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
            taken from Yahoo Finance, and for crypto from CoinPaprika. It is not a valuation.{" "}
            Confidence is the weaker of the two dates stored for that asset. An asset with no
            pre-AI figure, which is most crypto and a few recent listings, is graded on its
            current size alone and its empty cell says the earlier date is unavailable.
          </p>
        ) : null}
        {ranked.length && missing.length ? (
          <Note>
            {ranked.length} of the {ind.assets.length} assets in this industry carry a size
            figure, so this table is not a ranking of everything here.
            {noBasis.length ? (
              <>
                {" "}
                {noBasis.length} publish no market capitalisation or fund assets figure at
                all, including{" "}
                {noBasis
                  .slice(0, 3)
                  .map((a) => a.name)
                  .join(", ")}
                {noBasis.length > 3 ? ` and ${noBasis.length - 3} more` : ""}, so there is
                nothing to rank.
              </>
            ) : null}
            {oneDateOnly.length ? (
              <>
                {" "}
                {oneDateOnly.length} have a figure at one date but not the other, so they
                cannot be placed in a table that compares two.
              </>
            ) : null}
            {noFigure.length ? (
              <>
                {" "}
                {noFigure.length} expected a size figure but none is stored, which is a gap in
                the data rather than a fact about the asset.
              </>
            ) : null}{" "}
            Nothing is estimated to fill a gap.
          </Note>
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
                <th className="px-3 py-2 font-medium">Confidence</th>
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
                <td className="px-3 py-2">
                  <ConfidenceBadge grade={r.confidence} />
                </td>
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
        lead="24 month return minus the average 24 month return of this industry. Positive means the asset beat its own peers. Volume trend is used as a second check where a volume series exists, and where the industry average sits far from the median the rank is reported but graded down."
        aside={<AsOf date={rising[0]?.periodEnd} />}
      >
        {rising.length ? (
          <Table
            head={
              <>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Asset</th>
                <th className="px-3 py-2 text-right font-medium">vs industry</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
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
                <td className="px-3 py-2" title={r.confidenceNote ?? undefined}>
                  <ConfidenceBadge grade={r.confidence} />
                </td>
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
