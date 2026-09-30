import type { Metadata } from "next";
import { Card, Note, Section, Table } from "@/components/ui";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Methodology",
  description:
    "Every ranking and demand number on this site, the free source it comes from, the formula behind it, and what is deliberately left blank.",
};

const RANKINGS = [
  {
    basis: "Size at a past date",
    formula: "Price on the snapshot date multiplied by shares outstanding.",
    source: "Yahoo Finance for equities and funds, CoinPaprika for crypto market cap",
    gap: "Crypto historical market cap is not published by any free source, so crypto only has a current size. Some funds do not publish shares outstanding, so they have no size at all.",
  },
  {
    basis: "Size now",
    formula: "Same formula, using the newest stored close.",
    source: "Yahoo Finance, CoinPaprika",
    gap: "A stock split or new issue between the two dates is not adjusted for, so a rank change can reflect a share count change rather than a price change.",
  },
  {
    basis: "Total return",
    formula: "Close on the later date divided by close on the earlier date, minus one. Two windows: 2019-01-01 to the last close of 2021, and that date to the newest close. Price only, dividends are not added.",
    source: "Yahoo Finance, Binance klines",
    gap: "Because dividends are excluded, a high yielding asset looks weaker than a total return figure would suggest. The number is labelled as a price return everywhere it appears.",
  },
  {
    basis: "24 month relative strength",
    formula: "The asset's 24 month return minus the average 24 month return of the other assets in the same industry. A positive number means the asset beat its own peers.",
    source: "Yahoo Finance, Binance",
    gap: "It is a ranking, not a prediction. A strong number can follow a large fall, and an asset with less than 24 months of history is left out of the list rather than given a short window.",
  },
];

const SIGNALS = [
  {
    source: "Google Trends",
    measure: "Search interest for the product term, weekly, last 8 weeks against the 8 before.",
    caveat: "Relative interest on a 0 to 100 scale inside one request, so it is a direction and a rough size, not a search count. A term shared by several products will move for all of them.",
  },
  {
    source: "Wikipedia pageviews",
    measure: "Pageviews for the mapped article, last 8 weeks against the 8 before.",
    caveat: "Interest in the article is not interest in buying. The article title is chosen in the seed list, and for a few products the page does not exist, so the source is simply missing.",
  },
  {
    source: "Hacker News",
    measure: "Number of stories in the Algolia search index mentioning the product, last 90 days against the 90 before.",
    caveat: "A very small audience. Useful as one input, never on its own.",
  },
  {
    source: "Reddit",
    measure: "Posts in the product's subreddits through the public search RSS, last 30 days against the 90 days before, both cut from the year feed.",
    caveat: "Rate limited and often silent, so a missing value is common and shown as missing. Reddit caps the 30 day feed at 25 results, which is why both windows are read from the year feed instead. Post counts here are small: across all thirty products the largest 90 day window is fifteen posts, so a percentage built on a single post is a rounding artifact and is not published.",
  },
  {
    source: "Google News RSS",
    measure: "Article count for the product name, last 30 days against the 30 before.",
    caveat: "News volume follows a story, so a spike usually means something happened rather than that demand grew.",
  },
];

