import type { Metadata } from "next";
import { Card, Note, Section, SourceHealthBlock, Table } from "@/components/ui";
import { getSourceHealth } from "@/lib/queries";

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
    gap: "Size is not one comparable quantity across the site. A stock's is market capitalisation, a fund's is assets under management, and a commodity future publishes neither, so it is shown without a size rather than given a proxy. Rankings only ever compare assets inside one industry, and every table says how many assets in that industry actually carry a size figure.",
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
    measure: "Posts in the product's subreddits through the public search RSS. The last 30 days against the rate over the 90 days immediately before, both cut from the year feed. The longer window is divided by three first, so the two figures cover the same length of time.",
    caveat: "Rate limited and often silent, so a missing value is common and shown as missing. Reddit caps the 30 day feed at 25 results, which is why both windows are read from the year feed instead. Post counts here are small: across all thirty products the largest 90 day window is fifteen posts, so a percentage built on a single post is a rounding artifact and is not published.",
  },
  {
    source: "Google News RSS",
    measure: "Article count for the product name, last 30 days against the 30 before.",
    caveat: "News volume follows a story, so a spike usually means something happened rather than that demand grew.",
  },
];

const NEW_SECTIONS = [
  {
    title: "Pakistan Stock Exchange",
    source:
      "The exchange's own end of day file, dps.psx.com.pk/download/mkt_summary/<date>.Z, a ZIP holding one pipe delimited line per listed symbol.",
    measure:
      "Close and volume per symbol per trading day. Eight sectors, using the exchange's own sector groupings, and every symbol was checked against the closing files for both 2021-12-31 and the latest trading day before being added.",
    gap: "Market capitalisation exists for the latest close only. The exchange publishes a current share count with no history behind it, and multiplying today's share count by a 2021 price would produce a figure that was never true, so these sectors show no pre-AI size at all. Prices and returns are in rupees: a return earned over a period of currency depreciation is not the same quantity as a dollar return, and no conversion is applied.",
  },
  {
    title: "Event windows",
    source:
      "The event date and description come from the public record, with a source URL shown on each event page. The price moves come from closes already stored by this site.",
    measure:
      "For each event, the change between the stored close nearest the event date and the stored close nearest 14 and 30 days later, for every asset that has both. Ranked by the size of the move, largest first, with rises and falls shown separately.",
    gap: "No causation is measured and none is claimed. Over any thirty day window some asset has the largest move whether or not anything happened, so a large number in an event table is evidence the asset moved and nothing else. Events are chosen by hand rather than detected, because detecting them from the price series would select the dates that sit next to large moves and every row would then confirm a relationship the selection had created.",
  },
  {
    title: "Marketplace rankings",
    source:
      "Amazon Best Sellers, the first page of nine categories, read as published. eBay's sold and completed search returns 403 to an ordinary request, so it is not used.",
    measure:
      "The top thirty positions of each category, with each listing's movement against the previous stored run of the same category.",
    gap: "A rank is an order, never a volume: Amazon publishes no units, so nothing here says how much of anything sold. Only the first page is read, because the rank counter restarts on page two and using it would mean guessing an offset. A listing absent from the previous run is reported as new rather than as a rise, because its earlier position was never published. None of this enters any product's demand score.",
  },
];

