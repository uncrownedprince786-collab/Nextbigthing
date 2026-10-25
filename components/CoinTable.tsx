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
  logo: string | null;
  /// Pegged to a dollar or an ounce. Marked in the table so a reader knows why its row never
  /// moves, and never shown on a signal board.
  pegged: boolean;
  /// True for a coin the registry has never collected -- which, on a venue, means newly listed
  /// far more often than not. It is the honest version of "new": we know when *we* first saw it,
  /// not when it was created.
  isNew: boolean;
}

/// What the brain is calling for the most-traded coins, fetched when a signal tab is opened.
interface Signal {
  slug: string;
  direction: "UP" | "DOWN";
  strength: "strong" | "weak" | null;
  probUp: number;
  marginPts: number;
  /// The close the call was read from, and the instant the window it covers ends.
  asOf: string;
  maturesAt: string;
  floor: number;
}

type Tab = "all" | "gainers" | "losers" | "recommended" | "new";
type SortKey = "rank" | "name" | "price" | "change24h" | "change7d" | "marketCap" | "volume24h";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All coins" },
  { key: "gainers", label: "Top gainers" },
  { key: "losers", label: "Top losers" },
  { key: "recommended", label: "Brain recommends" },
  { key: "new", label: "Newly listed" },
];

/// Dollars of 24-hour volume a coin needs before it may appear on the gainers, losers or newly
/// listed boards.
///
/// Set at a quarter of a million because that is roughly where a coin stops being a single
/// participant's book. Below it a 24-hour percentage is not a market move -- it is one trade
/// against an empty order book, and the coins producing them are the same ones no data source
/// tracks, which is why their seven-day and market-cap cells were blank. The floor removes the
/// blanks and the noise in one go, because they were always the same coins.
///
/// The main "All coins" board is not filtered: it is sorted by market capitalisation, so these
/// coins sit far below the hundred rows rendered and never reach a reader anyway.
const MIN_BOARD_VOLUME = 250_000;

/// Whether every column this table prints has a value for this coin.
///
/// The gainers, losers and newly listed boards are curated lists, and a curated list has no
/// business carrying a row it cannot describe. Sorting 2,320 coins by 24-hour percentage pulls
/// up tokens no data source tracks -- MEZO, DEOD, MBK, YVE -- whose seven-day and market-cap
/// cells came out blank, and tokenised equities like SNDKB and MSTRB which have no circulating
/// crypto supply and therefore no market capitalisation at all. The blank was not a bug to be
/// filled in; those numbers do not exist for those instruments.
///
/// So they are not listed here. "All coins" still carries every one of them, sorted by
/// capitalisation, where the long tail belongs and where nothing claims to be a highlight.
function complete(r: Row): boolean {
  return (
    (r.volume24h ?? 0) >= MIN_BOARD_VOLUME &&
    r.marketCap !== null &&
    r.change7d !== null &&
    r.price !== null
  );
}

