import type { Metadata } from "next";
import Link from "next/link";
import { Card, ConfidenceBadge, Empty, HowToRead, Note, Pill, Section } from "@/components/ui";
import { EVENT_DUPLICATE_WITHIN_DAYS, getEvents, getRecentMarketNews } from "@/lib/queries";
import { headlineOf, rankHeadlines } from "@/lib/newsRank";
import { EVENT_SOON_DAYS } from "@/lib/decision";
import { calendarDaysUntil, isoDate, longDate, startOfToday } from "@/lib/format";

export const revalidate = 3600;

/// One stored news row as this page reads it. Taken from the query rather than redeclared so
/// that a column added there reaches the strip without a second edit here.
type MarketNewsRow = Awaited<ReturnType<typeof getRecentMarketNews>>[number];

export const metadata: Metadata = {
  title: "Event calendar",
  description:
    "Dated items that have not happened yet, soonest first, and separately the measured price moves after dated events that have. A diary against forgetting, not a reason to hold anything.",
};

const CATEGORY_TONE: Record<string, "default" | "warn" | "up" | "down"> = {
  conflict: "warn",
  policy: "default",
  technology: "up",
  market: "down",
};

/// One line per dated item: the day, how far off it is, what kind of item it is, and the asset
/// it is attached to.
///
/// Four facts and deliberately nothing else. The old index card carried a summary paragraph and
/// a row reading "no stored closes span this window", which for a date in the future is not a
/// gap in the data — it is the future, and 94 cards each announcing it filled the page with an
/// absence that was never going to be filled.
///
/// The link goes to the asset rather than to `/event/<slug>`. Measured impact rows only exist
/// for events that have happened: in the stored data every scheduled row has zero of them, so
/// an event link here would send a reader to a page whose only content is a note saying there
/// is nothing to measure yet. The asset page is where a reader can actually do something with
/// the date.
///
/// `UpcomingBlock` renders almost exactly this row, and is not used here for one reason: it
/// closes with a four-line paragraph about how providers publish these dates, which belongs
/// once on a page and not three times down it. That paragraph is printed below the sections
/// instead.
function CalendarRows({
  rows,
  today,
}: {
  rows: Awaited<ReturnType<typeof getEvents>>;
  today: Date;
}) {
  return (
    <ul className="divide-border border-border divide-y rounded-lg border">
      {rows.map((e) => {
        const days = calendarDaysUntil(e.date, today);
        const asset = e.links[0]?.asset ?? null;
        const product = e.links[0]?.product ?? null;
        return (
          <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2">
            <span className="num text-muted-foreground w-24 shrink-0 text-xs">
              {isoDate(e.date)}
            </span>
            <span className="w-20 shrink-0">
              <Pill tone={days <= EVENT_SOON_DAYS ? "warn" : "default"}>
                {days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days}d`}
              </Pill>
            </span>
            {/* The date and the countdown are already 176px of fixed width, so below `sm` the
                name takes its own line under them instead of the 155px remainder. */}
            <span className="w-full min-w-0 text-sm sm:w-auto sm:flex-1">
              {asset ? (
                <Link
                  href={`/asset/${encodeURIComponent(asset.symbol)}`}
                  className="num font-medium underline underline-offset-2"
                >
                  {asset.symbol}
                </Link>
              ) : (
                <span className="font-medium">{product?.name ?? e.name}</span>
              )}
              {" — "}
              <span className="text-muted-foreground">{e.category}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/// The market news strip: published items, newest first, one row per story.
///
/// Built to the same shape as `CalendarRows` on purpose — same fixed date column, same pill
/// width, same wrapping behaviour below `sm` — so the two blocks read as one page rather than
/// as a calendar with a feed bolted under it. The pill says how long ago rather than how long
/// until, which is the one visible difference and is the distinction the section lead draws.
function NewsStrip({
  rows,
  today,
}: {
  rows: ReturnType<typeof rankHeadlines<MarketNewsRow>>;
  today: Date;
}) {
  return (
    <ul className="divide-border border-border divide-y rounded-lg border">
      {rows.map((n) => {
        // Counted in calendar days from local midnight, exactly as `calendarDaysUntil` does, and
        // never from `Date.now()`. `publishedAt` is a timestamp rather than a date, so a diff
        // from the current clock rounds differently depending on the hour an item was filed:
        // the first draft of this block printed "2026-10-02 / yesterday" two rows above
        // "2026-10-03 / yesterday". Two rows on one page disagreeing about what yesterday was
        // is worse than either label.
        const published = new Date(n.publishedAt);
        published.setHours(0, 0, 0, 0);
        const days = Math.max(0, -calendarDaysUntil(published, today));
        return (
          <li key={n.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2">
            <span className="num text-muted-foreground w-24 shrink-0 text-xs">
              {isoDate(published)}
            </span>
            <span className="w-20 shrink-0">
              <Pill>{days === 0 ? "today" : days === 1 ? "yesterday" : `${days}d ago`}</Pill>
            </span>
            <span className="w-full min-w-0 text-sm sm:w-auto sm:flex-1">
              {n.asset ? (
                <Link
                  href={`/asset/${encodeURIComponent(n.asset.symbol)}`}
                  className="num font-medium underline underline-offset-2"
                >
                  {n.asset.symbol}
                </Link>
              ) : null}
              {" — "}
              {/* `nofollow` with the rest: these are outbound links to whoever a feed named,
                  carried in bulk, and this site does not vouch for any of them. */}
              <a
                href={n.url}
                target="_blank"
                rel="noopener noreferrer nofollow"
                className="underline underline-offset-2"
              >
                {headlineOf(n.title, n.publisher)}
                <span className="sr-only"> (opens in a new tab)</span>
              </a>{" "}
              <span className="text-muted-foreground">
                {n.publisher}
                {n.outlets > 1 ? ` and ${n.outlets - 1} more` : ""}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default async function EventsPage() {
  const today = startOfToday();
  // Soonest first, with provider restatements of one earnings date already folded away in
  // `getEvents`. Everything below is a slice of this one ordering, so no section can disagree
  // with another about which date comes next.
  // Two independent reads, in parallel: the calendar and the week's published news are
  // different claims from different tables and neither waits on the other.
  const [events, recentNews] = await Promise.all([getEvents(), getRecentMarketNews(7)]);

  // Ranked by the same reading the asset pages use, then capped. Eight is the most this block
  // can hold without becoming the page: the calendar is still what this page is for, and a
  // ninth row would push "Next 30 days" off a phone screen entirely.
  const marketNews = rankHeadlines(recentNews).slice(0, 8);

  const upcoming = events.filter((e) => calendarDaysUntil(e.date, today) >= 0);
  const next7 = upcoming.filter((e) => calendarDaysUntil(e.date, today) <= 7);
  const next30 = upcoming.filter((e) => {
    const d = calendarDaysUntil(e.date, today);
    return d > 7 && d <= 30;
  });
  const later = upcoming.filter((e) => calendarDaysUntil(e.date, today) > 30);

  // The second concept on this page, and the only rows on it that were measured rather than
  // merely published. An event with no stored impact rows is not shown here at all: a heading
  // reading "past measured windows" above a row with nothing measured under it would be the
  // same empty block this page was built to delete.
  const past = events.filter((e) => calendarDaysUntil(e.date, today) < 0);
  const measured = past.filter((e) => e._count.impacts > 0);
  const passedUnmeasured = past.length - measured.length;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Event calendar</h1>

      {/* The first thing on the page is what the page is not. A calendar sitting on a site that
          publishes LONG and SHORT reads as a list of reasons to act unless it says otherwise in
          the first sentence, and a dated earnings report is the weakest possible reason: it is
          known to everyone, it was known weeks ago, and its direction is not in it. */}
      <p className="text-muted-foreground mt-2 max-w-3xl text-sm">
        Dates, not decisions. Nothing on this page sets a direction. A scheduled earnings or
        dividend date is context: when one falls within {EVENT_SOON_DAYS} days, the decision
        panel on an asset page marks the timing <strong>CARE</strong> and leaves the direction
        exactly as the price and the news left it. The reason a diary like this is worth keeping
        is forgetting, not foresight — a date that was public for weeks is the commonest way a
        move arrives and still surprises somebody.
      </p>

      <Note>
        The two halves of this page are different kinds of claim and are not mixed. Above, dated
        items somebody has published, which have not happened and are not measured. Below, price
        moves measured from stored closes after dates that have passed. A measured move is
        evidence that an asset moved in a window; it is not evidence that the event moved it, and
        nothing here says what any future date will do.
      </Note>

      <Section
        title="Next 7 days"
        lead="Soonest first. A date inside this window is the one worth knowing about before opening anything today."
      >
        {next7.length ? (
          <CalendarRows rows={next7} today={today} />
        ) : (
          <Empty>
            Nothing is published for the next seven days. That is a quiet week in the stored
            calendar, not a missing feed — the next thirty days are below.
          </Empty>
        )}
      </Section>

      {/* The strip. It sits directly under the seven day calendar because it answers the question
          that calendar raises and cannot answer: in a normal week every dated row is an
          ex-dividend date, and none of the things that actually moved a price was on a calendar
          at all. Newest first, which is this block's own "soonest first" — these have happened,
          so the most recent is the most current. */}
      <Section
        title="Market news and statements"
        lead="What has actually been published in the last seven days, most recent first. These have already happened, so they are not calendar entries and are not mixed with the dates above."
      >
        {marketNews.length ? (
          <NewsStrip rows={marketNews} today={today} />
        ) : (
          <Empty>
            No market news was stored in the last seven days. That is a quiet week in the feeds
            rather than an empty calendar.
          </Empty>
        )}
      </Section>

      <Section
        title="Next 30 days"
        lead="The rest of the month, same ordering, excluding anything already listed above."
      >
        {next30.length ? (
          <CalendarRows rows={next30} today={today} />
        ) : (
          <Empty>
            Nothing is published between next week and thirty days out.
          </Empty>
        )}
      </Section>

      <Section title="Later">
        {later.length ? (
          // Collapsed, because this is the part that used to be the first screen. These dates
          // are real and a reader occasionally wants them; none of them is news today, and a
          // calendar whose top row is fifteen months away has buried the only row that matters.
          <details className="border-border bg-muted/30 rounded-lg border px-4 py-1 text-sm sm:py-3">
            <summary className="-my-1 cursor-pointer py-3 font-medium select-none sm:my-0 sm:py-0">
              <span className="num">{later.length}</span> dates more than 30 days out
            </summary>
            <div className="mt-3 mb-3 sm:mb-0">
              <CalendarRows rows={later} today={today} />
            </div>
          </details>
        ) : (
          <Empty>Nothing is published more than thirty days out.</Empty>
        )}
      </Section>

      {measured.length ? (
        <Section
          title="Past measured windows"
          lead="Dates that have passed and whose following weeks were measured from stored closes. These are the only rows on this page that contain a measurement."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {measured.map((e) => {
              const line = e.analysis[0];
              return (
                <Card key={e.id} href={`/event/${e.slug}`}>
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-medium">{e.name}</h3>
                    <Pill tone={CATEGORY_TONE[e.category] ?? "default"}>{e.category}</Pill>
                  </div>
                  <p className="text-muted-foreground num mt-1 text-xs">{longDate(e.date)}</p>
                  <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
                    {e.summary}
                  </p>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <span className="text-muted-foreground num text-xs">
                      {e._count.impacts} measured rows
                    </span>
                    {line ? <ConfidenceBadge grade={line.confidence} /> : null}
                  </div>
                </Card>
              );
            })}
          </div>

          <HowToRead
            title="How to read a measured window"
            points={[
              <>
                <strong>Start with the window, not the number.</strong> Each event page says how
                many days were measured and from what date. A move measured over 30 days contains
                everything else that happened in those 30 days too.
              </>,
              <>
                <strong>Look at both ends of the table.</strong> Every event page lists the
                largest rises and the largest falls. If they are similar in size the window was
                volatile rather than directional, and a story told from the top of the table alone
                would be the opposite of one told from the bottom.
              </>,
              <>
                <strong>Over any thirty days some asset has the largest move.</strong> That is
                true whether or not anything happened, which is why a big number here is not
                evidence that the event produced it.
              </>,
              <>
                <strong>Compare one asset across several events.</strong> An asset at the top of
                every window is a volatile asset, not an asset uniquely sensitive to each of those
                dates.
              </>,
            ]}
          />
        </Section>
      ) : null}

      <div className="text-muted-foreground mt-8 space-y-2 text-xs leading-relaxed">
        <p>
          Scheduled dates as the provider publishes them. Companies move these and a time is not
          always published, so the day is the claim and not the hour. Where the provider restated
          one date more than once, the soonest day within{" "}
          <span className="num">{EVENT_DUPLICATE_WITHIN_DAYS}</span> days for the same asset and
          the same kind of item is kept and the later restatements are not listed, which is why a
          company reporting once appears once.
        </p>
        {passedUnmeasured ? (
          <p>
            <span className="num">{passedUnmeasured}</span> scheduled{" "}
            {passedUnmeasured === 1 ? "date has" : "dates have"} passed with nothing measured
            after {passedUnmeasured === 1 ? "it" : "them"} yet, so{" "}
            {passedUnmeasured === 1 ? "it is" : "they are"} not listed above. A measured window
            needs stored closes on both sides of it.
          </p>
        ) : null}
        <p>
          The historical list is short because it is written by hand, in{" "}
          <code>jobs/events.py</code>. Detecting events from the price series would fill it with
          whatever dates happen to sit next to large moves, and every row would then appear to
          confirm a relationship the selection had already created. The{" "}
          <Link href="/methodology" className="underline underline-offset-2">
            methodology page
          </Link>{" "}
          sets out the rest of the rules. Measured as of {isoDate(new Date())}.
        </p>
      </div>
    </div>
  );
}
