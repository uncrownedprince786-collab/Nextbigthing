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

  return (
    <Card>
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
          <div className="mt-1">
            {signal.tone ? (
              <Pill tone={toneTone as "up" | "down" | "default"}>{signal.tone}</Pill>
            ) : (
              <Pill>no direction published</Pill>
            )}
          </div>
          <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
            {signal.positive} positive, {signal.negative} negative, {signal.neutral} neither,
            of {signal.items}.
            {signal.tone
              ? ""
              : " Too few headlines to read a direction, so only the counts are shown."}
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
            <strong>None of this is a forecast.</strong> It is what was published in a stated
            window, from {signal.source}.
          </>,
        ]}
      />
    </Card>
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
