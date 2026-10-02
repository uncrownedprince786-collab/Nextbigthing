import Link from "next/link";
import { isoDate, pct, price, toneClass } from "@/lib/format";
import {
  CHECK_WORDS,
  COVERAGE_WORDS,
  rewardWords,
  FINDING_WORDS,
  HORIZON_WORDS,
  METHOD_WORDS,
  PRODUCT_STATUS_WORDS,
  SETUP_WORDS,
  THESIS_WORDS,
  direction,
  targetsDisagree,
  tradingWords,
  unusualWords,
} from "@/lib/plain";

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
    recentStories: number;
    baselineStoryDaily: number | null;
    robustZ: number | null;
    changeKind: string;
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
            {signal.changeKind && signal.changeKind !== "none" ? (
              <Pill>{signal.changeKind}</Pill>
            ) : null}
            <span className="text-warn text-sm font-medium">
              {signal.recentStories} {signal.recentStories === 1 ? "story" : "stories"} in the
              last 3 days
              {signal.spikeRatio != null ? (
                <>
                  , about {signal.spikeRatio.toFixed(1)}&times; the earlier rate
                </>
              ) : null}
              {signal.robustZ != null ? (
                <> and {signal.robustZ.toFixed(1)}σ above this feed&apos;s own median</>
              ) : null}
            </span>
          </div>
          <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
            Counted as distinct <strong>stories</strong>, not items
            {signal.recentItems > signal.recentStories ? (
              <>
                {" "}
                &mdash; these {signal.recentStories} arrived as {signal.recentItems} items, so
                some of it is one report carried more than once
              </>
            ) : null}
            . This counts stories; it does not read them. What arrived is in the news list on
            this page.
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
            <strong>A catalyst flag is a count, not a verdict.</strong> It says distinct
            stories arrived in the last three days at several times the earlier rate{" "}
            <em>and</em> well above what this feed normally varies by. Both tests have to
            agree, because a ratio alone fires on a busy Tuesday. It has not read the stories,
            so it cannot tell you whether what arrived was good or bad.
          </>,
          <>
            <strong>Stories, not articles.</strong> One report syndicated to twenty outlets is
            one piece of information. Headlines are grouped into stories by word overlap
            inside a time window, and the counts above are of stories — the item count is
            shown beside them so the amount of duplication is visible rather than hidden.
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

