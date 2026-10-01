import type { Metadata } from "next";
import Link from "next/link";
import { Empty, HowToRead, Note, ProductCard, Section } from "@/components/ui";
import { getProducts } from "@/lib/queries";
import { relativeTime } from "@/lib/format";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Products",
  description:
    "Demand read for consumer products from Google Trends, Wikipedia pageviews, Hacker News, Reddit and Google News. Short windows, named sources, no forecast.",
};

// The blurbs state the rule in `jobs/analysis.py` rather than a paraphrase of it. "Rising"
// is reached two ways and only one of them requires every source to agree, so describing it
// as unanimous would claim more agreement than the group actually holds. There is no
// falling status either: a product whose average went down lands in `flat` with everything
// else that did not rise, and the label has to say so or a reader takes "Flat" as no change.
const GROUPS = [
  {
    key: "rising",
    label: "Rising now",
    tone: "up" as const,
    blurb:
      "Every source that answered points up and the average is at least +5%, or the average is at least +10% on its own.",
  },
  {
    key: "early",
    label: "Early signal",
    tone: "warn" as const,
    blurb:
      "Two or more sources, an average above zero, at least one of them pointing up — but short of the rising threshold.",
  },
  {
    key: "flat",
    label: "Flat or falling",
    tone: "default" as const,
    blurb:
      "No net rise in the measured window. Products whose average fell sit here too, because nothing is ranked as falling.",
  },
  {
    key: "unknown",
    label: "No data",
    tone: "default" as const,
    blurb: "No source answered, so nothing is claimed.",
  },
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
          answered, with no weighting. Confidence says how many sources answered and whether
          they point the same way. As of{" "}
          {all[0]?.computedAt ? relativeTime(all[0].computedAt) : "the last run"}.
        </p>
      </div>

      {groups.map((g) => (
        <Section key={g.key} title={`${g.label} (${g.items.length})`} lead={g.blurb}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {g.items.map((p) => (
              <ProductCard key={p.id} product={p} tone={g.tone} />
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

      <HowToRead
        title="How to read this list"
        points={[
          <>
            <strong>The group is a threshold, not a verdict.</strong> Each blurb above
            states the rule that put a product in that group. Nothing here is a judgement
            about whether the product is any good, or whether the rise will last.
          </>,
          <>
            <strong>Read the confidence badge before the number.</strong> They are separate
            claims. A large score with a low grade is usually one source talking loudly,
            and the grade is the part that says how well evidenced the figure is.
          </>,
          <>
            <strong>The score averages unlike things.</strong> A change in search interest
            and a change in the number of forum posts are not the same measurement, and the
            average of the two is a summary of direction rather than a quantity of demand.
          </>,
          <>
            <strong>&ldquo;No data&rdquo; is not zero.</strong> Those products are missing a
            reading, not reading flat, so they are left out of every ranking rather than
            placed at the bottom of one.
          </>,
          <>
            <strong>Order inside a group is by score, largest first.</strong> Leading a
            group is not the same as being the best evidenced figure in it, and the products
            with no score at all are simply listed by name. Open a product to see each
            source&apos;s own number and window.
          </>,
        ]}
      />

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