export default function MethodologyPage() {
  return (
    <div className="max-w-4xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Methodology</h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Every figure on this site is computed by a script from a free public source and
          stored in a database. Nothing is estimated, filled in or carried over from another
          period. Where a source cannot answer, the cell says so.
        </p>
      </div>

      <Section title="Snapshot dates" lead="The pre-AI window ends at the last trading day of 2021. The current window ends at the newest stored close.">
        <Table
          head={
            <>
              <th className="px-3 py-2 font-medium">Window</th>
              <th className="px-3 py-2 font-medium">Dates used</th>
              <th className="px-3 py-2 font-medium">Why</th>
            </>
          }
        >
          <tr>
            <td className="px-3 py-2">Before the AI wave</td>
            <td className="num px-3 py-2">2019-01-01 to 2021-12-31</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">
              The two years before the large language model release cycle began.
            </td>
          </tr>
          <tr>
            <td className="px-3 py-2">Since then</td>
            <td className="num px-3 py-2">2021-12-31 to newest close</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">
              The same boundary, so the two windows are directly comparable.
            </td>
          </tr>
          <tr>
            <td className="px-3 py-2">Relative strength</td>
            <td className="num px-3 py-2">24 months to newest close</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">
              Long enough to include a full cycle of winners and losers.
            </td>
          </tr>
        </Table>
      </Section>

      <Section title="Rankings" lead="Four bases, each stored as a row with its own source and as of date.">
        <ul className="space-y-3">
          {RANKINGS.map((r) => (
            <li key={r.basis}>
              <Card>
                <h3 className="font-medium">{r.basis}</h3>
                <p className="mt-1 text-sm leading-relaxed">{r.formula}</p>
                <p className="text-muted-foreground mt-2 text-xs">Source: {r.source}</p>
                <Note>{r.gap}</Note>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Product demand" lead="Five sources, read on the same short windows for all thirty products.">
        <ul className="space-y-3">
          {SIGNALS.map((s) => (
            <li key={s.source}>
              <Card>
                <h3 className="font-medium">{s.source}</h3>
                <p className="mt-1 text-sm leading-relaxed">{s.measure}</p>
                <Note>{s.caveat}</Note>
              </Card>
            </li>
          ))}
        </ul>
        <Card className="mt-3">
          <h3 className="font-medium">Demand score and status</h3>
          <p className="mt-1 text-sm leading-relaxed">
            The score is the plain average of the percentage change of every source that
            answered, with no weighting and no adjustment. A source that did not answer is
            left out of the average, and is never counted as a zero. Status is{" "}
            <strong>rising</strong> when every source that answered is up and the average is
            at least 5 points, or when the average is at least 10,{" "}
            <strong>early</strong> when the average is positive, something is up, and at
            least two sources answered, <strong>flat</strong> otherwise, and{" "}
            <strong>unknown</strong> when nothing answered. A single source answering is
            reported as <strong>flat</strong>, not as early interest, because one reading is
            not a trend. Status is a label for the measured window and nothing more.
          </p>
        </Card>
      </Section>

      <Section
        title="Confidence"
        lead="Every ranking, product and written line carries a grade, and the reason for it is stored next to the grade rather than left to the reader."
      >
        <p className="text-muted-foreground max-w-3xl text-sm leading-relaxed">
          A grade of high, medium, low or no data describes how well evidenced a figure is.
          It is not a view on direction, and it is not a prediction. A number can be accurate
          and still be thinly measured, so the two are judged separately.
        </p>
        <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm leading-relaxed">
          <li>
            <strong className="text-foreground">Rankings.</strong> An industry average is
            compared with its own median. If the two are far apart, the average is not a fair
            description of a typical peer, so the row is graded down and the gap is stated. The
            published rank is left as it is, because changing the comparator would quietly
            rewrite history.
          </li>
          <li>
            <strong className="text-foreground">Products.</strong> Agreement is measured
            against the average, not against whichever side has more sources. Three sources
            down and one up is a minority position. Sources that split up and down, or where
            the average and the median fall on opposite sides of zero, cap the grade at
            medium. One source supplying most of the average is disclosed but does not cap the
            grade by itself, because several sources can agree on direction while one supplies
            the size.
          </li>
          <li>
            <strong className="text-foreground">Small denominators.</strong> A Reddit
            percentage is not published at all when the window it is measured against holds
            fewer than five posts, because one post against none is a rounding artifact. When
            the base is between five and nine the percentage is published, since the arithmetic
            is correct, but the grade is capped at medium: at that scale a single post moves the
            number by ten to twenty percent. No product currently grades high, and the reason
            is written on the product rather than left for you to infer.
          </li>
        </ul>
        <Note>
          A grade is never more confident than the sentence beside it. The site is more
          willing to show a small number honestly labelled than a large one that hides how
          little is behind it.
        </Note>
      </Section>

      <Section title="What this site will not do">
        <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm leading-relaxed">
          <li>No forecasts, no target prices, no probability of anything happening.</li>
          <li>No paid data, no broker feed, no scraping behind a login, no fingerprint tricks.</li>
          <li>No filling a missing number from a related one. Crypto has no historical size because no free source publishes it.</li>
          <li>No X or Twitter data, because there is no free public source that can be used without a paid account.</li>
          <li>No performance claims. This is a read only archive of measured direction.</li>
        </ul>
        <Note>
          Data can be late, revised or wrong. A price feed that misses a day, a Trends term
          that is shared by several products, or a Reddit request that gets rate limited all
          change what a number means. Every page shows the as of date so a stale figure is
          visible rather than hidden.
        </Note>
      </Section>

      <Section title="How the data is refreshed">
        <p className="text-muted-foreground max-w-3xl text-sm leading-relaxed">
          A scheduled job runs the scripts in this repository: prices and news daily,
          rankings daily, product signals weekly because Reddit and Wikipedia rate limit.
          Each run writes rows with a period end date, and this site reads only what has been
          written. If a job fails, the old rows stay and the freshness table on the front
          page shows the date of the last successful run. Nothing on the site is computed in
          the browser.
        </p>
      </Section>
    </div>
  );
}
