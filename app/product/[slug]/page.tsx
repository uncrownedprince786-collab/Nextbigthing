import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AccuracyNote,
  Card,
  ConfidenceBadge,
  DiscussionBlock,
  Empty,
  HowToRead,
  Note,
  Pill,
  Section,
  Table,
} from "@/components/ui";
import { getAccuracy, getHumanSignal, getProduct, getProductMarketplace } from "@/lib/queries";
import { count, isoDate, longDate, pct, relativeTime, toneClass } from "@/lib/format";

export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const p = await getProduct(slug);
  if (!p) return { title: "Product not found" };
  return { title: p.name, description: p.summary };
}

const METRIC_TEXT: Record<string, string> = {
  trends_8w_vs_8w_pct: "Search interest, 8 weeks against the 8 before",
  trends_26w_yoy_pct: "Search interest, 26 weeks against the 26 before",
  wiki_views_8w_vs_8w_pct: "Pageviews, 8 weeks against the 8 before",
  wiki_views_26w_yoy_pct: "Pageviews, 26 weeks against the 26 before",
  hn_stories_90d_change_pct: "Stories, 90 days against the 90 before",
  reddit_posts_30d_change_pct:
    "Posts, the last 30 days against the rate over the 90 days before",
  gnews_articles_30d_change_pct: "Articles, 30 days against the 30 before",
  reddit_posts_30d: "Posts in the last 30 days",
  reddit_posts_90d_base: "Posts in the 90 days immediately before that",
  hn_stories_90d: "Stories in the last 90 days",
  gnews_articles_30d: "Articles in the last 30 days",
};

/// The five metrics that make up the demand score, kept identical to SCORED_SIGNALS in
/// jobs/nbt.py. Long window Trends and Wikipedia rows are stored and shown for the record
/// but never counted, so a product with both an 8 week and a 26 week reading is not
/// treated as two independent sources. The source is listed here rather than read off a
/// row, because a metric that never ran has no row to read it from and must still be
/// reported as missing.
const SCORED = [
  { source: "googleTrends", metric: "trends_8w_vs_8w_pct" },
  { source: "wikipedia", metric: "wiki_views_8w_vs_8w_pct" },
  { source: "hackerNews", metric: "hn_stories_90d_change_pct" },
  { source: "reddit", metric: "reddit_posts_30d_change_pct" },
  { source: "googleNews", metric: "gnews_articles_30d_change_pct" },
] as const;
const SCORED_METRICS = new Set<string>(SCORED.map((s) => s.metric));

