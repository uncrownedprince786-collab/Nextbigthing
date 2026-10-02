import type { Metadata } from "next";
import * as React from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AccuracyNote,
  AsOf,
  ConfidenceBadge,
  ConfidenceKey,
  DiscussionBlock,
  Empty,
  GeographyBlock,
  HowToRead,
  Note,
  Pill,
  Section,
  Table,
} from "@/components/ui";
import { ProductDecisionPanel } from "@/components/decision";
import { decideProduct } from "@/lib/productDecision";
import {
  getAccuracy,
  getHumanSignal,
  getProduct,
  getProductMarketplace,
  getProductRegions,
} from "@/lib/queries";
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

/// One collapsed measurement block, and the only disclosure pattern on this page.
///
/// Native `<details>` because this repo ships no client JavaScript by design, and the
/// classes are the same ones `HowToRead` and `ConfidenceKey` already use in
/// components/ui.tsx — the padding that collapses from `sm` up is what gives the summary a
/// 44px tap target on a phone without changing the desktop box. Declared here rather than
/// added to ui.tsx because that file belongs to someone else this week.
///
/// Each group gets its own disclosure instead of one block holding the whole page: a single
/// "Details" toggle means a reader after the marketplace table has to open, and scroll
/// past, every table above it.
function Detail({
  title,
  lead,
  children,
}: {
  title: string;
  lead?: string;
  children: React.ReactNode;
}) {
  return (
    <details className="border-border bg-muted/30 mt-3 rounded-lg border px-4 py-1 sm:py-3">
      <summary className="-my-1 cursor-pointer py-3 text-sm font-medium select-none sm:my-0 sm:py-0">
        {title}
      </summary>
      {lead ? (
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">{lead}</p>
      ) : null}
      <div className="mt-3 mb-3 sm:mb-0">{children}</div>
    </details>
  );
}

