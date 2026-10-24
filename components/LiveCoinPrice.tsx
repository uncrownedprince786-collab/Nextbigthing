"use client";

import * as React from "react";

/// One coin's price, kept current and flashing on every tick.
///
/// **Why it has to be a client component.** The page under it prints an entry, a stop and a target
/// computed from the close the model read. A reader comparing those against a price that was
/// struck when the page was rendered is comparing against the past, and on a five-minute call the
/// past is the whole horizon. So the price updates, and it flashes green or red as it moves --
/// because a number that changes silently does not tell you it changed.
///
/// Held to the same rule as `components/LivePrice.tsx`: it imports no server module, reads no
/// environment, and talks to exactly one same-origin URL.

const POLL_MS = 2000;
const FLASH_MS = 800;

function coinPrice(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const d = a >= 1000 ? 2 : a >= 1 ? 4 : a >= 0.01 ? 5 : a >= 0.0001 ? 6 : 8;
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
}

export function LiveCoinPrice({
  slug,
  initialPrice,
  initialChange,
  initialChangeAbs,
}: {
  slug: string;
  initialPrice: number | null;
  initialChange: number | null;
  initialChangeAbs: number | null;
}) {
  const [price, setPrice] = React.useState(initialPrice);
  const [change, setChange] = React.useState(initialChange);
  const [flash, setFlash] = React.useState<"up" | "down" | null>(null);
  const prev = React.useRef<number | null>(initialPrice);

  React.useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let clear: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      try {
        const res = await fetch("/api/crypto/prices", { cache: "no-store" });
        if (res.ok && alive) {
          const body = (await res.json()) as {
            prices: Record<string, { p: number; c: number | null }>;
          };
          const row = body.prices?.[slug];
          if (row && Number.isFinite(row.p)) {
            const was = prev.current;
            if (was !== null && row.p !== was) {
              setFlash(row.p > was ? "up" : "down");
              if (clear) clearTimeout(clear);
              clear = setTimeout(() => alive && setFlash(null), FLASH_MS);
            }
            prev.current = row.p;
            setPrice(row.p);
            if (row.c !== null) setChange(row.c);
          }
        }
      } catch {
        // Keep the last price rather than blanking it. A reader looking at a stale number that is
        // labelled nothing is better served than one looking at an em dash.
      }
      if (alive) timer = setTimeout(tick, POLL_MS);
    };

    const start = () => {
      if (timer === undefined && document.visibilityState === "visible") void tick();
    };
    const stop = () => {
      if (timer !== undefined) {
        clearTimeout(timer);
        timer = undefined;
      }
    };
    const onVis = () => (document.visibilityState === "visible" ? start() : stop());
    document.addEventListener("visibilitychange", onVis);
    start();
    return () => {
      alive = false;
      stop();
      if (clear) clearTimeout(clear);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [slug]);

  const up = (change ?? 0) >= 0;
  // open = price / (1 + pct/100), so the move is price - open. Guarded against a -100% print.
  const open = price !== null && change !== null && 1 + change / 100 > 0
    ? price / (1 + change / 100)
    : null;
  const abs = open !== null && price !== null ? price - open : null;
  const decimals = price !== null && Math.abs(price) >= 1000 ? 2 : 4;
  return (
    <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
      <span
        className={`num rounded px-1.5 text-4xl font-semibold tracking-tight transition-colors duration-500 ${
          flash === "up"
            ? "bg-[var(--up)]/15 text-[var(--up)]"
            : flash === "down"
              ? "bg-[var(--down)]/15 text-[var(--down)]"
              : ""
        }`}
      >
        {coinPrice(price)}
      </span>
      {change !== null ? (
        <span className={`num text-lg font-medium ${up ? "text-[var(--up)]" : "text-[var(--down)]"}`}>
          {/* Derived from the price and the percentage rather than carried separately. The two
              arrive from different calls at different ages, and a stored absolute change beside a
              freshly polled price drifts apart within a minute -- which showed as a positive
              number next to a negative percentage. One number cannot disagree with itself. */}
          {abs !== null ? `${abs >= 0 ? "+" : ""}${abs.toFixed(decimals)} ` : ""}
          ({up ? "+" : ""}
          {change.toFixed(2)}%)
        </span>
      ) : null}
    </div>
  );
}
