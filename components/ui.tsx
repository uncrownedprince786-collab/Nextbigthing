import Link from "next/link";
import { isoDate, pct, toneClass } from "@/lib/format";

export function Section({
  title,
  lead,
  aside,
  children,
}: {
  title: string;
  lead?: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-10 first:mt-0">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {aside}
      </div>
      {lead ? <p className="text-muted-foreground mt-0 mb-3 max-w-3xl text-sm">{lead}</p> : null}
      {children}
    </section>
  );
}

export function Card({
  href,
  children,
  className = "",
}: {
  href?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const cls = `border-border bg-card rounded-lg border p-4 ${className}`;
  return href ? (
    <Link href={href} className={`${cls} block transition-colors hover:border-primary/50`}>
      {children}
    </Link>
  ) : (
    <div className={cls}>{children}</div>
  );
}

export function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-warn bg-warn-bg mt-2 rounded border border-warn/25 px-3 py-2 text-xs leading-relaxed">
      {children}
    </p>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-muted-foreground border-border rounded-lg border border-dashed px-4 py-6 text-center text-sm">
      {children}
    </p>
  );
}

export function AsOf({ date }: { date: Date | string | null | undefined }) {
  return (
    <span className="text-muted-foreground text-xs">as of {isoDate(date)}</span>
  );
}

