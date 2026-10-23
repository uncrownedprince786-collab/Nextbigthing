"use client";

import * as React from "react";

/// The market table: searchable, sortable, and ticking.
///
/// **Why this is a client component.** Three things here have no server-rendered form. The filter
/// must not round-trip -- that is a page load per keystroke, on the page whose whole complaint was
/// how long it took to open. The sort is the same. And a price that updates has to update in the
/// browser: a server-rendered table is a photograph, and the flash that tells you *which* price
/// just moved only exists if something remembers what it was a moment ago.
///
/// It reaches no server value -- no database module, no environment -- and talks to exactly one
/// same-origin URL, `/api/crypto/prices`, which is the rule `components/LivePrice.tsx` is held to
/// and the reason that one is allowed.

const POLL_MS = 2000;
/// How many rows are in the DOM before the reader asks for more.
///
/// Every coin is in memory and every one is searched; this is only how many are *drawn*. Five
/// hundred rows is about four thousand DOM nodes, which the browser lays out on every repaint --
/// and the prices repaint every two seconds. A reader scanning a market table reads the top of
/// it; a reader looking for one coin types its name, and search is over the whole set.
const PAGE = 100;
/// How long a cell stays lit after a change. Long enough to catch out of the corner of an eye,
/// short enough that a fast mover is not permanently highlighted and therefore unreadable.
const FLASH_MS = 800;

export interface Row {
  rank: number;
  slug: string;
  name: string;
  ticker: string;
  price: number | null;
  change24h: number | null;
  change7d: number | null;
  marketCap: number | null;
  volume24h: number | null;
  tradable: boolean;
}

type Tab = "all" | "gainers" | "losers";
type SortKey = "rank" | "name" | "price" | "change24h" | "change7d" | "marketCap" | "volume24h";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All coins" },
  { key: "gainers", label: "Top gainers" },
  { key: "losers", label: "Top losers" },
];

