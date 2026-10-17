"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { Empty, Note, Table } from "@/components/ui";
import { price } from "@/lib/format";
import {
  DEFAULT_PREFS,
  getPrefsSnapshot,
  prefsServerSnapshot,
  subscribePrefs,
} from "../prefs";
import type { WatchlistRow } from "../api/watchlist/route";
import {
  getWatchlistSnapshot,
  readWatchlist,
  subscribeWatchlist,
  watchlistServerSnapshot,
  writeWatchlist,
} from "./storage";

/// Screen 6 — the watchlist, rendered from this browser's own list.
///
/// Four states, kept apart on purpose, because collapsing them is how a list starts lying:
///
///   * **not read yet** -- the server cannot see `localStorage`, so the first paint knows nothing
///     and says nothing. Rendering "empty" here would tell a reader with a full list that it was
///     gone.
///   * **read, and empty** -- the reader has saved nothing.
///   * **saved, and resolved** -- rows with their stored close, its date and its source.
///   * **saved, but not resolvable** -- the row is kept and marked. A symbol that no longer
///     resolves is a thing the reader should see and decide about, not a row that quietly
///     disappears from their own list.
export function WatchlistClient() {
  // The list and the preferences are read after mount and subscribed to, so neither the server nor
  // the first client render has to guess at this browser's storage.
  const items = useSyncExternalStore(subscribeWatchlist, getWatchlistSnapshot, watchlistServerSnapshot);
  const prefs =
    useSyncExternalStore(subscribePrefs, getPrefsSnapshot, prefsServerSnapshot) ?? DEFAULT_PREFS;
  const [rows, setRows] = useState<WatchlistRow[] | null>(null);
  const [omitted, setOmitted] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // Nothing to resolve before the list is read, and an empty list renders its own screen. The
    // states that matter are set only from the fetch's callbacks, never synchronously here.
    if (items === null || items.length === 0) return;
    let live = true;
    fetch("/preview/api/watchlist", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ symbols: items.map((i) => i.symbol) }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: { rows: WatchlistRow[]; omitted: number }) => {
        if (!live) return;
        setRows(d.rows);
        setOmitted(d.omitted);
        setFailed(false);
      })
      .catch(() => {
        if (!live) return;
        // The list is still the reader's list even when the readings cannot be fetched, so the
        // symbols stay on screen and the failure is stated rather than rendered as no data.
        setRows(null);
        setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [items]);

  const remove = useCallback((symbol: string) => {
    // Writing dispatches the change event, which the subscription above turns into a re-read.
    writeWatchlist(readWatchlist().filter((i) => i.symbol !== symbol));
  }, []);

  if (items === null) {
    return <Empty>Reading this browser&rsquo;s saved list.</Empty>;
  }

  if (items.length === 0) {
    return (
      <Empty>
        Nothing saved yet. Open an instrument from{" "}
        <Link href="/preview/markets" className="underline">Markets</Link> and use
        &ldquo;Save to watchlist&rdquo;. The list is held in this browser only.
      </Empty>
    );
  }

  const added = new Map(items.map((i) => [i.symbol, i.addedAt]));

  // The `recentFirst` preference, honoured here rather than stored and ignored: newest save
  // first, or alphabetically by symbol when it is off. Stable either way — the alphabetical
  // branch keeps insertion order for equal symbols, which cannot happen (toggle dedupes).
  const ordered = prefs.recentFirst
    ? [...items].sort((a, b) => (a.addedAt < b.addedAt ? 1 : a.addedAt > b.addedAt ? -1 : 0))
    : [...items].sort((a, b) => a.symbol.localeCompare(b.symbol));

  return (
    <>
      {omitted > 0 ? (
        <Note>
          Showing the first 50 of {items.length} saved instruments. {omitted} are not resolved here,
          to stay inside the database&rsquo;s shared connection limit.
        </Note>
      ) : null}
      {failed ? (
        <Note>
          The stored readings for these instruments could not be fetched, so only the saved symbols
          are shown. Nothing below should be treated as current.
        </Note>
      ) : null}
      <Table
        head={
          <>
            <th className="px-3 py-2 text-left">Symbol</th>
            <th className="px-3 py-2 text-left">Name</th>
            <th className="px-3 py-2 text-right">Latest stored close</th>
            <th className="px-3 py-2 text-left">As of</th>
            <th className="px-3 py-2 text-left">Saved</th>
            <th className="px-3 py-2 text-right">&nbsp;</th>
          </>
        }
      >
        {ordered.map((item) => {
          const row = rows?.find((r) => r.symbol === item.symbol) ?? null;
          return (
            <tr key={item.symbol}>
              <td className="px-3 py-2">
                <Link href={`/preview/asset/${encodeURIComponent(item.symbol)}`} className="underline">
                  {item.symbol}
                </Link>
              </td>
              <td className="px-3 py-2">
                {row?.unknown ? (
                  <span className="text-muted-foreground">
                    {item.name} — no instrument with this symbol is stored
                  </span>
                ) : (
                  (row?.name ?? item.name)
                )}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {row && !row.unknown && row.close !== null ? (
                  <>
                    {price(row.close, row.currency, row.market)}
                    {prefs.verboseProvenance ? (
                      <span className="text-muted-foreground block text-xs">
                        {[row.priceSource, row.closeDate ? row.closeDate.slice(0, 10) : null]
                          .filter(Boolean)
                          .join(" · ") || "provenance not recorded"}
                      </span>
                    ) : null}
                  </>
                ) : (
                  <span className="text-muted-foreground">
                    {row && !row.unknown ? "no close stored" : "not available"}
                  </span>
                )}
              </td>
              <td className="px-3 py-2">
                {row?.closeDate ? (
                  <>
                    {row.closeDate.slice(0, 10)}
                    {prefs.verboseProvenance ? (
                      <span className="text-muted-foreground block text-xs">
                        {row.closeDate.slice(11, 16)}Z
                      </span>
                    ) : row.priceSource ? (
                      <span className="text-muted-foreground block text-xs">{row.priceSource}</span>
                    ) : null}
                  </>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
              <td className="px-3 py-2 text-xs">{(added.get(item.symbol) ?? "").slice(0, 10)}</td>
              <td className="px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={() => remove(item.symbol)}
                  className="text-muted-foreground text-xs underline"
                >
                  Remove
                </button>
              </td>
            </tr>
          );
        })}
      </Table>
    </>
  );
}