/// The measured conditions, in the order a person actually asks about them.
///
/// Built from one principle: simplifying the language must not remove the data. Each line is
/// a plain sentence with the numbers it was derived from sitting next to it, so a reader
/// learns what the numbers mean by seeing them used rather than by being told a verdict.
///
/// The three parts that are not optional, because they are what stop this being a tip:
/// `against` is always rendered when it exists, `missing` is always rendered when it exists,
/// and the invalidation is always rendered. A state with its disagreements hidden is a
/// recommendation wearing a measurement's clothes.
export function SetupBlock({
  setup,
  currency = "USD",
}: {
  setup: {
    state: string;
    horizon: string;
    headline: string;
    conditions: string;
    missing: string;
    against: string;
    entryLevel: number | null;
    entryNote: string | null;
    invalidateLevel: number | null;
    invalidateNote: string | null;
    rangeNote: string | null;
    confidence: string;
    confidenceNote: string | null;
    periodEnd: Date | string;
  } | null;
  currency?: string;
}) {
  if (!setup) {
    return (
      <Empty>
        No condition read is stored for this asset yet. It is computed from stored prices,
        news readings and analogs by <code>python jobs/setup.py</code>.
      </Empty>
    );
  }

  const LABEL: Record<string, { text: string; tone: "up" | "down" | "warn" | "default" }> = {
    buy: { text: "conditions present", tone: "up" },
    short: { text: "downside conditions present", tone: "down" },
    wait: { text: "direction clear, conditions incomplete", tone: "warn" },
    none: { text: "no clear setup", tone: "default" },
  };
  const label = LABEL[setup.state] ?? LABEL.none;
  const conditions = setup.conditions.split(" | ").filter(Boolean);
  const against = setup.against === "none" ? [] : setup.against.split(" | ").filter(Boolean);
  const missing = setup.missing === "none" ? [] : setup.missing.split(" | ").filter(Boolean);

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={label.tone}>{label.text}</Pill>
        <Pill>{setup.horizon}</Pill>
        <ConfidenceBadge grade={setup.confidence} />
        <AsOf date={setup.periodEnd} />
      </div>

      <p className="mt-3 text-sm leading-relaxed">{setup.headline}</p>

      <div className="mt-4">
        <p className="text-muted-foreground text-xs font-medium">
          What the data shows
        </p>
        <ul className="mt-1.5 space-y-1">
          {conditions.map((c, i) => (
            <li key={i} className="text-muted-foreground num text-xs leading-relaxed">
              {c}
            </li>
          ))}
        </ul>
      </div>

      {against.length ? (
        <div className="border-warn/30 bg-warn-bg mt-4 rounded-lg border px-3 py-2">
          <p className="text-warn text-xs font-medium">What goes against it</p>
          <ul className="mt-1.5 space-y-1">
            {against.map((c, i) => (
              <li key={i} className="text-muted-foreground text-xs leading-relaxed">
                {c}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {missing.length ? (
        <div className="mt-3">
          <p className="text-muted-foreground text-xs font-medium">
            What could not be checked
          </p>
          <ul className="mt-1.5 space-y-1">
            {missing.map((c, i) => (
              <li key={i} className="text-muted-foreground text-xs leading-relaxed">
                {c}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
            An input that could not be evaluated is reported as unavailable, never counted as
            satisfied.
          </p>
        </div>
      ) : null}

      <div className="border-border mt-4 grid gap-3 border-t pt-3 sm:grid-cols-2">
        {setup.entryLevel != null ? (
          <div>
            <p className="text-muted-foreground text-xs font-medium">Level above</p>
            <p className="num mt-0.5 text-sm">{price(setup.entryLevel, currency)}</p>
            <p className="text-muted-foreground mt-0.5 text-[11px] leading-relaxed">
              {setup.entryNote}
            </p>
          </div>
        ) : null}
        {setup.invalidateLevel != null ? (
          <div>
            <p className="text-muted-foreground text-xs font-medium">
              What would break the reason
            </p>
            <p className="num mt-0.5 text-sm">{price(setup.invalidateLevel, currency)}</p>
            <p className="text-muted-foreground mt-0.5 text-[11px] leading-relaxed">
              {setup.invalidateNote}
            </p>
          </div>
        ) : null}
      </div>

      {setup.rangeNote ? (
        <p className="text-muted-foreground mt-3 text-[11px] leading-relaxed">
          {setup.rangeNote}.
        </p>
      ) : null}

      {setup.confidenceNote ? (
        <p className="text-muted-foreground mt-2 text-[11px] leading-relaxed">
          {setup.confidenceNote}.
        </p>
      ) : null}

      <Note>
        This describes measured conditions and nothing else. It is not advice, it does not say
        what will happen, and every condition behind it is listed above so the state can be
        checked rather than trusted. Conditions change; the invalidation level is the one to
        read first.
      </Note>
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

/// What has happened to the reason behind a directional read since the day it was recorded.
///
/// The opening sentence is shown above the current status on purpose. A reader arriving at a
/// weakening thesis needs the claim first and the decay second, because a status with no
/// claim attached is a colour.
///
/// The checks are rendered oldest first, as a sequence. A reason that has gone
/// active → active → weakening is a different thing from one that has been weakening since
/// the day it opened, and only the order shows that.
export function ThesisBlock({
  thesis,
  currency = "USD",
}: {
  currency?: string;
  thesis: {
    direction: string;
    horizon: string;
    status: string;
    reason: string;
    changed: string;
    held: string;
    openedOn: Date | string;
    openHeadline: string;
    openClose: number | null;
    lastClose: number | null;
    invalidateLevel: number | null;
    changePctSinceOpen: number | null;
    sessionsSince: number;
    confidence: string;
    confidenceNote: string | null;
    asOf: Date | string;
    checks: {
      id: string;
      asOf: Date | string;
      status: string;
      changed: string;
      changePctSinceOpen: number | null;
    }[];
  } | null;
}) {
  if (!thesis) {
    return (
      <Empty>
        No directional read has been held long enough to have a recorded reason. A thesis only
        exists for a buy or short state, and it is written by{" "}
        <code>python jobs/thesis.py</code>.
      </Empty>
    );
  }

  const STATUS: Record<string, { text: string; tone: "up" | "down" | "warn" | "default" }> = {
    active: { text: "reason intact", tone: "up" },
    weakening: { text: "reason weakening", tone: "warn" },
    broken: { text: "reason broken", tone: "down" },
  };
  const label = STATUS[thesis.status] ?? STATUS.weakening;
  const changed = thesis.changed === "none" ? [] : thesis.changed.split(", ").filter(Boolean);
  const held = thesis.held === "none" ? [] : thesis.held.split(", ").filter(Boolean);

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={label.tone}>{label.text}</Pill>
        <Pill>{thesis.direction}</Pill>
        <Pill>{thesis.horizon}</Pill>
        <ConfidenceBadge grade={thesis.confidence} />
        <AsOf date={thesis.asOf} />
      </div>

      <p className="text-muted-foreground mt-3 text-xs">
        Recorded on {isoDate(thesis.openedOn)}, {thesis.sessionsSince} stored{" "}
        {thesis.sessionsSince === 1 ? "session" : "sessions"} ago:
      </p>
      <p className="mt-1 text-sm leading-relaxed italic">{thesis.openHeadline}</p>

      <p className="mt-3 text-sm leading-relaxed">{thesis.reason}</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div>
          <p className="text-muted-foreground text-xs">Close when recorded</p>
          <p className="num mt-0.5 text-sm">{price(thesis.openClose, currency)}</p>
        </div>
        <div>
          <p className="text-muted-foreground text-xs">Close now</p>
          <p className="num mt-0.5 text-sm">
            {price(thesis.lastClose, currency)}
            {thesis.changePctSinceOpen != null ? (
              <span className={`ml-2 ${toneClass(thesis.changePctSinceOpen)}`}>
                {pct(thesis.changePctSinceOpen)}
              </span>
            ) : null}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground text-xs">Level named on the day</p>
          <p className="num mt-0.5 text-sm">{price(thesis.invalidateLevel, currency)}</p>
        </div>
      </div>

      {changed.length ? (
        <div className="border-warn/30 bg-warn-bg mt-4 rounded-lg border px-3 py-2">
          <p className="text-warn text-xs font-medium">
            Conditions that no longer read as they did
          </p>
          <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
            {changed.join(", ")}
          </p>
        </div>
      ) : null}

      {held.length ? (
        <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
          Unchanged since the opening day: {held.join(", ")}.
        </p>
      ) : null}

      {thesis.checks.length > 1 ? (
        <div className="mt-4">
          <p className="text-muted-foreground text-xs font-medium">Every check, in order</p>
          <ul className="mt-1.5 space-y-1">
            {thesis.checks.map((c) => (
              <li key={c.id} className="text-muted-foreground num text-xs leading-relaxed">
                {isoDate(c.asOf)} · {c.status}
                {c.changePctSinceOpen != null ? ` · ${pct(c.changePctSinceOpen)} since open` : ""}
                {c.changed !== "none" ? ` · changed: ${c.changed}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {thesis.confidenceNote ? <Note>{thesis.confidenceNote}.</Note> : null}

      <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
        A status describes whether the conditions the state was recorded on are still
        measurable. It is not a score, it does not say the read was right, and a broken
        reason is left broken rather than revised once the level it named was passed.
      </p>
    </Card>
  );
}

/// How much of a recent move the asset shared with its market and its own industry.
///
/// The bar is three segments sized by share, and it is only drawn when all three parts
/// exist. A two-segment bar with a gap would read as a measurement with a missing piece
/// rather than as a split that was never made.
export function AttributionBlock({
  attribution,
}: {
  attribution: {
    windowDays: number;
    totalPct: number;
    marketPct: number;
    sectorPct: number | null;
    specificPct: number | null;
    marketShare: number | null;
    sectorShare: number | null;
    specificShare: number | null;
    leader: string | null;
    leaderMargin: number | null;
    peers: number;
    groupSize: number;
    headline: string;
    confidence: string;
    confidenceNote: string | null;
    periodEnd: Date | string;
  } | null;
}) {
  if (!attribution) {
    return (
      <Empty>
        No move split is stored for this asset. It is computed from stored closes by{" "}
        <code>python jobs/attribution.py</code>, and needs four weeks of them.
      </Empty>
    );
  }

  const PARTS = [
    {
      key: "market",
      label: "Its exchange group",
      value: attribution.marketPct,
      share: attribution.marketShare,
      bar: "bg-muted-foreground/60",
    },
    {
      key: "sector",
      label: "Its own industry, beyond the group",
      value: attribution.sectorPct,
      share: attribution.sectorShare,
      bar: "bg-muted-foreground/40",
    },
    {
      key: "specific",
      label: "Left over, particular to this asset",
      value: attribution.specificPct,
      share: attribution.specificShare,
      bar: "bg-primary/70",
    },
  ];
  const complete = PARTS.every((p) => p.value != null && p.share != null);

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={attribution.totalPct >= 0 ? "up" : "down"}>
          {pct(attribution.totalPct)} over {attribution.windowDays} sessions
        </Pill>
        {attribution.leader ? (
          <Pill>mostly shared with: {attribution.leader}</Pill>
        ) : (
          <Pill tone="warn">no component is far enough ahead to name</Pill>
        )}
        <ConfidenceBadge grade={attribution.confidence} />
        <AsOf date={attribution.periodEnd} />
      </div>

      <p className="mt-3 text-sm leading-relaxed">{attribution.headline}</p>

      {complete ? (
        <div className="mt-4">
          <div className="border-border flex h-2.5 w-full overflow-hidden rounded-full border">
            {PARTS.map((p) => (
              <div
                key={p.key}
                className={p.bar}
                style={{ width: `${((p.share ?? 0) * 100).toFixed(1)}%` }}
              />
            ))}
          </div>
          <ul className="mt-2.5 space-y-1">
            {PARTS.map((p) => (
              <li key={p.key} className="flex items-baseline justify-between gap-3 text-xs">
                <span className="text-muted-foreground flex items-center gap-2">
                  <span className={`inline-block h-2 w-2 rounded-sm ${p.bar}`} />
                  {p.label}
                </span>
                <span className="num">
                  <span className={toneClass(p.value)}>
                    {p.value != null ? `${p.value >= 0 ? "+" : ""}${p.value.toFixed(1)} pts` : "-"}
                  </span>
                  <span className="text-muted-foreground ml-2">
                    {p.share != null ? `${(p.share * 100).toFixed(0)}% of the distance` : ""}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
        Medians over {attribution.peers} industry peers and {attribution.groupSize} assets in
        its exchange group. The three parts sum to the move by construction, and the shares are
        taken from absolute values, so a sector that fell while the asset rose still accounts
        for part of the distance between them.
      </p>

      {attribution.confidenceNote ? <Note>{attribution.confidenceNote}.</Note> : null}

      <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
        This is co-movement. It says what the asset moved <em>with</em>, which is a different
        sentence from one about cause, and no probability is attached to any of the three: a
        likelihood would need measured outcomes, and none have matured.
      </p>
    </Card>
  );
}

/// Assets sitting next to something that has started being written about.
///
/// Every row shows the chain that reached it, because the chain is the whole claim. A score
/// with no path behind it would be an unexplained ranking, and an unexplained ranking is the
/// one thing a reader cannot argue with.
export function NeighbourhoodBlock({
  relevance,
  showAsset = true,
}: {
  relevance: {
    periodEnd: Date | string | null;
    rows: {
      id: string;
      score: number;
      hops: number;
      edgeKind: string;
      path: string;
      asset?: { symbol: string; name: string };
    }[];
  };
  showAsset?: boolean;
}) {
  if (!relevance.rows.length) {
    return (
      <Empty>
        Nothing was reached. Either no catalyst is flagged today, or the names carrying one sit
        only in edge groups too large to mean anything about a single member.
      </Empty>
    );
  }

  return (
    <>
      <ul className="space-y-2">
        {relevance.rows.map((r) => (
          <li key={r.id} className="border-border rounded-lg border px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              {showAsset && r.asset ? (
                <Link
                  href={`/asset/${encodeURIComponent(r.asset.symbol)}`}
                  className="text-sm font-medium underline underline-offset-2"
                >
                  {r.asset.name}
                </Link>
              ) : (
                <span className="text-sm font-medium">{r.edgeKind} link</span>
              )}
              <span className="flex items-center gap-2">
                <Pill>
                  {r.hops} {r.hops === 1 ? "hop" : "hops"}
                </Pill>
                <Pill>{r.edgeKind}</Pill>
              </span>
            </div>
            <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">{r.path}.</p>
          </li>
        ))}
      </ul>
      <Note>
        An edge is a relationship somebody recorded. Relevance travelling along one is a reason
        to look, never evidence that a move on one end reached the other. The walk stops at two
        hops and skips any group too large to say anything about one of its members.
      </Note>
    </>
  );
}

/// The first thing a reader sees on an asset page, in plain words.
///
/// Deliberately above every table. The order of the lines is the order a person asks the
/// questions in — what is happening, why, what the news is, what goes against it, what is
/// next, what the setup is, and what would change the view — and each line is one sentence
/// drawn from a stored row rather than a figure to interpret.
///
/// Nothing here is new information. Every line is a restatement of something the deeper
/// sections show with its numbers, source and as-of date attached, which is what makes the
/// simplification safe: the evidence has not been replaced, it has been moved down the page.
export function PlainSummary({
  name,
  dayPct,
  investigation,
  horizons,
  thesis,
  upcoming,
}: {
  name: string;
  dayPct: number | null;
  investigation: {
    headline: string;
    found: string;
    notFound: string;
    pointsToward: string;
    unconfirmed: string;
    volumeRatio: number | null;
    robustZ: number | null;
    periodEnd: Date | string;
    findings: { id: string; kind: string; status: string; detail: string }[];
  } | null;
  horizons: {
    id: string;
    horizon: string;
    state: string;
    headline: string;
    against: string;
    entryLevel: number | null;
    invalidateLevel: number | null;
    invalidateNote: string | null;
  }[];
  thesis: { status: string; reason: string } | null;
  upcoming: { id: string; name: string; date: Date | string }[];
}) {
  const dir = direction(dayPct);
  const soonest = horizons.find((h) => h.state === "buy" || h.state === "short") ?? horizons[0];
  const setup = soonest ? SETUP_WORDS[soonest.state] ?? SETUP_WORDS.none : null;
  const newsFinding = investigation?.findings.find((f) => f.kind === "news");
  const trading = tradingWords(investigation?.volumeRatio);

  const against = soonest && soonest.against !== "none"
    ? soonest.against.split(" | ").filter(Boolean)
    : [];

  return (
    <Card className="border-primary/30">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">{name}</h2>
        <Pill tone={dir.tone}>
          {dir.word}
          {dayPct != null ? ` ${pct(dayPct, 1)}` : ""}
        </Pill>
        {setup ? <Pill tone={setup.tone}>{setup.label}</Pill> : null}
        {thesis && THESIS_WORDS[thesis.status] ? (
          <Pill tone={THESIS_WORDS[thesis.status].tone}>
            {THESIS_WORDS[thesis.status].label}
          </Pill>
        ) : null}
      </div>

      <dl className="mt-4 space-y-3 text-sm">
        <div>
          <dt className="text-muted-foreground text-xs font-medium">What&apos;s happening</dt>
          <dd className="mt-0.5 leading-relaxed">
            {investigation
              ? investigation.headline
              : dayPct != null
                ? `${name} is ${dir.word.toLowerCase()} ${pct(dayPct, 1)} on its latest stored day, which is within what it normally does.`
                : "No price change is stored for the latest day."}
            {trading ? ` There was ${trading}.` : ""}
          </dd>
        </div>

        <div>
          <dt className="text-muted-foreground text-xs font-medium">Why</dt>
          <dd className="mt-0.5 leading-relaxed">
            {investigation
              ? investigation.pointsToward
              : "Nothing unusual happened, so nothing was investigated. The conditions below are the ordinary reading."}
          </dd>
        </div>

        <div>
          <dt className="text-muted-foreground text-xs font-medium">News</dt>
          <dd className="mt-0.5 leading-relaxed">
            {newsFinding
              ? newsFinding.status === "found"
                ? newsFinding.detail
                : "No story is stored for it in the days around the move."
              : "No news check has been run for this asset yet."}
          </dd>
        </div>

        <div>
          <dt className="text-muted-foreground text-xs font-medium">
            What goes against it
          </dt>
          <dd className="mt-0.5 leading-relaxed">
            {against.length ? (
              <ul className="space-y-1">
                {against.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            ) : (
              "Nothing measured points the other way right now."
            )}
          </dd>
        </div>

        <div>
          <dt className="text-muted-foreground text-xs font-medium">What&apos;s next</dt>
          <dd className="mt-0.5 leading-relaxed">
            {upcoming.length ? (
              <>
                {upcoming[0].name} on {isoDate(upcoming[0].date)}
                {upcoming.length > 1 ? `, and ${upcoming.length - 1} more dated item${upcoming.length > 2 ? "s" : ""}` : ""}.
              </>
            ) : (
              "No scheduled date is stored for it."
            )}
          </dd>
        </div>

        <div>
          <dt className="text-muted-foreground text-xs font-medium">
            What would change the view
          </dt>
          <dd className="mt-0.5 leading-relaxed">
            {soonest?.invalidateLevel != null
              ? `${soonest.invalidateNote ?? "A close past the level named with this read"}. Until then the conditions above are what the data shows.`
              : "No invalidation level is stored, because there is no directional read to invalidate."}
          </dd>
        </div>
      </dl>

      {investigation ? (
        <p className="text-muted-foreground mt-4 text-xs leading-relaxed">
          {investigation.unconfirmed.split(" | ")[0]}.
        </p>
      ) : null}
    </Card>
  );
}

/// The same asset on every horizon it has been read on, side by side.
///
/// Side by side and not reconciled. `buy` today and `wait` on the quarter are two answers to
/// two different questions, and a page that showed one would be choosing a window and calling
/// it the truth.
export function HorizonStrip({
  horizons,
  currency = "USD",
}: {
  currency?: string;
  horizons: {
    id: string;
    horizon: string;
    state: string;
    headline: string;
    missing: string;
    entryLevel: number | null;
    invalidateLevel: number | null;
    confidence: string;
    periodEnd: Date | string;
    targets: {
      id: string;
      method: string;
      low: number;
      high: number;
      rewardRisk: number | null;
      agreement: number | null;
      note: string;
    }[];
  }[];
}) {
  if (!horizons.length) {
    return (
      <Empty>
        No condition read is stored for this asset on any horizon yet. The swing read comes from{" "}
        <code>python jobs/setup.py</code>, the other two from <code>python jobs/horizons.py</code>.
      </Empty>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-3">
      {horizons.map((h) => {
        const words = SETUP_WORDS[h.state] ?? SETUP_WORDS.none;
        const label = HORIZON_WORDS[h.horizon] ?? { label: h.horizon, window: "" };
        const missing = h.missing === "none" ? [] : h.missing.split(" | ").filter(Boolean);
        const disagree = h.targets.some((t) => targetsDisagree(t.agreement));
        return (
          <Card key={h.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium">{label.label}</h3>
              <ConfidenceBadge grade={h.confidence} />
            </div>
            <div className="mt-2">
              <Pill tone={words.tone}>{words.label}</Pill>
            </div>
            <p className="mt-2 text-xs leading-relaxed">{words.plain}</p>
            <p className="text-muted-foreground mt-2 text-xs leading-relaxed">{h.headline}</p>

            {h.entryLevel != null || h.invalidateLevel != null ? (
              <dl className="mt-3 space-y-1 text-xs">
                {h.entryLevel != null ? (
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted-foreground">Above</dt>
                    <dd className="num">{price(h.entryLevel, currency)}</dd>
                  </div>
                ) : null}
                {h.invalidateLevel != null ? (
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted-foreground">View changes below</dt>
                    <dd className="num">{price(h.invalidateLevel, currency)}</dd>
                  </div>
                ) : null}
              </dl>
            ) : null}

            {h.targets.length ? (
              <div className="mt-3">
                <p className="text-muted-foreground text-xs font-medium">
                  How far it could run, three ways
                </p>
                <ul className="mt-1 space-y-1">
                  {h.targets.map((t) => (
                    <li key={t.id} className="flex items-baseline justify-between gap-2 text-xs">
                      <span className="text-muted-foreground">
                        {METHOD_WORDS[t.method] ?? t.method}
                      </span>
                      <span className="num">
                        {t.low === t.high
                          ? price(t.low, currency)
                          : `${price(t.low, currency)} to ${price(t.high, currency)}`}
                      </span>
                      {rewardWords(t.rewardRisk) ? (
                        <span className="text-muted-foreground w-full text-[11px] leading-relaxed">
                          {rewardWords(t.rewardRisk)}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
                {disagree ? (
                  <Note>
                    These three ways of measuring disagree with each other. That disagreement is
                    shown rather than averaged away: the methods are answering the same question
                    from different evidence, and when they part company neither one is the
                    answer.
                  </Note>
                ) : null}
                <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
                  Measured ranges, not forecasts. Hover each note on the deeper table below for
                  what it was measured from.
                </p>
              </div>
            ) : null}

            {missing.length ? (
              <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
                Could not be checked: {missing.join("; ")}.
              </p>
            ) : null}
            <div className="mt-2">
              <AsOf date={h.periodEnd} />
            </div>
          </Card>
        );
      })}
    </div>
  );
}

/// What was actually looked at when something moved, including everything that was not found.
///
/// The absences get the same visual weight as the findings on purpose. A reader who only sees
/// what was found cannot tell a thin investigation from a thorough one, and the common honest
/// outcome here is a move with no story behind it.
export function InvestigationBlock({
  investigation,
}: {
  investigation: {
    trigger: string;
    triggerDetail: string;
    pointsToward: string;
    unconfirmed: string;
    leading: string | null;
    confidence: string;
    confidenceNote: string | null;
    periodEnd: Date | string;
    findings: {
      id: string;
      kind: string;
      status: string;
      detail: string;
      sourceName: string | null;
      observedAt: Date | string | null;
    }[];
    hypotheses: {
      id: string;
      label: string;
      statement: string;
      priorBase: number | null;
      priorNote: string | null;
      magnitude: number | null;
      supporting: string;
      contradicting: string;
      posterior: number | null;
      posteriorNote: string;
    }[];
  } | null;
}) {
  if (!investigation) {
    return (
      <Empty>
        Nothing unusual has been measured for this asset, so no investigation was run. That is
        the ordinary state: the engine only looks when a move is large against the asset&apos;s
        own history.
      </Empty>
    );
  }

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="warn">looked into: {investigation.trigger}</Pill>
        <ConfidenceBadge grade={investigation.confidence} />
        <AsOf date={investigation.periodEnd} />
      </div>
      <p className="mt-3 text-sm leading-relaxed">{investigation.triggerDetail}.</p>
      <p className="mt-2 text-sm leading-relaxed">{investigation.pointsToward}</p>

      <div className="mt-4">
        <p className="text-muted-foreground text-xs font-medium">
          Everything that was checked
        </p>
        <ul className="mt-1.5 space-y-1.5">
          {investigation.findings.map((f) => {
            const words = FINDING_WORDS[f.status] ?? FINDING_WORDS.unavailable;
            return (
              <li key={f.id} className="flex flex-wrap items-baseline gap-2 text-xs">
                <span className="min-w-[8.5rem] font-medium">
                  {CHECK_WORDS[f.kind] ?? f.kind}
                </span>
                <Pill tone={words.tone}>{words.label}</Pill>
                <span className="text-muted-foreground flex-1 leading-relaxed">
                  {f.detail}
                  {f.sourceName ? ` — ${f.sourceName}` : ""}
                  {f.observedAt ? ` (${isoDate(f.observedAt)})` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="mt-4">
        <p className="text-muted-foreground text-xs font-medium">
          The possible explanations, side by side
        </p>
        <ul className="mt-1.5 space-y-2">
          {investigation.hypotheses.map((h) => (
            <li key={h.id} className="border-border rounded-lg border px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium">{h.statement}</span>
                {h.label === investigation.leading ? (
                  <Pill tone="up">most support</Pill>
                ) : null}
              </div>
              {h.magnitude != null ? (
                <p className="num text-muted-foreground mt-1 text-xs">
                  measured share {h.magnitude >= 0 ? "+" : ""}
                  {h.magnitude.toFixed(1)} points of the move
                </p>
              ) : null}
              <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                For: {h.supporting}
              </p>
              <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                Against: {h.contradicting}
              </p>
              {h.priorBase != null ? (
                <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                  Across everything measured so far, this is what leads{" "}
                  {Math.round(h.priorBase * 100)}% of the time.
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      <Note>
        No probability is attached to any of these. For the three measured shares the figure
        <em> is</em> the measurement, so updating a belief with it would be circular; for the
        news explanation it would need a measured rate of how often a story precedes a move,
        and no outcome has matured yet.
      </Note>

      <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
        {investigation.unconfirmed.split(" | ").join(". ")}.
      </p>
    </Card>
  );
}

/// Whether the intraday series behind a same-day read can be trusted.
///
/// Shown even when everything is complete, because "checked, and complete" is a different
/// statement from an empty space, and the second is indistinguishable from not having looked.
export function IntradayHealth({
  health,
}: {
  health: {
    sessions: {
      id: string;
      sessionDate: Date | string;
      interval: number;
      status: string;
      barsExpected: number | null;
      barsStored: number;
      note: string;
    }[];
    intervals: { interval: number; bars: number; newest: Date | null }[];
  };
}) {
  if (!health.sessions.length) {
    return (
      <Empty>
        No intraday session has been fetched for this asset. Either nothing about it currently
        warrants the request budget, or this provider does not serve it intraday — the sessions
        table records which, and an unserved asset is a stored fact rather than a gap.
      </Empty>
    );
  }
  const TONE: Record<string, "up" | "down" | "warn" | "default"> = {
    complete: "up",
    partial: "warn",
    stale: "warn",
    empty: "default",
    failed: "down",
    unsupported: "default",
  };
  return (
    <Card>
      <ul className="space-y-1.5">
        {health.sessions.map((s) => (
          <li key={s.id} className="flex flex-wrap items-baseline gap-2 text-xs">
            <span className="num min-w-[5.5rem]">{isoDate(s.sessionDate)}</span>
            <span className="text-muted-foreground min-w-[3rem]">{s.interval}m</span>
            <Pill tone={TONE[s.status] ?? "default"}>{s.status}</Pill>
            <span className="text-muted-foreground num">
              {s.barsStored}
              {s.barsExpected != null ? ` of about ${s.barsExpected}` : ""} bars
            </span>
            <span className="text-muted-foreground flex-1 leading-relaxed">{s.note}</span>
          </li>
        ))}
      </ul>
      {health.intervals.length ? (
        <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
          Stored:{" "}
          {health.intervals
            .map((i) => `${i.bars.toLocaleString("en-US")} bars at ${i.interval}m`)
            .join(", ")}
          . The 15, 30 and 60 minute bars are built from the five minute ones and are only
          written when every component bar is present, so a gap stays a gap.
        </p>
      ) : null}
    </Card>
  );
}

/// The front page's answer to "what matters now".
///
/// Ordered by how unusual a move was for that asset rather than by how large it was, because a
/// 3% day is ordinary for one of these names and remarkable for another. Each row leads with
/// the sentence and keeps the figure beside it.
export function WhatMattersBlock({
  matters,
}: {
  matters: {
    periodEnd: Date | string | null;
    rows: {
      id: string;
      headline: string;
      pointsToward: string;
      trigger: string;
      movePct: number | null;
      robustZ: number | null;
      volumeRatio: number | null;
      leading: string | null;
      confidence: string;
      asset: { symbol: string; name: string };
    }[];
  };
}) {
  if (!matters.rows.length) {
    return (
      <Empty>
        Nothing moved unusually against its own history today. That is the ordinary state, and
        an empty list here is a real answer rather than a missing one.
      </Empty>
    );
  }
  return (
    <>
      <div className="grid gap-3 lg:grid-cols-2">
        {matters.rows.map((r) => {
          const unusual = unusualWords(r.robustZ);
          return (
            <Card key={r.id} href={`/asset/${encodeURIComponent(r.asset.symbol)}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-medium">{r.asset.name}</h3>
                {r.movePct != null ? (
                  <Pill tone={r.movePct >= 0 ? "up" : "down"}>{pct(r.movePct, 1)}</Pill>
                ) : (
                  <Pill tone="warn">{r.trigger}</Pill>
                )}
              </div>
              <p className="mt-2 text-xs leading-relaxed">{r.headline}</p>
              <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
                {r.pointsToward}
              </p>
              {unusual ? (
                <p className="text-muted-foreground mt-1.5 text-xs">{unusual}.</p>
              ) : null}
              <div className="mt-2">
                <ConfidenceBadge grade={r.confidence} />
              </div>
            </Card>
          );
        })}
      </div>
      <Note>
        These are the moves that are large <em>for the asset that made them</em>, not the largest
        moves on the site. Each one has been checked against company news, its industry, the
        calendar, the related names and its own history, and the asset page lists what was found
        and what was not.
      </Note>
    </>
  );
}

/// The first thing on an asset or product page: four short lines and a way down to the rest.
///
/// Deliberately small. Everything in it is a restatement of a value already computed and
/// already shown further down with its source and as-of date, so the block adds no claim —
/// it only puts the answer before the evidence instead of after it.
///
/// The caution line is omitted entirely when there is nothing true to put in it. A caution
/// that is always present is wallpaper, and a reader learns to skip the one time it matters.
export function SimpleRead({
  lines,
  detailHref = "#detail",
}: {
  lines: {
    shows: string;
    grade: string;
    gradeWhy: string;
    caution: string | null;
    changes: string | null;
  };
  detailHref?: string;
}) {
  return (
    <Card className="border-primary/40">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold tracking-tight">Simple read</h2>
        <ConfidenceBadge grade={lines.grade} />
      </div>

      <p className="mt-2.5 text-sm leading-relaxed">{lines.shows}</p>

      <dl className="mt-3 space-y-1.5 text-xs">
        <div className="flex gap-2">
          <dt className="text-muted-foreground min-w-[7.5rem] shrink-0">Confidence</dt>
          <dd className="leading-relaxed">
            {GRADE_PLAIN[lines.grade] ?? lines.grade} — {lines.gradeWhy}
          </dd>
        </div>
        {lines.caution ? (
          <div className="flex gap-2">
            <dt className="text-warn min-w-[7.5rem] shrink-0 font-medium">Watch out</dt>
            <dd className="leading-relaxed">{lines.caution}</dd>
          </div>
        ) : null}
        {lines.changes ? (
          <div className="flex gap-2">
            <dt className="text-muted-foreground min-w-[7.5rem] shrink-0">
              Changes the view
            </dt>
            <dd className="leading-relaxed">{lines.changes}</dd>
          </div>
        ) : null}
      </dl>

      <a
        href={detailHref}
        className="text-primary mt-3 inline-block text-xs underline underline-offset-2"
      >
        Full detail below ↓
      </a>

      <p className="text-muted-foreground mt-2 text-[11px] leading-relaxed">
        A description of measured conditions. Not advice, and it does not say what will happen.
      </p>
    </Card>
  );
}

/// The grade in a word a reader does not have to decode.
const GRADE_PLAIN: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "Not graded",
};

/// One product, scannable in a second.
///
/// Name, status, score, badge — and nothing else at the top level. The long grade explanation
/// moved behind a disclosure because it is the reason the first screen of /products could not
/// be read quickly: thirty cards each carrying a paragraph is thirty paragraphs, and the
/// reader wanted the shape of the list.
///
/// `<details>` rather than React state so the card stays a server component, which keeps this
/// page free of client JavaScript entirely.
export function ProductCard({
  product,
  tone,
}: {
  tone: "up" | "warn" | "default";
  product: {
    id: string;
    slug: string;
    name: string;
    category: string;
    status: string;
    demandScore: number | null;
    confidence: string;
    sourcesAnswered: number;
    sourcesAgree: number;
    confidenceNote: string | null;
    summary: string;
  };
}) {
  return (
    <Card>
      <Link href={`/product/${product.slug}`} className="block">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium underline-offset-2 hover:underline">{product.name}</h3>
          <Pill tone={tone}>{PRODUCT_STATUS_WORDS[product.status]?.label ?? product.status}</Pill>
        </div>
        <div className="mt-2 flex items-baseline justify-between gap-2">
          <span className={`num text-lg font-semibold ${toneClass(product.demandScore)}`}>
            {pct(product.demandScore)}
          </span>
          <ConfidenceBadge grade={product.confidence} />
        </div>
        <p className="text-muted-foreground mt-1 text-[11px]">
          {product.category} · {product.sourcesAnswered} of 5 sources answered
          {product.sourcesAnswered > 0 ? `, ${product.sourcesAgree} agree` : ""}
        </p>
      </Link>

      {product.confidenceNote || product.summary ? (
        <details className="group mt-2">
          <summary className="text-muted-foreground hover:text-foreground cursor-pointer list-none text-[11px] underline underline-offset-2">
            Why this grade
          </summary>
          {product.confidenceNote ? (
            <p className="text-muted-foreground mt-1.5 text-[11px] leading-relaxed">
              {product.confidenceNote}
            </p>
          ) : null}
          {product.summary ? (
            <p className="text-muted-foreground mt-1.5 text-[11px] leading-relaxed">
              {product.summary}
            </p>
          ) : null}
        </details>
      ) : null}
    </Card>
  );
}

/// Three compact boxes near the top of the home page: what to watch, what is dated, what is
/// getting attention.
///
/// One number or state per row and a link, and no prose on the cards. The sections below are
/// unchanged; this is a way into them rather than a replacement for them. Every row comes from
/// a table that was already being read on this page.
export function ScanBox({
  title,
  lead,
  empty,
  rows,
}: {
  title: string;
  lead: string;
  empty: string;
  rows: { key: string; label: string; value: string; href?: string; tone?: "up" | "down" | "warn" | "default" }[];
}) {
  return (
    <Card>
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="text-muted-foreground mt-0.5 text-[11px] leading-relaxed">{lead}</p>
      {rows.length ? (
        <ul className="mt-2.5 space-y-1.5">
          {rows.map((r) => (
            <li key={r.key} className="flex items-baseline justify-between gap-2 text-xs">
              {r.href ? (
                <Link href={r.href} className="truncate underline-offset-2 hover:underline">
                  {r.label}
                </Link>
              ) : (
                <span className="truncate">{r.label}</span>
              )}
              <span className={`num shrink-0 ${r.tone ? toneClass(r.tone === "up" ? 1 : r.tone === "down" ? -1 : 0) : ""}`}>
                {r.value}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground mt-2.5 text-xs leading-relaxed">{empty}</p>
      )}
    </Card>
  );
}

/// Source health, for the reader.
///
/// Two shapes from one component because the two places want different amounts. `brief` is
/// the home page: a line that says everything is answering, or names only what is not, so a
/// healthy day costs one line and a fault is impossible to miss. The full form is the
/// methodology page, where every source is listed whatever its state.
///
/// Status words come from COVERAGE_WORDS rather than being written here, so the page cannot
/// drift from the four states the audit job actually writes.
export function SourceHealthBlock({
  sources,
  brief = false,
}: {
  sources: { source: string; status: string; rows: number; newest: Date | null; note: string | null }[];
  brief?: boolean;
}) {
  if (!sources.length) {
    return <Empty>No source health has been measured yet. It is written by the audit job on every run.</Empty>;
  }
  const faults = sources.filter((s) => s.status !== "healthy");
  const shown = brief ? faults : sources;

  if (brief && !faults.length) {
    return (
      <p className="text-muted-foreground text-sm">
        All {sources.length} measured sources are answering as expected.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {brief ? (
        <p className="text-muted-foreground text-sm">
          {faults.length} of {sources.length} measured sources need reading with care. The rest are answering as
          expected.
        </p>
      ) : null}
      <ul className="divide-border divide-y">
        {shown.map((s) => {
          const words = COVERAGE_WORDS[s.status] ?? {
            label: s.status,
            plain: "This status has no reader wording yet.",
            tone: "default" as const,
          };
          return (
            <li key={s.source} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
              <span className="text-sm font-medium">{s.source}</span>
              <Pill tone={words.tone}>{words.label}</Pill>
              <AsOf date={s.newest} />
              {!brief ? (
                <span className="text-muted-foreground text-xs">
                  {s.rows.toLocaleString("en-US")} rows
                </span>
              ) : null}
              <span className="text-muted-foreground w-full text-xs leading-relaxed">
                {words.plain}
                {s.note ? ` ${s.note}` : ""}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
