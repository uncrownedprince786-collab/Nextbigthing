/// The watchlist's storage, and the reason it is `localStorage` and not a table.
///
/// `prisma/schema.prisma` has no `User`, `Account`, `Session`, `Watchlist` or `Preference` model,
/// and `package.json` has no auth dependency. Every page in this project is anonymous and
/// read-only. A server-side watchlist is therefore not a screen -- it is an auth provider, session
/// handling, user-scoped tables, migrations and a privacy position for stored user data, which
/// `WORKSTREAMS-2026-10-17.md` §0 records as the single largest undeclared item in the UI
/// workstream and says should be decided deliberately rather than absorbed.
///
/// So the list lives in this browser. That ships the flow, defers the subsystem, and is honest
/// with the reader about where their list is -- which is why every surface that shows the list
/// also says it is device-local. It does not sync, it does not survive clearing site data, and it
/// is not visible to the server. Saying so is the feature; a watchlist that quietly lived in one
/// browser while looking like an account would be the dishonest version.

/// One saved instrument. `symbol` is the key the asset routes take; `name` is carried so the list
/// can render without a lookup, and `addedAt` is an ISO instant so the list can be ordered by when
/// the reader saved each one rather than alphabetically.
export interface SavedItem {
  symbol: string;
  name: string;
  addedAt: string;
}

export const WATCHLIST_KEY = "nbt.preview.watchlist.v1";

/// Browser storage throws rather than returning null in a private window, with site data blocked,
/// and during the thumbnail capture the host runs over published pages. Every read and write here
/// is therefore wrapped, and a failure is the empty list rather than a crash: a watchlist that
/// cannot be stored is a degraded screen, not a broken site.
export function readWatchlist(): SavedItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(WATCHLIST_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Anything in storage is data this code did not write in this session -- another tab, an older
    // version of this page, or a reader editing it by hand. Each row is checked rather than cast.
    return parsed.filter(
      (x): x is SavedItem =>
        Boolean(x) &&
        typeof x === "object" &&
        typeof (x as SavedItem).symbol === "string" &&
        typeof (x as SavedItem).name === "string" &&
        typeof (x as SavedItem).addedAt === "string",
    );
  } catch {
    return [];
  }
}

export function writeWatchlist(items: SavedItem[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items));
  } catch {
    // Storage is full, blocked, or unavailable. The in-memory list stays correct for this page
    // view and the next read returns what was last stored, which is the honest degradation.
  }
  // Same-tab listeners: the `storage` event fires in *other* tabs only, so a save on this page
  // would not reach a watchlist rendered beside it without this.
  try {
    window.dispatchEvent(new CustomEvent(WATCHLIST_EVENT));
  } catch {
    // CustomEvent is unavailable in no browser this runs in; the guard costs nothing.
  }
}

export const WATCHLIST_EVENT = "nbt:watchlist-changed";

export function isSaved(items: SavedItem[], symbol: string): boolean {
  return items.some((i) => i.symbol === symbol);
}

/// Add or remove, returning the new list. Adding an instrument already saved is a no-op rather
/// than a duplicate row, and the added instant of the existing entry is kept.
export function toggle(items: SavedItem[], symbol: string, name: string): SavedItem[] {
  if (isSaved(items, symbol)) return items.filter((i) => i.symbol !== symbol);
  return [...items, { symbol, name, addedAt: new Date().toISOString() }];
}