/// The two tabs that need a direction rather than a price.
/// One board, not two.
///
/// Up and down were separate tabs, which split a list that is already short -- the floor speaks
/// on roughly one bar in nine, so forty coins yield a handful of calls and splitting them by
/// sign regularly left one side empty and reading like a fault. The direction is a property of
/// each call, not of the list, so it belongs in the row rather than in the tab. What a reader
/// wants is one answer to one question: what is the brain sure about right now, and which way.
const SIGNAL_TABS: Tab[] = ["recommended"];

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
  const [signals, setSignals] = React.useState<Signal[] | null>(null);
  const [signalState, setSignalState] = React.useState<"idle" | "loading" | "failed">("idle");
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

  // Asked for only when a reader opens one of the two tabs that needs it, and only once: a
  // direction cannot change faster than the bar it was read from, and scoring forty coins is
  // forty venue calls.
  // The in-flight guard is a ref, not state, and `signalState` is deliberately NOT a dependency.
  //
  // It was both: the effect set `signalState` and listed it, so changing it re-ran the effect,
  // whose cleanup set `alive = false` and cancelled the fetch that was still in the air. The
  // request completed, the response was thrown away, and the tab sat on "Reading the last closed
  // bar..." for ever while the endpoint it was waiting for answered correctly every time.
  // Whether *either* signal tab is open, rather than which one.
  //
  // The effect below used to depend on `tab` itself, and the two are not the same thing: moving
  // between "recommends up" and "recommends down" changed `tab`, so React tore the effect down
  // and ran its cleanup, which set `alive = false` and discarded the in-flight request -- while
  // `asked.current` stayed true, so no replacement was ever sent. The fetch returned 200, its
  // body was thrown away, and both tabs sat on "Reading the last closed bar…" for the rest of the
  // session. One request serves both tabs, so switching between them must not disturb it.
  const needsSignals = SIGNAL_TABS.includes(tab);
  const asked = React.useRef(false);
  React.useEffect(() => {
    if (!needsSignals || asked.current) return;
    asked.current = true;
    let alive = true;
    void (async () => {
      setSignalState("loading");
      try {
        const res = await fetch("/api/crypto/signals?h=m15", { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const body = (await res.json()) as { signals?: Signal[] };
        if (!alive) return;
        setSignals(body.signals ?? []);
        setSignalState("idle");
      } catch {
        if (alive) {
          setSignalState("failed");
          // Let a later visit try again rather than pinning the failure for the session.
          asked.current = false;
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [needsSignals]);

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

    if (tab === "gainers" || tab === "losers") {
      // A coin with no 24-hour figure is not a zero mover, it is an unknown one, so it is left
      // out of both boards rather than parked in the middle of them.
      //
      // The volume floor is the other half, and it is what fixes the blank cells rather than
      // hiding them. Sorting 2,320 coins purely by 24-hour percentage fills both boards with
      // tokens nobody trades -- MEZO, XPX, KRAFT, OKAI -- whose moves are one print on a dead
      // book and which no data source tracks, so their 7-day and market-cap cells were empty.
      // The emptiness was the honest half of the problem; the dishonest half was calling a
      // $40,000-a-day token a "top gainer" at all. A board whose entries cannot be traded is
      // not a shorter board than it should be, it is a wrong one.
      const movers = out.filter((r) => r.change24h !== null && complete(r));
      out = movers.sort((a, b) =>
        tab === "gainers" ? b.change24h! - a.change24h! : a.change24h! - b.change24h!,
      );
      return out.slice(0, 25);
    }

    if (tab === "new") {
      // Ordered by volume, because a newly listed coin nobody trades is not an opportunity --
      // and held to the same floor, for the same reason.
      return out
        .filter((r) => r.isNew && complete(r))
        .sort((a, b) => (b.volume24h ?? 0) - (a.volume24h ?? 0))
        .slice(0, 50);
    }

    if (SIGNAL_TABS.includes(tab)) {
      if (!signals) return [];
      // Only the calls that cleared their lane's conviction floor. These tabs say the brain
      // *recommends* a direction, and the floor is what that word rests on: on the retrained
      // five-minute lane the gated calls are right 64.5% of the time against 53.7% over every
      // bar, so a tab filled with ungated leans would be ten points worse than the one it
      // claims to be. A lean the model holds weakly is still shown -- on the coin's own page,
      // beside its margin -- but it does not belong on a list headed "recommends".
      // Ordered by how far from even the probability sits, so the calls the brain is surest
      // about are the ones a reader sees first -- regardless of which way they point.
      const order = new Map(
        signals
          .filter((s) => s.strength === "strong")
          .sort((x, y) => Math.abs(y.probUp - 0.5) - Math.abs(x.probUp - 0.5))
          .map((s, i) => [s.slug, i]),
      );
      return out.filter((r) => order.has(r.slug)).sort((a, b) => order.get(a.slug)! - order.get(b.slug)!);
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
  }, [merged, q, tab, sort, desc, signals]);

  const signalOf = React.useMemo(
    () => new Map((signals ?? []).map((s) => [s.slug, s])),
    [signals],
  );

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
              const sig = SIGNAL_TABS.includes(tab) ? signalOf.get(r.slug) : undefined;
              return (
                <tr key={r.slug} className="border-border hover:bg-muted/50 border-b last:border-0">
                  <td className="text-muted-foreground num px-3 py-2.5 text-left">
                    {tab === "all" ? r.rank : i + 1}
                  </td>
                  <td className="px-3 py-2.5">
                    <a href={`/crypto/${r.slug}`} className="flex items-center gap-2 hover:underline">
                      {r.logo ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={r.logo}
                          alt=""
                          width={18}
                          height={18}
                          loading="lazy"
                          className="h-[18px] w-[18px] shrink-0 rounded-full"
                        />
                      ) : (
                        <span className="bg-muted text-muted-foreground flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[9px] font-semibold">
                          {r.ticker.slice(0, 1)}
                        </span>
                      )}
                      <span className="truncate">
                        <span className="font-medium">{r.name}</span>{" "}
                        <span className="text-muted-foreground text-xs">{r.ticker}</span>
                        {r.pegged ? (
                          <span className="text-muted-foreground ml-1.5 rounded border border-border px-1 py-0.5 text-[9px] tracking-wide uppercase">
                            pegged
                          </span>
                        ) : null}
                      </span>
                      {sig ? (
                        <span
                          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            sig.direction === "UP"
                              ? "bg-[var(--up)]/15 text-[var(--up)]"
                              : "bg-[var(--down)]/15 text-[var(--down)]"
                          }`}
                        >
                          {/*
                            The window, not the word "STRONG".
                            **"STRONG" here and "medium" on the coin page were two different
                            things wearing similar words.** This badge meant the call cleared its
                            lane's conviction floor; the coin page's "medium" is the lane's
                            standing evidence grade across its whole holdout. A reader saw
                            UP · STRONG on the board, opened the coin, read "medium", and had no
                            way to know those were answers to different questions. Neither word
                            told them the one thing they actually needed -- how long the call is
                            for. So the badge carries the window, and the conviction is what
                            being on this board means at all.
                          */}
                          {sig.direction} · 15m
                        </span>
                      ) : null}
                      {sig ? (
                        <span
                          className="text-muted-foreground shrink-0 text-[10px] tabular-nums"
                          title={`Read from the bar that closed at ${new Date(sig.asOf).toUTCString()}; the window it covers ends at ${new Date(sig.maturesAt).toUTCString()}.`}
                        >
                          till {new Date(sig.maturesAt).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      ) : null}
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
                  {SIGNAL_TABS.includes(tab)
                    ? signalState === "loading"
                      ? "Reading the last closed bar for the forty most-traded coins…"
                      : signalState === "failed"
                        ? "The directions could not be read just now."
                        : "No coin in the top forty clears the confidence floor on this bar. The brain read every one of them and recommends none — which is most bars, by design, because it only speaks on about one in nine."
                    : tab === "new"
                      ? "No newly listed coin is in this list."
                      : `No coin here matches “${q}”.`}
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
            : tab === "gainers" || tab === "losers"
              ? `${shown.length} biggest ${tab === "gainers" ? "risers" : "fallers"} over 24 hours`
              : tab === "new"
                ? `${shown.length} coins the venue lists and the registry has not collected, by volume`
                : `${shown.length} of the forty most-traded coins recommended over the next fifteen minutes${
                    signals ? `, from ${signals.length} read` : ""
                  } · gated calls measured 61.3% on the holdout`}
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
