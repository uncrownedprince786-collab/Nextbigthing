"use client";

import * as React from "react";

/// The last trade for one asset, kept fresh in the browser.
///
/// It prints what the server stored, with the time that price was struck, and from then on asks
/// `/api/quote` once a minute while the tab is visible. A quote older than five minutes is shown as
/// delayed -- with its age -- rather than dressed as current; the endpoint tries a provider on demand
/// for exactly that case, and if it cannot, this says so.
///
/// It sits beside the stored close and never replaces it: the rule table reads closes, so nothing here
/// can change a verdict. It reaches no server value: it imports no database module, reads no
/// environment, and talks to one same-origin URL.

const STALE_MS = 5 * 60 * 1000;
const POLL_MS = 60 * 1000;

interface Quote {
  price: number;
  quotedAt: string;
}

function format(price: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: price < 1 ? 6 : 2 }).format(price);
  } catch {
    return price.toFixed(price < 1 ? 6 : 2);
  }
}

function clock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}

function ago(ms: number): string {
  const m = Math.max(0, Math.round(ms / 60_000));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}

export function LivePrice({
  symbol,
  currency,
  initial,
}: {
  symbol: string;
  currency: string;
  initial: Quote | null;
}) {
  const [quote, setQuote] = React.useState<Quote | null>(initial);
  // Null until mounted: the page is cached for an hour, so an age computed at render time on the
  // server would be wrong by the time anyone read it, and would not match the browser's first paint.
  const [now, setNow] = React.useState<number | null>(null);
  const [tried, setTried] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    async function refresh() {
      if (document.visibilityState !== "visible") return;
      try {
        const res = await fetch(`/api/quote?symbol=${encodeURIComponent(symbol)}`, { signal: controller.signal });
        if (!res.ok) return;
        const body = (await res.json()) as { price?: number; quotedAt?: string };
        if (alive && typeof body.price === "number" && body.price > 0 && typeof body.quotedAt === "string") {
          setQuote((old) =>
            !old || new Date(body.quotedAt as string).getTime() >= new Date(old.quotedAt).getTime()
              ? { price: body.price as number, quotedAt: body.quotedAt as string }
              : old,
          );
        }
      } catch {
        /* a failed refresh leaves the last quote on screen with its own age */
      } finally {
        if (alive) setTried(true);
      }
    }
    // First reading of the clock after mount, in a callback: the age is for the browser to work out, and
    // calling setState synchronously in the effect body would render twice for nothing.
    const first = window.setTimeout(() => setNow(Date.now()), 0);
    void refresh();
    const poll = window.setInterval(() => void refresh(), POLL_MS);
    const tick = window.setInterval(() => setNow(Date.now()), 30_000);
    // A tab coming back to the front asks at once, rather than showing a delayed quote for up to a
    // minute: the poll skips hidden tabs on purpose, so the return is the moment a refresh is owed.
    const onVisible = () => {
      setNow(Date.now());
      void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      controller.abort();
      window.clearTimeout(first);
      window.clearInterval(poll);
      window.clearInterval(tick);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [symbol]);

  if (!quote) {
    return (
      <p className="text-muted-foreground mt-2 text-xs">
        {tried ? "No quote has been struck for this name yet." : "Looking for a last trade…"}
      </p>
    );
  }
  const age = now === null ? null : now - new Date(quote.quotedAt).getTime();
  const delayed = age !== null && age > STALE_MS;
  return (
    <p className="mt-2 text-xs" aria-live="polite">
      <span className="text-muted-foreground">Last trade </span>
      <span className="num font-medium">{format(quote.price, currency)}</span>
      <span className="text-muted-foreground">
        {" "}
        · {clock(quote.quotedAt)}
        {age !== null ? ` · ${ago(age)}` : ""}
      </span>
      {delayed ? <span className="text-warn"> · delayed</span> : null}
    </p>
  );
}
