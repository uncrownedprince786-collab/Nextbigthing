import type { Metadata } from "next";
import Link from "next/link";
import { Card, Empty, Note, Pill, Section } from "@/components/ui";
import { getProducts } from "@/lib/queries";
import { pct, relativeTime, toneClass } from "@/lib/format";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Products",
  description:
    "Demand read for consumer products from Google Trends, Wikipedia pageviews, Hacker News, Reddit and Google News. Short windows, named sources, no forecast.",
};

const GROUPS = [
  { key: "rising", label: "Rising now", tone: "up" as const, blurb: "Every source that answered points up." },
  { key: "early", label: "Early signal", tone: "warn" as const, blurb: "Net positive, but weaker or built on few sources." },
  { key: "flat", label: "Flat", tone: "default" as const, blurb: "No clear direction in the measured window." },
  { key: "unknown", label: "No data", tone: "default" as const, blurb: "No source answered, so nothing is claimed." },
];

export default async function ProductsPage() {
  const all = await getProducts();
  const groups = GROUPS.map((g) => ({
    ...g,
    items: all.filter((p) => (p.status || "unknown") === g.key),
  })).filter((g) => g.items.length);

  return (
    <div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Products</h1>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm">
          Thirty consumer products, each read from the same five free sources. Windows are
          short on purpose: eight weeks of search interest, eight weeks of pageviews, ninety
          days of forum and news items. A short window measures attention, not sales.
        </p>
        <p className="text-muted-foreground mt-2 text-xs">
          Demand score is the plain average of the percentage change of each source that
          answered, with no weighting. As of {all[0]?.computedAt ? relativeTime(all[0].computedAt) : "the last run"}.
        </p>
      </div>

      {groups.map((g) => (
        <Section key={g.key} title={`${g.label} (${g.items.length})`} lead={g.blurb}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {g.items.map((p) => (
              <Card key={p.id} href={`/product/${p.slug}`}>
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-medium">{p.name}</h3>
                  <Pill tone={g.tone}>{p.status}</Pill>
                </div>
                <p className="text-muted-foreground mt-1 text-xs">{p.category}</p>
                <p className={`num mt-3 text-lg font-semibold ${toneClass(p.demandScore)}`}>
                  {pct(p.demandScore)}
                </p>
                <p className="text-muted-foreground mt-1 line-clamp-3 text-xs leading-relaxed">{p.summary}</p>
                {p.demandNote ? (
                  <p className="text-muted-foreground/90 mt-2 text-[11px] leading-relaxed">{p.demandNote}</p>
                ) : null}
              </Card>
            ))}
          </div>
        </Section>
      ))}

      {groups.length === 0 ? (
        <Empty>
          No products have been seeded yet. Run <code>python jobs/seed.py</code> and then{" "}
          <code>python jobs/signals.py</code>.
        </Empty>
      ) : (
        <Note>
          Demand read is not a sales forecast. A jump in search interest can follow a price
          cut, a launch or a news story, and the source does not say which. Every product
          page shows the individual source numbers and the evidence link, so the read can be
          checked rather than trusted.
        </Note>
      )}

      <p className="text-muted-foreground mt-8 text-xs">
        Looking for the assets behind these products? Each product page lists the tickers it
        touches, with the relationship stated. See also{" "}
        <Link href="/industry/mega-cap-tech" className="underline underline-offset-2">
          the industry rankings
        </Link>
        .
      </p>
    </div>
  );
}
