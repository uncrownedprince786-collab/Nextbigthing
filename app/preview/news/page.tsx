import type { Metadata } from "next";
import { Empty, Note, Section } from "@/components/ui";
import { getRecentMarketNews, getUpcoming } from "@/lib/queries";

/// Screen 5 — news, events and catalysts, in time order.
///
/// Two rules the data forces. **Publication time is not retrieval time**: `publishedAt` is what is
/// shown, and the moment a row was collected is never substituted for it — that substitution is
/// exactly what makes an old story read as today's. And **one story is one row**:
/// `getRecentMarketNews` already carries `lineageId`, so a headline syndicated across five
/// publishers appears once under the first that published it rather than five times.
export const revalidate = 900;
export const metadata: Metadata = { title: "News and events" };

function stamp(d: Date | null | undefined) {
  return d ? `${new Date(d).toISOString().slice(0, 16).replace("T", " ")}Z` : "undated";
}

export default async function NewsPage() {
  const [news, upcoming] = await Promise.all([
    getRecentMarketNews(7, 120).catch(() => []),
    getUpcoming({ take: 10 }).catch(() => []),
  ]);

  const seen = new Set<string>();
  const unique = news.filter((n) => {
    const key = n.lineageId ?? n.id;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const folded = news.length - unique.length;

  return (
    <>
      <Section title="Dated events ahead">
        {upcoming.length === 0 ? (
          <Empty>No scheduled events are stored for the window ahead.</Empty>
        ) : (
          <ul className="space-y-2 text-sm">
            {upcoming.map((e) => (
              <li key={e.id}>
                <span className="text-muted-foreground">
                  {new Date(e.date).toISOString().slice(0, 10)}
                </span>{" "}
                {e.name}
                {e.category ? (
                  <span className="text-muted-foreground"> · {e.category}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Recent headlines">
        <Note>
          Times are publication times as the source published them, not when the row was
          collected.
          {folded > 0
            ? ` ${folded} syndicated duplicate${folded === 1 ? "" : "s"} folded into the first publisher.`
            : null}
        </Note>
        {unique.length === 0 ? (
          <Empty>No headlines are stored for the last seven days.</Empty>
        ) : (
          <ul className="space-y-2 text-sm">
            {unique.slice(0, 60).map((n) => (
              <li key={n.id}>
                <span className="text-muted-foreground">{stamp(n.publishedAt)}</span>{" "}
                {n.url ? (
                  <a
                    href={n.url}
                    className="underline underline-offset-2"
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {n.title}
                  </a>
                ) : (
                  n.title
                )}
                {n.asset ? (
                  <span className="text-muted-foreground"> · {n.asset.symbol}</span>
                ) : null}
                {n.publisher ? (
                  <span className="text-muted-foreground"> · {n.publisher}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}
