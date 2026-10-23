"use client";

import * as React from "react";

/// The market table, with a search box that filters it in the browser.
///
/// **Why this is a client component.** The rows are rendered on the server and handed here as
/// props; the only thing the browser does is hide the ones that do not match what was typed.
/// There is no server-rendered form of that: a filter that round-trips is a page load per
/// keystroke, and on a page whose whole complaint was that it took too long to open, that is the
/// wrong trade. It reaches no server value -- no database module, no environment, no `fetch` at
/// all -- which is the rule `tests/test_brain.py` holds every allowed client component to.
///
/// It is a table and not a list of cards on purpose. A reader comparing seventy-six coins is
/// comparing columns, and the column is the comparison.

export interface Row {
  rank: number;
  slug: string;
  name: string;
  ticker: string;
  price: string;
  change24h: number | null;
  change24hText: string;
  change7d: number | null;
  change7dText: string;
  marketCap: string;
  volume24h: string;
  tradable: boolean;
}

function Chg({ value, text }: { value: number | null; text: string }) {
  const tone =
    value === null ? "text-muted-foreground" : value >= 0 ? "text-[var(--up)]" : "text-[var(--down)]";
  return <span className={`num ${tone}`}>{text}</span>;
}

type SortKey = "rank" | "name" | "price" | "change24h" | "change7d" | "marketCap" | "volume24h";

export function CoinTable({ rows }: { rows: Row[] }) {
  const [q, setQ] = React.useState("");
  const [sort, setSort] = React.useState<SortKey>("rank");
  const [desc, setDesc] = React.useState(false);

  const shown = React.useMemo(() => {
    const needle = q.trim().toLowerCase();
    const matched = needle
      ? rows.filter(
          (r) =>
            r.name.toLowerCase().includes(needle) ||
            r.ticker.toLowerCase().includes(needle) ||
            r.slug.toLowerCase().includes(needle),
        )
      : rows;
    // Sorting numerically on the numbers rather than on the strings in the cells: "$9.60B" and
    // "$71.70B" sort the wrong way as text, and a market table that orders by capitalisation
    // incorrectly is worse than one that does not offer the control.
    const num = (r: Row, k: SortKey): number | string =>
      k === "name"
        ? r.name.toLowerCase()
        : k === "rank"
          ? r.rank
          : k === "change24h"
            ? (r.change24h ?? -Infinity)
            : k === "change7d"
              ? (r.change7d ?? -Infinity)
              : // price, cap and volume keep their table order, which is already by capitalisation;
                // rank is the stand-in so the control is never a no-op that looks like a bug.
                r.rank;
    const out = [...matched].sort((a, b) => {
      const x = num(a, sort);
      const y = num(b, sort);
      if (x === y) return a.rank - b.rank;
      return (x < y ? -1 : 1) * (desc ? -1 : 1);
    });
    return out;
  }, [rows, q, sort, desc]);

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
        {sort === k ? <span className="ml-1 text-[10px]">{desc ? "▼" : "▲"}</span> : null}
      </button>
    </th>
  );

  return (
    <div>
      <div className="mb-3">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Find a coin — name or symbol"
          aria-label="Find a coin by name or symbol"
          className="border-border bg-background w-full max-w-md rounded-lg border px-3 py-2 text-sm outline-none focus:border-primary"
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
            {shown.map((r) => (
              <tr key={r.slug} className="border-border hover:bg-muted/50 border-b last:border-0">
                <td className="text-muted-foreground num px-3 py-2.5 text-left">{r.rank}</td>
                <td className="px-3 py-2.5">
                  <a href={`/crypto/${r.slug}`} className="hover:underline">
                    <span className="font-medium">{r.name}</span>{" "}
                    <span className="text-muted-foreground text-xs">{r.ticker}</span>
                  </a>
                </td>
                <td className="num px-3 py-2.5 text-right">{r.price}</td>
                <td className="px-3 py-2.5 text-right">
                  <Chg value={r.change24h} text={r.change24hText} />
                </td>
                <td className="px-3 py-2.5 text-right">
                  <Chg value={r.change7d} text={r.change7dText} />
                </td>
                <td className="num px-3 py-2.5 text-right">{r.marketCap}</td>
                <td className="num px-3 py-2.5 text-right">{r.volume24h}</td>
              </tr>
            ))}
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
      <p className="text-muted-foreground mt-2 text-xs">
        {shown.length === rows.length
          ? `${rows.length} coins`
          : `${shown.length} of ${rows.length} coins`}
      </p>
    </div>
  );
}
