"use client";

import { useSyncExternalStore } from "react";
import {
  getWatchlistSnapshot,
  subscribeWatchlist,
  toggle,
  watchlistServerSnapshot,
  writeWatchlist,
} from "./storage";

/// Save or unsave one instrument, from wherever that instrument is being read.
///
/// Rendered on the asset screen, which is a server component: this is the one client island in the
/// browse path and it holds no data of its own beyond the saved list.
///
/// It renders its neutral state until this browser's list is read. The saved list is in
/// `localStorage`, which the server cannot see, so a button that claimed "Saved" in the HTML would
/// be guessing -- and guessing wrong is a hydration mismatch. `useSyncExternalStore` reads the list
/// after mount and subscribes to changes, and `ready` (the list has been read) keeps the two
/// renders identical: before it, nobody is told anything; after it, the button states the truth.
export function SaveButton({ symbol, name }: { symbol: string; name: string }) {
  const items = useSyncExternalStore(subscribeWatchlist, getWatchlistSnapshot, watchlistServerSnapshot);
  const ready = items !== null;
  const saved = ready && items.some((i) => i.symbol === symbol);

  return (
    <button
      type="button"
      // Disabled until mounted rather than hidden: a control that appears a moment after the page
      // does is a control the reader's cursor misses.
      disabled={!ready}
      onClick={() => {
        if (items === null) return;
        writeWatchlist(toggle(items, symbol, name));
      }}
      className="border-border rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
      aria-pressed={ready ? saved : undefined}
    >
      {!ready ? "Watchlist" : saved ? "Saved — remove" : "Save to watchlist"}
    </button>
  );
}