export default async function MethodologyPage() {
  const health = await getSourceHealth();
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
        title="Current discussion"
        lead="Three readings taken from the news coverage already stored for each asset and product: how much was published, how it was worded, and whether it reads as promotion."
      >
        <Card>
          <h3 className="font-medium">What produces the wording direction</h3>
          <p className="mt-1 text-sm leading-relaxed">
            Every stored headline is matched against a fixed list of directional words. A
            headline matching only positive words is counted positive, only negative words
            negative, and a headline matching both is counted as neither, because
            &ldquo;revenue beats but guidance misses&rdquo; is genuinely both and picking a
            winner on match count would invent a judgement the wording does not support. The
            direction is the net share of the window, and it is published only when the
            window holds at least 8 headlines and the net sits more than 15 points from zero.
            Below either threshold the counts are shown and no direction is.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            This is a word list, not sentiment analysis, and the difference is stated on every
            page that shows it. It reads headlines and never article bodies. It cannot see
            negation, so &ldquo;not a record year&rdquo; counts the positive word. It cannot
            see sarcasm or context at all. Words whose direction flips with context are left
            out of both lists entirely: <em>cut</em> is bad news about guidance and good news
            about interest rates, so it counts as neither.
          </p>
        </Card>

        <Card className="mt-3">
          <h3 className="font-medium">Attention, and why it is not interest</h3>
          <p className="mt-1 text-sm leading-relaxed">
            Attention compares the number of items in the last 30 days with the 30 days
            immediately before, and is called rising or falling only past 25 points, because
            news counts are noisy week to week. When the earlier window holds fewer than 5
            items the comparison is left empty rather than divided: one extra article against
            a base of two is +50%, which is arithmetic and not a change in attention.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            It measures coverage collected, not public interest. A feed that was rate limited
            returns fewer items, which looks identical to a quieter month, so the raw counts
            are always printed beside the percentage.
          </p>
        </Card>

        <Card className="mt-3">
          <h3 className="font-medium">The hype flag</h3>
          <p className="mt-1 text-sm leading-relaxed">
            A separate list of promotional and clickbait wording is counted the same way. The
            flag is raised only when that wording covers at least a fifth of the window{" "}
            <em>and</em> attention is rising at the same time. Promotional wording on its own
            is a publisher&apos;s house style; promotional wording arriving with a jump in
            coverage is the thing worth naming.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            The flag describes how a story is being written, not the thing being written
            about. Heavily promoted and overvalued are different claims and only the first is
            measured here.
          </p>
        </Card>
      </Section>

      <Section
        title="Checking these readings against what happened"
        lead="Every reading is logged on the day it is generated, and the move that followed is measured later. Nothing is published from that log until there is enough of it to divide by."
      >
        <Card>
          <p className="text-sm leading-relaxed">
            When a discussion reading is written it is stored with the factors it rested on
            and the closing price on that day. Thirty and sixty days later the price move
            since that close is measured and stored beside it. Readings with no direction are
            logged too: whether quiet, split coverage is followed by anything is exactly the
            question the log exists to answer, and recording only the confident readings would
            make any eventual figure flattering.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            Nothing is filled in. A window that has not elapsed stays open. A product has no
            price series, so its readings are marked unmeasurable rather than given a number.
            A window falling in a gap in the stored prices keeps its blank instead of
            borrowing a close more than five days away.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            No rate is published until at least 20 readings have matured, and the pages say
            how many are still waiting instead. A hit rate over a handful of rows is the kind
            of impressive-looking number this site exists not to publish. When there is enough
            to report, it will be reported as what followed the readings, measured from the
            stored close — not as a claim that the readings caused the moves, and not as a
            forecast.
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

      <Section
        title="The three newer sections"
        lead="Pakistan, events and marketplace rankings arrived after the original build, and each carries a limit worth stating before the numbers are read."
      >
        <div className="space-y-4">
          {NEW_SECTIONS.map((n) => (
            <Card key={n.title}>
              <h3 className="font-medium">{n.title}</h3>
              <dl className="mt-2 space-y-2 text-sm">
                <div>
                  <dt className="text-muted-foreground text-xs">Source</dt>
                  <dd className="leading-relaxed">{n.source}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">What is measured</dt>
                  <dd className="leading-relaxed">{n.measure}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">What it cannot tell you</dt>
                  <dd className="text-muted-foreground leading-relaxed">{n.gap}</dd>
                </div>
              </dl>
            </Card>
          ))}
        </div>
      </Section>

      {/* These three read only rows the site already stored, which is why they could be
          added without a new source. Each one is a measurement whose limit is sharper than
          its output, so the limit is stated beside it rather than in a footnote. */}
      <Section
        title="Reading a state over time, a move, and a neighbourhood"
        lead="Three readings added over the stored rows rather than over a new source. Each is arithmetic, and each has a limit worth knowing before the number is used."
      >
        <div className="space-y-4">
          <Card>
            <h3 className="font-medium">What has happened to the reason</h3>
            <p className="mt-2 text-sm leading-relaxed">
              A condition read says what the numbers show today. Once that read has been held
              for a few days the useful question is a different one: is the reason it exists
              still there? So the day a directional state first appeared is kept, along with
              the conditions recorded on that day, and every later day is compared against
              them. The conditions are a copy of that day&apos;s row and are never recomputed,
              because recomputing them would answer what we would have said then knowing what
              we know now.
            </p>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
              A reason is <em>weakening</em> when a condition has flipped its verdict or
              stopped being available, and <em>broken</em> when a stored close has passed the
              level the opening day named, or the read now points the other way. Broken is
              final. A later recovery does not reopen it, because the only value of a level
              written down in advance is that passing it cannot be taken back.
            </p>
            <Note>
              A status says whether the recorded conditions are still measurable. It does not
              say the read was right, and the counts are never shown as a percentage, which
              would read as a hit rate for something that measures nothing of the kind.
            </Note>
          </Card>

          <Card>
            <h3 className="font-medium">What a move was shared with</h3>
            <p className="mt-2 text-sm leading-relaxed">
              A 20 session move is split three ways: the median move across every asset quoted
              in the same exchange group, the median across the asset&apos;s own industry peers
              beyond that, and whatever is left. Medians rather than averages, because one
              very large crypto return would otherwise describe a sector nobody is in. The
              three parts add up to the move exactly, so they compete rather than overlap.
            </p>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
              Below three industry peers with enough history the last two parts are not
              separated at all, and the row says the remainder could not be split instead of
              crediting it to the asset. Where the largest two parts are close, neither is
              named.
            </p>
            <Note>
              This is co-movement. It says what an asset moved <em>with</em>, never what moved
              it, and no probability is attached to any of the three: that would need a
              measured outcome rate, and the outcome log has no matured rows yet.
            </Note>
          </Card>

          <Card>
            <h3 className="font-medium">Why something is near today&apos;s news</h3>
            <p className="mt-2 text-sm leading-relaxed">
              When a catalyst is flagged, the relationships already stored are walked outward
              from it: assets linked to the same product, assets concerned by the same dated
              item, and assets in a small enough industry. The walk stops at two steps, skips
              any group large enough that membership says more about the group than about a
              member, and divides every link by the size of the group it came from, so being
              one of two assets linked to a product counts for more than being one of twenty
              in a sector.
            </p>
            <Note>
              A link is a relationship somebody recorded. Something reaching this list is a
              reason to look at it, and never evidence that a move on one end reached the
              other. Every row shows the chain that reached it, so a chain you do not accept
              can be discarded on sight.
            </Note>
          </Card>
        </div>
      </Section>

      <Section
        title="How to research something here yourself"
        lead="The order below is the one the site itself follows, and it is arranged so that the cheap checks come before the expensive ones."
      >
        <ol className="space-y-4 text-sm leading-relaxed">
          <li>
            <strong>1. Ask what would count as an answer, before looking.</strong>{" "}
            &ldquo;Is this rising?&rdquo; has no answer until you say rising against what,
            over what period. Every table on this site names both, and that is the only
            reason any of it can be checked. A question that cannot be answered wrongly
            cannot be answered.
          </li>
          <li>
            <strong>2. Find the number, then find its denominator.</strong> A percentage
            with no base is unreadable. +200% on this site might be six posts against two.
            The product pages print the raw counts next to every Reddit percentage for
            exactly this reason, and a figure whose base was never recorded is deleted
            rather than shown.
          </li>
          <li>
            <strong>3. Count the sources that answered, not the ones that agreed.</strong>{" "}
            Four sources agreeing on a small move is stronger than one source reporting a
            huge one. A source that did not answer is not evidence either way, and a source
            reporting no change still answered.
          </li>
          <li>
            <strong>4. Check whether one input is carrying the result.</strong> An average
            of five numbers where one supplies most of the magnitude is that one
            reading with an average written over it. Every demand score on this site
            discloses its largest contributor&apos;s share.
          </li>
          <li>
            <strong>5. Compare like with like.</strong> A 30 day count against a 90 day
            count is not a change, it is a ratio of two window lengths. Two assets in
            different currencies have comparable returns and incomparable sizes. Most
            errors that survive a first look are this one wearing different clothes.
          </li>
          <li>
            <strong>6. Separate what moved from why it moved.</strong> The first is
            measurable from a price series and the second is not. When a number sits next
            to an event, the honest sentence is that both happened, in that order.
          </li>
          <li>
            <strong>7. Write down what would change your mind.</strong> If nothing would,
            the reading was a conclusion looking for support. The confidence grades here
            exist so that a figure can be reported and doubted in the same breath.
          </li>
        </ol>
        <Note>
          None of this is investment advice, and none of it is a method for making money.
          It is how to avoid being misled by a number, including by one on this site.
        </Note>
      </Section>

      <Section title="What this site will not do">
        <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm leading-relaxed">
          <li>No forecasts, no target prices, no probability of anything happening.</li>
          <li>No paid data, no broker feed, no scraping behind a login, no fingerprint tricks.</li>
          <li>No filling a missing number from a related one. Crypto has no historical size because no free source publishes it.</li>
          <li>No X or Twitter data, because there is no free public source that can be used without a paid account.</li>
          <li>No performance claims. This is a read only archive of measured direction.</li>
          <li>
            No claim that an event caused a price move. The event windows measure what
            moved in a period and stop there.
          </li>
          <li>
            No sales, revenue or margin figures for any product. No marketplace publishes
            them for free and none of them can be derived from a bestseller rank.
          </li>
          <li>
            No conversion between rupees and dollars. Returns compare across currencies
            already; sizes do not, and converting them at today&apos;s rate would misstate
            every historical figure.
          </li>
        </ul>
        <Note>
          Data can be late, revised or wrong. A price feed that misses a day, a Trends term
          that is shared by several products, or a Reddit request that gets rate limited all
          change what a number means. Every page shows the as of date so a stale figure is
          visible rather than hidden.
        </Note>
      </Section>

      <Section
        title="Source health"
        lead="Every source this site reads, and whether it is currently answering. Measured by the audit job on each run, not asserted here."
      >
        <SourceHealthBlock sources={health} />
        <p className="text-muted-foreground mt-3 max-w-3xl text-xs leading-relaxed">
          A feed that quietly stops looks exactly like a quiet week in the data. These four
          states exist to keep those apart: a source can be answering, answering thinly, late,
          or not answering at all. Nothing here is a verdict on the site — it says what was
          collected, so a thin reading can be recognised as thin rather than read as a finding.
        </p>
      </Section>

      <Section title="How the data is refreshed">
        <p className="text-muted-foreground max-w-3xl text-sm leading-relaxed">
          A scheduled job runs the scripts in this repository: prices and news daily for
          both exchanges, rankings and event windows daily, and product signals and the
          marketplace charts weekly, because Reddit and Wikipedia rate limit and the
          bestseller charts move faster than anything here is meant to track.
          Each run writes rows with a period end date, and this site reads only what has been
          written. If a job fails, the old rows stay and the freshness table on the front
          page shows the date of the last successful run. Nothing on the site is computed in
          the browser.
        </p>
      </Section>
    </div>
  );
}
