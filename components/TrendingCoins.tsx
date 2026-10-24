import Link from "next/link";
import type { TrendingCoin } from "@/lib/cryptoTrending";

/// The coins worth looking at right now, as cards with the shape of the move on them.
///
/// A sparkline is drawn from the exact closes the card's numbers came from, coloured by the
/// direction over that window rather than by the 24-hour figure beside it -- the two can disagree,
/// and when they do that disagreement is the most useful thing on the card: a coin up 8% on the
/// day whose last four hours are red is a different trade from one that is still climbing.
///
/// Inline SVG, no client JavaScript and no chart library, like every other figure on this site.

function Spark({ points, up }: { points: number[]; up: boolean }) {
  if (points.length < 2) {
    return <div className="text-muted-foreground mt-2 h-10 text-[10px]">no recent bars</div>;
  }
  const w = 200;
  const h = 40;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p - min) / span) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const stroke = up ? "var(--up)" : "var(--down)";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-2 h-10 w-full" role="img" aria-hidden="true">
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function coinPrice(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const d = a >= 1000 ? 2 : a >= 1 ? 4 : a >= 0.01 ? 5 : a >= 0.0001 ? 6 : 8;
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
}

export function TrendingCoins({ coins }: { coins: TrendingCoin[] }) {
  if (coins.length === 0) return null;
  return (
    <section>
      <h2 className="text-lg font-semibold">Trending</h2>
      <p className="text-muted-foreground mt-0.5 text-xs">
        Moving and liquid, both: the biggest 24-hour moves among coins clearing $2M of volume, so
        this is not a leaderboard of tokens nobody trades. The line is the last four hours.
      </p>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {coins.map((c) => {
          const up = (c.change24h ?? 0) >= 0;
          const sparkUp = c.spark.length > 1 ? c.spark[c.spark.length - 1] >= c.spark[0] : up;
          return (
            <Link
              key={c.slug}
              href={`/crypto/${c.slug}`}
              className="border-border hover:bg-muted/40 rounded-lg border p-3 transition"
            >
              <div className="flex items-center gap-2">
                {c.logo ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={c.logo}
                    alt=""
                    width={20}
                    height={20}
                    className="h-5 w-5 rounded-full"
                    loading="lazy"
                  />
                ) : (
                  // A lettered placeholder rather than a broken image: most of the universe has no
                  // logo, and an empty frame on 1,100 cards reads as a fault.
                  <span className="bg-muted text-muted-foreground flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold">
                    {c.ticker.slice(0, 1)}
                  </span>
                )}
                <span className="truncate text-sm font-medium">{c.name}</span>
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="num text-sm font-semibold">{coinPrice(c.price)}</span>
                <span
                  className={`num text-xs font-medium ${up ? "text-[var(--up)]" : "text-[var(--down)]"}`}
                >
                  {up ? "▲" : "▼"} {Math.abs(c.change24h ?? 0).toFixed(2)}%
                </span>
              </div>
              <Spark points={c.spark} up={sparkUp} />
            </Link>
          );
        })}
      </div>
    </section>
  );
}
