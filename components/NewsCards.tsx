import { relativeTime } from "@/lib/format";

/// Recent coverage of one coin, as cards with the article's own picture.
///
/// A headline with a picture is read and a list of blue links is skimmed past, which is the whole
/// reason this is not the list it replaced. The image is the article's `og:image`, filled in by
/// `jobs/news_images.py`; where a publisher advertises none the card falls back to the coin's own
/// logo, and where there is no logo either to a lettered tile. Three fallbacks deep because the
/// grid has to look like a grid even when the third column is a wire story from a site that
/// publishes no meta tags.
///
/// Images are loaded lazily and the frame is fixed before they arrive, so a slow publisher's CDN
/// cannot push the rest of the page around as it loads.

export interface NewsItem {
  id: string;
  title: string;
  url: string;
  publisher: string;
  publishedAt: Date;
  outlets: number;
  imageUrl: string | null;
}

export function NewsCards({
  items,
  name,
  fallbackLogo,
  ticker,
}: {
  items: NewsItem[];
  name: string;
  fallbackLogo: string | null;
  ticker: string;
}) {
  if (items.length === 0) return null;
  const [lead, ...rest] = items;
  const cards = [lead, ...rest.slice(0, 5)];

  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">{name} latest news</h2>
      <div className="mt-3 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((n) => (
          <a
            key={n.id}
            href={n.url}
            target="_blank"
            rel="noopener noreferrer"
            className="group block"
          >
            <div className="bg-muted relative aspect-[16/9] w-full overflow-hidden rounded-lg">
              {n.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={n.imageUrl}
                  alt=""
                  loading="lazy"
                  className="h-full w-full object-cover transition group-hover:scale-[1.02]"
                />
              ) : fallbackLogo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={fallbackLogo}
                  alt=""
                  loading="lazy"
                  className="absolute top-1/2 left-1/2 h-12 w-12 -translate-x-1/2 -translate-y-1/2 rounded-full opacity-60"
                />
              ) : (
                <span className="text-muted-foreground absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-2xl font-semibold">
                  {ticker.slice(0, 3)}
                </span>
              )}
            </div>
            <h3 className="mt-2 text-sm leading-snug font-semibold group-hover:underline">
              {n.title}
            </h3>
            <div className="text-muted-foreground mt-1.5 text-xs">
              {n.publisher}
              {/* How many desks carried the story: the difference between one outlet's take and
                  something the whole market read. */}
              {n.outlets > 1 ? ` and ${n.outlets - 1} more` : ""}
            </div>
            <div className="text-muted-foreground text-xs">{relativeTime(n.publishedAt)}</div>
          </a>
        ))}
      </div>
      <p className="text-muted-foreground mt-3 text-xs">
        The last seven days only, newest first. Nothing here is read by the model — the direction
        above is computed from price and order flow alone, and these sit beside it rather than
        behind it.
      </p>
    </section>
  );
}
