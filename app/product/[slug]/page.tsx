import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, Empty, Note, Pill, Section, Table } from "@/components/ui";
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

const SOURCE_NAME: Record<string, string> = {
  googleTrends: "Google Trends",
  wikipedia: "Wikipedia pageviews",
  hackerNews: "Hacker News",
  reddit: "Reddit",
  googleNews: "Google News",
};

const METRIC_TEXT: Record<string, string> = {
  trends_8w_vs_8w_pct: "Search interest, 8 weeks against the 8 before",
  wiki_views_8w_vs_8w_pct: "Pageviews, 8 weeks against the 8 before",
  hn_stories_90d_change_pct: "Stories, 90 days against the 90 before",
  reddit_posts_30d_change_pct: "Posts, 30 days against the 90 before",
  gnews_articles_30d_change_pct: "Articles, 30 days against the 30 before",
};

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const p = await getProduct(slug);
  if (!p) notFound();

  const read = p.analysis[0];
  const changeSignals = p.signals.filter((s) => s.metric.endsWith("_pct"));
  const levelSignals = p.signals.filter((s) => !s.metric.endsWith("_pct"));
  const answered = changeSignals.filter((s) => s.value != null);
  const missing = ["googleTrends", "wikipedia", "hackerNews", "reddit", "googleNews"].filter(
    (src) => !answered.some((s) => s.source === src),
  );

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
        title="What each source measured"
        lead="Change first, then the raw level. A source with no value is listed as missing rather than estimated."
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
          {[...changeSignals, ...levelSignals].map((s) => (
            <tr key={s.id}>
              <td className="px-3 py-2 whitespace-nowrap">{SOURCE_NAME[s.source] ?? s.source}</td>
              <td className="text-muted-foreground px-3 py-2 text-xs">
                {METRIC_TEXT[s.metric] ?? s.metric}
              </td>
              <td
                className={`num px-3 py-2 text-right font-medium ${
                  s.metric.endsWith("_pct") ? toneClass(s.value) : ""
                }`}
              >
                {s.value == null ? "not available" : s.metric.endsWith("_pct") ? pct(s.value) : count(s.value)}
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
            {missing.map((m) => SOURCE_NAME[m]).join(", ")}{" "}
            {missing.length === 1 ? "did" : "did"} not answer in the last run
            {p.subreddits ? ` for r/${p.subreddits}` : ""}
            . {p.wikiTitle
              ? "The Wikipedia article title and the Trends term come from the seed list and can be wrong; if one source is always empty, the mapping is the first thing to check."
              : "No Wikipedia title is mapped for this product."}
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
