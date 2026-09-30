const SIZE_UNIT: Record<string, string> = {
  marketCap: "market cap",
  fundAssets: "fund size",
  none: "size",
};

/// What a size figure actually is for this asset. "Size" is not one comparable quantity
/// across the site: a stock's is market capitalisation, a fund's is assets under
/// management, and a commodity future has none at all. Ranking only ever happens within one
/// industry, but the label still has to say which of these a number is.
export function sizeBasisText(basis: string | null | undefined): string {
  switch (basis) {
    case "marketCap":
      return "market capitalisation, price multiplied by shares outstanding";
    case "fundAssets":
      return "fund size, the assets the fund holds";
    default:
      return "no size figure is published for this instrument";
  }
}

/// What a currency is written as in front of a number. A size figure quoted in rupees and
/// printed with a dollar sign is not a cosmetic error: it is wrong by a factor of nearly
/// three hundred, and it is wrong in the direction that makes a Karachi listing look like
/// a global one. Anything not listed here falls back to the ISO code, which is ugly and
/// correct, rather than to a symbol that would be neither.
const CURRENCY_MARK: Record<string, string> = { USD: "$", PKR: "Rs." };

export function currencyMark(currency: string | null | undefined): string {
  if (!currency) return "$";
  return CURRENCY_MARK[currency] ?? `${currency} `;
}

export function money(
  value: number | null | undefined,
  currency: string | null | undefined = "USD",
): string {
  if (value == null || Number.isNaN(value)) return "not available";
  const m = currencyMark(currency);
  if (value >= 1e12) return `${m}${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `${m}${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `${m}${(value / 1e6).toFixed(0)}M`;
  return `${m}${value.toFixed(0)}`;
}

/// A price, which needs more precision than a size and never an abbreviation.
export function price(
  value: number | null | undefined,
  currency: string | null | undefined = "USD",
): string {
  if (value == null || Number.isNaN(value)) return "not available";
  return `${currencyMark(currency)}${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
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
