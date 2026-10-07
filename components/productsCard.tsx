import Link from "next/link";
import { Pill } from "@/components/ui";

/// The products block on the overview, and the reason it is its own component.
///
/// Products are not assets and `ASSET_CLASSES` cannot carry them. An asset answers "long, short or
/// wait" off a price series; a product answers "is anyone paying attention yet, and where do I go
/// to check" off Google Trends, Wikipedia, Reddit, Hacker News and news counts. They share no
/// decision shape, no market, no entry level and no stop, so putting a products card inside the
/// asset-class grid would mean a card whose every column means something different from its
/// neighbours' — which is how a reader comes to believe a demand score is a price signal.
///
/// It therefore sits in its own band, under the class grid, with its own heading and its own
/// vocabulary: attention rather than action, a score rather than an entry.

/// How many products the card carries. Five, the same as a class card, so the two bands read as
/// one page rather than two designs.
export const TOP_PRODUCTS = 5;

const TONE = { rising: "up", early: "warn", flat: "default", unknown: "default" } as const;
const LABEL = { rising: "RISING", early: "EARLY", flat: "FLAT", unknown: "NO DATA" } as const;

export interface ProductRow {
  slug: string;
  name: string;
  status: string | null;
  demandScore: number | null;
}

/// Rising first, then early, then the rest; within a group the higher demand score first.
///
/// Deliberately the same shape as `byOpportunity` for assets: something-to-look-at before
/// nothing-to-look-at, then the better evidenced of those. A plain sort by score would put a flat
/// product with a high absolute reading above a rising one, which inverts the only thing the
/// status is for.
const RANK: Record<string, number> = { rising: 0, early: 1, flat: 2, unknown: 3 };

export function byAttention(a: ProductRow, b: ProductRow): number {
  const ra = RANK[a.status || "unknown"] ?? 3;
  const rb = RANK[b.status || "unknown"] ?? 3;
  if (ra !== rb) return ra - rb;
  const sa = a.demandScore ?? Number.NEGATIVE_INFINITY;
  const sb = b.demandScore ?? Number.NEGATIVE_INFINITY;
  if (sa !== sb) return sb - sa;
  return a.name.localeCompare(b.name);
}

export function ProductsCard({ rows }: { rows: ProductRow[] }) {
  const top = [...rows].sort(byAttention).slice(0, TOP_PRODUCTS);
  const rising = rows.filter((p) => (p.status || "unknown") === "rising").length;

  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold tracking-tight">Products</h2>
      <p className="text-muted-foreground mt-1 mb-3 max-w-2xl text-sm">
        A demand reading, not a price one. Nothing here counts a sale: the score is built from
        search, encyclopaedia, forum and news attention, so it says whether people are looking, not
        whether anything sold.
      </p>
      {/* `min-w-0` for the reason the class cards carry it: a grid item defaults to
          `min-width: auto` and will not shrink below its content, which on a phone pushes the
          right-hand end of each row outside a `overflow-x-clip` parent and clips it. */}
      <div className="border-border bg-card min-w-0 rounded-lg border p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <Link
            href="/products"
            className="text-sm font-semibold tracking-tight underline-offset-2 hover:underline"
          >
            Most attention now
          </Link>
          <span className="text-muted-foreground text-xs">
            {rows.length} {rows.length === 1 ? "product" : "products"}
            {rows.length ? `, ${rising} rising` : ""}
          </span>
        </div>

        {top.length === 0 ? (
          <p className="text-muted-foreground mt-3 text-xs">
            No stored product reading yet. The demand jobs write one row per product per run, so
            this is a list that has not been through a run rather than a list with nothing in it.
          </p>
        ) : (
          <ul className="mt-3 space-y-1.5">
            {top.map((p) => {
              const key = (p.status || "unknown") as keyof typeof LABEL;
              return (
                <li key={p.slug} className="flex items-baseline justify-between gap-x-3">
                  <Link
                    href={`/product/${encodeURIComponent(p.slug)}`}
                    className="min-w-0 flex-1 truncate text-sm underline-offset-2 hover:underline"
                    title={p.name}
                  >
                    {p.name}
                  </Link>
                  <span className="flex shrink-0 items-baseline gap-x-2">
                    <Pill tone={TONE[key] ?? "default"}>{LABEL[key] ?? "NO DATA"}</Pill>
                    <span className="text-muted-foreground text-micro w-12 text-right">
                      {/* The score is a relative reading on its own 0-100 scale, so it is printed
                          as a bare number with no unit and never compared across products. */}
                      {p.demandScore === null ? "—" : Math.round(p.demandScore)}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        <Link
          href="/products"
          className="text-muted-foreground hover:text-foreground mt-3 inline-block text-xs underline underline-offset-2"
        >
          All {rows.length} products &rarr;
        </Link>
      </div>
    </section>
  );
}
