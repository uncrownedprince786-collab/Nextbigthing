/// Live quotes: what is shown, when it counts as stale, and how a stale one is refreshed on demand.
///
/// Pure and dependency-free (injected `fetch` and clock), so every rule here is testable with no
/// network. A quote is a last trade, shown beside a close and never in place of one: the rule table
/// reads closes, and a decision that moved with the tape would change on every refresh.

/// A quote older than this is stale and is refreshed on demand. Five minutes is also the platform
/// floor for the job that writes them, so a healthy tick is never stale by this measure.
export const QUOTE_STALE_MS = 5 * 60 * 1000;
/// How long one on-demand answer is reused. The only thing between a public endpoint and a free
/// provider's rate limit, so it is per symbol and it is not optional.
export const MEMO_TTL_MS = 60 * 1000;
/// A provider that has not answered by now is treated as not having answered.
export const FETCH_TIMEOUT_MS = 1500;
/// A quote stamped further ahead of the clock than this is a bad timestamp, not a fast market.
const FUTURE_SLACK_MS = 5 * 60 * 1000;

export interface Quote {
  price: number;
  /// ISO timestamp of when the price was struck, not when it was stored or fetched.
  quotedAt: string;
}

export function quoteAgeMs(quotedAt: Date | string, now: Date): number {
  return now.getTime() - new Date(quotedAt).getTime();
}

export function isStale(quotedAt: Date | string | null | undefined, now: Date): boolean {
  if (!quotedAt) return true;
  const age = quoteAgeMs(quotedAt, now);
  return !Number.isFinite(age) || age > QUOTE_STALE_MS;
}

/// "14:05 UTC", from an ISO timestamp. UTC and said so: a page cached for an hour cannot know the
/// reader's zone, and a time with no zone on a market page is a guess.
export function clockUtc(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}

/// Whether a quote adds anything beside the close already printed. Once a market has closed the last
/// trade IS the close and a second line repeating it is noise; a quote earns a line when it was struck
/// on a later day than the close, or sits more than a twentieth of a percent away from it.
export function quoteBesideClose(
  quote: { price: number; quotedAt: Date | string } | null | undefined,
  close: { price: number | null | undefined; date: Date | string | null | undefined },
): Quote | null {
  if (!quote || !Number.isFinite(quote.price) || quote.price <= 0) return null;
  const at = new Date(quote.quotedAt);
  if (Number.isNaN(at.getTime())) return null;
  const out = { price: quote.price, quotedAt: at.toISOString() };
  if (close.price == null || !close.date) return out;
  const closeDay = new Date(close.date).toISOString().slice(0, 10);
  const laterDay = at.toISOString().slice(0, 10) > closeDay;
  const apart = Math.abs(quote.price - close.price) / close.price > 0.0005;
  return laterDay || apart ? out : null;
}

/// Where an on-demand refresh may look. Both are keyed by the asset's stored source reference, and the
/// reference is checked against what that provider's identifiers look like before it goes in a URL.
export type FreshSource = { source: "yahoo" | "coinpaprika"; ref: string };

const YAHOO_REF = /^[A-Za-z0-9.=^-]{1,24}$/;
const PAPRIKA_REF = /^[a-z0-9-]{1,60}$/;

type FetchLike = (url: string, init: { signal: AbortSignal; headers: Record<string, string> }) => Promise<{
  ok: boolean;
  json: () => Promise<unknown>;
}>;

function positive(n: unknown): n is number {
  return typeof n === "number" && Number.isFinite(n) && n > 0;
}

/// One provider answer, validated, or null. Never throws and never returns a made-up number.
export async function fetchFreshQuote(src: FreshSource, fetchImpl: FetchLike, now: Date): Promise<Quote | null> {
  const ok = src.source === "yahoo" ? YAHOO_REF.test(src.ref) : PAPRIKA_REF.test(src.ref);
  if (!ok) return null;
  const url =
    src.source === "yahoo"
      ? `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(src.ref)}?interval=1m&range=1d`
      : `https://api.coinpaprika.com/v1/tickers/${encodeURIComponent(src.ref)}?quotes=USD`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetchImpl(url, { signal: controller.signal, headers: { "User-Agent": "nextbigthing-quote/1" } });
    if (!res.ok) return null;
    const body = (await res.json()) as Record<string, unknown>;
    let price: unknown;
    let at: number;
    if (src.source === "yahoo") {
      const meta = ((body?.chart as { result?: { meta?: Record<string, unknown> }[] } | undefined)?.result?.[0]?.meta ?? {}) as Record<string, unknown>;
      price = meta.regularMarketPrice;
      at = Number(meta.regularMarketTime) * 1000;
    } else {
      const usd = ((body?.quotes as Record<string, { price?: unknown }> | undefined)?.USD ?? {}) as { price?: unknown };
      price = usd.price;
      at = Date.parse(String(body?.last_updated ?? ""));
    }
    if (!positive(price) || !Number.isFinite(at) || at > now.getTime() + FUTURE_SLACK_MS) return null;
    return { price, quotedAt: new Date(at).toISOString() };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/// A per-key memo with a time to live and an injected clock. An answer, including "no answer", is kept
/// for `ttlMs`, so a provider that is down is not asked again by every request in the same minute.
export function makeMemo<T>(ttlMs: number, clock: () => number = Date.now) {
  const store = new Map<string, { at: number; value: T }>();
  return {
    get(key: string): { hit: true; value: T } | { hit: false } {
      const e = store.get(key);
      if (e && clock() - e.at < ttlMs) return { hit: true, value: e.value };
      return { hit: false };
    },
    set(key: string, value: T) {
      store.set(key, { at: clock(), value });
      // Bounded: a public endpoint must not be able to grow a map without limit.
      if (store.size > 2000) store.delete(store.keys().next().value as string);
    },
  };
}
