"use client";

import { useEffect, useState } from "react";
import { readWatchlist, toggle, writeWatchlist, WATCHLIST_EVENT } from "./storage";

/// Save or unsave one instrument, from wherever that instrument is being read.
///
/// Rendered on the asset screen, which is a server component: this is the one client island in the
/// browse path and it holds no data of its own beyond the saved list.
///
/// It renders its neutral state on the server and corrects itself after mount. The saved list is
/// in `localStorage`, which the server cannot see, so a button that claimed "Saved" in the HTML
/// would be guessing -- and guessing wrong is a hydration mismatch. `ready` is what keeps the two
/// renders identical: before mount nobody is told anything, after mount the button states the
/// truth for this browser.
export function SaveButton({ symbol, name }: { symbol: string; name: string }) {
  const [saved, setSaved] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => setSaved(readWatchlist().some((i) => i.symbol === symbol));
    sync();
    setReady(true);
    // Both events: `storage` for another tab, the custom one for a save on this page.
    window.addEventListener("storage", sync);
    window.addEventListener(WATCHLIST_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(WATCHLIST_EVENT, sync);
    };
  }, [symbol]);

  return (
    <button
      type="button"
      // Disabled until mounted rather than hidden: a control that appears a moment after the page
      // does is a control the reader's cursor misses.
      disabled={!ready}
      onClick={() => {
        const next = toggle(readWatchlist(), symbol, name);
        writeWatchlist(next);
        setSaved(next.some((i) => i.symbol === symbol));
      }}
      className="border-border rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
      aria-pressed={ready ? saved : undefined}
    >
      {!ready ? "Watchlist" : saved ? "Saved — remove" : "Save to watchlist"}
    </button>
  );
}
