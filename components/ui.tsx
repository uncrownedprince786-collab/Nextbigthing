import Link from "next/link";
import { isoDate } from "@/lib/format";

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