export function Pill({ children, tone = "default" }: { children: React.ReactNode; tone?: "default" | "up" | "down" | "warn" }) {
  const tones: Record<string, string> = {
    default: "text-muted-foreground border-border",
    up: "text-up border-up/30 bg-up/5",
    down: "text-down border-down/30 bg-down/5",
    warn: "text-warn border-warn/30 bg-warn-bg",
  };
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-[11px] leading-4 ${tones[tone]}`}>
      {children}
    </span>
  );
}

export type Confidence = "high" | "medium" | "low" | "none";

const CONFIDENCE_COPY: Record<Confidence, { label: string; tone: string; title: string }> = {
  high: {
    label: "High confidence",
    tone: "text-up border-up/30 bg-up/5",
    title: "Several independent sources point the same way",
  },
  medium: {
    label: "Medium confidence",
    tone: "text-warn border-warn/30 bg-warn-bg",
    title: "Sources partly agree, or one source is carrying most of the figure",
  },
  low: {
    label: "Low confidence",
    tone: "text-down border-down/30 bg-down/5",
    title: "Few sources answered, or they disagree",
  },
  none: {
    label: "No data",
    tone: "text-muted-foreground border-border",
    title: "No source returned a value, so nothing is claimed",
  },
};

/// Shows how well a figure is evidenced. The grade is always spelled out rather than left
/// as a colour, and "none" reads as no data instead of as a weak result.
export function ConfidenceBadge({
  grade,
  className = "",
}: {
  grade: Confidence | string | null | undefined;
  className?: string;
}) {
  const key = (grade ?? "none") as Confidence;
  const copy = CONFIDENCE_COPY[key] ?? CONFIDENCE_COPY.none;
  return (
    <span
      title={copy.title}
      className={`inline-block rounded-full border px-2 py-0.5 text-[11px] leading-4 ${copy.tone} ${className}`}
    >
      {copy.label}
    </span>
  );
}

/// Grades a claim that spans two dates, such as a size table that reports both the past
/// and the current figure. The grade is the weaker of the measurements actually shown, so
/// one poorly evidenced date cannot hide behind a well evidenced one. Dates with no stored
/// row are skipped rather than counted as no data, because the page says so in words
/// instead; "none" is returned only when nothing at all was stored.
export function weakest(...grades: (Confidence | string | null | undefined)[]): Confidence {
  const rank: Record<Confidence, number> = { none: 0, low: 1, medium: 2, high: 3 };
  let out: Confidence | null = null;
  for (const g of grades) {
    if (g == null) continue;
    const key = g as Confidence;
    if (!(key in rank)) continue;
    if (out === null || rank[key] < rank[out]) out = key;
  }
  return out ?? "none";
}

export function Table({ head, children }: { head: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="border-border overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead className="bg-muted/60">
          <tr className="text-muted-foreground text-left text-xs">
            {head}
          </tr>
        </thead>
        <tbody className="divide-border divide-y">{children}</tbody>
      </table>
    </div>
  );
}

/// A short lesson in reading the table it sits next to.
///
/// This is the teaching layer, and it is a collapsed block rather than a banner on
/// purpose. Someone who already knows how to read a confidence grade should not have to
/// scroll past the explanation every time, and someone who does not should not have to
/// guess that the explanation exists. `<details>` does both with no JavaScript, which
/// keeps these pages server rendered like everything else here.
export function HowToRead({
  title = "How to read this page",
  points,
}: {
  title?: string;
  points: React.ReactNode[];
}) {
  return (
    <details className="border-border bg-muted/30 mt-4 rounded-lg border px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium select-none">{title}</summary>
      <ul className="text-muted-foreground mt-3 space-y-2 leading-relaxed">
        {points.map((p, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden="true" className="text-primary/60">
              &bull;
            </span>
            <span>{p}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/// What the public discussion around one target currently looks like.
///
/// Three readings side by side and never merged into one verdict, because they answer
/// different questions and disagree often: how much is being written, how it is worded, and
/// whether it is being written to sell a click. A reader who sees only a merged score cannot
/// tell which of the three moved.
///
/// The counts sit next to every direction on purpose. "Positive" over 40 headlines and
/// "positive" over 9 are the same word doing very different work, and the second one is the
/// common case. Where a direction was withheld the block says so rather than showing
/// neutral, since no reading and a balanced reading are not the same finding.
export function DiscussionBlock({
  signal,
  targetLabel,
}: {
  signal: {
    items: number;
    positive: number;
    negative: number;
    neutral: number;
    tone: string | null;
    toneScore: number | null;
    priorItems: number;
    velocityPct: number | null;
    attention: string;
    recentItems: number;
    baselineDaily: number | null;
    spikeRatio: number | null;
    catalyst: boolean;
    catalystNote: string | null;
    hypeTerms: number;
    hypeFlag: boolean;
    hypeNote: string | null;
    windowDays: number;
    periodEnd: Date | string;
    confidence: string;
    confidenceNote: string | null;
    source: string;
  } | null;
  targetLabel: string;
}) {
  if (!signal) {
    return (
      <Empty>
        No discussion reading has been written for {targetLabel} yet. It is computed from
        stored news coverage by <code>python jobs/human.py</code>.
      </Empty>
    );
  }

  const attentionTone =
    signal.attention === "rising" ? "up" : signal.attention === "falling" ? "down" : "default";
  const toneTone =
    signal.tone === "positive" ? "up" : signal.tone === "negative" ? "down" : "default";

  // THIN_ITEMS mirrors MIN_ITEMS in jobs/human.py. The page labels a thin reading rather
  // than hiding it: being early means reading weak evidence, and a reader shown nothing
  // cannot judge anything. The label is not optional, though — an unlabelled thin reading
  // is the actual dishonesty.
  const THIN_ITEMS = 8;
  const thin = signal.items > 0 && signal.items < THIN_ITEMS;

  return (
    <Card>
      {signal.catalyst ? (
        <div className="border-warn/40 bg-warn-bg mb-4 rounded-lg border px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="warn">catalyst</Pill>
            <span className="text-warn text-sm font-medium">
              {signal.recentItems} items in the last 3 days
              {signal.spikeRatio != null ? (
                <>
                  , about {signal.spikeRatio.toFixed(1)}&times; the earlier daily rate
                </>
              ) : null}
            </span>
          </div>
          <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
            Something recent is being written about that was not before. This counts
            headlines; it does not read them. What arrived is in the news list on this page.
          </p>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <p className="text-muted-foreground text-xs">Attention</p>
          <div className="mt-1 flex items-baseline gap-2">
            <Pill tone={attentionTone as "up" | "down" | "default"}>{signal.attention}</Pill>
            {signal.velocityPct != null ? (
              <span className={`num text-sm ${toneClass(signal.velocityPct)}`}>
                {pct(signal.velocityPct)}
              </span>
            ) : null}
          </div>
          <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
            {signal.items} headlines in {signal.windowDays} days against {signal.priorItems} in
            the {signal.windowDays} before
            {signal.velocityPct == null
              ? ", too few to compare, so no change is reported"
              : ""}
            .
          </p>
        </div>

        <div>
          <p className="text-muted-foreground text-xs">Headline wording</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {signal.tone ? (
              <Pill tone={toneTone as "up" | "down" | "default"}>{signal.tone}</Pill>
            ) : (
              <Pill>no headlines stored</Pill>
            )}
            {thin ? <Pill tone="warn">thin</Pill> : null}
          </div>
          <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
            {signal.positive} positive, {signal.negative} negative, {signal.neutral} neither,
            of {signal.items}.
            {thin
              ? ` Read on ${signal.items} headlines, so it is shown early rather than because it is well evidenced.`
              : ""}
          </p>
        </div>

        <div>
          <p className="text-muted-foreground text-xs">Promotional wording</p>
          <div className="mt-1">
            {signal.hypeFlag ? <Pill tone="warn">hype flagged</Pill> : <Pill>not flagged</Pill>}
          </div>
          <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
            {signal.hypeTerms} of {signal.items} headlines use promotional wording.
          </p>
        </div>
      </div>

      <div className="border-border mt-4 flex flex-wrap items-center gap-2 border-t pt-3">
        <ConfidenceBadge grade={signal.confidence} />
        <AsOf date={signal.periodEnd} />
      </div>

      {signal.confidenceNote ? (
        <p className="text-muted-foreground mt-2 text-[11px] leading-relaxed">
          {signal.confidenceNote}.
        </p>
      ) : null}

      {signal.catalystNote && !signal.catalyst ? (
        <p className="text-muted-foreground mt-2 text-[11px] leading-relaxed">
          {signal.catalystNote}.
        </p>
      ) : null}

      {signal.hypeNote ? <Note>{signal.hypeNote}.</Note> : null}

      <HowToRead
        title="How this reading is produced, and what it cannot see"
        points={[
          <>
            <strong>It is a word list, not sentiment analysis.</strong> Headlines are matched
            against a fixed list of directional words. There is no model involved, and the
            match counts are shown above so the arithmetic can be checked.
          </>,
          <>
            <strong>It reads headlines only.</strong> Never article bodies. It cannot see
            negation, so &ldquo;not a record year&rdquo; counts the positive word, and it
            cannot see sarcasm or context at all.
          </>,
          <>
            <strong>A headline worded both ways counts as neither.</strong> &ldquo;Revenue
            beats but guidance misses&rdquo; is genuinely both, so it is left out of the
            direction rather than assigned to whichever side matched more words.
          </>,
          <>
            <strong>Attention measures coverage, not interest.</strong> A feed that was rate
            limited returns fewer items, which looks identical to a quieter month. That is why
            the raw counts are printed next to the percentage.
          </>,
          <>
            <strong>Hype describes the writing, not the asset.</strong> The flag is raised
            only when promotional wording arrives together with rising coverage. Heavily
            promoted and overvalued are different claims and only the first is measured here.
          </>,
          <>
            <strong>A catalyst flag is a count, not a verdict.</strong> It says items arrived
            in the last three days at several times the earlier rate, which is the shape of
            news breaking. It has not read them, so it cannot tell you whether what arrived
            was good, bad, or a rewrite of the same story by four outlets.
          </>,
          <>
            <strong>Thin readings are shown, labelled thin.</strong> A direction built on a
            few headlines is published rather than withheld, because a signal worth having is
            usually weak when it first appears. The count is always next to it so the
            weakness is visible rather than implied.
          </>,
          <>
            <strong>None of this is a forecast.</strong> It is what was published in a stated
            window, from {signal.source}.
          </>,
        ]}
      />
    </Card>
  );
}

/// What followed the past days that most resembled this asset's latest day.
///
/// Built to be hard to misread as a forecast, which is the whole difficulty with a panel like
/// this. Three things are therefore always on screen together and none of them is optional:
/// the number of matches, the full range of what followed, and how often it went up. An
/// average of +0.4% over 60 matches that ran from -9% to +11% is not a signal, and a reader
/// who sees only the average cannot tell that.
export function AnalogBlock({
  analogs,
}: {
  analogs: {
    periodEnd: Date | string | null;
    rows: {
      id: string;
      horizonDays: number;
      dayReturnPct: number;
      volumeRatio: number | null;
      fiveDayPct: number | null;
      toleranceNote: string;
      matches: number;
      positive: number;
      meanPct: number | null;
      medianPct: number | null;
      minPct: number | null;
      maxPct: number | null;
      confidence: string;
      confidenceNote: string | null;
    }[];
  };
}) {
  if (!analogs.periodEnd || !analogs.rows.length) {
    return (
      <Empty>
        No near-term analogs are stored for this asset yet. They are computed from stored
        closes and volumes by <code>python jobs/analogs.py</code>.
      </Empty>
    );
  }

  const setup = analogs.rows[0];
  return (
    <div>
      <Card>
        <p className="text-muted-foreground text-xs">The day being matched</p>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
          <span>
            One day return{" "}
            <span className={`num font-medium ${toneClass(setup.dayReturnPct)}`}>
              {pct(setup.dayReturnPct, 2)}
            </span>
          </span>
          {setup.volumeRatio != null ? (
            <span>
              Volume{" "}
              <span className="num font-medium">{setup.volumeRatio.toFixed(2)}×</span> its 20
              day average
            </span>
          ) : null}
          {setup.fiveDayPct != null ? (
            <span>
              Five day{" "}
              <span className={`num font-medium ${toneClass(setup.fiveDayPct)}`}>
                {pct(setup.fiveDayPct, 1)}
              </span>
            </span>
          ) : null}
        </div>
        <p className="text-muted-foreground mt-2 text-[11px] leading-relaxed">
          A past day counts as similar when {setup.toleranceNote}. Absolute price and volume
          are deliberately not matched on: they would mostly find days near this price rather
          than days that looked like this one.
        </p>
      </Card>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {analogs.rows.map((r) => (
          <Card key={r.id}>
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-medium">
                {r.horizonDays === 1 ? "Next session" : `Next ${r.horizonDays} sessions`}
              </h3>
              <ConfidenceBadge grade={r.confidence} />
            </div>

            {r.matches ? (
              <>
                <p className="mt-2 text-sm">
                  <span className="num font-semibold">{r.matches}</span> similar past days.{" "}
                  <span className="num font-semibold">{r.positive}</span> were followed by a
                  rise, <span className="num font-semibold">{r.matches - r.positive}</span> by
                  a fall or no change.
                </p>
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <span className="text-muted-foreground">Average</span>
                  <span className={`num text-right ${toneClass(r.meanPct)}`}>
                    {pct(r.meanPct, 2)}
                  </span>
                  <span className="text-muted-foreground">Median</span>
                  <span className={`num text-right ${toneClass(r.medianPct)}`}>
                    {pct(r.medianPct, 2)}
                  </span>
                  <span className="text-muted-foreground">Range</span>
                  <span className="num text-right">
                    {pct(r.minPct, 1)} to {pct(r.maxPct, 1)}
                  </span>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground mt-2 text-sm">
                No past day in the stored history matched this setup, so there is nothing to
                report. That is an unusual day, not a strong one.
              </p>
            )}

            {r.confidenceNote ? (
              <p className="text-muted-foreground mt-2 text-[11px] leading-relaxed">
                {r.confidenceNote}.
              </p>
            ) : null}
          </Card>
        ))}
      </div>

      <Note>
        This is a record of what followed similar days, not a statement about this one. The
        same setup appears in the sample with both outcomes, which is why the count and the
        full range sit next to every average here. Read the range first.
      </Note>
    </div>
  );
}

/// Dated items that have not happened yet.
///
/// A diary, and the reason it exists is forgetting rather than prediction: an earnings report
/// on a known day is the commonest way a price moves for a reason that was public and
/// forgettable weeks in advance. Nothing here claims a date will do anything.
export function UpcomingBlock({
  events,
  showTargets = true,
}: {
  events: {
    id: string;
    slug: string;
    name: string;
    date: Date | string;
    category: string;
    notes: string | null;
    source: string;
    links?: {
      id: string;
      relation: string;
      asset: { symbol: string; name: string } | null;
      product: { slug: string; name: string } | null;
    }[];
  }[];
  showTargets?: boolean;
}) {
  if (!events.length) {
    return (
      <Empty>
        No scheduled dates are stored. They are fetched from the provider&apos;s company
        calendar by <code>python jobs/upcoming.py</code>.
      </Empty>
    );
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return (
    <div>
      <ul className="divide-border border-border divide-y rounded-lg border">
        {events.map((e) => {
          const when = new Date(e.date);
          const days = Math.round((when.getTime() - today.getTime()) / 86_400_000);
          return (
            <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2">
              <span className="num text-muted-foreground w-24 shrink-0 text-xs">
                {isoDate(e.date)}
              </span>
              <span className="w-20 shrink-0">
                <Pill tone={days <= 3 ? "warn" : "default"}>
                  {days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days}d`}
                </Pill>
              </span>
              <span className="min-w-0 flex-1 text-sm">
                {showTargets && e.links?.length ? (
                  <>
                    {e.links[0].asset ? (
                      <Link
                        href={`/asset/${encodeURIComponent(e.links[0].asset.symbol)}`}
                        className="font-medium underline underline-offset-2"
                      >
                        {e.links[0].asset.name}
                      </Link>
                    ) : (
                      <span className="font-medium">{e.links[0].product?.name}</span>
                    )}
                    {" — "}
                  </>
                ) : null}
                <span className="text-muted-foreground">{e.category}</span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-muted-foreground mt-2 text-[11px] leading-relaxed">
        Scheduled dates as the provider publishes them. Companies move these and a time is
        not always published, so the day is the claim and not the hour. Nothing here says what
        a date will do to a price; what followed past events of the same kind is measured
        after the fact, never before.
      </p>
    </div>
  );
}

