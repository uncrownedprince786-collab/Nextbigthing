/// The preview interface's preferences, held in this browser.
///
/// Same position as `app/preview/watchlist/storage.ts`, taken for the same reason: the schema has
/// no `Preference` model and the project has no identity subsystem, so a stored preference has
/// nowhere to belong to. These live in `localStorage` and every surface that reads them says so.
///
/// Only preferences the interface can actually honour are offered — a settings screen listing
/// switches that do nothing is worse than one with switches that work, so each key here has a
/// reader: `recentFirst` and `verboseProvenance` are both consumed by
/// `app/preview/watchlist/WatchlistClient.tsx`.

const PREFS_KEY = "nbt.preview.prefs.v1";

export const PREFS_EVENT = "nbt:prefs-changed";

export interface Prefs {
  /// Order the watchlist by when each instrument was saved rather than alphabetically.
  recentFirst: boolean;
  /// Show each figure's source and full timestamp inline rather than only under the date.
  verboseProvenance: boolean;
}

export const DEFAULT_PREFS: Prefs = { recentFirst: true, verboseProvenance: false };

export function readPrefs(): Prefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(PREFS_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return DEFAULT_PREFS;
    const p = parsed as Partial<Prefs>;
    return {
      recentFirst: typeof p.recentFirst === "boolean" ? p.recentFirst : DEFAULT_PREFS.recentFirst,
      verboseProvenance:
        typeof p.verboseProvenance === "boolean" ? p.verboseProvenance : DEFAULT_PREFS.verboseProvenance,
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function writePrefs(prefs: Prefs): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Blocked or full storage: the switch still reflects this page view, and the next read
    // returns what was last stored. Nothing here is important enough to warn about.
  }
  try {
    window.dispatchEvent(new CustomEvent(PREFS_EVENT));
  } catch {
    // CustomEvent is unavailable in no browser this runs in; the guard costs nothing.
  }
}