const SOURCE_NAME: Record<string, string> = {
  googleTrends: "Google Trends",
  wikipedia: "Wikipedia pageviews",
  hackerNews: "Hacker News",
  reddit: "Reddit",
  googleNews: "Google News",
};

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const p = await getProduct(slug);
  if (!p) notFound();

  // Matched on the search term against listing titles, and reported as exactly that. It
  // is a text match, not a measurement of the product category, and it is deliberately
  // fetched after the product rather than joined into the demand score.
  const market = await getProductMarketplace(p.trendsTerm || p.name);
  const [discussion, accuracy] = await Promise.all([
    getHumanSignal({ productId: p.id }),
    getAccuracy(30),
  ]);

  const read = p.analysis[0];

  // A metric can hold more than one stored row, so the newest per metric is the reading.
  const latest = new Map<string, (typeof p.signals)[number]>();
  for (const s of [...p.signals].sort((a, b) => b.periodEnd.getTime() - a.periodEnd.getTime())) {
    if (!latest.has(s.metric)) latest.set(s.metric, s);
  }
  const signals = [...latest.values()];

  const scored = signals.filter((s) => SCORED_METRICS.has(s.metric));
  const context = signals.filter((s) => !SCORED_METRICS.has(s.metric));
  // A metric with no stored row at all is missing too, so a source that never ran is not
  // silently dropped from the list the reader is shown.
  const missing = SCORED.filter(
    ({ metric }) => signals.find((s) => s.metric === metric)?.value == null,
  ).map(({ source }) => source);

  // Only one row per source can count, so a product with a duplicate metric cannot look
  // like it has more voices than there are sources.
  const bySource = new Map<string, (typeof scored)[number]>();
  for (const { source, metric } of SCORED) {
    const s = signals.find((x) => x.metric === metric);
    if (s && s.value != null) bySource.set(source, s);
  }
  const up = [...bySource.values()].filter((s) => (s.value ?? 0) > 0);
  const down = [...bySource.values()].filter((s) => (s.value ?? 0) < 0);
  const flat = [...bySource.values()].filter((s) => (s.value ?? 0) === 0);

  return (
    <div>
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{p.name}</h1>
          <Pill
            tone={p.status === "rising" ? "up" : p.status === "early" ? "warn" : "default"}
          >
            {p.status}
          </Pill>
          <ConfidenceBadge grade={p.confidence} />
        </div>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm">{p.summary}</p>
        <p className="text-muted-foreground mt-2 text-xs">
          {p.category} · demand score{" "}
          <span className={toneClass(p.demandScore)}>{pct(p.demandScore)}</span> · measured{" "}
          {p.computedAt ? relativeTime(p.computedAt) : "never"}
        </p>
      </div>

      {read ? (
        <Card className="mt-6">
          <h2 className="font-medium">Demand read</h2>
          <p className="mt-2 text-sm leading-relaxed">{read.body}</p>
          {read.dataNote ? <Note>{read.dataNote}</Note> : null}
        </Card>
      ) : null}

      <Section
        title="Do the sources agree"
        lead="One row per source, so agreement can be seen rather than taken on trust. A source that did not answer is shown as missing and is not counted as agreement."
      >
        <Table
          head={
            <>
              <th className="px-3 py-2 font-medium">Source</th>
              <th className="px-3 py-2 font-medium">Direction</th>
              <th className="px-3 py-2 text-right font-medium">Change</th>
              <th className="px-3 py-2 text-right font-medium">Counted</th>
            </>
          }
        >
          {Object.entries(SOURCE_NAME).map(([key, label]) => {
            const s = bySource.get(key);
            const v = s?.value ?? null;
            return (
              <tr key={key}>
                <td className="px-3 py-2 whitespace-nowrap">{label}</td>
                <td className="px-3 py-2">
                  {v == null ? (
                    <span className="text-muted-foreground text-xs">did not answer</span>
                  ) : v > 0 ? (
                    <Pill tone="up">up</Pill>
                  ) : v < 0 ? (
                    <Pill tone="down">down</Pill>
                  ) : (
                    <Pill>no change</Pill>
                  )}
                </td>
                <td className={`num px-3 py-2 text-right ${toneClass(v)}`}>
                  {v == null ? "-" : pct(v)}
                </td>
                <td className="num text-muted-foreground px-3 py-2 text-right">
                  {s ? "yes" : "no"}
                </td>
              </tr>
            );
          })}
        </Table>
        <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
          {bySource.size === 0
            ? "No source answered, so nothing is claimed about this product."
            : up.length && down.length
              ? `${up.length} point up and ${down.length} point down, so the average is a weak read and the grade is capped at medium.`
              : up.length || down.length
                ? [
                    // A source sitting at exactly zero has not moved, so counting it as
                    // pointing down would overstate how much of this is agreement.
                    up.length + down.length === 1
                      ? `The single source that moved points ${up.length ? "up" : "down"}`
                      : `The ${up.length + down.length} that moved all point ${up.length ? "up" : "down"}`,
                    flat.length
                      ? `, and ${flat.length} of ${bySource.size} report no change at all`
                      : "",
                    ".",
                  ]
                    .join("")
                    .replace(",.", ".")
                : `All ${bySource.size} that answered report no change.`}{" "}
          The score is the plain mean of the counted rows, so a large single reading can carry
          it, which is what the confidence grade is reporting. A source sitting at zero is
          counted as answering but is not counted as agreeing on a direction.
        </p>
        {p.confidenceNote ? <Note>{p.confidenceNote}</Note> : null}
      </Section>

      <Section
        title="What each source measured"
        lead="Change first, then the raw counts behind it. Long window rows are listed for the record and are not part of the score."
      >
        <Table
          head={
            <>
              <th className="px-3 py-2 font-medium">Source</th>
              <th className="px-3 py-2 font-medium">Measure</th>
              <th className="px-3 py-2 text-right font-medium">Value</th>
              <th className="px-3 py-2 text-right font-medium">Window end</th>
              <th className="px-3 py-2 font-medium">Evidence</th>
            </>
          }
        >
          {[...scored, ...context].map((s) => (
            <tr key={s.id}>
              <td className="px-3 py-2 whitespace-nowrap">{SOURCE_NAME[s.source] ?? s.source}</td>
              <td className="text-muted-foreground px-3 py-2 text-xs">
                {METRIC_TEXT[s.metric] ?? s.metric}
                {SCORED_METRICS.has(s.metric) ? null : (
                  <span className="text-muted-foreground/70"> (not scored)</span>
                )}
              </td>
              <td
                className={`num px-3 py-2 text-right font-medium ${
                  SCORED_METRICS.has(s.metric) ? toneClass(s.value) : ""
                }`}
              >
                {s.value == null
                  ? "not available"
                  : SCORED_METRICS.has(s.metric)
                    ? pct(s.value)
                    : count(s.value)}
              </td>
              <td className="num text-muted-foreground px-3 py-2 text-right">{isoDate(s.periodEnd)}</td>
              <td className="text-muted-foreground px-3 py-2 text-xs">
                {s.evidence ? s.evidence : "no single item to point at"}
              </td>
            </tr>
          ))}
        </Table>
        {missing.length ? (
          <Note>
            {[...new Set(missing)].map((m) => SOURCE_NAME[m]).join(", ")} did not answer in the
            last run{p.subreddits ? ` for r/${p.subreddits}` : ""}.{" "}
            {p.wikiTitle
              ? "The Wikipedia article title and the Trends term come from the seed list and can be wrong; if one source is always empty, the mapping is the first thing to check."
              : "No Wikipedia title is mapped for this product."}{" "}
            A missing source is not a zero. Reddit is left out of the score entirely when the
            90 day window it is measured against holds fewer than five posts, because a
            change off a base that small is a rounding artifact rather than a demand signal.
          </Note>
        ) : null}
      </Section>

      <Section
        title="Current discussion"
        lead="What has been published about this product lately, how it was worded, and whether it reads as promotion. Kept separate from the demand score above, which measures search and forum activity rather than wording."
      >
        <DiscussionBlock signal={discussion} targetLabel={p.name} />
        <div className="mt-3">
          <AccuracyNote accuracy={accuracy} />
        </div>
      </Section>

      <Section
        title="Marketplace and local notes"
        lead="Where this product shows up on a public marketplace chart, and what a reader would have to check by hand. Kept out of the demand score above."
      >
        <Note>
          A bestseller rank is a different claim from a search trend. It says one listing
          is outselling others in its category, on one marketplace, on the day the chart
          was read. It is not a measure of this product category, and none of it is
          counted in the score above.
        </Note>

        {market.items.length ? (
          <>
            <p className="text-muted-foreground mt-3 mb-2 text-sm">
              {market.items.length} listing{market.items.length === 1 ? "" : "s"} in the
              stored charts of {isoDate(market.periodEnd)} have
              &ldquo;{p.trendsTerm || p.name}&rdquo; in the title.
            </p>
            <Table
              head={
                <>
                  <th className="px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Listing</th>
                  <th className="px-3 py-2 font-medium">Category</th>
                  <th className="px-3 py-2 font-medium">Since the last run</th>
                </>
              }
            >
              {market.items.map((it) => {
                const diff =
                  it.previousRank == null ? null : it.previousRank - it.rank;
                return (
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
                    <td className="text-muted-foreground px-3 py-2 text-xs">
                      {it.categoryName}
                    </td>
                    <td className="px-3 py-2">
                      {diff == null ? (
                        <Pill>new to this chart</Pill>
                      ) : diff === 0 ? (
                        <span className="text-muted-foreground text-xs">unchanged</span>
                      ) : (
                        <Pill tone={diff > 0 ? "up" : "down"}>
                          {diff > 0 ? "up" : "down"} {Math.abs(diff)}
                        </Pill>
                      )}
                    </td>
                  </tr>
                );
              })}
            </Table>
          </>
        ) : (
          <Empty>
            No listing in the stored marketplace charts has this product&apos;s search
            term in its title. That is a statement about thirty positions in a handful of
            categories, not about whether the product sells.{" "}
            <Link href="/marketplace" className="underline underline-offset-2">
              See what is stored
            </Link>
            .
          </Empty>
        )}

        <div className="border-border bg-muted/30 mt-4 rounded-lg border px-4 py-3">
          <h3 className="text-sm font-medium">
            Checking this product locally, by hand
          </h3>
          <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
            No free public endpoint publishes Pakistani marketplace demand, so this site
            stores no number for it and does not estimate one. These are the checks a
            reader would have to make themselves, listed so the gap is explicit rather
            than invisible:
          </p>
          <ul className="text-muted-foreground mt-2 space-y-1.5 text-xs leading-relaxed">
            <li>
              &bull; Search &ldquo;{p.trendsTerm || p.name}&rdquo; on Daraz and on
              Facebook Marketplace, and count how many sellers already list it. A category
              with no sellers is not necessarily an opening; it is often a category that
              has been tried.
            </li>
            <li>
              &bull; Compare the local asking price against the landed cost: unit price,
              freight, customs duty and sales tax on the HS code, and the bank&apos;s
              exchange rate on the day. The margin that survives all four is the real one.
            </li>
            <li>
              &bull; Check whether the item needs certification or a regulated import
              route. Anything with a battery, a radio, or a medical claim usually does.
            </li>
            <li>
              &bull; Watch the same searches over several weeks before acting. A single
              reading of a marketplace is one day&apos;s evidence, which is exactly what
              the confidence rules on this site say about every other single reading.
            </li>
          </ul>
          <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
            None of this is advice about whether to buy or sell anything. It is a list of
            what has not been measured.
          </p>
        </div>
      </Section>

      <HowToRead
        title="How to read a demand score"
        points={[
          <>
            <strong>Count the sources before reading the number.</strong> Five sources are
            possible. A score built on one is that source&apos;s reading with an average
            written over it, and the page says so where it happens.
          </>,
          <>
            <strong>Agreement matters more than size.</strong> Four sources agreeing on
            +8% is stronger evidence than one source reporting +300%. The confidence grade
            is built on exactly this and the badge explains itself on hover.
          </>,
          <>
            <strong>Check whether one source is carrying the average.</strong> The
            comparison table shows each source&apos;s share. When one supplies most of the
            magnitude, the direction may still be agreed but the size of the number is
            that one source&apos;s.
          </>,
          <>
            <strong>Small Reddit bases are published but never graded high.</strong> A
            change from 2 posts to 6 really is +200%, and it is also six posts. The
            arithmetic and the confidence claim are judged separately.
          </>,
          <>
            <strong>Attention is not sales.</strong> Everything in the score above measures
            people looking, reading or posting. Nothing in it measures anyone buying.
          </>,
        ]}
      />

      <Section
        title="Assets this product touches"
        lead="Stated relationships, not recommendations. A product can matter to a company without that company selling it."
      >
        {p.assetLinks.length ? (
          <ul className="grid gap-2 sm:grid-cols-2">
            {p.assetLinks.map((l) => (
              <li key={l.id} className="border-border rounded-lg border px-3 py-2 text-sm">
                <Link href={`/asset/${encodeURIComponent(l.asset.symbol)}`} className="font-medium underline underline-offset-2">
                  {l.asset.name}
                </Link>
                <span className="text-muted-foreground ml-2 text-xs">{l.asset.industry.name}</span>
                <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{l.relation}</p>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No assets are linked to this product.</Empty>
        )}
      </Section>

      <Section title="Recent news collected for this product">
        {p.news.length ? (
          <ul className="space-y-2">
            {p.news.map((n) => (
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
          <Empty>No news items matched this product in the stored window.</Empty>
        )}
      </Section>

      <p className="text-muted-foreground mt-8 text-xs">
        Search term: {p.trendsTerm || "not set"} · Wikipedia article: {p.wikiTitle || "not set"}{" "}
        · last written {p.computedAt ? longDate(p.computedAt) : "never"}.
      </p>
    </div>
  );
}