/// Where attention for a product sits geographically.
///
/// Every number here is a share normalised inside its own list, which is the single fact a
/// reader has to hold on to, so it is stated above the tables rather than in a footnote. The
/// consequence is counter-intuitive enough to spell out: a small population can top a list
/// on very few searches, and on the term used to verify this source Wyoming outranked
/// California four to one. So the tables are labelled as where interest is *concentrated
/// relative to local search volume*, which is what the source measures, and not as where the
/// buyers are, which it does not.
///
/// City level is absent because the source returns nothing at that resolution, and the block
/// says so instead of leaving a reader to assume it was not looked for.
export function GeographyBlock({
  geo,
}: {
  geo: {
    periodEnd: Date | string | null;
    lists: {
      key: string;
      label: string;
      timeframe: string;
      source: string;
      rows: { name: string; value: number; rank: number }[];
    }[];
  };
}) {
  if (!geo.periodEnd || !geo.lists.length) {
    return (
      <Empty>
        No regional breakdown is stored for this product yet. It is fetched from Google
        Trends by <code>python jobs/geo.py</code>.
      </Empty>
    );
  }

  return (
    <div>
      <p className="text-muted-foreground text-sm leading-relaxed">
        Each value is 0&ndash;100 <strong>within its own list</strong>, so 100 means the
        highest place in that list and says nothing about how many searches that was. Values
        are not comparable between lists, or between products.
      </p>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {geo.lists.map((list) => (
          <Card key={list.key}>
            <h3 className="text-sm font-medium">{list.label}</h3>
            <p className="text-muted-foreground mt-0.5 text-[11px]">
              {list.timeframe} &middot; {list.rows.length} places
            </p>
            <ul className="mt-3 space-y-1.5">
              {list.rows.slice(0, 8).map((r) => (
                <li key={r.name} className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground num w-4 shrink-0 text-right">
                    {r.rank}
                  </span>
                  <span className="flex-1 truncate">{r.name}</span>
                  <span
                    aria-hidden="true"
                    className="bg-primary/25 h-1.5 shrink-0 rounded-full"
                    style={{ width: `${Math.max(2, Math.round(r.value * 0.42))}px` }}
                  />
                  <span className="num text-muted-foreground w-7 shrink-0 text-right">
                    {Math.round(r.value)}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      <Note>
        A small population produces a high score cheaply. Because the value is a share of
        local searching rather than a count of it, a place with little search traffic can
        reach 100 on very few searches &mdash; on the term used to verify this source,
        Wyoming scored 100 against California&apos;s 24. Read these as where interest is
        concentrated relative to local search volume, not as where the buyers are.
      </Note>

      <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
        <strong className="text-foreground">City level is not available.</strong> Asked for
        directly, the source returns an empty result at city resolution for terms that have
        full state-level data, so no metro table is shown. That is a limit of the free source,
        not an omission, and nothing here is substituted for it. As of{" "}
        {isoDate(geo.periodEnd)}, from {geo.lists[0]?.source}.
      </p>
    </div>
  );
}

/// What the accuracy log currently supports, which for a while is nothing.
///
/// The honest state of a feedback loop that has just started is that it has no answer yet,
/// and saying so is the whole point: a hit rate computed over a handful of matured rows would
/// be exactly the impressive-looking number the project exists not to publish.
export function AccuracyNote({
  accuracy,
}: {
  accuracy: {
    horizon: number;
    measured: number;
    positive: number;
    open: number;
    enough: boolean;
    mean: number | null;
    earliest: Date | string | null;
  };
}) {
  if (!accuracy.enough) {
    return (
      <p className="text-muted-foreground text-xs leading-relaxed">
        Every reading on this page is logged on the day it is generated, and the price move
        over the {accuracy.horizon} days after it is measured once that window has passed.
        So far {accuracy.measured} readings have matured and {accuracy.open} are still
        waiting, which is too few to quote a rate from. No accuracy figure is published until
        there are enough matured rows to divide by.
      </p>
    );
  }
  return (
    <p className="text-muted-foreground text-xs leading-relaxed">
      Of {accuracy.measured} logged readings whose {accuracy.horizon} day window has passed,
      {" "}
      {accuracy.positive} were followed by a positive price move, a mean of{" "}
      <span className="num">{pct(accuracy.mean)}</span>
      {accuracy.earliest ? <> since {isoDate(accuracy.earliest)}</> : null}. This is what
      followed the readings, measured from the close stored beside each one. It is not a
      claim that the readings caused the moves, and it is not a forecast.
    </p>
  );
}

/// The currency a set of figures is quoted in, said once above the table rather than
/// repeated on every row. Returns are percentages and compare across currencies; sizes do
/// not, and a reader who has scrolled past the heading needs to be told which they are
/// looking at.
export function CurrencyNote({ currency, market }: { currency: string; market: string }) {
  if (currency === "USD") return null;
  return (
    <p className="text-muted-foreground text-xs">
      Every price and size on this page is quoted in {currency}
      {market === "PK" ? ", as published by the Pakistan Stock Exchange" : ""}. Percentage
      returns compare across currencies; the size figures do not, and are not comparable
      with the dollar figures elsewhere on this site.
    </p>
  );
}