/// How far a listing moved on the stored chart, as a word plus a number.
///
/// A rank that went from 9 to 4 improved by five positions, so the delta is
/// previous - current and a positive number reads as "up". Note what this is not: a
/// position on a bestseller chart is an ordering against other listings on one marketplace
/// on one day. It is never a count of units, and nothing on this page turns it into one.
///
/// The same arithmetic is written out at app/marketplace/page.tsx:20 as a `Move` component.
/// That file is not mine to touch, so this copy is kept as small as it can be rather than
/// shared; the two should become one component when both pages have the same owner.
function rankMove(rank: number, previousRank: number | null) {
  if (previousRank == null) return <Pill>new to this chart</Pill>;
  const diff = previousRank - rank;
  if (diff === 0) return <span className="text-muted-foreground text-xs">unchanged</span>;
  return (
    <Pill tone={diff > 0 ? "up" : "down"}>
      {diff > 0 ? "up" : "down"} {Math.abs(diff)}
    </Pill>
  );
}

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const p = await getProduct(slug);
  if (!p) notFound();

  // Matched on the search term against listing titles, and reported as exactly that. It
  // is a text match, not a measurement of the product category, and it is deliberately
  // fetched after the product rather than joined into the demand score.
  const market = await getProductMarketplace(p.trendsTerm || p.name);
  const [discussion, accuracy, geo] = await Promise.all([
    getHumanSignal({ productId: p.id }),
    getAccuracy(30),
    getProductRegions(p.id),
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

  // The whole decision, computed in one place by lib/productDecision.ts so the rules can be
  // tested as rules. The counts passed in are the job's own stored columns rather than
  // `bySource.size`, because `Product.confidence` was graded from exactly this pair — grading
  // the panel from a differently derived count would print a grade next to a number that did
  // not produce it. The table further down shows the rows themselves, so the two can be
  // compared rather than taken on trust.
  //
  // `regions` is flattened out of the stored lists. It is empty for most products today: the
  // geo job keeps being cancelled, so the panel says "geo not stored yet" and means it. The
  // five "where to check" links are built from the term alone and so survive every source
  // being silent, which is the one state this page has to stay useful in.
  const decision = decideProduct({
    name: p.name,
    term: p.trendsTerm || p.name,
    status: p.status,
    demandScore: p.demandScore,
    sourcesAnswered: p.sourcesAnswered,
    sourcesAgree: p.sourcesAgree,
    confidence: p.confidence,
    regions: geo.lists.flatMap((l) => l.rows),
    marketplaceItems: market.items.length,
  });

  return (
    <div>
      {/* Four words and a date. Everything a reader might act on is in the panel below, so
          the header's whole job is to say which product this is and how fresh it is. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{p.name}</h1>
        <Pill tone={p.status === "rising" ? "up" : p.status === "early" ? "warn" : "default"}>
          {p.status}
        </Pill>
        <span className="text-muted-foreground text-xs">
          {p.category} &middot; measured {p.computedAt ? relativeTime(p.computedAt) : "never"}
        </span>
      </div>

      {/* The decision, first, on every product page. Nothing is above it because nothing on
          this page is worth reading before the answer and the links. */}
      <div className="mt-4">
        <ProductDecisionPanel decision={decision} name={p.name} />
      </div>

      {/* Everything that was prose at the top of this page now lives in here, as the
          measurements it was describing.
          `id="detail"` is kept because the old simple-read card linked to it, so a bookmark
          or an inbound link still lands on the evidence rather than on nothing. */}
      <Section
        title="Details"
        lead="Every measurement the panel was built from, each in its own block. Open what you want to check; nothing in here changes the answer above, it is what the answer was read off."
      >
        <div id="detail" className="scroll-mt-4">
          {/* Explained once, in words a tap can reach. The badges below rely on `title=`,
              which no touch device shows. */}
          <ConfidenceKey />
          <Detail
            title="Do the sources agree"
            lead="One row per source, so agreement can be seen rather than taken on trust. A source that did not answer is shown as missing and is not counted as agreement."
          >
            <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="text-sm">
                Demand score{" "}
                <span className={`num font-medium ${toneClass(p.demandScore)}`}>
                  {pct(p.demandScore)}
                </span>
              </span>
              <ConfidenceBadge grade={p.confidence} />
            </div>

            {/* 480px rather than the 640px default: four short columns do not need the
                width, and the source names wrap now instead of being held on one line,
                which is what was pushing this table sideways at 375px. */}
            <Table
              minWidth="480px"
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
                    <td className="px-3 py-2">{label}</td>
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

            {/* One sentence on what the rows add up to. The three paragraphs that used to
                sit here restated the confidence rules a third time; the panel's risk line
                and the confidence badge above already carry that, so what is left is the
                count a reader cannot get from the table at a glance. */}
            <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
              {bySource.size === 0
                ? "No source answered, so nothing is claimed about this product."
                : up.length && down.length
                  ? `${up.length} point up and ${down.length} point down, so the average is a weak read.`
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
              The score is the plain mean of the counted rows. A source sitting at zero counts
              as answering and not as agreeing on a direction.
            </p>
            {p.confidenceNote ? <Note>{p.confidenceNote}</Note> : null}
          </Detail>

          <Detail
            title="What each source measured"
            lead="Change first, then the raw counts behind it. Long window rows are listed for the record and are not part of the score."
          >
            {/* Two free-text columns, so this one is given room to be honest about its
                widths and its first cell is pinned: the reader scrolling right for the
                evidence needs to keep seeing which source they are reading. The text cells
                are capped in characters so a long evidence string widens the scroller
                instead of stretching the table past every other column. */}
            <Table
              minWidth="760px"
              stickyFirstColumn
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
                  <td className="px-3 py-2">{SOURCE_NAME[s.source] ?? s.source}</td>
                  <td className="text-muted-foreground px-3 py-2 text-xs">
                    <span className="wrap-hard block max-w-[30ch]">
                      {METRIC_TEXT[s.metric] ?? s.metric}
                      {SCORED_METRICS.has(s.metric) ? null : (
                        <span className="text-muted-foreground/70"> (not scored)</span>
                      )}
                    </span>
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
                  <td className="num text-muted-foreground px-3 py-2 text-right">
                    {isoDate(s.periodEnd)}
                  </td>
                  <td className="text-muted-foreground px-3 py-2 text-xs">
                    <span className="wrap-hard block max-w-[36ch]">
                      {s.evidence ? s.evidence : "no single item to point at"}
                    </span>
                  </td>
                </tr>
              ))}
            </Table>
            {missing.length ? (
              <Note>
                {[...new Set(missing)].map((m) => SOURCE_NAME[m]).join(", ")} did not answer in
                the last run{p.subreddits ? ` for r/${p.subreddits}` : ""}.{" "}
                {p.wikiTitle
                  ? "The Wikipedia article title and the Trends term come from the seed list and can be wrong; if one source is always empty, the mapping is the first thing to check."
                  : "No Wikipedia title is mapped for this product."}{" "}
                A missing source is not a zero. Reddit is left out of the score entirely when
                the 90 day window it is measured against holds fewer than five posts, because a
                change off a base that small is a rounding artifact rather than a reading.
              </Note>
            ) : null}
          </Detail>

          {/* The written read, kept because it is a stored row with a data note attached,
              and demoted because the panel now says the same thing in four words. */}
          {read || p.summary ? (
            <Detail title="The written read for this product">
              <p className="text-sm leading-relaxed">{read ? read.body : p.summary}</p>
              {read?.dataNote ? <Note>{read.dataNote}</Note> : null}
              {read && p.summary ? (
                <p className="text-muted-foreground mt-3 text-xs leading-relaxed">{p.summary}</p>
              ) : null}
              {!read ? (
                <Note>
                  No demand read has been written for this product yet, so the line above is the
                  seed description and not a measurement.
                </Note>
              ) : null}
            </Detail>
          ) : null}

          <Detail
            title="Current discussion"
            lead="What has been published about this product lately, how it was worded, and whether it reads as promotion. Kept separate from the demand score, which measures search and forum activity rather than wording."
          >
            <DiscussionBlock signal={discussion} targetLabel={p.name} />
            <div className="mt-3">
              <AccuracyNote accuracy={accuracy} />
            </div>
          </Detail>

          <Detail
            title="Where the attention is"
            lead="The geographic breakdown of search interest, from Google Trends' own regional data. Countries and regions are available from free sources; city level is not."
          >
            <GeographyBlock geo={geo} />
            {/* The empty case is the usual case, so it gets a reason and a next click rather
                than a dashed box. The link is the one the panel already built from the
                stored term — this page does not assemble its own search URLs, so there is
                exactly one place a wrong term can produce a wrong link. */}
            {geo.lists.length ? null : (
              <Note>
                Nothing is stored because the geography job has not completed for this product,
                not because the source returned no places. Until it runs, the panel reads
                &ldquo;geo not stored yet&rdquo; and no country is named anywhere on this page.
                To check it by hand, open the <strong>Google Trends</strong> link under{" "}
                <strong>Where to check</strong> at the top of this page: it shows the regional
                breakdown for this term directly.
              </Note>
            )}
          </Detail>

          <Detail
            title="Marketplace listings"
            lead="Where this product's search term shows up on a public marketplace chart. Kept out of the demand score."
          >
            <div className="mb-3">
              <AsOf date={market.periodEnd} />
            </div>
            <Note>
              A bestseller rank is a different claim from a search trend. It says one listing is
              ordered above others in its category, on one marketplace, on the day the chart
              was read. It is not a count of units sold, nothing in this database counts a
              sale, and none of it is counted in the score.
            </Note>

            {market.items.length ? (
              <>
                <p className="text-muted-foreground mt-3 mb-2 text-sm">
                  {market.items.length} listing{market.items.length === 1 ? "" : "s"} in the
                  stored charts of {isoDate(market.periodEnd)} have &ldquo;
                  {p.trendsTerm || p.name}&rdquo; in the title.
                </p>
                <Table
                  minWidth="600px"
                  head={
                    <>
                      <th className="px-3 py-2 font-medium">#</th>
                      <th className="px-3 py-2 font-medium">Listing</th>
                      <th className="px-3 py-2 font-medium">Category</th>
                      <th className="px-3 py-2 font-medium">Since the last run</th>
                    </>
                  }
                >
                  {market.items.map((it) => (
                    <tr key={it.id}>
                      <td className="num text-muted-foreground px-3 py-2">{it.rank}</td>
                      <td className="px-3 py-2">
                        <a
                          href={it.url}
                          rel="noopener noreferrer nofollow"
                          target="_blank"
                          className="wrap-hard block max-w-[34ch] underline underline-offset-2"
                        >
                          {it.title}
                        </a>
                      </td>
                      <td className="text-muted-foreground px-3 py-2 text-xs">
                        <span className="wrap-hard block max-w-[20ch]">{it.categoryName}</span>
                      </td>
                      <td className="px-3 py-2">{rankMove(it.rank, it.previousRank)}</td>
                    </tr>
                  ))}
                </Table>
              </>
            ) : (
              // Same requirement as the geography block: an explicit reason, never a blank.
              // Two different reasons produce this state and a reader is owed both, because
              // "no chart is stored" and "the term is not on the chart" mean opposite things.
              <Empty>
                {market.periodEnd
                  ? `No listing in the charts stored on ${isoDate(market.periodEnd)} has this product's search term in its title. That is a statement about thirty positions in a handful of categories, not about whether anyone is buying it.`
                  : "No marketplace chart is stored at all yet — the weekly job has not run. That is a gap in the collection, not a reading about this product."}{" "}
                <Link href="/marketplace" className="underline underline-offset-2">
                  See what is stored
                </Link>
                . The Amazon, eBay, Daraz and Facebook Marketplace links in{" "}
                <strong>Where to check</strong> above search these marketplaces live, which is
                the only way to see this today.
              </Empty>
            )}
          </Detail>

          <Detail
            title="Assets this product touches"
            lead="Stated relationships, not recommendations. A product can matter to a company without that company selling it."
          >
            {p.assetLinks.length ? (
              <ul className="grid gap-2 sm:grid-cols-2">
                {p.assetLinks.map((l) => (
                  <li key={l.id} className="border-border bg-card rounded-lg border px-3 py-2 text-sm">
                    <Link
                      href={`/asset/${encodeURIComponent(l.asset.symbol)}`}
                      className="font-medium underline underline-offset-2"
                    >
                      {l.asset.name}
                    </Link>
                    <span className="text-muted-foreground ml-2 text-xs">
                      {l.asset.industry.name}
                    </span>
                    <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                      {l.relation}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No assets are linked to this product.</Empty>
            )}
          </Detail>

          <Detail title="Recent news collected for this product">
            {p.news.length ? (
              <ul className="space-y-2">
                {p.news.map((n) => (
                  <li key={n.id} className="border-border border-b pb-2 text-sm last:border-0">
                    <a
                      href={n.url}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className="wrap-hard underline underline-offset-2"
                    >
                      {n.title}
                    </a>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      {n.publisher} &middot; {relativeTime(n.publishedAt)}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No news items matched this product in the stored window.</Empty>
            )}
          </Detail>
        </div>

        {/* Left outside the disclosures on purpose: it is already collapsed, and it is the
            one block that teaches a reader how to read everything inside them. */}
        <HowToRead
          title="How to read a demand score"
          points={[
            <>
              <strong>Count the sources before reading the number.</strong> Five sources are
              possible. A score built on one is that source&apos;s reading with an average
              written over it, and the panel&apos;s risk line says so when it happens.
            </>,
            <>
              <strong>Agreement matters more than size.</strong> Four sources agreeing on +8%
              is stronger evidence than one source reporting +300%. The confidence grade is
              built on exactly this.
            </>,
            <>
              <strong>Small Reddit bases are published but never graded high.</strong> A change
              from 2 posts to 6 really is +200%, and it is also six posts. The arithmetic and
              the confidence claim are judged separately.
            </>,
            <>
              <strong>Attention is not sales.</strong> Everything here measures people
              looking, reading or posting. Nothing in this database counts a single sale, and
              the marketplace rank above is an ordering rather than a quantity.
            </>,
            <>
              <strong>What is not measured is listed, not left out.</strong> No free public
              source publishes local marketplace demand, so none is estimated. The links in{" "}
              <strong>Where to check</strong> are where that gap gets closed by hand.
            </>,
          ]}
        />
      </Section>

      <p className="text-muted-foreground mt-8 text-xs">
        Search term: {p.trendsTerm || "not set"} &middot; Wikipedia article:{" "}
        {p.wikiTitle || "not set"} &middot; last written{" "}
        {p.computedAt ? longDate(p.computedAt) : "never"}.
      </p>
    </div>
  );
}
