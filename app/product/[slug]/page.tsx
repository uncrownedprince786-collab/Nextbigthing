import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, ConfidenceBadge, Empty, Note, Pill, Section, Table } from "@/components/ui";
import { getProduct } from "@/lib/queries";
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
  reddit_posts_30d_change_pct: "Posts, 30 days against the 90 before",
  gnews_articles_30d_change_pct: "Articles, 30 days against the 30 before",
  reddit_posts_30d: "Posts in the last 30 days",
  reddit_posts_90d_base: "Posts in the 90 days before that",
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
              : flat.length && !up.length && !down.length
                ? `All ${bySource.size} that answered report no change.`
                : `All ${bySource.size} that answered point ${up.length ? "up" : "down"}.`}{" "}
          The score is the plain mean of the counted rows, so a large single reading can carry
          it, which is what the confidence grade is reporting.
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