function compactUsd(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(2)}K`;
  return `$${v.toFixed(2)}`;
}

function coinPrice(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const d = a >= 1000 ? 2 : a >= 1 ? 4 : a >= 0.01 ? 5 : a >= 0.0001 ? 6 : 8;
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
}

function pct(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function Chg({ value }: { value: number | null }) {
  const tone =
    value === null ? "text-muted-foreground" : value >= 0 ? "text-[var(--up)]" : "text-[var(--down)]";
  return <span className={`num ${tone}`}>{pct(value)}</span>;
}

export function CoinTable({ rows }: { rows: Row[] }) {
  const [q, setQ] = React.useState("");
  const [tab, setTab] = React.useState<Tab>("all");
  const [sort, setSort] = React.useState<SortKey>("rank");
  const [desc, setDesc] = React.useState(false);
  const [limit, setLimit] = React.useState(PAGE);

  // The live layer sits on top of the server's rows rather than replacing them: a coin the venue
  // stops answering for keeps the price the page was rendered with instead of blanking.
  const [live, setLive] = React.useState<Record<string, { p: number; c: number | null }>>({});
  const [flash, setFlash] = React.useState<Record<string, "up" | "down">>({});
  const prev = React.useRef<Record<string, number>>({});

  React.useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const clears: ReturnType<typeof setTimeout>[] = [];

    const tick = async () => {
      try {
        const res = await fetch("/api/crypto/prices", { cache: "no-store" });
        if (res.ok && alive) {
          const body = (await res.json()) as {
            prices: Record<string, { p: number; c: number | null }>;
          };
          const lit: Record<string, "up" | "down"> = {};
          for (const [slug, v] of Object.entries(body.prices ?? {})) {
            const was = prev.current[slug];
            if (was !== undefined && v.p !== was) lit[slug] = v.p > was ? "up" : "down";
            prev.current[slug] = v.p;
          }
          setLive(body.prices ?? {});
          if (Object.keys(lit).length) {
            setFlash((f) => ({ ...f, ...lit }));
            clears.push(
              setTimeout(() => {
                if (!alive) return;
                setFlash((f) => {
                  const next = { ...f };
                  for (const k of Object.keys(lit)) delete next[k];
                  return next;
                });
              }, FLASH_MS),
            );
          }
        }
      } catch {
        // A missed tick is the previous price for two more seconds, which is the right failure:
        // the alternative is a table that empties itself whenever a public endpoint hiccups.
      }
      // Scheduled after the response rather than on an interval, so a slow answer cannot stack
      // requests behind itself on a tab that has been left open.
      if (alive) timer = setTimeout(tick, POLL_MS);
    };

    // Only while the tab is actually being looked at. A background tab polling a venue forever is
    // the thing that gets an IP rate-limited for every reader at once.
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
      clears.forEach(clearTimeout);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  const merged = React.useMemo(
    () =>
      rows.map((r) => {
        const l = live[r.slug];
        return l ? { ...r, price: l.p, change24h: l.c ?? r.change24h } : r;
      }),
    [rows, live],
  );

  const shown = React.useMemo(() => {
    const needle = q.trim().toLowerCase();
    let out = needle
      ? merged.filter(
          (r) =>
            r.name.toLowerCase().includes(needle) ||
            r.ticker.toLowerCase().includes(needle) ||
            r.slug.toLowerCase().includes(needle),
        )
      : merged;

    if (tab !== "all") {
      // A coin with no 24-hour figure is not a zero mover, it is an unknown one, so it is left
      // out of both boards rather than parked in the middle of them.
      const movers = out.filter((r) => r.change24h !== null);
      out = movers.sort((a, b) =>
        tab === "gainers" ? b.change24h! - a.change24h! : a.change24h! - b.change24h!,
      );
      return out.slice(0, 25);
    }

    const num = (r: Row, k: SortKey): number | string =>
      k === "name"
        ? r.name.toLowerCase()
        : k === "rank"
          ? r.rank
          : k === "price"
            ? (r.price ?? -Infinity)
            : k === "change24h"
              ? (r.change24h ?? -Infinity)
              : k === "change7d"
                ? (r.change7d ?? -Infinity)
                : k === "marketCap"
                  ? (r.marketCap ?? -Infinity)
                  : (r.volume24h ?? -Infinity);
    return [...out].sort((a, b) => {
      const x = num(a, sort);
      const y = num(b, sort);
      if (x === y) return a.rank - b.rank;
      return (x < y ? -1 : 1) * (desc ? -1 : 1);
    });
  }, [merged, q, tab, sort, desc]);

  const head = (k: SortKey, label: string, align = "text-right") => (
    <th className={`px-3 py-2 ${align} font-medium`}>
      <button
        type="button"
        className="hover:text-foreground cursor-pointer"
        onClick={() => {
          if (sort === k) setDesc(!desc);
          else {
            setSort(k);
            setDesc(k !== "name" && k !== "rank");
          }
        }}
      >
        {label}
        {tab === "all" && sort === k ? (
          <span className="ml-1 text-[10px]">{desc ? "▼" : "▲"}</span>
        ) : null}
      </button>
    </th>
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="border-border flex overflow-hidden rounded-lg border">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => {
                setTab(t.key);
                setLimit(PAGE);
              }}
              className={`px-3 py-2 text-sm transition ${
                tab === t.key ? "bg-primary/10 text-foreground font-medium" : "hover:bg-muted"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setLimit(PAGE);
          }}
          placeholder="Find a coin — name or symbol"
          aria-label="Find a coin by name or symbol"
          className="border-border bg-background focus:border-primary w-full max-w-xs rounded-lg border px-3 py-2 text-sm outline-none"
        />
      </div>

      <div className="border-border overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="text-muted-foreground border-border border-b text-xs">
            <tr>
              {head("rank", "#", "text-left")}
              {head("name", "Name", "text-left")}
              {head("price", "Price")}
              {head("change24h", "24h")}
              {head("change7d", "7d")}
              {head("marketCap", "Market cap")}
              {head("volume24h", "Volume (24h)")}
            </tr>
          </thead>
          <tbody>
            {shown.slice(0, limit).map((r, i) => {
              const lit = flash[r.slug];
              return (
                <tr key={r.slug} className="border-border hover:bg-muted/50 border-b last:border-0">
                  <td className="text-muted-foreground num px-3 py-2.5 text-left">
                    {tab === "all" ? r.rank : i + 1}
                  </td>
                  <td className="px-3 py-2.5">
                    <a href={`/crypto/${r.slug}`} className="hover:underline">
                      <span className="font-medium">{r.name}</span>{" "}
                      <span className="text-muted-foreground text-xs">{r.ticker}</span>
                    </a>
                  </td>
                  {/* The flash is the point of the live layer: a column of numbers that changes
                      silently tells you nothing about which one moved. */}
                  <td className="px-3 py-2.5 text-right">
                    <span
                      className={`num inline-block rounded px-1.5 py-0.5 transition-colors duration-500 ${
                        lit === "up"
                          ? "bg-[var(--up)]/15 text-[var(--up)]"
                          : lit === "down"
                            ? "bg-[var(--down)]/15 text-[var(--down)]"
                            : ""
                      }`}
                    >
                      {coinPrice(r.price)}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <Chg value={r.change24h} />
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <Chg value={r.change7d} />
                  </td>
                  <td className="num px-3 py-2.5 text-right">{compactUsd(r.marketCap)}</td>
                  <td className="num px-3 py-2.5 text-right">{compactUsd(r.volume24h)}</td>
                </tr>
              );
            })}
            {shown.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-muted-foreground px-3 py-6 text-center">
                  No coin here matches “{q}”.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs">
          {tab === "all"
            ? shown.length === rows.length
              ? `${Math.min(limit, shown.length)} of ${rows.length} coins`
              : `${Math.min(limit, shown.length)} of ${shown.length} matching ${rows.length} coins`
            : `${shown.length} biggest ${tab === "gainers" ? "risers" : "fallers"} over 24 hours`}
          {Object.keys(live).length > 0 ? " · prices live" : ""}
        </p>
        {shown.length > limit ? (
          <button
            type="button"
            onClick={() => setLimit((n) => n + PAGE * 2)}
            className="border-border hover:bg-muted rounded-lg border px-3 py-1.5 text-xs"
          >
            Show {Math.min(PAGE * 2, shown.length - limit)} more
          </button>
        ) : null}
      </div>
    </div>
  );
}
