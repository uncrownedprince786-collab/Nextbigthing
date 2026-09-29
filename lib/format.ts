const SIZE_UNIT: Record<string, string> = {
  marketCap: "market cap",
  fundAssets: "fund size",
  none: "size",
};

export function money(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "not available";
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  return `$${value.toFixed(0)}`;
}

export function sizeLabel(basis: string): string {
  return SIZE_UNIT[basis] ?? "size";
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "not available";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function count(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "not available";
  return Math.round(value).toLocaleString("en-US");
}

export function isoDate(value: Date | string | null | undefined): string {
  if (!value) return "no date";
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "no date";
  return d.toISOString().slice(0, 10);
}

export function longDate(value: Date | string | null | undefined): string {
  if (!value) return "no date";
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "no date";
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function relativeTime(value: Date | string | null | undefined): string {
  if (!value) return "";
  const d = typeof value === "string" ? new Date(value) : value;
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  if (days < 365) return `${Math.floor(days / 30)} months ago`;
  return `${Math.floor(days / 365)} years ago`;
}

export function toneClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "text-muted-foreground";
  if (value > 0) return "text-up";
  if (value < 0) return "text-down";
  return "text-muted-foreground";
}
